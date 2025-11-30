/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 25-02-13.
 */
#include "amr_behavior_tree/plugins/action/cloud_chassis_nav_name_node.hpp"

namespace ymrobot
{
    CloudChassisNavNameNode::CloudChassisNavNameNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::CloudChassisNav>(xml_tag_name, action_name,
                                                                                                                                                                                                                                   conf)
    {
    }

    void CloudChassisNavNameNode::on_tick()
    {
        if (!getInput<std::string>("nav_pose_name", goal_.nav_target_name))
        {
            throw BT::RuntimeError("[CloudChassisNavNameNode]Missing required input [wait_elevator_time]");
        }
        goal_.nav_mode = 0; // 采用名称导航
        goal_.is_open_near_explation = getInput<bool>("is_activate_the_nearby_point").value();
        goal_.occupied_tolerance = std::stof(getInput<std::string>("nearby_point_radius").value());
    }

    BT::NodeStatus CloudChassisNavNameNode::on_aborted()
    {
        RCLCPP_ERROR(node_->get_logger(), "[cloud_chassis_nav_node]Failure.");
        return BT::NodeStatus::FAILURE;
    }

    BT::NodeStatus CloudChassisNavNameNode::on_success()
    {
        RCLCPP_INFO(node_->get_logger(), "[cloud_chassis_nav_node]Success.");
        return BT::NodeStatus::SUCCESS;
    }
}

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
    BT::NodeBuilder builder = [](const std::string &name,
                                 const BT::NodeConfiguration &config)
    {
        return std::make_unique<ymrobot::CloudChassisNavNameNode>(name, "cloud_chassis_nav_action", config);
    };
    factory.registerBuilder<ymrobot::CloudChassisNavNameNode>("CloudChassisNavNameNode", builder);
}