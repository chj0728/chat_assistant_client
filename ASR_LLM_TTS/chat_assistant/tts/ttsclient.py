import time
from typing import Any, Optional, Self

from logger import logger

from .tts_local import LocalTTSBackend
from .tts_remote import RemoteTTSBackend
from .ttsbase import TTSBase


class TTSClient(TTSBase):
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
        tts_server_type = config.get("tts_server_type", config.get("type", "tts_local"))
        remote_host = config.get("host", "dashscope.aliyuncs.com")
        remote_port = config.get("port")
        remote_scheme = config.get("remote_scheme", "wss")
        remote_path = config.get("remote_path", "/api-ws/v1/realtime")
        remote_url = config.get("remote_url")
        if remote_url is None:
            if remote_port:
                remote_url = (
                    f"{remote_scheme}://{remote_host}:{remote_port}{remote_path}"
                )
            else:
                remote_url = f"{remote_scheme}://{remote_host}{remote_path}"

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
            "api_key": config.get("api_key"),
            "model": config.get("model", "qwen3-tts-flash-realtime"),
            "remote_url": remote_url,
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
            host=host,
            port=port,
            timeout_sec=timeout_sec,
            sample_rate=sample_rate,
            channels=channels,
            chunk_size=chunk_size,
            buffer_size=buffer_size,
            playback_dtype=playback_dtype,
            playback_start_delay_sec=playback_start_delay_sec,
        )

        self.speaker_id = speaker_id
        self.speed = speed
        self.use_websocket = use_websocket
        self.ws_path = ws_path
        self.ws_ping_interval = ws_ping_interval
        self.ws_ping_timeout = ws_ping_timeout

        self.tts_server_type = tts_server_type
        self.voice = voice or voice_type or "Cherry"
        self.voice_type = self.voice
        self.api_key = api_key
        self.model = model
        self.remote_url = (
            remote_url or "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )
        self.remote_mode = remote_mode

        self._backend: Any = self._create_backend()

    def _initialize_runtime_components(self) -> None:
        self.stream = self.__create_output_stream()
        self.stream.start()
        self.tts_thread = self.__start_tts_worker()
        self.__initialize_websocket_if_needed()

    def _create_backend(self):
        if self.tts_server_type == "tts_remote":
            return RemoteTTSBackend(self)
        return LocalTTSBackend(self)

    def _initialize_backend_if_needed(self) -> None:
        self.__initialize_websocket_if_needed()

    def _start_tts_worker(self):
        return self.__start_tts_worker()

    def _close_backend_runtime(self) -> None:
        if self._backend is not None:
            self._backend.close_runtime()

    def _build_http_url(self, path: str) -> str:
        return f"http://{self.host}:{self.port}{path}"

    @classmethod
    def from_config(cls, config: dict) -> Self:
        return cls(**cls._build_init_kwargs_from_config(config))

    def reset_from_config(self, config: dict) -> None:
        self.stop()
        self._apply_init_kwargs(**self._build_init_kwargs_from_config(config))
        self._initialize_runtime_components()

    def generate_wav(self, text, filename) -> bool:
        if self.tts_server_type == "tts_remote":
            return self._backend.generate_wav(text, filename)

        try:
            with self.__request_stream(text, data_type="wav") as resp:
                resp.raise_for_status()

                if "audio" not in resp.headers.get("Content-Type", ""):
                    logger.error("返回不是音频")
                    logger.error(resp.text)
                    return False

                with open(filename, "wb") as f:
                    f.write(resp.content)
            return True

        except Exception as e:
            logger.error(f"TTS 请求失败: {e}")
            return False

    def change_preset(self, preset):
        self.voice = preset
        self.voice_type = preset
        if self.tts_server_type == "tts_remote":
            self._backend.change_voice(preset)

    def __create_output_stream(self):
        return self._create_output_stream()

    def __start_tts_worker(self):
        return self._backend.start_tts_worker()

    def __initialize_websocket_if_needed(self) -> None:
        self._backend.initialize_if_needed()

    def __request_stream(self, text: str, data_type: str):
        if self.tts_server_type != "tts_local":
            raise RuntimeError("远端 TTS 不支持通过本地 HTTP 接口请求音频流")
        return self._backend.request_stream(text, data_type)

    def __close_ws_runtime(self):
        self._close_backend_runtime()

    def stop(self):
        self._stop_event.set()
        self.interrupt()
        self.__close_ws_runtime()
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
        if self.tts_thread is not None:
            self.tts_thread.join(timeout=3)


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
