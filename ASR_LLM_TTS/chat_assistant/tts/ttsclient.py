import asyncio
import json
import queue
import threading
import time
import wave
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Optional

import numpy as np
import requests
import sounddevice as sd
import websockets
from websockets.exceptions import ConnectionClosed
from playsound3 import playsound

from logger import logger


class TTSClient:
    def __init__(
        self,
        host,
        port,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 2048,
        buffer_size: int = 8192,  # 增加缓冲区大小
        speaker_id: int = 0,
        speed: float = 1.0,
        use_websocket: bool = False,
        ws_path: str = "/ws/inference_zero_shot",
        ws_ping_interval: Optional[float] = None,
        ws_ping_timeout: Optional[float] = None,
    ):
        self.host = host
        self.port = port
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.buffer_size = buffer_size  # 增加缓冲区大小
        self.speaker_id = speaker_id
        self.speed = speed
        self.use_websocket = use_websocket
        self.ws_path = ws_path
        self.ws_ping_interval = ws_ping_interval
        self.ws_ping_timeout = ws_ping_timeout
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_started = threading.Event()

        if self.use_websocket:
            self._start_ws_runtime()

        # 文本队列 + 音频队列
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()

        self.sound = None
        self.is_sounding = False
        self._stop_event = threading.Event()
        self._interrupt_event = threading.Event()
        self._audio_lock = threading.Lock()
        self._playback_buffer = np.empty((0, self.channels), dtype=np.float32)

        # 回调式音频输出流。队列空时自动补静音，避免设备断粮 underrun。
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.buffer_size,
            latency="low",
            callback=self._audio_callback,
        )
        self.stream.start()

        # TTS 线程
        self.tts_thread = threading.Thread(
            target=self._tts_loop,
            daemon=True,
        )
        self.tts_thread.start()

    # ================= 私有接口 =================

    def _audio_callback(self, outdata, frames, time_info, status):
        del time_info
        if status:
            # 回调状态日志保留为 debug，避免刷屏。
            logger.debug(f"音频回调状态: {status}")

        if self._stop_event.is_set() or self._interrupt_event.is_set():
            outdata.fill(0)
            self.is_sounding = False
            return

        filled = 0
        with self._audio_lock:
            while filled < frames:
                if self._playback_buffer.shape[0] == 0:
                    try:
                        chunk = self.audio_queue.get_nowait()
                    except queue.Empty:
                        break

                    pcm = np.frombuffer(chunk, dtype=np.float32)
                    if pcm.size == 0:
                        continue
                    if pcm.size % self.channels != 0:
                        logger.warning("丢弃未对齐的音频块")
                        continue
                    self._playback_buffer = np.ascontiguousarray(
                        pcm.reshape(-1, self.channels)
                    )

                take = min(frames - filled, self._playback_buffer.shape[0])
                outdata[filled : filled + take] = self._playback_buffer[:take]
                self._playback_buffer = self._playback_buffer[take:]
                filled += take

        if filled < frames:
            outdata[filled:].fill(0)

        self.is_sounding = filled > 0

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

            start_time = time.time()
            self._tts_request(text)
            elapsed_time = time.time() - start_time
            logger.info(f"完整音频传输耗时: {elapsed_time:.2f} 秒")

    def _tts_request(self, text):
        """
        请求服务端并顺序推 PCM
        """
        if self.use_websocket:
            self._tts_request_ws(text)
            return

        self._tts_request_http(text)

    def _tts_request_http(self, text):
        try:
            with requests.post(
                "http://" + self.host + f":{self.port}/inference_zero_shot",
                data={
                    "tts_text": text,
                    "data_type": "pcm",
                    "sid": self.speaker_id,
                    "speed": self.speed,
                },
                stream=True,
            ) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    # 检查停止或打断标志
                    if self._stop_event.is_set():
                        return
                    if self._interrupt_event.is_set():
                        return
                    if not chunk:
                        continue
                    self.audio_queue.put(chunk)
                    # logger.info(f"TTS 推送音频块，大小: {len(chunk)} 字节")
        except Exception as e:
            logger.error(f"HTTP TTS 请求失败: {e}")

    def _tts_request_ws(self, text):
        try:
            self._start_ws_runtime()
            self._run_ws_coro(self._tts_request_ws_async(text), timeout=None)
        except Exception as e:
            logger.error(f"WebSocket TTS 请求失败: {e}")
            self._run_ws_coro(self._close_ws_async(), timeout=3)

    def _start_ws_runtime(self):
        if self._ws_thread is not None and self._ws_thread.is_alive():
            return

        self._ws_started.clear()
        self._ws_thread = threading.Thread(
            target=self._ws_loop_worker,
            daemon=True,
            name="tts-ws-loop",
        )
        self._ws_thread.start()

        if not self._ws_started.wait(timeout=5):
            raise RuntimeError("WebSocket 事件循环线程启动超时")

    def _ws_loop_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ws_loop = loop
        self._ws_started.set()
        logger.info("TTS WebSocket 事件循环线程已启动")
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self._close_ws_async())
            except Exception as e:
                logger.warning(f"WebSocket 线程退出清理失败: {e}")
            finally:
                loop.close()

    def _run_ws_coro(self, coro, timeout: Optional[float]):
        if self._ws_loop is None:
            raise RuntimeError("WebSocket 事件循环未初始化")

        future = asyncio.run_coroutine_threadsafe(coro, self._ws_loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            raise

    async def _ensure_ws_connected(self):
        # Reuse an existing connection object. If it's stale, send/recv will
        # raise ConnectionClosed and retry logic will reconnect.
        if self._ws is not None:
            return

        url = f"ws://{self.host}:{self.port}{self.ws_path}"
        self._ws = await websockets.connect(
            url,
            max_size=None,
            ping_interval=self.ws_ping_interval,
            ping_timeout=self.ws_ping_timeout,
        )
        logger.info(f"WebSocket 已连接: {url}")

    async def _close_ws_async(self):
        if self._ws is None:
            return

        try:
            await self._ws.close()
            logger.info("WebSocket 已关闭")
        except Exception as e:
            logger.warning(f"关闭 WebSocket 失败: {e}")
        finally:
            self._ws = None

    def _close_ws_runtime(self):
        if self._ws_loop is None:
            return

        try:
            self._run_ws_coro(self._close_ws_async(), timeout=3)
        except Exception as e:
            logger.warning(f"WebSocket 清理失败: {e}")
        finally:
            if self._ws_loop is not None:
                self._ws_loop.call_soon_threadsafe(self._ws_loop.stop)
            if self._ws_thread is not None:
                self._ws_thread.join(timeout=3)
            self._ws_loop = None
            self._ws_thread = None

    async def _tts_request_ws_async(self, text):
        payload = {
            "tts_text": text,
            "sid": self.speaker_id,
            "speed": self.speed,
        }

        for attempt in range(2):
            await self._ensure_ws_connected()
            assert self._ws is not None

            try:
                await self._ws.send(json.dumps(payload, ensure_ascii=False))

                while True:
                    if self._stop_event.is_set() or self._interrupt_event.is_set():
                        return

                    message = await self._ws.recv()

                    if isinstance(message, bytes):
                        self.audio_queue.put(message)
                        continue

                    try:
                        event = json.loads(message)
                    except json.JSONDecodeError:
                        logger.warning(f"收到无法解析的 WebSocket 文本消息: {message}")
                        continue

                    event_name = event.get("event")
                    if event_name == "done":
                        return

                    if event_name == "error":
                        logger.error(f"WebSocket TTS 返回错误: {event.get('detail')}")
                        return

                    logger.info(f"收到 WebSocket 事件: {event}")
            except ConnectionClosed as e:
                logger.warning(f"WebSocket 已断开，准备重连: {e}")
                self._ws = None
                if attempt == 1:
                    raise

    # ================= 公共接口 =================

    def generate_wav(self, text, filename) -> bool:
        try:
            url = f"http://{self.host}:{self.port}/inference_zero_shot"

            resp = requests.post(
                url,
                data={
                    "tts_text": text,
                    "data_type": "wav",
                    "sid": self.speaker_id,
                    "speed": self.speed,
                },
            )

            resp.raise_for_status()

            if "audio" not in resp.headers.get("Content-Type", ""):
                logger.error("返回不是音频")
                logger.error(resp.text)
                return False

            with open(filename, "wb") as f:
                f.write(resp.content)
            return True

        except Exception as e:
            logger.error(f"TTS 请求失败: {e}")
            return False

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
            or not self.audio_queue.empty()
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

        with self._audio_lock:
            self._playback_buffer = np.empty((0, self.channels), dtype=np.float32)

        if self.sound is not None and self.sound.is_alive():
            self.sound.stop()
            time.sleep(0.1)
            logger.info("正在停止当前播放的音频...")

        self._interrupt_event.clear()

    def stop(self):
        """停止播放器"""
        self._stop_event.set()
        self._close_ws_runtime()
        self.stream.stop()
        self.stream.close()
        self.tts_thread.join()


if __name__ == "__main__":

    tts_client = TTSClient(host="192.168.50.107", port=50000, speaker_id=0, speed=1.0)

    # 测试 TTS 播放
    tts_client.speak("你好，这是一段测试语音。")
    time.sleep(1)
    while tts_client.is_active():
        time.sleep(1)
    logger.info("播放完成")

    # 测试生成 WAV 文件
    tts_client.generate_wav(
        "你好，这是一段测试语音保存的语音合成示例。",
        "./wavs/example.wav",
    )
    logger.info("WAV 文件生成完成")

    tts_ws_client = TTSClient(
        host="192.168.50.107",
        port=50000,
        speaker_id=0,
        speed=1.0,
        use_websocket=True,
    )
    # 测试 WebSocket TTS 播放
    tts_ws_client.speak("你好，这是一段通过 WebSocket 接收的测试语音。")
    time.sleep(2)
    while tts_ws_client.is_active():
        time.sleep(1)
    logger.info("WebSocket 播放完成")
    time.sleep(2)
