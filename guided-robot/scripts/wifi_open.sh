#!/bin/bash

# 检查是否以 root 权限运行
if [ "$EUID" -ne 0 ]; then
  echo "请以 root 权限运行此脚本。"
  exit 1
fi

# 检查是否提供了参数
if [ $# -ne 1 ]; then
  echo "使用方法: $0 [on|off]"
  echo "  on   - 开启 Wi-Fi"
  echo "  off  - 关闭 Wi-Fi"
  exit 1
fi

# 获取 Wi-Fi 接口名称
WIFI_INTERFACE=$(nmcli device | grep wifi | awk '{print $1}')

if [ -z "$WIFI_INTERFACE" ]; then
  echo "未找到 Wi-Fi 接口。"
  exit 1
fi

# 根据参数开启或关闭 Wi-Fi
case "$1" in
  on)
    echo "正在开启 Wi-Fi..."
    nmcli radio wifi on
    nmcli device connect "$WIFI_INTERFACE"
    ;;
  off)
    echo "正在关闭 Wi-Fi..."
    nmcli radio wifi off
    ;;
  *)
    echo "无效的参数。使用方法: $0 [on|off]"
    exit 1
    ;;
esac

echo "操作完成。"