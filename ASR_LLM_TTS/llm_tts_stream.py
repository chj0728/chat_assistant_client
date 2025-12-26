from tts.ttsplay import RealtimeTTSPlayer

from llm.llmclient import LLMClient

import requests

if __name__ == "__main__":

    tts_player = RealtimeTTSPlayer(
        host="http://192.168.50.125",
        port=50000,
    )

    # tts_player.generate_wav("你好呀！请问有什么可以帮到你的吗？", "welcome.wav")
    # tts_player.play_audio("welcome.wav")

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

        buffer = ""

        for token in llm_client.stream_chat(user_input):
            print(token, end="", flush=True)
            buffer += token

            # # ===== 更稳健的断句条件 =====
            # if (
            #     token in ["。", "！", "？"]
            #     and len(buffer) >= 15
            #     and not buffer.rstrip().endswith(("*", "#", '"', "”"))
            # ):
        tts_player.speak(buffer.strip(), interrupt=False)
        # buffer = ""

        # 循环结束后，把剩余的也说出来
        # if buffer.strip():
        #     tts_player.speak(buffer.strip(), interrupt=False)

        print("\n")

    print("对话结束")
