/**
 * HintonBot License. All rights reserved.
 * Created by Zewei Ding on 24-4-20.
 */

#include "amr_behavior_tree/plugins/action/say_something_node.hpp"

#include <memory>
#include <string>

namespace ymrobot
{
  namespace amr_bt
  {
    SaySomethingNode::SaySomethingNode(const std::string &service_node_name,
                                       const BT::NodeConfiguration &conf)
        : BT::SyncActionNode(service_node_name, conf)
    {
    }

    BT::NodeStatus SaySomethingNode::tick()
    {
      std::string message;
      getInput("message", message);
      RCLCPP_INFO(logger_, message.c_str());   // 居然可以 (*^▽^*)
      setOutput("result", message + " <<<<");
      return BT::NodeStatus::SUCCESS;
    }

  } // namespace amr_bt
} // namespace ymrobot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<amr_bt::SaySomethingNode>("SaySomething");
}