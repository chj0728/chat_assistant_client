import queue
import threading
import time
from typing import Protocol

import numpy as np
from logger import logger

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    sd = None


class AudioStreamOwner(Protocol):
    """Protocol for classes that own AudioQueueOutputStream.

    Args:
        _stop_event: 停止事件，用于通知音频流停止播放。
        _interrupt_event: 中断事件，用于通知音频流立即停止并清空状态。
        is_sounding: 当前是否正在播放音频。
        _audio_active_started_ts: 最近一次开始播放音频的时间戳。
        _last_audio_chunk_ts: 最近一次音频块的时间戳。
        _audio_lock: 音频锁，用于保护音频缓冲区的访问。
        _playback_buffer: 播放缓冲区，用于存储待播放的音频数据。
        audio_queue: 音频队列，用于存储待播放的音频块。
        _playback_start_delay_sec: 播放开始延迟时间，单位为秒。
        _playback_hangover_sec: 播放挂起时间，单位为秒。

    """

    _stop_event: threading.Event
    _interrupt_event: threading.Event
    _playback_started_event: threading.Event
    is_sounding: bool
    _audio_active_started_ts: float
    _last_audio_chunk_ts: float
    _audio_lock: threading.Lock
    _playback_buffer: np.ndarray
    audio_queue: "queue.Queue[bytes]"
    _playback_start_delay_sec: float
    _playback_hangover_sec: float


class AudioQueueOutputStream:
    """基于 sounddevice.OutputStream 的音频输出流实现，从提供的队列中读取 PCM 音频数据进行播放。

    Args:
        owner: AudioStreamOwner 实例，提供播放状态和控制事件。
        sample_rate: 音频采样率，单位为 Hz。
        channels: 音频通道数 （例如单声道为 1，立体声为 2）。
        buffer_size: 音频缓冲区大小，单位为样本数。
        dtype: 音频数据类型，例如 "int16"。
    """

    def __init__(
        self,
        owner: AudioStreamOwner,
        *,
        sample_rate: int,
        channels: int,
        buffer_size: int,
        dtype: str,
    ) -> None:
        if sd is None:
            raise RuntimeError("sounddevice 未安装，无法创建音频输出流")

        self._owner = owner
        self._channels = channels
        self._dtype = np.dtype(dtype)
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype=dtype,
            blocksize=buffer_size,
            latency="low",
            callback=self._audio_callback,
        )

    def start(self) -> None:
        """启动音频输出流"""
        self._stream.start()

    def stop(self) -> None:
        """停止音频输出流"""
        self._stream.stop()

    def close(self) -> None:
        """关闭音频输出流"""
        self._stream.close()

    @property
    def active(self) -> bool:
        """音频输出流是否处于活动状态"""
        return bool(getattr(self._stream, "active", False))

    def _audio_callback(self, outdata, frames, time_info, status) -> None:
        """sounddevice 输出流回调函数，从 AudioStreamOwner 的音频队列中读取 PCM 数据填充输出缓冲区，并管理播放状态"""
        del time_info
        owner = self._owner
        now = time.monotonic()

        if status:
            logger.debug(f"音频回调状态: {status}")

        if owner._stop_event.is_set() or owner._interrupt_event.is_set():
            outdata.fill(0)
            owner.is_sounding = False
            owner._audio_active_started_ts = 0.0
            owner._last_audio_chunk_ts = 0.0
            owner._playback_started_event.clear()
            return

        filled = 0
        with owner._audio_lock:
            while filled < frames:
                if owner._playback_buffer.shape[0] == 0:
                    try:
                        chunk = owner.audio_queue.get_nowait()
                    except queue.Empty:
                        break

                    pcm = np.frombuffer(chunk, dtype=self._dtype)
                    if pcm.size == 0:
                        continue
                    if pcm.size % self._channels != 0:
                        logger.warning("丢弃未对齐的音频块")
                        continue
                    owner._playback_buffer = np.ascontiguousarray(
                        pcm.reshape(-1, self._channels)
                    )

                take = min(frames - filled, owner._playback_buffer.shape[0])
                outdata[filled : filled + take] = owner._playback_buffer[:take]
                owner._playback_buffer = owner._playback_buffer[take:]
                filled += take

        if filled < frames:
            outdata[filled:].fill(0)

        if filled > 0:
            if owner._audio_active_started_ts <= 0.0:
                owner._audio_active_started_ts = now
            owner._last_audio_chunk_ts = now
            owner.is_sounding = (
                now - owner._audio_active_started_ts
            ) >= owner._playback_start_delay_sec
            if owner.is_sounding:
                owner._playback_started_event.set()
        else:
            keep_active = (
                now - owner._last_audio_chunk_ts
            ) < owner._playback_hangover_sec
            owner.is_sounding = keep_active
            if not keep_active:
                owner._audio_active_started_ts = 0.0
                owner._playback_started_event.clear()
