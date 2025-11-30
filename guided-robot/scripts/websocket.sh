#!/bin/bash

# 检查是否传入正确的参数
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <html_file> <old_ip> <new_ip>"
    echo "Example: $0 index.html 172.16.20.190 192.168.1.100"
    exit 1
fi

# 参数
HTML_FILE=$1
OLD_IP=$2
NEW_IP=$3

# 检查 HTML 文件是否存在
if [ ! -f "$HTML_FILE" ]; then
    echo "Error: File $HTML_FILE does not exist."
    exit 1
fi

# 替换 IP 地址
sed -i "s/$OLD_IP/$NEW_IP/g" "$HTML_FILE"
if [ $? -ne 0 ]; then
    echo "Error: Failed to update IP address."
    exit 1
fi
echo "IP address updated successfully from $OLD_IP to $NEW_IP in $HTML_FILE."

# 启动 HTTP 服务器
echo "Starting HTTP server to serve $HTML_FILE..."
python3 -m http.server 8000 --directory "$(dirname "$HTML_FILE")" &
SERVER_PID=$!

echo "HTTP server is running. Open your browser and visit http://localhost:8080/$(basename "$HTML_FILE")"
echo "Press Ctrl+C to stop the server."

# 捕获终止信号以停止服务器
trap "kill $SERVER_PID; echo 'HTTP server stopped.'; exit 0" INT

# 等待用户手动停止
wait $SERVER_PID
