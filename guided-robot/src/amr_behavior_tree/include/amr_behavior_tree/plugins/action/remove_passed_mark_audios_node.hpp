/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-04-01.
 */

#pragma once

#include <memory>
#include <string>
#include <fstream>
#include <sstream>

#include "behaviortree_cpp_v3/action_node.h"

#include "ymrobot_msgs/msg/task.hpp"
#include "rclcpp/rclcpp.hpp"

namespace ymrobot
{
  // std::map<std::string, std::string> fixed_audio_name_map =
  //     {
  //         {"讲解点0", "0"},
  //         {"讲解点1", "1"},
  //         {"讲解点2", "2"},
  //         {"讲解点3", "3"},
  //         {"讲解点4", "4"},
  //         {"讲解点5", "5"}
  //       };

  class RemovePassedMarkAudiosNode : public BT::SyncActionNode
  {
  public:
    RemovePassedMarkAudiosNode(const std::string &xml_tag_name,
                               const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {
          BT::InputPort<std::vector<std::string>>("input_mark_audio_list", ""),

          BT::OutputPort<std::vector<std::string>>("output_mark_audio_list", ""),
          BT::OutputPort<std::string>("mark_audio", ""),
      };
    }

  private:
    BT::NodeStatus tick() override;
    bool GetFixedAudio(const std::string &action_fixed_str_file, const int columnIndex);

    rclcpp::Logger logger_{rclcpp::get_logger("remove_passed_mark_audios_node")};
    std::map<std::string, std::string> fixed_audio_name_map;
    bool is_read_action_fixed_map = false;
  };
} // namespace ymrobot