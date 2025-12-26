import requests
import json

from .tools.functions import get_shanghai_time

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
    }
]

TOOL_FUNCTIONS = {
    "get_shanghai_time": get_shanghai_time,
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
                "你叫千问，是一个由Qwen3模型驱动的智能助手。"
                "只要用户提出的问题需要使用工具（例如查询时间），你就应该调用相应的工具，"
                "然后将工具返回的信息整合到你的回答中。"
            ),
        }

        self.llm_url = f"{self.host}:{self.port}/v1/models"
        try:
            response = requests.get(self.llm_url)
            data = response.json()

            # 获取第一个模型的ID
            self.model_id = data["data"][0]["id"]
            print(f"使用的模型ID: {self.model_id}")

            self.model_root = data["data"][0]["root"]
            print(f"模型根目录: {self.model_root}")

        except Exception as e:
            print(f"获取模型列表失败: {e}")
            raise e

    def reset(self):
        """清空上下文"""
        self.messages.clear()

    def add_user_message(self, text: str):

        # 添加用户消息到上下文
        # self.messages.append({"role": "user", "content": text})

        # 不添加到上下文，只作为本次请求的输入
        self.messages.clear()
        self.messages = [self.system_prompt, {"role": "user", "content": text}]

        # 限制回答长度
        self.messages.append({"role": "system", "content": "请将回答控制在100字以内。"})

    def add_assistant_message(self, text: str):
        self.messages.append({"role": "assistant", "content": text})

    def stream_chat(self, user_text: str):
        """
        发送用户输入，返回 token 级生成器
        （支持 tool_calls，不影响普通对话）
        """
        self.add_user_message(user_text)

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

            # ========= 工具调用（关键修正） =========
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

                    print(f"\n调用工具: {func_name}，参数: {arguments_str}")

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


if __name__ == "__main__":

    llm_client = LLMClient(host="http://192.168.50.125", port=8000, temperature=0.1)
    print("开始与模型对话（输入 exit 或 quit 退出）")

    while True:
        user_input = input("你：").strip()
        if user_input.lower() in ["exit", "quit"]:
            break

        print("助手：", end="", flush=True)

        for token in llm_client.stream_chat(user_input):
            print(token, end="", flush=True)

        print("\n")

    print("对话结束")
