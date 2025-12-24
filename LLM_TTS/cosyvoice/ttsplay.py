import threading
import queue
import requests
import numpy as np
from playsound3 import playsound
import sounddevice as sd
import time


import queue
import threading
import time
import requests
import numpy as np
import sounddevice as sd


class RealtimeTTSPlayer:
    def __init__(
        self,
        tts_url,
        sample_rate=24000,
        channels=1,
        chunk_size=4096,
    ):
        self.tts_url = tts_url
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size

        # 文本队列 + 音频队列
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()

        self.is_sounding = False
        self._stop_event = threading.Event()

        # 音频输出流
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=0,
        )
        self.stream.start()

        # 播放线程（只负责播）
        self.play_thread = threading.Thread(
            target=self._play_loop,
            daemon=True,
        )
        self.play_thread.start()

        # TTS 线程
        self.tts_thread = threading.Thread(
            target=self._tts_loop,
            daemon=True,
        )
        self.tts_thread.start()

    # ================= 私有接口 =================

    def _play_loop(self):
        while not self._stop_event.is_set():
            try:
                data = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                self.is_sounding = False
                time.sleep(0.1)
                continue

            self.is_sounding = True
            try:
                pcm = np.frombuffer(data, dtype=np.int16)
                self.stream.write(pcm)
            except Exception as e:
                print("音频播放出错:", e)

    def _tts_loop(self):
        """
        严格串行的 TTS worker
        """
        while not self._stop_event.is_set():
            try:
                text = self.text_queue.get(timeout=0.1)
            except queue.Empty:
                time.sleep(0.1)
                continue

            self._tts_request(text)

    def _tts_request(self, text):
        """
        请求 CosyVoice，并顺序推 PCM
        """
        try:
            with requests.post(
                self.tts_url, data={"tts_text": text, "data_type": "pcm"}, stream=True
            ) as resp:
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    if self._stop_event.is_set():
                        return
                    if not chunk:
                        continue
                    self.audio_queue.put(chunk)
        except Exception as e:
            print("TTS 请求失败:", e)

    # ================= 公共接口 =================

    def generate_wav(self, text, filename):
        """
        根据文本生成 WAV 文件（阻塞）
        """
        try:
            with requests.post(
                self.tts_url,
                data={"tts_text": text, "data_type": "wav"},
            ) as resp:
                with open(filename, "wb") as f:
                    f.write(resp.content)
            print(f"WAV 文件已保存到 {filename}")
        except Exception as e:
            print("TTS 请求失败:", e)
            return None

    def speak(self, text, interrupt=False):
        """
        只负责把文本放进队列，不阻塞，由后台线程处理并播放语音合成
        """
        if not text.strip():
            return

        if interrupt:
            self.clear()

        self.text_queue.put(text)

    def is_active(self):
        """检查播放器是否正在播放音频"""
        return (
            self.is_sounding
            or not self.text_queue.empty()
            or not self.audio_queue.empty()
        )

    def play_audio(self, file_path):
        """播放本地音频文件（阻塞）"""
        try:
            sound = playsound(file_path, block=False)
            while sound.is_alive():
                time.sleep(0.1)  # 等待音频播放结束
            print("播放完成！")
        except Exception as e:
            print(f"播放失败: {e}")

    def clear(self):
        """打断：清空文本 + 音频"""
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
            except queue.Empty:
                break

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def stop(self):
        """停止播放器"""
        self._stop_event.set()
        self.stream.stop()
        self.stream.close()

        self.play_thread.join()
        self.tts_thread.join()


if __name__ == "__main__":

    tts_player = RealtimeTTSPlayer(
        tts_url="http://192.168.50.125:50000/inference_zero_shot"
    )

    # real-time TTS with no interruption
    tts_player.speak("我叫千问，是Qwen3模型驱动的智能助手，专注于回答各种问题。")
    time.sleep(2)

    # tts_player.speak("您好！有什么可以帮助您的吗？")
    # time.sleep(2)

    # interrupt with a new sentence
    # tts_player.speak("这是一段新的语音，会打断之前的播放。", interrupt=True)
    # time.sleep(2)

    # # 等待播放完成
    # while tts_player.is_active():
    #     time.sleep(0.5)
    # tts_player.stop()

    # # generate wav file
    # tts_player.generate_wav(
    #     "这是通过生成 WAV 文件的方式保存的语音合成示例。",
    #     "example.wav",
    # )
    # # play local audio file
    # tts_player.play_audio("example.wav")

    # tts_player.generate_wav(
    #     "你好，千问",
    #     "hello_qianwen.wav",
    # )
    # # play local audio file
    # tts_player.play_audio("hello_qianwen.wav")
    # tts_player.stop()

    print("播放器已关闭。")
