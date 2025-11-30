/*
 * ymrobot License. All rights reserved.
 * Created by Zewei Ding on 24-3-17.
 */

#pragma once

#include <memory>
#include <string>

#include "behaviortree_cpp_v3/condition_node.h"

#include <ymrobot_msgs/msg/task.hpp>
#include <rclcpp/rclcpp.hpp>

namespace ymrobot
{
  namespace amr_bt
  {

    class NeedIndexNode : public BT::ConditionNode
    {
    public:
      NeedIndexNode(const std::string &name, const BT::NodeConfiguration &conf);

      NeedIndexNode() = delete;

      BT::NodeStatus tick() override;

      static BT::PortsList providedPorts()
      {
        return {
                BT::InputPort<std::string>("need_bt_index", "The task currently received"),
                BT::InputPort<std::string>("index", "", "Script index")};
      }

    private:
      rclcpp::Node::SharedPtr node_;
    };

  } // namespace amr_bt

} // namespace ymrobot
