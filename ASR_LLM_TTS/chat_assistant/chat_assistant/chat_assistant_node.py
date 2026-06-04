import rclpy
from app import ChatAssistant
from config import get_default_config_path
from logger import logger
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node

from chat_assistant.node_handlers import ChatAssistantHandlers
from chat_assistant.node_interfaces import RosInterfaceRegistry
from chat_assistant.node_tools import dynamic_middlewares


class ChatAssistantNode(
    ChatAssistantHandlers,
    RosInterfaceRegistry,
    Node,
):
    def __init__(self):

        Node.__init__(self, "chat_assistant_node")

        RosInterfaceRegistry.__init__(self)

        self.init_chat_assistant()

    def init_chat_assistant(self):
        """初始化聊天助手核心对象, 并传入动态工具中间件。"""

        self.config_path = get_default_config_path()
        logger.info(f"默认配置文件路径: {self.config_path}")

        self.chat_assistant = ChatAssistant(
            config_path=self.config_path,
            dynamic_middlewares=dynamic_middlewares,
        )


def main(args=None):
    rclpy.init(args=args)
    chat_assistant_node = ChatAssistantNode()
    chat_assistant_node.chat_assistant.start_recording()

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(chat_assistant_node)

    try:
        while rclpy.ok():
            chat_assistant_node.process_runtime_once()
            executor.spin_once(timeout_sec=0.05)

    except (KeyboardInterrupt, ExternalShutdownException):
        chat_assistant_node.chat_assistant.stop_recording()
        logger.info("Shutdown signal received, exiting main loop...")

    finally:
        if rclpy.ok():
            chat_assistant_node.chat_assistant.stop_recording()
            chat_assistant_node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
