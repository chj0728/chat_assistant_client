#include "set_params_action_node.hpp"

namespace ymrobot
{
    SetParamsActionbNode::SetParamsActionbNode() : Node("set_params_action_node")
    {
        Init();
    }

    SetParamsActionbNode::~SetParamsActionbNode()
    {
    }

     void SetParamsActionbNode::Init()
    {
        InitParams();
        CreateActionServer();
        InitStandbyPoint();
    }

    void SetParamsActionbNode::InitStandbyPoint()
    {
        std::string standby_point;
        try
        {
            YAML::Node config = YAML::LoadFile("/home/ymrobot/ros2_ws_guidance/src/guided-robot/params/robot.yaml");

            if (config["robot"] && config["robot"]["standby_point"])
            {
                standby_point = config["robot"]["standby_point"].as<std::string>();
            }
        }
        catch (const YAML::Exception &e)
        {
            RCLCPP_ERROR(this->get_logger(), "YAML 文件解析失败: %s", e.what());
        }
        auto standby_point_list = sql_manager_.GetColumnFromCSV("/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/mark_points.csv", 8);
        if (std::find(standby_point_list.begin(), standby_point_list.end(), standby_point) == standby_point_list.end())
        {
            SetYaml("/home/ymrobot/ros2_ws_guidance/src/guided-robot/params/robot.yaml", "robot", "standby_point", "充电桩");
        }
    }

    void SetParamsActionbNode::InitParams()
    {
        this->declare_parameter("cloud_chassis_max_linear_speed_pub_name", "");
        this->declare_parameter("cloud_chassis_max_angular_speed_pub_name", "");
        this->declare_parameter("power_threshold_parameter_update_pub_name", "");
        this->declare_parameter("modify_timbre_pub_name", "");
        this->declare_parameter("active_wake_up_threshold_pub_name", "");
        this->declare_parameter("is_open_active_wake_up_name", "");
        this->declare_parameter("welcome_language_selection_name", "");
        this->declare_parameter("is_open_near_point_explanation_pub_name", "");
        this->declare_parameter("set_params_action_server_name", "");
        this->declare_parameter("mark_points_txt_adress", "");
        this->declare_parameter("concession_distance_threshold_pub_name", "");
        this->declare_parameter("is_open_passive_wake_up_name", "");
        this->declare_parameter("yaml_file_adress", "");
        this->declare_parameter("modify_wakeup_word_pub_name", "");

        cloud_chassis_max_linear_speed_pub_name_ = this->get_parameter("cloud_chassis_max_linear_speed_pub_name").as_string();
        cloud_chassis_max_angular_speed_pub_name_ = this->get_parameter("cloud_chassis_max_angular_speed_pub_name").as_string();
        power_threshold_parameter_update_pub_name_ = this->get_parameter("power_threshold_parameter_update_pub_name").as_string();
        modify_timbre_pub_name_ = this->get_parameter("modify_timbre_pub_name").as_string();
        active_wake_up_threshold_pub_name_ = this->get_parameter("active_wake_up_threshold_pub_name").as_string();
        is_open_active_wake_up_name_ = this->get_parameter("is_open_active_wake_up_name").as_string();
        welcome_language_selection_name_ = this->get_parameter("welcome_language_selection_name").as_string();
        is_open_near_point_explanation_pub_name_ = this->get_parameter("is_open_near_point_explanation_pub_name").as_string();
        set_params_action_server_name_ = this->get_parameter("set_params_action_server_name").as_string();
        mark_points_txt_adress_ = this->get_parameter("mark_points_txt_adress").as_string();
        concession_distance_threshold_pub_name_ = this->get_parameter("concession_distance_threshold_pub_name").as_string();
        is_open_passive_wake_up_name_ = this->get_parameter("is_open_passive_wake_up_name").as_string();
        yaml_file_adress_ = this->get_parameter("yaml_file_adress").as_string();
        modify_wakeup_word_pub_name_ = this->get_parameter("modify_wakeup_word_pub_name").as_string();

        std::cout << "yaml_file_adress_  *****:" << yaml_file_adress_ << std::endl;
    }

    void SetParamsActionbNode::CreateActionServer()
    {
        cloud_chassis_max_linear_speed_pub_ = this->create_publisher<std_msgs::msg::Float64>(cloud_chassis_max_linear_speed_pub_name_, 1);
        cloud_chassis_max_angular_speed_pub_ = this->create_publisher<std_msgs::msg::Float64>(cloud_chassis_max_angular_speed_pub_name_, 1);
        power_threshold_parameter_update_pub_ = this->create_publisher<std_msgs::msg::Float64>(power_threshold_parameter_update_pub_name_, 1);
        active_wake_up_threshold_pub_ = this->create_publisher<std_msgs::msg::Float64>(active_wake_up_threshold_pub_name_, 1);
        is_open_active_wake_up_ = this->create_publisher<std_msgs::msg::Bool>(is_open_active_wake_up_name_, 1);
        modify_timbre_pub_ = this->create_publisher<std_msgs::msg::String>(modify_timbre_pub_name_, 1);
        welcome_word_selection_pub_ = this->create_publisher<std_msgs::msg::String>(welcome_language_selection_name_, 1);
        concession_distance_threshold_pub_ = this->create_publisher<std_msgs::msg::Float64>(concession_distance_threshold_pub_name_, 1);
        is_open_passive_wake_up_ = this->create_publisher<std_msgs::msg::Bool>(is_open_passive_wake_up_name_, 1);
        modify_wakeup_word_pub_ = this->create_publisher<ymrobot_msgs::msg::WakeUpWordSetting>(modify_wakeup_word_pub_name_, 1);
        set_params_action_server_ = rclcpp_action::create_server<ymrobot_msgs::action::GetCurrentTask>(
            this,
            set_params_action_server_name_,
            std::bind(&SetParamsActionbNode::SetParamsHandleGoal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&SetParamsActionbNode::SetParamsHandleCancel, this, std::placeholders::_1),
            std::bind(&SetParamsActionbNode::SetParamsHandleAccepted, this, std::placeholders::_1));
    }

    rclcpp_action::GoalResponse SetParamsActionbNode::SetParamsHandleGoal(const rclcpp_action::GoalUUID &, std::shared_ptr<const ymrobot_msgs::action::GetCurrentTask::Goal> goal)
    {
        RCLCPP_INFO(this->get_logger(), "收到设置参数请求");
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse SetParamsActionbNode::SetParamsHandleCancel(const std::shared_ptr<GoalHandleSetParams> goal_handle)
    {
        RCLCPP_INFO(this->get_logger(), "收到取消设置参数请求");
        (void)goal_handle;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void SetParamsActionbNode::SetParamsHandleAccepted(const std::shared_ptr<GoalHandleSetParams> goal_handle)
    {
        std::thread(std::bind(&SetParamsActionbNode::SetParamsExecuteMove, this, goal_handle)).detach();
    }

    void SetParamsActionbNode::SetParamsExecuteMove(const std::shared_ptr<GoalHandleSetParams> goal_handle)
    {
        auto commands = goal_handle->get_goal()->current_task.commands;
        auto result = std::make_shared<ymrobot_msgs::action::GetCurrentTask::Result>();

        RCLCPP_INFO(this->get_logger(), "当前需要设置参数的数量为:%d", commands.size());
        if (commands.empty())
        {
            RCLCPP_ERROR(this->get_logger(), "当前需要设置参数的数量为空,请检查!");
            result->success = false;
            result->message = "当前需要设置参数的数量为空,请检查!";
            goal_handle->abort(result);
        }

        // for (auto command : commands)
        // {
        //     if (command.code == ymrobot_msgs::msg::Command::WAKE_UP)
        //     {
        //         RCLCPP_INFO(this->get_logger(), "唤醒机器人");
        //         // 替换为你的脚本路径
        //         const std::string scriptPath = "/path/to/your/script.sh";

        //         // 执行脚本
        //         int result = std::system(scriptPath.c_str());

        //         if (result == 0)
        //         {
        //             std::cout << "脚本执行成功！" << std::endl;
        //         }
        //         else
        //         {
        //             std::cerr << "脚本执行失败！" << std::endl;
        //         }
        //     }

        //     if (command.params_code == "linear_velocity")
        //     {
        //         std_msgs::msg::Float64 linear_velocity;
        //         linear_velocity.data = std::stod(command.params[0]);
        //         cloud_chassis_max_linear_speed_pub_->publish(linear_velocity);
        //     }
        //     else if (command.params_code == "angular_velocity")
        //     {
        //         std_msgs::msg::Float64 angular_velocity;
        //         angular_velocity.data = std::stod(command.params[0]);
        //         cloud_chassis_max_angular_speed_pub_->publish(angular_velocity);
        //     }
        //     else if (command.params_code == "battery_level")
        //     {
        //         std_msgs::msg::Float64 battery_level;
        //         battery_level.data = std::stod(command.params[0]);
        //         power_threshold_parameter_update_pub_->publish(battery_level);
        //     }
        //     else if (command.params_code == "voice_type")
        //     {
        //         std_msgs::msg::String modify_timbre;
        //         modify_timbre.data = command.params[0];
        //         modify_timbre_pub_->publish(modify_timbre);
        //     }
        //     else if (command.params_code == "pending_point_name")
        //     {
        //         RCLCPP_INFO(this->get_logger(), "设置参数：设置点类型");
        //         std::string pose_name = command.params[0];
        //         std::string val_str = command.params[1];
        //         RCLCPP_INFO(this->get_logger(), "设置待命点： %s",pose_name.c_str());
        //         // sql_manager_.UpdateRowByColumn(mark_points_txt_adress_, "pose_name", pose_name, "pose_type", val_str);
        //         //  打开文件，如果文件不存在则创建，如果存在则覆盖内容
        //         std::ofstream file(mark_points_txt_adress_);
        //         if (file.is_open())
        //         {
        //             file << pose_name << std::endl;
        //             file.close();
        //             RCLCPP_INFO(this->get_logger(), "设置参数：设置点类型成功");
        //         }
        //         else
        //         {
        //             RCLCPP_ERROR(this->get_logger(), "无法打开文件: %s", mark_points_txt_adress_.c_str());
        //         }
        //     }
        //     else if (command.params_code == "is_open_solicitation")
        //     {
        //         RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启 招揽功能");
        //         bool is_open_solicitation_;
        //         if(command.params[0] == "0")
        //         {
        //             is_open_solicitation_ = false;
        //         }
        //         else if(command.params[0] == "1")
        //         {
        //             is_open_solicitation_ = true;
        //         }
        //         else
        //         {
        //             RCLCPP_ERROR(this->get_logger(), "设置参数：设置是否开启 参数错误");
        //             return;
        //         }

        //         RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启 %s", is_open_solicitation_ ? "true" : "false");
        //     }
        // }

        for (auto command : commands)
        {
            auto it = set_params_name_map.find(command.params_code);
            std::cout <<"***************command.params_code  "<< command.params_code << std::endl;
            SetParameterType set_parameter_type = (it != set_params_name_map.end()) ? it->second : SetParameterType::UNKNOWN;

            switch (set_parameter_type)
            {
            case SetParameterType::LINEAR_VELOCITY:
            {
                std_msgs::msg::Float64 linear_velocity;
                linear_velocity.data = std::stod(command.params[0]);
                cloud_chassis_max_linear_speed_pub_->publish(linear_velocity);
                break;
            }
            case SetParameterType::ANGULAR_VELOCITY:
            {
                std_msgs::msg::Float64 angular_velocity;
                angular_velocity.data = std::stod(command.params[0]);
                cloud_chassis_max_angular_speed_pub_->publish(angular_velocity);
                break;
            }
            case SetParameterType::BATTERY_LEVEL:
            {
                std_msgs::msg::Float64 battery_level;
                battery_level.data = std::stod(command.params[0]);
                power_threshold_parameter_update_pub_->publish(battery_level);
                SetYaml("/home/ymrobot/ros2_ws_guidance/src/guided-robot/params/nodes_xiugai.yaml", "system_master_control", "low_battery_recharge_threshold", (double)battery_level.data);
                break;
            }
            case SetParameterType::VOICE_TYPE:
            {
                std_msgs::msg::String modify_timbre;
                modify_timbre.data = command.params[0];
                modify_timbre_pub_->publish(modify_timbre);
                std::cout << "modify_timbre: " << modify_timbre.data << std::endl;
                SetYaml("/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/config/conversation.yaml", "ROBOT", "VOICENAME", modify_timbre.data);
                break;
            }
            case SetParameterType::PENDING_POINT_NAME:
            {
                SetPendingPointName(command.params[1]);
                break;
            }
            case SetParameterType::IS_OPEN_SOLICITATION:
            {
                RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启 招揽功能");
                bool is_open_solicitation_;
                if (command.params[0] == "0")
                {
                    is_open_solicitation_ = false;
                }
                else if (command.params[0] == "1")
                {
                    is_open_solicitation_ = true;
                }
                else
                {
                    RCLCPP_ERROR(this->get_logger(), "设置参数：设置是否开启 参数错误");
                    return;
                }
                RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启 %s", is_open_solicitation_ ? "true" : "false");
                break;
            }
            case SetParameterType::IS_OPEN_ACTIVE_WAKE_UP:
            {
                RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启 主动唤醒功能");
                IsOpenActiveWakeUp(command.params[0]);
                break;
            }
            case SetParameterType::ACTIVE_WAKE_UP_THRESHOLD:
            {
                RCLCPP_INFO(this->get_logger(), "设置参数：设置是主动唤醒阈值设置");
                ActiveWakeUpThresholdSetting(command.params[0]);
                break;
            }
            case SetParameterType::WELCOME_LANGUAGE_SELECTION:
            {
                RCLCPP_INFO(this->get_logger(), "设置参数：设置欢迎语选择");
                WelcomeLanguageSelection(command.params[0]);
                break;
            }
            case SetParameterType::NEAR_POINT_EXPLANATION_ENABLE:
            {
                RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启 就近点讲解功能");
                IsOpenNearPointExplanation(command.params[0]);
                break;
            }
            case SetParameterType::CONCESSION_DISTANCE_THRESHOLD_SETTING:
            {
                RCLCPP_INFO(this->get_logger(), "设置参数：让步距离阈值设置");
                SetConcessionDistanceThreshold(command.params[0]);
                break;
            }
            case SetParameterType::IS_OPEN_PASSIVE_WAKE_UP:
            {
                RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启 被动唤醒功能");
                SetPassiveWakeUp(command.params[0]);
                break;
            }
            case SetParameterType::WAKE_WORD:
            {
                RCLCPP_INFO(this->get_logger(), "唤醒词修改"); 
                auto wake_up_word_modification = ymrobot_msgs::msg::WakeUpWordSetting();

                for(auto a : command.params)
                {
                    wake_up_word_modification.wake_up_word.emplace_back(a);
                }
                
                for(auto b : wake_up_word_modification.wake_up_word)
                {
                    std::cout << "唤醒词： " << b << std::endl;
                }
                modify_wakeup_word_pub_->publish(wake_up_word_modification);
                break;
            }
            case SetParameterType::SOLICITATION_FUNCTION:
            {
                RCLCPP_INFO(this->get_logger(), "设置参数：设置招揽功能");
                IsOpenActiveWakeUp(command.params[0]);
                break;
            }
            case SetParameterType::AI_PERSONA:
            {
                RCLCPP_INFO(this->get_logger(), "AI人设");
                SetYaml("/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/config/conversation.yaml", "ROBOT", "VOICENAME", command.params[0]);
                break;
            }
            default:
                RCLCPP_WARN(this->get_logger(), "设置参数,不支持的参数类型");
                break;
            }
        }
    }

    void SetParamsActionbNode::IsOpenActiveWakeUp(const std::string &is_wake_up)
    {
        bool is_open_active_wake_up;
        std_msgs::msg::Bool is_open_active_wake_up_msg;
        if (is_wake_up == "0")
        {
            is_open_active_wake_up = false;
        }
        else if (is_wake_up == "1")
        {
            is_open_active_wake_up = true;
        }
        RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启主动唤醒 %s", is_open_active_wake_up ? "true" : "false");
        is_open_active_wake_up_msg.data = is_open_active_wake_up;
        is_open_active_wake_up_->publish(is_open_active_wake_up_msg);
        SetYaml(yaml_file_adress_, "robot", "is_open_active_wake_up", is_open_active_wake_up);
    }

    void SetParamsActionbNode::ActiveWakeUpThresholdSetting(const std::string &active_wake_up_threshold_str)
    {
        // 唤醒阈值设置
        double active_wake_up_threshold = std::stod(active_wake_up_threshold_str);
        std_msgs::msg::Float64 active_wake_up_threshold_msg;
        active_wake_up_threshold_msg.data = active_wake_up_threshold;
        active_wake_up_threshold_pub_->publish(active_wake_up_threshold_msg);
    }

    void SetParamsActionbNode::WelcomeLanguageSelection(const std::string &welcome_language_selection_str)
    {
        RCLCPP_INFO(this->get_logger(), "设置参数：设置欢迎语选择 %s", welcome_language_selection_str.c_str());
        std_msgs::msg::String welcome_language_selection_msg;
        welcome_language_selection_msg.data = welcome_language_selection_str;
        welcome_word_selection_pub_->publish(welcome_language_selection_msg);
        // SetYaml(yaml_file_adress_, "robot", "welcome_word", welcome_language_selection_str);
    }

    void SetParamsActionbNode::IsOpenNearPointExplanation(const std::string &is_open_near_point_explanation_str)
    {
        bool is_open_near_point_explanation;
        std_msgs::msg::Bool is_open_near_point_explanation_msg;
        if (is_open_near_point_explanation_str == "0")
        {
            is_open_near_point_explanation = false;
        }
        else if (is_open_near_point_explanation_str == "1")
        {
            is_open_near_point_explanation = true;
        }
        RCLCPP_INFO(this->get_logger(), "设置参数：设置是否开启就近点讲解 %s", is_open_near_point_explanation ? "true" : "false");
        is_open_near_point_explanation_msg.data = is_open_near_point_explanation;
        is_open_near_point_explanation_pub_->publish(is_open_near_point_explanation_msg);
    }

    void SetParamsActionbNode::SetConcessionDistanceThreshold(const std::string &concession_distance_threshold_str)
    {
        RCLCPP_INFO(this->get_logger(), "设置参数：设置让步阈值距离设置: %s", concession_distance_threshold_str.c_str());
        std_msgs::msg::Float64 concession_distance_threshold_msg;
        concession_distance_threshold_msg.data = std::stod(concession_distance_threshold_str);
        concession_distance_threshold_pub_->publish(concession_distance_threshold_msg);
    }

    void SetParamsActionbNode::SetPassiveWakeUp(const std::string &is_passive_wake_up_str)
    { 
        std_msgs::msg::Bool msg;
        if (is_passive_wake_up_str == "0")
        {
            RCLCPP_INFO(this->get_logger(), "设置参数：关闭被动唤醒");
            msg.data = false;
            is_open_passive_wake_up_->publish(msg);
            SetYaml(yaml_file_adress_, "robot", "is_activate_passive_wake_up", msg.data);
        }
        else if (is_passive_wake_up_str == "1")
        {
            RCLCPP_INFO(this->get_logger(), "设置参数：设开启主动唤醒");
            msg.data = true;
            is_open_passive_wake_up_->publish(msg);
            SetYaml(yaml_file_adress_, "robot", "is_activate_passive_wake_up", msg.data);
        }
    }

    void SetParamsActionbNode::SetPendingPointName(const std::string &pending_point_name_str)
    {
        // auto pending_point_name = "\"" + pending_point_name_str + "\"";
        auto pending_point_name = pending_point_name_str;
        RCLCPP_INFO(this->get_logger(), "设置参数：设置待命点名称 %s", pending_point_name.c_str());
        SetYaml("/home/ymrobot/ros2_ws_guidance/src/guided-robot/params/robot.yaml", "robot", "standby_point", pending_point_name);
    }

    void SetParamsActionbNode::SetWakeUpWordModification(const std::string &wake_up_word_modification_str)
    {
        RCLCPP_INFO(this->get_logger(), "设置参数：设置唤醒词修改 %s", wake_up_word_modification_str.c_str());
        auto wake_up_word_modification = ymrobot_msgs::msg::WakeUpWordSetting();
        wake_up_word_modification.wake_up_word.emplace_back(wake_up_word_modification_str);
        modify_wakeup_word_pub_->publish(wake_up_word_modification);
        // SetYaml(yaml_file_adress_, "robot", "awakening_words", wake_up_word_modification_str);
    }

    template <typename T>
    void SetParamsActionbNode::SetYaml(const std::string &yaml_file_path, const std::string &ros2_node_name, const std::string &parameter_name, const T &parameter_value)
    {
        try
        {
            YAML::Node config = YAML::LoadFile(yaml_file_path);
            // if (config[ros2_node_name])
            // {
            //     // 直接修改 config，不需要引用
            //     config[ros2_node_name][parameter_name] = parameter_value;
            // }
            // else
            // {
            //     RCLCPP_ERROR(this->get_logger(), "Key 'robot' not found in YAML file.");
            // }

            // 情况1: 直接参数(robot节点)
            if (config[ros2_node_name][parameter_name])
            {
                config[ros2_node_name][parameter_name] = parameter_value;
            }
            // 情况2: ros__parameters下的参数(pedestrian_detector_node节点)
            else if (config[ros2_node_name]["ros__parameters"] &&
                     config[ros2_node_name]["ros__parameters"][parameter_name])
            {
                config[ros2_node_name]["ros__parameters"][parameter_name] = parameter_value;
            }
            else
            {
                RCLCPP_ERROR(this->get_logger(),
                             "Parameter '%s' not found in node '%s'",
                             parameter_name.c_str(),
                             ros2_node_name.c_str());
                return;
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
    auto node = std::make_shared<ymrobot::SetParamsActionbNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}