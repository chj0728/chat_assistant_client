#include <vector>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"
#include "nav2_behavior_tree/bt_action_node.hpp"
#include <ymrobot_msgs/action/get_current_task.hpp>
#include "ymrobot_msgs/msg/task.hpp"

namespace ymrobot
{
    class SetParamsNode : public nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::GetCurrentTask>
    {
    public:
        SetParamsNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf);

        static BT::PortsList providedPorts()
        {
            return {BT::InputPort<ymrobot_msgs::msg::Task>("current_task")};
        }

        void on_tick() override;
        BT::NodeStatus on_aborted() override;
        BT::NodeStatus on_success() override;
    };
}
