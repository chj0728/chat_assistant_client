import queue
import threading
from typing import Protocol

import numpy as np


class OutputStreamProtocol(Protocol):
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
