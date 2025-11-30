/**
 * HintonBot License. All rights reserved.
 * Created by Hao Wang on 2024-10-21
 */

#include "amr_behavior_tree/plugins/action/parse_task_node.hpp"

#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>

namespace ymrobot
{
  namespace amr_bt
  {
    ParsetaskNode::ParsetaskNode(const std::string &service_node_name,
                                 const BT::NodeConfiguration &conf)
        : BT::SyncActionNode(service_node_name, conf)
    {
    }

    BT::NodeStatus ParsetaskNode::tick()
    {
      ymrobot_msgs::msg::Task current_task{};
      std::string behavior_index_;
      std::string bt_tree_behavior_index_;
      std::string nav_pose_name_ = "";
      std::string fixed_action_ = "";
      ymrobot_msgs::msg::VoiceMessage voice_message_;
      ymrobot_msgs::msg::ImageVideo image_video_;

      if (!getInput("current_task", current_task))
      {
        RCLCPP_ERROR(logger_, "解析任务行为树，没有收到任务");
        return BT::NodeStatus::FAILURE;
      }

      const auto commands = current_task.commands;
      if (commands.empty())
      {
        return BT::NodeStatus::FAILURE;
      }

      for (auto &&command : commands)
      {
        switch (command.code)
        {
        case ymrobot_msgs::msg::Command::NAVIGATION:
        case ymrobot_msgs::msg::Command::CLOUD_NAVIGATION:
        {
          geometry_msgs::msg::PoseStamped pose;
          pose = current_task.nav_points[0].position;
          pose.header.stamp = rclcpp::Clock(RCL_ROS_TIME).now();
          pose.header.frame_id = "map";
          break;
        }
        case ymrobot_msgs::msg::Command::MULIT_POINTS_NAVIGATION:
        {
          std::vector<geometry_msgs::msg::PoseStamped> poses;
          for (auto &&nav_point : current_task.nav_points)
          {
            geometry_msgs::msg::PoseStamped pose;
            pose = nav_point.position;
            pose.header.stamp = rclcpp::Clock(RCL_ROS_TIME).now();
            pose.header.frame_id = "map";
            poses.emplace_back(pose);
          }
          break;
        }
        case ymrobot_msgs::msg::Command::CLOUD_NAVIGATION_NAME:
        case ymrobot_msgs::msg::Command::CLOUD_MULIT_POINTS_NAVIGATION:
        {
          std::string nav_goal_name;
          nav_goal_name = current_task.nav_points[0].nav_name;
          RCLCPP_INFO(logger_, "要导航的点位名，%s", nav_goal_name);
          nav_pose_name_ = nav_goal_name;
          behavior_index_ = bt_action_index_map[command.code];
          RCLCPP_INFO(logger_, "解析任务行为树序号为：%s", behavior_index_);
          break;
        }
        case ymrobot_msgs::msg::Command::CLOUD_MULIT_POINTS_NAVIGATION_NAME:
        {
          std::vector<std::string> nav_goal_names;
          for (auto &&nav_point : current_task.nav_points)
          {
            nav_goal_names.emplace_back(nav_point.nav_name);
          }
          break;
        }
        case ymrobot_msgs::msg::Command::CHARGE:
        case ymrobot_msgs::msg::Command::FINISH_CHARGE:
        case ymrobot_msgs::msg::Command::BUILD_MAP:
        case ymrobot_msgs::msg::Command::UPLOAD_MAP:
        case ymrobot_msgs::msg::Command::SAVE_MAP:
        case ymrobot_msgs::msg::Command::RELOCALIZE:
        case ymrobot_msgs::msg::Command::MULIT_FLOOR_NAVIGATION:
        case ymrobot_msgs::msg::Command::DOT:
        case ymrobot_msgs::msg::Command::MANUAL_CONTROL_MOVE:
        case ymrobot_msgs::msg::Command::PLACE_CARTESIAN:
        case ymrobot_msgs::msg::Command::PLACE_JOINT:
        case ymrobot_msgs::msg::Command::PLACE_CONTROL_MODE:
        case ymrobot_msgs::msg::Command::GRASP:
        case ymrobot_msgs::msg::Command::SPEECH_2_TXT:
        case ymrobot_msgs::msg::Command::EXPRESSION_FIXED:
        case ymrobot_msgs::msg::Command::SETTING_PARAMETERS:
        case ymrobot_msgs::msg::Command::WAKE_UP:
        case ymrobot_msgs::msg::Command::UPLOAD_OPERATION_LOGS:
        {
          behavior_index_ = bt_action_index_map[command.code];
          RCLCPP_INFO(logger_, "解析任务行为树序号为：%s", behavior_index_.c_str());
          break;
        }
        case ymrobot_msgs::msg::Command::PLACE_FIXED:
        {
          behavior_index_ = bt_action_index_map[command.code];
          fixed_action_ = current_task.commands[0].params[0];
          RCLCPP_INFO(logger_, "解析任务行为树序号为：%s", behavior_index_.c_str());
          break;
        }
        case ymrobot_msgs::msg::Command::EXE_BEHAVIOR_TREE:
        {
          RCLCPP_INFO(logger_, "执行行为树--子树任务");
          behavior_index_ = bt_action_index_map[command.code];
          bt_tree_behavior_index_ = bt_tree_index_map[current_task.behavior_tree];
          RCLCPP_INFO(logger_, "执行行为树行为，子行为为： %s", bt_tree_behavior_index_.c_str());
          // break;
          setOutput("nav_pose_name", nav_pose_name_);
          setOutput("behavior_index", behavior_index_);
          setOutput("bt_tree_behavior_index", bt_tree_behavior_index_);
          return BT::NodeStatus::SUCCESS;
        }
        case ymrobot_msgs::msg::Command::PLAY_FIX_AUDIO:
        {
          RCLCPP_INFO(logger_, "播放固定音频");
          behavior_index_ = bt_action_index_map[command.code];
          voice_message_.fixed_audio_name = current_task.commands[0].params[0];
          voice_message_.audio_task_type = 0;
          setOutput("behavior_index", behavior_index_);
          setOutput("voice_message", voice_message_);
          break;
        }
        case ymrobot_msgs::msg::Command::TXT_2_AUDIO:
        {
          RCLCPP_INFO(logger_, "文本转音频");
          behavior_index_ = bt_action_index_map[command.code];
          voice_message_.synthetic_audio_title = current_task.commands[0].params_code;
          voice_message_.synthetic_audio_txt = current_task.commands[0].params[0];
          voice_message_.audio_task_type = 1;
          voice_message_.timbre = current_task.commands[0].params[1];
          std::cout << "文本转音频,音色为" << voice_message_.timbre << std::endl;
          setOutput("behavior_index", behavior_index_);
          setOutput("voice_message", voice_message_);
          return BT::NodeStatus::SUCCESS;
          break;
        }
        case ymrobot_msgs::msg::Command::UPLOAD_VOICE_CONVERSATION_LOGS:
        {
          RCLCPP_INFO(logger_, "上传语音对话日志");
          behavior_index_ = bt_action_index_map[command.code];
          voice_message_.audio_task_type = 3;
          setOutput("behavior_index", behavior_index_);
          setOutput("voice_message", voice_message_);
          return BT::NodeStatus::SUCCESS;
          break;
        }
        case ymrobot_msgs::msg::Command::PLAY_ONLINE_AUDIO:
        {
          RCLCPP_INFO(logger_, "播放在线音频");
          behavior_index_ = bt_action_index_map[command.code];
          voice_message_.audio_task_type = 4;
          voice_message_.play_online_audio = current_task.commands[0].params[0];
          voice_message_.timbre = current_task.commands[0].params[1];
          setOutput("behavior_index", behavior_index_);
          setOutput("voice_message", voice_message_);
          return BT::NodeStatus::SUCCESS; // bug 嘿嘿
          break;
        }
        case ymrobot_msgs::msg::Command::PHOTOGRAPH:
        {
          RCLCPP_INFO(logger_, "执行拍照功能");
          behavior_index_ = bt_action_index_map[command.code];
          image_video_.camera_task_type = 0;
          image_video_.number_of_photos = std::stoi(current_task.commands[0].params[0]);
          image_video_.photos_interval = std::stoi(current_task.commands[1].params[0]);
          setOutput("image_video", image_video_);
          setOutput("behavior_index", behavior_index_);
          RCLCPP_INFO(logger_, "执行拍照功能，拍照次数、拍照间隔参数为：%d, %d", image_video_.number_of_photos, image_video_.photos_interval);
          RCLCPP_INFO(logger_, "behavior_index_ %s", behavior_index_.c_str());
          return BT::NodeStatus::SUCCESS; // bug 嘿嘿
        }
        case ymrobot_msgs::msg::Command::CAMERA:
        {
          RCLCPP_INFO(logger_, "执行录像功能");
          behavior_index_ = bt_action_index_map[command.code];
          image_video_.camera_task_type = 1;
          image_video_.video_recording_time = std::stoi(current_task.commands[0].params[0]);
          setOutput("image_video", image_video_);
          setOutput("behavior_index", behavior_index_);
          RCLCPP_INFO(logger_, "执行录像功能，录像时长为:%d", image_video_.video_recording_time);
          return BT::NodeStatus::SUCCESS;
        }
        default:
        {
          RCLCPP_ERROR(logger_, "解析任务行为树，没有找到对应的命令");
          return BT::NodeStatus::FAILURE;
        }
        }
      }

      setOutput("nav_pose_name", nav_pose_name_);
      setOutput("behavior_index", behavior_index_);
      setOutput("bt_tree_behavior_index", bt_tree_behavior_index_);
      setOutput("fixed_action", fixed_action_);
      return BT::NodeStatus::SUCCESS;
    }
  }

} // namespace hintonbot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<amr_bt::ParsetaskNode>("ParsetaskNode");
}