import queue
import threading
import time

import numpy as np
from logger import logger

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    sd = None

from ..backend_context import TTSBackendContext
from .protocol import MyOutputStreamProtocol


def _apply_playback_gain(pcm: np.ndarray, gain: float) -> np.ndarray:
    """应用播放增益到 PCM 数据，根据数据类型进行适当的缩放和剪辑，确保在放大音量的同时避免削波失真。对于浮点型数据，直接乘以增益并剪辑到 [-1.0, 1.0]；对于整数型数据，先转换为浮点型进行增益处理，然后根据数据类型的范围进行剪辑，最后转换回原始数据类型。对于其他数据类型，则不进行处理直接返回原始 PCM 数据。"""
    if gain == 1.0 or pcm.size == 0:
        return pcm

    if np.issubdtype(pcm.dtype, np.floating):
        return np.clip(pcm.astype(np.float32) * gain, -1.0, 1.0).astype(
            pcm.dtype, copy=False
        )

    if np.issubdtype(pcm.dtype, np.integer):
        limits = np.iinfo(pcm.dtype)
        return np.clip(
            pcm.astype(np.float32) * gain,
            limits.min,
            limits.max,
        ).astype(pcm.dtype, copy=False)

    return pcm


class MyOutputStream(MyOutputStreamProtocol):
    def __init__(
        self,
        context: TTSBackendContext,
        sample_rate: int = 16000,
        channels: int = 1,
        buffer_size: int = 4096,
        dtype: str = "int16",
        playback_start_delay_sec: float = 0.0,
        playback_hangover_sec: float = 0.0,
        playback_gain: float = 1.0,
    ) -> None:

        self.context = context
        self.is_sounding = False

        if sd is None:
            raise RuntimeError("sounddevice 未安装，无法创建音频输出流")

        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer_size = buffer_size
        self.dtype = dtype

        self.audio_lock = threading.Lock()
        self.audio_active_started_ts = 0.0
        self.last_audio_chunk_ts = 0.0
        self.playback_start_delay_sec = playback_start_delay_sec
        self.playback_hangover_sec = playback_hangover_sec
        self.playback_gain = max(playback_gain, 0.0)
        self.playback_buffer = np.empty((0, self.channels), dtype=self.dtype)

        self.stop_event = threading.Event()
        self.interrupt_event = threading.Event()
        self.playback_started_event = threading.Event()

        self.output_stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.buffer_size,
            latency="low",
            callback=self._audio_callback,
        )

    def _audio_callback(self, outdata, frames, time_info, status) -> None:
        """音频回调函数，用于处理音频数据的输出和播放状态的更新。"""
        del time_info
        now = time.monotonic()

        if status:
            logger.debug(f"音频回调状态: {status}")

        if self.stop_event.is_set() or self.interrupt_event.is_set():
            outdata.fill(0)
            self.is_sounding = False
            self.audio_active_started_ts = 0.0
            self.last_audio_chunk_ts = 0.0
            self.playback_started_event.clear()
            return

        filled = 0
        with self.audio_lock:
            while filled < frames:
                if self.playback_buffer.shape[0] == 0:
                    try:
                        chunk = self.context.audio_queue.get_nowait()
                    except queue.Empty:
                        break

                    pcm = np.frombuffer(chunk, dtype=self.dtype)
                    pcm = _apply_playback_gain(pcm, self.playback_gain)
                    if pcm.size == 0:
                        continue
                    if pcm.size % self.channels != 0:
                        logger.warning("丢弃未对齐的音频块")
                        continue
                    self.playback_buffer = np.ascontiguousarray(
                        pcm.reshape(-1, self.channels)
                    )

                take = min(frames - filled, self.playback_buffer.shape[0])
                outdata[filled : filled + take] = self.playback_buffer[:take]
                self.playback_buffer = self.playback_buffer[take:]
                filled += take

        if filled < frames:
            outdata[filled:].fill(0)

        ####### 声音检测逻辑，延迟判断起播音频播放状态 #######
        if filled > 0:
            # 先记录首帧时间；达到起播确认窗口后再判定为播放。
            if self.audio_active_started_ts <= 0.0:
                self.audio_active_started_ts = now
            self.last_audio_chunk_ts = now
            self.is_sounding = (
                now - self.audio_active_started_ts
            ) >= self.playback_start_delay_sec
            if self.is_sounding:
                self.playback_started_event.set()
        else:
            # 短暂挂起窗口用于吸收回调调度抖动，避免状态频繁抖动。
            keep_active = (now - self.last_audio_chunk_ts) < self.playback_hangover_sec
            self.is_sounding = keep_active
            if not keep_active:
                self.audio_active_started_ts = 0.0
                self.playback_started_event.clear()
        ################################################

    def _reset_playback_state(self) -> None:
        """重置播放状态，清空播放缓冲区和相关时间戳，并更新播放状态标志和事件，确保在停止或中断播放时能够正确地清理播放状态并准备好下一次播放。"""
        with self.audio_lock:
            self.playback_buffer = np.empty((0, self.channels), dtype=self.dtype)
            self.audio_active_started_ts = 0.0
            self.last_audio_chunk_ts = 0.0
        self.is_sounding = False
        self.playback_started_event.clear()

    def start(self) -> None:
        self.output_stream.start()

    def stop(self) -> None:
        self.output_stream.stop()

    def close(self) -> None:
        self.output_stream.close()

    def interrupt(self) -> None:

        self.interrupt_event.set()
        time.sleep(0.2)
        self._reset_playback_state()
        self.interrupt_event.clear()

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        return self.playback_started_event.wait(timeout=timeout_sec)

    def is_sounding_flag(self) -> bool:
        return self.is_sounding
