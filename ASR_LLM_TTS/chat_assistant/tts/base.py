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

from .audio import AudioQueueOutputStream, OutputStreamProtocol

INTERRUPT_GRACE_PERIOD_SEC = 0.2
LOCAL_AUDIO_STOP_WAIT_SEC = 0.1


class TTSClientBase(OutputStreamProtocol):
    """TTS 基类，同时声明了 TTS 客户端的核心接口和基础功能实现，具体的 TTS 客户端实现可以继承该基类并重写必要的方法以适配不同的 TTS 服务和协议。"""

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
    output_stream: AudioQueueOutputStream | None
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

        ############# OutputStreamProtocol 相关属性 #############
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
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
        ########################################################

        self.sound = None
        self.output_stream = None
        self.tts_thread = None

    def _create_output_stream(self):
        return AudioQueueOutputStream(
            self,
            sample_rate=self.sample_rate,
            channels=self.channels,
            buffer_size=self.buffer_size,
            dtype=self.playback_dtype,
        )

    def _initialize_runtime_components(self) -> None:
        self.output_stream = self._create_output_stream()
        self.output_stream.start()
        self.tts_thread = self._start_tts_worker()
        self._initialize_backend_if_needed()

    def _initialize_backend_if_needed(self) -> None:
        return

    def _start_tts_worker(self):
        raise NotImplementedError

    def _reset_playback_state(self) -> None:
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
        while not target_queue.empty():
            try:
                target_queue.get_nowait()
            except queue.Empty:
                break

    def _stop_local_audio_playback(self) -> None:
        if self.sound is not None and self.sound.is_alive():
            logger.info("正在停止当前播放的音频...")
            self.sound.stop()
            time.sleep(LOCAL_AUDIO_STOP_WAIT_SEC)

    def speak(self, text, interrupt=True):
        self._interrupt_event.clear()
        normalized_text = text.strip()

        if interrupt and normalized_text:
            self.interrupt()

        if not normalized_text:
            return

        self.text_queue.put(normalized_text)

    def is_active(self):
        return self.is_sounding or (self.sound is not None and self.sound.is_alive())

    def play_audio(self, file_path, block=False):
        try:
            if playsound is None:
                raise RuntimeError("playsound3 未安装，无法播放本地音频")

            self._stop_local_audio_playback()
            self.sound = playsound(file_path, block=block)
        except Exception as e:
            logger.error(f"播放{file_path}失败: {e}")

    def play_audio_from_pcm(self, pcm_bytes):
        with wave.open("temp.wav", "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)
        self.play_audio("temp.wav")

    def interrupt(self):
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
        self.voice = preset

    def get_playback_start_delay_sec(self):
        return self._playback_start_delay_sec

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        if self.is_sounding:
            return True
        return self._playback_started_event.wait(timeout=timeout_sec)
