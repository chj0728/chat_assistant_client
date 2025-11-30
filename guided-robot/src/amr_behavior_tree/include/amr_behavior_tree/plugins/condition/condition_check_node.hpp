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

        class ConditionCheck : public BT::ConditionNode
        {
        public:
            ConditionCheck(const std::string &name, const BT::NodeConfiguration &conf);

            ConditionCheck() = delete;

            BT::NodeStatus tick() override;

            static BT::PortsList providedPorts()
            {
                return {
                    BT::InputPort<std::string>("is_open_skip", "是否开启跳过机制")};
            }

        private:
            rclcpp::Node::SharedPtr node_;
        };

    } // namespace amr_bt

} // namespace ymrobot
