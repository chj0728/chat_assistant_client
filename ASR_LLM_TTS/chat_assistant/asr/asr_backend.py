import asyncio
import queue
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
    ) -> None:
        self.asr_backend_context = asr_backend_context
        self.asr_runtime = asr_runtime
        self.asr_input_stream = asr_input_stream
        self.asr_worker_thread: Optional[threading.Thread] = None

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
                logger.error(f"[vision_id: {self.asr_backend_context.vision_id}] [ASR + Voice] 推理失败: {e}")
            finally:
                elapsed_time = time.time() - start_time
                logger.info(
                    f"[vision_id: {self.asr_backend_context.vision_id}] [ASR + Voice] 推理耗时: {elapsed_time:.3f} 秒"
                )

    def start(self) -> None:
        """初始化 ASR 后端资源，启动 ASR worker 线程和音频输入流。"""

        self.asr_runtime.start()
        self.asr_input_stream.start()

        self.asr_worker_thread = threading.Thread(
            target=self.asr_worker_loop, daemon=True, name="asr-worker"
        )
        self.asr_worker_thread.start()
        logger.info("ASR 后端已启动")

    def stop(self) -> None:
        """停止 ASR 后端资源，通知 ASR worker 线程和音频输入流停止运行。"""

        self.asr_backend_context.stop_event.set()

        if self.asr_worker_thread and self.asr_worker_thread.is_alive():
            self.asr_worker_thread.join()
            logger.info("ASR worker 线程已停止")

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
