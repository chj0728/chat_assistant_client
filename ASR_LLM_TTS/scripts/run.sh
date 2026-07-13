#!/usr/bin/env bash
set -e

# chat_assistant 进程守护脚本。
#
# 功能：
#   1. 加载 Python 虚拟环境及 ROS 2 工作空间；
#   2. 启动并监控 Web 服务和 ROS 2 节点；
#   3. 任一节点异常退出时，统一清理后重启全部节点；
#   4. 通过 PID 文件清理上一次异常退出后遗留的进程组。

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
WORK_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
PKG_DIR="$WORK_DIR/chat_assistant"
LOGS_DIR="$WORK_DIR/logs"
RUN_PID_FILE="$WORK_DIR/.run.pid"
NODE_PID_DIR="$WORK_DIR/.run.pids"

LOG_RETENTION_COUNT=40
RESTART_DELAY=1
SHUTDOWN_TIMEOUT=5

# 节点格式："名称|启动命令"。
# 每个节点均在独立进程组中运行，确保停止时可以同时清理其子进程。
NODES=(
    "web_server|python3 -m chat_assistant.web.web_server --host 0.0.0.0 --port 17890"
    "chat_assistant_node|ros2 run chat_assistant chat_assistant_node"
)

declare -A PIDS

# 停止 PID 文件中记录的旧守护脚本，避免同时运行多个 run.sh。
stop_previous_supervisor() {
    if [[ ! -f "$RUN_PID_FILE" ]]; then
        return
    fi

    local old_pid old_cmd
    old_pid=$(<"$RUN_PID_FILE")
    if [[ ! "$old_pid" =~ ^[0-9]+$ ]] || [[ "$old_pid" == "$$" ]]; then
        return
    fi
    if ! kill -0 "$old_pid" 2>/dev/null; then
        return
    fi

    old_cmd=$(ps -p "$old_pid" -o args= 2>/dev/null || true)
    if [[ "$old_cmd" != *"run.sh"* ]]; then
        echo "[WARN] Ignoring stale run PID file (PID=$old_pid)"
        return
    fi

    echo "[INFO] Found previous run.sh (PID=$old_pid), shutting it down..."
    kill -INT "$old_pid" 2>/dev/null || true
    local deadline=$((SECONDS + SHUTDOWN_TIMEOUT))
    while kill -0 "$old_pid" 2>/dev/null && (( SECONDS < deadline )); do
        sleep 0.1
    done
    if kill -0 "$old_pid" 2>/dev/null; then
        echo "[WARN] Previous run.sh did not exit in time, forcing exit"
        kill -KILL "$old_pid" 2>/dev/null || true
    fi
}

# 仅在 PID 文件仍属于当前脚本时删除它，避免误删新实例的记录。
cleanup_supervisor_pid() {
    if [[ -f "$RUN_PID_FILE" ]] && [[ "$(<"$RUN_PID_FILE")" == "$$" ]]; then
        rm -f "$RUN_PID_FILE"
    fi
}

# 判断指定进程组是否仍有进程存活。
is_process_group_running() {
    local pgid=$1
    kill -0 -- "-$pgid" 2>/dev/null
}

# 向本轮启动的所有存活节点进程组发送指定信号。
signal_all_nodes() {
    local signal=$1
    local name pid

    for name in "${!PIDS[@]}"; do
        pid=${PIDS[$name]}
        if is_process_group_running "$pid"; then
            echo "[INFO] Sending SIG$signal to $name (PGID=$pid)"
            kill -"$signal" -- "-$pid" 2>/dev/null || true
        fi
    done
}

# 等待本轮全部节点进程组退出，超时返回非零状态。
wait_for_all_nodes() {
    local deadline=$((SECONDS + SHUTDOWN_TIMEOUT))
    local pid running

    while (( SECONDS < deadline )); do
        running=false
        for pid in "${PIDS[@]}"; do
            if is_process_group_running "$pid"; then
                running=true
                break
            fi
        done

        if [[ "$running" == "false" ]]; then
            wait "${PIDS[@]}" 2>/dev/null || true
            return 0
        fi
        sleep 0.1
    done

    return 1
}

# 优雅停止全部节点；超时后升级为 SIGKILL，避免遗留子进程占用端口。
stop_all_nodes() {
    local signal=${1:-INT}

    signal_all_nodes "$signal"
    if wait_for_all_nodes; then
        return
    fi

    echo "[WARN] Node shutdown timed out after ${SHUTDOWN_TIMEOUT}s, forcing exit"
    signal_all_nodes KILL
    wait "${PIDS[@]}" 2>/dev/null || true
}

# 处理 Ctrl+C：停止所有节点并删除本轮运行状态。
shutdown() {
    echo "[INFO] Shutdown requested"
    trap - SIGINT SIGTERM
    stop_all_nodes INT
    rm -rf "$NODE_PID_DIR"
    echo "[INFO] Exit"
    exit 0
}

# SIGTERM 用作热重载信号：停止节点，由主循环负责重新启动。
reload() {
    echo "[INFO] Reload requested"
    signal_all_nodes TERM
}

# 清理上一次异常退出时记录的节点。
# 清理前会核对 PID 和启动命令，避免 PID 被复用后误杀无关进程。
cleanup_tracked_nodes() {
    local node_info name cmd pid_file old_pid old_cmd

    echo "[INFO] Checking for previously tracked node processes..."
    for node_info in "${NODES[@]}"; do
        name=${node_info%%|*}
        cmd=${node_info#*|}
        pid_file="$NODE_PID_DIR/${name}.pid"

        if [[ ! -f "$pid_file" ]]; then
            continue
        fi

        old_pid=$(<"$pid_file")
        if [[ ! "$old_pid" =~ ^[0-9]+$ ]] || ! kill -0 "$old_pid" 2>/dev/null; then
            rm -f "$pid_file"
            continue
        fi

        old_cmd=$(ps -p "$old_pid" -o args= 2>/dev/null || true)
        if [[ "$old_cmd" != *"$cmd"* ]]; then
            echo "[WARN] Ignoring stale PID file for $name (PID=$old_pid)"
            rm -f "$pid_file"
            continue
        fi

        echo "[INFO] Stopping previous $name process group (PGID=$old_pid)"
        kill -TERM -- "-$old_pid" 2>/dev/null || true
        sleep 0.5
        if is_process_group_running "$old_pid"; then
            kill -KILL -- "-$old_pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
    done
}

# 只保留最新的归档日志，避免日志目录无限增长。
cleanup_old_logs() {
    local log_entries=()
    local total_logs entry log_path

    mapfile -d '' log_entries < <(
        find "$LOGS_DIR" -maxdepth 1 -mindepth 1 \
            \( -type f -o -type d \) \
            -name 'asr_llm_tts.*' -printf '%T@\t%p\0' |
            sort -z -nr
    )

    total_logs=${#log_entries[@]}
    if (( total_logs <= LOG_RETENTION_COUNT )); then
        echo "[INFO] Log cleanup skipped, found $total_logs archived logs"
        return
    fi

    echo "[INFO] Cleaning archived logs, keeping latest $LOG_RETENTION_COUNT of $total_logs entries"
    for ((i = LOG_RETENTION_COUNT; i < total_logs; i++)); do
        entry=${log_entries[$i]}
        log_path=${entry#*$'\t'}
        echo "[INFO] Removing old log: $(basename "$log_path")"
        rm -rf "$log_path"
    done
}

# 启动全部节点，并记录进程组 ID，供停止和异常恢复使用。
start_all_nodes() {
    local node_info name cmd pid

    : > "$LOGS_DIR/nodes.log"
    for node_info in "${NODES[@]}"; do
        name=${node_info%%|*}
        cmd=${node_info#*|}

        echo "[INFO] Starting $name..."
        # 后台 shell 默认可能忽略 SIGINT，因此显式恢复信号并创建独立进程组。
        setsid env --default-signal=INT,QUIT \
            bash -c 'exec bash -c "$1"' _ "$cmd" &
        pid=$!

        PIDS["$name"]=$pid
        printf '%s\n' "$pid" > "$NODE_PID_DIR/${name}.pid"
        printf 'cmd: [%s], PID: [%s]\n' "$cmd" "$pid" >> "$LOGS_DIR/nodes.log"
    done
}

# 加载运行环境，并准备日志和 PID 目录。
prepare_environment() {
    echo "run.sh path: $SCRIPT_DIR"
    echo "work dir path: $WORK_DIR"

    cd "$WORK_DIR"
    source "$WORK_DIR/../venv/bin/activate"
    source "$WORK_DIR/install/setup.bash"

    mkdir -p "$LOGS_DIR" "$NODE_PID_DIR"
    cleanup_old_logs
    cleanup_tracked_nodes

    cd "$PKG_DIR"
}

# 持续监控节点；任一节点退出后，完整停止本轮节点再统一重启。
supervise_nodes() {
    local exit_code

    while true; do
        start_all_nodes

        # wait -n 的非零状态必须放在条件语句中处理，避免被 set -e 直接终止脚本。
        if wait -n "${PIDS[@]}"; then
            exit_code=0
        else
            exit_code=$?
        fi

        echo "[WARN] A process exited (code=$exit_code), restarting all nodes in $RESTART_DELAY seconds..."
        stop_all_nodes INT
        sleep "$RESTART_DELAY"
    done
}

# 脚本入口：初始化配置、接管旧实例，然后进入节点守护循环。
main() {
    # 可选参数 debug 用于向所有子进程传递调试模式。
    if [[ "${1:-}" == "debug" ]]; then
        export DEBUG_MODE=true
        echo "Debug mode enabled"
    else
        export DEBUG_MODE=false
        echo "Debug mode disabled"
    fi

    trap cleanup_supervisor_pid EXIT
    trap shutdown SIGINT
    trap reload SIGTERM

    stop_previous_supervisor
    printf '%s\n' "$$" > "$RUN_PID_FILE"
    prepare_environment
    supervise_nodes
}

# 直接执行脚本时进入主流程；被测试或其他脚本 source 时只加载函数。
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
