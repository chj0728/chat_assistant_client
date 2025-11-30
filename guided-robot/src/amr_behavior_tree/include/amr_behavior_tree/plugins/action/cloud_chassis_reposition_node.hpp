#include <vector>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"
#include "nav2_behavior_tree/bt_action_node.hpp"
#include <ymrobot_msgs/action/cloud_chassis_nav_reposition.hpp>
#include "ymrobot_msgs/msg/task.hpp"

namespace ymrobot
{
    class CloudChassisNavReposition : public nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::CloudChassisNavReposition>
    {
    public:
        CloudChassisNavReposition(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf);

        static BT::PortsList providedPorts()
        {
            return {BT::InputPort<ymrobot_msgs::msg::Task>("current_task", "The task currently received")};
        }

        void on_tick() override;
        BT::NodeStatus on_aborted() override;
        BT::NodeStatus on_success() override;
    private:
        rclcpp::Logger logger_{rclcpp::get_logger("CloudChassisNavRepositionNode")};
    };
}
