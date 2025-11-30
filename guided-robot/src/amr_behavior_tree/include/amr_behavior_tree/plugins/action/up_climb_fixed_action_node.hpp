#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"
#include "nav2_behavior_tree/bt_action_node.hpp"
#include <ymrobot_msgs/msg/task.hpp>
#include <ymrobot_msgs/action/up_climb_action.hpp>

#include <fstream>
#include <sstream>

namespace ymrobot
{
    // std::map<std::string, uint8_t> up_fixed_action_name_map =
    //     {{"初始化(双臂归位)", 0},
    //      {"左挥手", 1},
    //      {"右挥手", 2},
    //      {"左指引", 3},
    //      {"右指引", 4},
    //      {"左握手", 5},
    //      {"右握手", 6},
    //      {"动作1", 7},
    //      {"动作2", 8},
    //      {"动作3", 9},
    //      {"动作4", 10},
    //      {"动作5", 11},
    //      {"动作6", 12}
    //     };

    class UpClimbFixedAction : public nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::UpClimbAction>
    {
    public:
        UpClimbFixedAction(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf);

        static BT::PortsList providedPorts()
        {
            return {
                BT::InputPort<std::string>("action_fixed_str"),
            };
        }

        void on_tick() override;
        BT::NodeStatus on_aborted() override;
        BT::NodeStatus on_success() override;

    private:
        bool GetActionFixed(const std::string &action_fixed_str_file, const int columnIndex);

    private:
        std::map<std::string, uint8_t> up_fixed_action_name_map;
        bool is_read_action_fixed_map = false;
    };
}
