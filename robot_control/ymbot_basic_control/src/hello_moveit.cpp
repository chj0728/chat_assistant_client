#include <chrono>
#include "std_msgs/msg/bool.hpp"
#include <rclcpp/rclcpp.hpp>
#include <moveit/move_group_interface/move_group_interface.h>
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/int8.hpp>
#include <ymrobot_msgs/srv/up_limb.hpp>
#include <random>

class AutoDualArmController : public rclcpp::Node
{
public:
    AutoDualArmController() : Node("auto_dual_arm_controller")
    {
        // 初始化预定义关节角度
        deliver_angles_ = {0, 0, 0, 1, 0, 0, 0, 0, 0, 0, -2, 0, 0, 0};
        zero_angles_ ={0, 0, 0, 1, 0, 25, 0, 0, 0, 0, -1, 0, -25, 0};
        right_introduce_angles_ = {0, 0, 0, 4, 35, -44, -17, -20, 0, 9, -8, 30, 17, 0};
        left_introduce_angles_ = {0, 0, -27, 20, -25, -13, -22, 20, 0, 0, 1, -30, 50, 0};
        left_shank_angles_ = {0, 0, -21, 0, 33, -14, -28, 0, 0, 0, 0, 0, -25, 0};
        right_shank_angles_ = {0, 0, 0, 0, 0, 25, 0, 0, 0, 8, -2, -40, 40, 15};
        // 合并的挥手动作轨迹
        left_wave_angles_ = {
            {0, 0, -50, 9, 18, -73, 60, 0, 0, 0, 0, 0, -25, 0},
            {0, 0, -50, 9, -25, -71, 78, 0, 0, 0, 0, 0, -25, 0},
            {0, 0, -50, 9, 18, -73, 60, 0, 0, 0, 0, 0, -25, 0},
            {0, 0, -50, 9, -25, -71, 78, 0, 0, 0, 0, 0, -25, 0},
            {0, 0, 0, 0, 0, 25, 0, 0, 0, 0, 0, 0, -25, 0}};

        right_wave_angles_ = {
            {0, 0, 0, 0, 0, 25, 0, 0, 0, 50, -14, -17, 73, -61},
            {0, 0, 0, 0, 0, 25, 0, 0, 0, 50, -14, 35, 68, -70},
            {0, 0, 0, 0, 0, 25, 0, 0, 0, 50, -14, -17, 73, -61},
            {0, 0, 0, 0, 0, 25, 0, 0, 0, 50, -14, 35, 68, -70},
            {0, 0, 0, 0, 0, 25, 0, 0, 0, 0, 0, 0, -25, 0}};

        


        talk_angles_ ={
            {0, 0, -33, 19, 16, -25, -20, 0, 0, 0, -2, 0, -25, 0},
            {0, 0, -33, 20, -17, -1, -20, 0, 0, 0, -2, 0, -25, 0},
            {0, 0, -33, 20, -17, -1, -20, 16, 0, 0, -2, 0, -25, 0},
            {0, 0, 0, 2, 0, 0, 0, 0, 0, 0, -2, 0, 0, 0},
            {0, 0, -20, 2, 0, 0, -20, 0, 0, 20, -2, 0, 19, 0},
            {0, 0, -20, 2, 0, -12, -20, -16, 0, 31, -5, 35, 30, 0},
            {0, 0, -38, 2, -5, -29, -20, 0, 0, 31, -5, 14, 0, 0},
            {0, 0, -7, 2, -10, -1, -20, 0, 0, 13, -3, 2, -1, 0},
            {0, 0, -40, 16, -8, -33, -20, 10, 0, 0, -2, 0, 0, 0},
            {0, 0, 0, 2, 0, 0, 0, 0, 0, 0, -2, 0, 0, 0},
            {0, 0, -10, 3, -8, -10, -20, 0, 0, 10, -5, 0, 10, 0},
            {0, 0, -20, 10, -10, -10, -20, 0, 0, 20, -10, 10, 10, 0},
            {0, 0, -30, 10, -10, -30, -20, 0, 0, 20, -10, 10, 10, 0},
            {0, 0, -20, 10, -30, 0, -20, 0, 0, 10, -10, 10, 0, 0},
            {0, 0, -10, 10, -30, 0, -20, -10, 0, 20, -10, 20, 10, 0},
            {0, 0, 0, 2, 0, 0, 0, 0, 0, 0, -2, 0, 0, 0},
            {0, 0, -40, 10, 0, 0, -20, 0, 0, 0, -2, 0, 0, 0},
            {0, 0, -40, 10, 0, 0, -20, 0, 0, 40, -10, 0, 0, 0},
            {0, 0, -40, 20, 0, 0, -20, 10, 0, 40, -10, 0, 0, 0},
            {0, 0, -40, 20, 0, 0, -20, -10, 0, 40, -20, 0, 0, 0},
            {0, 0, -20, 5, -5, 5, -35, 0, 0, 30, -5, 13, 24, 0}, 
            {0, 0, -20, 10, -10, -10, -20, 0, 0, 20, -10, 10, 10, 0},
            {0, 0, -30, 10, -10, -30, -20, 0, 0, 20, -10, 10, 10, 0},
            {0, 0, -30, 5, -15, -15, -35, 0, 0, 30, -5, 13, 20, 0},

        };
        // 创建arms_state发布者
        arms_state_publisher_ = this->create_publisher<std_msgs::msg::Int8>("arms_state", 10);
        // 启动后延迟2秒执行（确保系统初始化完成），并确保只执行一次
        timer_ = this->create_wall_timer(
            std::chrono::seconds(1),
            [this]()
            { this->executeActionSequence(); });

        // 订阅动作话题
        // upper_body_data_subscriber_ = this->create_subscription<std_msgs::msg::String>(
        //     "upper_body_data", 10, std::bind(&AutoDualArmController::upper_bodyDataCallback, this, std::placeholders::_1));
            
        // up_climb_stop_sub_ = this->create_subscription<std_msgs::msg::String>("up_climb_action_stop", 10, std::bind(&AutoDualArmController::UpClimbStopSubCallback, this, std::placeholders::_1));
        up_climb_service_ = this->create_service<ymrobot_msgs::srv::UpLimb>("up_climb_srv", std::bind(&AutoDualArmController::UpClimbActionServiceCallback, this, std::placeholders::_1, std::placeholders::_2));
        
        sound_detected_sub_ = this->create_subscription<std_msgs::msg::Bool>(
            "/sound_detected", 
            10, 
            std::bind(&AutoDualArmController::soundDetectedCallback, this, std::placeholders::_1));
        auto sub = this->create_subscription<std_msgs::msg::String>(
            "/cancel_current_task", 
            10, 
            [&](const std_msgs::msg::String::SharedPtr msg) {
                arms_data_callback(msg);
            }
        );
        // auto sub_1 = this->create_subscription<std_msgs::msg::Bool>(
        //     "/sound_detected", 
        //     10, 
        //     [&](const std_msgs::msg::Bool::SharedPtr msg) {
        //         sound_detected_callback(msg);
        //     }
        // );
    }

private:


    void publishArmsState(int8_t state)
    {
        auto message = std_msgs::msg::Int8();
        message.data = state;
        arms_state_publisher_->publish(message);
        // RCLCPP_INFO(this->get_logger(), "发布arms_state: %d", state);
    }


    void executeActionSequence()
    {
        // 初始化MoveGroupInterface
        initMoveGroups();

        // 默认动作序列（可以根据需要修改）
        // const std::vector<std::pair<std::string, std::vector<double>>> action_sequence = {
        //     {"递送姿势", introduce_angles_},
        //     {"挥手动作", wave_angles_},
        //     {"收回姿势", deliver_angles_}};
        // executeMovement(dual_arm_group_, convertToRadians(deliver_angles_));

        timer_->cancel();
    }



    void initMoveGroups()
    {
        if (!move_groups_initialized_)
        {
            dual_arm_group_ = std::make_shared<moveit::planning_interface::MoveGroupInterface>(
                shared_from_this(), "upper_body");
            dual_arm_group_->setMaxVelocityScalingFactor(0.4);
            dual_arm_group_->setMaxAccelerationScalingFactor(0.3);
            move_groups_initialized_ = true;
        }
    }

    std::vector<double> convertToRadians(const std::vector<double> &degrees)
    {
        std::vector<double> radians;
        for (auto deg : degrees)
            radians.push_back(deg * M_PI / 180.0);
        return radians;
    }


    // 修改-by 顾
    bool executeMovement(const moveit::planning_interface::MoveGroupInterfacePtr move_group, const std::vector<double> &joints)
    {
        bool is_exe_successed = false;
        move_group->setJointValueTarget(joints);
        moveit::planning_interface::MoveGroupInterface::Plan plan;
        if (move_group->plan(plan) == moveit::core::MoveItErrorCode::SUCCESS)
        {
            auto exe_result = move_group->execute(plan);
            if(need_arm_init)
            {
                RCLCPP_INFO(this->get_logger(), "收到取消指令，正在回到初始位置...");
                
                // 停止当前运动
                move_group->stop();
                
                // 设置目标为初始位置
                move_group->setJointValueTarget(convertToRadians(deliver_angles_));
                
                // 规划并执行
                moveit::planning_interface::MoveGroupInterface::Plan plan;
                if (move_group->plan(plan) == moveit::core::MoveItErrorCode::SUCCESS)
                {
                    move_group->execute(plan);
                    RCLCPP_INFO(this->get_logger(), "已回到初始位置");
                }
                else
                {
                    RCLCPP_ERROR(this->get_logger(), "回到初始位置失败");
                }
                
                need_arm_init = false; // 重置标志位
                move_group->clearPoseTargets();
                return false; // 按需求返回false
            }
            if (exe_result == moveit::core::MoveItErrorCode::SUCCESS)
            {
                RCLCPP_INFO(this->get_logger(), "机械臂执行成功");
                is_exe_successed = true;
            }
            else
            {
                RCLCPP_ERROR(this->get_logger(), "机械臂执行失败");
                is_exe_successed = false;
            }

            move_group->clearPoseTargets();
        }
        else
        {
            RCLCPP_ERROR(this->get_logger(), "动作规划失败！");
            is_exe_successed = false;
        }

        return is_exe_successed;
    }
    void arms_data_callback(const std_msgs::msg::String::SharedPtr msg){
        if (msg->data == "cancel") {
            need_arm_init = true;
            // RCLCPP_INFO(rclcpp::get_log      ger("arms_data_callback"), "Arm initialization needed: %s", need_arm_init ? "true" : "false");
        } else{
            need_arm_init = false;
        }
    }

    void soundDetectedCallback(const std_msgs::msg::Bool::SharedPtr msg)
    {
        sound_flag = msg->data;
        // RCLCPP_INFO(this->get_logger(), "Received sound detection: %s", 
        //             sound_flag ? "true" : "false");
            
        if(talk_flag && sound_flag) {
            // Generate random index
            arm_flag = true;
            static std::random_device rd;
            static std::mt19937 gen(rd());
            std::uniform_int_distribution<> dis(0, talk_angles_.size()-1);
            int random_index = dis(gen);

            // Get random action
            auto& selected_action = talk_angles_[random_index];
            dual_arm_group_->setMaxVelocityScalingFactor(0.3);
            dual_arm_group_->setMaxAccelerationScalingFactor(0.2);
            
            if (executeMovement(dual_arm_group_, convertToRadians(selected_action))) {
                rclcpp::sleep_for(std::chrono::seconds(2));  // Hold the pose for 2 seconds
            } else {
                RCLCPP_ERROR(this->get_logger(), "Failed to execute talking motion");
            }
        }else{
            if(arm_flag){
                executeMovement(dual_arm_group_, convertToRadians(zero_angles_));
                arm_flag = false ;
            }
        }
    }

    // void sound_detected_callback(const std_msgs::msg::Bool::SharedPtr msg) {

    //     sound_flag = msg->data;
    //     RCLCPP_INFO(this->get_logger(), "sound_flag: %d, talk_flag: %d", sound_flag, talk_flag);
    //     if(talk_flag){

    //         if(sound_flag){
    //             // 生成随机索引
    //             static std::random_device rd;
    //             static std::mt19937 gen(rd());
    //             std::uniform_int_distribution<> dis(0, talk_angles_.size()-1);
    //             int random_index = dis(gen);

    //             // 获取随机动作
    //             auto& selected_action = talk_angles_[random_index];
    //             dual_arm_group_->setMaxVelocityScalingFactor(0.3);
    //             dual_arm_group_->setMaxAccelerationScalingFactor(0.2);
    //             if (executeMovement(dual_arm_group_, convertToRadians(selected_action))) {
    //                 rclcpp::sleep_for(std::chrono::seconds(2));  // 保持动作5秒
    //             } else {
    //                 RCLCPP_ERROR(this->get_logger(), "动作执行失败");
    //             }
    //                         // rclcpp::sleep_for(std::chrono::seconds(2));
    //         }
    //         }
    //     }

    void UpClimbActionServiceCallback(
        const std::shared_ptr<ymrobot_msgs::srv::UpLimb::Request> request,
        std::shared_ptr<ymrobot_msgs::srv::UpLimb::Response> response) 
    {
        auto up_climb_resquest_type = request->up_limb_task_type;
        bool all_success = true;  // 将变量移到 switch 外部
    
        switch (up_climb_resquest_type) {
            case 0: {
                RCLCPP_INFO(this->get_logger(), "执行笛卡尔坐标系变化动作");
                break;
            }
            case 1: {
                RCLCPP_INFO(this->get_logger(), "执行关节变化动作");
                break;
            }
            case 2: {
                RCLCPP_INFO(this->get_logger(), "执行上肢预设动作变化");
                publishArmsState(request->action_fixed);
                // 根据 action_fixed 的值选择不同的动作
                switch (request->action_fixed) {
                    case 0:  // 执行 deliver_angles_
                        talk_flag = false;  
                        RCLCPP_INFO(this->get_logger(), "执行初始位置");
                        dual_arm_group_->setMaxVelocityScalingFactor(0.4);
                        dual_arm_group_->setMaxAccelerationScalingFactor(0.4);
                        all_success = executeMovement(dual_arm_group_, convertToRadians(zero_angles_));
                        response->success = all_success;
                        response->message = all_success ? "初始位置执行成功" : "初始位置执行失败";
                        rclcpp::sleep_for(std::chrono::seconds(1));
                        talk_flag =true ;
                        break;
                    
                    case 1:  
                        talk_flag = false; 
                        RCLCPP_INFO(this->get_logger(), "执行左挥手动作序列");
                        dual_arm_group_->setMaxVelocityScalingFactor(0.4);
                        dual_arm_group_->setMaxAccelerationScalingFactor(0.4);
                        all_success = true;  // 重置为 true
                        for (const auto &wave_position : left_wave_angles_) {
                            if (!executeMovement(dual_arm_group_, convertToRadians(wave_position))) {
                                all_success = false;
                                break;
                            }
                        }
                        response->success = all_success;
                        response->message = all_success ? "左挥手动作执行成功" : "左挥手动作执行失败";
                        rclcpp::sleep_for(std::chrono::seconds(1));
                        talk_flag = true; 
                        break;
                    
                    case 2:  
                        talk_flag = false; 
                        RCLCPP_INFO(this->get_logger(), "执行右挥手动作序列");
                        dual_arm_group_->setMaxVelocityScalingFactor(0.4);
                        dual_arm_group_->setMaxAccelerationScalingFactor(0.4);
                        all_success = true;  // 重置为 true
                        for (const auto &wave_position : right_wave_angles_) {
                            if (!executeMovement(dual_arm_group_, convertToRadians(wave_position))) {
                                all_success = false;
                                break;
                            }
                        }
                        response->success = all_success;
                        response->message = all_success ? "右挥手动作执行成功" : "右挥手动作执行失败";
                        rclcpp::sleep_for(std::chrono::seconds(1));
                        talk_flag = true; 
                        break;
                    
                    case 3:  
                        talk_flag = false; 
                        RCLCPP_INFO(this->get_logger(), "执行左指引姿势");
                        dual_arm_group_->setMaxVelocityScalingFactor(0.4);
                        dual_arm_group_->setMaxAccelerationScalingFactor(0.4);
                        all_success = executeMovement(dual_arm_group_, convertToRadians(left_introduce_angles_));
                        response->success = all_success;
                        response->message = all_success ? "左指引姿势执行成功" : "左指引姿势执行失败";
                        rclcpp::sleep_for(std::chrono::seconds(1));
                        talk_flag = true; 
                        break;

                    case 4:  
                        talk_flag = false; 
                        RCLCPP_INFO(this->get_logger(), "执行右指引姿势");
                        dual_arm_group_->setMaxVelocityScalingFactor(0.4);
                        dual_arm_group_->setMaxAccelerationScalingFactor(0.4);
                        all_success = executeMovement(dual_arm_group_, convertToRadians(right_introduce_angles_));
                        response->success = all_success;
                        response->message = all_success ? "右指引姿势执行成功" : "右指引姿势执行失败";
                        rclcpp::sleep_for(std::chrono::seconds(1));
                        talk_flag = true; 
                        break;

                    case 5:  
                        talk_flag = false; 
                        RCLCPP_INFO(this->get_logger(), "执行左手握手姿势");
                        dual_arm_group_->setMaxVelocityScalingFactor(0.4);
                        dual_arm_group_->setMaxAccelerationScalingFactor(0.4);
                        all_success = executeMovement(dual_arm_group_, convertToRadians(left_shank_angles_));
                        response->success = all_success;
                        response->message = all_success ? "左手握手姿势执行成功" : "左手握手姿势执行失败";
                        rclcpp::sleep_for(std::chrono::seconds(1));
                        talk_flag = true; 
                        break;

                    case 6:  
                        talk_flag = false; 
                        RCLCPP_INFO(this->get_logger(), "执行右手握手姿势");
                        dual_arm_group_->setMaxVelocityScalingFactor(0.6);
                        dual_arm_group_->setMaxAccelerationScalingFactor(0.4);
                        all_success = executeMovement(dual_arm_group_, convertToRadians(right_shank_angles_));
                        response->success = all_success;
                        response->message = all_success ? "右手握手姿势执行成功" : "右手握手姿势执行失败";
                        rclcpp::sleep_for(std::chrono::seconds(1));
                        talk_flag = true; 
                        break;

                    case 7:  
                        talk_flag = false; 
                        RCLCPP_INFO(this->get_logger(), "执行左挥手动作序列");
                        dual_arm_group_->setMaxVelocityScalingFactor(0.4);
                        dual_arm_group_->setMaxAccelerationScalingFactor(0.4);
                        all_success = true;  // 重置为 true
                        for (const auto &wave_position : talk_angles_) {
                            if (!executeMovement(dual_arm_group_, convertToRadians(wave_position))) {
                                all_success = false;
                                break;
                            }
                        }
                        response->success = all_success;
                        response->message = all_success ? "左挥手动作执行成功" : "左挥手动作执行失败";
                        rclcpp::sleep_for(std::chrono::seconds(1));
                        talk_flag = true; 
                        break;
                    

                    default:
                        RCLCPP_WARN(this->get_logger(), "无效的预设动作类型: %d", request->action_fixed);
                        response->success = false;
                        response->message = "无效的预设动作类型";
                        break;
                }
                break;
            }
            default: {
                RCLCPP_WARN(this->get_logger(), "无效的任务类型: %d", up_climb_resquest_type);
                response->success = false;
                response->message = "无效的任务类型";
                break;
            }
        }
    }


private:
    // 成员变量
    rclcpp::TimerBase::SharedPtr timer_;
    rclcpp::Publisher<std_msgs::msg::Int8>::SharedPtr arms_state_publisher_;
    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr upper_body_data_subscriber_;
    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr up_climb_stop_sub_{}; // 上肢动作取消\暂停\继续sub
    rclcpp::Service<ymrobot_msgs::srv::UpLimb>::SharedPtr up_climb_service_{};   // 上肢动作服务端
    std::shared_ptr<moveit::planning_interface::MoveGroupInterface> dual_arm_group_;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sound_detected_sub_;
    std::vector<double> deliver_angles_, left_introduce_angles_,right_introduce_angles_,left_shank_angles_,right_shank_angles_,zero_angles_;
    std::vector<std::vector<double>> left_wave_angles_,right_wave_angles_,qiangjinjiu_angles_,shudaonan_angles_,shanzhongwenda_angles_,anlu_angles_,talk_angles_; // 合并的挥手动作轨迹
    bool move_groups_initialized_ = false;
    bool need_arm_init = false; //暂停服务
    bool talk_flag = true ;
    bool sound_flag = false;
    bool arm_flag = false;
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    auto controller = std::make_shared<AutoDualArmController>();
    rclcpp::spin(controller);
    return 0;
}
