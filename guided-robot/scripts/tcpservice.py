import socket

def tcp_server(host='127.0.0.1', port=65432):
    # 创建一个 socket 对象
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        # 绑定地址和端口
        server_socket.bind((host, port))
        server_socket.listen()
        print(f"Server listening on {host}:{port}")

        # 接受客户端连接
        conn, addr = server_socket.accept()
        with conn:
            print(f"Connected by {addr}")
            while True:
                # 接收数据
                data = conn.recv(1024)
                if not data:
                    print("Client disconnected.")
                    break

                # 打印接收到的数据
                print(f"Received: {data.decode('utf-8')}")

                # 发送反馈（回显）
                conn.sendall(data)

if __name__ == "__main__":
    tcp_server()