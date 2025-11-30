#include <chrono>
#include <memory>
#include <string>
#include <vector>
#include <thread>
#include <fstream>
#include <filesystem>
#include <variant>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include <nav2_msgs/action/navigate_through_poses.hpp>
#include <nav2_msgs/action/navigate_to_pose.hpp>
#include <nav2_msgs/srv/load_map.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include "nav2_behavior_tree/behavior_tree_engine.hpp"
#include "nav2_behavior_tree/ros_topic_logger.hpp"
#include "std_msgs/msg/string.hpp"
#include <std_msgs/msg/u_int8.hpp>
#include <std_msgs/msg/bool.hpp>

#include <ymrobot_msgs/msg/task.hpp>
#include <ymrobot_msgs/msg/task_status.hpp>
#include <ymrobot_msgs/msg/task_status_code.hpp>
#include <ymrobot_msgs/msg/map_manage.hpp>
#include <ymrobot_msgs/msg/map_task_command.hpp>
#include <ymrobot_msgs/msg/slam_command.hpp>
#include <ymrobot_msgs/msg/dot_points.hpp>
#include <ymrobot_msgs/msg/dot_points_list.hpp>
#include <ymrobot_msgs/srv/slam_task_manage.hpp>
#include <ymrobot_msgs/srv/map_task_manage.hpp>
#include <interface/srv/relocalize.hpp>
#include <interface/srv/save_maps.hpp>
#include <sql_manager.hpp>
// #include <boost/algorithm/string.hpp>  // 启用 可能有问题

using FieldType = std::variant<int, double, std::string>;

namespace ymrobot
{
    // 任务结果
    enum class TaskResult : uint8_t
    {
        SUCCEEDED = 0,
        FAILED,
        CANCELED,
        PAUSED
    };

    class TaskGuidance : public rclcpp::Node
    {
    public:
        TaskGuidance();
        //~TaskGuidance();

    private:
        void Init();

        void InitParams();   // 初始化参数
        void InitDataBase(); // 初始化数据库
        void InitBehaviorTree();
        void CreatePubService();
        void TaskSubCallback(const ymrobot_msgs::msg::Task::SharedPtr msg);
        void ParseTask(const ymrobot_msgs::msg::Task::SharedPtr msg);

        void PauseTask();
        void ResumeTask();
        void CancelTask();
        void Relocalize(const std::shared_ptr<ymrobot_msgs::msg::Task> &task);
        void MapManager(const std::shared_ptr<ymrobot_msgs::msg::Task> &task);
        void StartBehaviorTreeTask(const std::shared_ptr<ymrobot_msgs::msg::Task> &task);

        bool LoadBehaviorTree(const std::string &bt_xml = "", const bool reload = false);
        bool IsCurrentTaskEmpty(const ymrobot_msgs::msg::Task &task);
        bool IsCurrentTaskEmptyForMuiltCommands(const ymrobot_msgs::msg::Task &task);
        std::string GetDefaultBtFilepath();
        ymrobot_msgs::msg::Task GetCurrentTask();

        void ExecuteBehaviorTreeTask();
        void ExecuteCallback();
        void NavModeSelect(const std::shared_ptr<ymrobot_msgs::msg::Task> &task);
        void MultFloorNav();

        // slam建图、重定位执行模块
        bool SavePcdMap(const std::string &pcd_file_path);
        bool SavePgmMap(const std::string &pcd_name, const std::string &pgm_name);
        bool StopPgoSlam();
        bool StartLocalizerSlam(const std::string &pcd_path);
        bool LoadMap(const std::string &map_yaml_path);
        bool IsMapFileExist(const std::string &path);

        // 数据库
        void CreateDir(const std::string &file_path);  // 创建文件夹
        void CreateFile(const std::string &file_path); // 创建文件

        // 任务状态
        bool OnTaskReceivedCallback(const ymrobot_msgs::msg::Task &task);
        void OnLoopCallback();
        void OnPreemptCallback();
        void OnPauseCallback();
        void OnResumeCallback();
        void OnCompletionCallback(const TaskResult &task_result);

    private:
        rclcpp::Logger logger_{rclcpp::get_logger("TaskGuidance")};

        BT::Tree tree_;
        BT::Blackboard::Ptr blackboard_;
        std::unique_ptr<nav2_behavior_tree::BehaviorTreeEngine> bt_;
        std::chrono::milliseconds bt_loop_duration_;
        std::chrono::milliseconds default_server_timeout_;

        SqlManagernNode sql_manager_;

        // topic\service\action
        rclcpp::Subscription<ymrobot_msgs::msg::Task>::SharedPtr task_sub_{};                   // 任务订阅topic
        rclcpp::Publisher<ymrobot_msgs::msg::TaskStatus>::SharedPtr task_state_pub_{};          // 任务状态发布topic
        rclcpp::Publisher<std_msgs::msg::UInt8>::SharedPtr map_mode_pub_{};                     // 地图模式发布topic
        rclcpp::Publisher<ymrobot_msgs::msg::DotPointsList>::SharedPtr dot_point_update_pub_{}; // 点位反馈更新topic
        rclcpp::Publisher<std_msgs::msg::String>::SharedPtr cancel_current_task_{};             // 取消任务topic
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr emergency_stop_machine_pub_{};        // 发布急停移动topic
        rclcpp::Client<nav2_msgs::srv::LoadMap>::SharedPtr nav2_map_client_{};                  // 加载地图客户端
        rclcpp::Client<ymrobot_msgs::srv::SlamTaskManage>::SharedPtr build_map_client_{};
        rclcpp::Client<interface::srv::SaveMaps>::SharedPtr save_pcd_client_{};
        rclcpp::Client<ymrobot_msgs::srv::MapTaskManage>::SharedPtr save_pgm_client_{};
        rclcpp::Client<ymrobot_msgs::srv::SlamTaskManage>::SharedPtr reloclizer_client_{};
        rclcpp::Client<interface::srv::Relocalize>::SharedPtr reloclizer_pcd_client_{};
        rclcpp_action::Client<nav2_msgs::action::NavigateThroughPoses>::SharedPtr multipose_nav_client_{};
        rclcpp_action::Client<nav2_msgs::action::NavigateToPose>::SharedPtr pose_nav_client_{};

        // config
        bool is_used_tree_;
        std::string platform_id_;
        std::string amr_id_;
        std::string task_topic_;
        std::string task_states_feedback_topic_;
        std::string emergency_stop_machine_pub_topic_;
        std::string db_path_;
        std::string maps_dir_;
        std::string slam_task_srv_name_;
        std::string relocalizer_task_srv_name_;
        std::string save_pcd_srv_name_;
        std::string save_pgm_srv_name_;
        std::string re_pcd_srv_name_;
        std::vector<std::string> plugin_lib_names_;
        std::string default_bt_xml_filename_;
        int timeout_;
        std::string points_db_path_;
        std::string map_db_path_;
        std::string dot_point_update_topic_;       // 点位反馈更新topic
        std::string cancel_current_task_pub_name_; // 取消当前任务

        std::string current_bt_xml_filename_;
        std::shared_ptr<ymrobot_msgs::msg::Task> current_task_{};
        ymrobot_msgs::msg::TaskStatus task_status_;
        mutable std::mutex task_mutex_; // 任务的互斥锁
        std::mutex status_mutex_;       // 任务状态的互斥锁
        std::future<void> task_future_;

        std::atomic<bool> is_cancel_requested_{false};
        std::atomic<bool> is_pause_requested_{false};

        rclcpp::Node::SharedPtr parent;
    };
}

bool ends_with(std::string_view str, std::string_view suffix)
{
    return str.size() >= suffix.size() &&
           str.compare(str.size() - suffix.size(), suffix.size(), suffix) == 0;
}