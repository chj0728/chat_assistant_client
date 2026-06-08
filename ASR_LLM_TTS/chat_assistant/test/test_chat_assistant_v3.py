import importlib

from voice import voice_recognizer as voice_recognizer_module


class DummyClient:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


def load_chat_assistant_module(monkeypatch):
    monkeypatch.setattr(
        voice_recognizer_module.VoiceRecognizer,
        "__init__",
        lambda self, threshold=0.175, max_prints_per_id=2: None,
    )

    module = importlib.import_module("app.chat_assistant_v3")
    return importlib.reload(module)


def test_reset_reinitializes_state_and_restarts_recording(monkeypatch):
    """测试 reset 是否释放旧客户端、清空状态并按需恢复录音。"""
    chat_assistant_module = load_chat_assistant_module(monkeypatch)

    configs = {
        "Audio": {},
        "VAD": {},
        "KWS": {},
    }
    monkeypatch.setattr(chat_assistant_module, "load_config", lambda _: configs)

    asr_clients = [DummyClient(), DummyClient()]
    llm_clients = [DummyClient(), DummyClient()]
    tts_clients = [DummyClient(), DummyClient()]

    monkeypatch.setattr(
        chat_assistant_module.ChatAssistant,
        "_build_asr_client",
        lambda self: asr_clients.pop(0),
    )
    monkeypatch.setattr(
        chat_assistant_module.ChatAssistant,
        "_build_llm_client",
        lambda self: llm_clients.pop(0),
    )
    monkeypatch.setattr(
        chat_assistant_module.ChatAssistant,
        "_build_tts_client",
        lambda self: tts_clients.pop(0),
    )

    assistant = chat_assistant_module.ChatAssistant(config_path="config.yaml")

    original_asr_client = assistant.asr_client
    original_llm_client = assistant.llm_client
    original_tts_client = assistant.tts_client
    original_asr_queue = assistant.asr_text_queue
    original_llm_queue = assistant.llm_text_queue
    original_response_queue = assistant.response_queue

    assistant.asr_text = "hello"
    assistant.llm_text = "world"
    assistant.current_user_id = "user-1"
    assistant.asr_text_queue.put("hello")
    assistant.llm_text_queue.put("world")
    assistant.response_queue.put({"asr_text": "hello", "llm_text": "world"})
    assistant.response_data.asr_text = "hello"
    assistant.response_data.llm_text = "world"

    stop_calls = []
    start_calls = []

    def fake_stop_recording(self):
        stop_calls.append(True)
        self.recording_active = False

    def fake_start_recording(self):
        start_calls.append(True)
        self.recording_active = True

    monkeypatch.setattr(
        chat_assistant_module.ChatAssistant, "stop_recording", fake_stop_recording
    )
    monkeypatch.setattr(
        chat_assistant_module.ChatAssistant, "start_recording", fake_start_recording
    )

    assistant.recording_active = True
    assistant.reset()

    assert stop_calls == [True]
    assert start_calls == [True]
    assert assistant.recording_active is True

    assert original_asr_client.stop_calls == 1
    assert original_llm_client.stop_calls == 1
    assert original_tts_client.stop_calls == 1

    assert assistant.asr_client is not original_asr_client
    assert assistant.llm_client is not original_llm_client
    assert assistant.tts_client is not original_tts_client

    assert assistant.asr_text == ""
    assert assistant.llm_text == ""
    assert assistant.current_user_id is None
    assert assistant.asr_text_queue is not original_asr_queue
    assert assistant.llm_text_queue is not original_llm_queue
    assert assistant.response_queue is not original_response_queue
    assert assistant.asr_text_queue.empty()
    assert assistant.llm_text_queue.empty()
    assert assistant.response_queue.empty()
    assert assistant.response_data.asr_text == ""
    assert assistant.response_data.llm_text == ""
