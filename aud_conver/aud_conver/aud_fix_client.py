#!/usr/bin/env python3
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from ymrobot_msgs.action import AudioControl
import time
import threading

class AudioClientNode(Node):
    def __init__(self):
        super().__init__('audio_client_node')
        
        self._action_client = ActionClient(
            self, 
            AudioControl, 
            'audio_control_action'
        )
        
        self.get_logger().info('等待Action Server...')
        if not self._action_client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error('Action Server 连接超时！')
            return
            
        self.get_logger().info('Action Server 已连接！')
        
    def send_goal_with_cancel(self):
        goal_msg = AudioControl.Goal()
        goal_msg.audio_task_type = 0
        goal_msg.fixed_audio_name = '0'  # 将映射到 101.mp3
        goal_msg.timbre = 0
        
        self.get_logger().info('发送Action Goal...')
        
        # 发送目标
        send_goal_future = self._action_client.send_goal_async(
            goal_msg, 
            feedback_callback=self.feedback_callback
        )
        
        # 等待发送完成
        rclpy.spin_until_future_complete(self, send_goal_future)
        
        # 获取结果
        self.goal_handle = send_goal_future.result()
        if self.goal_handle is None:
            self.get_logger().error('发送Goal失败！')
            return False
            
        # 不要访问可能不存在的属性
        self.get_logger().info('Goal发送完成')
        
        if not hasattr(self.goal_handle, 'accepted') or not self.goal_handle.accepted:
            self.get_logger().error('Goal未被服务器接受')
            return False
            
        self.get_logger().info(f'Goal被接受, ID={self.goal_handle.goal_id}')
        
        # 等待一段时间后使用另一种方式取消 - 发送task_type=1的新请求
        self.get_logger().info('音频正在播放...')
        for i in range(3):
            self.get_logger().info(f'音频播放中... {i+1}秒')
            time.sleep(1.0)
            
        self.get_logger().info('尝试通过原始取消API取消...')
        try:
            # 尝试使用标准取消API
            if hasattr(self.goal_handle, 'cancel_goal_async'):
                cancel_future = self.goal_handle.cancel_goal_async()
                self.get_logger().info('取消请求已发送，等待结果...')
                
                rclpy.spin_until_future_complete(self, cancel_future)
                try:
                    cancel_result = cancel_future.result()
                    if cancel_result is not None:
                        self.get_logger().info(f'取消请求结果: {cancel_result.return_code}')
                except Exception as e:
                    self.get_logger().error(f'处理取消结果时出错: {e}')
        except Exception as e:
            self.get_logger().error(f'发送取消请求时出错: {e}')
            
        # 等待1秒看是否已经取消
        time.sleep(1.0)
            
        # 使用task_type=1的新请求作为备选方案
        self.get_logger().info('通过发送task_type=1的新请求方式取消...')
        cancel_goal_msg = AudioControl.Goal()
        cancel_goal_msg.audio_task_type = 1  # 停止命令
        cancel_goal_msg.fixed_audio_name = '0'  # 不重要，但需要有效值
        cancel_goal_msg.timbre = 0
        
        # 发送停止命令
        cancel_send_future = self._action_client.send_goal_async(cancel_goal_msg)
        rclpy.spin_until_future_complete(self, cancel_send_future)
        cancel_goal_handle = cancel_send_future.result()
        
        if cancel_goal_handle is None:
            self.get_logger().error('发送停止命令失败')
        else:
            self.get_logger().info('停止命令已发送')
            
            # 等待获取结果
            try:
                if hasattr(cancel_goal_handle, 'get_result_async'):
                    get_result_future = cancel_goal_handle.get_result_async()
                    rclpy.spin_until_future_complete(self, get_result_future)
                    result = get_result_future.result().result
                    self.get_logger().info(f'停止命令结果: success={result.success}, message={result.message}')
            except Exception as e:
                self.get_logger().error(f'获取停止命令结果时出错: {e}')
                
        # 等待原始请求的结果
        self.get_logger().info('尝试获取原始请求的最终结果...')
        try:
            if hasattr(self.goal_handle, 'get_result_async'):
                result_future = self.goal_handle.get_result_async()
                self.get_logger().info('等待最终结果...')
                rclpy.spin_until_future_complete(self, result_future, timeout_sec=3.0)
                
                if result_future.done():
                    try:
                        result = result_future.result().result
                        self.get_logger().info(f'最终结果: success={result.success}, message={result.message}')
                    except Exception as e:
                        self.get_logger().error(f'获取结果数据时出错: {e}')
                else:
                    self.get_logger().warning('获取结果超时')
        except Exception as e:
            self.get_logger().error(f'获取结果过程中出错: {e}')
            
        self.get_logger().info('操作完成')
        return True
    
    def feedback_callback(self, feedback_msg):
        """处理来自服务端的反馈"""
        feedback = feedback_msg.feedback
        self.get_logger().info(f'收到反馈: {feedback.message}')

def main(args=None):
    rclpy.init(args=args)
    
    client_node = AudioClientNode()
    client_node.send_goal_with_cancel()
    
    # 清理
    client_node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()