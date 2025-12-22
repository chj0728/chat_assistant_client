import threading
import queue
import requests
import numpy as np
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

    # ================= 播放 =================

    def _play_loop(self):
        while not self._stop_event.is_set():
            try:
                data = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                self.is_sounding = False
                continue

            self.is_sounding = True
            try:
                pcm = np.frombuffer(data, dtype=np.int16)
                self.stream.write(pcm)
            except Exception as e:
                print("音频播放出错:", e)

    # ================= TTS =================

    def speak(self, text, interrupt=True):
        """
        只负责把文本放进队列
        """
        if not text.strip():
            return

        if interrupt:
            self.clear()

        self.text_queue.put(text)

    def _tts_loop(self):
        """
        严格串行的 TTS worker
        """
        while not self._stop_event.is_set():
            try:
                text = self.text_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._tts_request(text)

    def _tts_request(self, text):
        """
        请求 CosyVoice，并顺序推 PCM
        """
        try:
            with requests.post(
                self.tts_url,
                data={"tts_text": text},
                stream=True,
            ) as resp:
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    if self._stop_event.is_set():
                        return
                    if not chunk:
                        continue
                    self.audio_queue.put(chunk)
        except Exception as e:
            print("TTS 请求失败:", e)

    # ================= 控制 =================

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
        self._stop_event.set()
        self.stream.stop()
        self.stream.close()


if __name__ == "__main__":

    tts_player = RealtimeTTSPlayer(
        tts_url="http://192.168.50.125:50000/inference_zero_shot"
    )

    tts_player.speak("你好呀！请问有什么可以帮到你的吗？")

    time.sleep(5)

    tts_player.speak("这是一段新的语音，会打断上一段。")

    time.sleep(5)
    tts_player.stop()
    print("播放器已关闭。")
