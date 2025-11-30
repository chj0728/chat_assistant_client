#!/bin/bash

# 进入工作目录
cd /home/ymrobot/ros2_ws || { echo "Failed to enter /home/ymrobot/ros2_ws directory"; exit 1; }

# 设置 ROS 环境
source install/setup.bash

# 显示菜单
ros2 run keyboard_control keyboard_control