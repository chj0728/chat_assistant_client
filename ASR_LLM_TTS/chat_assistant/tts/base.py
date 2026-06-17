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

from .audio import (
    AudioQueueOutputStream,
    MyOutputStream,
    OutputStreamProtocol,
)
from .backend import MyTTSBackend
from .backend_context import TTSBackendContext
from .runtimes.protocol import TTSRuntimeProtocol

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
    output_stream: AudioQueueOutputStream
    tts_thread: threading.Thread | None

    def _apply_base_init_kwargs(
        self,
        *,
        sample_rate: int,
        channels: int,
        chunk_size: int,
        buffer_size: int,
        playback_dtype: str,
        playback_start_delay_sec: float,
    ) -> None:
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
        self.output_stream: AudioQueueOutputStream
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
        raise NotImplementedError

    def _start_tts_worker(self):
        raise NotImplementedError

    @staticmethod
    def _drain_queue(target_queue: queue.Queue) -> None:
        """清空指定的队列，丢弃其中的所有元素，确保队列在中断或停止播放时被正确清理。"""
        while not target_queue.empty():
            try:
                target_queue.get_nowait()
            except queue.Empty:
                break

    def _stop_local_audio_playback(self) -> None:
        """停止当前正在播放的本地音频，如果有的话，并等待一段时间以确保音频播放已经完全停止，避免与后续的 TTS 音频播放产生冲突或叠加。"""
        if self.sound is not None and self.sound.is_alive():
            logger.info("正在停止当前播放的音频...")
            self.sound.stop()
            time.sleep(LOCAL_AUDIO_STOP_WAIT_SEC)

    def speak(self, text, interrupt=True):
        """请求 TTS 播放指定的文本内容，如果 interrupt 参数为 True，则在请求播放前会先中断当前的播放状态，确保新的文本能够立即被播放而不会与之前的播放内容产生冲突或叠加。"""
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

        self._stop_local_audio_playback()

        if not self.text_queue.empty() or not self.audio_queue.empty():
            logger.info("正在清空播放队列...")
        self._drain_queue(self.text_queue)
        self._drain_queue(self.audio_queue)

        self.output_stream.interrupt()

    def change_preset(self, preset):
        self.voice = preset

    def get_playback_start_delay_sec(self):
        return self._playback_start_delay_sec

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        if self.is_sounding:
            return True
        return self._playback_started_event.wait(timeout=timeout_sec)


class MyTTSClientBase:
    def __init__(self, **kwargs) -> None:

        self.sound = None

        self.on_init(**kwargs)

    def on_init(self, **kwargs) -> None:

        self.tts_server_type = kwargs.get("tts_server_type", "tts_local")
        self.timeout_sec = kwargs.get("timeout_sec", 10.0)
        self.playback_start_delay_sec = kwargs.get("playback_start_delay_sec", 0.0)
        self.playback_hangover_sec = kwargs.get("playback_hangover_sec", 0.0)
        self.playback_gain = kwargs.get(self.tts_server_type, {}).get(
            "playback_gain", kwargs.get("playback_gain", 1.0)
        )

        self.sample_rate = kwargs.get(self.tts_server_type, {}).get(
            "sample_rate", kwargs.get("sample_rate", 16000)
        )
        self.channels = kwargs.get(self.tts_server_type, {}).get(
            "channels", kwargs.get("channels", 1)
        )
        self.dtype = kwargs.get(self.tts_server_type, {}).get(
            "dtype", kwargs.get("dtype", "int16")
        )
        self.buffer_size = kwargs.get(self.tts_server_type, {}).get(
            "buffer_size", kwargs.get("buffer_size", 4096)
        )

        self.chunk_size = kwargs.get(self.tts_server_type, {}).get(
            "chunk_size", kwargs.get("chunk_size", 1024)
        )

        self.host = kwargs.get("tts_local", {}).get("host", "0.0.0.0")
        self.port = kwargs.get("tts_local", {}).get("port", 0)
        self.speaker_id = kwargs.get("tts_local", {}).get("speaker_id", 0)
        self.speed = kwargs.get("tts_local", {}).get("speed", 1.0)
        self.use_websocket = kwargs.get("tts_local", {}).get("use_websocket", False)
        self.ws_path = kwargs.get("tts_local", {}).get("ws_path", "/ws/api/tts")

        self.voice_type = kwargs.get("tts_remote", {}).get("voice_type", "Ethan")
        self.model = kwargs.get("tts_remote", {}).get(
            "model", "qwen3-tts-flash-realtime"
        )
        self.remote_mode = kwargs.get("tts_remote", {}).get("remote_mode", "commit")
        self.remote_url = kwargs.get("tts_remote", {}).get("remote_url", None)

        self.text_queue: queue.Queue[str] = queue.Queue()
        self.audio_queue: queue.Queue[bytes] = queue.Queue()

        self.stop_event = threading.Event()
        self.interrupt_event = threading.Event()

        self.output_stream = self.create_output_stream()
        self.tts_runtime = self.create_tts_runtime()
        self.tts_backend = self.create_tts_backend()

        self.tts_backend.on_start()

    def create_backend_context(self, **kwargs) -> TTSBackendContext:

        return TTSBackendContext(
            host=self.host,
            port=self.port,
            timeout=self.timeout_sec,
            sample_rate=self.sample_rate,
            channels=self.channels,
            chunk_size=self.chunk_size,
            text_queue=self.text_queue,
            audio_queue=self.audio_queue,
            stop_event=self.stop_event,
            interrupt_event=self.interrupt_event,
            speaker_id=self.speaker_id,
            speed=self.speed,
            use_websocket=self.use_websocket,
            ws_path=self.ws_path,
            # ws_ping_interval=self.ws_ping_interval,
            # ws_ping_timeout=self.ws_ping_timeout,
            voice=self.voice_type,
            # api_key=self.api_key,
            model=self.model,
            remote_url=self.remote_url,
            remote_mode=self.remote_mode,
        )

    def create_output_stream(self) -> MyOutputStream:

        return MyOutputStream(
            context=self.create_backend_context(),
            sample_rate=self.sample_rate,
            channels=self.channels,
            buffer_size=self.buffer_size,
            dtype=self.dtype,
            playback_start_delay_sec=self.playback_start_delay_sec,
            playback_hangover_sec=self.playback_hangover_sec,
            playback_gain=self.playback_gain,
        )

    def create_tts_runtime(self) -> TTSRuntimeProtocol:

        if self.tts_server_type == "tts_remote":
            from .runtimes.qwen import QwenTTSRuntime

            return QwenTTSRuntime(self.create_backend_context())
        else:
            from .runtimes.sherpa import SherpaTTSRuntime

            return SherpaTTSRuntime(self.create_backend_context())

    def create_tts_backend(self) -> MyTTSBackend:

        return MyTTSBackend(
            tts_backend_context=self.create_backend_context(),
            tts_runtime=self.tts_runtime,
            output_stream=self.output_stream,
            worker_thread_name="tts-loop-worker",
            request_error_log_prefix="TTS 请求失败",
            transfer_elapsed_log_label="TTS 音频传输耗时",
        )

    @staticmethod
    def _drain_queue(target_queue: queue.Queue) -> None:
        """清空指定的队列，丢弃其中的所有元素，确保队列在中断或停止播放时被正确清理。"""
        while not target_queue.empty():
            try:
                target_queue.get_nowait()
            except queue.Empty:
                break

    ################ 对外接口 #####################

    def generate_wav(self, text: str, filename: str) -> bool:
        """生成 WAV 文件，适用于需要将合成的音频保存为本地文件的场景。"""
        return self.tts_backend.generate_wav(text, filename)

    def speak(self, text, interrupt=True):
        """请求 TTS 播放指定的文本内容，如果 interrupt 参数为 True，则在请求播放前会先中断当前的播放状态，确保新的文本能够立即被播放而不会与之前的播放内容产生冲突或叠加。"""
        self.interrupt_event.clear()
        normalized_text = text.strip()

        if interrupt and normalized_text:
            self.interrupt()

        if not normalized_text:
            return

        self.text_queue.put(normalized_text)

    def interrupt(self):
        """
        1. 停止本地音频文件播放
        2. 清空文本和音频队列，确保没有残留的待播放内容
        3. 调用 TTS 后端的中断方法，确保正在播放的 TTS 音频被中断
        """
        self.stop_local_audio_playback()

        if not self.text_queue.empty() or not self.audio_queue.empty():
            logger.info("正在清空播放队列...")
        self._drain_queue(self.text_queue)
        self._drain_queue(self.audio_queue)

        self.tts_backend.interrupt()

    def is_active(self) -> bool:
        """判断 OutputStream 是否处于播放状态 或者当前是否有本地音频正在播放，适用于需要判断 TTS 客户端整体播放状态的场景。"""
        return self.tts_backend.is_active() or (
            self.sound is not None and self.sound.is_alive()
        )

    def play_audio(self, file_path, block=False):
        """播放指定路径的本地音频文件，适用于需要播放预先合成的音频文件的场景。"""
        try:
            if playsound is None:
                raise RuntimeError("playsound3 未安装，无法播放本地音频")

            self.stop_local_audio_playback()
            self.sound = playsound(file_path, block=block)
        except Exception as e:
            logger.error(f"播放{file_path}失败: {e}")

    def play_audio_from_pcm(self, pcm_bytes):
        """从 PCM 字节数据临时生成 WAV 文件并播放。"""
        with wave.open("temp.wav", "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)
        self.play_audio("temp.wav")

    def stop_local_audio_playback(self) -> None:
        """停止当前正在播放的本地音频，如果有的话，并等待一段时间以确保音频播放已经完全停止，避免与后续的 TTS 音频播放产生冲突或叠加。"""
        if self.sound is not None and self.sound.is_alive():
            logger.info("正在停止当前播放的音频...")
            self.sound.stop()
            time.sleep(LOCAL_AUDIO_STOP_WAIT_SEC)

    def get_playback_start_delay_sec(self):
        """获取播放开始的延迟时间。"""
        return self.playback_start_delay_sec

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        """等待output_stream进入播放状态，返回是否成功进入播放状态，适用于需要确认音频已经开始播放的场景。"""
        return self.tts_backend.wait_until_playback_starts(timeout_sec=timeout_sec)
