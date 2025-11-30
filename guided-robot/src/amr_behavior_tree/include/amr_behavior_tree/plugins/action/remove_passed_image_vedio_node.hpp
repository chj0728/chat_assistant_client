/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-04-01.
 */

#pragma once

#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp_v3/action_node.h"

#include <ymrobot_msgs/msg/image_video.hpp>
#include "ymrobot_msgs/msg/task.hpp"
namespace ymrobot
{
  class RemovePassedImageVedioActionNode : public BT::SyncActionNode
  {
  public:
    RemovePassedImageVedioActionNode(const std::string &xml_tag_name,
                                     const BT::NodeConfiguration &conf);

    static BT::PortsList providedPorts()
    {
      return {
          BT::InputPort<std::vector<ymrobot_msgs::msg::ImageVideo>>("input_image_vedio_action_list", ""),

          BT::OutputPort<std::vector<ymrobot_msgs::msg::ImageVideo>>("output_image_vedio_action_list", ""),
          BT::OutputPort<std::vector<ymrobot_msgs::msg::ImageVideo>>("image_vedio_msg", ""),
      };
    }

  private:
    BT::NodeStatus tick() override;
    rclcpp::Logger logger_{rclcpp::get_logger("remove_passed_fixed_up_action_node")};
  };
} // namespace ymrobot