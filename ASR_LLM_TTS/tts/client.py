import requests
import wave

import time

# 引入 playsound3 库以支持非阻塞播放 wav 文件
from playsound3 import playsound

TTS_URL = "http://192.168.50.125:50000/inference_zero_shot"
SAMPLE_RATE = 24000


def play_audio(file_path):
    try:
        sound = playsound(file_path, block=False)
        while sound.is_alive():
            time.sleep(0.1)  # 等待音频播放结束
        print("播放完成！")
    except Exception as e:
        print(f"播放失败: {e}")


# 将 PCM 字节数据保存为 WAV 文件
def pcm_to_wav(pcm_bytes, filename, sample_rate=24000):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def test_post_request_raw():
    """测试 POST 请求，返回原始 PCM 数据"""
    print("\n测试 POST 请求...")
    text = "你好呀！我是千问，阿里巴巴集团旗下的通义实验室研发的超大规模语言模型。请问有什么可以帮到你的吗？"

    url = TTS_URL

    response = requests.post(url, data={"tts_text": text})
    print(f"状态码: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")

    if response.status_code == 200:
        pcm_to_wav(response.content, "output_post.wav")

        print(f"POST 请求成功，保存到 output_post.wav")
        verify_audio("output_post.wav")
        return True
    else:
        print(f"POST 请求失败: {response.text}")
        return False


def test_post_request_wave():
    """测试 POST 请求，返回 wav 格式"""
    print("\n测试 POST 请求，返回 wav 格式...")
    text = "你好呀！我是千问，阿里巴巴集团旗下的通义实验室研发的超大规模语言模型。"

    url = TTS_URL

    response = requests.post(url, data={"tts_text": text, "data_type": "wav"})
    print(f"状态码: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")

    if response.status_code == 200:
        with open("output_post.wav", "wb") as f:
            f.write(response.content)
        print(f"POST 请求成功，保存到 output_post.wav")
        # 验证音频文件
        verify_audio("output_post.wav")
    else:
        print(f"POST 请求失败: {response.text}")


def generate_wav(text, filename):
    """生成 WAV 文件"""
    url = TTS_URL

    response = requests.post(url, data={"tts_text": text, "data_type": "wav"})
    print(f"状态码: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")

    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"POST 请求成功，保存到 {filename}")
        # 验证音频文件
        verify_audio(filename)
    else:
        print(f"POST 请求失败: {response.text}")


def verify_audio(filename):
    """验证音频文件"""
    try:
        with wave.open(filename, "rb") as wav_file:
            print(f"音频信息:")
            print(f"  声道数: {wav_file.getnchannels()}")
            print(f"  采样宽度: {wav_file.getsampwidth()} 字节")
            print(f"  采样率: {wav_file.getframerate()} Hz")
            print(f"  帧数: {wav_file.getnframes()}")
            print(f"  时长: {wav_file.getnframes() / wav_file.getframerate():.2f} 秒")
    except Exception as e:
        print(f"验证音频文件失败: {e}")


if __name__ == "__main__":

    test_post_request_wave()
    play_audio("output_post.wav")

    time.sleep(2)
    test_post_request_raw()
    play_audio("output_post.wav")

    # generate_wav("你好", "hello.wav")
    # play_audio("hello.wav")

    # time.sleep(2)
    # generate_wav("介绍一下你自己吧！", "intro.wav")
    # play_audio("intro.wav")
