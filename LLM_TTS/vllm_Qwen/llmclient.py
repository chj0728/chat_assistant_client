import requests
import json


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
            "content": "你叫千问，是一个由Qwen3模型驱动的智能助手，擅长回答各种问题，提供有用的信息，并与用户进行自然的对话。",
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
        """
        self.add_user_message(user_text)

        payload = {
            "model": self.model_id,
            "messages": self.messages,
            **self.generation_config,
        }

        response = requests.post(
            f"{self.host}:{self.port}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            stream=True,
            timeout=self.timeout,
        )

        assistant_reply = ""

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            if not line.startswith("data: "):
                continue

            data = line[len("data: ") :]

            if data == "[DONE]":
                break

            chunk = json.loads(data)
            delta = chunk["choices"][0]["delta"]

            if "content" in delta:
                token = delta["content"]
                assistant_reply += token
                yield token

        # 生成结束，写回上下文
        if assistant_reply.strip():
            self.add_assistant_message(assistant_reply)


if __name__ == "__main__":

    llm_client = LLMClient(
        host="http://192.168.50.125",
        port=8000,
    )
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
