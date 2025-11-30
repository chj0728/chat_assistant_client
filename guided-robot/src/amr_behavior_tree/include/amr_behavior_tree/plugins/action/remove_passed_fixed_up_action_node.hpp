/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-04-01.
 */

#pragma once

#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"

#include "ymrobot_msgs/msg/task.hpp"
namespace ymrobot
{
  class RemovePassedFixedUpActionNode : public BT::SyncActionNode
  {
  public:
    RemovePassedFixedUpActionNode(const std::string &xml_tag_name,
                               const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {
          BT::InputPort<std::vector<std::string>>("input_mark_fixed_up_action_list", ""),
          BT::OutputPort<std::vector<std::string>>("output_mark_fixed_up_action_list", ""),
          BT::OutputPort<std::string>("fixed_action", ""),
      };
    }

  private:
    BT::NodeStatus tick() override;
    rclcpp::Logger logger_{rclcpp::get_logger("remove_passed_fixed_up_action_node")};
  };
} // namespace ymrobot