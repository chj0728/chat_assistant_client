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

import sqlite3
from pathlib import Path
from typing import Any, Generator

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

# from langgraph.store.sqlite import SqliteStore
# from uuid import uuid7
# from langsmith import uuid7_from_datetime
from langchain_core.utils.uuid import uuid7
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
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
    "你需要简洁且有礼貌地回答用户的问题，请保持回答简短且有条理，控制在100字以内。\n"
    "在回答中尽量避免使用标点符号结尾，以便更自然地进行语音合成。\n"
    "如果你不确定答案，可以礼貌地告诉用户你不知道。\n"
    "只有当用户回答退出、结束等相关内容时，调用结束对话的工具函数，礼貌地结束对话。"
)
INTENT_TAG_START = "<INTENT>"
INTENT_TAG_END = "</INTENT>"


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


def select_stream_flush_index(
    buffer: str,
    *,
    min_chunk_chars: int,
    max_chunk_chars: int,
    punctuation_marks: str,
) -> int | None:
    """选择流式文本的切分位置，并避免切入尾部未闭合的 INTENT 标签。"""
    if len(buffer) < min_chunk_chars:
        return None

    flush_index = None
    last_punctuation = max(
        (buffer.rfind(mark) for mark in punctuation_marks), default=-1
    )
    if last_punctuation >= min_chunk_chars:
        flush_index = last_punctuation + 1
    elif len(buffer) >= max_chunk_chars:
        flush_index = max_chunk_chars

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
        llm_cfg = config.get("llm", {})
        return cls(
            host=llm_cfg.get("host", "localhost"),
            port=llm_cfg.get("port", 8000),
            temperature=llm_cfg.get("temperature", 0.6),
            top_p=llm_cfg.get("top_p", 0.95),
            top_k=llm_cfg.get("top_k", 50),
            max_completion_tokens=llm_cfg.get("max_completion_tokens", 256),
            enable_thinking=llm_cfg.get("enable_thinking", False),
            extra_system_prompt=llm_cfg.get("extra_system_prompt", ""),
            rag_enable=llm_cfg.get("rag_enable", False),
            dynamic_middlewares=dynamic_middlewares,
        )

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

        ## 创建一个使用内存检查点的简易代理，适用于不需要持久化对话历史的场景，如单轮问答或测试环境
        self.tiny_agent = self._create_agent_instance(checkpointer=InMemorySaver())

        ## 创建一个完整版本的代理，支持工具调用和上下文记忆，适用于需要多轮对话和上下文理解的场景
        ## 使用 sqlite 检查点保存对话状态，确保在多用户场景下能够持久化和管理每个用户的对话历史
        ## |--->refer from: https://reference.langchain.com/python/langgraph.checkpoint.sqlite/SqliteSaver
        self.db_path = DEFAULT_DB_PATH
        with create_optimized_sqlite_connection(self.db_path) as conn:
            # 创建一个 SqliteSaver 实例
            sqlite_saver = SqliteSaver(conn)
            self.agent = self._create_agent_instance(checkpointer=sqlite_saver)

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
            logger.warning(f"使用默认模型ID: {self.model_id}")

    def _create_chat_model(
        self,
        *,
        temperature: float,
        top_p: float,
        top_k: int,
        max_completion_tokens: int,
        enable_thinking: bool,
    ) -> ChatOpenAI:
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
        self, user_text: str, user_id: str | None = None
    ) -> HumanMessage:
        """构造用户输入消息。"""
        return HumanMessage(
            content=user_text,
            additional_kwargs={
                "user_id": user_id,
            },
        )

    def _build_system_message(self, prompt: str) -> SystemMessage:
        """构造系统提示消息。"""
        return SystemMessage(content=prompt)

    def _build_input_messages(self, user_text: str, user_id: str | None = None) -> list:
        """构造输入消息列表，包含单次RAG增强时的系统提示和用户输入。"""
        if self.rag_enable and self.rag_client is not None:
            return [
                self._build_system_message(
                    self.rag_client.query(user_text).get("prompt", "")
                ),
                self._build_human_message(user_text, user_id=user_id),
            ]

        return [
            self._build_human_message(user_text, user_id=user_id),
            # self._build_system_message("you are a helpful assistant."),
        ]

    # -------- public methods for user --------

    def chat_response(self, user_text: str, user_id: str | None = None) -> str | None:
        """
        发送用户输入，返回完整回答文本
        """
        # human_msg = self._build_human_message(user_text, user_id=user_id)

        # system_msg = SystemMessage("You are a helpful assistant.")
        # messages = [
        #     system_msg,
        #     human_msg,
        # ]

        messages = self._build_input_messages(user_text, user_id=user_id)
        logger.debug(f"构建输入消息-------------->: {[m for m in messages]}")

        # if user_id:
        logger.debug(f"用户ID: {user_id} - 用户输入: {user_text}")

        result = self.agent.invoke(
            {"messages": messages},
            context=CustomContext(user_id=user_id),
            ## 这里的 thread_id 是为了让 agent 能够区分不同用户的对话上下文，确保每个用户的对话历史独立存储和管理
            ## 具体实现上，agent 会使用 thread_id 来索引和检索对应用户的对话历史，从而在多用户场景下正确地维护每个用户的上下文信息
            ## thread_id 的具体命名和使用方式可以根据实际需求进行调整，关键是要确保它能够唯一标识每个用户的对话线程
            ## refer from:
            ## 1. https://docs.langchain.com/langsmith/observability-concepts#threads
            ## 2. https://docs.langchain.com/langsmith/threads#group-traces-into-threads
            # {"configurable": {"thread_id": user_id}},
            config={
                "callbacks": self.callback_handlers,
                "configurable": {
                    "thread_id": user_id if user_id else str(self.thread_id)
                },  # 使用用户ID作为线程ID，如果未提供用户ID，则使用默认线程ID
            },
            stream_mode="values",
        )
        logger.debug(self.callback_handlers[1].usage_metadata)  # 输出使用统计信息
        last_ai_content = self.__get_last_ai_content(result)
        return last_ai_content

    def chat_response_stream(
        self, user_text: str, user_id: str | None = None
    ) -> Generator[tuple[str, int], Any, None]:
        """
        发送用户输入，以流式方式返回回答文本的分段内容，适合边说边播的场景
        """
        index = 0
        # human_msg = self._build_human_message(user_text, user_id=user_id)
        messages = self._build_input_messages(user_text, user_id=user_id)
        logger.debug(f"构建输入消息-------------->: {[m for m in messages]}")
        buffer = ""
        min_chunk_chars = 20
        max_chunk_chars = 50
        punctuation_marks = "。！？!?；;，,：:"
        for chunk in self.agent.stream(
            {"messages": messages},
            context=CustomContext(user_id=user_id),
            # {"configurable": {"thread_id": user_id}},
            config={
                "callbacks": self.callback_handlers,
                "configurable": {
                    "thread_id": (user_id if user_id else str(self.thread_id))
                },
            },
            stream_mode="messages",
        ):
            ai_chunk = chunk[0] if isinstance(chunk, tuple) else chunk
            if not isinstance(ai_chunk, AIMessageChunk):
                continue

            chunk_text = normalize_message_content(ai_chunk.content)

            if not chunk_text:
                continue

            buffer += chunk_text

            while buffer:
                flush_index = select_stream_flush_index(
                    buffer,
                    min_chunk_chars=min_chunk_chars,
                    max_chunk_chars=max_chunk_chars,
                    punctuation_marks=punctuation_marks,
                )
                if flush_index is None:
                    break

                yield buffer[:flush_index], index
                buffer = buffer[flush_index:]
                index += 1

        if buffer:
            yield buffer, index


if __name__ == "__main__":
    llm_agent = LLMAgent(host="192.168.50.125", port=8000)

    # llm_agent.add_system_prompt("你叫小白，是一个智能助理。")

    user_id = input("请输入用户ID（可选，直接回车跳过）: ").strip() or None

    while True:
        user_input = input("User: ").strip()
        if user_input.lower() in ["exit", "quit"]:
            break
        response = llm_agent.chat_response(user_input, user_id=user_id)

        print("AI:", response)

        # for response_chunk, index in llm_agent.chat_response_stream(user_input, user_id=user_id):
        #     print("AI:", response_chunk, end="\n", flush=False)
        # print()
