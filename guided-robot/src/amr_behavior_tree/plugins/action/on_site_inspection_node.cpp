
#include <string>
#include <memory>
#include <limits>
#include "amr_behavior_tree/plugins/action/on_site_inspection_node.hpp"

namespace ymrobot
{

  OnSiteInspectionNode::OnSiteInspectionNode(const std::string &service_node_name,
                                             const BT::NodeConfiguration &conf)
      : BT::SyncActionNode(service_node_name, conf)
  {
  }

  BT::NodeStatus OnSiteInspectionNode::tick()
  {
    setStatus(BT::NodeStatus::RUNNING);
    auto current_task_ = ymrobot_msgs::msg::Task();
    std::vector<std::string> mark_nav_target_list;
    std::vector<std::string> audio_list;
    std::vector<std::string> fixed_up_action_list;
    std::vector<std::string> time_of_camera;                   // 录像时长
    std::vector<std::string> camera_interval_list;             // 拍照间隔
    std::vector<std::string> number_of_photos_taken_list;      // 拍照次数
    std::string is_audio_played_throughout_the_entire_process; // 是否全程播放音频
    std::string full_audio_name;                               // 全程音频文件名
    std::string is_the_entire_process_recorded;                // 是否全程录制
    std::vector<std::string> is_activate_the_nearby_point;                  // 是否激活附近点
    std::vector<std::string> nearby_point_radius;              // 就近点距离
    std::vector<ymrobot_msgs::msg::ImageVideo> image_video_message_list;
    getInput("current_task", current_task_);

    // 获取导航点
    for (auto nav_target : current_task_.nav_points)
    {
      std::string target_name = nav_target.nav_name;
      mark_nav_target_list.emplace_back(target_name);
    }

    for (const auto& command : current_task_.commands)
    {
      if(command.params_code == "music")
      {
        for(auto audio : command.params)
        {
          audio_list.emplace_back(audio);
        }
      }
      else if(command.params_code == "up_climb")
      {
        for(auto fixed_up_action : command.params)
        {
          fixed_up_action_list.emplace_back(fixed_up_action);
        }
      }
      else if(command.params_code == "camera_interval")
      {
        for(auto videotape : command.params)
        {
          camera_interval_list.emplace_back(videotape);
        }
      }
      else if(command.params_code == "time_of_camera")
      {
        for(auto image_video_message : command.params)
        {
          time_of_camera.emplace_back(image_video_message);
        }
      }
      else if(command.params_code == "number_of_photos_taken")
      {
        for(auto number_of_photos_taken : command.params)
        {
          number_of_photos_taken_list.emplace_back(number_of_photos_taken);
        }
      }
      else if(command.params_code == "play_audio_throughout_the_entire_process")
      {
        if(command.params[0] == "")
        {
          RCLCPP_INFO(logger_, "是否播放全程音频:  不需要播放音频");
          is_audio_played_throughout_the_entire_process = "0";
          full_audio_name = "";
        }
        else
        {
          is_audio_played_throughout_the_entire_process = "1";
          full_audio_name = command.params[0];
          RCLCPP_INFO(logger_, "是否播放全程音频:  需要播放音频 %s", full_audio_name.c_str());
        }
      }
      else if(command.params_code == "activate_full_video_recording")
      {
        if(command.params[0] == "0")
        {
          RCLCPP_INFO(logger_, "是否录制全程视频:  不需要录制视频");
          is_the_entire_process_recorded = "0";
        }
        else if(command.params[0] == "1")
        {
          is_the_entire_process_recorded = "1";
          RCLCPP_INFO(logger_, "是否录制全程视频:  需要录制视频");
        }
      }
      else if(command.params_code == "is_enbale_nearest_point_disdance")
      {
        if(command.params[0] == "0")
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
        for(auto number_of_photos_taken : command.params)
        {
          nearby_point_radius.emplace_back(number_of_photos_taken);
        }
      }
    }

    for(int i = 0; i < number_of_photos_taken_list.size(); i++)
    {
      ymrobot_msgs::msg::ImageVideo image_video_msg;
      image_video_msg.camera_task_type = 2;
      if(number_of_photos_taken_list[i] == "")
      {
        image_video_msg.number_of_photos = 0;
      }
      else
      {
        image_video_msg.number_of_photos = std::stoi(number_of_photos_taken_list[i]);
        image_video_msg.photos_interval = std::stoi(camera_interval_list[i]);
      }

      if(time_of_camera[i] == "")
      {
        image_video_msg.video_recording_time = 0;
      }
      else
      {
        image_video_msg.video_recording_time = std::stoi(time_of_camera[i]);
      }

      image_video_message_list.emplace_back(image_video_msg);
    }

    auto cycles_num = std::to_string(mark_nav_target_list.size());
    setOutput("the_number_of_cycles", cycles_num);
    setOutput("mark_nav_target_list", mark_nav_target_list);
    setOutput("audio_list", audio_list);
    setOutput("fixed_up_action_list", fixed_up_action_list);
    setOutput("image_video_message_list", image_video_message_list);
    setOutput("is_audio_played_throughout_the_entire_process", is_audio_played_throughout_the_entire_process);
    setOutput("full_audio_name", full_audio_name);
    setOutput("is_the_entire_process_recorded", is_the_entire_process_recorded);
    setOutput("is_activate_the_nearby_point", is_activate_the_nearby_point);
    setOutput("nearby_point_radius", nearby_point_radius);
    return BT::NodeStatus::SUCCESS;
  }

} // namespace ymrobot

#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<ymrobot::OnSiteInspectionNode>("OnSiteInspectionNode");
}
