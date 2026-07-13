"""在线程事件循环中运行的可复用 WebSocket 客户端。"""

import asyncio
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Coroutine, Optional, TypeVar

from logger import logger

try:
    import websockets
except ImportError:  # pragma: no cover - 仅在缺少可选依赖的环境触发
    websockets = None


T = TypeVar("T")


class ThreadedWebSocketClient:
    """为同步调用方管理 WebSocket 连接及后台 asyncio 事件循环。"""

    def __init__(
        self,
        url: str,
        *,
        name: str,
        ping_interval: Optional[float] = None,
        ping_timeout: Optional[float] = None,
        startup_timeout: float = 5.0,
    ) -> None:
        """保存连接参数，但不立即创建线程或网络连接。"""
        self.url = url
        self.name = name
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.startup_timeout = startup_timeout

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connection = None
        self._started = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._connect_lock: Optional[asyncio.Lock] = None

    @property
    def connection(self):
        """返回当前连接；调用方应先在事件循环中调用 ``connect()``。"""
        return self._connection

    def start(self) -> None:
        """启动后台事件循环线程；重复调用不会重复创建线程。"""
        with self._lifecycle_lock:
            thread_is_alive = self._thread is not None and self._thread.is_alive()
            if not thread_is_alive:
                if websockets is None:
                    raise RuntimeError("websockets 未安装，无法启用 WebSocket")

                self._started.clear()
                self._connect_lock = None
                self._thread = threading.Thread(
                    target=self._loop_worker,
                    daemon=True,
                    name=f"{self.name}-ws-loop",
                )
                self._thread.start()

        if not self._started.wait(timeout=self.startup_timeout):
            raise RuntimeError(f"{self.name} WebSocket 事件循环线程启动超时")

    def run(
        self, coroutine: Coroutine[Any, Any, T], timeout: Optional[float]
    ) -> T:
        """在线程事件循环中执行协程，并将结果同步返回给调用方。"""
        loop = self._loop
        if loop is None or not loop.is_running():
            coroutine.close()
            raise RuntimeError(f"{self.name} WebSocket 事件循环未运行")

        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            raise TimeoutError from None

    async def connect(self):
        """建立或复用仍然可用的 WebSocket 连接。"""
        if self._is_connection_open():
            return self._connection

        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()

        async with self._connect_lock:
            if self._is_connection_open():
                return self._connection
            if websockets is None:
                raise RuntimeError("websockets 未安装，无法启用 WebSocket")

            self._connection = await websockets.connect(
                self.url,
                max_size=None,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
            )
            logger.info("%s WebSocket 已连接: %s", self.name, self.url)
            return self._connection

    def invalidate(self, connection=None) -> None:
        """在连接异常断开后清除缓存，避免后续请求继续复用。"""
        if connection is None or connection is self._connection:
            self._connection = None

    async def close_connection(self) -> None:
        """关闭当前 WebSocket 连接。"""
        connection = self._connection
        if connection is None:
            return

        try:
            await connection.close()
            logger.info("%s WebSocket 已关闭", self.name)
        except Exception as exc:
            logger.warning("关闭 %s WebSocket 失败: %s", self.name, exc)
        finally:
            if connection is self._connection:
                self._connection = None

    def stop(self, timeout: float = 3.0) -> None:
        """关闭连接并停止后台事件循环线程；未启动时可安全调用。"""
        loop = self._loop
        thread = self._thread
        if loop is None or thread is None:
            return

        try:
            self.run(self.close_connection(), timeout=timeout)
        except Exception as exc:
            logger.warning("%s WebSocket 连接清理失败: %s", self.name, exc)
        finally:
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=timeout)

        if thread.is_alive():
            logger.warning("%s WebSocket 事件循环线程未在期限内退出", self.name)
            return

        self._loop = None
        self._thread = None
        self._connect_lock = None

    def _is_connection_open(self) -> bool:
        """判断缓存的连接是否仍可复用。"""
        return self._connection is not None and getattr(
            self._connection, "close_code", None
        ) is None

    def _loop_worker(self) -> None:
        """创建并持续运行当前客户端专属的 asyncio 事件循环。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        loop.call_soon(self._started.set)
        logger.info("%s WebSocket 事件循环线程已启动", self.name)
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self.close_connection())
                self._cancel_pending_tasks(loop)
            finally:
                loop.close()

    @staticmethod
    def _cancel_pending_tasks(loop: asyncio.AbstractEventLoop) -> None:
        """取消事件循环退出时仍未完成的任务，避免资源泄漏警告。"""
        pending = asyncio.all_tasks(loop)
        if not pending:
            return

        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
