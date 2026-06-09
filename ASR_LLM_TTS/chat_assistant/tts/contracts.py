import queue
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class TTSBackendContext:
    """TTS 后端上下文，包含后端运行时所需的各种参数和状态。

    Args:
        host: TTS 服务主机地址。
        port: TTS 服务端口号。
        timeout: 请求超时时间，单位为秒。
        sample_rate: 音频采样率，单位为 Hz。
        channels: 音频通道数 （例如单声道为 1，立体声为 2）。
        chunk_size: 音频块大小，单位为样本数。
        text_queue: 文本输入队列，TTS worker 从中获取待合成的文本。
        audio_queue: 音频输出队列，TTS worker 将合成的音频数据放入其中。
        stop_event: 停止事件，用于通知 TTS worker 停止运行。
        interrupt_event: 中断事件，用于通知 TTS worker 立即停止当前合成并清空状态。
        speaker_id: 说话人 ID，用于指定 TTS 说话人。
        speed: 语速，默认为 1.0
        use_websocket: 是否使用 WebSocket 连接 TTS 服务。
        ws_path: WebSocket 连接路径，默认为 "/ws/api/tts"。
        ws_ping_interval: WebSocket ping 间隔时间，单位为秒。
        ws_ping_timeout: WebSocket ping 超时时间，单位为秒。
        voice: 语音名称，用于指定 TTS 语音。
        api_key: API 密钥，用于远端 TTS 认证。
        model: 模型名称，用于远端 TTS 选择模型。
        remote_url: 远端 TTS 服务 URL，格式为 "host:port"。
        remote_mode: 远端 TTS 模式，默认为 "commit": 由客户端主动提交文本缓冲区以触发合成，适合需要精确控制合成时机的场景（如对话式 AI 逐轮合成）
                                    server_commit : 由服务端智能处理文本分段与合成时机，适合大段文本的连续合成场景。客户端只需持续追加文本，无需关注分段和提交。
    """

    host: str
    port: int
    timeout: float
    sample_rate: int
    channels: int
    chunk_size: int
    text_queue: queue.Queue[str]
    audio_queue: queue.Queue[bytes]
    stop_event: threading.Event
    interrupt_event: threading.Event
    speaker_id: int = 0
    speed: float = 1.0
    use_websocket: bool = False
    ws_path: str = "/ws/api/tts"
    ws_ping_interval: Optional[float] = None
    ws_ping_timeout: Optional[float] = None
    voice: str = "Cherry"
    api_key: Optional[str] = None
    model: str = "qwen3-tts-flash-realtime"
    remote_url: Optional[str] = None
    remote_mode: str = "commit"
