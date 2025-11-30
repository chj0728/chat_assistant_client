#!/bin/bash

# 获取脚本所在目录的上级目录
RUNNING_PATH="$(cd "$(dirname "$(readlink -f "$0")")"/.. && pwd)"

# 地图保存路径为 assets 目录
MAPS_DIR="$RUNNING_PATH/assets"  # assets 目录路径
WORKSPACE_PATH="$(cd "$SCRIPT_DIR/../../" && pwd)"
PCD_FILE="$MAPS_DIR/map.pcd"

# 调用 ROS 2 服务保存地图
cd "${WORKSPACE}"
source install/setup.bash
ros2 service call /pgo/save_maps interface/srv/SaveMaps "{file_path: \"$MAPS_DIR\", save_patches: false}"

echo "地图已保存到 $MAPS_DIR"

# 保存完地图后休眠1秒
sleep 1

# 启动launch文件
echo "启动 launch 文件"
ros2 launch pcd2pgm pcd2pgm.launch.py PCD_FILE_PATH:="$PCD_FILE"

# 休眠1.5秒
sleep 1.5

# 运行 map_saver_cli
echo "运行 map_saver_cli 保存地图"
ros2 run nav2_map_server map_saver_cli -f "$MAPS_DIR/map"

echo "地图保存并导出完成！"
