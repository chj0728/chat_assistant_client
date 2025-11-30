import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node
import pygame
import os

from ymrobot_msgs.action import PlayMp3

class PlayMp3ActionServer(Node):

    def __init__(self):
        super().__init__('play_mp3_action_server')
        print("进入播放语音")
        self._action_server = ActionServer(
            self,
            PlayMp3,
            'play_mp3_service', # 服务名称
            self.execute_callback)

    def execute_callback(self, goal_handle):
        self.get_logger().info('Executing goal...')

        file_path = goal_handle.request.mp3_file_path

        if not os.path.exists(file_path):
            goal_handle.abort()
            result = PlayMp3.Result()
            result.success = False
            self.get_logger().error(f"File not found: {file_path}")
            return result

        pygame.mixer.init()
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            rclpy.spin_once(self, timeout_sec=0.1)
            feedback_msg = PlayMp3.Feedback()
            feedback_msg.status = "播放mp3中..."
            goal_handle.publish_feedback(feedback_msg)

        goal_handle.succeed()

        result = PlayMp3.Result()
        result.success = True
        return result

def main(args=None):
    rclpy.init(args=args)

    play_mp3_action_server = PlayMp3ActionServer()

    rclpy.spin(play_mp3_action_server)

    play_mp3_action_server.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()