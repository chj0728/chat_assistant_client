from llm import LLMAgent
from logger import logger
from tts.ttsplay import RealtimeTTSPlayer

if __name__ == "__main__":

    tts_player = RealtimeTTSPlayer(
        host="192.168.50.125",
        port=50000,
    )
    tts_player.change_preset(
        "longshu_zh"
    )  # 可选值: "default"(女性活泼), "zh"(男性非标准) , "hard_zh"(男性业余), "longshu_zh"(男性专业), "longwan_zh"（女性专业）

    # tts_player.generate_wav("你好呀！请问有什么可以帮到你的吗？", "welcome.wav")
    # tts_player.play_audio("welcome.wav")

    llm_client = LLMAgent(
        host="192.168.50.125",
        port=8000,
        temperature=0.6,  # 设置较低的温度以获得更确定性的回答
        top_p=0.9,  # 使用 nucleus 采样
        top_k=50,  # 使用 top-k 采样
        max_tokens=256,
    )

    # llm_client.add_system_prompt("你叫小白")

    # print("开始与模型对话（输入 exit 或 quit 退出）")
    logger.info("开始与模型对话（输入 exit 或 quit 退出）")

    while True:
        user_input = input("你：").strip()
        if user_input.lower() in ["exit", "quit"]:
            break

        llm_response = ""

        if tts_player.is_active():
            # print("\n⚠️ 上一次的语音还没播完，请稍等片刻...\n")
            logger.warning("⚠️ 上一次的语音还没播完，请稍等片刻...")
            continue

        # for token in llm_client.stream_chat(user_input):
        #     print(token, end="", flush=True)
        #     buffer += token
        llm_response = llm_client.chat_response(user_input)
        print(f"助手：{llm_response}")

        # # ===== 更稳健的断句条件 =====
        # if (
        #     token in ["。", "！", "？"]
        #     and len(buffer) >= 15
        #     and not buffer.rstrip().endswith(("*", "#", '"', "”"))
        # ):
        if llm_response:
            tts_player.speak(llm_response.strip(), interrupt=True)
        # buffer = ""

        # 循环结束后，把剩余的也说出来
        # if buffer.strip():
        #     tts_player.speak(buffer.strip(), interrupt=False)

    # print("对话结束")
    logger.info("对话结束")
