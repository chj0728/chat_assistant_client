import queue
import threading
from dataclasses import dataclass, field


@dataclass(slots=True)
class TTSBackendContext:
    """TTS 后端上下文，包含后端运行时所需的各种参数和状态。

    Args:
        timeout: 请求超时时间，单位为秒。
        text_queue: 文本输入队列，TTS worker 从中获取待合成的文本。
        audio_queue: 音频输出队列，TTS worker 将合成的音频数据放入其中。
        stop_event: 停止事件，用于通知 TTS worker 停止运行。
        interrupt_event: 中断事件，用于通知 TTS worker 立即停止当前合成并清空状态。
    """

    timeout: float = 10.0
    text_queue: queue.Queue[str] = field(default_factory=queue.Queue)
    audio_queue: queue.Queue[bytes] = field(default_factory=queue.Queue)
    stop_event: threading.Event = field(default_factory=threading.Event)
    interrupt_event: threading.Event = field(default_factory=threading.Event)
