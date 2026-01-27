import requests
import json

VLLM_URL = "http://192.168.50.125:8000/v1/chat/completions"
MODEL_NAME = "Qwen/Qwen3"

messages = []

print("开始与模型对话（输入 exit 或 quit 退出）")

while True:
    user_input = input("你：").strip()
    if user_input.lower() in ["exit", "quit"]:
        break

    messages.append({"role": "user", "content": user_input})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "max_tokens": 256,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    print("助手：", end="", flush=True)

    response = requests.post(
        VLLM_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        stream=True,
    )

    assistant_reply = ""

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue

        # vLLM / OpenAI 流式格式：data: {...}
        if line.startswith("data: "):
            data = line[len("data: ") :]

            if data == "[DONE]":
                break

            chunk = json.loads(data)
            delta = chunk["choices"][0]["delta"]

            if "content" in delta:
                token = delta["content"]
                assistant_reply += token
                print(token, end="", flush=True)

    print("\n")
    messages.append({"role": "assistant", "content": assistant_reply})

print("对话结束")
