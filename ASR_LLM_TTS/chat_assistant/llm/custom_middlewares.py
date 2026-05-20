"""
自定义中间件模块

description:
    这里定义了一些自定义中间件，这些中间件会被注册到 Agent 中，供 Agent 在对话过程中调用。
    这些中间件可以实现一些特定的功能，比如在模型生成消息前后进行处理。
reference:
    - https://docs.langchain.com/oss/python/langchain/middleware/custom#decorator-based-middleware
    - https://docs.langchain.com/oss/python/langchain/runtime#inside-middleware
"""

from collections.abc import Callable
from typing import Any

from config import get_max_messages
from langchain.agents import AgentState
from langchain.agents.middleware import (
    ModelRequest,
    ModelResponse,
    after_agent,
    after_model,
    before_agent,
    before_model,
    dynamic_prompt,
    wrap_model_call,
)
from langchain.messages import RemoveMessage
from langchain_core.messages import (
    SystemMessage,
    trim_messages,
)
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime
from logger import logger

from llm.custom_context import CustomContext


@before_agent
def test_before_agent(state: AgentState, runtime: Runtime) -> None:
    # global call_flag
    # call_flag = True
    logger.debug("=======> Before Agent Dynamic Middleware")
    # messages = state["messages"]
    # logger.debug(f"Current messages: {[m for m in messages]}")
    # for m in messages:
    #     m.pretty_print()


@before_model
def trim_messages_before_model(
    state: AgentState, runtime: Runtime[CustomContext]
) -> dict[str, Any] | None:
    """Keep only the last few messages to fit context window.
    official docs: https://docs.langchain.com/oss/python/langchain/short-term-memory#trim-messages
    """

    logger.debug(f"runtime.context.user_id------------>: \n{runtime.context.user_id}")

    messages = state["messages"]

    logger.debug("\n=======> Before Model Middleware:\n Current messages:\n ")
    for i, m in enumerate(messages):
        logger.debug(f"Message {i}: {m}")

    # info = runtime.execution_info
    # logger.debug(f"模型调用上下文信息------------>: \n{info}")

    # logger.debug(f"runtime.server_info------------>: \n{runtime.server_info}")

    # logger.debug(f"runtime.context------------>: \n{runtime.context}")

    # refer from: https://juejin.cn/post/7534535266226192430
    # # 使用 token 数量限制的方式来控制对话历史长度
    # trimmed_tokens_messages = trim_messages(
    #     messages,
    #     max_tokens=get_max_tokens(),  # 保留消息的最大token数量，超过时会删除最旧的消息，直到总token数在限制内
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
    trimmed_messages = trim_messages(
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

    logger.debug(
        "\n=======> Before Model Middleware:\n Trimmed messages to fit context window:\n "
    )
    for i, m in enumerate(trimmed_messages):
        logger.debug(f"Message {i}: {m}")

    # return {"messages": trimmed}
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *trimmed_messages]}


@before_model
def move_the_system_to_beginning(
    state: AgentState, runtime: Runtime[CustomContext]
) -> dict[str, Any] | None:
    """将System message移动到最前端"""
    messages = state["messages"]

    if not messages:
        return None

    system_messages = [m for m in messages if isinstance(m, SystemMessage)]
    if not system_messages:
        return None

    non_system_messages = [m for m in messages if not isinstance(m, SystemMessage)]
    reordered_messages = [*system_messages, *non_system_messages]

    if reordered_messages == messages:
        return None

    logger.debug(
        "\n=======> Before Model Middleware:\n Reordered messages with SystemMessage at the beginning:\n "
    )
    for i, m in enumerate(reordered_messages):
        logger.info(f"Message {i}: {m}")

    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *reordered_messages]}


@wrap_model_call
def update_system_prompt_dynamically(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    """根据上下文动态更新系统提示词"""
    # 当前模型调用的上下文信息
    if request.system_message is None:
        logger.warning("模型调用请求中没有系统消息，无法动态更新系统提示词")
        return handler(request)
    else:
        default_system_prompt = list(request.system_message.content_blocks)
        logger.debug(f"默认系统提示词内容块：{default_system_prompt}")
        return handler(request)


@dynamic_prompt
def dynamic_system_prompt(request: ModelRequest) -> str:
    """根据上下文动态生成系统提示词"""
    dynamic_system_prompt = ""
    if request.runtime.context:

        default_system_prompt = request.runtime.context.default_system_prompt
        logger.debug(f"默认系统提示词内容块：{default_system_prompt}")

        rag_prompt = request.runtime.context.rag_prompt
        logger.debug(f"RAG 提示词内容块：{rag_prompt}")

        dynamic_system_prompt = (default_system_prompt or "") + (rag_prompt or "")

    return dynamic_system_prompt


@after_model
def delete_system_message_after_model(
    state: AgentState, runtime: Runtime
) -> dict[str, Any] | None:
    """删除模型回复中的系统消息，避免系统消息被后续对话历史保留和重复使用。"""
    messages = state["messages"]

    logger.debug("\n=======> After Model Middleware:\n Current messages:\n ")
    for i, m in enumerate(messages):
        logger.debug(f"Message {i}: {m}")

    # 删除 AI 回复中的系统消息
    cleaned_messages = [m for m in messages if not isinstance(m, SystemMessage)]

    logger.debug(
        "\n=======> After Model Middleware:\n Cleaned messages (removed SystemMessage):\n "
    )
    for i, m in enumerate(cleaned_messages):
        logger.debug(f"Message {i}: {m}")

    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *cleaned_messages]}


@after_agent
def test_after_agent(state: AgentState, runtime: Runtime) -> None:
    logger.debug("=======> After Agent Dynamic Middleware")
    # messages = state["messages"]
    # logger.debug(f"Current messages: {[m for m in messages]}")
    # for m in messages:
    #     m.pretty_print()


def get_custom_middlewares() -> list:
    """获取自定义中间件列表"""
    return [
        dynamic_system_prompt,
        # update_system_prompt_dynamically,
        test_before_agent,
        trim_messages_before_model,
        # move_the_system_to_beginning,
        delete_system_message_after_model,
        test_after_agent,
    ]
