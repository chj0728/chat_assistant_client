import threading
import time
import wave
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
import webrtcvad
from logger import logger

from ..asr_backend_context import ASRBackendContext
from .protocol import InputStreamProtocol

AudioSegment = tuple[bytes, float]


class InputStream(InputStreamProtocol):
    """Microphone input stream with VAD based utterance segmentation."""

    VAD_FRAME_DURATIONS_MS = (10, 20, 30)
    PCM_SAMPLE_WIDTH = 2
    OUTPUT_CHANNELS = 1

    def __init__(
        self,
        asr_backend_context: ASRBackendContext,
        device: int | str | None = None,
        **kwargs: Any,
    ) -> None:
        """初始化输入流配置、运行状态和 VAD 实例。"""
        self.asr_backend_context = asr_backend_context
        self.device = device

        self.recording_active = False
        self.recorder_thread: threading.Thread | None = None
        self.input_stream: sd.InputStream | None = None

        self.segments_to_save: list[AudioSegment] = []
        self.pre_recording_buffer: deque[AudioSegment] = deque()
        self.last_saved_end = time.time()
        self.last_active_time = time.time()
        # self.last_vad_end_time = time.time()

        self._init_audio_settings(kwargs.get("Audio", {}))
        self._init_vad_settings(kwargs.get("VAD", {}))

    def _init_audio_settings(self, audio_cfg: dict[str, Any]) -> None:
        """从 Audio 配置读取采样率、通道数、块大小和文件轮转参数。"""
        self.enable = audio_cfg.get("enable", False)
        self.samplerate = audio_cfg.get("samplerate", 16000)
        self.channels = audio_cfg.get("channels", 1)
        self.chunk_duration_ms = audio_cfg.get("chunk_duration_ms", 20)
        self.audio_file_count = 0
        self.max_file_count = audio_cfg.get("max_file_count", 20)

        self._refresh_chunk_size()
        valid_chunk_bytes = {
            int(self.samplerate * ms / 1000) * self.PCM_SAMPLE_WIDTH
            for ms in self.VAD_FRAME_DURATIONS_MS
        }
        if self.chunk_bytes not in valid_chunk_bytes:
            logger.warning("chunk_duration_ms 设置不合适，已调整为 20 ms")
            self.chunk_duration_ms = 20
            self._refresh_chunk_size()

    def _init_vad_settings(self, vad_cfg: dict[str, Any]) -> None:
        """从 VAD 配置读取分段阈值、输出目录和 WebRTC VAD 参数。"""
        self.vad_mode = vad_cfg.get("vad_mode", vad_cfg.get("mode", 3))
        self.output_dir = (
            Path(__file__).resolve().parent.parent / vad_cfg.get("output_dir", "output")
        ).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.no_speech_duration = vad_cfg.get("no_speech_duration", 0.5)
        self.decibel_threshold = vad_cfg.get("decibel_threshold", -40)
        self.min_recording_duration = vad_cfg.get("min_recording_duration", 1.0)
        self.max_recording_duration = vad_cfg.get("max_recording_duration", 10.0)
        self.pause_duration = vad_cfg.get("pause_duration", 1.5)
        self.pre_recording_buffer_duration = vad_cfg.get(
            "pre_recording_buffer_duration", 0.5
        )
        self.vad = webrtcvad.Vad(self.vad_mode)

    def _refresh_chunk_size(self) -> None:
        """根据采样率和块时长刷新帧数与 PCM 字节数。"""
        self.chunk_frames = int(self.samplerate * self.chunk_duration_ms / 1000)
        self.chunk_bytes = self.chunk_frames * self.PCM_SAMPLE_WIDTH

    def start(self) -> None:
        """启动音频输入流，准备好接收和处理音频数据。"""
        if not self.enable:
            logger.warning("音频采集模块未启用")
            return

        if self.recording_active:
            logger.warning("录音线程已在运行，忽略重复启动请求")
            return

        self._reset_runtime_state()
        self.recording_active = True
        self.recorder_thread = threading.Thread(
            target=self.input_stream_thread,
            name="asr-input-stream",
            daemon=True,
        )
        self.recorder_thread.start()
        logger.info("音频输入流线程已启动")

    def stop(self) -> None:
        """停止音频输入流，释放相关资源。"""
        if not self.recording_active:
            logger.info("音频输入流线程已停止")
            return

        self.recording_active = False
        if self.recorder_thread and self.recorder_thread.is_alive():
            self.recorder_thread.join()

        self.close()
        logger.info("音频输入流线程已停止")

    def close(self) -> None:
        """关闭音频输入流，彻底释放相关资源。"""
        if self.input_stream is not None:
            self.input_stream.close()
            self.input_stream = None

    def _reset_runtime_state(self) -> None:
        """重置一次录音会话的临时片段、缓冲区和时间戳。"""
        now = time.time()
        self._clear_pending_segments()
        self.last_saved_end = now
        self.last_active_time = now
        # self.last_vad_end_time = now

    def _clear_pending_segments(self) -> None:
        """清空待保存音频片段和预录音缓冲区。"""
        self.segments_to_save.clear()
        self.pre_recording_buffer.clear()

    def _append_pre_recording_buffer(
        self, audio_bytes: bytes, timestamp: float
    ) -> None:
        """保存最近一小段历史音频，用于补齐有效录音开头。"""
        if self.pre_recording_buffer_duration <= 0:
            return

        self.pre_recording_buffer.append((audio_bytes, timestamp))
        while (
            self.pre_recording_buffer
            and timestamp - self.pre_recording_buffer[0][1]
            > self.pre_recording_buffer_duration
        ):
            self.pre_recording_buffer.popleft()

    def _build_audio_frames_with_pre_buffer(self) -> list[bytes]:
        """拼接预录音缓冲和当前有效片段，生成完整音频帧列表。"""
        if not self.segments_to_save:
            return []

        start_time = self.segments_to_save[0][1]
        pre_buffer_frames = [
            audio_bytes
            for audio_bytes, timestamp in self.pre_recording_buffer
            if timestamp < start_time
        ]

        if pre_buffer_frames:
            pre_buffer_duration = sum(len(frame) for frame in pre_buffer_frames) / (
                self.PCM_SAMPLE_WIDTH * self.OUTPUT_CHANNELS * self.samplerate
            )
            logger.info(f"补充录音开头缓冲: {pre_buffer_duration:.2f} 秒")

        segment_frames = [audio_bytes for audio_bytes, _ in self.segments_to_save]
        return pre_buffer_frames + segment_frames

    def _has_speech(self, audio_bytes: bytes) -> bool:
        """检查 mono PCM16 音频中是否包含 WebRTC VAD 识别到的语音。"""
        if len(audio_bytes) < self.chunk_bytes:
            return False

        for offset in range(
            0,
            len(audio_bytes) - self.chunk_bytes + 1,
            self.chunk_bytes,
        ):
            frame = audio_bytes[offset : offset + self.chunk_bytes]
            if self.vad.is_speech(frame, self.samplerate):
                return True

        return False

    @staticmethod
    def _calculate_decibel(audio_np: np.ndarray) -> float:
        """根据 float 音频数组计算 RMS 分贝值。"""
        if audio_np.size == 0:
            return float("-inf")
        rms = np.sqrt(np.mean(np.square(audio_np)))
        return 20 * np.log10(max(rms, 1e-10))

    @staticmethod
    def _float_to_pcm16(audio_np: np.ndarray) -> bytes:
        """将 sounddevice 的 float32 音频转换为 mono PCM16 字节流。"""
        if audio_np.ndim == 2:
            audio_np = audio_np[:, 0]

        audio_clipped = np.clip(audio_np, -1.0, 1.0)
        return (audio_clipped * 32767).astype(np.int16).tobytes()

    def _finalize_pending_segments(self, timestamp: float) -> None:
        """在片段结束时校验缓冲间隔并触发保存。"""
        if not self.segments_to_save:
            return

        # if self.segments_to_save[-1][1] <= self.last_vad_end_time + self.pause_duration:
        #     logger.warning("缓冲时间内，跳过保存音频")
        #     self._clear_pending_segments()
        #     return

        self.save_audio_only()
        # self.last_active_time = timestamp
        self._clear_pending_segments()

    def input_stream_thread(self) -> None:
        """音频输入流线程函数，持续读取音频并按 VAD 结果推送给 ASR 后端。"""
        audio_buffer: list[np.ndarray] = []
        frames_collected = 0
        analysis_interval_frames = max(
            self.chunk_frames,
            int(0.20 * self.samplerate),
            1,
        )
        self.last_active_time = time.time()

        logger.info("音频录制已开始（sounddevice）")
        logger.info(f"单次回调音频帧数: {self.chunk_frames}")
        logger.info(f"单次回调音频时长: {self.chunk_frames / self.samplerate:.3f} 秒")
        logger.info(f"分析间隔音频帧数: {analysis_interval_frames}")
        logger.info(
            f"分析间隔时长: {analysis_interval_frames / self.samplerate:.3f} 秒"
        )

        def reset_buffer() -> None:
            """清空当前分析窗口中的音频缓存。"""
            nonlocal audio_buffer, frames_collected
            audio_buffer.clear()
            frames_collected = 0

        def audio_callback(indata, frames, time_info, status) -> None:
            """sounddevice 回调：累积音频帧并按分析窗口送入 VAD 流程。"""
            nonlocal frames_collected
            if not self.recording_active:
                raise sd.CallbackStop()
            if status:
                logger.warning(f"音频输入状态异常: {status}")

            audio_buffer.append(indata.copy())
            frames_collected += frames
            if frames_collected < analysis_interval_frames:
                return

            audio_np = np.concatenate(audio_buffer, axis=0)
            audio_bytes = self._float_to_pcm16(audio_np)
            reset_buffer()
            self._process_audio_chunk(audio_np, audio_bytes, time.time())

        effective_device = self._resolve_input_device()
        stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.chunk_frames,
            callback=audio_callback,
            device=effective_device,
        )

        self.input_stream = stream
        try:
            with stream:
                logger.info("音频输入流已打开，等待录音...")
                while self.recording_active:
                    time.sleep(0.1)
        finally:
            self.input_stream = None

    def _process_audio_chunk(
        self, audio_np: np.ndarray, audio_bytes: bytes, timestamp: float
    ) -> None:
        """处理一个分析窗口内的音频，按能量和 VAD 结果更新分段状态。"""
        if not self.segments_to_save:
            self._append_pre_recording_buffer(audio_bytes, timestamp)

        decibel = self._calculate_decibel(audio_np)
        if decibel < self.decibel_threshold:
            self._handle_silence(audio_bytes, timestamp)
        elif self._has_speech(audio_bytes):
            self._handle_speech(audio_bytes, timestamp, decibel)
        elif self.segments_to_save:
            logger.info(f"未检测到语音活动，分贝: {decibel:.2f} dB，继续等待")
            self.segments_to_save.append((audio_bytes, timestamp))

        if self._exceeds_max_recording_duration():
            logger.info(
                f"录音片段时长超过最大值 {self.max_recording_duration} 秒，保存音频段"
            )
            self._finalize_pending_segments(timestamp)

    def _handle_silence(self, audio_bytes: bytes, timestamp: float) -> None:
        """处理低于分贝阈值的音频，并在静音超时后结束当前片段。"""
        if not self.segments_to_save:
            return

        self.segments_to_save.append((audio_bytes, timestamp))
        if timestamp - self.last_active_time > self.no_speech_duration:
            logger.info("静音时间超过阈值，收集历史音频段")
            self._finalize_pending_segments(timestamp)
        else:
            logger.info("静音时间未超过阈值，继续等待")

    def _handle_speech(
        self, audio_bytes: bytes, timestamp: float, decibel: float
    ) -> None:
        """处理检测到语音的音频块，并记录活跃时间。"""
        if timestamp < self.last_saved_end + self.pause_duration:
            logger.warning("缓冲时间内，忽略音频")
            return

        logger.info(f"检测到语音活动，分贝: {decibel:.2f} dB")
        self.last_active_time = timestamp
        self.segments_to_save.append((audio_bytes, timestamp))

    def _exceeds_max_recording_duration(self) -> bool:
        """判断当前片段是否已经超过最大录音时长。"""
        if not self.segments_to_save:
            return False
        return (
            self.segments_to_save[-1][1] - self.segments_to_save[0][1]
            > self.max_recording_duration
        )

    def _resolve_input_device(self) -> int | str | None:
        """列出输入设备并解析最终传给 sounddevice 的设备标识。"""
        devices = sd.query_devices()
        input_devices = [
            (idx, info)
            for idx, info in enumerate(devices)
            if info["max_input_channels"] > 0
        ]

        logger.info(f"共发现 {len(input_devices)} 个音频输入设备:")
        for idx, info in input_devices:
            hostapi = sd.query_hostapis(info["hostapi"])["name"]
            logger.info(
                f"  [{idx}] {info['name']} "
                f"(max_input_channels={info['max_input_channels']}, "
                f"default_samplerate={info['default_samplerate']}, hostapi={hostapi})"
            )

        if self.device is not None:
            if isinstance(self.device, int) and self.device < len(devices):
                logger.info(
                    f"使用指定输入设备: [{self.device}] "
                    f"{devices[self.device]['name']}"
                )
            else:
                logger.info(f"使用指定输入设备: {self.device}")
            return self.device

        default_device = sd.default.device[0]
        if default_device is not None and default_device < len(devices):
            logger.info(
                f"使用系统默认输入设备: [{default_device}] "
                f"{devices[default_device]['name']}"
            )
            return default_device

        logger.info("使用 sounddevice 自动选择的默认设备")
        return None

    def save_audio_only(self) -> None:
        """将当前 PCM16 音频片段送入 ASR 队列，并循环保存为 WAV 文件。"""
        if not self.segments_to_save:
            return

        try:
            # if time.time() - self.last_vad_end_time < self.pause_duration:
            #     logger.warning("缓冲时间内，跳过保存音频")
            #     return

            start_time = self.segments_to_save[0][1]
            end_time = self.segments_to_save[-1][1]
            if not self._is_valid_recording_interval(start_time, end_time):
                return

            audio_frames = self._build_audio_frames_with_pre_buffer()
            audio_bytes = b"".join(audio_frames)
            audio_output_path = self._next_audio_output_path()

            self.asr_backend_context.audio_frames_queue.put(audio_bytes)
            self._write_wav(audio_output_path, audio_bytes)
            logger.info(f"保存音频文件: {audio_output_path}")

            self.last_saved_end = end_time
            # self.last_vad_end_time = end_time
            formatted_time = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(self.last_saved_end)
            )
            logger.info(f"最新音频片段保存结束时间: {formatted_time}")
        finally:
            self.segments_to_save.clear()

    def _is_valid_recording_interval(self, start_time: float, end_time: float) -> bool:
        """校验录音片段是否不重叠且时长在允许范围内。"""
        if self.last_saved_end >= start_time:
            logger.warning("当前片段与之前片段重叠，跳过保存")
            return False

        recording_duration = end_time - start_time
        logger.info(f"录音时长: {recording_duration:.2f} 秒")
        min_duration = self.min_recording_duration + self.no_speech_duration
        max_duration = self.max_recording_duration + self.no_speech_duration

        if recording_duration < min_duration:
            logger.warning("录音时长过短，跳过保存")
            return False
        if recording_duration > max_duration:
            logger.warning("录音时长过长，跳过保存")
            return False
        return True

    def _next_audio_output_path(self) -> Path:
        """生成循环覆盖的 WAV 输出路径。"""
        self.audio_file_count = (self.audio_file_count % self.max_file_count) + 1
        return self.output_dir / f"audio_{self.audio_file_count}.wav"

    def _write_wav(self, audio_output_path: Path, audio_bytes: bytes) -> None:
        """将 mono PCM16 字节流写入 WAV 文件。"""
        with wave.open(str(audio_output_path), "wb") as wf:
            wf.setnchannels(self.OUTPUT_CHANNELS)
            wf.setsampwidth(self.PCM_SAMPLE_WIDTH)
            wf.setframerate(self.samplerate)
            wf.writeframes(audio_bytes)
