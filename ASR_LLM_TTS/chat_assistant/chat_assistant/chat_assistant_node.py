import os
import time
from enum import Enum
from pathlib import Path
from queue import Empty, Full, Queue

import rclpy
from app import ChatAssistant
from chat_assistant_interfaces.msg import Response
from chat_assistant_interfaces.srv import GenerateWav, GetString
from config import load_config
from langchain.agents import AgentState
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    after_agent,
    after_model,
    before_agent,
)
from langchain.agents.middleware.types import ToolCallRequest
from langchain.tools import tool
from langgraph.runtime import Runtime
from logger import logger
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger


class ToolEvent(Enum):
    WAVE_HANDS = 0  # 代表挥手回应事件
    END_CONVERSATION = 1  # 代表结束对话事件


MAX_QUEUE_SIZE = 10
tool_event_queue = Queue(maxsize=MAX_QUEUE_SIZE)


def push_queue(data_queue: Queue, value) -> None:
    """将最新文本加入有限队列，保持队列容量受控。"""
    try:
        data_queue.put_nowait(value)
    except Full:
        try:
            data_queue.get_nowait()
        except Empty:
            pass
        data_queue.put_nowait(value)


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
            tools=[*request.tools, response_wave_hands_tool, end_conversation_tool, adjust_speaker_volume_tool]
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


@before_agent
def test_before_agent(state: AgentState, runtime: Runtime) -> None:
    # global call_flag
    # call_flag = True
    logger.debug("=======> Before Agent Dynamic Middleware")
    messages = state["messages"]
    logger.debug(f"Current messages: {[m for m in messages]}")
    # for m in messages:
    #     m.pretty_print()


# @2026-04-10 by caohaojie
# this middleware is moved to llmagent.py, and is added to the static_middleware_list
# @before_model
# def trim_messages_before_model(
#     state: AgentState, runtime: Runtime
# ) -> dict[str, Any] | None:
#     """Keep only the last few messages to fit context window."""
#     pass


# @after_model
# def delete_old_messages_after_model(state: AgentState, runtime: Runtime) -> dict | None:
#     # logger.info("=======> After Model Middleware")
#     """Remove old messages to keep conversation manageable."""
#     messages = state["messages"]
#     logger.debug(
#         f"After LLM Middleware - Current messages: {[m.content for m in messages]}"
#     )

#     # messages[0].pretty_print()

#     if len(messages) > MAX_MESSAGES:
#         logger.debug(
#             f"历史对话消息量超过最大限制 ({len(messages)}) 超过最大限制 ({MAX_MESSAGES})，删除最旧的三分之一消息"
#         )

#         return {
#             "messages": [
#                 RemoveMessage(id=m.id if m.id else "")
#                 for m in messages[: len(messages) // 3]  # 删除最旧的三分之一消息
#             ]
#         }
#     return None


@after_model
def test_after_model(state: AgentState, runtime: Runtime) -> None:
    logger.debug("=======> After Model Middleware")
    messages = state["messages"]
    logger.debug(f"Current messages: {[m for m in messages]}")
    # for m in messages:
    #     m.pretty_print()


@after_agent
def test_after_agent(state: AgentState, runtime: Runtime) -> None:
    logger.debug("=======> After Agent Dynamic Middleware")
    messages = state["messages"]
    logger.debug(f"Current messages: {[m for m in messages]}")
    # for m in messages:
    #     m.pretty_print()


middlewares = [
    # DynamicToolMiddleware(),
    test_before_agent,
    # test_before_model,
    # trim_messages_before_model,
    # delete_old_messages_after_model,
    test_after_model,
    test_after_agent,
]


class ChatAssistantNode(Node):
    def __init__(self):
        super().__init__("chat_assistant_node")

        self.current_user_id = None
        self.last_user_id_msg_time = None
        self.user_id_stale_timeout_sec = 1.0

        self.declare_parameter("config_path", "config/config.yaml")

        self.init_params()

        self.audio_cb_group = ReentrantCallbackGroup()
        self.interrupt_cb_group = ReentrantCallbackGroup()

        # 创建服务
        ## 重新加载配置文件参数
        self.create_service(Trigger, "reload_config", self.handle_reload_config)

        ## 激活聊天助手服务
        self.create_service(
            Trigger, "activate_assistant", self.handle_activate_assistant
        )
        ## 将聊天助手置于空闲状态服务
        self.create_service(Trigger, "idle_assistant", self.handle_idle_assistant)

        ## 激活ASR服务
        self.create_service(Trigger, "activate_asr", self.handle_activate_asr)
        ## 将ASR置于空闲状态服务
        self.create_service(Trigger, "idle_asr", self.handle_idle_asr)

        ## 激活LLM
        self.create_service(Trigger, "activate_llm", self.handle_activate_llm)
        ## 置于空闲状态，停用LLM
        self.create_service(Trigger, "idle_llm", self.handle_idle_llm)

        ## 激活TTS
        self.create_service(Trigger, "activate_tts", self.handle_activate_tts)
        ## 置于空闲状态，停用TTS
        self.create_service(Trigger, "idle_tts", self.handle_idle_tts)

        ## 接收audio_path，只调用 ASR 完成语音识别，返回文本结果服务
        self.create_service(GetString, "asr_infer", self.handle_asr_infer)

        ## 接收文本输入，只调用 LLM 完成文本生成，返回文本结果服务
        self.create_service(GetString, "llm_infer", self.handle_llm_infer)

        ## 接收文本输入，只调用 TTS 完成文本转语音，并在线播放音频服务
        self.create_service(GetString, "tts_infer", self.handle_tts_infer)

        ## 接收文本输入，调用 ASR、LLM、TTS 完成一次完整的交互服务
        self.create_service(
            GetString, "chat_assistant_infer", self.handle_chat_assistant_infer
        )

        ## 接收audio_path，直接播放音频服务
        self.create_service(
            GetString,
            "play_audio_file",
            self.handle_play_audio,
            callback_group=self.audio_cb_group,
        )

        ## 打断当前播放音频服务
        self.create_service(
            Trigger,
            "interrupt_audio",
            self.handle_interrupt_audio,
            callback_group=self.interrupt_cb_group,
        )

        ## 接收文本输入和音频保存路径，调用 TTS 完成文本转语音，保存音频文件服务
        self.create_service(
            GenerateWav, "tts_generate_wav", self.handle_tts_generate_wav
        )

    def init_params(self):

        self.config_path = (
            self.get_parameter("config_path").get_parameter_value().string_value
        )
        self.config_yaml = Path(self.config_path).expanduser().resolve()
        logger.info(f"配置文件路径: {self.config_yaml}")

        self.load_config_and_initialize()

        self.chat_assistant = ChatAssistant(
            config_path=self.config_path,
            # dynamic_tool_middlewares=DynamicToolMiddleware(),
            dynamic_middleware_list=middlewares,
        )

    def load_config_and_initialize(self):
        """
        加载配置文件参数
        初始化 ROS 相关参数和话题发布者
        """
        # ----------- 读取配置文件 -----------
        # try:
        #     with open(self.config_yaml, "r", encoding="utf-8") as f:
        #         self.configs = yaml.safe_load(f)
        #         # logger.info(f"配置文件内容:\n{self.configs}")
        # except Exception as e:
        #     logger.error(f"读取配置文件失败: {e}")

        self.configs = load_config()

        ros_cfg = self.configs.get("ros_cfg", {})

        self.asr_publish_topic = ros_cfg.get("asr_publish_topic", "asr_result")
        self.llm_publish_topic = ros_cfg.get("llm_publish_topic", "llm_result")
        self.response_publish_topic = ros_cfg.get(
            "response_publish_topic", "assistant_response"
        )

        self.tts_active_topic = ros_cfg.get(
            "tts_active_topic", "sound_detected_default"
        )

        self.user_id_subscribe_topic = ros_cfg.get(
            "user_id_subscribe_topic", "user_id_topic"
        )
        self.user_id_stale_timeout_sec = float(
            ros_cfg.get("user_id_stale_timeout_sec", 1.0)
        )

        # 创建话题发布者
        ## 发布asr识别结果话题
        self.asr_publisher = self.create_publisher(String, self.asr_publish_topic, 10)

        ## 发布 llm 生成结果话题
        self.llm_publisher = self.create_publisher(String, self.llm_publish_topic, 10)

        ## 发布综合响应结果话题
        self.response_publisher = self.create_publisher(
            Response, self.response_publish_topic, 10
        )

        ## 发布 TTS 播放状态话题
        self.tts_status_publisher = self.create_publisher(
            Bool, self.tts_active_topic, 1
        )

        ## 订阅用户ID话题
        self.create_subscription(
            String, self.user_id_subscribe_topic, self.handle_user_id, 1
        )

    def get_latest_user_id(self):
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

    def handle_chat_assistant_infer(self, request, response):
        """
        接收文本输入，调用 ASR、LLM、TTS 完成一次完整的交互服务
        """
        input_text = request.input
        request_user_id = request.user_id if hasattr(request, "user_id") else None
        request_user_id = request_user_id.strip() if request_user_id else None
        user_id = request_user_id if request_user_id else self.get_latest_user_id()

        logger.info(
            f"收到聊天助手完整交互请求，输入文本: {input_text}，user_id: {user_id}"
        )
        self.chat_assistant.Inference(input_text=input_text, user_id=user_id)

        response.success = True
        response.message = "聊天助手完整交互已完成"
        logger.info("聊天助手完整交互已完成")
        return response

    def handle_interrupt_audio(self, request, response):
        """
        打断当前播放音频服务
        """
        logger.info("收到打断当前播放音频请求")
        self.chat_assistant.interrupt()
        response.success = True
        response.message = "已打断当前播放音频"
        return response

    def handle_play_audio(self, request, response):
        """
        接收audio_path，直接播放音频服务
        """
        audio_path = request.input

        # 检查 audio_path 是否有效存在
        if os.path.exists(audio_path) is False:
            response.success = False
            response.message = f"音频路径无效: {audio_path}"
            logger.error(response.message)
            return response

        logger.info(f"收到播放音频请求，音频路径: {audio_path}")
        play_result = self.chat_assistant.play_audio(audio_path)

        # 检查播放结果是否有效
        if play_result is False:
            response.success = False
            response.message = "音频未能成功播放"
            logger.error(response.message)
            return response

        response.success = True
        response.message = "音频播放成功"
        logger.info("音频播放成功")
        return response

    def handle_tts_generate_wav(self, request, response):
        """
        接收文本输入和音频保存路径，调用 TTS 完成文本转语音，保存音频文件服务
        """
        input_text = request.input_text
        output_path = request.input_filename
        # 创建保存目录（如果不存在）
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        logger.info(
            f"收到 TTS 生成 WAV 文件请求\n输入文本:[{input_text}]\n保存路径: {output_path}"
        )
        tts_result = self.chat_assistant.generate_wav(input_text, output_path)

        # 检查 TTS 结果是否有效
        if tts_result is False:
            response.success = False
            response.message = "TTS 未能成功生成 WAV 文件"
            logger.error(response.message)
            return response

        response.success = True
        response.message = f"WAV 文件已保存到 {output_path}"
        logger.info("请求 TTS 生成 WAV 文件成功")
        return response

    def handle_reload_config(self, request, response):
        """
        重新加载配置文件参数服务
        """
        logger.info("收到重新加载配置文件请求")

        # 重新加载ros参数
        self.load_config_and_initialize()

        # 重新初始化聊天助手
        self.chat_assistant.load_config_and_initialize()
        self.chat_assistant.start_recording()

        response.success = True
        response.message = "配置文件已重新加载"
        return response

    def handle_tts_infer(self, request, response):
        """
        接收文本输入，只调用 TTS 完成文本转语音，并播放音频服务
        """
        input_text = request.input

        logger.info(f"TTS 收到请求，输入文本: [{input_text}]")
        tts_result = self.chat_assistant.tts_infer(input_text)

        # 检查 TTS 结果是否有效
        if tts_result is False:
            response.success = False
            response.message = "TTS 播放超时 或者 TTS 播放音频太短"
            return response

        response.success = True
        response.message = "TTS 请求成功"
        logger.info("TTS 请求成功")
        return response

    def handle_llm_infer(self, request, response):
        """
        接收文本输入（可选用户ID），只调用 LLM 完成文本生成，返回文本结果服务
        """
        input_text = request.input
        request_user_id = request.user_id if hasattr(request, "user_id") else None
        request_user_id = request_user_id.strip() if request_user_id else None
        user_id = request_user_id if request_user_id else self.get_latest_user_id()

        logger.info(f"LLM 收到请求，输入文本: [{input_text}], user_id: [{user_id}]")
        llm_result = self.chat_assistant.llm_infer(input_text, user_id=user_id)

        # 检查 LLM 结果是否有效
        if llm_result is None:
            response.success = False
            response.message = "LLM 未能生成有效文本"
            logger.error(response.message)
            return response

        response.success = True
        response.message = llm_result
        logger.info("LLM 请求成功")
        return response

    def handle_asr_infer(self, request, response):
        """
        接收audio_path，只调用 ASR 完成语音识别，返回文本结果服务
        """
        audio_path = request.input

        # 检查 audio_path 是否有效存在
        if os.path.exists(audio_path) is False:
            response.success = False
            response.message = f"音频路径无效: {audio_path}"
            logger.error(response.message)
            return response

        logger.info(f"ASR 收到请求，音频路径: {audio_path}")
        asr_result = self.chat_assistant.asr_infer(audio_path)

        # 检查 ASR 结果是否有效
        if asr_result is None:
            response.success = False
            response.message = "ASR 未能识别出有效文本"
            logger.error(response.message)
            return response

        response.success = True
        response.message = asr_result
        logger.info("ASR 请求成功")
        return response

    def handle_activate_assistant(self, request, response):
        """
        激活LLM 和TTS服务
        """
        logger.info("激活LLM 和TTS服务")
        self.chat_assistant.activate_llm_agent()
        self.chat_assistant.activate_tts_client()
        response.success = True
        response.message = "LLM 和 TTS 已激活"
        return response

    def handle_idle_assistant(self, request, response):
        """
        将LLM 和TTS置于空闲状态服务
        """
        logger.info("将LLM 和TTS置于空闲状态")
        self.chat_assistant.deactivate_llm_agent()
        self.chat_assistant.deactivate_tts_client()
        response.success = True
        response.message = "LLM 和 TTS 已置于空闲状态"
        return response

    def handle_activate_asr(self, request, response):
        """
        激活ASR服务
        """
        logger.info("激活ASR")
        self.chat_assistant.activate_asr_client()
        response.success = True
        response.message = "ASR已激活"
        return response

    def handle_idle_asr(self, request, response):
        """
        将ASR置于空闲状态服务
        """
        logger.info("将ASR置于空闲状态")
        self.chat_assistant.deactivate_asr_client()
        response.success = True
        response.message = "ASR已置于空闲状态"
        return response

    def handle_activate_llm(self, request, response):
        """
        激活LLM服务
        """
        logger.info("激活LLM")
        self.chat_assistant.activate_llm_agent()
        response.success = True
        response.message = "LLM已激活"
        return response

    def handle_idle_llm(self, request, response):
        """
        将LLM置于空闲状态服务
        """
        logger.info("将LLM置于空闲状态")
        self.chat_assistant.deactivate_llm_agent()
        response.success = True
        response.message = "LLM已置于空闲状态"
        return response

    def handle_activate_tts(self, request, response):
        """
        激活TTS服务
        """
        logger.info("激活TTS")
        self.chat_assistant.activate_tts_client()
        response.success = True
        response.message = "TTS已激活"
        return response

    def handle_idle_tts(self, request, response):
        """
        将TTS置于空闲状态服务
        """
        logger.info("将TTS置于空闲状态")
        self.chat_assistant.deactivate_tts_client()
        response.success = True
        response.message = "TTS已置于空闲状态"
        return response

    def handle_tool_events(self):
        """
        处理工具事件队列中的事件
        """
        global tool_event_queue
        try:
            tool_event = tool_event_queue.get_nowait()

            if tool_event == ToolEvent.WAVE_HANDS.value:
                logger.info("Main loop handling tool event: WAVE_HANDS")
                # 在这里添加挥手回应的具体实现代码

            elif tool_event == ToolEvent.END_CONVERSATION.value:
                logger.info("Main loop handling tool event: END_CONVERSATION")
                # 在这里添加结束对话的具体实现代码
                self.chat_assistant.deactivate_llm_agent()

        except Empty:
            pass

    def handle_user_id(self, msg):
        """
        处理订阅到的用户ID消息
        """
        user_id = msg.data.strip() if msg.data else None
        self.last_user_id_msg_time = time.time()
        self.current_user_id = user_id
        logger.debug(f"收到用户ID消息: {user_id}")
        self.chat_assistant.set_current_user_id(user_id)


def main(args=None):
    rclpy.init(args=args)
    chat_assistant_node = ChatAssistantNode()
    chat_assistant_node.chat_assistant.start_recording()

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(chat_assistant_node)

    try:
        while rclpy.ok():

            # 定期检查订阅用户ID是否超时，超时后回退为 None
            chat_assistant_node.get_latest_user_id()

            if chat_assistant_node.chat_assistant.asr_text_queue.empty() is False:
                asr_text = chat_assistant_node.chat_assistant.asr_text_queue.get(
                    timeout=0.05
                )

                # 发布 asr_text 到话题
                msg = String()
                msg.data = asr_text
                chat_assistant_node.asr_publisher.publish(msg)
                # logger.info(f"发布 ASR 识别结果到话题: [{asr_text}]")

            if chat_assistant_node.chat_assistant.llm_text_queue.empty() is False:
                llm_response = (
                    chat_assistant_node.chat_assistant.llm_text_queue.get(
                        timeout=0.05
                    )
                )

                # 发布 llm_response 到话题
                msg = String()
                msg.data = llm_response
                chat_assistant_node.llm_publisher.publish(msg)
                # logger.info(f"发布 LLM 生成结果到话题: [{llm_response}]")

            if chat_assistant_node.chat_assistant.response_queue.empty() is False:
                response_data = chat_assistant_node.chat_assistant.response_queue.get(
                    timeout=0.05
                )

                # 发布 综合响应结果 到话题
                response_msg = Response()
                response_msg.asr_text = response_data.get("asr_text", "")
                response_msg.llm_text = response_data.get("llm_text", "")
                chat_assistant_node.response_publisher.publish(response_msg)
                logger.info(
                    f"发布 综合响应结果 到话题: ASR Text: [{response_msg.asr_text}], LLM Text: [{response_msg.llm_text}]"
                )

            if chat_assistant_node.chat_assistant.check_tts_active():
                # 发布 TTS 播放状态 到话题
                tts_msg = Bool()
                tts_msg.data = True
                chat_assistant_node.tts_status_publisher.publish(tts_msg)
            else:
                tts_msg = Bool()
                tts_msg.data = False
                chat_assistant_node.tts_status_publisher.publish(tts_msg)

            # global call_flag
            # if call_flag:
            #     call_flag = False
            #     logger.info("Main loop detected middleware call.")

            # handle tool events
            chat_assistant_node.handle_tool_events()

            # rclpy.spin_once(chat_assistant_node, timeout_sec=0.05)
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
