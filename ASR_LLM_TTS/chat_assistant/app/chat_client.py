import os
import re
import wave
import requests
import sounddevice as sd
import numpy as np
import time
import threading
from scipy.io.wavfile import write
from queue import Queue
from pypinyin import pinyin, Style

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
print(f"当前文件目录: {current_dir}")

# -------------------- 初始化 ASR ------------------
from asr.asrclient import ASRClient

asr_client = ASRClient(
    host="http://192.168.50.125",
    port=2002,
    timeout=30,
)

# ----------------- 初始化 LLM -------------------
from llm.llmclient import LLMClient

llm_client = LLMClient(
    host="http://192.168.50.125",
    port=8000,
)

# ----------------- 初始化 TTS -------------------
from tts.ttsplay import RealtimeTTSPlayer

tts_client = RealtimeTTSPlayer(
    host="http://192.168.50.125",
    port=50000,
)


# 参数设置
AUDIO_RATE = 16000  # 44100  # 16000  # 音频采样率
AUDIO_CHANNELS = 1  # 单声道
CHUNK = 1024  # 音频块大小

VAD_MODE = 3  # VAD 模式 (0-3, 数字越大越敏感)
OUTPUT_DIR = "./output"  # 输出目录
NO_SPEECH_THRESHOLD = 0.5  # 无效语音阈值，单位：秒
NO_REACTIVE_KWS_THRESHOLD = 30  # 多久未检测到唤醒词，重置唤醒词状态，单位：秒

folder_path = "./ASR_LLM_TTS/"
audio_file_count = 0
audio_file_count_tmp = 0

# 全局变量
recording_active = True  # 当前是否处于录音状态
segments_to_save = []  # 待保存的音频片段
saved_intervals = []  # 已保存的时间区间
last_active_time = time.time()  # 上次检测到有效语音的时间
last_vad_end_time = 0  # 上次保存的 VAD 有效段结束时间
last_llm_time = time.time()  # 上次与 LLM 交互的时间

# --- 唤醒词、声纹变量配置 ---
set_KWS = "ni hao xiao xue"  # 唤醒词拼音
flag_KWS = 0  # 唤醒词检测标志
failed_enable_kws_count = 0  # 连续未检测到唤醒词计数

flag_KWS_used = 1  # 是否启用唤醒词检测 0 不启用 1 启用
flag_sv_used = 0  # 是否启用声纹检测 0 不启用 1 启用

flag_sv_enroll = 0  # 是否处于声纹注册状态 0 否 1 是
thred_sv = 0.35  # 声纹相似度阈值，低于此值则认为是同一人

# 初始化 WebRTC VAD
import webrtcvad

vad = webrtcvad.Vad()
vad.set_mode(VAD_MODE)


def extract_chinese_and_convert_to_pinyin(input_string):
    """
    提取字符串中的汉字，并将其转换为拼音。

    :param input_string: 原始字符串
    :return: 转换后的拼音字符串
    """
    # 使用正则表达式提取所有汉字
    chinese_characters = re.findall(r"[\u4e00-\u9fa5]", input_string)
    # 将汉字列表合并为字符串
    chinese_text = "".join(chinese_characters)

    # 转换为拼音
    pinyin_result = pinyin(chinese_text, style=Style.NORMAL)
    # 将拼音列表拼接为字符串
    pinyin_text = " ".join([item[0] for item in pinyin_result])

    return pinyin_text


# 音频录制线程
def audio_recorder():
    global audio_queue, recording_active
    global last_active_time, segments_to_save, last_vad_end_time

    audio_buffer = []
    frames_collected = 0
    print("音频录制已开始（sounddevice）")

    def audio_callback(indata, frames, time_info, status):
        nonlocal audio_buffer, frames_collected
        global last_active_time, segments_to_save, last_vad_end_time

        if status:
            print("Audio status:", status)

        if not recording_active:
            raise sd.CallbackStop()

        # indata: float32 [-1.0, 1.0]
        audio_buffer.append(indata.copy())
        frames_collected += frames

        # 每 0.02 秒检测一次 VAD
        if frames_collected >= int(0.02 * AUDIO_RATE):
            audio_np = np.concatenate(audio_buffer, axis=0)

            # 转成 int16 bytes（保持原来的 VAD 接口）
            audio_int16 = (audio_np * 32767).astype(np.int16).tobytes()

            vad_result = check_vad_activity(audio_int16)

            if vad_result:
                print("检测到语音活动")
                last_active_time = time.time()
                segments_to_save.append((audio_int16, time.time()))
            else:
                pass
                # print("静音中...")

            audio_buffer.clear()
            frames_collected = 0

        # 检查无效语音时间
        if time.time() - last_active_time > NO_SPEECH_THRESHOLD:
            if segments_to_save and segments_to_save[-1][1] > last_vad_end_time:
                # save_audio_video()
                save_audio_only()
                last_active_time = time.time()

        time.sleep(0.01)

    with sd.InputStream(
        samplerate=AUDIO_RATE,
        channels=AUDIO_CHANNELS,
        dtype="float32",
        blocksize=CHUNK,
        callback=audio_callback,
    ):
        while recording_active:
            time.sleep(0.1)

    print("音频录制已停止")


# 检测 VAD 活动
# def check_vad_activity(audio_data):
#     # 将音频数据分块检测
#     num, rate = 0, 0.5
#     step = int(AUDIO_RATE * 0.02)  # 20ms 块大小
#     flag_rate = round(rate * len(audio_data) // step)

#     for i in range(0, len(audio_data), step):
#         chunk = audio_data[i : i + step]
#         if len(chunk) == step:
#             if vad.is_speech(chunk, sample_rate=AUDIO_RATE):
#                 num += 1

#     if num > flag_rate:
#         return True
#     return False


def check_vad_activity(audio_bytes: bytes) -> bool:
    """
    audio_bytes: int16 PCM, mono
    """
    frame_ms = 30  # webrtcvad 推荐
    bytes_per_sample = 2
    frame_size = int(AUDIO_RATE * frame_ms / 1000) * bytes_per_sample

    if len(audio_bytes) < frame_size:
        return False

    for i in range(0, len(audio_bytes) - frame_size + 1, frame_size):
        frame = audio_bytes[i : i + frame_size]
        if vad.is_speech(frame, AUDIO_RATE):
            return True

    return False


def save_audio_only():
    """
    只负责把 segments_to_save 中的音频保存为 wav 文件
    """
    global segments_to_save, last_vad_end_time, saved_intervals
    global audio_file_count, flag_sv_enroll, set_SV_enroll

    if not segments_to_save:
        return None

    # ===============================
    # 1. 生成输出路径
    # ===============================
    if flag_sv_enroll:
        # audio_output_path = os.path.join(set_SV_enroll, "enroll_0.wav")
        pass
    else:
        audio_file_count += 1
        audio_output_path = os.path.join(OUTPUT_DIR, f"audio_{audio_file_count}.wav")

    os.makedirs(os.path.dirname(audio_output_path), exist_ok=True)

    # ===============================
    # 2. 时间区间判断（防重复）
    # ===============================
    start_time = segments_to_save[0][1]
    end_time = segments_to_save[-1][1]

    if saved_intervals and saved_intervals[-1][1] >= start_time:
        print("当前片段与之前片段重叠，跳过保存")
        segments_to_save.clear()
        return None

    # ===============================
    # 3. 拼接音频
    # ===============================
    audio_frames = [seg[0] for seg in segments_to_save]

    if flag_sv_enroll:
        # 每段约 0.5 秒（与你前面逻辑一致）
        audio_length = 0.5 * len(segments_to_save)
        if audio_length < 3:
            print("声纹注册语音需大于 3 秒，请重新注册")
            segments_to_save.clear()
            return None

    # ===============================
    # 4. 保存 WAV
    # ===============================
    with wave.open(audio_output_path, "wb") as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(AUDIO_RATE)
        wf.writeframes(b"".join(audio_frames))

    print(f"音频已保存: {audio_output_path}")

    # ===============================
    # 5. 更新状态
    # ===============================
    saved_intervals.append((start_time, end_time))
    last_vad_end_time = end_time

    segments_to_save.clear()

    # 使用线程执行推理
    threading.Thread(target=Inference, args=(audio_output_path,)).start()

    return audio_output_path


def Inference(audio_path):
    """
    负责调用 ASR -> LLM -> TTS
    """
    global asr_client, llm_client, tts_client

    global flag_KWS, flag_KWS_used, set_KWS, failed_enable_kws_count

    global last_llm_time

    print(f"开始处理音频: {audio_path}")

    # ----- ASR -----
    try:
        asr_text = asr_client.recognize(audio_path).strip()
        # asr_text = asr_client.recognize(
        #     "/home/xuyao/chj/ws/ymbot/LLM_TTS/wavs/hello_qianwen.wav"
        # ).strip()
    except Exception as e:
        print(f"ASR 识别失败: {e}")
        return

    if not asr_text:
        print("ASR 未识别到有效文本")
        return
    print(f"ASR 识别结果: {asr_text}")

    # ----- 唤醒词检测 -----
    if time.time() - last_llm_time > NO_REACTIVE_KWS_THRESHOLD:
        print("长时间未与 LLM 交互，重置唤醒词状态")
        flag_KWS = 0

    # 判断是否启用唤醒词检测
    if flag_KWS_used and flag_KWS == 0:
        pinyin_text = extract_chinese_and_convert_to_pinyin(asr_text)
        print(f"转换为拼音: {pinyin_text}")

        if set_KWS in pinyin_text:
            print("检测到唤醒词，开始与模型对话")
            flag_KWS = 1
            last_llm_time = time.time()
            failed_enable_kws_count = 0
        else:
            print("未检测到唤醒词，忽略本次输入")
            flag_KWS = 0
            failed_enable_kws_count += 1
            if failed_enable_kws_count >= 2:
                tts_client.play_audio("./wavs/enable_kws.wav")
                failed_enable_kws_count = 0
            return

    # ----- LLM -----
    print("开始与模型对话...")
    llm_response = ""
    try:
        llm_response = llm_client.chat_response(asr_text)
        print(f"LLM 回复: {llm_response}")
    except Exception as e:
        print(f"LLM 对话失败: {e}")
        return

    if not llm_response:
        print("LLM 未生成有效响应")
        return

    # ----- TTS -----
    try:
        tts_client.speak(llm_response.strip())

        # 更新最近与 LLM 交互时间
        last_llm_time = time.time()

    except Exception as e:
        print(f"TTS 播放失败: {e}")
        return


if __name__ == "__main__":

    try:
        # 启动音频录制线程
        audio_thread = threading.Thread(target=audio_recorder)
        audio_thread.start()

        print("按 Ctrl+C 停止录制")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("停止录制中...")
        recording_active = False
        audio_thread.join()
        print("录制已停止")
