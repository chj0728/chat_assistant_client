import io
import json
import os
import re
import wave
from math import gcd

import numpy as np
import requests
from logger import logger
from transport import ThreadedWebSocketClient

try:
    from websockets.exceptions import ConnectionClosed
except ImportError:  # pragma: no cover - 仅在缺少可选依赖的环境触发

    class ConnectionClosed(Exception):
        """Fallback exception when the optional websockets package is absent."""


from ..asr_backend_context import ASRBackendContext
from .protocol import ASRRuntimeProtocol

ASR_SAMPLE_RATE = 16000
ASR_CHANNELS = 1


class SherpaASRRuntime(ASRRuntimeProtocol):
    """通过 HTTP 或长连接 WebSocket 调用 Sherpa-ONNX ASR 服务。"""

    def __init__(self, asr_backend_context: ASRBackendContext, **kwargs) -> None:
        self.asr_backend_context = asr_backend_context

        self.on_init(**kwargs)

    def on_init(self, **kwargs) -> None:
        """读取当前服务类型对应的连接和音频配置。"""
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

        self._ws_client = ThreadedWebSocketClient(
            f"ws://{self.host}:{self.port}{self.ws_path}",
            name="ASR",
            ping_interval=self.ws_ping_interval,
            ping_timeout=self.ws_ping_timeout,
        )

    def start(self) -> None:
        """启动可选的 WebSocket 事件循环并预连接服务端。"""
        if self.use_websocket:
            self._ws_client.start()
            try:
                self._ws_client.run(self._ws_client.connect(), timeout=self.timeout_sec)
            except TimeoutError:
                logger.error("ASR WebSocket 连接超时")
            except (ConnectionError, OSError, ConnectionClosed) as exc:
                logger.error(f"ASR WebSocket 连接异常: {exc}")
        logger.info("ASR Runtime 已启动")

    def stop(self) -> None:
        """停止 WebSocket 事件循环并释放连接资源。"""
        if self.use_websocket:
            self._ws_client.stop(timeout=self.timeout_sec)
        logger.info("ASR Runtime 已停止")

    def asr_infer_wav_path(self, wav_path: str) -> str:
        """识别 WAV 文件；HTTP 保留文件上传，WebSocket 发送解码后的样本。"""
        if self.use_websocket:
            return self.clean_asr_text(self.__recognize_ws(wav_path))
        return self.clean_asr_text(self.__recognize_http(wav_path))

    def asr_infer_frames(self, frames: bytes) -> str:
        """兼容 bytes 或 bytes 帧序列输入，并按 PCM16 执行识别。"""
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
        """兼容既有 PCM16 调用；新录音主路径应使用 asr_infer_samples。"""
        if self.use_websocket:
            return self.clean_asr_text(
                self.__recognize_ws_pcm16_bytes(
                    pcm16_bytes,
                    sample_rate=self.sample_rate,
                    channels=self.channels,
                )
            )
        return self.clean_asr_text(
            self.__recognize_http_pcm16_bytes(
                pcm16_bytes,
                sample_rate=self.sample_rate,
                channels=self.channels,
            )
        )

    def asr_infer_samples(self, samples: np.ndarray) -> str:
        """直接使用 float32 音频数组执行 WebSocket 或 HTTP 识别。"""
        samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim != 1:
            raise ValueError("ASR samples must be a mono one-dimensional array")
        if samples.size == 0:
            return ""
        samples = np.ascontiguousarray(samples)

        if self.use_websocket:
            if self.sample_rate != ASR_SAMPLE_RATE:
                raise AssertionError(f"Unsupported sample_rate: {self.sample_rate}")
            if self.channels != ASR_CHANNELS:
                raise AssertionError(f"Unsupported channels: {self.channels}")
            return self.clean_asr_text(self.__recognize_ws_samples(samples))

        return self.clean_asr_text(
            self.__recognize_http_samples(
                samples, sample_rate=self.sample_rate, channels=self.channels
            )
        )

    @staticmethod
    def normalize_audio_frames(audio_frames) -> bytes:
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
        """读取 WAV，并转换为 16kHz 单声道归一化 float32 数组。"""
        try:
            import soundfile as sf
            from scipy.signal import resample_poly
        except ImportError as e:
            raise RuntimeError("读取并转换 WAV 需要安装 soundfile 和 scipy") from e

        samples, sample_rate = sf.read(
            wave_filename,
            dtype="float32",
            always_2d=True,
        )
        if samples.shape[0] == 0:
            return np.empty(0, dtype=np.float32)

        mono_samples = samples.mean(axis=1, dtype=np.float32)
        target_sample_rate = ASR_SAMPLE_RATE
        if sample_rate != target_sample_rate:
            logger.info(f"Resampling from {sample_rate} Hz to {target_sample_rate} Hz")
            rate_gcd = gcd(sample_rate, target_sample_rate)
            mono_samples = resample_poly(
                mono_samples,
                target_sample_rate // rate_gcd,
                sample_rate // rate_gcd,
            )

        return np.ascontiguousarray(mono_samples, dtype=np.float32)

    @staticmethod
    def clean_asr_text(text: str) -> str:
        """对 ASR 结果文本进行清理，去除特殊标记和多余空格等。"""
        text = re.sub(r"<unk>", "", text)
        text = re.sub(r"\s+", "", text)
        return text.strip()

    def _http_url(self, path: str) -> str:
        """构造当前 ASR 服务的 HTTP URL。"""
        return f"http://{self.host}:{self.port}{path}"

    @staticmethod
    def _parse_http_response(response) -> str:
        """校验 ASR HTTP 响应并提取文本。"""
        if response.status_code != 200:
            message = f"ASR server error [{response.status_code}]: {response.text}"
            logger.error(message)
            raise RuntimeError(message)

        result = response.json()
        if result.get("code") != 0:
            message = f"ASR failed: {result.get('msg')}"
            logger.error(message)
            raise RuntimeError(message)
        return str(result.get("text", "")).strip()

    def _post_wav(self, filename: str, file_obj) -> str:
        """以 multipart WAV 文件调用兼容 HTTP 接口。"""
        response = requests.post(
            self._http_url("/api/asr"),
            files={"file": (filename, file_obj, "audio/wav")},
            timeout=self.timeout,
        )
        return self._parse_http_response(response)

    def __recognize_http(self, wav_path: str) -> str:
        """上传已有 WAV 文件执行 HTTP 识别。"""
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Wav file not found: {wav_path}")

        with open(wav_path, "rb") as wav_file:
            return self._post_wav(os.path.basename(wav_path), wav_file)

    def __recognize_http_pcm16_bytes(
        self,
        pcm16_bytes: bytes,
        sample_rate: int = ASR_SAMPLE_RATE,
        channels: int = ASR_CHANNELS,
    ) -> str:
        """兼容 PCM16 输入，临时封装为 WAV 后上传。"""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16_bytes)

        wav_buffer.seek(0)
        return self._post_wav("audio.wav", wav_buffer)

    def __recognize_http_samples(
        self,
        samples: np.ndarray,
        sample_rate: int = ASR_SAMPLE_RATE,
        channels: int = ASR_CHANNELS,
    ) -> str:
        """通过 HTTP 直接发送 mono float32 little-endian 音频。"""
        if channels != ASR_CHANNELS:
            raise ValueError(f"Unsupported channels: {channels}")

        payload = np.ascontiguousarray(samples, dtype="<f4").tobytes()
        response = requests.post(
            self._http_url("/api/asr/float32"),
            data=payload,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Sample-Rate": str(sample_rate),
                "X-Channels": str(channels),
            },
            timeout=self.timeout,
        )
        return self._parse_http_response(response)

    def _run_ws_recognition(self, coroutine) -> str:
        """在线程化 WebSocket 事件循环中执行一次识别协程。"""
        try:
            return self._ws_client.run(coroutine, timeout=self.timeout)
        except TimeoutError:
            logger.error("ASR WebSocket 识别超时")
        except (ConnectionClosed, ConnectionError, OSError, RuntimeError) as exc:
            logger.error(f"ASR WebSocket 识别异常: {exc}")
        return ""

    def __recognize_ws(self, wav_path: str) -> str:
        """读取 WAV 并通过 WebSocket 识别。"""
        return self._run_ws_recognition(self.__recognize_ws_async(wav_path))

    def __recognize_ws_pcm16_bytes(
        self,
        pcm16_bytes: bytes,
        sample_rate: int = ASR_SAMPLE_RATE,
        channels: int = ASR_CHANNELS,
    ) -> str:
        """通过 WebSocket 发送 PCM16 字节流进行识别。"""
        return self._run_ws_recognition(
            self.__recognize_ws_pcm16_async(
                pcm16_bytes, sample_rate=sample_rate, channels=channels
            )
        )

    def __recognize_ws_samples(self, samples: np.ndarray) -> str:
        """通过 WebSocket 直接发送 float32 音频数组。"""
        return self._run_ws_recognition(self.__recognize_ws_samples_async(samples))

    async def __recognize_ws_async(self, wav_path: str) -> str:
        """读取 WAV 文件并转交 float32 WebSocket 发送流程。"""
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Wav file not found: {wav_path}")

        data = self.read_wave(wav_path)
        return await self.__recognize_ws_samples_async(data)

    async def __recognize_ws_pcm16_async(
        self,
        pcm16_bytes: bytes,
        sample_rate: int = ASR_SAMPLE_RATE,
        channels: int = ASR_CHANNELS,
    ) -> str:
        """接收 PCM16 字节流，转换为 float32 数组后通过 WebSocket 发送进行识别。"""
        if sample_rate != ASR_SAMPLE_RATE:
            raise AssertionError(f"Unsupported sample_rate: {sample_rate}")
        if channels != ASR_CHANNELS:
            raise AssertionError(f"Unsupported channels: {channels}")

        samples_int16 = np.frombuffer(pcm16_bytes, dtype=np.int16)
        data = samples_int16.astype(np.float32) / 32768.0
        return await self.__recognize_ws_samples_async(data)

    async def __recognize_ws_samples_async(self, data: np.ndarray) -> str:
        """接收归一化的 float32 音频数据，通过 WebSocket 发送进行识别。"""
        data = np.ascontiguousarray(data, dtype=np.float32)

        for attempt in range(2):
            ws = await self._ws_client.connect()
            if ws is None:
                raise ConnectionError("WebSocket 连接失败，未返回连接对象")

            try:
                start = 0
                while start < data.shape[0]:
                    end = min(start + self.samples_per_message, data.shape[0])
                    await ws.send(data[start:end].tobytes())
                    start += self.samples_per_message

                await ws.send("Done")
            except ConnectionClosed as exc:
                logger.warning(f"ASR WebSocket 会话中断，准备重连: {exc}")
                self._ws_client.invalidate(ws)
                if attempt == 1:
                    raise
                continue

            try:
                last_message = await self.__receive_results(ws)
            except ConnectionClosed as exc:
                logger.warning(f"ASR WebSocket 接收阶段异常断开，准备重连: {exc}")
                self._ws_client.invalidate(ws)
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

    async def __receive_results(self, ws):
        """从 WebSocket 接收识别结果，直到收到 "Done" 消息或连接关闭。返回最后一条文本消息。"""
        last_message = ""

        while True:
            try:
                message = await ws.recv()
            except ConnectionClosed as exc:
                # 某些 ASR 服务端不会额外发送 Done 文本，而是直接以 1000 关闭。
                if getattr(exc, "code", None) == 1000:
                    logger.info("ASR WS 服务端正常关闭，按会话结束处理")
                    self._ws_client.invalidate(ws)
                    break
                self._ws_client.invalidate(ws)
                raise

            if not isinstance(message, str):
                continue

            if message in ("Done!", "Done"):
                break

            last_message = message

        return last_message
