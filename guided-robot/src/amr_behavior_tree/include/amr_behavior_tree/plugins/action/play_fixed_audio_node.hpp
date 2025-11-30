#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"
#include "nav2_behavior_tree/bt_action_node.hpp"
#include <ymrobot_msgs/msg/task.hpp>
#include <ymrobot_msgs/action/audio_control.hpp>

#include "spdlog/logger.h"
#include "spdlog/spdlog.h"
#include "spdlog/sinks/rotating_file_sink.h"

namespace ymrobot
{
    class PlayFixedAudioNode : public nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::AudioControl>
    {
    public:
        PlayFixedAudioNode(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf);

        static BT::PortsList providedPorts()
        {
            return {
                BT::InputPort<std::string>("fixed_audio"),
            };
        }

        void on_tick() override;
        BT::NodeStatus on_aborted() override;
        BT::NodeStatus on_success() override;

    private:
        std::shared_ptr<spdlog::logger> logger;
    };
}


