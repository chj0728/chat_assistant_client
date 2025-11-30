/**
 * YMrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-03-07.
 */

#pragma once

#include <chrono>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include <ymrobot_msgs/srv/up_limb.hpp>
#include <ymrobot_msgs/action/up_climb_action.hpp>

namespace ymrobot
{
    using GoalUpClimbFixedAction = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::UpClimbAction>;

    class UpClimbActionNode : public rclcpp::Node
    {
    public:
        UpClimbActionNode();
        //~UpClimbActionNode();

    private:
        void Init();

        void InitParams();
        void CreateActionServer();

        rclcpp_action::GoalResponse UpClimbFixedActionHandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::UpClimbAction::Goal> goal); // 执行上肢动作
        rclcpp_action::CancelResponse UpClimbFixedActionHandleCancel(const std::shared_ptr<GoalUpClimbFixedAction> goal_handle);
        void UpClimbFixedActionHandleAccepted(const std::shared_ptr<GoalUpClimbFixedAction> goal_handle);
        void UpClimbFixedActionExecute(const std::shared_ptr<GoalUpClimbFixedAction> goal_handle);

    private:
        rclcpp::Logger logger_{rclcpp::get_logger("up_climb_action_node")};

        rclcpp::Client<ymrobot_msgs::srv::UpLimb>::SharedPtr up_limb_srv_client_;
        rclcpp_action::Server<ymrobot_msgs::action::UpClimbAction>::SharedPtr up_climb_fixed_action_server_{};

        // config
        std::string up_limb_srv_name_;
        std::string up_climb_fixed_action_name_;
        int service_wait_over_time_;

        int wait_service_time_;
        bool is_service_online_;
    };
}