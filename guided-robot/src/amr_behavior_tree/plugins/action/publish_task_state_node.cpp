#include "amr_behavior_tree/plugins/action/publish_task_state_node.hpp"

#include <memory>
#include <string>

namespace ymrobot
{
  namespace amr_bt
  {
    PublishTaskStateNode::PublishTaskStateNode(const std::string &service_node_name,
                                               const BT::NodeConfiguration &conf)
        : BT::SyncActionNode(service_node_name, conf)
    {
      node_ = rclcpp::Node::make_shared("publish_task_state_node");
      node_task_state_pub_ = node_->create_publisher<ymrobot_msgs::msg::BTNodeTaskState>("bt_node_states", 1);
    }

    BT::NodeStatus PublishTaskStateNode::tick()
    {
      std::string node_task_type;
      std::string node_task_state;
      std::string node_name;
      std::string node_task_error;
      std::string node_task_error_message;
      std::string node_task_id;
      std::string node_action_content;
      ymrobot_msgs::msg::BTNodeTaskState node_task_state_msg;

      getInput<std::string>("node_task_type", node_task_type);   // node任务类型
      getInput<std::string>("node_task_state", node_task_state); // node任务状态
      getInput<std::string>("node_name", node_name);
      getInput<std::string>("node_task_error", node_task_error);
      getInput<std::string>("node_action_content", node_action_content);
      getInput<std::string>("node_task_error_message", node_task_error_message);
      getInput<std::string>("node_task_id", node_task_id);

      node_task_state_msg.task_type = node_task_type;
      node_task_state_msg.node_name = node_name;
      node_task_state_msg.node_task_state = node_task_state;
      node_task_state_msg.node_task_error = node_task_error;
      node_task_state_msg.node_task_error_message = node_task_error_message;
      node_task_state_msg.node_action_content = node_action_content;
      node_task_state_msg.task_id = node_task_id;

      node_task_state_pub_->publish(node_task_state_msg);
      RCLCPP_INFO(node_->get_logger(), "PublishTaskStateNode: 发布node任务状态信息");
      return BT::NodeStatus::SUCCESS;
    }

  }
}

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<amr_bt::PublishTaskStateNode>("PublishTaskStateNode");
}