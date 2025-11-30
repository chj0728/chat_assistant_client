#!/bin/bash

# 日志管理
LOG_PATH="/home/ymrobot/ros2_ws_guidance/ros2_logs"
LOG_BACKUP_PATH="/home/ymrobot/ros2_ws_guidance/ros2_logs.backup"
MAX_LOG_NUM=50  # 保留最新的 50 个日志
CRASH_LOG="$LOG_PATH/crash.log"

# 如果日志备份目录存在，则进行日志备份和清理
if [ -d "$LOG_BACKUP_PATH" ]; then
  # 获取当前时间戳，格式为年月日时分秒
  TIMESTAMP=$(date +"%Y%m%d%H%M%S")

  # 将当前日志目录移动到备份目录，并使用时间戳命名
  if [ -d "$LOG_PATH" ]; then
    mv "$LOG_PATH" "$LOG_BACKUP_PATH/$TIMESTAMP"
  fi

  # 清理旧日志，保留最新的 $MAX_LOG_NUM 个日志
  cd "$LOG_BACKUP_PATH" || exit
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
    mv "$LOG_PATH" "$LOG_BACKUP_PATH/$TIMESTAMP"
  fi
fi

# 创建新的日志目录
mkdir -p "$LOG_PATH"

chmod -R 777 "$LOG_PATH"
chmod -R 777 "$LOG_BACKUP_PATH"
chmod -R 777 "$LOG_BACKUP_PATH"

export RCUTILS_LOGGING_SEVERITY=INFO

echo "开始运行上传日志......."
chmod +x /home/ymrobot/ros2_ws_guidance/src/guided-robot/src/log_uploader_node/log_uploader_node/log_uploader_node.py
python3 /home/ymrobot/ros2_ws_guidance/src/guided-robot/src/log_uploader_node/log_uploader_node/log_uploader_node.py

# 检查日志上传脚本是否成功
if [ $? -eq 0 ]; then
  echo "日志上传成功。"
else
  echo "日志上传失败，请检查日志文件。"
  exit 1
fi

# 运行子脚本并记录日志

echo "开始运行 run_aud.sh..."
bash /home/ymrobot/run_aud.sh &
AUD_STATUS=$?
if [ $AUD_STATUS -ne 0 ]; then
  echo "run_aud.sh 执行失败，退出码: $AUD_STATUS" >> "$CRASH_LOG"
  exit $AUD_STATUS
fi

sleep 2

echo "开始运行 run_ymrobot.sh..."
bash /home/ymrobot/run_ymrobot.sh >> "$LOG_PATH/ymrobot.log" 2>&1 
YMROBOT_STATUS=$?
if [ $YMROBOT_STATUS -ne 0 ]; then
  echo "run_ymrobot.sh 执行失败，退出码: $YMROBOT_STATUS" >> "$CRASH_LOG"
  exit $YMROBOT_STATUS
fi

echo "所有脚本执行完成。"
