#include "ymbot_hardware_driver/ymbot_head_RTrobot_api.h"

#include <atomic>
#include <chrono>
#include <mutex>
#include <thread>
#include <iostream>
#include <string>
#include <random>
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/int32_multi_array.hpp>
#include <ymrobot_msgs/srv/emoji.hpp>
#include <std_msgs/msg/int8.hpp>
std::atomic<bool> run_flag(true);
bool audio_input_flag = false;
bool audio_input_flag2 = false;
std::string head_serial_port;

std::atomic<bool> head_dev_received(false);
// rclcpp::Time last_zero_time;   // 记录上次 horizontal 和 vertical 不为 0 的时间
// rclcpp::Time audio_input_start_time; // 记录 audio_input_flag 满足的时间点
rclcpp::Clock clock_;
rclcpp::Time last_zero_time = clock_.now();
rclcpp::Time audio_input_start_time = clock_.now();
rclcpp::Service<ymrobot_msgs::srv::EMOJI>::SharedPtr emoji_service_{};
int face_flag = 0 ;
bool follow_up_action_executed = false; // 标记是否已经执行了后续动作组
int  app_flag = -1;
int random_delay = 0; // 随机延迟时间（5 到 8 秒）
int normal_counter = 0;
std::vector<int> servo_ids = {1, 2, 3, 4, 13, 17, 18, 19, 20};

    std::vector<int> max_positions = {1588, 1618, 1794, 1853, 1647, 1706, 1824, 1706, 1294};
    std::vector<int> min_positions = {1382, 1353, 1382, 1500, 1471, 1441, 1500, 1206, 1029};
    std::vector<int> open_mouse_eyeson = {1529, 1500, 1794, 1853, 1600, 1559, 1550, 1206,1029};
    std::vector<int> open_mouse_eyeson1 = {1529, 1500, 1794, 1853, 1610, 1559, 1550, 1206,1029};
    std::vector<int> open_mouse_eyeson2 = {1529, 1500, 1794, 1853, 1590, 1559, 1550, 1206,1029};
    std::vector<int> close_mouse_eyeson = {1529, 1500,1794, 1853,1499,1559, 1550,1206,1029};
    std::vector<int> close_mouse_eyeson1 = {1529, 1500,1794, 1853,1481,1559, 1550,1206,1029};
    std::vector<int> open_mouse_eyesoff = {1529, 1500,1382, 1500,1600,1559, 1550,1706,1294};
    std::vector<int> close_mouse_eyesoff = {1529, 1500,1382, 1500,1471,1559, 1550,1706,1294};
    // 创建随机选择容器
    std::vector<std::vector<int>> open_actions = {open_mouse_eyeson, open_mouse_eyeson1, open_mouse_eyeson2};
    std::vector<std::vector<int>> close_actions = {close_mouse_eyeson, close_mouse_eyeson1};

    // 初始化随机数引擎
    // std::random_device rd;
    // std::mt19937 gen(rd());
    // std::uniform_int_distribution<int> open_dist(0, open_actions.size()-1);
    // std::uniform_int_distribution<int> close_dist(0, close_actions.size()-1);

    const std::vector<std::string> SHANJIAN_ACTIONS ={
        
       

    };
    const std::vector<std::string> ANLUSHAN_ACTIONS ={
        


    };



    const std::vector<std::string> QIANGJINJIU_ACTIONS ={

        

    };


    const std::vector<std::string> SHUDAONAN_ACTIONS ={

        
    };


    RTrobot robot(servo_ids, max_positions, min_positions);
    // RTrobot robot(servo_ids, max_positions, min_positions);

void set_thread_priority(std::thread& thread, int priority, int cpu_core, rclcpp::Node::SharedPtr node) {
    pthread_t nativeHandle = thread.native_handle();

    // 设置线程优先级
    int policy = SCHED_FIFO;
    struct sched_param param;
    param.sched_priority = priority;
    int result = pthread_setschedparam(nativeHandle, policy, &param);
    if (result != 0) {
        RCLCPP_ERROR_STREAM(node->get_logger(), "Failed to set thread priority for thread ID " << pthread_self()
                                                                        << ". Error code: " << result);
    }
    else {
        RCLCPP_INFO_STREAM(node->get_logger(), "Successfully set thread priority for thread ID " << pthread_self());
    }

    // 设置 CPU 亲和性
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(cpu_core, &cpuset);
    result = pthread_setaffinity_np(nativeHandle, sizeof(cpu_set_t), &cpuset);
    if (result != 0) {
        RCLCPP_ERROR_STREAM(node->get_logger(), "Failed to set CPU affinity for thread ID " << pthread_self() << ". Error code: " << result);
    }
    else {
        RCLCPP_INFO_STREAM(node->get_logger(), "Successfully set CPU affinity for thread ID " << pthread_self());
    }
}

void head_dev_callback(const std_msgs::msg::String::SharedPtr msg, rclcpp::Node::SharedPtr node) {
    if (msg->data != "not_found") {
        head_serial_port = msg->data;
        head_dev_received.store(true);
        // RCLCPP_INFO(node->get_logger(), "Received head device port: %s", head_serial_port.c_str());
    } else {
        RCLCPP_WARN(node->get_logger(), "Head device not found!");
    }
}

void face_state_callback(const std_msgs::msg::Int8::SharedPtr msg)
{
    // 更新面部状态
    face_flag = msg->data;
    // RCLCPP_INFO(rclcpp::get_logger("arms_state_logger"), "收到面部状态: %d", face_flag);
}

//  检测输入声音大小的回调函数
void sound_detected_callback(const std_msgs::msg::Bool::SharedPtr msg) {
    audio_input_flag = msg->data;
}
void sound_data_callback(const std_msgs::msg::Bool::SharedPtr msg) {
    audio_input_flag2 = msg->data;
}
// void face_data_callback(const std_msgs::msg::String::SharedPtr msg) {
//     // 接收字符串消息
//     app_flag = std::stoi(msg->data);
//     std::cout << "The integer value is: " << app_flag << std::endl;
// }

// 表情服务回调函数
void EmojiActionServiceCallback(
    const std::shared_ptr<ymrobot_msgs::srv::EMOJI::Request> request,
        std::shared_ptr<ymrobot_msgs::srv::EMOJI::Response> response) 
{

    bool success = false;
    
    // 根据action_code执行对应动作组
    // switch(request->action_code) {  // 使用与hello代码一致的字段名
    //     case 0:  // 眨眼
    //         success = robot.run_action_group(0);
    //         response->message = success ? "眨眼动作执行成功" : "眨眼动作执行失败";
    //         break;
    //     case 1:  // 眼球转动
    //         success = robot.run_action_group(1);
    //         response->message = success ? "眼球转动执行成功" : "眼球转动执行失败";
    //         break;
    //     case 2:  // 微笑
    //         success = robot.run_action_group(12);
    //         response->message = success ? "微笑动作执行成功" : "微笑动作执行失败";
    //         break;
    //     case 3:  // 张嘴
    //         success = robot.run_action_group(9);
    //         response->message = success ? "张嘴动作执行成功" : "张嘴动作执行失败";
    //         break;
    //     case 4:  // 其他动作
    //         success = robot.run_action_group(10);
    //         response->message = success ? "动作执行成功" : "动作执行失败";
    //         break;
    //     case 5:  // 眨眼（另一只眼）
    //         success = robot.run_action_group(11);
    //         response->message = success ? "眨眼动作执行成功" : "眨眼动作执行失败";
    //         break;
    //     default:
    //         response->message = "无效的动作码";
    //         success = false;
    //         break;
    // }
    
    response->success = success;
}


bool  talk_flag = true; 


mutex mtx; // 用于保护对target_positions的访问


// 面部动作，后面用多线程启动
void face_action_function(rclcpp::Node::SharedPtr node) {

    auto start_wait = std::chrono::steady_clock::now();
    while (!head_dev_received.load() && 
           std::chrono::steady_clock::now() - start_wait < std::chrono::seconds(10) &&
           rclcpp::ok()) {
        RCLCPP_INFO_ONCE(node->get_logger(), "Waiting for head_dev topic...");
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    if (!head_dev_received.load()) {
        RCLCPP_ERROR(node->get_logger(), "Timeout waiting for head_dev topic! Using default port.");
        head_serial_port = "/dev/ttyCH341USB2"; // 默认值
    }

    if (false == robot.initialization(head_serial_port.c_str())) {
        return;
    }

    int target_velocity = 500;
    // int delay_time = 500;
    int time_k = 0;


    target_velocity = 150;
    // delay_time = 2;
    bool is_talking = true;
    bool no_talking = false;
    bool should_stop_group = true;
    int test_count = 0;
    bool has_executed = false;

    auto last_action_time = chrono::steady_clock::now();
    const chrono::seconds action_interval(8); // 8秒间隔
    // 定时器变量，记录上次执行时间,保证动作组执行完毕
    auto last_execution_time = chrono::steady_clock::now();
    const chrono::seconds required_duration(30); // 持续时间：35秒

    while (run_flag) {

        // RCLCPP_INFO(rclcpp::get_logger("arms_state_logger"), "%d", face_flag);
        switch (face_flag)
        {
        case 7:
            for (const auto& action : SHUDAONAN_ACTIONS) {
                robot.send_raw_action(action);  // 需要RTrobot类添加这个方法
                this_thread::sleep_for(chrono::milliseconds(33));
                // cout << "!!!!!" << endl;
            }
            face_flag = 0 ;
            this_thread::sleep_for(chrono::milliseconds(4000));
            break;

            
        case 8:
            for (const auto& action : QIANGJINJIU_ACTIONS) {
                robot.send_raw_action(action);  // 需要RTrobot类添加这个方法
                this_thread::sleep_for(chrono::milliseconds(33));
                // cout << "!!!!!" << endl;
            }
            face_flag = 0 ;
            this_thread::sleep_for(chrono::milliseconds(2000));
            break;

        case 9:
            this_thread::sleep_for(chrono::milliseconds(1000));
            for (const auto& action : SHANJIAN_ACTIONS) {
                robot.send_raw_action(action);  // 需要RTrobot类添加这个方法
                this_thread::sleep_for(chrono::milliseconds(33));
                // cout << "!!!!!" << endl;
            }
            face_flag = 0 ;
            this_thread::sleep_for(chrono::milliseconds(1000));
            break;

        case 10:
            for (const auto& action : ANLUSHAN_ACTIONS) {
                robot.send_raw_action(action);  // 需要RTrobot类添加这个方法
                this_thread::sleep_for(chrono::milliseconds(33));
                // cout << "!!!!!" << endl;
            }
            face_flag = 0 ;
            this_thread::sleep_for(chrono::milliseconds(1000));
            break;

        default:
            break;
        }
        if ( !audio_input_flag && !audio_input_flag2) {
            // 如果 horizontal 和 vertical 同时为 0，记录时间
            if ((clock_.now() - last_zero_time).seconds() >= 60) {
                // 如果已经超过 10秒，执行平稳回到默认位置
                talk_flag = false ;
                no_talking = true ;
            }
        } else {
            // 如果 horizontal 或 vertical 不是 0，重置 last_zero_time
            last_zero_time = clock_.now();
            talk_flag = true;
            no_talking = false;
        }

        if(talk_flag){
            // robot.stop_action();
            if (audio_input_flag || audio_input_flag2) {
                if(should_stop_group){
                    this_thread::sleep_for(chrono::milliseconds(50));
                    robot.stop_action();
                    this_thread::sleep_for(chrono::milliseconds(50));
                    should_stop_group = false;
                }
                // auto& selected_open = open_actions[open_dist(gen)];
                // auto& selected_close = close_actions[close_dist(gen)];
                auto current_time = chrono::steady_clock::now();
                robot.run_action_group(3);
                
                    if (current_time - last_action_time >= action_interval) {
                        this_thread::sleep_for(chrono::milliseconds(50));
                        robot.stop_action();
                        this_thread::sleep_for(chrono::milliseconds(50));
                        robot.run_action_group(4);
                        this_thread::sleep_for(chrono::milliseconds(50));
                        
                        last_action_time = current_time;

                    // }
                    }
            }
        else{

                follow_up_action_executed = false; // 重置标记
            }
            
        }
        else if(no_talking){

            auto current_time = chrono::steady_clock::now();
            if (current_time - last_execution_time >= required_duration) {
                if(!should_stop_group){
                    this_thread::sleep_for(chrono::milliseconds(50));
                    robot.stop_action();
                    this_thread::sleep_for(chrono::milliseconds(50));
                    should_stop_group = true;
                }
                
                
                robot.run_action_group(1);
                // 更新上次执行时间
                last_execution_time = current_time;
            }
        }
     
        test_count ++;

    }
    // robot.stop_action();
    // this_thread::sleep_for(chrono::milliseconds(50));
    // robot.run_action_group(2);
    // robot.control_servos(close_mouse_eyeson,90);
}

int main(int argc, char** argv) {

    rclcpp::init(argc, argv);
    auto node = std::make_shared<rclcpp::Node>("ymbot_xiaoxue_face_expression");

    // // 获取从 launch 文件中传递的参数，默认值是 "/dev/ttyACM0"
    // node->declare_parameter("head_serial_port", "/dev/ttyCH341USB1");
    // node->get_parameter("head_serial_port", head_serial_port);
    // RCLCPP_INFO(node->get_logger(), "Using serial port: %s", head_serial_port.c_str());
    // nh.param<std::string>("head_serial_port", head_serial_port, "/dev/ttyACM1");
    // RCLCPP_INFO("Using serial port: %s", head_serial_port.c_str());

    // ros::Subscriber sub_1 = nh.subscribe("/sbus_data", 1, keyboard_callback);
    auto head_dev_sub = node->create_subscription<std_msgs::msg::String>(
        "head_dev",
        10,
        [&](const std_msgs::msg::String::SharedPtr msg) {
            head_dev_callback(msg, node);
        });

    auto face_state_sub = node->create_subscription<std_msgs::msg::Int8>(
        "arms_state", 
        10, 
        [&](const std_msgs::msg::Int8::SharedPtr msg) {
            face_state_callback(msg);
        }
    );

    auto sub_1 = node->create_subscription<std_msgs::msg::Bool>(
        "/sound_detected", 
        10, 
        [&](const std_msgs::msg::Bool::SharedPtr msg) {
            sound_detected_callback(msg);
        }
    );
    auto sub_2 = node->create_subscription<std_msgs::msg::Bool>(
        "/sound_data", 
        10, 
        [&](const std_msgs::msg::Bool::SharedPtr msg) {
            sound_data_callback(msg);
        }
    );
    // auto sub_2 = node->create_subscription<std_msgs::msg::String>(
    //     "/face_data", 
    //     10, 
    //     [&](const std_msgs::msg::String::SharedPtr msg) {
    //         face_data_callback(msg);
    //     }
    // );
    auto emoji_service_ = node->create_service<ymrobot_msgs::srv::EMOJI>(
        "emoji_srv",
        &EmojiActionServiceCallback);


    // std::thread t_face_action(face_action_function);
    std::thread t_face_action([&]() {
        face_action_function(node);
    });
    t_face_action.detach();

    rclcpp::spin(node);   // 进入循环，等待回调

    run_flag.store(false);
    // cout << "0" << endl;
    this_thread::sleep_for(chrono::seconds(5));


    return 0;
}