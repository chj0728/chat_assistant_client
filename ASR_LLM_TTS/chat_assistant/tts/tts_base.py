import queue
import threading
import time
import wave
from typing import Any

import numpy as np
from logger import logger

try:
    from playsound3 import playsound
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    playsound = None

from .stream import AudioQueueOutputStream, AudioStreamOwner

INTERRUPT_GRACE_PERIOD_SEC = 0.2
LOCAL_AUDIO_STOP_WAIT_SEC = 0.1


class TTSClientBase(AudioStreamOwner):
    """TTS 基类，同时声明 AudioStreamOwner 所需的播放状态接口。"""

    audio_queue: queue.Queue[bytes]
    is_sounding: bool
    _audio_active_started_ts: float
    _audio_lock: threading.Lock
    _last_audio_chunk_ts: float
    _playback_start_delay_sec: float
    _playback_hangover_sec: float
    _playback_buffer: np.ndarray
    _stop_event: threading.Event
    _interrupt_event: threading.Event
    _playback_started_event: threading.Event

    sound: Any
    stream: AudioQueueOutputStream | None
    tts_thread: threading.Thread | None

    def _apply_base_init_kwargs(
        self,
        *,
        host,
        port,
        timeout_sec: float,
        sample_rate: int,
        channels: int,
        chunk_size: int,
        buffer_size: int,
        playback_dtype: str,
        playback_start_delay_sec: float,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_sec = timeout_sec
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.buffer_size = buffer_size
        self.playback_dtype = playback_dtype

        self.text_queue: queue.Queue[str] = queue.Queue()
        self.audio_queue: queue.Queue[bytes] = queue.Queue()

        self.sound = None
        self.is_sounding = False

        self._audio_active_started_ts = 0.0
        self._audio_lock = threading.Lock()
        self._last_audio_chunk_ts = 0.0
        self._playback_start_delay_sec = playback_start_delay_sec
        self._playback_hangover_sec = 0.0
        self._playback_buffer = np.empty(
            (0, self.channels), dtype=np.dtype(playback_dtype)
        )

        self._stop_event = threading.Event()
        self._interrupt_event = threading.Event()
        self._playback_started_event = threading.Event()

        self.stream = None
        self.tts_thread = None

    def _create_output_stream(self):
        """创建音频输出流。"""
        return AudioQueueOutputStream(
            self,
            sample_rate=self.sample_rate,
            channels=self.channels,
            buffer_size=self.buffer_size,
            dtype=self.playback_dtype,
        )

    def _initialize_runtime_components(self) -> None:
        """初始化 TTS 运行时组件，包括音频流和工作线程。"""
        self.stream = self._create_output_stream()
        self.stream.start()
        self.tts_thread = self._start_tts_worker()
        self._initialize_backend_if_needed()

    def _initialize_backend_if_needed(self) -> None:
        """初始化 TTS 后端运行时（如果需要）。"""
        return

    def _start_tts_worker(self):
        """启动 TTS 工作线程。"""
        raise NotImplementedError

    def _close_backend_runtime(self) -> None:
        """关闭 TTS 后端运行时。"""
        return

    def _reset_playback_state(self) -> None:
        """重置播放状态，包括播放缓冲区和时间戳。"""
        with self._audio_lock:
            self._playback_buffer = np.empty(
                (0, self.channels), dtype=np.dtype(self.playback_dtype)
            )
            self._audio_active_started_ts = 0.0
            self._last_audio_chunk_ts = 0.0
        self.is_sounding = False
        self._playback_started_event.clear()

    @staticmethod
    def _drain_queue(target_queue: queue.Queue) -> None:
        """清空队列中的所有元素。"""
        while not target_queue.empty():
            try:
                target_queue.get_nowait()
            except queue.Empty:
                break

    def _stop_local_audio_playback(self) -> None:
        """停止本地音频播放。"""
        if self.sound is not None and self.sound.is_alive():
            logger.info("正在停止当前播放的音频...")
            self.sound.stop()
            time.sleep(LOCAL_AUDIO_STOP_WAIT_SEC)

    ######### TTS 客户端接口 #########
    def speak(self, text, interrupt=True):
        """将文本加入 TTS 播放队列，等待 TTS 后端处理并通过音频流播放。"""
        self._interrupt_event.clear()
        normalized_text = text.strip()

        if interrupt and normalized_text:
            self.interrupt()

        if not normalized_text:
            return

        self.text_queue.put(normalized_text)

    def is_active(self):
        """检查 TTS 客户端是否处于活动状态，即是否正在播放音频。"""
        return self.is_sounding or (self.sound is not None and self.sound.is_alive())

    def play_audio(self, file_path, block=False):
        """播放本地音频文件。"""
        try:
            if playsound is None:
                raise RuntimeError("playsound3 未安装，无法播放本地音频")

            self._stop_local_audio_playback()
            self.sound = playsound(file_path, block=block)
        except Exception as e:
            logger.error(f"播放{file_path}失败: {e}")

    def play_audio_from_pcm(self, pcm_bytes):
        """将 PCM 数据写入临时 WAV 文件并播放。"""
        with wave.open("temp.wav", "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)
        self.play_audio("temp.wav")

    def interrupt(self):
        """中断当前的 TTS 播放，清空播放队列并重置播放状态。"""
        self._interrupt_event.set()
        time.sleep(INTERRUPT_GRACE_PERIOD_SEC)

        if not self.text_queue.empty() or not self.audio_queue.empty():
            logger.info("正在清空播放队列...")

        self._drain_queue(self.text_queue)
        self._drain_queue(self.audio_queue)
        self._reset_playback_state()
        self._stop_local_audio_playback()
        self._interrupt_event.clear()

    def change_preset(self, preset):
        """更改 TTS 的语音预设。"""
        self.voice = preset

    def get_playback_start_delay_sec(self):
        """获取 TTS 播放开始的延迟时间（秒）。"""
        return self._playback_start_delay_sec

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        """等待 TTS 播放开始，直到超时。"""
        if self.is_sounding:
            return True
        return self._playback_started_event.wait(timeout=timeout_sec)

    def stop(self):
        """停止 TTS 播放并清理资源。"""
        self._stop_event.set()
        self.interrupt()
        self._close_backend_runtime()
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
        if self.tts_thread is not None:
            self.tts_thread.join(timeout=3)
