import os
import requests
from typing import Optional

from logger import logger


class ASRClient:
    """
    FunASR HTTP Client
    """

    def __init__(
        self,
        host="192.168.50.125",
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
                "http://" + self.host + ":" + str(self.port) + "/asr",
                files=files,
                timeout=self.timeout,
            )

        if response.status_code != 200:

            logger.error(f"ASR server error [{response.status_code}]: {response.text}")
            raise RuntimeError(
                f"ASR server error [{response.status_code}]: {response.text}"
            )

        result = response.json()

        if result.get("code") != 0:
            logger.error(f"ASR failed: {result.get('msg')}")
            raise RuntimeError(f"ASR failed: {result.get('msg')}")

        # 只提取 speaker_id 为 0 的文本
        # spk_0_tex = ""
        # sentences = result.get("sentences", [])
        # for sentence in sentences:
        #     logger.info(
        #         f"speaker_id={sentence.get('speaker_id')}:start={sentence['start']:.2f}, end={sentence['end']:.2f}, text={sentence['text']}"
        #     )
        #     if sentence.get("speaker_id") == 0:
        #         spk_0_tex += sentence["text"] + " "

        # logger.info(f"Speaker 0 Text: {spk_0_tex.strip()}")
        # # return result.get("text", "")
        # return spk_0_tex.strip()

        # # 如果只存在speaker_id为0的句子，则返回其文本 ，否则返回空字符串
        # sentences = result.get("sentences", [])

        # for sentence in sentences:
        #     logger.info(
        #         f"speaker_id={sentence.get('speaker_id')}:start={sentence['start']:.2f}, end={sentence['end']:.2f}, text={sentence['text']}"
        #     )

        # spk_0_sentences = [s for s in sentences if s.get("speaker_id") == 0]
        # if len(spk_0_sentences) == len(sentences):
        #     spk_0_text = " ".join(s["text"] for s in spk_0_sentences)
        #     # logger.info(f"Speaker 0 Text: {spk_0_text.strip()}")
        #     return spk_0_text.strip()

        # return ""

        # 读取 "text" 字段，如果不存在则返回空字符串
        text = result.get("text", "").strip()
        return text


# ===============================
# 单独运行时的测试
# ===============================
if __name__ == "__main__":
    client = ASRClient(
        host="192.168.50.107",
        port=2002,
        timeout=30,
    )

    wav = "./wavs/example.wav"
    text = client.recognize(wav)
    # print("ASR Result:", text)
    logger.info(f"ASR Result: {text}")
