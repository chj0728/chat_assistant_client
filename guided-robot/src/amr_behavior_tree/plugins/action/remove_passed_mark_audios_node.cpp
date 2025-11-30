/**
/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/remove_passed_mark_audios_node.hpp"

#include <memory>
#include <string>
#include <cstdlib>

#include <rclcpp/rclcpp.hpp>

namespace ymrobot
{
  RemovePassedMarkAudiosNode::RemovePassedMarkAudiosNode(const std::string &service_node_name,
                                                         const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
    // std::string action_fixed_str_file = "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/mark_audio_list.csv";
    // if (GetFixedAudio(action_fixed_str_file, 0))
    // {
    //   RCLCPP_INFO(logger_, "[RemovePassedMarkAudiosNode]读取预设动作文件%s成功", action_fixed_str_file.c_str());
    //   is_read_action_fixed_map = true;
    // }
    // else
    // {
    //   RCLCPP_ERROR(logger_, "[RemovePassedMarkAudiosNode]读取预设动作文件%s失败", action_fixed_str_file.c_str());
    //   is_read_action_fixed_map = false;
    // }
  }

  BT::NodeStatus RemovePassedMarkAudiosNode::tick()
  {
    // if (!is_read_action_fixed_map)
    // {
    //   return BT::NodeStatus::FAILURE;
    // }

    setStatus(BT::NodeStatus::RUNNING);
    std::vector<std::string> mark_audio_list;
    getInput("input_mark_audio_list", mark_audio_list);

    if (mark_audio_list.empty())
    {
      RCLCPP_ERROR(logger_, "导览音频点位mark_audio_list为空");
      return BT::NodeStatus::FAILURE;
    }
    setOutput("mark_audio", mark_audio_list[0]);
    RCLCPP_INFO(logger_, "当前要执行的音频：%s", mark_audio_list[0].c_str());

    mark_audio_list.erase(mark_audio_list.begin());
    setOutput("output_mark_audio_list", mark_audio_list);

    return BT::NodeStatus::SUCCESS;
  }

  bool RemovePassedMarkAudiosNode::GetFixedAudio(const std::string &action_fixed_str_file, const int columnIndex)
  {
    std::ifstream file(action_fixed_str_file);
    if (!file.is_open())
    {
      RCLCPP_ERROR(logger_, "[RemovePassedMarkAudiosNode]无法打开文件 %s", action_fixed_str_file.c_str());
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
      fixed_audio_name_map.insert({columnValues[i], std::to_string(i)});
      RCLCPP_INFO(logger_, "[RemovePassedMarkAudiosNode]固定音频:%s ,下标:%d", columnValues[i].c_str(), i);
    }
  }

} // namespace hintonbot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::RemovePassedMarkAudiosNode>("RemovePassedMarkAudiosNode");
}