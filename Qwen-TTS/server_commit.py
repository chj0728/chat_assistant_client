import base64
import os
import threading
import time
from typing import Any

import dashscope
import numpy as np
import sounddevice as sd
from dashscope.audio.qwen_tts_realtime import (
    AudioFormat,
    QwenTtsRealtime,
    QwenTtsRealtimeCallback,
)
from dotenv import load_dotenv

qwen_tts_realtime: QwenTtsRealtime | None = None
text_to_synthesize = [
    "对吧~我就特别喜欢这种超市，",
    "尤其是过年的时候",
    "去逛超市",
    "就会觉得",
    "超级超级开心！",
    "想买好多好多的东西呢！",
]

DO_VIDEO_TEST = False

load_dotenv()


def init_dashscope_api_key():
    """
    Set your DashScope API-key. More information:
    https://github.com/aliyun/alibabacloud-bailian-speech-demo/blob/master/PREREQUISITES.md
    """

    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    if "DASHSCOPE_API_KEY" in os.environ:
        dashscope.api_key = os.environ[
            "DASHSCOPE_API_KEY"
        ]  # load API-key from environment variable DASHSCOPE_API_KEY
        print("DashScope API Key loaded from environment variable.")
    else:
        dashscope.api_key = (
            "sk-518aac827a894b1fb0fbdb0147c1d84f"  # set API-key manually
        )
        print("DashScope API Key set manually in the code.")


class MyCallback(QwenTtsRealtimeCallback):
    def __init__(self):
        self.complete_event = threading.Event()
        self.stream = sd.OutputStream(
            samplerate=24000,
            channels=1,
            dtype="int16",
            latency="low",
        )
        self.stream.start()

    def on_open(self) -> None:
        print("connection opened, init player")

    def on_close(self, close_status_code, close_msg) -> None:
        self.stream.stop()
        self.stream.close()
        print(
            "connection closed with code: {}, msg: {}, destroy player".format(
                close_status_code, close_msg
            )
        )

    def on_event(self, response: dict[str, Any]) -> None:
        try:
            global qwen_tts_realtime
            event_type = response["type"]
            if "session.created" == event_type:
                print("start session: {}".format(response["session"]["id"]))
            if "response.audio.delta" == event_type:
                recv_audio_b64 = response["delta"]
                pcm_bytes = base64.b64decode(recv_audio_b64)
                pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
                self.stream.write(pcm)
            if "response.done" == event_type and qwen_tts_realtime is not None:
                print(f"response {qwen_tts_realtime.get_last_response_id()} done")
            if "session.finished" == event_type:
                print("session finished")
                self.complete_event.set()
        except Exception as e:
            print("[Error] {}".format(e))
            return

    def wait_for_finished(self):
        self.complete_event.wait()


if __name__ == "__main__":
    init_dashscope_api_key()

    print("Initializing ...")

    callback = MyCallback()

    qwen_tts_realtime = QwenTtsRealtime(
        # 如需使用指令控制功能，请将model替换为qwen3-tts-instruct-flash-realtime
        model="qwen3-tts-flash-realtime",
        callback=callback,
        # 以下为华北2（北京）地域的URL，各地域的URL不同。
        url="wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
    )

    qwen_tts_realtime.connect()
    qwen_tts_realtime.update_session(
        voice="Ethan",
        response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
        # 如需使用指令控制功能，请取消下方注释，并将model替换为qwen3-tts-instruct-flash-realtime
        # instructions='语速较快，带有明显的上扬语调，适合介绍时尚产品。',
        # optimize_instructions=True,
        mode="server_commit",
    )
    for text_chunk in text_to_synthesize:
        print(f"send text: {text_chunk}")
        qwen_tts_realtime.append_text(text_chunk)
        time.sleep(0.1)
    qwen_tts_realtime.finish()
    callback.wait_for_finished()
    print(
        "[Metric] session: {}, first audio delay: {}".format(
            qwen_tts_realtime.get_session_id(),
            qwen_tts_realtime.get_first_audio_delay(),
        )
    )
