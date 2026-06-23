import queue
import threading

from ASR_LLM_TTS.chat_assistant.tts.tts_client import TTSClientBase
from ASR_LLM_TTS.chat_assistant.tts.backend_context import TTSBackendContext
from ASR_LLM_TTS.chat_assistant.tts.runtimes.fallback import FallbackTTSRuntime


class FakeRuntime:
    def __init__(
        self,
        *,
        fail_start=False,
        fail_tts=False,
        wav_result=True,
        events=None,
        name="runtime",
    ) -> None:
        self.fail_start = fail_start
        self.fail_tts = fail_tts
        self.wav_result = wav_result
        self.events = events
        self.name = name
        self.started = False
        self.stopped = False
        self.tts_texts = []
        self.wav_requests = []

    def start(self) -> None:
        if self.events is not None:
            self.events.append(f"{self.name}-start")
        if self.fail_start:
            raise RuntimeError("start failed")
        self.started = True

    def stop(self) -> None:
        if self.events is not None:
            self.events.append(f"{self.name}-stop")
        self.stopped = True

    def tts_infer(self, text: str) -> None:
        self.tts_texts.append(text)
        if self.fail_tts:
            raise TimeoutError("tts timeout")

    def generate_wav(self, text: str, filename: str) -> bool:
        self.wav_requests.append((text, filename))
        return self.wav_result

    def change_voice(self, voice: str) -> None:
        self.voice = voice


def build_context() -> TTSBackendContext:
    return TTSBackendContext(
        text_queue=queue.Queue(),
        audio_queue=queue.Queue(),
        stop_event=threading.Event(),
        interrupt_event=threading.Event(),
    )


class FakeOutputStream:
    def __init__(self, *, server_type, sample_rate, channels, dtype) -> None:
        self.server_type = server_type
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def interrupt(self) -> None:
        pass

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        return False

    def is_sounding_flag(self) -> bool:
        return False


class FakeBackend:
    def __init__(self, output_stream) -> None:
        self.output_stream = output_stream

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def generate_wav(self, text: str, filename: str) -> bool:
        return False

    def interrupt(self) -> None:
        pass

    def is_active(self) -> bool:
        return False

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        return False


class SwitchableClient(TTSClientBase):
    def create_output_stream(self, server_type=None):
        active_server_type = server_type or self.tts_server_type
        return FakeOutputStream(
            server_type=active_server_type,
            sample_rate=self.get_playback_config_value(
                active_server_type, "sample_rate", 16000
            ),
            channels=self.get_playback_config_value(active_server_type, "channels", 1),
            dtype=self.get_playback_config_value(active_server_type, "dtype", "int16"),
        )

    def create_tts_runtime(self):
        return FakeRuntime()

    def create_tts_backend(self):
        return FakeBackend(self.output_stream)

    def start(self) -> None:
        pass


def test_fallback_runtime_switches_when_primary_start_fails() -> None:
    primary = FakeRuntime(fail_start=True)
    fallback = FakeRuntime()
    runtime = FallbackTTSRuntime(
        build_context(),
        primary_factory=lambda: primary,
        fallback_factory=lambda: fallback,
    )

    runtime.start()

    assert primary.stopped is True
    assert fallback.started is True


def test_fallback_runtime_retries_tts_text_on_fallback() -> None:
    events = []
    primary = FakeRuntime(fail_tts=True)
    fallback = FakeRuntime(events=events, name="fallback")
    runtime = FallbackTTSRuntime(
        build_context(),
        primary_factory=lambda: primary,
        fallback_factory=lambda: fallback,
        fallback_switch_callback=lambda: events.append("switch-output"),
    )

    runtime.tts_infer("你好")

    assert events == ["switch-output", "fallback-start"]
    assert primary.tts_texts == ["你好"]
    assert primary.stopped is True
    assert fallback.started is True
    assert fallback.tts_texts == ["你好"]


def test_fallback_runtime_uses_fallback_when_primary_wav_returns_false() -> None:
    primary = FakeRuntime(wav_result=False)
    fallback = FakeRuntime(wav_result=True)
    runtime = FallbackTTSRuntime(
        build_context(),
        primary_factory=lambda: primary,
        fallback_factory=lambda: fallback,
    )

    result = runtime.generate_wav("你好", "out.wav")

    assert result is True
    assert primary.wav_requests == [("你好", "out.wav")]
    assert fallback.wav_requests == [("你好", "out.wav")]


def test_client_switches_output_stream_to_local_playback_format() -> None:
    client = SwitchableClient(
        tts_server_type="tts_remote",
        tts_remote={
            "sample_rate": 24000,
            "channels": 1,
            "dtype": "int16",
        },
        tts_local={
            "sample_rate": 16000,
            "channels": 1,
            "dtype": "float32",
        },
    )
    old_output_stream = client.output_stream
    client.output_stream_started = True

    client.switch_output_stream("tts_local")

    assert old_output_stream.stopped is True
    assert old_output_stream.closed is True
    assert client.output_stream.server_type == "tts_local"
    assert client.output_stream.sample_rate == 16000
    assert client.output_stream.dtype == "float32"
    assert client.output_stream.started is True
    assert client.tts_backend.output_stream is client.output_stream
