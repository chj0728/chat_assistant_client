"""
Custom context for LLM
description:
    自定义上下文模板，这些模板会被注册到 Agent 中，供 Agent 在对话过程中调用。
reference:
    - https://docs.langchain.com/oss/python/langchain/runtime
"""

from dataclasses import dataclass

from config import get_default_system_prompt


@dataclass
class CustomContext:
    """自定义上下文类，可以根据需要添加更多字段。"""

    # 这里可以添加一些自定义字段，比如用户信息、会话状态等
    user_id: str | None = "default_user"
    vision_id: str | None = "default_vision"
    voice_id: str | None = "default_voice"
    session_id: str = "default_session"
    default_system_prompt: str | None = (
        get_default_system_prompt()
    )  # 从配置中获取默认系统提示词
    rag_prompt: str | None = None  # RAG 检索结果，可以在生成提示词时使用
    # 其他字段...


def get_custom_context_cls() -> type[CustomContext]:
    """获取自定义上下文类，可以根据需要从其他地方获取数据来填充上下文。"""
    context_cls = CustomContext
    context_cls.default_system_prompt = get_default_system_prompt()
    return context_cls
