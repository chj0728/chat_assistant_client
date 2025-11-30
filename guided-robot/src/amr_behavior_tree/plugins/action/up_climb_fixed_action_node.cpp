/**
 * HintonBot License. All rights reserved.
 * Created by Qianhui Gu on 24-7-27.
 */

#include <memory>
#include <string>

#include "amr_behavior_tree/plugins/action/up_climb_fixed_action_node.hpp"

namespace ymrobot
{
  UpClimbFixedAction::UpClimbFixedAction(const std::string &xml_tag_name, const std::string &action_name, const BT::NodeConfiguration &conf) : nav2_behavior_tree::BtActionNode<ymrobot_msgs::action::UpClimbAction>(xml_tag_name, action_name, conf)
  {
    std::string action_fixed_str_file = "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/up_action_list.csv";
    if (GetActionFixed(action_fixed_str_file, 1))
    {
      RCLCPP_INFO(node_->get_logger(), "[UpClimbFixedAction]读取预设动作文件%s成功", action_fixed_str_file.c_str());
      is_read_action_fixed_map = true;
    }
    else
    {
      RCLCPP_ERROR(node_->get_logger(), "[UpClimbFixedAction]读取预设动作文件%s失败", action_fixed_str_file.c_str());
      is_read_action_fixed_map = false;
    }
  }

  void UpClimbFixedAction::on_tick()
  {
    if(!is_read_action_fixed_map)
    {
      setStatus(BT::NodeStatus::SUCCESS);
      return;
    }
    std::string action_fixed_str;
    RCLCPP_INFO(node_->get_logger(), "[UpClimbFixedAction]执行上肢预设动作%s", action_fixed_str.c_str());
    getInput("action_fixed_str", action_fixed_str);
    auto action_fixed = up_fixed_action_name_map[action_fixed_str];
    goal_.action_fixed = action_fixed;
    goal_.up_limb_task_type = 2;
  }

  BT::NodeStatus UpClimbFixedAction::on_aborted()
  {
    RCLCPP_ERROR(node_->get_logger(), "[UpClimbFixedAction]上肢固定动作执行失败");
    return BT::NodeStatus::FAILURE;
  }

  BT::NodeStatus UpClimbFixedAction::on_success()
  {
    RCLCPP_INFO(node_->get_logger(), "[UpClimbFixedAction]上肢固定动作执行成功.");
    return BT::NodeStatus::SUCCESS;
  }

  bool UpClimbFixedAction::GetActionFixed(const std::string &action_fixed_str_file, const int columnIndex)
  {
    std::ifstream file(action_fixed_str_file);
    if (!file.is_open())
    {
      RCLCPP_ERROR(node_->get_logger(), "[UpClimbFixedAction]无法打开文件 %s", action_fixed_str_file.c_str());
      return false;
    }
    std::vector<std::string> columnValues;
    std::string line, value;
    while (std::getline(file, line))
    {
      std::istringstream iss(line);
      int index = 0; // 新增变量 index
      while (std::getline(iss, value, ','))
      {
        if (index == columnIndex)
        {
          columnValues.push_back(value);
          break; // 添加 break 语句
        }
        index++;
      }
    }
    file.close();

    for (int i = 0; i < columnValues.size(); i++)
    {
      up_fixed_action_name_map.insert({columnValues[i], i});
      RCLCPP_INFO(node_->get_logger(), "[UpClimbFixedAction]上肢固定音频:%s ,下标:%d", columnValues[i].c_str(), i);
    }
  }
}

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  BT::NodeBuilder builder = [](const std::string &name,
                               const BT::NodeConfiguration &config)
  {
    return std::make_unique<ymrobot::UpClimbFixedAction>(name, "up_climb_action", config);
  };

  factory.registerBuilder<ymrobot::UpClimbFixedAction>("UpClimbFixedAction", builder);
}
