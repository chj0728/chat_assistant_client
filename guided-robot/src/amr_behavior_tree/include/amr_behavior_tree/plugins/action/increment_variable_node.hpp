#pragma once

#include <memory>
#include <string>

#include "behaviortree_cpp_v3/action_node.h"
#include "rclcpp/rclcpp.hpp"

namespace ymrobot
{
  class IncrementVariableNode : public BT::SyncActionNode
  {
  public:
    IncrementVariableNode(const std::string &xml_tag_name,
                          const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {BT::InputPort<std::string>("input_increment_variable", ""),
              BT::OutputPort<std::string>("output_increment_variable", "")};
    }

  private:
    BT::NodeStatus tick() override;
  };
} // namespace ymrobot