import queue
import threading
from typing import Any

from tts.backend_context import TTSBackendContext
from tts.tts_client import TTSClient


class DummySound:
    """模拟 playsound3 返回的本地音频播放对象。"""

    def __init__(self, alive: bool = True) -> None:
        self.alive = alive
        self.stop_calls = 0

    def is_alive(self) -> bool:
        return self.alive

    def stop(self) -> None:
        self.stop_calls += 1
        self.alive = False


class StubOutputStream:
    """记录输出流生命周期调用。"""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.close_calls = 0
        self.interrupt_calls = 0
        self.is_sounding = False
        self.wait_timeouts: list[float] = []

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def interrupt(self) -> None:
        self.interrupt_calls += 1

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        self.wait_timeouts.append(timeout_sec)
        return self.is_sounding

    def is_sounding_flag(self) -> bool:
        return self.is_sounding


class StubRuntime:
    """记录 TTS runtime 调用，避免测试中访问真实服务。"""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.generate_wav_calls: list[tuple[str, str]] = []

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def tts_infer(self, text: str) -> None:
        pass

    def generate_wav(self, text: str, filename: str) -> bool:
        self.generate_wav_calls.append((text, filename))
        return True


class StubBackend:
    """记录 TTS backend 入口调用，便于断言客户端转发行为。"""

    def __init__(self, output_stream: StubOutputStream, runtime: StubRuntime) -> None:
        self.output_stream = output_stream
        self.runtime = runtime
        self.start_calls = 0
        self.stop_calls = 0
        self.interrupt_calls = 0
        self.generate_wav_calls: list[tuple[str, str]] = []
        self.wait_timeouts: list[float] = []
        self.active = False

    def on_start(self) -> None:
        self.start_calls += 1

    def on_stop(self) -> None:
        self.stop_calls += 1

    def generate_wav(self, text: str, filename: str) -> bool:
        self.generate_wav_calls.append((text, filename))
        return self.runtime.generate_wav(text, filename)

    def interrupt(self) -> None:
        self.interrupt_calls += 1

    def is_active(self) -> bool:
        return self.active

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        self.wait_timeouts.append(timeout_sec)
        return self.active


class StubTTSClient(TTSClient):
    """用 stub 组件替代真实 TTS 输出流、runtime 和 backend。"""

    def __init__(self, **kwargs: Any) -> None:
        self.created_output_streams: list[StubOutputStream] = []
        self.created_runtimes: list[StubRuntime] = []
        self.created_backends: list[StubBackend] = []
        self.created_output_stream_server_types: list[str | None] = []
        super().__init__(**kwargs)

    def create_output_stream(
        self, server_type: str | None = None
    ) -> StubOutputStream:
        self.created_output_stream_server_types.append(server_type)
        stream = StubOutputStream()
        self.created_output_streams.append(stream)
        return stream

    def create_tts_runtime(self) -> StubRuntime:
        runtime = StubRuntime()
        self.created_runtimes.append(runtime)
        return runtime

    def create_tts_backend(self) -> StubBackend:
        backend = StubBackend(self.output_stream, self.tts_runtime)
        self.created_backends.append(backend)
        return backend


def test_tts_client_initializes_queues_events_components_and_starts_backend() -> None:
    """测试 TTSClient 初始化时创建运行状态并启动后端。"""
    client = StubTTSClient(tts_server_type="sherpa_onnx_tts", timeout_sec=7.5)

    assert client.tts_server_type == "sherpa_onnx_tts"
    assert client.timeout_sec == 7.5
    assert isinstance(client.text_queue, queue.Queue)
    assert isinstance(client.audio_queue, queue.Queue)
    assert isinstance(client.stop_event, threading.Event)
    assert isinstance(client.interrupt_event, threading.Event)
    assert client.output_stream_started is True

    assert len(client.created_output_streams) == 1
    assert len(client.created_runtimes) == 1
    assert len(client.created_backends) == 1
    assert client.tts_backend.start_calls == 1


def test_create_backend_context_shares_client_state() -> None:
    """测试后端上下文复用客户端队列和事件。"""
    client = StubTTSClient(timeout_sec=8.0)

    context = client.create_backend_context()

    assert isinstance(context, TTSBackendContext)
    assert context.timeout == 8.0
    assert context.text_queue is client.text_queue
    assert context.audio_queue is client.audio_queue
    assert context.stop_event is client.stop_event
    assert context.interrupt_event is client.interrupt_event


def test_get_playback_config_value_prefers_server_specific_value() -> None:
    """测试播放配置优先读取当前 TTS 类型下的配置。"""
    client = StubTTSClient(
        tts_server_type="zipvoice_tts",
        sample_rate=16000,
        zipvoice_tts={"sample_rate": 24000, "buffer_size": 1024},
    )

    assert client.get_playback_config_value("zipvoice_tts", "sample_rate", 8000) == 24000
    assert client.get_playback_config_value("zipvoice_tts", "buffer_size", 4096) == 1024
    assert client.get_playback_config_value("zipvoice_tts", "channels", 1) == 1


def test_speak_enqueues_normalized_text_and_interrupts() -> None:
    """测试 speak 会规范化文本、按需中断并入队。"""
    client = StubTTSClient()

    client.speak("  你好  ")

    assert client.text_queue.get_nowait() == "你好"
    assert client.tts_backend.interrupt_calls == 1


def test_speak_can_append_without_interrupting() -> None:
    """测试 speak(interrupt=False) 不会中断当前播放。"""
    client = StubTTSClient()

    client.speak("继续说", interrupt=False)

    assert client.text_queue.get_nowait() == "继续说"
    assert client.tts_backend.interrupt_calls == 0


def test_speak_ignores_blank_text() -> None:
    """测试 speak 会忽略空白文本。"""
    client = StubTTSClient()

    client.speak("   ")

    assert client.text_queue.empty()
    assert client.tts_backend.interrupt_calls == 0


def test_interrupt_clears_queues_stops_local_audio_and_interrupts_backend(monkeypatch):
    """测试 interrupt 会清空队列、停止本地音频并通知后端中断。"""
    client = StubTTSClient()
    sound = DummySound(alive=True)
    client.sound = sound
    client.text_queue.put("hello")
    client.audio_queue.put(b"audio")
    monkeypatch.setattr("tts.tts_client.time.sleep", lambda _: None)

    client.interrupt()

    assert client.text_queue.empty()
    assert client.audio_queue.empty()
    assert sound.stop_calls == 1
    assert client.tts_backend.interrupt_calls == 1


def test_is_active_reflects_backend_and_local_audio() -> None:
    """测试 is_active 同时考虑后端播放状态和本地音频状态。"""
    client = StubTTSClient()

    assert client.is_active() is False

    client.tts_backend.active = True
    assert client.is_active() is True

    client.tts_backend.active = False
    client.sound = DummySound(alive=True)
    assert client.is_active() is True


def test_generate_wav_delegates_to_backend(tmp_path) -> None:
    """测试 generate_wav 是否转发到 TTS 后端。"""
    client = StubTTSClient()
    target_file = tmp_path / "output.wav"

    result = client.generate_wav("你好", str(target_file))

    assert result is True
    assert client.tts_backend.generate_wav_calls == [("你好", str(target_file))]
    assert client.tts_runtime.generate_wav_calls == [("你好", str(target_file))]


def test_wait_until_playback_starts_delegates_to_backend() -> None:
    """测试等待起播状态是否转发到 TTS 后端。"""
    client = StubTTSClient()

    assert client.wait_until_playback_starts(timeout_sec=2.5) is False
    assert client.tts_backend.wait_timeouts == [2.5]


def test_stop_delegates_to_backend_and_marks_stream_stopped() -> None:
    """测试 stop 会停止后端并更新输出流启动状态。"""
    client = StubTTSClient()

    client.stop()

    assert client.tts_backend.stop_calls == 1
    assert client.output_stream_started is False


def test_switch_output_stream_replaces_stream_and_updates_backend() -> None:
    """测试切换输出流时会停止旧流、创建新流并同步到后端。"""
    client = StubTTSClient()
    old_stream = client.output_stream

    client.switch_output_stream("sherpa_onnx_tts")

    assert old_stream.stop_calls == 1
    assert old_stream.close_calls == 1
    assert client.output_stream is not old_stream
    assert client.tts_backend.output_stream is client.output_stream
    assert client.output_stream.start_calls == 1
    assert client.created_output_stream_server_types[-1] == "sherpa_onnx_tts"


def test_from_config_passes_config_to_constructor() -> None:
    """测试 from_config 使用配置字典构造客户端。"""
    client = StubTTSClient.from_config(
        {"tts_server_type": "zipvoice_tts", "timeout_sec": 12.0}
    )

    assert client.tts_server_type == "zipvoice_tts"
    assert client.timeout_sec == 12.0


def test_reset_from_config_stops_and_reinitializes_client() -> None:
    """测试 reset_from_config 会停止旧后端并按新配置重建实例。"""
    client = StubTTSClient(tts_server_type="sherpa_onnx_tts", timeout_sec=5.0)
    old_backend = client.tts_backend
    old_text_queue = client.text_queue
    old_audio_queue = client.audio_queue

    client.reset_from_config({"tts_server_type": "zipvoice_tts", "timeout_sec": 15.0})

    assert old_backend.stop_calls == 1
    assert client.tts_server_type == "zipvoice_tts"
    assert client.timeout_sec == 15.0
    assert client.tts_backend is not old_backend
    assert client.text_queue is not old_text_queue
    assert client.audio_queue is not old_audio_queue
    assert client.tts_backend.start_calls == 1
