#include <iostream>
#include <chrono>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <ymrobot_msgs/action/camera_function.hpp>

#include <cv_bridge/cv_bridge.h>
#include <opencv2/opencv.hpp>

namespace ymrobot
{
    using GoalHandleSaveMedia = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::CameraFunction>;
    class CameraFunctionNode : public rclcpp::Node
    {
    public:
        CameraFunctionNode();
        // ~CameraFunctionNode();

    private:
        void Init();
        void InitParams();
        void CreatePubSub();

        void ImageSubCallback(const sensor_msgs::msg::Image::SharedPtr msg);

        rclcpp_action::GoalResponse CameraFunctionHandleGoal(const rclcpp_action::GoalUUID & /*uuid*/, std::shared_ptr<const ymrobot_msgs::action::CameraFunction::Goal> goal);
        rclcpp_action::CancelResponse CameraFunctionHandleCancel(const std::shared_ptr<GoalHandleSaveMedia> goal_handle);
        void CameraFunctionHandleAccepted(const std::shared_ptr<GoalHandleSaveMedia> goal_handle);
        void CameraFunctionExecuteMove(const std::shared_ptr<GoalHandleSaveMedia> goal_handle);

        std::string GetFileName(const std::string& dir, const std::string& prefix, const std::string& extension, bool use_timestamp = true); // 生成带时间戳的文件名 true是使用时间  false是使用序列号
    private:
        // config
        std::string image_sub_name_;
        std::string cemera_action_server_name_ ;
        std::string default_image_path_; //图像默认保存路径
        std::string video_default_path_; // 视频默认保存路径
        int default_video_fps_;   //
        
        //
        rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_{};
        rclcpp_action::Server<ymrobot_msgs::action::CameraFunction>::SharedPtr camera_function_server_;  // Action服务器

        std::shared_mutex image_mutex_;

        sensor_msgs::msg::Image::SharedPtr last_image_;  // 存储最新图像
    };
}