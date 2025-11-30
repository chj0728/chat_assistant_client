/**
/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/remove_passed_mark_points_node.hpp"

#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>

namespace ymrobot
{
  RemovePassedMarkPointsNode::RemovePassedMarkPointsNode(const std::string &service_node_name,
                                                         const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
  }

  BT::NodeStatus RemovePassedMarkPointsNode::tick()
  {
    setStatus(BT::NodeStatus::RUNNING);
    std::vector<std::string> mark_nav_target_list;
    getInput("input_mark_nav_target_list", mark_nav_target_list);

    if (mark_nav_target_list.empty())
    {
      RCLCPP_ERROR(logger_,"导览点位列表mark_nav_target_list 是空的");
      return BT::NodeStatus::FAILURE;
    }
    setOutput("mark_nav_target", mark_nav_target_list[0]);
    RCLCPP_INFO(logger_,"当前要执行的导览点位: %s", mark_nav_target_list[0].c_str());

    mark_nav_target_list.erase(mark_nav_target_list.begin());
    setOutput("output_mark_nav_target_list", mark_nav_target_list);

    return BT::NodeStatus::SUCCESS;
  }

} // namespace hintonbot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::RemovePassedMarkPointsNode>("RemovePassedMarkPointsNode");
}