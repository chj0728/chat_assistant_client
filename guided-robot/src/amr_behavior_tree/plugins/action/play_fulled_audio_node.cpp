/**
/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/play_fulled_audio_node.hpp"

namespace ymrobot
{
  PlayFullAudioNode::PlayFullAudioNode(const std::string &service_node_name,
                                       const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
    node_ = rclcpp::Node::make_shared("play_full_audio_node");
    chassis_task_status_sub_ = node_->create_subscription<std_msgs::msg::String>("chassis_task_status", 1, std::bind(&PlayFullAudioNode::CloudChassisNavCallBack, this, std::placeholders::_1));
  }

  void PlayFullAudioNode::CloudChassisNavCallBack(const std_msgs::msg::String::SharedPtr msg)
  {
    std::cout << "PlayFullAudioNode: 机器人任务成" << msg->data << std::endl;
    is_complete_task_.store(true);
  }

  BT::NodeStatus PlayFullAudioNode::tick()
  {
    std::string is_audio_played_throughout_the_entire_process;
    std::string full_audio_name;
    getInput<std::string>("is_audio_played_throughout_the_entire_process", is_audio_played_throughout_the_entire_process);
    getInput<std::string>("full_audio_name", full_audio_name);

    if (is_audio_played_throughout_the_entire_process == "0")
    {
      RCLCPP_INFO(logger_, "PlayFullAudioNode: 不需要全程播放音频");
    }
    else if (is_audio_played_throughout_the_entire_process == "1")
    {
      RCLCPP_INFO(logger_, "PlayFullAudioNode: 需要全程播放音频,音频为： %s", full_audio_name.c_str());

      while (true)
      {
        if (is_complete_task_.load())
        {
          is_complete_task_.store(false);
          return BT::NodeStatus::SUCCESS;
        }
        std::this_thread::sleep_for(std::chrono::seconds(1));
      }
    }
    return BT::NodeStatus::SUCCESS;
  }

} // namespace hintonbot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::PlayFullAudioNode>("PlayFullAudioNode");
}