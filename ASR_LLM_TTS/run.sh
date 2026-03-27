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
    # 解除信号捕获，防止多次按 Ctrl+C 重复触发卡死
    trap - SIGINT SIGTERM 

    if [[ -n "$CHAT_PID" ]] && kill -0 "$CHAT_PID" 2>/dev/null; then
        echo "[INFO] Killing chat_assistant_node (PID=$CHAT_PID)"
        kill -SIGTERM "$CHAT_PID" 2>/dev/null || true
    fi
    if [[ -n "$LOG_WEB_PID" ]] && kill -0 "$LOG_WEB_PID" 2>/dev/null; then
        echo "[INFO] Killing log_web_server (PID=$LOG_WEB_PID)"
        kill -SIGTERM "$LOG_WEB_PID" 2>/dev/null || true
    fi
    
    # 给程序 1 秒钟的优雅退出时间，如果卡死则用 SIGKILL 强制终结
    sleep 1
    
    if [[ -n "$CHAT_PID" ]] && kill -0 "$CHAT_PID" 2>/dev/null; then
        kill -9 "$CHAT_PID" 2>/dev/null || true
    fi
    if [[ -n "$LOG_WEB_PID" ]] && kill -0 "$LOG_WEB_PID" 2>/dev/null; then
        kill -9 "$LOG_WEB_PID" 2>/dev/null || true
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
        kill -SIGTERM "$CHAT_PID" 2>/dev/null || true
    fi
    if [[ -n "$LOG_WEB_PID" ]] && kill -0 "$LOG_WEB_PID" 2>/dev/null; then
        kill -SIGTERM "$LOG_WEB_PID" 2>/dev/null || true
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
    echo "[INFO] Starting log_web_server..."
    python3 -m chat_assistant.log_web_server --host 0.0.0.0 --port 17890 &
    LOG_WEB_PID=$!
    echo "log_web_server.py started with PID $LOG_WEB_PID" &> "$SHELL_DIR/log_web_server.log"

    echo "[INFO] Starting chat_assistant_node..."
    python3 -m chat_assistant.chat_assistant_node &
    CHAT_PID=$!
    echo "chat_assistant_node.py started with PID $CHAT_PID" &> "$SHELL_DIR/chat_assistant_node.log"

    # 等待任意一个后台进程退出
    wait -n "$CHAT_PID" "$LOG_WEB_PID"
    EXIT_CODE=$?

    echo "[WARN] A process exited (code=$EXIT_CODE), restarting..."
    
    # 清理遗留进程
    if kill -0 "$CHAT_PID" 2>/dev/null; then
        kill -SIGTERM "$CHAT_PID"
    fi
    if kill -0 "$LOG_WEB_PID" 2>/dev/null; then
        kill -SIGTERM "$LOG_WEB_PID"
    fi
    
    sleep "$RESTART_DELAY"
done
