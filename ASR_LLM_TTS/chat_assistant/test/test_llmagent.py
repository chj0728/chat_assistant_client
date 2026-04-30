from types import SimpleNamespace
from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware
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
    agent.global_system_msg = SystemMessage(content="")
    agent.extra_system_prompt = ""
    agent.callback_handlers = [SimpleNamespace(), SimpleNamespace(usage_metadata={})]
    agent.thread_id = llmagent_module.uuid7()
    agent.rag_enable = False
    agent.rag_client = None
    return agent


def test_get_callback_handlers_returns_default_handlers():
    """测试 get_callback_handlers 是否返回默认回调处理器列表。"""
    handlers = llmagent_module.get_callback_handlers()

    assert len(handlers) == 2
    assert handlers[1].usage_metadata == {}


def test_build_global_system_prompt_appends_extra_prompt():
    """测试 build_global_system_prompt 是否正确拼接额外系统提示。"""
    prompt = llmagent_module.build_global_system_prompt("补充规则")

    assert llmagent_module.DEFAULT_SYSTEM_PROMPT in prompt
    assert prompt.endswith("补充规则\n")


def test_from_config_maps_llm_options_to_constructor():
    """测试 from_config 是否将 llm 配置映射到构造参数。"""

    class StubAgent(llmagent_module.LLMAgent):
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    middleware = cast(AgentMiddleware, object())
    config = {
        "llm": {
            "host": "127.0.0.1",
            "port": 9000,
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 10,
            "max_completion_tokens": 512,
            "enable_thinking": True,
            "extra_system_prompt": "extra",
            "rag_enable": True,
        }
    }

    agent = cast(Any, StubAgent.from_config(config, dynamic_middlewares=[middleware]))

    assert agent.kwargs == {
        "host": "127.0.0.1",
        "port": 9000,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 10,
        "max_completion_tokens": 512,
        "enable_thinking": True,
        "extra_system_prompt": "extra",
        "rag_enable": True,
        "dynamic_middlewares": [middleware],
    }


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


def test_build_input_messages_without_rag_returns_only_human_message():
    """测试未启用 RAG 时输入消息仅包含用户消息。"""
    agent = build_agent_shell()

    messages = agent._build_input_messages("你好", user_id="user-1")

    assert messages == [
        HumanMessage(content="你好", additional_kwargs={"user_id": "user-1"})
    ]


def test_build_input_messages_with_rag_prepends_system_message():
    """测试启用 RAG 时输入消息会带上检索增强提示。"""
    agent = build_agent_shell()
    agent.rag_enable = True
    agent.rag_client = cast(
        Any, SimpleNamespace(query=lambda user_text: {"prompt": f"RAG:{user_text}"})
    )

    messages = agent._build_input_messages("你好", user_id="user-1")

    assert messages == [
        SystemMessage(content="RAG:你好"),
        HumanMessage(content="你好", additional_kwargs={"user_id": "user-1"}),
    ]


def test_chat_response_uses_agent_with_user_id_context():
    """测试 chat_response 在提供 user_id 时会传入正确上下文和线程 ID。"""
    agent = build_agent_shell()
    stateful_agent = DummyAgent(
        invoke_result={"messages": [AIMessage(content="有上下文回答")]}
    )
    agent.agent = cast(Any, stateful_agent)

    result = agent.chat_response("你好", user_id="user-1")

    assert result == "有上下文回答"
    assert len(stateful_agent.invoke_calls) == 1
    invoke_args, invoke_kwargs = stateful_agent.invoke_calls[0]
    assert invoke_args == (
        {
            "messages": [
                HumanMessage(content="你好", additional_kwargs={"user_id": "user-1"})
            ]
        },
    )
    assert invoke_kwargs["context"] == llmagent_module.CustomContext(user_id="user-1")
    assert invoke_kwargs["config"] == {
        "callbacks": agent.callback_handlers,
        "configurable": {"thread_id": "user-1"},
    }
    assert invoke_kwargs["stream_mode"] == "values"


def test_chat_response_uses_default_thread_id_without_user_id():
    """测试 chat_response 在未提供 user_id 时使用默认 thread_id。"""
    agent = build_agent_shell()
    stateful_agent = DummyAgent(
        invoke_result={"messages": [AIMessage(content="快速回答")]}
    )
    agent.agent = cast(Any, stateful_agent)

    result = agent.chat_response("你好")

    assert result == "快速回答"
    assert len(stateful_agent.invoke_calls) == 1
    invoke_args, invoke_kwargs = stateful_agent.invoke_calls[0]
    assert invoke_args == (
        {
            "messages": [
                HumanMessage(content="你好", additional_kwargs={"user_id": None})
            ]
        },
    )
    assert invoke_kwargs["context"] == llmagent_module.CustomContext(user_id=None)
    assert invoke_kwargs["config"] == {
        "callbacks": agent.callback_handlers,
        "configurable": {"thread_id": str(agent.thread_id)},
    }
    assert invoke_kwargs["stream_mode"] == "values"


def test_chat_response_stream_flushes_by_max_chunk_length():
    """测试 chat_response_stream 是否在达到最大长度时正确切分输出。"""
    agent = build_agent_shell()
    stateful_agent = DummyAgent(stream_result=[AIMessageChunk(content="a" * 55)])
    agent.agent = cast(Any, stateful_agent)

    result = list(agent.chat_response_stream("hello"))

    assert result == [("a" * 50, 0), ("a" * 5, 1)]
    stream_args, stream_kwargs = stateful_agent.stream_calls[0]
    assert stream_args == (
        {
            "messages": [
                HumanMessage(content="hello", additional_kwargs={"user_id": None})
            ]
        },
    )
    assert stream_kwargs["context"] == llmagent_module.CustomContext(user_id=None)
    assert stream_kwargs["config"] == {
        "callbacks": agent.callback_handlers,
        "configurable": {"thread_id": str(agent.thread_id)},
    }
    assert stream_kwargs["stream_mode"] == "messages"


def test_chat_response_stream_flushes_by_punctuation_with_user_id():
    """测试 chat_response_stream 在提供 user_id 时是否按标点优先切分。"""
    agent = build_agent_shell()
    sentence = "这是一段足够长的文本用于测试分句逻辑而且已经超过二十个字。"
    stateful_agent = DummyAgent(
        stream_result=[(AIMessageChunk(content=sentence), SimpleNamespace())]
    )
    agent.agent = cast(Any, stateful_agent)

    result = list(agent.chat_response_stream("你好", user_id="user-2"))

    assert result == [(sentence, 0)]
    assert len(stateful_agent.stream_calls) == 1
    stream_args, stream_kwargs = stateful_agent.stream_calls[0]
    assert stream_args == (
        {
            "messages": [
                HumanMessage(content="你好", additional_kwargs={"user_id": "user-2"})
            ]
        },
    )
    assert stream_kwargs["context"] == llmagent_module.CustomContext(user_id="user-2")
    assert stream_kwargs["config"] == {
        "callbacks": agent.callback_handlers,
        "configurable": {"thread_id": "user-2"},
    }
    assert stream_kwargs["stream_mode"] == "messages"


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
    agent.agent = cast(Any, tiny_agent)

    result = list(agent.chat_response_stream("hello"))

    assert result == [(plain_text, 0), (intent_text, 1)]


def test_get_last_ai_content_returns_none_for_non_ai_message():
    """测试 __get_last_ai_content 遇到非 AIMessage 时是否返回 None。"""
    agent = build_agent_shell()

    get_last_ai_content = cast(Any, getattr(agent, "_LLMAgent__get_last_ai_content"))
    result = get_last_ai_content({"messages": [HumanMessage(content="hello")]})

    assert result is None
