/**
 * HintonBot License. All rights reserved.
 * Created by Zewei Ding on 24-4-20.
 */

#include "amr_behavior_tree/plugins/action/get_standby_point_node.hpp"

#include <memory>
#include <string>

namespace ymrobot
{
  namespace amr_bt
  {
    GetStandbyPoint::GetStandbyPoint(const std::string &service_node_name,
                                     const BT::NodeConfiguration &conf)
        : BT::SyncActionNode(service_node_name, conf)
    {
    }

    // BT::NodeStatus GetStandbyPoint::tick()
    // {
    //   std::string mark_points_adress_;
    //   getInput("mark_points_adress", mark_points_adress_);
    //   RCLCPP_INFO(logger_, "点位文件路径:%s", mark_points_adress_.c_str());
    //   auto poses = ReadCSV(mark_points_adress_);

    //   for (const auto &pose : poses)
    //   {
    //     if (pose.pose_type == "1")
    //     {
    //       setOutput("standby_point", pose.pose_name); // 设置输出变量
    //       RCLCPP_INFO(logger_, "找到待命点: %s", pose.pose_name.c_str());
    //       return BT::NodeStatus::SUCCESS;
    //     }
    //   }
    //   RCLCPP_ERROR(logger_, "没有找到待命点");
    //   return BT::NodeStatus::FAILURE;
    // }

    BT::NodeStatus GetStandbyPoint::tick()
    {
      std::string yaml_file_path;
      getInput("mark_points_adress", yaml_file_path); // 从行为树输入获取 YAML 文件路径

      RCLCPP_INFO(logger_, "yaml文件地址: %s", yaml_file_path.c_str());
      try
      {
        YAML::Node config = YAML::LoadFile(yaml_file_path);

        if (config["robot"] && config["robot"]["standby_point"])
        {
          std::string standby_point = config["robot"]["standby_point"].as<std::string>();
          RCLCPP_INFO(logger_, "从 YAML 读取待命点: %s", standby_point.c_str());
          setOutput("standby_point", standby_point);
          return BT::NodeStatus::SUCCESS;
        }
        else
        {
          RCLCPP_ERROR(logger_, "YAML 文件中未找到 robot.standby_point 字段");
          return BT::NodeStatus::FAILURE;
        }
      }
      catch (const YAML::Exception &e)
      {
        RCLCPP_ERROR(logger_, "YAML 文件解析失败: %s", e.what());
        return BT::NodeStatus::FAILURE;
      }
    }

    std::vector<PoseData> GetStandbyPoint::ReadCSV(const std::string &file_path)
    {
      std::vector<PoseData> poses;
      std::ifstream file(file_path);

      if (!file.is_open())
      {
        std::cerr << "Error opening file: " << file_path << std::endl;
        return poses;
      }

      std::string line;
      bool is_header = true;

      while (std::getline(file, line))
      {
        if (is_header)
        {
          is_header = false; // 跳过头行
          continue;
        }

        std::stringstream ss(line);
        PoseData pose;

        std::getline(ss, pose.location_name, ',');
        std::getline(ss, pose.map_name, ',');
        std::getline(ss, pose.x, ',');
        std::getline(ss, pose.y, ',');
        std::getline(ss, pose.z, ',');
        std::getline(ss, pose.roll, ',');
        std::getline(ss, pose.pitch, ',');
        std::getline(ss, pose.yaw, ',');
        std::getline(ss, pose.pose_name, ',');
        std::getline(ss, pose.pose_type);

        poses.push_back(pose);
      }

      return poses;
    }
  }
} // namespace ymrobot

using namespace ymrobot;
#include "behaviortree_cpp_v3/bt_factory.h"
BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<amr_bt::GetStandbyPoint>("GetStandbyPoint");
}