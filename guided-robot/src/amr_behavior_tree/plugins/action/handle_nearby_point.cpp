/**
/**
 * YmBot License. All rights reserved.
 * Created by Yaoyang Hu on 2025-9-15
 */

#include "amr_behavior_tree/plugins/action/handle_nearby_point.hpp"

#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>

namespace ymrobot
{
  HandleNearbyPoint::HandleNearbyPoint(const std::string &service_node_name,
                                                         const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
  }

  BT::NodeStatus HandleNearbyPoint::tick()
  {
    setStatus(BT::NodeStatus::RUNNING);
    std::vector<std::string> is_activate_the_nearby_point_list;
    std::vector<std::string> nearby_point_radius_list;
    bool is_activate_the_nearby_point;
    getInput("is_activate_the_nearby_point", is_activate_the_nearby_point_list);
    getInput("nearby_point_radius", nearby_point_radius_list);

    if (is_activate_the_nearby_point_list.empty())
    {
      RCLCPP_ERROR(logger_,"是否开启就近点为空，不启用就近点");
      return BT::NodeStatus::SUCCESS;
    }
    is_activate_the_nearby_point = (is_activate_the_nearby_point_list[0] == "0") ? false : true;
    setOutput("is_activate_the_nearby_point_value", is_activate_the_nearby_point);
    RCLCPP_INFO(logger_,"是否开启就近点: %s", is_activate_the_nearby_point ? "true" : "false");

    is_activate_the_nearby_point_list.erase(is_activate_the_nearby_point_list.begin());
    setOutput("is_activate_the_nearby_point", is_activate_the_nearby_point_list);

    setOutput("nearby_point_radius_value", nearby_point_radius_list[0]);
    RCLCPP_INFO(logger_,"当前就近点范围: %s", nearby_point_radius_list[0].c_str());

    nearby_point_radius_list.erase(nearby_point_radius_list.begin());
    setOutput("nearby_point_radius", nearby_point_radius_list);

    return BT::NodeStatus::SUCCESS;
  }

}


#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::HandleNearbyPoint>("HandleNearbyPoint");
}