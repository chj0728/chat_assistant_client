import os

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain.agents.middleware.types import ToolCallRequest
from langchain.tools import tool
from logger import logger

from chat_assistant.node_handlers import ToolEvent, push_queue, tool_event_queue


@tool(description="当有人问候的时候，挥手回应")
def response_wave_hands_tool():
    logger.info("调用工具函数->机器人挥了挥手，表示问候！")
    push_queue(tool_event_queue, ToolEvent.WAVE_HANDS.value)


@tool(
    description="只有当用户回答退出、结束等相关内容时，调用结束对话工具，礼貌地结束对话"
)
def end_conversation_tool():
    logger.info("调用工具函数->机器人礼貌地结束了对话。")
    push_queue(tool_event_queue, ToolEvent.END_CONVERSATION.value)


@tool(description="调整默认扬声器音量")
def adjust_speaker_volume_tool(volume: int):
    logger.info(f"调用工具函数->调整系统默认扬声器音量为 {volume}。")

    if volume > 0 and volume <= 10:
        volume = int(volume * 10)
    elif volume < 0:
        volume = 0
    elif volume > 100:
        volume = 100

    os.system(f"pactl set-sink-volume @DEFAULT_SINK@ {volume}%")


class DynamicToolMiddleware(AgentMiddleware):
    """动态工具中间件示例，用于在运行时注册和调用工具。"""

    def wrap_model_call(self, request: ModelRequest, handler):
        updated = request.override(
            tools=[
                *request.tools,
                response_wave_hands_tool,
                end_conversation_tool,
                adjust_speaker_volume_tool,
            ]
        )
        return handler(updated)

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        if request.tool_call["name"] == "response_wave_hands_tool":
            logger.info("动态工具中间件: 检测到挥手回应工具调用")
            return handler(request.override(tool=response_wave_hands_tool))

        if request.tool_call["name"] == "end_conversation_tool":
            logger.info("动态工具中间件: 检测到结束对话工具调用")
            return handler(request.override(tool=end_conversation_tool))

        if request.tool_call["name"] == "adjust_speaker_volume_tool":
            logger.info("动态工具中间件: 检测到调整扬声器音量工具调用")
            return handler(request.override(tool=adjust_speaker_volume_tool))

        return handler(request)


dynamic_middlewares = [
    # DynamicToolMiddleware(),
]
