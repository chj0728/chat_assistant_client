/**
 * HintonBot License. All rights reserved.
 * Created by Zewei Ding on 24-4-20.
 */

#pragma once

#include <memory>
#include <string>
#include "rclcpp/rclcpp.hpp"

#include "behaviortree_cpp_v3/action_node.h"

namespace ymrobot
{
  namespace amr_bt
  {
    /**
     * @brief A SaySomethingNode class prints the message.
     */
    class SaySomethingNode : public BT::SyncActionNode
    {
    public:
      SaySomethingNode(const std::string &xml_tag_name,
                       const BT::NodeConfiguration &conf);

      static BT::PortsList providedPorts()
      {
        return {BT::InputPort<std::string>("message", "Message to say."),
                BT::OutputPort<std::string>("result", "Message to output")};
      }

    private:
      BT::NodeStatus tick() override;
      rclcpp::Logger logger_{rclcpp::get_logger("SaySomethingNode")};
    };
  } // namespace amr_bt
} // namespace ymrobot
