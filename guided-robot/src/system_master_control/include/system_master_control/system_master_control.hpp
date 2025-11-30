#ifndef SYSTEM_MASTER_CONTROL_HPP
#define SYSTEM_MASTER_CONTROL_HPP

#include <iostream>
#include <thread>
#include <mutex>
#include <unistd.h>
#include <stdlib.h>
#include <boost/asio.hpp>
#include <boost/beast.hpp>
#include <fstream>
#include <vector>
#include <string>
#include <queue>
#include <shared_mutex>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <algorithm>

#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/empty.hpp>
#include <std_msgs/msg/float64.hpp>
#include <std_msgs/msg/int64.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <geometry_msgs/msg/pose.hpp>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/buffer.h>
#include <std_msgs/msg/int32.hpp>

#include <ymrobot_msgs/msg/task.hpp>
#include <ymrobot_msgs/msg/led_show.hpp>
#include <ymrobot_msgs/msg/command.hpp>
#include <ymrobot_msgs/msg/nav_point.hpp>
#include <ymrobot_msgs/msg/movebase.hpp>
#include <ymrobot_msgs/msg/control_mode.hpp>
#include <ymrobot_msgs/msg/robot_device_status.hpp>
#include <ymrobot_msgs/msg/task_status.hpp>
#include <ymrobot_msgs/msg/task_status_code.hpp>
#include <ymrobot_msgs/msg/dot_points_list.hpp>
#include <ymrobot_msgs/msg/binary_data.hpp>
#include <ymrobot_msgs/msg/update_list.hpp>
#include <ymrobot_msgs/msg/cloud_chassis_status.hpp>
#include <ymrobot_msgs/msg/bt_node_task_state.hpp>
#include <ymrobot_msgs/srv/up_limb.hpp>
#include <ymrobot_msgs/srv/emoji.hpp>
#include <ymrobot_msgs/srv/audio.hpp>
#include <ymrobot_msgs/srv/move_target.hpp>
#include <ymrobot_msgs/srv/large_model_request_task.hpp>

#include <nlohmann/json.hpp>
#include <mqtt/async_client.h>                // mqtt
#include <websocketpp/config/asio_no_tls.hpp> // websocket
#include <websocketpp/server.hpp>
#include <robot_device_status.hpp>
#include <thread_safe_queue.hpp> // 线程安全队列
#include <sql_manager.hpp>
#include <arpa/inet.h> // udp
#include <sys/socket.h>
#include <unistd.h>

namespace ymrobot
{
    using json = nlohmann::json;
    using websocketpp::connection_hdl;
    using WebSocketServer = websocketpp::server<websocketpp::config::asio>;

    enum class CONTROL_MODE : uint8_t
    {
        SHOU_DONG = 0x00, // 手动
        SHOU_DONG_CLOUD,  // 手动云控
        ZI_DONG
    };

    enum class UP_CLIMB_CURRENT_CONTROL_MODE
    {
        SHOU_DONG, // 手动
        AUTO
    };

    // 机器人运行状态
    enum class ROBOT_STATUS
    {
        IDLE = 0,      // 空闲中   0
        RUNNING = 1,   // 运行中   1
        CHARGING = 2,  // 充电中   2
        UPGRADING = 3, // 升级中   3
        PAUSED = 4,    // 暂停中   4
        ERROR = 5      // 故障中   5
    };

    // 当前任务级别
    enum class CURRENT_TASK_LEVEL
    {
        MAX,         // 最高
        MIN,         // 最低
        INTERMEDIATE // 中等
    };

    // 大模型任务运行状态
    enum class LARGE_MODEL_TASK_STATUS
    {
        RUNNING,   // 运行中
        SUCCESSED, // 成功
        FAIL,      // 失败
    };

    // 控制模式
    std::map<std::string, CONTROL_MODE> control_mode_name_map =
        {{"manual_platform", CONTROL_MODE::SHOU_DONG_CLOUD},
         {"autonomous", CONTROL_MODE::ZI_DONG},
         {"manual_remote", CONTROL_MODE::SHOU_DONG}};

    // 任务执行状态
    std::map<uint8_t, std::string> task_status_name_map =
        {{0x00, "running"},
         {0x01, "completed"},
         {0x02, "successed"},
         {0x03, "fail"},
         {0x04, "cancel"},
         {0x05, "wait"},
         {0x06, "refuse"},
         {0x07, "none"}};

    // 任务类型转义
    std::map<std::string, uint8_t> task_type_name_map =
        {{"registration", ymrobot_msgs::msg::Task::REG},
         {"task_mgmt", ymrobot_msgs::msg::Task::TASK_GUIDANCE},
         {"bt_task", ymrobot_msgs::msg::Task::BT_TASK},
         {"chassis_task", ymrobot_msgs::msg::Task::CHSSIS},
         {"cloud_chassis_task", ymrobot_msgs::msg::Task::CLOUD_CHASSIS},
         {"limb_act", ymrobot_msgs::msg::Task::UP_LIMB},
         {"motion_api", ymrobot_msgs::msg::Task::MOVE},
         {"video_svc", ymrobot_msgs::msg::Task::VIDEO_IMAGE},
         {"voice_cmd", ymrobot_msgs::msg::Task::VOICE},
         {"humanoid_move", ymrobot_msgs::msg::Task::HUMANOID},
         {"emoji_task", ymrobot_msgs::msg::Task::EMOJI_TASK},
         {"system_management", ymrobot_msgs::msg::Task::SYSTEM_MANAGEMENT}};

    // 动作转义
    std::map<std::string, uint8_t> action_type_name_map =
        {
            {"register", ymrobot_msgs::msg::Command::REGISTER},
            {"log_off", ymrobot_msgs::msg::Command::LOG_OFF},
            {"pause", ymrobot_msgs::msg::Command::PAUSE},
            {"cancel", ymrobot_msgs::msg::Command::CANCLE},
            {"wait", ymrobot_msgs::msg::Command::WAIT},
            {"finish_wait", ymrobot_msgs::msg::Command::FINISH_WAIT},
            {"charge", ymrobot_msgs::msg::Command::CHARGE},
            {"finsh_charge", ymrobot_msgs::msg::Command::FINISH_CHARGE},
            {"build_map", ymrobot_msgs::msg::Command::BUILD_MAP},
            {"upload_map", ymrobot_msgs::msg::Command::UPLOAD_MAP},
            {"save_map", ymrobot_msgs::msg::Command::SAVE_MAP},
            {"relocalize", ymrobot_msgs::msg::Command::RELOCALIZE},
            {"navigation", ymrobot_msgs::msg::Command::NAVIGATION},
            {"mulit_points_navigation", ymrobot_msgs::msg::Command::MULIT_POINTS_NAVIGATION},
            {"mulit_floor_navigation", ymrobot_msgs::msg::Command::MULIT_FLOOR_NAVIGATION},
            {"cloud_navigation", ymrobot_msgs::msg::Command::CLOUD_NAVIGATION},
            {"cloud_mulit_points_navigation", ymrobot_msgs::msg::Command::CLOUD_MULIT_POINTS_NAVIGATION},
            {"cloud_navigation_name", ymrobot_msgs::msg::Command::CLOUD_NAVIGATION_NAME},
            {"cloud_mulit_points_navigation_name", ymrobot_msgs::msg::Command::CLOUD_MULIT_POINTS_NAVIGATION_NAME},
            {"manual_control_move", ymrobot_msgs::msg::Command::MANUAL_CONTROL_MOVE},
            {"exe_behavior_tree", ymrobot_msgs::msg::Command::EXE_BEHAVIOR_TREE},
            {"place_cartesian", ymrobot_msgs::msg::Command::PLACE_CARTESIAN},
            {"place_joint", ymrobot_msgs::msg::Command::PLACE_JOINT},
            {"place_fixed", ymrobot_msgs::msg::Command::PLACE_FIXED},
            {"place_control_mode", ymrobot_msgs::msg::Command::PLACE_CONTROL_MODE},
            {"grasp", ymrobot_msgs::msg::Command::GRASP},
            {"camera", ymrobot_msgs::msg::Command::CAMERA},
            {"play_fix_audio", ymrobot_msgs::msg::Command::PLAY_FIX_AUDIO},
            {"speech_to_txt", ymrobot_msgs::msg::Command::SPEECH_2_TXT},
            {"txt_to_audio", ymrobot_msgs::msg::Command::TXT_2_AUDIO},
            {"expression_fixed", ymrobot_msgs::msg::Command::EXPRESSION_FIXED},
            {"wake_up", ymrobot_msgs::msg::Command::WAKE_UP},
            {"resume", ymrobot_msgs::msg::Command::POWER_OFF},
            {"setting_parameters", ymrobot_msgs::msg::Command::SETTING_PARAMETERS},
            {"synthetic_audio", ymrobot_msgs::msg::Command::SYNTHETIC_AUDIO},
            {"upload_voice_conversation_logs", ymrobot_msgs::msg::Command::UPLOAD_VOICE_CONVERSATION_LOGS},
            {"photograph", ymrobot_msgs::msg::Command::PHOTOGRAPH},
            {"play_online_audio", ymrobot_msgs::msg::Command::PLAY_ONLINE_AUDIO},
            {"", ymrobot_msgs::msg::Command::NONE}};

    std::map<int, std::string> poetry_recitation_name_map =
        {{7, "蜀道难音频"},
         {8, "将进酒音频"},
         {9, "山中问答音频"},
         {10, "寄刘待御馆"}};

    class SystemMasterControl : public rclcpp::Node, public mqtt::callback
    {
    public:
        SystemMasterControl();
        ~SystemMasterControl();

    private:
        void Init();

        void InitParams();
        void CreateSubAndPub();
        void InitCommunication();                                   // 初始化通信
        std::vector<std::string> GetMqttTopics();                   // 获取MQTT订阅主题
        void InitMqttClinet(const std::vector<std::string> topics); // 初始化MQTT
        void MqttMsgConnect();
        void InitWebSocketServer(); // 初始化webscolet

        // 后面可能使用线程池或者异步的方法
        void RobotStatusThread();       // 机器人状态线程
        void MsgHandlerThread();        // 消息处理线程
        void WebSocketServerThread();   // WebSocket 服务器线程
        void FeedbackMessagesProcess(); // 反馈消息处理

        void message_arrived(mqtt::const_message_ptr msg) override; // mqtt
        void connected(const std::string &cause) override;
        void connection_lost(const std::string &cause) override;
        void MqttMsgHandle(const mqtt::const_message_ptr &msg);
        void WebsocketOnOpen(connection_hdl hdl);                                      // WebSocket 连接建立时的回调函数
        void WebsocketOnClose(connection_hdl hdl);                                     // WebSocket 连接关闭时的回调函数
        void WebsocketOnMessage(connection_hdl hdl, WebSocketServer::message_ptr msg); // WebSocket 收到消息时的回调函数

        void ControlModeSelect(std::string mode);                                         // 控制模式选择
        void ControlModePub(const ymrobot_msgs::msg::ControlMode &control_mode_msg);      // 控制模式发布
        bool IsMatchedRobot(const std::string &robot_id, const std::string &platform_id); // 匹配机器人

        void ParseTaskYunji(const json &msg);           // 任务解析 -- 采用行为树方案 --- 云迹底盘
        void InvokeRobotRegTask(const json &msg);       // 机器人注册
        void InvokeMoveControlTask(const json &msg);    // 移动控制
        void InvokeChassisControlTask(const json &msg); // 底盘控制

        void GetDeviceStatus();                                                                              // 获取设备状态
        void GetCurrentRobotPose(double &x, double &y, double &z, double &roll, double &pitch, double &yaw); // 获取移动机器人当前位置和姿态
        void GetCurrentRobotPointName();

        json CreateSqlData(json audio_list, json expression_list, json up_action_list, json nav_point_list);
        json GetAudioData();                                             // 获取音频数据
        json GetExpressionData(const std::string &expression_file_path); // 获取表情数据
        json GetUpActionData(const std::string &up_action_file_path);    // 获取上臂动作数据
        json GetPoseData(const std::string &pose_file_path);             // 获取点位数据库数据

        void SendMqttRequsetMessage(const std::string &task_type, const std::string &action_code, const std::vector<std::string> &params);
        void AddRobotStatusMessages(const json &msg); // 添加机器人状态消息
        void AddTaskStatusMessages(const json &msg);  // 添加任务状态消息
        void SendMqttInitMessage(const json &msg);    // 发送MQTT消息
        void SendMqttDeviceMessage(const json &msg);  // 发送MQTT消息
        void SendMqttTaskMessage(const json &msg);    // 发送MQTT消息
        void SendMqttAlarmMessage(const json &msg);   // 发送MQTT消息 -- 报警
        void SendWebSocketMessage(const json &msg);   // 发送WebSocket消息

        ymrobot_msgs::msg::Task ExecuteCommands(const json &msg);
        void TaskStatusSubCallback(const ymrobot_msgs::msg::TaskStatus::SharedPtr msg);                                                                                                                       // 任务状态订阅回调函数
        void BtTaskNodeStatusSubCallback(const ymrobot_msgs::msg::BTNodeTaskState::SharedPtr msg);                                                                                                            // BT任务节点状态订阅回调函数
        void DataUpdateListSubCallback(const ymrobot_msgs::msg::UpdateList::SharedPtr msg);                                                                                                                   // 数据库更新阅回调函数
        void CloudChassisNavCallBack(const std_msgs::msg::Empty::SharedPtr msg);                                                                                                                              // 云迹底盘控制任务服务 回调函数
        void PowerThresholdParameterUpdateSubCallback(const std_msgs::msg::Float64::SharedPtr msg);                                                                                                           // 充电阈值参数订阅回调函数
        void CloudChassisStatusInfoSubCallback(const ymrobot_msgs::msg::CloudChassisStatus::SharedPtr msg);                                                                                                   // 云迹底盘状态订阅回调函数
        void UpLimbControlCallBack(rclcpp::Client<ymrobot_msgs::srv::UpLimb>::SharedFuture result_future);                                                                                                    // 上臂控制任务服务 回调函数
        void EmojiControlCallBack(rclcpp::Client<ymrobot_msgs::srv::EMOJI>::SharedFuture result_future);                                                                                                      // 表情控制任务服务 回调函数
        void AudioControlCallBack(rclcpp::Client<ymrobot_msgs::srv::Audio>::SharedFuture result_future);                                                                                                      // 音频控制任务服务 回调函数
        void MoveTargetServerCallback(const std::shared_ptr<ymrobot_msgs::srv::MoveTarget::Request> request, std::shared_ptr<ymrobot_msgs::srv::MoveTarget::Response> response);                              // 移动控制任务服务 回调函数
        void LargeModelRequestSrviceCallback(const std::shared_ptr<ymrobot_msgs::srv::LargeModelRequestTask::Request> request, std::shared_ptr<ymrobot_msgs::srv::LargeModelRequestTask::Response> response); // 大模型请求服务 回调函数
        void AlarmInfoSubCallback(const std_msgs::msg::String::SharedPtr msg);                                                                                                                                // 报警信息订阅回调函数

        void RechargeThresholdJudgment(const double current_power); // 充电阈值判断
        void CurrentRobotStatusUpdate();                            // 当前机器人状态更新
        void StopRobot();                                           // 停止机器人移动
        void CancelCurrentTask();                                   // 取消当前任务
        void MoveWaitPose();                                        // 移动到等待点位  -- 当电量到达阈值时候

    private:
        rclcpp::Logger logger_{rclcpp::get_logger("SystemMasterControl")};
        std::shared_ptr<RobotDeviceStatus> device_status_manager_{};
        SqlManagernNode sql_manager_;
        std::string current_robot_id_ = "";    // 机器人ID
        std::string current_platform_id_ = ""; // 当前平台ID

        std::thread *mqtt_clinet_thread_, *robot_status_thread_, *msg_handler_thread_, *msg_send_thread_, websocket_thread_, *http_clinet_thread_;

        WebSocketServer ws_server_; // websocket服务

        std::shared_ptr<mqtt::async_client> mqtt_client_; // mqtt客户端
        mqtt::connect_options connOpts;
        std::vector<std::string> mqtt_topics_;

        std::set<connection_hdl, std::owner_less<connection_hdl>> connections_; // 活跃的 WebSocket 连接集合
        std::condition_variable command_condition;                              // 减少了线程在空循环中等待消息时的 CPU 使用率。优化队列的等待与唤醒逻辑
        std::mutex mqtt_publish_mutex_;                                         // l1 mqtt链接
        mutable std::mutex command_queue_mutex_;                                // l2  消息队列处理
        std::mutex chassis_task_status_mutex_;                                  // l3  底盘消息队列处理
        std::mutex ws_connections_mutex_;                                       // l4 websocket链接
        std::mutex move_base_mutex_;                                            // l5 move_base
        std::shared_mutex cloud_chassis_state_mutex_;                           // l6 云迹底盘状态锁
        std::future<void> move_base_task_future_;                               // 异步 用于处理机器人移动任务
        std::atomic<bool> is_robot_status_thread_running_{true};                // 机器人状态线程原子锁；
        std::atomic<bool> is_robot_mag_handler_thread_running_{true};           // 消息处理线程原子锁
        std::atomic<bool> is_connect_success_{false};                           // 消息处理线程原子锁
        std::atomic<bool> is_mqtt_connect_success_{false};                      // 消息处理线程原子锁
        std::atomic<bool> is_webscoket_connect_success_{false};                 // 消息处理线程原子锁
        std::atomic<bool> is_first_connect_success_{true};                      // 是否是初始化
        std::atomic<bool> is_robot_reged_{true};                                // 是否是已注册
        std::atomic<bool> is_move_feedback_{false};                             // 是否是有移动反馈
        std::atomic<bool> is_move_success_{false};                              // 是否移动成功
        std::atomic<bool> is_cloud_chassis_update_{false};                      // 云迹底盘点位更新通知

        // action/ topic /service
        rclcpp::Publisher<ymrobot_msgs::msg::ControlMode>::SharedPtr control_mode_pub_{};                        // 控制模式发布topic
        rclcpp::Publisher<ymrobot_msgs::msg::Movebase>::SharedPtr move_base_cloud_pub_{};                        // 底盘cloud移动控制
        rclcpp::Publisher<ymrobot_msgs::msg::Task>::SharedPtr chassis_task_pub_{};                               // 底盘任务发布topic
        rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr up_climb_control_mode_pub_{};                          // 控制模式发布topic
        rclcpp::Publisher<ymrobot_msgs::msg::LedShow>::SharedPtr led_show_pub_{};                                // led灯发布topic
        rclcpp::Publisher<std_msgs::msg::Int64>::SharedPtr current_robot_status_pub_{};                          // 任务状态发布topic
        rclcpp::Subscription<ymrobot_msgs::msg::TaskStatus>::SharedPtr chassis_task_status_sub_{};               // 底盘任务状态订阅
        rclcpp::Subscription<ymrobot_msgs::msg::BTNodeTaskState>::SharedPtr node_task_status_sub_{};             // 底盘任务状态订阅
        rclcpp::Subscription<ymrobot_msgs::msg::UpdateList>::SharedPtr data_update_list_sub_{};                  // 数据库记录更新订阅
        rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr power_threshold_parameter_update_sub_{};         // 电量阈值更新订阅
        rclcpp::Subscription<ymrobot_msgs::msg::CloudChassisStatus>::SharedPtr cloud_chassis_status_info_sub_{}; // 云迹底盘状态订阅
        rclcpp::Subscription<std_msgs::msg::String>::SharedPtr alarm_info_sub_{};                                // 报警信息订阅
        rclcpp::Client<ymrobot_msgs::srv::UpLimb>::SharedPtr up_limb_client_{};                                  // 上臂服务
        rclcpp::Client<ymrobot_msgs::srv::EMOJI>::SharedPtr emoji_control_client_{};                             // 表情控制客户端
        rclcpp::Client<ymrobot_msgs::srv::Audio>::SharedPtr audio_control_client_{};                             // 音频控制客户端
        rclcpp::Service<ymrobot_msgs::srv::MoveTarget>::SharedPtr move_target_service_{};                        // 移动目标服务  -- 暂时这版本需要 ， 后期我这边控制
        rclcpp::Service<ymrobot_msgs::srv::LargeModelRequestTask>::SharedPtr large_model_request_service_{};     // 大模型交互服务--服务端
        rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr play_fixed_audio_pub_{};                                           // 播放固定音频发布者

        std::queue<json> command_queue_;           // 任务消息队列
        ThreadSafeQueue<json> robot_status_queue_; // 机器人状态消息队列
        ThreadSafeQueue<json> task_status_queue_;  // 任务事件反馈消息队列

        /*config param*/
        std::string robot_id_;                    // 机器人id
        bool is_open_mqtt_;                       // 通讯模式 true:启用mqtt false:启用websocket
        bool is_open_reg_;                        // 是否开启注册功能
        std::string mqtt_server_ip_;              // mqtt服务器ip
        std::string client_id_;                   // mqtt客户端id
        int mqtt_qs_;                             // mqtt消息质量
        std::string mqtt_topic_pre_fix_;          // mqtt主题前缀
        std::string mqtt_topic_init_pub_fix_;     // mqtt发布主题 -- 初始化上传数据
        std::string mqtt_topic_device_pub_fix_;   // mqtt发布主题 -- 实时上传的设备信息
        std::string mqtt_topic_task_pub_fix_;     // mqtt发布主题 -- 任务响应以及反馈消息
        std::string mqtt_topic_alarm_sms_fix_;    // mqtt发布主题 -- 机器人报警短信上传
        std::string mqtt_topic_request_task_fix_; // mqtt发布主题 -- 机器人请求任务
        std::string user_name_;                   // mqtt用户名
        std::string pass_word_;                   // mqtt密码
        std::string ca_cert_;                     // ca证书
        std::string websocket_ip_;                // ws的ip地址
        int websocket_port_;                      // ws的端口号
        // publish topic
        std::string control_mode_pub_name_;         // 控制模式topic
        std::string chassis_task_pub_name_;         // 底盘任务topic
        std::string up_control_mode_pub_name_;      // 上肢控制模式topic
        std::string led_show_pub_name_;             // led发布者
        std::string current_robot_status_pub_name_; // 当前机器人状态发布者
        // subscribe topic
        std::string chassis_task_status_sub_name_;              // 底盘任务状态topic
        std::string data_update_list_sub_name_;                 // 数据库更新topic
        std::string power_threshold_parameter_update_sub_name_; // 回充电量阈值更新订阅名
        std::string cloud_chassis_status_sub_name_;             // 云迹底盘状态订阅主题
        std::string alarm_info_sub_name_;                       // 报警信息订阅
        std::string node_task_status_sub_name_;
        // clinet
        std::string up_limb_control_clinet_name_; // 上臂控制服务名
        std::string emoji_control_clinet_name_;   // 表情控制服务名
        std::string audio_control_clinet_name_;   // 音频控制服务名
        std::string move_target_srv_;             // 移动目标服务
        // srv
        std::string large_model_request_srv_name_; // 大模型交互服务名
        // other
        std::string mp3_file_path_;                                // mp3文件路径
        std::string expression_file_path_;                         // 表情文件路径
        std::string up_action_file_path_;                          // 上肢动作文件路径
        std::string pose_file_path_;                               // 点位文件路径
        int control_move_heart_time_;                              // 控制移动心跳时间
        std::atomic<double> low_battery_recharge_threshold_{20.0}; // 低电量充电阈值
        std::atomic<double> exc_task_battery_threshold_{30.0};     // 在充电时候，可执行任务的充电的电量阈值
        std::atomic<double> low_battery_alarm_threshold_{5.0};     // 低电量报警阈值

        std::atomic<uint32_t> heart_beat_{0}; // 心跳
        std::shared_ptr<tf2_ros::Buffer> tf_buffer_;
        std::shared_ptr<tf2_ros::TransformListener> tf_listener_;

        int wait_service_time_;                                       // 等待服务超时时间
        double last_move_ts_;                                         // 上次移动的时间戳
        UP_CLIMB_CURRENT_CONTROL_MODE current_up_climb_control_mode_; // 当前上肢的控制模式  -- 自动或者手动模式
        ymrobot_msgs::msg::CloudChassisStatus current_chassis_info_;  // 当前底盘信息反馈  而不是底盘状态
        ymrobot_msgs::msg::RobotDeviceStatus current_device_status_;  // 当前设备状态
        CONTROL_MODE current_system_control_mode_;                    // 当前控制模式
        uint8_t current_task_status_;                                 // 当前任务状态

        std::atomic<ROBOT_STATUS> current_robot_status_, last_robot_status_;                                  // 当前机器人状态
        std::atomic<CURRENT_TASK_LEVEL> current_task_level_;                                                  // 当前任务等级
        int current_larget_model_task_id_;                                                                    // 当前大模型任务ID
        std::atomic<LARGE_MODEL_TASK_STATUS> is_large_mode_task_successed_{LARGE_MODEL_TASK_STATUS::RUNNING}; // 大模型任务运行状态
        std::vector<std::string> point_name_list_;                                                            // 点位名称列表


        std::atomic<bool> is_charge_{false}; // 心跳
    };
}

// 计时器函数，测量函数执行时间
template <typename Func>
auto FunctionTimer(Func func)
{
    // 获取当前时间点
    auto start = std::chrono::high_resolution_clock::now();
    // 执行函数
    func();
    // 获取当前时间点
    auto end = std::chrono::high_resolution_clock::now();
    // 计算执行时间
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    // 返回执行时间（毫秒）
    return duration.count();
}

#endif // SYSTEM_MASTER_CONTROL_HPP