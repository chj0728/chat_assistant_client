import rclpy
from rclpy.node import Node

from std_msgs.msg import String


class ParaConfig(Node):

    def __init__(self):
        super().__init__('para_config')
        self.subscription_update_wakeupword = self.create_subscription(
            WakeUpWordSetting,
            'modify_wakeup_word',
            self.update_wakeupword_callback,
            1
        )
    
    def update_wakeupword_callback(self, msg):
        """
        接收唤醒词的回调，更新欢迎词，重启生效
        """
        try:
            self.get_logger().info(f"接收到{len(msg.wake_up_word)}个字符串")
            keyword_file_path = "/home/ymrobot/ros2_ws_guidance/src/aud_conver/config/keywords.txt"
            lines = []
            for text in msg.wake_up_word:
                lines.append(f"{text};nCM:500")
            with open(keyword_file_path, 'w', encoding='UTF-8') as f:
                f.write('\n'.join(lines))
            self.get_logger().info(f"成功更新唤醒词文件内容")
        except Exception as e:
            self.get_logger().error(f"处理消息时出错：{str(e)}")

def main(args=None):
    rclpy.init(args=args)

    para_config = ParaConfig()

    rclpy.spin(para_config)
    para_config.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()