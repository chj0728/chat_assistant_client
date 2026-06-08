import base64
import os
import threading
import wave
from typing import Any, cast

from logger import logger

from .backend_base import TTSBackendContext, TTSRuntime

try:
    import dashscope
    from dashscope.audio.qwen_tts_realtime import (
        AudioFormat,
        QwenTtsRealtime,
        QwenTtsRealtimeCallback,
    )
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    dashscope = None
    AudioFormat = None
    QwenTtsRealtime = None
    QwenTtsRealtimeCallback = object


try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    load_dotenv = None


_REMOTE_CALLBACK_BASE = cast(Any, QwenTtsRealtimeCallback)


class _RemoteCallback(_REMOTE_CALLBACK_BASE):
    def __init__(self, audio_queue) -> None:
        super().__init__()
        self._audio_queue = audio_queue
        self.complete_event = threading.Event()
        self.session_finished_event = threading.Event()
        self.connection_closed_event = threading.Event()
        self._response_chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._playback_enabled = True

    def reset_response(self, *, playback_enabled: bool) -> None:
        with self._lock:
            self._response_chunks = []
        self._playback_enabled = playback_enabled
        self.complete_event.clear()
        self.connection_closed_event.clear()

    def get_response_pcm(self) -> bytes:
        with self._lock:
            return b"".join(self._response_chunks)

    def on_open(self) -> None:
        logger.info("远端 TTS 连接已建立")

    def on_close(self, close_status_code, close_msg) -> None:
        self.connection_closed_event.set()
        logger.info(
            "远端 TTS 连接已关闭，code=%s msg=%s",
            close_status_code,
            close_msg,
        )

    def on_event(self, response: dict[str, Any]) -> None:
        try:
            event_type = response["type"]
            if event_type == "session.created":
                logger.info("远端 TTS session 已创建: %s", response["session"]["id"])
                return

            if event_type == "response.audio.delta":
                pcm_bytes = base64.b64decode(response["delta"])
                with self._lock:
                    self._response_chunks.append(pcm_bytes)
                if self._playback_enabled:
                    self._audio_queue.put(pcm_bytes)
                return

            if event_type == "response.done":
                self.complete_event.set()
                return

            if event_type == "session.finished":
                self.complete_event.set()
                self.session_finished_event.set()
        except Exception as e:
            logger.error(f"处理远端 TTS 响应失败: {e}")

    def wait_for_response_done(self, timeout_sec: float) -> bool:
        return self.complete_event.wait(timeout=timeout_sec)

    def wait_for_finished(self, timeout_sec: float) -> bool:
        return self.session_finished_event.wait(timeout=timeout_sec)

    def is_connection_closed(self) -> bool:
        return self.connection_closed_event.is_set()


class RemoteTTSRuntime(TTSRuntime):
    def __init__(self, context: TTSBackendContext) -> None:
        self._context = context
        self._runtime_lock = threading.Lock()
        self._qwen_tts = None
        self._callback = None

        if load_dotenv is not None:
            load_dotenv()

    def _reset_runtime_locked(self) -> None:
        qwen_tts = self._qwen_tts
        self._qwen_tts = None
        self._callback = None

        if qwen_tts is None:
            return

        try:
            qwen_tts.finish()
        except Exception as e:
            if "closed" in str(e).lower():
                logger.info("远端 TTS 连接已关闭，跳过重复关闭")
                return
            logger.warning(f"关闭远端 TTS 会话失败: {e}")

    ####### TTSRuntime 接口实现 ######
    def initialize_if_needed(self) -> None:
        self._ensure_runtime()

    def close_runtime(self) -> None:
        with self._runtime_lock:
            self._reset_runtime_locked()

    def run_tts(self, text: str) -> None:
        self.synthesize(text, playback_enabled=True)

    ################################

    def _ensure_runtime(self) -> None:
        if self._qwen_tts is not None:
            callback = self._callback
            if callback is not None and not callback.is_connection_closed():
                return

            logger.info("检测到远端 TTS 连接已关闭，准备重建运行时")
            self._reset_runtime_locked()

        if dashscope is None or QwenTtsRealtime is None or AudioFormat is None:
            raise RuntimeError("dashscope 未安装，无法启用远端 TTS")

        api_key = self._context.api_key or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法启用远端 TTS")

        dashscope.api_key = api_key
        self._callback = _RemoteCallback(self._context.audio_queue)
        qwen_tts_cls = cast(Any, QwenTtsRealtime)
        audio_format = cast(Any, AudioFormat)
        self._qwen_tts = qwen_tts_cls(
            model=self._context.model,
            callback=self._callback,
            url=self._context.remote_url,
        )
        self._qwen_tts.connect()
        self._qwen_tts.update_session(
            voice=self._context.voice,
            response_format=audio_format.PCM_24000HZ_MONO_16BIT,
            mode=self._context.remote_mode,
        )

    ####### 远端 TTS 运行时接口实现 ######
    def change_voice(self, voice: str) -> None:
        self._context.voice = voice
        with self._runtime_lock:
            if self._qwen_tts is None:
                return
            audio_format = cast(Any, AudioFormat)
            self._qwen_tts.update_session(
                voice=self._context.voice,
                response_format=audio_format.PCM_24000HZ_MONO_16BIT,
                mode=self._context.remote_mode,
            )

    def generate_wav(self, text: str, filename: str) -> bool:
        try:
            pcm_bytes = self.synthesize(text, playback_enabled=False)
            if not pcm_bytes:
                return False
            with wave.open(filename, "wb") as wf:
                wf.setnchannels(self._context.channels)
                wf.setsampwidth(2)
                wf.setframerate(self._context.sample_rate)
                wf.writeframes(pcm_bytes)
            return True
        except Exception as e:
            logger.error(f"远端 TTS 生成 WAV 失败: {e}")
            return False

    def synthesize(self, text: str, *, playback_enabled: bool) -> bytes:
        """执行 TTS 合成，返回合成的 PCM 音频数据。
        如果 playback_enabled=True，则在合成过程中会将 PCM 数据放入音频队列以供播放；如果 playback_enabled=False，则仅返回完整的 PCM 数据，不进行播放。
        """
        normalized_text = text.strip()
        if not normalized_text:
            return b""

        with self._runtime_lock:
            self._ensure_runtime()
            assert self._callback is not None
            assert self._qwen_tts is not None

            self._callback.reset_response(playback_enabled=playback_enabled)
            try:
                self._qwen_tts.append_text(normalized_text)
                self._qwen_tts.commit()
            except Exception as e:
                if "closed" not in str(e).lower():
                    raise

                logger.info("远端 TTS 连接已失效，正在重建后重试当前请求")
                self._reset_runtime_locked()
                self._ensure_runtime()
                assert self._callback is not None
                assert self._qwen_tts is not None
                self._callback.reset_response(playback_enabled=playback_enabled)
                self._qwen_tts.append_text(normalized_text)
                self._qwen_tts.commit()

        if not self._callback.wait_for_response_done(timeout_sec=self._context.timeout):
            raise TimeoutError("远端 TTS 响应超时")
        return self._callback.get_response_pcm()
