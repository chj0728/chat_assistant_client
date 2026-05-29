from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol, cast

from chat_assistant_interfaces.msg import LLMResponse, Response
from chat_assistant_interfaces.srv import GenerateWav, GetString, RequestTTS
from rclpy.node import Node
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger


@dataclass(frozen=True)
class NodeRosConfig:
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
    service_type: Any
    service_name: str
    handler_name: str
    callback_group_attr: Optional[str] = None


@dataclass(frozen=True)
class PublisherSpec:
    attribute_name: str
    message_type: Any
    config_attr: str
    qos_depth: int


@dataclass(frozen=True)
class SubscriptionSpec:
    message_type: Any
    config_attr: str
    handler_name: str
    qos_depth: int


class RosInterfaceOwner(Protocol):
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
    ServiceSpec(GetString, "llm_infer", "handle_llm_infer"),
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
