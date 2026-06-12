import os
import time
from typing import Optional

from dotenv import load_dotenv
from logger import logger

from .backend import TTSBackend
from .backend_context import TTSBackendContext
from .base import MyTTSClientBase, TTSClientBase
from .runtimes.qwen import QwenTTSRuntime
from .runtimes.sherpa import SherpaTTSRuntime

load_dotenv()


# --------------------- 阿里云 DashScope API Key 配置说明 ---------------------
# 1. 获取 API Key：访问 https://help.aliyun.com/zh/model-studio/get-api-key 获取 API Key。
# 2. 配置 API Key：有两种方式配置 API Key：
#    a. 环境变量：将 API Key 设置为环境变量 DASHSCOPE_API_KEY，例如在 Linux/MacOS 终端执行 export DASHSCOPE_API_KEY=你的APIKey，或在 Windows 命令提示符执行 set DASHSCOPE_API_KEY=你的APIKey。
#    b. 在 .env 文件中添加一行 DASHSCOPE_API_KEY=你的APIKey，并确保在代码中使用 load_dotenv() 加载环境变量。
# --------------------- 阿里云 DashScope API Key 配置说明 ---------------------
def GET_DASHSCOPE_API_KEY() -> Optional[str]:
    return os.environ.get("DASHSCOPE_API_KEY", "").strip()


class TTSClient(TTSClientBase):
    def __init__(
        self,
        host,
        port,
        timeout_sec: float = 30.0,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 2048,
        buffer_size: int = 4096,
        speaker_id: int = 0,
        speed: float = 1.0,
        use_websocket: bool = False,
        ws_path: str = "/ws/api/tts",
        ws_ping_interval: Optional[float] = None,
        ws_ping_timeout: Optional[float] = None,
        playback_start_delay_sec: float = 0.0,
        tts_server_type: str = "tts_local",
        voice: Optional[str] = None,
        voice_type: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "qwen3-tts-flash-realtime",
        remote_url: Optional[str] = None,
        remote_mode: str = "commit",
    ):
        self._apply_init_kwargs(
            host=host,
            port=port,
            timeout_sec=timeout_sec,
            sample_rate=sample_rate,
            channels=channels,
            chunk_size=chunk_size,
            buffer_size=buffer_size,
            speaker_id=speaker_id,
            speed=speed,
            use_websocket=use_websocket,
            ws_path=ws_path,
            ws_ping_interval=ws_ping_interval,
            ws_ping_timeout=ws_ping_timeout,
            playback_start_delay_sec=playback_start_delay_sec,
            tts_server_type=tts_server_type,
            voice=voice,
            voice_type=voice_type,
            api_key=api_key,
            model=model,
            remote_url=remote_url,
            remote_mode=remote_mode,
        )
        self._initialize_runtime_components()

    @staticmethod
    def _build_init_kwargs_from_config(config: dict) -> dict:
        tts_server_type = config.get("tts_server_type", "tts_local")
        return {
            "host": config.get("host", "192.168.10.101"),
            "port": config.get("port", 50000),
            "timeout_sec": config.get("timeout_sec", 30),
            "sample_rate": config.get("sample_rate", 16000),
            "channels": config.get("channels", 1),
            "chunk_size": config.get("chunk_size", 2048),
            "buffer_size": config.get("buffer_size", 4096),
            "speaker_id": config.get("speaker_id", 0),
            "speed": config.get("speed", 1.0),
            "use_websocket": config.get("use_websocket", False),
            "ws_path": config.get("ws_path", "/ws/api/tts"),
            "ws_ping_interval": config.get("ws_ping_interval"),
            "ws_ping_timeout": config.get("ws_ping_timeout"),
            "playback_start_delay_sec": config.get("playback_start_delay_sec", 0.0),
            "tts_server_type": tts_server_type,
            "voice": config.get("voice", config.get("voice_type", "Cherry")),
            "voice_type": config.get("voice_type", config.get("voice", "Cherry")),
            "api_key": config.get("api_key", GET_DASHSCOPE_API_KEY()),
            "model": config.get("model", "qwen3-tts-flash-realtime"),
            "remote_url": config.get(
                "remote_url", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
            ),
            "remote_mode": config.get("remote_mode", "commit"),
        }

    def _apply_init_kwargs(
        self,
        *,
        host,
        port,
        timeout_sec: float = 30.0,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 2048,
        buffer_size: int = 4096,
        speaker_id: int = 0,
        speed: float = 1.0,
        use_websocket: bool = False,
        ws_path: str = "/ws/api/tts",
        ws_ping_interval: Optional[float] = None,
        ws_ping_timeout: Optional[float] = None,
        playback_start_delay_sec: float = 0.0,
        tts_server_type: str = "tts_local",
        voice: Optional[str] = None,
        voice_type: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "qwen3-tts-flash-realtime",
        remote_url: Optional[str] = None,
        remote_mode: str = "commit",
    ) -> None:
        playback_dtype = "int16" if tts_server_type == "tts_remote" else "float32"

        self._apply_base_init_kwargs(
            sample_rate=sample_rate,
            channels=channels,
            chunk_size=chunk_size,
            buffer_size=buffer_size,
            playback_dtype=playback_dtype,
            playback_start_delay_sec=playback_start_delay_sec,
        )

        self.host = host
        self.port = port
        self.timeout_sec = timeout_sec
        self.tts_server_type = tts_server_type

        ############## Sherpa TTS 配置项 ##############
        self.speaker_id = speaker_id
        self.speed = speed
        self.use_websocket = use_websocket
        self.ws_path = ws_path
        self.ws_ping_interval = ws_ping_interval
        self.ws_ping_timeout = ws_ping_timeout

        ############# Qwen TTS 配置项 #############
        self.voice = voice or voice_type or "Cherry"
        self.voice_type = self.voice
        self.api_key = api_key
        self.model = model
        self.remote_url = (
            remote_url or "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )
        self.remote_mode = remote_mode

    def _initialize_runtime_components(self) -> None:

        self.output_stream = self._create_output_stream()
        self.output_stream.start()

        self.tts_backend = self._create_backend(self._create_backend_context())
        self.tts_backend.on_start()

    def _create_backend_context(self) -> TTSBackendContext:

        return TTSBackendContext(
            host=self.host,
            port=self.port,
            timeout=self.timeout_sec,
            sample_rate=self.sample_rate,
            channels=self.channels,
            chunk_size=self.chunk_size,
            text_queue=self.text_queue,
            audio_queue=self.audio_queue,
            stop_event=self._stop_event,
            interrupt_event=self._interrupt_event,
            speaker_id=self.speaker_id,
            speed=self.speed,
            use_websocket=self.use_websocket,
            ws_path=self.ws_path,
            ws_ping_interval=self.ws_ping_interval,
            ws_ping_timeout=self.ws_ping_timeout,
            voice=self.voice,
            api_key=self.api_key,
            model=self.model,
            remote_url=self.remote_url,
            remote_mode=self.remote_mode,
        )

    def _create_backend(self, context: TTSBackendContext) -> TTSBackend:
        if self.tts_server_type == "tts_remote":
            runtime = QwenTTSRuntime(context)
            return TTSBackend(
                context=context,
                runtime=runtime,
                worker_thread_name="tts-remote-worker",
                request_error_log_prefix="远端 TTS 请求失败",
                transfer_elapsed_log_label="远端 TTS 音频传输耗时",
            )

        runtime = SherpaTTSRuntime(context)
        return TTSBackend(
            context=context,
            runtime=runtime,
            worker_thread_name="tts-local-worker",
            request_error_log_prefix="本地 TTS 请求失败",
            transfer_elapsed_log_label="本地 TTS 音频传输耗时",
        )

    @classmethod
    def from_config(cls, config: dict) -> "TTSClient":
        return cls(**cls._build_init_kwargs_from_config(config))

    def reset_from_config(self, config: dict) -> None:
        self.stop()
        self._apply_init_kwargs(**self._build_init_kwargs_from_config(config))
        self._initialize_runtime_components()

    def generate_wav(self, text, filename) -> bool:
        return self.tts_backend.generate_wav(text, filename)

    def change_voice(self, voice: str) -> None:
        self.voice = voice
        self.voice_type = voice
        self.tts_backend.change_voice(voice)

    def stop(self):

        self._stop_event.set()

        self.interrupt()

        # 关闭音频输出流
        if self.output_stream is not None:
            self.output_stream.stop()
            self.output_stream.close()

        # 关闭 TTS 后端运行时，确保所有资源都被正确释放
        self.tts_backend.on_stop()


class MyTTSClient(MyTTSClientBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def build_init_kwargs_from_config(config: dict) -> dict:
        # tts_kwargs = config.get("TTS", {})
        return config

    @classmethod
    def from_config(cls, config: dict) -> "MyTTSClient":
        init_kwargs = cls.build_init_kwargs_from_config(config)
        return cls(**init_kwargs)

    def reset_from_config(self, config: dict) -> None:

        self.tts_backend.on_stop()

        init_kwargs = self.build_init_kwargs_from_config(config)
        self.__init__(**init_kwargs)


if __name__ == "__main__":
    from config import load_config, reload_config

    configs = load_config()

    tts_server_type = configs.get("tts_server", ["tts_local"])[0]
    logger.info(f"选择的 TTS 服务器类型: {tts_server_type}")
    tts_cfg = dict(configs.get(tts_server_type, {}))
    tts_cfg["tts_server_type"] = tts_server_type
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
    tts_server_type = configs.get("tts_server", ["tts_local"])[0]
    logger.info(f"选择的 TTS 服务器类型: {tts_server_type}")
    tts_cfg = dict(configs.get(tts_server_type, {}))
    tts_cfg["tts_server_type"] = tts_server_type

    tts_client.reset_from_config(tts_cfg)

    tts_client.speak("你好，这是一段通过 WebSocket 接收的测试语音。")
    time.sleep(2)
    while tts_client.is_active():
        time.sleep(1)
    logger.info("WebSocket 播放完成")
    time.sleep(2)
    logger.info("TTS 客户端测试完成")


__all__ = ["GET_DASHSCOPE_API_KEY", "TTSClient"]
