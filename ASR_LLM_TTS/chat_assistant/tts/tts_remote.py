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
    raise ImportError(
        "缺少 dashscope 库，无法使用远端 TTS 功能。请安装 dashscope 库后重试。"
    )


try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    load_dotenv = None


REMOTE_CALLBACK_BASE = cast(Any, QwenTtsRealtimeCallback)


class RemoteCallback(REMOTE_CALLBACK_BASE):
    """QwenTtsRealtimeCallback 的子类。\n
    服务端会通过回调的方式，将服务端响应事件和数据返回给客户端。\n
    需要实现回调方法，处理服务端返回的信息或者数据。\n
    reference: https://bailian.console.aliyun.com/cn-beijing?spm=a2c4g.11186623.0.0.60905ec6tR3xaB&tab=api#/api/?type=model&url=2950054

    Args:
        audio_queue: 音频数据队列，用于存放服务端返回的 PCM 音频数据，以供播放线程消费。
        complete_event: TTS 响应完成事件，当服务端返回 response.done 或 session.finished 事件时触发，表示当前 TTS 请求的响应已完成。
        session_finished_event: TTS 会话完成事件，当服务端返回 session.finished 事件时触发，表示当前 TTS 会话已完成。
        connection_closed_event: TTS 连接关闭事件，当服务端连接关闭时触发，表示当前 TTS 连接已关闭。
        _response_chunks: 用于存储服务端返回的 PCM 音频数据块，最终合并成完整的 PCM 音频数据。
        _lock: 保护 _response_chunks 的线程锁，确保在多线程环境下对 _response_chunks 的访问是线程安全的。
        _playback_enabled: 是否启用播放功能，如果为 True，则在接收 PCM 音频数据时会将数据放入 audio_queue 以供播放线程消费；如果为 False，则仅保存 PCM 音频数据而不进行播放。
    """

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
        """当和服务端建立连接完成后，该方法立刻被回调。"""
        logger.info("远端 TTS 连接已建立")

    def on_close(self, close_status_code, close_msg) -> None:
        """当服务已经关闭连接后进行回调。"""
        self.connection_closed_event.set()
        logger.info(
            "远端 TTS 连接已关闭，code=%s msg=%s",
            close_status_code,
            close_msg,
        )

    def on_event(self, response: dict[str, Any]) -> None:
        """包括对接口调用的回复响应和模型生成的文本和音频。
        reference: https://help.aliyun.com/zh/model-studio/qwen-tts-realtime-server-events
        """
        try:

            event_type = response["type"]

            # 客户端连接到服务端后，响应的第一个事件
            if event_type == "session.created":
                logger.info("远端 TTS session 已创建: %s", response["session"]["id"])

            # 当模型增量生成新的audio数据时，系统会返回服务器 response.audio.delta 事件。
            if event_type == "response.audio.delta":
                pcm_bytes = base64.b64decode(response["delta"])
                with self._lock:
                    self._response_chunks.append(pcm_bytes)
                if self._playback_enabled:
                    self._audio_queue.put(pcm_bytes)

            # 当响应生成完成时，服务端会返回此事件。
            if event_type == "response.done":
                self.complete_event.set()

            # 当所有响应生成完成时，服务端会返回此事件。
            if event_type == "session.finished":
                self.complete_event.set()
                self.session_finished_event.set()

        except Exception as e:
            logger.error(f"处理远端 TTS 响应失败: {e}")

    def reset_response(self, *, playback_enabled: bool = False) -> None:
        """在开始新的 TTS 请求之前调用，重置之前请求的响应数据和状态。

        Args:
            playback_enabled: 是否启用播放功能，如果为 True，则在接收 PCM 音频数据时会将数据放入 audio_queue 以供播放线程消费；
            如果为 False，则仅保存 PCM 音频数据而不进行播放。
        """

        with self._lock:
            self._response_chunks = []

        self._playback_enabled = playback_enabled

        self.complete_event.clear()
        self.session_finished_event.clear()
        self.connection_closed_event.clear()

    def get_response_pcm(self) -> bytes:
        """获取当前 TTS 请求的完整 PCM 音频数据，返回值为 bytes 类型。"""
        with self._lock:
            return b"".join(self._response_chunks)

    def wait_for_response_done(self, timeout_sec: float) -> bool:
        """等待当前 TTS 请求的响应完成，返回值为 bool 类型，表示是否在指定超时时间内完成。"""
        return self.complete_event.wait(timeout=timeout_sec)

    def wait_for_session_finished(self, timeout_sec: float) -> bool:
        """等待当前 TTS 会话完成，返回值为 bool 类型，表示是否在指定超时时间内完成。"""
        return self.session_finished_event.wait(timeout=timeout_sec)

    def is_connection_closed(self) -> bool:
        """检查远端 TTS 连接是否已关闭，返回值为 bool 类型。"""
        return self.connection_closed_event.is_set()


class RemoteTTSRuntime(TTSRuntime):
    def __init__(self, context: TTSBackendContext) -> None:

        self.context = context
        self.runtime_lock = threading.RLock()

        self.initialize_runtime()

    def reset_runtime(self) -> None:
        """清理当前运行时引用并尽力关闭旧会话。"""
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
        """初始化远端 TTS 运行时，建立与服务端的连接并准备进行 TTS 合成。"""

        self.init_dashscope_api_key()

        self.init_qwen_tts()

    def init_dashscope_api_key(self) -> None:
        """初始化 dashscope API key，优先使用环境变量 DASHSCOPE_API_KEY 的值，如果 context 中有 api_key 配置则覆盖环境变量。"""
        if load_dotenv is not None:
            load_dotenv()

        if dashscope is None or QwenTtsRealtime is None or AudioFormat is None:
            raise RuntimeError("dashscope 未安装，无法启用远端 TTS")

        api_key = self.context.api_key or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法启用远端 TTS")

        dashscope.api_key = api_key

    def init_qwen_tts(self) -> None:
        """初始化 QwenTtsRealtime 实例并建立连接。"""
        self.callback = RemoteCallback(self.context.audio_queue)

        self.qwen_tts = QwenTtsRealtime(
            model=self.context.model,
            callback=self.callback,
            url=self.context.remote_url,
        )
        self.qwen_tts.connect()

        self.qwen_tts.update_session(
            voice=self.context.voice,
            response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            mode=self.context.remote_mode,
        )

    def ensure_runtime(self) -> None:
        """确保远端 TTS 运行时已正确初始化，如果连接已关闭则重建运行时。"""

        with self.runtime_lock:
            if self.callback is None or self.qwen_tts is None:
                self.initialize_runtime()
                return

            if self.callback.is_connection_closed():
                logger.warning("远端 TTS 连接已关闭，正在重新建立连接...")
                self.reset_runtime()
                self.initialize_runtime()

    def session_to_finish(self) -> None:
        """客户端显式调用 session.finish 通知服务端清理状态，服务端返回 session.finished 后关闭连接"""

        with self.runtime_lock:
            self.reset_runtime()

    def synthesize(self, text: str, *, playback_enabled: bool) -> bytes:
        """执行 TTS 合成，返回合成的 PCM 音频数据。
        如果 playback_enabled=True，则在合成过程中会将 PCM 数据放入音频队列以供播放；如果 playback_enabled=False，则仅返回完整的 PCM 数据，不进行播放。
        """
        normalized_text = text.strip()
        if not normalized_text:
            return b""

        with self.runtime_lock:
            self.ensure_runtime()
            assert self.callback is not None
            assert self.qwen_tts is not None

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
                    raise

        return self.callback.get_response_pcm()

    ####### TTSRuntime 接口实现 ######
    def initialize_if_needed(self) -> None:
        self.ensure_runtime()

    def close_runtime(self) -> None:
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
                wf.setnchannels(self.context.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.context.sample_rate)
                wf.writeframes(pcm_bytes)
            return True
        except Exception as e:
            logger.error(f"远端 TTS 生成 WAV 失败: {e}")
            return False

    def change_voice(self, voice: str) -> None:
        self.context.voice = voice
        with self.runtime_lock:
            if self.qwen_tts is None:
                return
            audio_format = cast(Any, AudioFormat)
            self.qwen_tts.update_session(
                voice=self.context.voice,
                response_format=audio_format.PCM_24000HZ_MONO_16BIT,
                mode=self.context.remote_mode,
            )

    ################################
