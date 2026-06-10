import queue
import threading
from typing import Protocol

import numpy as np


class OutputStreamProtocol(Protocol):
    """音频输出流协议，定义了 TTS 客户端与音频输出流之间的交互接口和必要的属性，具体的音频输出流实现需要遵循该协议以确保与 TTS 客户端的兼容性和正确的功能实现。

    Args:
        audio_queue: 音频数据队列，用于存储待播放的音频数据块，音频输出流会从该队列中读取数据进行播放。
        is_sounding: 是否正在播放音频的状态标志，TTS 客户端通过该属性可以判断当前是否有音频正在播放。
        _audio_active_started_ts: 音频开始播放的时间戳，用于判断音频播放状态和实现相关的播放逻辑。
        _last_audio_chunk_ts: 上一次音频数据块被处理的时间戳，用于实现播放状态的挂起和恢复逻辑。
        _audio_lock: 音频数据访问锁，确保在多线程环境下对音频数据的安全访问和修改。
        _playback_buffer: 音频播放缓冲区，用于存储当前正在播放的音频数据块，确保连续播放和处理音频数据。
        _playback_start_delay_sec: 播放起播确认延迟秒数，用于判断音频播放状态的起播条件，确保在音频数据连续播放达到一定时间后才确认进入播放状态。
        _playback_hangover_sec: 播放挂起秒数，用于在音频数据短暂中断时保持播放状态，避免因回调调度抖动导致的状态频繁切换。
        _stop_event: 停止事件，用于控制音频输出流的停止，当该事件被设置时，音频输出流应立即停止播放并清空相关状态。
        _interrupt_event: 中断事件，用于控制音频输出流的中断，当该事件被设置时，音频输出流应立即中断当前播放并清空相关状态。
        _playback_started_event: 播放开始事件，用于通知 TTS 客户端音频播放已经开始，当音频播放状态进入播放状态时应设置该事件，反之则应清除该事件。

    """

    audio_queue: "queue.Queue[bytes]"
    is_sounding: bool
    _audio_active_started_ts: float
    _last_audio_chunk_ts: float
    _audio_lock: threading.Lock
    _playback_buffer: np.ndarray
    _playback_start_delay_sec: float
    _playback_hangover_sec: float
    _stop_event: threading.Event
    _interrupt_event: threading.Event
    _playback_started_event: threading.Event
