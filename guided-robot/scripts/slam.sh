#!/bin/bash

# 1. 编译 LIVOX-SDK2
echo "编译 LIVOX-SDK2..."
cd Livox-SDK2/
mkdir -p build
cd build
cmake .. && make -j
sudo make install
echo "LIVOX-SDK2 编译完成。"

# 2. 编译 Sophus
echo "编译 Sophus..."
cd ../../Sophus
mkdir -p build
cd build
cmake .. -DSOPHUS_USE_BASIC_LOGGING=ON
make
sudo make install
echo "Sophus 编译完成。"

# 3. 编译 livox_ros_driver2
echo "编译 livox_ros_driver2..."
cd ../../livox_ros_driver2
source /opt/ros/humble/setup.sh
./build.sh humble
echo "livox_ros_driver2 编译完成。"

echo "所有编译任务已完成。"
