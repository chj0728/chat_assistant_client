import queue
import threading
from typing import Any

from logger import logger

from .asr_backend import ASRBackend
from .asr_backend_context import ASRAudioData, ASRBackendContext
from .runtimes import SherpaASRRuntime
from .runtimes.protocol import ASRRuntimeProtocol
from .stream.input import InputStream
from .stream.protocol import InputStreamProtocol


class ASRClientBase:
    """组装 ASR 输入流、运行时和后台工作线程，并提供统一入口。"""

    def __init__(self, **kwargs) -> None:
        self.on_init(**kwargs)
        self.start()

    def on_init(self, **kwargs) -> None:
        """初始化共享状态，并按依赖顺序创建三个 ASR 组件。"""
        self.asr_server_type = kwargs.get("asr_server_type", "asr_local")
        self.audio_data_queue: queue.Queue[tuple[ASRAudioData, str | None]] = (
            queue.Queue(maxsize=10)
        )
        self.result_data_queue: queue.Queue[tuple[str, Any | None, str | None]] = (
            queue.Queue(maxsize=10)
        )

        self.vision_id: str | None = None
        self.stop_event = threading.Event()
        self.interrupt_event = threading.Event()

        # 三个组件必须共享同一个上下文，否则 vision_id 等可变状态会分叉。
        self.backend_context = self.create_backend_context()
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
        """创建引用当前队列、事件和视觉 ID 的后端上下文。"""
        return ASRBackendContext(
            audio_data_queue=self.audio_data_queue,
            result_data_queue=self.result_data_queue,
            vision_id=self.vision_id,
            stop_event=self.stop_event,
            interrupt_event=self.interrupt_event,
        )

    def create_input_stream(self, **kwargs) -> InputStreamProtocol:
        """创建使用共享上下文的 ASR 输入流。"""
        return InputStream(asr_backend_context=self.backend_context, **kwargs)

    def create_asr_runtime(self, **kwargs) -> ASRRuntimeProtocol:
        """创建使用共享上下文的 ASR 运行时。"""
        return SherpaASRRuntime(asr_backend_context=self.backend_context, **kwargs)

    def create_asr_backend(self, **kwargs) -> ASRBackend:
        """使用已创建的输入流和运行时组装 ASR 后端。"""
        return ASRBackend(
            asr_backend_context=self.backend_context,
            asr_runtime=self.asr_runtime,
            asr_input_stream=self.input_stream,
            **kwargs,
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
        """同步更新客户端和共享后端上下文中的视觉 ID。"""
        self.vision_id = vision_id
        self.asr_backend.update_vision_id(vision_id)

    def save_tmp_wav(self) -> bool:
        """保存最近一次识别片段的临时 WAV 文件。"""
        return self.asr_backend.save_tmp_wav()


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
        """停止当前组件，并使用新配置完整重建客户端。"""
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
                asr_result, voice_id, audio_saved_path = (
                    asr_client.result_data_queue.get(timeout=0.1)
                )
                logger.info(
                    f"ASR 识别结果: {asr_result}, 关联视觉ID: {asr_client.vision_id}, "
                    f"关联声纹ID: {voice_id}, 音频保存路径: {audio_saved_path}"
                )
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        asr_client.stop()
