from cosyvoice.ttsplay import RealtimeTTSPlayer

from vllm_Qwen.llmclient import LLMClient

import requests

if __name__ == "__main__":

    tts_player = RealtimeTTSPlayer(
        tts_url="http://192.168.50.125:50000/inference_zero_shot"
    )

    # tts_player.generate_wav("你好呀！请问有什么可以帮到你的吗？", "welcome.wav")
    # tts_player.play_audio("welcome.wav")

    # 获取模型id 和 模型列表
    api_url = "http://192.168.50.125:8000/v1/models"

    try:
        response = requests.get(api_url)
        data = response.json()

        # 获取第一个模型的ID
        model_id = data["data"][0]["id"]
        print(f"使用的模型ID: {model_id}")

        model_root = data["data"][0]["root"]
        print(f"模型根目录: {model_root}")

    except Exception as e:
        print(f"获取模型列表失败: {e}")
        raise e

    llm_client = LLMClient(
        base_url="http://192.168.50.125:8000",
        model=model_id,
    )

    print("开始与模型对话（输入 exit 或 quit 退出）")

    while True:
        user_input = input("你：").strip()
        if user_input.lower() in ["exit", "quit"]:
            break

        print("助手：", end="", flush=True)

        buffer = ""

        for token in llm_client.stream_chat(user_input):
            print(token, end="", flush=True)
            buffer += token

            # ===== 更稳健的断句条件 =====
            if (
                token in ["。", "！", "？"]
                and len(buffer) >= 15
                and not buffer.rstrip().endswith(("*", "#", '"', "”"))
            ):
                tts_player.speak(buffer.strip(), interrupt=False)
                buffer = ""

        # 循环结束后，把剩余的也说出来
        if buffer.strip():
            tts_player.speak(buffer.strip(), interrupt=False)

        print("\n")

    print("对话结束")
