#include "system_master_control.hpp"

#define MQTT_TOPIC_PROPERTIES_READ "/properties/read"
#define MQTT_TOPIC_PROPERTIES_WRITE "/properties/write"
#define MQTT_TOPIC_FUNCTION_INVOKE "/function/invoke"
#define MQTT_TOPIC_MSG "/msg/+"
#define MQTT_TIME_OUT_TS 2.0                 // mqtt连接超时时间
#define STATUS_THREAD_HZ 1                   // 机器人状态线程频率
#define LARGE_MODE_TASK_FEEDBACK_THREAD_HZ 1 // 大模型任务反馈线程频率

namespace ymrobot
{
    SystemMasterControl::SystemMasterControl() : rclcpp::Node("system_master_control")
    {
        Init();
    }

    SystemMasterControl::~SystemMasterControl()
    {
        delete msg_handler_thread_;
        delete msg_send_thread_;
        delete mqtt_clinet_thread_;
    }

    void SystemMasterControl::Init()
    {
        InitParams();
        CreateSubAndPub();
        InitCommunication();
        robot_status_thread_ = new std::thread(&SystemMasterControl::RobotStatusThread, this);   // 机器人状态线程
        msg_handler_thread_ = new std::thread(&SystemMasterControl::MsgHandlerThread, this);     // 消息处理线程
        msg_send_thread_ = new std::thread(&SystemMasterControl::FeedbackMessagesProcess, this); // 使用mqtt或者websocket 发送消息线程
    }

    void SystemMasterControl::InitParams()
    {
        this->declare_parameter("robot_id", "");
        this->declare_parameter("mqtt_server_ip", "");
        this->declare_parameter("client_id", "");
        this->declare_parameter("mqtt_qs", 0);
        this->declare_parameter("mqtt_topic_pre_fix", "");
        this->declare_parameter("mqtt_topic_init_pub_fix", "");
        this->declare_parameter("mqtt_topic_device_pub_fix", "");
        this->declare_parameter("mqtt_topic_task_pub_fix", "");
        this->declare_parameter("mqtt_topic_alarm_sms_fix", "");
        this->declare_parameter("mqtt_topic_request_task_fix", "");
        this->declare_parameter("user_name", "");
        this->declare_parameter("pass_word", "");
        this->declare_parameter("ca_cert", "");
        this->declare_parameter("websocket_html_ip", "0.0.0.0");
        this->declare_parameter("websocket_html_port", 8080);
        // publish topic
        this->declare_parameter("chassis_task_pub_name", "");
        this->declare_parameter("control_mode_pub_name", "");
        this->declare_parameter("up_control_mode_pub_name", "");
        this->declare_parameter("led_show_pub_name", "");
        this->declare_parameter("current_robot_status_pub_name", "");
        // subscribe topic
        this->declare_parameter("chassis_task_status_sub_name", "");
        this->declare_parameter("data_update_list_sub_name", "");
        this->declare_parameter("power_threshold_parameter_update_sub_name", "");
        this->declare_parameter("cloud_chassis_status_sub_name", "");
        this->declare_parameter("node_task_status_sub_name", "");
        // clinet
        this->declare_parameter("up_limb_control_clinet_name", "");
        this->declare_parameter("emoji_control_clinet_name", "");
        this->declare_parameter("audio_control_clinet_name", "");
        // srv
        this->declare_parameter("large_model_request_srv_name", "");
        // other
        this->declare_parameter("mp3_file_path", "");
        this->declare_parameter("expression_file_path", "");
        this->declare_parameter("up_action_file_path", "");
        this->declare_parameter("pose_file_path", "");
        this->declare_parameter("service_wait_over_time", 5.0);
        this->declare_parameter("http_time_out", 5000);
        this->declare_parameter("control_move_heart_time", 2);
        this->declare_parameter("low_battery_recharge_threshold", 20);
        this->declare_parameter("execute_task_battery_threshold", 80.0);
        this->declare_parameter("is_enable_automatic_recharge", false);

        mqtt_server_ip_ = this->get_parameter("mqtt_server_ip").as_string();
        client_id_ = this->get_parameter("client_id").as_string();
        mqtt_qs_ = this->get_parameter("mqtt_qs").as_int();
        mqtt_topic_pre_fix_ = this->get_parameter("mqtt_topic_pre_fix").as_string();
        mqtt_topic_init_pub_fix_ = this->get_parameter("mqtt_topic_init_pub_fix").as_string();
        mqtt_topic_device_pub_fix_ = this->get_parameter("mqtt_topic_device_pub_fix").as_string();
        mqtt_topic_task_pub_fix_ = this->get_parameter("mqtt_topic_task_pub_fix").as_string();
        mqtt_topic_alarm_sms_fix_ = this->get_parameter("mqtt_topic_alarm_sms_fix").as_string();
        mqtt_topic_request_task_fix_ = this->get_parameter("mqtt_topic_request_task_fix").as_string();
        user_name_ = this->get_parameter("user_name").as_string();
        pass_word_ = this->get_parameter("pass_word").as_string();
        ca_cert_ = this->get_parameter("ca_cert").as_string();
        // publish topic
        chassis_task_pub_name_ = this->get_parameter("chassis_task_pub_name").as_string();
        control_mode_pub_name_ = this->get_parameter("control_mode_pub_name").as_string();
        up_control_mode_pub_name_ = this->get_parameter("up_control_mode_pub_name").as_string();
        led_show_pub_name_ = this->get_parameter("led_show_pub_name").as_string();
        current_robot_status_pub_name_ = this->get_parameter("current_robot_status_pub_name").as_string();
        // subscribe topic
        chassis_task_status_sub_name_ = this->get_parameter("chassis_task_status_sub_name").as_string();
        data_update_list_sub_name_ = this->get_parameter("data_update_list_sub_name").as_string();
        power_threshold_parameter_update_sub_name_ = this->get_parameter("power_threshold_parameter_update_sub_name").as_string();
        cloud_chassis_status_sub_name_ = this->get_parameter("cloud_chassis_status_sub_name").as_string();
        node_task_status_sub_name_ = this->get_parameter("node_task_status_sub_name").as_string();
        // clint
        up_limb_control_clinet_name_ = this->get_parameter("up_limb_control_clinet_name").as_string();
        emoji_control_clinet_name_ = this->get_parameter("emoji_control_clinet_name").as_string();
        audio_control_clinet_name_ = this->get_parameter("audio_control_clinet_name").as_string();
        // srv
        large_model_request_srv_name_ = this->get_parameter("large_model_request_srv_name").as_string();
        // other
        mp3_file_path_ = this->get_parameter("mp3_file_path").as_string();
        expression_file_path_ = this->get_parameter("expression_file_path").as_string();
        up_action_file_path_ = this->get_parameter("up_action_file_path").as_string();
        pose_file_path_ = this->get_parameter("pose_file_path").as_string();
        robot_id_ = this->get_parameter("robot_id").as_string();
        control_move_heart_time_ = this->get_parameter("control_move_heart_time").as_int();
        low_battery_recharge_threshold_ = (double)(this->get_parameter("low_battery_recharge_threshold").as_int());
        exc_task_battery_threshold_ = this->get_parameter("execute_task_battery_threshold").as_double();

        current_robot_id_ = robot_id_;
        RCLCPP_INFO(this->get_logger(), "当前机器人id: %s", current_robot_id_.c_str());

        current_robot_status_ = ROBOT_STATUS::IDLE;
        last_robot_status_ = ROBOT_STATUS::IDLE;
        current_task_status_ = ymrobot_msgs::msg::TaskStatusCode::NONE;

        current_chassis_info_.power_percent = 80.0;
    }

    void SystemMasterControl::CreateSubAndPub()
    {
        // control_mode_pub_ = this->create_publisher<ymrobot_msgs::msg::ControlMode>(control_mode_pub_name_, 2);
        chassis_task_pub_ = this->create_publisher<ymrobot_msgs::msg::Task>(chassis_task_pub_name_, 2);
        up_climb_control_mode_pub_ = this->create_publisher<std_msgs::msg::Bool>(up_control_mode_pub_name_, 1);
        led_show_pub_ = this->create_publisher<ymrobot_msgs::msg::LedShow>(led_show_pub_name_, 1);
        current_robot_status_pub_ = this->create_publisher<std_msgs::msg::Int64>(current_robot_status_pub_name_, 1);
        chassis_task_status_sub_ = this->create_subscription<ymrobot_msgs::msg::TaskStatus>(chassis_task_status_sub_name_, 1, std::bind(&SystemMasterControl::TaskStatusSubCallback, this, std::placeholders::_1));
        data_update_list_sub_ = this->create_subscription<ymrobot_msgs::msg::UpdateList>(data_update_list_sub_name_, 1, std::bind(&SystemMasterControl::DataUpdateListSubCallback, this, std::placeholders::_1));
        power_threshold_parameter_update_sub_ = this->create_subscription<std_msgs::msg::Float64>(power_threshold_parameter_update_sub_name_, 1, std::bind(&SystemMasterControl::PowerThresholdParameterUpdateSubCallback, this, std::placeholders::_1));
        cloud_chassis_status_info_sub_ = this->create_subscription<ymrobot_msgs::msg::CloudChassisStatus>(cloud_chassis_status_sub_name_, 2, std::bind(&SystemMasterControl::CloudChassisStatusInfoSubCallback, this, std::placeholders::_1));
        node_task_status_sub_ = this->create_subscription<ymrobot_msgs::msg::BTNodeTaskState>(node_task_status_sub_name_, 1, std::bind(&SystemMasterControl::BtTaskNodeStatusSubCallback, this, std::placeholders::_1));
        up_limb_client_ = this->create_client<ymrobot_msgs::srv::UpLimb>(up_limb_control_clinet_name_);
        audio_control_client_ = this->create_client<ymrobot_msgs::srv::Audio>(audio_control_clinet_name_);
        large_model_request_service_ = this->create_service<ymrobot_msgs::srv::LargeModelRequestTask>(large_model_request_srv_name_, std::bind(&SystemMasterControl::LargeModelRequestSrviceCallback, this, std::placeholders::_1, std::placeholders::_2));
        play_fixed_audio_pub_ = this->create_publisher<std_msgs::msg::Int32>("play_fixed_audio", 1);
    }

    std::vector<std::string> SystemMasterControl::GetMqttTopics()
    {
        std::vector<std::string> topics_vec = {mqtt_topic_pre_fix_};
        return topics_vec;
    }

    void SystemMasterControl::InitCommunication()
    {
        if (is_open_mqtt_)
        {
            RCLCPP_INFO(this->get_logger(), "采用mqtt通信方式");
            mqtt_topics_ = GetMqttTopics();
            for (auto a : mqtt_topics_)
            {
                std::cout << a << std::endl;
            }
            if (mqtt_topics_.empty())
            {
                RCLCPP_ERROR(this->get_logger(), "[init] error! topics of the mqtt is empty! return!");
                return;
            }
            mqtt_clinet_thread_ = new std::thread(&SystemMasterControl::InitMqttClinet, this, mqtt_topics_);
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "采用websocket通信方式");
            InitWebSocketServer();
            auto websocket_future_ = std::async(std::launch::async, &SystemMasterControl::WebSocketServerThread, this); // 使用异步方法启动 WebSocket 服务器线程
        }
    }

    void SystemMasterControl::InitMqttClinet(const std::vector<std::string> topics)
    {
        mqtt::string_ref user_name = user_name_;
        mqtt::binary_ref pass_word = pass_word_;

        mqtt_client_ = std::make_shared<mqtt::async_client>(mqtt_server_ip_, client_id_);
        mqtt_client_->set_callback(*this);

        connOpts = mqtt::connect_options_builder()
                       .user_name(user_name)
                       .password(pass_word)
                       .clean_session(true)
                       .automatic_reconnect(std::chrono::seconds(5), std::chrono::seconds(30))
                       .finalize();

        MqttMsgConnect();
    }

    void SystemMasterControl::MqttMsgConnect()
    {
        try
        {
            mqtt_client_->connect(connOpts)->wait();
            RCLCPP_INFO(this->get_logger(), "mqtt链接成功.");
        }
        catch (const mqtt::exception &ex)
        {
            RCLCPP_ERROR(this->get_logger(), "mqtt连接失败, %s", ex.what());
            // 写一个重连机制  自带重连机制
        }

        try
        {
            auto mqtt_qs_list = {mqtt_qs_};
            mqtt_client_->subscribe(mqtt::string_collection::create(mqtt_topics_), mqtt_qs_list);
        }
        catch (const std::exception &e)
        {
            RCLCPP_ERROR(this->get_logger(), "mqtt连接失败: %s", e.what());
        }
    }

    void SystemMasterControl::InitWebSocketServer()
    {
        ws_server_.init_asio();
        ws_server_.set_open_handler(std::bind(&SystemMasterControl::WebsocketOnOpen, this, std::placeholders::_1));
        ws_server_.set_close_handler(std::bind(&SystemMasterControl::WebsocketOnClose, this, std::placeholders::_1));
        ws_server_.set_message_handler(std::bind(&SystemMasterControl::WebsocketOnMessage, this, std::placeholders::_1, std::placeholders::_2));
    }

    void SystemMasterControl::RobotStatusThread()
    {
        rclcpp::WallRate loop_rate(STATUS_THREAD_HZ);
        unsigned int cnt = 0;
        while (is_robot_status_thread_running_.load())
        {
            if (!is_connect_success_.load())
            {
                loop_rate.sleep(); // 避免忙等待 等待5s
                continue;
            }

            if (heart_beat_ > 60000)
            {
                heart_beat_ = 0;
            }

            json status;
            status["ID"] = current_robot_id_; // 机器人ID
            status["HB"] = heart_beat_++;     // 机器人心跳信息
            status["DS"] = json::object();    // 机器人设备状态
            status["RS"] = json::object();    // 机器人运行状态
            {
                cnt++;
                unsigned int pose_time = std::floor(1.0 * STATUS_THREAD_HZ);
                if (cnt % pose_time == 0)
                {
                    {
                        std::shared_lock<std::shared_mutex> l6(cloud_chassis_state_mutex_);
                        status["PS"]["X"] = current_chassis_info_.x;
                        status["PS"]["y"] = current_chassis_info_.y;
                        status["PS"]["z"] = 0.0;
                        status["PS"]["yaw"] = current_chassis_info_.yaw;
                        status["PS"]["tgp"] = current_chassis_info_.move_target;
                    }

                    status["RS"]["ST"] = current_robot_status_.load(); // 机器人状态
                    status["RS"]["ET"] = 0;                            // 错误码

                    // std::cout << "当前机器人状态： "<< (int)current_robot_status_.load()<<std::endl;
                    CurrentRobotStatusUpdate();

                    // if ((this->get_clock()->now().seconds() - last_move_ts_ > control_move_heart_time_) && (current_system_control_mode_ == CONTROL_MODE::SHOU_DONG))
                    // {
                    //     RCLCPP_WARN(this->get_logger(), "移动机器平台控制未在规定时间内下发移动指令，现在暂停移动机器人，超过时间：%d", control_move_heart_time_);
                    //     StopRobot();
                    // }
                }
                unsigned int device_time = std::floor(5.0 * STATUS_THREAD_HZ);
                if (cnt % device_time == 0)
                {
                    status["DS"]["BAT"]["perc"] = current_chassis_info_.power_percent;

                    status["DS"]["LM"]["spd"] = 0.0;
                    status["DS"]["LM"]["temp"] = 0.0;
                    status["DS"]["RM"]["spd"] = 0.0;
                    status["DS"]["RM"]["temp"] = 0.0;

                    status["DS"]["CPU"]["temp"] = device_status_manager_->GetCpuTemperature();
                    status["DS"]["CPU"]["usage"] = device_status_manager_->GetCpuUsage(8);
                    status["DS"]["MEM"]["usage"] = device_status_manager_->GetMemoryUsage();
                    cnt = 0;

                    // if(is_enable_automatic_recharge_.load())
                    // {
                    //     RechargeThresholdJudgment(double(current_chassis_info_.power_percent)); // 充电阈值判断
                    // }

                    RechargeThresholdJudgment(double(current_chassis_info_.power_percent)); // 充电阈值判断
                }
            }
            AddRobotStatusMessages(status); // 将机器人状态信息加入队列
            loop_rate.sleep();
        }
    }

    void SystemMasterControl::MsgHandlerThread()
    {
        // 后期选择平台需要更改
        while (is_robot_mag_handler_thread_running_.load())
        {
            std::unique_lock<std::mutex> l2(command_queue_mutex_);
            command_condition.wait(l2, [this]
                                   { return !command_queue_.empty() || !is_robot_mag_handler_thread_running_.load(); }); // 等待条件变量通知
            if (!is_robot_mag_handler_thread_running_.load())
            {
                break; // 线程终止信号
            }

            if (!command_queue_.empty())
            {
                json msg = command_queue_.front(); // 获取队列中的第一条消息
                command_queue_.pop();              // 移除队列中的第一条消息
                l2.unlock();


                auto robot_id = msg["amr_id"].get<std::string>();
                auto platform_id = msg["platform_id"].get<std::string>();
                auto task_type = msg["task_type"].get<std::string>();
                std::string action_code = "";
                if (msg.contains("commands"))
                {
                    action_code = msg["commands"][0]["code"].get<std::string>();
                }
                auto control_mode = msg["control_mode"].get<std::string>();

                if (task_type == "registration")
                {
                    InvokeRobotRegTask(msg);
                    continue;
                }

                // if (!IsMatchedRobot(robot_id, platform_id))
                // {
                //     continue;
                // }

                // ControlModeSelect(control_mode);
                if (task_type != "motion_api")
                {
                    json task_respose_msg;
                    task_respose_msg["feedback_type"] = "task_response";
                    task_respose_msg["amr_id"] = robot_id;
                    task_respose_msg["platform_id"] = platform_id;
                    task_respose_msg["task_type"] = task_type;
                    task_respose_msg["action_code"] = action_code;
                    AddTaskStatusMessages(task_respose_msg);
                }

                ParseTaskYunji(msg);
            }
            else
            {
                l2.unlock();
                std::this_thread::sleep_for(std::chrono::milliseconds(10)); // 避免忙等待
                continue;
            }
        }
    }

    void SystemMasterControl::WebSocketServerThread()
    {
        websocket_thread_ = std::thread([this]()
                                        {
            std::string ip_address = websocket_ip_;
            int port = websocket_port_;
            std::cout << "ip_address: " << ip_address << ", port: " << port << std::endl;

            ws_server_.set_reuse_addr(true); // 允许端口重用
            ws_server_.listen(boost::asio::ip::tcp::endpoint(boost::asio::ip::address::from_string(ip_address), port));  // 监听端口
            ws_server_.start_accept();
            RCLCPP_INFO(logger_, "WebSocket 服务器已启动，监听地址: %s, 端口: %d", ip_address.c_str(), port);
            ws_server_.run(); });
    }

    void SystemMasterControl::message_arrived(mqtt::const_message_ptr msg)
    {
        MqttMsgHandle(msg);
    }

    void SystemMasterControl::connected(const std::string &cause)
    {
        RCLCPP_INFO(this->get_logger(), "Connected to MQTT broker: %s", cause.c_str());
        is_connect_success_.store(true);
    }

    void SystemMasterControl::connection_lost(const std::string &cause)
    {
        RCLCPP_ERROR(this->get_logger(), "mqtt失联: %s", cause.c_str());
        is_connect_success_.store(false);
    }

    void SystemMasterControl::MqttMsgHandle(const mqtt::const_message_ptr &msg)
    {
        try
        {
            // 获取当前时间戳
            auto now = std::chrono::system_clock::now();
            auto now_c = std::chrono::system_clock::to_time_t(now);
            auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;

            // 格式化时间戳
            std::tm now_tm = *std::localtime(&now_c);
            std::ostringstream oss;
            oss << std::put_time(&now_tm, "%Y-%m-%d %H:%M:%S") << "." << std::setw(3) << std::setfill('0') << now_ms.count();
            RCLCPP_INFO(logger_, "[%s] 收到消息: %s", oss.str().c_str(), msg->to_string().c_str()); // 打印时间戳和消息

            json command = json::parse(msg->to_string()); // 解析 JSON 消息
            std::lock_guard<std::mutex> l2(command_queue_mutex_);
            command_queue_.push(command);   // 将消息加入队列
            command_condition.notify_one(); // 通知等待线程
        }
        catch (const std::exception &e)
        {
            RCLCPP_ERROR(logger_, "解析 JSON 消息失败: %s", e.what());
        }
    }

    void SystemMasterControl::WebsocketOnOpen(connection_hdl hdl)
    {
        std::lock_guard<std::mutex> l1(ws_connections_mutex_);
        connections_.insert(hdl);
        is_connect_success_.store(true);
        RCLCPP_INFO(logger_, "WebSocket 连接已建立。");
    }

    void SystemMasterControl::WebsocketOnClose(connection_hdl hdl)
    {
        std::lock_guard<std::mutex> l1(ws_connections_mutex_);
        connections_.erase(hdl);
        RCLCPP_INFO(logger_, "WebSocket 连接已关闭。");
    }

    void SystemMasterControl::WebsocketOnMessage(connection_hdl hdl, WebSocketServer::message_ptr msg)
    {
        try
        {
            RCLCPP_INFO(logger_, "收到消息: %s", msg->get_payload().c_str());
            json command = json::parse(msg->get_payload()); // 解析 JSON 消息
            std::lock_guard<std::mutex> l2(command_queue_mutex_);
            command_queue_.push(command);   // 将消息加入队列
            command_condition.notify_one(); // 通知等待线程
        }
        catch (const std::exception &e)
        {
            RCLCPP_ERROR(logger_, "解析 JSON 消息失败: %s", e.what());
        }
    }

    void SystemMasterControl::ControlModeSelect(std::string mode)
    {
        CONTROL_MODE control_mode = control_mode_name_map[mode];
        ymrobot_msgs::msg::ControlMode control_mode_msg;

        switch (control_mode)
        {
        case CONTROL_MODE::SHOU_DONG:
        {
            control_mode_msg.code = ymrobot_msgs::msg::ControlMode::SHOU_DONG;
            break;
        }
        case CONTROL_MODE::SHOU_DONG_CLOUD:
        {
            control_mode_msg.code = ymrobot_msgs::msg::ControlMode::SHOU_DONG_CLOUD;
            break;
        }
        case CONTROL_MODE::ZI_DONG:
        {
            control_mode_msg.code = ymrobot_msgs::msg::ControlMode::AUTO;
            break;
        }
        default:
            break;
        }

        if (control_mode == current_system_control_mode_)
        {
            return;
        }

        ControlModePub(control_mode_msg);
        current_system_control_mode_ = control_mode;
    }

    void SystemMasterControl::ControlModePub(const ymrobot_msgs::msg::ControlMode &control_mode_msg)
    {
        RCLCPP_INFO(logger_, "发送控制模式消息");
        control_mode_pub_->publish(control_mode_msg);
    }

    void SystemMasterControl::ParseTaskYunji(const json &msg)
    {
        if (task_type_name_map.count(msg["task_type"].get<std::string>()) == 0)
        {
            RCLCPP_ERROR(logger_, "任务类型不存在");
            return;
        }
        RCLCPP_INFO(logger_, "收到发送任务消息: %s", msg.dump().c_str());
        auto task_type = task_type_name_map[msg["task_type"].get<std::string>()];
        std::cout << "任务类型： " << task_type << std::endl;
        json response_json;

        switch (task_type)
        {
        case ymrobot_msgs::msg::Task::REG:
        {
            InvokeRobotRegTask(msg);
            break;
        }
        case ymrobot_msgs::msg::Task::BT_TASK:
        case ymrobot_msgs::msg::Task::CHSSIS:
        case ymrobot_msgs::msg::Task::CLOUD_CHASSIS:
        case ymrobot_msgs::msg::Task::UP_LIMB:
        case ymrobot_msgs::msg::Task::VIDEO_IMAGE:
        case ymrobot_msgs::msg::Task::VOICE:
        case ymrobot_msgs::msg::Task::HUMANOID:
        case ymrobot_msgs::msg::Task::EMOJI_TASK:
        {
            if (current_robot_status_ == ROBOT_STATUS::CHARGING || current_robot_status_ == ROBOT_STATUS::UPGRADING || current_robot_status_ == ROBOT_STATUS::RUNNING)
            {
                json task_status_msg;
                task_status_msg["response_type"] = "task_status_response";
                task_status_msg["amr_id"] = msg["amr_id"];
                task_status_msg["task_id"] = msg["task_id"];
                task_status_msg["status"] = "fail";
                task_status_msg["text"] = msg.value("text", "");
                AddTaskStatusMessages(task_status_msg);
                break;
            }
            InvokeChassisControlTask(msg);
            break;
        }
        case ymrobot_msgs::msg::Task::TASK_GUIDANCE:
        case ymrobot_msgs::msg::Task::SYSTEM_MANAGEMENT:
        {
            InvokeChassisControlTask(msg);
            break;
        }
        case ymrobot_msgs::msg::Task::MOVE:
        {
            move_base_task_future_ = std::async(std::launch::async, &SystemMasterControl::InvokeMoveControlTask, this, msg);
            return; // 直接返回，不阻塞后续代码
        }
        default:
            break;
        }
        response_json["feedback_type"] = "task_response";
        response_json["amr_id"] = msg["amr_id"];
        response_json["task_id"] = msg["task_id"];
        response_json["task_type"] = msg["task_type"];
        response_json["action_code"] = "";
        if (msg.contains("commands"))
        {
            response_json["action_code"] = msg["commands"][0]["code"];
        }
        AddTaskStatusMessages(response_json);
    }

    bool SystemMasterControl::IsMatchedRobot(const std::string &robot_id, const std::string &platform_id)
    {
        std::cout << "robot_id: " << robot_id << ", platform_id: " << platform_id << std::endl;
        if (robot_id != current_robot_id_ || platform_id != current_platform_id_ || robot_id.empty() || platform_id.empty())
        {
            return false;
        }
        return true;
    }

    void SystemMasterControl::InvokeRobotRegTask(const json &msg)
    {
        RCLCPP_INFO(logger_, "收到机器人注册消息");
        std::string robot_id = msg["amr_id"];
        std::string platform_id = msg["platform_id"];
        auto command_code = msg["commands"][0]["code"].get<std::string>();

        json feedback;
        feedback["amr_id"] = robot_id;
        feedback["task_id"] = msg["task_id"];

        if (robot_id != current_robot_id_)
        {
            RCLCPP_WARN(this->get_logger(), "注册/注销功能,机器人id不匹配");
            feedback["status"] = "failed";
            feedback["txt"] = "机器人ID不匹配";
            AddTaskStatusMessages(feedback);
            return;
        }

        if (command_code == "register")
        {
            RCLCPP_INFO(this->get_logger(), "执行注册操作");
            current_platform_id_ = platform_id;
            feedback["status"] = "successed";
            feedback["txt"] = "注册成功";
            is_robot_reged_.store(true);
        }
        else if (command_code == "log_off")
        {
            RCLCPP_INFO(this->get_logger(), "执行注销操作");
            current_platform_id_ = "";
            feedback["status"] = "successed";
            feedback["txt"] = "注销成功";
            is_robot_reged_.store(false);
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "未知的命令代码: %s", command_code.c_str());
            feedback["status"] = "failed";
            feedback["txt"] = "未知的命令代码";
        }

        AddTaskStatusMessages(feedback);
    }

    void SystemMasterControl::InvokeMoveControlTask(const json &msg)
    {
        ymrobot_msgs::msg::Movebase move_base_msg;
        move_base_msg.speed = msg["SP"];
        move_base_msg.angle = msg["AG"];

        {
            std::lock_guard<std::mutex> l5(move_base_mutex_);
            last_move_ts_ = rclcpp::Clock().now().seconds();
            move_base_cloud_pub_->publish(move_base_msg);
        }
    }

    void SystemMasterControl::InvokeChassisControlTask(const json &msg)
    {
        auto nav_task_msg = ExecuteCommands(msg);
        chassis_task_pub_->publish(nav_task_msg);
    }

    void SystemMasterControl::GetDeviceStatus()
    {
        auto cpu_temperature = device_status_manager_->GetCpuTemperature();
        auto cpu_usage = device_status_manager_->GetCpuUsage(8);
        auto memory_usage = device_status_manager_->GetMemoryUsage();

        current_device_status_.cpu_temperature = cpu_temperature;
        current_device_status_.cpu_usage = cpu_usage;
        current_device_status_.memory_usage = memory_usage;
    }

    void SystemMasterControl::GetCurrentRobotPose(double &x, double &y, double &z, double &roll, double &pitch, double &yaw)
    {
        geometry_msgs::msg::PoseStamped pose_msg;
        try
        {
            // Get transform from tf tree
            auto transform = tf_buffer_->lookupTransform("map", "base_link", tf2::TimePointZero);
            // Fill pose message
            pose_msg.header.stamp = this->get_clock()->now();
            pose_msg.header.frame_id = "map";
            pose_msg.pose.position.x = transform.transform.translation.x;
            pose_msg.pose.position.y = transform.transform.translation.y;
            pose_msg.pose.position.z = transform.transform.translation.z;
            pose_msg.pose.orientation = transform.transform.rotation;

            // Convert quaternion to Euler angles (roll, pitch, yaw)
            tf2::Quaternion quat(
                pose_msg.pose.orientation.x,
                pose_msg.pose.orientation.y,
                pose_msg.pose.orientation.z,
                pose_msg.pose.orientation.w);

            tf2::Matrix3x3 mat(quat);
            mat.getRPY(roll, pitch, yaw); // roll, pitch, yaw are in radians

            // Assign values to output parameters
            x = pose_msg.pose.position.x;
            y = pose_msg.pose.position.y;
            z = pose_msg.pose.position.z;
        }
        catch (const tf2::TransformException &ex)
        {
            // In case of error, set all pose values to 0 (invalid pose)
            x = 0.0;
            y = 0.0;
            z = 0.0;
            roll = 0.0;
            pitch = 0.0;
            yaw = 0.0;

            RCLCPP_ERROR(this->get_logger(), "Transform error: %s", ex.what());
        }
    }

    void SystemMasterControl::GetCurrentRobotPointName()
    {
        point_name_list_ = sql_manager_.GetColumnFromCSV(pose_file_path_, 8);
        std::cout << "点位名称列表：" << std::endl;
        for (auto a : point_name_list_)
        {
            std::cout << a << std::endl;
        }
    }

    json SystemMasterControl::CreateSqlData(json audio_list, json expression_list, json up_action_list, json nav_point_list)
    {
        json sql_data;
        // sql_data["amr_id"] = *current_device_info_.robot_id;
        // sql_data["platform_id"] = *current_device_info_.platform_id;
        sql_data["amr_id"] = current_robot_id_;
        ;
        sql_data["platform_id"] = current_platform_id_;
        sql_data["task_type"] = "sql_data_update";
        sql_data["action_type"] = "all_data";
        sql_data["audio_list"] = audio_list;
        sql_data["expression_list"] = expression_list;
        sql_data["up_action_list"] = up_action_list;
        sql_data["nav_point_list"] = nav_point_list;

        RCLCPP_INFO(this->get_logger(), "从数据库中获取sql_data:%s", sql_data.dump().c_str());
        return sql_data;
    }

    json SystemMasterControl::GetAudioData()
    {
        json audio_data_list = sql_manager_.GetColumnFromCSV(mp3_file_path_, 0);
        return audio_data_list;
    }

    json SystemMasterControl::GetExpressionData(const std::string &expression_file_path)
    {
        json expression_list = sql_manager_.GetColumnFromCSV(expression_file_path, 1);
        return expression_list;
    }

    json SystemMasterControl::GetUpActionData(const std::string &up_action_file_path)
    {
        json up_action_list = sql_manager_.GetColumnFromCSV(up_action_file_path, 1);
        return up_action_list;
    }

    json SystemMasterControl::GetPoseData(const std::string &pose_file_path)
    {
        json result;
        std::vector<json> nav_point_list; // 存储所有导航点位的列表

        std::ifstream file(pose_file_path);
        if (!file.is_open())
        {
            result["error"] = "无法打开点位文件";
            return result;
        }

        // 跳过标题行（第一行）
        std::string line;
        std::getline(file, line);

        // 逐行解析 CSV 文件
        while (std::getline(file, line))
        {
            std::stringstream ss(line);
            std::string item;
            json point;

            try
            {
                std::getline(ss, item, ',');
                point["location_name"] = item;
                std::getline(ss, item, ',');
                point["map_name"] = item;
                std::getline(ss, item, ',');
                point["x"] = std::stod(item);
                std::getline(ss, item, ',');
                point["y"] = std::stod(item);
                std::getline(ss, item, ',');
                point["z"] = std::stod(item);
                std::getline(ss, item, ',');
                point["roll"] = std::stod(item);
                std::getline(ss, item, ',');
                point["pitch"] = std::stod(item);
                std::getline(ss, item, ',');
                point["yaw"] = std::stod(item);
                std::getline(ss, item, ',');
                point["pose_name"] = item;
                std::getline(ss, item, ',');
                point["pose_type"] = item;
                nav_point_list.push_back(point);
            }
            catch (const std::exception &e)
            {
                continue;
            }
        }
        return nav_point_list;
    }

    // json SystemMasterControl::GetPoseData(const std::string &pose_file_path)
    // {
    //     json up_action_list = sql_manager_.GetColumnFromCSV(pose_file_path, 0);
    //     return up_action_list;
    // }

    void SystemMasterControl::SendMqttRequsetMessage(const std::string &task_type, const std::string &action_code, const std::vector<std::string> &params)
    {
        json message;
        message["feedback_type"] = "request_task";
        message["amr_id"] = current_robot_id_;
        message["platform_id"] = current_platform_id_;
        message["task_type"] = task_type;
        message["action_code"] = action_code;
        message["params"] = params;

        std::lock_guard<std::mutex> lock(mqtt_publish_mutex_);
        if (!is_connect_success_.load())
        {
            return;
        }
        mqtt_client_->publish(mqtt_topic_request_task_fix_, message.dump());
        RCLCPP_INFO(this->get_logger(), "发送请求后端执行任务消息:%s", message.dump().c_str());
    }

    void SystemMasterControl::AddRobotStatusMessages(const json &msg)
    {
        robot_status_queue_.Push(msg);
    }

    void SystemMasterControl::AddTaskStatusMessages(const json &msg)
    {
        task_status_queue_.Push(msg);
    }

    void SystemMasterControl::FeedbackMessagesProcess()
    {
        rclcpp::WallRate loop_rate(10);
        while (rclcpp::ok())
        {
            if (!is_connect_success_.load() || !is_robot_reged_.load())
            {
                loop_rate.sleep();
                continue;
            }

            json message;
            // if (is_first_connect_success_.load() && is_cloud_chassis_update_.load())
            if (is_first_connect_success_.load())
            {
                message = CreateSqlData(GetAudioData(), GetExpressionData(expression_file_path_), GetUpActionData(up_action_file_path_), GetPoseData(pose_file_path_));
                SendMqttInitMessage(message);
                message.clear();
                RCLCPP_INFO(this->get_logger(), "设备初始化，上报sql数据");
                is_first_connect_success_.store(false);
                is_cloud_chassis_update_.store(false);
                GetCurrentRobotPointName();
            }

            // 优先处理事件驱动消息POWER_OFF
            while (task_status_queue_.TryPop(message))
            {
                SendMqttTaskMessage(message);
                message.clear();
            }
            // 其次处理定时消息
            while (robot_status_queue_.TryPop(message))
            {
                SendMqttDeviceMessage(message);
                message.clear();
            }

            loop_rate.sleep();
        }
    }

    ymrobot_msgs::msg::Task SystemMasterControl::ExecuteCommands(const json &msg)
    {
        json msg_data = msg;
        json respon_data;
        auto nav_task_msg = ymrobot_msgs::msg::Task();
        auto binary_file_msg = ymrobot_msgs::msg::BinaryData();

        auto task_type = task_type_name_map[msg_data["task_type"].get<std::string>()];
        std::cout << "任务类型2： " << static_cast<int>(task_type) << std::endl;
        try
        {
            auto nav_points_msgs = std::vector<ymrobot_msgs::msg::NavPoint>();
            std::cout << "1111" << std::endl;
            nav_task_msg.platform_id = msg_data["platform_id"];
            nav_task_msg.amr_id = msg_data["amr_id"];
            nav_task_msg.task_id = msg_data["task_id"];
            nav_task_msg.task_type = task_type;
            // nav_task_msg.control_mode = msg_data["control_mode"].get<uint8_t>();
            nav_task_msg.behavior_tree = msg_data.value("behavior_tree", "");
            nav_task_msg.reload = msg_data["reload"].get<bool>();

            ymrobot_msgs::msg::Command command_;
            command_.code = action_type_name_map[msg_data["commands"][0]["code"].get<std::string>()]; // 动作转义

            if (msg_data["nav_points"].size() > 0)
            {
                for (auto point : msg_data["nav_points"])
                {
                    auto nav_points_msg = ymrobot_msgs::msg::NavPoint();
                    auto pose = geometry_msgs::msg::PoseStamped();
                    nav_points_msg.seq = point["seq"].get<int>();
                    nav_points_msg.nav_name = point["name"].get<std::string>();
                    nav_points_msg.nav_map_name = point["map_name"].get<std::string>();
                    if (task_type == ymrobot_msgs::msg::Task::BT_TASK || command_.code == ymrobot_msgs::msg::Command::CLOUD_NAVIGATION_NAME)
                    {
                        nav_points_msgs.emplace_back(nav_points_msg);
                        continue;
                    }
                    else
                    {
                        pose.header.frame_id = "map";
                        pose.header.stamp = this->get_clock()->now();
                        pose.pose.position.x = point["pose"]["position"]["x"];
                        pose.pose.position.y = point["pose"]["position"]["y"];
                        pose.pose.position.z = point["pose"]["position"]["z"];
                        pose.pose.orientation.w = point["pose"]["orientation"]["w"];
                        pose.pose.orientation.x = point["pose"]["orientation"]["x"];
                        pose.pose.orientation.y = point["pose"]["orientation"]["y"];
                        pose.pose.orientation.z = point["pose"]["orientation"]["z"];
                        nav_points_msg.position = pose;
                        nav_points_msgs.emplace_back(nav_points_msg);
                    }
                }
                nav_task_msg.nav_points = nav_points_msgs;
            }

            for (auto command : msg_data["commands"])
            {
                auto command_msg = ymrobot_msgs::msg::Command();
                auto params = std::vector<std::string>();
                command_msg.code = action_type_name_map[command["code"].get<std::string>()]; // 动作转义

                // 假如有时候没有下发动作，就需要写一个假动作来欺骗行为树
                if (command["params"].is_array()) {
                    auto& params_array = command["params"];
                    for (auto& param : params_array) {
                        if (param.is_null()) {
                            param = "初始化(双臂归位)";
                        }
                    }
                }
                for (auto param : command["params"])
                {
                    params.emplace_back(param);
                }
                command_msg.params = params;
                command_msg.params_code = command["params_code"].get<std::string>();
                nav_task_msg.commands.push_back(command_msg);
            }

            binary_file_msg.file_format = "";
            binary_file_msg.binary_data = std::vector<uint8_t>();
            // binary_file_msg.file_format = msg_data["file_format"];
            // binary_file_msg.binary_data = msg_data["binary_data"].get<std::vector<uint8_t>>();

            nav_task_msg.binary_file = binary_file_msg;
            RCLCPP_INFO(this->get_logger(), "当前任务解析成功,准备下发至task_gudiance");
        }
        catch (const std::exception &e)
        {
            RCLCPP_ERROR(this->get_logger(), "当前任务解析解析失败，%s", e.what());
            return nav_task_msg;
        }

        return nav_task_msg;
    }

    void SystemMasterControl::TaskStatusSubCallback(const ymrobot_msgs::msg::TaskStatus::SharedPtr msg)
    {
        auto task_status = msg->status;
        std::cout << "来任务状态消息****" << std::endl;
        if (task_status == current_task_status_)
        {
            return;
        }

        json task_status_msg;
        current_task_status_ = task_status;
        std::string current_task_status = task_status_name_map[current_task_status_];
        task_status_msg["response_type"] = "task_status_response";
        task_status_msg["amr_id"] = msg->amr_id;
        task_status_msg["task_id"] = msg->task_id;
        task_status_msg["status"] = (current_task_status != "cancel") ? current_task_status : "fail";
        task_status_msg["text"] = msg->text;
        AddTaskStatusMessages(task_status_msg);
        std::cout << "当前任务id： " << current_larget_model_task_id_ << std::endl;

        if (current_task_status == "running")
        {
            current_robot_status_.store(ROBOT_STATUS::RUNNING);
            RCLCPP_INFO(this->get_logger(), "任务在运行中");
        }
        else if (current_task_status == "successed")
        {
            if (msg->task_id == std::to_string(current_larget_model_task_id_))
            {
                is_large_mode_task_successed_.store(LARGE_MODEL_TASK_STATUS::SUCCESSED);
                RCLCPP_INFO(this->get_logger(), "大模型任务成功");
            }

            if(is_charge_.load())
            {
                RCLCPP_INFO(this->get_logger(), "吹彩虹任务成功");
                is_charge_.store(false);
                return;
            }

            current_robot_status_.store(ROBOT_STATUS::IDLE);
            RCLCPP_INFO(this->get_logger(), "任务成功");
        }
        else if (current_task_status == "fail")
        {
            if (msg->task_id == std::to_string(current_larget_model_task_id_))
            {
                is_large_mode_task_successed_.store(LARGE_MODEL_TASK_STATUS::FAIL);
                RCLCPP_INFO(this->get_logger(), "大模型任务失败");
            }
            current_robot_status_.store(ROBOT_STATUS::IDLE);
            RCLCPP_INFO(this->get_logger(), "任务失败");
        }
        else if (current_task_status == "cancel")
        {
            RCLCPP_INFO(this->get_logger(), "current_task_status: %s", current_task_status.c_str());
            current_robot_status_.store(ROBOT_STATUS::IDLE);
            RCLCPP_INFO(this->get_logger(), "任务取消");
        }
    }

    void SystemMasterControl::BtTaskNodeStatusSubCallback(const ymrobot_msgs::msg::BTNodeTaskState::SharedPtr msg)
    {
        std::cout << "来行为树节点状态消息****" << std::endl;
        std::string task_type = msg->task_type;
        std::string action_code = msg->node_name;
        std::string action_content = msg->node_action_content;
        std::string task_status = msg->node_task_state;
        std::string txt = msg->node_task_error_message;

        json task_node_status_json_msg;
        task_node_status_json_msg["feedback_type"] = "node_task_status";
        task_node_status_json_msg["amr_id"] = current_robot_id_;
        task_node_status_json_msg["task_type"] = task_type;
        task_node_status_json_msg["action_code"] = action_code;
        task_node_status_json_msg["action_content"] = action_content;
        task_node_status_json_msg["task_status"] = task_status;
        task_node_status_json_msg["txt"] = txt;
        task_node_status_json_msg["node_task_id"] = msg->task_id;
        AddTaskStatusMessages(task_node_status_json_msg);
    }

    void SystemMasterControl::DataUpdateListSubCallback(const ymrobot_msgs::msg::UpdateList::SharedPtr msg)
    {
        is_cloud_chassis_update_.store(true);
        json message;
        switch (msg->code)
        {
        case ymrobot_msgs::msg::UpdateList::ALL_ACTION:
        {
            message = CreateSqlData(GetAudioData(), GetExpressionData(expression_file_path_), GetUpActionData(up_action_file_path_), GetPoseData(pose_file_path_));
            message["action_type"] = "audio_data";
            break;
        }
        case ymrobot_msgs::msg::UpdateList::POSE_MANAGER:
        {
            message = CreateSqlData(GetAudioData(), GetExpressionData(expression_file_path_), GetUpActionData(up_action_file_path_), json());
            message["action_type"] = "audio_data";
            break;
        }
        case ymrobot_msgs::msg::UpdateList::AUDIO:
        {
            message = CreateSqlData(GetAudioData(), json(), json(), json());
            message["action_type"] = "audio_data";
            break;
        }
        case ymrobot_msgs::msg::UpdateList::EMOJI:
        {
            message = CreateSqlData(json(), GetExpressionData(expression_file_path_), json(), json());
            message["action_type"] = "expression_data";
            break;
        }
        case ymrobot_msgs::msg::UpdateList::UP_CLIMB_ACTION:
        {
            message = CreateSqlData(json(), json(), GetUpActionData(up_action_file_path_), json());
            message["action_type"] = "up_action_data";
            break;
        }
        default:
            break;
        }
        SendMqttInitMessage(message);
        message.clear();
        RCLCPP_INFO(this->get_logger(), "更新列表消息发送至后端成功");
    }

    void SystemMasterControl::CloudChassisNavCallBack(const std_msgs::msg::Empty::SharedPtr msg)
    {
        is_cloud_chassis_update_.store(true);
    }

    void SystemMasterControl::PowerThresholdParameterUpdateSubCallback(const std_msgs::msg::Float64::SharedPtr msg)
    {
        double power_threshold = msg->data;
        low_battery_recharge_threshold_.store(power_threshold);
        RCLCPP_INFO(this->get_logger(), "回充电量阈值更新为: %f", power_threshold);
    }

    void SystemMasterControl::CloudChassisStatusInfoSubCallback(const ymrobot_msgs::msg::CloudChassisStatus::SharedPtr msg)
    {
        {
            std::unique_lock<std::shared_mutex> l6(cloud_chassis_state_mutex_);
            current_chassis_info_ = *msg;
        }
    }

    void SystemMasterControl::UpLimbControlCallBack(rclcpp::Client<ymrobot_msgs::srv::UpLimb>::SharedFuture result_future)
    {
        auto success = result_future.get()->success;
        json msg;
        msg["am_id"] = "111";
        msg["platform_id"] = "111";
        msg["task_type"] = "up_limb";

        if (success)
        {
            RCLCPP_INFO(this->get_logger(), "上臂任务成功");
            msg["success"] = true;
            msg["message"] = "上臂任务成功";
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "上臂任务失败");
            msg["success"] = false;
            msg["message"] = "上臂任务成功";
        }
        AddTaskStatusMessages(msg);
    }

    void SystemMasterControl::AudioControlCallBack(rclcpp::Client<ymrobot_msgs::srv::Audio>::SharedFuture result_future)
    {
        std::cout << "音频消息返回了" << std::endl;
        auto success = result_future.get()->success;
        json msg;
        msg["am_id"] = "111";
        msg["platform_id"] = "111";
        msg["task_type"] = "voice_cmd";

        if (success)
        {
            RCLCPP_INFO(this->get_logger(), "固定语音任务成功");
            msg["success"] = true;
            msg["message"] = "固定语音任务成功";
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "固定语音任务失败");
            msg["success"] = false;
            msg["message"] = "固定语音任务失败";
        }
        AddTaskStatusMessages(msg);
    }

    void SystemMasterControl::MoveTargetServerCallback(const std::shared_ptr<ymrobot_msgs::srv::MoveTarget::Request> request, std::shared_ptr<ymrobot_msgs::srv::MoveTarget::Response> response)
    {
        if (request == nullptr)
        {
            response->success = false;
            response->message = "上肢请求移动为空";
            return;
        }

        auto target_pose = request->target_pose;
        json msg;
        msg["am_id"] = "111";
        msg["platform_id"] = "111";
        msg["task_type"] = "move_target";
        msg["target_pose"] = target_pose;

        RCLCPP_INFO(this->get_logger(), "请求移动点：%s", target_pose);

        // for (auto &hdl : connections_)
        // {
        //     try
        //     {
        //         ws_server_.send(hdl, msg.dump(), websocketpp::frame::opcode::text); // 发送状态消息
        //     }
        //     catch (const websocketpp::exception &e)
        //     {
        //         RCLCPP_ERROR(this->get_logger(), "发送状态失败: %s", e.what());
        //     }
        // }

        SendWebSocketMessage(msg);

        while (true)
        {
            if (is_move_feedback_.load())
            {
                break;
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(1000)); // 等待1000毫秒
        }

        if (!is_move_success_.load())
        {
            response->success = false;
            response->message = "移动失败";
        }
        else
        {
            response->success = true;
            response->message = "移动成功";
        }

        is_move_feedback_.store(false);
        is_move_success_.store(false);
    }

    void SystemMasterControl::LargeModelRequestSrviceCallback(const std::shared_ptr<ymrobot_msgs::srv::LargeModelRequestTask::Request> request, std::shared_ptr<ymrobot_msgs::srv::LargeModelRequestTask::Response> response)
    {
        if (request == nullptr || current_robot_status_ == ROBOT_STATUS::RUNNING || current_robot_status_ == ROBOT_STATUS::UPGRADING || current_robot_status_ == ROBOT_STATUS::ERROR || current_robot_status_ == ROBOT_STATUS::CHARGING)
        {
            response->success = false;
            response->message = "当前状态不允执行任务";
            return;
        }

        current_robot_status_ = ROBOT_STATUS::RUNNING;
        ++current_larget_model_task_id_;
        ymrobot_msgs::msg::Task task_msg;
        ymrobot_msgs::msg::Command command_msg;
        ymrobot_msgs::msg::NavPoint nav_msg;
        task_msg.platform_id = current_platform_id_;
        task_msg.amr_id = current_robot_id_;
        task_msg.task_id = std::to_string(current_larget_model_task_id_);

        switch (request->larget_mode_task_type)
        {
        case 0:
        {
            std::string nav_target_name = request->mark_point_name;
            RCLCPP_INFO(this->get_logger(), "大模型命令：自动导航到 %s", nav_target_name.c_str());

            bool exists = std::find(point_name_list_.begin(), point_name_list_.end(), nav_target_name) != point_name_list_.end();
            if (!exists)
            {
                RCLCPP_ERROR(this->get_logger(), "导航目标点不存在");
                response->success = false;
                response->message = "任务执行失败,导航目标点不存在";
                return;
            }

            command_msg.code = ymrobot_msgs::msg::Command::CLOUD_NAVIGATION_NAME;
            nav_msg.seq = 0;
            nav_msg.nav_name = nav_target_name;
            task_msg.nav_points.emplace_back(nav_msg);
            break;
        }
        case 1:
        {
            RCLCPP_INFO(this->get_logger(), "大模型命令：自动多点导航");
            command_msg.code = ymrobot_msgs::msg::Command::MULIT_POINTS_NAVIGATION;
            auto nav_points = request->mark_point_name_list;
            for (auto nav_pose_name : nav_points)
            {
                command_msg.params.emplace_back(nav_pose_name);
            }
            break;
        }
        case 2:
        {
            RCLCPP_INFO(this->get_logger(), "执行请求导览任务: %s", request->guidance_task_name.c_str());
            std::vector<std::string> params;
            params.emplace_back(request->guidance_task_name);
            SendMqttRequsetMessage("bt_task", "guide_explanation", params);
            break;
        }
        case 3:
        {
            RCLCPP_INFO(this->get_logger(), "请求执行上肢任务: %d", request->upper_climb_fixed_action);
            // auto up_request = std::make_shared<ymrobot_msgs::srv::UpLimb::Request>();
            // up_request->up_limb_task_type = 2;
            // up_request->action_fixed = request->upper_climb_fixed_action;
            // auto future2 = up_limb_client_->async_send_request(up_request);
            // future2.wait();
            // break;

            // RCLCPP_INFO(this->get_logger(), "请求执行诗词任务: %d", request->upper_climb_fixed_action);
            // command_msg.code = ymrobot_msgs::msg::Command::EXE_BEHAVIOR_TREE;
            // command_msg.params.emplace_back(request->upper_climb_fixed_action);

            std::string poetry_recitation_name = poetry_recitation_name_map[request->upper_climb_fixed_action];
            RCLCPP_INFO(this->get_logger(), "执行诗词任务: %s", poetry_recitation_name.c_str());
            std::vector<std::string> params;
            params.emplace_back(poetry_recitation_name);
            SendMqttRequsetMessage("limb_act", "place_fixed", params);
            break;
        }
        default:
            break;
        }
        task_msg.commands.emplace_back(command_msg);
        chassis_task_pub_->publish(task_msg);

        // // 使用异步方式来处理任务状态检查 bug
        // auto task_future = std::async(std::launch::async, [this, response]()
        //                               {
        // rclcpp::Rate loop_rate(LARGE_MODE_TASK_FEEDBACK_THREAD_HZ);
        // while (rclcpp::ok())
        // {
        //     if (is_large_mode_task_successed_.load() == LARGE_MODEL_TASK_STATUS::RUNNING)
        //     {
        //         loop_rate.sleep();
        //         continue;
        //     }
        //     else if (is_large_mode_task_successed_.load() == LARGE_MODEL_TASK_STATUS::SUCCESSED)
        //     {
        //         response->success = true;
        //         response->message = "任务执行成功";
        //         RCLCPP_INFO(this->get_logger(), "大模型任务执行成功");
        //         break;
        //     }
        //     else if (is_large_mode_task_successed_.load() == LARGE_MODEL_TASK_STATUS::FAIL)
        //     {
        //         response->success = false;
        //         response->message = "任务执行失败";
        //         RCLCPP_ERROR(this->get_logger(), "大模型任务执行失败");
        //         break;
        //     }

        //     loop_rate.sleep();
        // }
        response->success = true;
        response->message = "任务执行成功";
        RCLCPP_INFO(this->get_logger(), "大模型任务执行成功");
        current_robot_status_.store(ROBOT_STATUS::IDLE);
        is_large_mode_task_successed_.store(LARGE_MODEL_TASK_STATUS::RUNNING);
    }

    void SystemMasterControl::AlarmInfoSubCallback(const std_msgs::msg::String::SharedPtr msg)
    {
        RCLCPP_INFO(this->get_logger(), "收到报警信息：%s", msg->data.c_str());
        json alarm_msg;
        alarm_msg["feedback_type"] = "alert_info";
        alarm_msg["amr_id"] = current_robot_id_;
        alarm_msg["platform_id"] = current_platform_id_;
        alarm_msg["txt"] = msg->data;
        SendMqttAlarmMessage(alarm_msg);
    }

    void SystemMasterControl::StopRobot()
    {
        ymrobot_msgs::msg::Movebase move_base_msg;
        move_base_msg.speed = 0.0;
        move_base_msg.angle = 0.0;
        move_base_cloud_pub_->publish(move_base_msg);
    }

    void SystemMasterControl::CancelCurrentTask()
    {
        ymrobot_msgs::msg::Task task_msg;
        ymrobot_msgs::msg::Command command_msg;
        task_msg.platform_id = current_platform_id_;
        task_msg.amr_id = current_robot_id_;
        task_msg.task_id = "111";
        task_msg.task_type = ymrobot_msgs::msg::Task::TASK_GUIDANCE;
        command_msg.code = ymrobot_msgs::msg::Command::CANCLE;
        task_msg.commands.emplace_back(command_msg);
        chassis_task_pub_->publish(task_msg);
        RCLCPP_INFO(this->get_logger(), "发送取消当前任务的指令");
    }

    void SystemMasterControl::MoveWaitPose()
    {
    }

    void SystemMasterControl::RechargeThresholdJudgment(const double current_power)
    {
        if(current_power <= low_battery_alarm_threshold_)
        {
            if(current_chassis_info_.charge_state)
            {
                current_robot_status_.store(ROBOT_STATUS::CHARGING);
                std::cout <<"[低于警报电量] 已经对上充电桩，停止回充动作" << std::endl;
                return;
            }
            if (current_robot_status_.load() != ROBOT_STATUS::CHARGING)
            {
                std_msgs::msg::Int32 msg;
                msg.data = 1;
                play_fixed_audio_pub_->publish(msg);
                std::cout << "当前电量低于警告阈值" << std::endl;


                current_robot_status_ = ROBOT_STATUS::CHARGING;
                ymrobot_msgs::msg::Task task_msg;
                auto command_msg = ymrobot_msgs::msg::Command();

                // command_msg.code == ymrobot_msgs::msg::Command::CHARGE;  // bug
                command_msg.code = ymrobot_msgs::msg::Command::CHARGE;
                task_msg.platform_id = current_platform_id_;
                task_msg.amr_id = current_robot_id_;
                task_msg.task_id = "111";
                task_msg.task_type = ymrobot_msgs::msg::Task::CLOUD_CHASSIS;
                task_msg.commands.push_back(command_msg);
                chassis_task_pub_->publish(task_msg);
                RCLCPP_INFO(this->get_logger(), "低于电量阈值，发送充电任务");

                return;
            }
        }
        else if (current_power <= low_battery_recharge_threshold_)
        {
            
            if(current_robot_status_.load() == ROBOT_STATUS::CHARGING)
            {
                // std::cout <<"111111111111111111"<<std::endl;
                return;
            }
            else if(current_chassis_info_.charge_state)
            {
                current_robot_status_.store(ROBOT_STATUS::CHARGING);
                std::cout <<"[低于预设低电量] 已经对上充电桩，停止回充动作" << std::endl;
                return;
            }
            else if (current_robot_status_.load() == ROBOT_STATUS::IDLE)
            {
                std::cout <<"************************************************"<<std::endl;
                current_robot_status_.store(ROBOT_STATUS::CHARGING);
                ymrobot_msgs::msg::Task task_msg;
                auto command_msg = ymrobot_msgs::msg::Command();

                // command_msg.code == ymrobot_msgs::msg::Command::CHARGE;  // bug
                command_msg.code = ymrobot_msgs::msg::Command::CHARGE;
                task_msg.platform_id = current_platform_id_;
                task_msg.amr_id = current_robot_id_;
                task_msg.task_id = "111";
                task_msg.task_type = ymrobot_msgs::msg::Task::CLOUD_CHASSIS;
                task_msg.commands.push_back(command_msg);
                chassis_task_pub_->publish(task_msg);
                RCLCPP_INFO(this->get_logger(), "低于电量阈值，发送充电任务");
                is_charge_.store(true);
            }
        }
        else if (current_power > low_battery_recharge_threshold_)
        {
            if (current_robot_status_ == ROBOT_STATUS::CHARGING)
            {
                current_robot_status_ = ROBOT_STATUS::IDLE;
            }
        }
    }

    void SystemMasterControl::CurrentRobotStatusUpdate()
    {
        // 如果当前状态与上一次状态相同，则直接返回
        if (current_robot_status_.load() == last_robot_status_.load())
        {
            return;
        }
        ymrobot_msgs::msg::LedShow led_show_msg;
        led_show_msg.luminance = 255; // 最大亮度
        auto current_robot_status_msg = std_msgs::msg::Int64();
        // 根据当前状态设置 RGB 颜色
        switch (current_robot_status_.load())
        {
        case ROBOT_STATUS::IDLE:
            led_show_msg.color_r = 0;   // 红色
            led_show_msg.color_g = 0;   // 绿色 255
            led_show_msg.color_b = 100; // 蓝色
            current_robot_status_msg.data = 0;
            break;
        case ROBOT_STATUS::RUNNING:
            led_show_msg.color_r = 0;   // 红色
            led_show_msg.color_g = 0;   // 绿色
            led_show_msg.color_b = 100; // 蓝色
            current_robot_status_msg.data = 1;
            break;
        case ROBOT_STATUS::CHARGING:
            led_show_msg.color_r = 100; // 红色
            led_show_msg.color_g = 100; // 绿色
            led_show_msg.color_b = 0;   // 蓝色
            current_robot_status_msg.data = 2;
            break;
        case ROBOT_STATUS::UPGRADING:
            led_show_msg.color_r = 128; // 红色
            led_show_msg.color_g = 0;   // 绿色
            led_show_msg.color_b = 128; // 蓝色
            current_robot_status_msg.data = 4;
            break;
        case ROBOT_STATUS::PAUSED:
            led_show_msg.color_r = 255; // 红色
            led_show_msg.color_g = 165; // 绿色
            led_show_msg.color_b = 0;   // 蓝色
            current_robot_status_msg.data = 5;
            break;
        case ROBOT_STATUS::ERROR:
            led_show_msg.color_r = 255; // 红色
            led_show_msg.color_g = 0;   // 绿色
            led_show_msg.color_b = 0;   // 蓝色
            current_robot_status_msg.data = 6;
            break;
        default:
            led_show_msg.color_r = 255; // 红色
            led_show_msg.color_g = 255; // 绿色
            led_show_msg.color_b = 255; // 蓝色
            break;
        }
        led_show_pub_->publish(led_show_msg);
        last_robot_status_ = current_robot_status_.load();
        current_robot_status_pub_->publish(current_robot_status_msg);
        std::cout << "发布灯带颜色*******************************************************************" << std::endl;
        // 空闲状态为：绿色
        // 运行状态为：蓝色
        // 充电状态为：黄色
        // 升级状态为：紫色
        // 暂停状态为：橙色
        // 错误状态为：红色
        // 其他状态为：白色
    }

    void SystemMasterControl::SendMqttInitMessage(const json &msg)
    {
        std::lock_guard<std::mutex> lock(mqtt_publish_mutex_);
        if (!is_connect_success_.load())
        {
            return;
        }
        mqtt_client_->publish(mqtt_topic_init_pub_fix_, msg.dump());
        RCLCPP_INFO(this->get_logger(), "发送消息：%s 至后端", msg.dump().c_str());
    }

    // void SystemMasterControl::SendMqttInitMessage(const json &msg) 
    // {
    //     std::lock_guard<std::mutex> lock(mqtt_publish_mutex_);
    //     if (!is_connect_success_.load()) {
    //         RCLCPP_WARN(this->get_logger(), "MQTT连接未就绪，消息丢弃");
    //         return;
    //     }
    //     try {
    //         std::string payload = msg.dump();
    //         mqtt_client_->publish(mqtt_topic_init_pub_fix_, payload);
    //         RCLCPP_INFO(this->get_logger(), "发送消息：%s", payload.c_str());
    //     } catch (const std::exception &e) {
    //         RCLCPP_ERROR(this->get_logger(), "JSON序列化失败：%s", e.what());
    //     }
    // }


    void SystemMasterControl::SendMqttDeviceMessage(const json &msg)
    {
        std::lock_guard<std::mutex> lock(mqtt_publish_mutex_);
        if (!is_connect_success_.load())
        {
            return;
        }
        mqtt_client_->publish(mqtt_topic_device_pub_fix_, msg.dump());
    }

    void SystemMasterControl::SendMqttTaskMessage(const json &msg)
    {
        std::lock_guard<std::mutex> lock(mqtt_publish_mutex_);
        if (!is_connect_success_.load())
        {
            return;
        }
        mqtt_client_->publish(mqtt_topic_task_pub_fix_, msg.dump());
    }

    void SystemMasterControl::SendMqttAlarmMessage(const json &msg)
    {
        std::lock_guard<std::mutex> lock(mqtt_publish_mutex_);
        if (!is_connect_success_.load())
        {
            return;
        }
        mqtt_client_->publish(mqtt_topic_alarm_sms_fix_, msg.dump());
    }

    void SystemMasterControl::SendWebSocketMessage(const json &msg)
    {
        for (auto &hdl : connections_)
        {
            try
            {
                ws_server_.send(hdl, msg.dump(), websocketpp::frame::opcode::text); // 发送状态消息
            }
            catch (const websocketpp::exception &e)
            {
                RCLCPP_ERROR(this->get_logger(), "发送状态失败: %s", e.what());
            }
        }
    }

}

int main(int argc, char *argv[])
{
    // rclcpp::init(argc, argv);
    // rclcpp::spin(std::make_shared<ymrobot::SystemMasterControl>());
    // rclcpp::shutdown();
    // return 0;

    rclcpp::init(argc, argv);
    auto node = std::make_shared<ymrobot::SystemMasterControl>();
    rclcpp::executors::MultiThreadedExecutor executor;
    executor.add_node(node);
    RCLCPP_INFO(node->get_logger(), "Node is running with MultiThreadedExecutor.");
    executor.spin();
    rclcpp::shutdown();
    return 0;
}