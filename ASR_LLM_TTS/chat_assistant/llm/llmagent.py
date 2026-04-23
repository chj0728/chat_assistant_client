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
from typing import Any

import requests
from config import load_config
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    before_model,
)
from langchain.messages import RemoveMessage
from langchain.tools import tool
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    trim_messages,
)

# from langchain_core.messages.utils import count_tokens_approximately
from langchain_openai import ChatOpenAI

# from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime
from logger import logger
from pydantic import SecretStr
from tools.functions import get_current_location, get_shanghai_time, get_weather_info

DEFAULT_MAX_MESSAGES = 5
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


def get_max_messages(default: int = DEFAULT_MAX_MESSAGES) -> int:
    """从配置中读取最大历史消息数，读取失败时回退默认值。"""
    config = load_config()
    max_messages = config.get("llm", {}).get("max_messages", default)
    logger.debug(f"LLM Agent 配置 - MAX_MESSAGES: {max_messages}")
    return max_messages


def build_system_prompt(extra_prompt: str | None = None) -> str:
    """构造系统提示词。"""
    if extra_prompt:
        return f"{DEFAULT_SYSTEM_PROMPT}\n{extra_prompt}\n"
    return DEFAULT_SYSTEM_PROMPT + "\n"


def get_default_tools() -> list:
    """返回默认启用的工具列表。"""
    return [
        get_current_time_tool,
        get_current_location_tool,
        get_weather_info_tool,
    ]


def normalize_message_content(content: Any) -> str:
    """将 LangChain 消息内容统一转换为字符串。"""
    if isinstance(content, list):
        return "".join(part if isinstance(part, str) else str(part) for part in content)
    if content is None:
        return ""
    return str(content)


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
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;          -- 写前日志模式，提高并发性能
        PRAGMA synchronous=NORMAL;        -- 平衡性能和数据安全
        PRAGMA cache_size=-2000;          -- 设置2MB缓存
        PRAGMA temp_store=MEMORY;         -- 临时表存储在内存中
        PRAGMA mmap_size=268435456;       -- 256MB内存映射
        PRAGMA busy_timeout=5000;         -- 5秒忙超时
        """
    )
    return conn


# @tool(description="当用户询问当前时间时，获取上海当前时间的工具函数")
@tool
def get_current_time_tool() -> str:
    """获取上海当前时间的工具函数"""
    logger.debug("调用工具函数->获取当前时间。")
    return get_shanghai_time()


# @tool(description="当用户询问当前位置信息时，获取当前位置信息的工具函数")
@tool
def get_current_location_tool() -> str:
    """获取当前位置信息的工具函数"""
    logger.debug("调用工具函数->获取当前位置信息。")
    return get_current_location()


# @tool(description="当用户询问天气信息时，获取天气信息的工具函数")
@tool
def get_weather_info_tool() -> str:
    """获取天气信息的工具函数"""
    logger.debug("调用工具函数->获取天气信息。")
    return get_weather_info()


@before_model
def trim_messages_before_model(
    state: AgentState, runtime: Runtime
) -> dict[str, Any] | None:
    """Keep only the last few messages to fit context window.
    official docs: https://docs.langchain.com/oss/python/langchain/short-term-memory#trim-messages
    """

    messages = state["messages"]

    logger.debug(
        f"\n=======> Before LLM Static Middleware:\n Current messages: {[m for m in messages]}"
    )

    # refer from: https://juejin.cn/post/7534535266226192430
    ## 使用 token 数量限制的方式来控制对话历史长度
    # trimmed = trim_messages(
    #     messages,
    #     max_tokens=100,  # 保留消息的最大token数量，超过时会删除最旧的消息，直到总token数在限制内
    #     strategy="last",  # 保留最近的消息，删除最旧的消息
    #     token_counter=count_tokens_approximately,  # 计算消息token数量的函数
    #     # Most chat models expect that chat history starts with either:
    #     # (1) a HumanMessage or
    #     # (2) a SystemMessage followed by a HumanMessage
    #     start_on="human",
    #     # Usually, we want to keep the SystemMessage
    #     # if it's present in the original history.
    #     # The SystemMessage has special instructions for the model.
    #     include_system=True,
    #     allow_partial=False,
    # )

    ## 使用消息数量限制的方式来控制对话历史长度
    trimmed = trim_messages(
        messages,
        # When `len` is passed in as the token counter function,
        # max_tokens will count the number of messages in the chat history.
        max_tokens=get_max_messages(),
        strategy="last",
        # Passing in `len` as a token counter function will
        # count the number of messages in the chat history.
        token_counter=len,
        # Most chat models expect that chat history starts with either:
        # (1) a HumanMessage or
        # (2) a SystemMessage followed by a HumanMessage
        start_on="human",
        # Usually, we want to keep the SystemMessage
        # if it's present in the original history.
        # The SystemMessage has special instructions for the model.
        include_system=True,
        allow_partial=False,
    )

    logger.debug(f"\nTrimmed messages: {[m for m in trimmed]}")

    # return {"messages": trimmed}
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *trimmed]}


class LLMAgent:
    """
    LLMAgent 类用于创建和管理基于大型语言模型（LLM）的聊天代理。
    基于 LangChain 框架，支持系统消息配置和从对话状态中提取 AI 消息内容的实用函数。
    """

    def __init__(
        self,
        host,
        port,
        dynamic_middleware_list: list[AgentMiddleware] | None = None,
        # dynamic_tool_middlewares: AgentMiddleware | None = None,
        temperature=0.6,
        top_p=0.95,
        top_k=50,
        max_tokens=256,
        enable_thinking=False,
        timeout=30,
        system_prompt: str | None = None,
    ):
        """
        初始化 LLMAgent 实例。

        参数:
            host (str): LLM 服务的主机地址。
            port (int): LLM 服务的端口号。
            dynamic_middleware_list (list[AgentMiddleware] | None): 可选的动态中间件列表。 默认值为 None。
            temperature (float): 控制生成文本的随机性。默认值为 0.6。
            top_p (float): 用于 nucleus 采样的概率阈值。默认值为 0.95。
            top_k (int): 用于 top-k 采样的词汇数量。默认值为 50。
            max_tokens (int): 生成文本的最大 token 数量。默认值为 256。
            enable_thinking (bool): 是否启用思考过程。默认值为 False。
            timeout (int): 请求超时时间（秒）。默认值为 30 秒。
            system_prompt (str | None): 系统提示信息。默认值为 None。
        """

        self.host = host
        self.port = port
        self.model_id = None
        self.model_root = None
        self.timeout = timeout
        self.static_middleware_list = [trim_messages_before_model]
        self.dynamic_middleware_list = (
            dynamic_middleware_list if dynamic_middleware_list else []
        )
        self.tools = get_default_tools()
        self.system_msg = SystemMessage(content=build_system_prompt(system_prompt))
        self.db_path = DEFAULT_DB_PATH

        self.llm_url = f"http://{self.host}:{self.port}/v1/models"
        self._load_model_metadata()

        self.llm_model = self._create_chat_model(
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
        )
        logger.info("LLM 模型初始化完成")

        # 创建聊天代理
        ## refer from:
        ## Agents: https://docs.langchain.com/oss/python/langchain/agents
        ## Short-term memory: https://docs.langchain.com/oss/python/langchain/short-term-memory

        ## 创建一个不使用检查点的简化版本的代理，用于快速响应不需要上下文记忆的请求
        self.tiny_agent = self._create_agent_instance()

        ## 创建一个完整版本的代理，支持工具调用和上下文记忆，适用于需要多轮对话和上下文理解的场景
        ## 使用 sqlite 检查点保存对话状态，确保在多用户场景下能够持久化和管理每个用户的对话历史
        ## |--->refer from: https://reference.langchain.com/python/langgraph.checkpoint.sqlite/SqliteSaver
        with create_optimized_sqlite_connection(self.db_path) as conn:
            # 创建一个 SqliteSaver 实例
            sqlite_saver = SqliteSaver(conn)
            self.agent = self._create_agent_instance(checkpointer=sqlite_saver)
        logger.info("LLM Agent 已就绪")

    # -------- private methods --------
    def _load_model_metadata(self) -> None:
        """探测远端模型信息，失败时回退默认模型。"""
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
        max_tokens: int,
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
                "max_completion_tokens": max_tokens,
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
        """
        return create_agent(
            self.llm_model,
            tools=self.tools,
            system_prompt=self.system_msg,
            checkpointer=checkpointer,
            middleware=self.static_middleware_list + self.dynamic_middleware_list,
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

    # -------- public methods for user --------

    def add_system_prompt(self, prompt: str):
        """
        追加系统提示内容。

        参数:
            prompt (str): 系统提示内容。
        """
        self.system_msg.content = build_system_prompt(prompt).rstrip("\n")

    def chat_response(self, user_text: str, user_id: str | None = None) -> str | None:
        """
        发送用户输入，返回完整回答文本
        """
        human_msg = self._build_human_message(user_text, user_id=user_id)

        if user_id:
            logger.debug(f"用户ID: {user_id} - 用户输入: {user_text}")
            # system_msg = SystemMessage("You are a helpful assistant.")
            # messages = [
            #     system_msg,
            #     human_msg,
            # ]

            result = self.agent.invoke(
                {"messages": [human_msg]},
                ## 这里的 thread_id 是为了让 agent 能够区分不同用户的对话上下文，确保每个用户的对话历史独立存储和管理
                ## 具体实现上，agent 会使用 thread_id 来索引和检索对应用户的对话历史，从而在多用户场景下正确地维护每个用户的上下文信息
                ## thread_id 的具体命名和使用方式可以根据实际需求进行调整，关键是要确保它能够唯一标识每个用户的对话线程
                ## refer from:
                ## 1. https://docs.langchain.com/langsmith/observability-concepts#threads
                ## 2. https://docs.langchain.com/langsmith/threads#group-traces-into-threads
                {"configurable": {"thread_id": user_id}},
                stream_mode="values",
            )
            last_ai_content = self.__get_last_ai_content(result)
            return last_ai_content
        else:
            logger.debug(f"用户ID未提供 - 用户输入: {user_text}")

            # conversation = [
            #     # {
            #     #     "role": "system",
            #     #     "content": self.system_msg.content,
            #     # },
            #     {"role": "user", "content": user_text},
            # ]
            # result = self.llm_model.invoke(conversation)

            result = self.tiny_agent.invoke(
                # {
                #     "messages": [
                #         {
                #             "role": "user",
                #             "content": user_text,
                #         }
                #     ]
                # }
                {"messages": [human_msg]}
            )
            last_ai_content = self.__get_last_ai_content(result)
            return last_ai_content

    def chat_response_stream(self, user_text: str, user_id: str | None = None):
        """
        发送用户输入，以流式方式返回回答文本的分段内容，适合边说边播的场景
        """
        index = 0
        human_msg = self._build_human_message(user_text, user_id=user_id)
        buffer = ""
        min_chunk_chars = 20
        max_chunk_chars = 50
        punctuation_marks = "。！？!?；;，,：:"
        for chunk in (
            self.agent.stream(
                {"messages": [human_msg]},
                {"configurable": {"thread_id": user_id}},
                stream_mode="messages",
            )
            if user_id
            else self.tiny_agent.stream(
                {"messages": [human_msg]},
                stream_mode="messages",
            )
        ):
            ai_chunk = chunk[0] if isinstance(chunk, tuple) else chunk
            if not isinstance(ai_chunk, AIMessageChunk):
                continue

            chunk_text = normalize_message_content(ai_chunk.content)

            if not chunk_text:
                continue

            buffer += chunk_text

            while buffer:
                flush_index = None
                if len(buffer) >= min_chunk_chars:
                    # Look for punctuation only starting from min_chunk_chars to ensure chunk has enough text
                    last_punctuation = max(
                        (buffer.rfind(mark) for mark in punctuation_marks), default=-1
                    )

                    if last_punctuation >= min_chunk_chars:
                        flush_index = last_punctuation + 1
                    elif len(buffer) >= max_chunk_chars:
                        flush_index = max_chunk_chars

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
