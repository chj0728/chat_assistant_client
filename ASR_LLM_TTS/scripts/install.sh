#!/bin/bash

SHELL_DIR=$(dirname "$(readlink -f "$0")")
VENV_DIR=$(cd "$SHELL_DIR/../../" && pwd)

# Check uv tool existence
if ! command -v uv &> /dev/null; then

    echo "[ERROR] uv tool not found."

    echo "[INFO] Trying to install uv tool..."
    # enter "y" to install uv tool
    read -p "Do you want to install uv tool now? (y/n): "
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        echo "[INFO] Installing uv tool..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
    else
        echo "[ERROR] uv tool installation aborted."
        exit 1
    fi

    # Check again if uv tool is installed
    if ! command -v uv &> /dev/null; then
        echo "[ERROR] uv tool installation failed. Please install it manually."
        exit 1
    fi
fi

# Check if the virtual environment exists
if [ ! -d "$VENV_DIR/venv" ]; then
    echo "[INFO] Virtual environment not found. Creating a new one..."

    cd "$VENV_DIR"
    uv venv venv --system-site-packages
    source "$VENV_DIR/venv/bin/activate"

    uv pip install -U -r ./ASR_LLM_TTS/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
    uv pip uninstall setuptools

    echo "[INFO] Virtual environment created and dependencies installed."
else
    echo "[INFO] Virtual environment already exists($VENV_DIR/venv). Skipping creation."

    # wheather to update dependencies
    read -p "Do you want to update the dependencies in the virtual environment? (y/n): "
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        echo "[INFO] Updating dependencies in the virtual environment..."
        source "$VENV_DIR/venv/bin/activate"
        cd "$VENV_DIR"
        uv pip install -U -r ./ASR_LLM_TTS/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
        uv pip uninstall setuptools
        echo "[INFO] Dependencies updated."
    else
        echo "[INFO] Skipping dependency update."
    fi
fi

echo "[INFO] Setup completed successfully."

echo "[INFO] You can now build the project using the build.sh script."