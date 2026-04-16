#!/bin/bash
set -e

sleep 1

# 读取动态参数 debug ,设置环境变量
# example: ./run.sh debug
if [[ "$1" == "debug" ]]; then
    export DEBUG_MODE=true
    echo "Debug mode enabled"
else
    export DEBUG_MODE=false
    echo "Debug mode disabled"
fi

# ===================== 配置区 =====================
ENABLE_SCRIPT=true
SHELL_DIR=$(dirname "$(readlink -f "$0")")
WORK_DIR=$(cd "$SHELL_DIR/chat_assistant" && pwd)
RESTART_DELAY=1
# =================================================

if [ "$ENABLE_SCRIPT" != "true" ]; then
    echo "Script execution is disabled"
    exit 0
fi

RUN_PID_FILE="$SHELL_DIR/.run.pid"

if [[ -f "$RUN_PID_FILE" ]]; then
    old_run_pid=$(cat "$RUN_PID_FILE")
    if [[ -n "$old_run_pid" ]] && kill -0 "$old_run_pid" 2>/dev/null && [[ "$old_run_pid" != "$$" ]]; then
        echo "[INFO] Found previous run.sh (PID=$old_run_pid), shutting it down..."
        kill -INT "$old_run_pid" 2>/dev/null || true
        # Wait a bit for the previous script to shutdown child processes gracefully
        sleep 1.5
        kill -9 "$old_run_pid" 2>/dev/null || true
    fi
fi
echo $$ > "$RUN_PID_FILE"

# ===================== 节点配置区 =====================
# 格式: "节点名称|启动命令"
# 方便后续添加新节点，只需在此数组中追加即可
NODES=(
    "web_server|python3 -m chat_assistant.web.web_server --host 0.0.0.0 --port 17890"
    "chat_assistant_node|python3 -m chat_assistant.chat_assistant_node"
)

declare -A PIDS

##########################
# 进程管理模块
##########################
kill_all_nodes() {
    local sig=$1
    for name in "${!PIDS[@]}"; do
        local pid="${PIDS[$name]}"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "[INFO] Killing $name (PID=$pid) with SIG$sig"
            kill -"$sig" "$pid" 2>/dev/null || true
        fi
    done
}

shutdown() {
    echo "[INFO] Shutdown requested"
    trap - SIGINT SIGTERM 

    kill_all_nodes TERM
    sleep 1
    kill_all_nodes KILL
    
    echo "[INFO] Exit"
    rm -f "$RUN_PID_FILE"
    exit 0
}

reload() {
    echo "[INFO] Reload requested"
    kill_all_nodes TERM
}

cleanup_legacy_nodes() {
    echo "[INFO] Checking for legacy processes in log files..."
    for node_info in "${NODES[@]}"; do
        local name="${node_info%%|*}"
        local log_file="$SHELL_DIR/${name}.log"
        if [[ -f "$log_file" ]]; then
            local old_pid=$(grep -o 'PID [0-9]*' "$log_file" | awk '{print $2}')
            if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
                echo "[INFO] Legacy process $name (PID=$old_pid) is still running. Killing it..."
                kill -TERM "$old_pid" 2>/dev/null || true
                sleep 0.5
                kill -9 "$old_pid" 2>/dev/null || true
            fi
        fi
    done
}

start_all_nodes() {
    for node_info in "${NODES[@]}"; do
        local name="${node_info%%|*}"
        local cmd="${node_info#*|}"
        
        echo "[INFO] Starting $name..."
        $cmd &
        local pid=$!
        PIDS["$name"]=$pid
        echo "$cmd started with PID $pid" &> "$SHELL_DIR/${name}.log"
    done
}

wait_any_node() {
    local pid_list=("${PIDS[@]}")
    wait -n "${pid_list[@]}"
}

trap shutdown SIGINT
trap reload SIGTERM

##########################
# 环境准备
##########################
cd "$SHELL_DIR"
echo "Current path: $(pwd)"

source install/setup.bash
source ../venv/bin/activate

cd "$WORK_DIR"
echo "Current path: $(pwd)"

# 清理记录在日志中的历史遗留进程
cleanup_legacy_nodes

##########################
# 主循环：守护进程
##########################
while true; do
    # 启动所有节点
    start_all_nodes
    
    # 等待任意一个后台进程退出
    wait_any_node
    EXIT_CODE=$?

    echo "[WARN] A process exited (code=$EXIT_CODE), restarting all nodes in $RESTART_DELAY seconds..."
    
    # 清理遗留进程
    kill_all_nodes TERM
    
    sleep "$RESTART_DELAY"
done