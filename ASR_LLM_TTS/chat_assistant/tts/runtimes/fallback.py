import queue
from collections.abc import Callable
from enum import Enum

from logger import logger

from ..backend_context import TTSBackendContext
from .protocol import TTSRuntimeProtocol


class _ActiveRuntime(Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"


class FallbackTTSRuntime(TTSRuntimeProtocol):
    """Use a primary TTS runtime and permanently fall back to a backup on failure."""

    def __init__(
        self,
        context: TTSBackendContext,
        primary_factory: Callable[[], TTSRuntimeProtocol],
        fallback_factory: Callable[[], TTSRuntimeProtocol],
        fallback_switch_callback: Callable[[], None] | None = None,
        *,
        primary_name: str = "primary TTS",
        fallback_name: str = "fallback TTS",
    ) -> None:
        self._context = context
        self._primary_factory = primary_factory
        self._fallback_factory = fallback_factory
        self._fallback_switch_callback = fallback_switch_callback
        self._primary_name = primary_name
        self._fallback_name = fallback_name
        self._primary_runtime: TTSRuntimeProtocol | None = None
        self._fallback_runtime: TTSRuntimeProtocol | None = None
        self._active_runtime = _ActiveRuntime.PRIMARY

    def _get_primary_runtime(self) -> TTSRuntimeProtocol:
        if self._primary_runtime is None:
            self._primary_runtime = self._primary_factory()
        return self._primary_runtime

    def _get_fallback_runtime(self) -> TTSRuntimeProtocol:
        if self._fallback_runtime is None:
            self._fallback_runtime = self._fallback_factory()
        return self._fallback_runtime

    def _drain_audio_queue(self) -> None:
        while not self._context.audio_queue.empty():
            try:
                self._context.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _switch_to_fallback(self, reason: Exception | str) -> TTSRuntimeProtocol:
        if self._active_runtime == _ActiveRuntime.FALLBACK:
            return self._get_fallback_runtime()

        logger.warning(
            "%s 不可用，切换到 %s: %s",
            self._primary_name,
            self._fallback_name,
            reason,
        )
        if self._primary_runtime is not None:
            try:
                self._primary_runtime.stop()
            except Exception as e:
                logger.warning("停止 %s 失败: %s", self._primary_name, e)

        self._drain_audio_queue()
        if self._fallback_switch_callback is not None:
            self._fallback_switch_callback()

        fallback_runtime = self._get_fallback_runtime()
        fallback_runtime.start()
        self._active_runtime = _ActiveRuntime.FALLBACK
        return fallback_runtime

    def start(self) -> None:
        if self._active_runtime == _ActiveRuntime.FALLBACK:
            self._get_fallback_runtime().start()
            return

        try:
            self._get_primary_runtime().start()
        except Exception as e:
            self._switch_to_fallback(e)

    def stop(self) -> None:
        for runtime in (self._primary_runtime, self._fallback_runtime):
            if runtime is None:
                continue
            try:
                runtime.stop()
            except Exception as e:
                logger.warning("停止 TTS runtime 失败: %s", e)

    def interrupt(self) -> None:
        self._context.interrupt_event.set()

        runtime = (
            self._fallback_runtime
            if self._active_runtime == _ActiveRuntime.FALLBACK
            else self._primary_runtime
        )
        if runtime is None:
            return

        try:
            runtime.interrupt()
        except Exception as e:
            logger.warning("中断 TTS runtime 失败: %s", e)

    def tts_infer(self, text: str) -> None:
        if self._active_runtime == _ActiveRuntime.FALLBACK:
            self._get_fallback_runtime().tts_infer(text)
            return

        try:
            self._get_primary_runtime().tts_infer(text)
        except Exception as e:
            fallback_runtime = self._switch_to_fallback(e)
            fallback_runtime.tts_infer(text)

    def generate_wav(self, text: str, filename: str) -> bool:
        if self._active_runtime == _ActiveRuntime.FALLBACK:
            return self._get_fallback_runtime().generate_wav(text, filename)

        try:
            if self._get_primary_runtime().generate_wav(text, filename):
                return True
            fallback_runtime = self._switch_to_fallback("生成 WAV 失败")
        except Exception as e:
            fallback_runtime = self._switch_to_fallback(e)

        return fallback_runtime.generate_wav(text, filename)

    def change_voice(self, voice: str) -> None:
        if self._active_runtime == _ActiveRuntime.FALLBACK:
            self._get_fallback_runtime().change_voice(voice)
            return

        try:
            self._get_primary_runtime().change_voice(voice)
        except Exception as e:
            fallback_runtime = self._switch_to_fallback(e)
            fallback_runtime.change_voice(voice)
