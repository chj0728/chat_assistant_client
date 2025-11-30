/**
 * YMrobot License. All rights reserved.
 * Created by QianHui Gu on 2025-03-26.
 */

#pragma once

#include <chrono>
#include <memory>
#include <string>
#include <iostream>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/bool.hpp>

#include <ymrobot_msgs/action/get_current_task.hpp>
#include "ymrobot_msgs/msg/command.hpp"
#include <ymrobot_msgs/msg/wake_up_word_setting.hpp>

#include <sql_manager.hpp>
#include <yaml-cpp/yaml.h>
#include <fstream>

namespace ymrobot
{
    using GoalHandleSetParams = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::GetCurrentTask>;

    // enum class SetParameterType
    // {
    //     LineSpeedSet = 0,   // 线速度设置
    //     AngularVelocitySet, // 角速度设置
    //     BatteryLevel,       // 电池电量阈值设置
    //     VoiceType,          // 语音音色设置
    //     PendingPointName,   // 待命点设置
    //     IsOpenSolicitation, // 是否打开 招揽功能
    //     WakeWord,           // 唤醒词设置
    //     IsOpenActiveWakeUp, // 是否打开主动唤醒功能
    //     IsOpenPassiveWakeUp // 是否开启被动唤醒功能
    // };

    enum class SetParameterType
    {
        LINEAR_VELOCITY,
        ANGULAR_VELOCITY,
        BATTERY_LEVEL,
        VOICE_TYPE,
        PENDING_POINT_NAME, // 设置待命点
        IS_OPEN_SOLICITATION,
        WAKE_WORD,
        IS_OPEN_ACTIVE_WAKE_UP,                // 是否打开主动唤醒功能
        IS_OPEN_PASSIVE_WAKE_UP,               // 是否打开被动唤醒功能
        ACTIVE_WAKE_UP_THRESHOLD,              // 主动唤醒阈值设置  -- 行人检测阈值
        WELCOME_LANGUAGE_SELECTION,            // 欢迎语选择
        NEAR_POINT_EXPLANATION_ENABLE,         // 就近点讲解功能开启
        CONCESSION_DISTANCE_THRESHOLD_SETTING, // 让步距离阈值设置
        WAKE_WORD_MODIFICATION,                // 唤醒词修改
        SOLICITATION_FUNCTION,                 // 招揽功能
        AI_PERSONA,
        UNKNOWN                                // 用于处理未匹配的情况
    };

    std::map<std::string, SetParameterType> set_params_name_map = {
        {"linear_velocity", SetParameterType::LINEAR_VELOCITY},
        {"angular_velocity", SetParameterType::ANGULAR_VELOCITY},
        {"battery_level", SetParameterType::BATTERY_LEVEL},
        {"voice_type", SetParameterType::VOICE_TYPE},
        {"pending_point_name", SetParameterType::PENDING_POINT_NAME},
        {"is_open_solicitation", SetParameterType::IS_OPEN_SOLICITATION},
        {"wake_word", SetParameterType::WAKE_WORD},
        {"is_open_active_wake_up", SetParameterType::IS_OPEN_ACTIVE_WAKE_UP},
        {"is_open_passive_wake_up", SetParameterType::IS_OPEN_PASSIVE_WAKE_UP},
        {"is_open_near_point_explanation", SetParameterType::NEAR_POINT_EXPLANATION_ENABLE},
        {"concession_distance_threshold", SetParameterType::CONCESSION_DISTANCE_THRESHOLD_SETTING},
        {"is_open_solicitation_function", SetParameterType::SOLICITATION_FUNCTION},
        {"wakeup_welcome_str", SetParameterType::WELCOME_LANGUAGE_SELECTION},
        {"wake_up_word_modification", SetParameterType::WAKE_WORD_MODIFICATION},
        {"ai_persona", SetParameterType::AI_PERSONA}};

    class SetParamsActionbNode : public rclcpp::Node
    {
    public:
        SetParamsActionbNode();
        ~SetParamsActionbNode();

    private:
        void Init();
        void InitParams();
         void InitStandbyPoint();
        void CreateActionServer();

        rclcpp_action::GoalResponse SetParamsHandleGoal(const rclcpp_action::GoalUUID & /*uuid*/, std::shared_ptr<const ymrobot_msgs::action::GetCurrentTask::Goal> goal);
        rclcpp_action::CancelResponse SetParamsHandleCancel(const std::shared_ptr<GoalHandleSetParams> goal_handle);
        void SetParamsHandleAccepted(const std::shared_ptr<GoalHandleSetParams> goal_handle);
        void SetParamsExecuteMove(const std::shared_ptr<GoalHandleSetParams> goal_handle);

        void IsOpenActiveWakeUp(const std::string &is_wake_up);
        void ActiveWakeUpThresholdSetting(const std::string &active_wake_up_threshold_str);
        void WelcomeLanguageSelection(const std::string &welcome_language_selection_str);          // 欢迎语选择
        void IsOpenNearPointExplanation(const std::string &is_open_near_point_explanation_str);    // 是否开启就近点讲解功能
        void SetConcessionDistanceThreshold(const std::string &concession_distance_threshold_str); // 设置让步距离
        void SetPassiveWakeUp(const std::string &is_passive_wake_up_str);                          // 设置被动唤醒
        void SetPendingPointName(const std::string &pending_point_name_str);                       // 设置待命点
        void SetWakeUpWordModification(const std::string &wake_up_word_modification_str);          // 设置唤醒词

        template <typename T>
        void SetYaml(const std::string &yaml_file_path, const std::string &ros2_node_name, const std::string &parameter_name, const T &parameter_value);

    private:
        SqlManagernNode sql_manager_;

        // config
        std::string cloud_chassis_max_linear_speed_pub_name_; // 云迹底盘最大线速度pub
        std::string cloud_chassis_max_angular_speed_pub_name_;
        std::string power_threshold_parameter_update_pub_name_;
        std::string is_open_active_wake_up_name_;                // 是否开启主动唤醒pub名称
        std::string modify_timbre_pub_name_;                     // 修改语音音色
        std::string active_wake_up_threshold_pub_name_;          // 主动唤醒阈值pub
        std::string welcome_language_selection_name_;            // 欢迎语选择pub
        std::string is_open_near_point_explanation_pub_name_;    // 就近点讲解功能开启
        std::string set_params_action_server_name_;              // 设置参数
        std::string voice_interaction_function_switch_pub_name_; // 语音交互功能开关
        std::string mark_points_txt_adress_;                     // 标记点位csv文件
        std::string yaml_file_adress_;                           // yaml文件路径
        std::string concession_distance_threshold_pub_name_;     // 让步距离阈值
        std::string is_open_passive_wake_up_name_;               // 是否开启被动唤醒
        std::string modify_wakeup_word_pub_name_;                // 修改唤醒词

        // action/ topic /service
        rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr cloud_chassis_max_linear_speed_pub_{};         // 发布云迹底盘最大线速度pub
        rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr cloud_chassis_max_angular_speed_pub_{};        // 发布云迹底盘最大角速度pub
        rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr power_threshold_parameter_update_pub_{};       // 回充电量阈值更新pub
        rclcpp::Publisher<std_msgs::msg::String>::SharedPtr modify_timbre_pub_{};                           // 修改语音音色pub
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr is_open_active_wake_up_{};                        // 是否开启主动唤醒功能
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr is_open_passive_wake_up_{};                       // 是否开启被动唤醒功能
        rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr active_wake_up_threshold_pub_{};               // 主动唤醒阈值发布pub
        rclcpp::Publisher<std_msgs::msg::String>::SharedPtr welcome_word_selection_pub_{};                  // 欢迎词选择发布pub
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr voice_interaction_function_switch_pub_{};         // 启动/关闭 语音交互
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr is_open_near_point_explanation_pub_{};            // 启动/关闭 就近点讲解功能
        rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr concession_distance_threshold_pub_{};          // 让步阈值距离发布
        rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr pedestrian_detection_threshold_release_pub_{}; // 行人检测阈值发布
        rclcpp_action::Server<ymrobot_msgs::action::GetCurrentTask>::SharedPtr set_params_action_server_{}; // 设置参数action服务
        rclcpp::Publisher<ymrobot_msgs::msg::WakeUpWordSetting>::SharedPtr modify_wakeup_word_pub_{};       // 设置唤醒词
    };
}