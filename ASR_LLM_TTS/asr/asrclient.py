import os
import requests
from typing import Optional


class ASRClient:
    """
    FunASR HTTP Client
    """

    def __init__(
        self,
        host="http://192.168.50.125",
        port=2002,
        timeout: int = 60,
    ):
        """
        :param host: ASR 服务地址
        :param port: ASR 服务端口
        :param timeout: 请求超时时间（秒）
        """
        self.host = host
        self.port = port
        self.timeout = timeout

    def recognize(self, wav_path: str) -> str:
        """
        发送 wav 文件，返回识别文本

        :param wav_path: wav 文件路径
        :return: 识别文本
        """
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Wav file not found: {wav_path}")

        with open(wav_path, "rb") as f:
            files = {"file": (os.path.basename(wav_path), f, "audio/wav")}

            response = requests.post(
                self.host + ":" + str(self.port) + "/asr",
                files=files,
                timeout=self.timeout,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"ASR server error [{response.status_code}]: {response.text}"
            )

        result = response.json()

        if result.get("code") != 0:
            raise RuntimeError(f"ASR failed: {result.get('msg')}")

        return result.get("text", "")


# ===============================
# 单独运行时的测试
# ===============================
if __name__ == "__main__":
    client = ASRClient(
        host="http://192.168.50.125",
        port=2002,
        timeout=30,
    )

    wav = "/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/asr/welcome.wav"
    text = client.recognize(wav)
    print("ASR Result:", text)
