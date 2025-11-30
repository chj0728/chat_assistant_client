#include <chrono>
#include <functional>
#include <memory>
#include <string>
#include <serial/serial.h>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"
#include "ymrobot_msgs/msg/aoa_position.hpp"
#include "ymrobot_msgs/msg/cloud_chassis_status.hpp"

namespace ymrobot{

  class AoaTracking : public rclcpp::Node
  {
    public:
      AoaTracking();
      int16_t bytesToInt16(const uint8_t* bytes, bool little_endian);
      uint16_t bytesToUInt16(const uint8_t* bytes, bool little_endian);
      uint32_t bytesToUInt32(const uint8_t* bytes, bool little_endian);
      void processSingleFrame(const std::string& frame);
      bool isValidFrame(const std::string& frame);
      void processSerial1Data(const uint8_t* data, size_t length);
      void pubAoaData();
    
    private:
      void chissis_status_callback(const ymrobot_msgs::msg::CloudChassisStatus & msg);
      bool InitSerial();
      
    
    private:
      float_t chissis_x = 0.0;
      float_t chissis_y = 0.0;
      float_t chissis_yaw = 0.0;
      serial::Serial serial1_;
      serial::Serial serial2_;
      rclcpp::TimerBase::SharedPtr timer_;
      rclcpp::Publisher<ymrobot_msgs::msg::AoaPosition>::SharedPtr publisher_;
      rclcpp::Subscription<ymrobot_msgs::msg::CloudChassisStatus>::SharedPtr chissis_status_subscription_;
  };
}
