import requests
import sounddevice as sd
import numpy as np

TTS_URL = "http://192.168.50.125:50000/inference_zero_shot"
SAMPLE_RATE = 24000
CHANNELS = 1


def realtime_tts(text):
    with sd.OutputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=0,  # 自动
    ) as stream:

        with requests.post(
            TTS_URL,
            data={"tts_text": text},
            stream=True,
        ) as resp:

            for chunk in resp.iter_content(chunk_size=4096):
                if not chunk:
                    continue

                pcm = np.frombuffer(chunk, dtype=np.int16)
                stream.write(pcm)

    print("✅ 播放完成")


if __name__ == "__main__":
    realtime_tts(
        "你好呀！我是千问，阿里巴巴集团旗下的通义实验室研发的超大规模语言模型。"
    )
