#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"
#include "nav2_behavior_tree/bt_action_node.hpp"
#include <ymrobot_msgs/msg/task.hpp>
#include <ymrobot_msgs/action/audio_control.hpp>
#include <ymrobot_msgs/msg/voice_message.hpp>
#include <ymrobot_msgs/srv/audio.hpp>
#include <ymrobot_msgs/msg/update_list.hpp>

namespace ymrobot
{
    class VoiceInteractionNode : public BT::SyncActionNode
    {
    public:
        VoiceInteractionNode(const std::string &xml_tag_name,
                             const BT::NodeConfiguration &conf);

        static BT::PortsList providedPorts()
        {
            return {
                BT::InputPort<ymrobot_msgs::msg::VoiceMessage>("voice_message"),
            };
        }

    private:
        BT::NodeStatus tick() override;

    private:
        rclcpp::Node::SharedPtr node_;
        rclcpp::Publisher<ymrobot_msgs::msg::UpdateList>::SharedPtr auido_update_pub_{}; // 控制模式发布topic
        rclcpp::Client<ymrobot_msgs::srv::Audio>::SharedPtr audio_control_client_{};     // 音频控制客户端
        rclcpp::Logger logger_{rclcpp::get_logger("VoiceInteractionNode")};              // 解析任务节点
    };
}
