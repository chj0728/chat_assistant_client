#pragma once

#include <memory>
#include <string>

#include "behaviortree_cpp_v3/action_node.h"
#include "rclcpp/rclcpp.hpp"
#include "ymrobot_msgs/msg/task.hpp"

namespace ymrobot
{
  class HandleNearbyPoint : public BT::SyncActionNode
  {
  public:
    HandleNearbyPoint(const std::string &xml_tag_name,
                               const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {
        BT::InputPort<std::vector<std::string>>("is_activate_the_nearby_point", ""),
        BT::InputPort<std::vector<std::string>>("nearby_point_radius", ""),
        BT::OutputPort<bool>("is_activate_the_nearby_point_value", ""),
        BT::OutputPort<std::vector<std::string>>("is_activate_the_nearby_point", ""),
        BT::OutputPort<std::string>("nearby_point_radius_value", ""),
        BT::OutputPort<std::vector<std::string>>("nearby_point_radius", ""),
      };
    }

  private:
    BT::NodeStatus tick() override;
    rclcpp::Logger logger_{rclcpp::get_logger("remove_passed_mark_points_node")};
  };
}
