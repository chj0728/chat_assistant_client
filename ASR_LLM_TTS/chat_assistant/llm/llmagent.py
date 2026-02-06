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

import requests
import json
import sys
import os

from pydantic import SecretStr

from langchain_openai import ChatOpenAI
from langchain_community.llms.vllm import VLLM, VLLMOpenAI
from langchain.chat_models import init_chat_model

from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain.agents.middleware.types import ToolCallRequest

from logger import logger


# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 将当前目录添加到Python路径（如果是相对导入）
sys.path.append(current_dir)
from tools.functions import get_shanghai_time, get_current_location, get_weather_info


@tool(description="获取当前时间的工具函数")
def get_current_time_tool() -> str:
    # """获取上海当前时间的工具函数"""
    logger.info("调用工具函数->获取当前时间。")
    return get_shanghai_time()


@tool(description="获取当前位置信息的工具函数")
def get_current_location_tool() -> str:
    # """获取当前位置信息的工具函数"""
    logger.info("调用工具函数->获取当前位置信息。")
    return get_current_location()


@tool(description="获取天气信息的工具函数")
def get_weather_info_tool() -> str:
    # """获取天气信息的工具函数"""
    logger.info("调用工具函数->获取天气信息。")
    return get_weather_info()


# -------- 测试 tools --------
# @tool(description="当有人问候的时候，挥手回应")
# def response_wave_hands_tool() -> str:
#     # """挥手回应的工具函数"""
#     logger.info("工具函数: 机器人挥了挥手，表示问候！")
#     return "机器人挥了挥手，表示问候！"


# @tool(description="当用户想要参观的时候，引导客户前往指定区域")
# def guide_customer_tool() -> str:
#     """引导客户的工具函数"""
#     logger.info("工具函数: 机器人引导客户前往指定区域。")
#     return "机器人引导客户前往指定区域。"


# @tool(description="当用户回答退出、结束等相关内容时，礼貌地结束对话")
# def end_conversation_tool() -> str:
#     """结束对话的工具函数"""
#     logger.info("工具函数: 机器人礼貌地结束了对话。")
#     return "机器人礼貌地结束了对话。"


class LLMAgent:
    """
    LLMAgent 类用于创建和管理基于大型语言模型（LLM）的聊天代理。
    基于 LangChain 框架，支持系统消息配置和从对话状态中提取 AI 消息内容的实用函数。
    """

    def __init__(
        self,
        host,
        port,
        middleware_list: list[AgentMiddleware] | None = None,
        # dynamic_tool_middlewares: AgentMiddleware | None = None,
        temperature=0.6,
        top_p=0.95,
        top_k=50,
        max_tokens=256,
        enable_thinking=False,
        timeout=30,
    ):
        """
        初始化 LLMAgent 实例。

        参数:
            host (str): LLM 服务的主机地址。
            port (int): LLM 服务的端口号。
            dynamic_tool_middlewares (AgentMiddleware | None): 可选的动态工具中间件。 默认值为 None。
            temperature (float): 控制生成文本的随机性。默认值为 0.6。
            top_p (float): 用于 nucleus 采样的概率阈值。默认值为 0.95。
            top_k (int): 用于 top-k 采样的词汇数量。默认值为 50。
            max_tokens (int): 生成文本的最大 token 数量。默认值为 256。
            enable_thinking (bool): 是否启用思考过程。默认值为 False。
            timeout (int): 请求超时时间（秒）。默认值为 30 秒。
        """

        self.host = host
        self.port = port
        self.model_id = None
        self.model_root = None
        self.timeout = timeout

        # 获取模型列表
        self.llm_url = f"http://{self.host}:{self.port}/v1/models"
        try:
            response = requests.get(self.llm_url)
            data = response.json()

            # 获取第一个模型的ID
            self.model_id = data["data"][0]["id"]
            logger.info(f"使用的模型ID: {self.model_id}")

            self.model_root = data["data"][0]["root"]
            logger.info(f"模型根目录: {self.model_root}")

        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            # 使用默认模型ID
            self.model_id = "Qwen/Qwen3"

        # 初始化 ChatOpenAI 实例
        self.llm_model = ChatOpenAI(
            model=self.model_id,
            stream_usage=True,
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_tokens,
            timeout=self.timeout,
            api_key=SecretStr("EMPTY"),  # vLLM不需要key
            base_url=f"http://{self.host}:{self.port}/v1",  # vLLM服务地址
            max_retries=2,
            extra_body={"chat_template_kwargs": {"enable_thinking": enable_thinking}},
        )
        logger.info("LLM 模型初始化完成")

        # 创建聊天代理
        self.agent = create_agent(
            self.llm_model,
            tools=[
                get_current_time_tool,
                get_current_location_tool,
                get_weather_info_tool,
                # response_wave_hands_tool,
                # guide_customer_tool,
                # end_conversation_tool,
            ],
            # system_prompt=self.system_msg if hasattr(self, "system_msg") else None,
            checkpointer=InMemorySaver(),  # 使用内存检查点保存对话状态
            middleware=middleware_list if middleware_list else [],
            # middleware=[dynamic_tool_middlewares] if dynamic_tool_middlewares else [],
        )
        logger.info("LLM Agent 创建完成")

        self.system_msg = SystemMessage(
            # """
            # 你需要简洁且有礼貌地回答用户的问题，请保持回答简短且有条理，控制在100字以内。
            # 只要用户询问关于时间或位置的问题时，优先使用工具来获取准确的信息，而不是直接从模型中生成答案。
            # 如果你不确定答案，可以礼貌地告诉用户你不知道，而不是编造答案。
            # 在回答中尽量避免使用标点符号结尾，以便更自然地进行语音合成。
            # 如果用户回答退出、结束等相关内容时，礼貌地结束对话。
            # """
            content="""你需要简洁且有礼貌地回答用户的问题，请保持回答简短且有条理，控制在100字以内。
只要用户询问关于时间或位置的问题时，优先使用工具来获取准确的信息，而不是直接从模型中生成答案。
如果你不确定答案，可以礼貌地告诉用户你不知道，而不是编造答案。
在回答中尽量避免使用标点符号结尾，以便更自然地进行语音合成。
如果用户回答退出、结束等相关内容时，调用结束对话工具，礼貌地结束对话。"""
        )

    # -------- private methods --------
    def get_last_ai_content(self, state) -> str | None:
        """
        从对话状态中提取最后一条 AI 消息的内容。

        参数:
            state: 对话状态对象，包含消息列表.

        返回:
            str: 最后一条 AI 消息的内容，如果不存在则返回空字符串。
        """
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, list):
                    return " ".join(
                        part if isinstance(part, str) else str(part) for part in content
                    )
                return content
        return None

    # -------- public methods for user --------

    def add_system_prompt(self, prompt: str):
        """
        追加系统提示内容。

        参数:
            prompt (str): 系统提示内容。
        """
        self.system_msg.content += "\n" + prompt

    def chat_response(self, user_text: str) -> str | None:
        """
        发送用户输入，返回完整回答文本
        """
        human_msg = HumanMessage(content=user_text)
        messages = [
            self.system_msg,
            human_msg,
        ]
        result = self.agent.invoke(
            {"messages": messages},
            {"configurable": {"thread_id": "1"}},
            stream_mode="values",
        )
        # logger.debug(f"LLM Agent 返回结果: {result}")
        last_ai_content = self.get_last_ai_content(result)
        return last_ai_content


if __name__ == "__main__":

    llm_agent = LLMAgent(host="192.168.50.125", port=8000)

    # llm_agent.add_system_prompt("你叫小白，是一个智能助理。")

    while True:
        user_input = input("User: ").strip()
        if user_input.lower() in ["exit", "quit"]:
            break
        response = llm_agent.chat_response(user_input)
        print("AI:", response)
