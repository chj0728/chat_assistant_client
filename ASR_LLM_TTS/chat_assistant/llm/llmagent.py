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
import os
import re
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Any, AsyncIterator, Generator

import requests
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
)
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
# from langchain_core.utils.uuid import uuid7
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from logger import logger
from pydantic import SecretStr

from llm.custom_callback_handlers import get_callback_handlers
from llm.custom_context import CustomContext
from llm.custom_db import (
    create_optimized_aiosqlite_connection,
)
from llm.custom_middlewares import get_custom_middlewares
from llm.custom_text_preprocessor import (
    normalize_message_content,
    select_stream_flush_index,
    split_leading_intent_tags,
    split_trailing_protected_suffix,
)
from llm.custom_tools import get_custom_tools

# ------------------------ 全局常量 ------------------------
load_dotenv()


def GET_API_TOKEN_FROM_ENV():
    """从环境变量获取 API_TOKEN，并进行基本验证。"""
    return os.getenv("API_TOKEN", "").strip()


def GET_API_ENDPOINT_FROM_ENV():
    """从环境变量获取 API_ENDPOINT，并进行基本验证。"""
    return os.getenv("API_ENDPOINT", "").strip()


DEFAULT_MODEL_ID = "qwen3.7-max"
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
STREAM_MIN_CHARS = 20
STREAM_MAX_CHARS = 50
STREAM_PUNCTUATION_MARKS = "。！？!?；;，,：:"
# ---------------------------------------------------------


def build_global_system_prompt(extra_prompt: str | None = None) -> str:
    """构造系统提示词。"""
    if extra_prompt:
        return f"{DEFAULT_SYSTEM_PROMPT}\n{extra_prompt}\n"
    return DEFAULT_SYSTEM_PROMPT + "\n"


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
        enable_rag=False,
        enable_cloud=False,
        enable_health_check=True,
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
            enable_rag (bool): 是否启用 RAG 功能。默认值为 False。启用后会在 调用LLM回复前先进行检索增强。
            enable_cloud (bool): 是否启用云端 LLM 服务，启用后会使用云端 API 进行推理，确保.env 中的 EAS_TOKEN 和 EAS_ENDPOINT 已正确配置。默认值为 False。
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
            enable_rag=enable_rag,
            enable_cloud=enable_cloud,
            enable_health_check=enable_health_check,
        )
        self._initialize_runtime_components()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

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
            "timeout": llm_cfg.get("timeout_sec", 30),
            "extra_system_prompt": llm_cfg.get("extra_system_prompt", ""),
            "enable_rag": llm_cfg.get("enable_rag", False),
            "dynamic_middlewares": dynamic_middlewares,
            "enable_cloud": llm_cfg.get("enable_cloud", False),
            "enable_health_check": llm_cfg.get("enable_health_check", True),
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
        enable_rag=False,
        enable_cloud=False,
        enable_health_check=True,
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
        self.enable_rag = enable_rag
        self.enable_cloud = enable_cloud
        self.enable_health_check = enable_health_check
        self.health_check_active = False
        self.health_check_thread = None
        self.interrupt_event = threading.Event()

        self.dynamic_middlewares = dynamic_middlewares if dynamic_middlewares else []
        self.custom_middlewares = get_custom_middlewares()  # 获取自定义中间件列表
        self.custom_tools = get_custom_tools()  # 获取自定义工具列表

        self.global_system_msg = SystemMessage(
            content=build_global_system_prompt(self.extra_system_prompt)
        )

        # self.thread_id = uuid7()  # 使用 UUID 作为无用户ID 时的 thread_id
        self.thread_id = "default_memory_checkpointer"
        logger.debug(f"LLM Agent 初始化 - thread_id: {self.thread_id}")

    def _initialize_runtime_components(self) -> None:
        """初始化与运行时相关的模型、Agent 和 RAG 状态。"""

        # 初始化api_key, base_url等模型参数
        self._init_api_key_and_base_url()

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

        # 启动后台循环监听线程 ，GET self.base_url/health
        if self.enable_health_check:
            self.health_check_active = True
            logger.info("启用 LLM 健康检查功能")
            self._start_health_check_loop()

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        dynamic_middlewares: list[AgentMiddleware] | None = None,
    ) -> "LLMAgent":
        """从配置字典创建 LLMAgent 实例，供外部调用，避免在外部模块中直接依赖 Agent 的创建细节。"""
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

    ########################################################
    # 模型和代理初始化相关的私有方法，
    # 包含模型信息拉取、模型实例创建、Agent 创建，以及后台事件循环管理等功能。

    def _init_api_key_and_base_url(self):
        """根据是否启用云端 LLM 服务，初始化 API 密钥和基础 URL。"""
        if self.enable_cloud:
            # 从环境变量获取云端 LLM 服务的 API 密钥和基础 URL，确保在 .env 文件中正确配置 API_TOKEN 和 API_ENDPOINT
            self.api_key = SecretStr(GET_API_TOKEN_FROM_ENV())
            self.endpoint = GET_API_ENDPOINT_FROM_ENV()
            self.base_url = self.endpoint + "/v1"
            logger.info("已启用云端 LLM 服务")
        else:
            self.api_key = SecretStr("EMPTY")  # 本地部署的模型不需要 API 密钥
            self.endpoint = f"http://{self.host}:{self.port}"
            self.base_url = self.endpoint + "/v1"
            logger.info("使用本地部署的 LLM 服务")

    def _init_chat_model(self) -> ChatOpenAI:
        """初始化 ChatOpenAI 模型实例，并拉取远端模型信息，失败时回退默认模型。"""
        self.llm_url = self.base_url + "/models"

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

        ## 创建一个使用内存检查点的代理实例，适用于需要持久化对话上下文的场景
        self.in_memory_checkpointer = InMemorySaver()
        self.tiny_agent = self._create_agent_instance(
            checkpointer=self.in_memory_checkpointer
        )

        ## 创建单次响应代理实例，用于处理无需持久化的单次对话
        self.single_response_agent = self._create_agent_instance(checkpointer=None)

        ## 创建持久化代理实例，适用于需要将对话上下文存储到数据库的场景
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

    def _init_rag_client(self):
        """初始化 RAG 客户端实例。"""
        if not self.enable_rag:
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

    def _build_cloud_auth_headers(self) -> dict[str, str] | None:
        """构造云端 API 请求的 Authorization 头。"""
        if not self.enable_cloud:
            return None
        token = self.api_key.get_secret_value()
        if not token:
            return None
        return {"Authorization": f"Bearer {token}"}

    def _load_model_metadata(self) -> None:
        """拉取远端模型信息，失败时回退默认模型。"""
        if self.enable_cloud:
            self.model_id = DEFAULT_MODEL_ID
            self.model_root = None
            logger.info(f"云端 LLM 使用默认模型ID: {self.model_id}")
            return

        try:
            response = requests.get(
                self.llm_url,
                timeout=self.timeout,
                headers=self._build_cloud_auth_headers(),
            )
            response.raise_for_status()
            data = response.json()
            model_list = data.get("data", []) if isinstance(data, dict) else []
            if not model_list:
                raise ValueError("模型列表为空或返回结构不符合预期")

            first_model = model_list[0]
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
            # raise RuntimeError("无法获取模型列表，且未设置默认模型ID") from e
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
            api_key=self.api_key,
            base_url=self.base_url,
            max_retries=2,
            # 查看日志专用
            # callbacks=self.callback_handlers,
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
            system_prompt=None,  # self.global_system_msg,
            middleware=self.custom_middlewares + self.dynamic_middlewares,
            context_schema=CustomContext,  # 获取自定义上下文类并传入 Agent
            checkpointer=checkpointer,
        )

    def _start_health_check_loop(self):
        """启动一个后台线程，定期检查 LLM 服务的健康状态。"""
        health_check_url = (
            self.llm_url if self.enable_cloud else self.endpoint + "/health"
        )

        def health_check_loop():
            headers = self._build_cloud_auth_headers()

            while self.health_check_active:
                try:
                    response = requests.get(
                        health_check_url, headers=headers, timeout=self.timeout
                    )
                    if response.status_code == 200:
                        logger.debug("LLM 服务健康检查成功")
                    else:
                        logger.warning(
                            f"LLM 服务健康检查失败，状态码: {response.status_code}"
                        )
                except Exception as e:
                    logger.error(f"LLM 服务健康检查异常: {e}")
                time.sleep(5)  # 每5秒检查一次

        self.health_check_thread = threading.Thread(
            target=health_check_loop, name="llm-health-check", daemon=True
        )
        self.health_check_thread.start()

    ########################################################

    ################# 后台事件循环中 Agent 调用的辅助方法 #################
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
                if self.interrupt_event.is_set():
                    logger.info("LLM 后台流式输出已中断")
                    return
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

    async def _cancel_background_task(self, background_task) -> None:
        """取消后台流式任务，并消费取消异常，避免留下未处理的 future 状态。"""
        background_task.cancel()
        try:
            await asyncio.wrap_future(background_task)
        except asyncio.CancelledError:
            pass

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

        self.health_check_active = False
        if self.health_check_thread is not None:
            self.health_check_thread.join(timeout=5)
            self.health_check_thread = None

        logger.info("LLM Agent已停止")

    def stop(self):
        self.close()

    def interrupt(self):
        """中断当前 LLM 流式输出。"""
        self.interrupt_event.set()

    async def aclose(self):
        """异步关闭后台事件循环线程。"""
        await asyncio.to_thread(self.close)

    ################################################################

    ########################## 对话状态预处理相关的私有方法 ##########################
    def _get_last_ai_content(self, state) -> str | None:
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

    def _build_runtime_config(self, thread_id: str | None = None) -> RunnableConfig:
        """构造带线程 ID 的运行时配置。"""
        return {
            "callbacks": self.callback_handlers,
            "configurable": {
                "thread_id": thread_id if thread_id else str(self.thread_id)
            },
        }

    def _build_human_message(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> HumanMessage:
        """构造用户输入消息。"""
        return HumanMessage(
            content=user_text,
            additional_kwargs={
                "format_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
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
        """构造输入用户输入消息列表"""
        # if self.enable_rag and self.rag_client is not None:
        #     return [
        #         self._build_system_message(
        #             self.rag_client.query(
        #                 query=user_text,
        #                 vision_user_id=vision_id,
        #                 voice_user_id=voice_id,
        #             ).get("prompt", "")
        #         ),
        #         self._build_human_message(
        #             user_text, vision_id=vision_id, voice_id=voice_id
        #         ),
        #     ]

        return [
            self._build_human_message(user_text, vision_id=vision_id, voice_id=voice_id)
        ]

    def _build_rag_prompt(
        self,
        user_text: str,
        rag_id: str | None = None,
        voice_id: str | None = None,
        is_active_ask: bool = False,
    ) -> str:
        """构造 RAG 增强提示词。"""
        if self.enable_rag and self.rag_client is not None:

            res = self.rag_client.query(
                query=user_text,
                vision_user_id=rag_id,
                voice_user_id=voice_id,
                is_active_ask=is_active_ask,
            )

            self.rag_prompt = res.get("prompt", "")
            logger.debug(f"RAG 增强提示词: {self.rag_prompt}")

            self.query_to_resolve: bool = res.get("second", False)
            logger.debug(f"Query to resolve name: {self.query_to_resolve}")

            return self.rag_prompt
        return ""

    def _build_runtime_context(
        self,
        user_text: str,
        vision_id: str | None = None,
        voice_id: str | None = None,
        rag_id: str | None = None,
        is_active_ask: bool = False,
    ) -> CustomContext:
        """构建运行时上下文。"""

        rag_prompt = self._build_rag_prompt(
            user_text,
            rag_id=rag_id,
            voice_id=voice_id,
            is_active_ask=is_active_ask,
        )
        if rag_prompt:
            return CustomContext(
                vision_id=vision_id, voice_id=voice_id, rag_prompt=rag_prompt
            )
        return CustomContext(vision_id=vision_id, voice_id=voice_id)

    def _prepare_request(
        self,
        user_text: str,
        vision_id: str | None = None,
        voice_id: str | None = None,
        rag_id: str | None = None,
        is_active_ask: bool = False,
    ) -> tuple[list, CustomContext, RunnableConfig]:
        """统一构造消息、上下文和运行时配置。"""

        messages = self._build_input_messages(
            user_text=user_text, vision_id=vision_id, voice_id=voice_id
        )
        logger.debug(f"构建输入消息-------------->: {[m for m in messages]}")

        custom_context = self._build_runtime_context(
            user_text=user_text,
            vision_id=vision_id,
            voice_id=voice_id,
            rag_id=rag_id,
            is_active_ask=is_active_ask,
        )
        logger.debug(f"构建运行时上下文-------------->: {custom_context}")

        runtime_config = self._build_runtime_config(thread_id=vision_id)
        logger.debug(f"构建运行时配置-------------->: {runtime_config}")

        return (
            messages,
            custom_context,
            runtime_config,
        )

    def _select_stream_agent(self, vision_id: str | None = None) -> Any:
        """根据是否存在视觉 ID 选择流式对话使用的 Agent。"""
        return self._get_agent() if vision_id else self.tiny_agent

    #############################################################################

    ############## 流式token输出 -> 文本分片的处理逻辑 ###################
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

    def _flush_remaining_stream_buffer(
        self, buffer: str, index: int
    ) -> tuple[list[tuple[str, int]], int]:
        """输出流式缓冲区中剩余的完整片段。"""
        if not buffer:
            return [], index

        fragments: list[tuple[str, int]] = []
        leading_tags, buffer = split_leading_intent_tags(buffer)
        for tag in leading_tags:
            fragments.append((tag, index))
            index += 1

        final_text, protected_suffix = split_trailing_protected_suffix(buffer)
        if final_text:
            fragments.append((final_text, index))
            index += 1

        if protected_suffix.endswith(INTENT_TAG_END):
            fragments.append((protected_suffix, index))

        return fragments, index

    ##################################################################

    ##################### 对外接口方法 #####################
    def get_query_to_resolve(self) -> bool:
        """返回是否需要查询以解析名称的标志。"""
        return getattr(self, "query_to_resolve", False)

    def set_query_to_resolve(self, value: bool) -> None:
        """设置是否需要查询以解析名称的标志。"""
        self.query_to_resolve = value

    def single_response(
        self, user_text: str, is_obtain_name: bool = False
    ) -> str | None:
        """发送用户输入，返回LLM解析后的用户名称，适合一次性获取解析结果的场景。

        params:
            user_text: 用户输入文本
            is_obtain_name: RAG 启用的情况下，获取用于解析名称的增强提示词。默认为 False。
        """
        # 1. 构造 HumanMessage（根据 is_obtain_name 决定内容）
        if is_obtain_name:
            human_msg = self._build_human_message(
                "（请按系统指令从【待分析文本】中抽取姓名）"
            )
        else:
            human_msg = self._build_human_message(user_text)

        # 2. 准备系统提示部分（包含可选的 RAG 增强提示词）
        system_parts = []

        # 2.1 全局系统提示（如果存在）
        if self.global_system_msg:
            system_parts.append(self.global_system_msg.content)

        # 2.2 RAG 增强提示词（如果启用）
        if self.enable_rag and self.rag_client is not None:
            res = self.rag_client.query(query=user_text, is_obtain_name=is_obtain_name)
            rag_prompt = res.get("prompt", "")
            if rag_prompt:
                system_parts.append(rag_prompt)
            logger.debug(f"RAG 增强提示词: {rag_prompt}")

        # 2.3 构建最终的系统消息（若有内容）
        messages = []
        if system_parts:
            combined_system = "\n\n".join(system_parts)
            messages.append(SystemMessage(content=combined_system))
        messages.append(human_msg)

        # 3. 准备调用配置
        invoke_config: RunnableConfig = {
            "callbacks": self.callback_handlers,
        }
        if is_obtain_name:
            # 姓名抽取要求确定性输出，降低随机性
            # 方法：创建一个临时绑定低温参数的模型副本
            llm_to_use = self.llm_model.bind(temperature=0.0, top_p=1.0)
        else:
            llm_to_use = self.llm_model

        # 4. 直接调用 LLM
        response = llm_to_use.invoke(messages, config=invoke_config)

        # 5. 提取 AI 消息内容
        last_ai_content = normalize_message_content(response.content)

        # 6. 姓名清洗（若需要）
        if is_obtain_name and last_ai_content is not None:
            from RAG.prompt_builder import sanitize_extracted_name

            sanitized = sanitize_extracted_name(last_ai_content)
            if sanitized != last_ai_content:
                logger.debug(
                    "姓名抽取结果已清洗: raw=%r sanitized=%r",
                    last_ai_content,
                    sanitized,
                )
            return sanitized
        return last_ai_content

    def chat_response(
        self,
        user_text: str,
        vision_id: str | None = None,
        voice_id: str | None = None,
        rag_id: str | None = None,
        is_active_ask: bool = False,
    ) -> str | None:
        """
        发送用户输入，获取 RAG 增强提示词，并返回LLM生成的回答文本。
        """
        messages, context, runtime_config = self._prepare_request(
            user_text,
            vision_id=vision_id,
            voice_id=voice_id,
            rag_id=rag_id,
            is_active_ask=is_active_ask,
        )
        result = (self._get_agent() if vision_id else self.tiny_agent).invoke(
            {"messages": messages},
            context=context,
            config=runtime_config,
            stream_mode="values",
        )
        logger.debug(self.callback_handlers[1].usage_metadata)  # 输出使用统计信息
        last_ai_content = self._get_last_ai_content(result)
        return last_ai_content

    def chat_response_stream(
        self,
        user_text: str,
        vision_id: str | None = None,
        voice_id: str | None = None,
        rag_id: str | None = None,
    ) -> Generator[tuple[str, int], Any, None]:
        """
        发送用户输入，获取 RAG 增强提示词，并以同步流式方式返回LLM生成的分段内容。
        """
        self.interrupt_event.clear()
        index = 0
        messages, context, runtime_config = self._prepare_request(
            user_text, vision_id=vision_id, voice_id=voice_id, rag_id=rag_id
        )
        buffer = ""
        stream_agent = self._select_stream_agent(vision_id)

        for chunk in stream_agent.stream(
            {"messages": messages},
            context=context,
            config=runtime_config,
            stream_mode="messages",
        ):
            if self.interrupt_event.is_set():
                logger.info("LLM 同步流式输出已中断")
                return

            fragments, buffer, index = self._append_stream_chunk(
                buffer,
                index,
                chunk,
                min_chunk_chars=STREAM_MIN_CHARS,
                max_chunk_chars=STREAM_MAX_CHARS,
                punctuation_marks=STREAM_PUNCTUATION_MARKS,
            )
            for fragment in fragments:
                if self.interrupt_event.is_set():
                    logger.info("LLM 同步流式输出已中断")
                    return

                yield fragment

        if self.interrupt_event.is_set():
            return

        fragments, _ = self._flush_remaining_stream_buffer(buffer, index)
        for fragment in fragments:
            if self.interrupt_event.is_set():
                logger.info("LLM 同步流式输出已中断")
                return

            yield fragment

    async def async_chat_response(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> str | None:
        """
        发送用户输入，获取 RAG 增强提示词，并异步返回LLM生成的完整回答文本。
        """
        messages, _, _ = self._prepare_request(
            user_text, vision_id=vision_id, voice_id=voice_id
        )

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
        last_ai_content = self._get_last_ai_content(result)
        return last_ai_content

    async def async_chat_response_stream(
        self, user_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> AsyncIterator[tuple[str, int]]:
        """
        发送用户输入，获取 RAG 增强提示词，并以异步流式方式返回LLM生成的分段内容。
        """
        self.interrupt_event.clear()
        index = 0
        messages, context, runtime_config = self._prepare_request(
            user_text, vision_id=vision_id, voice_id=voice_id
        )
        buffer = ""
        if self._use_direct_agent_path():
            logger.debug("直接调用 agent.astream 进行流式对话")
            chunk_iter = self._select_stream_agent(vision_id).astream(
                {"messages": messages},
                context=context,
                config=runtime_config,
                stream_mode="messages",
            )
            async for chunk in chunk_iter:
                if self.interrupt_event.is_set():
                    logger.info("LLM 异步流式输出已中断")
                    return
                fragments, buffer, index = self._append_stream_chunk(
                    buffer,
                    index,
                    chunk,
                    min_chunk_chars=STREAM_MIN_CHARS,
                    max_chunk_chars=STREAM_MAX_CHARS,
                    punctuation_marks=STREAM_PUNCTUATION_MARKS,
                )
                for fragment in fragments:
                    if self.interrupt_event.is_set():
                        logger.info("LLM 异步流式输出已中断")
                        return
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
                if self.interrupt_event.is_set():
                    logger.info("LLM 后台异步流式输出已中断")
                    await self._cancel_background_task(background_task)
                    break
                try:
                    event_type, payload = await asyncio.to_thread(
                        output_queue.get, True, 0.05
                    )
                except Empty:
                    continue
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
                    min_chunk_chars=STREAM_MIN_CHARS,
                    max_chunk_chars=STREAM_MAX_CHARS,
                    punctuation_marks=STREAM_PUNCTUATION_MARKS,
                )
                for fragment in fragments:
                    if self.interrupt_event.is_set():
                        logger.info("LLM 后台异步流式输出已中断")
                        await self._cancel_background_task(background_task)
                        return
                    yield fragment

            if not self.interrupt_event.is_set():
                await asyncio.wrap_future(background_task)
        if self.interrupt_event.is_set():
            return

        fragments, _ = self._flush_remaining_stream_buffer(buffer, index)
        for fragment in fragments:
            if self.interrupt_event.is_set():
                logger.info("LLM 异步流式输出已中断")
                return
            yield fragment

    # async list checkpoints
    async def alist_checkpoints(self, thread_id: str | None = None) -> list:
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

    # async get_tuple
    async def aget_checkpoint_tuple(self, thread_id: str | None = None) -> tuple | None:
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

    # delete_thread
    def delete_thread(self, thread_id: str | None = None) -> bool:
        """根据线程ID删除对应的对话线程数据。 如果线程ID未提供，则删除内存检查点中的默认线程ID的数据。"""
        if thread_id and self.async_sqlite_saver is not None:
            self.async_sqlite_saver.delete_thread(thread_id=thread_id)
            return True
        else:
            self.in_memory_checkpointer.delete_thread(thread_id=str(self.thread_id))
            return True

    ########################################################


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
        response = llm_agent.chat_response(
            user_input, vision_id=vision_id, voice_id=voice_id
        )
        print("AI:", response)

        # 同步流式获取回复文本分片
        # print("AI:", end=" ", flush=True)
        # for chunk, _ in llm_agent.chat_response_stream(
        #     user_input, vision_id=vision_id, voice_id=voice_id
        # ):
        #     print(chunk, end=" ", flush=True)
        # print()  # 换行

        checkpoints = await llm_agent.aget_checkpoint_tuple(thread_id=vision_id)
        for checkpoint in checkpoints or []:
            print(checkpoint)

        for message in (
            checkpoints[1].get("channel_values").get("messages") if checkpoints else []
        ):
            print(f"{message.type}--->: {message.content}")

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


if __name__ == "__main__":
    asyncio.run(_main())
