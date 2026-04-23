from types import SimpleNamespace
from typing import Any, cast

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
)
from llm import llmagent as llmagent_module


class DummyHTTPResponse:
    def __init__(self, json_data=None, raise_error=None):
        self._json_data = json_data or {}
        self._raise_error = raise_error

    def raise_for_status(self):
        if self._raise_error is not None:
            raise self._raise_error

    def json(self):
        return self._json_data


class DummyAgent:
    def __init__(self, *, invoke_result=None, stream_result=None):
        self.invoke_result = invoke_result
        self.stream_result = stream_result or []
        self.invoke_calls = []
        self.stream_calls = []

    def invoke(self, *args, **kwargs):
        self.invoke_calls.append((args, kwargs))
        return self.invoke_result

    def stream(self, *args, **kwargs):
        self.stream_calls.append((args, kwargs))
        for item in self.stream_result:
            yield item


def build_agent_shell():
    agent = llmagent_module.LLMAgent.__new__(llmagent_module.LLMAgent)
    agent.system_msg = cast(Any, SystemMessage(content=""))
    return agent


def test_get_max_messages_uses_config_value(monkeypatch):
    """测试 get_max_messages 是否正确读取配置中的 max_messages 值。"""
    monkeypatch.setattr(
        llmagent_module,
        "load_config",
        lambda: {"llm": {"max_messages": 9}},
    )

    assert llmagent_module.get_max_messages() == 9


def test_get_max_messages_falls_back_to_default(monkeypatch):
    """测试 get_max_messages 在配置缺失时是否回退到默认值。"""
    monkeypatch.setattr(llmagent_module, "load_config", lambda: {})

    assert llmagent_module.get_max_messages(default=7) == 7


def test_build_system_prompt_appends_extra_prompt():
    """测试 build_system_prompt 是否正确拼接额外系统提示。"""
    prompt = llmagent_module.build_system_prompt("补充规则")

    assert llmagent_module.DEFAULT_SYSTEM_PROMPT in prompt
    assert prompt.endswith("补充规则\n")


def test_select_stream_flush_index_avoids_open_intent_suffix():
    """测试流式切分不会切进尾部未闭合的 INTENT 标签。"""
    plain_text = "这是一段足够长的普通文本用于测试分段阈值是否生效。"
    buffer = plain_text + "<INTENT>WAIT_FOR_TALK"

    flush_index = llmagent_module.select_stream_flush_index(
        buffer,
        min_chunk_chars=20,
        max_chunk_chars=50,
        punctuation_marks="。！？!?；;，,：:",
    )

    assert flush_index == len(plain_text)


def test_select_stream_flush_index_allows_closed_intent_suffix():
    """测试 INTENT 标签闭合后，不会被误判为受保护尾段。"""
    plain_text = "这是一段足够长的普通文本用于测试分段阈值是否生效。"
    buffer = plain_text + "<INTENT>WAIT_FOR_TALK</INTENT>"

    flush_index = llmagent_module.select_stream_flush_index(
        buffer,
        min_chunk_chars=20,
        max_chunk_chars=50,
        punctuation_marks="。！？!?；;，,：:",
    )

    assert flush_index == len(plain_text)


def test_normalize_message_content_handles_list_and_none():
    """测试 normalize_message_content 是否正确处理列表和 None。"""
    assert (
        llmagent_module.normalize_message_content(["你好", 123, "世界"])
        == "你好123世界"
    )
    assert llmagent_module.normalize_message_content(None) == ""


def test_create_optimized_sqlite_connection_creates_parent_directory(tmp_path):
    """测试 create_optimized_sqlite_connection 是否自动创建数据库父目录。"""
    db_path = tmp_path / "nested" / "agent.db"

    with llmagent_module.create_optimized_sqlite_connection(db_path) as conn:
        cursor = conn.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0].lower()

    assert db_path.parent.exists() is True
    assert journal_mode == "wal"


def test_load_model_metadata_uses_remote_metadata(monkeypatch):
    """测试 _load_model_metadata 成功时是否正确写入远端模型信息。"""
    agent = build_agent_shell()
    agent.llm_url = "http://127.0.0.1:8000/v1/models"
    agent.timeout = 5
    agent.model_id = None
    agent.model_root = None

    monkeypatch.setattr(
        llmagent_module.requests,
        "get",
        lambda url, timeout: DummyHTTPResponse(
            json_data={"data": [{"id": "custom-model", "root": "/models/custom"}]}
        ),
    )

    agent._load_model_metadata()

    assert agent.model_id == "custom-model"
    assert agent.model_root == "/models/custom"


def test_load_model_metadata_falls_back_to_default(monkeypatch):
    """测试 _load_model_metadata 失败时是否回退到默认模型。"""
    agent = build_agent_shell()
    agent.llm_url = "http://127.0.0.1:8000/v1/models"
    agent.timeout = 5
    agent.model_id = None
    agent.model_root = "unexpected"

    def raise_request_error(url, timeout):
        raise RuntimeError("network down")

    monkeypatch.setattr(llmagent_module.requests, "get", raise_request_error)

    agent._load_model_metadata()

    assert agent.model_id == llmagent_module.DEFAULT_MODEL_ID
    assert agent.model_root is None


def test_add_system_prompt_updates_system_message():
    """测试 add_system_prompt 是否正确更新系统提示消息内容。"""
    agent = build_agent_shell()

    agent.add_system_prompt("新的规则")

    system_content = cast(str, agent.system_msg.content)
    assert "新的规则" in system_content
    assert system_content.endswith("新的规则")


def test_chat_response_uses_stateful_agent_for_user_id():
    """测试 chat_response 在提供 user_id 时是否走带上下文的 agent。"""
    agent = build_agent_shell()
    stateful_agent = DummyAgent(
        invoke_result={"messages": [AIMessage(content="有上下文回答")]}
    )
    tiny_agent = DummyAgent(invoke_result={"messages": [AIMessage(content="不应使用")]})
    agent.agent = cast(Any, stateful_agent)
    agent.tiny_agent = cast(Any, tiny_agent)

    result = agent.chat_response("你好", user_id="user-1")

    assert result == "有上下文回答"
    assert len(stateful_agent.invoke_calls) == 1
    invoke_args, invoke_kwargs = stateful_agent.invoke_calls[0]
    assert invoke_args[0]["messages"][0] == HumanMessage(
        content="你好",
        additional_kwargs={"user_id": "user-1"},
    )
    assert invoke_args[1] == {"configurable": {"thread_id": "user-1"}}
    assert invoke_kwargs == {"stream_mode": "values"}
    assert tiny_agent.invoke_calls == []


def test_chat_response_uses_tiny_agent_without_user_id():
    """测试 chat_response 在未提供 user_id 时是否走无上下文的 tiny_agent。"""
    agent = build_agent_shell()
    stateful_agent = DummyAgent(
        invoke_result={"messages": [AIMessage(content="不应使用")]}
    )
    tiny_agent = DummyAgent(invoke_result={"messages": [AIMessage(content="快速回答")]})
    agent.agent = cast(Any, stateful_agent)
    agent.tiny_agent = cast(Any, tiny_agent)

    result = agent.chat_response("你好")

    assert result == "快速回答"
    assert len(tiny_agent.invoke_calls) == 1
    invoke_args, invoke_kwargs = tiny_agent.invoke_calls[0]
    assert invoke_args == (
        {
            "messages": [
                HumanMessage(content="你好", additional_kwargs={"user_id": None})
            ]
        },
    )
    assert invoke_kwargs == {}
    assert stateful_agent.invoke_calls == []


def test_chat_response_stream_flushes_by_max_chunk_length():
    """测试 chat_response_stream 是否在达到最大长度时正确切分输出。"""
    agent = build_agent_shell()
    stateful_agent = DummyAgent()
    tiny_agent = DummyAgent(stream_result=[AIMessageChunk(content="a" * 55)])
    agent.agent = cast(Any, stateful_agent)
    agent.tiny_agent = cast(Any, tiny_agent)

    result = list(agent.chat_response_stream("hello"))

    assert result == [("a" * 50, 0), ("a" * 5, 1)]


def test_chat_response_stream_flushes_by_punctuation_with_user_id():
    """测试 chat_response_stream 在提供 user_id 时是否按标点优先切分。"""
    agent = build_agent_shell()
    sentence = "这是一段足够长的文本用于测试分句逻辑而且已经超过二十个字。"
    stateful_agent = DummyAgent(
        stream_result=[(AIMessageChunk(content=sentence), SimpleNamespace())]
    )
    tiny_agent = DummyAgent()
    agent.agent = cast(Any, stateful_agent)
    agent.tiny_agent = cast(Any, tiny_agent)

    result = list(agent.chat_response_stream("你好", user_id="user-2"))

    assert result == [(sentence, 0)]
    assert len(stateful_agent.stream_calls) == 1
    stream_args, stream_kwargs = stateful_agent.stream_calls[0]
    assert stream_args[1] == {"configurable": {"thread_id": "user-2"}}
    assert stream_kwargs == {"stream_mode": "messages"}


def test_chat_response_stream_keeps_intent_tag_unsplit():
    """测试 chat_response_stream 不会把尾部 INTENT 标签切开。"""
    agent = build_agent_shell()
    plain_text = "这是一段足够长的文本用于测试标签保护并满足分段阈值。"
    intent_text = "<INTENT>WAIT_FOR_TALK</INTENT>"
    tiny_agent = DummyAgent(
        stream_result=[
            AIMessageChunk(content=plain_text),
            AIMessageChunk(content="<INTENT>WAIT_FOR_"),
            AIMessageChunk(content="TALK</INTENT>"),
        ]
    )
    agent.agent = cast(Any, DummyAgent())
    agent.tiny_agent = cast(Any, tiny_agent)

    result = list(agent.chat_response_stream("hello"))

    assert result == [(plain_text, 0), (intent_text, 1)]


def test_get_last_ai_content_returns_none_for_non_ai_message():
    """测试 __get_last_ai_content 遇到非 AIMessage 时是否返回 None。"""
    agent = build_agent_shell()

    get_last_ai_content = cast(Any, getattr(agent, "_LLMAgent__get_last_ai_content"))
    result = get_last_ai_content({"messages": [HumanMessage(content="hello")]})

    assert result is None
