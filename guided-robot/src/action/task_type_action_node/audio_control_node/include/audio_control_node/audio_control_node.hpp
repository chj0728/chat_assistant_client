/**
 * YMrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-03-28.
 */

#pragma once

#include <chrono>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/string.hpp>

#include <ymrobot_msgs/msg/command.hpp>
#include <ymrobot_msgs/srv/audio.hpp>
#include <ymrobot_msgs/action/audio_control.hpp>

namespace ymrobot
{
    using GoalHandleAudio = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::AudioControl>;
    using namespace std::chrono_literals;

    enum class AudioTaskResult
    {
        RUNNING,   // 运行中
        SUCCESSED, // 失败
        FAILED     // 成功
    };

    class AudioControlNode : public rclcpp::Node
    {
    public:
        AudioControlNode();
        //~AudioControlNode();

    private:
        void Init();
        void InitParams();
        void CreateActionServer();

        rclcpp_action::GoalResponse AudioHandleGoal(const rclcpp_action::GoalUUID & /*uuid*/, std::shared_ptr<const ymrobot_msgs::action::AudioControl::Goal> goal);
        rclcpp_action::CancelResponse AudioHandleCancel(const std::shared_ptr<GoalHandleAudio> goal_handle);
        void AudioHandleAccepted(const std::shared_ptr<GoalHandleAudio> goal_handle);
        void AudioExecuteMove(const std::shared_ptr<GoalHandleAudio> goal_handle);

        void ModifyTimbreSubCallback(const std_msgs::msg::String::SharedPtr msg);                        // 修改音色订阅回调
        void AudioControlCallBack(rclcpp::Client<ymrobot_msgs::srv::Audio>::SharedFuture result_future); // 音频控制任务服务 回调函数

    private:
        rclcpp::Logger logger_{rclcpp::get_logger("audio_control_node")};

        // config
        std::string modify_timbre_sub_name_;
        std::string audio_action_server_name_;
        std::string audio_control_action_name_;
        int service_wait_over_time_; // 服务等待超时时间

        // action/ topic /service
        rclcpp::Subscription<std_msgs::msg::String>::SharedPtr modify_timbre_sub_{};                 // 修改音色订阅
        rclcpp::Client<ymrobot_msgs::srv::Audio>::SharedPtr audio_control_client_{};                 // 音频控制客户端
        rclcpp_action::Server<ymrobot_msgs::action::AudioControl>::SharedPtr audio_action_server_{}; // 语音交互action服务

        std::atomic<AudioTaskResult> is_audio_control_task_successed_{AudioTaskResult::RUNNING}; // 语音交互任务结果
        int wait_service_time_;                                                                  // 等待服务时间
    };
}