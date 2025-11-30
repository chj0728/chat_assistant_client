#include <iostream>
#include <thread>
#include <string>
#include <atomic>
#include <zmq.hpp>
#include <mutex>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <shared_mutex>

#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/empty.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/int32.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include <ymrobot_msgs/msg/cloud_chassis_status.hpp>
#include <ymrobot_msgs/msg/update_list.hpp>
#include <ymrobot_msgs/msg/movebase.hpp>
#include <ymrobot_msgs/msg/led_show.hpp>
#include <ymrobot_msgs/msg/cloud_chassis_mark_point.hpp>
#include <ymrobot_msgs/msg/cloud_chassis_mark_point_list.hpp>
#include <ymrobot_msgs/srv/c_loud_nav.hpp>
#include <ymrobot_msgs/action/cloud_chassis_nav.hpp>
#include <ymrobot_msgs/action/cloud_chassis_charge.hpp>
#include <ymrobot_msgs/action/cloud_chassis_nav_reposition.hpp>

#include <sql_manager.hpp>
#include <nlohmann/json.hpp>
#include <thread_safe_queue.hpp> // 线程安全队列
#include <yaml-cpp/yaml.h>

namespace ymrobot
{
    using json = nlohmann::json;
    using GoalHandleChassisNav = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::CloudChassisNav>;
    using GoalHandleChassisCharge = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::CloudChassisCharge>;
    using GoalHandleChassisNavReposition = rclcpp_action::ServerGoalHandle<ymrobot_msgs::action::CloudChassisNavReposition>;

    struct RobotStatusInfo
    {
        std::string move_target;    // 移动指令指定的目标点位名称
        std::string move_status;    // v0.7.12新增，移动任务的具体状态
        std::string running_status; // v0.7.12新增，移动任务的具体状态
        int move_retry_times;       // v0.7.7新增，移动失败重试次数
        bool charge_state;          // v0.7.7新增，充电状态 true->充电中状态。false->未充电状态。
        bool soft_estop_state;      // v0.7.7新增，软急停状态 true->急停中，false->非急停中
        bool hard_estop_state;      // v0.7.7新增，硬急停状态 true->急停中，false->非急停中
        bool estop_state;           //
        int power_percent;          // v0.7.7新增，当前电量百分比，取值范围[0,100]
        double current_pose_x;      // v0.7.7新增，当前机器人位置
        double current_pose_y;      //
        double current_pose_theta;  //
        int current_floor;          // 当前楼层
        std::string chargepile_id;
        std::string error_code; // 错误码
    };

    enum class CloudChassisRunStatus
    {
        DISCONNECT, // 未连接状态
        ACTIVATE,   // 激活状态
        INIT,       // 初始化状态
        IDLE,       // 闲置状态
        RUNNING,    // 运行状态
        FAULT,      // 故障状态
        CHARGING    // 充电状态
    };

    enum class VEL_CONTROL_MODE
    {
        CLOUD_CONTROL = 1, // 云平台控制
        AUTO_CONTROL = 2,  // 自动驾驶
        KEY_CONTROL = 3    // 键盘控制
    };

    class CloudWaterChassisNode : public rclcpp::Node
    {
    public:
        CloudWaterChassisNode();
        ~CloudWaterChassisNode();

    private:
        void Init();

        void InitTcpClient();
        void ReconnectTcpClient(); // 重连TCP客户端
        void InitParams();
        void CreateSubAndPub();

        void ChassisTaskProcessThread();    // 云迹底盘任务线程
        void ReceiveTcpMessageThread();     // 接收云迹反馈消息
        void CloudChassisRunStatusThread(); // 云迹底盘状态线程

        void SendTcpMessage(const std::string &msg); // 发送云迹命令
        void ParseTcpMessage(const std::string &msg);
        void AddTaskMessages(const std::string &msg); // 添加任务状态消息

        void SendRequestChassisStatus();   // 请求获取云迹底盘状态
        void SendResquestMarkerPoint();    // 请求获取点位标记
        void SendResquestSelfDiagnosis();   // 请求底盘自诊断
        void SendResquestHumanDetection(); // 请求获取人形检测信息

        void GetMarkerPoint(const char *data, size_t length); // 获取marker点位列表

        // Sub/Action/Service
        void PublishCloudChassisRobotStatus(const RobotStatusInfo &robot_status_info); // 发布云迹底盘状态
        void MoveBaseCallback(const ymrobot_msgs::msg::Movebase::SharedPtr msg);       // 移动控制订阅回调函数
        void KeyControlSubCallback(const geometry_msgs::msg::Twist::SharedPtr msg);    // 键盘控制服务回调函数
        void LedShowSubCallback(const ymrobot_msgs::msg::LedShow::SharedPtr msg);      // 灯条显示服务回调函数
        void MaxLinearSpeedSubCallback(const std_msgs::msg::Float64 msg);              // 最大线速度订阅回调函数
        void MaxAngularSpeedSubCallback(const std_msgs::msg::Float64 msg);             // 最大角速度订阅回调函数
        void ControlModeSubCallback(const std_msgs::msg::Bool::SharedPtr msg);
        void CancelMoveSubCallback(const std_msgs::msg::String::SharedPtr msg);                                                                                              // 云迹底盘控制模式订阅回调函数
        void PedestrianDetectionThresholdSubCallback(const std_msgs::msg::Float64::SharedPtr msg);                                                                           // 行人检测阈值订阅回调函数
        void SoftEmergencyStopSubCallback(const std_msgs::msg::Bool::SharedPtr msg);                                                                                         // 软急停订阅回调函数
        void NavTargetServiceCallback(const std::shared_ptr<ymrobot_msgs::srv::CLoudNav::Request> request, std::shared_ptr<ymrobot_msgs::srv::CLoudNav::Response> response); // 云迹导航服务回调函数
        void EnableNearPointExplationSubCallback(const std_msgs::msg::Bool::SharedPtr msg);                                                                                  // 开启近点解释服务回调函数
        void ExplainTheThresholdNearbyPointSubCallback(const std_msgs::msg::Float64::SharedPtr msg);                                                                         // 设置近点解释阈值服务回调函数
        //
        rclcpp_action::GoalResponse ChassisNavHandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::CloudChassisNav::Goal> goal); // 云迹导航Action
        void ChassisNavHandleAccepted(const std::shared_ptr<GoalHandleChassisNav> goal_handle);                                                                         // 云迹导航Action
        rclcpp_action::CancelResponse ChassisNavHandleCancel(const std::shared_ptr<GoalHandleChassisNav> goal_handle);                                                  // 云迹导航Action
        void ChassisNavExecute(const std::shared_ptr<GoalHandleChassisNav> goal_handle);                                                                                // 云迹导航Action
        //
        rclcpp_action::GoalResponse ChassisChargeHandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::CloudChassisCharge::Goal> goal); // 云迹充电Action
        void ChassisChargeHandleAccepted(const std::shared_ptr<GoalHandleChassisCharge> goal_handle);                                                                         // 云迹充电Action
        rclcpp_action::CancelResponse ChassisChargeHandleCancel(const std::shared_ptr<GoalHandleChassisCharge> goal_handle);                                                  // 云迹充电Action
        void ChassisChargeExecute(const std::shared_ptr<GoalHandleChassisCharge> goal_handle);
        //
        rclcpp_action::GoalResponse ChassisNavRepositionHandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::CloudChassisNavReposition::Goal> goal); // 云迹重定位Action
        void ChassisNavRepositionHandleAccepted(const std::shared_ptr<GoalHandleChassisNavReposition> goal_handle);                                                                         // 云迹重定位Action
        rclcpp_action::CancelResponse ChassisNavRepositionHandleCancel(const std::shared_ptr<GoalHandleChassisNavReposition> goal_handle);                                                  // 云迹重定位Action
        void ChassisNavRepositionExecute(const std::shared_ptr<GoalHandleChassisNavReposition> goal_handle);                                                                                // 云迹重定位Action

        void InvokeNav(const double &x, const double &y, const double &yaw);
        void InvokeNavName(const std::string &msg, const std::string &uuid);
        void InvokeMoveControl(const double &vel, const double &angle);
        void InvokeKeyControl(const double &vel, const double &angle);
        void InvokeLedShow(const double &r, const double &g, const double &b);
        void InvokeSetLinearSpeed(const double &max_speed_linear);
        void InvokeSetAngularSpeed(const double &max_speed_angular);
        void InvokeChargeAction(const std::string &action);        // 执行充电动作
        void InvokeCancelMove();                                   // 执行取消移动
        void InvokeReposition(const std::string &reposition_name); // 执行重定位动作
        void InvokeSoftEmergencyStop(const bool &stop_flag);       // 执行软急停动作
        void RequestMapListInfo();
        void AlarmInfo(const std::string &msg);

        void ParseRobotMessage(const json &msg);                // 解析机器人消息
        void ParseRobotStatusMessages(const json &msg);         // 解析机器人状态消息
        void ParsePedestrianDetectionMessages(const json &msg); // 解析机器人行人检测消息

        long GenerateUniqueId();             // 生成唯一ID
        std::string GetCurrentFloorCharge(); // 获取当前楼层充电信息
        void PubDetectedPerson();            // 发布检测到的行人信息

        template <typename T>
        void SetYaml(const std::string &yaml_file_path, const std::string &parameter_name, const T &parameter_value);

    private:
        std::thread receive_tcp_service_thread_, chassis_task_process_thread_, cloud_chassis_run_status_thread_; // tcp服务线程,云迹底盘任务线程,云迹底盘运行状态线程
        SqlManagernNode sqlManager;

        std::unique_ptr<zmq::context_t> tcp_context_; // ZeroMQ 上下文
        std::unique_ptr<zmq::socket_t> tcp_socket_;   // ZeroMQ 套接字
        int tcp_socket_fd_;                           // TCP socket 文件描述符

        // 锁
        std::shared_mutex robot_status_info_mutex_; // l1 机器人状态信息robot_status_info_
        std::mutex tcp_socket_mutex_;               // l2 保护tcp_socket_的互斥锁

        // config
        std::string server_address_;                                   // tcp服务端地址
        int server_port_;                                              // tcp服务端端口
        std::string mark_points_csv_adress_;                           // 标记点位csv文件地址
        std::string pub_chassis_status_info_topic_;                    // 发布云迹底盘状态话题
        std::string cloud_chassis_point_upadte_pub_name_;              // 云迹底盘标记点位更新话题
        std::string cloud_water_mark_point_topic_name_;                // 云迹底盘标记点位话题
        std::string play_fixed_audio_pub_name_;                        // 播放固定音频话题
        std::string alarm_info_pub_name_;                              // 告警信息发布话题
        std::string publish_detected_person_pub_name_;                 // 发布检测到的行人信息话题
        std::string cloud_water_move_base_topic_;                      // 云迹手动控制速度话题
        std::string key_vel_move_base_topic_;                          // 键盘移动控制速度订阅者
        std::string recharge_result_pub_name_;                          // 回冲结果发布者
        std::string max_linear_speed_sub_name_;                        // 最大线速度订阅者
        std::string max_angle_speed_sub_name_;                         // 最大角速度订阅者
        std::string led_show_topic_name_;                              // led灯带show订阅者
        std::string cancel_current_move_sub_name_;                     // 取消当前移动订阅者
        std::string enable_pedestrian_detection_sub_name_;             // 启动人形检测
        std::string soft_emergency_stop_sub_name_;                     // 软急停订阅者
        std::string cloud_water_nav_target_srv_name_;                  // 云迹导航服务名称
        std::string cloud_chassis_nav_action_name_;                    // 云迹导航action名称
        std::string cloud_chassis_charge_action_name_;                 // 云迹充电action名称
        std::string cloud_chassis_reposition_action_name_;             // 云迹重定位action名称
        int max_continuous_retries_;                                   // 最大连续重试次数
        double occupied_tolerance_;                                    // 让步停靠距离参数，单位米。 -- 就近点讲解阈值
        double traffic_peak_time_threshold_;                           // 交通高峰时间阈值，单位秒。 -- 8s检测
        double pedestrian_detection_distance_threshold_;               // 人形检测距离阈值，单位米。
        bool is_open_near_explation_;                                  // 是否开启就近点讲解功能
        std::string yaml_file_;

        rclcpp::Publisher<ymrobot_msgs::msg::CloudChassisStatus>::SharedPtr cloud_chassis_status_pub_{};                      // 云迹底盘状态发布者
        rclcpp::Publisher<ymrobot_msgs::msg::CloudChassisMarkPointList>::SharedPtr cloud_chassis_mark_point_pub_{};           // 云迹底盘标记点位发布者
        rclcpp::Publisher<ymrobot_msgs::msg::UpdateList>::SharedPtr cloud_chassis_mark_point_upate_pub_{};                    // 云迹底盘标记点位更新发布者
        rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr play_fixed_audio_pub_{};                                           // 播放固定音频发布者
        rclcpp::Publisher<std_msgs::msg::String>::SharedPtr alarm_info_pub_{};                                                // 报警信息发布者
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr publish_detected_person_pub_{};                                     // 发布检测到的行人信息发布者
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr recharge_result_pub_{};                                             // 回冲结果发布者
        rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr key_vel_control_sub_{};                                    // 键盘控制订阅者
        rclcpp::Subscription<ymrobot_msgs::msg::LedShow>::SharedPtr led_show_sub_{};                                          // 灯带业务显示颜色订阅者
        rclcpp::Subscription<ymrobot_msgs::msg::Movebase>::SharedPtr move_base_sub_{};                                        // 移动控制订阅者
        rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr max_linear_speed_sub_{};                                      // 最大线速度订阅者
        rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr max_angle_speed_sub_{};                                       // 最大角速度订阅者
        rclcpp::Subscription<std_msgs::msg::String>::SharedPtr cancel_current_move_sub_{};                                    // 取消当前移动任务订阅者
        rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr enable_pedestrian_detection_sub_{};                              // 启动人形检测订阅者
        rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr is_open_near_point_explanation_sub_{};                           // 是否开启就近点讲解功能函数
        rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr explain_the_threshold_nearby_sub_{};                          // 就近点讲解距离阈值订阅者
        rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr soft_emergency_stop_sub_{};                                      // 软急停订阅者
        rclcpp::Service<ymrobot_msgs::srv::CLoudNav>::SharedPtr nav_target_srv_{};                                            // 导航到目标点服务
        rclcpp_action::Server<ymrobot_msgs::action::CloudChassisNav>::SharedPtr cloud_chassis_nav_action_{};                  // 导航到目标点action
        rclcpp_action::Server<ymrobot_msgs::action::CloudChassisCharge>::SharedPtr cloud_chassis_charge_action_{};            // 充电action
        rclcpp_action::Server<ymrobot_msgs::action::CloudChassisNavReposition>::SharedPtr cloud_chassis_reposition_action_{}; // 重定位action

        ThreadSafeQueue<std::string> cloud_chassis_task_queue_; // 云迹任务队列

        std::atomic<bool> recive_nav_resulst_{false};         // 接收导航结果
        std::atomic<bool> is_request_get_robot_status_{true}; // 接收导航结果
        std::atomic<bool> is_first_connect_success_{true};    // 第一次连接成功标志

        RobotStatusInfo robot_status_info_;                                                          // 机器人状态信息
        std::atomic<CloudChassisRunStatus> cloud_chassis_status_{CloudChassisRunStatus::DISCONNECT}; // 云迹底盘状态
        std::string robot_charging_station_location_;                                                // 充电站位置
        std::string get_mark_point_buffer_;                                                          // mark点位数据缓存区
        std::vector<std::string> packets_;                                                           // 完整数据包列表
        std::vector<std::string> mark_points_data_hearder;                                           // mark点位数据表头
        VEL_CONTROL_MODE current_evl_control_mode_;

        rclcpp::Time last_play_time_; // 历史音频播放时间
    };
}