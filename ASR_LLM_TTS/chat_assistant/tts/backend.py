import queue
import threading
import time
from abc import ABC, abstractmethod

from logger import logger

from .backend_context import TTSBackendContext
from .runtimes.protocol import TTSRuntimeProtocol
from .stream.protocol import MyOutputStreamProtocol

WORKER_POLL_TIMEOUT_SEC = 0.1


class TTSBackendBase(ABC):
    """TTS 后端生命周期接口，只保留对外可见的基本控制入口。"""

    @abstractmethod
    def on_start(self) -> None:
        """初始化运行时资源。"""

    @abstractmethod
    def on_stop(self) -> None:
        """关闭运行时资源。"""


class MyTTSBackend(TTSBackendBase):
    def __init__(
        self,
        tts_backend_context: TTSBackendContext,
        tts_runtime: TTSRuntimeProtocol,
        output_stream: MyOutputStreamProtocol,
        worker_thread_name: str = "tts-worker",
        request_error_log_prefix: str = "TTS 请求失败",
        transfer_elapsed_log_label: str = "音频传输耗时",
    ) -> None:
        self.tts_backend_context = tts_backend_context
        self.tts_runtime = tts_runtime
        self.output_stream = output_stream
        self.worker_thread_name = worker_thread_name
        self.request_error_log_prefix = request_error_log_prefix
        self.transfer_elapsed_log_label = transfer_elapsed_log_label
        self.worker_loop_thread: threading.Thread | None = None

    def worker_loop(self) -> None:
        while not self.tts_backend_context.stop_event.is_set():
            try:
                text = self.tts_backend_context.text_queue.get(
                    timeout=WORKER_POLL_TIMEOUT_SEC
                )
            except queue.Empty:
                continue

            start_time = time.time()
            try:
                self.tts_runtime.tts_infer(text)
            except (OSError, RuntimeError, ValueError) as e:
                logger.error(f"{self.request_error_log_prefix}: {e}")
            finally:
                elapsed_time = time.time() - start_time
                logger.debug(
                    f"{self.transfer_elapsed_log_label}: {elapsed_time:.2f} 秒"
                )

    ############ 实例化基类接口 ############
    def on_start(self) -> None:

        self.worker_loop_thread = threading.Thread(
            target=self.worker_loop,
            daemon=True,
            name=self.worker_thread_name,
        )
        self.worker_loop_thread.start()

        self.tts_runtime.start()

        self.output_stream.start()

    def on_stop(self) -> None:

        self.tts_backend_context.stop_event.set()
        if self.worker_loop_thread is not None:
            self.worker_loop_thread.join(timeout=3.0)
        self.tts_backend_context.stop_event.clear()

        self.tts_runtime.stop()

        self.output_stream.stop()
        self.output_stream.close()
        logger.info("TTS 后端已停止")

    ########################################

    def generate_wav(self, text: str, filename: str) -> bool:
        return self.tts_runtime.generate_wav(text, filename)

    def interrupt(self) -> None:
        self.tts_runtime.interrupt()
        self.output_stream.interrupt()

    def is_active(self) -> bool:
        return self.output_stream.is_sounding_flag()

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        if self.is_active():
            return True
        return self.output_stream.wait_until_playback_starts(timeout_sec)
