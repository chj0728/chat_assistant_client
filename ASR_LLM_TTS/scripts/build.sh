#!/bin/bash

SHELL_DIR=$(dirname "$(readlink -f "$0")")
WORK_DIR=$(cd "$SHELL_DIR/../" && pwd)

filter_prefix_path() {
    local var_name="$1"
    local var_value="${!var_name}"
    local filtered=""
    local entry

    IFS=':' read -r -a entries <<< "$var_value"
    for entry in "${entries[@]}"; do
        [[ -z "$entry" ]] && continue
        if [[ -d "$entry" ]]; then
            if [[ -n "$filtered" ]]; then
                filtered+=" :$entry"
            else
                filtered="$entry"
            fi
        fi
    done

    filtered="${filtered// :/:}"
    export "$var_name=$filtered"
}

cd "$SHELL_DIR"
echo "Current path: $(pwd)"

# remove the existing build directory if it exists
if [ -d "$WORK_DIR/build" ]; then
    echo "[INFO] Removing existing build directory: $WORK_DIR/build"
    rm -rf "$WORK_DIR/build"
fi
if [ -d "$WORK_DIR/install" ]; then
    echo "[INFO] Removing existing install directory: $WORK_DIR/install"
    rm -rf "$WORK_DIR/install"
fi
if [ -d "$WORK_DIR/log" ]; then
    echo "[INFO] Removing existing logs directory: $WORK_DIR/log"
    rm -rf "$WORK_DIR/log"
fi

filter_prefix_path AMENT_PREFIX_PATH
filter_prefix_path CMAKE_PREFIX_PATH
filter_prefix_path COLCON_PREFIX_PATH

# source the uv venv
if [ -f "$WORK_DIR/../venv/bin/activate" ]; then
    echo "[INFO] Sourcing virtual environment: $WORK_DIR/../venv"
    source "$WORK_DIR/../venv/bin/activate"
else
    echo "[ERROR] Virtual environment not found: $WORK_DIR/../venv"
    echo "[INFO] Please create a virtual environment and install the required dependencies at $WORK_DIR/../venv"
    exit 1
fi

# build the package
echo "[INFO] Building the package(in $WORK_DIR)..."
cd "$WORK_DIR"
python -m colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release

# check if the build was successful
if [ $? -ne 0 ]; then
    echo "[ERROR] Build failed. Please check the output above for errors."
    exit 1
fi

# check if the install/setup.bash file exists
if [ ! -f "$WORK_DIR/install/setup.bash" ]; then
    echo "[ERROR] Install setup.bash not found: $WORK_DIR/install/setup.bash"
    echo "[INFO] Please check if the build was successful and the install directory was created."
    exit 1
fi

echo "[INFO] Build and installation completed successfully."