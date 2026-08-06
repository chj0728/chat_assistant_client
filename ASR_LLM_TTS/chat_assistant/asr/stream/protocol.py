from typing import Protocol


class InputStreamProtocol(Protocol):

    def start(self) -> None:
        """启动音频输入流，准备好接收和处理音频数据。"""
        ...

    def stop(self) -> None:
        """停止音频输入流，释放相关资源。"""
        ...

    def close(self) -> None:
        """关闭音频输入流，彻底释放相关资源。"""
        ...

    def save_tmp_wav(
        self,
        root_dir: str | None = None,
        parent_dir_name: str | None = None,
        file_name: str | None = None,
    ) -> bool:
        """保存临时音频文件，返回是否成功。\n
        example:
            save_tmp_wav(root_dir="/tmp", parent_dir_name="audio", file_name="test.wav")
        it will save the temporary audio file to /tmp/audio/test.wav \n
        if root_dir or parent_dir_name or file_name is None, use default values.
        save the temporary audio file to \n
        {project_root}/ASR_LLM_TTS/logs/audio/{year-month-day}/{year-month-day-hour-minute-second}.wav
        """
        ...
