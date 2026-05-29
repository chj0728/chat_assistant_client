import os
import time
from pathlib import Path
from typing import Any

import rclpy
from app import ChatAssistant
from config import load_config
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
)
from langchain.agents.middleware.types import ToolCallRequest
from langchain.tools import tool
from logger import logger
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node

from chat_assistant.node_handlers import (
    ChatAssistantLoopMixin,
    ChatAssistantServiceHandlersMixin,
    ChatAssistantStateHandlersMixin,
    ToolEvent,
    push_queue,
    tool_event_queue,
)
from chat_assistant.node_interfaces import NodeRosConfig, RosInterfaceRegistryMixin


@tool(description="当有人问候的时候，挥手回应")
def response_wave_hands_tool():
    # """挥手回应的工具函数"""
    logger.info("调用工具函数->机器人挥了挥手，表示问候！")

    global tool_event_queue
    push_queue(tool_event_queue, ToolEvent.WAVE_HANDS.value)
    return


@tool(
    description="只有当用户回答退出、结束等相关内容时，调用结束对话工具，礼貌地结束对话"
)
def end_conversation_tool():
    # """结束对话的工具函数"""
    logger.info("调用工具函数->机器人礼貌地结束了对话。")
    global tool_event_queue
    push_queue(tool_event_queue, ToolEvent.END_CONVERSATION.value)
    return


@tool(description="调整默认扬声器音量")
def adjust_speaker_volume_tool(volume: int):
    # """调整系统默认扬声器音量的工具函数"""
    logger.info(f"调用工具函数->调整系统默认扬声器音量为 {volume}。")

    if volume > 0 and volume <= 10:
        volume = int(volume * 10)  # 将0-10的音量转换为0-100的百分比
    elif volume < 0:
        volume = 0
    elif volume > 100:
        volume = 100
    # 在这里添加实际的音量调整逻辑
    # pactl set-sink-volume @DEFAULT_SINK@ {volume}%
    os.system(f"pactl set-sink-volume @DEFAULT_SINK@ {volume}%")

    return


class DynamicToolMiddleware(AgentMiddleware):
    """
    动态工具中间件示例，用于在运行时注册和调用工具
    """

    def wrap_model_call(self, request: ModelRequest, handler):
        # 添加动态工具请求处理
        updated = request.override(
            tools=[
                *request.tools,
                response_wave_hands_tool,
                end_conversation_tool,
                adjust_speaker_volume_tool,
            ]
        )
        # logger.info("动态工具中间件: 添加挥手回应和结束对话工具")
        return handler(updated)

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        # 处理特定工具调用
        if request.tool_call["name"] == "response_wave_hands_tool":
            logger.info("动态工具中间件: 检测到挥手回应工具调用")
            return handler(request.override(tool=response_wave_hands_tool))

        if request.tool_call["name"] == "end_conversation_tool":
            logger.info("动态工具中间件: 检测到结束对话工具调用")
            return handler(request.override(tool=end_conversation_tool))

        if request.tool_call["name"] == "adjust_speaker_volume_tool":
            logger.info("动态工具中间件: 检测到调整扬声器音量工具调用")
            return handler(request.override(tool=adjust_speaker_volume_tool))

        return handler(request)


# call_flag = False

dynamic_middlewares = [
    # DynamicToolMiddleware(),
]


class ChatAssistantNode(
    ChatAssistantServiceHandlersMixin,
    ChatAssistantStateHandlersMixin,
    ChatAssistantLoopMixin,
    RosInterfaceRegistryMixin,
    Node,
):
    def __init__(self):
        super().__init__("chat_assistant_node")

        self.current_user_id = None
        self.last_user_id_msg_time = None
        self.user_id_stale_timeout_sec = 1.0

        self.current_user_face_status = False
        self.last_user_face_msg_time = time.time()
        self.last_user_face_true_time = time.time()
        self.user_face_stale_timeout_sec = 1.0

        self.asr_publisher: Any = None
        self.llm_publisher: Any = None
        self.response_publisher: Any = None
        self.tts_status_publisher: Any = None
        self.resolved_user_name_publisher: Any = None

        self.declare_parameter("config_path_value", "config/config.yaml")

        self.ros_interface_config = NodeRosConfig()
        self._publisher_handles = []
        self._subscription_handles = []

        self.init_params()

        self.audio_cb_group = ReentrantCallbackGroup()
        self.interrupt_cb_group = ReentrantCallbackGroup()

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

    # except KeyboardInterrupt:
    #     if rclpy.ok():  # 检查上下文是否仍然有效
    #         logger.info("KeyboardInterrupt detected, shutting down...")
    #     else:
    #         logger.info("rclpy context is no longer valid, shutting down...")

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
