import asyncio
import json
import os
import queue
import socket
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable

from logger import logger

from .asr_backend_context import ASRAudioData, ASRBackendContext
from .runtimes.protocol import ASRRuntimeProtocol
from .stream.protocol import InputStreamProtocol

try:
    from voice.voice_recognizer import VoiceRecognizer
except ImportError:
    VoiceRecognizer = None

from config import get_vad_no_speech_threshold

TAIL_SILENCE_MS = int(get_vad_no_speech_threshold() * 1000)

# 外部 ASR 文本推送服务：每行一个 UTF-8 JSON，例如 {"text": "..."}
EXTERNAL_ASR_TEXT_HOST = os.environ.get("EXTERNAL_ASR_TEXT_HOST", "192.168.10.101")
EXTERNAL_ASR_TEXT_PORT = int(os.environ.get("EXTERNAL_ASR_TEXT_PORT", "9103"))
EXTERNAL_ASR_RECONNECT_SECONDS = float(
    os.environ.get("EXTERNAL_ASR_RECONNECT_SECONDS", "1.0")
)
EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS = float(
    os.environ.get("EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS", "1.0")
)


class ASRBackendBase(ABC):
    """ASR 后端生命周期接口，只保留对外可见的基本控制入口。"""

    @abstractmethod
    def start(self) -> None:
        """初始化运行时资源。"""

    @abstractmethod
    def stop(self) -> None:
        """关闭运行时资源。"""


class ASRBackend(ASRBackendBase):
    """管理 ASR 运行时、音频输入、声纹识别和后台工作线程。"""

    def __init__(
        self,
        asr_backend_context: ASRBackendContext,
        asr_runtime: ASRRuntimeProtocol,
        asr_input_stream: InputStreamProtocol,
        **kwargs,
    ) -> None:
        self.asr_backend_context = asr_backend_context
        self.asr_runtime = asr_runtime
        self.asr_input_stream = asr_input_stream
        self.asr_worker_thread: threading.Thread | None = None

        self.enable_external_asr: bool = kwargs.get("enable_external_asr", False)
        self.external_asr_text_worker_thread: threading.Thread | None = None
        self._external_asr_socket: socket.socket | None = None
        self._external_asr_socket_lock = threading.Lock()
        self.external_asr_text_host = kwargs.get(
            "EXTERNAL_ASR_TEXT_HOST", EXTERNAL_ASR_TEXT_HOST
        )
        self.external_asr_text_port = kwargs.get(
            "EXTERNAL_ASR_TEXT_PORT", EXTERNAL_ASR_TEXT_PORT
        )
        self.external_asr_reconnect_seconds = kwargs.get(
            "EXTERNAL_ASR_RECONNECT_SECONDS", EXTERNAL_ASR_RECONNECT_SECONDS
        )
        self.external_asr_socket_timeout_seconds = kwargs.get(
            "EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS", EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS
        )

        if VoiceRecognizer is not None:
            self.voice_recognizer = VoiceRecognizer(
                low_thresh=0.60, high_thresh=0.67, max_prints_per_id=1
            )
        else:
            self.voice_recognizer = None

    def asr_worker_loop(self) -> None:
        """ASR 后端工作线程主循环，持续监听音频输入队列，触发 ASR 推理请求。"""

        while not self.asr_backend_context.stop_event.is_set():
            try:
                audio_data, audio_saved_path = (
                    self.asr_backend_context.audio_data_queue.get(timeout=0.1)
                )
            except queue.Empty:
                continue

            start_time = time.time()
            try:
                asr_text, voice_id = asyncio.run(
                    self.async_asr_voice_recognize_audio(audio_data)
                )
                self.asr_backend_context.result_data_queue.put(
                    (asr_text, voice_id, audio_saved_path)
                )
            except (OSError, RuntimeError, ValueError) as exc:
                logger.error(
                    f"[vision_id: {self.asr_backend_context.vision_id}] "
                    f"[ASR + Voice] 推理失败: {exc}"
                )
            finally:
                elapsed_time = time.time() - start_time
                logger.info(
                    f"[vision_id: {self.asr_backend_context.vision_id}] [ASR + Voice] 推理耗时: {elapsed_time:.3f} 秒"
                )

    def external_asr_text_worker_loop(self) -> None:
        """订阅外部 ASR 文本服务，将每条 text 写入统一的 ASR 结果队列。"""
        reconnect_delay = self.external_asr_reconnect_seconds

        while not self.asr_backend_context.stop_event.is_set():
            sock: socket.socket | None = None
            try:
                logger.info(
                    f"[External ASR] 正在连接 "
                    f"{self.external_asr_text_host}:{self.external_asr_text_port}"
                )
                sock = socket.create_connection(
                    (self.external_asr_text_host, self.external_asr_text_port),
                    timeout=self.external_asr_socket_timeout_seconds,
                )
                sock.settimeout(self.external_asr_socket_timeout_seconds)

                with self._external_asr_socket_lock:
                    self._external_asr_socket = sock

                reconnect_delay = self.external_asr_reconnect_seconds
                recv_buffer = b""
                logger.info(
                    f"[External ASR] 已连接 "
                    f"{self.external_asr_text_host}:{self.external_asr_text_port}"
                )

                while not self.asr_backend_context.stop_event.is_set():
                    try:
                        data = sock.recv(4096)
                    except TimeoutError:
                        continue

                    if not data:
                        raise ConnectionError("服务端已断开连接")

                    recv_buffer += data
                    while b"\n" in recv_buffer:
                        raw_line, recv_buffer = recv_buffer.split(b"\n", 1)
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue

                        try:
                            payload = json.loads(raw_line.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as e:
                            logger.warning(f"[External ASR] 忽略非法 JSON 行: {e}")
                            continue

                        text = (
                            payload.get("text") if isinstance(payload, dict) else None
                        )
                        if not isinstance(text, str):
                            logger.warning(
                                f"[External ASR] 忽略缺少 text 字段的消息: {payload!r}"
                            )
                            continue

                        text = text.strip()
                        if not text:
                            continue

                        # 外部服务不提供声纹和音频路径，统一以 None 入队。
                        self.asr_backend_context.result_data_queue.put(
                            (text, None, None)
                        )
                        logger.info(f"[External ASR] 收到文本: {text}")

            except OSError as e:
                if not self.asr_backend_context.stop_event.is_set():
                    logger.warning(
                        f"[External ASR] 连接/读取失败: {e}；"
                        f"{reconnect_delay:.1f} 秒后重连"
                    )
                    self.asr_backend_context.stop_event.wait(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2.0, 10.0)
            finally:
                if sock is not None:
                    with self._external_asr_socket_lock:
                        if self._external_asr_socket is sock:
                            self._external_asr_socket = None
                    try:
                        sock.close()
                    except OSError:
                        pass

        logger.info("[External ASR] worker 线程已退出")

    def _close_external_asr_socket(self) -> None:
        """主动关闭 socket，解除 recv 阻塞，让 stop() 不必等待超时。"""
        with self._external_asr_socket_lock:
            sock = self._external_asr_socket
            self._external_asr_socket = None

        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def start(self) -> None:
        """初始化 ASR 后端资源，启动 ASR worker 线程和音频输入流。"""

        self.asr_runtime.start()

        if not self.enable_external_asr:
            self.asr_input_stream.start()

        self.asr_worker_thread = threading.Thread(
            target=self.asr_worker_loop, daemon=True, name="asr-worker"
        )
        self.asr_worker_thread.start()

        if self.enable_external_asr:
            self.external_asr_text_worker_thread = threading.Thread(
                target=self.external_asr_text_worker_loop,
                daemon=True,
                name="external-asr-text-worker",
            )
            self.external_asr_text_worker_thread.start()
            logger.info("[External ASR] worker 线程已启动")

        logger.info("ASR 后端已启动")

    def stop(self) -> None:
        """停止 ASR 后端资源，通知 ASR worker 线程和音频输入流停止运行。"""

        self.asr_backend_context.stop_event.set()

        self._close_external_asr_socket()

        if self.asr_worker_thread and self.asr_worker_thread.is_alive():
            self.asr_worker_thread.join()
            logger.info("ASR worker 线程已停止")

        if (
            self.enable_external_asr
            and self.external_asr_text_worker_thread
            and self.external_asr_text_worker_thread.is_alive()
        ):
            self.external_asr_text_worker_thread.join()
            logger.info("[External ASR] worker 线程已停止")

        self.asr_input_stream.stop()
        self.asr_runtime.stop()
        logger.info("ASR 后端已停止")

    def update_vision_id(self, vision_id: str | None) -> None:
        """更新当前视觉ID，供ASR后端使用。"""
        self.asr_backend_context.vision_id = vision_id

    def recognize(self, wav_path: str) -> str:
        """识别指定 WAV 文件，返回识别结果文本。"""
        return self.asr_runtime.asr_infer_wav_path(wav_path)

    def recognize_frames(self, audio_frames: bytes) -> str:
        """识别指定音频帧数据，返回识别结果文本。"""
        return self.asr_runtime.asr_infer_frames(audio_frames)

    def recognize_pcm16_bytes(self, pcm16_bytes: bytes) -> str:
        """识别指定 PCM16 bytes 音频数据，返回识别结果文本。"""
        return self.asr_runtime.asr_infer_pcm16_bytes(pcm16_bytes)

    async def async_recognize_frames(self, audio_frames: bytes) -> str:
        """异步识别指定音频帧数据，返回识别结果文本。"""
        return await asyncio.to_thread(self.asr_runtime.asr_infer_frames, audio_frames)

    async def async_recognize_pcm16_bytes(self, pcm16_bytes: bytes) -> str:
        """异步识别指定 PCM16 bytes 音频数据，返回识别结果文本。"""
        return await asyncio.to_thread(
            self.asr_runtime.asr_infer_pcm16_bytes, pcm16_bytes
        )

    async def async_recognize_audio(self, audio_data: ASRAudioData) -> str:
        """直接使用采集阶段保留的 float32 音频执行识别。"""
        return await asyncio.to_thread(
            self.asr_runtime.asr_infer_samples,
            audio_data.samples,
        )

    async def _recognize_with_voice(
        self, asr_result: Awaitable[str], pcm16_bytes: bytes
    ) -> tuple[str, str | None]:
        """并行执行 ASR 与可选声纹识别，并统一整理声纹结果。"""
        logger.debug(
            f"基于 vision_id:[ {self.asr_backend_context.vision_id} ] "
            "的 ASR + Voice 识别正在进行中..."
        )
        voice_result = (
            self.voice_recognizer.recognize_async(
                pcm16_bytes,
                user_id=self.asr_backend_context.vision_id,
                tail_silence_ms=TAIL_SILENCE_MS,
            )
            if self.voice_recognizer is not None
            else asyncio.sleep(0, result=None)
        )
        asr_text, voice_matches = await asyncio.gather(asr_result, voice_result)
        voice_id = voice_matches[0] if voice_matches else None
        return asr_text, voice_id

    async def async_asr_voice_recognize_audio(
        self, audio_data: ASRAudioData
    ) -> tuple[str, str | None]:
        """并行执行 ASR 与声纹识别，分别复用其所需的音频格式。"""
        return await self._recognize_with_voice(
            self.async_recognize_audio(audio_data),
            audio_data.pcm16_bytes,
        )

    async def async_asr_voice_recognize_pcm16_bytes(
        self, pcm16_bytes: bytes
    ) -> tuple[str, str | None]:
        """兼容 PCM16 调用，并行返回 ASR 文本和声纹结果。"""
        return await self._recognize_with_voice(
            self.async_recognize_pcm16_bytes(pcm16_bytes),
            pcm16_bytes,
        )

    def save_tmp_wav(
        self,
        root_dir: str | None = None,
        parent_dir_name: str | None = None,
        file_name: str | None = None,
    ) -> bool:
        """委托输入流保存最近一次识别音频。"""
        return self.asr_input_stream.save_tmp_wav(
            root_dir=root_dir,
            parent_dir_name=parent_dir_name,
            file_name=file_name,
        )
