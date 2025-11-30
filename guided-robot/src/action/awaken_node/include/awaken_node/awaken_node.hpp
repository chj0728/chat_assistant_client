#include <iostream>
#include <thread>
#include <mutex>

#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/bool.hpp>

namespace ymrobot
{
    class AwakenNode : public rclcpp::Node
    {
    public:
        AwakenNode();
        ~AwakenNode();

    private:
        void Init();
        void CreateSubPub();
        void InitParams();

        void CheckIfPersonNearby();

        void OnAwakenSubCallback(const std_msgs::msg::Bool::SharedPtr msg);
        void IsPersonNearbyTimerCallback(const std_msgs::msg::Bool::SharedPtr msg);

    private:
        rclcpp::TimerBase::SharedPtr awaken_timer_{}; // 唤醒定时器

        // config
        std::string awaken_pub_name_;
        std::string awaken_sub_name_;
        std::string is_person_nearby_sub_name_;

        // sub pub
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr awaken_pub_{};              // 有人靠近发布者 pub
        rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr awaken_sub_{};           // 是否开启自动唤醒
        rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr is_person_nearby_sub_{}; // 是否有人靠近sub

        std::atomic<bool> is_open_active_wake_up_{false}; // 是否开启自动唤醒
        std::atomic<bool> is_person_nearby_{false};       // 是否有人靠近
    };
}