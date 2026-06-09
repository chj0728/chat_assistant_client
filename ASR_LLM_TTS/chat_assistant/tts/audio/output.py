import queue
import time

import numpy as np
from logger import logger

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    sd = None

from .protocol import OutputStreamProtocol


class AudioQueueOutputStream:
    def __init__(
        self,
        owner: OutputStreamProtocol,
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
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()

    @property
    def active(self) -> bool:
        return bool(getattr(self._stream, "active", False))

    def _audio_callback(self, outdata, frames, time_info, status) -> None:
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
