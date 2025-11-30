/**
 * ymrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-02-06
 */

#pragma once

#include <memory>
#include <string>

#include "behaviortree_cpp_v3/action_node.h"
#include <tf2/LinearMath/Quaternion.h>
#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>

#include "ymrobot_msgs/msg/task.hpp"
#include <ymrobot_msgs/msg/voice_message.hpp>
#include <ymrobot_msgs/msg/image_video.hpp>
#include <ymrobot_msgs/msg/patrol_mission.hpp>

namespace ymrobot
{
    namespace amr_bt
    {
        // 行为树index解析
        std::map<uint8_t, std::string> bt_action_index_map =
            {
                {ymrobot_msgs::msg::Command::NONE, "0"},                                // 无命令
                {ymrobot_msgs::msg::Command::REGISTER, "1"},                            // 注册
                {ymrobot_msgs::msg::Command::LOG_OFF, "2"},                             // 注销
                {ymrobot_msgs::msg::Command::PAUSE, "3"},                               // 暂停操作
                {ymrobot_msgs::msg::Command::RESUME, "4"},                              // 恢复操作
                {ymrobot_msgs::msg::Command::CANCLE, "5"},                              // 取消任务操作
                {ymrobot_msgs::msg::Command::WAIT, "6"},                                // 进入休眠模式
                {ymrobot_msgs::msg::Command::FINISH_WAIT, "7"},                         // 从休眠模式唤醒
                {ymrobot_msgs::msg::Command::CHARGE, "8"},                              // 回冲
                {ymrobot_msgs::msg::Command::FINISH_CHARGE, "9"},                       // 结束回冲
                {ymrobot_msgs::msg::Command::BUILD_MAP, "10"},                          // 建图
                {ymrobot_msgs::msg::Command::UPLOAD_MAP, "11"},                         // 更新地图
                {ymrobot_msgs::msg::Command::DOWNLOAD_MAP, "12"},                       // 下载地图
                {ymrobot_msgs::msg::Command::SAVE_MAP, "13"},                           // 保存地图
                {ymrobot_msgs::msg::Command::RELOCALIZE, "14"},                         // 重定位
                {ymrobot_msgs::msg::Command::NAVIGATION, "15"},                         // 导航
                {ymrobot_msgs::msg::Command::MULIT_POINTS_NAVIGATION, "16"},            // 多点导航
                {ymrobot_msgs::msg::Command::MULIT_FLOOR_NAVIGATION, "17"},             // 跨楼层导航（只适合单点）
                {ymrobot_msgs::msg::Command::DOT, "18"},                                // 打点
                {ymrobot_msgs::msg::Command::CLOUD_NAVIGATION, "19"},                   // 云迹单点导航
                {ymrobot_msgs::msg::Command::CLOUD_MULIT_POINTS_NAVIGATION, "20"},      // 云迹多点导航
                {ymrobot_msgs::msg::Command::CLOUD_NAVIGATION_NAME, "21"},              // 云迹单点点位名称导航
                {ymrobot_msgs::msg::Command::CLOUD_MULIT_POINTS_NAVIGATION_NAME, "22"}, // 云迹多点点位名导航
                {ymrobot_msgs::msg::Command::MANUAL_CONTROL_MOVE, "23"},                // 遥控控制移动
                {ymrobot_msgs::msg::Command::EXE_BEHAVIOR_TREE, "24"},                  // 执行行为树
                {ymrobot_msgs::msg::Command::PLACE_CARTESIAN, "25"},                    // 末端变化（笛卡尔坐标）导航
                {ymrobot_msgs::msg::Command::PLACE_JOINT, "26"},                        // 关节变化导航
                {ymrobot_msgs::msg::Command::PLACE_FIXED, "27"},                        // 上肢预设动作执行
                {ymrobot_msgs::msg::Command::PLACE_CONTROL_MODE, "28"},                 // 上肢控制模式切换
                {ymrobot_msgs::msg::Command::GRASP, "29"},                              // 夹爪动作
                {ymrobot_msgs::msg::Command::CAMERA, "30"},                             // 相机
                {ymrobot_msgs::msg::Command::PLAY_FIX_AUDIO, "31"},                     // 播放固定音频
                {ymrobot_msgs::msg::Command::TXT_2_AUDIO, "32"},                        // 文字转语音
                {ymrobot_msgs::msg::Command::SPEECH_2_TXT, "33"},                       // 语音转文字（在线和离线都有）
                {ymrobot_msgs::msg::Command::EXPRESSION_FIXED, "34"},                   // 表情预设执行动作
                {ymrobot_msgs::msg::Command::WAKE_UP, "35"},                            // 唤醒
                {ymrobot_msgs::msg::Command::POWER_OFF, "36"},                          // 远程关机
                {ymrobot_msgs::msg::Command::SETTING_PARAMETERS, "37"},                 // 设置参数
                {ymrobot_msgs::msg::Command::SYNTHETIC_AUDIO, "38"},                    // 删掉固定音频
                {ymrobot_msgs::msg::Command::VOICE_INTERACTION_FUNCTION_SWITCH, "39"},  // 启动/关闭 语音交互功能开关
                {ymrobot_msgs::msg::Command::UPLOAD_VOICE_CONVERSATION_LOGS, "40"},     // 上传语音对话日志
                {ymrobot_msgs::msg::Command::UPLOAD_OPERATION_LOGS, "41"},              // 上传运行日志
                {ymrobot_msgs::msg::Command::PLAY_ONLINE_AUDIO, "42"},                  // 播放在线音频
                {ymrobot_msgs::msg::Command::PHOTOGRAPH, "42"}                          // 拍照       
        };

        std::map<std::string, std::string> bt_tree_index_map =
            {
                {"guide_explanation", "1"},
                {"poetry_recitation", "2"},
                {"patrol", "3"}  // 巡逻巡检
            };

        class ParsetaskNode : public BT::SyncActionNode
        {
        public:
            ParsetaskNode(const std::string &xml_tag_name,
                          const BT::NodeConfiguration &conf);

            static BT::PortsList providedPorts()
            {
                return {
                    BT::InputPort<ymrobot_msgs::msg::Task>("current_task", "The task currently received"),

                    BT::OutputPort<std::string>("behavior_index", "nav point selected"),
                    BT::OutputPort<std::string>("bt_tree_behavior_index", "nav point selected"),

                    BT::OutputPort<std::string>("nav_pose_name", "nav point selected"),
                    BT::OutputPort<std::string>("nav_pose_name_list", "nav point selected"),
                    BT::OutputPort<geometry_msgs::msg::PoseStamped>("nav_goal", "nav point selected"),
                    BT::OutputPort<std::vector<geometry_msgs::msg::PoseStamped>>("nav_goals", "nav point selected"),
                    BT::OutputPort<std::string>("map_name", "nav point selected"),
                    BT::OutputPort<std::string>("fixed_action", "上肢固定动作"),   
                    BT::OutputPort<ymrobot_msgs::msg::VoiceMessage>("voice_message", "语音消息"),
                    BT::OutputPort<ymrobot_msgs::msg::ImageVideo>("image_video", "图像视频消息"),
                    BT::OutputPort<ymrobot_msgs::msg::PatrolMission>("patrol_mission", "巡逻巡检任务"),
                    // BT::OutputPort<std::string>("task_id", "任务id"),
                };
            }

        private:
            BT::NodeStatus tick() override;
            rclcpp::Logger logger_{rclcpp::get_logger("ParsetaskNode")};  // 解析任务节点
        };
    } // namespace amr_bt
} // namespace ymrobot
