import asyncio
import json
import os
import queue
import re
import threading
import time
import wave
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Optional

import numpy as np
import requests
import websockets
from websockets.exceptions import ConnectionClosed

try:
    import sounddevice as sd
except ImportError:
    sd = None

from logger import logger


class ASRClient:
    """
    ASRClient 支持两种模式：\n
    1. HTTP 模式：通过 HTTP POST 请求发送 wav 文件进行识别
    2. WebSocket 模式：通过 WebSocket 连接发送音频数据流进行实时识别，并接收识别结果
    使用 WebSocket 模式时，ASRClient 会在后台启动一个事件循环线程来管理 WebSocket 连接
    """

    def __init__(
        self,
        host="192.168.50.125",
        port=2002,
        timeout_sec: float = 30.0,
        use_websocket: bool = False,
        ws_path: str = "/ws/api/asr",
        ws_ping_interval: Optional[float] = None,
        ws_ping_timeout: Optional[float] = None,
        samples_per_message: int = 8000,
        seconds_per_message: float = 0.1,
        asr_queue_size: int = 20,
        mic_channels: int = 1,
        mic_samplerate: int = 16000,
        mic_block_seconds: float = 0.05,
    ):
        """
        :param host: ASR 服务地址
        :param port: ASR 服务端口
        :param timeout_sec: 请求超时时间（秒）
        :param use_websocket: 是否使用 WebSocket 流式识别
        :param ws_path: WebSocket 路径
        :param ws_ping_interval: WebSocket ping 间隔
        :param ws_ping_timeout: WebSocket ping 超时
        :param samples_per_message: 每次通过 WS 发送的采样点数量
        :param seconds_per_message: 模拟实时发送时每块之间的间隔（秒）
        :param asr_queue_size: 识别结果队列大小（满时丢弃最旧）
        :param mic_channels: 麦克风输入通道数
        :param mic_samplerate: 麦克风采样率
        :param mic_block_seconds: 麦克风每块时长（秒）
        """
        self.host = host
        self.port = port
        self.timeout = timeout_sec
        self.use_websocket = use_websocket
        self.ws_path = ws_path
        self.ws_ping_interval = ws_ping_interval
        self.ws_ping_timeout = ws_ping_timeout
        self.samples_per_message = samples_per_message
        self.seconds_per_message = seconds_per_message
        self.mic_channels = mic_channels
        self.mic_samplerate = mic_samplerate
        self.mic_block_seconds = mic_block_seconds

        self._asr_text_queue: queue.Queue[str] = queue.Queue(maxsize=asr_queue_size)

        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_started = threading.Event()

        self._mic_thread: Optional[threading.Thread] = None
        self._mic_loop: Optional[asyncio.AbstractEventLoop] = None
        self._mic_started = threading.Event()
        self._mic_stop_event = threading.Event()

        ############# 如果使用 WebSocket 模式，提前启动事件循环线程，避免首次请求时的启动延迟 #############
        if self.use_websocket:
            self._start_ws_runtime()
            # self.start_mic_stream() # 目前不默认启动麦克风流式识别，由上层传输wav文件时调用 recognize() 方法即可
            time.sleep(1.0)  # 确保事件循环线程启动完成
            try:
                self._run_ws_coro(self._ensure_ws_connected(), timeout=self.timeout)
            except TimeoutError:
                logger.error("ASR WebSocket 连接超时")
            except Exception as e:
                logger.error(f"ASR WebSocket 连接异常: {e}")
        ###################################################################

    ############ 公共接口 ############
    def recognize(self, wav_path: str, use_websocket: Optional[bool] = True) -> str:
        """
        发送 wav 文件，返回识别文本

        :param wav_path: wav 文件路径
        :param use_websocket: 是否使用 WebSocket 模式进行识别，默认为 True（使用 WebSocket 请求）
        :return: 识别文本
        """
        if not self.use_websocket and use_websocket:
            logger.warning(
                "ASRClient 当前未启用 WebSocket 模式，默认使用 HTTP 请求进行识别。"
            )
            return self._clean_asr_text(self._recognize_http(wav_path))

        if self.use_websocket and use_websocket:
            return self._clean_asr_text(self._recognize_ws(wav_path))

        return self._clean_asr_text(self._recognize_http(wav_path))

    ###################################

    def _clean_asr_text(self, text: str) -> str:
        # 1. 删除 <unk>
        text = re.sub(r"<unk>", "", text)

        # 2. 合并多空格
        text = re.sub(r"\s+", " ", text)

        # # 3. 合并类似 "s s v v" → "ssvv"
        # text = re.sub(r"\b([a-zA-Z])\s+(?=[a-zA-Z]\b)", r"\1", text)

        return text.strip()

    def _recognize_http(self, wav_path: str) -> str:
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Wav file not found: {wav_path}")

        with open(wav_path, "rb") as f:
            files = {"file": (os.path.basename(wav_path), f, "audio/wav")}

            response = requests.post(
                "http://" + self.host + ":" + str(self.port) + "/api/asr",
                files=files,
                timeout=self.timeout,
            )

        if response.status_code != 200:

            logger.error(f"ASR server error [{response.status_code}]: {response.text}")
            raise RuntimeError(
                f"ASR server error [{response.status_code}]: {response.text}"
            )

        result = response.json()

        if result.get("code") != 0:
            logger.error(f"ASR failed: {result.get('msg')}")
            raise RuntimeError(f"ASR failed: {result.get('msg')}")

        # 只提取 speaker_id 为 0 的文本
        # spk_0_tex = ""
        # sentences = result.get("sentences", [])
        # for sentence in sentences:
        #     logger.info(
        #         f"speaker_id={sentence.get('speaker_id')}:start={sentence['start']:.2f}, end={sentence['end']:.2f}, text={sentence['text']}"
        #     )
        #     if sentence.get("speaker_id") == 0:
        #         spk_0_tex += sentence["text"] + " "

        # logger.info(f"Speaker 0 Text: {spk_0_tex.strip()}")
        # # return result.get("text", "")
        # return spk_0_tex.strip()

        # # 如果只存在speaker_id为0的句子，则返回其文本 ，否则返回空字符串
        # sentences = result.get("sentences", [])

        # for sentence in sentences:
        #     logger.info(
        #         f"speaker_id={sentence.get('speaker_id')}:start={sentence['start']:.2f}, end={sentence['end']:.2f}, text={sentence['text']}"
        #     )

        # spk_0_sentences = [s for s in sentences if s.get("speaker_id") == 0]
        # if len(spk_0_sentences) == len(sentences):
        #     spk_0_text = " ".join(s["text"] for s in spk_0_sentences)
        #     # logger.info(f"Speaker 0 Text: {spk_0_text.strip()}")
        #     return spk_0_text.strip()

        # return ""

        # 读取 "text" 字段，如果不存在则返回空字符串
        text = result.get("text", "").strip()
        return text

    @staticmethod
    def _read_wave(wave_filename: str) -> np.ndarray:
        with wave.open(wave_filename) as f:
            assert f.getframerate() == 16000, f.getframerate()
            assert f.getnchannels() == 1, f.getnchannels()
            assert f.getsampwidth() == 2, f.getsampwidth()

            num_samples = f.getnframes()
            samples = f.readframes(num_samples)
            samples_int16 = np.frombuffer(samples, dtype=np.int16)
            return samples_int16.astype(np.float32) / 32768.0

    def _start_ws_runtime(self):
        if self._ws_thread is not None and self._ws_thread.is_alive():
            return

        self._ws_started.clear()
        self._ws_thread = threading.Thread(
            target=self._ws_loop_worker,
            daemon=True,
            name="asr-ws-loop",
        )
        self._ws_thread.start()

        if not self._ws_started.wait(timeout=5):
            raise RuntimeError("WebSocket 事件循环线程启动超时")

    def _ws_loop_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ws_loop = loop
        self._ws_started.set()
        logger.info("ASR WebSocket 事件循环线程已启动")
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self._close_ws_async())
            except Exception as e:
                logger.warning(f"ASR WebSocket 线程退出清理失败: {e}")
            finally:
                loop.close()

    def _run_ws_coro(self, coro, timeout: Optional[float]):
        if self._ws_loop is None:
            raise RuntimeError("ASR WebSocket 事件循环未初始化")

        future = asyncio.run_coroutine_threadsafe(coro, self._ws_loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            raise

    async def _ensure_ws_connected(self):
        if self._ws is not None:
            # 连接对象可能已被服务端关闭；仅在仍可用时复用。
            if getattr(self._ws, "close_code", None) is None:
                return
            self._ws = None

        url = f"ws://{self.host}:{self.port}{self.ws_path}"
        self._ws = await websockets.connect(
            url,
            max_size=None,
            ping_interval=self.ws_ping_interval,
            ping_timeout=self.ws_ping_timeout,
        )
        logger.info(f"ASR WebSocket 已连接: {url}")

    async def _close_ws_async(self):
        if self._ws is None:
            return

        try:
            await self._ws.close()
            logger.info("ASR WebSocket 已关闭")
        except Exception as e:
            logger.warning(f"关闭 ASR WebSocket 失败: {e}")
        finally:
            self._ws = None

    async def _receive_results(self):
        assert self._ws is not None
        last_message = ""

        while True:
            try:
                message = await self._ws.recv()
            except ConnectionClosed as e:
                # 某些 ASR 服务端不会额外发送 Done 文本，而是直接以 1000 关闭。
                if e.code == 1000:
                    logger.info("ASR WS 服务端正常关闭，按会话结束处理")
                    self._ws = None
                    break
                self._ws = None
                raise

            if not isinstance(message, str):
                continue

            if message in ("Done!", "Done"):
                break

            last_message = message
            try:
                # logger.info(f"ASR WS 中间结果: {json.loads(message)}")
                pass
            except json.JSONDecodeError:
                logger.info(f"ASR WS 文本消息: {message}")

        return last_message

    async def _recognize_ws_async(self, wav_path: str) -> str:
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Wav file not found: {wav_path}")

        data = self._read_wave(wav_path)

        for attempt in range(2):
            await self._ensure_ws_connected()
            assert self._ws is not None

            try:
                start = 0
                while start < data.shape[0]:
                    end = min(start + self.samples_per_message, data.shape[0])
                    chunk = data.data[start:end].tobytes()
                    await self._ws.send(chunk)

                    # Simulate streaming. You can remove the sleep if you want
                    # if self.seconds_per_message > 0:
                    #     await asyncio.sleep(self.seconds_per_message)

                    start += self.samples_per_message

                await self._ws.send("Done")
            except ConnectionClosed as e:
                logger.warning(f"ASR WebSocket 会话中断，准备重连: {e}")
                self._ws = None
                if attempt == 1:
                    raise
                continue

            try:
                last_message = await self._receive_results()
            except ConnectionClosed as e:
                logger.warning(f"ASR WebSocket 接收阶段异常断开，准备重连: {e}")
                self._ws = None
                if attempt == 1:
                    raise
                continue

            if not last_message:
                return ""

            try:
                payload = json.loads(last_message)
                return str(payload.get("text", "")).strip()
            except json.JSONDecodeError:
                return last_message.strip()

        return ""

    def _recognize_ws(self, wav_path: str) -> str:
        try:
            return self._run_ws_coro(
                self._recognize_ws_async(wav_path), timeout=self.timeout
            )
        except TimeoutError:
            logger.error("ASR WebSocket 连接超时")
            self._run_ws_coro(self._close_ws_async(), timeout=self.timeout)
            return ""
        except Exception as e:
            logger.error(f"ASR WebSocket 识别异常: {e}")
            self._run_ws_coro(self._close_ws_async(), timeout=self.timeout)
            return ""

    def _push_recognized_text(self, text: str):
        text = text.strip()
        if not text:
            return

        if self._asr_text_queue.full():
            try:
                self._asr_text_queue.get_nowait()
            except queue.Empty:
                pass

        self._asr_text_queue.put_nowait(text)

    async def _mic_inputstream_generator(self):
        if sd is None:
            raise RuntimeError("sounddevice 未安装，无法启用麦克风流式识别")

        q_in: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def callback(indata, frame_count, time_info, status):
            del frame_count, time_info
            loop.call_soon_threadsafe(q_in.put_nowait, (indata.copy(), status))

        stream = sd.InputStream(
            callback=callback,
            channels=self.mic_channels,
            dtype="float32",
            samplerate=self.mic_samplerate,
            blocksize=int(self.mic_block_seconds * self.mic_samplerate),
        )

        with stream:
            while not self._mic_stop_event.is_set():
                indata, status = await q_in.get()
                yield indata, status

    async def _receive_mic_results(self, websocket):
        last_message = ""
        last_segment = None

        try:
            async for message in websocket:
                if not isinstance(message, str):
                    continue

                if message in ("Done!", "Done"):
                    if last_message:
                        self._push_recognized_text(last_message)
                    return

                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue

                text = str(payload.get("text", "")).strip()
                segment = payload.get("segment")

                # segment 变化说明上一段识别结束，入队上一段文本。
                if (
                    segment is not None
                    and last_segment is not None
                    and segment != last_segment
                    and last_message
                ):
                    self._push_recognized_text(last_message)

                if text:
                    last_message = text

                if segment is not None:
                    last_segment = segment
        except ConnectionClosed as e:
            if e.code != 1000:
                logger.warning(f"ASR 麦克风接收中断: {e}")
        finally:
            if last_message:
                self._push_recognized_text(last_message)

    async def _mic_stream_loop(self):
        backoff = 1.0

        while not self._mic_stop_event.is_set():
            url = f"ws://{self.host}:{self.port}{self.ws_path}"
            try:
                async with websockets.connect(
                    url,
                    max_size=None,
                    ping_interval=self.ws_ping_interval,
                    ping_timeout=self.ws_ping_timeout,
                ) as websocket:
                    logger.info(f"ASR 麦克风 WebSocket 已连接: {url}")
                    self._mic_started.set()
                    backoff = 1.0

                    receive_task = asyncio.create_task(
                        self._receive_mic_results(websocket)
                    )

                    async for indata, status in self._mic_inputstream_generator():
                        if self._mic_stop_event.is_set():
                            break
                        if status:
                            logger.debug(f"ASR 麦克风状态: {status}")

                        indata = np.ascontiguousarray(indata.reshape(-1))
                        await websocket.send(indata.tobytes())

                    await websocket.send("Done")
                    await receive_task
            except Exception as e:
                if self._mic_stop_event.is_set():
                    break
                logger.warning(f"ASR 麦克风流式识别异常，将重连: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 5.0)

    def _mic_loop_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._mic_loop = loop
        self._mic_started.set()

        try:
            loop.run_until_complete(self._mic_stream_loop())
        finally:
            loop.close()
            self._mic_loop = None

    def start_mic_stream(self):
        if not self.use_websocket:
            return

        if sd is None:
            logger.warning("sounddevice 未安装，跳过麦克风录制线程")
            return

        if self._mic_thread is not None and self._mic_thread.is_alive():
            return

        self._mic_stop_event.clear()
        self._mic_started.clear()
        self._mic_thread = threading.Thread(
            target=self._mic_loop_worker,
            daemon=True,
            name="asr-mic-loop",
        )
        self._mic_thread.start()

    def stop_mic_stream(self):
        self._mic_stop_event.set()

        if self._mic_loop is not None:
            self._mic_loop.call_soon_threadsafe(lambda: None)

        if self._mic_thread is not None:
            self._mic_thread.join(timeout=3)
            self._mic_thread = None

    def pop_recognized_text(self, timeout: Optional[float] = None) -> Optional[str]:
        try:
            if timeout is None:
                return self._asr_text_queue.get_nowait()
            return self._asr_text_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_recognized_queue_size(self) -> int:
        return self._asr_text_queue.qsize()

    def close(self):
        self.stop_mic_stream()

        if self._ws_loop is None:
            return

        try:
            self._run_ws_coro(self._close_ws_async(), timeout=3)
        except Exception as e:
            logger.warning(f"ASR WebSocket 清理失败: {e}")
        finally:
            if self._ws_loop is not None:
                self._ws_loop.call_soon_threadsafe(self._ws_loop.stop)
            if self._ws_thread is not None:
                self._ws_thread.join(timeout=3)
            self._ws_loop = None
            self._ws_thread = None


# ===============================
# 单独运行时的测试
# ===============================
if __name__ == "__main__":

    ws_client = ASRClient(
        host="192.168.50.220",
        port=2002,
        timeout_sec=30,
        use_websocket=False,
        ws_path="/",
    )

    import time

    time.sleep(1)  # 等待 WebSocket 连接稳定
    time1 = time.time()
    ws_text = ws_client.recognize("./wavs/example.wav")
    logger.info(f"ASR WS Result: {ws_text}")
    logger.info(f"ASR WS Recognition Time: {time.time() - time1:.2f} seconds")

    time1 = time.time()
    ws_text = ws_client.recognize("./wavs/example.wav", use_websocket=True)
    logger.info(f"ASR WS Result: {ws_text}")
    logger.info(f"ASR WS Recognition Time: {time.time() - time1:.2f} seconds")

    time.sleep(5)  # 等待日志输出完成

    ws_client.close()
