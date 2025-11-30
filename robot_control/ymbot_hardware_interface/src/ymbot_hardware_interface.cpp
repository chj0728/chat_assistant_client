// Copyright 2021 ros2_control Development Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "rclcpp/rclcpp.hpp"
#include <rclcpp/utilities.hpp>
#include "ymbot_hardware_driver/ymbot_joint_eu.h"
#include "ymbot_hardware_interface/ymbot_hardware_interface.hpp"
#include "hardware_interface/types/hardware_interface_type_values.hpp"

using namespace std;

namespace ymbot_hardware_interface {

int channel = 0;
vector<int> motors_id = {11, 12, 22, 21, 31, 32, 33, 34, 35, 41, 42, 43, 44, 45};
int n_motors = motors_id.size();
vector<YmbotJointEu> motor(n_motors);
vector<string> joints_name(n_motors);
vector<float> joints_offset_angle(n_motors);
int n_joints;

const char *green = "\033[1;32m";
const char *red   = "\033[1;31m";
const char *reset = "\033[0m";

hardware_interface::CallbackReturn ymbot_hardware_interface::on_init(
        const hardware_interface::HardwareInfo &info) {
    if (hardware_interface::SystemInterface::on_init(info) !=
        hardware_interface::CallbackReturn::SUCCESS) {
        return hardware_interface::CallbackReturn::ERROR;
    }

    // get paramaters from config file

    // get paramaters from urdf file
    n_joints = info_.joints.size();
    hw_positions_.resize(n_joints, std::numeric_limits<double>::quiet_NaN());
    hw_commands_.resize(n_joints, std::numeric_limits<double>::quiet_NaN());
    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%sNumber of joints: %d%s", green, n_joints, reset);

    // motors communication initialization
    for (int devIndex = 0; devIndex < 3; devIndex++) {
        if (PLANET_SUCCESS != planet_initDLL(planet_DeviceType_Canable, devIndex,
                                            channel, planet_Baudrate_1000)) {
        RCLCPP_ERROR(rclcpp::get_logger("ymbot_hardware_interface"),
                    "%sCanable %d communication initialization failed !!!%s",
                    red, devIndex, reset);
        return hardware_interface::CallbackReturn::ERROR;
        }
    }

    
    for (const hardware_interface::ComponentInfo &joint : info_.joints) {
        // DiffBotSystem has exactly one states and one command interface on each
        // joint

       
        if (joint.command_interfaces.size() != 1) {
        RCLCPP_FATAL(rclcpp::get_logger("ymbot_hardware_interface"),
                    "Joint '%s' has %zu command interfaces found. 1 expected.",
                    joint.name.c_str(), joint.command_interfaces.size());
        return hardware_interface::CallbackReturn::ERROR;
        }



        if (joint.command_interfaces[0].name !=
            hardware_interface::HW_IF_POSITION) {
        RCLCPP_FATAL(
            rclcpp::get_logger("ymbot_hardware_interface"),
            "Joint '%s' have %s command interfaces found. '%s' expected.",
            joint.name.c_str(), joint.command_interfaces[0].name.c_str(),
            hardware_interface::HW_IF_POSITION);
        return hardware_interface::CallbackReturn::ERROR;
        }




        if (joint.state_interfaces.size() != 1) {
        RCLCPP_FATAL(rclcpp::get_logger("ymbot_hardware_interface"),
                    "Joint '%s' has %zu state interface. 2 expected.",
                    joint.name.c_str(), joint.state_interfaces.size());
        return hardware_interface::CallbackReturn::ERROR;
        }
        
        

        if (joint.state_interfaces[0].name != hardware_interface::HW_IF_POSITION) {
        RCLCPP_FATAL(
            rclcpp::get_logger("ymbot_hardware_interface"),
            "Joint '%s' have '%s' as first state interface. '%s' expected.",
            joint.name.c_str(), joint.state_interfaces[0].name.c_str(),
            hardware_interface::HW_IF_POSITION);
        return hardware_interface::CallbackReturn::ERROR;
        }



    }


    return hardware_interface::CallbackReturn::SUCCESS;
}

std::vector<hardware_interface::StateInterface>
ymbot_hardware_interface::export_state_interfaces() {
    std::vector<hardware_interface::StateInterface> state_interfaces;
    for (int i = 0; i < n_joints; i++) {
        state_interfaces.emplace_back(hardware_interface::StateInterface(
            info_.joints[i].name, hardware_interface::HW_IF_POSITION,
            &hw_positions_[i]));
    }
    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%sexport_state_interfaces successfully%s", green, reset);

    return state_interfaces;
}

std::vector<hardware_interface::CommandInterface>
ymbot_hardware_interface::export_command_interfaces() {
    std::vector<hardware_interface::CommandInterface> command_interfaces;
    for (int i = 0; i < n_joints; i++) {
        command_interfaces.emplace_back(hardware_interface::CommandInterface(
            info_.joints[i].name, hardware_interface::HW_IF_POSITION,
            &hw_commands_[i]));
    }
    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%sexport_command_interfaces successfully%s", green, reset);

    return command_interfaces;
}

hardware_interface::CallbackReturn ymbot_hardware_interface::on_configure(
        const rclcpp_lifecycle::State & /*previous_state*/) {
    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%stest on_configure%s", green, reset);
                         
    joints_offset_angle = { 180, 180, 180, 180, 178.731,   179.247,  180.626, 154.363, 185.999, 
                            182.939,   181.703, 187.103, 202.516, 175.303};
    
    joints_name = { "Body_Joint1", "Body_Joint2", "Neck_Joint1", "Neck_Joint2", "Left_Arm_Joint1",  "Left_Arm_Joint2",  "Left_Arm_Joint3",  "Left_Arm_Joint4",  "Left_Arm_Joint5",   
                    "Right_Arm_Joint1", "Right_Arm_Joint2", "Right_Arm_Joint3", "Right_Arm_Joint4", "Right_Arm_Joint5"};

    for (int i = 0; i < n_motors; i++) {
        motor[i].motor_id = motors_id[i];
        motor[i].joint_offset_angle = joints_offset_angle[i];
        motor[i].joint_offset_radian = motor[i].joint_offset_angle / 180.0 * M_PI;
        motor[i].joint_name = joints_name[i];
        if (motors_id[i] > 10 && motors_id[i] < 30) {
        motor[i].dev_index = 0;   // 换接线前是1  2025.2.12     2025.5.15换板子
        } else if (motors_id[i] > 30 && motors_id[i] < 40) {
        motor[i].dev_index = 1;   // 换接线前是0  2025.2.12     2025.5.15换板子
        } else if (motors_id[i] > 40 && motors_id[i] < 50) {
        motor[i].dev_index = 2;   // 换接线前是2  2025.2.12     2025.5.15换板子
        } else {
        RCLCPP_ERROR(rclcpp::get_logger("ymbot_hardware_interface"),
                    "%sThere is an id number in the motors_id that does not "
                    "match the actual motor.%s",
                    red, reset);
        return hardware_interface::CallbackReturn::ERROR;
        }
    }

    for (int i = 0; i < n_joints; i++) {
        RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                    "%sjoint name: %s%s", green, info_.joints[i].name.c_str(),
                    reset);
    }

    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%sAll robot joints: %d and all controlled motors: %d%s", green,
                n_joints, n_motors, reset);

    if ((n_motors != n_joints)) {
        RCLCPP_ERROR(rclcpp::get_logger("ymbot_hardware_interface"),
                    "%sthe number of 'motors id' is incorrect%s", red, reset);
        return hardware_interface::CallbackReturn::ERROR;
    }

    if (static_cast<int>(joints_offset_angle.size()) != n_motors) {
        RCLCPP_ERROR(rclcpp::get_logger("ymbot_hardware_interface"),
                    "%sthe number of 'joints offset' is incorrect%s", red, reset);
        return hardware_interface::CallbackReturn::ERROR;
    }

    return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn ymbot_hardware_interface::on_cleanup(
        const rclcpp_lifecycle::State & /*previous_state*/) {
    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%stest on_cleanup%s", green, reset);

    return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn ymbot_hardware_interface::on_activate(
        const rclcpp_lifecycle::State & /*previous_state*/) {
    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%sActivating ...please wait...%s", green, reset);
    for (int i = 0; i < n_motors; i++) {
        if (motor[i].motor_initialization_CSP()) {
        RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                    "%smotor %d enabled successfully%s", green, motor[i].motor_id,
                    reset);
        this_thread::sleep_for(chrono::milliseconds(50));
        } else {
        RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                    "%smotor %d enabled failure%s", green, motor[i].motor_id,
                    reset);
        if (motor[i].motor_disabled()) {
            RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                        "%smotor %d disabled successfully%s", green,
                        motor[i].motor_id, reset);
        } else {
            RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                        "%smotor %d disabled) failure%s", green, motor[i].motor_id,
                        reset);
        }
        this_thread::sleep_for(chrono::milliseconds(1000));
        planet_freeDLL(0);
        planet_freeDLL(1);
        planet_freeDLL(2);
        return hardware_interface::CallbackReturn::ERROR;
    }

        // Proactive acquisition of first position to avoid unreasonable values
        if (PLANET_SUCCESS != planet_getPosition(motor[i].dev_index,
                                                motor[i].motor_id,
                                                &motor[i].present_position)) {
        cout << "Motor " << motor[i].motor_id << " get position failed" << endl;
        return hardware_interface::CallbackReturn::ERROR;
        }
        motor[i].present_joint_radian =
            motor[i].present_position / 180.0 * M_PI - motor[i].joint_offset_radian;
        RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                    "%spresent_joint_radian: %f%s", green,
                    motor[i].present_joint_radian, reset);
        hw_positions_[i] = motor[i].present_joint_radian;
        hw_commands_[i] = hw_positions_[i];
    }
    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%sSuccessfully activated!%s", green, reset);

    return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn ymbot_hardware_interface::on_deactivate(
        const rclcpp_lifecycle::State & /*previous_state*/) {
    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%sDeactivating ...please wait...%s", green, reset);

    for (int i = 0; i < n_joints; i++) {
        motor[i].motor_disabled();
        this_thread::sleep_for(chrono::seconds(1));
    }

    RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
                "%sSuccessfully deactivated!%s", green, reset);

    return hardware_interface::CallbackReturn::SUCCESS;
}

// hardware_interface::CallbackReturn ymbot_hardware_interface::on_shutdown(
//     const rclcpp_lifecycle::State & /*previous_state*/) {
// RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
//             "%sDeactivating ...please wait...%s", green, reset);

// for (int i = 0; i < n_joints; i++) {
//     motor[i].motor_disabled();
//     this_thread::sleep_for(chrono::seconds(1));
// }

// RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
//             "%sSuccessfully shut down!%s", red, reset);

// return hardware_interface::CallbackReturn::SUCCESS;
// }

hardware_interface::return_type
ymbot_hardware_interface::read(const rclcpp::Time & /*time*/,
                                const rclcpp::Duration &period) {
    for (size_t i = 0; i < hw_positions_.size(); i++) {
        // Get the motor index based on the joint name
        int motor_index = -1;
        for (int j = 0; j < n_motors; j++) {
        if (info_.joints[i].name == motor[j].joint_name) {
            motor_index = j;
            break;
        }
        }

        if (motor_index == -1) {
        RCLCPP_ERROR(rclcpp::get_logger("ymbot_hardware_interface"),
                    "No motor found for joint '%s'",
                    info_.joints[i].name.c_str());
        return hardware_interface::return_type::ERROR;
        }

        // Get the motor position
        if (PLANET_SUCCESS !=
            planet_getPosition(motor[motor_index].dev_index,
                            motor[motor_index].motor_id,
                            &motor[motor_index].present_position)) {
        RCLCPP_ERROR(rclcpp::get_logger("ymbot_hardware_interface"),
                    "Failed to get position for motor %d",
                    motor[motor_index].motor_id);
        return hardware_interface::return_type::ERROR;
        }

        // Convert the motor position to joint position and assign to hw_positions_
        motor[motor_index].present_joint_radian =
            motor[motor_index].present_position / 180.0 * M_PI -
            motor[motor_index].joint_offset_radian;
        hw_positions_[i] = motor[motor_index].present_joint_radian;
    }

    // RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"), "read: %.6f",
    //             period.seconds());
    // for (size_t i = 0; i < hw_positions_.size(); i++) {
    //   RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
    //               "hw_positions_[%zu]: %.6f", i, hw_positions_[i]);
    // }

    return hardware_interface::return_type::OK;
}

hardware_interface::return_type
ymbot_hardware_interface::write(const rclcpp::Time & /*time*/,
                                const rclcpp::Duration &period) {
    for (size_t i = 0; i < hw_commands_.size(); i++) {
        // Get the motor index based on the joint name
        int motor_index = -1;
        for (int j = 0; j < n_motors; j++) {
        if (info_.joints[i].name == motor[j].joint_name) {
            motor_index = j;
            break;
        }
        }

        if (motor_index == -1) {
        RCLCPP_ERROR(rclcpp::get_logger("ymbot_hardware_interface"),
                    "No motor found for joint '%s'",
                    info_.joints[i].name.c_str());
        return hardware_interface::return_type::ERROR;
        }

        // Convert the joint command to motor command
        motor[motor_index].target_position =
            (hw_commands_[i] + motor[motor_index].joint_offset_radian) / M_PI *
            180.0;

        // Send the command to the motor
        if (PLANET_SUCCESS !=
            planet_quick_setTargetPosition(motor[motor_index].dev_index,
                                        motor[motor_index].motor_id,
                                        motor[motor_index].target_position)) {
        RCLCPP_ERROR(rclcpp::get_logger("ymbot_hardware_interface"),
                    "Failed to set target position for motor %d",
                    motor[motor_index].motor_id);
        return hardware_interface::return_type::ERROR;
        }
    }

    // RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"), "write:
    // %.6f", period.seconds()); for (size_t i = 0; i < hw_commands_.size(); i++)
    // {
    //   RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
    //               "hw_commands_[%zu]: %.6f", i, hw_commands_[i]/M_PI*180.0);
    //   // RCLCPP_INFO(rclcpp::get_logger("ymbot_hardware_interface"),
    //   //             "target_position[%zu]: %.6f", i,
    //   motor[i].target_position);
    // }

    return hardware_interface::return_type::OK;
}

} // namespace ymbot_hardware_interface

#include "pluginlib/class_list_macros.hpp"
PLUGINLIB_EXPORT_CLASS(ymbot_hardware_interface::ymbot_hardware_interface,
                       hardware_interface::SystemInterface)
