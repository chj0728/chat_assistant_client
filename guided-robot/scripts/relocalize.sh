#!/bin/bash

# 切换到工作空间目录
cd /home/ymrobot/ros2_ws || { echo "Failed to enter /home/cat/ros2_ws directory"; exit 1; }

# Source ROS2 环境
source install/setup.bash

# 发布第一个服务请求
ros2 service call /localizer/relocalize interface/srv/Relocalize "{
  \"pcd_path\": \"/home/cat/ros2_ws/src/ym_robot_ws/assets/map.pcd\", 
  \"x\": 0.0, 
  \"y\": 0.0, 
  \"z\": 0.0, 
  \"yaw\": 0.0, 
  \"pitch\": 0.0, 
  \"roll\": 0.0
}"

# 延迟 1 秒
sleep 1

# 发布第二个服务请求
ros2 service call /localizer/relocalize_check interface/srv/IsValid "{
  \"code\": 0
}"
