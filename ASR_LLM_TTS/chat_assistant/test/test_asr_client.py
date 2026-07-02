import asyncio
import queue
import sys
import threading
import types
from typing import Any

websockets_stub = types.ModuleType("websockets")
websockets_exceptions_stub = types.ModuleType("websockets.exceptions")
websockets_exceptions_stub.ConnectionClosed = RuntimeError
websockets_stub.exceptions = websockets_exceptions_stub
sys.modules.setdefault("websockets", websockets_stub)
sys.modules.setdefault("websockets.exceptions", websockets_exceptions_stub)

sounddevice_stub = types.ModuleType("sounddevice")
sounddevice_stub.InputStream = object
sounddevice_stub.CallbackStop = RuntimeError
sounddevice_stub.default = types.SimpleNamespace(device=[None, None])
sounddevice_stub.query_devices = lambda: []
sounddevice_stub.query_hostapis = lambda hostapi: {"name": str(hostapi)}
sys.modules.setdefault("sounddevice", sounddevice_stub)

webrtcvad_stub = types.ModuleType("webrtcvad")
webrtcvad_stub.Vad = lambda mode=3: types.SimpleNamespace(
    is_speech=lambda frame, sample_rate: False
)
sys.modules.setdefault("webrtcvad", webrtcvad_stub)

from asr import ASRClient
from asr.asr_backend_context import ASRBackendContext


class StubInputStream:
    """记录输入流生命周期调用，避免测试中访问真实麦克风。"""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.close_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class StubRuntime:
    """占位 ASR runtime，测试客户端装配时不加载真实模型。"""

    pass


class StubBackend:
    """记录 ASRBackend 入口调用，便于断言客户端转发行为。"""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.updated_vision_ids: list[str | None] = []
        self.recognize_calls: list[str] = []
        self.recognize_frames_calls: list[Any] = []
        self.async_recognize_frames_calls: list[Any] = []

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def recognize(self, wav_path: str) -> str:
        self.recognize_calls.append(wav_path)
        return f"recognized:{wav_path}"

    def recognize_frames(self, audio_frames: Any) -> str:
        self.recognize_frames_calls.append(audio_frames)
        return "recognized_frames"

    async def async_recognize_frames(self, audio_frames: Any) -> str:
        self.async_recognize_frames_calls.append(audio_frames)
        return "async_recognized_frames"

    def update_vision_id(self, vision_id: str | None) -> None:
        self.updated_vision_ids.append(vision_id)


class StubASRClient(ASRClient):
    """用 stub 组件替代真实 ASR 组件的可测试客户端。"""

    def __init__(self, **kwargs: Any) -> None:
        self.created_input_streams: list[StubInputStream] = []
        self.created_runtimes: list[StubRuntime] = []
        self.created_backends: list[StubBackend] = []
        super().__init__(**kwargs)

    def create_input_stream(self, **kwargs: Any) -> StubInputStream:
        stream = StubInputStream()
        self.created_input_streams.append(stream)
        return stream

    def create_asr_runtime(self, **kwargs: Any) -> StubRuntime:
        runtime = StubRuntime()
        self.created_runtimes.append(runtime)
        return runtime

    def create_asr_backend(self, **kwargs: Any) -> StubBackend:
        backend = StubBackend()
        self.created_backends.append(backend)
        return backend


def test_asr_client_initializes_queues_events_and_starts_backend() -> None:
    """测试 ASRClient 初始化时创建上下文状态并启动后端。"""
    client = StubASRClient(asr_server_type="asr_local")

    assert client.asr_server_type == "asr_local"
    assert isinstance(client.audio_frames_queue, queue.Queue)
    assert client.audio_frames_queue.maxsize == 10
    assert isinstance(client.asr_voice_result_queue, queue.Queue)
    assert client.asr_voice_result_queue.maxsize == 10
    assert isinstance(client.stop_event, threading.Event)
    assert isinstance(client.interrupt_event, threading.Event)
    assert client.vision_id is None

    assert len(client.created_input_streams) == 1
    assert len(client.created_runtimes) == 1
    assert len(client.created_backends) == 1
    assert client.asr_backend.start_calls == 1


def test_create_backend_context_shares_client_state() -> None:
    """测试后端上下文复用客户端队列、事件和视觉 ID。"""
    client = StubASRClient()
    client.vision_id = "camera-1"

    context = client.create_backend_context()

    assert isinstance(context, ASRBackendContext)
    assert context.audio_frames_queue is client.audio_frames_queue
    assert context.asr_voice_result_queue is client.asr_voice_result_queue
    assert context.stop_event is client.stop_event
    assert context.interrupt_event is client.interrupt_event
    assert context.vision_id == "camera-1"


def test_start_and_stop_delegate_to_backend() -> None:
    """测试 start/stop 是否转发到 ASR 后端。"""
    client = StubASRClient()

    client.start()
    client.stop()

    assert client.asr_backend.start_calls == 2
    assert client.asr_backend.stop_calls == 1


def test_recognize_delegates_to_backend() -> None:
    """测试 WAV 文件识别是否转发到 ASR 后端。"""
    client = StubASRClient()

    result = client.recognize("demo.wav")

    assert result == "recognized:demo.wav"
    assert client.asr_backend.recognize_calls == ["demo.wav"]


def test_recognize_frames_delegates_to_backend() -> None:
    """测试音频帧识别是否转发到 ASR 后端。"""
    client = StubASRClient()
    frames = b"\x00\x01"

    result = client.recognize_frames(frames)

    assert result == "recognized_frames"
    assert client.asr_backend.recognize_frames_calls == [frames]


def test_async_recognize_frames_delegates_to_backend() -> None:
    """测试异步音频帧识别是否转发到 ASR 后端。"""
    client = StubASRClient()
    frames = b"\x02\x03"

    result = asyncio.run(client.async_recognize_frames(frames))

    assert result == "async_recognized_frames"
    assert client.asr_backend.async_recognize_frames_calls == [frames]


def test_update_vision_id_delegates_to_backend() -> None:
    """测试视觉 ID 更新是否转发到 ASR 后端。"""
    client = StubASRClient()

    client.update_vision_id("vision-42")
    client.update_vision_id(None)

    assert client.asr_backend.updated_vision_ids == ["vision-42", None]


def test_from_config_passes_config_to_constructor() -> None:
    """测试 from_config 使用配置字典构造客户端。"""
    client = StubASRClient.from_config({"asr_server_type": "custom_asr"})

    assert client.asr_server_type == "custom_asr"


def test_reset_from_config_stops_and_reinitializes_client() -> None:
    """测试 reset_from_config 会停止旧后端并按新配置重建实例。"""
    client = StubASRClient(asr_server_type="old_asr")
    old_backend = client.asr_backend
    old_audio_queue = client.audio_frames_queue

    client.reset_from_config({"asr_server_type": "new_asr"})

    assert old_backend.stop_calls == 1
    assert client.asr_server_type == "new_asr"
    assert client.asr_backend is not old_backend
    assert client.audio_frames_queue is not old_audio_queue
    assert client.asr_backend.start_calls == 1
