#include "up_climb_action_node.hpp"

namespace ymrobot
{
    UpClimbActionNode::UpClimbActionNode() : Node("up_climb_action_node")
    {
        Init();
    }

    void UpClimbActionNode::Init()
    {
        InitParams();
        CreateActionServer();
    }

    void UpClimbActionNode::InitParams()
    {
        wait_service_time_ = 0;
        is_service_online_ = true;

        this->declare_parameter("up_limb_srv_name", "");
        this->declare_parameter("up_climb_fixed_action_name", "");
        this->declare_parameter("service_wait_over_time", 5);

        up_limb_srv_name_ = this->get_parameter("up_limb_srv_name").as_string();
        up_climb_fixed_action_name_ = this->get_parameter("up_climb_fixed_action_name").as_string();
        service_wait_over_time_ = this->get_parameter("service_wait_over_time").as_int();
    }

    void UpClimbActionNode::CreateActionServer()
    {
        up_limb_srv_client_ = this->create_client<ymrobot_msgs::srv::UpLimb>(up_limb_srv_name_);
        up_climb_fixed_action_server_ = rclcpp_action::create_server<ymrobot_msgs::action::UpClimbAction>(
            this,
            up_climb_fixed_action_name_,
            std::bind(&UpClimbActionNode::UpClimbFixedActionHandleGoal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&UpClimbActionNode::UpClimbFixedActionHandleCancel, this, std::placeholders::_1),
            std::bind(&UpClimbActionNode::UpClimbFixedActionHandleAccepted, this, std::placeholders::_1));
    }

    rclcpp_action::GoalResponse UpClimbActionNode::UpClimbFixedActionHandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::UpClimbAction::Goal> goal)
    {
        RCLCPP_INFO(this->get_logger(), "收到执行上肢预设动作请求");
        (void)uuid;
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse UpClimbActionNode::UpClimbFixedActionHandleCancel(const std::shared_ptr<GoalUpClimbFixedAction> goal_handle)
    {
        RCLCPP_INFO(this->get_logger(), "收到取消上肢预设动作请求");
        (void)goal_handle;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void UpClimbActionNode::UpClimbFixedActionHandleAccepted(const std::shared_ptr<GoalUpClimbFixedAction> goal_handle)
    {
        std::thread{std::bind(&UpClimbActionNode::UpClimbFixedActionExecute, this, std::placeholders::_1), goal_handle}.detach();
    }

    void UpClimbActionNode::UpClimbFixedActionExecute(const std::shared_ptr<GoalUpClimbFixedAction> goal_handle)
    {
        const auto goal = goal_handle->get_goal();
        RCLCPP_INFO(this->get_logger(), "开始执行上肢预设动作");

        // result->success = true;
        // result->message = "上肢预设动作执行成功";
        // goal_handle->succeed(result);

        auto result = std::make_shared<ymrobot_msgs::action::UpClimbAction::Result>();
        auto feedback = std::make_shared<ymrobot_msgs::action::UpClimbAction::Feedback>();

        auto request = std::make_shared<ymrobot_msgs::srv::UpLimb::Request>();
        request->up_limb_task_type = 2; // 执行上肢预设动作变化
        request->action_fixed = goal->action_fixed;

        while (!up_limb_srv_client_->wait_for_service(std::chrono::seconds(1)))
        {
            if (!rclcpp::ok())
            {
                RCLCPP_ERROR(this->get_logger(), "等待服务的过程中被打断...");
            }

            if (wait_service_time_ >= (int)service_wait_over_time_)
            {
                RCLCPP_INFO(this->get_logger(), "等待上臂服务端上线超时,超过 %d s", service_wait_over_time_);
                wait_service_time_ = 0;
                is_service_online_ = false;
                break;
            }

            wait_service_time_++;
            RCLCPP_INFO(this->get_logger(), "等待上臂服务端上线中");
        }

        if (!is_service_online_)
        {
            result->success = false;
            result->message = "等待上臂服务端上线超时";
            goal_handle->abort(result);
            is_service_online_ = true;
            RCLCPP_ERROR(this->get_logger(), "等待上臂服务端上线超时");
            return;
        }

        auto future = up_limb_srv_client_->async_send_request(request);
        future.wait(); // 使用这阻塞会不会造成问题 有待验证

        if (future.get()->success)
        {
            result->success = true;
            result->message = "上肢预设动作执行成功";
            goal_handle->succeed(result);
            RCLCPP_INFO(this->get_logger(), "[%d]上肢预设动作执行成功", goal->action_fixed);
        }
        else
        {
            result->success = false;
            result->message = "上肢预设动作执行失败";
            goal_handle->abort(result);
            RCLCPP_ERROR(this->get_logger(), "[%d]上肢预设动作执行失败", goal->action_fixed);
        }
    }

}

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<ymrobot::UpClimbActionNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}