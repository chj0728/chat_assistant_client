#pragma once

#include <memory>
#include <string>
#include <fstream>
#include <sstream>
#include <iostream>
#include <vector>

#include "rclcpp/rclcpp.hpp"

#include <yaml-cpp/yaml.h> // 确保包含 YAML 头文件
#include "behaviortree_cpp_v3/action_node.h"

namespace ymrobot
{
    namespace amr_bt
    {
        // 用于存储 CSV 数据
        struct PoseData
        {
            std::string location_name;
            std::string map_name;
            std::string x, y, z;
            std::string roll, pitch, yaw;
            std::string pose_name;
            std::string pose_type;
        };

        class GetStandbyPoint : public BT::SyncActionNode
        {
        public:
            GetStandbyPoint(const std::string &xml_tag_name,
                            const BT::NodeConfiguration &conf);

            static BT::PortsList providedPorts()
            {
                return {BT::InputPort<std::string>("mark_points_adress", "点位文件路径"),
                        BT::OutputPort<std::string>("standby_point", "待命点")};
            }

        private:
            BT::NodeStatus tick() override;
            std::vector<PoseData> ReadCSV(const std::string &file_path);

        private:
            rclcpp::Logger logger_{rclcpp::get_logger("GetStandbyPoint")};
        };
    } // namespace amr_bt
} // namespace ymrobot
