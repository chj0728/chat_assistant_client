import requests
import json
import wave
import time
from playsound3 import playsound

# ======================
# 配置
# ======================
VLLM_URL = "http://192.168.50.125:8000/v1/chat/completions"
MODEL_NAME = "Qwen/Qwen3-8B"

TTS_URL = "http://192.168.50.125:50000/inference_zero_shot"
SAMPLE_RATE = 24000


# ======================
# 工具函数
# ======================
def pcm_to_wav(pcm_bytes, filename, sample_rate=SAMPLE_RATE):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def play_audio(file_path):
    try:
        sound = playsound(file_path, block=False)
        print("\n 正在播放语音...")
        while sound.is_alive():
            time.sleep(0.1)
    except Exception as e:
        print(f"播放失败: {e}")


def tts_and_play(text):
    """调用 CosyVoice TTS → 播放"""
    print("\n 正在合成语音...")

    resp = requests.post(
        TTS_URL,
        data={"tts_text": text},
        timeout=120,
    )

    if resp.status_code != 200:
        print("❌ TTS 失败:", resp.text)
        return

    wav_path = "assistant.wav"
    pcm_to_wav(resp.content, wav_path)

    play_audio(wav_path)


# ======================
# 主对话逻辑
# ======================
messages = []

print("开始与模型对话（输入 exit 或 quit 退出）")

while True:
    user_input = input("你：").strip()
    if user_input.lower() in ["exit", "quit"]:
        break

    messages.append({"role": "user", "content": user_input})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "max_tokens": 256,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    print("助手：", end="", flush=True)

    response = requests.post(
        VLLM_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        stream=True,
        timeout=120,
    )

    assistant_reply = ""

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue

        if line.startswith("data: "):
            data = line[len("data: ") :]

            if data == "[DONE]":
                break

            chunk = json.loads(data)
            delta = chunk["choices"][0]["delta"]

            if "content" in delta:
                token = delta["content"]
                assistant_reply += token
                print(token, end="", flush=True)

    print("\n")

    messages.append({"role": "assistant", "content": assistant_reply})

    # === 生成完一句再 TTS ===
    if assistant_reply.strip():
        tts_and_play(assistant_reply)

print("对话结束")
