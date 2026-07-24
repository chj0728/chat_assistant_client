import asyncio
import json

import requests
from logger import logger
from transport import ThreadedWebSocketClient

from ..backend_context import TTSBackendContext
from .protocol import TTSRuntimeProtocol

try:
    from websockets.exceptions import ConnectionClosed
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    ConnectionClosed = Exception


class SherpaTTSRuntime(TTSRuntimeProtocol):
    def __init__(self, context: TTSBackendContext, **kwargs) -> None:
        self.kwargs = kwargs

        self._context = context

        self.host = self.kwargs.get("host", "0.0.0.0")
        self.port = self.kwargs.get("port", 50000)

        self.chunk_size = self.kwargs.get("chunk_size", 2048)
        self.use_websocket = self.kwargs.get("use_websocket", True)
        self.ws_path = self.kwargs.get("ws_path", "/ws/api/tts")
        self.ws_ping_interval = self.kwargs.get("ws_ping_interval", None)
        self.ws_ping_timeout = self.kwargs.get("ws_ping_timeout", None)
        self._ws_client = ThreadedWebSocketClient(
            f"ws://{self.host}:{self.port}{self.ws_path}",
            name="TTS",
            ping_interval=self.ws_ping_interval,
            ping_timeout=self.ws_ping_timeout,
        )

        self.speaker_id = self.kwargs.get("speaker_id", 1)
        self.speed = self.kwargs.get("speed", 1.0)

        logger.info(
            "SherpaTTSRuntime 初始化完成，host=%s port=%s use_websocket=%s ws_path=%s",
            self.host,
            self.port,
            self.use_websocket,
            self.ws_path,
        )

    def request_stream(self, text: str, data_type: str):
        return requests.post(
            self._build_http_url("/api/tts"),
            data={
                "tts_text": text,
                "data_type": data_type,
                "sid": self.speaker_id,
                "speed": self.speed,
            },
            timeout=self._context.timeout,
            stream=data_type == "pcm",
        )

    def _build_http_url(self, path: str) -> str:
        return f"http://{self.host}:{self.port}{path}"

    def _should_stop_request(self) -> bool:
        return (
            self._context.stop_event.is_set() or self._context.interrupt_event.is_set()
        )

    def _tts_request(self, text):
        if self.use_websocket:
            self._tts_request_ws(text)
            return
        self._tts_request_http(text)

    def _tts_request_http(self, text):
        try:
            with self.request_stream(text, data_type="pcm") as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    if self._should_stop_request():
                        return
                    if not chunk:
                        continue
                    if self._should_stop_request():
                        return
                    self._context.audio_queue.put(chunk)
        except requests.RequestException as e:
            logger.error(f"HTTP TTS 请求失败: {e}")

    def _tts_request_ws(self, text):
        try:
            self._ws_client.start()
            self._ws_client.run(self._tts_request_ws_async(text), timeout=10)
        except TimeoutError:
            logger.error("TTS WebSocket 请求超时")
            self._close_ws_connection()
        except (ConnectionError, ConnectionClosed, OSError, RuntimeError) as e:
            logger.error(f"WebSocket TTS 请求失败: {e}")
            self._close_ws_connection()

    def _close_ws_connection(self):
        try:
            self._ws_client.run(
                self._ws_client.close_connection(), timeout=self._context.timeout
            )
        except (ConnectionError, ConnectionClosed, OSError, RuntimeError) as e:
            logger.warning(f"WebSocket 连接清理失败: {e}")

    async def _tts_request_ws_async(self, text):
        payload = {
            "tts_text": text,
            "sid": self.speaker_id,
            "speed": self.speed,
        }

        for attempt in range(2):
            ws = await self._ws_client.connect()
            if ws is None:
                raise ConnectionError("WebSocket 连接失败，未返回连接对象")

            try:
                while True:
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=0.1)
                    except (asyncio.TimeoutError, ConnectionClosed):
                        break

                await ws.send(json.dumps(payload, ensure_ascii=False))

                while True:
                    if self._should_stop_request():
                        logger.info("TTS WebSocket 收到停止/打断信号")
                        return

                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue

                    if self._should_stop_request():
                        logger.info("TTS WebSocket 收到停止/打断信号")
                        return

                    if isinstance(message, bytes):
                        self._context.audio_queue.put(message)
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
                self._ws_client.invalidate(ws)
                if attempt == 1:
                    raise

    ######################## 实现 TTSRuntimeProtocol 接口方法 ########################
    def start(self) -> None:
        if not self.use_websocket:
            return

        self._ws_client.start()
        try:
            self._ws_client.run(
                self._ws_client.connect(), timeout=self._context.timeout
            )
        except TimeoutError:
            logger.error("TTS WebSocket 连接超时")
        except (ConnectionError, ConnectionClosed, OSError, RuntimeError) as e:
            logger.error(f"TTS WebSocket 连接失败: {e}")

    def stop(self) -> None:
        self._ws_client.stop(timeout=3)

    def interrupt(self) -> None:
        """中断当前正在进行的 TTS 推理。"""
        self._context.interrupt_event.set()
        logger.info("TTS 推理已中断")

    def tts_infer(self, text: str) -> None:
        self._tts_request(text)

    def generate_wav(self, text: str, filename: str) -> bool:
        try:
            with self.request_stream(text, data_type="wav") as resp:
                resp.raise_for_status()

                if "audio" not in resp.headers.get("Content-Type", ""):
                    logger.error("返回不是音频")
                    logger.error(resp.text)
                    return False

                with open(filename, "wb") as f:
                    f.write(resp.content)
            return True
        except (OSError, requests.RequestException) as e:
            logger.error(f"TTS 请求失败: {e}")
            return False

    def change_voice(self, voice: str) -> None:
        logger.warning("当前 TTS 后端不支持动态更改语音设置: %s", voice)

    ##############################################################################
