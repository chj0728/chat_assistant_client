#include "ymbot_hardware_driver/ymbot_hands_RTrobot_api.h"
#include <atomic>
#include <chrono>
#include <mutex>
#include <thread>
#include <iostream>
#include <string>
#include <random>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include <std_msgs/msg/int32_multi_array.hpp>
#include <std_msgs/msg/int8.hpp>
#include <std_msgs/msg/string.hpp>
std::string left_hand_serial_port;
std::string right_hand_serial_port;
std::atomic<bool> run_flag(true);
vector<int> servos_id = {1, 2, 3, 4, 5, 6};
std::atomic<bool> bow_flag(false);
std::atomic<bool> lead_way_left(false);
std::atomic<bool> lead_way_right(false);
std::atomic<bool> left_hand_dev_received(false);
std::atomic<bool> right_hand_dev_received(false);
std::atomic<int8_t> arms_state(0);  // 使用int8_t存储手臂状态
int arms_flag = 0 ;
// Set max and min positions
vector<int> servos_left_max_position = {1650, 1650, 1650, 1650, 1650, 1500};
vector<int> servos_left_min_position = {1500, 1500, 1500, 1500, 1500, 1500};
vector<int> servos_right_max_position = {1500, 1500, 1500, 1500, 1500, 1500};
vector<int> servos_right_min_position = {1350, 1350, 1350, 1350, 1350, 1500};

// hands positions
vector<int> left_hand_open = {1500, 1500, 1500, 1500, 1500, 1500};
vector<int> left_hand_close = {1600, 1600, 1600, 1600, 1600, 1500};

vector<int> right_hand_open = {1500, 1500, 1500, 1500, 1500, 1500};
vector<int> right_hand_close = {1400, 1400, 1400, 1400, 1400, 1500};

// Initial positions
vector<int> left_hand_target_positions = left_hand_open;
vector<int> right_hand_target_positions = right_hand_open;

// Instantiate the RTrobot_hands object
RTrobot_hands left_hand_servo(servos_id, servos_left_max_position, servos_left_min_position);
RTrobot_hands right_hand_servo(servos_id, servos_right_max_position, servos_right_min_position);


void left_hand_dev_callback(const std_msgs::msg::String::SharedPtr msg, rclcpp::Node::SharedPtr node) {
    if (msg->data != "not_found") {
        left_hand_serial_port = msg->data;
        left_hand_dev_received.store(true);
        // RCLCPP_INFO(node->get_logger(), "Received left_hand device port: %s", left_hand_serial_port.c_str());
    } else {
        RCLCPP_WARN(node->get_logger(), "left_hand device not found!");
    }
}

void right_hand_dev_callback(const std_msgs::msg::String::SharedPtr msg, rclcpp::Node::SharedPtr node) {
    if (msg->data != "not_found") {
        right_hand_serial_port = msg->data;
        right_hand_dev_received.store(true);
        // RCLCPP_INFO(node->get_logger(), "Received right_hand device port: %s", right_hand_serial_port.c_str());
    } else {
        RCLCPP_WARN(node->get_logger(), "right_hand device not found!");
    }
}


void arms_state_callback(const std_msgs::msg::Int8::SharedPtr msg)
{
    // 更新手臂状态
    arms_flag = msg->data;
    RCLCPP_INFO(rclcpp::get_logger("arms_state_logger"), "收到手臂状态: %d", msg->data);
}


void left_hand_action(rclcpp::Node::SharedPtr node)
{
    while (run_flag)
    {
    // left_hand_servo.run_action_group(1);
    //     std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    //     std::cout << "111" << std::endl;
    // left_hand_servo.run_action_group(2);
    //     std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    auto start_wait = std::chrono::steady_clock::now();
    while (!left_hand_dev_received.load() && 
           std::chrono::steady_clock::now() - start_wait < std::chrono::seconds(10) &&
           rclcpp::ok()) {
        RCLCPP_INFO_ONCE(node->get_logger(), "Waiting for left_hand_dev topic...");
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    if (!left_hand_dev_received.load()) {
        // RCLCPP_ERROR(node->get_logger(), "Timeout waiting for left_hand_dev topic! Using default port.");
        left_hand_serial_port = "/dev/ttyCH341USB1"; // 默认值
    }

    if (!left_hand_servo.initialization(left_hand_serial_port.c_str()))
    {
        return ;
    }
        int8_t current_state = arms_flag;
        
        switch(current_state) {
            case 0:  // 初始位置手势
                left_hand_servo.run_action_group(1);
                break;
            case 1:  // 挥手手势
                left_hand_servo.run_action_group(1);
                break;
            case 2:  // 挥手手势
                left_hand_servo.run_action_group(1);
                break;
            case 3:  // 介绍手势
                left_hand_servo.run_action_group(1);
                break;
            case 4:  // 介绍手势
                left_hand_servo.run_action_group(1);
                break;
            case 5:  // 介绍手势
                left_hand_servo.run_action_group(20);
                break;
            case 6:  // 介绍手势
                left_hand_servo.run_action_group(1);
                break;
                
            default:
                break;
        }
        
        std::this_thread::sleep_for(std::chrono::milliseconds(1000)); // 控制执行间隔
    }
    // 程序退出时执行动作组2
    left_hand_servo.run_action_group(1);
}

void right_hand_action(rclcpp::Node::SharedPtr node)
{
    auto start_wait = std::chrono::steady_clock::now();
    while (!right_hand_dev_received.load() && 
           std::chrono::steady_clock::now() - start_wait < std::chrono::seconds(10) &&
           rclcpp::ok()) {
        RCLCPP_INFO_ONCE(node->get_logger(), "Waiting for right_hand_dev topic...");
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    if (!right_hand_dev_received.load()) {
        RCLCPP_ERROR(node->get_logger(), "Timeout waiting for right_hand_dev topic! Using default port.");
        right_hand_serial_port = "/dev/ttyCH341USB0"; // 默认值
    }

    if (!right_hand_servo.initialization(right_hand_serial_port.c_str()))
    {
        return ;
    }

    while (run_flag)
    {
        // right_hand_servo.run_action_group(1);
        // std::this_thread::sleep_for(std::chrono::milliseconds(1000));
        // right_hand_servo.run_action_group(2);
        // std::this_thread::sleep_for(std::chrono::milliseconds(1000));
        int8_t current_state = arms_flag;
        
        switch(current_state) {
            case 0:  // 初始位置手势
                right_hand_servo.run_action_group(1);
                break;
            case 1:  // 挥手手势
                right_hand_servo.run_action_group(1);
                break;
            case 2:  // 挥手手势
                right_hand_servo.run_action_group(1);
                break;
            case 3:  // 介绍手势
                right_hand_servo.run_action_group(1);
                break;
            case 4:  // 介绍手势
                right_hand_servo.run_action_group(1);
                break;
            case 5:  // 介绍手势
                right_hand_servo.run_action_group(1);
                break;
            case 6:  // 介绍手势

                right_hand_servo.run_action_group(17);
                break;
            default:
                break;
        }
        
        std::this_thread::sleep_for(std::chrono::milliseconds(1000)); // 控制执行间隔
    }

    // 程序退出时执行动作组2
    right_hand_servo.run_action_group(1);
}

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<rclcpp::Node>("ymbot_xiaoxue_hands");

    // 获取从 launch 文件中传递的参数，默认值是 "/dev/ttyACM0"
    // node->declare_parameter("left_hand_serial_port", "/dev/ttyCH341USB0");
    // node->get_parameter("left_hand_serial_port", left_hand_serial_port);

    // node->declare_parameter("right_hand_serial_port", "/dev/ttyCH341USB2");
    // node->get_parameter("right_hand_serial_port", right_hand_serial_port);
    // RCLCPP_INFO(node->get_logger(), "Using serial port: %s", left_hand_serial_port.c_str());
    // RCLCPP_INFO(node->get_logger(), "Using serial port: %s", right_hand_serial_port.c_str());
    auto left_hand_dev_sub = node->create_subscription<std_msgs::msg::String>(
        "left_hand_dev",
        10,
        [&](const std_msgs::msg::String::SharedPtr msg) {
            left_hand_dev_callback(msg, node);
        });
    auto right_hand_dev_sub = node->create_subscription<std_msgs::msg::String>(
        "right_hand_dev",
        10,
        [&](const std_msgs::msg::String::SharedPtr msg) {
            right_hand_dev_callback(msg, node);
        });

    // 订阅arms_state话题
    auto arms_state_sub = node->create_subscription<std_msgs::msg::Int8>(
        "arms_state", 
        10, 
        [&](const std_msgs::msg::Int8::SharedPtr msg) {
            arms_state_callback(msg);
        }
    );


    // Initialize communication
    // if (!left_hand_servo.initialization(left_hand_serial_port.c_str()))
    // {
    //     return 0;
    // }

    // if (!right_hand_servo.initialization(right_hand_serial_port.c_str()))
    // {
    //     return 0;
    // }

    // 启动两个线程来控制左右手
    // std::thread t_left(left_hand_action);
    // std::thread t_right(right_hand_action);
    std::thread t_left([&]() {
        left_hand_action(node);
    });
    std::thread t_right([&]() {
        right_hand_action(node);
    });
    t_left.detach();
    t_right.detach();


    rclcpp::spin(node);   // 进入循环，等待回调

    run_flag.store(false);
    // this_thread::sleep_for(chrono::seconds(5));
    right_hand_servo.run_action_group(1);
    left_hand_servo.run_action_group(1);
    return 0;
}