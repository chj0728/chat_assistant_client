/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-04-01.
 */

#pragma once

#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include <std_msgs/msg/string.hpp>
#include "behaviortree_cpp_v3/action_node.h"

namespace ymrobot
{
  class PubUpClimbStopNode : public BT::SyncActionNode
  {
  public:
    PubUpClimbStopNode(const std::string &xml_tag_name,
                               const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
    }

  private:
    BT::NodeStatus tick() override;
    rclcpp::Logger logger_{rclcpp::get_logger("remove_passed_mark_points_node")};
    rclcpp::Node::SharedPtr node_;
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr stop_publisher_;
  };
} // namespace ymrobot