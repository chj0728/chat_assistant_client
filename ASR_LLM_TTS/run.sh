#!/bin/bash
sleep 10
# ===================== 配置区 =====================
ENABLE_SCRIPT=true
CURRENT_USER=$(id -un 2>/dev/null || echo "unknown_user") #POSIX标准
SHELL_DIR=$(dirname $(readlink -f "$0"))
WORK_DIR=$(cd "$SHELL_DIR/chat_assistant" && pwd)
# =====================================================


# 检查标志位
if [ "$ENABLE_SCRIPT" != "true" ]; then
    echo "Script execution is disabled (ENABLE_SCRIPT=$ENABLE_SCRIPT)"
    exit 0
fi

# 定义一个函数，当按下 CTRL+C 时停止所有后台进程
cleanup() {
    echo "Stopping all processes..."
    #使用 kill 停止所有后台进程
    kill $(jobs -p)
    wait
    echo "All processes stopped."
    exit 0
}

# 捕获 SIGINT 信号 (CTRL+C)
trap cleanup SIGINT

# 启动 ROS 环境
cd "$SHELL_DIR" || {
    echo "Failed to enter SHELL_DIR directory!"
    exit 1
}
echo "Current path: $(pwd)"

source install/setup.bash
source venv/bin/activate

cd "$WORK_DIR" || {
    echo "Failed to enter WORK_DIR directory!"
    exit 1
}
echo "Current path: $(pwd)"

# 启动 chat_assistant_node.py
echo "Starting chat_assistant_node.py..."
python3 -m chat_assistant.chat_assistant_node & > /dev/null
CHAT_ASSISTANT_PID=$!
echo "chat_assistant_node.py started with PID $CHAT_ASSISTANT_PID"

# 等待所有后台进程完成
wait $CHAT_ASSISTANT_PID