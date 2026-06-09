import queue
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Protocol

from logger import logger

WORKER_POLL_TIMEOUT_SEC = 0.1


class TTSBackendBase(ABC):
    """TTS 后端生命周期接口，只保留对外可见的基本控制入口。"""

    @abstractmethod
    def initialize_if_needed(self) -> None:
        """按需初始化运行时资源。"""

    @abstractmethod
    def start(self) -> threading.Thread:
        """启动 TTS worker 线程。"""

    @abstractmethod
    def close(self) -> None:
        """关闭运行时并释放资源。"""


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


class TTSRuntime(Protocol):
    """TTS 后端运行时Protocol，定义了后端运行时需要实现的接口方法。"""

    def initialize_if_needed(self) -> None:
        """按需初始化运行时资源。"""
        ...

    def close_runtime(self) -> None:
        """关闭运行时并释放资源。"""
        ...

    def tts_infer(self, text: str) -> None:
        """执行 TTS 推理，将合成的音频数据块放入音频队列供播放线程使用。
        Args:
            text: 待合成文本。
        """
        ...

    def generate_wav(self, text: str, filename: str) -> bool:
        """生成 WAV 文件。
        Args:
            text: 待合成文本。
            filename: 输出 WAV 文件名。
        Returns:
            bool: 是否生成成功。
        """
        ...

    def change_voice(self, voice: str) -> None:
        """更改语音设置，适用于支持多语音的 TTS 后端。
        Args:
            voice: 语音名称。
        """
        ...


class TTSBackend(TTSBackendBase):
    """TTS 后端实现类，负责管理 TTS 运行时的生命周期，并提供对外的控制接口。
    Args:
        context: TTSBackendContext 实例，包含后端运行时所需的各种参数和状态。
        runtime: TTSRuntime 实例，提供 TTS 合成的具体实现。
        worker_thread_name: TTS worker 线程名称，默认为 "tts-worker"。
        request_error_log_prefix: TTS 请求错误日志前缀，默认为 "TTS 请求失败"。
        transfer_elapsed_log_label: 音频传输耗时日志标签，默认为 "音频传输耗时"。
    """

    def __init__(
        self,
        *,
        context: TTSBackendContext,
        runtime: TTSRuntime,
        worker_thread_name: str = "tts-worker",
        request_error_log_prefix: str = "TTS 请求失败",
        transfer_elapsed_log_label: str = "音频传输耗时",
    ) -> None:
        self._context = context
        self._runtime = runtime
        self._worker_thread_name = worker_thread_name
        self._request_error_log_prefix = request_error_log_prefix
        self._transfer_elapsed_log_label = transfer_elapsed_log_label

    def _tts_loop(self) -> None:
        """TTS 后端主循环，用于处理文本队列并调用运行时进行 TTS 合成。"""
        while not self._context.stop_event.is_set():
            try:
                text = self._context.text_queue.get(timeout=WORKER_POLL_TIMEOUT_SEC)
            except queue.Empty:
                continue

            start_time = time.time()
            try:
                self._runtime.tts_infer(text)
            except Exception as e:
                logger.error(f"{self._request_error_log_prefix}: {e}")
            finally:
                elapsed_time = time.time() - start_time
                logger.debug(
                    f"{self._transfer_elapsed_log_label}: {elapsed_time:.2f} 秒"
                )

    ### TTSBackendBase 接口实现 ###
    def initialize_if_needed(self) -> None:
        self._runtime.initialize_if_needed()

    def start(self) -> threading.Thread:
        tts_thread = threading.Thread(
            target=self._tts_loop,
            daemon=True,
            name=self._worker_thread_name,
        )
        tts_thread.start()
        return tts_thread

    def close(self) -> None:
        self._runtime.close_runtime()

    #################################

    ####### TTS 后端运行时接口 #######
    def change_voice(self, voice: str) -> None:
        """更改语音设置，适用于支持多语音的 TTS 后端。"""
        self._context.voice = voice
        self._runtime.change_voice(voice)

    def request_stream(self, text: str, data_type: str):
        """请求音频流，适用于支持音频流的 TTS 后端。"""
        request_stream = getattr(self._runtime, "request_stream", None)
        if not callable(request_stream):
            raise NotImplementedError("当前 TTS 后端不支持请求音频流")
        return request_stream(text, data_type)

    def generate_wav(self, text: str, filename: str) -> bool:
        """生成 WAV 文件，适用于支持生成 WAV 的 TTS 后端。"""
        return self._runtime.generate_wav(text, filename)
