import os
import re
import wave
import sounddevice as sd
import numpy as np
import time
import threading
import yaml
import webrtcvad
from scipy.io.wavfile import write
from queue import Queue
from pypinyin import pinyin, Style

from asr.asrclient import ASRClient
from vllm_Qwen.llmclient import LLMClient
from cosyvoice.ttsplay import RealtimeTTSPlayer

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
print(f"当前文件目录: {current_dir}")
config_yaml_path = os.path.join(current_dir, "config", "config.yaml")
print(f"配置文件路径: {config_yaml_path}")


class ChatAssistant:
    def __init__(self, config_yaml: str):

        self.configs = None

        # 读取配置文件
        try:
            with open(config_yaml, "r", encoding="utf-8") as f:
                self.configs = yaml.safe_load(f)
                print(f"配置文件内容:\n{self.configs}")
        except Exception as e:
            print(f"读取配置文件失败: {e}")
            raise e

        self.asr_client = ASRClient(
            host=self.configs.get("ASR", {}).get("host", "http://192.168.50.125"),
            port=self.configs.get("ASR", {}).get("port", 2002),
            timeout=30,
        )
        self.llm_client = LLMClient(
            host=self.configs.get("LLM", {}).get("host", "http://192.168.50.125"),
            port=self.configs.get("LLM", {}).get("port", 8000),
        )
        self.tts_client = RealtimeTTSPlayer(
            host=self.configs.get("TTS", {}).get("host", "http://192.168.50.125"),
            port=self.configs.get("TTS", {}).get("port", 50000),
        )

        self.audio_rate = self.configs.get("Audio", {}).get("rate", 16000)
        self.audio_channels = self.configs.get("Audio", {}).get("channels", 1)
        self.chunk_size = self.configs.get("Audio", {}).get("chunk_size", 1024)

        self.vad_mode = self.configs.get("VAD", {}).get("mode", 3)
        self.output_dir = (
            current_dir + "/" + self.configs.get("VAD", {}).get("output_dir", "output")
        )
        os.makedirs(self.output_dir, exist_ok=True)
        self.no_speech_threshold = self.configs.get("VAD", {}).get(
            "no_speech_threshold", 0.5
        )
        self.reactive_kws_threshold = self.configs.get("VAD", {}).get(
            "reactive_kws_threshold", 30
        )
        self.min_recording_duration = self.configs.get("VAD", {}).get(
            "min_recording_duration", 1.0
        )
        self.max_recording_duration = self.configs.get("VAD", {}).get(
            "max_recording_duration", 10.0
        )
        self.vad = webrtcvad.Vad(self.vad_mode)

        self.set_kws = self.configs.get("KWS", {}).get("wake_word", "你好小白")
        self.set_kws_pinyin = self.configs.get("KWS", {}).get(
            "wake_word_pinyin", "ni hao xiao bai"
        )
        self.flag_kws_used = self.configs.get("KWS", {}).get("enable", True)
        self.flag_kws = 0  # 唤醒词检测标志
        self.failed_enable_kws_count = 0  # 连续未检测到唤醒词计数

        self.recording_active = True  # 当前是否处于录音状态
        self.segments_to_save = []  # 待保存的音频片段
        self.saved_intervals = []  # 已保存的时间区间
        self.last_active_time = time.time()  # 上次检测到有效语音的时间
        self.last_vad_end_time = 0  # 上次保存的 VAD 有效段结束时间
        self.last_llm_time = time.time()  # 上次与 LLM 交互的时间
        self.audio_file_count = 0

    def extract_chinese_and_convert_to_pinyin(self, input_string):
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

    def check_vad_activity(self, audio_bytes: bytes) -> bool:
        """
        audio_bytes: int16 PCM, mono
        """
        frame_ms = 30  # webrtcvad 推荐
        bytes_per_sample = 2
        frame_size = int(self.audio_rate * frame_ms / 1000) * bytes_per_sample

        if len(audio_bytes) < frame_size:
            return False

        for i in range(0, len(audio_bytes) - frame_size + 1, frame_size):
            frame = audio_bytes[i : i + frame_size]
            if self.vad.is_speech(frame, self.audio_rate):
                return True

        return False

    def save_audio_only(self):
        """
        只负责把 segments_to_save 中的音频保存为 wav 文件
        """
        if not self.segments_to_save:
            return None

        # ===============================
        # 2. 时间区间判断（防重复）
        # ===============================
        start_time = self.segments_to_save[0][1]
        end_time = self.segments_to_save[-1][1]

        # 检查是否与之前的片段重叠
        if self.saved_intervals and self.saved_intervals[-1][1] >= start_time:
            print("当前片段与之前片段重叠，跳过保存")
            self.segments_to_save.clear()
            return None

        # 检查录音时长是否满足要求
        recording_duration = end_time - start_time
        print(f"录音时长: {recording_duration:.2f} 秒")
        if recording_duration < self.min_recording_duration:
            print("录音时长过短，跳过保存")
            self.segments_to_save.clear()
            return None
        if recording_duration > self.max_recording_duration:
            print("录音时长过长，跳过保存")
            self.segments_to_save.clear()
            return None

        # ===============================
        # 1. 生成输出路径
        # ===============================
        # if self.flag_sv_enroll:
        #     # audio_output_path = os.path.join(set_SV_enroll, "enroll_0.wav")
        #     pass
        # else:
        self.audio_file_count += 1
        audio_output_path = os.path.join(
            self.output_dir, f"audio_{self.audio_file_count}.wav"
        )

        os.makedirs(os.path.dirname(audio_output_path), exist_ok=True)

        # ===============================
        # 3. 拼接音频
        # ===============================
        audio_frames = [seg[0] for seg in self.segments_to_save]

        # if self.flag_sv_enroll:
        #     # 每段约 0.5 秒（与你前面逻辑一致）
        #     audio_length = 0.5 * len(self.segments_to_save)
        #     if audio_length < 3:
        #         print("声纹注册语音需大于 3 秒，请重新注册")
        #         self.segments_to_save.clear()
        #         return None

        # ===============================
        # 4. 保存 WAV
        # ===============================
        with wave.open(audio_output_path, "wb") as wf:
            wf.setnchannels(self.audio_channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.audio_rate)
            wf.writeframes(b"".join(audio_frames))

        print(f"音频已保存: {audio_output_path}")

        # ===============================
        # 5. 更新状态
        # ===============================
        self.saved_intervals.append((start_time, end_time))
        self.last_vad_end_time = end_time

        self.segments_to_save.clear()

        # 使用线程执行推理
        threading.Thread(target=self.Inference, args=(audio_output_path,)).start()

        return audio_output_path

    # 音频录制线程
    def audio_recorder_thread(self):
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

            if not self.recording_active:
                raise sd.CallbackStop()

            # indata: float32 [-1.0, 1.0]
            audio_buffer.append(indata.copy())
            frames_collected += frames

            # 每 0.02 秒检测一次 VAD
            if frames_collected >= int(0.02 * self.audio_rate):
                audio_np = np.concatenate(audio_buffer, axis=0)

                # 转成 int16 bytes（保持原来的 VAD 接口）
                audio_int16 = (audio_np * 32767).astype(np.int16).tobytes()

                vad_result = self.check_vad_activity(audio_int16)

                if vad_result:
                    print("检测到语音活动")
                    self.last_active_time = time.time()
                    self.segments_to_save.append((audio_int16, time.time()))
                else:
                    pass
                    # print("静音中...")

                audio_buffer.clear()
                frames_collected = 0

            # 检查无效语音时间
            if time.time() - self.last_active_time > self.no_speech_threshold:
                if (
                    self.segments_to_save
                    and self.segments_to_save[-1][1] > self.last_vad_end_time
                ):
                    # save_audio_video()
                    self.save_audio_only()
                    self.last_active_time = time.time()
            time.sleep(0.01)

        with sd.InputStream(
            samplerate=self.audio_rate,
            channels=self.audio_channels,
            dtype="float32",
            blocksize=self.chunk_size,
            callback=audio_callback,
        ):
            while self.recording_active:
                time.sleep(0.1)

        print("音频录制已停止")

    def Inference(self, audio_path):
        """
        负责调用 ASR、LLM、TTS 完成一次完整的交互
        """
        print(f"开始处理音频: {audio_path}")

        # ----- ASR -----
        try:
            asr_text = self.asr_client.recognize(audio_path).strip()
        except Exception as e:
            print(f"ASR 识别失败: {e}")
            return

        if not asr_text:
            print("ASR 未识别到有效文本")
            return
        print(f"ASR 识别结果: {asr_text}")

        # ----- 唤醒词检测 -----
        if time.time() - self.last_llm_time > self.reactive_kws_threshold:
            print("长时间未与 LLM 交互，重置唤醒词状态")
            self.flag_kws = 0

        # 判断是否启用唤醒词检测
        if self.flag_kws_used and self.flag_kws == 0:
            pinyin_text = self.extract_chinese_and_convert_to_pinyin(asr_text)
            print(f"转换为拼音: {pinyin_text}")

            if self.set_kws_pinyin in pinyin_text:
                print("检测到唤醒词，开始与模型对话")
                self.flag_kws = 1
                self.last_llm_time = time.time()
                self.failed_enable_kws_count = 0
            else:
                print("未检测到唤醒词，忽略本次输入")
                self.flag_kws = 0
                self.failed_enable_kws_count += 1
                if self.failed_enable_kws_count >= 2:
                    self.tts_client.play_audio(current_dir + "/wavs/enable_kws.wav")
                    self.failed_enable_kws_count = 0
                return

        # ----- LLM -----
        print("开始与模型对话...")
        llm_response = ""
        try:
            for token in self.llm_client.stream_chat(asr_text):
                print(token, end="", flush=True)
                llm_response += token
            print("\n")
        except Exception as e:
            print(f"LLM 对话失败: {e}")
            return

        if not llm_response:
            print("LLM 未生成有效响应")
            return

        # ----- TTS -----
        try:
            self.tts_client.speak(llm_response.strip())

            # 更新最近与 LLM 交互时间
            self.last_llm_time = time.time()

        except Exception as e:
            print(f"TTS 播放失败: {e}")
            return


if __name__ == "__main__":

    assistant = ChatAssistant(
        config_yaml=config_yaml_path,
    )

    print("ChatAssistant 初始化完成")

    try:
        # 启动音频录制线程
        recorder_thread = threading.Thread(
            target=assistant.audio_recorder_thread, daemon=True
        )
        recorder_thread.start()

        print("按 Ctrl+C 停止程序")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("停止录音...")
        assistant.recording_active = False
        recorder_thread.join()
        print("程序已退出")
