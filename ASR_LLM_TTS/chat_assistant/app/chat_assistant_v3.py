import re
import threading
import time
import wave
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Generator

import numpy as np
import sounddevice as sd
import webrtcvad
import yaml
from asr import ASRClient
from config import load_config
from llm import LLMAgent
from logger import logger
from pypinyin import Style, pinyin
from tts import RealtimeTTSPlayer, TTSClient

MAX_QUEUE_SIZE = 10

SPECIAL_WORD_MAP = {
    # 这里目标正确词作为键，常见错误变体列表作为值，可以根据实际情况调整和扩展
    "": [
        # 常见 ASR 错误示例，可以根据实际情况调整和扩展
    ],
}


@dataclass
class ResponseData:
    asr_text: str = ""
    llm_text: str = ""

    def clear(self):
        """重置响应数据"""
        self.asr_text = ""
        self.llm_text = ""


class AssistantState(Enum):
    IDLE = 0  # 空闲 / 待唤醒
    ACTIVE = 1  # 激活状态
    LISTENING = 2  # 正在录音（等用户说话）
    THINKING = 3  #  ASR / LLM 推理中
    SPEAKING = 4  # TTS 播放中


class ASRClientState(Enum):
    IDLE = 0  # 空闲
    ACTIVE = 1  # 激活状态


class LLMAgentState(Enum):
    IDLE = 0  # 空闲
    ACTIVE = 1  # 激活状态


class TTSClientState(Enum):
    IDLE = 0  # 空闲
    ACTIVE = 1  # 激活状态


class ChatAssistant:
    def __init__(
        self,
        config_path: str,
        dynamic_tool_middlewares=None,
        dynamic_middleware_list=None,
    ):

        self.config_yaml = Path(config_path).expanduser().resolve()
        self.configs = {}

        self.asr_text = ""
        self.llm_text = ""
        self.current_user_id = None

        self.asr_text_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.llm_text_queue = Queue(maxsize=MAX_QUEUE_SIZE)

        # 同时包括 asr_text 和 llm_text
        self.response_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        # self.response_json = {}
        self.response_data = ResponseData()
        self.response_data.clear()

        self.input_stream = None
        self.recorder_thread = None
        self.recording_active = False

        # self.dynamic_tool_middlewares = dynamic_tool_middlewares
        self.dynamic_middleware_list = dynamic_middleware_list

        self.load_config_and_initialize()

    def __push_queue(self, data_queue: Queue, value) -> None:
        """将最新文本加入有限队列，保持队列容量受控。"""
        try:
            data_queue.put_nowait(value)
        except Full:
            try:
                data_queue.get_nowait()
            except Empty:
                pass
            data_queue.put_nowait(value)

    def set_state(self, new_state: AssistantState) -> None:
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
            target=self.__audio_recorder_thread, daemon=True
        )
        self.recorder_thread.start()
        # self.set_state(AssistantState.LISTENING)

    def stop_recording(self):
        """
        停止录音
        """

        if self.input_stream:
            self.input_stream.close()
            self.input_stream = None
            logger.info("音频输入流已关闭")

        if not self.recording_active:
            logger.info("录音线程已停止")
            return
        self.recording_active = False

        if self.recorder_thread and self.recorder_thread.is_alive():
            self.recorder_thread.join()
            logger.info("录音线程正在停止...")
        self.recorder_thread = None

        # self.set_state(AssistantState.IDLE)

    def load_config_and_initialize(self):

        # ----------- 读取配置文件 -----------
        # try:
        #     with open(self.config_yaml, "r", encoding="utf-8") as f:
        #         self.configs = yaml.safe_load(f)
        #         logger.info(f"配置文件内容:\n{self.configs}")
        # except Exception as e:
        #     logger.error(f"读取配置文件失败: {e}")
        #     # raise e
        self.configs = load_config()
        logger.debug("当前配置:\n%s", yaml.dump(self.configs, allow_unicode=True))

        # ----------- 初始化ASR、LLM、TTS客户端 -----------
        ############ ASR 服务器选择和客户端初始化 ##########
        asr_server_type = self.configs.get("asr_server", ["asr_local"])[0]
        logger.info(f"选择的 ASR 服务器类型: {asr_server_type}")
        asr_cfg = self.configs.get(asr_server_type, {})

        self.asr_client = ASRClient(
            host=asr_cfg.get("host", "192.168.10.101"),
            port=asr_cfg.get("port", 2002),
            timeout_sec=asr_cfg.get("timeout_sec", 30),
            use_websocket=asr_cfg.get("use_websocket", False),
        )

        ########### LLM 服务器选择和客户端初始化 ##########
        llm_cfg = self.configs.get("llm", {})
        self.llm_client = LLMAgent(
            host=llm_cfg.get("host", "192.168.50.125"),
            port=llm_cfg.get("port", 8000),
            temperature=llm_cfg.get("temperature", 0.3),
            max_tokens=llm_cfg.get("max_tokens", 512),
            enable_thinking=llm_cfg.get("enable_thinking", False),
            # dynamic_tool_middlewares=self.dynamic_tool_middlewares,
            dynamic_middleware_list=self.dynamic_middleware_list,
            timeout=llm_cfg.get("timeout_sec", 10),
            system_prompt=llm_cfg.get("system_prompt", ""),
        )
        system_prompt = llm_cfg.get("system_prompt", "")
        if system_prompt:
            self.llm_client.add_system_prompt(system_prompt)
        self.enable_stream = llm_cfg.get("enable_stream", False)

        ########### TTS 服务器选择和客户端初始化 ##########
        tts_server_type = self.configs.get("tts_server", ["tts_local"])[0]
        logger.info(f"选择的 TTS 服务器类型: {tts_server_type}")
        tts_cfg = self.configs.get(tts_server_type, {})

        if tts_server_type == "tts_remote":
            self.tts_client = RealtimeTTSPlayer(
                host=tts_cfg.get("host", "192.168.50.220"),
                port=tts_cfg.get("port", 50000),
            )
            self.tts_client.change_preset(
                tts_cfg.get("voice_type", "default")
            )  # "default"(女性活泼), "zh"(男性非标准) , "hard_zh"(男性业余), "longshu_zh"(男性专业), "longwan_zh"（女性专业）

        elif tts_server_type == "tts_local":
            self.tts_client = TTSClient(
                host=tts_cfg.get("host", "192.168.10.101"),
                port=tts_cfg.get("port", 50000),
                timeout_sec=tts_cfg.get("timeout_sec", 30),
                speaker_id=tts_cfg.get("speaker_id", 0),
                speed=tts_cfg.get("speed", 1.0),
                use_websocket=tts_cfg.get("use_websocket", True),
                playback_start_delay_sec=tts_cfg.get("playback_start_delay_sec", 0.0),
            )
        else:
            logger.error(f"未知的 TTS 服务器类型: {tts_server_type}")
            raise ValueError(f"未知的 TTS 服务器类型: {tts_server_type}")
        # ------------------------------------------------

        ############## 音频采集参数 ##############
        audio_cfg = self.configs.get("Audio", {})

        self.audio_rate = audio_cfg.get("rate", 16000)
        self.audio_channels = audio_cfg.get("channels", 1)
        self.chunk_duration_ms = audio_cfg.get("chunk_duration_ms", 30)
        self.audio_file_count = 0
        self.max_file_count = audio_cfg.get("max_file_count", 50)
        # self.chunk_size = audio_cfg.get("chunk_size", 1024)

        # 帧 = 采样率 * 持续时间(秒) （给 sounddevice 用）
        self.chunk_frames = int(self.audio_rate * self.chunk_duration_ms / 1000)
        # 每帧2字节（16位采样）,字节数（给 PCM / VAD / AEC 用）
        self.chunk_bytes = self.chunk_frames * 2
        valid_frame_bytes = {
            int(self.audio_rate * ms / 1000) * 2 for ms in (10, 20, 30)
        }
        if self.chunk_bytes not in valid_frame_bytes:
            logger.warning("chunk_duration_ms 设置不合适，已调整为 20 ms 对应的字节数")
            self.chunk_duration_ms = 20
            self.chunk_frames = int(self.audio_rate * self.chunk_duration_ms / 1000)
            self.chunk_bytes = self.chunk_frames * 2
        #########################################

        ############## VAD 参数 ##############
        vad_cfg = self.configs.get("VAD", {})

        self.vad_mode = vad_cfg.get("mode", 3)
        self.output_dir = (
            Path(__file__).resolve().parent.parent / vad_cfg.get("output_dir", "output")
        ).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.no_speech_threshold = vad_cfg.get("no_speech_threshold", 0.5)
        self.decibel_threshold = vad_cfg.get("decibel_threshold", -40)
        self.min_recording_duration = vad_cfg.get("min_recording_duration", 1.0)
        self.max_recording_duration = vad_cfg.get("max_recording_duration", 10.0)
        self.pause_duration = vad_cfg.get("pause_duration", 1.5)
        self.vad = webrtcvad.Vad(self.vad_mode)
        ######################################

        ############## 唤醒词参数 ##############
        kws_cfg = self.configs.get("KWS", {})

        self.set_kws = kws_cfg.get("wake_word", "你好小特")
        self.set_kws_pinyin = self.__extract_chinese_and_convert_to_pinyin(self.set_kws)
        self.kws_fuzzy_similarity_threshold = kws_cfg.get(
            "fuzzy_similarity_threshold", 0.78
        )
        logger.info(f"设置的唤醒词: {self.set_kws}, 拼音: {self.set_kws_pinyin}")

        self.flag_kws_used = kws_cfg.get("enable", True)
        if not self.flag_kws_used:
            logger.info("未启用唤醒词激活功能")
        self.flag_kws = 0  # 唤醒词检测标志
        self.failed_enable_kws_count = 0  # 连续未检测到唤醒词计数
        self.failed_kws_counts = kws_cfg.get(
            "failed_kws_counts", 2
        )  # 连续未检测到唤醒词次数达到此值时，推送提示语音
        self.failed_kws_threshold = kws_cfg.get(
            "failed_kws_threshold", 30
        )  # 连续未检测到唤醒词次数 达到 failed_kws_counts 后，推送提示语音的时间间隔 (秒)
        self.reactive_kws_threshold = kws_cfg.get(
            "reactive_kws_threshold", 100
        )  # 重置 需要唤醒词检测 激活 LLM 时间间隔 (秒)
        self.last_failed_kws_time = time.time()
        #######################################

        ################ 其他状态变量 ##############
        self.recording_active = False  # 当前是否处于录音状态
        self.segments_to_save = []  # 待保存的音频片段
        self.saved_intervals = []  # 已保存的时间区间
        self.last_active_time = time.time()  # 上次检测到有效语音的时间
        self.last_vad_end_time = time.time()  # 上次保存的 VAD 有效段结束时间
        self.last_llm_time = time.time()  # 上次与 LLM 交互的时间
        self.last_tts_time = time.time()  # 上次 TTS 播放的时间
        self.last_interface_time = time.time()  # 上次与任何模块交互的时间

        self.enable_interrupt_tts = self.configs.get("enable_interrupt_tts", False)
        self.enable_replace_special_characters = self.configs.get(
            "enable_replace_special_characters", False
        )
        self.word_map = SPECIAL_WORD_MAP

        self.state = AssistantState.IDLE
        self.state_lock = threading.Lock()

        self.asr_client_state = (
            ASRClientState.ACTIVE
            if self.configs.get("asr_enable", False)
            else ASRClientState.IDLE
        )  # 根据配置决定 ASR Client 是否默认激活
        self.llm_agent_state = (
            LLMAgentState.ACTIVE
            if self.configs.get("llm_enable", False)
            else LLMAgentState.IDLE
        )  # 根据配置决定 LLM Agent 是否默认激活
        self.tts_client_state = (
            TTSClientState.ACTIVE
            if self.configs.get("tts_enable", False)
            else TTSClientState.IDLE
        )  # 根据配置决定 TTS 是否默认激活

        # ====== 能量统计 ======
        self.energy_instability_check = self.configs.get(
            "energy_instability_check", True
        )
        # self.energy_window_duration = self.configs.get("energy_window_duration", 5.0)
        self.max_energy_frames = self.configs.get("energy_frames", 50)  # 50 x 0.1s = 5s
        self.energy_instability_threshold = self.configs.get(
            "energy_instability_threshold", 2.0
        )
        self.energy_window = []  # 每个分析块的 RMS

    def __compute_energy_instability(self):
        """
        计算能量不稳定性指标（标准差 / 均值）
        """
        if len(self.energy_window) < 5:
            return 0.0
        mean = np.mean(self.energy_window)
        std = np.std(self.energy_window)
        # logger.info(f"能量均值: {mean:.6f}, 标准差: {std:.6f}")
        return std / (mean + 1e-6)

    def __reset_segment_state(self):
        """重置音频片段状态。"""
        self.segments_to_save.clear()
        self.energy_window.clear()

    def __extract_chinese_and_convert_to_pinyin(self, input_string):
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

    def __is_kws_pinyin_match(self, detected_pinyin: str) -> bool:
        """判断待检测拼音是否与唤醒词拼音近似匹配。"""
        if not detected_pinyin or not self.set_kws_pinyin:
            return False

        detected_tokens = detected_pinyin.split()
        target_tokens = self.set_kws_pinyin.split()

        if not detected_tokens or not target_tokens:
            return False

        # 先走快速路径：包含完整目标拼音，直接判定为命中。
        if self.set_kws_pinyin in detected_pinyin:
            logger.info("唤醒词拼音包含精确匹配")
            return True

        target_joined = "".join(target_tokens)
        target_len = len(target_tokens)

        # 使用滑窗计算拼音相似度，允许长度有 1 个音节误差。
        candidate_lens = {target_len}
        if target_len > 1:
            candidate_lens.add(target_len - 1)
            candidate_lens.add(target_len + 1)

        best_score = 0.0
        best_window = ""

        for win_len in sorted(candidate_lens):
            if win_len <= 0:
                continue

            if len(detected_tokens) < win_len:
                window_tokens_list = [detected_tokens]
            else:
                window_tokens_list = [
                    detected_tokens[i : i + win_len]
                    for i in range(0, len(detected_tokens) - win_len + 1)
                ]

            for window_tokens in window_tokens_list:
                window_joined = "".join(window_tokens)
                score = SequenceMatcher(None, window_joined, target_joined).ratio()

                if score > best_score:
                    best_score = score
                    best_window = " ".join(window_tokens)

                if score >= self.kws_fuzzy_similarity_threshold:
                    logger.info(
                        "唤醒词近似匹配成功, 窗口拼音: '%s', 相似度: %.3f, 阈值: %.3f",
                        " ".join(window_tokens),
                        score,
                        self.kws_fuzzy_similarity_threshold,
                    )
                    return True

        logger.info(
            "唤醒词近似匹配未命中, 最佳窗口: '%s', 最佳相似度: %.3f, 阈值: %.3f",
            best_window,
            best_score,
            self.kws_fuzzy_similarity_threshold,
        )
        return False

    # 统计字符串中的汉字数量
    def __count_chinese_characters(self, input_string):
        """
        统计字符串中的汉字数量。

        :param input_string: 原始字符串
        :return: 汉字数量
        """
        chinese_characters = re.findall(r"[\u4e00-\u9fa5]", input_string)
        return len(chinese_characters)

    # 替换字符串中的特殊字符为智己
    def __replace_special_characters(self, input_string):
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

    # 去除字符串 末尾 的 <INTENT> </INTENT> 标签
    def __remove_intent_tags(self, input_string):
        """
        去除字符串末尾的 <INTENT> </INTENT> 标签。

        :param input_string: 原始字符串
        :return: 去除标签后的字符串
        """
        if not input_string:
            return input_string

        # 使用正则表达式去除末尾的 <INTENT>...</INTENT> 标签
        cleaned_string = re.sub(
            r"<INTENT>.*?</INTENT>$", "", input_string, flags=re.DOTALL
        )

        return cleaned_string.strip()

    def __check_vad_activity(self, audio_bytes: bytes) -> bool:
        """
        audio_bytes: int16 PCM, mono
        """
        # frame_ms = 20  # webrtcvad 推荐
        # bytes_per_sample = 2
        # frame_size = int(self.audio_rate * frame_ms / 1000) * bytes_per_sample

        if len(audio_bytes) < self.chunk_bytes:
            return False

        for i in range(0, len(audio_bytes) - self.chunk_bytes + 1, self.chunk_bytes):
            frame = audio_bytes[i : i + self.chunk_bytes]
            if self.vad.is_speech(frame, self.audio_rate):
                return True

        return False

    def __calculate_decibel(self, audio_np: np.ndarray) -> float:
        """计算音频分贝值，避免对零取对数。"""
        if audio_np.size == 0:
            return float("-inf")
        rms = np.sqrt(np.mean(np.square(audio_np)))
        return 20 * np.log10(max(rms, 1e-10))

    def __float_to_pcm16(self, audio_np: np.ndarray) -> bytes:
        """将 float32 音频转换为 PCM16 字节流。"""
        # audio_clipped = np.clip(audio_np, -1.0, 1.0)
        # return (audio_clipped * 32767).astype(np.int16).tobytes()

        # audio_np: (N, 1) or (N,)
        if audio_np.ndim == 2:
            audio_np = audio_np[:, 0]  # ✅ 取 mono

        audio_clipped = np.clip(audio_np, -1.0, 1.0)
        return (audio_clipped * 32767).astype(np.int16).tobytes()

    def __finalize_pending_segments(self, timestamp: float) -> None:
        """在长时间静音后触发音频保存。"""

        energy_instability = self.__compute_energy_instability()
        # logger.info(f"能量不稳定性指标(标准差/均值): {energy_instability:.6f}")

        # ====== 判定阈值 ======
        if (
            energy_instability > self.energy_instability_threshold
            and self.energy_instability_check
        ):
            logger.info(f"当前指标(标准差/均值): {energy_instability:.6f}")
            logger.info(f"阈值(标准差/均值): {self.energy_instability_threshold:.6f}")
            logger.warning("疑似多人说话，音频能量不稳定，放弃保存音频")
            self.__reset_segment_state()
            return

        # 能量稳定，保存音频
        if (
            self.segments_to_save
            and self.segments_to_save[-1][1] > self.last_vad_end_time
        ):
            self.__save_audio_only()
            self.last_active_time = timestamp

        # 重置状态
        self.__reset_segment_state()

    def __update_llm_text(self, llm_text):
        """更新 LLM 文本，并推送到队列。"""

        # 更新单个响应数据对象，并推送到单独的 LLM 文本队列
        self.__push_queue(self.llm_text_queue, llm_text)

        # 更新综合响应数据对象，并推送到综合队列
        self.response_data.llm_text = llm_text
        self.__push_queue(self.response_queue, asdict(self.response_data))
        self.response_data.clear()

    ################## 保存音频的模块 ##################
    def __save_audio_only(self):
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
        if current_time - self.last_vad_end_time < self.pause_duration:
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
            logger.warning("当前片段与之前片段重叠，跳过保存")
            self.segments_to_save.clear()
            return None

        # 检查录音时长是否满足要求
        recording_duration = end_time - start_time
        # print(f"录音时长: {recording_duration:.2f} 秒")
        logger.info(f"录音时长: {recording_duration:.2f} 秒")
        if recording_duration < self.min_recording_duration:
            logger.warning("录音时长过短，跳过保存")
            self.segments_to_save.clear()
            return None
        if recording_duration > self.max_recording_duration:
            logger.warning("录音时长过长，跳过保存")
            self.segments_to_save.clear()
            return None

        # ===============================
        # 1. 生成输出路径 ,循环保存最近 self.max_file_count 条音频
        # ===============================
        self.audio_file_count = (self.audio_file_count % self.max_file_count) + 1
        audio_output_path = self.output_dir / f"audio_{self.audio_file_count}.wav"

        # ===============================
        # 3. 拼接音频
        # ===============================
        audio_frames = [seg[0] for seg in self.segments_to_save]

        # 直接将 PCM16 字节流传给 ASR 识别
        self.Inference(audio_frames=audio_frames)

        # ===============================
        # 4. 保存 WAV
        # ===============================
        with wave.open(str(audio_output_path), "wb") as wf:
            wf.setnchannels(self.audio_channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.audio_rate)
            wf.writeframes(b"".join(audio_frames))
        logger.info(f"保存音频文件: {audio_output_path}")

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
        # self.Inference(audio_frames=audio_frames, audio_path=str(audio_output_path))

        return audio_output_path

    #################### 音频录制线程 ###################
    def __audio_recorder_thread(self):

        audio_buffer = []
        frames_collected = 0
        self.last_active_time = time.time()

        # 每收集 ≥ 200ms（或 ≥ 一个 chunk_frames）的音频，就做一次分析
        analysis_interval_frames = max(
            1, max(self.chunk_frames, int(0.20 * self.audio_rate))
        )

        logger.info("音频录制已开始（sounddevice）")
        logger.info(f"单次回调音频帧数: {self.chunk_frames}")
        logger.info(f"单次回调音频时长: {self.chunk_frames / self.audio_rate:.3f} 秒")
        logger.info(f"分析间隔音频帧数: {analysis_interval_frames}")
        logger.info(
            f"分析间隔时长: {analysis_interval_frames / self.audio_rate:.3f} 秒"
        )

        def reset_buffer():
            nonlocal audio_buffer, frames_collected
            audio_buffer.clear()
            frames_collected = 0

        def audio_callback(indata, frames, time_info, status):
            nonlocal frames_collected

            if not self.recording_active:
                raise sd.CallbackStop()

            now = time.time()

            if self.tts_client.is_active():
                # tts 播放中，代表模型正在说话
                # 更新 last_interface_time
                self.last_interface_time = now

            # indata: float32 [-1.0, 1.0]
            audio_buffer.append(indata.copy())
            frames_collected += frames

            # 累积足够的音频进行分析
            if frames_collected >= analysis_interval_frames:
                # 合并音频块
                audio_np = np.concatenate(audio_buffer, axis=0)
                # 转为 PCM16 字节流
                audio_bytes = self.__float_to_pcm16(audio_np)
                # 重置缓冲区
                reset_buffer()

                # === NEW: 计算 RMS 能量 ===
                rms = np.sqrt(np.mean(audio_np**2) + 1e-8)
                # logger.info(f"RMS 能量: {rms:.6f}")
                self.energy_window.append(rms)
                if len(self.energy_window) > self.max_energy_frames:
                    # logger.info("能量窗口已满，移除最早的能量值")
                    self.energy_window.pop(0)

                # 计算分贝
                decibel = self.__calculate_decibel(audio_np)

                ## 如果分贝低于阈值
                if decibel < self.decibel_threshold:
                    ### 静音时间超过 no_speech_threshold and 有待保存音频段 则保存音频段
                    if (
                        now - self.last_active_time > self.no_speech_threshold
                        and self.segments_to_save
                    ):
                        logger.info("静音时间超过阈值，保存音频段")
                        ### 保存末尾的音频段
                        self.segments_to_save.append((audio_bytes, now))
                        self.__finalize_pending_segments(now)

                    ### 否则，继续等待, 保存静音段，防止断句不准确
                    else:
                        if self.segments_to_save:
                            logger.info("静音时间未超过阈值，继续等待，保存静音段")
                            self.segments_to_save.append((audio_bytes, now))

                ## 分贝高于阈值，继续处理
                else:
                    ### 如果 检测 VAD 活动，则保存音频段
                    if self.__check_vad_activity(audio_bytes):
                        logger.info("检测到语音活动，分贝: {:.2f} dB".format(decibel))
                        self.last_active_time = now
                        self.segments_to_save.append((audio_bytes, now))

                ## 如果处于录音段内（已有数据） and 录音时长超过最大值，则保存音频段
                if self.segments_to_save and (
                    self.segments_to_save[-1][1] - self.segments_to_save[0][1]
                    > (self.max_recording_duration - 0.2)
                ):
                    logger.info(
                        f"录音时长超过最大值{self.max_recording_duration}秒，保存音频段"
                    )
                    # self.segments_to_save.append((audio_bytes, now))
                    self.__finalize_pending_segments(now)

        # with self.input_stream =sd.InputStream(
        #     samplerate=self.audio_rate,
        #     channels=self.audio_channels,
        #     dtype="float32",
        #     blocksize=self.chunk_frames,
        #     callback=audio_callback,
        # ):
        with sd.InputStream(
            samplerate=self.audio_rate,
            channels=self.audio_channels,
            dtype="float32",
            blocksize=self.chunk_frames,
            callback=audio_callback,
        ) as self.input_stream:
            logger.info("音频输入流已打开，等待录音...")
            while self.recording_active:
                time.sleep(1)
        # logger.info(
        #     "sd.default.device info: {}".format(sd.query_devices(sd.default.device))
        # )
        # while self.recording_active:
        #     time.sleep(1)

        # print("音频录制已停止")
        # logger.info("音频录制已停止")

    ############# 功能模块激活状态管理 #############
    def activate(self):
        """
        激活助手，进入 ACTIVE 状态
        """
        self.set_state(AssistantState.ACTIVE)

    def idle(self):
        """
        进入空闲状态
        """
        self.set_state(AssistantState.IDLE)

    def activate_asr_client(self):
        """
        激活 ASR Client，进入 ACTIVE 状态
        """
        self.asr_client_state = ASRClientState.ACTIVE

    def deactivate_asr_client(self):
        """
        使 ASR Client 进入空闲状态
        """
        self.asr_client_state = ASRClientState.IDLE

    def activate_llm_agent(self):
        """
        激活 LLM Agent，进入 ACTIVE 状态
        """
        self.llm_agent_state = LLMAgentState.ACTIVE

    def deactivate_llm_agent(self):
        """
        使 LLM Agent 进入空闲状态
        """
        self.llm_agent_state = LLMAgentState.IDLE

    def activate_tts_client(self):
        """
        激活 TTS Client，进入 ACTIVE 状态
        """
        self.tts_client_state = TTSClientState.ACTIVE

    def deactivate_tts_client(self):
        """
        使 TTS Client 进入空闲状态
        """
        self.tts_client_state = TTSClientState.IDLE

    ###############################################

    ################# 业务功能接口 ##################
    def set_current_user_id(self, user_id: str | None):
        """
        设置当前用户 ID，LLM 推理时会携带该 ID 以支持个性化对话
        """
        self.current_user_id = (
            user_id.strip() if isinstance(user_id, str) and user_id.strip() else None
        )
        logger.debug(f"当前用户 ID 已设置为: {self.current_user_id}")

    def generate_wav(self, text, output_path) -> bool:
        """
        负责调用 TTS 完成文本转语音，保存音频文件
        """
        logger.info("请求 TTS 生成语音文件中...")
        time_now = time.time()
        try:
            tts_result = self.tts_client.generate_wav(text, output_path)
            elapsed_time = time.time() - time_now
            logger.info(f"TTS 生成语音文件耗时: {elapsed_time:.2f} 秒")
            return tts_result
        except Exception as e:
            logger.error(f"TTS 生成语音文件失败: {e}")
            return False

    def play_audio(self, audio_path):
        """
        负责调用 TTS 播放音频文件
        """
        logger.info(f"开始播放音频文件: {audio_path}")
        try:
            self.tts_client.play_audio(audio_path, block=False)
            return True
        except Exception:
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
            logger.error(f"中断后台播放失败: {e}")
            return False

    def check_tts_status(self) -> bool:
        """
        检查 TTS 模块状态并根据当前状态决定是否继续播放

        Returns:
            bool: 如果可以继续播放返回 True，否则返回 False
        """
        # -------- 检查 TTS 模块状态 ----------
        if self.tts_client_state == TTSClientState.IDLE:
            logger.warning("TTS 模块未激活，跳过TTS播放")
            self.last_interface_time = time.time()
            time.sleep(0.1)
            return False
        # -------- 检查 TTS 播放状态 如果正在播放且未启用打断功能，则跳过播放 -----------
        if self.tts_client.is_active() and not self.enable_interrupt_tts:
            logger.warning("语音播放中，未启用打断，跳过TTS播放")
            self.last_interface_time = time.time()
            return False
        # --------- 检查 TTS 播放状态，如果正在播放且启用了打断功能，则中断当前播放 -----------
        if self.tts_client.is_active() and self.enable_interrupt_tts:
            logger.info("语音播放中，启用了打断功能，准备中断播放")
            self.tts_client.interrupt()
            time.sleep(0.1)
            return True

        return True

    def check_tts_active(self) -> bool:
        """
        负责检查 TTS 播放状态
        """
        try:
            is_active = self.tts_client.is_active()
            return is_active
        except Exception:
            return False

    def asr_infer(self, audio_path: str | None = None, audio_frames=None):
        """
        负责调用 ASR 完成语音识别，支持音频文件路径或 PCM16 字节流输入
         - 如果同时提供了 audio_frames 和 audio_path，则优先使用 audio_frames 进行识别，以提高实时性和效率
         - 如果 audio_frames 为空且提供了 audio_path，则使用音频文件进行识别
         - 如果两者都未提供，则返回空字符串
         - 返回识别文本，失败时返回空字符串
         - 注意：如果同时提供了 audio_frames 和 audio_path，且 audio_frames 识别结果为空，则不会回退到 audio_path 进行识别，以保证流程的确定性和效率。
         - 如果需要在帧识别失败时回退到文件识别，可以在外部调用时先调用一次 asr_infer(audio_frames=...)，如果结果为空再调用一次 asr_infer(audio_path=...)。
        """
        logger.info("ASR 识别中...")
        time_now = time.time()
        try:
            if audio_frames is not None:
                asr_text = self.asr_client.recognize_frames(
                    audio_frames,
                    sample_rate=self.audio_rate,
                    channels=self.audio_channels,
                ).strip()

                # # 帧识别失败时回退到文件识别，保证兼容旧流程。
                # if not asr_text and audio_path:
                #     logger.warning("audio_frames 识别为空，回退到音频文件识别")
                #     asr_text = self.asr_client.recognize(audio_path).strip()
            elif audio_path:
                asr_text = self.asr_client.recognize(audio_path).strip()
            else:
                logger.warning("未提供 audio_frames 或 audio_path，跳过 ASR 识别")
                return ""

            logger.info(
                f"ASR 识别结果: [{asr_text}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
            )
            return asr_text
        except Exception as e:
            logger.error(f"ASR 识别失败: {e}")
            return ""

    def llm_infer(self, input_text: str, user_id: str | None = None):
        """
        接收输入文本（可选携带用户 ID），调用 LLM 完成推理，返回生成的文本响应
        Parameters:
            input_text (str): 输入文本
            user_id (str | None): 可选的用户 ID，用于记忆相同用户的对话上下文，如果为 None 直接与LLM 进行对话
        Returns:
            str: LLM 生成的文本响应，失败时返回空字符串
        """
        logger.info("LLM 推理中...")
        effective_user_id = user_id if user_id is not None else self.current_user_id
        llm_text = ""
        time_now = time.time()
        try:
            llm_text = self.llm_client.chat_response(input_text, effective_user_id)
            if not llm_text:
                logger.warning("LLM 返回空响应")
                llm_text = ""
            logger.info(
                f"LLM 推理结果: [{llm_text}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
            )

            self.last_interface_time = time.time()
            return llm_text

        except Exception as e:
            logger.error(f"LLM 对话失败: {e}")
            self.last_interface_time = time.time()

            return ""

    def llm_stream_infer(
        self, input_text: str, user_id: str | None = None
    ) -> Generator[tuple[str, int], None, None]:
        """
        接收输入文本（可选携带用户 ID），调用 LLM 完成流式推理，逐步返回生成的文本响应片段和对应的索引
        Parameters:
            input_text (str): 输入文本
            user_id (str | None): 可选的用户 ID，用于记忆相同用户的对话上下文，如果为 None 直接与LLM 进行对话
        Returns:
            Generator[tuple[str, int], None, None]: 生成器，逐步返回LLM 生成的文本响应片段和对应的索引，失败时返回空字符串和当前索引
        """
        logger.info("LLM 流式推理中...")
        effective_user_id = user_id if user_id is not None else self.current_user_id
        time_now = time.time()
        llm_response_chunks = []
        index = 0
        try:
            for llm_response_chunk, index in self.llm_client.chat_response_stream(
                input_text, effective_user_id
            ):
                logger.info(
                    f"LLM 流式推理输出 [{index}]: [{llm_response_chunk}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
                )
                llm_response_chunks.append(llm_response_chunk)
                time_now = time.time()

                yield llm_response_chunk, index

            self.last_interface_time = time.time()

        except Exception as e:
            logger.error(f"LLM 流式对话失败: {e}")
            yield "", index

    def tts_infer(self, llm_response):
        """
        负责调用 TTS 完成语音合成和播放
        """

        logger.info("TTS 合成和播放中...")
        time_now = time.time()
        try:
            self.tts_client.speak(llm_response.strip())

            # while not self.tts_client.is_active():
            #     if time.time() - time_now > 5.0:
            #         logger.error("TTS 播放超时 或者 TTS 播放音频太短")
            #         return False
            #     time.sleep(0.01)

            # elapsed_time = 0
            # if isinstance(self.tts_client, RealtimeTTSPlayer):
            #     elapsed_time = time.time() - time_now
            # else:
            #     elapsed_time = (
            #         time.time()
            #         - time_now
            #         - self.tts_client.get_playback_start_delay_sec()
            #     )

            # logger.info(f"TTS 合成并播放音频延迟: {elapsed_time:.2f} 秒")
            return self.tts_cost_time(time_now)

            # return True
        except Exception as e:
            logger.error(f"TTS 播放失败: {e}")
            return False

    def tts_stream_infer(self, llm_response_chunk, index):
        """
        负责调用 TTS 完成流式语音片段的合成和推送（非阻塞）
        """
        logger.info(f"TTS 推送流式片段 [{index}]...")
        time_now = time.time()
        try:
            # 假设 tts_client.speak 为异步或基于缓冲队列的非阻塞调用
            self.tts_client.speak(llm_response_chunk.strip(), interrupt=False)
            if index == 0:
                threading.Thread(target=self.tts_cost_time, args=(time_now,)).start()
            return True
        except Exception as e:
            logger.error(f"TTS 推送流式片段 [{index}] 失败: {e}")
            return False

    def tts_cost_time(self, start_time):
        """
        计算 TTS 合成并播放音频的延迟时间
        """
        while not self.tts_client.is_active():
            if time.time() - start_time > 5.0:
                logger.error("TTS 播放超时 或者 TTS 播放音频太短")
                return False
            time.sleep(0.01)

        elapsed_time = 0
        if isinstance(self.tts_client, RealtimeTTSPlayer):
            elapsed_time = time.time() - start_time
        else:
            elapsed_time = (
                time.time()
                - start_time
                - self.tts_client.get_playback_start_delay_sec()
            )
        logger.info(f"TTS 合成并播放音频延迟: {elapsed_time:.2f} 秒")
        return True

    def kws_infer(self, asr_text):
        """
        负责唤醒词检测逻辑
        """

        # 提取汉字并转换为拼音
        pinyin_text = self.__extract_chinese_and_convert_to_pinyin(asr_text)
        logger.info(f"转换为拼音: {pinyin_text}")
        wake_word_matched = self.__is_kws_pinyin_match(pinyin_text)

        if wake_word_matched and self.tts_client.is_active():
            logger.warning("检测到唤醒词， TTS 播放中，打断播放以避免语音叠加")

            # self.flag_kws = 1
            self.llm_agent_state = LLMAgentState.ACTIVE

            self.tts_client.interrupt()

            time.sleep(0.1)

            self.last_interface_time = time.time()
            return True

        # 判断是否需要重置唤醒词状态
        if time.time() - self.last_interface_time > self.reactive_kws_threshold:
            # self.flag_kws = 0
            # if self.llm_agent_state == LLMAgentState.ACTIVE:
            self.llm_agent_state = LLMAgentState.IDLE

            logger.info("长时间未与 LLM 交互，重置 LLM 模块为 IDLE 状态")

        # 判断是否启用唤醒词检测
        if self.flag_kws_used:
            # logger.info("需要唤醒词激活")
            if self.llm_agent_state == LLMAgentState.ACTIVE:
                logger.info("LLM 模块已处于 ACTIVE 状态，无需检测唤醒词")
                self.last_interface_time = time.time()
                return True

            if wake_word_matched:
                # self.flag_kws = 1
                self.llm_agent_state = LLMAgentState.ACTIVE

                self.failed_enable_kws_count = 0

                self.last_interface_time = time.time()

                logger.info("检测到唤醒词，激活 LLM 模块")
                return True
            else:
                # self.flag_kws = 0
                self.llm_agent_state = LLMAgentState.IDLE

                self.failed_enable_kws_count += 1

                logger.info(
                    "未检测到唤醒词，失败次数: {}".format(self.failed_enable_kws_count)
                )

                # 如果连续多次未检测到唤醒词，且距离上次提示已超过一定时间，则推送提示语音
                if (
                    self.failed_enable_kws_count >= self.failed_kws_counts
                    and time.time() - self.last_failed_kws_time
                    > self.failed_kws_threshold
                ):
                    self.__update_llm_text(f"你可以说出:{self.set_kws} 来唤醒我!")

                    # 只有在 ACTIVE 状态下才播放提示语音
                    if self.tts_client_state == TTSClientState.ACTIVE:
                        logger.info("TTS处于 ACTIVE 状态，准备播放提示语音")
                        if self.tts_client.is_active() and self.enable_interrupt_tts:
                            logger.info("TTS 播放中，启用了打断功能，准备中断播放")
                            self.tts_client.interrupt()
                            time.sleep(0.1)

                        self.tts_infer(f"你可以说出:{self.set_kws} 来唤醒我!")

                    self.failed_enable_kws_count = 0
                    self.last_failed_kws_time = time.time()

                else:
                    self.__update_llm_text("")

                self.last_interface_time = time.time()
                return False

        else:
            self.llm_agent_state = LLMAgentState.ACTIVE
            self.last_interface_time = time.time()
            logger.info("未启用唤醒词激活功能")
            return True

    ##########################################################

    ####################### 核心交互流程 #######################
    def Inference(
        self,
        audio_frames=None,
        audio_path: str | None = None,
        input_text: str | None = None,
        user_id: str | None = None,
    ):
        """
        负责调用 ASR、LLM、TTS 完成一次完整的交互
        Parameters:
            - audio_frames: 可选的 PCM16 字节流输入，用于 ASR 识别，优先级高于 audio_path
            - audio_path: 可选的音频文件路径输入，用于 ASR 识别，当 audio_frames 为空时使用
            - input_text: 可选的文本输入，用于 ASR 识别，当 audio_frames 和 audio_path 都为空时使用
            - user_id: 可选的用户 ID，用于支持个性化对话，如果为 None 则使用当前默认用户 ID
        """
        logger.info("\n\n开始一次完整的交互流程...")
        effective_user_id = user_id if user_id is not None else self.current_user_id

        # 响应数据，包括 asr_text 和 llm_text
        # self.response_json = {}
        self.response_data.clear()

        self.asr_text = ""
        # -------- 检查 asr client 状态 ----------
        if self.asr_client_state == ASRClientState.IDLE:
            self.last_interface_time = time.time()

            logger.warning("ASR 模块未激活，跳过本次交互")
            return

        # -------- asr 识别 -----------
        if audio_frames is not None:
            self.asr_text = self.asr_infer(audio_frames=audio_frames)
        elif audio_path:
            self.asr_text = self.asr_infer(audio_path=audio_path)
        elif input_text:
            self.asr_text = input_text
        else:
            logger.warning("未提供音频路径或输入文本，跳过本次交互")
            self.last_interface_time = time.time()
            return
        # self.asr_text = "你好，小特"  # 测试代码，固定返回唤醒词
        # ## response_json 更新 asr_text
        # response_json["asr_text"] = self.asr_text
        if not self.asr_text:
            logger.warning("ASR 未识别到有效文本，跳过本次交互")
            self.last_interface_time = time.time()
            # self.set_state(AssistantState.LISTENING)
            return

        # -------- 判断asr_text中汉字数量，过少则忽略 ----------
        chinese_char_count = self.__count_chinese_characters(self.asr_text)
        if chinese_char_count < 2:
            logger.warning("ASR 识别文本中汉字数量过少，跳过本次交互")
            self.last_interface_time = time.time()
            return

        # ------- 替换特殊词汇 -------
        if self.enable_replace_special_characters:
            logger.info(f"替换前 ASR 文本: {self.asr_text}")
            self.asr_text = self.__replace_special_characters(self.asr_text)
            logger.info(f"替换后 ASR 文本: {self.asr_text}")

        ## 更新asr_text队列
        self.__push_queue(self.asr_text_queue, self.asr_text)
        ##  更新 asr_text
        # self.response_json["asr_text"] = self.asr_text
        self.response_data.asr_text = self.asr_text

        # ----------- 唤醒词检测 -----------
        if self.flag_kws_used:
            if not self.kws_infer(self.asr_text):
                # self.set_state(AssistantState.LISTENING)

                self.last_interface_time = time.time()
                return

        self.llm_text = ""
        # -------- 检查 LLM Agent 状态 ----------
        if self.llm_agent_state == LLMAgentState.IDLE:
            self.last_interface_time = time.time()

            logger.warning("LLM 模块未激活，跳过本次交互")

            self.__update_llm_text(self.llm_text)

            return

        if self.enable_stream:
            # -------- llm tts stream --------------
            # -------- 先确认当前阶段是否允许播放 TTS，避免分段打断自己 ---------
            tts_can_play = self.check_tts_status()
            for chunk, index in self.llm_stream_infer(
                self.asr_text, user_id=effective_user_id
            ):
                self.llm_text += chunk
                if chunk.strip() and tts_can_play:
                    self.tts_stream_infer(
                        self.__remove_intent_tags(chunk.strip()), index
                    )
            self.__update_llm_text(self.llm_text)
        else:
            # -------- llm 推理 -----------
            self.llm_text = self.llm_infer(self.asr_text, user_id=effective_user_id)
            self.__update_llm_text(self.llm_text)

            # -------- tts 播放 -----------
            ## -------- 检查 TTS 逻辑状态 ----------
            if not self.check_tts_status():
                return
            self.tts_infer(self.__remove_intent_tags(self.llm_text))

        logger.info("本次交互完成，等待下一次录音")


if __name__ == "__main__":
    # 获取当前文件所在目录
    current_dir = Path(__file__).resolve().parent
    logger.info(f"当前文件目录: {current_dir}")
    config_yaml_path = (current_dir / "../config/config.yaml").resolve()
    logger.info(f"配置文件路径: {config_yaml_path}")

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
