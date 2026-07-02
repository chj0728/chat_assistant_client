import importlib
import sys
import types
from queue import Queue
from typing import Any


class DummyClient:
    """记录客户端生命周期调用的轻量 stub。"""

    def __init__(self) -> None:
        self.stop_calls = 0
        self.close_calls = 0
        self.updated_vision_ids: list[str | None] = []

    def stop(self) -> None:
        self.stop_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def is_active(self) -> bool:
        return False

    def update_vision_id(self, vision_id: str | None) -> None:
        self.updated_vision_ids.append(vision_id)


class FactoryStub:
    """模拟 ASR/LLM/TTS 类的 from_config 工厂。"""

    created_configs: list[dict[str, Any]] = []

    @classmethod
    def from_config(cls, config: dict[str, Any], **kwargs: Any) -> DummyClient:
        cls.created_configs.append(config)
        return DummyClient()


def install_runtime_stubs(monkeypatch) -> None:
    """为 chat_assistant_v3 的重依赖提供最小测试替身。"""
    asr_stub = types.ModuleType("asr")
    asr_stub.ASRClient = FactoryStub

    llm_stub = types.ModuleType("llm")
    llm_stub.LLMAgent = FactoryStub

    tts_stub = types.ModuleType("tts")
    tts_stub.TTSClient = FactoryStub

    pypinyin_stub = types.ModuleType("pypinyin")
    pypinyin_stub.Style = types.SimpleNamespace(NORMAL="normal")
    pypinyin_stub.pinyin = lambda text, style=None: [[char] for char in text]

    monkeypatch.setitem(sys.modules, "asr", asr_stub)
    monkeypatch.setitem(sys.modules, "llm", llm_stub)
    monkeypatch.setitem(sys.modules, "tts", tts_stub)
    monkeypatch.setitem(sys.modules, "pypinyin", pypinyin_stub)


def load_chat_assistant_module(monkeypatch):
    """用 stub 依赖重新加载 chat_assistant_v3 模块。"""
    install_runtime_stubs(monkeypatch)
    module = importlib.import_module("app.chat_assistant_v3")
    return importlib.reload(module)


def test_reset_reinitializes_state_and_restarts_worker(monkeypatch):
    """测试 reset 是否停止旧组件、清空状态、重建组件并重新启动主线程。"""
    chat_assistant_module = load_chat_assistant_module(monkeypatch)

    configs = {
        "ASR": {"asr_server_type": "stub_asr"},
        "LLM": {"llm_server_type": "stub_llm"},
        "TTS": {"tts_server_type": "stub_tts"},
        "KWS": {"enable": True, "wake_word": "你好小特"},
        "asr_enable": True,
        "llm_enable": True,
        "tts_enable": True,
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

    start_calls = []

    def fake_start(self) -> None:
        start_calls.append(True)
        self.worker_thread_active = True

    monkeypatch.setattr(chat_assistant_module.ChatAssistant, "start", fake_start)

    assistant = chat_assistant_module.ChatAssistant(config_path="config.yaml")
    original_asr_client = assistant.asr_client
    original_llm_client = assistant.llm_client
    original_tts_client = assistant.tts_client
    original_asr_queue = assistant.asr_text_queue
    original_llm_queue = assistant.llm_text_queue
    original_response_queue = assistant.response_queue
    original_resolved_user_names_queue = assistant.resolved_user_names_queue

    assistant.asr_text = "hello"
    assistant.llm_text = "world"
    assistant.current_user_id = "user-1"
    assistant.current_user_name = "张三"
    assistant.current_user_face_status = True
    assistant.asr_text_queue.put("hello")
    assistant.llm_text_queue.put("world")
    assistant.response_queue.put({"asr_text": "hello", "llm_text": "world"})
    assistant.resolved_user_names_queue.put("张三")
    assistant.response_data.asr_text = "hello"
    assistant.response_data.llm_text = "world"
    assistant.worker_thread_active = True

    assistant.reset()

    assert start_calls == [True]
    assert assistant.worker_thread_active is True

    assert original_asr_client.stop_calls == 1
    assert original_llm_client.stop_calls == 1
    assert original_tts_client.stop_calls == 1

    assert assistant.asr_client is not original_asr_client
    assert assistant.llm_client is not original_llm_client
    assert assistant.tts_client is not original_tts_client

    assert assistant.asr_text == ""
    assert assistant.llm_text == ""
    assert assistant.current_user_id is None
    assert assistant.current_user_name is None
    assert assistant.current_user_face_status is False
    assert assistant.response_data.asr_text == ""
    assert assistant.response_data.llm_text == ""

    assert assistant.asr_text_queue is not original_asr_queue
    assert assistant.llm_text_queue is not original_llm_queue
    assert assistant.response_queue is not original_response_queue
    assert assistant.resolved_user_names_queue is not original_resolved_user_names_queue
    assert assistant.asr_text_queue.empty()
    assert assistant.llm_text_queue.empty()
    assert assistant.response_queue.empty()
    assert assistant.resolved_user_names_queue.empty()


def test_shutdown_component_prefers_stop_then_close(monkeypatch):
    """测试组件释放优先调用 stop，缺少 stop 时再调用 close。"""
    chat_assistant_module = load_chat_assistant_module(monkeypatch)

    stoppable = DummyClient()
    chat_assistant_module.ChatAssistant._shutdown_component(stoppable, "stoppable")
    assert stoppable.stop_calls == 1
    assert stoppable.close_calls == 0

    class ClosableOnly:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    closable = ClosableOnly()
    chat_assistant_module.ChatAssistant._shutdown_component(closable, "closable")
    assert closable.close_calls == 1


def test_push_queue_drops_oldest_when_full(monkeypatch):
    """测试有限队列满时会丢弃最旧元素并保留最新元素。"""
    chat_assistant_module = load_chat_assistant_module(monkeypatch)
    assistant = chat_assistant_module.ChatAssistant.__new__(
        chat_assistant_module.ChatAssistant
    )
    target_queue = Queue(maxsize=2)

    push_queue = getattr(assistant, "_ChatAssistant__push_queue")
    push_queue(target_queue, "first")
    push_queue(target_queue, "second")
    push_queue(target_queue, "third")

    assert list(target_queue.queue) == ["second", "third"]
