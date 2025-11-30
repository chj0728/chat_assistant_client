/*
 * ymrobot License. All rights reserved.
 * Created by Zewei Ding on 24-3-17.
 */

#include "amr_behavior_tree/plugins/condition/condition_check_node.hpp"

namespace ymrobot
{
    namespace amr_bt
    {
        ConditionCheck::ConditionCheck(const std::string &name,
                                       const BT::NodeConfiguration &conf)
            : BT::ConditionNode(name, conf)
        {
            node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
        }

        BT::NodeStatus ConditionCheck::tick()
        {
            std::string is_open_skip;
            if (!getInput("is_open_skip", is_open_skip))
            {
                return BT::NodeStatus::FAILURE;
            }

            if (is_open_skip != "1")
            {
                std::cout << "不开启点位跳过功能" << std::endl;
                return BT::NodeStatus::FAILURE;
            }

            std::cout << "开启点位跳过功能" << std::endl;
            return BT::NodeStatus::SUCCESS;
        }

    } // namespace amr_bt
} // namespace ymrobot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
    factory.registerNodeType<amr_bt::ConditionCheck>("ConditionCheckNode");
}