import rclpy
from rclpy.node import Node
from ymrobot_msgs.srv import LargeModelRequestTask
import time
import threading

class AudioServiceServerNode(Node):
    def __init__(self):
        super().__init__('audio_service_server_node')
        self.srv = self.create_service(LargeModelRequestTask, 'audio_service', self.audio_service_callback)
        self.get_logger().info('音频服务服务端已启动')

    def audio_service_callback(self, request, response):
        # 记录接收到的请求详情
        self.get_logger().info(
            f'收到服务请求: '
            f'task_type={request.larget_mode_task_type}, '
            f'mark_point_name={request.mark_point_name}, '
            f'mark_point_name_list={request.mark_point_name_list}, '
            f'guidance_task_name={request.guidance_task_name}'
        )

        # 直接在回调中处理，避免使用额外线程
        try:
            # 模拟5秒处理时间
            time.sleep(5)
            
            # 明确设置响应
            response.success = True
            response.message = f"成功执行任务: {request.mark_point_name}"
            
            # 记录响应日志
            self.get_logger().info(f'服务处理完成: {response.message}')
            
            return response
        except Exception as e:
            # 处理任何可能的异常
            self.get_logger().error(f"服务处理发生错误: {e}")
            response.success = False
            response.message = str(e)
            return response

def main(args=None):
    # 初始化ROS2
    rclpy.init(args=args)

    # 创建服务节点
    audio_service_server = AudioServiceServerNode()

    try:
        # 持续运行节点
        rclpy.spin(audio_service_server)
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在关闭服务...")
    finally:
        # 销毁节点
        audio_service_server.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()