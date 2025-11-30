#pragma once

#include <memory>
#include <string>

#include "behaviortree_cpp_v3/action_node.h"
#include "rclcpp/rclcpp.hpp"
#include "ymrobot_msgs/msg/task.hpp"
#include <std_msgs/msg/string.hpp>

namespace ymrobot
{
  class PlayFullAudioNode : public BT::SyncActionNode
  {
  public:
    PlayFullAudioNode(const std::string &xml_tag_name,
                      const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {
          BT::InputPort<std::string>("is_audio_played_throughout_the_entire_process", "是否全程播放音频"),
          BT::InputPort<std::string>("full_audio_name", "全程音频文件名"),
      };
    }

  private:
    BT::NodeStatus tick() override;
    void CloudChassisNavCallBack(const std_msgs::msg::String::SharedPtr msg);

  private:
    rclcpp::Node::SharedPtr node_;
    rclcpp::Logger logger_{rclcpp::get_logger("play_fulled_audio_node")};
    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr chassis_task_status_sub_{}; // 订阅机器人的任务是否完成
    std::atomic<bool> is_complete_task_{false};                                        // 低电量充电阈值
  };
} // namespace ymrobot