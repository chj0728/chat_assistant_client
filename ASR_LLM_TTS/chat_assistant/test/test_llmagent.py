import asyncio
import importlib
import sys
import types
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class BaseMessage:
    content: Any
    additional_kwargs: dict[str, Any] = field(default_factory=dict)


class AIMessage(BaseMessage):
    pass


class AIMessageChunk(BaseMessage):
    pass


class HumanMessage(BaseMessage):
    pass


class SystemMessage(BaseMessage):
    pass


@dataclass
class CustomContext:
    vision_id: str | None = None
    voice_id: str | None = None
    rag_prompt: str | None = None


class DummyHTTPResponse:
    def __init__(self, json_data=None, raise_error=None, status_code=200):
        self._json_data = json_data or {}
        self._raise_error = raise_error
        self.status_code = status_code

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
        self.ainvoke_calls = []
        self.stream_calls = []
        self.astream_calls = []

    def invoke(self, *args, **kwargs):
        self.invoke_calls.append((args, kwargs))
        return self.invoke_result

    async def ainvoke(self, *args, **kwargs):
        self.ainvoke_calls.append((args, kwargs))
        return self.invoke_result

    def stream(self, *args, **kwargs):
        self.stream_calls.append((args, kwargs))
        yield from self.stream_result

    async def astream(self, *args, **kwargs):
        self.astream_calls.append((args, kwargs))
        for item in self.stream_result:
            yield item


class DummyCheckpointer:
    def __init__(self):
        self.deleted_threads = []

    def delete_thread(self, thread_id):
        self.deleted_threads.append(thread_id)


class SecretStr:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def install_llmagent_stubs(monkeypatch) -> None:
    """为 llmagent 的外部重依赖提供最小测试替身。"""
    langchain_agents = types.ModuleType("langchain.agents")
    langchain_agents.create_agent = lambda *args, **kwargs: DummyAgent()

    langchain_middleware = types.ModuleType("langchain.agents.middleware")
    langchain_middleware.AgentMiddleware = object

    langchain_core_messages = types.ModuleType("langchain_core.messages")
    langchain_core_messages.AIMessage = AIMessage
    langchain_core_messages.AIMessageChunk = AIMessageChunk
    langchain_core_messages.HumanMessage = HumanMessage
    langchain_core_messages.SystemMessage = SystemMessage

    langchain_core_runnables = types.ModuleType("langchain_core.runnables")
    langchain_core_runnables.RunnableConfig = dict

    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = lambda **kwargs: SimpleNamespace(
        kwargs=kwargs,
        bind=lambda **bind_kwargs: SimpleNamespace(
            bind_kwargs=bind_kwargs,
            invoke=lambda messages, config=None: AIMessage(content="bound-response"),
        ),
        invoke=lambda messages, config=None: AIMessage(content="response"),
    )

    langgraph_memory = types.ModuleType("langgraph.checkpoint.memory")
    langgraph_memory.InMemorySaver = DummyCheckpointer

    langgraph_sqlite_aio = types.ModuleType("langgraph.checkpoint.sqlite.aio")
    langgraph_sqlite_aio.AsyncSqliteSaver = lambda conn: SimpleNamespace(
        setup=lambda: None
    )

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None

    pydantic = types.ModuleType("pydantic")
    pydantic.SecretStr = SecretStr

    callback_handlers = types.ModuleType("llm.custom_callback_handlers")
    callback_handlers.get_callback_handlers = lambda: [
        SimpleNamespace(),
        SimpleNamespace(usage_metadata={}),
    ]

    custom_context = types.ModuleType("llm.custom_context")
    custom_context.CustomContext = CustomContext

    custom_db = types.ModuleType("llm.custom_db")
    custom_db.create_optimized_aiosqlite_connection = lambda path: None

    custom_middlewares = types.ModuleType("llm.custom_middlewares")
    custom_middlewares.get_custom_middlewares = lambda: []

    custom_tools = types.ModuleType("llm.custom_tools")
    custom_tools.get_custom_tools = lambda: []

    preprocessor = types.ModuleType("llm.custom_text_preprocessor")
    preprocessor.normalize_message_content = normalize_message_content
    preprocessor.select_stream_flush_index = select_stream_flush_index
    preprocessor.split_leading_intent_tags = split_leading_intent_tags
    preprocessor.split_trailing_protected_suffix = split_trailing_protected_suffix

    modules = {
        "langchain.agents": langchain_agents,
        "langchain.agents.middleware": langchain_middleware,
        "langchain_core.messages": langchain_core_messages,
        "langchain_core.runnables": langchain_core_runnables,
        "langchain_openai": langchain_openai,
        "langgraph.checkpoint.memory": langgraph_memory,
        "langgraph.checkpoint.sqlite.aio": langgraph_sqlite_aio,
        "dotenv": dotenv,
        "pydantic": pydantic,
        "llm.custom_callback_handlers": callback_handlers,
        "llm.custom_context": custom_context,
        "llm.custom_db": custom_db,
        "llm.custom_middlewares": custom_middlewares,
        "llm.custom_tools": custom_tools,
        "llm.custom_text_preprocessor": preprocessor,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def normalize_message_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, list):
        return "".join(str(item) for item in content)
    return str(content)


def split_leading_intent_tags(buffer: str) -> tuple[list[str], str]:
    tags = []
    while buffer.startswith("<INTENT>") and "</INTENT>" in buffer:
        end_index = buffer.index("</INTENT>") + len("</INTENT>")
        tags.append(buffer[:end_index])
        buffer = buffer[end_index:]
    return tags, buffer


def split_trailing_protected_suffix(buffer: str) -> tuple[str, str]:
    start_index = buffer.rfind("<INTENT>")
    end_index = buffer.rfind("</INTENT>")
    if start_index != -1 and (end_index == -1 or end_index < start_index):
        return buffer[:start_index], buffer[start_index:]
    return buffer, ""


def select_stream_flush_index(
    buffer: str,
    *,
    min_chunk_chars: int,
    max_chunk_chars: int,
    punctuation_marks: str,
) -> int | None:
    final_text, _ = split_trailing_protected_suffix(buffer)
    if len(final_text) < min_chunk_chars:
        return None
    punctuation_indexes = [
        index + 1
        for index, char in enumerate(final_text[:max_chunk_chars])
        if char in punctuation_marks and index + 1 >= min_chunk_chars
    ]
    if punctuation_indexes:
        return punctuation_indexes[-1]
    return min(len(final_text), max_chunk_chars)


def load_llmagent_module(monkeypatch):
    install_llmagent_stubs(monkeypatch)
    module = importlib.import_module("llm.llmagent")
    return importlib.reload(module)


def build_agent_shell(llmagent_module):
    agent = llmagent_module.LLMAgent.__new__(llmagent_module.LLMAgent)
    agent.global_system_msg = SystemMessage(content="")
    agent.extra_system_prompt = ""
    agent.callback_handlers = [SimpleNamespace(), SimpleNamespace(usage_metadata={})]
    agent.thread_id = "default_memory_checkpointer"
    agent.enable_rag = False
    agent.rag_client = None
    agent.agent = None
    agent.tiny_agent = None
    agent.single_response_agent = None
    agent.async_sqlite_saver = None
    agent.in_memory_checkpointer = DummyCheckpointer()
    agent._background_loop = None
    return agent


async def collect_async_iter(async_iterable):
    return [item async for item in async_iterable]


def test_build_global_system_prompt_appends_extra_prompt(monkeypatch):
    """测试 build_global_system_prompt 是否正确拼接额外系统提示。"""
    llmagent_module = load_llmagent_module(monkeypatch)

    prompt = llmagent_module.build_global_system_prompt("补充规则")

    assert llmagent_module.DEFAULT_SYSTEM_PROMPT in prompt
    assert prompt.endswith("补充规则\n")


def test_build_init_kwargs_from_config_uses_current_keys(monkeypatch):
    """测试配置字典是否映射为当前 LLMAgent 构造参数。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    middleware = object()

    kwargs = llmagent_module.LLMAgent._build_init_kwargs_from_config(
        {
            "llm": {
                "host": "127.0.0.1",
                "port": 9000,
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 10,
                "max_completion_tokens": 512,
                "enable_thinking": True,
                "timeout_sec": 45,
                "extra_system_prompt": "extra",
                "enable_rag": True,
                "enable_cloud": True,
                "enable_health_check": False,
            }
        },
        dynamic_middlewares=[middleware],
    )

    assert kwargs == {
        "host": "127.0.0.1",
        "port": 9000,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 10,
        "max_completion_tokens": 512,
        "enable_thinking": True,
        "timeout": 45,
        "extra_system_prompt": "extra",
        "enable_rag": True,
        "dynamic_middlewares": [middleware],
        "enable_cloud": True,
        "enable_health_check": False,
    }


def test_from_config_passes_kwargs_to_constructor(monkeypatch):
    """测试 from_config 是否通过配置创建 LLMAgent。"""
    llmagent_module = load_llmagent_module(monkeypatch)

    class StubAgent(llmagent_module.LLMAgent):
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    agent = StubAgent.from_config({"llm": {"host": "host-a", "port": 1000}})

    assert agent.kwargs["host"] == "host-a"
    assert agent.kwargs["port"] == 1000


def test_reset_from_config_reinitializes_instance_state(monkeypatch):
    """测试 reset_from_config 会关闭旧状态并按新配置重新初始化实例。"""
    llmagent_module = load_llmagent_module(monkeypatch)

    class ResettableStubAgent(llmagent_module.LLMAgent):
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
                    "temperature": self.temperature,
                    "timeout": self.timeout,
                    "enable_thinking": self.enable_thinking,
                    "extra_system_prompt": self.extra_system_prompt,
                    "enable_rag": self.enable_rag,
                    "enable_cloud": self.enable_cloud,
                    "dynamic_middlewares": self.dynamic_middlewares,
                    "system_prompt": self.global_system_msg.content,
                }
            )

    first_middleware = object()
    second_middleware = object()
    agent = ResettableStubAgent(
        host="127.0.0.1",
        port=8000,
        dynamic_middlewares=[first_middleware],
        extra_system_prompt="old",
        timeout=15,
    )

    agent.reset_from_config(
        {
            "llm": {
                "host": "192.168.1.20",
                "port": 9001,
                "temperature": 0.2,
                "top_p": 0.7,
                "top_k": 20,
                "max_completion_tokens": 128,
                "enable_thinking": True,
                "timeout_sec": 60,
                "extra_system_prompt": "new prompt",
                "enable_rag": True,
                "enable_cloud": True,
                "enable_health_check": False,
            }
        },
        dynamic_middlewares=[second_middleware],
    )

    assert agent.close_calls == 1
    assert len(agent.initialize_snapshots) == 2
    assert agent.host == "192.168.1.20"
    assert agent.port == 9001
    assert agent.temperature == 0.2
    assert agent.top_p == 0.7
    assert agent.top_k == 20
    assert agent.max_completion_tokens == 128
    assert agent.enable_thinking is True
    assert agent.timeout == 60
    assert agent.extra_system_prompt == "new prompt"
    assert agent.enable_rag is True
    assert agent.enable_cloud is True
    assert agent.enable_health_check is False
    assert agent.dynamic_middlewares == [second_middleware]
    assert agent.global_system_msg.content == llmagent_module.build_global_system_prompt(
        "new prompt"
    )


def test_load_model_metadata_uses_remote_metadata(monkeypatch):
    """测试 _load_model_metadata 成功时是否写入远端模型信息。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    agent.llm_url = "http://127.0.0.1:8000/v1/models"
    agent.timeout = 5
    agent.enable_cloud = False
    agent.model_id = None
    agent.model_root = None
    calls = []

    def fake_get(url, timeout, headers=None):
        calls.append((url, timeout, headers))
        return DummyHTTPResponse(
            json_data={"data": [{"id": "custom-model", "root": "/models/custom"}]}
        )

    monkeypatch.setattr(llmagent_module.requests, "get", fake_get)
    agent._load_model_metadata()

    assert agent.model_id == "custom-model"
    assert agent.model_root == "/models/custom"
    assert calls == [("http://127.0.0.1:8000/v1/models", 5, None)]


def test_load_model_metadata_cloud_uses_default_without_request(monkeypatch):
    """测试云端模式不请求模型列表，直接使用默认模型 ID。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    agent.enable_cloud = True
    agent.model_id = None
    agent.model_root = "unexpected"

    agent._load_model_metadata()

    assert agent.model_id == llmagent_module.DEFAULT_MODEL_ID
    assert agent.model_root is None


def test_load_model_metadata_falls_back_to_default(monkeypatch):
    """测试模型元数据请求失败时回退到默认模型。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    agent.llm_url = "http://127.0.0.1:8000/v1/models"
    agent.timeout = 5
    agent.enable_cloud = False
    agent.model_id = None
    agent.model_root = "unexpected"

    def raise_request_error(url, timeout, headers=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(llmagent_module.requests, "get", raise_request_error)
    agent._load_model_metadata()

    assert agent.model_id == llmagent_module.DEFAULT_MODEL_ID
    assert agent.model_root is None


def test_init_api_key_and_base_url_supports_local_and_cloud(monkeypatch):
    """测试本地与云端模式的 API 地址初始化。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)

    agent.enable_cloud = False
    agent.host = "localhost"
    agent.port = 8000
    agent._init_api_key_and_base_url()
    assert agent.api_key.get_secret_value() == "EMPTY"
    assert agent.endpoint == "http://localhost:8000"
    assert agent.base_url == "http://localhost:8000/v1"

    monkeypatch.setenv("API_TOKEN", "token")
    monkeypatch.setenv("API_ENDPOINT", "https://api.example.com")
    agent.enable_cloud = True
    agent._init_api_key_and_base_url()
    assert agent.api_key.get_secret_value() == "token"
    assert agent.endpoint == "https://api.example.com"
    assert agent.base_url == "https://api.example.com/v1"


def test_build_input_messages_returns_human_message_with_ids(monkeypatch):
    """测试输入消息会带上视觉和语音 ID。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)

    messages = agent._build_input_messages(
        "你好", vision_id="vision-1", voice_id="voice-1"
    )

    assert messages == [
        HumanMessage(
            content="你好",
            additional_kwargs={
                "format_time": messages[0].additional_kwargs["format_time"],
                "vision_id": "vision-1",
                "voice_id": "voice-1",
            },
        )
    ]


def test_build_runtime_context_uses_rag_prompt(monkeypatch):
    """测试启用 RAG 时运行时上下文包含检索增强提示词。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    agent.enable_rag = True
    agent.rag_client = SimpleNamespace(
        query=lambda **kwargs: {"prompt": "RAG prompt", "second": True}
    )

    context = agent._build_runtime_context(
        "你好", vision_id="vision-1", voice_id="voice-1", rag_id="rag-1"
    )

    assert context == CustomContext(
        vision_id="vision-1", voice_id="voice-1", rag_prompt="RAG prompt"
    )
    assert agent.get_query_to_resolve() is True


def test_chat_response_uses_tiny_agent_without_vision_id(monkeypatch):
    """测试无视觉 ID 时 chat_response 使用 tiny_agent 和默认线程。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    agent.tiny_agent = DummyAgent(
        invoke_result={"messages": [AIMessage(content="快速回答")]}
    )

    result = agent.chat_response("你好")

    assert result == "快速回答"
    invoke_args, invoke_kwargs = agent.tiny_agent.invoke_calls[0]
    assert invoke_args[0]["messages"][0].content == "你好"
    assert invoke_kwargs["context"] == CustomContext(vision_id=None, voice_id=None)
    assert invoke_kwargs["config"]["configurable"]["thread_id"] == str(agent.thread_id)
    assert invoke_kwargs["stream_mode"] == "values"


def test_chat_response_uses_stateful_agent_with_vision_id(monkeypatch):
    """测试有视觉 ID 时 chat_response 使用持久化 agent 和视觉线程。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    agent.agent = DummyAgent(invoke_result={"messages": [AIMessage(content="上下文回答")]})

    result = agent.chat_response("你好", vision_id="vision-1", voice_id="voice-1")

    assert result == "上下文回答"
    invoke_args, invoke_kwargs = agent.agent.invoke_calls[0]
    assert invoke_args[0]["messages"][0].additional_kwargs["vision_id"] == "vision-1"
    assert invoke_kwargs["context"] == CustomContext(
        vision_id="vision-1", voice_id="voice-1"
    )
    assert invoke_kwargs["config"]["configurable"]["thread_id"] == "vision-1"


def test_chat_response_stream_flushes_chunks(monkeypatch):
    """测试同步流式响应按最大长度输出分片。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    agent.tiny_agent = DummyAgent(stream_result=[AIMessageChunk(content="a" * 55)])

    result = list(agent.chat_response_stream("hello"))

    assert result == [("a" * 50, 0), ("a" * 5, 1)]
    assert agent.tiny_agent.stream_calls[0][1]["stream_mode"] == "messages"


def test_chat_response_stream_keeps_intent_tag_unsplit(monkeypatch):
    """测试流式响应不会切开尾部 INTENT 标签。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    plain_text = "这是一段足够长的文本用于测试标签保护并满足分段阈值。"
    intent_text = "<INTENT>WAIT_FOR_TALK</INTENT>"
    agent.tiny_agent = DummyAgent(
        stream_result=[
            AIMessageChunk(content=plain_text),
            AIMessageChunk(content="<INTENT>WAIT_FOR_"),
            AIMessageChunk(content="TALK</INTENT>"),
        ]
    )

    result = list(agent.chat_response_stream("hello"))

    assert result == [(plain_text, 0), (intent_text, 1)]


def test_async_chat_response_direct_agent_path(monkeypatch):
    """测试异步完整响应在手工注入 agent 时走直接路径。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    agent.agent = DummyAgent(invoke_result={"messages": [AIMessage(content="异步回答")]})

    result = asyncio.run(agent.async_chat_response("你好", vision_id="vision-1"))

    assert result == "异步回答"
    assert len(agent.agent.ainvoke_calls) == 1


def test_async_chat_response_stream_direct_agent_path(monkeypatch):
    """测试异步流式响应在手工注入 agent 时走直接路径。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)
    sentence = "这是一段足够长的文本用于测试异步流式输出。"
    agent.agent = DummyAgent(stream_result=[AIMessageChunk(content=sentence)])

    result = asyncio.run(
        collect_async_iter(
            agent.async_chat_response_stream("你好", vision_id="vision-1")
        )
    )

    assert result == [(sentence, 0)]
    assert len(agent.agent.astream_calls) == 1


def test_get_last_ai_content_returns_none_for_non_ai_message(monkeypatch):
    """测试 _get_last_ai_content 遇到非 AIMessage 时返回 None。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)

    result = agent._get_last_ai_content({"messages": [HumanMessage(content="hello")]})

    assert result is None


def test_delete_thread_uses_memory_checkpointer_by_default(monkeypatch):
    """测试 delete_thread 默认删除内存检查点中的默认线程。"""
    llmagent_module = load_llmagent_module(monkeypatch)
    agent = build_agent_shell(llmagent_module)

    assert agent.delete_thread() is True
    assert agent.in_memory_checkpointer.deleted_threads == [str(agent.thread_id)]
