#include "task_guidance.hpp"

namespace ymrobot
{
    TaskGuidance::TaskGuidance() : Node("task_guidance")
    {
        Init();
    }

    void TaskGuidance::Init()
    {
        InitParams();
        parent = rclcpp::Node::make_shared("test_node");
        // InitDataBase();
        InitBehaviorTree();
        CreatePubService();
    }

    void TaskGuidance::InitParams()
    {
        this->declare_parameter("task_topic", "");
        this->declare_parameter("task_states_feedback_topic", "");
        this->declare_parameter("is_used_tree", false);
        this->declare_parameter("maps_dir", "");
        this->declare_parameter("slam_task_srv_name", "");
        this->declare_parameter("save_pcd_srv_name", "");
        this->declare_parameter("save_pgm_srv_name", "");
        this->declare_parameter("relocalizer_task_srv_name", "");
        this->declare_parameter("re_pcd_srv_name", "");
        this->declare_parameter("plugin_lib_names", std::vector<std::string>());
        this->declare_parameter("default_bt_xml_filename", "");
        this->declare_parameter("timeout", 100);
        this->declare_parameter("dot_point_update_topic", "");
        this->declare_parameter("cancel_current_task_pub_name", "");

        task_topic_ = this->get_parameter("task_topic").as_string();
        task_states_feedback_topic_ = this->get_parameter("task_states_feedback_topic").as_string();
        is_used_tree_ = this->get_parameter("is_used_tree").as_bool();
        maps_dir_ = this->get_parameter("maps_dir").as_string();
        slam_task_srv_name_ = this->get_parameter("slam_task_srv_name").as_string();
        save_pcd_srv_name_ = this->get_parameter("save_pcd_srv_name").as_string();
        save_pgm_srv_name_ = this->get_parameter("save_pgm_srv_name").as_string();
        relocalizer_task_srv_name_ = this->get_parameter("relocalizer_task_srv_name").as_string();
        re_pcd_srv_name_ = this->get_parameter("re_pcd_srv_name").as_string();
        default_bt_xml_filename_ = this->get_parameter("default_bt_xml_filename").as_string();
        plugin_lib_names_ = this->get_parameter("plugin_lib_names").as_string_array();
        timeout_ = this->get_parameter("timeout").as_int();
        dot_point_update_topic_ = this->get_parameter("dot_point_update_topic").as_string();
        cancel_current_task_pub_name_ = this->get_parameter("cancel_current_task_pub_name").as_string();

        if (is_used_tree_)
        {
            RCLCPP_INFO(this->get_logger(), "采用行为树方式");
        }
        else
        {
            RCLCPP_INFO(this->get_logger(), "采用命令方式");
        }
    }

    void TaskGuidance::InitDataBase()
    {
    }

    void TaskGuidance::InitBehaviorTree()
    {
        std::cout << "初始化行为树" << std::endl;
        default_server_timeout_ = bt_loop_duration_ = std::chrono::milliseconds(timeout_);
        bt_ = std::make_unique<nav2_behavior_tree::BehaviorTreeEngine>(plugin_lib_names_);
        blackboard_ = BT::Blackboard::create();
        blackboard_->set<rclcpp::Node::SharedPtr>("node", parent);                                                // NOLINT
        blackboard_->set<std::chrono::milliseconds>("server_timeout", default_server_timeout_);                   // NOLINT
        blackboard_->set<std::chrono::milliseconds>("bt_loop_duration", bt_loop_duration_);                       // NOLINT
        blackboard_->set<std::chrono::milliseconds>("wait_for_service_timeout", std::chrono::milliseconds(5000)); // 设置默认超时时间
        LoadBehaviorTree(default_bt_xml_filename_);
        std::cout << "初始化行为树完成" << std::endl;
    }

    void TaskGuidance::CreatePubService()
    {
        task_sub_ = this->create_subscription<ymrobot_msgs::msg::Task>(task_topic_, 10, std::bind(&TaskGuidance::TaskSubCallback, this, std::placeholders::_1)); // 清扫动作任务执行

        task_state_pub_ = this->create_publisher<ymrobot_msgs::msg::TaskStatus>(task_states_feedback_topic_, 10);
        map_mode_pub_ = this->create_publisher<std_msgs::msg::UInt8>("map_mode", 1);
        dot_point_update_pub_ = this->create_publisher<ymrobot_msgs::msg::DotPointsList>(dot_point_update_topic_, 1); // 点位更新上传topic
        cancel_current_task_ = this->create_publisher<std_msgs::msg::String>(cancel_current_task_pub_name_, 1);       // 取消当前任务
        nav2_map_client_ = this->create_client<nav2_msgs::srv::LoadMap>("map_server/load_map");
        build_map_client_ = this->create_client<ymrobot_msgs::srv::SlamTaskManage>(slam_task_srv_name_);
        save_pcd_client_ = this->create_client<interface::srv::SaveMaps>(save_pcd_srv_name_);
        save_pgm_client_ = this->create_client<ymrobot_msgs::srv::MapTaskManage>(save_pgm_srv_name_);
        reloclizer_client_ = this->create_client<ymrobot_msgs::srv::SlamTaskManage>(relocalizer_task_srv_name_);
        reloclizer_pcd_client_ = this->create_client<interface::srv::Relocalize>(re_pcd_srv_name_);

        multipose_nav_client_ = rclcpp_action::create_client<nav2_msgs::action::NavigateThroughPoses>(this, "/navigate_through_poses"); // 创建多点导航客户端
        pose_nav_client_ = rclcpp_action::create_client<nav2_msgs::action::NavigateToPose>(this, "/navigate_to_pose");                  // 创建单点导航客户端
    }

    void TaskGuidance::TaskSubCallback(const ymrobot_msgs::msg::Task::SharedPtr msg)
    {
        if (msg == nullptr)
            return;

        ParseTask(msg);
    }

    void TaskGuidance::ParseTask(const ymrobot_msgs::msg::Task::SharedPtr msg)
    {
        RCLCPP_INFO(logger_, "接收到任务，对任务开始进行解析,一共 %d 条命令", msg->commands.size());
        RCLCPP_INFO(logger_, "接收到的任务ID为: %s", msg->task_id.c_str());
        auto msg_ = msg;
        if (msg_->commands.empty())
        {
            RCLCPP_ERROR(get_logger(), "No commands");
            return;
        }

        for (const auto &command : msg->commands)
        {

            switch (command.code)
            {
            case ymrobot_msgs::msg::Command::PAUSE:
            case ymrobot_msgs::msg::Command::WAIT:
            {
                RCLCPP_INFO(logger_, "任务为：暂停当前任务");
                PauseTask();
                break;
            }
            case ymrobot_msgs::msg::Command::RESUME:
            case ymrobot_msgs::msg::Command::FINISH_WAIT:
            {
                RCLCPP_INFO(logger_, "任务为：继续当前任务");
                ResumeTask();
                break;
            }
            case ymrobot_msgs::msg::Command::CANCLE:
            {
                RCLCPP_INFO(logger_, "任务为：取消当前任务");
                CancelTask();
                break;
            }
            case ymrobot_msgs::msg::Command::BUILD_MAP:
            case ymrobot_msgs::msg::Command::SAVE_MAP:
            case ymrobot_msgs::msg::Command::NAVIGATION:
            case ymrobot_msgs::msg::Command::CHARGE:
            case ymrobot_msgs::msg::Command::FINISH_CHARGE:
            case ymrobot_msgs::msg::Command::RELOCALIZE:
            case ymrobot_msgs::msg::Command::SETTING_PARAMETERS:
            case ymrobot_msgs::msg::Command::CLOUD_NAVIGATION_NAME:
            case ymrobot_msgs::msg::Command::CLOUD_MULIT_POINTS_NAVIGATION_NAME:
            case ymrobot_msgs::msg::Command::CLOUD_NAVIGATION:
            case ymrobot_msgs::msg::Command::CLOUD_MULIT_POINTS_NAVIGATION:
            case ymrobot_msgs::msg::Command::MULIT_FLOOR_NAVIGATION:
            case ymrobot_msgs::msg::Command::MULIT_POINTS_NAVIGATION:
            case ymrobot_msgs::msg::Command::PLACE_FIXED:
            case ymrobot_msgs::msg::Command::UPLOAD_VOICE_CONVERSATION_LOGS:
            case ymrobot_msgs::msg::Command::PHOTOGRAPH:
            case ymrobot_msgs::msg::Command::CAMERA:
            case ymrobot_msgs::msg::Command::PLAY_FIX_AUDIO:
            case ymrobot_msgs::msg::Command::TXT_2_AUDIO:
            case ymrobot_msgs::msg::Command::PLAY_ONLINE_AUDIO:
            case ymrobot_msgs::msg::Command::SYNTHETIC_AUDIO:
            {
                if (!IsCurrentTaskEmpty(*msg))
                    break;
                StartBehaviorTreeTask(current_task_);
                break;
            }
            case ymrobot_msgs::msg::Command::EXE_BEHAVIOR_TREE:
            {
                if (!IsCurrentTaskEmptyForMuiltCommands(*msg))
                    break;
                StartBehaviorTreeTask(current_task_);
                break;
            }
            default:
            {
                RCLCPP_WARN(logger_, "无法解析行为动作");
                break;
            }
            }
        }
    }

    void TaskGuidance::PauseTask()
    {
        {
            std::lock_guard<std::mutex> l(task_mutex_);
            if (!current_task_)
            {
                RCLCPP_WARN(logger_, "没有任务需要暂停");
                return;
            }
        }
        RCLCPP_INFO(logger_, "暂停任务 [%s]", current_task_->task_id.c_str());
        // is_pause_requested_.store(true);

        {
            // 发布暂停指令
            std_msgs::msg::Bool msg;
            msg.data = true;
            emergency_stop_machine_pub_->publish(msg);
        }
    }

    void TaskGuidance::ResumeTask()
    {
        ymrobot_msgs::msg::Task task;
        {
            std::lock_guard<std::mutex> l(task_mutex_);
            if (!current_task_)
            {
                RCLCPP_WARN(logger_, "没有任务需要继续");
                return;
            }
            task = *current_task_;
        }
        RCLCPP_INFO(logger_, "继续执行当前任务 [%s]", task.task_id.c_str());
        OnResumeCallback();
        ExecuteBehaviorTreeTask();
    }

    void TaskGuidance::CancelTask()
    {
        // 这是行为树的方法
        // {
        //     std::lock_guard<std::mutex> l(task_mutex_);
        //     if (!current_task_)
        //     {
        //         RCLCPP_WARN(logger_, "没有任务需要取消");
        //         return;
        //     }
        // }
        // RCLCPP_INFO(logger_, "取消一个任务 [%s]", current_task_->task_id.c_str());
        // if (is_pause_requested_.load())
        // {
        //     OnCompletionCallback(TaskResult::CANCELED);
        //     is_pause_requested_.store(false);
        //     std::lock_guard<std::mutex> l(task_mutex_);
        //     current_task_ = nullptr;
        //     return;
        // }
        // is_cancel_requested_.store(true);
        // return;

        // 下面是云迹底盘的做法
        {
            auto cancel_msg = std_msgs::msg::String();
            cancel_msg.data = "cancel";
            cancel_current_task_->publish(cancel_msg); // 取消当前任务 发送给云迹底盘节点

            {
                std::lock_guard<std::mutex> l(task_mutex_);
                if (!current_task_)
                {
                    RCLCPP_WARN(logger_, "没有任务需要取消");
                    return;
                }
            }
            RCLCPP_INFO(logger_, "取消一个任务 [%s]", current_task_->task_id.c_str());
            if (is_pause_requested_.load())
            {
                OnCompletionCallback(TaskResult::CANCELED);
                is_pause_requested_.store(false);
                std::lock_guard<std::mutex> l(task_mutex_);
                current_task_ = nullptr;
                return;
            }
            is_cancel_requested_.store(true);
            RCLCPP_INFO(logger_, "取消标志位置位");
            return;
        }
    }

    void TaskGuidance::Relocalize(const std::shared_ptr<ymrobot_msgs::msg::Task> &task)
    {
        RCLCPP_INFO(logger_, "开始重定位任务");

        auto command = task->commands[0];
        std::string map_file = command.params[0];
        std::string map_file_path = maps_dir_ + "/" + map_file + "/map.yaml";
        std::string pcd_file_path = maps_dir_ + "/" + map_file + "/map.pcd";

        RCLCPP_INFO(logger_, "开始加载地图任务");

        if (!IsMapFileExist(map_file_path))
        {
            RCLCPP_ERROR(logger_, "地图文件不存在. 地图文件地址为：%s", map_file_path.c_str());
            return;
        }

        if (!LoadMap(map_file_path))
        {
            RCLCPP_ERROR(logger_, "加载地图失败. 地图文件地址为：%s", map_file_path.c_str());
            return;
        }

        RCLCPP_INFO(logger_, "开始重定位任务");
        if (!StartLocalizerSlam(pcd_file_path))
        {
            RCLCPP_ERROR(logger_, "启动定位失败");
            return;
        }
    }

    void TaskGuidance::MapManager(const std::shared_ptr<ymrobot_msgs::msg::Task> &task)
    {
        auto command = task->commands[0];

        switch (command.code)
        {
        case ymrobot_msgs::msg::Command::BUILD_MAP:
        {
            RCLCPP_INFO(logger_, "选择建图模式");
            auto request = std::make_shared<ymrobot_msgs::srv::SlamTaskManage::Request>();
            auto slam_task_action = ymrobot_msgs::msg::SlamCommand();
            request->task = slam_task_action.mapping;
            request->action = slam_task_action.start;

            while (!build_map_client_->wait_for_service(std::chrono::seconds(1)))
            {
                if (!rclcpp::ok())
                {
                    RCLCPP_ERROR(logger_, "等待建图服务的过程中被打断...");
                }
                RCLCPP_INFO(logger_, "等待建图服务端上线中");
            }

            build_map_client_->async_send_request(request);
            break;
        }
        case ymrobot_msgs::msg::Command::SAVE_MAP:
        {
            RCLCPP_INFO(logger_, "停止建图");

            auto request2 = std::make_shared<ymrobot_msgs::srv::SlamTaskManage::Request>();
            auto slam_task_action = ymrobot_msgs::msg::SlamCommand();

            auto map_name = std::move(command.params[0]);
            auto pcd_file_path = maps_dir_ + "/" + map_name + "/";
            auto pcd_file = maps_dir_ + "/" + map_name + "/map.pcd";

            if (!IsMapFileExist(pcd_file_path))
            {
                RCLCPP_INFO(logger_, "地图文件夹不存在");
                CreateDir(pcd_file_path);
            }

            if (!SavePcdMap(pcd_file_path))
            {
                RCLCPP_ERROR(logger_, "PCD地图保存失败");
                break;
            }

            if (!StopPgoSlam())
            {
                RCLCPP_ERROR(logger_, "停止PGO-SLAM失败");
                break;
            }

            if (SavePgmMap(pcd_file, pcd_file_path))
            {
                RCLCPP_INFO(logger_, "PGM地图保存成功");
            }
            break;
        }
        }
    }

    void TaskGuidance::StartBehaviorTreeTask(const std::shared_ptr<ymrobot_msgs::msg::Task> &task)
    {
        // if (!LoadBehaviorTree(task->behavior_tree, task->reload)) // bug 这里是加载行为树会导致错误 需要修改
        if (!LoadBehaviorTree("", task->reload)) // 使用默认行为树
        {
            RCLCPP_WARN(logger_, "无法加载行为树: %s", task->behavior_tree.c_str());
            std::lock_guard<std::mutex> l(task_mutex_);
            current_task_ = nullptr;
            return;
        }

        RCLCPP_INFO(logger_, "开始执行新的任务 [%s]", task->task_id.c_str());
        ExecuteBehaviorTreeTask();
    }

    bool TaskGuidance::LoadBehaviorTree(const std::string &bt_xml, const bool reload)
    {
        RCLCPP_INFO_STREAM(logger_, "Calling LoadBehaviorTree with bt_xml: "
                                        << bt_xml << ", reload: " << std::boolalpha
                                        << reload);

        auto filename = bt_xml.empty() ? default_bt_xml_filename_ : bt_xml;

        if (current_bt_xml_filename_ == filename && !reload)
        {
            return true;
        }

        try
        {
            // 使用boost库
            // tree_ = boost::ends_with(filename, ".xml")
            //             ? bt_->createTreeFromFile(filename, blackboard_)
            //             : bt_->createTreeFromText(bt_xml, blackboard_);

            tree_ = ends_with(filename, ".xml")
                        ? bt_->createTreeFromFile(filename, blackboard_)
                        : bt_->createTreeFromText(bt_xml, blackboard_);

            for (auto &blackboard : tree_.blackboard_stack)
            {
                blackboard->set<rclcpp::Node::SharedPtr>("node", parent);
                blackboard->set<std::chrono::milliseconds>("server_timeout", std::chrono::milliseconds(500));
                blackboard->set<std::chrono::milliseconds>("bt_loop_duration", std::chrono::milliseconds(500));
                blackboard_->set<std::chrono::milliseconds>("wait_for_service_timeout", std::chrono::milliseconds(5000)); // 设置默认超时时间
            }
        }
        catch (const std::exception &e)
        {
            RCLCPP_ERROR(logger_, "无法加载行为树--: %s", e.what());
            return false;
        }

        current_bt_xml_filename_ = filename;
        RCLCPP_INFO(logger_, "加载行为树成功");
        return true;
    }

    bool TaskGuidance::IsCurrentTaskEmpty(const ymrobot_msgs::msg::Task &task)
    {
        std::lock_guard<std::mutex> l(task_mutex_);
        if (current_task_)
        {
            RCLCPP_WARN(logger_, "当前任务未完成, 无法开始新任务");
            return false;
        }
        current_task_ = std::make_shared<ymrobot_msgs::msg::Task>(task);
        return true;
    }

    bool TaskGuidance::IsCurrentTaskEmptyForMuiltCommands(const ymrobot_msgs::msg::Task &task)
    {
        std::lock_guard<std::mutex> l(task_mutex_);
        if (current_task_)
        {
            RCLCPP_WARN(logger_, "多commands参数,没事没事，放行！！！！");
            return false;
        }
        current_task_ = std::make_shared<ymrobot_msgs::msg::Task>(task);
        return true;
    }

    std::string TaskGuidance::GetDefaultBtFilepath()
    {
        return std::string();
    }

    ymrobot_msgs::msg::Task TaskGuidance::GetCurrentTask()
    {
        std::lock_guard<std::mutex> l(task_mutex_);
        return *current_task_;
    }

    void TaskGuidance::ExecuteBehaviorTreeTask()
    {
        is_cancel_requested_.store(false);
        is_pause_requested_.store(false);

        task_future_ = std::async(std::launch::async, &TaskGuidance::ExecuteCallback, this);
    }

    void TaskGuidance::ExecuteCallback()
    {
        if (!OnTaskReceivedCallback(*current_task_))
        {
            std::lock_guard<std::mutex> l(task_mutex_);
            current_task_ = nullptr;
            return;
        }

        auto canceling = [&]() -> bool
        {
            return is_pause_requested_.load() || is_cancel_requested_.load();
        };

        auto on_loop = [&]()
        {
            if (is_cancel_requested_)
            {
                RCLCPP_INFO(logger_, "on_loop函数 is_cancel_requested");
                OnPreemptCallback();
            }
            else if (is_pause_requested_)
            {
                RCLCPP_INFO(logger_, "on_loop函数 is_pause_requested_");
                OnPauseCallback();
            }
            else
            {
                // RCLCPP_INFO(logger_, "on_loop函数 ! and !");
                OnLoopCallback();
            }
        };


        RCLCPP_INFO(logger_, "BehaviorTree parameters:  1\n");

        RCLCPP_INFO(logger_, "开始执行行为树");
        blackboard_->set("current_task", *current_task_);                                    // 黑板：设置当前任务
        blackboard_->set<ymrobot_msgs::msg::Command>("command", current_task_->commands[0]); // 黑板：设置当前commmand

        // NavModeSelect(current_task_);  //这是用于导航的，现在版本不需要了
        
        RCLCPP_INFO(logger_, "BehaviorTree parameters:  2\n");
        
        nav2_behavior_tree::BtStatus rc = bt_->run(&tree_, on_loop, canceling, bt_loop_duration_);
        
        bt_->haltAllActions(tree_.rootNode());

        TaskResult rc2;
        switch (rc)
        {
        case nav2_behavior_tree::BtStatus::SUCCEEDED:
            rc2 = TaskResult::SUCCEEDED;
            break;

        case nav2_behavior_tree::BtStatus::FAILED:
            rc2 = TaskResult::FAILED;
            break;

        case nav2_behavior_tree::BtStatus::CANCELED:
            if (is_pause_requested_.load())
            {
                rc2 = TaskResult::PAUSED;
            }
            else
            {
                rc2 = TaskResult::CANCELED;
            }
            break;
        }

        OnCompletionCallback(rc2);
        if (!is_pause_requested_.load())
        {
            std::lock_guard<std::mutex> l(task_mutex_);
            current_task_ = nullptr;
        }
    }

    void TaskGuidance::NavModeSelect(const std::shared_ptr<ymrobot_msgs::msg::Task> &task)
    {
        auto commands = task->commands;
        auto nav_mode = commands[0].code;
        auto nav_points = task->nav_points;

        if (nav_mode == ymrobot_msgs::msg::Command::NAVIGATION)
        {
            geometry_msgs::msg::PoseStamped nav_point;
            RCLCPP_INFO(logger_, "单点导航");
            if (nav_points.empty())
            {
                std::cout << "1111" << std::endl;
                std::string nav_name = commands[0].params[0];
                // 下面是对点位名进行校验和导航功能
            }
            else
            {
                nav_point = nav_points[0].position;
                nav_point.header.frame_id = "map";
                nav_point.header.stamp = this->get_clock()->now();

                std::cout << "导航点： x : " << nav_point.pose.position.x << "  y: " << nav_point.pose.position.y << std::endl;
            }

            blackboard_->set<geometry_msgs::msg::PoseStamped>("nav_goal", nav_point);
        }
        else if (nav_mode == ymrobot_msgs::msg::Command::MULIT_POINTS_NAVIGATION)
        {
            std::vector<geometry_msgs::msg::PoseStamped> points;
            RCLCPP_INFO(logger_, "多点导航");
            if (nav_points.empty())
            {
                std::string nav_name = commands[0].params[0];
                // 下面是对点位名进行校验和导航功能
            }
            else
            {
                for (auto _point : nav_points)
                {
                    auto point = _point.position;
                    point.header.frame_id = "map";
                    point.header.stamp = this->get_clock()->now();
                    points.emplace_back(point);
                }
            }

            blackboard_->set<std::vector<geometry_msgs::msg::PoseStamped>>("goals", points);
        }
        else if (nav_mode == ymrobot_msgs::msg::Command::MULIT_FLOOR_NAVIGATION)
        {
            MultFloorNav();
        }
    }

    void TaskGuidance::MultFloorNav()
    {
        auto target_pose_floor = current_task_->nav_points[0].map_index;
        // 下面是楼层地图选择功能。
        geometry_msgs::msg::PoseStamped current_floor_wait_point;
        geometry_msgs::msg::PoseStamped target_floor_wait_point;
    }

    bool TaskGuidance::SavePcdMap(const std::string &pcd_file_path)
    {
        auto request = std::make_shared<interface::srv::SaveMaps::Request>();
        request->file_path = pcd_file_path;
        request->save_patches = false;
        auto response = save_pcd_client_->async_send_request(request);
        response.wait();

        if (response.get()->success)
        {
            RCLCPP_INFO(logger_, "PCD地图保存成功");
            return true;
            // sqlite::database *map_db_{};
        }
        else
        {
            RCLCPP_ERROR(logger_, "PCD地图保存失败，错误信息:%s", response.get()->message.c_str());
            return false;
        }
    }

    bool TaskGuidance::SavePgmMap(const std::string &pcd_name, const std::string &pgm_name)
    {
        auto request = std::make_shared<ymrobot_msgs::srv::MapTaskManage::Request>();
        auto task = ymrobot_msgs::msg::MapTaskCommand();
        task.code = ymrobot_msgs::msg::MapTaskCommand::PCD2PGM;

        request->pcd_name = pcd_name;
        request->pgm_name = pgm_name;
        request->map_task = task;

        auto future = save_pgm_client_->async_send_request(request);
        future.wait();

        if (future.get()->success)
        {
            RCLCPP_INFO(logger_, "保存PGM地图成功");
            return true;
        }
        else
        {
            RCLCPP_ERROR(logger_, "保存PGM地图失败，错误信息：%s", future.get()->message.c_str());
            return false;
        }
    }

    bool TaskGuidance::StopPgoSlam()
    {
        auto request2 = std::make_shared<ymrobot_msgs::srv::SlamTaskManage::Request>();
        auto slam_task_action = ymrobot_msgs::msg::SlamCommand();

        request2->task = slam_task_action.mapping;
        request2->action = "stop";
        auto future = build_map_client_->async_send_request(request2);

        future.wait();
        if (future.get()->success)
        {
            RCLCPP_INFO(logger_, "停止PGO-SLAM成功");
            return true;
        }
        else
        {
            RCLCPP_ERROR(logger_, "停止PGO-SLAM失败，错误信息:%s", future.get()->message.c_str());
            return false;
        }
    }

    int srv_count = 0;
    bool TaskGuidance::StartLocalizerSlam(const std::string &pcd_path)
    {
        RCLCPP_INFO(logger_, "pcd地图地址: %s", pcd_path.c_str());
        auto request = std::make_shared<ymrobot_msgs::srv::SlamTaskManage::Request>();
        auto slam_task_action = ymrobot_msgs::msg::SlamCommand();

        request->task = "relocalize"; // slam_task_action.relocalize
        request->action = "start";
        std::cout << "11111" << std::endl;
        auto future = reloclizer_client_->async_send_request(request);
        future.wait();
        if (future.get()->success)
        {
            RCLCPP_INFO(logger_, "启动本地化SLAM成功");
        }
        else
        {
            RCLCPP_ERROR(logger_, "启动本地化SLAM失败，错误信息:%s", future.get()->message.c_str());
            return false;
        }

        // RCLCPP_INFO(logger_, "pcd地图地址: %s", pcd_path.c_str());
        auto request2 = std::make_shared<interface::srv::Relocalize::Request>();
        request2->pcd_path = std::move(pcd_path);
        request2->x = 0.0;
        request2->y = 0.0;
        request2->z = 0.0;
        request2->yaw = 0.0;
        request2->pitch = 0.0;
        request2->roll = 0.0;

        while (!reloclizer_pcd_client_->wait_for_service(std::chrono::seconds(1)))
        {
            if (srv_count > 10)
            {
                RCLCPP_INFO(logger_, "重定位,pcd初始化服务端超时，超过10s");
                srv_count = 0;
                break;
            }
            ++srv_count;
            RCLCPP_INFO(logger_, "Waiting for service to be available...");
        }

        srv_count = 0;
        auto future2 = reloclizer_pcd_client_->async_send_request(request2);
        future2.wait();
        if (future2.get()->success)
        {
            RCLCPP_INFO(logger_, "重定位成功");
            return true;
        }
        else
        {
            RCLCPP_ERROR(logger_, "重定位失败，错误信息:%s", future2.get()->message.c_str());
            return false;
        }
    }

    bool TaskGuidance::LoadMap(const std::string &map_yaml_path)
    {
        RCLCPP_INFO(logger_, "[TaskGuidance]: 加载地图");
        std_msgs::msg::UInt8 map_mode;
        map_mode.data = 2;
        map_mode_pub_->publish(map_mode);

        auto request = std::make_shared<nav2_msgs::srv::LoadMap::Request>();
        request->map_url = map_yaml_path;
        auto future = nav2_map_client_->async_send_request(request);

        future.wait();

        if (future.get()->result == nav2_msgs::srv::LoadMap::Response::RESULT_SUCCESS)
        {
            RCLCPP_INFO(logger_, "地图加载成功");
            return true;
        }
        else
        {
            RCLCPP_ERROR(logger_, "地图加载失败，错误信息");
            return false;
        }
    }

    bool TaskGuidance::IsMapFileExist(const std::string &path)
    {
        std::ifstream file(path);
        return file.good();
    }

    void TaskGuidance::CreateDir(const std::string &file_path)
    {
        std::filesystem::create_directory(file_path);
    }

    void TaskGuidance::CreateFile(const std::string &file_path)
    {
        std::ofstream file(file_path);
        file.close();
    }

    bool TaskGuidance::OnTaskReceivedCallback(const ymrobot_msgs::msg::Task &task)
    {
        if (task_state_pub_)
        {
            const auto task = GetCurrentTask();
            std::lock_guard<std::mutex> l2(status_mutex_);

            task_status_.task_id = task.task_id;
            task_status_.text = "Task Running";
            task_status_.status = ymrobot_msgs::msg::TaskStatusCode::RUNNING;

            task_state_pub_->publish(task_status_);
        }
        return true;
    }

    void TaskGuidance::OnLoopCallback()
    {
    }

    void TaskGuidance::OnPreemptCallback()
    {
        if (task_state_pub_)
        {
            std::lock_guard<std::mutex> l2(status_mutex_);
            task_status_.task_id = current_task_->task_id;
            task_status_.text = "Task Preempting";
            task_status_.status = ymrobot_msgs::msg::TaskStatusCode::ABORTED; // 这边待会检查一下
            task_state_pub_->publish(task_status_);
        }
    }

    void TaskGuidance::OnPauseCallback()
    {
        if (task_state_pub_)
        {
            std::lock_guard<std::mutex> l2(status_mutex_);
            task_status_.task_id = current_task_->task_id;
            task_status_.text = "Task Preempting";
            task_status_.status = ymrobot_msgs::msg::TaskStatusCode::HELD;
            task_state_pub_->publish(task_status_);
        }
    }

    void TaskGuidance::OnResumeCallback()
    {
        if (task_state_pub_)
        {
            std::lock_guard<std::mutex> l2(status_mutex_);
            task_status_.task_id = current_task_->task_id;
            task_status_.text = "Task Resumed";
            task_status_.status = ymrobot_msgs::msg::TaskStatusCode::RUNNING;
            task_state_pub_->publish(task_status_);
        }
    }

    void TaskGuidance::OnCompletionCallback(const TaskResult &task_result)
    {
        std::lock_guard<std::mutex> l2(status_mutex_);
        switch (task_result)
        {
        case TaskResult::SUCCEEDED:
        {
            RCLCPP_INFO(logger_, "Task succeeded");
            task_status_.text = "Task Succeeded";
            task_status_.status = ymrobot_msgs::msg::TaskStatusCode::SUCCEEDED;
        }
        break;

        case TaskResult::FAILED:
        {
            RCLCPP_ERROR(logger_, "Task failed");
            task_status_.text = "Task Failed";
            task_status_.status = ymrobot_msgs::msg::TaskStatusCode::ABORTED;
        }
        break;

        case TaskResult::CANCELED:
        {
            RCLCPP_INFO(logger_, "Task canceled");
            task_status_.text = "Task Canceled";
            task_status_.status = ymrobot_msgs::msg::TaskStatusCode::CANCLE;
        }
        break;

        case TaskResult::PAUSED:
        {
            RCLCPP_INFO(logger_, "Task paused");
            task_status_.text = "Task Paused";
            task_status_.status = ymrobot_msgs::msg::TaskStatusCode::HELD;
        }
        break;
        }

        if (task_state_pub_)
        {
            task_status_.amr_id = current_task_->amr_id;
            task_status_.task_id = current_task_->task_id;
            task_state_pub_->publish(task_status_);
            RCLCPP_INFO(logger_, "任务状态发布成功，任务ID为：%s", task_status_.task_id.c_str());
        }
    }
}

int main(int argc, char *argv[])
{
    /* 初始化ROS2 */
    rclcpp::init(argc, argv);

    /* 运行节点MinimalPublisher */
    rclcpp::spin(std::make_shared<ymrobot::TaskGuidance>());

    /* 退出ROS2 */
    rclcpp::shutdown();
    return 0;
}