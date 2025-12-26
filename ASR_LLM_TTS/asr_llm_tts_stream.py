import requests
import sounddevice as sd
import numpy as np

from scipy.io.wavfile import write

from tts.ttsplay import RealtimeTTSPlayer
from llm.llmclient import LLMClient
from asr.asrclient import ASRClient


def record_audio(filename="output.wav", sample_rate=44100):
    print("按下 Enter 开始录音...")
    input()  # 等待用户按下 Enter 键开始录音
    print("录音中... 按下 Enter 键结束录音")

    # 开始录音
    recording = []
    try:

        def callback(indata, frames, time, status):
            recording.append(indata.copy())

        with sd.InputStream(samplerate=sample_rate, channels=1, callback=callback):
            input()  # 等待用户再次按下 Enter 键结束录音
    except Exception as e:
        print(f"录音出现错误: {e}")
        return

    # 将录音数据合并并保存为 WAV 文件
    audio_data = np.concatenate(recording, axis=0)
    write(filename, sample_rate, (audio_data * 32767).astype(np.int16))
    print(f"录音已保存为 {filename}")


if __name__ == "__main__":

    # ----- 初始化 ASR -----
    asr_client = ASRClient(
        host="http://192.168.50.125",
        port=2002,
        timeout=30,
    )

    # ----- 初始化 TTS -----
    tts_player = RealtimeTTSPlayer(
        host="http://192.168.50.125",
        port=50000,
    )
    # tts_player.generate_wav("你好呀！请问有什么可以帮到你的吗？", "welcome.wav")
    # tts_player.play_audio("welcome.wav")

    # ----- 初始化 LLM -----
    api_url = "http://192.168.50.125:8000/v1/models"

    try:
        response = requests.get(api_url)
        data = response.json()

        # 获取第一个模型的ID
        model_id = data["data"][0]["id"]
        print(f"使用的模型ID: {model_id}")

        model_root = data["data"][0]["root"]
        print(f"模型根目录: {model_root}")

    except Exception as e:
        print(f"获取模型列表失败: {e}")
        raise e

    llm_client = LLMClient(
        host="http://192.168.50.125",
        port=8000,
    )

    print("开始与模型对话（输入 exit 或 quit 退出）")

    while True:
        # user_input = input("你：").strip()
        # if user_input.lower() in ["exit", "quit"]:
        #     break
        record_audio("user_input.wav", sample_rate=44100)
        try:
            user_input = asr_client.recognize("user_input.wav").strip()
        except Exception as e:
            print(f"ASR 识别失败: {e}")
            continue
        print("助手：", end="", flush=True)

        buffer = ""

        for token in llm_client.stream_chat(user_input):
            print(token, end="", flush=True)
            buffer += token

            # ===== 更稳健的断句条件 =====
            if (
                token in ["。", "！", "？"]
                and len(buffer) >= 15
                and not buffer.rstrip().endswith(("*", "#", '"', "”"))
            ):
                tts_player.speak(buffer.strip(), interrupt=False)
                buffer = ""

        # 循环结束后，把剩余的也说出来
        if buffer.strip():
            tts_player.speak(buffer.strip(), interrupt=False)

        print("\n")

        user_input = input("按下 Enter 键继续对话，或输入 exit/quit 退出：").strip()
        if user_input.lower() in ["exit", "quit"]:
            break

    print("对话结束")
