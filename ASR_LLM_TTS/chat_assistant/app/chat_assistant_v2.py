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
from pathlib import Path
from queue import Queue, Full, Empty
from pypinyin import pinyin, Style
from enum import Enum


from asr.asrclient import ASRClient
from llm.llmclient import LLMClient
from tts.ttsplay import RealtimeTTSPlayer

from logger import logger

MAX_QUEUE_SIZE = 10

# 获取当前文件所在目录
current_dir = Path(__file__).resolve().parent
logger.info(f"当前文件目录: {current_dir}")
config_yaml_path = (current_dir / "../config/config.yaml").resolve()
logger.info(f"配置文件路径: {config_yaml_path}")


SPECIAL_WORD_MAP = {
    "智己": [
        "自己",
        "智几",
        "治己",
        "之际",
        "知己",
        "只记",
        "只几",
        "只机",
        "只及",
        "之几",
        "之机",
        "之及",
        "治几",
        "治机",
        "治及",
        "直几",
        "直机",
        "直及",
        "植机",
        "植及",
        "执机",
        "执及",
        "职机",
        "职及",
        "置机",
        "置及",
    ],
}


class AssistantState(Enum):
    IDLE = 0  # 空闲 / 待唤醒
    ACTIVE = 1  # 激活状态
    LISTENING = 2  # 正在录音（等用户说话）
    THINKING = 3  #  ASR / LLM 推理中
    SPEAKING = 4  # TTS 播放中


class ChatAssistant:
    def __init__(self, config_path: str):

        self.config_yaml = Path(config_path).expanduser().resolve()
        self.configs = {}

        self.asr_text = ""
        self.llm_response = ""

        self.asr_text_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.llm_response_queue = Queue(maxsize=MAX_QUEUE_SIZE)

        # 同时保存 jason 形式的响应文本，包括 asr_text 和 llm_text
        self.response_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.response_json = {}

        self.recorder_thread = None
        self.recording_active = False

        self.load_config_and_initialize()

    def _push_queue(self, data_queue: Queue, value) -> None:
        """将最新文本加入有限队列，保持队列容量受控。"""
        try:
            data_queue.put_nowait(value)
        except Full:
            try:
                data_queue.get_nowait()
            except Empty:
                pass
            data_queue.put_nowait(value)

    def _set_state(self, new_state: AssistantState) -> None:
        with self.state_lock:
            self.state = new_state

    def get_state(self) -> AssistantState:
        with self.state_lock:
            return self.state

        # # 启动录音
        # self.start_recording()

    # 析构函数
    def __del__(self):
        """
        析构函数，释放资源
        """
        logger.info("ChatAssistant 正在释放资源...")
        self.stop_recording()
        logger.info("ChatAssistant 资源已释放.")

    def start_recording(self):
        """
        开始录音
        """
        if self.recording_active:
            logger.warning("录音线程已在运行，忽略重复启动请求")
            return

        self.recording_active = True

        # 启动音频录制线程
        self.recorder_thread = threading.Thread(
            target=self.audio_recorder_thread, daemon=True
        )
        self.recorder_thread.start()
        # self._set_state(AssistantState.LISTENING)

    def stop_recording(self):
        """
        停止录音
        """
        if not self.recording_active:
            logger.info("录音线程已停止")
            return

        self.recording_active = False

        if self.recorder_thread and self.recorder_thread.is_alive():
            self.recorder_thread.join()
        self.recorder_thread = None
        # self._set_state(AssistantState.IDLE)

    def load_config_and_initialize(self):

        # ----------- 读取配置文件 -----------
        try:
            with open(self.config_yaml, "r", encoding="utf-8") as f:
                self.configs = yaml.safe_load(f)
                logger.info(f"配置文件内容:\n{self.configs}")
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            # raise e

        # ----------- 初始化ASR、LLM、TTS客户端 -----------
        asr_cfg = self.configs.get("ASR", {})
        llm_cfg = self.configs.get("LLM", {})
        tts_cfg = self.configs.get("TTS", {})

        self.asr_client = ASRClient(
            host=asr_cfg.get("host", "http://192.168.50.125"),
            port=asr_cfg.get("port", 2002),
            timeout=asr_cfg.get("timeout", 30),
        )

        self.llm_client = LLMClient(
            host=llm_cfg.get("host", "http://192.168.50.125"),
            port=llm_cfg.get("port", 8000),
        )
        system_prompt = llm_cfg.get("system_prompt", "")
        if system_prompt:
            self.llm_client.add_system_prompt(system_prompt)

        self.tts_client = RealtimeTTSPlayer(
            host=tts_cfg.get("host", "http://192.168.50.125"),
            port=tts_cfg.get("port", 50000),
        )

        # ----------- 初始化音频录制和VAD参数 -----------
        audio_cfg = self.configs.get("Audio", {})
        vad_cfg = self.configs.get("VAD", {})

        self.audio_rate = audio_cfg.get("rate", 16000)
        self.audio_channels = audio_cfg.get("channels", 1)
        self.chunk_size = audio_cfg.get("chunk_size", 1024)

        self.vad_mode = vad_cfg.get("mode", 3)
        self.output_dir = (current_dir / vad_cfg.get("output_dir", "output")).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.no_speech_threshold = vad_cfg.get("no_speech_threshold", 0.5)
        self.reactive_kws_threshold = vad_cfg.get("reactive_kws_threshold", 30)
        self.decibel_threshold = vad_cfg.get("decibel_threshold", -40)
        self.min_recording_duration = vad_cfg.get("min_recording_duration", 1.0)
        self.max_recording_duration = vad_cfg.get("max_recording_duration", 10.0)
        self.pause_duration = vad_cfg.get("pause_duration", 1.5)
        self.vad = webrtcvad.Vad(self.vad_mode)

        kws_cfg = self.configs.get("KWS", {})
        self.set_kws_pinyin = kws_cfg.get("wake_word_pinyin", "hi xiao bai")
        self.flag_kws_used = kws_cfg.get("enable", True)
        self.flag_kws = 0  # 唤醒词检测标志
        self.failed_enable_kws_count = 0  # 连续未检测到唤醒词计数

        self.recording_active = False  # 当前是否处于录音状态
        self.segments_to_save = []  # 待保存的音频片段
        self.saved_intervals = []  # 已保存的时间区间
        self.last_active_time = time.time()  # 上次检测到有效语音的时间
        self.last_vad_end_time = 0  # 上次保存的 VAD 有效段结束时间
        self.last_llm_time = time.time()  # 上次与 LLM 交互的时间
        self.audio_file_count = 0

        self.enable_replace_special_characters = self.configs.get(
            "enable_replace_special_characters", False
        )
        self.word_map = SPECIAL_WORD_MAP

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

    # 统计字符串中的汉字数量
    def count_chinese_characters(self, input_string):
        """
        统计字符串中的汉字数量。

        :param input_string: 原始字符串
        :return: 汉字数量
        """
        chinese_characters = re.findall(r"[\u4e00-\u9fa5]", input_string)
        return len(chinese_characters)

    # 替换字符串中的特殊字符为智己
    def replace_special_characters(self, input_string):
        """
        替换字符串中的特殊字符如为智己。

        :param input_string: 原始字符串
        :return: 替换后的字符串
        """
        if not input_string:
            return input_string

        for correct_word, variants in self.word_map.items():
            for variant in variants:
                input_string = input_string.replace(variant, correct_word)

        return input_string

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

    def _calculate_decibel(self, audio_np: np.ndarray) -> float:
        """计算音频分贝值，避免对零取对数。"""
        if audio_np.size == 0:
            return float("-inf")
        rms = np.sqrt(np.mean(np.square(audio_np)))
        return 20 * np.log10(max(rms, 1e-10))

    def _float_to_pcm16(self, audio_np: np.ndarray) -> bytes:
        """将 float32 音频转换为 PCM16 字节流。"""
        audio_clipped = np.clip(audio_np, -1.0, 1.0)
        return (audio_clipped * 32767).astype(np.int16).tobytes()

    def _finalize_pending_segments(self, timestamp: float) -> None:
        """在长时间静音后触发音频保存。"""
        if (
            self.segments_to_save
            and self.segments_to_save[-1][1] > self.last_vad_end_time
        ):
            self.save_audio_only()
            self.last_active_time = timestamp

    def save_audio_only(self):
        """
        只负责把 segments_to_save 中的音频保存为 wav 文件
        """
        if not self.segments_to_save:
            return None

        # # ===============================
        # # TTS 播放中，跳过保存
        # # ===============================
        # if self.tts_client.is_active():
        #     # print("TTS 播放中，跳过保存音频")
        #     logger.warning("TTS 播放中，跳过保存音频")
        #     self.segments_to_save.clear()
        #     self.last_llm_time = time.time()
        #     return None

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
        audio_output_path = self.output_dir / f"audio_{self.audio_file_count}.wav"

        # ===============================
        # 3. 拼接音频
        # ===============================
        audio_frames = [seg[0] for seg in self.segments_to_save]

        # ===============================
        # 4. 保存 WAV
        # ===============================
        with wave.open(str(audio_output_path), "wb") as wf:
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
        self.Inference(str(audio_output_path))

        return audio_output_path

    # 音频录制线程
    def audio_recorder_thread(self):

        audio_buffer = []
        frames_collected = 0
        analysis_interval_frames = max(
            1, max(self.chunk_size, int(0.10 * self.audio_rate))
        )
        logger.info("音频录制已开始（sounddevice）")

        def reset_buffer():
            nonlocal audio_buffer, frames_collected
            audio_buffer.clear()
            frames_collected = 0

        def audio_callback(indata, frames, time_info, status):
            nonlocal frames_collected

            if not self.recording_active:
                raise sd.CallbackStop()

            now = time.time()

            # indata: float32 [-1.0, 1.0]
            audio_buffer.append(indata.copy())
            frames_collected += frames

            if frames_collected >= analysis_interval_frames:
                audio_np = np.concatenate(audio_buffer, axis=0)
                reset_buffer()

                decibel = self._calculate_decibel(audio_np)
                if decibel < self.decibel_threshold:
                    if now - self.last_active_time > self.no_speech_threshold:
                        self._finalize_pending_segments(now)
                    return

                audio_int16 = self._float_to_pcm16(audio_np)

                if self.check_vad_activity(audio_int16):
                    logger.info("检测到语音活动，分贝: {:.2f} dB".format(decibel))
                    self.last_active_time = now
                    self.segments_to_save.append((audio_int16, now))

            if now - self.last_active_time > self.no_speech_threshold:
                self._finalize_pending_segments(now)

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
        self._set_state(AssistantState.ACTIVE)

    def idle(self):
        """
        进入空闲状态
        """
        self._set_state(AssistantState.IDLE)

    def generate_wav(self, text, output_path):
        """
        负责调用 TTS 完成文本转语音，保存音频文件
        """
        logger.info(f"开始 TTS 生成 WAV 文件: {output_path}")
        try:
            tts_result = self.tts_client.generate_wav(text, output_path)
            return tts_result
        except Exception as e:
            return False

    def play_audio(self, audio_path):
        """
        负责调用 TTS 播放音频文件
        """
        logger.info(f"开始播放音频文件: {audio_path}")
        try:
            self.tts_client.play_audio(audio_path, block=False)
            return True
        except Exception as e:
            return False

    def interrupt(self):
        """
        负责中断当前 TTS 播放
        """
        # print("中断当前 TTS 播放")
        logger.info("开始中断后台播放...")
        try:
            self.tts_client.interrupt()
            logger.info("后台播放已中断")
            return True
        except Exception as e:
            return False

    def asr_infer(self, audio_path):
        """
        负责调用 ASR 完成语音识别
        """
        logger.info(f"开始 ASR 识别: {audio_path}")
        try:
            asr_text = self.asr_client.recognize(audio_path).strip()
            logger.info(f"ASR 识别结果: {asr_text}")
            return asr_text
        except Exception as e:
            logger.error(f"ASR 识别失败: {e}")
            return ""

    def llm_infer(self, asr_text):
        """
        负责调用 LLM 完成对话
        """
        logger.info("开始与模型对话...")
        llm_response = ""
        try:
            llm_response = self.llm_client.chat_response(asr_text)
            logger.info(f"LLM 回复: {llm_response}")
            return llm_response
        except Exception as e:
            logger.error(f"LLM 对话失败: {e}")
            return ""

    def tts_infer(self, llm_response):
        """
        负责调用 TTS 完成语音合成和播放
        """
        logger.info("开始 TTS 播放...")
        try:
            self.tts_client.speak(llm_response.strip())
            return True
        except Exception as e:
            logger.error(f"TTS 播放失败: {e}")
            return False

    def kws_infer(self, asr_text):
        """
        负责唤醒词检测
        """

        # 提取汉字并转换为拼音
        pinyin_text = self.extract_chinese_and_convert_to_pinyin(asr_text)
        logger.info(f"转换为拼音: {pinyin_text}")

        if self.set_kws_pinyin in pinyin_text and self.tts_client.is_active():
            logger.warning("检测到唤醒词， TTS 播放中，打断播放以避免语音叠加")

            self.flag_kws = 1

            self.tts_client.interrupt()

            time.sleep(0.5)

            self.last_llm_time = time.time()
            return True

        # 判断是否需要重置唤醒词状态
        if time.time() - self.last_llm_time > self.reactive_kws_threshold:
            # print("长时间未与 LLM 交互，重置唤醒词状态")
            logger.info("长时间未与 LLM 交互，重置唤醒词状态")
            self.flag_kws = 0

        # 判断是否启用唤醒词检测
        if self.flag_kws_used and self.flag_kws == 0:

            logger.info("需要唤醒词检测")

            if self.set_kws_pinyin in pinyin_text:
                logger.info("检测到唤醒词，开始与模型对话")

                self.flag_kws = 1
                self.failed_enable_kws_count = 0

                self.last_llm_time = time.time()
                return True
            else:

                self.flag_kws = 0
                self.failed_enable_kws_count += 1

                logger.info(
                    "未检测到唤醒词，失败次数: {}".format(self.failed_enable_kws_count)
                )

                if self.failed_enable_kws_count >= 2:

                    self._push_queue(
                        self.llm_response_queue, "请说出正确的唤醒词后再进行对话。"
                    )
                    self.response_json["llm_text"] = "请说出正确的唤醒词后再进行对话。"

                    self.failed_enable_kws_count = 0
                else:
                    self._push_queue(self.llm_response_queue, "")
                    self.response_json["llm_text"] = ""

                self.last_llm_time = time.time()
                return False

        else:
            logger.info("不需要唤醒词检测")
            return True

    def Inference(self, audio_path):
        """
        负责调用 ASR、LLM、TTS 完成一次完整的交互
        """

        # jason 形式的响应文本，包括 asr_text 和 llm_text
        self.response_json = {}

        # -------- asr 识别 -----------
        self.asr_text = self.asr_infer(audio_path)
        # ## response_json 更新 asr_text
        # response_json["asr_text"] = self.asr_text
        if not self.asr_text:
            logger.warning("ASR 未识别到有效文本，跳过本次交互")
            self.last_llm_time = time.time()
            # self._set_state(AssistantState.LISTENING)
            return

        # -------- 判断asr_text中汉字数量，过少则忽略 ----------
        chinese_char_count = self.count_chinese_characters(self.asr_text)
        if chinese_char_count < 4:
            logger.warning("ASR 识别文本中汉字数量过少，跳过本次交互")
            self.last_llm_time = time.time()
            return

        # ------- 替换特殊词汇 -------
        if self.enable_replace_special_characters:
            logger.info(f"替换前 ASR 文本: {self.asr_text}")
            self.asr_text = self.replace_special_characters(self.asr_text)
            logger.info(f"替换后 ASR 文本: {self.asr_text}")
        else:
            logger.info("未启用特殊词汇替换功能")

        ## 更新asr_text队列
        self._push_queue(self.asr_text_queue, self.asr_text)
        ## response_json 更新 asr_text
        self.response_json["asr_text"] = self.asr_text

        # ----------- 唤醒词检测 -----------
        if not self.kws_infer(self.asr_text):
            # self._set_state(AssistantState.LISTENING)
            # 更新 response_queue 队列
            self._push_queue(self.response_queue, self.response_json)
            self.last_llm_time = time.time()
            return

        # self._set_state(AssistantState.THINKING)

        # -------- 检查 TTS 播放状态 ----------
        if self.tts_client.is_active():
            logger.warning("语音播放中，跳过本次交互")
            self.last_llm_time = time.time()
            return

        # -------- llm 对话 -----------
        self.llm_response = self.llm_infer(self.asr_text)
        if not self.llm_response:
            self.last_llm_time = time.time()
            # self._set_state(AssistantState.LISTENING)
            logger.warning("LLM 未生成有效回复，跳过本次交互")
            return
        ## 更新llm_response队列
        self._push_queue(self.llm_response_queue, self.llm_response)

        ## response_json 更新 llm_text
        self.response_json["llm_text"] = self.llm_response
        ## 更新 response_queue 队列
        self._push_queue(self.response_queue, self.response_json)

        # -------- 检查当前状态是否为空闲 ----------
        if self.get_state() == AssistantState.IDLE:
            logger.warning("语音助手未激活，跳过本次交互")
            self.last_llm_time = time.time()
            time.sleep(1.0)
            return

        # -------- tts 播放 -----------
        # self._set_state(AssistantState.SPEAKING)
        self.tts_infer(self.llm_response)
        self.last_llm_time = time.time()
        # self._set_state(AssistantState.LISTENING)

        logger.info("本次交互完成，等待下一次录音...")


if __name__ == "__main__":

    assistant = ChatAssistant(config_path=str(config_yaml_path))

    assistant.start_recording()

    # print("ChatAssistant 初始化完成")
    logger.info("ChatAssistant 初始化完成")

    try:

        logger.info("按 Ctrl+C 停止程序")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("停止程序中...")
        assistant.stop_recording()
        logger.info("程序已停止")
