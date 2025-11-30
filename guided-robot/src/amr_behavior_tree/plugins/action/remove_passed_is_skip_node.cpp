/**
/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/remove_passed_is_skip_node.hpp"

#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>

namespace ymrobot
{
  RemovePassedIsSikpNode::RemovePassedIsSikpNode(const std::string &service_node_name,
                                                 const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
  }

  BT::NodeStatus RemovePassedIsSikpNode::tick()
  {
    setStatus(BT::NodeStatus::RUNNING);
    std::vector<std::string> is_skip_list;
    getInput("input_is_skip_list", is_skip_list);

    if (is_skip_list.empty())
    {
      RCLCPP_ERROR(logger_, "是否跳过列表is_skip_list 是空的");
      return BT::NodeStatus::FAILURE;
    }
    setOutput("is_open_skip", is_skip_list[0]);
    RCLCPP_INFO(logger_, "是否跳过: %s", is_skip_list[0].c_str());

    is_skip_list.erase(is_skip_list.begin());
    setOutput("output_is_skip_list", is_skip_list);

    return BT::NodeStatus::SUCCESS;
  }

} // namespace hintonbot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::RemovePassedIsSikpNode>("RemovePassedIsSikpNode");
}