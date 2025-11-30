#ifndef YMBOT_HEAD_API_H
#define YMBOT_HEAD_API_H

#include <fcntl.h>
#include <iomanip>
#include <iostream>
#include <stdio.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>
#include <vector>

using namespace std;

class RTrobot_hands {
  public:
  /**
     * @brief 构造函数
     * @param id 舵机的 ID
     * @param servo_max_positions 舵机的最大位置
     * @param servo_min_positions 舵机的最小位置
     * @throw std::invalid_argument 如果参数长度不一致则抛出异常
     */
    RTrobot_hands(const std::vector<int>& id,
            const std::vector<int>& servo_max_positions,
            const std::vector<int>& servo_min_positions);
    /**
     * @brief 析构函数
     */
    ~RTrobot_hands();
    
    /**
     * @brief 串口初始化
     * @param port_name 串口名称，例如 /dev/ttyACM0
     * @return 布尔值
     */
    bool initialization(const char* port_name);

    /**
     * @brief 设置舵机的目标位置
     * @param id 电机id号
     * @param target_position 目标位置，范围：500-2500
     * @return 无返回值
     */
    void set_position(const int id, const int target_position);


    /**
     * @brief 设置舵机的启动速度
     * @param target_velocity
     * 表示速度，本质上是运行时间，值越小速度越大，范围：0-9999，一般单个表情包含的各个舵机运动速度相同
     * @return 无返回值
     */
    void set_velocity(const int target_velocity);


    /**
     * @brief 设置完位置，速度，延迟时间后，发送指令
     * @return 布尔值
     */
    bool send_data();


    /**
     * @brief 发送指令后，两秒内接收板子反馈的信息，并且直接打印ASCII码，接收成功则输出“OK”，超过两秒则接收失败
     * @return 布尔值
     */
    bool receive_data();


    /**
     * @brief 舵机通电后自动执行板子中的动作。使用该函数可以停止动作组（注意：停止后不可恢复，只能发送新的指令重新执行）
     * @return 布尔值
     */
    bool stop_action();


    /**
     * @brief 重新启动控制器
     * @return 布尔值
     */
    bool reset();



    /**
     * @brief 执行特定动作组（写在板子里了）
     * @param action_group_num 动作组的序号
     * @return 布尔值
     */
    bool run_action_group(int action_group_num);



    /**
     * @brief 控制舵机，单个和多个都可以
     * @param target_position 目标位置，范围：500-2500
     * @param target_velocity
     * 表示速度，本质上是运行时间，值越小速度越大，范围：0-9999，一般单个表情包含的各个舵机运动速度相同
     * @return 布尔值
     */
    bool control_servos(const vector<int> target_position, const int target_velocity);

  private:
    int serial_port_;
    string data_;
    vector<int> id_;
    vector<int> servo_max_positions_;
    vector<int> servo_min_positions_;
    int is_debug_ = 0;
};

#endif
