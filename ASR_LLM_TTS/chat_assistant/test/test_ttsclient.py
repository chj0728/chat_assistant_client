from typing import Any, cast

import numpy as np
from tts.ttsclient import TTSClient


class DummyStream:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class DummyThread:
    def __init__(self):
        self.join_timeout = None

    def join(self, timeout=None):
        self.join_timeout = timeout

    def is_alive(self):
        return False


class DummySound:
    def __init__(self, alive=True):
        self.alive = alive
        self.stop_called = False

    def is_alive(self):
        return self.alive

    def stop(self):
        self.stop_called = True
        self.alive = False


class DummyResponse:
    def __init__(
        self,
        *,
        content_type="audio/wav",
        content=b"audio-bytes",
        text="",
        raise_error=None,
    ):
        self.headers = {"Content-Type": content_type}
        self.content = content
        self.text = text
        self._raise_error = raise_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self._raise_error is not None:
            raise self._raise_error


def build_client(monkeypatch):
    stream = DummyStream()
    worker_thread = DummyThread()

    monkeypatch.setattr(
        TTSClient,
        "_TTSClient__create_output_stream",
        lambda self: stream,
    )
    monkeypatch.setattr(
        TTSClient,
        "_TTSClient__start_tts_worker",
        lambda self: worker_thread,
    )
    monkeypatch.setattr(
        TTSClient,
        "_TTSClient__initialize_websocket_if_needed",
        lambda self: None,
    )
    monkeypatch.setattr("tts.ttsclient.time.sleep", lambda _: None)

    client = TTSClient(host="127.0.0.1", port=50000)
    return client, stream, worker_thread


def test_speak_enqueues_normalized_text_and_interrupts(monkeypatch):
    """测试 speak 方法是否正确规范化文本、入队并调用 interrupt"""
    client, _, _ = build_client(monkeypatch)
    interrupt_calls = []

    monkeypatch.setattr(client, "interrupt", lambda: interrupt_calls.append(True))

    client.speak("  你好  ")

    assert client.text_queue.get_nowait() == "你好"
    assert interrupt_calls == [True]


def test_speak_ignores_blank_text(monkeypatch):
    """测试 speak 方法是否正确忽略仅包含空白字符的文本"""
    client, _, _ = build_client(monkeypatch)
    interrupt_calls = []

    monkeypatch.setattr(client, "interrupt", lambda: interrupt_calls.append(True))

    client.speak("   ")

    assert client.text_queue.empty()
    assert interrupt_calls == []


def test_interrupt_clears_queues_and_resets_playback_state(monkeypatch):
    """测试 interrupt 方法是否正确清空文本和音频队列、重置播放状态并停止正在播放的音频"""
    client, _, _ = build_client(monkeypatch)
    sound = DummySound(alive=True)
    client.text_queue.put("hello")
    client.audio_queue.put(np.array([0.1, 0.2], dtype=np.float32).tobytes())
    client._playback_buffer = np.ones((2, client.channels), dtype=np.float32)
    client._audio_active_started_ts = 1.0
    client._last_audio_chunk_ts = 2.0
    client.is_sounding = True
    client.sound = cast(Any, sound)

    client.interrupt()

    assert client.text_queue.empty()
    assert client.audio_queue.empty()
    assert client._playback_buffer.size == 0
    assert client._audio_active_started_ts == 0.0
    assert client._last_audio_chunk_ts == 0.0
    assert client.is_sounding is False
    assert sound.stop_called is True
    assert client._interrupt_event.is_set() is False


def test_generate_wav_writes_audio_file(monkeypatch, tmp_path):
    """测试 generate_wav 方法是否正确写入音频文件"""
    client, _, _ = build_client(monkeypatch)
    target_file = tmp_path / "output.wav"

    monkeypatch.setattr(
        client,
        "_TTSClient__request_stream",
        lambda text, data_type: DummyResponse(content=b"wav-bytes"),
    )

    result = client.generate_wav("你好", str(target_file))

    assert result is True
    assert target_file.read_bytes() == b"wav-bytes"


def test_generate_wav_rejects_non_audio_response(monkeypatch, tmp_path):
    """测试 generate_wav 方法是否正确拒绝非音频响应并且不写入文件"""
    client, _, _ = build_client(monkeypatch)
    target_file = tmp_path / "output.wav"

    monkeypatch.setattr(
        client,
        "_TTSClient__request_stream",
        lambda text, data_type: DummyResponse(
            content_type="application/json",
            text="server error",
        ),
    )

    result = client.generate_wav("你好", str(target_file))

    assert result is False
    assert target_file.exists() is False


def test_is_active_reflects_playback_and_local_audio(monkeypatch):
    """测试 is_active 方法是否正确反映播放状态和本地音频状态"""
    client, _, _ = build_client(monkeypatch)
    sound = DummySound(alive=True)

    assert client.is_active() is False

    client.is_sounding = True
    assert client.is_active() is True

    client.is_sounding = False
    client.sound = cast(Any, sound)
    assert client.is_active() is True


def test_stop_releases_resources(monkeypatch):
    """测试 stop 方法是否正确释放资源、停止流和线程并调用 interrupt 和关闭 WebSocket"""
    client, stream, worker_thread = build_client(monkeypatch)
    interrupt_calls = []
    close_ws_calls = []

    monkeypatch.setattr(client, "interrupt", lambda: interrupt_calls.append(True))
    monkeypatch.setattr(
        client,
        "_TTSClient__close_ws_runtime",
        lambda: close_ws_calls.append(True),
    )

    client.stop()

    assert client._stop_event.is_set() is True
    assert interrupt_calls == [True]
    assert close_ws_calls == [True]
    assert stream.stopped is True
    assert stream.closed is True
    assert worker_thread.join_timeout == 3
