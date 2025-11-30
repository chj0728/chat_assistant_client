/**
/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/increment_variable_node.hpp"

namespace ymrobot
{
  IncrementVariableNode::IncrementVariableNode(const std::string &service_node_name,
                                       const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
  }

  BT::NodeStatus IncrementVariableNode::tick()
  {
    std::string input_increment_variable;
    std::string output_increment_variable;
    getInput<std::string>("input_increment_variable", input_increment_variable);

    int input_increment_variable_int = std::stoi(input_increment_variable); 
    input_increment_variable_int += 1;

    setOutput<std::string>("output_increment_variable", std::to_string(input_increment_variable_int));
    return BT::NodeStatus::SUCCESS;
  }

} // namespace hintonbot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::IncrementVariableNode>("IncrementVariableNode");
}