import os
import re
import wave
import sounddevice as sd
import numpy as np
import time
import threading
import yaml
import webrtcvad
from scipy.io.wavfile import write
from queue import Queue
from pypinyin import pinyin, Style
from enum import Enum


from asr.asrclient import ASRClient
from llm.llmclient import LLMClient
from tts.ttsplay import RealtimeTTSPlayer

from logger import logger

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# print(f"当前文件目录: {current_dir}")
logger.info(f"当前文件目录: {current_dir}")
config_yaml_path = os.path.join(current_dir, "../config/config.yaml")
# print(f"配置文件路径: {config_yaml_path}")
logger.info(f"配置文件路径: {config_yaml_path}")


class AssistantState(Enum):
    IDLE = 0  # 空闲 / 待唤醒
    ACTIVE = 1  # 激活状态
    LISTENING = 2  # 正在录音（等用户说话）
    THINKING = 3  #  ASR / LLM 推理中
    SPEAKING = 4  # TTS 播放中


class ChatAssistant:
    def __init__(self, config_path: str):

        self.config_yaml = config_path
        self.configs = None

        self.asr_text = ""
        self.asr_text_queue = Queue()
        self.llm_response = ""
        self.llm_response_queue = Queue()

        self.load_config_and_initialize()

        # 启动音频录制线程
        self.recorder_thread = threading.Thread(
            target=self.audio_recorder_thread, daemon=True
        )
        self.recorder_thread.start()

    def load_config_and_initialize(self):

        # ----------- 读取配置文件 -----------
        try:
            with open(self.config_yaml, "r", encoding="utf-8") as f:
                self.configs = yaml.safe_load(f)
                # print(f"配置文件内容:\n{self.configs}")
                logger.info(f"配置文件内容:\n{self.configs}")
        except Exception as e:
            # print(f"读取配置文件失败: {e}")
            logger.error(f"读取配置文件失败: {e}")
            raise e

        # ----------- 初始化ASR、LLM、TTS客户端 -----------
        self.asr_client = ASRClient(
            host=self.configs.get("ASR", {}).get("host", "http://192.168.50.125"),
            port=self.configs.get("ASR", {}).get("port", 2002),
            timeout=30,
        )

        self.llm_client = LLMClient(
            host=self.configs.get("LLM", {}).get("host", "http://192.168.50.125"),
            port=self.configs.get("LLM", {}).get("port", 8000),
        )
        self.llm_client.add_system_prompt(
            self.configs.get("LLM", {}).get("system_prompt", "")
        )

        self.tts_client = RealtimeTTSPlayer(
            host=self.configs.get("TTS", {}).get("host", "http://192.168.50.125"),
            port=self.configs.get("TTS", {}).get("port", 50000),
        )

        # ----------- 初始化音频录制和VAD参数 -----------
        self.audio_rate = self.configs.get("Audio", {}).get("rate", 16000)
        self.audio_channels = self.configs.get("Audio", {}).get("channels", 1)
        self.chunk_size = self.configs.get("Audio", {}).get("chunk_size", 1024)

        self.vad_mode = self.configs.get("VAD", {}).get("mode", 3)
        self.output_dir = (
            current_dir + "/" + self.configs.get("VAD", {}).get("output_dir", "output")
        )
        os.makedirs(self.output_dir, exist_ok=True)
        self.no_speech_threshold = self.configs.get("VAD", {}).get(
            "no_speech_threshold", 0.5
        )
        self.reactive_kws_threshold = self.configs.get("VAD", {}).get(
            "reactive_kws_threshold", 30
        )
        self.min_recording_duration = self.configs.get("VAD", {}).get(
            "min_recording_duration", 1.0
        )
        self.max_recording_duration = self.configs.get("VAD", {}).get(
            "max_recording_duration", 10.0
        )
        self.pause_duration = self.configs.get("VAD", {}).get("pause_duration", 1.5)
        self.vad = webrtcvad.Vad(self.vad_mode)

        self.set_kws_pinyin = self.configs.get("KWS", {}).get(
            "wake_word_pinyin", "hi xiao bai"
        )
        self.flag_kws_used = self.configs.get("KWS", {}).get("enable", True)
        self.flag_kws = 0  # 唤醒词检测标志
        self.failed_enable_kws_count = 0  # 连续未检测到唤醒词计数

        self.recording_active = True  # 当前是否处于录音状态
        self.segments_to_save = []  # 待保存的音频片段
        self.saved_intervals = []  # 已保存的时间区间
        self.last_active_time = time.time()  # 上次检测到有效语音的时间
        self.last_vad_end_time = 0  # 上次保存的 VAD 有效段结束时间
        self.last_llm_time = time.time()  # 上次与 LLM 交互的时间
        self.audio_file_count = 0

        self.state = AssistantState.IDLE
        self.state_lock = threading.Lock()

        # 是否允许 ASR
        self.enable_asr = True

    def extract_chinese_and_convert_to_pinyin(self, input_string):
        """
        提取字符串中的汉字，并将其转换为拼音。

        :param input_string: 原始字符串
        :return: 转换后的拼音字符串
        """
        # 使用正则表达式提取所有汉字
        chinese_characters = re.findall(r"[\u4e00-\u9fa5]", input_string)
        # 将汉字列表合并为字符串
        chinese_text = "".join(chinese_characters)

        # 转换为拼音
        pinyin_result = pinyin(chinese_text, style=Style.NORMAL)
        # 将拼音列表拼接为字符串
        pinyin_text = " ".join([item[0] for item in pinyin_result])

        return pinyin_text

    def check_vad_activity(self, audio_bytes: bytes) -> bool:
        """
        audio_bytes: int16 PCM, mono
        """
        frame_ms = 30  # webrtcvad 推荐
        bytes_per_sample = 2
        frame_size = int(self.audio_rate * frame_ms / 1000) * bytes_per_sample

        if len(audio_bytes) < frame_size:
            return False

        for i in range(0, len(audio_bytes) - frame_size + 1, frame_size):
            frame = audio_bytes[i : i + frame_size]
            if self.vad.is_speech(frame, self.audio_rate):
                return True

        return False

    def save_audio_only(self):
        """
        只负责把 segments_to_save 中的音频保存为 wav 文件
        """
        if not self.segments_to_save:
            return None

        # ===============================
        # TTS 播放中，跳过保存
        # ===============================
        if self.tts_client.is_active():
            # print("TTS 播放中，跳过保存音频")
            logger.warning("TTS 播放中，跳过保存音频")
            self.segments_to_save.clear()
            self.last_llm_time = time.time()
            return None
        # ===============================
        # 缓冲时间判断
        # ===============================
        current_time = time.time()
        if current_time - self.last_llm_time < self.pause_duration:
            logger.warning("缓冲时间内，跳过保存音频")
            self.segments_to_save.clear()
            return None

        # ===============================
        # 2. 时间区间判断（防重复）
        # ===============================
        start_time = self.segments_to_save[0][1]
        end_time = self.segments_to_save[-1][1]

        # 检查是否与之前的片段重叠
        if self.saved_intervals and self.saved_intervals[-1][1] >= start_time:
            # print("当前片段与之前片段重叠，跳过保存")
            logger.warning("当前片段与之前片段重叠，跳过保存")
            self.segments_to_save.clear()
            return None

        # 检查录音时长是否满足要求
        recording_duration = end_time - start_time
        # print(f"录音时长: {recording_duration:.2f} 秒")
        logger.info(f"录音时长: {recording_duration:.2f} 秒")
        if recording_duration < self.min_recording_duration:
            # print("录音时长过短，跳过保存")
            logger.warning("录音时长过短，跳过保存")
            self.segments_to_save.clear()
            return None
        if recording_duration > self.max_recording_duration:
            # print("录音时长过长，跳过保存")
            logger.warning("录音时长过长，跳过保存")
            self.segments_to_save.clear()
            return None

        # ===============================
        # 1. 生成输出路径
        # ===============================
        # self.audio_file_count += 1
        self.audio_file_count = 1
        audio_output_path = os.path.join(
            self.output_dir, f"audio_{self.audio_file_count}.wav"
        )

        os.makedirs(os.path.dirname(audio_output_path), exist_ok=True)

        # ===============================
        # 3. 拼接音频
        # ===============================
        audio_frames = [seg[0] for seg in self.segments_to_save]

        # ===============================
        # 4. 保存 WAV
        # ===============================
        with wave.open(audio_output_path, "wb") as wf:
            wf.setnchannels(self.audio_channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.audio_rate)
            wf.writeframes(b"".join(audio_frames))
        # print(f"检测到有效语音，已保存音频文件: {audio_output_path}")
        logger.info(f"检测到有效语音，已保存音频文件: {audio_output_path}")
        # print(f"音频已保存: {audio_output_path}")

        # ===============================
        # 5. 更新状态
        # ===============================
        self.saved_intervals.append((start_time, end_time))
        self.last_vad_end_time = end_time

        self.segments_to_save.clear()

        # 使用线程执行推理
        # temp_audio_output_path = "/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/tts/intro.wav"
        # threading.Thread(target=self.Inference, args=(audio_output_path,)).start()
        # 直接调用函数
        self.Inference(audio_output_path)

        return audio_output_path

    # 音频录制线程
    def audio_recorder_thread(self):

        audio_buffer = []
        frames_collected = 0
        logger.info("音频录制已开始（sounddevice）")

        def audio_callback(indata, frames, time_info, status):
            nonlocal audio_buffer, frames_collected

            if self.state == AssistantState.IDLE:
                logger.info("当前状态为空闲，停止录音")
                time.sleep(1.0)
                return

            if not self.recording_active:
                raise sd.CallbackStop()

            # indata: float32 [-1.0, 1.0]
            audio_buffer.append(indata.copy())
            frames_collected += frames

            # 每 0.10 秒检测一次 VAD
            if frames_collected >= int(0.10 * self.audio_rate):
                audio_np = np.concatenate(audio_buffer, axis=0)

                # 转成 int16 bytes（保持原来的 VAD 接口）
                audio_int16 = (audio_np * 32767).astype(np.int16).tobytes()

                vad_result = self.check_vad_activity(audio_int16)

                if vad_result:
                    # print("检测到语音活动...")
                    logger.info("检测到语音活动...")
                    self.last_active_time = time.time()
                    self.segments_to_save.append((audio_int16, time.time()))
                else:
                    pass
                    # print("静音中...")

                audio_buffer.clear()
                frames_collected = 0

            # 检查无效语音时间
            if time.time() - self.last_active_time > self.no_speech_threshold:
                if (
                    self.segments_to_save
                    and self.segments_to_save[-1][1] > self.last_vad_end_time
                ):
                    # save_audio_video()
                    self.save_audio_only()
                    self.last_active_time = time.time()
            time.sleep(0.01)

        with sd.InputStream(
            samplerate=self.audio_rate,
            channels=self.audio_channels,
            dtype="float32",
            blocksize=self.chunk_size,
            callback=audio_callback,
        ):
            while self.recording_active:
                time.sleep(1)

        # print("音频录制已停止")
        logger.info("音频录制已停止")

    def activate(self):
        """
        激活助手，进入 ACTIVE 状态
        """
        with self.state_lock:
            self.state = AssistantState.ACTIVE

    def idle(self):
        """
        进入空闲状态
        """
        with self.state_lock:
            self.state = AssistantState.IDLE

    def generate_wav(self, text, output_path):
        """
        负责调用 TTS 完成文本转语音，保存音频文件
        """
        print(f"开始 TTS 生成 WAV 文件: {output_path}")
        try:
            tts_result = self.tts_client.generate_wav(text, output_path)
            return tts_result
        except Exception as e:
            return False

    def play_audio(self, audio_path):
        """
        负责调用 TTS 播放音频文件
        """
        print(f"开始播放音频文件: {audio_path}")
        try:
            self.tts_client.play_audio(audio_path, block=True)
            return True
        except Exception as e:
            return False

    def asr_infer(self, audio_path):
        """
        负责调用 ASR 完成语音识别
        """
        print(f"开始 ASR 识别: {audio_path}")
        try:
            asr_text = self.asr_client.recognize(audio_path).strip()
            # print(f"ASR 识别结果: {asr_text}")
            logger.info(f"ASR 识别结果: {asr_text}")
            return asr_text
        except Exception as e:
            # print(f"ASR 识别失败: {e}")
            logger.error(f"ASR 识别失败: {e}")
            return ""

    def llm_infer(self, asr_text):
        """
        负责调用 LLM 完成对话
        """
        print("开始与模型对话...")
        llm_response = ""
        try:
            llm_response = self.llm_client.chat_response(asr_text)
            # print(f"LLM 回复: {llm_response}")
            logger.info(f"LLM 回复: {llm_response}")
            return llm_response
        except Exception as e:
            # print(f"LLM 对话失败: {e}")
            logger.error(f"LLM 对话失败: {e}")
            return ""

    def tts_infer(self, llm_response):
        """
        负责调用 TTS 完成语音合成和播放
        """
        # print("开始 TTS 播放...")
        logger.info("开始 TTS 播放...")
        try:
            self.tts_client.speak(llm_response.strip())
            return True
        except Exception as e:
            # print(f"TTS 播放失败: {e}")
            logger.error(f"TTS 播放失败: {e}")
            return False

    def kws_infer(self, asr_text):
        """
        负责唤醒词检测
        """

        # 判断是否需要重置唤醒词状态
        if time.time() - self.last_llm_time > self.reactive_kws_threshold:
            # print("长时间未与 LLM 交互，重置唤醒词状态")
            logger.info("长时间未与 LLM 交互，重置唤醒词状态")
            self.flag_kws = 0

        # 判断是否启用唤醒词检测
        if self.flag_kws_used and self.flag_kws == 0:
            pinyin_text = self.extract_chinese_and_convert_to_pinyin(asr_text)
            # print(f"转换为拼音: {pinyin_text}")
            logger.info(f"转换为拼音: {pinyin_text}")

            if self.set_kws_pinyin in pinyin_text:
                # print("检测到唤醒词，开始与模型对话")
                logger.info("检测到唤醒词，开始与模型对话")
                self.flag_kws = 1
                self.last_llm_time = time.time()
                self.failed_enable_kws_count = 0
            else:
                # print("未检测到唤醒词，忽略本次输入")
                logger.info("未检测到唤醒词，忽略本次输入")
                self.flag_kws = 0
                self.failed_enable_kws_count += 1
                if self.failed_enable_kws_count >= 2:
                    self.tts_client.play_audio(
                        current_dir + "/wavs/enable_kws.wav", block=True
                    )
                    self.failed_enable_kws_count = 0
                return False
        return True

    def Inference(self, audio_path):
        """
        负责调用 ASR、LLM、TTS 完成一次完整的交互
        """

        # asr 识别
        self.asr_text = self.asr_infer(audio_path)
        if not self.asr_text:
            logger.warning("ASR 未识别到有效文本")
            return
        ## 更新asr_text队列
        self.asr_text_queue.put(self.asr_text)

        # 唤醒词检测
        if not self.kws_infer(self.asr_text):
            return

        # llm 对话
        self.llm_response = self.llm_infer(self.asr_text)
        if not self.llm_response:
            self.last_llm_time = time.time()
            return
        ## 更新llm_response队列
        self.llm_response_queue.put(self.llm_response)

        # tts 播放
        self.tts_infer(self.llm_response)
        self.last_llm_time = time.time()

        # print("本次交互完成，等待下一次录音...")
        logger.info("本次交互完成，等待下一次录音...")

        # 控制队列大小，最多保留最新的10条记录
        while self.asr_text_queue.qsize() > 10:
            self.asr_text_queue.get(timeout=0.01)
        while self.llm_response_queue.qsize() > 10:
            self.llm_response_queue.get(timeout=0.01)


if __name__ == "__main__":

    assistant = ChatAssistant(config_path=config_yaml_path)

    # print("ChatAssistant 初始化完成")
    logger.info("ChatAssistant 初始化完成")

    try:
        # # 启动音频录制线程
        # recorder_thread = threading.Thread(
        #     target=assistant.audio_recorder_thread, daemon=True
        # )
        # recorder_thread.start()

        print("按 Ctrl+C 停止程序")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("停止录音...")
        assistant.recording_active = False
        assistant.recorder_thread.join()
        logger.info("程序已退出")
