#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"
#include "nav2_behavior_tree/bt_action_node.hpp"
#include <ymrobot_msgs/action/cloud_chassis_nav.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>

#include "spdlog/logger.h"
#include "spdlog/spdlog.h"
#include "spdlog/sinks/rotating_file_sink.h"

namespace ymrobot
{
    class CloudChassisNavNode : public nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::CloudChassisNav>
    {
    public:
        CloudChassisNavNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf);

        static BT::PortsList providedPorts()
        {
            return {
                BT::InputPort<geometry_msgs::msg::PoseStamped>("nav_goal"),
            };
        }

        void on_tick() override;
        BT::NodeStatus on_aborted() override;
        BT::NodeStatus on_success() override;

    private:
        std::shared_ptr<spdlog::logger> logger;
    };
}


