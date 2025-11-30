#include <rclcpp/rclcpp.hpp>
#include <cmath>
#include <vector>
#include <iostream>
#include <signal.h>
#include "ymbot_hardware_driver/ymbot_joint_eu.h"
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/int32_multi_array.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <thread>
#include <atomic>

using namespace std::chrono_literals;

class NeckControlNode : public rclcpp::Node {
public:
  NeckControlNode() : Node("neck_control_node") {
    // 初始化电机
    initialize_motors();

    // 创建订阅器
    sound_sub_ = this->create_subscription<std_msgs::msg::Bool>(
      "/sound_detected", 10,
      [this](const std_msgs::msg::Bool::SharedPtr msg) {
        audio_input_flag_ = msg->data;
      });

    keyboard_sub_ = this->create_subscription<std_msgs::msg::Int32MultiArray>(
      "/sbus_data", 10,
      [this](const std_msgs::msg::Int32MultiArray::SharedPtr msg) {
        if (msg->data[3] == 1) {
          talk_flag_ = true;
        } else if(msg->data[3] == -1){
          talk_flag_ = false;
        }
        if(msg->data[1] == 1){
          move_flag_ = true;
        }else{
          move_flag_ = false;
        }
        if(msg->data[4] == 1){
          control_flag_ = 1;
        }else if (msg->data[4] == -1){
          control_flag_ = -1;
        }else{
          control_flag_ = 0;
        }
      });

    control_sub_ = this->create_subscription<std_msgs::msg::Float64MultiArray>(
      "/target_rel_angles", 10,
      [this](const std_msgs::msg::Float64MultiArray::SharedPtr msg) {
        if (!talk_flag_) {
          RCLCPP_INFO(this->get_logger(), "Motor control disabled");
          return;
        }
        horizontal_ = msg->data[0];
        vertical_ = msg->data[1];
      });

    // 启动控制线程
    control_thread_ = std::thread(&NeckControlNode::neck_control, this);
  }

  ~NeckControlNode() {
    run_flag_.store(false);
    if (control_thread_.joinable()) {
      control_thread_.join();
    }
  }

private:
  // 类成员变量
  std::vector<YmbotJointEu> motor_{1};
  std::atomic<bool> talk_flag_{true};
  std::atomic<bool> move_flag_{false};
  std::atomic<bool> run_flag_{true};
  bool audio_input_flag_ = false;
  float horizontal_ = 0;
  float vertical_ = 0;
  int control_flag_ = 0;

  // ROS2订阅器
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sound_sub_;
  rclcpp::Subscription<std_msgs::msg::Int32MultiArray>::SharedPtr keyboard_sub_;
  rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr control_sub_;
  std::thread control_thread_;

  void initialize_motors() {
    int id_array[] = {22};
    int n_motor_group = 1;
    int n_motors = sizeof(id_array)/sizeof(id_array[0]);
    int channel = 0;

    for (int devIndex = 1; devIndex < n_motor_group + 1 ; devIndex++) {
      if (PLANET_SUCCESS != planet_initDLL(planet_DeviceType_Canable, devIndex, channel, planet_Baudrate_1000)) {
        RCLCPP_ERROR(this->get_logger(), "Canable %d init failed", devIndex);
        return;
      }
    }

    for (int i = 0; i < n_motors; i++) {
      motor_[i].motor_id = id_array[i];
      motor_[i].dev_index = 1;

      if (motor_[i].motor_initialization_CSP()) {
        RCLCPP_INFO(this->get_logger(), "Motor %d init success", motor_[i].motor_id);
      } else {
        RCLCPP_ERROR(this->get_logger(), "Motor %d init failed", motor_[i].motor_id);
        return;
      }
    }
    RCLCPP_INFO(this->get_logger(), "All motors initialized");
  }

  void smooth_move_motor(int motor_id, float target_position, float speed) {
    for (auto& m : motor_) {
      if (m.motor_id == motor_id) {
        float current_position;
        if (PLANET_SUCCESS != planet_getPosition(m.dev_index, m.motor_id, &current_position)) {
          RCLCPP_ERROR(this->get_logger(), "Failed get pos: %d", m.motor_id);
          return;
        }

        float position_diff = target_position - current_position;
        float step = (position_diff > 0) ? std::min(position_diff, speed) 
                                        : std::max(position_diff, -speed);
                                        
        while (std::abs(target_position - current_position) > std::abs(step)) {
          current_position += step;
          if (PLANET_SUCCESS != planet_quick_setTargetPosition(m.dev_index, m.motor_id, 
                                                              static_cast<int>(current_position))) {
            RCLCPP_ERROR(this->get_logger(), "Move failed: %d", m.motor_id);
            return;
          }
          rclcpp::sleep_for(60ms);
        }

        if (PLANET_SUCCESS != planet_quick_setTargetPosition(m.dev_index, m.motor_id, target_position)) {
          RCLCPP_ERROR(this->get_logger(), "Final pos failed: %d", m.motor_id);
          return;
        }
        RCLCPP_INFO(this->get_logger(), "Motor %d moved to %.2f", m.motor_id, target_position);
        return;
      }
    }
  }

  void neck_control() {
    std::vector<int> action_sequences = {0, 1, 2, 3, 4, 5};
    std::srand(time(0));
    bool first_run = true;
    auto run_flag_start_time = this->now();
    auto last_execution_time = this->now();

    while (rclcpp::ok() && run_flag_.load()) {
      if (audio_input_flag_) {
        if (first_run) {
          run_flag_start_time = this->now();
          first_run = false;
        }

        if ((this->now() - run_flag_start_time).seconds() < 3.0) {
          rclcpp::sleep_for(100ms);
          continue;
        }

        if ((this->now() - last_execution_time).seconds() < 5.0) {
          rclcpp::sleep_for(100ms);
          continue;
        }

        if (action_sequences.empty()) {
          action_sequences = {0, 1, 2, 3, 4, 5};
        }

        int random_index = rand() % action_sequences.size();
        int action_sequence = action_sequences[random_index];
        action_sequences.erase(action_sequences.begin() + random_index);

        switch (action_sequence) {
            case 0:
                smooth_move_motor(22, 275, 1.5);
                rclcpp::sleep_for(std::chrono::milliseconds(2000));
                smooth_move_motor(22, 290, 2);
                rclcpp::sleep_for(std::chrono::milliseconds(1000));
                break;
            case 1:
                smooth_move_motor(22, 305, 1.5);
                rclcpp::sleep_for(std::chrono::milliseconds(2000));
                smooth_move_motor(22, 290, 2);
                rclcpp::sleep_for(std::chrono::milliseconds(1000));
                break;
            case 2:
                smooth_move_motor(22, 275, 1.5);
                rclcpp::sleep_for(std::chrono::milliseconds(2000));
                smooth_move_motor(22, 305, 1.5);
                rclcpp::sleep_for(std::chrono::milliseconds(2000));
                smooth_move_motor(22, 290, 2);
                rclcpp::sleep_for(std::chrono::milliseconds(1000));
                break;
            case 3:
                smooth_move_motor(22, 280, 1.5);
                rclcpp::sleep_for(std::chrono::milliseconds(2000));
                smooth_move_motor(22, 290, 2);
                rclcpp::sleep_for(std::chrono::milliseconds(1000));
                break;
            case 4:
                smooth_move_motor(22, 300, 1.5);
                rclcpp::sleep_for(std::chrono::milliseconds(2000));
                smooth_move_motor(22, 290, 2);
                rclcpp::sleep_for(std::chrono::milliseconds(1000));
                break;
            case 5:
                smooth_move_motor(22, 280, 1.5);
                rclcpp::sleep_for(std::chrono::milliseconds(2000));
                smooth_move_motor(22, 300, 1.5);
                rclcpp::sleep_for(std::chrono::milliseconds(2000));
                smooth_move_motor(22, 290, 2);
                rclcpp::sleep_for(std::chrono::milliseconds(1000));
                break;
        }

        last_execution_time = this->now();
      }
      rclcpp::sleep_for(50ms);
    }
  }
};

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<NeckControlNode>();
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();
  rclcpp::shutdown();
  return 0;
}





