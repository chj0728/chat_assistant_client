#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

source "$WORKSPACE_DIR/install/setup.bash"

PYTHON_SCRIPT="$SCRIPT_DIR/ros2_logger.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
  echo "Error: Python script $PYTHON_SCRIPT not found!"
  exit 1
fi

echo "Running ROS 2 logger from $PYTHON_SCRIPT..."
python3 "$PYTHON_SCRIPT"
