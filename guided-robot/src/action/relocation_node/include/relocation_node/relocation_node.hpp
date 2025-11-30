#include <chrono>
#include <memory>
#include <fstream>
#include <filesystem>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/u_int8.hpp>
#include <nav2_msgs/srv/load_map.hpp>

#include <ymrobot_msgs/msg/slam_command.hpp>
#include <ymrobot_msgs/srv/slam_task_manage.hpp>
#include <ymrobot_msgs/action/relcation.hpp>
#include <interface/srv/relocalize.hpp>

namespace ymrobot
{
    using RelocationAction = ymrobot_msgs::action::Relcation;
    using GoalHandleRelocation = rclcpp_action::ServerGoalHandle<RelocationAction>;

    class RelocationNode : public rclcpp::Node
    {
    public:
        RelocationNode();
        // ~RelocationNode();

    private:
        void Init();               // 初始化
        void InitParams();         // 初始化参数
        void CreateActionServer(); // 创建action服务

        bool IsMapFileExist(const std::string &path);         // 判断地图文件是否存在
        bool LoadMap(const std::string &map_yaml_path);       // 加载地图文件
        bool StartLocalizerSlam(const std::string &pcd_path); // 启动重定位SLAM

        rclcpp_action::GoalResponse HandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const RelocationAction::Goal> goal); // 接受任务
        void HandleAccepted(const std::shared_ptr<GoalHandleRelocation> goal_handle);                                                    // 接受任务
        rclcpp_action::CancelResponse HandleCancel(const std::shared_ptr<GoalHandleRelocation> goal_handle);                             // 取消任务
        void Execute(const std::shared_ptr<GoalHandleRelocation> goal_handle);

    private:
        rclcpp::Logger logger_{rclcpp::get_logger("RelocationNode")};

        // config
        std::string relcation_action_str_;      // 重定位Action名称
        std::string relocalizer_task_srv_name_; // 重定位SLAM服务名
        std::string re_pcd_srv_name_;           // 重定位SLAM服务名
        std::string maps_dir_;                  // 地图文件目录

        // action / topic / service
        rclcpp::Publisher<std_msgs::msg::UInt8>::SharedPtr map_mode_pub_{};                // 地图模式发布
        rclcpp::Client<nav2_msgs::srv::LoadMap>::SharedPtr nav2_map_client_{};             // 地图客户端
        rclcpp::Client<ymrobot_msgs::srv::SlamTaskManage>::SharedPtr reloclizer_client_{}; // 重定位客户端
        rclcpp::Client<interface::srv::Relocalize>::SharedPtr reloclizer_pcd_client_{};    // 重定位客户端
        rclcpp_action::Server<RelocationAction>::SharedPtr relcation_action_server_{};     // 重定位action服务
    };
} // namespace name
