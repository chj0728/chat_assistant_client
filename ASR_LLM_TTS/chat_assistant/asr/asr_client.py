import queue
import threading
from typing import Any, Optional

from logger import logger

from .asr_backend import ASRBackend
from .asr_backend_context import ASRBackendContext
from .runtimes import SherpaASRRuntime
from .runtimes.protocol import ASRRuntimeProtocol
from .stream.input import InputStream
from .stream.protocol import InputStreamProtocol


class ASRClientBase:
    """ASR客户端基类，定义了ASR客户端的基本接口和功能。"""

    def __init__(self, **kwargs) -> None:

        self.on_init(**kwargs)

        self.start()

    def on_init(self, **kwargs) -> None:
        """ASR客户端参数初始化方法。"""

        self.asr_server_type = kwargs.get(
            "asr_server_type", "asr_local"
        )  # ASR服务器类型，默认为 "asr_local"

        # self.asr_text_queue: queue.Queue[str] = queue.Queue(
        #     maxsize=10
        # )  # ASR识别结果文本队列，供外部使用
        self.audio_frames_queue: queue.Queue[bytes] = queue.Queue(
            maxsize=10
        )  # 音频帧数据队列，供ASR后端使用
        self.asr_voice_result_queue: queue.Queue[tuple[str, Any | None]] = queue.Queue(
            maxsize=10
        )  # ASR识别结果和声纹识别结果队列，供外部使用

        self.vision_id: Optional[str] = None

        self.stop_event = threading.Event()  # 停止事件，通知ASR后端停止运行
        self.interrupt_event = (
            threading.Event()
        )  # 中断事件，通知ASR后端立即停止当前识别并清空状态

        self.input_stream = self.create_input_stream(**kwargs)
        self.asr_runtime = self.create_asr_runtime(**kwargs)
        self.asr_backend = self.create_asr_backend(**kwargs)

    def start(self) -> None:
        """启动ASR客户端，初始化相关资源。"""
        self.asr_backend.start()

    def stop(self) -> None:
        """停止ASR客户端，释放相关资源。"""
        self.asr_backend.stop()

    def create_backend_context(self) -> ASRBackendContext:
        """创建ASR后端上下文对象。"""
        return ASRBackendContext(
            # asr_text_queue=self.asr_text_queue,
            audio_frames_queue=self.audio_frames_queue,
            asr_voice_result_queue=self.asr_voice_result_queue,
            vision_id=self.vision_id,
            stop_event=self.stop_event,
            interrupt_event=self.interrupt_event,
        )

    def create_input_stream(self, **kwargs) -> InputStreamProtocol:
        """创建ASR输入流对象。"""
        return InputStream(asr_backend_context=self.create_backend_context(), **kwargs)

    def create_asr_runtime(self, **kwargs) -> ASRRuntimeProtocol:
        """创建ASR运行时对象。"""
        return SherpaASRRuntime(
            asr_backend_context=self.create_backend_context(), **kwargs
        )

    def create_asr_backend(self, **kwargs) -> ASRBackend:
        """创建ASR后端对象。"""
        return ASRBackend(
            asr_backend_context=self.create_backend_context(),
            asr_runtime=self.create_asr_runtime(**kwargs),
            asr_input_stream=self.create_input_stream(**kwargs),
        )

    def recognize(self, wav_path: str) -> str:
        """识别指定 WAV 文件，返回识别结果文本。"""
        return self.asr_backend.recognize(wav_path)

    def recognize_frames(self, audio_frames) -> str:
        """识别指定音频帧数据，返回识别结果文本。"""
        return self.asr_backend.recognize_frames(audio_frames)

    async def async_recognize_frames(self, audio_frames) -> str:
        """异步识别指定音频帧数据，返回识别结果文本。"""
        return await self.asr_backend.async_recognize_frames(audio_frames)

    def update_vision_id(self, vision_id: str | None) -> None:
        """更新当前视觉ID，供ASR后端使用。"""
        # self.vision_id = vision_id
        self.asr_backend.update_vision_id(vision_id)
        # logger.info(f"ASR 客户端视觉ID已更新: {self.vision_id}")


class ASRClient(ASRClientBase):
    """ASR客户端实现类，基于ASRClientBase实现具体功能。"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    @staticmethod
    def build_init_kwargs_from_config(config: dict) -> dict:
        return config

    @classmethod
    def from_config(cls, config: dict) -> "ASRClient":
        init_kwargs = cls.build_init_kwargs_from_config(config)
        return cls(**init_kwargs)

    def reset_from_config(self, config: dict) -> None:

        self.stop()

        init_kwargs = self.build_init_kwargs_from_config(config)
        self.__init__(**init_kwargs)


if __name__ == "__main__":
    from config import load_config

    configs = load_config()

    asr_cfg = configs.get("ASR", {})
    asr_client = ASRClient.from_config(asr_cfg)

    try:
        while True:
            try:

                # asr_result = asr_client.asr_text_queue.get(timeout=0.1)
                asr_result, voice_id = asr_client.asr_voice_result_queue.get(
                    timeout=0.1
                )
                if asr_result:
                    logger.info(
                        f"ASR 识别结果: {asr_result}, 关联视觉ID: {asr_client.vision_id}, 关联声纹ID: {voice_id}"
                    )

            except queue.Empty:
                continue
    except KeyboardInterrupt:

        asr_client.stop()
