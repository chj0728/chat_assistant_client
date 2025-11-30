#!/bin/bash

# 进入工作目录
cd /home/ymrobot/ros2_ws || { echo "Failed to enter /home/ymrobot/ros2_ws directory"; exit 1; }

# 设置 ROS 环境
source install/setup.bash

# 显示菜单
echo "请选择要发布的 topic 命令："

# 读取用户输入
read -p "请输入数字 (1-20): " choice

# 根据用户输入执行对应操作
case $choice in
  1)
    echo "重定位..."
ros2 topic pub -1 --qos-reliability reliable task_guidance/task ymrobot_msgs/msg/Task "platform_id: 'PAAS_dev'
amr_id: 'ymrobot'
task_id: '111'
nav_points: []
commands: [{'code': 12,'params': ['twolou', '112', 'aab']}]
index: '3'"
    ;;
  2)
    echo "执行行为树..."
ros2 topic pub -1 --qos-reliability reliable task_guidance/task ymrobot_msgs/msg/Task "platform_id: 'PAAS_dev'
amr_id: 'ymrobot'
task_id: '111'
nav_points: []
commands: [{'code': 19,'params': []}]
index: '6'"
    ;;
  3)
    echo "发布电梯开门指令..."
ros2 topic pub -1 --qos-reliability reliable  /wait_elevator_action/enter_elevator std_msgs/msg/Bool "data: true"
    ;;
  4)
    echo "退出脚本。"
    exit 0
    ;;
  *)
    echo "无效的选择，请输入 1、2 或 3。"
    exit 1
    ;;
esac