"""
Custom context for LLM
description:
    自定义上下文模板，这些模板会被注册到 Agent 中，供 Agent 在对话过程中调用。
reference:
    - https://docs.langchain.com/oss/python/langchain/runtime
"""

from dataclasses import dataclass


@dataclass
class CustomContext:
    """自定义上下文类，可以根据需要添加更多字段。"""

    # 这里可以添加一些自定义字段，比如用户信息、会话状态等
    user_id: str | None = "default_user"
    vision_id: str | None = "default_vision"
    voice_id: str | None = "default_voice"
    session_id: str = "default_session"
    # 其他字段...


def get_custom_context_cls() -> type[CustomContext]:
    """获取自定义上下文类，可以根据需要从其他地方获取数据来填充上下文。"""
    # 这里可以添加一些逻辑来获取实际的上下文数据，比如从数据库、缓存等
    return CustomContext
