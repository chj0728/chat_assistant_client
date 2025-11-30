
#include <string>
#include <memory>
#include <limits>
#include "amr_behavior_tree/plugins/action/traverse_guidance_node.hpp"

namespace ymrobot
{

  TraverseNavPose::TraverseNavPose(const std::string &service_node_name,
                                   const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
  }

  BT::NodeStatus TraverseNavPose::tick()
  {
    setStatus(BT::NodeStatus::RUNNING);
    auto current_task_ = ymrobot_msgs::msg::Task();
    std::vector<std::string> mark_nav_target_list;
    std::vector<std::string> audio_list;
    std::vector<std::string> fixed_up_action_list;
    std::vector<std::string> is_skip_list;
    std::vector<std::string> is_activate_the_nearby_point;     // 是否激活附近点
    std::vector<std::string> nearby_point_radius; // 就近点距离
    std::string task_id;
    getInput("current_task", current_task_);

    task_id = current_task_.task_id;
    for (auto nav_target : current_task_.nav_points)
    {
      std::string target_name = nav_target.nav_name;
      mark_nav_target_list.emplace_back(target_name);
    }

    for (const auto &command : current_task_.commands)
    {
      if (command.params_code == "music")
      {
        for (auto audio : command.params)
        {
          audio_list.emplace_back(audio);
        }
      }
      else if (command.params_code == "up_climb")
      {
        for (auto fixed_up_action : command.params)
        {
          fixed_up_action_list.emplace_back(fixed_up_action);
        }
      }
      else if (command.params_code == "activate_nearest_point")
      {
        if (command.params[0] == "0")
        {
          RCLCPP_INFO(logger_, "是否激活附近点:  不需要激活附近点");
          is_activate_the_nearby_point.emplace_back("0");
        }
        else
        {
          is_activate_the_nearby_point.emplace_back("1");
          RCLCPP_INFO(logger_, "是否激活附近点:  需要激活附近点");
        }
      }
      else if (command.params_code == "nearest_point_disdance")
      {
        for (auto number_of_photos_taken : command.params)
        {
          nearby_point_radius.emplace_back(number_of_photos_taken);
        }
      }
      else if (command.params_code == "skip")
      {
        for (auto is_skip : command.params)
        {
          is_skip_list.emplace_back(is_skip);
        }
      }
    }

    // for (auto audio : current_task_.commands[0].params)
    // {
    //   audio_list.emplace_back(audio);
    // }

    // for (auto fixed_up_action : current_task_.commands[1].params)
    // {
    //   fixed_up_action_list.emplace_back(fixed_up_action);
    // }

    // for (auto is_skip : current_task_.commands[3].params)
    // {
    //   is_skip_list.emplace_back(is_skip);
    // }
    auto cycles_num = std::to_string(mark_nav_target_list.size());
    std::cout << "cycles_num:{}" << cycles_num << std::endl;

    setOutput("the_number_of_cycles", cycles_num);
    setOutput("mark_nav_target_list", mark_nav_target_list);
    setOutput("audio_list", audio_list);
    setOutput("fixed_up_action_list", fixed_up_action_list);
    setOutput("is_skip_list", is_skip_list);
    setOutput("is_activate_the_nearby_point", is_activate_the_nearby_point);
    setOutput("nearby_point_radius", nearby_point_radius);
    setOutput("task_id", task_id);

    RCLCPP_INFO(logger_, "导览业务行为树，一共有 %s 个循环", cycles_num.c_str());
    RCLCPP_INFO(logger_, "导览业务行为树，导航点列表：");
    for (auto a : mark_nav_target_list)
    {
      RCLCPP_INFO(logger_, "%s", a.c_str());
    }
    RCLCPP_INFO(logger_, "导览业务行为树，音频列表：");
    for (auto b : audio_list)
    {
      RCLCPP_INFO(logger_, "%s", b.c_str());
    }
    RCLCPP_INFO(logger_, "导览业务行为树，固定上肢动作列表：");
    for (auto c : fixed_up_action_list)
    {
      RCLCPP_INFO(logger_, "%s", c.c_str());
    }
    return BT::NodeStatus::SUCCESS;
  }

} // namespace ymrobot

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::TraverseNavPose>("TraverseNavPose");
}
