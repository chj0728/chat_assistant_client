import time
from pathlib import Path
from typing import Any

import rclpy
from app import ChatAssistant
from config import load_config
from logger import logger
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node

from chat_assistant.node_handlers import (
    ChatAssistantServiceHandlersMixin,
    ChatAssistantStateLoopMixin,
    ChatAssistantTopicHandlersMixin,
)
from chat_assistant.node_interfaces import NodeRosConfig, RosInterfaceRegistryMixin
from chat_assistant.node_tools import dynamic_middlewares


class ChatAssistantNode(
    ChatAssistantServiceHandlersMixin,
    ChatAssistantTopicHandlersMixin,
    ChatAssistantStateLoopMixin,
    RosInterfaceRegistryMixin,
    Node,
):
    def __init__(self):
        super().__init__("chat_assistant_node")

        self.asr_publisher: Any = None
        self.llm_publisher: Any = None
        self.response_publisher: Any = None
        self.tts_status_publisher: Any = None
        self.resolved_user_name_publisher: Any = None

        self.current_user_id = None
        self.last_user_id_msg_time = None
        self.user_id_stale_timeout_sec = 1.0

        self.current_user_face_status = False
        self.last_user_face_msg_time = time.time()
        self.last_user_face_true_time = time.time()
        self.user_face_stale_timeout_sec = 1.0

        self.ros_interface_config = NodeRosConfig()
        self._publisher_handles = []
        self._subscription_handles = []
        self.audio_cb_group = ReentrantCallbackGroup()
        self.interrupt_cb_group = ReentrantCallbackGroup()

        self.declare_parameter("config_path_value", "config/config.yaml")
        self.init_params()
        self._create_services()

    def init_params(self):

        self.config_path_value = (
            self.get_parameter("config_path_value").get_parameter_value().string_value
        )
        logger.info(f"从参数服务器获取的配置文件路径: {self.config_path_value}")
        self.config_path = (
            Path(self.config_path_value).expanduser().resolve()
            if self.config_path_value
            else None
        )
        logger.info(f"配置文件路径: {self.config_path}")

        self.load_config_and_initialize()

        self.chat_assistant = ChatAssistant(
            config_path=self.config_path,
            dynamic_middlewares=dynamic_middlewares,
        )

    def load_config_and_initialize(self):
        """
        加载配置文件参数
        初始化 ROS 相关参数和话题发布者
        """
        self._destroy_topic_interfaces()

        self.configs = load_config(self.config_path) if self.config_path else {}

        self.ros_interface_config = NodeRosConfig.from_mapping(
            self.configs.get("ros_cfg", {})
        )
        self.user_id_stale_timeout_sec = (
            self.ros_interface_config.user_id_stale_timeout_sec
        )
        self.user_face_stale_timeout_sec = (
            self.ros_interface_config.user_face_stale_timeout_sec
        )

        self._create_topic_interfaces()


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
