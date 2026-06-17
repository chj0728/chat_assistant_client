import asyncio
import os
import time
from enum import Enum
from queue import Empty, Full, Queue
from typing import TYPE_CHECKING, Any, Protocol

from chat_assistant_interfaces.msg import LLMResponse, Response
from config import clear_config_cache
from logger import logger
from rclpy.publisher import Publisher
from std_msgs.msg import Bool, String

if TYPE_CHECKING:
    from app import ChatAssistant


class ToolEvent(Enum):
    WAVE_HANDS = 0
    END_CONVERSATION = 1


MAX_QUEUE_SIZE = 10
tool_event_queue = Queue(maxsize=MAX_QUEUE_SIZE)


def push_queue(data_queue: Queue, value: Any) -> None:
    """将最新文本加入有限队列，保持队列容量受控。"""
    try:
        data_queue.put_nowait(value)
    except Full:
        try:
            data_queue.get_nowait()
        except Empty:
            pass
        data_queue.put_nowait(value)


class ChatAssistantNodeOwner(Protocol):
    """定义 ChatAssistantNode 所需的属性和方法协议，便于在多个 mixin 类中引用和实现

    Args:
      chat_assistant (ChatAssistant): 聊天助手核心对象，提供 ASR、LLM、TTS 等功能接口

      asr_publisher (Publisher): ASR 结果发布器
      llm_publisher (Publisher): LLM 结果发布器
      response_publisher (Publisher): 综合响应结果发布器
      tts_status_publisher (Publisher): TTS 状态发布器
      resolved_user_name_publisher (Publisher): 解析后的用户名发布器

      current_user_id (Any): 当前用户 ID，基于订阅数据更新
      last_user_id_msg_time (Any): 上次接收到用户 ID 消息的时间戳，用于判断数据是否过期
      user_id_stale_timeout_sec (float): 用户 ID 数据过期时间阈值，单位秒

      current_user_face_status (bool): 当前用户人脸状态，基于订阅数据更新
      last_user_face_msg_time (float): 上次接收到用户人脸信息消息的时间戳，用于判断数据是否过期
      last_user_face_true_time (float): 上次接收到用户人脸状态为 True 的时间戳，用于判断人脸状态是否过期
      user_face_stale_timeout_sec (float): 用户人脸状态数据过期时间阈值，单位秒
    """

    chat_assistant: "ChatAssistant"

    asr_publisher: Publisher
    llm_publisher: Publisher
    response_publisher: Publisher
    tts_status_publisher: Publisher
    resolved_user_name_publisher: Publisher

    current_user_id: Any
    last_user_id_msg_time: Any
    user_id_stale_timeout_sec: float

    current_user_face_status: bool
    last_user_face_msg_time: float
    last_user_face_true_time: float
    user_face_stale_timeout_sec: float

    _ros_interface_lock: Any

    def reload_config_and_initialize(self) -> None:
        """重新加载配置文件并进行必要的初始化"""
        ...

    def get_latest_user_id(self) -> Any:
        """获取最新用户 ID，考虑数据过期情况"""
        ...

    def get_latest_user_face_status(self) -> bool:
        """获取最新用户人脸状态，考虑数据过期情况"""
        ...

    def handle_tool_events(self) -> None:
        """处理工具事件队列中的事件"""
        ...

    def _publish_pending_asr_text(self) -> None:
        """发布待发布的 ASR 文本"""
        ...

    def _publish_pending_llm_text(self) -> None:
        """发布待发布的 LLM 文本"""
        ...

    def _publish_pending_response(self) -> None:
        """发布待发布的综合响应结果"""
        ...

    def _publish_tts_status(self) -> None:
        """发布 TTS 状态"""
        ...

    def _publish_pending_resolved_user_name(self) -> None:
        """发布待发布的解析后的用户名"""
        ...

    def _publish_message(self, publisher_name: str, msg: Any) -> bool:
        """通过指定的发布器发布消息，返回发布是否成功"""
        ...


class ChatAssistantServiceHandlersMixin:
    """定义 ChatAssistantNode 的服务处理函数，处理来自 ROS 服务的请求并调用聊天助手核心对象的方法完成相应的功能。"""

    def handle_chat_assistant_infer(self: ChatAssistantNodeOwner, request, response):
        """
        接收文本输入，调用 ASR、LLM、TTS 完成一次完整的交互服务
        """
        input_text = request.input_text

        request_user_id = request.user_id if hasattr(request, "user_id") else None
        request_user_id = request_user_id.strip() if request_user_id else None
        user_id = request_user_id if request_user_id else self.get_latest_user_id()

        voice_id = request.voice_id if hasattr(request, "voice_id") else None
        voice_id = voice_id.strip() if voice_id else None

        logger.info(
            f"收到聊天助手完整交互请求，输入文本: {input_text}，user_id: {user_id}，voice_id: {voice_id}"
        )
        asyncio.run(
            self.chat_assistant.Inference(
                input_text=input_text, user_id=user_id, voice_id=voice_id
            )
        )

        response.success = True
        response.message = "聊天助手完整交互已完成"
        logger.info("聊天助手完整交互已完成")
        return response

    def handle_interrupt_audio(self: ChatAssistantNodeOwner, request, response):
        """
        打断当前播放音频服务
        """
        logger.info("收到打断当前播放音频请求")
        self.chat_assistant.interrupt()
        response.success = True
        response.message = "已打断当前播放音频"
        return response

    def handle_play_audio(self: ChatAssistantNodeOwner, request, response):
        """
        接收audio_path，直接播放音频服务
        """
        audio_path = request.input

        if os.path.exists(audio_path) is False:
            response.success = False
            response.message = f"音频路径无效: {audio_path}"
            logger.error(response.message)
            return response

        logger.info(f"收到播放音频请求，音频路径: {audio_path}")
        play_result = self.chat_assistant.play_audio(audio_path)

        if play_result is False:
            response.success = False
            response.message = "音频未能成功播放"
            logger.error(response.message)
            return response

        response.success = True
        response.message = "音频播放成功"
        logger.info("音频播放成功")
        return response

    def handle_tts_generate_wav(self: ChatAssistantNodeOwner, request, response):
        """
        接收文本输入和音频保存路径，调用 TTS 完成文本转语音，保存音频文件服务
        """
        input_text = request.input_text
        output_path = request.input_filename
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        logger.info(
            f"收到 TTS 生成 WAV 文件请求\n输入文本:[{input_text}]\n保存路径: {output_path}"
        )
        tts_result = self.chat_assistant.generate_wav(input_text, output_path)

        if tts_result is False:
            response.success = False
            response.message = "TTS 未能成功生成 WAV 文件"
            logger.error(response.message)
            return response

        response.success = True
        response.message = f"WAV 文件已保存到 {output_path}"
        logger.info("请求 TTS 生成 WAV 文件成功")
        return response

    def handle_reload_config(self: ChatAssistantNodeOwner, request, response):
        """
        重新加载配置文件参数服务
        """
        logger.info("收到重新加载配置文件请求")

        clear_config_cache()
        self.reload_config_and_initialize()
        self.chat_assistant.reset()

        response.success = True
        response.message = "配置文件已重新加载"
        return response

    def handle_tts_infer(self: ChatAssistantNodeOwner, request, response):
        """
        接收文本输入，只调用 TTS 完成文本转语音，并播放音频服务
        """
        request_index = (
            request.request_index if hasattr(request, "request_index") else 0
        )
        request_text = request.request_text if hasattr(request, "request_text") else ""

        logger.info(f"TTS 收到请求，输入文本[{request_index}]: [{request_text}]")
        tts_result = self.chat_assistant.tts_stream_infer(
            llm_response_chunk=request_text, index=request_index
        )

        if tts_result is False:
            response.success = False
            response.message = "TTS 播放超时 或者 TTS 播放音频太短"
            return response

        response.success = True
        response.message = "TTS 请求成功"
        logger.info("TTS 请求成功")
        return response

    def handle_llm_infer(self: ChatAssistantNodeOwner, request, response):
        """
        接收文本输入（可选用户ID），只调用 LLM 完成文本生成，返回文本结果服务
        """
        input_text = request.input
        request_user_id = request.user_id if hasattr(request, "user_id") else None
        request_user_id = request_user_id.strip() if request_user_id else None
        user_id = request_user_id if request_user_id else self.get_latest_user_id()
        is_active_ask = (
            request.is_active_ask if hasattr(request, "is_active_ask") else False
        )

        logger.info(
            f"LLM 收到请求，输入文本: [{input_text}], user_id: [{user_id}], is_active_ask: [{is_active_ask}]"
        )
        # llm_result = asyncio.run(
        #     self.chat_assistant.async_llm_infer(input_text, vision_id=user_id)
        # )
        llm_result = self.chat_assistant.llm_infer(
            input_text, vision_id=user_id, is_active_ask=is_active_ask
        )

        if llm_result is None:
            response.success = False
            response.message = "LLM 未能生成有效文本"
            logger.error(response.message)
            return response

        response.success = True
        response.message = llm_result
        logger.info("LLM 请求成功")
        return response

    def handle_asr_infer(self: ChatAssistantNodeOwner, request, response):
        """
        接收audio_path，只调用 ASR 完成语音识别，返回文本结果服务
        """
        audio_path = request.input

        if os.path.exists(audio_path) is False:
            response.success = False
            response.message = f"音频路径无效: {audio_path}"
            logger.error(response.message)
            return response

        logger.info(f"ASR 收到请求，音频路径: {audio_path}")
        asr_result = self.chat_assistant.asr_infer(audio_path)

        if asr_result is None:
            response.success = False
            response.message = "ASR 未能识别出有效文本"
            logger.error(response.message)
            return response

        response.success = True
        response.message = asr_result
        logger.info("ASR 请求成功")
        return response

    def handle_activate_assistant(self: ChatAssistantNodeOwner, request, response):
        logger.info("激活LLM 和TTS服务")
        self.chat_assistant.activate_llm_agent()
        self.chat_assistant.activate_tts_client()
        response.success = True
        response.message = "LLM 和 TTS 已激活"
        return response

    def handle_idle_assistant(self: ChatAssistantNodeOwner, request, response):
        logger.info("将LLM 和TTS置于空闲状态")
        self.chat_assistant.deactivate_llm_agent()
        self.chat_assistant.deactivate_tts_client()
        response.success = True
        response.message = "LLM 和 TTS 已置于空闲状态"
        return response

    def handle_activate_asr(self: ChatAssistantNodeOwner, request, response):
        logger.info("激活ASR")
        self.chat_assistant.activate_asr_client()
        response.success = True
        response.message = "ASR已激活"
        return response

    def handle_idle_asr(self: ChatAssistantNodeOwner, request, response):
        logger.info("将ASR置于空闲状态")
        self.chat_assistant.deactivate_asr_client()
        response.success = True
        response.message = "ASR已置于空闲状态"
        return response

    def handle_activate_llm(self: ChatAssistantNodeOwner, request, response):
        logger.info("激活LLM")
        self.chat_assistant.activate_llm_agent()
        response.success = True
        response.message = "LLM已激活"
        return response

    def handle_idle_llm(self: ChatAssistantNodeOwner, request, response):
        logger.info("将LLM置于空闲状态")
        self.chat_assistant.deactivate_llm_agent()
        response.success = True
        response.message = "LLM已置于空闲状态"
        return response

    def handle_activate_tts(self: ChatAssistantNodeOwner, request, response):
        logger.info("激活TTS")
        self.chat_assistant.activate_tts_client()
        response.success = True
        response.message = "TTS已激活"
        return response

    def handle_idle_tts(self: ChatAssistantNodeOwner, request, response):
        logger.info("将TTS置于空闲状态")
        self.chat_assistant.deactivate_tts_client()
        response.success = True
        response.message = "TTS已置于空闲状态"
        return response

    def handle_delete_user_context(self: ChatAssistantNodeOwner, request, response):
        """
        删除指定用户 ID 的对话上下文服务
        """
        user_id_to_delete = request.user_id.strip()

        logger.info(f"收到删除用户上下文请求，用户 ID: {user_id_to_delete}")
        delete_result = self.chat_assistant.delete_user_context(user_id_to_delete)

        if delete_result is False:
            response.success = False
            response.message = (
                f"未能找到用户 ID {user_id_to_delete} 的上下文，或删除失败"
            )
            logger.error(response.message)
            return response

        response.success = True
        response.message = f"用户 ID {user_id_to_delete} 的上下文已成功删除"
        logger.info(response.message)
        return response


class ChatAssistantTopicHandlersMixin:
    """定义 ChatAssistantNode 的话题处理函数，处理来自 ROS 订阅的话题消息并调用聊天助手核心对象的方法完成相应的功能。"""

    def handle_user_id(self: ChatAssistantNodeOwner, msg):
        """
        处理订阅到的用户 vision_id 消息，更新当前用户 ID，并记录消息接收时间以便后续判断数据是否过期
        """
        self.last_user_id_msg_time = time.time()
        self.current_user_id = msg.data.strip() if msg.data else None
        logger.debug(f"收到用户vision_id消息: {self.current_user_id}")
        self.chat_assistant.set_current_user_id(self.current_user_id)

    def handle_user_face(self: ChatAssistantNodeOwner, msg):
        """
        处理订阅到的用户人脸信息消息，更新当前用户人脸状态，并记录消息接收时间以便后续判断数据是否过期
        """
        self.last_user_face_msg_time = time.time()
        logger.debug(f"收到用户人脸信息消息: {msg.data}")

        if msg.data:
            self.last_user_face_true_time = time.time()
            self.chat_assistant.set_current_user_face_status(True)
            self.current_user_face_status = True
            return

        if (
            time.time() - self.last_user_face_true_time
        ) > self.user_face_stale_timeout_sec:
            self.chat_assistant.set_current_user_face_status(False)
            self.current_user_face_status = False


class ChatAssistantStateHandlersMixin:
    """定义 ChatAssistantNode 的状态处理函数，定期检查和处理工具事件、用户 ID 和人脸状态的更新，
    并发布 ASR、LLM、综合响应、TTS 状态和解析后的用户名等信息。"""

    def process_runtime_once(self: ChatAssistantNodeOwner) -> None:

        self.handle_tool_events()
        self.get_latest_user_id()
        self.get_latest_user_face_status()

        self._publish_pending_asr_text()
        self._publish_pending_llm_text()
        self._publish_pending_response()
        self._publish_tts_status()
        self._publish_pending_resolved_user_name()

    def handle_tool_events(self: ChatAssistantNodeOwner):
        """
        处理工具事件队列中的事件
        """
        try:
            tool_event = tool_event_queue.get_nowait()

            if tool_event == ToolEvent.WAVE_HANDS.value:
                logger.info("Main loop handling tool event: WAVE_HANDS")

            elif tool_event == ToolEvent.END_CONVERSATION.value:
                logger.info("Main loop handling tool event: END_CONVERSATION")

        except Empty:
            pass

    def get_latest_user_id(self: ChatAssistantNodeOwner):
        """
        获取最新用户ID；当订阅数据超时未更新时，返回 None
        """
        if self.last_user_id_msg_time is None:
            return None

        if (time.time() - self.last_user_id_msg_time) > self.user_id_stale_timeout_sec:
            if self.current_user_id is not None:
                logger.debug("用户ID订阅数据超时，回退为 None")
            self.current_user_id = None
            self.last_user_id_msg_time = None
            self.chat_assistant.set_current_user_id(None)
            return None

        return self.current_user_id

    def get_latest_user_face_status(self: ChatAssistantNodeOwner):
        """
        获取最新用户人脸状态；当订阅数据超时未更新时，返回 False（表示未检测到人脸）
        """
        if (
            (time.time() - self.last_user_face_msg_time)
            > self.user_face_stale_timeout_sec
            and self.current_user_face_status is True
        ):
            logger.debug("用户人脸信息订阅数据超时，回退为 False")

            self.chat_assistant.set_current_user_face_status(False)
            self.current_user_face_status = False

            return self.current_user_face_status

        return self.current_user_face_status

    def _publish_pending_asr_text(self: ChatAssistantNodeOwner) -> None:
        if self.chat_assistant.asr_text_queue.empty() is False:
            asr_text = self.chat_assistant.asr_text_queue.get(timeout=0.05)
            msg = String()
            msg.data = asr_text
            self._publish_message("asr_publisher", msg)

    def _publish_pending_llm_text(self: ChatAssistantNodeOwner) -> None:
        if self.chat_assistant.llm_text_queue.empty() is False:
            llm_response = self.chat_assistant.llm_text_queue.get(timeout=0.05)
            msg = LLMResponse()
            msg.response_index = llm_response[0].get("index", 0)
            msg.response_text = llm_response[0].get("text", "")
            self._publish_message("llm_publisher", msg)

    def _publish_pending_response(self: ChatAssistantNodeOwner) -> None:
        if self.chat_assistant.response_queue.empty() is False:
            response_data = self.chat_assistant.response_queue.get(timeout=0.05)
            response_msg = Response()
            response_msg.asr_text = response_data.get("asr_text", "")
            response_msg.llm_text = response_data.get("llm_text", "")
            if not self._publish_message("response_publisher", response_msg):
                return
            logger.info(
                "发布 综合响应结果 到话题: ASR Text: [%s], LLM Text: [%s]",
                response_msg.asr_text,
                response_msg.llm_text,
            )

    def _publish_tts_status(self: ChatAssistantNodeOwner) -> None:
        tts_msg = Bool()
        tts_msg.data = self.chat_assistant.check_tts_active()
        self._publish_message("tts_status_publisher", tts_msg)

    def _publish_pending_resolved_user_name(self: ChatAssistantNodeOwner) -> None:
        if self.chat_assistant.resolved_user_names_queue.empty() is False:
            resolved_user_name = self.chat_assistant.resolved_user_names_queue.get(
                timeout=0.05
            )
            msg = String()
            msg.data = resolved_user_name or ""
            if not self._publish_message("resolved_user_name_publisher", msg):
                return
            logger.info(f"发布解析后的用户名: {resolved_user_name}")

    def _publish_message(
        self: ChatAssistantNodeOwner, publisher_name: str, msg: Any
    ) -> bool:
        """通过指定的发布器发布消息，返回发布是否成功"""
        with self._ros_interface_lock:
            publisher = getattr(self, publisher_name, None)
            if publisher is None:
                return False
            publisher.publish(msg)
            return True


class ChatAssistantHandlers(
    ChatAssistantServiceHandlersMixin,
    ChatAssistantTopicHandlersMixin,
    ChatAssistantStateHandlersMixin,
):
    """将服务处理函数、话题处理函数和状态处理函数组合到一个类中，供 ChatAssistantNode 继承使用。"""

    ...
