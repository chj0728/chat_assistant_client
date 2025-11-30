/**
/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/pub_up_climb_stop_node.hpp"

namespace ymrobot
{
  PubUpClimbStopNode::PubUpClimbStopNode(const std::string &service_node_name,
                                         const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
    stop_publisher_ = node_->create_publisher<std_msgs::msg::String>("up_climb_action_stop", 1);
  }

  BT::NodeStatus PubUpClimbStopNode::tick()
  {
    auto stop_msg = std_msgs::msg::String();
    stop_msg.data = "stop";
    stop_publisher_->publish(stop_msg);
    RCLCPP_INFO(node_->get_logger(), "发布停止上肢运动指令");

    return BT::NodeStatus::SUCCESS;
  }

} // namespace hintonbot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::PubUpClimbStopNode>("PubUpClimbStopNode");
}