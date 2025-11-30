#ifndef LOG_UPLOADER_HPP
#define LOG_UPLOADER_HPP

#include <filesystem>
#include <string>
#include <vector>
#include <chrono>
#include <memory>
#include <curl/curl.h>
#include <openssl/md5.h>
#include <zip.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/string.hpp>

#include <ymrobot_msgs/action/log_update.hpp>

namespace fs = std::filesystem;

namespace ymrobot
{
    using GoalHandleLogUpdate = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::LogUpdate>;

    class LogUploader : public rclcpp::Node
    {
    public:
        LogUploader();

    private:
        void Init();
        void InitParams();
        void CreateSubActions();

        void UploadFileTask(const std::string &file_path); // 上传文件
        void trigger_upload_on_startup();                  // 上传日志流程
        void process_and_upload();                         // 处理并上传日志的主流程

        bool is_network_available();                                   // 检查网络是否可用
        bool check_log_dir();                                          // 检查日志文件夹是否存在
        std::string get_latest_log_folder();                           // 获取最新时间日志文件夹 , 如果失败返回空字符串
        std::string compress_logs(const std::string &log_folder_path); // 压缩指定的日志文件夹为zip文件
        std::string generate_signature(const std::string &timestamp);  // 生成签名: md5(robotId + timestamp + token)
        bool upload_file(const std::string &file_path);                // 通过HTTP上传文件  要上传的文件路径
        std::string get_current_timestamp();                           // 当前时间戳字符串(格式: YYYYMMDD_HHMMSS)

        static size_t write_callback(void *contents, size_t size, size_t nmemb, void *userp); // CURL写回调函数
        std::string md5_hash(const std::string &input);                                       // 计算字符串的MD5哈希值

        rclcpp_action::GoalResponse LogUpdateHandleGoal(const rclcpp_action::GoalUUID & /*uuid*/, std::shared_ptr<const ymrobot_msgs::action::LogUpdate::Goal> goal);
        rclcpp_action::CancelResponse LogUpdateHandleCancel(const std::shared_ptr<GoalHandleLogUpdate> goal_handle);
        void LogUpdateHandleAccepted(const std::shared_ptr<GoalHandleLogUpdate> goal_handle);
        void LogUpdateExecuteMove(const std::shared_ptr<GoalHandleLogUpdate> goal_handle);

        void upload_image_task_callback(const std_msgs::msg::String::SharedPtr msg);      // 上传图像任务回调函数

    private:
        // 配置参数
        std::string log_dir_;                // 日志源目录路径
        std::string temp_dir_;               // 临时工作目录路径
        std::string image_file_dir_;         // 图像文件存储目录
        std::string upload_url_;             // 运行日志上传接口URL
        std::string auth_token_;             // 运行日志授权token
        std::string image_upload_url_;       // 图像上传接口URL
        std::string image_auth_token_;       // 图像日志授权token
        std::string video_upload_url_;       // 视频上传接口URL
        std::string video_auth_token_;       // 视频日志授权token
        std::string robot_id_;               // 机器人ID
        int max_retries_;                    // 最大重试次数
        int retry_interval_;                 // 重试间隔(秒)
        int network_check_timeout_;          // 网络检查超时时间(秒)
        std::string network_check_url_;      // 网络检查地址
        std::string log_update_action_name_; // 日志
        std::string image_update_topic_name_;

        rclcpp_action::Server<ymrobot_msgs::action::LogUpdate>::SharedPtr log_update_action_server_{};
        rclcpp::Subscription<std_msgs::msg::String>::SharedPtr upload_image_task_sub_{}; // 上传图像任务订阅
    };
}

#endif // LOG_UPLOADER_HPP