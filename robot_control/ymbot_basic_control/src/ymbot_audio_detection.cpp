// #include "rclcpp/rclcpp.hpp"
// #include "std_msgs/msg/bool.hpp"
// #include <pulse/pulseaudio.h>
// #include <atomic>
// #include <mutex>
// #include <thread>
// #include <iomanip>
// #include <ctime>

// class AudioOutputStatusNode : public rclcpp::Node
// {
// public:
//     AudioOutputStatusNode() : Node("audio_output_status_node")
//     {
//         // 创建发布器
//         audio_status_pub_ = this->create_publisher<std_msgs::msg::Bool>("sound_detected", 10);
        
//         // 初始化PulseAudio
//         init_pulseaudio();
        
//         // 创建定时器，以10Hz的频率检查音频状态
//         timer_ = this->create_wall_timer(
//             std::chrono::milliseconds(100),
//             [this]() {
//                 std_msgs::msg::Bool msg;
//                 msg.data = audio_playing_.load();
//                 audio_status_pub_->publish(msg);
                
//                 // 可选：记录状态变化
//                 if (msg.data != last_status_) {
//                     auto now = std::chrono::system_clock::now();
//                     auto now_c = std::chrono::system_clock::to_time_t(now);
//                     std::ostringstream oss;
//                     oss << "[" << std::put_time(std::localtime(&now_c), "%T") 
//                         << "] 音频状态: " << (msg.data ? "开始" : "停止");
//                     RCLCPP_INFO(this->get_logger(), "%s", oss.str().c_str());
//                     last_status_ = msg.data;
//                 }
//             });
//     }
    
//     ~AudioOutputStatusNode() {
//         // 清理PulseAudio资源
//         if (context_) {
//             pa_context_disconnect(context_);
//             pa_context_unref(context_);
//         }
//         if (mainloop_) {
//             pa_mainloop_free(mainloop_);
//         }
//     }

// private:
//     void init_pulseaudio() {
//         // 创建主循环和上下文
//         mainloop_ = pa_mainloop_new();
//         pa_mainloop_api *api = pa_mainloop_get_api(mainloop_);
//         context_ = pa_context_new(api, "audio_output_status");
        
//         // 设置状态回调
//         pa_context_set_state_callback(context_, [](pa_context* c, void* userdata) {
//             auto self = static_cast<AudioOutputStatusNode*>(userdata);
//             switch (pa_context_get_state(c)) {
//                 case PA_CONTEXT_READY:
//                     RCLCPP_INFO(self->get_logger(), "PulseAudio连接就绪");
//                     self->setup_monitoring();
//                     break;
//                 case PA_CONTEXT_FAILED:
//                     RCLCPP_ERROR(self->get_logger(), "PulseAudio连接失败");
//                     break;
//                 case PA_CONTEXT_TERMINATED:
//                     RCLCPP_INFO(self->get_logger(), "PulseAudio连接终止");
//                     break;
//                 default:
//                     break;
//             }
//         }, this);
        
//         // 连接PulseAudio服务器
//         pa_context_connect(context_, nullptr, PA_CONTEXT_NOFLAGS, nullptr);
        
//         // 启动PulseAudio处理线程
//         mainloop_thread_ = std::thread([this]() {
//             int ret;
//             if (pa_mainloop_run(mainloop_, &ret) < 0) {
//                 RCLCPP_ERROR(this->get_logger(), "PulseAudio主循环错误: %d", ret);
//             }
//         });
//     }
    
//     void setup_monitoring() {
//         // 获取默认sink名称
//         pa_operation* op = pa_context_get_server_info(context_, [](pa_context* c, const pa_server_info* i, void* userdata) {
//             if (!i) return;
            
//             auto self = static_cast<AudioOutputStatusNode*>(userdata);
//             self->default_sink_ = i->default_sink_name;
//             RCLCPP_INFO(self->get_logger(), "默认音频输出设备: %s", self->default_sink_.c_str());
            
//             // 开始监控默认sink
//             self->update_audio_status();
//         }, this);
//         pa_operation_unref(op);
//     }
    
//     void update_audio_status() {
//         if (default_sink_.empty()) return;
        
//         pa_operation* op = pa_context_get_sink_info_by_name(
//             context_, 
//             default_sink_.c_str(), 
//             [](pa_context* c, const pa_sink_info* i, int eol, void* userdata) {
//                 if (eol || !i) return;
                
//                 auto self = static_cast<AudioOutputStatusNode*>(userdata);
                
//                 // 检测音频状态
//                 bool is_active = false;
//                 if (i->state == PA_SINK_RUNNING) {
//                     // 检查字节数是否在增加（表示有音频输出）
//                     static uint64_t last_bytes = 0;
//                     if (i->resample_bytes > last_bytes && last_bytes > 0) {
//                         is_active = true;
//                     }
//                     last_bytes = i->resample_bytes;
//                 }
                
//                 // 更新状态
//                 self->audio_playing_.store(is_active);
//             }, 
//             this);
//         pa_operation_unref(op);
//     }
    
//     // 定时更新音频状态
//     void check_audio_status() {
//         update_audio_status();
//     }

//     rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr audio_status_pub_;
//     rclcpp::TimerBase::SharedPtr timer_;
    
//     // PulseAudio相关资源
//     pa_context* context_ = nullptr;
//     pa_mainloop* mainloop_ = nullptr;
//     std::thread mainloop_thread_;
//     std::string default_sink_;
    
//     // 音频状态
//     std::atomic<bool> audio_playing_{false};
//     bool last_status_ = false;
// };

// int main(int argc, char** argv)
// {
//     rclcpp::init(argc, argv);
//     auto node = std::make_shared<AudioOutputStatusNode>();
//     rclcpp::spin(node);
//     rclcpp::shutdown();
//     return 0;
// }
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include <cstdio>
#include <cstring>
#include <unistd.h>

// 检查音频输出状态
bool is_audio_running() {
    std::string cmd = "pactl list sinks";
    FILE* fp = popen(cmd.c_str(), "r");
    if (fp == nullptr) {
        RCLCPP_ERROR(rclcpp::get_logger("audio_output_status_node"), "Failed to run pactl command");
        return false;
    }

    // 读取命令输出
    char buffer[512];
    bool is_running = false;
    while (fgets(buffer, sizeof(buffer), fp) != nullptr) {
        // 查找 "RUNNING" 状态
        if (strstr(buffer, "RUNNING") != nullptr) {
            is_running = true;
            break;
        }
    }

    pclose(fp);  // 使用 pclose 来关闭通过 popen 打开的流
    return is_running;
}

class AudioOutputStatusNode : public rclcpp::Node
{
public:
    AudioOutputStatusNode() : Node("audio_output_status_node")
    {
        // 创建发布器
        audio_status_pub_ = this->create_publisher<std_msgs::msg::Bool>("sound_detected", 10);
    }

    void check_audio_status()
    {
        // 检查音频状态
        bool audio_running = is_audio_running();
        
        // 发布音频状态
        std_msgs::msg::Bool msg;
        msg.data = audio_running;
        audio_status_pub_->publish(msg);
        
        // RCLCPP_INFO(this->get_logger(), "Audio output status: %s", audio_running ? "True" : "False");
    }

private:
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr audio_status_pub_;
};

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);

    auto node = std::make_shared<AudioOutputStatusNode>();
    
    rclcpp::Rate loop_rate(5);  // 设置频率为 5hz
    

    while (rclcpp::ok()) {
        node->check_audio_status();
        rclcpp::spin_some(node);  // 执行回调
        loop_rate.sleep();
    }

    rclcpp::shutdown();
    return 0;
}
// #include "rclcpp/rclcpp.hpp"
// #include "std_msgs/msg/bool.hpp"
// #include <chrono>

// using namespace std::chrono_literals;

// class AudioOutputStatusNode : public rclcpp::Node
// {
// public:
//     AudioOutputStatusNode() 
//     : Node("audio_output_status_node"),
//       last_msg_time_(this->now()),
//       last_sound_state_(false),
//       is_active_(false)
//     {
//         // 创建订阅器
//         sound_detected_sub_ = this->create_subscription<std_msgs::msg::Bool>(
//             "sound_detected", 10,
//             std::bind(&AudioOutputStatusNode::sound_detected_callback, this, std::placeholders::_1));
        
//         // 创建发布器
//         sound_data_pub_ = this->create_publisher<std_msgs::msg::Bool>("sound_data", 10);
        
//         // 创建定时器（10Hz）
//         timer_ = this->create_wall_timer(
//             100ms,  // 10Hz
//             std::bind(&AudioOutputStatusNode::timer_callback, this));
//     }

// private:
//     void sound_detected_callback(const std_msgs::msg::Bool::SharedPtr msg)
//     {
//         last_sound_state_ = msg->data;
//         last_msg_time_ = this->now();
        
//         // 当检测到声音时激活持续发布状态
//         if (msg->data) {
//             is_active_ = true;
//         }
//     }

//     void timer_callback()
//     {
//         auto now = this->now();
//         auto time_diff = now - last_msg_time_;
//         bool current_state = false;

//         // 检查是否超时（0.5秒未收到消息视为超时）
//         if (time_diff > 1000ms) {
//             is_active_ = false;  // 超时后停止持续发布
//         }

//         // 确定当前发布状态
//         if (is_active_) {
//             current_state = true;
//         } else {
//             // 如果收到false消息（非超时情况）
//             if (time_diff <= 1000ms && !last_sound_state_) {
//                 current_state = false;
//             }
//             // 超时情况也发布false
//             else if (time_diff > 1000ms) {
//                 current_state = false;
//             }
//         }

//         // 发布声音数据状态
//         std_msgs::msg::Bool msg;
//         msg.data = current_state;
//         sound_data_pub_->publish(msg);
        
//         RCLCPP_DEBUG(this->get_logger(), "Publishing sound_data: %s", 
//                      current_state ? "True" : "False");
//     }

//     rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sound_detected_sub_;
//     rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr sound_data_pub_;
//     rclcpp::TimerBase::SharedPtr timer_;
    
//     rclcpp::Time last_msg_time_;
//     bool last_sound_state_;
//     bool is_active_;  // 标记是否需要持续发布true
// };

// int main(int argc, char** argv)
// {
//     rclcpp::init(argc, argv);
//     auto node = std::make_shared<AudioOutputStatusNode>();
//     rclcpp::spin(node);
//     rclcpp::shutdown();
//     return 0;
// }