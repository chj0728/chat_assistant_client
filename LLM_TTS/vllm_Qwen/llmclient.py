import requests
import json


class LLMClient:
    def __init__(
        self,
        base_url,
        model,
        temperature=0.6,
        top_p=0.95,
        top_k=20,
        max_tokens=256,
        enable_thinking=False,
        timeout=120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
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

    def reset(self):
        """清空上下文"""
        self.messages.clear()

    def add_user_message(self, text: str):

        # 添加用户消息到上下文
        # self.messages.append({"role": "user", "content": text})

        # 不添加到上下文，只作为本次请求的输入
        self.messages.clear()
        self.messages = [{"role": "user", "content": text}]

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
            "model": self.model,
            "messages": self.messages,
            **self.generation_config,
        }

        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
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
        base_url="http://192.168.50.125:8000",
        model="Qwen/Qwen3-8B",
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
