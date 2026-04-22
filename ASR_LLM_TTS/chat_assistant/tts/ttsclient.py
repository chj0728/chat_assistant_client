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
from logger import logger
from playsound3 import playsound
from websockets.exceptions import ConnectionClosed


WORKER_POLL_TIMEOUT_SEC = 0.1 # 后台线程轮询文本队列的超时时间，单位为秒
INTERRUPT_GRACE_PERIOD_SEC = 0.2 # 打断后等待正在播放的音频块自然结束的宽限时间，单位为秒，过短可能导致频繁打断时声音碎片过多，过长可能导致响应不够及时
LOCAL_AUDIO_STOP_WAIT_SEC = 0.1 # 本地音频停止后等待实际停止的宽限时间，单位为秒，过短可能导致声音未完全停止，过长可能导致响应不够及时
WS_STARTUP_WAIT_SEC = 1.0 # WebSocket 运行时预热等待时间，单位为秒，过短可能导致首次请求时连接未准备好，过长可能导致启动延迟增加


class TTSClient:
    def __init__(
        self,
        host,
        port,
        timeout_sec: float = 30.0,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 2048,
        buffer_size: int = 4096,  # 增加缓冲区大小
        speaker_id: int = 0,
        speed: float = 1.0,
        use_websocket: bool = False,
        ws_path: str = "/ws/api/tts",
        ws_ping_interval: Optional[float] = None,
        ws_ping_timeout: Optional[float] = None,
        playback_start_delay_sec: float = 0.0,
    ):
        """_summary_

        Args:
            host (str): TTS server 的主机地址。
            port (int): TTS server 的端口号。
            timeout_sec (float): 请求超时时间，单位为秒。默认值为 30 秒。
            speaker_id (int, optional): 选择的说话人 ID。默认值为 0。
            sample_rate (int, optional): 音频播放的采样率。默认值为 16000。
            channels (int, optional): 音频通道数。默认值为 1。
            chunk_size (int, optional): 音频块的大小。默认值为 2048。
            buffer_size (int, optional): 音频缓冲区的大小。默认值为 4096。
            speed (float, optional): 播放速度。默认值为 1.0。
            use_websocket (bool, optional): 是否使用 WebSocket 进行 TTS。默认值为 False。
            ws_path (str, optional): WebSocket 路径。默认值为 "/ws/api/tts"。
            ws_ping_interval (Optional[float], optional): WebSocket ping 间隔。默认值为 None。
            ws_ping_timeout (Optional[float], optional): WebSocket ping 超时。默认值为 None。
            playback_start_delay_sec (float, optional): 判断起播的延迟时间，单位为秒。默认值为 0.0 秒，即没有延迟。
        """
        self.host = host
        self.port = port
        self.timeout = timeout_sec
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

        # 文本队列 + 音频队列
        self.text_queue: queue.Queue[str] = queue.Queue()
        self.audio_queue: queue.Queue[bytes] = queue.Queue()

        self.sound = None
        self.is_sounding = False
        self._audio_active_started_ts = 0.0  # 首帧时间戳，用于起播确认
        self._last_audio_chunk_ts = 0.0  # 最后一次收到音频块的时间戳，用于挂起判断
        self._playback_start_delay_sec = playback_start_delay_sec  # 起播确认延迟时间
        self._playback_hangover_sec = 0.0  # 结束后的挂起时间
        self._stop_event = threading.Event()
        self._interrupt_event = threading.Event()
        self._audio_lock = threading.Lock()
        self._playback_buffer = np.empty((0, self.channels), dtype=np.float32)

        self.stream = self.__create_output_stream()
        self.stream.start()
        self.tts_thread = self.__start_tts_worker()
        self.__initialize_websocket_if_needed()

    # ================= 私有接口 =================

    def __create_output_stream(self) -> sd.OutputStream:
        """创建音频输出流。"""
        return sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.buffer_size,
            latency="low",
            callback=self.__audio_callback,
        )

    def __start_tts_worker(self) -> threading.Thread:
        """启动后台 TTS worker。"""
        tts_thread = threading.Thread(
            target=self.__tts_loop,
            daemon=True,
            name="tts-worker",
        )
        tts_thread.start()
        return tts_thread

    def __initialize_websocket_if_needed(self) -> None:
        """按需预热 WebSocket 运行时，避免首次请求额外延迟。"""
        if not self.use_websocket:
            return

        self.__start_ws_runtime()
        time.sleep(WS_STARTUP_WAIT_SEC)
        try:
            self.__run_ws_coro(self.__ensure_ws_connected(), timeout=self.timeout)
        except TimeoutError:
            logger.error("TTS WebSocket 连接超时")
        except Exception as e:
            logger.error(f"TTS WebSocket 连接失败: {e}")

    def __build_http_url(self, path: str) -> str:
        return f"http://{self.host}:{self.port}{path}"

    def __reset_playback_state(self) -> None:
        with self._audio_lock:
            self._playback_buffer = np.empty((0, self.channels), dtype=np.float32)
            self._audio_active_started_ts = 0.0
            self._last_audio_chunk_ts = 0.0
        self.is_sounding = False

    @staticmethod
    def __drain_queue(target_queue: queue.Queue) -> None:
        while not target_queue.empty():
            try:
                target_queue.get_nowait()
            except queue.Empty:
                break

    def __stop_local_audio_playback(self) -> None:
        if self.sound is not None and self.sound.is_alive():
            self.sound.stop()
            time.sleep(LOCAL_AUDIO_STOP_WAIT_SEC)

    def __request_stream(self, text: str, data_type: str):
        return requests.post(
            self.__build_http_url("/api/tts"),
            data={
                "tts_text": text,
                "data_type": data_type,
                "sid": self.speaker_id,
                "speed": self.speed,
            },
            timeout=self.timeout,
            stream=data_type == "pcm",
        )

    def __audio_callback(self, outdata, frames, time_info, status):
        del time_info
        now = time.monotonic()
        if status:
            # 回调状态日志保留为 debug，避免刷屏。
            logger.debug(f"音频回调状态: {status}")

        if self._stop_event.is_set() or self._interrupt_event.is_set():
            outdata.fill(0)
            self.is_sounding = False
            self._audio_active_started_ts = 0.0
            self._last_audio_chunk_ts = 0.0
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

        ####### 声音检测逻辑，延迟判断起播音频播放状态 #######
        if filled > 0:
            # 先记录首帧时间；达到起播确认窗口后再判定为播放。
            if self._audio_active_started_ts <= 0.0:
                self._audio_active_started_ts = now
            self._last_audio_chunk_ts = now
            self.is_sounding = (
                now - self._audio_active_started_ts
            ) >= self._playback_start_delay_sec
        else:
            # 短暂挂起窗口用于吸收回调调度抖动，避免状态频繁抖动。
            keep_active = (
                now - self._last_audio_chunk_ts
            ) < self._playback_hangover_sec
            self.is_sounding = keep_active
            if not keep_active:
                self._audio_active_started_ts = 0.0
        ################################################

    def __tts_loop(self):
        """
        严格串行的 TTS worker
        """
        while not self._stop_event.is_set():
            try:
                text = self.text_queue.get(timeout=WORKER_POLL_TIMEOUT_SEC)
            except queue.Empty:
                continue

            start_time = time.time()
            self.__tts_request(text)
            elapsed_time = time.time() - start_time
            logger.debug(f"完整音频传输耗时: {elapsed_time:.2f} 秒")

    def __tts_request(self, text):
        """
        请求服务端并顺序推 PCM
        """
        if self.use_websocket:
            self.__tts_request_ws(text)
            return

        self.__tts_request_http(text)

    def __tts_request_http(self, text):
        try:
            with self.__request_stream(text, data_type="pcm") as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
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

    def __tts_request_ws(self, text):
        try:
            self.__start_ws_runtime()
            self.__run_ws_coro(self.__tts_request_ws_async(text), timeout=self.timeout)
        except TimeoutError:
            logger.error("TTS WebSocket 请求超时")
            self.__run_ws_coro(self.__close_ws_async(), timeout=self.timeout)
        except Exception as e:
            logger.error(f"WebSocket TTS 请求失败: {e}")
            self.__run_ws_coro(self.__close_ws_async(), timeout=self.timeout)

    def __start_ws_runtime(self):
        if self._ws_thread is not None and self._ws_thread.is_alive():
            return

        self._ws_started.clear()
        self._ws_thread = threading.Thread(
            target=self.__ws_loop_worker,
            daemon=True,
            name="tts-ws-loop",
        )
        self._ws_thread.start()

        if not self._ws_started.wait(timeout=5):
            raise RuntimeError("WebSocket 事件循环线程启动超时")

    def __ws_loop_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ws_loop = loop
        self._ws_started.set()
        logger.info("TTS WebSocket 事件循环线程已启动")
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self.__close_ws_async())
            except Exception as e:
                logger.warning(f"WebSocket 线程退出清理失败: {e}")
            finally:
                loop.close()

    def __run_ws_coro(self, coro, timeout: Optional[float]):
        """在 WebSocket 事件循环中运行协程，并等待结果

        Args:
            coro (Coroutine): 要在 WebSocket 事件循环中运行的协程
            timeout (Optional[float]): 等待结果的超时时间（秒），为 None 表示无限等待

        Raises:
            RuntimeError: 如果 WebSocket 事件循环未初始化

        Returns:
            Any: 协程的返回结果
        """
        if self._ws_loop is None:
            raise RuntimeError("WebSocket 事件循环未初始化")

        future = asyncio.run_coroutine_threadsafe(coro, self._ws_loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            raise

    async def __ensure_ws_connected(self):
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
        logger.info(f"TTS WebSocket 已连接: {url}")

    async def __close_ws_async(self):
        if self._ws is None:
            return

        try:
            await self._ws.close()
            logger.info("TTS WebSocket 已关闭")
        except Exception as e:
            logger.warning(f"关闭 TTS WebSocket 失败: {e}")
        finally:
            self._ws = None

    def __close_ws_runtime(self):
        if self._ws_loop is None:
            return

        try:
            self.__run_ws_coro(self.__close_ws_async(), timeout=3)
        except Exception as e:
            logger.warning(f"WebSocket 清理失败: {e}")
        finally:
            if self._ws_loop is not None:
                self._ws_loop.call_soon_threadsafe(self._ws_loop.stop)
            if self._ws_thread is not None:
                self._ws_thread.join(timeout=3)
            self._ws_loop = None
            self._ws_thread = None

    async def __tts_request_ws_async(self, text):
        payload = {
            "tts_text": text,
            "sid": self.speaker_id,
            "speed": self.speed,
        }

        for attempt in range(2):
            await self.__ensure_ws_connected()
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
            with self.__request_stream(text, data_type="wav") as resp:
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
        self._interrupt_event.clear()

        normalized_text = text.strip()
        if not normalized_text:
            return

        if interrupt:
            self.interrupt()

        self.text_queue.put(normalized_text)

    def is_active(self):
        """检查播放器是否正在播放音频"""
        return (
            self.is_sounding
            # or not self.audio_queue.empty()
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
            self.__stop_local_audio_playback()

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

        time.sleep(INTERRUPT_GRACE_PERIOD_SEC)

        if not self.text_queue.empty() or not self.audio_queue.empty():
            logger.info("正在清空播放队列...")

        self.__drain_queue(self.text_queue)
        self.__drain_queue(self.audio_queue)
        self.__reset_playback_state()
        # if self.sound is not None and self.sound.is_alive():
        self.__stop_local_audio_playback()
        logger.info("正在停止当前播放的音频...")

        self._interrupt_event.clear()

    def get_playback_start_delay_sec(self):
        return self._playback_start_delay_sec

    def stop(self):
        """停止播放器"""
        self._stop_event.set()
        self.interrupt()
        self.__close_ws_runtime()
        self.stream.stop()
        self.stream.close()
        self.tts_thread.join(timeout=3)


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
