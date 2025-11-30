import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String
from rcl_interfaces.msg import Log
import os
from datetime import datetime

class Ros2Logger(Node):
    def __init__(self):
        super().__init__('ros2_logger')
        # 获取脚本所在路径的上上级目录
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

        # 在上上级目录中创建 ros2_logs 文件夹
        log_dir = os.path.join(base_dir, "ros2_logs")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"ros2_combined_{timestamp}.log")

        self.get_logger().info(f"Logging to file: {self.log_file}")

        qos = QoSProfile(depth=10)
        self.subscription = self.create_subscription(
            Log,
            '/rosout',
            self.log_callback,
            qos
        )

    def log_callback(self, msg):
        """处理从 /rosout 收到的日志消息并写入文件"""
        # 构建日志内容
        log_entry = f"[{msg.stamp.sec}.{msg.stamp.nanosec}] [{msg.level}] {msg.name}: {msg.msg}\n"

        # 过滤掉 rviz 的日志
        if "rviz" not in msg.name:
            # 保存日志到文件
            with open(self.log_file, 'a') as file:
                file.write(log_entry)

def main(args=None):
    rclpy.init(args=args)
    node = Ros2Logger()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down ROS 2 Logger...")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
