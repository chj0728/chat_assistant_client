#ifndef _ROBOT_POSE_DOT_H_
#define _ROBOT_POSE_DOT_H_

#include <vector>
#include <fstream>

#include "rclcpp/rclcpp.hpp"
#include <rclcpp_action/rclcpp_action.hpp>
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "tf2_ros/transform_listener.h"
#include "tf2_ros/buffer.h"
#include "std_msgs/msg/string.hpp"

#include <ymrobot_msgs/action/pose_manager.hpp>
#include <ymrobot_msgs/msg/update_list.hpp>
#include <sql_manager.hpp>

namespace ymrobot
{
    using GoalHandlePoseManager = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::PoseManager>;

    class RobotPoseManagerActionNode : public rclcpp::Node
    {
    public:
        RobotPoseManagerActionNode();
        //~RobotPoseManagerActionNode();

    private:
        void Init();
        void InitParams();
        void CreatePubSub();
        void InitPoseData();

        rclcpp_action::GoalResponse HandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::PoseManager::Goal> goal); // 接受任务
        void HandleAccepted(const std::shared_ptr<GoalHandlePoseManager> goal_handle);                                                                    // 接受任务
        rclcpp_action::CancelResponse HandleCancel(const std::shared_ptr<GoalHandlePoseManager> goal_handle);                                             // 取消任务
        void Execute(const std::shared_ptr<GoalHandlePoseManager> goal_handle);

        void RecordCurrentRobotPose(const std::string &pose_name, const std::string &map_name, const std::string &pose_describe, const std::string &pose_manager_csv_adress);
        void DelectPose(const std::string &pose_name, const std::string &pose_manager_csv_adress);

        geometry_msgs::msg::PoseStamped GetCurrentPose();

    private:
        SqlManagernNode sql_manager_;

        std::string pose_manager_action_name_;
        std::string save_pose_str_;
        std::string delete_pose_str_;
        std::string pose_manager_csv_adress_; // 点位数据库文件地址

        std::shared_ptr<tf2_ros::Buffer> tf_buffer_;
        std::shared_ptr<tf2_ros::TransformListener> tf_listener_;

        rclcpp::Publisher<ymrobot_msgs::msg::UpdateList>::SharedPtr update_list_pub_{};                    // 数据更新列表发布者
        rclcpp_action::Server<ymrobot_msgs::action::PoseManager>::SharedPtr pose_manager_action_server_{}; // 重定位action服务

        std::vector<std::string> pose_name_headers_;
        std::string update_list_topic_name_;
    };
}

#endif