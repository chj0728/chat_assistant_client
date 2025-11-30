/**
/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/remove_passed_fixed_up_action_node.hpp"

#include <memory>
#include <string>

namespace ymrobot
{
  RemovePassedFixedUpActionNode::RemovePassedFixedUpActionNode(const std::string &service_node_name,
                                                         const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
  }

  BT::NodeStatus RemovePassedFixedUpActionNode::tick()
  {
    setStatus(BT::NodeStatus::RUNNING);
    std::vector<std::string> input_mark_fixed_up_action_list;
    getInput("input_mark_fixed_up_action_list", input_mark_fixed_up_action_list);

    if (input_mark_fixed_up_action_list.empty())
    {
      RCLCPP_ERROR(logger_,"导览上肢固定动作input_mark_fixed_up_action_list是空的");
      setOutput("fixed_action", "初始化(双臂归位)");
      // return BT::NodeStatus::FAILURE;
    }
    setOutput("fixed_action", input_mark_fixed_up_action_list[0]);
    RCLCPP_INFO(logger_,"当前要执行的上肢固定动作: %s", input_mark_fixed_up_action_list[0].c_str());

    input_mark_fixed_up_action_list.erase(input_mark_fixed_up_action_list.begin());
    setOutput("output_mark_fixed_up_action_list", input_mark_fixed_up_action_list);

    return BT::NodeStatus::SUCCESS;
  }

} // namespace hintonbot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::RemovePassedFixedUpActionNode>("RemovePassedFixedUpActionNode");
}