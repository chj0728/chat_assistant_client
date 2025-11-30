/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 25-02-13.
 */
#include "amr_behavior_tree/plugins/action/cloud_chassis_reposition_node.hpp"

namespace ymrobot
{
    CloudChassisNavReposition::CloudChassisNavReposition(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::CloudChassisNavReposition>(xml_tag_name, action_name,
                                                                                                                                                                                                                  conf)
    {
    }

    void CloudChassisNavReposition::on_tick()
    {
        ymrobot_msgs::msg::Task current_task;
        getInput<ymrobot_msgs::msg::Task>("current_task", current_task);
        std::string reposition_pose_name = current_task.commands[0].params[0];
        RCLCPP_INFO(node_->get_logger(), "重定位点:%s", reposition_pose_name.c_str());
        goal_.reposition_pose_name = reposition_pose_name;
    }

    BT::NodeStatus CloudChassisNavReposition::on_aborted()
    {
        RCLCPP_ERROR(node_->get_logger(), "[CloudChassisNavReposition]Failure.");
        return BT::NodeStatus::FAILURE;
    }

    BT::NodeStatus CloudChassisNavReposition::on_success()
    {
        RCLCPP_INFO(node_->get_logger(), "[CloudChassisNavReposition]Success.");
        return BT::NodeStatus::SUCCESS;
    }

}

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
    BT::NodeBuilder builder = [](const std::string &name,
                                 const BT::NodeConfiguration &config)
    {
        return std::make_unique<ymrobot::CloudChassisNavReposition>(name, "cloud_chassis_reposition_action", config);
    };

    factory.registerBuilder<ymrobot::CloudChassisNavReposition>("CloudChassisNavRepositionNode", builder);
}