import queue
import threading
import time
from typing import Any

import numpy as np
from logger import logger

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    sd = None

from ..backend_context import TTSBackendContext
from .protocol import MyOutputStreamProtocol


def _apply_playback_gain(pcm: np.ndarray, gain: float) -> np.ndarray:
    """应用播放增益并按 PCM 数据类型裁剪，避免削波失真。"""
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
    """Sounddevice based streaming PCM player for TTS output."""

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
        device: int | str | None = None,
    ) -> None:
        """初始化输出流参数、播放状态和 sounddevice 输出流。"""
        self.context = context

        if sd is None:
            raise RuntimeError("sounddevice 未安装，无法创建音频输出流")

        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer_size = buffer_size
        self.dtype = dtype

        self.audio_lock = threading.Lock()
        self.playback_start_delay_sec = playback_start_delay_sec
        self.playback_hangover_sec = playback_hangover_sec
        self.playback_gain = max(playback_gain, 0.0)

        self.stop_event = threading.Event()
        self.interrupt_event = threading.Event()
        self.playback_started_event = threading.Event()
        self.output_stream = self._create_output_stream(device)
        self._reset_playback_state()

    def _create_output_stream(self, device: int | str | None) -> Any:
        """创建 sounddevice 输出流。"""
        if sd is None:
            raise RuntimeError("sounddevice 未安装，无法创建音频输出流")
        return sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.buffer_size,
            latency="low",
            callback=self._audio_callback,
            device=self._resolve_output_device(device),
        )

    def _resolve_output_device(self, device: int | str | None) -> int | str | None:
        """列出输出设备并解析最终传给 sounddevice 的设备标识。"""
        if sd is None:
            raise RuntimeError("sounddevice 未安装，无法创建音频输出流")
        devices = sd.query_devices()
        output_devices = [
            (idx, info)
            for idx, info in enumerate(devices)
            if info["max_output_channels"] > 0
        ]

        logger.info(f"共发现 {len(output_devices)} 个音频输出设备:")
        for idx, info in output_devices:
            hostapi = sd.query_hostapis(info["hostapi"])["name"]
            logger.info(
                f"  [{idx}] {info['name']} "
                f"(max_output_channels={info['max_output_channels']}, "
                f"default_samplerate={info['default_samplerate']}, hostapi={hostapi})"
            )

        if device is not None:
            if isinstance(device, int) and device < len(devices):
                logger.info(f"使用指定输出设备: [{device}] {devices[device]['name']}")
            else:
                logger.info(f"使用指定输出设备: {device}")
            return device

        default_device = sd.default.device[1]
        if default_device is not None and default_device < len(devices):
            logger.info(
                f"使用系统默认输出设备: [{default_device}] "
                f"{devices[default_device]['name']}"
            )
            return default_device

        logger.info("使用 sounddevice 自动选择的默认设备")
        return None

    def _audio_callback(self, outdata, frames, time_info, status) -> None:
        """sounddevice 回调：填充输出缓冲并更新播放状态。"""
        del time_info
        now = time.monotonic()

        if status:
            logger.debug(f"音频回调状态: {status}")

        if self.stop_event.is_set() or self.interrupt_event.is_set():
            outdata.fill(0)
            self._reset_playback_state()
            return

        with self.audio_lock:
            filled = self._fill_output_buffer(outdata, frames)

        if filled < frames:
            outdata[filled:].fill(0)

        self._update_playback_state(filled > 0, now)

    def _fill_output_buffer(self, outdata, frames: int) -> int:
        """从内部缓冲和 TTS 队列取音频，尽量填满本次输出帧。"""
        filled = 0
        while filled < frames:
            if self.playback_buffer.shape[0] == 0 and not self._load_next_chunk():
                break

            take = min(frames - filled, self.playback_buffer.shape[0])
            outdata[filled : filled + take] = self.playback_buffer[:take]
            self.playback_buffer = self.playback_buffer[take:]
            filled += take

        return filled

    def _load_next_chunk(self) -> bool:
        """从音频队列读取下一个 PCM 块并放入播放缓冲。"""
        while True:
            try:
                chunk = self.context.audio_queue.get_nowait()
            except queue.Empty:
                return False

            pcm = np.frombuffer(chunk, dtype=self.dtype)
            pcm = _apply_playback_gain(pcm, self.playback_gain)
            if pcm.size == 0:
                continue
            if pcm.size % self.channels != 0:
                logger.warning("丢弃未对齐的音频块")
                continue

            self.playback_buffer = np.ascontiguousarray(pcm.reshape(-1, self.channels))
            return True

    def _update_playback_state(self, has_audio: bool, now: float) -> None:
        """根据输出帧是否包含音频更新播放状态和起播事件。"""
        if has_audio:
            if self.audio_active_started_ts <= 0.0:
                self.audio_active_started_ts = now
            self.last_audio_chunk_ts = now
            self.is_sounding = (
                now - self.audio_active_started_ts
            ) >= self.playback_start_delay_sec
            if self.is_sounding:
                self.playback_started_event.set()
            return

        keep_active = (now - self.last_audio_chunk_ts) < self.playback_hangover_sec
        self.is_sounding = keep_active
        if not keep_active:
            self.audio_active_started_ts = 0.0
            self.playback_started_event.clear()

    def _reset_playback_state(self) -> None:
        """清空播放缓冲、时间戳和起播事件。"""
        with self.audio_lock:
            self.playback_buffer = np.empty((0, self.channels), dtype=self.dtype)
            self.audio_active_started_ts = 0.0
            self.last_audio_chunk_ts = 0.0
        self.is_sounding = False
        self.playback_started_event.clear()

    def start(self) -> None:
        """启动音频输出流。"""
        self.output_stream.start()

    def stop(self) -> None:
        """停止音频输出流并清理播放状态。"""
        self.output_stream.stop()
        self._reset_playback_state()

    def close(self) -> None:
        """关闭音频输出流并释放底层资源。"""
        self.output_stream.close()

    def interrupt(self) -> None:
        """短暂置位中断信号，清空当前播放缓冲。"""
        self.interrupt_event.set()
        time.sleep(0.2)
        self._reset_playback_state()
        self.interrupt_event.clear()

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        """等待音频进入确认播放状态。"""
        return self.playback_started_event.wait(timeout=timeout_sec)

    def is_sounding_flag(self) -> bool:
        """返回当前是否处于播放状态。"""
        return self.is_sounding
