// ymbot_c_motor.hpp

#ifndef YMBOT_JOINT_EU_H
#define YMBOT_JOINT_EU_H

#include "eu_planet.h" //motors
#include <atomic>
#include <iostream>
#include <sys/time.h>
#include <thread>

class YmbotJointEu {
  public:
    int dev_index;
    int motor_id;
    int motor_mode; // 1:轮廓位置模式-速度     2:轮廓位置模式-时间    3:轮廓速度模式    4:电流模式    5:周期同步位置模式
    bool flag_enable;

    float rated_torque;

    float present_position;
    float target_position;
    float record_position;

    float present_velocity;
    float target_velocity;

    float present_current;
    float target_current;

    std::string joint_name;
    float joint_offset_angle;
    float joint_offset_radian;
    float present_joint_radian;
    float target_joint_radian;

    float joint_limit_max;
    float joint_limit_min;

    YmbotJointEu();
    bool motor_initialization_CSP();
    bool motor_initialization_PV();
    float comput_current(double torque);
    void set_zero_current();
    bool motor_disabled();
};

#endif