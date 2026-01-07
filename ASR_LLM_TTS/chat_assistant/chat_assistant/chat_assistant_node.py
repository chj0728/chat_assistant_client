import os
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException

from std_msgs.msg import String
from std_srvs.srv import Trigger
from chat_assistant_interfaces.srv import GetString, GenerateWav

from app.chat_assistant_v1 import ChatAssistant as ChatAssistantV1
from app.chat_assistant_v2 import ChatAssistant as ChatAssistantV2

from logger import logger


class ChatAssistantNode(Node):
    def __init__(self):
        super().__init__("chat_assistant_node")

        self.declare_parameter("config_path", "config/config.yaml")

        self.init_params()

        # 创建话题发布者
        ## 发布asr识别结果话题
        self.asr_publisher = self.create_publisher(String, "asr_result", 10)

        ## 发布 llm 生成结果话题
        self.llm_publisher = self.create_publisher(String, "llm_result", 10)

        # 创建服务
        ## 重新加载配置文件参数
        self.create_service(Trigger, "reload_config", self.handle_reload_config)

        ## 激活聊天助手服务
        self.create_service(
            Trigger, "activate_assistant", self.handle_activate_assistant
        )
        ## 将聊天助手置于空闲状态服务
        self.create_service(Trigger, "idle_assistant", self.handle_idle_assistant)

        ## 接收audio_path，直接播放音频服务
        self.create_service(GetString, "play_audio_file", self.handle_play_audio)

        ## 接收audio_path，只调用 ASR 完成语音识别，返回文本结果服务
        self.create_service(GetString, "asr_infer", self.handle_asr_infer)

        ## 接收文本输入，只调用 LLM 完成文本生成，返回文本结果服务
        self.create_service(GetString, "llm_infer", self.handle_llm_infer)

        ## 接收文本输入，只调用 TTS 完成文本转语音，并在线播放音频服务
        self.create_service(GetString, "tts_infer", self.handle_tts_infer)

        ## 接收文本输入和音频保存路径，调用 TTS 完成文本转语音，保存音频文件服务
        self.create_service(
            GenerateWav, "tts_generate_wav", self.handle_tts_generate_wav
        )

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
            f"收到 TTS 生成 WAV 文件请求，输入文本: {input_text}，保存路径: {output_path}"
        )
        tts_result = self.chat_assistant.generate_wav(input_text, output_path)

        # 检查 TTS 结果是否有效
        if tts_result is False:
            response.success = False
            response.message = "TTS 未能成功生成 WAV 文件"
            logger.error(response.message)
            return response

        response.success = True
        response.message = f"WAV 文件已保存到 {tts_result}"
        logger.info(f"WAV 文件已保存到 {tts_result}")
        return response

    def handle_reload_config(self, request, response):
        """
        重新加载配置文件参数服务
        """
        logger.info("收到重新加载配置文件请求")
        self.chat_assistant.load_config_and_initialize()
        response.success = True
        response.message = "配置文件已重新加载"
        return response

    def handle_tts_infer(self, request, response):
        """
        接收文本输入，只调用 TTS 完成文本转语音，并播放音频服务
        """
        input_text = request.input

        logger.info(f"收到 TTS 推理请求，输入文本: {input_text}")
        tts_result = self.chat_assistant.tts_infer(input_text)

        # 检查 TTS 结果是否有效
        if tts_result is False:
            response.success = False
            response.message = "TTS 未能成功合成或播放音频"
            logger.error(response.message)
            return response

        response.success = True
        response.message = "TTS 合成并播放音频成功"
        logger.info("TTS 推理成功")
        return response

    def handle_llm_infer(self, request, response):
        """
        接收文本输入，只调用 LLM 完成文本生成，返回文本结果服务
        """
        input_text = request.input

        logger.info(f"收到 LLM 推理请求，输入文本: {input_text}")
        llm_result = self.chat_assistant.llm_infer(input_text)

        # 检查 LLM 结果是否有效
        if llm_result is None:
            response.success = False
            response.message = "LLM 未能生成有效文本"
            logger.error(response.message)
            return response

        response.success = True
        response.message = llm_result
        logger.info(f"LLM 推理结果: {llm_result}")
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

        logger.info(f"收到 ASR 推理请求，音频路径: {audio_path}")
        asr_result = self.chat_assistant.asr_infer(audio_path)

        # 检查 ASR 结果是否有效
        if asr_result is None:
            response.success = False
            response.message = "ASR 未能识别出有效文本"
            logger.error(response.message)
            return response

        response.success = True
        response.message = asr_result
        logger.info(f"ASR 推理结果: {asr_result}")
        return response

    def handle_activate_assistant(self, request, response):
        """
        激活聊天助手服务
        """
        logger.info("激活聊天助手")
        self.chat_assistant.activate()
        response.success = True
        response.message = "聊天助手已激活"
        return response

    def handle_idle_assistant(self, request, response):
        """
        将聊天助手置于空闲状态服务
        """
        logger.info("将聊天助手置于空闲状态")
        self.chat_assistant.idle()
        response.success = True
        response.message = "聊天助手已置于空闲状态"
        return response

    def init_params(self):

        self.config_path = (
            self.get_parameter("config_path").get_parameter_value().string_value
        )
        logger.info(f"配置文件路径: {self.config_path}")

        self.chat_assistant = ChatAssistantV2(config_path=self.config_path)


def main(args=None):
    rclpy.init(args=args)
    chat_assistant_node = ChatAssistantNode()
    chat_assistant_node.chat_assistant.start_recording()

    try:
        while rclpy.ok():

            if chat_assistant_node.chat_assistant.asr_text_queue.empty() is False:
                asr_text = chat_assistant_node.chat_assistant.asr_text_queue.get(
                    timeout=0.05
                )

                # 发布 asr_text 到话题
                msg = String()
                msg.data = asr_text
                chat_assistant_node.asr_publisher.publish(msg)
                logger.info(f"发布 ASR 识别结果到话题: {asr_text}")

            if chat_assistant_node.chat_assistant.llm_response_queue.empty() is False:
                llm_response = (
                    chat_assistant_node.chat_assistant.llm_response_queue.get(
                        timeout=0.05
                    )
                )

                # 发布 llm_response 到话题
                msg = String()
                msg.data = llm_response
                chat_assistant_node.llm_publisher.publish(msg)
                logger.info(f"发布 LLM 生成结果到话题: {llm_response}")

            rclpy.spin_once(chat_assistant_node, timeout_sec=0.05)

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
            chat_assistant_node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
