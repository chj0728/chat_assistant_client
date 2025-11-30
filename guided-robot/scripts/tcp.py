import socket

def tcp_client(host='192.168.10.10', port=31001):
    # 创建一个 socket 对象
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        # 连接到服务器
        client_socket.connect((host, port))
        print(f"Connected to server at {host}:{port}")
        message = "/api/position_adjust"
        # 发送数据

        # 发送消息到服务器
        client_socket.sendall(message.encode('utf-8'))
        print(f"Sent: {message}")
        while True:


            # 接收服务器的反馈
            data = client_socket.recv(2048)

            print(f"Received: {data.decode('utf-8')}")

if __name__ == "__main__":
    tcp_client()