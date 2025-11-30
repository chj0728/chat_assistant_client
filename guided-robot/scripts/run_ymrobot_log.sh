#!/bin/bash
export PYTHONDONTWRITEBYTECODE=1

PASSWORD="ggg661900"

# 使用 echo 和管道将密码传递给 sudo 命令
echo "$PASSWORD" | sudo -S chmod 777 /dev/tty*

# 检查命令是否执行成功
if [ $? -eq 0 ]; then
  echo "串口使能成功。"
else
  echo "串口使能成功失败，请检查密码或权限。"
fi

# 进入工作目录
cd /home/ymrobot/ros2_ws_guidance || { echo "Failed to enter /home/ymrobot/ros2_ws directory"; exit 1; }

# 设置 ROS 环境
source install/setup.bash

# 日志管理
LOG_PATH="/home/ymrobot/ros2_ws_guidance/ros2_logs"
LOG_BACKUP_PATH="/home/ymrobot/ros2_ws_guidance/ros2_logs.backup"
MAX_LOG_NUM=50  # 保留最新的 50 个日志
CRASH_LOG="$LOG_PATH/crash.log"

# 如果日志备份目录存在，则进行日志备份和清理
if [ -d "$LOG_BACKUP_PATH" ]; then
  # 将当前日志目录移动到备份目录
  if [ -d "$LOG_PATH" ]; then
    mv "$LOG_PATH" "$LOG_BACKUP_PATH/log.1"
  fi

  # 清理旧日志，保留最新的 $MAX_LOG_NUM 个日志
  cd "$LOG_BACKUP_PATH" || exit
  [ -d "log.$MAX_LOG_NUM" ] && rm -rf "log.$MAX_LOG_NUM"

  LOG_NUM=$((MAX_LOG_NUM - 1))
  while [ "$LOG_NUM" -gt 0 ]; do
    if [ -d "log.$LOG_NUM" ]; then
      AVAILABLE_SPACE=$(df -k . | tail -n 1 | awk '{print $4}')
      if [ "$AVAILABLE_SPACE" -lt 2097152 ]; then
        rm -rf "log.$LOG_NUM"  # 如果可用空间小于 2GB，直接删除旧日志
      else
        mv "log.$LOG_NUM" "log.$((LOG_NUM + 1))"  # 将日志编号递增
      fi
    fi
    LOG_NUM=$((LOG_NUM - 1))
  done
  cd /home/ymrobot/ros2_ws_guidance/ || exit
else
  # 如果日志备份目录不存在，则创建它
  mkdir -p "$LOG_BACKUP_PATH"
  if [ -d "$LOG_PATH" ]; then
    mv "$LOG_PATH" "$LOG_BACKUP_PATH/log.1"
  fi
fi

# 创建新的日志目录
mkdir -p "$LOG_PATH"

export RCUTILS_LOGGING_SEVERITY=INFO

# 启动 run_load_map.launch.py，并将日志追加到 crash.log
echo "Starting run_load_map.launch.py..."
ros2 launch /home/ymrobot/ros2_ws_guidance/src/guided-robot/launch/run.launch.py >> "$CRASH_LOG" 2>&1

echo "All launch files started successfully. Logs are saved in $CRASH_LOG."