import asyncio
import queue
import threading
import wave
from typing import Any, cast

import numpy as np
import pytest
from asr import asrclient as asrclient_module


class DummyLoop:
    def __init__(self):
        self.calls = []
        self.stop_called = False

    def call_soon_threadsafe(self, callback):
        self.calls.append(callback)

    def stop(self):
        self.stop_called = True


class DummyThread:
    def __init__(self):
        self.join_timeout = None

    def join(self, timeout=None):
        self.join_timeout = timeout

    def is_alive(self):
        return True


def build_client_shell() -> asrclient_module.ASRClient:
    client = asrclient_module.ASRClient.__new__(asrclient_module.ASRClient)
    client.host = "127.0.0.1"
    client.port = 6006
    client.timeout = 5.0
    client.use_websocket = False
    client.ws_path = "/ws/api/asr"
    client.ws_ping_interval = None
    client.ws_ping_timeout = None
    client.samples_per_message = 4
    client.seconds_per_message = 0.0
    client.mic_channels = 1
    client.mic_samplerate = 16000
    client.mic_block_seconds = 0.05
    client._asr_text_queue = queue.Queue(maxsize=2)
    client._ws_loop = None
    client._ws = None
    client._ws_thread = None
    client._ws_started = threading.Event()
    client._mic_thread = None
    client._mic_loop = None
    client._mic_started = threading.Event()
    client._mic_stop_event = threading.Event()
    return client


def test_normalize_audio_frames_accepts_byteslike():
    """测试 normalize_audio_frames 是否直接接受 bytes-like 输入。"""
    result = asrclient_module.ASRClient.normalize_audio_frames(b"abc")

    assert result == b"abc"


def test_normalize_audio_frames_joins_iterable_frames():
    """测试 normalize_audio_frames 是否正确拼接帧列表和元组帧。"""
    frames = [b"ab", (bytearray(b"cd"),), memoryview(b"ef")]

    result = asrclient_module.ASRClient.normalize_audio_frames(frames)

    assert result == b"abcdef"


def test_normalize_audio_frames_rejects_invalid_frame_type():
    """测试 normalize_audio_frames 是否拒绝非法帧类型。"""
    with pytest.raises(TypeError):
        asrclient_module.ASRClient.normalize_audio_frames(["bad-frame"])


def test_read_wave_returns_normalized_float32_samples(tmp_path):
    """测试 read_wave 是否正确读取并归一化 16kHz 单声道 PCM wav。"""
    wav_path = tmp_path / "sample.wav"
    samples = np.array([0, 16384, -16384], dtype=np.int16)

    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(samples.tobytes())

    result = asrclient_module.ASRClient.read_wave(str(wav_path))

    assert result.dtype == np.float32
    assert np.allclose(result, np.array([0.0, 0.5, -0.5], dtype=np.float32))


def test_clean_asr_text_removes_unk_and_extra_spaces():
    """测试 clean_asr_text 是否去除 <unk> 和多余空格。"""
    client = build_client_shell()

    result = client.clean_asr_text(" <unk>  你好   世界 <unk> ")

    assert result == "你好世界"


def test_reset_from_config_reinitializes_instance_state():
    """测试 reset_from_config 会关闭旧状态并按新配置重建实例。"""

    class ResettableStubClient(asrclient_module.ASRClient):
        def __init__(self, **kwargs):
            self.close_calls = 0
            self.initialize_snapshots = []
            super().__init__(**kwargs)

        def close(self):
            self.close_calls += 1

        def _initialize_runtime_components(self):
            self.initialize_snapshots.append(
                {
                    "host": self.host,
                    "port": self.port,
                    "timeout": self.timeout,
                    "use_websocket": self.use_websocket,
                    "ws_path": self.ws_path,
                    "samples_per_message": self.samples_per_message,
                    "seconds_per_message": self.seconds_per_message,
                    "queue_size": self._asr_text_queue.maxsize,
                    "mic_channels": self.mic_channels,
                    "mic_samplerate": self.mic_samplerate,
                    "mic_block_seconds": self.mic_block_seconds,
                }
            )

    client = ResettableStubClient(
        host="127.0.0.1",
        port=6006,
        timeout_sec=5.0,
        use_websocket=False,
        asr_queue_size=2,
    )
    original_queue = client._asr_text_queue

    client.reset_from_config(
        {
            "host": "192.168.1.8",
            "port": 7001,
            "timeout_sec": 12.5,
            "use_websocket": True,
            "ws_path": "/custom/ws",
            "ws_ping_interval": 3.0,
            "ws_ping_timeout": 4.0,
            "samples_per_message": 4096,
            "seconds_per_message": 0.2,
            "asr_queue_size": 5,
            "mic_channels": 2,
            "mic_samplerate": 22050,
            "mic_block_seconds": 0.1,
        }
    )

    assert client.close_calls == 1
    assert len(client.initialize_snapshots) == 2
    assert client.host == "192.168.1.8"
    assert client.port == 7001
    assert client.timeout == 12.5
    assert client.use_websocket is True
    assert client.ws_path == "/custom/ws"
    assert client.ws_ping_interval == 3.0
    assert client.ws_ping_timeout == 4.0
    assert client.samples_per_message == 4096
    assert client.seconds_per_message == 0.2
    assert client.mic_channels == 2
    assert client.mic_samplerate == 22050
    assert client.mic_block_seconds == 0.1
    assert client._asr_text_queue.maxsize == 5
    assert client._asr_text_queue is not original_queue

    assert client.initialize_snapshots[-1] == {
        "host": "192.168.1.8",
        "port": 7001,
        "timeout": 12.5,
        "use_websocket": True,
        "ws_path": "/custom/ws",
        "samples_per_message": 4096,
        "seconds_per_message": 0.2,
        "queue_size": 5,
        "mic_channels": 2,
        "mic_samplerate": 22050,
        "mic_block_seconds": 0.1,
    }


def test_recognize_routes_to_http_when_websocket_disabled(monkeypatch):
    """测试 recognize 在未启用 WebSocket 时是否走 HTTP 识别分支。"""
    client = build_client_shell()
    http_calls = []

    monkeypatch.setattr(
        client,
        "_ASRClient__recognize_http",
        lambda wav_path: http_calls.append(wav_path) or " <unk> 结果 ",
    )

    result = client.recognize("demo.wav")

    assert result == "结果"
    assert http_calls == ["demo.wav"]


def test_recognize_routes_to_websocket_when_enabled(monkeypatch):
    """测试 recognize 在启用 WebSocket 时是否走 WebSocket 识别分支。"""
    client = build_client_shell()
    client.use_websocket = True
    ws_calls = []

    monkeypatch.setattr(
        client,
        "_ASRClient__recognize_ws",
        lambda wav_path: ws_calls.append(wav_path) or "  websocket结果  ",
    )

    result = client.recognize("demo.wav", use_websocket=True)

    assert result == "websocket结果"
    assert ws_calls == ["demo.wav"]


def test_recognize_frames_trims_odd_pcm_bytes_before_http(monkeypatch):
    """测试 recognize_frames 是否在 HTTP 路径前裁掉奇数字节。"""
    client = build_client_shell()
    captured = {}

    def fake_recognize_http_pcm16_bytes(pcm16_bytes, sample_rate=16000, channels=1):
        captured["pcm16_bytes"] = pcm16_bytes
        captured["sample_rate"] = sample_rate
        captured["channels"] = channels
        return "  frame_result  "

    monkeypatch.setattr(
        client,
        "_ASRClient__recognize_http_pcm16_bytes",
        fake_recognize_http_pcm16_bytes,
    )

    result = client.recognize_frames(b"abc", sample_rate=8000, channels=2)

    assert result == "frame_result"
    assert captured["pcm16_bytes"] == b"ab"
    assert captured["sample_rate"] == 8000
    assert captured["channels"] == 2


def test_push_recognized_text_drops_oldest_when_queue_full():
    """测试 _push_recognized_text 是否在队列满时丢弃最旧结果。"""
    client = build_client_shell()

    client._push_recognized_text("first")
    client._push_recognized_text("second")
    client._push_recognized_text("third")

    assert client.get_recognized_queue_size() == 2
    assert client.pop_recognized_text() == "second"
    assert client.pop_recognized_text() == "third"


def test_pop_recognized_text_returns_none_when_queue_empty():
    """测试 pop_recognized_text 在队列为空时是否返回 None。"""
    client = build_client_shell()

    assert client.pop_recognized_text() is None


def test_receive_results_returns_last_message_before_done():
    """测试 __receive_results 是否返回 Done 前最后一条文本消息。"""
    client = build_client_shell()

    class DummyWebSocket:
        def __init__(self):
            self.messages = iter(["first", "second", "Done"])

        async def recv(self):
            return next(self.messages)

    client._ws = cast(Any, DummyWebSocket())
    receive_results = cast(Any, getattr(client, "_ASRClient__receive_results"))

    result = asyncio.run(receive_results())

    assert result == "second"


def test_close_stops_mic_and_ws_runtime(monkeypatch):
    """测试 close 是否停止麦克风线程并关闭 WebSocket 运行时。"""
    client = build_client_shell()
    ws_loop = DummyLoop()
    ws_thread = DummyThread()
    stop_mic_calls = []
    run_ws_coro_calls = []

    client._ws_loop = cast(Any, ws_loop)
    client._ws_thread = cast(Any, ws_thread)

    async def fake_close_ws_async():
        return None

    monkeypatch.setattr(client, "stop_mic_stream", lambda: stop_mic_calls.append(True))
    monkeypatch.setattr(
        client,
        "_ASRClient__close_ws_async",
        fake_close_ws_async,
    )

    def fake_run_ws_coro(coro, timeout):
        run_ws_coro_calls.append(timeout)
        return asyncio.run(coro)

    monkeypatch.setattr(client, "_ASRClient__run_ws_coro", fake_run_ws_coro)

    client.close()

    assert stop_mic_calls == [True]
    assert run_ws_coro_calls == [3]
    assert len(ws_loop.calls) == 1
    assert ws_loop.calls[0] == ws_loop.stop
    assert ws_thread.join_timeout == 3
    assert client._ws_loop is None
    assert client._ws_thread is None
