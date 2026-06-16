from typing import Protocol


class ASRRuntimeProtocol(Protocol):
    """ASR 后端运行时 Protocol，定义了后端运行时需要实现的接口方法。"""

    def start(self) -> None:
        """按需初始化运行时资源。"""
        ...

    def stop(self) -> None:
        """关闭运行时资源。"""
        ...

    def asr_infer_wav_path(self, wav_path: str) -> str:
        """执行 ASR 推理，输入 WAV 文件路径，返回识别结果文本。
        Args:
            wav_path: 待识别 WAV 文件路径。
        Returns:
            str: 识别结果文本。
        """
        ...

    def asr_infer_frames(self, frames: bytes) -> str:
        """执行 ASR 推理，输入音频帧数据，返回识别结果文本。
        Args:
            frames: 待识别音频帧数据。
        Returns:
            str: 识别结果文本。
        """
        ...

    def asr_infer_pcm16_bytes(self, pcm16_bytes: bytes) -> str:
        """执行 ASR 推理，输入 PCM16 bytes 音频数据，返回识别结果文本。
        Args:
            pcm16_bytes: 待识别 PCM16 bytes 音频数据。
        Returns:
            str: 识别结果文本。
        """
        ...

    def normalize_audio_frames(self, audio_frames) -> bytes:
        """将多种帧输入格式归一化为单段 PCM16 bytes。"""
        ...
