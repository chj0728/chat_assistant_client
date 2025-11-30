/**
 * HintonBot License. All rights reserved.
 * Created by Qianhui Gu on 24-7-27.
 */

#include <memory>
#include <string>

#include "amr_behavior_tree/plugins/action/set_params_node.hpp"

namespace ymrobot
{
  SetParamsNode::SetParamsNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::GetCurrentTask>(xml_tag_name, action_name, conf)
  {
  }

  void SetParamsNode::on_tick()
  {
    getInput("current_task", goal_.current_task);
  }

  BT::NodeStatus SetParamsNode::on_aborted()
  {
    RCLCPP_ERROR(node_->get_logger(), "[SetParamsNode]Failure.");
    return BT::NodeStatus::FAILURE;
  }

  BT::NodeStatus SetParamsNode::on_success()
  {
    RCLCPP_INFO(node_->get_logger(), "[SetParamsNode]Success.");
    return BT::NodeStatus::SUCCESS;
  }
}

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  BT::NodeBuilder builder = [](const std::string &name,
                               const BT::NodeConfiguration &config)
  {
    return std::make_unique<ymrobot::SetParamsNode>(name, "set_params_server", config);
  };

  factory.registerBuilder<ymrobot::SetParamsNode>("SetParamsNode", builder);
}