/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 25-02-13.
 */
#include "amr_behavior_tree/plugins/action/cloud_chassis_nav_node.hpp"

namespace ymrobot
{
    CloudChassisNavNode::CloudChassisNavNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::CloudChassisNav>(xml_tag_name, action_name,
                                                                                                                                                                                                                  conf)
    {
    }

    void CloudChassisNavNode::on_tick()
    {
        geometry_msgs::msg::PoseStamped nav_pose;
        if (!getInput<geometry_msgs::msg::PoseStamped>("nav_goal", nav_pose))
        {
            throw BT::RuntimeError("[cloud_chassis_nav_node]Missing required input [wait_elevator_time]");
        }
        goal_.nav_mode = 1;
        goal_.nav_target_x = nav_pose.pose.position.x;
        goal_.nav_target_y = nav_pose.pose.position.y;
        double roll, pitch, yaw;
        tf2::Quaternion tf_quat;
        tf2::fromMsg(nav_pose.pose.orientation, tf_quat);  // ROS 2 -> tf2 转换
        tf2::Matrix3x3 mat(tf_quat);
        mat.getRPY(roll, pitch, yaw);
        goal_.nav_target_yaw = yaw;
    }

    BT::NodeStatus CloudChassisNavNode::on_aborted()
    {
        RCLCPP_ERROR(node_->get_logger(), "[cloud_chassis_nav_node]Failure.");
        return BT::NodeStatus::FAILURE;
    }

    BT::NodeStatus CloudChassisNavNode::on_success()
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
        return std::make_unique<ymrobot::CloudChassisNavNode>(name, "cloud_chassis_nav_action", config);
    };

    factory.registerBuilder<ymrobot::CloudChassisNavNode>("CloudChassisNavNode", builder);
}