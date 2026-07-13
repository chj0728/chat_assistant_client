import asyncio
from types import SimpleNamespace

import pytest

from transport import ThreadedWebSocketClient
from transport import threaded_websocket


class FakeConnection:
    """记录公共 WebSocket 客户端对连接的复用及关闭行为。"""

    def __init__(self) -> None:
        """创建一个处于打开状态的伪连接。"""
        self.close_code = None
        self.close_calls = 0

    async def close(self) -> None:
        """模拟关闭 WebSocket 连接。"""
        self.close_calls += 1
        self.close_code = 1000


def test_start_run_and_stop_manage_event_loop_thread(monkeypatch) -> None:
    """公共客户端应支持启动、同步执行协程及幂等停止。"""
    monkeypatch.setattr(threaded_websocket, "websockets", SimpleNamespace())
    client = ThreadedWebSocketClient("ws://localhost/ws", name="test")

    client.start()

    assert client.run(asyncio.sleep(0, result="ok"), timeout=1) == "ok"

    client.stop(timeout=1)
    client.stop(timeout=1)

    assert client._loop is None
    assert client._thread is None


def test_connect_reuses_open_connection_and_stop_closes_it(monkeypatch) -> None:
    """连接仍可用时应复用，并在停止客户端时统一关闭。"""
    connection = FakeConnection()
    connect_calls = []

    async def fake_connect(url, **kwargs):
        """返回测试连接并记录连接参数。"""
        connect_calls.append((url, kwargs))
        return connection

    monkeypatch.setattr(
        threaded_websocket,
        "websockets",
        SimpleNamespace(connect=fake_connect),
    )
    client = ThreadedWebSocketClient(
        "ws://localhost/ws",
        name="test",
        ping_interval=20,
        ping_timeout=10,
    )
    client.start()

    first = client.run(client.connect(), timeout=1)
    second = client.run(client.connect(), timeout=1)
    client.stop(timeout=1)

    assert first is connection
    assert second is connection
    assert len(connect_calls) == 1
    assert connect_calls[0] == (
        "ws://localhost/ws",
        {"max_size": None, "ping_interval": 20, "ping_timeout": 10},
    )
    assert connection.close_calls == 1


def test_run_cancels_timed_out_coroutine(monkeypatch) -> None:
    """同步等待超时后应取消后台协程并抛出统一的 TimeoutError。"""
    cancelled = asyncio.Event()

    async def wait_forever() -> None:
        """等待取消信号，用于验证超时清理。"""
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(threaded_websocket, "websockets", SimpleNamespace())
    client = ThreadedWebSocketClient("ws://localhost/ws", name="test")
    client.start()

    with pytest.raises(TimeoutError):
        client.run(wait_forever(), timeout=0.01)

    client.run(asyncio.wait_for(cancelled.wait(), timeout=1), timeout=1)
    client.stop(timeout=1)
