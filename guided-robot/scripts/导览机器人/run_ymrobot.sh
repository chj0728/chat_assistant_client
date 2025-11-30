#!/bin/bash

# 设置脚本名称用于日志记录
SCRIPT_NAME="run_ymrobot.sh"

# 获取当前时间戳
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# 记录脚本开始时间
echo "[$TIMESTAMP] $SCRIPT_NAME 开始执行" >&2

# 检查必要的环境变量
if [ -z "$ROS_DISTRO" ]; then
    echo "[$TIMESTAMP] 错误: ROS环境未设置，请先 source ROS环境" >&2
    exit 1
fi

# 检查必要的目录是否存在
WORKSPACE_DIR="/home/ymrobot/ros2_ws_guidance"
if [ ! -d "$WORKSPACE_DIR" ]; then
    echo "[$TIMESTAMP] 错误: 工作目录 $WORKSPACE_DIR 不存在" >&2
    exit 1
fi

# 进入工作目录
cd "$WORKSPACE_DIR" || {
    echo "[$TIMESTAMP] 错误: 无法进入工作目录 $WORKSPACE_DIR" >&2
    exit 1
}

# 1. 启动YMROBOT相关节点
echo "[$TIMESTAMP] 启动YMROBOT节点..." >&2
source install/setup.bash
ros2 launch /home/ymrobot/ros2_ws_guidance/src/guided-robot/launch/run.launch.py

# 检查节点启动状态
YMROBOT_STATUS=$?
if [ $YMROBOT_STATUS -ne 0 ]; then
    echo "[$TIMESTAMP] 错误: YMROBOT节点启动失败，退出码: $YMROBOT_STATUS" >&2
    exit $YMROBOT_STATUS
fi

# 2. 其他YMROBOT相关操作可以在这里添加
# 例如：
# echo "[$TIMESTAMP] 执行YMROBOT配置..." >&2
# ./configure_ymrobot.sh

# 记录脚本成功结束
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
echo "[$TIMESTAMP] $SCRIPT_NAME 执行完成" >&2

exit 0