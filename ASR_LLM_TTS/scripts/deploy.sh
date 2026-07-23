#!/usr/bin/env bash
# 遇到命令失败、未定义变量或管道错误时立即退出，并让 ERR trap 可被函数继承。
set -Eeuo pipefail

# 使用绝对路径生成 Supervisor 配置，避免从其他目录执行时路径错误。
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
RUN_SCRIPT="$SCRIPT_DIR/run.sh"
SUPERVISOR_CONF="/etc/supervisor/conf.d/chat_agent.conf"
PROGRAM_NAME="chat_agent"

log() {
    printf '[INFO] %s\n' "$*"
}

fail() {
    printf '[ERROR] %s\n' "$*" >&2
    exit 1
}

usage() {
        cat <<EOF
用法: $(basename "$0") [命令]

命令:
    deploy    安装 Supervisor、更新配置并启动程序（默认）
    start     启动 $PROGRAM_NAME
    stop      停止 $PROGRAM_NAME
    restart   重启 $PROGRAM_NAME
    status    查看 $PROGRAM_NAME 状态
    reload    重新加载 Supervisor 服务及全部配置
    update    重新读取配置并应用变更
    logs      持续查看标准输出和错误日志
    help      显示此帮助信息
EOF
}

# Supervisor 未安装时，通过系统包管理器自动安装。
install_supervisor() {
    if command -v supervisord >/dev/null 2>&1 && command -v supervisorctl >/dev/null 2>&1; then
        log "Supervisor is already installed."
        return
    fi

    command -v apt-get >/dev/null 2>&1 || fail "apt-get is unavailable; please install Supervisor manually."

    log "Supervisor is not installed. Installing it now..."
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y supervisor
}

# 启动 Supervisor，并在 systemd 环境下设置为开机自启。
start_supervisor_service() {
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl enable --now supervisor
    else
        sudo service supervisor start
    fi
}

# 创建或更新程序配置，并补充访问用户 PipeWire/PulseAudio 会话所需的环境变量。
create_supervisor_config() {
    local deploy_user deploy_uid user_home user_runtime_dir user_bus
    local ros_domain_id ros_discovery_range temp_conf
    # 即使通过 sudo 执行脚本，也让业务进程以原登录用户身份运行。
    deploy_user=${SUDO_USER:-$(id -un)}
    deploy_uid=$(id -u "$deploy_user")
    user_home=$(getent passwd "$deploy_user" | cut -d: -f6)
    [[ -n "$user_home" ]] || fail "Unable to determine the home directory for user: $deploy_user"

    # 系统级 Supervisor 默认没有桌面用户会话环境，缺少这些变量时
    # sounddevice 可能无法连接 PipeWire，进而错误地回退到 HDMI 硬件设备。
    user_runtime_dir="/run/user/$deploy_uid"
    user_bus="unix:path=$user_runtime_dir/bus"
    if [[ ! -d "$user_runtime_dir" ]]; then
        log "Warning: user runtime directory does not exist: $user_runtime_dir"
        log "Audio playback requires user $deploy_user to have an active login session."
    fi

    # Supervisor 不会继承当前终端环境。ROS_DOMAIN_ID 不一致时，即使节点正常运行，
    # 用户终端中的 ros2 node/service 命令也无法通过 DDS 发现该节点。
    ros_domain_id=${ROS_DOMAIN_ID:-0}
    ros_discovery_range=${ROS_AUTOMATIC_DISCOVERY_RANGE:-SUBNET}
    [[ "$ros_domain_id" =~ ^[0-9]+$ ]] || fail "ROS_DOMAIN_ID must be a non-negative integer: $ros_domain_id"
    log "Using ROS_DOMAIN_ID=$ros_domain_id, ROS_AUTOMATIC_DISCOVERY_RANGE=$ros_discovery_range"

    # 先写入临时文件，再由 install 原子地复制到系统配置目录。
    temp_conf=$(mktemp)

    cat > "$temp_conf" <<EOF
[program:$PROGRAM_NAME]
directory=$SCRIPT_DIR
command=/bin/bash -c "exec ./run.sh"
user=$deploy_user
autostart=true
autorestart=true
startsecs=10
# run.sh 使用 SIGINT 执行优雅清理；同时停止整个进程组，避免遗留子进程。
stopsignal=INT
stopasgroup=true
killasgroup=true
environment=HOME="$user_home",USER="$deploy_user",XDG_RUNTIME_DIR="$user_runtime_dir",DBUS_SESSION_BUS_ADDRESS="$user_bus",PULSE_SERVER="unix:$user_runtime_dir/pulse/native",ROS_DOMAIN_ID="$ros_domain_id",ROS_AUTOMATIC_DISCOVERY_RANGE="$ros_discovery_range"
stderr_logfile=/var/log/chat_agent.err.log
stdout_logfile=/var/log/chat_agent.out.log
EOF

    if sudo test -f "$SUPERVISOR_CONF" && sudo cmp -s "$temp_conf" "$SUPERVISOR_CONF"; then
        log "Supervisor configuration is already up to date: $SUPERVISOR_CONF"
        rm -f "$temp_conf"
        return
    fi

    if sudo test -f "$SUPERVISOR_CONF"; then
        log "Updating Supervisor configuration: $SUPERVISOR_CONF"
    else
        log "Creating Supervisor configuration: $SUPERVISOR_CONF"
    fi
    sudo install -m 0644 "$temp_conf" "$SUPERVISOR_CONF"
    rm -f "$temp_conf"
}

# 通知 Supervisor 读取新配置，并确保 chat_agent 处于启动状态。
reload_supervisor() {
    local program_state

    log "Reloading Supervisor configuration..."
    sudo supervisorctl reread
    sudo supervisorctl update

    # status 在程序尚未注册或已停止时可能返回非零，不能让脚本因此提前退出。
    program_state=$(sudo supervisorctl status "$PROGRAM_NAME" 2>/dev/null | awk '{print $2}' || true)
    case "$program_state" in
        RUNNING|STARTING)
            ;;
        *)
            sudo supervisorctl start "$PROGRAM_NAME"
            ;;
    esac

    sudo supervisorctl status "$PROGRAM_NAME"
}

# 执行完整部署流程；不传参数时默认调用此函数。
deploy() {
    [[ -f "$RUN_SCRIPT" ]] || fail "run.sh not found: $RUN_SCRIPT"
    [[ -x "$RUN_SCRIPT" ]] || fail "run.sh is not executable; run: chmod +x '$RUN_SCRIPT'"

    install_supervisor
    start_supervisor_service
    create_supervisor_config
    reload_supervisor

    log "Deployment completed."
    log "Logs: /var/log/chat_agent.out.log and /var/log/chat_agent.err.log"
}

# 将常用 supervisorctl 操作统一封装到部署脚本中。
main() {
    local command=${1:-deploy}

    command -v sudo >/dev/null 2>&1 || fail "sudo is required to manage Supervisor."

    case "$command" in
        deploy)
            deploy
            ;;
        start|stop|restart|status)
            sudo supervisorctl "$command" "$PROGRAM_NAME"
            ;;
        reload)
            # reload 会重启 supervisord，并重新加载所有受管程序的配置。
            sudo supervisorctl reload
            ;;
        update)
            sudo supervisorctl reread
            sudo supervisorctl update
            sudo supervisorctl status "$PROGRAM_NAME"
            ;;
        logs)
            sudo tail -n 100 -f /var/log/chat_agent.out.log /var/log/chat_agent.err.log
            ;;
        help|-h|--help)
            usage
            ;;
        *)
            usage >&2
            fail "Unknown command: $command"
            ;;
    esac
}

main "$@"
