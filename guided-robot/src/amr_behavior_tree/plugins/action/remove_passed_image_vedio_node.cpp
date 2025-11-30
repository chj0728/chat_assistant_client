/**
/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/remove_passed_image_vedio_node.hpp"

#include <memory>
#include <string>

namespace ymrobot
{
  RemovePassedImageVedioActionNode::RemovePassedImageVedioActionNode(const std::string &service_node_name,
                                                                     const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
  }

  BT::NodeStatus RemovePassedImageVedioActionNode::tick()
  {
    setStatus(BT::NodeStatus::RUNNING);
    std::vector<ymrobot_msgs::msg::ImageVideo> input_image_vedio_action_list;
    getInput("input_image_vedio_action_list", input_image_vedio_action_list);

    if (input_image_vedio_action_list.empty())
    {
      RCLCPP_ERROR(logger_, "图像音频列表是空的");
      return BT::NodeStatus::FAILURE;
    }
    setOutput("image_vedio_msg", input_image_vedio_action_list[0]);

    input_image_vedio_action_list.erase(input_image_vedio_action_list.begin());
    setOutput("input_image_vedio_action_list", input_image_vedio_action_list);

    return BT::NodeStatus::SUCCESS;
  }

}

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::RemovePassedImageVedioActionNode>("RemovePassedImageVedioActionNode");
}