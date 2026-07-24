import queue
import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class ASRAudioData:
    """一次完整语音片段，同时保留 ASR 与 PCM 边界所需的数据。"""

    samples: np.ndarray
    pcm16_bytes: bytes


@dataclass(slots=True)
class ASRBackendContext:
    """ASR 后端上下文，包含后端运行时所需的各种参数和状态。

    Args:
        sample_rate: 音频采样率，单位为 Hz。
        channels: 音频通道数 （例如单声道为 1，立体声为 2）。
        chunk_size: 音频块大小，单位为样本数。
        samples_per_message: 每条消息包含的样本数。
        seconds_per_message: 模拟实时发送时，每条消息的时间长度，单位为秒。
        text_queue: 文本输出队列，ASR worker 将识别结果文本放入其中。
        audio_data_queue: (音频数据, 音频待保存路径) 输入队列，供 ASR worker 识别。
        result_data_queue: (asr_result, voice_id_result, audio_saved_path) 输出队列，ASR worker 将文本识别结果、声纹识别结果和音频保存路径放入其中供外部使用。
        stop_event: 停止事件，用于通知 ASR worker 停止运行。
        interrupt_event: 中断事件，用于通知 ASR worker 立即停止当前识别并清空状态。
    """

    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    samples_per_message: int = 8000
    seconds_per_message: float = 0.1
    # asr_text_queue: queue.Queue[str] = queue.Queue(maxsize=10)
    # audio_frames_queue: queue.Queue[bytes] = queue.Queue(maxsize=10)
    audio_data_queue: queue.Queue[tuple[ASRAudioData, str | None]] = field(
        default_factory=lambda: queue.Queue(maxsize=10)
    )
    # asr_voice_result_queue: queue.Queue[tuple[str, Any | None]] = queue.Queue(
    #     maxsize=10
    # )
    # (asr_result, voice_id_result,audio_saved_path) 文本识别结果、声纹识别结果和音频保存路径队列，供外部使用
    result_data_queue: queue.Queue[tuple[str, Any | None, str | None]] = field(
        default_factory=lambda: queue.Queue(maxsize=10)
    )
    vision_id: str | None = None
    # voice_id: Optional[str] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    interrupt_event: threading.Event = field(default_factory=threading.Event)
