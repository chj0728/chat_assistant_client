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

    def save_tmp_wav(self) -> bool:
        """保存临时音频文件，返回是否成功。"""
        ...
