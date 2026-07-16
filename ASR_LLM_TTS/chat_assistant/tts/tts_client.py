import queue
import threading
import time
import wave

from logger import logger

try:
    from playsound3 import playsound
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    playsound = None

from .backend import MyTTSBackend
from .backend_context import TTSBackendContext
from .runtimes.protocol import TTSRuntimeProtocol
from .stream import (
    MyOutputStream,
)

INTERRUPT_GRACE_PERIOD_SEC = 0.1
LOCAL_AUDIO_STOP_WAIT_SEC = 0.1


class TTSClientBase:
    """组装 TTS runtime、输出流和后台 worker，并维护共享运行状态。"""

    def __init__(self, **kwargs) -> None:
        self.sound = None
        self.on_init(**kwargs)
        self.start()

    def on_init(self, **kwargs) -> None:
        """初始化配置、队列和共享上下文，并按依赖顺序创建组件。"""
        self._init_kwargs = kwargs

        self.primary_factory = kwargs.get("primary_factory", "qwen3_tts")
        self.fallback_factory = kwargs.get("fallback_factory", "sherpa_onnx_tts")
        self.timeout_sec = kwargs.get("timeout_sec", 10.0)

        self.playback_start_delay_sec = kwargs.get("playback_start_delay_sec", 0.0)
        self.sample_rate = kwargs.get(self.primary_factory, {}).get(
            "sample_rate", kwargs.get("sample_rate", 16000)
        )

        self.text_queue: queue.Queue[str] = queue.Queue()
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self.stop_event = threading.Event()
        self.interrupt_event = threading.Event()
        self.output_stream_started = False

        # 所有组件共享同一个 context，确保队列和中断状态只有一个来源。
        self.backend_context = self.create_backend_context()
        self.output_stream = self.create_output_stream()
        self.tts_runtime = self.create_tts_runtime()
        self.tts_backend = self.create_tts_backend()

    def start(self) -> None:
        """启动 TTS worker、runtime 和输出流。"""
        self.tts_backend.on_start()
        self.output_stream_started = True

    def stop(self) -> None:
        """停止 TTS 组件并释放输出资源。"""
        self.tts_backend.on_stop()
        self.output_stream_started = False

    def get_playback_config_value(self, server_type: str, key: str, default):
        """优先读取指定 TTS 工厂的播放配置，再回退到全局配置。"""
        return self._init_kwargs.get(server_type, {}).get(
            key, self._init_kwargs.get(key, default)
        )

    def create_backend_context(self) -> TTSBackendContext:
        """创建引用当前队列和事件的共享后端上下文。"""
        return TTSBackendContext(
            timeout=self.timeout_sec,
            text_queue=self.text_queue,
            audio_queue=self.audio_queue,
            stop_event=self.stop_event,
            interrupt_event=self.interrupt_event,
        )

    def create_output_stream(self, server_type: str | None = None) -> MyOutputStream:
        """按指定工厂的音频格式创建输出流，并复用共享上下文。"""
        active_server_type = server_type or self.primary_factory
        sample_rate = self.get_playback_config_value(
            active_server_type, "sample_rate", 16000
        )
        channels = self.get_playback_config_value(active_server_type, "channels", 1)
        dtype = self.get_playback_config_value(active_server_type, "dtype", "int16")
        buffer_size = self.get_playback_config_value(
            active_server_type, "buffer_size", 4096
        )

        playback_start_delay_sec = self.get_playback_config_value(
            active_server_type, "playback_start_delay_sec", 0.0
        )
        playback_hangover_sec = self.get_playback_config_value(
            active_server_type, "playback_hangover_sec", 0.0
        )
        playback_gain = self.get_playback_config_value(
            active_server_type, "playback_gain", 1.0
        )

        return MyOutputStream(
            context=self.backend_context,
            sample_rate=sample_rate,
            channels=channels,
            buffer_size=buffer_size,
            dtype=dtype,
            playback_start_delay_sec=playback_start_delay_sec,
            playback_hangover_sec=playback_hangover_sec,
            playback_gain=playback_gain,
        )

    def create_tts_runtime(self) -> TTSRuntimeProtocol:
        """创建带故障切换能力的 TTS runtime。"""
        from .runtimes.fallback import FallbackTTSRuntime

        return FallbackTTSRuntime(
            context=self.backend_context,
            primary_factory=lambda: self.create_factory_runtime(self.primary_factory),
            fallback_factory=lambda: self.create_factory_runtime(self.fallback_factory),
            fallback_switch_callback=lambda: self.switch_output_stream(
                self.fallback_factory
            ),
            primary_name=f"主 TTS 工厂: {self.primary_factory}",
            fallback_name=f"备用 TTS 工厂: {self.fallback_factory}",
        )

    def create_factory_runtime(self, factory_name: str) -> TTSRuntimeProtocol:
        """按工厂名称按需创建具体 runtime。"""
        if factory_name == "qwen3_tts":
            return self.create_qwen_tts_runtime()
        if factory_name == "sherpa_onnx_tts":
            return self.create_sherpa_tts_runtime()
        if factory_name == "voxcpm_cpp_tts":
            return self.create_voxcpm_cpp_tts_runtime()
        raise ValueError(f"未知的 TTS 工厂名称: {factory_name}")

    def create_qwen_tts_runtime(self) -> TTSRuntimeProtocol:
        from .runtimes.qwen_tts import QwenTTSRuntime

        return QwenTTSRuntime(
            self.backend_context, **self._init_kwargs.get("qwen3_tts", {})
        )

    def create_sherpa_tts_runtime(self) -> TTSRuntimeProtocol:
        from .runtimes.sherpa_onnx_tts import SherpaTTSRuntime

        return SherpaTTSRuntime(
            self.backend_context,
            **self._init_kwargs.get("sherpa_onnx_tts", {}),
        )

    def create_voxcpm_cpp_tts_runtime(self) -> TTSRuntimeProtocol:
        from .runtimes.voxcpm_cpp_tts import VoxCPMCppTTSRuntime

        return VoxCPMCppTTSRuntime(
            self.backend_context,
            **self._init_kwargs.get("voxcpm_cpp_tts", {}),
        )

    def switch_output_stream(self, server_type: str) -> None:
        """切换备用 runtime 时同步替换匹配音频格式的输出流。"""
        logger.info("正在切换 TTS 输出流格式: %s", server_type)
        old_output_stream = self.output_stream

        self.sample_rate = self.get_playback_config_value(
            server_type, "sample_rate", 16000
        )

        try:
            old_output_stream.stop()
        except Exception as exc:
            logger.warning("停止旧 TTS 输出流失败: %s", exc)

        try:
            old_output_stream.close()
        except Exception as exc:
            logger.warning("关闭旧 TTS 输出流失败: %s", exc)

        self.output_stream = self.create_output_stream(server_type)

        if hasattr(self, "tts_backend"):
            self.tts_backend.output_stream = self.output_stream

        if self.output_stream_started:
            self.output_stream.start()

    def create_tts_backend(self) -> MyTTSBackend:
        """使用已创建的 runtime、输出流和共享上下文组装后端。"""
        return MyTTSBackend(
            tts_backend_context=self.backend_context,
            tts_runtime=self.tts_runtime,
            output_stream=self.output_stream,
            worker_thread_name="tts-loop-worker",
            request_error_log_prefix="TTS 请求失败",
            transfer_elapsed_log_label="TTS 音频传输耗时",
        )

    @staticmethod
    def _drain_queue(target_queue: queue.Queue) -> None:
        """非阻塞地清空指定队列。"""
        while not target_queue.empty():
            try:
                target_queue.get_nowait()
            except queue.Empty:
                break

    def generate_wav(self, text: str, filename: str) -> bool:
        """生成 WAV 文件，适用于需要将合成的音频保存为本地文件的场景。"""
        return self.tts_backend.generate_wav(text, filename)

    def speak(self, text: str, interrupt: bool = True) -> None:
        """提交合成文本；默认先中断当前任务以便立即播放新内容。"""
        normalized_text = text.strip()
        if not normalized_text:
            return

        self.interrupt_event.clear()

        if interrupt:
            self.interrupt()
            self.interrupt_event.clear()

        self.text_queue.put(normalized_text)

    def interrupt(self) -> None:
        """停止本地播放、清空待处理队列并中断 runtime 和输出流。"""
        self.interrupt_event.set()

        self.stop_local_audio_playback()

        if not self.text_queue.empty() or not self.audio_queue.empty():
            logger.info("正在清空播放队列...")
        self._drain_queue(self.text_queue)
        self._drain_queue(self.audio_queue)

        self.tts_backend.interrupt()

    def is_active(self) -> bool:
        """返回后端、本地播放或待处理队列是否仍处于活跃状态。"""
        return (
            self.output_stream_active()
            or (self.sound is not None and self.sound.is_alive())
            or not self.text_queue.empty()
            or not self.audio_queue.empty()
        )

    def output_stream_active(self) -> bool:
        """判断输出流是否处于活跃状态。"""
        return self.tts_backend.is_active()

    def play_audio(self, file_path: str, block: bool = False) -> None:
        """使用本地播放器播放指定音频文件。"""
        try:
            if playsound is None:
                raise RuntimeError("playsound3 未安装，无法播放本地音频")

            self.stop_local_audio_playback()
            self.sound = playsound(file_path, block=block)
        except Exception as exc:
            logger.error(f"播放{file_path}失败: {exc}")

    def play_audio_from_pcm(self, pcm_bytes: bytes) -> None:
        """从 PCM 字节数据临时生成 WAV 文件并播放。"""
        with wave.open("temp.wav", "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)
        self.play_audio("temp.wav")

    def stop_local_audio_playback(self) -> None:
        """停止本地文件播放，并短暂等待播放器完成清理。"""
        if self.sound is not None and self.sound.is_alive():
            logger.info("正在停止当前播放的音频...")
            self.sound.stop()
            time.sleep(LOCAL_AUDIO_STOP_WAIT_SEC)

    def get_playback_start_delay_sec(self) -> float:
        """获取播放开始的延迟时间。"""
        return self.playback_start_delay_sec

    def wait_until_playback_starts(self, timeout_sec: float = 5.0) -> bool:
        """等待输出流进入播放状态。"""
        return self.tts_backend.wait_until_playback_starts(timeout_sec=timeout_sec)


class TTSClient(TTSClientBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def build_init_kwargs_from_config(config: dict) -> dict:
        """将 TTS 配置转换为构造参数。"""
        return config

    @classmethod
    def from_config(cls, config: dict) -> "TTSClient":
        init_kwargs = cls.build_init_kwargs_from_config(config)
        return cls(**init_kwargs)

    def reset_from_config(self, config: dict) -> None:
        """停止当前组件，并使用新配置完整重建客户端。"""
        self.stop()
        init_kwargs = self.build_init_kwargs_from_config(config)
        self.__init__(**init_kwargs)


if __name__ == "__main__":
    from config import load_config, reload_config

    configs = load_config()

    tts_cfg = dict(configs.get("TTS", {}))
    tts_client = TTSClient.from_config(tts_cfg)

    tts_client.speak("你好，这是一段测试语音。")
    time.sleep(1)
    while tts_client.is_active():
        time.sleep(1)
    logger.info("播放完成")

    tts_client.generate_wav(
        "你好，这是一段测试语音保存的语音合成示例。",
        "./wavs/example.wav",
    )
    logger.info("WAV 文件生成完成")

    time.sleep(3)

    configs = reload_config()
    tts_cfg = dict(configs.get("TTS", {}))
    tts_client.reset_from_config(tts_cfg)

    tts_client.speak("你好，这是一段通过 WebSocket 接收的测试语音。")
    time.sleep(2)
    while tts_client.is_active():
        time.sleep(1)
    logger.info("WebSocket 播放完成")
    time.sleep(2)
    logger.info("TTS 客户端测试完成")
