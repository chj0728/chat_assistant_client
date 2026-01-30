import threading
import queue
import requests
import numpy as np
from playsound3 import playsound
import sounddevice as sd
import time
import wave


import queue
import threading
import time
import requests
import numpy as np
import sounddevice as sd

from logger import logger


class RealtimeTTSPlayer:
    def __init__(
        self,
        host,
        port,
        sample_rate: int = 48000,
        channels: int = 1,
        chunk_size: int = 4096,
        buffer_size: int = 8192,  # 增加缓冲区大小
    ):
        self.host = host
        self.port = port
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.buffer_size = buffer_size  # 增加缓冲区大小
        self.preset = "default"  # "default"(女性活泼), "zh"(男性非标准) , "hard_zh"(男性业余), "longshu_zh"(男性专业), "longwan_zh"（女性专业）

        # 文本队列 + 音频队列
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue(maxsize=10)

        self.sound = None
        self.is_sounding = False
        self._stop_event = threading.Event()
        self._interrupt_event = threading.Event()

        # 音频输出流
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.buffer_size,  # 使用更大的缓冲区
            latency="high",
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

            if self._interrupt_event.is_set():
                self.is_sounding = False
                time.sleep(0.1)
                continue
            try:
                data = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                self.is_sounding = False
                time.sleep(0.1)
                continue

            self.is_sounding = True
            try:
                pcm = np.frombuffer(data, dtype=np.int16)
                self.stream.write(pcm)
            except Exception as e:
                # print("音频播放出错:", e)
                logger.error(f"音频播放出错: {e}")

    def _tts_loop(self):
        """
        严格串行的 TTS worker
        """
        while not self._stop_event.is_set():

            time.sleep(0.1)

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
                "http://" + self.host + f":{self.port}/inference_zero_shot",
                data={"tts_text": text, "data_type": "pcm", "preset": self.preset},
                stream=True,
            ) as resp:
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    # 检查停止或打断标志
                    if self._stop_event.is_set():
                        return
                    if self._interrupt_event.is_set():
                        return
                    if not chunk:
                        continue
                    self.audio_queue.put(chunk)
        except Exception as e:
            # print("TTS 请求失败:", e)
            logger.error(f"TTS 请求失败: {e}")

    # ================= 公共接口 =================

    def generate_wav(self, text, filename, preset="default"):
        """
        根据文本生成 WAV 文件（阻塞）

        preset 可选值: "default"(女性活泼), "zh"(男性非标准) , "hard_zh"(男性业余), "longshu_zh"(男性专业), "longwan_zh"（女性专业）
        依据 preset 选择不同的接口
        """
        try:
            with requests.post(
                "http://" + self.host + f":{self.port}/inference_zero_shot",
                data={"tts_text": text, "data_type": "wav", "preset": preset},
            ) as resp:
                with open(filename, "wb") as f:
                    f.write(resp.content)
            # print(f"WAV 文件已保存到 {filename}")
            logger.info(f"WAV 文件已保存到 {filename}")
            return filename
        except Exception as e:
            # print("TTS 请求失败:", e)
            logger.error(f"TTS 请求失败: {e}")
            return None

    def generate_wav_zh(self, text, filename):
        """
        根据文本生成 WAV 文件（阻塞）
        """
        try:
            with requests.post(
                "http://" + self.host + f":{self.port}/inference_zero_shot_zh",
                data={"tts_text": text, "data_type": "wav"},
            ) as resp:
                with open(filename, "wb") as f:
                    f.write(resp.content)
            # print(f"WAV 文件已保存到 {filename}")
            logger.info(f"WAV 文件已保存到 {filename}")
            return filename
        except Exception as e:
            # print("TTS 请求失败:", e)
            logger.error(f"TTS 请求失败: {e}")
            return None

    def generate_wav_hard_zh(self, text, filename):
        """
        根据文本生成 WAV 文件（阻塞）
        """
        try:
            with requests.post(
                "http://" + self.host + f":{self.port}/inference_zero_shot_hard_zh",
                data={"tts_text": text, "data_type": "wav"},
            ) as resp:
                with open(filename, "wb") as f:
                    f.write(resp.content)
            # print(f"WAV 文件已保存到 {filename}")
            logger.info(f"WAV 文件已保存到 {filename}")
            return filename
        except Exception as e:
            # print("TTS 请求失败:", e)
            logger.error(f"TTS 请求失败: {e}")
            return None

    def generate_wav_longshu_zh(self, text, filename):
        """
        根据文本生成 WAV 文件（阻塞）
        """
        try:
            with requests.post(
                "http://" + self.host + f":{self.port}/inference_zero_shot_longshu_zh",
                data={"tts_text": text, "data_type": "wav"},
            ) as resp:
                with open(filename, "wb") as f:
                    f.write(resp.content)
            # print(f"WAV 文件已保存到 {filename}")
            logger.info(f"WAV 文件已保存到 {filename}")
            return filename
        except Exception as e:
            # print("TTS 请求失败:", e)
            logger.error(f"TTS 请求失败: {e}")
            return None

    def generate_wav_longwan_zh(self, text, filename):
        """
        根据文本生成 WAV 文件（阻塞）
        """
        try:
            with requests.post(
                "http://" + self.host + f":{self.port}/inference_zero_shot_longwan_zh",
                data={"tts_text": text, "data_type": "wav"},
            ) as resp:
                with open(filename, "wb") as f:
                    f.write(resp.content)
            # print(f"WAV 文件已保存到 {filename}")
            logger.info(f"WAV 文件已保存到 {filename}")
            return filename
        except Exception as e:
            # print("TTS 请求失败:", e)
            logger.error(f"TTS 请求失败: {e}")
            return None

    def change_preset(self, preset):
        """
        更改 TTS 预设
        preset 可选值: "default"(女性活泼), "zh"(男性非标准) , "hard_zh"(男性业余), "longshu_zh"(男性专业), "longwan_zh"（女性专业）
        """
        self.preset = preset
        logger.info(f"TTS 预设已更改为: {preset}")

    def speak(self, text, interrupt=True):
        """
        只负责把文本放进队列，不阻塞，由后台线程处理并播放语音合成
        """
        # 清除打断标志
        self._interrupt_event.clear()

        if not text.strip():
            return

        if interrupt:
            self.interrupt()

        self.text_queue.put(text)

    def is_active(self):
        """检查播放器是否正在播放音频"""
        return (
            self.is_sounding
            # or not self.text_queue.empty()
            # or not self.audio_queue.empty()
            # or not self.stream.stopped
            # not self.stream.stopped
            # self.stream.active
            # self.sound is not None
            or (self.sound is not None and self.sound.is_alive())
        )

    def play_audio(self, file_path, block=False):
        """播放本地音频文件（阻塞/非阻塞）"""
        try:
            # 如果有正在播放的音频，先停止它
            if self.sound is not None and self.sound.is_alive():
                self.sound.stop()
                time.sleep(0.1)  # 等待音频停止

            self.sound = playsound(file_path, block=block)

            # currunt_time = time.time()
            # while self.sound.is_alive():
            #     if time.time() - currunt_time > 30:
            #         print("播放超时，强制结束")
            #         break
            #     if self._interrupt_event.is_set():
            #         logger.info("播放被打断，停止播放音频")
            #         break
            #     time.sleep(0.1)  # 等待音频播放结束
            # # print("播放完成！")

            logger.info(f"开始播放音频文件: {file_path}")
        except Exception as e:

            logger.error(f"播放{file_path}失败: {e}")

    def play_audio_from_pcm(self, pcm_bytes):
        """从 PCM 字节数据播放音频（阻塞）"""
        with wave.open("temp.wav", "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)
        self.play_audio("temp.wav")

    def interrupt(self):
        """打断：清空文本 + 音频"""
        self._interrupt_event.set()

        time.sleep(0.2)

        if not self.text_queue.empty() or not self.audio_queue.empty():
            logger.info("正在清空播放队列...")

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

        if self.sound is not None and self.sound.is_alive():
            self.sound.stop()
            time.sleep(0.1)
            logger.info("正在停止当前播放的音频...")

        self._interrupt_event.clear()

    def stop(self):
        """停止播放器"""
        self._stop_event.set()
        self.stream.stop()
        self.stream.close()

        self.play_thread.join()
        self.tts_thread.join()


if __name__ == "__main__":

    tts_player = RealtimeTTSPlayer(
        host="192.168.50.125",
        port=50000,
    )

    # real-time TTS with no interruption
    tts_player.speak("我叫千问，是Qwen3模型驱动的智能助手，专注于回答各种问题。")
    time.sleep(1)

    # tts_player.speak("您好！有什么可以帮助您的吗？")
    # time.sleep(2)

    # interrupt with a new sentence
    # tts_player.speak("这是一段新的语音，会打断之前的播放。", interrupt=True)
    # time.sleep(2)

    # 等待播放完成
    while tts_player.is_active():
        # print("正在播放...")
        logger.info("正在播放...")
        time.sleep(0.5)
    # tts_player.stop()

    # # generate wav file
    # tts_player.generate_wav(
    #     "这是通过生成 WAV 文件的方式保存的语音合成示例。",
    #     "example.wav",
    # )
    # tts_player.play_audio("example.wav", block=True)

    # tts_player.generate_wav_zh(
    #     "这是通过生成 WAV 文件的方式保存的语音合成示例。",
    #     "example_zh.wav",
    # )
    # tts_player.play_audio("example_zh.wav", block=True)

    # tts_player.generate_wav_hard_zh(
    #     "这是通过生成 WAV 文件的方式保存的语音合成示例。",
    #     "example_hard_zh.wav",
    # )
    # tts_player.play_audio("example_hard_zh.wav", block=True)

    # tts_player.generate_wav_longshu_zh(
    #     "这是通过生成 WAV 文件的方式保存的语音合成示例。",
    #     "example_longshu_zh.wav",
    # )
    # tts_player.play_audio("example_longshu_zh.wav", block=True)

    # tts_player.generate_wav_longwan_zh(
    #     "这是通过生成 WAV 文件的方式保存的语音合成示例。",
    #     "example_longwan_zh.wav",
    # )
    # tts_player.play_audio("example_longwan_zh.wav", block=True)

    # tts_player.generate_wav(
    #     "你好，千问",
    #     "hello_qianwen.wav",
    # )
    # # play local audio file
    # tts_player.play_audio("hello_qianwen.wav")
    # tts_player.stop()

    # print("播放器已关闭。")
    logger.info("播放器已关闭。")
