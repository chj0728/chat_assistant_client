"""
ASR_LLM_TTS.chat_assistant.llm.llmagent 的 Docstring

description: 该模块定义了用于创建和管理基于大型语言模型（LLM）的聊天代理的功能。
基于 LangChain 框架
支持系统消息配置
支持工具函数调用
支持多轮对话和上下文记忆
参考链接:
- LangChain 官方文档: https://docs.langchain.com/oss/python/langchain/agents
- LangChain GitHub 仓库: https://github.com/langchain-ai/langchain
"""

import asyncio
import re
import sqlite3
import threading
from pathlib import Path
from queue import Queue
from typing import Any, AsyncIterator, Generator

import aiosqlite
import requests
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
)
from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig

# from langgraph.store.sqlite import SqliteStore
# from uuid import uuid7
# from langsmith import uuid7_from_datetime
from langchain_core.utils.uuid import uuid7
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from logger import logger
from pydantic import SecretStr

from llm.custom_context import CustomContext
from llm.custom_middlewares import get_custom_middlewares
from llm.custom_tools import get_custom_tools

DEFAULT_MODEL_ID = "Qwen/Qwen3"
DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent.parent / "db" / "agent_conversations.db"
)
DEFAULT_SYSTEM_PROMPT = (
    "你需要简洁且有礼貌地回答用户的问题，请保持回答简短且有条理，控制在120字以内。\n"
    "正文中请正常使用中文标点符号来表达停顿和语义边界，便于流式切分和语音合成。\n"
    "如果你不确定答案，可以礼貌地告诉用户你不知道。\n"
    "只有当用户回答退出、结束等相关内容时，调用结束对话的工具函数，礼貌地结束对话。"
)
INTENT_TAG_START = "<INTENT>"
INTENT_TAG_END = "</INTENT>"
INTENT_TAG_PATTERN = re.compile(
    rf"{re.escape(INTENT_TAG_START)}.*?{re.escape(INTENT_TAG_END)}", re.DOTALL
)


# config 设置里的回调函数示例，实际使用时可以根据需要进行修改和扩展
## refer from:
## - https://reference.langchain.com/python/langchain-core/callbacks/base/BaseCallbackHandler
## - https://reference.langchain.org.cn/python/langchain_core/callbacks/
class my_callback_handler(BaseCallbackHandler):
    """自定义回调函数示例，用于处理模型生成的消息块。"""

    logger.debug("初始化自定义回调处理器")

    # def on_chain_start(self, serialized, inputs, **kwargs):
    #     logger.debug("链开始")


def get_callback_handlers():
    """返回默认启用的回调处理器列表。"""
    return [
        my_callback_handler(),
        UsageMetadataCallbackHandler(),
    ]


def build_global_system_prompt(extra_prompt: str | None = None) -> str:
    """构造系统提示词。"""
    if extra_prompt:
        return f"{DEFAULT_SYSTEM_PROMPT}\n{extra_prompt}\n"
    return DEFAULT_SYSTEM_PROMPT + "\n"


def normalize_message_content(content: Any) -> str:
    """将 LangChain 消息内容统一转换为字符串。"""
    if isinstance(content, list):
        return "".join(part if isinstance(part, str) else str(part) for part in content)
    if content is None:
        return ""
    return str(content)


def find_protected_suffix_start(buffer: str) -> int | None:
    """返回尾部未闭合 INTENT 标签的起始位置；若不存在则返回 None。"""
    last_open = buffer.rfind(INTENT_TAG_START)
    if last_open < 0:
        return None

    last_close = buffer.rfind(INTENT_TAG_END)
    if last_close > last_open:
        return None

    return last_open


def find_trailing_intent_tag_start(buffer: str) -> int | None:
    """返回尾部完整或未闭合 INTENT 标签的起始位置；若尾部不存在则返回 None。"""
    last_open = buffer.rfind(INTENT_TAG_START)
    if last_open < 0:
        return None

    last_close = buffer.rfind(INTENT_TAG_END)
    if last_close < last_open:
        return last_open

    trailing_intent_end = last_close + len(INTENT_TAG_END)
    if trailing_intent_end == len(buffer):
        return last_open

    return None


def find_trailing_intent_prefix_start(buffer: str) -> int | None:
    """返回尾部未拼完整的 INTENT 起始标签前缀位置；若不存在则返回 None。"""
    for prefix_len in range(len(INTENT_TAG_START) - 1, 0, -1):
        prefix = INTENT_TAG_START[:prefix_len]
        if buffer.endswith(prefix):
            return len(buffer) - prefix_len
    return None


def find_trailing_protected_suffix_start(buffer: str) -> int | None:
    """返回尾部受保护后缀的起始位置，覆盖完整、未闭合及部分 INTENT 标签。"""
    trailing_intent_tag_start = find_trailing_intent_tag_start(buffer)
    if trailing_intent_tag_start is not None:
        return trailing_intent_tag_start
    return find_trailing_intent_prefix_start(buffer)


def split_trailing_protected_suffix(buffer: str) -> tuple[str, str]:
    """拆分正文与尾部受保护的 INTENT 标签后缀。"""
    protected_suffix_start = find_trailing_protected_suffix_start(buffer)
    if protected_suffix_start is None:
        return buffer, ""
    return buffer[:protected_suffix_start], buffer[protected_suffix_start:]


def build_visible_text_and_raw_offsets(buffer: str) -> tuple[str, list[int]]:
    """构造忽略完整 INTENT 标签后的可见文本，以及可见字符到原始下标的映射。"""
    visible_parts: list[str] = []
    raw_offsets: list[int] = []
    cursor = 0

    for match in INTENT_TAG_PATTERN.finditer(buffer):
        segment = buffer[cursor : match.start()]
        visible_parts.append(segment)
        raw_offsets.extend(range(cursor + 1, match.start() + 1))
        cursor = match.end()

    tail_segment = buffer[cursor:]
    visible_parts.append(tail_segment)
    raw_offsets.extend(range(cursor + 1, len(buffer) + 1))

    return "".join(visible_parts), raw_offsets


def split_leading_intent_tags(buffer: str) -> tuple[list[str], str]:
    """拆分位于缓冲区开头的完整 INTENT 标签，保持标签整体输出。"""
    leading_tags: list[str] = []
    remaining = buffer

    while True:
        match = INTENT_TAG_PATTERN.match(remaining)
        if match is None:
            break
        leading_tags.append(match.group(0))
        remaining = remaining[match.end() :]

    return leading_tags, remaining


def select_stream_flush_index(
    buffer: str,
    *,
    min_chunk_chars: int,
    max_chunk_chars: int,
    punctuation_marks: str,
) -> int | None:
    """选择流式文本的切分位置，在指定窗口内优先按标点切分。"""
    protected_suffix_start = find_trailing_protected_suffix_start(buffer)
    searchable_buffer = (
        buffer[:protected_suffix_start]
        if protected_suffix_start is not None
        else buffer
    )
    searchable_text, raw_offsets = build_visible_text_and_raw_offsets(searchable_buffer)

    if len(searchable_text) < min_chunk_chars:
        return None

    window_end = min(len(searchable_text), max_chunk_chars)
    window_text = searchable_text[:window_end]
    window_start = min_chunk_chars - 1

    flush_index = None
    last_punctuation = max(
        (window_text.rfind(mark, window_start) for mark in punctuation_marks),
        default=-1,
    )
    if last_punctuation >= window_start:
        flush_index = raw_offsets[last_punctuation]
    elif len(searchable_text) >= max_chunk_chars:
        flush_index = raw_offsets[max_chunk_chars - 1]

    if flush_index is None:
        return None

    protected_suffix_start = find_protected_suffix_start(buffer)
    if protected_suffix_start is None or flush_index <= protected_suffix_start:
        return flush_index

    if protected_suffix_start >= min_chunk_chars:
        return protected_suffix_start

    return None


def create_optimized_sqlite_connection(db_path: str | Path) -> sqlite3.Connection:
    """创建经过性能优化的SQLite连接"""
    db_path = Path(db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=False,  # 允许多线程访问
        timeout=30,  # 超时时间
        isolation_level=None,  # 自动提交模式
    )

    # 性能优化配置
    conn.executescript("""
        PRAGMA journal_mode=WAL;          -- 写前日志模式，提高并发性能
        PRAGMA synchronous=NORMAL;        -- 平衡性能和数据安全
        PRAGMA cache_size=-2000;          -- 设置2MB缓存
        PRAGMA temp_store=MEMORY;         -- 临时表存储在内存中
        PRAGMA mmap_size=268435456;       -- 256MB内存映射
        PRAGMA busy_timeout=5000;         -- 5秒忙超时
        """)
    return conn


async def create_optimized_aiosqlite_connection(
    db_path: str | Path,
) -> aiosqlite.Connection:
    """创建经过性能优化的异步SQLite连接"""
    db_path = Path(db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _create_connection():
        conn = await aiosqlite.connect(
            str(db_path),
            check_same_thread=False,  # 允许多线程访问
            timeout=30,  # 超时时间
            isolation_level=None,  # 自动提交模式
        )

        # 性能优化配置
        await conn.executescript("""
            PRAGMA journal_mode=WAL;          -- 写前日志模式，提高并发性能
            PRAGMA synchronous=NORMAL;        -- 平衡性能和数据安全
            PRAGMA cache_size=-2000;          -- 设置2MB缓存
            PRAGMA temp_store=MEMORY;         -- 临时表存储在内存中
            PRAGMA mmap_size=268435456;       -- 256MB内存映射
            PRAGMA busy_timeout=5000;         -- 5秒忙超时
            """)
        return conn

    return await _create_connection()


class LLMAgent:
    """
    LLMAgent 类用于创建和管理基于大型语言模型（LLM）的聊天代理。
    基于 LangChain 框架，支持系统消息配置和从对话状态中提取 AI 消息内容的实用函数。
    """

    def __init__(
        self,
        host,
        port,
        dynamic_middlewares: list[AgentMiddleware] | None = None,
        temperature=0.6,
        top_p=0.95,
        top_k=50,
        max_completion_tokens=256,
        enable_thinking=False,
        timeout=30,
        extra_system_prompt: str | None = None,
        rag_enable=False,
    ):
        """
        初始化 LLMAgent 实例。

        参数:
            host (str): LLM 服务的主机地址。
            port (int): LLM 服务的端口号。
            dynamic_middlewares (list[AgentMiddleware] | None): 可选的动态中间件列表。 默认值为 None。
            temperature (float): 控制生成文本的随机性。默认值为 0.6。
            top_p (float): 用于 nucleus 采样的概率阈值。默认值为 0.95。
            top_k (int): 用于 top-k 采样的词汇数量。默认值为 50。
            max_completion_tokens (int): 生成内容（completion） 的 token 数量，根据实际情况调整。默认值为 256。
            enable_thinking (bool): 是否启用思考过程。默认值为 False。
            timeout (int): 请求超时时间（秒）。默认值为 30 秒。
            extra_system_prompt (str | None): 额外的系统提示信息。用于初始化agent时构建的全局系统提示词。默认值为 None。
            rag_enable (bool): 是否启用 RAG 功能。默认值为 False。启用后会在 调用LLM回复前先进行检索增强。
        """

        self._apply_init_kwargs(
            host=host,
            port=port,
            dynamic_middlewares=dynamic_middlewares,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_completion_tokens=max_completion_tokens,
            enable_thinking=enable_thinking,
            timeout=timeout,
            extra_system_prompt=extra_system_prompt,
            rag_enable=rag_enable,
        )
        self._initialize_runtime_components()

    @staticmethod
    def _build_init_kwargs_from_config(
        config: dict[str, Any],
        dynamic_middlewares: list[AgentMiddleware] | None = None,
    ) -> dict[str, Any]:
        """从配置字典中提取 LLMAgent 初始化参数。"""
        llm_cfg = config.get("llm", {})
        return {
            "host": llm_cfg.get("host", "localhost"),
            "port": llm_cfg.get("port", 8000),
            "temperature": llm_cfg.get("temperature", 0.6),
            "top_p": llm_cfg.get("top_p", 0.95),
            "top_k": llm_cfg.get("top_k", 50),
            "max_completion_tokens": llm_cfg.get("max_completion_tokens", 256),
            "enable_thinking": llm_cfg.get("enable_thinking", False),
            "timeout": llm_cfg.get("timeout", 30),
            "extra_system_prompt": llm_cfg.get("extra_system_prompt", ""),
            "rag_enable": llm_cfg.get("rag_enable", False),
            "dynamic_middlewares": dynamic_middlewares,
        }

    def _apply_init_kwargs(
        self,
        *,
        host,
        port,
        dynamic_middlewares: list[AgentMiddleware] | None = None,
        temperature=0.6,
        top_p=0.95,
        top_k=50,
        max_completion_tokens=256,
        enable_thinking=False,
        timeout=30,
        extra_system_prompt: str | None = None,
        rag_enable=False,
    ) -> None:
        """将初始化参数写入实例状态。"""

        self.host = host
        self.port = port
        self.model_id = None
        self.model_root = None
        self.timeout = timeout

        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.max_completion_tokens = max_completion_tokens
        self.enable_thinking = enable_thinking
        self.extra_system_prompt = extra_system_prompt
        self.rag_enable = rag_enable

        self.dynamic_middlewares = dynamic_middlewares if dynamic_middlewares else []
        self.custom_middlewares = get_custom_middlewares()  # 获取自定义中间件列表
        self.custom_tools = get_custom_tools()  # 获取自定义工具列表

        self.global_system_msg = SystemMessage(
            content=build_global_system_prompt(self.extra_system_prompt)
        )

        self.thread_id = (
            uuid7()
        )  # 使用 UUID 作为无用户ID 时的 thread_id ，确保每个 LLMAgent 实例的对话上下文独立且唯一
        logger.debug(f"LLM Agent 初始化 - thread_id: {self.thread_id}")

    def _initialize_runtime_components(self) -> None:
        """初始化与运行时相关的模型、Agent 和 RAG 状态。"""

        # 初始化使用统计回调处理器，用于收集和记录模型调用的使用数据，如 token 数量、调用次数等。这些数据可以用于监控模型的使用情况和优化性能。
        ## refer from: https://docs.langchain.com/oss/python/langchain/models#token-usage
        self.callback_handlers = get_callback_handlers()

        # 初始化 ChatOpenAI 模型实例，并拉取远端模型信息，失败时回退默认模型
        self.llm_model = self._init_chat_model()
        logger.info("LLM Chat Model 初始化完成")

        # 初始化聊天代理实例，支持工具调用和上下文记忆，适用于需要多轮对话和上下文理解的场景
        self._init_agent()
        logger.info("LLM Agent 已就绪")

        # 初始化 RAG 客户端实例
        self._init_rag_client()

    # 传入配置参数初始化 Agent 实例，供外部调用，避免在外部模块中直接依赖 Agent 的创建细节
    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        dynamic_middlewares: list[AgentMiddleware] | None = None,
    ) -> "LLMAgent":
        """从配置字典创建 LLMAgent 实例。"""
        return cls(
            **cls._build_init_kwargs_from_config(
                config, dynamic_middlewares=dynamic_middlewares
            )
        )

    def reset_from_config(
        self,
        config: dict[str, Any],
        dynamic_middlewares: list[AgentMiddleware] | None = None,
    ) -> None:
        """根据配置字典重置实例状态，并重新初始化底层运行时资源。"""
        self.close()
        self._apply_init_kwargs(
            **self._build_init_kwargs_from_config(
                config, dynamic_middlewares=dynamic_middlewares
            )
        )
        self._initialize_runtime_components()

    # -------- private methods --------
    def _init_chat_model(self) -> ChatOpenAI:
        """初始化 ChatOpenAI 模型实例，并拉取远端模型信息，失败时回退默认模型。"""
        self.llm_url = f"http://{self.host}:{self.port}/v1/models"
        self._load_model_metadata()
        return self._create_chat_model(
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            max_completion_tokens=self.max_completion_tokens,
            enable_thinking=self.enable_thinking,
        )

    def _init_agent(self):
        """初始化聊天代理实例。"""
        # ---------------- 创建聊天代理 ----------------
        ## refer from:
        ## Agents: https://docs.langchain.com/oss/python/langchain/agents
        ## Short-term memory: https://docs.langchain.com/oss/python/langchain/short-term-memory

        ## 保留一个轻量代理，便于测试或无持久化场景下复用既有装配逻辑
        self.tiny_agent = self._create_agent_instance(checkpointer=InMemorySaver())

        self.db_path = DEFAULT_DB_PATH
        self.async_sqlite_saver = None
        self._async_sqlite_conn = None
        self.agent = None
        self._background_loop = None
        self._background_thread = None
        self._background_ready = threading.Event()
        self._background_lock = threading.Lock()
        self._startup_error = None
        self._start_background_runtime()

    def _start_background_runtime(self):
        """启动长期存活的后台事件循环，并在其中初始化异步 Agent。"""
        with self._background_lock:
            if (
                self._background_thread is not None
                and self._background_thread.is_alive()
            ):
                return

            self._background_ready.clear()
            self._startup_error = None
            self._background_thread = threading.Thread(
                target=self._run_background_loop,
                name="llm-agent-loop",
                daemon=True,
            )
            self._background_thread.start()

        self._background_ready.wait()
        if self._startup_error is not None:
            raise RuntimeError("后台异步 Agent 初始化失败") from self._startup_error

    def _run_background_loop(self):
        """在线程中运行长期后台事件循环。"""
        loop = asyncio.new_event_loop()
        self._background_loop = loop
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._initialize_background_runtime())
        except Exception as exc:
            self._startup_error = exc
            self._background_ready.set()
            return

        self._background_ready.set()

        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self._shutdown_background_runtime())
            finally:
                asyncio.set_event_loop(None)
                loop.close()
                self._background_loop = None

    async def _initialize_background_runtime(self):
        """在后台事件循环中初始化持久化连接和 Agent。"""
        self._async_sqlite_conn = await create_optimized_aiosqlite_connection(
            self.db_path
        )
        self.async_sqlite_saver = AsyncSqliteSaver(self._async_sqlite_conn)
        await self.async_sqlite_saver.setup()
        self.agent = self._create_agent_instance(checkpointer=self.async_sqlite_saver)

    async def _shutdown_background_runtime(self):
        """在后台事件循环中释放持久化资源。"""
        self.agent = None
        self.async_sqlite_saver = None

        async_sqlite_conn = self._async_sqlite_conn
        self._async_sqlite_conn = None
        if async_sqlite_conn is not None:
            await async_sqlite_conn.close()

    def _use_direct_agent_path(self) -> bool:
        """测试替身或手工注入 agent 时，允许不经过后台 loop 直接调用。"""
        return (
            self.agent is not None and getattr(self, "_background_loop", None) is None
        )

    def _get_background_loop(self) -> asyncio.AbstractEventLoop:
        """返回已初始化完成的后台事件循环。"""
        background_loop = self._background_loop
        if background_loop is None:
            raise RuntimeError("后台事件循环尚未初始化")
        return background_loop

    def _get_agent(self) -> Any:
        """返回已初始化完成的长期复用 Agent。"""
        agent = self.agent
        if agent is None:
            raise RuntimeError("后台 Agent 尚未初始化")
        return agent

    def _get_async_sqlite_saver(self) -> AsyncSqliteSaver:
        """返回已初始化完成的长期复用 AsyncSqliteSaver。"""
        async_sqlite_saver = self.async_sqlite_saver
        if async_sqlite_saver is None:
            raise RuntimeError("后台 AsyncSqliteSaver 尚未初始化")
        return async_sqlite_saver

    async def _run_on_background_loop(self, coro):
        """把协程提交到长期后台事件循环执行。"""
        self._start_background_runtime()
        future = asyncio.run_coroutine_threadsafe(coro, self._get_background_loop())
        return await asyncio.wrap_future(future)

    async def _ainvoke_on_background(
        self, messages: list, vision_id: str | None = None, voice_id: str | None = None
    ) -> Any:
        """在后台事件循环中执行 agent.ainvoke。"""
        return await self._get_agent().ainvoke(
            {"messages": messages},
            context=CustomContext(vision_id=vision_id, voice_id=voice_id),
            config=self._build_runtime_config(vision_id),
            stream_mode="values",
        )

    async def _astream_to_queue_on_background(
        self,
        messages: list,
        output_queue: Queue,
        vision_id: str | None = None,
        voice_id: str | None = None,
    ) -> None:
        """在后台事件循环中执行 agent.astream，并通过线程安全队列向外转发。"""
        try:
            async for chunk in (
                self._get_agent() if vision_id else self.tiny_agent
            ).astream(
                {"messages": messages},
                context=CustomContext(vision_id=vision_id, voice_id=voice_id),
                config=self._build_runtime_config(thread_id=vision_id),
                stream_mode="messages",
            ):
                output_queue.put(("chunk", chunk))
        except Exception as exc:
            output_queue.put(("error", exc))
        finally:
            output_queue.put(("done", None))

    async def _alist_checkpoints_on_background(self, config: RunnableConfig) -> list:
        """在后台事件循环中获取检查点列表。"""
        return [
            checkpoint
            async for checkpoint in self._get_async_sqlite_saver().alist(config=config)
        ]

    async def _aget_checkpoint_tuple_on_background(
        self, config: RunnableConfig
    ) -> tuple | None:
        """在后台事件循环中获取检查点元组。"""
        return await self._get_async_sqlite_saver().aget_tuple(config=config)

    def _collect_ready_stream_fragments(
        self,
        buffer: str,
        index: int,
        *,
        min_chunk_chars: int,
        max_chunk_chars: int,
        punctuation_marks: str,
    ) -> tuple[list[tuple[str, int]], str, int]:
        """从累计缓冲区中提取一个可立即输出的流式文本分片。"""
        flush_index = select_stream_flush_index(
            buffer,
            min_chunk_chars=min_chunk_chars,
            max_chunk_chars=max_chunk_chars,
            punctuation_marks=punctuation_marks,
        )
        if flush_index is None:
            return [], buffer, index

        return [(buffer[:flush_index], index)], buffer[flush_index:], index + 1

    def _append_stream_chunk(
        self,
        buffer: str,
        index: int,
        chunk: Any,
        *,
        min_chunk_chars: int,
        max_chunk_chars: int,
        punctuation_marks: str,
    ) -> tuple[list[tuple[str, int]], str, int]:
        """处理单个流式 chunk，并返回当前可输出的文本分片。"""
        ai_chunk = chunk[0] if isinstance(chunk, tuple) else chunk
        if not isinstance(ai_chunk, (AIMessageChunk, AIMessage)):
            return [], buffer, index

        chunk_text = normalize_message_content(ai_chunk.content)
        if not chunk_text:
            return [], buffer, index

        buffer += chunk_text
        fragments: list[tuple[str, int]] = []
        leading_tags, buffer = split_leading_intent_tags(buffer)
        for tag in leading_tags:
            fragments.append((tag, index))
            index += 1

        ready_fragments, buffer, index = self._collect_ready_stream_fragments(
            buffer,
            index,
            min_chunk_chars=min_chunk_chars,
            max_chunk_chars=max_chunk_chars,
            punctuation_marks=punctuation_marks,
        )
        fragments.extend(ready_fragments)
        return fragments, buffer, index

    def close(self):
        """停止后台事件循环线程并释放长期资源。"""
        background_lock = getattr(self, "_background_lock", None)
        if background_lock is None:
            return

        with background_lock:
            background_loop = getattr(self, "_background_loop", None)
            background_thread = getattr(self, "_background_thread", None)

        if background_loop is None or background_thread is None:
            return

        background_loop.call_soon_threadsafe(background_loop.stop)
        background_thread.join(timeout=5)
        self._background_thread = None

    async def aclose(self):
        """异步关闭后台事件循环线程。"""
        await asyncio.to_thread(self.close)

    def _build_runtime_config(self, thread_id: str | None = None) -> RunnableConfig:
        """构造带线程 ID 的运行时配置。"""
        return {
            "callbacks": self.callback_handlers,
            "configurable": {
                "thread_id": thread_id if thread_id else str(self.thread_id)
            },
        }

    def _init_rag_client(self):
        """初始化 RAG 客户端实例。"""
        if not self.rag_enable:
            logger.info("RAG 功能未启用")
            self.rag_client = None
            return
        try:
            from RAG.rag_api import RAGService

            self.rag_client = RAGService()
            logger.info("RAG 客户端初始化成功")
        except ImportError as e:
            logger.error(f"无法导入 RAG 模块: {e}")
            self.rag_client = None
            logger.warning("RAG 功能将不可用")

    def _load_model_metadata(self) -> None:
        """拉取远端模型信息，失败时回退默认模型。"""
        try:
            response = requests.get(self.llm_url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            first_model = data["data"][0]
            self.model_id = first_model["id"]
            self.model_root = first_model.get("root")
            logger.info(f"使用的模型ID: {self.model_id}")
            logger.info(f"模型根目录: {self.model_root}")
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            self.model_id = DEFAULT_MODEL_ID
            self.model_root = None
            # 如果模型列表接口不可用，后续调用模型时可能会失败，除非默认模型ID在本地可用。根据实际情况调整错误处理逻辑。
            ## 程序退出或抛出异常可能更合适，避免后续调用时才发现模型不可用的问题。
            raise RuntimeError("无法获取模型列表，且未设置默认模型ID") from e
            logger.warning(f"使用默认模型ID: {self.model_id}")

    def _create_chat_model(
        self,
        *,
        temperature: float,
        top_p: float,
        top_k: int,
        max_completion_tokens: int,
        enable_thinking: bool,
    ):
        """
        创建底层 ChatOpenAI 模型实例。
        refer from: https://reference.langchain.com/python/langchain-openai/chat_models/base/ChatOpenAI
        """
        return ChatOpenAI(
            model=self.model_id if self.model_id else DEFAULT_MODEL_ID,
            stream_usage=True,
            temperature=temperature,
            top_p=top_p,
            timeout=self.timeout,
            api_key=SecretStr("EMPTY"),
            base_url=f"http://{self.host}:{self.port}/v1",
            max_retries=2,
            # vLLM parameters
            ## refer from: https://docs.vllm.ai/en/v0.9.2/api/vllm/entrypoints/openai/protocol.html#vllm.entrypoints.openai.protocol.ChatCompletionRequest
            extra_body={
                "chat_template_kwargs": {"enable_thinking": enable_thinking},
                "max_completion_tokens": max_completion_tokens,
                "top_k": top_k,
            },
        )

    def _create_agent_instance(self, checkpointer=None):
        """
        统一创建 LangChain Agent，避免 tiny/full agent 的重复装配。
        - refer from:
            - Agents: https://docs.langchain.com/oss/python/langchain/agents
            - Short-term memory: https://docs.langchain.com/oss/python/langchain/short-term-memory
            - sqlite checkpointer: https://reference.langchain.com/python/langgraph.checkpoint.sqlite/SqliteSaver
            - context_schema：https://docs.langchain.com/oss/python/langchain/runtime
        """
        return create_agent(
            self.llm_model,
            tools=self.custom_tools,
            system_prompt=self.global_system_msg,
            middleware=self.custom_middlewares + self.dynamic_middlewares,
            context_schema=CustomContext,  # 获取自定义上下文类并传入 Agent
            checkpointer=checkpointer,
        )

    def __get_last_ai_content(self, state) -> str | None:
        """
        从对话状态中提取最后一条 AI 消息的内容。

        参数:
            state: 对话状态对象，包含消息列表.

        返回:
            str: 最后一条 AI 消息的内容，如果不存在则返回空字符串。
        """
        # for msg in reversed(state.get("messages", [])):
        #     if isinstance(msg, AIMessage):
        #         content = msg.content
        #         if isinstance(content, list):
        #             return " ".join(
        #                 part if isinstance(part, str) else str(part) for part in content
        #             )
        #         return content
        # return None
        latest_message = (
            state.get("messages", [])[-1] if state.get("messages") else None
        )
        if isinstance(latest_message, AIMessage):
            return normalize_message_content(latest_message.content)
        return None

    def _build_human_message(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> HumanMessage:
        """构造用户输入消息。"""
        return HumanMessage(
            content=user_text,
            additional_kwargs={
                "vision_id": vision_id,
                "voice_id": voice_id,
            },
        )

    def _build_system_message(self, prompt: str) -> SystemMessage:
        """构造系统提示消息。"""
        return SystemMessage(content=prompt)

    def _build_input_messages(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> list:
        """构造输入消息列表，包含单次RAG增强时的系统提示和用户输入。"""
        if self.rag_enable and self.rag_client is not None:
            return [
                self._build_system_message(
                    self.rag_client.query(
                        query=user_text,
                        vision_user_id=vision_id,
                        voice_user_id=voice_id,
                    ).get("prompt", "")
                ),
                self._build_human_message(
                    user_text, vision_id=vision_id, voice_id=voice_id
                ),
            ]

        return [
            self._build_human_message(
                user_text, vision_id=vision_id, voice_id=voice_id
            ),
            # self._build_system_message("you are a helpful assistant."),
        ]

    # -------- public methods for user --------

    def chat_response(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> str | None:
        """
        发送用户输入，返回完整回答文本，适合一次性获取完整回复的场景
        """
        messages = self._build_input_messages(
            user_text, vision_id=vision_id, voice_id=voice_id
        )
        logger.debug(f"构建输入消息-------------->: {[m for m in messages]}")
        result = (self._get_agent() if vision_id else self.tiny_agent).invoke(
            {"messages": messages},
            context=CustomContext(vision_id=vision_id, voice_id=voice_id),
            config=self._build_runtime_config(thread_id=vision_id),
            stream_mode="values",
        )
        logger.debug(self.callback_handlers[1].usage_metadata)  # 输出使用统计信息
        last_ai_content = self.__get_last_ai_content(result)
        return last_ai_content

    def chat_response_stream(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> Generator[tuple[str, int], Any, None]:
        """
        发送用户输入，以同步流式方式返回回答文本的分段内容，适合边说边播的场景
        """
        index = 0
        # human_msg = self._build_human_message(user_text, user_id=user_id)
        messages = self._build_input_messages(
            user_text, vision_id=vision_id, voice_id=voice_id
        )
        logger.debug(f"构建输入消息-------------->: {[m for m in messages]}")
        buffer = ""
        min_chunk_chars = 20
        max_chunk_chars = 50
        punctuation_marks = "。！？!?；;，,：:"

        for chunk in (self._get_agent() if vision_id else self.tiny_agent).stream(
            {"messages": messages},
            context=CustomContext(vision_id=vision_id, voice_id=voice_id),
            config=self._build_runtime_config(thread_id=vision_id),
            stream_mode="messages",
        ):

            fragments, buffer, index = self._append_stream_chunk(
                buffer,
                index,
                chunk,
                min_chunk_chars=min_chunk_chars,
                max_chunk_chars=max_chunk_chars,
                punctuation_marks=punctuation_marks,
            )
            for fragment in fragments:
                yield fragment

        if buffer:
            leading_tags, buffer = split_leading_intent_tags(buffer)
            for tag in leading_tags:
                yield tag, index
                index += 1

            final_text, protected_suffix = split_trailing_protected_suffix(buffer)
            if final_text:
                yield final_text, index
                index += 1

            if protected_suffix.endswith(INTENT_TAG_END):
                yield protected_suffix, index

    async def async_chat_response(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> str | None:
        """
        发送用户输入，异步返回完整回答文本
        """
        messages = self._build_input_messages(
            user_text, vision_id=vision_id, voice_id=voice_id
        )
        logger.debug(f"构建输入消息-------------->: {[m for m in messages]}")

        # if user_id:
        logger.debug(f"视觉ID: {vision_id}, 语音ID: {voice_id} - 用户输入: {user_text}")

        if self._use_direct_agent_path():
            logger.debug("直接调用 agent.ainvoke 进行对话")
            result = await self._ainvoke_on_background(messages, vision_id, voice_id)
        else:
            logger.debug("通过后台事件循环调用 agent.ainvoke 进行对话")
            result = await self._run_on_background_loop(
                self._ainvoke_on_background(messages, vision_id, voice_id)
            )
        logger.debug(self.callback_handlers[1].usage_metadata)  # 输出使用统计信息
        last_ai_content = self.__get_last_ai_content(result)
        return last_ai_content

    async def async_chat_response_stream(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> AsyncIterator[tuple[str, int]]:
        """
        发送用户输入，以异步流式方式返回回答文本的分段内容，适合边说边播的场景
        """
        index = 0
        # human_msg = self._build_human_message(user_text, user_id=user_id)
        messages = self._build_input_messages(
            user_text, vision_id=vision_id, voice_id=voice_id
        )
        logger.debug(f"构建输入消息-------------->: {[m for m in messages]}")
        buffer = ""
        min_chunk_chars = 20
        max_chunk_chars = 50
        punctuation_marks = "。！？!?；;，,：:"
        if self._use_direct_agent_path():
            logger.debug("直接调用 agent.astream 进行流式对话")
            chunk_iter = (self._get_agent() if vision_id else self.tiny_agent).astream(
                {"messages": messages},
                context=CustomContext(vision_id=vision_id, voice_id=voice_id),
                config=self._build_runtime_config(thread_id=vision_id),
                stream_mode="messages",
            )
            async for chunk in chunk_iter:
                fragments, buffer, index = self._append_stream_chunk(
                    buffer,
                    index,
                    chunk,
                    min_chunk_chars=min_chunk_chars,
                    max_chunk_chars=max_chunk_chars,
                    punctuation_marks=punctuation_marks,
                )
                for fragment in fragments:
                    yield fragment
        else:
            logger.debug("通过后台事件循环调用 agent.astream 进行流式对话")
            self._start_background_runtime()
            output_queue: Queue = Queue()
            background_task = asyncio.run_coroutine_threadsafe(
                self._astream_to_queue_on_background(
                    messages, output_queue, vision_id=vision_id, voice_id=voice_id
                ),
                self._get_background_loop(),
            )

            while True:
                event_type, payload = await asyncio.to_thread(output_queue.get)
                if event_type == "done":
                    break
                if event_type == "error":
                    await asyncio.wrap_future(background_task)
                    raise payload

                chunk = payload
                fragments, buffer, index = self._append_stream_chunk(
                    buffer,
                    index,
                    chunk,
                    min_chunk_chars=min_chunk_chars,
                    max_chunk_chars=max_chunk_chars,
                    punctuation_marks=punctuation_marks,
                )
                for fragment in fragments:
                    yield fragment

            await asyncio.wrap_future(background_task)
        if buffer:
            leading_tags, buffer = split_leading_intent_tags(buffer)
            for tag in leading_tags:
                yield tag, index
                index += 1

            final_text, protected_suffix = split_trailing_protected_suffix(buffer)
            if final_text:
                yield final_text, index
                index += 1

            if protected_suffix.endswith(INTENT_TAG_END):
                yield protected_suffix, index

    # list checkpoints
    async def list_checkpoints(self, thread_id: str | None = None) -> list:
        """根据线程ID列出对应的对话检查点列表。 如果线程ID未提供，则使用默认线程ID列出检查点。"""
        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id if thread_id else str(self.thread_id)
            }
        }
        if self._use_direct_agent_path() and self.async_sqlite_saver is not None:
            return [
                checkpoint
                async for checkpoint in self.async_sqlite_saver.alist(config=config)
            ]
        return await self._run_on_background_loop(
            self._alist_checkpoints_on_background(config)
        )

    # get_tuple
    async def get_checkpoint_tuple(self, thread_id: str | None = None) -> tuple | None:
        """根据线程ID获取对应的对话检查点数据元组。 如果线程ID未提供，则使用默认线程ID获取检查点。"""
        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id if thread_id else str(self.thread_id)
            }
        }
        if self._use_direct_agent_path() and self.async_sqlite_saver is not None:
            return await self.async_sqlite_saver.aget_tuple(config=config)
        return await self._run_on_background_loop(
            self._aget_checkpoint_tuple_on_background(config)
        )

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


async def _main():

    from config import load_config, reload_config

    configs = load_config()

    # llm_agent = LLMAgent(host="192.168.50.125", port=8000)
    llm_agent = LLMAgent.from_config(configs)

    vision_id = input("请输入视觉ID（可选，直接回车跳过）: ").strip() or None
    voice_id = input("请输入语音ID（可选，直接回车跳过）: ").strip() or None

    while True:
        user_input = input(
            'User<"quit or exit" to exit, "reset" to reset agent>: '
        ).strip()
        if user_input.lower() in ["exit", "quit"]:
            break
        if user_input.lower() == "reset":
            configs = reload_config()
            llm_agent.reset_from_config(configs)
            print("Agent 已重置，您可以继续输入对话。")
            continue
        # # 异步获取完整回复文本
        # response = await llm_agent.async_chat_response(
        #     user_input, vision_id=vision_id, voice_id=voice_id
        # )

        # # 同步获取完整回复文本
        # response = llm_agent.chat_response(
        #     user_input, vision_id=vision_id, voice_id=voice_id
        # )
        # print("AI:", response)

        # 同步流式获取回复文本分片
        print("AI:", end=" ", flush=True)
        for chunk, _ in llm_agent.chat_response_stream(
            user_input, vision_id=vision_id, voice_id=voice_id
        ):
            print(chunk, end=" ", flush=True)
        print()  # 换行

        # checkpoints = await llm_agent.get_checkpoint_tuple(thread_id=vision_id)

        # config
        # checkpoints[0] if checkpoints else None

        # checkpoint
        # checkpoints[1] if checkpoints else None

        # metadata
        # checkpoints[2] if checkpoints else None

        # parent_config
        # checkpoints[3] if checkpoints else None

        # pending_writes
        # checkpoints[4] if checkpoints else None

        # for checkpoint in checkpoints or []:
        #     print(checkpoint)

        # for message in (
        #     checkpoints[1].get("channel_values").get("messages") if checkpoints else []
        # ):
        #     print(f"{message.type}: {message.content}")


if __name__ == "__main__":
    asyncio.run(_main())
