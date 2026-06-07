import asyncio
import json
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Optional

import requests
from logger import logger

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    websockets = None
    ConnectionClosed = Exception

from .backend_base import TTSBackendContext, TTSRuntime

WS_STARTUP_WAIT_SEC = 1.0


class LocalTTSRuntime(TTSRuntime):
    def __init__(self, context: TTSBackendContext) -> None:
        self._context = context
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_started = threading.Event()

    ####### TTSRuntime 接口实现 ######
    def initialize_if_needed(self) -> None:
        if not self._context.use_websocket:
            return

        self._start_ws_runtime()
        time.sleep(WS_STARTUP_WAIT_SEC)
        try:
            self._run_ws_coro(
                self._ensure_ws_connected(), timeout=self._context.timeout
            )
        except TimeoutError:
            logger.error("TTS WebSocket 连接超时")
        except Exception as e:
            logger.error(f"TTS WebSocket 连接失败: {e}")

    def close_runtime(self) -> None:
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

    def run_tts(self, text: str) -> None:
        self._tts_request(text)

    #############################

    def request_stream(self, text: str, data_type: str):
        return requests.post(
            self._build_http_url("/api/tts"),
            data={
                "tts_text": text,
                "data_type": data_type,
                "sid": self._context.speaker_id,
                "speed": self._context.speed,
            },
            timeout=self._context.timeout,
            stream=data_type == "pcm",
        )

    def _build_http_url(self, path: str) -> str:
        return f"http://{self._context.host}:{self._context.port}{path}"

    def _tts_request(self, text):
        if self._context.use_websocket:
            self._tts_request_ws(text)
            return

        self._tts_request_http(text)

    def _tts_request_http(self, text):
        try:
            with self.request_stream(text, data_type="pcm") as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=self._context.chunk_size):
                    if (
                        self._context.stop_event.is_set()
                        or self._context.interrupt_event.is_set()
                    ):
                        return
                    if not chunk:
                        continue
                    self._context.audio_queue.put(chunk)
        except Exception as e:
            logger.error(f"HTTP TTS 请求失败: {e}")

    def _tts_request_ws(self, text):
        try:
            self._start_ws_runtime()
            self._run_ws_coro(self._tts_request_ws_async(text), timeout=10)
        except TimeoutError:
            logger.error("TTS WebSocket 请求超时")
            self._run_ws_coro(self._close_ws_async(), timeout=self._context.timeout)
        except Exception as e:
            logger.error(f"WebSocket TTS 请求失败: {e}")
            self._run_ws_coro(self._close_ws_async(), timeout=self._context.timeout)

    def _start_ws_runtime(self):
        if self._ws_thread is not None and self._ws_thread.is_alive():
            return

        if websockets is None:
            raise RuntimeError("websockets 未安装，无法启用 WebSocket TTS")

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
            raise TimeoutError from None

    async def _ensure_ws_connected(self):
        if self._ws is not None:
            return

        url = f"ws://{self._context.host}:{self._context.port}{self._context.ws_path}"
        self._ws = await websockets.connect(
            url,
            max_size=None,
            ping_interval=self._context.ws_ping_interval,
            ping_timeout=self._context.ws_ping_timeout,
        )
        logger.info(f"TTS WebSocket 已连接: {url}")

    async def _close_ws_async(self):
        if self._ws is None:
            return

        try:
            await self._ws.close()
            logger.info("TTS WebSocket 已关闭")
        except Exception as e:
            logger.warning(f"关闭 TTS WebSocket 失败: {e}")
        finally:
            self._ws = None

    async def _tts_request_ws_async(self, text):
        payload = {
            "tts_text": text,
            "sid": self._context.speaker_id,
            "speed": self._context.speed,
        }

        for attempt in range(2):
            await self._ensure_ws_connected()
            assert self._ws is not None

            try:
                while True:
                    try:
                        await asyncio.wait_for(self._ws.recv(), timeout=0.1)
                    except (asyncio.TimeoutError, ConnectionClosed):
                        break

                await self._ws.send(json.dumps(payload, ensure_ascii=False))

                while True:
                    if (
                        self._context.stop_event.is_set()
                        or self._context.interrupt_event.is_set()
                    ):
                        logger.info("TTS WebSocket 收到停止/打断信号")
                        return

                    message = await self._ws.recv()

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
                self._ws = None
                if attempt == 1:
                    raise
