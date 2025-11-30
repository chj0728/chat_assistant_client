#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import os
import numpy as np
from datetime import datetime

class ImageCaptureNode(Node):
    def __init__(self):
        super().__init__('image_capture_node')
        
        # 初始化工具
        self.bridge = CvBridge()
        self.current_frame = None
        self.frame_ready = False
        
        # 订阅图像topic
        self.subscription = self.create_subscription(
            Image,
            '/image_raw',
            self.image_callback,
            10)
        
        # 创建显示窗口
        cv2.namedWindow("Current Frame", cv2.WINDOW_NORMAL)
        
        self.get_logger().info("图像捕获节点已启动，等待数据...")

    def image_callback(self, msg):
        """图像回调函数，持续更新最新帧"""
        try:
            self.current_frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.frame_ready = True
            
            # 实时显示当前帧
            self.display_frame()
            
            # 打印帧信息（调试用）
            self.print_frame_info()
            
        except Exception as e:
            self.get_logger().error(f'图像转换失败: {str(e)}')

    def display_frame(self):
        """显示当前帧到OpenCV窗口"""
        if self.current_frame is not None:
            display_frame = cv2.resize(self.current_frame, (640, 480))  # 统一显示尺寸
            cv2.imshow("Current Frame", display_frame)
            cv2.waitKey(1)

    def print_frame_info(self):
        """打印当前帧信息到终端"""
        if self.current_frame is not None:
            print("\n=== 当前帧信息 ===")
            print(f"尺寸: {self.current_frame.shape[1]}x{self.current_frame.shape[0]}")
            print(f"通道数: {self.current_frame.shape[2] if len(self.current_frame.shape) > 2 else 1}")
            print(f"数据类型: {self.current_frame.dtype}")
            print(f"像素值范围: B[{np.min(self.current_frame[:,:,0])}-{np.max(self.current_frame[:,:,0])}] "
                  f"G[{np.min(self.current_frame[:,:,1])}-{np.max(self.current_frame[:,:,1])}] "
                  f"R[{np.min(self.current_frame[:,:,2])}-{np.max(self.current_frame[:,:,2])}]")
            print("=================\n")

    def capture_frame(self, save_path=None):
        """
        捕获当前帧为PNG格式并返回图像数据
        参数:
            save_path: 可选的文件保存路径
        返回:
            (success, image_data) 元组
        """
        if not self.frame_ready:
            self.get_logger().warning("无可用图像帧")
            return (False, None)
        
        try:
            # 编码为PNG
            ret, png_data = cv2.imencode('.png', self.current_frame)
            
            if not ret:
                self.get_logger().error("PNG编码失败")
                return (False, None)
            
            # 保存到文件（如果指定路径）
            if save_path is not None:
                os.makedirs(save_path, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = f"frame_{timestamp}.png"
                full_path = os.path.join(save_path, filename)
                with open(full_path, 'wb') as f:
                    f.write(png_data.tobytes())
                self.get_logger().info(f"图像已保存至: {full_path}")
            
            return (True, png_data.tobytes())
            
        except Exception as e:
            self.get_logger().error(f'捕获帧时出错: {str(e)}')
            return (False, None)

    def destroy_node(self):
        cv2.destroyAllWindows()
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = ImageCaptureNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()