import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol, cast

from chat_assistant_interfaces.msg import LLMResponse, Response
from chat_assistant_interfaces.srv import GenerateWav, GetString, RequestLLM, RequestTTS
from config import load_config
from logger import logger
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger


@dataclass(frozen=True)
class NodeRosConfig:
    """ROS接口配置类，包含所有ROS接口相关的配置项。

    Attributes:
        asr_publish_topic: ASR 结果发布主题名称
        llm_publish_topic: LLM 结果发布主题名称
        response_publish_topic: 综合响应结果发布主题名称
        tts_active_topic: TTS 状态发布主题名称
        resolved_user_name_topic: 解析后的用户名发布主题名称
        user_id_subscribe_topic: 用户ID订阅主题名称
        user_id_stale_timeout_sec: 用户ID过期时间（秒）
        user_face_subscribe_topic: 用户面部状态订阅主题名称
        user_face_stale_timeout_sec: 用户面部状态过期时间（秒）

    """

    asr_publish_topic: str = "asr_result"
    llm_publish_topic: str = "llm_result"
    response_publish_topic: str = "assistant_response"
    tts_active_topic: str = "sound_detected_default"
    resolved_user_name_topic: str = "resolved_user_name"

    user_id_subscribe_topic: str = "user_id_topic"
    user_id_stale_timeout_sec: float = 1.0
    user_face_subscribe_topic: str = "is_faced"
    user_face_stale_timeout_sec: float = 1.0

    @classmethod
    def from_mapping(cls, ros_cfg: Mapping[str, Any]) -> "NodeRosConfig":
        return cls(
            asr_publish_topic=ros_cfg.get("asr_publish_topic", cls.asr_publish_topic),
            llm_publish_topic=ros_cfg.get("llm_publish_topic", cls.llm_publish_topic),
            response_publish_topic=ros_cfg.get(
                "response_publish_topic", cls.response_publish_topic
            ),
            tts_active_topic=ros_cfg.get("tts_active_topic", cls.tts_active_topic),
            resolved_user_name_topic=ros_cfg.get(
                "resolved_user_name_topic", cls.resolved_user_name_topic
            ),
            user_id_subscribe_topic=ros_cfg.get(
                "user_id_subscribe_topic", cls.user_id_subscribe_topic
            ),
            user_id_stale_timeout_sec=float(
                ros_cfg.get("user_id_stale_timeout_sec", cls.user_id_stale_timeout_sec)
            ),
            user_face_subscribe_topic=ros_cfg.get(
                "user_face_subscribe_topic", cls.user_face_subscribe_topic
            ),
            user_face_stale_timeout_sec=float(
                ros_cfg.get(
                    "user_face_stale_timeout_sec", cls.user_face_stale_timeout_sec
                )
            ),
        )


@dataclass(frozen=True)
class ServiceSpec:
    """ROS 服务规范，包含服务类型、服务名称、处理函数名称以及可选的回调组属性。

    Attributes:
        service_type: ROS 服务类型，例如 Trigger 等。
        service_name: ROS 服务名称，节点将使用此名称创建服务。
        handler_name: 处理函数名称，节点将调用此函数来处理服务请求。
        callback_group_attr: Optional[str] = None - 如果指定，表示处理函数所属的回调组属性名称，节点将使用该回调组来创建服务。
    """

    service_type: Any
    service_name: str
    handler_name: str
    callback_group_attr: Optional[str] = None


@dataclass(frozen=True)
class PublisherSpec:
    """ROS 发布者规范，包含发布者属性名称、消息类型、配置属性名称和 QoS 深度。

    Attributes:
        attribute_name: 发布者属性名称，节点将使用此名称创建发布者。
        message_type: 消息类型，例如 String 等。
        config_attr: 配置属性名称，节点将使用此属性设置话题名称。
        qos_depth: QoS 深度，用于设置发布者的队列长度。
    """

    attribute_name: str
    message_type: Any
    config_attr: str
    qos_depth: int


@dataclass(frozen=True)
class SubscriptionSpec:
    """ROS 订阅者规范，包含订阅者属性名称、消息类型、配置属性名称和 QoS 深度。

    Attributes:
        message_type: 消息类型，例如 String 等。
        config_attr: 配置属性名称，节点将使用此属性设置订阅的话题名称。
        handler_name: 处理函数名称，节点将调用此函数来处理接收到的消息。
        qos_depth: QoS 深度，用于设置订阅者的队列长度。
    """

    message_type: Any
    config_attr: str
    handler_name: str
    qos_depth: int


class RosInterfaceOwner(Protocol):
    """Protocol for classes that own ROS interfaces (publishers, subscriptions, services).

    Attributes:
        ros_interface_config: ROS 接口配置对象，包含话题名称和服务名称等信息。
        _publisher_handles: 发布者句柄列表，用于管理创建的发布者。
        _subscription_handles: 订阅者句柄列表，用于管理创建的订阅者。
        audio_cb_group: 音频回调组，用于处理音频相关的回调。
        interrupt_cb_group: 音频中断回调组，用于处理音频中断相关的回调。
    """

    ros_interface_config: NodeRosConfig
    _publisher_handles: list[Any]
    _subscription_handles: list[Any]
    audio_cb_group: Any
    interrupt_cb_group: Any


SERVICE_SPECS = (
    ServiceSpec(Trigger, "reload_config", "handle_reload_config"),
    ServiceSpec(Trigger, "activate_assistant", "handle_activate_assistant"),
    ServiceSpec(Trigger, "idle_assistant", "handle_idle_assistant"),
    ServiceSpec(Trigger, "activate_asr", "handle_activate_asr"),
    ServiceSpec(Trigger, "idle_asr", "handle_idle_asr"),
    ServiceSpec(Trigger, "activate_llm", "handle_activate_llm"),
    ServiceSpec(Trigger, "idle_llm", "handle_idle_llm"),
    ServiceSpec(Trigger, "activate_tts", "handle_activate_tts"),
    ServiceSpec(Trigger, "idle_tts", "handle_idle_tts"),
    ServiceSpec(GetString, "asr_infer", "handle_asr_infer"),
    ServiceSpec(RequestLLM, "llm_infer", "handle_llm_infer"),
    ServiceSpec(RequestTTS, "tts_infer", "handle_tts_infer"),
    ServiceSpec(GetString, "chat_assistant_infer", "handle_chat_assistant_infer"),
    ServiceSpec(
        GetString,
        "play_audio_file",
        "handle_play_audio",
        callback_group_attr="audio_cb_group",
    ),
    ServiceSpec(
        Trigger,
        "interrupt_audio",
        "handle_interrupt_audio",
        callback_group_attr="interrupt_cb_group",
    ),
    ServiceSpec(GenerateWav, "tts_generate_wav", "handle_tts_generate_wav"),
    ServiceSpec(GetString, "delete_user_context", "handle_delete_user_context"),
)


PUBLISHER_SPECS = (
    PublisherSpec("asr_publisher", String, "asr_publish_topic", 10),
    PublisherSpec("llm_publisher", LLMResponse, "llm_publish_topic", 10),
    PublisherSpec("response_publisher", Response, "response_publish_topic", 10),
    PublisherSpec("tts_status_publisher", Bool, "tts_active_topic", 1),
    PublisherSpec(
        "resolved_user_name_publisher",
        String,
        "resolved_user_name_topic",
        10,
    ),
)


SUBSCRIPTION_SPECS = (
    SubscriptionSpec(String, "user_id_subscribe_topic", "handle_user_id", 1),
    SubscriptionSpec(Bool, "user_face_subscribe_topic", "handle_user_face", 1),
)


class RosInterfaceRegistryMixin:
    """ROS接口注册类，提供创建和销毁ROS服务、发布者和订阅者的方法。"""

    def _create_services(self: RosInterfaceOwner) -> None:
        node = cast(Node, self)
        for spec in SERVICE_SPECS:
            kwargs = {}
            if spec.callback_group_attr is not None:
                kwargs["callback_group"] = getattr(self, spec.callback_group_attr)

            node.create_service(
                spec.service_type,
                spec.service_name,
                getattr(self, spec.handler_name),
                **kwargs,
            )

    def _create_topic_interfaces(self: RosInterfaceOwner) -> None:
        node = cast(Node, self)
        for spec in PUBLISHER_SPECS:
            publisher = node.create_publisher(
                spec.message_type,
                getattr(self.ros_interface_config, spec.config_attr),
                spec.qos_depth,
            )
            setattr(self, spec.attribute_name, publisher)
            self._publisher_handles.append(publisher)

        for spec in SUBSCRIPTION_SPECS:
            subscription = node.create_subscription(
                spec.message_type,
                getattr(self.ros_interface_config, spec.config_attr),
                getattr(self, spec.handler_name),
                spec.qos_depth,
            )
            self._subscription_handles.append(subscription)

    def _destroy_topic_interfaces(self: RosInterfaceOwner) -> None:
        node = cast(Node, self)
        for subscription in self._subscription_handles:
            node.destroy_subscription(subscription)
        self._subscription_handles.clear()

        for publisher in self._publisher_handles:
            node.destroy_publisher(publisher)
        self._publisher_handles.clear()


class RosInterfaceRegistry(RosInterfaceRegistryMixin):
    """ROS接口注册类，继承自RosInterfaceRegistryMixin，提供完整的ROS接口注册功能。"""

    def __init__(self):

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

        self.init_parameters()
        self.init_ros_interfaces()

    def init_ros_interfaces(self):
        """初始化ROS接口，创建服务、发布者和订阅者。"""
        self._create_services()
        self._create_topic_interfaces()

    def init_parameters(self):
        """初始化参数，加载配置文件并设置相关参数。"""

        self.ros_interface_config = NodeRosConfig.from_mapping(
            load_config().get("ros_cfg", {})
        )

        self.user_id_stale_timeout_sec = (
            self.ros_interface_config.user_id_stale_timeout_sec
        )
        logger.info(f"用户ID过期时间阈值: {self.user_id_stale_timeout_sec} 秒")

        self.user_face_stale_timeout_sec = (
            self.ros_interface_config.user_face_stale_timeout_sec
        )
        logger.info(f"用户人脸信息过期时间阈值: {self.user_face_stale_timeout_sec} 秒")

    def reset_ros_interfaces(self):
        """重置ROS接口，销毁现有接口并根据最新配置重新创建。"""
        self._destroy_topic_interfaces()
        self.init_parameters()
        self._create_topic_interfaces()

    def reload_config_and_initialize(self):
        """
        重新加载配置文件参数
        初始化 ROS 相关参数和话题发布者
        """

        self.reset_ros_interfaces()
