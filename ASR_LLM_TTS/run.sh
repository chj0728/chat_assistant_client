#!/bin/bash
set -e

sleep 1

# ===================== 配置区 =====================
ENABLE_SCRIPT=true
CURRENT_USER=$(id -un 2>/dev/null || echo "unknown_user")
SHELL_DIR=$(dirname "$(readlink -f "$0")")
WORK_DIR=$(cd "$SHELL_DIR/chat_assistant" && pwd)
RESTART_DELAY=1
# =================================================

if [ "$ENABLE_SCRIPT" != "true" ]; then
    echo "Script execution is disabled"
    exit 0
fi

CHAT_PID=""

##########################
# 彻底退出（Ctrl+C）
##########################
shutdown() {
    echo "[INFO] Shutdown requested"
    if [[ -n "$CHAT_PID" ]] && kill -0 "$CHAT_PID" 2>/dev/null; then
        echo "[INFO] Killing chat_assistant_node (PID=$CHAT_PID)"
        kill -SIGINT "$CHAT_PID"
        wait "$CHAT_PID"
    fi
    echo "[INFO] Exit"
    exit 0
}

##########################
# 热重载（kill 默认）
##########################
reload() {
    echo "[INFO] Reload requested"
    if [[ -n "$CHAT_PID" ]] && kill -0 "$CHAT_PID" 2>/dev/null; then
        kill -SIGINT "$CHAT_PID"
        wait "$CHAT_PID"
    fi
}

trap shutdown SIGINT
trap reload SIGTERM

##########################
# 环境准备
##########################
cd "$SHELL_DIR"
echo "Current path: $(pwd)"

source install/setup.bash
source venv/bin/activate

cd "$WORK_DIR"
echo "Current path: $(pwd)"

##########################
# 主循环：守护进程
##########################
while true; do
    echo "[INFO] Starting chat_assistant_node..."
    python3 -m chat_assistant.chat_assistant_node &
    CHAT_PID=$!

    # 保存日志到 $SHELL_DIR/chat_assistant_node.log
    echo "chat_assistant_node.py started with PID $CHAT_PID" &> "$SHELL_DIR/chat_assistant_node.log"

    wait "$CHAT_PID"
    EXIT_CODE=$?

    echo "[WARN] chat_assistant_node exited (code=$EXIT_CODE)"

    sleep "$RESTART_DELAY"
done
