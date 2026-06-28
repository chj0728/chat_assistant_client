from .protocol import TTSRuntimeProtocol as TTSRuntimeProtocol

__all__ = [
    "FallbackTTSRuntime",
    "QwenTTSRuntime",
    "SherpaTTSRuntime",
    "TTSRuntimeProtocol",
    "VoxCPMCppTTSRuntime",
]


def __getattr__(name: str):
    if name == "FallbackTTSRuntime":
        from .fallback import FallbackTTSRuntime

        return FallbackTTSRuntime
    if name == "QwenTTSRuntime":
        from .qwen_tts import QwenTTSRuntime

        return QwenTTSRuntime
    if name == "SherpaTTSRuntime":
        from .sherpa_onnx_tts import SherpaTTSRuntime

        return SherpaTTSRuntime
    if name == "VoxCPMCppTTSRuntime":
        from .voxcpm_cpp_tts import VoxCPMCppTTSRuntime

        return VoxCPMCppTTSRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
