from typing import Any

import requests
from logger import logger

from ..backend_context import TTSBackendContext
from .protocol import TTSRuntimeProtocol


class VoxCPMCppTTSRuntime(TTSRuntimeProtocol):
    def __init__(self, context: TTSBackendContext, **kwargs) -> None:
        self.kwargs = kwargs
        self._context = context

        self.host = self.kwargs.get("host", "127.0.0.1")
        self.port = self.kwargs.get("port", 8080)
        self.base_url = self.kwargs.get("base_url") or f"http://{self.host}:{self.port}"
        self.speech_path = self.kwargs.get("speech_path", "/v1/audio/speech")
        self.health_path = self.kwargs.get("health_path", "/healthz")
        self.enable_health_check = self.kwargs.get("enable_health_check", False)

        self.api_key = self.kwargs.get("api_key", "")
        self.model = self.kwargs.get("model", "voxcpm")
        self.voice = self.kwargs.get("voice", "taiyi")
        self.speed = self.kwargs.get("speed", 1.0)
        self.chunk_size = self.kwargs.get("chunk_size", 2048)
        self.max_attempts = self.kwargs.get("max_attempts", 1)

        self.channels = self.kwargs.get("channels", 1)
        self.sample_rate = self.kwargs.get("sample_rate", 24000)
        self.dtype = self.kwargs.get("dtype", "int16")

        logger.info(
            "VoxCPMCppTTSRuntime 初始化完成，base_url=%s model=%s voice=%s sample_rate=%s",
            self.base_url,
            self.model,
            self.voice,
            self.sample_rate,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _payload(
        self, text: str, response_format: str, stream_format: str
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": response_format,
            "speed": self.speed,
            "stream_format": stream_format,
        }
        if self.max_attempts is not None:
            payload["max-attempts"] = self.max_attempts
        return payload

    def request_stream(
        self, text: str, response_format: str = "pcm", stream_format: str = "audio"
    ):
        return requests.post(
            self._build_url(self.speech_path),
            json=self._payload(text, response_format, stream_format),
            headers=self._headers(),
            timeout=self._context.timeout,
            stream=response_format == "pcm" and stream_format == "audio",
        )

    def _health_check(self) -> None:
        if not self.enable_health_check:
            return
        resp = requests.get(
            self._build_url(self.health_path),
            headers=self._headers(),
            timeout=self._context.timeout,
        )
        resp.raise_for_status()

    ######################## 实现 TTSRuntimeProtocol 接口方法 ########################
    def start(self) -> None:
        try:
            self._health_check()
        except Exception as e:
            logger.error(f"VoxCPM C++ TTS 健康检查失败: {e}")

    def stop(self) -> None:
        return

    def tts_infer(self, text: str) -> None:
        try:
            with self.request_stream(
                text, response_format="pcm", stream_format="audio"
            ) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    if (
                        self._context.stop_event.is_set()
                        or self._context.interrupt_event.is_set()
                    ):
                        return
                    if not chunk:
                        continue
                    self._context.audio_queue.put(chunk)
        except Exception as e:
            logger.error(f"VoxCPM C++ TTS 请求失败: {e}")

    def generate_wav(self, text: str, filename: str) -> bool:
        try:
            with self.request_stream(
                text, response_format="wav", stream_format="audio"
            ) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "")
                if (
                    "audio" in content_type
                    or content_type == "application/octet-stream"
                ):
                    with open(filename, "wb") as f:
                        f.write(resp.content)
                    return True

                logger.error("VoxCPM C++ TTS 返回不是音频: %s", resp.text)
                return False
        except Exception as e:
            logger.error(f"VoxCPM C++ TTS 生成 WAV 失败: {e}")
            return False

    def change_voice(self, voice: str) -> None:
        self.voice = voice
        logger.info("VoxCPM C++ TTS voice 已切换为: %s", self.voice)

    ##############################################################################
