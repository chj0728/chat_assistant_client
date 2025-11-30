/*
    * 根据当前agv的坐标数据，信标的方位角和仰角计算信标在云迹底盘地图上的xy坐标和角度
*/

#include "aoa_tracking_node.hpp"

namespace ymrobot{
  using namespace std::chrono_literals;

  AoaTracking::AoaTracking()
  : Node("aoa_tracking")
  {
    if (!InitSerial())
    {
      RCLCPP_ERROR(this->get_logger(), "连接串口失败！！！");
    }
    chissis_status_subscription_ = this->create_subscription<ymrobot_msgs::msg::CloudChassisStatus>(
      "cloud_chassis_status_info",
      2,
      std::bind(&AoaTracking::chissis_status_callback, this, std::placeholders::_1)
    );
    timer_ = this->create_wall_timer(
        2s, std::bind(&AoaTracking::pubAoaData, this));
  }

  bool AoaTracking::InitSerial()
  {
    try {
          serial1_.setPort("/dev/ttyUSB0");
          serial1_.setBaudrate(115200);
          serial::Timeout timeout1 = serial::Timeout::simpleTimeout(1000);
          serial1_.setTimeout(timeout1);
          serial1_.open();
          RCLCPP_INFO(this->get_logger(), "Serial port 1 opened successfully");
    } catch (const std::exception& e) {
        RCLCPP_ERROR(this->get_logger(), "Failed to open serial port 1: %s", e.what());
    }
    try {
          serial2_.setPort("/dev/ttyUSB1");
          serial2_.setBaudrate(115200);
          serial::Timeout timeout2 = serial::Timeout::simpleTimeout(1000);
          serial2_.setTimeout(timeout2);
          serial2_.open();
          RCLCPP_INFO(this->get_logger(), "Serial port 2 opened successfully");
    } catch (const std::exception& e) {
        RCLCPP_ERROR(this->get_logger(), "Failed to open serial port 2: %s", e.what());
        return false;
    }
    return true;
  }

  void AoaTracking::pubAoaData()
  {
    if (serial1_.isOpen()) {
      try {
          size_t bytes_available = serial1_.available();
          if (bytes_available > 0) {
              std::vector<uint8_t> buffer(bytes_available);
              size_t bytes_read = serial1_.read(buffer.data(), bytes_available);
              
              if (bytes_read > 0) {
                  // 处理接收到的数据
                  processSerial1Data(buffer.data(), bytes_read);
              }
          }
      } catch (const std::exception& e) {
          RCLCPP_ERROR(this->get_logger(), "Error reading from serial port 1: %s", e.what());
      }
    }
    else if (serial2_.isOpen()){
      try {
          size_t bytes_available = serial2_.available();
          if (bytes_available > 0) {
            std::vector<uint8_t> buffer(bytes_available);
            size_t bytes_read = serial2_.read(buffer.data(), bytes_available);
            
            if (bytes_read > 0) {
                // 处理接收到的数据
                processSerial1Data(buffer.data(), bytes_read);
            }
          }
      } catch (const std::exception& e) {
          RCLCPP_ERROR(this->get_logger(), "Error reading from serial port 2: %s", e.what());
      }
    }
  }

  void AoaTracking::processSerial1Data(const uint8_t* data, size_t length)
  {
    static std::string buffer;
    buffer.append(reinterpret_cast<const char*>(data), length);
    
    // 直接从缓冲区末尾开始查找最后一个帧头
    size_t frame_start = buffer.find("\xFF\xFF\xFF\xFF");
    
    if (frame_start == std::string::npos) {
        buffer.clear();  // 没有帧头，清空缓冲区
        return;
    }
    
    // 检查是否有足够的数据读取长度字段
    if (buffer.size() < frame_start + 6) {
        buffer.clear();  // 数据不足，清空缓冲区
        RCLCPP_WARN(this->get_logger(), "数据不足");
        return;
    }
    
    // 读取帧长度（大端序）
    uint8_t length_high = static_cast<uint8_t>(buffer[frame_start + 4]);
    uint8_t length_low = static_cast<uint8_t>(buffer[frame_start + 5]);
    uint16_t frame_length = (length_high << 8) | length_low;
    
    // 快速验证帧长度
    if (frame_length < 6 || frame_length > 200) {
        buffer.clear();  // 无效长度，清空缓冲区
        RCLCPP_WARN(this->get_logger(), "无效长度");
        return;
    }
    
    // 检查是否有完整的帧数据
    if (buffer.size() < frame_start + frame_length) {
        RCLCPP_INFO(this->get_logger(), "数据不完整");
        buffer.clear();  // 数据不完整，清空缓冲区
        return;
    }
    
    // 提取最新帧
    std::string latest_frame = buffer.substr(frame_start, frame_length);
    
    if (isValidFrame(latest_frame)) {
        processSingleFrame(latest_frame);
        RCLCPP_DEBUG(this->get_logger(), "处理最新一帧，长度: %u 字节", frame_length);
    } else {
        RCLCPP_WARN(this->get_logger(), "最新帧验证失败");
    }
    
    // 清空缓冲区
    buffer.clear();
  }

  void AoaTracking::chissis_status_callback(const ymrobot_msgs::msg::CloudChassisStatus & msg)
  {
    this->chissis_x = msg.x;
    this->chissis_y = msg.y;
    this->chissis_yaw = msg.yaw;
    RCLCPP_INFO(this->get_logger(), "接收到chissis数据 : x: '%f', y: '%f', yaw: '%f'", this->chissis_x, this->chissis_y, this->chissis_yaw);
  }

  bool AoaTracking::isValidFrame(const std::string& frame)
  {
    // 检查帧长度
    if (frame.size() != 37) {
        RCLCPP_WARN(this->get_logger(), "Invalid frame length: %zu bytes, expected 37", frame.size());
        return false;
    }

    // 将字符串转换为uint8_t数组以便处理
    const uint8_t* frame_data = reinterpret_cast<const uint8_t*>(frame.data());

    // 检查帧头（4字节连续的0xFF）
    if (frame_data[0] != 0xFF || frame_data[1] != 0xFF || 
        frame_data[2] != 0xFF || frame_data[3] != 0xFF) {
        RCLCPP_WARN(this->get_logger(), "Invalid frame header: %02X %02X %02X %02X", 
                  frame_data[0], frame_data[1], frame_data[2], frame_data[3]);
        return false;
    }

    // 检查异或校验
    uint8_t calculated_xor = 0;
    for (size_t i = 0; i < 36; ++i) {
        calculated_xor ^= frame_data[i];
    }

    if (calculated_xor != frame_data[36]) {
        RCLCPP_WARN(this->get_logger(), "XOR checksum failed: calculated 0x%02X, received 0x%02X", 
                  calculated_xor, frame_data[36]);
        return false;
    }

    return true;
  }

  void AoaTracking::processSingleFrame(const std::string& frame)
  {
    const uint8_t* frame_data = reinterpret_cast<const uint8_t*>(frame.data());

    try {
        // 解析距离（4字节，小端序）：偏移量16-19字节
        uint32_t distance_raw = bytesToUInt32(&frame_data[20], false);
        float distance = static_cast<float>(distance_raw) / 100.0;  // 厘米

        // 解析方位角（2字节，有符号小端序）：偏移量20-21字节
        int16_t azimuth_raw = bytesToInt16(&frame_data[24], false);
        float azimuth = static_cast<float>(azimuth_raw);

        // 解析仰角（2字节，有符号小端序）：偏移量22-23字节
        int16_t elevation_raw = bytesToInt16(&frame_data[26], false);
        float elevation = static_cast<float>(elevation_raw);

        // 角度转弧度
        double azimuth_rad = azimuth * M_PI / 180.0;  // 方位角
        double elevation_rad = elevation * M_PI / 180.0;  // 仰角

        RCLCPP_INFO(this->get_logger(), "AOA数据: 距离=%.3fm, 方位角=%.2f(rad), 仰角=%.2f(rad)",
                    distance, azimuth_rad, elevation_rad);

        double relative_x = this->chissis_x + (distance * cos(elevation_rad) * cos(this->chissis_yaw - azimuth_rad));
        double relative_y = this->chissis_y + (distance * cos(elevation_rad) * sin(this->chissis_yaw - azimuth_rad));
        double relative_yaw = this->chissis_yaw + azimuth_rad;    // 云迹底盘的坐标是以x轴正向作为0度，然后逆时针转作为正方向

        RCLCPP_INFO(this->get_logger(), "计算出来的坐标信息：(%0.2f, %0.2f, %0.2f)", relative_x, relative_y, relative_yaw);
        auto aoa_msg = ymrobot_msgs::msg::AoaPosition();
        aoa_msg.x = relative_x;
        aoa_msg.y = relative_y;
        aoa_msg.yaw = relative_yaw;
        this->publisher_ = this->create_publisher<ymrobot_msgs::msg::AoaPosition>("aoa_position", 1);
        this->publisher_->publish(aoa_msg);

    } catch (const std::exception& e) {
        RCLCPP_ERROR(this->get_logger(), "Error parsing frame: %s", e.what());
    }
  }

  uint16_t AoaTracking::bytesToUInt16(const uint8_t* bytes, bool little_endian)
  {
      if (little_endian) {
          return (bytes[1] << 8) | bytes[0];
      } else {
          return (bytes[0] << 8) | bytes[1];
      }
  }

  int16_t AoaTracking::bytesToInt16(const uint8_t* bytes, bool little_endian)
  {
      uint16_t raw = bytesToUInt16(bytes, little_endian);
      return *reinterpret_cast<const int16_t*>(&raw);
  }

  uint32_t AoaTracking::bytesToUInt32(const uint8_t* bytes, bool little_endian)
  {
      if (little_endian) {
          return (bytes[3] << 24) | (bytes[2] << 16) | (bytes[1] << 8) | bytes[0];
      } else {
          return (bytes[0] << 24) | (bytes[1] << 16) | (bytes[2] << 8) | bytes[3];
      }
  }


}

int main(int argc, char * argv[])
  {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<ymrobot::AoaTracking>());
    rclcpp::shutdown();
    return 0;
  }