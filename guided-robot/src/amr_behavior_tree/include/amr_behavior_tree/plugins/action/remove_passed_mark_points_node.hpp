/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-04-01.
 */

#pragma once

#include <memory>
#include <string>

#include "behaviortree_cpp_v3/action_node.h"
#include "rclcpp/rclcpp.hpp"
#include "ymrobot_msgs/msg/task.hpp"

namespace ymrobot
{
  class RemovePassedMarkPointsNode : public BT::SyncActionNode
  {
  public:
    RemovePassedMarkPointsNode(const std::string &xml_tag_name,
                               const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {
          BT::InputPort<std::vector<std::string>>("input_mark_nav_target_list", ""),
          BT::OutputPort<std::vector<std::string>>("output_mark_nav_target_list", ""),
          BT::OutputPort<std::string>("mark_nav_target", ""),
      };
    }

  private:
    BT::NodeStatus tick() override;
    rclcpp::Logger logger_{rclcpp::get_logger("remove_passed_mark_points_node")};
  };
} // namespace ymrobot