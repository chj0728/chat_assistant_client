#!/bin/bash
export PYTHONDONTWRITEBYTECODE=1
cd /home/cat/ros2_ws || { echo "Failed to enter /home/cat/ros2_ws directory"; exit 1; }

source install/setup.bash

sleep 0.5

ros2 launch ./src/ceiling/launch/display.launch.py
