#!/bin/bash

# 设置工作空间路径
WORKSPACE_DIR="/home/ymrobot/ros2_ws_guidance"

# 检查工作空间目录是否存在
if [ ! -d "$WORKSPACE_DIR" ]; then
  echo "Error: Workspace directory $WORKSPACE_DIR does not exist."
  exit 1
fi

# 切换到工作空间目录
cd "$WORKSPACE_DIR" || exit

# 源化setup.bash
source install/setup.bash

# 启动ROS2 launch文件
ros2 launch aud_conver lager.launch.py