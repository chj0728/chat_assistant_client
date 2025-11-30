#include "awaken_node.hpp"

namespace ymrobot
{
    AwakenNode::AwakenNode() : Node("awaken_node")
    {
    }

    AwakenNode::~AwakenNode()
    {
    }

    void AwakenNode::Init()
    {
        awaken_timer_ = this->create_wall_timer(std::chrono::seconds(1), std::bind(&AwakenNode::CheckIfPersonNearby, this)); // 唤醒定时器
    }

    void AwakenNode::CreateSubPub()
    {
    }

    void AwakenNode::CheckIfPersonNearby()
    {
        if (!is_open_active_wake_up_.load())
        {
            return;
        }

        if(!is_person_nearby_.load())
        {
            return;
        }

        std_msgs::msg::Bool msg;
        msg.data = true;
        awaken_pub_->publish(msg); // 发布唤醒指令
    }

    void AwakenNode::OnAwakenSubCallback(const std_msgs::msg::Bool::SharedPtr msg)
    {
        auto is_open_active_wake_up = msg->data;
        if (is_open_active_wake_up)
        {
            RCLCPP_INFO(this->get_logger(), "启用自动唤醒");
            is_open_active_wake_up_.store(true);
        }
    }

    void AwakenNode::IsPersonNearbyTimerCallback(const std_msgs::msg::Bool::SharedPtr msg)
    {
        if(msg->data)
        {
            is_person_nearby_.store(true);
        }
    }
}