/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 25-02-13.
 */
#include "amr_behavior_tree/plugins/action/play_fixed_audio_node.hpp"

namespace ymrobot
{
    PlayFixedAudioNode::PlayFixedAudioNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::AudioControl>(xml_tag_name, action_name,
                                                                                                                                                                                                                  conf)
    {
    }

    void PlayFixedAudioNode::on_tick()
    {
        if (!getInput<std::string>("fixed_audio", goal_.fixed_audio_name))
        {
            // RCLCPP_ERROR(node_->get_logger(), "[play_fixed_audio_node[fixed_aud_name is null]Failure.");
            throw BT::RuntimeError("[play_fixed_audio_node]Missing required input [play_fixed_audio_node]");
        }
        goal_.audio_task_type = 0; // 播放固定音频
    }

    BT::NodeStatus PlayFixedAudioNode::on_aborted()
    {
        RCLCPP_ERROR(node_->get_logger(), "[play_fixed_audio_node]Failure.");
        return BT::NodeStatus::FAILURE;
    }

    BT::NodeStatus PlayFixedAudioNode::on_success()
    {
        RCLCPP_INFO(node_->get_logger(), "[play_fixed_audio_node]Success.");
        return BT::NodeStatus::SUCCESS;
    }

}

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
    BT::NodeBuilder builder = [](const std::string &name,
                                 const BT::NodeConfiguration &config)
    {
        return std::make_unique<ymrobot::PlayFixedAudioNode>(name, "audio_control_action", config);
    };

    factory.registerBuilder<ymrobot::PlayFixedAudioNode>("PlayFixedAudioNode", builder);
}
