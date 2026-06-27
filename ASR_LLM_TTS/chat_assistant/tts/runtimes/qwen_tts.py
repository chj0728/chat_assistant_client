import base64
import os
import threading
import wave
from typing import Any, cast

from logger import logger

from ..backend_context import TTSBackendContext
from .protocol import TTSRuntimeProtocol

try:
    import dashscope
    from dashscope.audio.qwen_tts_realtime import (
        AudioFormat,
        QwenTtsRealtime,
        QwenTtsRealtimeCallback,
    )
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    raise ImportError(
        "缺少 dashscope 库，无法使用远端 TTS 功能。请安装 dashscope 库后重试。"
    )

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    load_dotenv = None


REMOTE_CALLBACK_BASE = cast(Any, QwenTtsRealtimeCallback)


class RemoteCallback(REMOTE_CALLBACK_BASE):
    def __init__(self, audio_queue) -> None:
        super().__init__()
        self._audio_queue = audio_queue
        self.complete_event = threading.Event()
        self.session_finished_event = threading.Event()
        self.connection_closed_event = threading.Event()
        self._response_chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._playback_enabled = True

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

            if event_type == "response.audio.delta":
                pcm_bytes = base64.b64decode(response["delta"])
                with self._lock:
                    self._response_chunks.append(pcm_bytes)
                if self._playback_enabled:
                    self._audio_queue.put(pcm_bytes)

            if event_type == "response.done":
                self.complete_event.set()

            if event_type == "session.finished":
                self.complete_event.set()
                self.session_finished_event.set()
        except Exception as e:
            logger.error(f"处理远端 TTS 响应失败: {e}")

    def reset_response(self, *, playback_enabled: bool = False) -> None:
        with self._lock:
            self._response_chunks = []
        self._playback_enabled = playback_enabled
        self.complete_event.clear()
        self.session_finished_event.clear()
        self.connection_closed_event.clear()

    def get_response_pcm(self) -> bytes:
        with self._lock:
            return b"".join(self._response_chunks)

    def wait_for_response_done(self, timeout_sec: float) -> bool:
        return self.complete_event.wait(timeout=timeout_sec)

    def wait_for_session_finished(self, timeout_sec: float) -> bool:
        return self.session_finished_event.wait(timeout=timeout_sec)

    def is_connection_closed(self) -> bool:
        return self.connection_closed_event.is_set()


class QwenTTSRuntime(TTSRuntimeProtocol):
    def __init__(self, context: TTSBackendContext, **kwargs) -> None:
        self.kwargs = kwargs

        self.context = context
        self.runtime_lock = threading.RLock()

        self.voice = self.kwargs.get("voice", "Cherry")
        self.model = self.kwargs.get("model", "qwen3-tts-flash-realtime")
        self.remote_url = self.kwargs.get("remote_url", None)
        self.remote_mode = self.kwargs.get("remote_mode", "commit")

        self.channels = self.kwargs.get("channels", 1)
        self.sample_rate = self.kwargs.get("sample_rate", 24000)
        self.dtype = self.kwargs.get("dtype", "int16")

        self.initialize_runtime()
        logger.info(
            "QwenTTSRuntime 初始化完成，voice=%s, model=%s, remote_url=%s, remote_mode=%s",
            self.voice,
            self.model,
            self.remote_url,
            self.remote_mode,
        )

    def reset_runtime(self) -> None:
        qwen_tts = getattr(self, "qwen_tts", None)
        callback = getattr(self, "callback", None)
        self.qwen_tts = None
        self.callback = None

        if qwen_tts is None:
            return

        try:
            qwen_tts.finish()
            if callback is not None and callback.wait_for_session_finished(
                timeout_sec=self.context.timeout
            ):
                logger.info("远端 TTS 会话结束完成")
            elif callback is not None:
                logger.warning("等待远端 TTS 会话结束超时")
        except Exception as e:
            if "closed" in str(e).lower():
                logger.info("远端 TTS 连接已关闭，跳过重复关闭")
                return
            logger.warning(f"关闭远端 TTS 会话失败: {e}")

    def initialize_runtime(self) -> None:
        self.init_dashscope_api_key()
        self.init_qwen_tts()

    def init_dashscope_api_key(self) -> None:
        if load_dotenv is not None:
            load_dotenv()

        if dashscope is None or QwenTtsRealtime is None or AudioFormat is None:
            raise ImportError("dashscope 未安装，无法启用远端 TTS")

        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("未配置 DASHSCOPE_API_KEY，无法启用远端 TTS")

        dashscope.api_key = api_key

    def init_qwen_tts(self) -> None:

        self.callback = RemoteCallback(self.context.audio_queue)
        self.qwen_tts = QwenTtsRealtime(
            model=self.model,
            callback=self.callback,
            url=self.remote_url,
        )
        self.qwen_tts.connect()
        self.qwen_tts.update_session(
            voice=self.voice,
            response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            mode=self.remote_mode,
        )

    def ensure_runtime(self) -> None:
        with self.runtime_lock:
            if (
                getattr(self, "callback", None) is None
                or getattr(self, "qwen_tts", None) is None
            ):
                self.initialize_runtime()
                return

            if self.callback is not None:
                if self.callback.is_connection_closed():
                    logger.warning("远端 TTS 连接已关闭，正在重新建立连接...")
                    self.reset_runtime()
                    self.initialize_runtime()

    def session_to_finish(self) -> None:
        with self.runtime_lock:
            self.reset_runtime()

    def synthesize(self, text: str, *, playback_enabled: bool) -> bytes:
        normalized_text = text.strip()
        if not normalized_text:
            return b""

        with self.runtime_lock:
            self.ensure_runtime()
            assert self.callback is not None
            assert self.qwen_tts is not None

            # 清除可能的残留音频数据，避免下次请求时被误用
            self.callback.reset_response(playback_enabled=playback_enabled)

            try:
                self.qwen_tts.append_text(normalized_text)
                self.qwen_tts.commit()
                if not self.callback.wait_for_response_done(
                    timeout_sec=self.context.timeout
                ):

                    raise TimeoutError("远端 TTS 响应超时")

            except Exception as e:
                if "closed" in str(e).lower():
                    logger.warning("远端 TTS 连接在请求期间关闭，正在重连后重试...")
                    self.reset_runtime()
                    self.initialize_runtime()
                    assert self.callback is not None
                    assert self.qwen_tts is not None
                    self.callback.reset_response(playback_enabled=playback_enabled)
                    self.qwen_tts.append_text(normalized_text)
                    self.qwen_tts.commit()
                    if not self.callback.wait_for_response_done(
                        timeout_sec=self.context.timeout
                    ):

                        raise TimeoutError("远端 TTS 重试后响应超时")
                else:
                    raise RuntimeError(f"{e}")

        return self.callback.get_response_pcm()

    ###################### 实现 TTSRuntimeProtocol 接口方法 ######################
    def start(self) -> None:
        self.ensure_runtime()

    def stop(self) -> None:
        with self.runtime_lock:
            self.session_to_finish()

    def tts_infer(self, text: str) -> None:
        self.synthesize(text, playback_enabled=True)

    def generate_wav(self, text: str, filename: str) -> bool:
        try:
            pcm_bytes = self.synthesize(text, playback_enabled=False)
            if not pcm_bytes:
                return False
            with wave.open(filename, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(pcm_bytes)
            return True
        except Exception as e:
            logger.error(f"远端 TTS 生成 WAV 失败: {e}")
            return False

    def change_voice(self, voice: str) -> None:
        self.voice = voice
        with self.runtime_lock:
            if self.qwen_tts is None:
                return
            audio_format = cast(Any, AudioFormat)
            self.qwen_tts.update_session(
                voice=self.voice,
                response_format=audio_format.PCM_24000HZ_MONO_16BIT,
                mode=self.remote_mode,
            )

    ##############################################################################
