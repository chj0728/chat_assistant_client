#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <termios.h>
#include <unistd.h>
#include <iostream>
#include <thread>

#include <geometry_msgs/msg/twist.hpp>
#include <rclcpp/rclcpp.hpp>
#include "std_msgs/msg/bool.hpp"

#include <ymrobot_msgs/msg/upper.hpp>
#include <ymrobot_msgs/msg/control_mode.hpp>

#define KEYCODE_RIGHT_ARROW 0x43
#define KEYCODE_LEFT_ARROW 0x44
#define KEYCODE_UP_ARROW 0x41
#define KEYCODE_DOWN_ARROW 0x42
#define KEYCODE_Q 0x71
#define KEYCODE_Z 0x7A
#define KEYCODE_E 0x65
#define KEYCODE_C 0x63
#define KEYCODE_W 0x77
#define KEYCODE_A 0x61
#define KEYCODE_S 0x73
#define KEYCODE_D 0x64
#define KEYCODE_B 0x62
#define KEYCODE_N 0x6E
#define KEYCODE_M 0x6D
#define KEYCODE_O 0x6F
#define KEYCODE_P 0x70
#define KEYCODE_SPACE 0x20
#define VALUE_SCALE 0.25
#define VALUE_CHANGE_SCALE 0.05
#define ANGULAR_MAX 0.5
#define ANGULAR_MIN 0.05
#define LINEAR_MAX 0.5
#define LINEAR_MIN 0.05
#define PUB_RATE 20
#define AUTOMODE_ON 0x01
#define AUTOMODE_OFF 0x00
#define CHASSIS_DISABLE 0x00
#define CHASSIS_ENABLE 0x01

using namespace std;

class Keyboard : public rclcpp::Node
{
public:
    Keyboard(const std::string &name);
    ~Keyboard() = default;

    void Loop();
    void PubThread();

private:
    void PrintStatus()
    {
        RCLCPP_INFO(this->get_logger(),
                    "currently:  speed %.2f  turn %.2f  chassis:%s  auto_mode:%s",
                    linear_scale_, angular_scale_,
                    motion_status_ ? "ENABLE" : "DISABLE ",
                    auto_mode_ ? "ON" : "OFF");
    }

private:
    /* data */
    double linear_ = 0., angular_ = 0., linear_scale_ = 0., angular_scale_ = 0.,
           linear_change_scale_ = 0., angular_change_scale_ = 0.;
    float value_scale_ = 0., angular_max_ = 0., angular_min_ = 0.,
          linear_max_ = 0., linear_min_ = 0.;
    std::atomic<bool> motion_status_{false};
    std::atomic<bool> auto_mode_{false};
    rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr vel_publisher_;
    rclcpp::Publisher<ymrobot_msgs::msg::Upper>::SharedPtr ymrobot_status_publisher_;
    rclcpp::Publisher<ymrobot_msgs::msg::ControlMode>::SharedPtr key_control_mode_publisher_{}; // 电机控制模式选择-- 手动控制
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr mortor_enable_publisher_{};               // 电机使能
    geometry_msgs::msg::Twist vel_msg_;
    ymrobot_msgs::msg::Upper status_msg_;
    std::atomic<bool> is_alive_{false};
    int32_t pub_rate_ = 0;
};

Keyboard::Keyboard(const std::string &name) : Node(name)
{
    if (this->get_parameter("LINEAR_SCALE", linear_scale_))
        RCLCPP_INFO(this->get_logger(), "[hintonbot_keyboard] LINEAR_SCALE is %.2f",
                    linear_scale_);
    else
    {
        linear_scale_ = VALUE_SCALE;
        RCLCPP_WARN(this->get_logger(),
                    "[hintonbot_keyboard] didn't find parameter LINEAR_SCALE, "
                    "default value %.2f",
                    linear_scale_);
    }
    if (this->get_parameter("ANGULAR_SCALE", angular_scale_))
        RCLCPP_INFO(this->get_logger(),
                    "[hintonbot_keyboard] ANGULAR_SCALE is %.2f", angular_scale_);
    else
    {
        angular_scale_ = VALUE_SCALE;
        RCLCPP_WARN(this->get_logger(),
                    "[hintonbot_keyboard] didn't find parameter ANGULAR_SCALE, "
                    "default value %.2f",
                    angular_scale_);
    }

    if (this->get_parameter("LINEAR_CHANGE_SCALE", linear_change_scale_))
        RCLCPP_INFO(this->get_logger(),
                    "[hintonbot_keyboard] LINEAR_CHANGE_SCALE is %.2f",
                    linear_change_scale_);
    else
    {
        linear_change_scale_ = VALUE_CHANGE_SCALE;
        RCLCPP_WARN(this->get_logger(),
                    "[hintonbot_keyboard] didn't find parameter "
                    "LINEAR_CHANGE_SCALE, default value %.2f",
                    linear_change_scale_);
    }
    if (this->get_parameter("ANGULAR_CHANGE_SCALE", angular_change_scale_))
        RCLCPP_INFO(this->get_logger(),
                    "[hintonbot_keyboard] ANGULAR_CHANGE_SCALE is %.2f",
                    angular_change_scale_);
    else
    {
        angular_change_scale_ = VALUE_CHANGE_SCALE;
        RCLCPP_WARN(this->get_logger(),
                    "[hintonbot_keyboard] didn't find parameter "
                    "ANGULAR_CHANGE_SCALE, default value %.2f",
                    angular_change_scale_);
    }
    if (this->get_parameter("LINEAR_MAX", linear_max_))
        RCLCPP_INFO(this->get_logger(), "[hintonbot_keyboard] LINEAR_MAX is %.2f",
                    linear_max_);
    else
    {
        linear_max_ = LINEAR_MAX;
        RCLCPP_WARN(this->get_logger(),
                    "[hintonbot_keyboard] didn't find parameter LINEAR_MAX, "
                    "default value %.2f",
                    linear_max_);
    }
    if (this->get_parameter("ANGULAR_MAX", angular_max_))
        RCLCPP_INFO(this->get_logger(), "[hintonbot_keyboard] ANGULAR_MAX is %.2f",
                    angular_max_);
    else
    {
        angular_max_ = ANGULAR_MAX;
        RCLCPP_WARN(this->get_logger(),
                    "[hintonbot_keyboard] didn't find parameter ANGULAR_MAX, "
                    "default value %.2f",
                    angular_max_);
    }
    linear_min_ = linear_change_scale_;
    angular_min_ = angular_change_scale_;
    if (this->get_parameter("PUBLISH_RATE", pub_rate_))
        RCLCPP_INFO(this->get_logger(), "[hintonbot_keyboard] PUBLISH_RATE is %dHZ",
                    pub_rate_);
    else
    {
        pub_rate_ = PUB_RATE;
        RCLCPP_WARN(this->get_logger(),
                    "[hintonbot_keyboard] didn't find parameter PUBLISH_RATE, "
                    "default value %dHZ",
                    pub_rate_);
    }

    vel_publisher_ = this->create_publisher<geometry_msgs::msg::Twist>("key_cmd_vel", 1);
    vel_msg_.linear.z = 0xaa;
    key_control_mode_publisher_ = this->create_publisher<ymrobot_msgs::msg::ControlMode>("chassis_vel_control_mode", 1);  // 底盘控制模式选择
    ymrobot_status_publisher_ = this->create_publisher<ymrobot_msgs::msg::Upper>("chassis/status_ctl", 1);
    mortor_enable_publisher_ = this->create_publisher<std_msgs::msg::Bool>("en_chassis_motor", 1);
}

int kfd = 0;
struct termios cooked, raw;
void Keyboard::Loop()
{
    char c;
    bool dirty = false;
    tcgetattr(kfd, &cooked);
    memcpy(&raw, &cooked, sizeof(struct termios));
    raw.c_lflag &= ~(ICANON | ECHO);
    raw.c_cc[VEOL] = 1;
    raw.c_cc[VEOF] = 2;
    tcsetattr(kfd, TCSANOW, &raw);
    puts("Reading from keyboard");
    puts("Use arrow or 'w' 'a' 's' 'd' keys to move the robot.");
    puts("Use arrow or 'b' 'n' 'm' keys to control the robot status.");
    puts("-----------------------------------------------------");
    puts("Use 'p' key exit keyboard control.");
    puts("q/z  	: increase/decrease only linear speeds by 0.05m/s.");
    puts("e/c  	: increase/decrease only angular speeds by 0.05rad/s.");
    puts("b/n	: switch enable/disable chassis status.");
    puts("o		: switch off/on auto status.");
    puts("--------------------------------------------------------");
    char msgShow[128];
    sprintf(msgShow, "currently:	speed %.2f	turn %.2f chassis:%s auto_mode:%s",
            linear_scale_, angular_scale_, motion_status_ ? "ENABLE" : "DISABLE ",
            auto_mode_ ? "ON" : "OFF");
    puts(msgShow);
    while (rclcpp::ok())
    {
        if (read(kfd, &c, 1) < 0)
        {
            perror("read():");
            exit(-1);
        }
        switch (c)
        {
        case KEYCODE_LEFT_ARROW:
            angular_ = 1.0;
            linear_ = 0.0;
            dirty = true;
            break;
        case KEYCODE_RIGHT_ARROW:
            angular_ = -1.0;
            linear_ = 0;
            dirty = true;
            break;
        case KEYCODE_UP_ARROW:
            linear_ = 1.0;
            angular_ = 0;
            dirty = true;
            break;
        case KEYCODE_DOWN_ARROW:
            linear_ = -1.0;
            angular_ = 0;
            dirty = true;
            break;
        case KEYCODE_A:
            angular_ = 1.0;
            linear_ = 0;
            dirty = true;
            break;
        case KEYCODE_D:
            angular_ = -1.0;
            linear_ = 0;
            dirty = true;
            break;
        case KEYCODE_W:
            linear_ = 1.0;
            angular_ = 0;
            dirty = true;
            break;
        case KEYCODE_S:
            linear_ = -1.0;
            angular_ = 0;
            dirty = true;
            break;
        case KEYCODE_Q:
            dirty = false;
            linear_scale_ += linear_change_scale_;
            if (linear_scale_ > linear_max_)
                linear_scale_ = linear_max_;
            PrintStatus();
            break;
        case KEYCODE_Z:
            dirty = false;
            linear_scale_ -= linear_change_scale_;
            if (linear_scale_ < linear_min_)
                linear_scale_ = linear_min_;
            PrintStatus();
            break;
        case KEYCODE_E:
            dirty = false;
            angular_scale_ += angular_change_scale_;
            if (angular_scale_ > angular_max_)
                angular_scale_ = angular_max_;
            PrintStatus();
            break;
        case KEYCODE_C:
            dirty = false;
            angular_scale_ -= angular_change_scale_;
            if (angular_scale_ < angular_min_)
                angular_scale_ = angular_min_;
            PrintStatus();
            break;
        case KEYCODE_B:
            dirty = false;
            motion_status_.store(true);
            {
                std::cout << "手动键控模式：使能电机" << std::endl;
                auto enable_mortor_msg = std_msgs::msg::Bool();
                enable_mortor_msg.data = true;
                mortor_enable_publisher_->publish(enable_mortor_msg);
            }
            PrintStatus();
            break;
        case KEYCODE_N:
            dirty = false;
            motion_status_.store(false);
            {
                std::cout << "手动键控模式：关闭电机" << std::endl;
                auto enable_mortor_msg = std_msgs::msg::Bool();
                enable_mortor_msg.data = false;
                mortor_enable_publisher_->publish(enable_mortor_msg);
            }
            PrintStatus();
            break;
        case KEYCODE_O:
            dirty = false;
            auto_mode_.store(true);
            std::cout <<"键控模式选择,选择自动模式"<<std::endl;
            {
                auto key_control_mode_msg = ymrobot_msgs::msg::ControlMode();
                key_control_mode_msg.code = ymrobot_msgs::msg::ControlMode::AUTO;
                key_control_mode_publisher_->publish(key_control_mode_msg);
            }
            PrintStatus();
            break;
        case KEYCODE_P:
            dirty = false;
            auto_mode_.store(false);
            std::cout <<"键控模式选择,选择键控模式"<<std::endl;
            {
                auto key_control_mode_msg = ymrobot_msgs::msg::ControlMode();
                key_control_mode_msg.code = ymrobot_msgs::msg::ControlMode::SHOU_DONG;
                key_control_mode_publisher_->publish(key_control_mode_msg);
            }
            PrintStatus();
            break;
        case KEYCODE_SPACE:
            dirty = false;
            auto_mode_.store(false);
            PrintStatus();
            break;
        default:
            angular_ = 0;
            linear_ = 0;
            break;
        }

        if (dirty == true)
        {
            vel_msg_.angular.z = angular_scale_ * angular_;
            vel_msg_.linear.x = linear_scale_ * linear_;
            vel_msg_.linear.z = 0xaa;
        }
        else
        {
            vel_msg_.angular.z = 0;
            vel_msg_.linear.x = 0;
            vel_msg_.linear.z = 0xaa;
        }
        is_alive_.store(true);
    }
    return;
}

void Keyboard::PubThread(void)
{
    uint32_t count = 0;
    rclcpp::Rate rate(20);
    while (rclcpp::ok())
    {
        if (is_alive_.load())
        {
            count = 0;
            is_alive_.store(false);
        }
        else
        {
            if (count < 10)
                count++;
            else
            {
                vel_msg_.angular.z = 0.0;
                vel_msg_.linear.x = 0.0;
            }
        }
        if (!auto_mode_)
            vel_publisher_->publish(vel_msg_);

        status_msg_.auto_status = auto_mode_;
        status_msg_.chassis_status = motion_status_;
        ymrobot_status_publisher_->publish(status_msg_);
        rate.sleep();
    }
}

void quit(int)
{
    tcsetattr(kfd, TCSANOW, &cooked);
    rclcpp::shutdown();
    exit(0);
}

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);

    signal(SIGINT, quit);

    auto keyboard_node = std::make_shared<Keyboard>("keyboard_control");
    std::thread thread_loop(&Keyboard::Loop, keyboard_node);
    std::thread thread_pub(&Keyboard::PubThread, keyboard_node);

    rclcpp::spin(keyboard_node);

    thread_pub.join();
    thread_loop.join();
    rclcpp::shutdown();
}