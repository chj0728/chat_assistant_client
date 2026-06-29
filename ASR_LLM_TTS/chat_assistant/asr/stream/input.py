import threading
import time
import wave
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
import webrtcvad
from logger import logger

from ..asr_backend_context import ASRBackendContext
from .protocol import InputStreamProtocol


class InputStream(InputStreamProtocol):
    def __init__(
        self,
        asr_backend_context: ASRBackendContext,
        device: int | str | None = None,
        **kwargs,
    ) -> None:
        self.asr_backend_context = asr_backend_context
        self.device = device

        self.recording_active = False
        self.segments_to_save = []
        self.pre_recording_buffer = deque()
        self.saved_intervals = []
        self.last_active_time = time.time()
        self.last_vad_end_time = time.time()

        self.input_stream = None  # 实际的音频输入流对象
        self.recorder_thread = threading.Thread(
            target=self.input_stream_thread, daemon=True
        )

        self.initialize_audio_settings(**kwargs)

        self.initialize_vad_settings(**kwargs)

    def initialize_audio_settings(self, **kwargs) -> None:
        """根据配置参数初始化音频相关设置，包括采样率、通道数、音频块大小等。"""
        audio_cfg = kwargs.get("Audio", {})

        self.enable = audio_cfg.get("enable", False)

        self.samplerate = audio_cfg.get("samplerate", 16000)
        self.channels = audio_cfg.get("channels", 1)
        self.chunk_duration_ms = audio_cfg.get("chunk_duration_ms", 20)
        self.audio_file_count = 0
        self.max_file_count = audio_cfg.get("max_file_count", 20)

        self.chunk_frames = int(self.samplerate * self.chunk_duration_ms / 1000)
        self.chunk_bytes = self.chunk_frames * 2
        valid_frame_bytes = {
            int(self.samplerate * ms / 1000) * 2 for ms in (10, 20, 30)
        }
        if self.chunk_bytes not in valid_frame_bytes:
            logger.warning("chunk_duration_ms 设置不合适，已调整为 20 ms 对应的字节数")
            self.chunk_duration_ms = 20
            self.chunk_frames = int(self.samplerate * self.chunk_duration_ms / 1000)
            self.chunk_bytes = self.chunk_frames * 2

    def initialize_vad_settings(self, **kwargs) -> None:
        """根据配置参数初始化 VAD 相关设置，包括 VAD 模式、无语音阈值、分贝阈值、最小/最大录音时长、静音持续时长等。"""
        vad_cfg = kwargs.get("VAD", {})

        self.vad_mode = vad_cfg.get("vad_mode", vad_cfg.get("mode", 3))
        self.output_dir = (
            Path(__file__).resolve().parent.parent / vad_cfg.get("output_dir", "output")
        ).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.no_speech_threshold = vad_cfg.get("no_speech_threshold", 0.5)
        self.decibel_threshold = vad_cfg.get("decibel_threshold", -40)
        self.min_recording_duration = vad_cfg.get("min_recording_duration", 1.0)
        self.max_recording_duration = vad_cfg.get("max_recording_duration", 10.0)
        self.pause_duration = vad_cfg.get("pause_duration", 1.5)
        self.pre_recording_buffer_duration = vad_cfg.get(
            "pre_recording_buffer_duration", 0.5
        )
        self.vad = webrtcvad.Vad(self.vad_mode)

    def start(self) -> None:
        """启动音频输入流，准备好接收和处理音频数据。"""

        if not self.enable:
            logger.warning("音频采集模块未启用")
            return

        if self.recording_active:
            logger.warning("录音线程已在运行，忽略重复启动请求")
            return

        self.segments_to_save = []
        self.pre_recording_buffer.clear()
        self.saved_intervals = []
        self.last_active_time = time.time()
        self.last_vad_end_time = time.time()

        self.recording_active = True
        self.recorder_thread.start()
        logger.info("音频输入流线程已启动")

    def stop(self) -> None:
        """停止音频输入流，释放相关资源。"""

        if not self.recording_active:
            logger.info("音频输入流线程已停止")
            return

        self.recording_active = False

        if self.recorder_thread and self.recorder_thread.is_alive():
            self.recorder_thread.join()
            logger.info("音频输入流线程已停止")

    def close(self) -> None:
        """关闭音频输入流，彻底释放相关资源。"""
        if self.input_stream is not None:
            self.input_stream.close()
            self.input_stream = None

    def __reset_segment_state(self):
        """重置音频片段状态。"""
        self.segments_to_save.clear()

    def __append_pre_recording_buffer(self, audio_bytes: bytes, timestamp: float) -> None:
        """保存最近一小段历史音频，用于补齐有效录音开头。"""
        if self.pre_recording_buffer_duration <= 0:
            return

        self.pre_recording_buffer.append((audio_bytes, timestamp))
        while (
            self.pre_recording_buffer
            and timestamp - self.pre_recording_buffer[0][1]
            > self.pre_recording_buffer_duration
        ):
            self.pre_recording_buffer.popleft()

    def __build_audio_frames_with_pre_buffer(self) -> list[bytes]:
        """录音片段满足时长要求后，把片段开始前的缓冲音频补到开头。"""
        if not self.segments_to_save:
            return []

        start_time = self.segments_to_save[0][1]
        pre_buffer_frames = [
            audio_bytes
            for audio_bytes, timestamp in self.pre_recording_buffer
            if timestamp < start_time
        ]
        if pre_buffer_frames:
            pre_buffer_duration = sum(len(frame) for frame in pre_buffer_frames) / (
                2 * max(self.channels, 1) * self.samplerate
            )
            logger.info(f"补充录音开头缓冲: {pre_buffer_duration:.2f} 秒")

        return pre_buffer_frames + [seg[0] for seg in self.segments_to_save]

    def __check_vad_activity(self, audio_bytes: bytes) -> bool:
        """
        audio_bytes: int16 PCM, mono
        """
        # frame_ms = 20  # webrtcvad 推荐
        # bytes_per_sample = 2
        # frame_size = int(self.audio_rate * frame_ms / 1000) * bytes_per_sample

        if len(audio_bytes) < self.chunk_bytes:
            return False

        for i in range(0, len(audio_bytes) - self.chunk_bytes + 1, self.chunk_bytes):
            frame = audio_bytes[i : i + self.chunk_bytes]
            if self.vad.is_speech(frame, self.samplerate):
                return True

        return False

    def __calculate_decibel(self, audio_np: np.ndarray) -> float:
        """计算音频分贝值，避免对零取对数。"""
        if audio_np.size == 0:
            return float("-inf")
        rms = np.sqrt(np.mean(np.square(audio_np)))
        return 20 * np.log10(max(rms, 1e-10))

    def __float_to_pcm16(self, audio_np: np.ndarray) -> bytes:
        """将 float32 音频转换为 PCM16 字节流。"""
        # audio_clipped = np.clip(audio_np, -1.0, 1.0)
        # return (audio_clipped * 32767).astype(np.int16).tobytes()

        # audio_np: (N, 1) or (N,)
        if audio_np.ndim == 2:
            audio_np = audio_np[:, 0]  # ✅ 取 mono

        audio_clipped = np.clip(audio_np, -1.0, 1.0)
        return (audio_clipped * 32767).astype(np.int16).tobytes()

    def __finalize_pending_segments(self, timestamp: float) -> None:
        """在长时间静音后触发音频保存。"""

        # energy_instability = self.__compute_energy_instability()
        # # logger.info(f"能量不稳定性指标(标准差/均值): {energy_instability:.6f}")

        # # ====== 判定阈值 ======
        # if (
        #     energy_instability > self.energy_instability_threshold
        #     and self.energy_instability_check
        # ):
        #     logger.info(f"当前指标(标准差/均值): {energy_instability:.6f}")
        #     logger.info(f"阈值(标准差/均值): {self.energy_instability_threshold:.6f}")
        #     logger.warning("疑似多人说话，音频能量不稳定，放弃保存音频")
        #     self.__reset_segment_state()
        #     return

        # 有录音片段且距离上次 VAD 结束时间超过 pause_duration 则保存音频
        if (
            self.segments_to_save
            and self.segments_to_save[-1][1]
            > self.last_vad_end_time + self.pause_duration
        ):
            self.save_audio_only()
            self.last_active_time = timestamp
        else:
            logger.warning("缓冲时间内，跳过保存音频")

        # 重置状态
        self.__reset_segment_state()

    def input_stream_thread(self) -> None:
        """音频输入流线程函数，持续读取音频数据并将其放入 ASR 后端上下文的音频帧输入队列中。"""
        audio_buffer = []
        frames_collected = 0
        self.last_active_time = time.time()

        # 每收集 ≥ 200ms（或 ≥ 一个 chunk_frames）的音频，就做一次分析
        analysis_interval_frames = max(
            1, max(self.chunk_frames, int(0.20 * self.samplerate))
        )

        logger.info("音频录制已开始（sounddevice）")
        logger.info(f"单次回调音频帧数: {self.chunk_frames}")
        logger.info(f"单次回调音频时长: {self.chunk_frames / self.samplerate:.3f} 秒")
        logger.info(f"分析间隔音频帧数: {analysis_interval_frames}")
        logger.info(
            f"分析间隔时长: {analysis_interval_frames / self.samplerate:.3f} 秒"
        )

        def reset_buffer():
            nonlocal audio_buffer, frames_collected
            audio_buffer.clear()
            frames_collected = 0

        def audio_callback(indata, frames, time_info, status):
            nonlocal frames_collected

            if not self.recording_active:
                raise sd.CallbackStop()

            now = time.time()

            # if self.tts_client.is_active():
            #     # tts 播放中，代表模型正在说话
            #     # 更新 last_interface_time
            #     self.last_interface_time = now

            # indata: float32 [-1.0, 1.0]
            audio_buffer.append(indata.copy())
            frames_collected += frames

            # 累积足够的音频进行分析
            if frames_collected >= analysis_interval_frames:
                # 合并音频块
                audio_np = np.concatenate(audio_buffer, axis=0)
                # 转为 PCM16 字节流
                audio_bytes = self.__float_to_pcm16(audio_np)
                # 重置缓冲区
                reset_buffer()
                self.__append_pre_recording_buffer(audio_bytes, now)

                # === NEW: 计算 RMS 能量 ===
                # rms = np.sqrt(np.mean(audio_np**2) + 1e-8)
                # # logger.info(f"RMS 能量: {rms:.6f}")
                # self.energy_window.append(rms)
                # if len(self.energy_window) > self.max_energy_frames:
                #     # logger.info("能量窗口已满，移除最早的能量值")
                #     self.energy_window.pop(0)

                # 计算分贝
                decibel = self.__calculate_decibel(audio_np)

                ## 如果分贝低于阈值
                if decibel < self.decibel_threshold:
                    ### 静音时间超过 no_speech_threshold and 有待保存音频段 则保存音频段
                    if (
                        now - self.last_active_time > self.no_speech_threshold
                        and self.segments_to_save
                    ):
                        logger.info("静音时间超过阈值，收集历史音频段")
                        ### 保存末尾的音频段
                        self.segments_to_save.append((audio_bytes, now))
                        self.__finalize_pending_segments(now)

                    ### 否则，继续等待, 保存静音段，防止断句不准确
                    else:
                        if self.segments_to_save:
                            logger.info("静音时间未超过阈值，继续等待，保存静音段")
                            self.segments_to_save.append((audio_bytes, now))

                ## 分贝高于阈值，继续处理
                else:
                    ### 如果 检测 VAD 活动，则保存音频段
                    if self.__check_vad_activity(audio_bytes):
                        logger.info("检测到语音活动，分贝: {:.2f} dB".format(decibel))
                        self.last_active_time = now
                        self.segments_to_save.append((audio_bytes, now))

                ## 如果处于录音段内（已有数据） and 录音时长超过最大值，则保存音频段
                if self.segments_to_save and (
                    self.segments_to_save[-1][1] - self.segments_to_save[0][1]
                    > (self.max_recording_duration - 0.2)
                ):
                    logger.info(
                        f"录音时长超过最大值{self.max_recording_duration}秒，保存音频段"
                    )
                    # self.segments_to_save.append((audio_bytes, now))
                    self.__finalize_pending_segments(now)

        # ---------- 查询并列出所有可用音频输入设备 ----------
        devices = sd.query_devices()
        input_devices = [
            (idx, info)
            for idx, info in enumerate(devices)
            if info["max_input_channels"] > 0
        ]
        logger.info(f"共发现 {len(input_devices)} 个音频输入设备:")
        for idx, info in input_devices:
            logger.info(
                f"  [{idx}] {info['name']} "
                f"(max_input_channels={info['max_input_channels']}, "
                f"default_samplerate={info['default_samplerate']}, "
                f"hostapi={sd.query_hostapis(info['hostapi'])['name']})"
            )

        # 确定最终使用的设备
        if self.device is None:
            effective_device = sd.default.device[0]  # 0 = input
            if effective_device is not None and effective_device < len(devices):
                logger.info(
                    f"使用系统默认输入设备: [{effective_device}] {devices[effective_device]['name']}"
                )
            else:
                logger.info("使用 sounddevice 自动选择的默认设备")
        else:
            effective_device = self.device
            if isinstance(self.device, int) and self.device < len(devices):
                logger.info(
                    f"使用指定输入设备: [{self.device}] {devices[self.device]['name']}"
                )
            else:
                logger.info(f"使用指定输入设备: {self.device}")
        # ----------------------------------------------------

        with sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.chunk_frames,
            callback=audio_callback,
            device=effective_device,
        ):
            logger.info("音频输入流已打开，等待录音...")
            while self.recording_active:
                time.sleep(0.1)

    def save_audio_only(self) -> None:
        """仅保存音频数据，不进行 ASR 识别。"""
        """
        将 PCM16 字节流片段 直接传给 ASR 识别，并保存为 WAV 文件。
        """
        if not self.segments_to_save:
            return None

        # ===============================
        # 缓冲时间判断
        # ===============================
        current_time = time.time()
        if current_time - self.last_vad_end_time < self.pause_duration:
            logger.warning("缓冲时间内，跳过保存音频")
            self.segments_to_save.clear()
            return None

        # ===============================
        # 2. 时间区间判断（防重复）
        # ===============================
        start_time = self.segments_to_save[0][1]
        end_time = self.segments_to_save[-1][1]

        # 检查是否与之前的片段重叠
        if self.saved_intervals and self.saved_intervals[-1][1] >= start_time:
            logger.warning("当前片段与之前片段重叠，跳过保存")
            self.segments_to_save.clear()
            return None

        # 检查录音时长是否满足要求
        recording_duration = end_time - start_time
        # print(f"录音时长: {recording_duration:.2f} 秒")
        logger.info(f"录音时长: {recording_duration:.2f} 秒")
        if recording_duration < self.min_recording_duration:
            logger.warning("录音时长过短，跳过保存")
            self.segments_to_save.clear()
            return None
        if recording_duration > self.max_recording_duration:
            logger.warning("录音时长过长，跳过保存")
            self.segments_to_save.clear()
            return None

        # ===============================
        # 1. 生成输出路径 ,循环保存最近 self.max_file_count 条音频
        # ===============================
        self.audio_file_count = (self.audio_file_count % self.max_file_count) + 1
        audio_output_path = self.output_dir / f"audio_{self.audio_file_count}.wav"

        # ===============================
        # 3. 拼接音频
        # ===============================
        audio_frames = self.__build_audio_frames_with_pre_buffer()

        self.asr_backend_context.audio_frames_queue.put(b"".join(audio_frames))

        # # 直接将 PCM16 字节流传给 ASR 识别
        # ## 如果交互有效，则保存音频文件
        # if self._run_inference_sync(audio_frames=audio_frames):
        #     # if self.Inference(audio_frames=audio_frames):

        # ===============================
        # 4. 保存 WAV
        # ===============================
        with wave.open(str(audio_output_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.samplerate)
            wf.writeframes(b"".join(audio_frames))
        logger.info(f"保存音频文件: {audio_output_path}")

        # # ===============================
        # # 5. 更新状态
        # # ===============================
        self.saved_intervals.append((start_time, end_time))
        self.last_vad_end_time = end_time
        # 2023-11-01 17:00:00 更新 VAD 结束时间: 1700000000.000
        formatted_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.last_vad_end_time)
        )
        logger.info(f"更新 VAD 结束时间: {formatted_time}")

        self.segments_to_save.clear()

        # # 使用线程执行推理
        # # temp_audio_output_path = "/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/tts/intro.wav"
        # # threading.Thread(target=self.Inference, args=(audio_output_path,)).start()
        # # 直接调用函数
        # # self.Inference(audio_frames=audio_frames, audio_path=str(audio_output_path))

        # return audio_output_path
