#include "cloud_water_chassis_node.hpp"

#define CHASSIS_SEND_MSG_HZ 20   // 云迹底盘发送消息频率
#define CHASSIS_NAV_RESULST_HZ 1 // 云迹底盘发布导航结果频率
#define CHASSIS_STATUS_HZ 1      // 云迹底盘状态更新线程

#define MAX_RECONNECT_ATTEMPTS 5        // 最大重连次数
#define INITIAL_RECONNECT_DELAY_MS 1000 // 初始重连延迟（毫秒）
#define MAX_RECONNECT_DELAY_MS 10000    // 最大重连延迟（毫秒）

namespace ymrobot
{
    CloudWaterChassisNode::CloudWaterChassisNode() : Node("cloud_water_chassis_node")
    {
        Init();
    }

    CloudWaterChassisNode::~CloudWaterChassisNode()
    {
        // 关闭TCP连接
        if (tcp_socket_fd_ >= 0)
        {
            close(tcp_socket_fd_);
            tcp_socket_fd_ = -1;
        }
        // 停止并等待线程结束
        if (receive_tcp_service_thread_.joinable())
        {
            receive_tcp_service_thread_.join();
        }
        if (chassis_task_process_thread_.joinable())
        {
            chassis_task_process_thread_.join();
        }
    }

    void CloudWaterChassisNode::Init()
    {
        InitParams();
        CreateSubAndPub();
        InitTcpClient();
        cloud_chassis_run_status_thread_ = std::thread(&CloudWaterChassisNode::CloudChassisRunStatusThread, this);
        receive_tcp_service_thread_ = std::thread(&CloudWaterChassisNode::ReceiveTcpMessageThread, this);
        chassis_task_process_thread_ = std::thread(&CloudWaterChassisNode::ChassisTaskProcessThread, this);
    }

    void CloudWaterChassisNode::CloudWaterChassisNode::InitTcpClient()
    {
        // try
        // {
        //     tcp_context_ = std::make_unique<zmq::context_t>(1);
        //     tcp_socket_ = std::make_unique<zmq::socket_t>(*tcp_context_, ZMQ_REQ);

        //     int reconnect_ivl = 100; // 初始重连间隔为 100 毫秒
        //     tcp_socket_->setsockopt(ZMQ_RECONNECT_IVL, &reconnect_ivl, sizeof(reconnect_ivl));
        //     int reconnect_ivl_max = 10000; // 最大重连间隔为 10 秒
        //     tcp_socket_->setsockopt(ZMQ_RECONNECT_IVL_MAX, &reconnect_ivl_max, sizeof(reconnect_ivl_max));

        //     tcp_socket_->connect(server_address_); // 链接tcp服务地址

        //     RCLCPP_INFO(this->get_logger(), "Connect to server success");
        //     is_connect_success_.store(true);
        // }
        // catch (const std::exception &e)
        // {
        //     std::cerr << "Error connecting to server: " << e.what() << std::endl;
        //     is_connect_success_.store(false);
        // }

        tcp_socket_fd_ = socket(AF_INET, SOCK_STREAM, 0);
        if (tcp_socket_fd_ < 0)
        {
            RCLCPP_ERROR(this->get_logger(), "无法连接到tcp服务端");
            return;
        }

        struct sockaddr_in server_addr;
        memset(&server_addr, 0, sizeof(server_addr));
        server_addr.sin_family = AF_INET;
        server_addr.sin_port = htons(server_port_); // tcp端口号
        RCLCPP_INFO(this->get_logger(), "tcp服务端地址：%s", server_address_.c_str());
        RCLCPP_INFO(this->get_logger(), "tcp服务端端口：%d", server_port_);

        if (inet_pton(AF_INET, server_address_.c_str(), &server_addr.sin_addr) <= 0)
        {
            RCLCPP_ERROR(this->get_logger(), "无效的IP地址");
            close(tcp_socket_fd_);
            cloud_chassis_status_ = CloudChassisRunStatus::DISCONNECT;
            return;
        }

        // if (connect(tcp_socket_fd_, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)
        // {
        //     RCLCPP_ERROR(this->get_logger(), "连接到tcp服务端失败");
        //     close(tcp_socket_fd_);
        //     cloud_chassis_status_ = CloudChassisRunStatus::DISCONNECT;
        //     return;
        // }

         // 目前暂未考虑底盘失联的问题
         while (true)
         {
             if (connect(tcp_socket_fd_, (struct sockaddr *)&server_addr, sizeof(server_addr)) == 0)
             {
                 RCLCPP_INFO(this->get_logger(), "链接tcp服务端成功, 地址和端口为: %s:%d", server_address_.c_str(), server_port_);
                 cloud_chassis_status_ = CloudChassisRunStatus::ACTIVATE;
                 break;
             }
 
             RCLCPP_WARN(this->get_logger(), "连接到tcp服务端失败: %s，1秒后重试...", strerror(errno));
             cloud_chassis_status_ = CloudChassisRunStatus::DISCONNECT;
             std::this_thread::sleep_for(std::chrono::seconds(1));
         }

        // RCLCPP_INFO(this->get_logger(), "链接tcp服务端成功,服务端地址和端口号分别为: %s:%d", server_address_.c_str(), server_port_);
        // cloud_chassis_status_ = CloudChassisRunStatus::ACTIVATE;
    }

    void CloudWaterChassisNode::ReconnectTcpClient()
    {
        int reconnect_attempts = 0;
        int reconnect_delay_ms = INITIAL_RECONNECT_DELAY_MS;

        while (reconnect_attempts < MAX_RECONNECT_ATTEMPTS && rclcpp::ok())
        {
            RCLCPP_INFO(this->get_logger(), "Attempting to reconnect to server (attempt %d/%d)...", reconnect_attempts + 1, MAX_RECONNECT_ATTEMPTS);

            try
            {
                std::lock_guard<std::mutex> l2(tcp_socket_mutex_);
                if (tcp_socket_)
                {
                    tcp_socket_->close();
                }
                if (tcp_context_)
                {
                    tcp_context_->close();
                }

                tcp_context_ = std::make_unique<zmq::context_t>(1);
                tcp_socket_ = std::make_unique<zmq::socket_t>(*tcp_context_, ZMQ_REQ);
                tcp_socket_->connect(server_address_);

                RCLCPP_INFO(this->get_logger(), "Reconnect to server success");
                cloud_chassis_status_ = CloudChassisRunStatus::ACTIVATE; // 重连成功，退出重连逻辑
                return;
            }
            catch (const std::exception &e)
            {
                RCLCPP_ERROR(this->get_logger(), "Reconnect failed: %s", e.what());
                reconnect_attempts++;
                reconnect_delay_ms = std::min(reconnect_delay_ms * 2, MAX_RECONNECT_DELAY_MS); // 指数退避
                std::this_thread::sleep_for(std::chrono::milliseconds(reconnect_delay_ms));
            }
        }

        RCLCPP_ERROR(this->get_logger(), "Max reconnect attempts reached. Giving up.");
        cloud_chassis_status_ = CloudChassisRunStatus::DISCONNECT; // 设置连接失败标志
    }

    void CloudWaterChassisNode::InitParams()
    {
        this->declare_parameter("server_address", "");
        this->declare_parameter("server_port", 0);
        this->declare_parameter("mark_points_csv_adress", "");
        this->declare_parameter("pub_chassis_status_info_topic", "");
        this->declare_parameter("cloud_water_mark_point_topic_name", "");
        this->declare_parameter("cloud_water_move_base_topic", "");
        this->declare_parameter("play_fixed_audio_pub_name", "");
        this->declare_parameter("alarm_info_pub_name", "");
        this->declare_parameter("key_vel_move_base_topic", "");
        this->declare_parameter("led_show_topic_name", "");
        this->declare_parameter("cloud_water_nav_target_srv_name", "");
        this->declare_parameter("cloud_chassis_nav_action_name", "");
        this->declare_parameter("cloud_chassis_charge_action_name", "");
        this->declare_parameter("cloud_chassis_point_upadte_pub_name", "");
        this->declare_parameter("cloud_chassis_reposition_action_name", "");
        this->declare_parameter("max_linear_speed_sub_name", "");
        this->declare_parameter("max_angle_speed_sub_name", "");
        this->declare_parameter("cancel_current_move_sub_name", "");
        this->declare_parameter("max_continuous_retries", 3);
        this->declare_parameter("occupied_tolerance", 0.6);
        this->declare_parameter("traffic_peak_time_threshold", 8.0);

        server_address_ = this->get_parameter("server_address").as_string();
        server_port_ = this->get_parameter("server_port").as_int();
        mark_points_csv_adress_ = this->get_parameter("mark_points_csv_adress").as_string();
        pub_chassis_status_info_topic_ = this->get_parameter("pub_chassis_status_info_topic").as_string();
        cloud_water_mark_point_topic_name_ = this->get_parameter("cloud_water_mark_point_topic_name").as_string();
        cloud_water_move_base_topic_ = this->get_parameter("cloud_water_move_base_topic").as_string();
        play_fixed_audio_pub_name_ = this->get_parameter("play_fixed_audio_pub_name").as_string();
        alarm_info_pub_name_ = this->get_parameter("alarm_info_pub_name").as_string();
        key_vel_move_base_topic_ = this->get_parameter("key_vel_move_base_topic").as_string();
        cloud_chassis_point_upadte_pub_name_ = this->get_parameter("cloud_chassis_point_upadte_pub_name").as_string();
        cloud_chassis_reposition_action_name_ = this->get_parameter("cloud_chassis_reposition_action_name").as_string();
        led_show_topic_name_ = this->get_parameter("led_show_topic_name").as_string();
        cloud_water_nav_target_srv_name_ = this->get_parameter("cloud_water_nav_target_srv_name").as_string();
        cloud_chassis_nav_action_name_ = this->get_parameter("cloud_chassis_nav_action_name").as_string();
        cloud_chassis_charge_action_name_ = this->get_parameter("cloud_chassis_charge_action_name").as_string();
        max_linear_speed_sub_name_ = this->get_parameter("max_linear_speed_sub_name").as_string();
        max_angle_speed_sub_name_ = this->get_parameter("max_angle_speed_sub_name").as_string();
        cancel_current_move_sub_name_ = this->get_parameter("cancel_current_move_sub_name").as_string();
        max_continuous_retries_ = this->get_parameter("max_continuous_retries").as_int();
        occupied_tolerance_ = this->get_parameter("occupied_tolerance").as_double();
        traffic_peak_time_threshold_ = this->get_parameter("traffic_peak_time_threshold").as_double();

        mark_points_data_hearder = {"location_name", "map_name", "x", "y", "z", "roll", "pitch", "yaw", "pose_name", "pose_type"};
        current_evl_control_mode_ = VEL_CONTROL_MODE::CLOUD_CONTROL;
        last_play_time_ = this->now();
    }

    void CloudWaterChassisNode::CreateSubAndPub()
    {
        cloud_chassis_status_pub_ = this->create_publisher<ymrobot_msgs::msg::CloudChassisStatus>(pub_chassis_status_info_topic_, 2);
        cloud_chassis_mark_point_upate_pub_ = this->create_publisher<ymrobot_msgs::msg::UpdateList>(cloud_chassis_point_upadte_pub_name_, 1);
        cloud_chassis_mark_point_pub_ = this->create_publisher<ymrobot_msgs::msg::CloudChassisMarkPointList>(cloud_water_mark_point_topic_name_, 2);
        play_fixed_audio_pub_ = this->create_publisher<std_msgs::msg::Int32>(play_fixed_audio_pub_name_, 1);
        alarm_info_pub_ = this->create_publisher<std_msgs::msg::String>(alarm_info_pub_name_, 1);
        move_base_sub_ = this->create_subscription<ymrobot_msgs::msg::Movebase>(cloud_water_move_base_topic_, 1, std::bind(&CloudWaterChassisNode::MoveBaseCallback, this, std::placeholders::_1));
        key_vel_control_sub_ = this->create_subscription<geometry_msgs::msg::Twist>(key_vel_move_base_topic_, 1, std::bind(&CloudWaterChassisNode::KeyControlSubCallback, this, std::placeholders::_1));
        led_show_sub_ = this->create_subscription<ymrobot_msgs::msg::LedShow>(led_show_topic_name_, 1, std::bind(&CloudWaterChassisNode::LedShowSubCallback, this, std::placeholders::_1));
        max_linear_speed_sub_ = this->create_subscription<std_msgs::msg::Float64>(max_linear_speed_sub_name_, 1, std::bind(&CloudWaterChassisNode::MaxLinearSpeedSubCallback, this, std::placeholders::_1));
        max_angle_speed_sub_ = this->create_subscription<std_msgs::msg::Float64>(max_angle_speed_sub_name_, 1, std::bind(&CloudWaterChassisNode::MaxAngularSpeedSubCallback, this, std::placeholders::_1));
        cancel_current_move_sub_ = this->create_subscription<std_msgs::msg::String>(cancel_current_move_sub_name_, 1, std::bind(&CloudWaterChassisNode::CancelMoveSubCallback, this, std::placeholders::_1));
        nav_target_srv_ = this->create_service<ymrobot_msgs::srv::CLoudNav>(cloud_water_nav_target_srv_name_, std::bind(&CloudWaterChassisNode::NavTargetServiceCallback, this, std::placeholders::_1, std::placeholders::_2));

        cloud_chassis_nav_action_ = rclcpp_action::create_server<ymrobot_msgs::action::CloudChassisNav>(
            this,
            cloud_chassis_nav_action_name_,
            std::bind(&CloudWaterChassisNode::ChassisNavHandleGoal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&CloudWaterChassisNode::ChassisNavHandleCancel, this, std::placeholders::_1),
            std::bind(&CloudWaterChassisNode::ChassisNavHandleAccepted, this, std::placeholders::_1));

        cloud_chassis_charge_action_ = rclcpp_action::create_server<ymrobot_msgs::action::CloudChassisCharge>(
            this,
            cloud_chassis_charge_action_name_,
            std::bind(&CloudWaterChassisNode::ChassisChargeHandleGoal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&CloudWaterChassisNode::ChassisChargeHandleCancel, this, std::placeholders::_1),
            std::bind(&CloudWaterChassisNode::ChassisChargeHandleAccepted, this, std::placeholders::_1));

        cloud_chassis_reposition_action_ = rclcpp_action::create_server<ymrobot_msgs::action::CloudChassisNavReposition>(
            this,
            cloud_chassis_reposition_action_name_,
            std::bind(&CloudWaterChassisNode::ChassisNavRepositionHandleGoal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&CloudWaterChassisNode::ChassisNavRepositionHandleCancel, this, std::placeholders::_1),
            std::bind(&CloudWaterChassisNode::ChassisNavRepositionHandleAccepted, this, std::placeholders::_1));
    }

    void CloudWaterChassisNode::ChassisTaskProcessThread()
    {
        rclcpp::WallRate loop_rate(CHASSIS_SEND_MSG_HZ);
        while (rclcpp::ok())
        {
            // 优先处理事件驱动消息
            std::string message;
            while (cloud_chassis_task_queue_.TryPop(message))
            {
                SendTcpMessage(message);
                message.clear();
            }
            loop_rate.sleep();
        }
    }

    void CloudWaterChassisNode::ReceiveTcpMessageThread()
    {
        char buffer[4096] = {0};
        while (true)
        {
            if (cloud_chassis_status_ == CloudChassisRunStatus::DISCONNECT)
            {
                continue;
            }

            {
                // std::unique_lock<std::mutex> l2(tcp_socket_mutex_, std::try_to_lock);
                // if (!l2.owns_lock())
                // {
                //     RCLCPP_WARN(this->get_logger(), "无法获取锁，跳过本次接收");
                //     continue;
                // }

                // 接收消息
                int bytes_received = recv(tcp_socket_fd_, buffer, sizeof(buffer) - 1, 0);
                if (bytes_received <= 0)
                {
                    if (bytes_received < 0)
                    {
                        RCLCPP_ERROR(this->get_logger(), "接收消息失败，错误码: %d", errno);
                    }
                    else
                    {
                        RCLCPP_ERROR(this->get_logger(), "连接已关闭，重新连接中...");
                    }

                    try
                    {
                        ReconnectTcpClient();
                    }
                    catch (const std::exception &e)
                    {
                        RCLCPP_ERROR(this->get_logger(), "重新连接失败: %s", e.what());
                    }
                    continue;
                }

                buffer[bytes_received] = '\0';
                std::string received_msg(buffer);
                // std::cout << "收到底盘反馈消息: " << received_msg << std::endl;

                if (cloud_chassis_status_ == CloudChassisRunStatus::ACTIVATE)
                {
                    GetMarkerPoint(buffer, bytes_received);
                    memset(buffer, 0, sizeof(buffer)); // 清空接收缓冲区
                    continue;
                }

                if (json::accept(received_msg))
                {
                    try
                    {
                        ParseRobotMessage(json::parse(received_msg));
                    }
                    catch (const std::exception &e)
                    {
                        RCLCPP_ERROR(this->get_logger(), "解析机器人消息失败: %s", e.what());
                    }
                }
                else
                {
                    RCLCPP_WARN(this->get_logger(), "接收到的消息不是有效的JSON格式");
                }
            }
        }
    }

    void CloudWaterChassisNode::CloudChassisRunStatusThread()
    {
        while (rclcpp::ok())
        {
            switch (cloud_chassis_status_)
            {
            case CloudChassisRunStatus::DISCONNECT:
            {
                break;
            }
            case CloudChassisRunStatus::ACTIVATE:
            {
                if (is_first_connect_success_.load())
                {
                    SendResquestMarkerPoint();
                    // SendResquestSelfDiagnosis();
                    is_first_connect_success_.store(false);
                }
                break;
            }
            case CloudChassisRunStatus::INIT:
            {
                SendRequestChassisStatus();
                cloud_chassis_status_ = CloudChassisRunStatus::IDLE;
                break;
            }
            case CloudChassisRunStatus::IDLE:
            {
                break;
            }
            case CloudChassisRunStatus::RUNNING:
            {
                break;
            }
            case CloudChassisRunStatus::FAULT:
            {
                break;
            }
            case CloudChassisRunStatus::CHARGING:
            {
                break;
            }
            default:
                break;
            }
        }
    }

    void CloudWaterChassisNode::SendTcpMessage(const std::string &msg)
    {
        if (msg.empty())
        {
            RCLCPP_INFO(this->get_logger(), "SendTcpMessage msg is empty");
            return;
        }

        try
        {
            // std::lock_guard<std::mutex> l2(tcp_socket_mutex_);
            if (tcp_socket_fd_ < 0)
            {
                RCLCPP_ERROR(this->get_logger(), "Socket is not connected");
                return;
            }
            RCLCPP_INFO(this->get_logger(), "发送消息: %s", msg.c_str());

            if (send(tcp_socket_fd_, msg.c_str(), msg.size(), 0) < 0)
            {
                RCLCPP_ERROR(this->get_logger(), "Failed to send message");
                cloud_chassis_status_ = CloudChassisRunStatus::DISCONNECT;
                ReconnectTcpClient();
            }
        }
        catch (const std::exception &e)
        {
            RCLCPP_ERROR(this->get_logger(), "Unexpected error: %s", e.what());
        }
    }

    void CloudWaterChassisNode::PublishCloudChassisRobotStatus(const RobotStatusInfo &robot_status_info)
    {
        auto robot_status_msg = ymrobot_msgs::msg::CloudChassisStatus();

        robot_status_msg.charge_state = robot_status_info.charge_state;
        robot_status_msg.soft_estop_state = robot_status_info.soft_estop_state;
        robot_status_msg.hard_estop_state = robot_status_info.hard_estop_state;
        robot_status_msg.estop_state = robot_status_info.estop_state;
        robot_status_msg.power_percent = robot_status_info.power_percent;
        robot_status_msg.x = robot_status_info.current_pose_x;
        robot_status_msg.y = robot_status_info.current_pose_y;
        robot_status_msg.yaw = robot_status_info.current_pose_theta;
        robot_status_msg.current_floor = robot_status_info.current_floor;
        robot_status_msg.move_target = robot_status_info.move_target;

        cloud_chassis_status_pub_->publish(robot_status_msg);
    }

    void CloudWaterChassisNode::MoveBaseCallback(const ymrobot_msgs::msg::Movebase::SharedPtr msg)
    {
        InvokeMoveControl(msg->speed, msg->angle);
    }

    void CloudWaterChassisNode::KeyControlSubCallback(const geometry_msgs::msg::Twist::SharedPtr msg)
    {
        float speed_val = msg->linear.x;
        float angle = msg->angular.z;
        static float last_speed = 0.0;
        static float last_angle = 0.0;
        if(fabs(speed_val - last_speed) < 1e-6 && fabs(angle - last_angle) < 1e-6)
        {
            return;
        }
        InvokeKeyControl(speed_val, angle);
    }

    void CloudWaterChassisNode::LedShowSubCallback(const ymrobot_msgs::msg::LedShow::SharedPtr msg)
    {
        int color_r = msg->color_r;
        int color_g = msg->color_g;
        int color_b = msg->color_b;
        InvokeLedShow(color_r, color_g, color_b);
    }

    void CloudWaterChassisNode::MaxLinearSpeedSubCallback(const std_msgs::msg::Float64 msg)
    {
        RCLCPP_INFO(this->get_logger(), "设置最大线速度max_linear_speed:%f", msg);
        double max_linear_speed = msg.data;
        InvokeSetLinearSpeed(max_linear_speed);
    }

    void CloudWaterChassisNode::MaxAngularSpeedSubCallback(const std_msgs::msg::Float64 msg)
    {
        RCLCPP_INFO(this->get_logger(), "设置最大角速度max_angular_speed:%f", msg);
        double max_angular_speed = msg.data; //
        InvokeSetAngularSpeed(max_angular_speed);
    }

    void CloudWaterChassisNode::ControlModeSubCallback(const std_msgs::msg::Bool::SharedPtr msg)
    {
    }

    void CloudWaterChassisNode::CancelMoveSubCallback(const std_msgs::msg::String::SharedPtr msg)
    {
        if (msg->data != "cancel")
        {
            return;
        }
        RCLCPP_INFO(this->get_logger(), "收到取消移动命令: %s", msg->data.c_str());
        InvokeCancelMove(); // 调用取消移动的接口
    }

    void CloudWaterChassisNode::SoftEmergencyStopSubCallback(const std_msgs::msg::Bool::SharedPtr msg)
    {
        bool soft_emergency_stop = msg->data;
        if (soft_emergency_stop)
        {
            RCLCPP_INFO(this->get_logger(), "启用软急停");
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "关闭软急停");
        }
        InvokeSoftEmergencyStop(soft_emergency_stop);
    }

    void CloudWaterChassisNode::ParseTcpMessage(const std::string &msg)
    {
        json json_msg = json::parse(msg);
    }

    void CloudWaterChassisNode::AddTaskMessages(const std::string &msg)
    {
        cloud_chassis_task_queue_.Push(msg);
    }

    void CloudWaterChassisNode::SendRequestChassisStatus()
    {
        std::string request_robot_status = "/api/request_data?topic=robot_status&frequency=1";
        AddTaskMessages(request_robot_status);
    }

    void CloudWaterChassisNode::SendResquestMarkerPoint()
    {
        std::string request_robot_status = "/api/markers/query_list";
        AddTaskMessages(request_robot_status);
        std::cout << "发送标记点位详细信息" << std::endl;
    }

    void CloudWaterChassisNode::SendResquestSelfDiagnosis()
    {
        std::string request_robot_self_diagnosis = "/api/diagnosis/get_result";
        AddTaskMessages(request_robot_self_diagnosis);
        std::cout << "发送底盘硬件自诊断" << std::endl;
    }

    void CloudWaterChassisNode::GetMarkerPoint(const char *data, size_t length)
    {
        get_mark_point_buffer_.append(data, length);
        size_t pos = get_mark_point_buffer_.find('\n');
        ymrobot_msgs::msg::CloudChassisMarkPoint mark_point_msg;
        auto mark_point_msg_list = ymrobot_msgs::msg::CloudChassisMarkPointList();
        std::vector<std::vector<std::string>> csv_data;

        if (pos == std::string::npos)
        {
            std::cout << "get_mark_point_buffer_ not find \n"
                      << std::endl;
            return;
        }

        packets_.push_back(get_mark_point_buffer_.substr(0, pos));
        get_mark_point_buffer_.erase(0, pos + 1);

        json json_msg = json::parse(packets_[0]);
        std::cout << "粘包处理好了，数据是： " << packets_[0] << std::endl;
        for (auto &[key, value] : json_msg["results"].items())
        {
            std::vector<std::string> row;
            row.emplace_back("云幕");
            row.emplace_back(std::to_string(value["floor"].get<int>()));                    // 地图名称  所属的楼层
            row.emplace_back(std::to_string(value["pose"]["position"]["x"].get<double>())); // x
            row.emplace_back(std::to_string(value["pose"]["position"]["y"].get<double>())); // y
            row.emplace_back(std::to_string(value["pose"]["position"]["z"].get<double>())); // z
            row.emplace_back(std::to_string(0.0));
            row.emplace_back(std::to_string(0.0));
            row.emplace_back(std::to_string(0.0));
            row.emplace_back(value["marker_name"].get<std::string>()); // 点位名称
            row.emplace_back(std::to_string(value["key"].get<int>())); // 描述-- 点位类型

            csv_data.push_back(row);
        }

        sqlManager.WriteCSVWithHeaders(mark_points_csv_adress_, mark_points_data_hearder, csv_data, false); // 写入点位数据到csv文件
        auto update_mark_pose = ymrobot_msgs::msg::UpdateList();
        update_mark_pose.code = ymrobot_msgs::msg::UpdateList::ALL_ACTION;
        cloud_chassis_mark_point_upate_pub_->publish(update_mark_pose); // 发布更新点位通知
        std::cout << "获取点位列表成功,发送点位更新topic" << std::endl;
        cloud_chassis_status_ = CloudChassisRunStatus::INIT;
    }

    void CloudWaterChassisNode::NavTargetServiceCallback(const std::shared_ptr<ymrobot_msgs::srv::CLoudNav::Request> request, std::shared_ptr<ymrobot_msgs::srv::CLoudNav::Response> response)
    {
        if (request == nullptr)
        {
            response->success = false;
            response->message = "移动请求命令不正确，请检查";
            return;
        }

        int nav_mode = request->nav_mode;
        auto nav_target_name = request->nav_target_name;

        if (nav_mode == 0)
        {
            RCLCPP_INFO(this->get_logger(), "点位名导航模式");
            InvokeNavName(nav_target_name, "111");
        }
        else if (nav_mode == 1)
        {
            RCLCPP_INFO(this->get_logger(), "点位导航模式");
            InvokeNav(request->nav_target_x, request->nav_target_y, request->nav_target_yaw);
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "未知导航模式");
        }

        rclcpp::Rate loop_rate(CHASSIS_NAV_RESULST_HZ);
        while (rclcpp::ok())
        {
            // std::lock_guard<std::mutex> l1(robot_status_info_mutex_); // 嘿嘿
            {
                std::shared_lock<std::shared_mutex> l1(robot_status_info_mutex_);
                if (robot_status_info_.move_target == nav_target_name && robot_status_info_.running_status == "idle")
                {
                    if (robot_status_info_.move_status == "succeeded")
                    {
                        response->success = true;
                        response->message = "导航成功";
                        return;
                    }
                    else if (robot_status_info_.move_status == "failed")
                    {
                        response->success = false;
                        response->message = "导航失败";
                        return;
                    }
                    else if (robot_status_info_.move_status == "canceled")
                    {
                        response->success = true;
                        response->message = "导航取消";
                    }
                }
            }
            loop_rate.sleep();
        }
    }

    void CloudWaterChassisNode::EnableNearPointExplationSubCallback(const std_msgs::msg::Bool::SharedPtr msg)
    {
        RCLCPP_INFO(this->get_logger(), "开启或者关闭就近点讲解功能");
        if (msg->data)
        {
            RCLCPP_INFO(this->get_logger(), "开启就近点讲解功能");
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "关闭就近点讲解功能");
        }
        is_open_near_explation_ = msg->data;
        SetYaml(yaml_file_, "is_open_pedestrian_detection", is_open_near_explation_);
    }

    void CloudWaterChassisNode::ExplainTheThresholdNearbyPointSubCallback(const std_msgs::msg::Float64::SharedPtr msg)
    {
        RCLCPP_INFO(this->get_logger(), "设置就近点讲解阈值");
        occupied_tolerance_ = msg->data;
        RCLCPP_INFO(this->get_logger(), "就近点讲解阈值为：%f", occupied_tolerance_);
        SetYaml(yaml_file_, "occupied_tolerance", occupied_tolerance_);
    }

    rclcpp_action::GoalResponse CloudWaterChassisNode::ChassisNavHandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::CloudChassisNav::Goal> goal)
    {
        RCLCPP_INFO(this->get_logger(), "收到单点导航请求");
        (void)uuid;
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    void CloudWaterChassisNode::ChassisNavHandleAccepted(const std::shared_ptr<GoalHandleChassisNav> goal_handle)
    {
        std::thread{std::bind(&CloudWaterChassisNode::ChassisNavExecute, this, goal_handle)}.detach();
    }

    rclcpp_action::CancelResponse CloudWaterChassisNode::ChassisNavHandleCancel(const std::shared_ptr<GoalHandleChassisNav> goal_handle)
    {
        return rclcpp_action::CancelResponse();
    }

    void CloudWaterChassisNode::ChassisNavExecute(const std::shared_ptr<GoalHandleChassisNav> goal_handle)
    {
        auto goal = goal_handle->get_goal();
        auto result = std::make_shared<ymrobot_msgs::action::CloudChassisNav::Result>();
        auto nav_mode = goal->nav_mode;
        is_open_near_explation_ = goal->is_open_near_explation;
        SetYaml(yaml_file_, "is_open_pedestrian_detection", is_open_near_explation_);
        occupied_tolerance_ = goal->occupied_tolerance;
        SetYaml(yaml_file_, "occupied_tolerance", occupied_tolerance_);
        std::cout << "233333" << std::endl;

        if (nav_mode == 0)
        {
            RCLCPP_INFO(this->get_logger(), "点位名导航模式");
            InvokeNavName(goal->nav_target_name, "111");
        }
        else if (nav_mode == 1)
        {
            RCLCPP_INFO(this->get_logger(), "点位坐标导航模式");
            InvokeNav(goal->nav_target_x, goal->nav_target_y, goal->nav_target_yaw);
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "未知导航模式");
        }
        RCLCPP_INFO(this->get_logger(), "监听云迹底盘导航是否成功");
        rclcpp::Rate loop_rate(CHASSIS_NAV_RESULST_HZ);
        int flag = 3;
        while (rclcpp::ok())
        {
            if (goal_handle->is_canceling())
            {
                RCLCPP_WARN(this->get_logger(), "移动任务被取消");
                result->success = false;
                result->message = "移动任务被取消";
                goal_handle->canceled(result);
                return;
            }

            // std::lock_guard<std::mutex> l1(robot_status_info_mutex_); // 嘿嘿 bug
            {
                std::shared_lock<std::shared_mutex> l1(robot_status_info_mutex_);
                if (robot_status_info_.move_target == goal->nav_target_name && robot_status_info_.running_status == "idle")
                {
                    if (robot_status_info_.move_status == "succeeded")
                    {
                        result->success = true;
                        result->message = "导航成功";
                        goal_handle->succeed(result);
                        std::cout << "导航成功" << std::endl;
                        return;
                    }
                    else if (robot_status_info_.move_status == "failed")
                    {
                        result->success = false;
                        result->message = "导航失败";
                        goal_handle->abort(result);
                        std::cout << "导航失败" << std::endl;
                        AlarmInfo("机器人自主导航失败,请人工干预");
                        return;
                    }
                    else if (robot_status_info_.move_status == "canceled")
                    {
                        result->success = false;
                        result->message = "导航任务被取消了";
                        goal_handle->abort(result);
                        return;
                    }
                }
            }
            loop_rate.sleep();
        }
    }

    rclcpp_action::GoalResponse CloudWaterChassisNode::ChassisChargeHandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::CloudChassisCharge::Goal> goal)
    {
        RCLCPP_INFO(this->get_logger(), "收到执行充电动作请求");
        (void)uuid;
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    void CloudWaterChassisNode::ChassisChargeHandleAccepted(const std::shared_ptr<GoalHandleChassisCharge> goal_handle)
    {
        std::thread{std::bind(&CloudWaterChassisNode::ChassisChargeExecute, this, goal_handle)}.detach();
    }

    rclcpp_action::CancelResponse CloudWaterChassisNode::ChassisChargeHandleCancel(const std::shared_ptr<GoalHandleChassisCharge> goal_handle)
    {
        RCLCPP_INFO(this->get_logger(), "收到取消充电动作请求");
        (void)goal_handle;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void CloudWaterChassisNode::ChassisChargeExecute(const std::shared_ptr<GoalHandleChassisCharge> goal_handle)
    {
        auto goal = goal_handle->get_goal();
        auto result = std::make_shared<ymrobot_msgs::action::CloudChassisCharge::Result>();
        auto feedback = std::make_shared<ymrobot_msgs::action::CloudChassisCharge::Feedback>();

        // std::string charge_station_name = goal->charge_point_name;
        // InvokeNavName(charge_station_name, "111");
        std::string charge_str = GetCurrentFloorCharge();
        InvokeNavName(charge_str, "111");

        // rclcpp::Rate loop_rate(1);
        bool is_charge_start = true;
        while (rclcpp::ok())
        {
            if (goal_handle->is_canceling())
            {
                RCLCPP_WARN(this->get_logger(), "充电被取消");
                result->success = false;
                result->message = "充电被取消";
                goal_handle->canceled(result);
                return;
            }
            if (robot_status_info_.running_status == "idle" && is_charge_start)
            {
                // RCLCPP_INFO(this->get_logger(), "未执行充电动作");
                continue;
            }
            is_charge_start = false;

            {
                auto fixed_audio_msg = std_msgs::msg::Int32();
                fixed_audio_msg.data = 1;                        // 播放--“充电中”
                play_fixed_audio_pub_->publish(fixed_audio_msg); // 发布请求播放--“充电中”
            }
            

            {
                std::shared_lock<std::shared_mutex> l1(robot_status_info_mutex_);
                if (robot_status_info_.charge_state)
                {
                    RCLCPP_INFO(this->get_logger(), "开始充电");
                    result->success = true;
                    result->message = "开始充电";
                    goal_handle->succeed(result);
                    return;
                }
                else if (!robot_status_info_.charge_state && (robot_status_info_.move_status == "failed"))
                {
                    RCLCPP_INFO(this->get_logger(), "自主充电失败");
                    result->success = false;
                    result->message = "充电失败";
                    goal_handle->abort(result);
                    AlarmInfo("回充失败,请检查机器人，并断电后，推动机器人到充电桩");
                    return;
                }
                else
                {
                    RCLCPP_INFO(this->get_logger(), "人为干预，导致充电失败");
                    result->success = false;
                    result->message = "充电失败";
                    goal_handle->abort(result);
                    // AlarmInfo("回充失败,请检查机器人，并断电后，推动机器人到充电桩");
                    return;
                }
            }

            // RCLCPP_INFO(this->get_logger(), "开始充电");
            // result->success = true;
            // result->message = "开始充电";
            // goal_handle->succeed(result);
            // return;
        }
    }

    rclcpp_action::GoalResponse CloudWaterChassisNode::ChassisNavRepositionHandleGoal(const rclcpp_action::GoalUUID &uuid, std::shared_ptr<const ymrobot_msgs::action::CloudChassisNavReposition::Goal> goal)
    {
        RCLCPP_INFO(this->get_logger(), "收到机器重定位动作请求");
        (void)uuid;
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    void CloudWaterChassisNode::ChassisNavRepositionHandleAccepted(const std::shared_ptr<GoalHandleChassisNavReposition> goal_handle)
    {
        std::thread{std::bind(&CloudWaterChassisNode::ChassisNavRepositionExecute, this, goal_handle)}.detach();
    }

    rclcpp_action::CancelResponse CloudWaterChassisNode::ChassisNavRepositionHandleCancel(const std::shared_ptr<GoalHandleChassisNavReposition> goal_handle)
    {
        RCLCPP_INFO(this->get_logger(), "收到取消机器重定位动作请求");
        (void)goal_handle;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void CloudWaterChassisNode::ChassisNavRepositionExecute(const std::shared_ptr<GoalHandleChassisNavReposition> goal_handle)
    {
        auto goal = goal_handle->get_goal();
        auto result = std::make_shared<ymrobot_msgs::action::CloudChassisNavReposition::Result>();

        auto relocation_str_name = goal->reposition_pose_name;
        InvokeReposition(relocation_str_name);
        result->success = true;
        result->message = "机器重定位成功";
        goal_handle->succeed(result);
    }

    void CloudWaterChassisNode::InvokeNav(const double &x, const double &y, const double &yaw)
    {
        std::string cmd = "/api/move?location=";
        std::string send_msg = cmd + std::to_string(x) + "," + std::to_string(y) + "," + "," + std::to_string(yaw);
        AddTaskMessages(send_msg);
    }

    void CloudWaterChassisNode::InvokeNavName(const std::string &msg, const std::string &uuid)
    {
        RCLCPP_INFO(this->get_logger(), "导航到: %s", msg.c_str());
        std::string cmd = "/api/move?marker=";
        std::string send_msg = cmd + msg + "&max_continuous_retries=" + std::to_string(max_continuous_retries_);
        if (is_open_near_explation_)
        {
            send_msg = send_msg + "&occupied_tolerance=" + std::to_string(occupied_tolerance_);
        }
        else
        {
            double occupied_tolerance = 0.3;
            send_msg = send_msg + "&occupied_tolerance=" + std::to_string(occupied_tolerance);
        }
        AddTaskMessages(send_msg);
    }

    void CloudWaterChassisNode::InvokeMoveControl(const double &vel, const double &angle)
    {
        std::string cmd = "/api/joy_control?";
        std::string vel_msg = "&linear_velocity=" + std::to_string(vel);
        std::string angle_msg = "angular_velocity=" + std::to_string(angle);
        std::string send_msg = cmd + vel_msg + angle_msg;
        AddTaskMessages(send_msg);
    }

    void CloudWaterChassisNode::InvokeKeyControl(const double &vel, const double &angle)
    {
        std::string cmd = "/api/joy_control?";
        std::string vel_msg = "&linear_velocity=" + std::to_string(vel);
        std::string angle_msg = "angular_velocity=" + std::to_string(angle);
        std::string send_msg = cmd + angle_msg + vel_msg;
        AddTaskMessages(send_msg);
    }

    void CloudWaterChassisNode::InvokeLedShow(const double &r, const double &g, const double &b)
    {
        std::string cmd = "/api/LED/set_color";
        std::string color_msg = "?r=" + std::to_string(r) + "&g=" + std::to_string(g) + "&b" + std::to_string(b);
        std::string send_msg = cmd + color_msg;
        AddTaskMessages(send_msg);
    }

    void CloudWaterChassisNode::InvokeSetLinearSpeed(const double &max_speed_linear)
    {
        std::string cmd = "/api/set_params?max_speed_linear=";
        std::string send_msg = cmd + std::to_string(max_speed_linear);
        AddTaskMessages(send_msg);
    }

    void CloudWaterChassisNode::InvokeSetAngularSpeed(const double &max_speed_angular)
    {
        std::string cmd = "/api/set_params?max_speed_angular=";
        std::string send_msg = cmd + std::to_string(max_speed_angular);
        AddTaskMessages(send_msg);
    }

    void CloudWaterChassisNode::InvokeChargeAction(const std::string &action)
    {
        if (action == "charge")
        {
            RCLCPP_INFO(this->get_logger(), "开始执行回充任务");
            std::string charge_str = GetCurrentFloorCharge();
            InvokeNavName(charge_str, "111");
        }
    }

    void CloudWaterChassisNode::InvokeCancelMove()
    {
        std::string cmd = "/api/move/cancel";
        AddTaskMessages(cmd);
    }

    void CloudWaterChassisNode::InvokeReposition(const std::string &reposition_name)
    {
        std::string send_msg = "/api/position_adjust?marker=";
        send_msg += reposition_name;
        SendTcpMessage(send_msg);
    }

    void CloudWaterChassisNode::InvokeSoftEmergencyStop(const bool &stop_flag)
    {
        std::string send_msg = "/api/estop?flag=";
        send_msg += stop_flag ? "true" : "false";
        SendTcpMessage(send_msg);
    }

    void CloudWaterChassisNode::RequestMapListInfo()
    {
        std::string send_msg = "/api/map/list_info";
        SendTcpMessage(send_msg);
    }

    void CloudWaterChassisNode::AlarmInfo(const std::string &msg)
    {
        RCLCPP_INFO(this->get_logger(), "发布报警信息: %s", msg.c_str());
        auto alarm_msg = std_msgs::msg::String();
        alarm_msg.data = msg;
        alarm_info_pub_->publish(alarm_msg);
    }

    void CloudWaterChassisNode::ParseRobotStatusMessages(const json &msg)
    {
        std::unique_lock<std::shared_mutex> l1(robot_status_info_mutex_);
        {
            robot_status_info_.move_target = msg["move_target"].get<std::string>();
            robot_status_info_.move_status = msg["move_status"].get<std::string>();
            robot_status_info_.running_status = msg["running_status"].get<std::string>();
            robot_status_info_.move_retry_times = msg["move_retry_times"].get<int>();
            robot_status_info_.charge_state = msg["charge_state"].get<bool>();
            robot_status_info_.soft_estop_state = msg["soft_estop_state"].get<bool>();
            robot_status_info_.hard_estop_state = msg["hard_estop_state"].get<bool>();
            robot_status_info_.estop_state = msg["estop_state"].get<bool>();
            robot_status_info_.power_percent = msg["power_percent"].get<int>();
            robot_status_info_.current_pose_x = msg["current_pose"]["x"].get<double>();
            robot_status_info_.current_pose_y = msg["current_pose"]["y"].get<double>();
            robot_status_info_.current_pose_theta = msg["current_pose"]["theta"].get<double>();
            robot_status_info_.current_floor = msg["current_floor"].get<int>();
            robot_status_info_.chargepile_id = msg["chargepile_id"].get<std::string>();
            robot_status_info_.error_code = msg["error_code"].get<std::string>();

            PublishCloudChassisRobotStatus(robot_status_info_);
        }
    }

    void CloudWaterChassisNode::ParseRobotMessage(const json &msg)
    {
        std::string msg_type = msg["type"].get<std::string>();
        if (msg_type == "callback")
        {
            auto msg_topic = msg["topic"].get<std::string>();
            if (msg_topic == "robot_status")
            {
                ParseRobotStatusMessages(msg["results"]);
            }
        }
        else if (msg_type == "notification")
        {
            if (msg["code"] == "01200")
            {
                rclcpp::Time current_time = this->now();
                auto diff = (current_time - last_play_time_).seconds();
                std::cout << "让一让,误差时间: " << diff << std::endl;
                // if (diff > traffic_peak_time_threshold_)
                // {
                //     last_play_time_ = current_time; // 更新上一次播放录音的时间
                //     return;
                // }
                RCLCPP_INFO(this->get_logger(), "由于机器人交通繁忙,请求播放--“让一让”录音");
                auto fixed_audio_msg = std_msgs::msg::Int32();
                fixed_audio_msg.data = 0;   // 播放--“让一让”
                play_fixed_audio_pub_->publish(fixed_audio_msg); // 发布请求播放--“让一让”录音
                last_play_time_ = current_time;                  // 更新上一次播放录音的时间
            }
        }
    }

    std::string CloudWaterChassisNode::GetCurrentFloorCharge()
    {
        std::string charge_point = "";
        std::string current_floor_charge = std::to_string(robot_status_info_.current_floor);
        auto result_list = sqlManager.FindRowsByColumn(mark_points_csv_adress_, 9, "11");
        if (result_list.size() == 0)
        {
            RCLCPP_WARN(this->get_logger(), "未找到充电点信息");
            return charge_point;
        }

        charge_point = result_list[0][0];
        for (auto result : result_list)
        {
            if (result[1] == current_floor_charge)
            {
                charge_point = result[8];
            }
        }

        RCLCPP_INFO(this->get_logger(), "当前楼层充电点:%s", charge_point.c_str());
        return charge_point;
    }

    void CloudWaterChassisNode::PubDetectedPerson()
    {
        auto detected_person_msg = std_msgs::msg::Bool();
        detected_person_msg.data = true;
        publish_detected_person_pub_->publish(detected_person_msg);
    }

    template <typename T>
    void CloudWaterChassisNode::SetYaml(const std::string &yaml_file_path, const std::string &parameter_name, const T &parameter_value)
    {
        try
        {
            YAML::Node config = YAML::LoadFile(yaml_file_path);
            if (config["cloud_water_chassis_node"])
            {
                // 直接修改 config，不需要引用
                config["cloud_water_chassis_node"][parameter_name] = parameter_value;
            }
            else
            {
                RCLCPP_ERROR(this->get_logger(), "Key 'robot' not found in YAML file.");
            }
            std::ofstream fout(yaml_file_path);
            fout << config;
            fout.close();
        }
        catch (const YAML::Exception &e)
        {
            RCLCPP_ERROR(this->get_logger(), "Failed to parse YAML file: %s", e.what());
        }
    }
}

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<ymrobot::CloudWaterChassisNode>());
    rclcpp::shutdown();
    return 0;
}