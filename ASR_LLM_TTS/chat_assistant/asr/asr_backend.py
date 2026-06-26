import asyncio
import json
import os
import queue
import socket
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

from logger import logger

from .asr_backend_context import ASRBackendContext
from .runtimes.protocol import ASRRuntimeProtocol
from .stream.protocol import InputStreamProtocol

try:
    from voice.voice_recognizer import VoiceRecognizer
except ImportError:
    VoiceRecognizer = None

from config import get_vad_no_speech_threshold

TAIL_SILENCE_MS = int(get_vad_no_speech_threshold() * 1000)

# 外部 ASR 文本推送服务：每行一个 UTF-8 JSON，例如 {"text": "..."}\n
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
        pass

    @abstractmethod
    def stop(self) -> None:
        """关闭运行时资源。"""
        pass


class ASRBackend(ASRBackendBase):
    """ASR 后端实现类\n
    - 后台线程持续监听音频输入队列，触发 ASR 推理请求。
    - 提供对外的控制接口。
    """

    def __init__(
        self,
        asr_backend_context: ASRBackendContext,
        asr_runtime: ASRRuntimeProtocol,
        asr_input_stream: InputStreamProtocol,
        **kwargs,
    ) -> None:
        self.kwargs = kwargs

        self.asr_backend_context = asr_backend_context
        self.asr_runtime = asr_runtime
        self.asr_input_stream = asr_input_stream
        self.asr_worker_thread: Optional[threading.Thread] = None

        #################### 外部 ASR 文本服务订阅相关配置 ####################
        self.enable_external_asr: bool = kwargs.get("enable_external_asr", False)
        self.external_asr_text_worker_thread: Optional[threading.Thread] = None
        self._external_asr_socket: Optional[socket.socket] = None
        self._external_asr_socket_lock = threading.Lock()
        self.EXTERNAL_ASR_TEXT_HOST = kwargs.get(
            "EXTERNAL_ASR_TEXT_HOST", EXTERNAL_ASR_TEXT_HOST
        )
        self.EXTERNAL_ASR_TEXT_PORT = kwargs.get(
            "EXTERNAL_ASR_TEXT_PORT", EXTERNAL_ASR_TEXT_PORT
        )
        self.EXTERNAL_ASR_RECONNECT_SECONDS = kwargs.get(
            "EXTERNAL_ASR_RECONNECT_SECONDS", EXTERNAL_ASR_RECONNECT_SECONDS
        )
        self.EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS = kwargs.get(
            "EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS", EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS
        )
        ###################################################################

        ########################## 声纹识别器初始化 #########################
        if VoiceRecognizer is not None:
            self.voice_recognizer = VoiceRecognizer(
                low_thresh=0.60, high_thresh=0.67, max_prints_per_id=1
            )
        else:
            self.voice_recognizer = None
        ##################################################################

    def asr_worker_loop(self) -> None:
        """ASR 后端工作线程主循环，持续监听音频输入队列，触发 ASR 推理请求。"""

        while not self.asr_backend_context.stop_event.is_set():
            try:
                # 从 ASRBackendContext 的音频输入队列中获取音频数据，等待超时时间为 0.1 秒
                audio_frames = self.asr_backend_context.audio_frames_queue.get(
                    timeout=0.1
                )
                pcm16_bytes = self.asr_runtime.normalize_audio_frames(audio_frames)

            except queue.Empty:
                continue

            start_time = time.time()
            try:
                asr_text, voice_id = asyncio.run(
                    self.async_asr_voice_recognize_pcm16_bytes(pcm16_bytes)
                )
                # self.asr_backend_context.asr_text_queue.put(asr_text)
                self.asr_backend_context.asr_voice_result_queue.put(
                    (asr_text, voice_id)
                )
            except Exception as e:
                logger.error(
                    f"[vision_id: {self.asr_backend_context.vision_id}] [ASR + Voice] 推理失败: {e}"
                )
            finally:
                elapsed_time = time.time() - start_time
                logger.info(
                    f"[vision_id: {self.asr_backend_context.vision_id}] [ASR + Voice] 推理耗时: {elapsed_time:.3f} 秒"
                )

    def external_asr_text_worker_loop(self) -> None:
        """订阅外部 ASR 文本服务，将每条 text 写入统一的 ASR 结果队列。"""
        reconnect_delay = self.EXTERNAL_ASR_RECONNECT_SECONDS

        while not self.asr_backend_context.stop_event.is_set():
            sock: Optional[socket.socket] = None
            try:
                logger.info(
                    f"[External ASR] 正在连接 "
                    f"{self.EXTERNAL_ASR_TEXT_HOST}:{self.EXTERNAL_ASR_TEXT_PORT}"
                )
                sock = socket.create_connection(
                    (self.EXTERNAL_ASR_TEXT_HOST, self.EXTERNAL_ASR_TEXT_PORT),
                    timeout=self.EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS,
                )
                sock.settimeout(self.EXTERNAL_ASR_SOCKET_TIMEOUT_SECONDS)

                with self._external_asr_socket_lock:
                    self._external_asr_socket = sock

                reconnect_delay = self.EXTERNAL_ASR_RECONNECT_SECONDS
                recv_buffer = b""
                logger.info(
                    f"[External ASR] 已连接 "
                    f"{self.EXTERNAL_ASR_TEXT_HOST}:{self.EXTERNAL_ASR_TEXT_PORT}"
                )

                while not self.asr_backend_context.stop_event.is_set():
                    try:
                        data = sock.recv(4096)
                    except socket.timeout:
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

                        # 复用既有队列格式：(asr_text, voice_id)。
                        # 外部服务未提供声纹结果，故 voice_id 为 None。
                        self.asr_backend_context.asr_voice_result_queue.put(
                            (text, None)
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
            except Exception as e:
                if not self.asr_backend_context.stop_event.is_set():
                    logger.exception(f"[External ASR] 工作线程异常: {e}")
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
        # logger.info(f"ASR 后端视觉ID已更新: {self.asr_backend_context.vision_id}")

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

    async def async_asr_voice_recognize_pcm16_bytes(
        self, pcm16_bytes: bytes
    ) -> tuple[str, Optional[str]]:
        """异步识别指定 PCM16 bytes 音频数据，返回识别结果文本和声纹结果。"""
        logger.debug(
            f"基于 vision_id:[ {self.asr_backend_context.vision_id} ] 的 ASR + Voice 识别正在进行中..."
        )
        asr_text, vr_results = await asyncio.gather(
            self.async_recognize_pcm16_bytes(pcm16_bytes),
            (
                self.voice_recognizer.recognize_async(
                    pcm16_bytes,
                    user_id=self.asr_backend_context.vision_id,
                    tail_silence_ms=TAIL_SILENCE_MS,
                )
                if self.voice_recognizer is not None
                else asyncio.sleep(0, result=None)
            ),
        )
        voice_id = vr_results[0] if vr_results else None
        return asr_text, voice_id
