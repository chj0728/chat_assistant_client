#pragma once

#include <memory>
#include <string>
#include "rclcpp/rclcpp.hpp"

#include "behaviortree_cpp_v3/action_node.h"
#include <ymrobot_msgs/msg/bt_node_task_state.hpp>

namespace ymrobot
{
  namespace amr_bt
  {
    /**
     * @brief A PublishTaskStateNode class prints the message.
     */
    class PublishTaskStateNode : public BT::SyncActionNode
    {
    public:
      PublishTaskStateNode(const std::string &xml_tag_name,
                           const BT::NodeConfiguration &conf);

      static BT::PortsList providedPorts()
      {
        return {
            BT::InputPort<std::string>("node_task_id"),
            BT::InputPort<std::string>("node_task_type"),
            BT::InputPort<std::string>("node_name"),
            BT::InputPort<std::string>("node_task_state"),
            BT::InputPort<std::string>("node_task_error"),
            BT::InputPort<std::string>("node_task_error_message"),
            BT::InputPort<std::string>("node_action_content")};
      }

    private:
      BT::NodeStatus tick() override;

    private:
      rclcpp::Node::SharedPtr node_;
      rclcpp::Logger logger_{rclcpp::get_logger("PublishTaskStateNode")};
      rclcpp::Publisher<ymrobot_msgs::msg::BTNodeTaskState>::SharedPtr node_task_state_pub_{}; // node任务状态发布者
    };
  } // namespace amr_bt
} // namespace ymrobot
