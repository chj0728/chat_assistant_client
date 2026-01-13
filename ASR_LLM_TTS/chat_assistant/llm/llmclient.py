import requests
import json

import sys
import os

from logger import logger

MAX_CHARS = 500  # 上下文最大字符数限制

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 将当前目录添加到Python路径（如果是相对导入）
sys.path.append(current_dir)

from tools.functions import get_shanghai_time, get_current_location, get_weather_info

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_shanghai_time",
            "description": "获取当前中国上海（Asia/Shanghai）的时间",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_location",
            "description": "获取当前位置信息",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_info",
            "description": "获取当前天气预报信息",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "get_shanghai_time": get_shanghai_time,
    "get_current_location": get_current_location,
    "get_weather_info": get_weather_info,
}


class LLMClient:
    def __init__(
        self,
        host,
        port,
        temperature=0.6,
        top_p=0.95,
        top_k=20,
        max_tokens=256,
        enable_thinking=False,
        timeout=60,
    ):
        self.host = host
        self.port = port
        self.model_id = None
        self.model_root = None
        self.timeout = timeout

        self.tools = TOOLS
        self.tool_functions = TOOL_FUNCTIONS

        self.generation_config = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "max_tokens": max_tokens,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        }

        self.messages = []

        self.system_prompt = {
            "role": "system",
            "content": (
                # "1. 你是一个由Qwen3模型驱动的中文语音助手，"
                "2. 你需要简洁且有礼貌地回答用户的问题，请保持回答简短且有条理，控制在100字以内。"
                "3. 只要用户询问关于时间或位置的问题时，优先使用工具来获取准确的信息，而不是直接从模型中生成答案。"
                "4. 如果你不确定答案，可以礼貌地告诉用户你不知道，而不是编造答案。"
                "5. 在回答中尽量避免使用标点符号结尾，以便更自然地进行语音合成。"
                "6. 如果用户回答退出、结束等相关内容时，礼貌地结束对话。"
            ),
        }

        self.developer_prompt = {
            "role": "developer",
            "content": (
                "只要用户询问关于时间或位置的问题时，优先使用工具来获取准确的信息，"
                "而不是直接从模型中生成答案。"
            ),
        }

        self.history = []  # 只放 user / assistant / tool

        self.llm_url = f"{self.host}:{self.port}/v1/models"
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

    def reset_history(self):
        """清空历史记录"""
        self.history.clear()

    def add_user_message(self, text: str):

        # 不添加到上下文，只作为本次请求的输入
        self.messages.clear()
        self.messages = [
            self.system_prompt,
            self.developer_prompt,
            *self.history,
            {"role": "user", "content": text},
        ]

    def add_assistant_message(self, text: str):
        self.messages.append({"role": "assistant", "content": text})

    def add_system_prompt(self, text: str):
        # append system prompt
        self.system_prompt["content"] += "\n" + text
        logger.info("新增系统提示词: %s", text)

    def _trim_history(self):
        total = sum(len(m.get("content", "")) for m in self.history)

        while total > MAX_CHARS and len(self.history) > 2:
            # print("修剪历史记录，当前字符数:", total)
            logger.info("修剪历史记录，当前字符数: %d", total)
            removed = self.history.pop(0)
            total -= len(removed.get("content", ""))

    def build_messages(self, user_text: str):
        """
        根据当前历史记录和用户输入，构建消息列表
        """

        # 修剪历史记录，确保不超过最大字符数
        self._trim_history()

        # 重新构建消息列表
        self.messages.clear()

        # 拼接消息列表
        self.messages = (
            [
                self.system_prompt,
                self.developer_prompt,
            ]
            + self.history
            + [{"role": "user", "content": user_text}]
        )

    # def stream_chat(self, user_text: str):
    def request_stream_response(self, user_text: str):
        """
        发送用户输入，返回 token 级生成器
        （支持 tool_calls，不影响普通对话）
        """
        # self.add_user_message(user_text)
        self.build_messages(user_text)

        payload = {
            "model": self.model_id,
            "messages": self.messages,
            **self.generation_config,
        }

        # 如果你之后启用 tools，可以在这里加
        if hasattr(self, "tools") and self.tools:
            payload["tools"] = self.tools
            payload["tool_choice"] = "auto"

        response = requests.post(
            f"{self.host}:{self.port}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            stream=True,
            timeout=self.timeout,
        )

        # 用来收集工具调用
        tool_calls = {}

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            if not line.startswith("data: "):
                continue

            data = line[len("data: ") :]

            if data == "[DONE]":
                break

            chunk = json.loads(data)
            choice = chunk["choices"][0]
            delta = choice.get("delta", {})

            # print("收到新数据块:", delta)

            # ========= 普通文本 =========
            if "content" in delta and delta["content"]:
                # print("收到新token:", delta["content"])
                yield delta["content"]

            # ========= 工具调用 =========
            if "tool_calls" in delta:
                # print("收到工具调用数据:", delta["tool_calls"])
                for call in delta["tool_calls"]:
                    index = call["index"]

                    if index not in tool_calls:
                        tool_calls[index] = {
                            "id": call.get("id"),
                            "name": call["function"]["name"],
                            "arguments": "",
                        }

                    # arguments 是流式拼接的（可能多次）
                    if "arguments" in call["function"]:
                        tool_calls[index]["arguments"] += call["function"]["arguments"]

        # ========= 处理工具调用结果 =========
        for index, call in tool_calls.items():
            func_name = call["name"]
            arguments_str = call["arguments"]

            # print(f"\n调用工具: {func_name}，参数: {arguments_str}")
            logger.info(f"调用工具: {func_name}，参数: {arguments_str}")

            # 解析参数（假设是 JSON 格式）
            try:
                arguments = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                arguments = {}

            # 执行工具函数
            if func_name in self.tool_functions:
                tool_function = self.tool_functions[func_name]
                tool_result = tool_function(**arguments)

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": tool_result,
                    }
                )

                # 继续生成后续回答
                followup_payload = {
                    "model": self.model_id,
                    "messages": self.messages,
                    **self.generation_config,
                }

                followup_response = requests.post(
                    f"{self.host}:{self.port}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(followup_payload),
                    stream=True,
                    timeout=self.timeout,
                )

                # 处理后续回答的流式输出
                for line in followup_response.iter_lines(decode_unicode=True):
                    if not line:
                        continue

                    if not line.startswith("data: "):
                        continue

                    data = line[len("data: ") :]

                    if data == "[DONE]":
                        break

                    chunk = json.loads(data)
                    choice = chunk["choices"][0]
                    delta = choice.get("delta", {})

                    if "content" in delta and delta["content"]:
                        yield delta["content"]

    def chat_response(self, user_text: str) -> str:
        """
        发送用户输入，返回完整回答文本
        """
        stream_response = self.request_stream_response(user_text)
        response_text = "".join([token for token in stream_response])
        self.history.append({"role": "assistant", "content": response_text})
        return response_text


if __name__ == "__main__":

    llm_client = LLMClient(host="http://192.168.50.125", port=8000, temperature=0.6)

    # llm_client.add_system_prompt("你叫小白")

    # print("开始与模型对话（输入 exit 或 quit 退出）")
    logger.info("开始与模型对话（输入 exit 或 quit 退出）")

    while True:
        user_input = input("你：").strip()
        if user_input.lower() in ["exit", "quit"]:
            break

        print("助手：", end="", flush=True)

        # assistant_reply = []
        # for token in llm_client.stream_chat(user_input):
        #     print(token, end="", flush=True)
        #     assistant_reply += [token]
        # # llm_client.add_assistant_message("".join(assistant_reply))
        # llm_client.history.append({"role": "user", "content": user_input})
        # llm_client.history.append(
        #     {"role": "assistant", "content": "".join(assistant_reply)}
        # )

        assistant_reply = llm_client.chat_response(user_input)
        print(assistant_reply)
        # print("\n")
        llm_client.history.append({"role": "user", "content": user_input})

    # print("对话结束")
    logger.info("对话结束")
