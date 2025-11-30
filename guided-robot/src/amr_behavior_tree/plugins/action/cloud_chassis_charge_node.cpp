/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 25-03-28.
 */
#include "amr_behavior_tree/plugins/action/cloud_chassis_charge_node.hpp"

namespace ymrobot
{
    CloudChassiChargeNode::CloudChassiChargeNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::CloudChassisCharge>(xml_tag_name, action_name,
                                                                                                                                                                                                                  conf)
    {
    }

    void CloudChassiChargeNode::on_tick()
    {
        if (!getInput<std::string>("charge_point_name", goal_.charge_point_name))
        {
            throw BT::RuntimeError("[cloud_chassis_nav_node]Missing required input [wait_elevator_time]");
        }
    }

    BT::NodeStatus CloudChassiChargeNode::on_aborted()
    {
        RCLCPP_ERROR(node_->get_logger(), "[CloudChassiChargeNode]Failure.");
        return BT::NodeStatus::FAILURE;
    }

    BT::NodeStatus CloudChassiChargeNode::on_success()
    {
        RCLCPP_INFO(node_->get_logger(), "[CloudChassiChargeNode]Success.");
        return BT::NodeStatus::SUCCESS;
    }

}

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
    BT::NodeBuilder builder = [](const std::string &name,
                                 const BT::NodeConfiguration &config)
    {
        return std::make_unique<ymrobot::CloudChassiChargeNode>(name, "cloud_chassis_charge_action", config);
    };

    factory.registerBuilder<ymrobot::CloudChassiChargeNode>("CloudChassiChargeNode", builder);
}