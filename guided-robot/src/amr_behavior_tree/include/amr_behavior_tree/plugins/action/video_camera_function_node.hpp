#include <vector>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"
#include "nav2_behavior_tree/bt_action_node.hpp"
#include <ymrobot_msgs/action/camera_function.hpp>
#include "ymrobot_msgs/msg/task.hpp"
#include "ymrobot_msgs/msg/image_video.hpp"

namespace ymrobot
{
    class VideoCameraFunctionNode : public nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::CameraFunction>
    {
    public:
        VideoCameraFunctionNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf);

        static BT::PortsList providedPorts()
        {
            return {
                BT::InputPort<ymrobot_msgs::msg::ImageVideo>("image_vedio_msg"),
            };
        }

        void on_tick() override;
        BT::NodeStatus on_aborted() override;
        BT::NodeStatus on_success() override;
    };
}
