"""
自定义工具模块

description:
    这里定义了一些自定义工具函数，这些函数会被注册到 Agent 中，供 Agent 在对话过程中调用。
    这些工具函数可以实现一些特定的功能，比如获取当前时间、获取位置信息、获取天气信息等。
reference:
    - https://docs.langchain.com/oss/python/langchain/agents#static-tools
"""

from langchain.tools import tool
from logger import logger
from tools.functions import get_current_location, get_shanghai_time, get_weather_info


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


def get_custom_tools() -> list:
    """获取自定义工具列表"""
    return [
        get_current_time_tool,
        get_current_location_tool,
        get_weather_info_tool,
    ]
