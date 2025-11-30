#include <cmath>
#include <termios.h>
#include <unistd.h>
#include <vector>

#include "ymbot_hardware_driver/ymbot_joint_eu.h"
#include "ymbot_hardware_driver/eu_planet.h"


int joint_control_command[14] = {0}, exit_flag = 0;
int keyboard_flag = 0;
bool motors_are_running_flag = false;
double radians_will_publish_to_ros[14] = {0.0};

char keycode_positive[14] = {'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', 'x', 'v', 'n', '1'};
char keycode_negative[14] = {'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'z', 'c', 'b', 'm', '2'};
std::atomic<bool> keyboard_running(true);
std::atomic<char> key(0);


// int id_array[] = {21, 22 ,11 ,12};
// 340.115   277.252 

// int id_array[] = {31, 32, 33, 34, 35};
// 185.29	173.71	173.639	213.349	179.995


// int id_array[] = {11,12};

int id_array[] = {41, 42, 43, 44, 45};
//  175.545	169.492	186.795	215.085	180.791


// int id_array[] = {35, 45};

using namespace std;

// 电机通讯异常后的退出函数
int n_motor_group = 3;
void free_canables() {
    // can口 通信关闭
    for (int i = 0; i < n_motor_group; i++) {
        if (PLANET_SUCCESS != planet_freeDLL(i)) {
            cout << "Motor communication canable" << i << " abnormality......exit" << endl;
        }
        
        else {
            cout <<  "Motor communication canable" << i << " closed successfully" << endl;
        }
    }
}

int MotorFunction() {
    /**************************************motors****************************************/
    int n_motors = sizeof(id_array) / sizeof(id_array[0]);
    vector<YmbotJointEu> motor(n_motors);
    vector<float> joints_offset_angle(n_motors);
    float temp_var1, temp_var2;

    int channel = 0;
    for (int devIndex = 0; devIndex < n_motor_group; devIndex++) {
        if (PLANET_SUCCESS != planet_initDLL(planet_DeviceType_Canable, devIndex, channel, planet_Baudrate_1000)) {
            cout << "Canable " << devIndex << " communication initialization failed !!!" << endl;
            return 0;
        }
    }


    cout << n_motors << endl;

        // ---------------------------------------------------------------------测试三个典型电机并获取dev_indices
        int dev_indices[3];
        vector<int> test_ids = {11, 31, 41};
        bool found;
    
        for (size_t i = 0; i < test_ids.size(); i++) {
            found = false;
            int test_id = test_ids[i];
            
            for (int j = 0; j < n_motor_group; j++) {
                bool heartbeat = false;
                if (PLANET_SUCCESS == planet_getHeartbeat(j, test_id, &heartbeat, 100) && heartbeat) {
                    dev_indices[i] = j;
                    cout << "---------------------------------------------尝试寻找通讯id中,忽略这附近的报错。ID范围" << test_id/10*10+1 << "-" << test_id/10*10+9 
                        << "对应dev_index: " << j << endl;
                    found = true;
                    break;
                }
            }
            
            if (!found) {
                cout << "错误：无法找到ID " << test_id << " 对应的dev_index！" << endl;
                return 0;
            }
        }
    
        // 输出结果验证
        cout << "获取的dev_indices: ";
        for (int i = 0; i < 3; i++) {
            cout << dev_indices[i] << "\t";
        }
        cout << endl;
    
        for (int i = 0; i < n_motors; i++) {
            if (id_array[i] > 10 && id_array[i] < 30) {
                motor[i].dev_index = dev_indices[0];
            }
            else if (id_array[i] > 30 && id_array[i] < 40) {
                motor[i].dev_index = dev_indices[1];
            }
            else if (id_array[i] > 40 && id_array[i] < 50) {
                motor[i].dev_index = dev_indices[2];
            }
            else {
                cout << "There is an id number in the id_array that does not match the actual motor." << endl;
                return 0;
            }
            motor[i].motor_id = id_array[i];
            // motor[i].joint_offset_angle = joints_offset_angle[i];
            // motor[i].joint_offset_radian = motor[i].joint_offset_angle / 180.0 * M_PI;}
        }
        // ---------------------------------------------------------------------测试三个典型电机并获取dev_indices
    

    // for (int i = 0; i < n_motors; i++) {
    //     if (id_array[i] > 10 && id_array[i] < 30) {
    //         motor[i].dev_index = 0;
    //     }
    //     else if (id_array[i] > 30 && id_array[i] < 40) {
    //         motor[i].dev_index = 1;
    //     }
    //     else if (id_array[i] > 40 && id_array[i] < 50) {
    //         motor[i].dev_index = 2;
    //     }
    //     else {
    //         cout << "There is an id number in the id_array that does not match the actual motor." << endl;
    //         return 0;
    //     }
    //     motor[i].motor_id = id_array[i];
    //     // motor[i].joint_offset_angle = joints_offset_angle[i];
    //     // motor[i].joint_offset_radian = motor[i].joint_offset_angle / 180.0 * M_PI;}
    // }

    cout << endl;
    // for(int i=0; i<sizeof(id_array)/sizeof(id_array[0]); i++){
    //     cout << "Motor " <<  motor[i].motor_id << "position: " << getPosition(motor[i].motor_id) << endl;
    // }

    // unsigned p = 0;
    // for (int i = 0; i < n_motors; i++) {
    //     planet_getPOfPositionLoop(motor[i].dev_index, motor[i].motor_id, &p);
    //     cout << motor[i].motor_id << ": " << p << endl;
    // }

    // unsigned p = 32;
    // int i = 0;
    // cout << planet_setPOfPositionLoop(motor[i].dev_index, motor[i].motor_id, p) << endl;
    // cout << planet_saveParas(motor[i].dev_index, motor[i].motor_id) << endl;

    // return 0;
     

    cout << "****************Motor initialization********************" << endl;
    for (int i = 0; i < n_motors; i++) {
        if (motor[i].motor_initialization_CSP()) {
            cout << "motor " << motor[i].motor_id << " enabled successfully" << endl;
            this_thread::sleep_for(chrono::milliseconds(500));
        }
        else {
            cout << "motor " << motor[i].motor_id << " enabled failed" << endl;
            // for (size_t j = 0u; j < n_motors; j++) {
            //     if (motor[j].motor_disabled()) {
            //         cout << "motor " << motor[i].motor_id << " disabled successfully" << endl;
            //     }
            //     else {
            //         cout << "motor " << motor[i].motor_id << " disabled failed" << endl;
            //     }
            //     this_thread::sleep_for(chrono::milliseconds(500));
            // }
            free_canables();
            return 0;
        }

        // Proactive acquisition of first position to avoid unreasonable values
        if (PLANET_SUCCESS != planet_getPosition(motor[i].dev_index, motor[i].motor_id, &motor[i].present_position)) {
            cout << "Motor " << motor[i].motor_id << " get position failed" << endl;
            return 0;
        }
        motor[i].present_joint_radian = motor[i].present_position / 180.0 * M_PI - motor[i].joint_offset_radian;
    }
    cout << "All motors initialized successfully" << endl;

    /**************************************keyboard motors****************************************/
    while (exit_flag == 0) {
        // 记录当前时间作为开始时间
        auto start_time = chrono::steady_clock::now();

        cout << "position is : ";
        for (int i = 0; i < sizeof(id_array) / sizeof(id_array[0]); i++) {
            if (joint_control_command[i] == 1) {
                planet_getPosition(motor[i].dev_index, motor[i].motor_id, &motor[i].present_position);
                motor[i].target_position = motor[i].present_position + 0.5;
                planet_quick_setTargetPosition(motor[i].dev_index, motor[i].motor_id, motor[i].target_position);
                motor[i].record_position = motor[i].target_position;
            }
            else if (joint_control_command[i] == -1) {
                planet_getPosition(motor[i].dev_index, motor[i].motor_id, &motor[i].present_position);
                motor[i].target_position = motor[i].present_position - 0.5;
                planet_quick_setTargetPosition(motor[i].dev_index, motor[i].motor_id, motor[i].target_position);
                motor[i].record_position = motor[i].target_position;
            }
            else {
                motor[i].target_position = motor[i].record_position;
                planet_quick_setTargetPosition(motor[i].dev_index, motor[i].motor_id, motor[i].target_position);
                motor[i].record_position = motor[i].target_position;
            }

            planet_getPosition(motor[i].dev_index, motor[i].motor_id, &motor[i].present_position);
            cout << motor[i].present_position << "\t";
        }
        // cout << endl;
        this_thread::sleep_for(chrono::milliseconds(20));

        // 记录当前时间作为结束时间
        auto end_time = chrono::steady_clock::now();
        // 计算时间差并输出
        auto elapsed_time = chrono::duration_cast<chrono::milliseconds>(end_time - start_time).count();
        cout << "Elapsed time: " << elapsed_time << " ms" << endl;
    }

    this_thread::sleep_for(chrono::milliseconds(500));
    for (int j = 0; j < n_motors; j++) {
        motor[j].motor_disabled();
        this_thread::sleep_for(chrono::seconds(1));
    }
    // planet_freeDLL(devIndex);
    return 0;
}

// 获取键盘键值线程函数
void KeyboardFunction() {
    struct termios original;
    struct termios modified; 

    // 禁用标准输入的行缓冲和回显
    tcgetattr(STDIN_FILENO, &original);
    modified = original;
    modified.c_lflag &= ~(ICANON | ECHO);
    tcsetattr(STDIN_FILENO, TCSANOW, &modified);

    while (keyboard_running) {
        char c;
        if (read(STDIN_FILENO, &c, 1) > 0) {
            // 将获取到的键值存储在共享变量中
            key.store(c);

            std::cout << c << std::endl;
            if (c == '`') {
                exit_flag = 1;
            }
            else {
                for (int i = 0; i < 14; i++) {
                    if (c == keycode_positive[i]) {
                        joint_control_command[i] = 1;
                    }
                    else if (c == keycode_negative[i]) {
                        joint_control_command[i] = -1;
                    }
                    else {
                        joint_control_command[i] = 0;
                    }
                }
            }
        }
    }
    // 恢复原始终端设置
    tcsetattr(STDIN_FILENO, TCSANOW, &original);
}

int main(int argc, char** argv) {
    thread t1(KeyboardFunction);
    t1.detach();
    // sleep(5);

    MotorFunction();

    return 0;
}
