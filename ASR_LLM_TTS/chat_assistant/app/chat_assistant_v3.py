import os
import re
import wave
from difflib import SequenceMatcher
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

from asr import ASRClient
from llm import LLMAgent, LLMClient
from tts import RealtimeTTSPlayer, TTSClient

from logger import logger

MAX_QUEUE_SIZE = 10

SPECIAL_WORD_MAP = {
    # 这里目标正确词作为键，常见错误变体列表作为值，可以根据实际情况调整和扩展
    "": [
        # 常见 ASR 错误示例，可以根据实际情况调整和扩展
    ],
}


class AssistantState(Enum):
    IDLE = 0  # 空闲 / 待唤醒
    ACTIVE = 1  # 激活状态
    LISTENING = 2  # 正在录音（等用户说话）
    THINKING = 3  #  ASR / LLM 推理中
    SPEAKING = 4  # TTS 播放中


class LLMAgentState(Enum):
    IDLE = 0  # 空闲
    ACTIVE = 1  # 激活状态


class TTSClientState(Enum):
    IDLE = 0  # 空闲
    ACTIVE = 1  # 激活状态


class ChatAssistant:
    def __init__(
        self, config_path: str, dynamic_tool_middlewares=None, middleware_list=None
    ):

        self.config_yaml = Path(config_path).expanduser().resolve()
        self.configs = {}

        self.asr_text = ""
        self.llm_response = ""

        self.asr_text_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.llm_response_queue = Queue(maxsize=MAX_QUEUE_SIZE)

        # 同时保存 jason 形式的响应文本，包括 asr_text 和 llm_text
        self.response_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.response_json = {}

        self.input_stream = None
        self.recorder_thread = None
        self.recording_active = False

        # self.dynamic_tool_middlewares = dynamic_tool_middlewares
        self.middleware_list = middleware_list

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
        llm_cfg = self.configs.get("LLM", {})
        self.llm_client = LLMAgent(
            host=llm_cfg.get("host", "192.168.50.125"),
            port=llm_cfg.get("port", 8000),
            # dynamic_tool_middlewares=self.dynamic_tool_middlewares,
            middleware_list=self.middleware_list,
        )
        system_prompt = llm_cfg.get("system_prompt", "")
        if system_prompt:
            self.llm_client.add_system_prompt(system_prompt)

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
            logger.warning(f"chunk_duration_ms 设置不合适，已调整为 20 ms 对应的字节数")
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
        self.set_kws_pinyin = self._extract_chinese_and_convert_to_pinyin(self.set_kws)
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

        self.enable_interrupt_tts = self.configs.get("enable_interrupt_tts", False)
        self.enable_replace_special_characters = self.configs.get(
            "enable_replace_special_characters", False
        )
        self.word_map = SPECIAL_WORD_MAP

        self.state = AssistantState.IDLE
        self.state_lock = threading.Lock()

        self.llm_agent_state = LLMAgentState.ACTIVE
        self.tts_client_state = TTSClientState.IDLE

        # 是否允许 ASR
        self.enable_asr = True

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

    def _compute_energy_instability(self):
        """
        计算能量不稳定性指标（标准差 / 均值）
        """
        if len(self.energy_window) < 5:
            return 0.0
        mean = np.mean(self.energy_window)
        std = np.std(self.energy_window)
        # logger.info(f"能量均值: {mean:.6f}, 标准差: {std:.6f}")
        return std / (mean + 1e-6)

    def _reset_segment_state(self):
        """重置音频片段状态。"""
        self.segments_to_save.clear()
        self.energy_window.clear()

    def _extract_chinese_and_convert_to_pinyin(self, input_string):
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

    def _is_kws_pinyin_match(self, detected_pinyin: str) -> bool:
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
    def _count_chinese_characters(self, input_string):
        """
        统计字符串中的汉字数量。

        :param input_string: 原始字符串
        :return: 汉字数量
        """
        chinese_characters = re.findall(r"[\u4e00-\u9fa5]", input_string)
        return len(chinese_characters)

    # 替换字符串中的特殊字符为智己
    def _replace_special_characters(self, input_string):
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

    def _check_vad_activity(self, audio_bytes: bytes) -> bool:
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

    def _calculate_decibel(self, audio_np: np.ndarray) -> float:
        """计算音频分贝值，避免对零取对数。"""
        if audio_np.size == 0:
            return float("-inf")
        rms = np.sqrt(np.mean(np.square(audio_np)))
        return 20 * np.log10(max(rms, 1e-10))

    def _float_to_pcm16(self, audio_np: np.ndarray) -> bytes:
        """将 float32 音频转换为 PCM16 字节流。"""
        # audio_clipped = np.clip(audio_np, -1.0, 1.0)
        # return (audio_clipped * 32767).astype(np.int16).tobytes()

        # audio_np: (N, 1) or (N,)
        if audio_np.ndim == 2:
            audio_np = audio_np[:, 0]  # ✅ 取 mono

        audio_clipped = np.clip(audio_np, -1.0, 1.0)
        return (audio_clipped * 32767).astype(np.int16).tobytes()

    def _finalize_pending_segments(self, timestamp: float) -> None:
        """在长时间静音后触发音频保存。"""

        energy_instability = self._compute_energy_instability()
        # logger.info(f"能量不稳定性指标(标准差/均值): {energy_instability:.6f}")

        # ====== 判定阈值 ======
        if (
            energy_instability > self.energy_instability_threshold
            and self.energy_instability_check
        ):
            logger.info(f"当前指标(标准差/均值): {energy_instability:.6f}")
            logger.info(f"阈值(标准差/均值): {self.energy_instability_threshold:.6f}")
            logger.warning("疑似多人说话，音频能量不稳定，放弃保存音频")
            self._reset_segment_state()
            return

        # 能量稳定，保存音频
        if (
            self.segments_to_save
            and self.segments_to_save[-1][1] > self.last_vad_end_time
        ):
            self.save_audio_only()
            self.last_active_time = timestamp

        # 重置状态
        self._reset_segment_state()

    ################## 保存音频的模块 ##################
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

        # ===============================
        # 4. 保存 WAV
        # ===============================
        with wave.open(str(audio_output_path), "wb") as wf:
            wf.setnchannels(self.audio_channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.audio_rate)
            wf.writeframes(b"".join(audio_frames))
        logger.info(f"检测到有效语音，已保存音频文件: {audio_output_path}")

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
        self.Inference(audio_path=str(audio_output_path))

        return audio_output_path

    #################### 音频录制线程 ###################
    def audio_recorder_thread(self):

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
                # 更新 last_llm_time
                self.last_llm_time = now

            # indata: float32 [-1.0, 1.0]
            audio_buffer.append(indata.copy())
            frames_collected += frames

            # 累积足够的音频进行分析
            if frames_collected >= analysis_interval_frames:

                # 合并音频块
                audio_np = np.concatenate(audio_buffer, axis=0)
                # 转为 PCM16 字节流
                audio_bytes = self._float_to_pcm16(audio_np)
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
                decibel = self._calculate_decibel(audio_np)

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
                        self._finalize_pending_segments(now)

                    ### 否则，继续等待, 保存静音段，防止断句不准确
                    else:
                        if self.segments_to_save:
                            logger.info("静音时间未超过阈值，继续等待，保存静音段")
                            self.segments_to_save.append((audio_bytes, now))

                ## 分贝高于阈值，继续处理
                else:
                    ### 如果 检测 VAD 活动，则保存音频段
                    if self._check_vad_activity(audio_bytes):
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
                    self._finalize_pending_segments(now)

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
        self._set_state(AssistantState.ACTIVE)

    def idle(self):
        """
        进入空闲状态
        """
        self._set_state(AssistantState.IDLE)

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

    def check_tts_active(self) -> bool:
        """
        负责检查 TTS 播放状态
        """
        try:
            is_active = self.tts_client.is_active()
            return is_active
        except Exception as e:
            return False

    def asr_infer(self, audio_path):
        """
        负责调用 ASR 完成语音识别
        """
        logger.info("ASR 识别中...")
        time_now = time.time()
        try:
            asr_text = self.asr_client.recognize(audio_path).strip()
            logger.info(
                f"ASR 识别结果: [{asr_text}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
            )
            return asr_text
        except Exception as e:
            logger.error(f"ASR 识别失败: {e}")
            return ""

    def llm_infer(self, asr_text):
        """
        负责调用 LLM 完成对话
        """
        logger.info("LLM 推理中...")
        llm_response = ""
        time_now = time.time()
        try:
            llm_response = self.llm_client.chat_response(asr_text)
            logger.info(
                f"LLM 推理结果: [{llm_response}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
            )
            return llm_response
        except Exception as e:
            logger.error(f"LLM 对话失败: {e}")
            return ""

    def tts_infer(self, llm_response):
        """
        负责调用 TTS 完成语音合成和播放
        """
        logger.info("TTS 合成和播放中...")
        time_now = time.time()
        try:
            self.tts_client.speak(llm_response.strip())

            while not self.tts_client.is_active():
                if time.time() - time_now > 5.0:
                    logger.error("TTS 播放超时 或者 TTS 播放音频太短")
                    return False
                time.sleep(0.01)

            elapsed_time = 0
            if isinstance(self.tts_client, RealtimeTTSPlayer):
                elapsed_time = time.time() - time_now
            else:
                elapsed_time = (
                    time.time()
                    - time_now
                    - self.tts_client.get_playback_start_delay_sec()
                )

            logger.info(f"TTS 合成并播放音频延迟: {elapsed_time:.2f} 秒")
            return True
        except Exception as e:
            logger.error(f"TTS 播放失败: {e}")
            return False

    def kws_infer(self, asr_text):
        """
        负责唤醒词检测
        """

        # 提取汉字并转换为拼音
        pinyin_text = self._extract_chinese_and_convert_to_pinyin(asr_text)
        logger.info(f"转换为拼音: {pinyin_text}")
        wake_word_matched = self._is_kws_pinyin_match(pinyin_text)

        if wake_word_matched and self.tts_client.is_active():
            logger.warning("检测到唤醒词， TTS 播放中，打断播放以避免语音叠加")

            # self.flag_kws = 1
            self.llm_agent_state = LLMAgentState.ACTIVE

            self.tts_client.interrupt()

            time.sleep(0.1)

            self.last_llm_time = time.time()
            return True

        # 判断是否需要重置唤醒词状态
        if time.time() - self.last_llm_time > self.reactive_kws_threshold:

            # self.flag_kws = 0
            # if self.llm_agent_state == LLMAgentState.ACTIVE:
            self.llm_agent_state = LLMAgentState.IDLE

            logger.info("长时间未与 LLM 交互，重置 LLM 模块为 IDLE 状态")

        # 判断是否启用唤醒词检测
        if self.flag_kws_used:

            # logger.info("需要唤醒词激活")
            if self.llm_agent_state == LLMAgentState.ACTIVE:
                logger.info("LLM 模块已处于 ACTIVE 状态，无需检测唤醒词")
                self.last_llm_time = time.time()
                return True

            if wake_word_matched:

                # self.flag_kws = 1
                self.llm_agent_state = LLMAgentState.ACTIVE

                self.failed_enable_kws_count = 0

                self.last_llm_time = time.time()

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

                    self._push_queue(
                        self.llm_response_queue, f"你可以说出:{self.set_kws} 来唤醒我!"
                    )
                    self.response_json["llm_text"] = (
                        f"你可以说出:{self.set_kws} 来唤醒我!"
                    )

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
                    self._push_queue(self.llm_response_queue, "")
                    self.response_json["llm_text"] = ""

                self.last_llm_time = time.time()
                return False

        else:
            self.llm_agent_state = LLMAgentState.ACTIVE
            self.last_llm_time = time.time()
            logger.info("未启用唤醒词激活功能")
            return True

    ##########################################################

    ####################### 核心交互流程 #######################
    def Inference(self, audio_path: str | None = None, input_text: str | None = None):
        """
        负责调用 ASR、LLM、TTS 完成一次完整的交互
        """
        logger.info("\n\n开始一次完整的交互流程...")

        # jason 形式的响应文本，包括 asr_text 和 llm_text
        self.response_json = {}

        # -------- asr 识别 -----------
        if audio_path:
            self.asr_text = self.asr_infer(audio_path)
        elif input_text:
            self.asr_text = input_text
        else:
            logger.warning("未提供音频路径或输入文本，跳过本次交互")
            self.last_llm_time = time.time()
            return
        # self.asr_text = "你好，小特"  # 测试代码，固定返回唤醒词
        # ## response_json 更新 asr_text
        # response_json["asr_text"] = self.asr_text
        if not self.asr_text:
            logger.warning("ASR 未识别到有效文本，跳过本次交互")
            self.last_llm_time = time.time()
            # self._set_state(AssistantState.LISTENING)
            return

        # -------- 判断asr_text中汉字数量，过少则忽略 ----------
        chinese_char_count = self._count_chinese_characters(self.asr_text)
        if chinese_char_count < 2:
            logger.warning("ASR 识别文本中汉字数量过少，跳过本次交互")
            self.last_llm_time = time.time()
            return

        # ------- 替换特殊词汇 -------
        if self.enable_replace_special_characters:
            logger.info(f"替换前 ASR 文本: {self.asr_text}")
            self.asr_text = self._replace_special_characters(self.asr_text)
            logger.info(f"替换后 ASR 文本: {self.asr_text}")
        # else:
        #     logger.info("未启用特殊词汇替换功能")

        ## 更新asr_text队列
        self._push_queue(self.asr_text_queue, self.asr_text)
        ## response_json 更新 asr_text
        self.response_json["asr_text"] = self.asr_text

        # ----------- 唤醒词检测 -----------
        if self.flag_kws_used:
            if not self.kws_infer(self.asr_text):
                # self._set_state(AssistantState.LISTENING)
                # 更新 response_queue 队列
                self._push_queue(self.response_queue, self.response_json)
                self.last_llm_time = time.time()
                return

        # self._set_state(AssistantState.THINKING)

        # -------- 检查 TTS 播放状态 ----------
        # if self.tts_client.is_active() and not self.enable_interrupt_tts:
        #     logger.warning("语音播放中，未启用打断，跳过本次交互")
        #     self.last_llm_time = time.time()
        #     return

        # -------- llm 对话 -----------
        if self.llm_agent_state == LLMAgentState.IDLE:

            self.last_llm_time = time.time()

            logger.warning("LLM 模块未激活，跳过本次交互")

            self._push_queue(self.llm_response_queue, "")
            self.response_json["llm_text"] = ""
            self._push_queue(self.response_queue, self.response_json)

            return

        self.llm_response = self.llm_infer(self.asr_text)

        if not self.llm_response:

            self.last_llm_time = time.time()

            # self._set_state(AssistantState.LISTENING)
            logger.warning("LLM 模块未生成有效回复，跳过本次交互")
            self._push_queue(self.llm_response_queue, "")
            self.response_json["llm_text"] = ""
            self._push_queue(self.response_queue, self.response_json)

            return

        ## 更新llm_response队列
        self._push_queue(self.llm_response_queue, self.llm_response)
        ## response_json 更新 llm_text
        self.response_json["llm_text"] = self.llm_response
        ## 更新 response_queue 队列
        self._push_queue(self.response_queue, self.response_json)

        # -------- 检查当前状态是否为空闲 ----------
        # if self.get_state() == AssistantState.IDLE:
        #     logger.warning("语音助手未激活，跳过TTS播放")
        #     self.last_llm_time = time.time()
        #     time.sleep(0.1)
        #     return

        if self.tts_client_state == TTSClientState.IDLE:
            logger.warning("TTS 模块未激活，跳过TTS播放")
            self.last_llm_time = time.time()
            time.sleep(0.1)
            return

        if self.tts_client.is_active() and not self.enable_interrupt_tts:
            logger.warning("语音播放中，未启用打断，跳过TTS播放")
            self.last_llm_time = time.time()
            return

        if self.tts_client.is_active() and self.enable_interrupt_tts:
            logger.info("语音播放中，启用了打断功能，准备中断播放")
            self.tts_client.interrupt()
            time.sleep(0.1)

        # -------- tts 播放 -----------
        # self._set_state(AssistantState.SPEAKING)
        self.tts_infer(self.llm_response)
        self.last_llm_time = time.time()
        # self._set_state(AssistantState.LISTENING)

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
