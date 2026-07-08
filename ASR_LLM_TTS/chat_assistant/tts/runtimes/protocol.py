from typing import Protocol


class TTSRuntimeProtocol(Protocol):
    """TTS 后端运行时 Protocol，定义了后端运行时需要实现的接口方法。"""

    def start(self) -> None:
        """启动运行时资源。"""
        ...

    def stop(self) -> None:
        """关闭运行时资源。"""
        ...

    def interrupt(self) -> None:
        """中断当前正在进行的 TTS 推理。"""
        pass

    def tts_infer(self, text: str) -> None:
        """执行 TTS 推理，将合成的音频数据块放入 TTSBackendContext 的 audio_queue 供播放线程使用。
        Args:
            text: 待合成文本。
        """
        ...

    def generate_wav(self, text: str, filename: str) -> bool:
        """生成 WAV 文件。
        Args:
            text: 待合成文本。
            filename: 输出 WAV 文件名。
        Returns:
            bool: 是否生成成功。
        """
        ...

    def change_voice(self, voice: str) -> None:
        """更改语音设置，适用于支持多语音的 TTS 后端。
        Args:
            voice: 语音名称。
        """
        ...
