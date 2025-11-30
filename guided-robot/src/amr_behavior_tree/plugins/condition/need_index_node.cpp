/*
 * ymrobot License. All rights reserved.
 * Created by Zewei Ding on 24-3-17.
 */

#include "amr_behavior_tree/plugins/condition/need_index_node.hpp"

namespace ymrobot
{
  namespace amr_bt
  {
    NeedIndexNode::NeedIndexNode(const std::string &name,
                                 const BT::NodeConfiguration &conf)
        : BT::ConditionNode(name, conf)
    {
      node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
    }

    BT::NodeStatus NeedIndexNode::tick()
    {
      std::string need_bt_index;
      std::string index;
      if (!getInput("need_bt_index", need_bt_index))
      {
        std::cout << "Missing required input [current_task" << std::endl;
        return BT::NodeStatus::FAILURE;
      }
      getInput("index", index);

      if (need_bt_index != index)
      {
        return BT::NodeStatus::FAILURE;
      }
      return BT::NodeStatus::SUCCESS;
    }

  } // namespace amr_bt
} // namespace ymrobot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<amr_bt::NeedIndexNode>("NeedIndex");
}