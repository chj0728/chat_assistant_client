// #include <iostream>
// #include <thread>
// #include <atomic>
// #include <sys/time.h>
// #include "eu_planet.h"//motors

#include "ymbot_hardware_driver/ymbot_joint_eu.h"

using namespace std;

YmbotJointEu::YmbotJointEu() {
    dev_index = 0;
    motor_id = 0;
    motor_mode = 1;
    flag_enable = false;

    rated_torque = 0.01;

    present_position = 0.0;
    target_position = 0.0;
    record_position = 0.0;


    present_velocity = 0.0;
    target_velocity = 0.0;

    present_current = 0.0;
    target_current = 0.0;

    joint_name = "";
    
    joint_offset_angle = 0.0;
    joint_offset_radian = 0.0;
    present_joint_radian = 0.0;
    target_joint_radian = 0.0;

    joint_limit_max = 0.0;
    joint_limit_min = 0.0;
}

bool YmbotJointEu::motor_initialization_CSP() {
    if (PLANET_SUCCESS == planet_setEnabled(dev_index, motor_id, true)) {
        cout << "Motor " << motor_id << " enabled successfully" << endl;
        motor_mode = 5;
        planet_setMode(dev_index, motor_id, motor_mode);
        planet_setTargetCurrent(dev_index, motor_id, 500);
        planet_setTargetVelocity(dev_index, motor_id, 10);

        if (PLANET_SUCCESS != planet_getPosition(dev_index, motor_id, &present_position)) {
            cout << "Motor " << motor_id << " get position failed" << endl;
            return false;
        };

        record_position = present_position;
        planet_quick_setTargetPosition(dev_index, motor_id, present_position + 0.1);
        this_thread::sleep_for(chrono::milliseconds(50));

        if (PLANET_SUCCESS != planet_getEnabled(dev_index, motor_id, &flag_enable)) {
            cout << "Motor " << motor_id << " get (enabled flag) failed" << endl;
            return false;
        };

        if (flag_enable) {
            cout << "Motor " << motor_id << " initialize successfully" << endl;
            planet_setTargetCurrent(dev_index, motor_id, 1600);
            if (motor_id == 44 || motor_id == 45 || motor_id == 46 || motor_id == 47) {
                planet_setTargetVelocity(dev_index, motor_id, 60);
            }
            else {
                planet_setTargetVelocity(dev_index, motor_id, 60);
            }
            cout << "Motor " << motor_id << " check flag" << endl;
            return true;
        }
        else {
            cout << "Motor " << motor_id << " initialize failed" << endl;
            return false;
        }
    }
    else {
        cout << "Motor " << motor_id << " enabled failed" << endl;
        cout << "Motor " << motor_id << " initialize failed" << endl;
        return false;
    }
}


bool YmbotJointEu::motor_initialization_PV() {
    if (PLANET_SUCCESS == planet_setEnabled(dev_index, motor_id, true)) {
        cout << "Motor " << motor_id << " enabled successfully" << endl;
        motor_mode = 3;
        planet_setMode(dev_index, motor_id, motor_mode);
        return true;
    }
    else {
        cout << "Motor " << motor_id << " enabled failed" << endl;
        return false;
    }
}


float YmbotJointEu::comput_current(double torque) {
    return torque / rated_torque * 1000;
}

void YmbotJointEu::set_zero_current() {
    planet_setTargetCurrent(dev_index, motor_id, 0);
}

bool YmbotJointEu::motor_disabled() {
    if (PLANET_SUCCESS == planet_setEnabled(dev_index, motor_id, false)) {
        cout << "Motor " << motor_id << " disabled successfully" << endl;
        return true;
    }
    else {
        cout << "Motor " << motor_id << " disabled failed" << endl;
        return false;
    }
}

int main() {
    ;
}
