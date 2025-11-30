#!/bin/bash

# 固定输入和输出日志文件名
input_file="/home/ymrobot/ros2_ws/ros2_logs/crash.log"
output_file="/home/ymrobot/ros2_ws/ros2_logs/crash_time.log"

# 检查输入文件是否存在
if [ ! -f "$input_file" ]; then
    echo "Error: Input log file '$input_file' not found."
    exit 1
fi

# 处理日志文件
while IFS= read -r line; do
    if [[ -n "$line" ]]; then  # 忽略空行
        # 提取时间戳和日志内容
        timestamp=$(echo "$line" | awk '{print $1}')
        log_content=$(echo "$line" | cut -d' ' -f2-)

        # 将 Unix 时间戳转换为年月日 时分秒.毫秒
        if [[ "$timestamp" =~ ^[0-9]+\.[0-9]+$ ]]; then
            seconds=$(echo "$timestamp" | cut -d. -f1)
            nanoseconds=$(echo "$timestamp" | cut -d. -f2)
            milliseconds=$(echo "$nanoseconds" | cut -c1-3)  # 取前三位作为毫秒

            # 使用 date 命令格式化时间
            formatted_time=$(date -d @"$seconds" "+%Y-%m-%d %H:%M:%S").$milliseconds
            echo "$formatted_time $log_content" >> "$output_file"
        else
            echo "$line" >> "$output_file"  # 如果格式不对，直接写入原行
        fi
    fi
done < "$input_file"

echo "Log file processed. Converted log saved to $output_file"