import queue
import threading
import time
from abc import ABC, abstractmethod

from logger import logger

from .contracts import TTSBackendContext
from .runtimes.protocol import TTSRuntimeProtocol

WORKER_POLL_TIMEOUT_SEC = 0.1


class TTSBackendBase(ABC):
    """TTS 后端生命周期接口，只保留对外可见的基本控制入口。"""

    # @abstractmethod
    # def initialize_if_needed(self) -> None:
    #     """按需初始化运行时资源。"""
    #     pass

    @abstractmethod
    def on_start(self) -> threading.Thread:
        """初始化运行时资源。"""
        pass

    @abstractmethod
    def on_stop(self) -> None:
        """关闭运行时资源。"""
        pass


class TTSBackend(TTSBackendBase):
    """TTS 后端实现类，负责管理 TTS 运行时的生命周期，并提供对外的控制接口。

    Args:
        context: TTSBackendContext 实例，包含后端运行时所需的各种参数和状态。
        runtime: TTSRuntimeProtocol 实例，提供 TTS 合成的具体实现。
        worker_thread_name: TTS worker 线程名称，默认为 "tts-worker"。
        request_error_log_prefix: TTS 请求错误日志前缀，默认为 "TTS 请求失败"。
        transfer_elapsed_log_label: 音频传输耗时日志标签，默认为 "音频传输耗时"。
    """

    def __init__(
        self,
        *,
        context: TTSBackendContext,
        runtime: TTSRuntimeProtocol,
        worker_thread_name: str = "tts-worker",
        request_error_log_prefix: str = "TTS 请求失败",
        transfer_elapsed_log_label: str = "音频传输耗时",
    ) -> None:
        self._context = context
        self._runtime = runtime
        self._worker_thread_name = worker_thread_name
        self._request_error_log_prefix = request_error_log_prefix
        self._transfer_elapsed_log_label = transfer_elapsed_log_label
        self.worker_loop_thread: threading.Thread | None = None

    def worker_loop(self) -> None:
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

    def on_start(self) -> None:

        self.worker_loop_thread = threading.Thread(
            target=self.worker_loop,
            daemon=True,
            name=self._worker_thread_name,
        )
        self.worker_loop_thread.start()

        self._runtime.initialize_if_needed()

    def on_stop(self) -> None:

        if self.worker_loop_thread is not None:
            self.worker_loop_thread.join(timeout=3.0)

        self._runtime.close_runtime()

    def change_voice(self, voice: str) -> None:
        self._context.voice = voice
        self._runtime.change_voice(voice)

    def request_stream(self, text: str, data_type: str):
        request_stream = getattr(self._runtime, "request_stream", None)
        if not callable(request_stream):
            raise NotImplementedError("当前 TTS 后端不支持请求音频流")
        return request_stream(text, data_type)

    def generate_wav(self, text: str, filename: str) -> bool:
        return self._runtime.generate_wav(text, filename)
