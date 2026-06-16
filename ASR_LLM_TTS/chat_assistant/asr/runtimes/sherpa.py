import asyncio
import io
import json
import os
import re
import threading
import time
import wave
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Optional

import numpy as np
import requests
import websockets
from logger import logger
from websockets.exceptions import ConnectionClosed

from ..asr_backend_context import ASRBackendContext
from .protocol import ASRRuntimeProtocol


class SherpaASRRuntime(ASRRuntimeProtocol):
    def __init__(self, asr_backend_context: ASRBackendContext, **kwargs) -> None:
        self.asr_backend_context = asr_backend_context

        self.on_init(**kwargs)

    def on_init(self, **kwargs) -> None:
        """将初始化参数。"""
        self.asr_cfg = kwargs.get(kwargs.get("asr_server_type", "asr_local"), {})

        self.host = self.asr_cfg.get("host", "localhost")
        self.port = self.asr_cfg.get("port", 8000)
        self.timeout_sec = self.asr_cfg.get("timeout_sec", 10.0)
        self.timeout = self.timeout_sec

        self.sample_rate = self.asr_cfg.get(
            "sample_rate", self.asr_backend_context.sample_rate
        )
        self.channels = self.asr_cfg.get("channels", self.asr_backend_context.channels)
        self.samples_per_message = self.asr_cfg.get(
            "samples_per_message", self.asr_backend_context.samples_per_message
        )
        self.seconds_per_message = self.asr_cfg.get(
            "seconds_per_message", self.asr_backend_context.seconds_per_message
        )

        self.use_websocket = self.asr_cfg.get("use_websocket", False)
        self.ws_path = self.asr_cfg.get("ws_path", "/ws/api/asr")
        self.ws_ping_interval = self.asr_cfg.get("ws_ping_interval", None)
        self.ws_ping_timeout = self.asr_cfg.get("ws_ping_timeout", None)

        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_started = threading.Event()

    def start(self) -> None:
        ############# 如果使用 WebSocket 模式，提前启动事件循环线程，避免首次请求时的启动延迟 #############
        if self.use_websocket:
            self.__start_ws_runtime()
            # self.start_mic_stream() # 目前不默认启动麦克风流式识别，由上层传输wav文件时调用 recognize() 方法即可
            time.sleep(1.0)  # 确保事件循环线程启动完成
            try:
                self.__run_ws_coro(
                    self.__ensure_ws_connected(), timeout=self.timeout_sec
                )
            except TimeoutError:
                logger.error("ASR WebSocket 连接超时")
            except Exception as e:
                logger.error(f"ASR WebSocket 连接异常: {e}")
        ###################################################################

    def stop(self) -> None:
        if self.use_websocket and self._ws_loop is not None:
            try:
                self.__run_ws_coro(self.__close_ws_async(), timeout=self.timeout_sec)
            except TimeoutError:
                logger.error("ASR WebSocket 关闭超时")
            except Exception as e:
                logger.error(f"ASR WebSocket 关闭异常: {e}")
            finally:
                if self._ws_loop is not None:
                    self._ws_loop.call_soon_threadsafe(self._ws_loop.stop)
                if self._ws_thread is not None:
                    self._ws_thread.join(timeout=3)
                self._ws_loop = None
                self._ws_thread = None

    def asr_infer_wav_path(self, wav_path: str) -> str:
        if self.use_websocket:
            return self.clean_asr_text(self.__recognize_ws(wav_path))
        else:
            return self.clean_asr_text(self.__recognize_http(wav_path))

    def asr_infer_frames(self, frames: bytes) -> str:

        pcm16_bytes = self.normalize_audio_frames(frames)
        if not pcm16_bytes:
            return ""

        if len(pcm16_bytes) % 2 != 0:
            logger.warning("音频字节长度不是 2 的整数倍，已丢弃最后 1 字节")
            pcm16_bytes = pcm16_bytes[:-1]
            if not pcm16_bytes:
                return ""

        return self.asr_infer_pcm16_bytes(pcm16_bytes)

    def asr_infer_pcm16_bytes(self, pcm16_bytes: bytes) -> str:
        if self.use_websocket:
            return self.clean_asr_text(
                self.__recognize_ws_pcm16_bytes(
                    pcm16_bytes,
                    sample_rate=self.sample_rate,
                    channels=self.channels,
                )
            )
        else:
            return self.clean_asr_text(
                self.__recognize_http_pcm16_bytes(
                    pcm16_bytes,
                    sample_rate=self.sample_rate,
                    channels=self.channels,
                )
            )

    ############## 数据处理相关实现 #################
    # @staticmethod
    def normalize_audio_frames(self, audio_frames) -> bytes:
        """将多种帧输入格式归一化为单段 PCM16 bytes。"""
        if audio_frames is None:
            return b""

        if isinstance(audio_frames, (bytes, bytearray, memoryview)):
            return bytes(audio_frames)

        normalized_frames = []
        for frame in audio_frames:
            if isinstance(frame, tuple) and frame:
                frame = frame[0]

            if not isinstance(frame, (bytes, bytearray, memoryview)):
                raise TypeError("audio_frames 中每项必须为 bytes 或 bytes-like 对象")

            normalized_frames.append(bytes(frame))

        return b"".join(normalized_frames)

    @staticmethod
    def read_wave(wave_filename: str) -> np.ndarray:
        """读取 wav 文件并返回归一化的 float32 numpy 数组，要求 16kHz 单声道 16-bit PCM 格式。"""
        with wave.open(wave_filename) as f:
            assert f.getframerate() == 16000, f.getframerate()
            assert f.getnchannels() == 1, f.getnchannels()
            assert f.getsampwidth() == 2, f.getsampwidth()

            num_samples = f.getnframes()
            samples = f.readframes(num_samples)
            samples_int16 = np.frombuffer(samples, dtype=np.int16)
            return samples_int16.astype(np.float32) / 32768.0

    def clean_asr_text(self, text: str) -> str:
        """对 ASR 结果文本进行清理，去除特殊标记和多余空格等。"""
        # 1. 删除 <unk>
        text = re.sub(r"<unk>", "", text)

        # 2. 合并多空格
        text = re.sub(r"\s+", "", text)

        # # 3. 合并类似 "s s v v" → "ssvv"
        # text = re.sub(r"\b([a-zA-Z])\s+(?=[a-zA-Z]\b)", r"\1", text)

        return text.strip()

    ################################################
    ############## 选择(HTTP 或 WebSocket) ###############
    def __recognize_http(self, wav_path: str) -> str:
        """通过 HTTP POST 请求发送 wav 文件进行识别。"""
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

    def __recognize_http_pcm16_bytes(
        self, pcm16_bytes: bytes, sample_rate: int = 16000, channels: int = 1
    ) -> str:
        """将 PCM16 字节流封装为 wav 格式后通过 HTTP POST 请求发送进行识别。"""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16_bytes)

        wav_buffer.seek(0)
        files = {"file": ("audio.wav", wav_buffer, "audio/wav")}

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

        return result.get("text", "").strip()

    def __recognize_ws(self, wav_path: str) -> str:
        """通过 WebSocket 发送 wav 文件进行识别。"""
        try:
            return self.__run_ws_coro(
                self.__recognize_ws_async(wav_path), timeout=self.timeout
            )
        except TimeoutError:
            logger.error("ASR WebSocket 识别超时")
            # self.__run_ws_coro(self.__close_ws_async(), timeout=self.timeout)
            return ""
        except Exception as e:
            logger.error(f"ASR WebSocket 识别异常: {e}")
            # self.__run_ws_coro(self.__close_ws_async(), timeout=self.timeout)
            return ""

    def __recognize_ws_pcm16_bytes(
        self, pcm16_bytes: bytes, sample_rate: int = 16000, channels: int = 1
    ) -> str:
        """通过 WebSocket 发送 PCM16 字节流进行识别。"""
        try:
            return self.__run_ws_coro(
                self.__recognize_ws_pcm16_async(
                    pcm16_bytes, sample_rate=sample_rate, channels=channels
                ),
                timeout=self.timeout,
            )
        except TimeoutError:
            logger.error("ASR WebSocket 识别超时")
            # self.__run_ws_coro(self.__close_ws_async(), timeout=self.timeout)
            return ""
        except Exception as e:
            logger.error(f"ASR WebSocket 识别异常: {e}")
            # self.__run_ws_coro(self.__close_ws_async(), timeout=self.timeout)
            return ""

    async def __recognize_ws_async(self, wav_path: str) -> str:
        """接收 wav 文件路径，读取音频数据后通过 WebSocket 发送进行识别。"""
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Wav file not found: {wav_path}")

        data = self.read_wave(wav_path)

        return await self.__recognize_ws_samples_async(data)

    async def __recognize_ws_pcm16_async(
        self, pcm16_bytes: bytes, sample_rate: int = 16000, channels: int = 1
    ) -> str:
        """接收 PCM16 字节流，转换为 float32 数组后通过 WebSocket 发送进行识别。"""
        if sample_rate != 16000:
            raise AssertionError(f"Unsupported sample_rate: {sample_rate}")
        if channels != 1:
            raise AssertionError(f"Unsupported channels: {channels}")

        samples_int16 = np.frombuffer(pcm16_bytes, dtype=np.int16)
        data = samples_int16.astype(np.float32) / 32768.0
        return await self.__recognize_ws_samples_async(data)

    async def __recognize_ws_samples_async(self, data: np.ndarray) -> str:
        """接收归一化的 float32 音频数据，通过 WebSocket 发送进行识别。"""
        data = np.ascontiguousarray(data, dtype=np.float32)

        for attempt in range(2):
            await self.__ensure_ws_connected()
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
                last_message = await self.__receive_results()
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

    ######################################################

    ######## WebSocket连接 及事件循环相关实现 ########
    def __start_ws_runtime(self):
        """启动 WebSocket 事件循环线程。"""
        if self._ws_thread is not None and self._ws_thread.is_alive():
            return

        self._ws_started.clear()
        self._ws_thread = threading.Thread(
            target=self.__ws_loop_worker,
            daemon=True,
            name="asr-ws-loop",
        )
        self._ws_thread.start()

        if not self._ws_started.wait(timeout=5):
            raise RuntimeError("WebSocket 事件循环线程启动超时")

    def __ws_loop_worker(self):
        """WebSocket 事件循环线程的工作函数。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ws_loop = loop
        self._ws_started.set()
        logger.info("ASR WebSocket 事件循环线程已启动")
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self.__close_ws_async())
            except Exception as e:
                logger.warning(f"ASR WebSocket 线程退出清理失败: {e}")
            finally:
                loop.close()

    def __run_ws_coro(self, coro, timeout: Optional[float]):
        """在 WebSocket 事件循环中运行协程，并等待结果。"""
        if self._ws_loop is None:
            raise RuntimeError("ASR WebSocket 事件循环未初始化")

        future = asyncio.run_coroutine_threadsafe(coro, self._ws_loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            raise

    async def __ensure_ws_connected(self):
        """确保 WebSocket 已连接，如果未连接则建立连接。"""
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

    async def __close_ws_async(self):
        """关闭 WebSocket 连接。"""
        if self._ws is None:
            return

        try:
            await self._ws.close()
            logger.info("ASR WebSocket 已关闭")
        except Exception as e:
            logger.warning(f"关闭 ASR WebSocket 失败: {e}")
        finally:
            self._ws = None

    async def __receive_results(self):
        """从 WebSocket 接收识别结果，直到收到 "Done" 消息或连接关闭。返回最后一条文本消息。"""
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

    ###############################################
