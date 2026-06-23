from .protocol import TTSRuntimeProtocol as TTSRuntimeProtocol

__all__ = [
    "FallbackTTSRuntime",
    "QwenTTSRuntime",
    "SherpaTTSRuntime",
    "TTSRuntimeProtocol",
]


def __getattr__(name: str):
    if name == "FallbackTTSRuntime":
        from .fallback import FallbackTTSRuntime

        return FallbackTTSRuntime
    if name == "QwenTTSRuntime":
        from .qwen_tts import QwenTTSRuntime

        return QwenTTSRuntime
    if name == "SherpaTTSRuntime":
        from .sherpa_tts import SherpaTTSRuntime

        return SherpaTTSRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
