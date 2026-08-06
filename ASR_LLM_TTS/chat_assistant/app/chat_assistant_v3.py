import asyncio
import queue
import threading
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import asdict
from pathlib import Path
from queue import Empty, Full, Queue

import yaml
from asr import ASRClient
from config import load_config
from llm import LLMAgent
from logger import log_user_dialog, logger

from app.assistant_support import (
    MAX_QUEUE_SIZE,
    SPECIAL_WORD_MAP,
    AssistantState,
    AssistantTextProcessor,
    ComponentState,
    ResponseData,
)

CLIENT_OPERATION_ERRORS = (
    AttributeError,
    EOFError,
    LookupError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class ChatAssistant:
    def __init__(
        self,
        config_path: str | Path | None = None,
        dynamic_middlewares=None,
    ):
        self.config_path = (
            Path(config_path).expanduser().resolve() if config_path else None
        )
        self.configs = load_config(self.config_path) if self.config_path else {}
        self.dynamic_middlewares = dynamic_middlewares

        self.asr_text = ""
        self.llm_text = ""
        self.current_user_id = None
        self.current_user_name = None
        self.current_user_face_status = False
        self.audio_saved_path = None

        self.asr_text_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.llm_text_queue = Queue(maxsize=MAX_QUEUE_SIZE)

        # 储存解析的 用户姓名 队列
        self.resolved_user_names_queue = Queue(maxsize=MAX_QUEUE_SIZE)

        # 同时包括 asr_text 和 llm_text
        self.response_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.response_data = ResponseData()
        self.response_data.clear()

        self.worker_thread_active = False
        self.worker_thread: threading.Thread | None = None

        self.load_config_and_initialize()

    def _reset_interaction_state(self) -> None:
        """重置交互过程中累积的文本与队列状态。"""
        self.asr_text = ""
        self.llm_text = ""
        self.current_user_id = None
        self.current_user_name = None
        self.current_user_face_status = False
        self.asr_text_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.llm_text_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.response_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.resolved_user_names_queue = Queue(maxsize=MAX_QUEUE_SIZE)
        self.response_data = ResponseData()
        self.response_data.clear()
        self.audio_saved_path = None

    @staticmethod
    def _shutdown_component(component, component_name: str) -> None:
        """按组件暴露的 stop/close 接口释放运行时资源。"""
        if component is None:
            return

        for method_name in ("stop", "close"):
            method = getattr(component, method_name, None)
            if callable(method):
                try:
                    method()
                except CLIENT_OPERATION_ERRORS as exc:
                    logger.warning(f"释放 {component_name} 资源失败: {exc}")
                return

    def _shutdown_clients(self) -> None:
        """释放已创建的 ASR、LLM、TTS 客户端运行时资源。"""
        self._shutdown_component(getattr(self, "asr_client", None), "ASRClient")
        self._shutdown_component(getattr(self, "llm_client", None), "LLMAgent")
        self._shutdown_component(getattr(self, "tts_client", None), "TTSClient")

    def __push_queue(self, data_queue: Queue, value) -> None:
        """将最新文本加入有限队列，保持队列容量受控。"""
        try:
            data_queue.put_nowait(value)
        except Full:
            try:
                data_queue.get_nowait()
            except Empty:
                pass
            data_queue.put_nowait(value)

    def set_state(self, new_state: AssistantState) -> None:
        with self.state_lock:
            self.state = new_state

    def get_state(self) -> AssistantState:
        with self.state_lock:
            return self.state

    # 析构函数
    def __del__(self):
        """
        析构函数，释放资源
        """
        # logger.info("ChatAssistant 正在释放资源...")
        # self.stop()
        # # self._shutdown_clients()

        logger.info("ChatAssistant 资源已释放.")

    def start(self):
        """启动助手，进入主循环。"""

        if self.worker_thread_active:
            logger.warning("助手主线程已在运行，忽略重复启动请求")
            return

        self.worker_thread_active = True
        self.worker_thread = threading.Thread(
            target=self.__worker_thread_entry, daemon=True
        )
        self.worker_thread.start()

    def __worker_thread_entry(self):
        """线程入口：在线程内运行异步主循环。"""
        asyncio.run(self.__worker_thread_loop())

    async def __worker_thread_loop(self):
        """助手主线程循环，持续监听 ASR 和 LLM 文本队列，更新综合响应数据对象，并推送到响应队列。"""
        while self.worker_thread_active:

            self.__update_status()

            try:
                result_data = self.asr_client.result_data_queue.get(timeout=0.1)
                if result_data:
                    asr_result, voice_id, self.audio_saved_path = result_data
                    logger.info(f"asr_text: [{asr_result}]")
                    logger.info(f"voice_id: [{voice_id}]")
                    logger.info(f"audio_saved_path: [{self.audio_saved_path}]")
                    if asr_result:
                        await self.Inference(input_text=asr_result, voice_id=voice_id)

            except queue.Empty:
                continue

            await asyncio.sleep(0.01)

    def stop(self):
        """停止助手，释放资源。"""
        self.worker_thread_active = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
            logger.info("语音助手主线程已停止")
        self.worker_thread = None
        self.worker_thread_active = False

        # self._shutdown_clients()
        self.asr_client.stop()
        self.llm_client.stop()
        self.tts_client.stop()

    def load_config_and_initialize(self):
        self.configs = load_config()
        logger.debug("当前配置:\n%s", yaml.dump(self.configs, allow_unicode=True))

        self._initialize_clients()
        self._initialize_kws_settings()
        self._initialize_runtime_state()

    def reset(self, restart_recording: bool | None = None) -> None:
        """重置助手状态并按当前配置重新初始化所有运行时资源。"""

        self.stop()
        # self._shutdown_clients()
        self._reset_interaction_state()
        self.load_config_and_initialize()

        self.start()

    def _initialize_clients(self) -> None:
        self.asr_client = self._build_asr_client()
        self.llm_client = self._build_llm_client()
        self.tts_client = self._build_tts_client()

    def _build_asr_client(self) -> ASRClient:

        asr_cfg = self.configs.get("ASR", {})
        return ASRClient.from_config(config=asr_cfg)

    def _build_llm_client(self) -> LLMAgent:

        self.llm_stream_infer_enable = self.configs.get(
            "llm_stream_infer_enable", False
        )

        return LLMAgent.from_config(
            config=self.configs,
            dynamic_middlewares=self.dynamic_middlewares,
        )

    def _build_tts_client(self):

        tts_cfg = self.configs.get("TTS", {})

        # from tts import TTSClient

        # tts_server_type = tts_cfg.get("tts_server_type", "tts_local")
        # logger.info(f"选择的 TTS 服务器类型: {tts_server_type}")
        # return TTSClient.from_config(config=tts_cfg)

        from tts import TTSClient

        return TTSClient.from_config(config=tts_cfg)

    def _initialize_kws_settings(self) -> None:
        kws_cfg = self.configs.get("KWS", {})

        self.set_kws = kws_cfg.get("wake_word", "你好小特")
        self.kws_fuzzy_similarity_threshold = kws_cfg.get(
            "fuzzy_similarity_threshold", 0.78
        )

        self.word_map = SPECIAL_WORD_MAP
        self.text_processor = AssistantTextProcessor(
            wake_word=self.set_kws,
            fuzzy_similarity_threshold=self.kws_fuzzy_similarity_threshold,
            word_map=self.word_map,
        )

        self.set_kws_pinyin = self.text_processor.wake_word_pinyin
        self.kws_enabled = kws_cfg.get("enable", True)
        if self.kws_enabled:
            logger.info("唤醒词功能已启用")
            logger.info(f"设置的唤醒词: {self.set_kws}, 拼音: {self.set_kws_pinyin}")

        self.flag_kws = 0
        self.failed_enable_kws_count = 0
        self.failed_kws_counts = kws_cfg.get("failed_kws_counts", 2)
        self.failed_kws_threshold = kws_cfg.get("failed_kws_threshold", 30)
        self.reactive_kws_threshold = kws_cfg.get("reactive_kws_threshold", 100)
        self.last_failed_kws_time = 0

    def _initialize_runtime_state(self) -> None:

        self.last_llm_time = time.time()
        self.last_tts_time = time.time()
        self.last_interface_time = time.time()

        self.state = AssistantState.IDLE
        self.state_lock = threading.Lock()

        self.asr_client_state = self._initial_component_state("asr_enable")
        self.llm_agent_state = self._initial_component_state("llm_enable")
        self.tts_client_state = self._initial_component_state("tts_enable")

        self.enable_user_face_info = self.configs.get("ros_cfg", {}).get(
            "enable_user_face_info", False
        )

        self.enable_replace_special_characters = self.configs.get(
            "enable_replace_special_characters", False
        )
        self.enable_interrupt_tts = self.configs.get("enable_interrupt_tts", False)
        self.enable_interrupt_by_asr_face = self.configs.get(
            "enable_interrupt_by_asr_face", False
        )

    def _initial_component_state(self, config_key: str) -> ComponentState:
        logger.info(
            f"组件 {config_key} 初始状态: {'ACTIVE' if self.configs.get(config_key, False) else 'IDLE'}"
        )
        return (
            ComponentState.ACTIVE
            if self.configs.get(config_key, False)
            else ComponentState.IDLE
        )

    def __update_llm_text(self, llm_text, index=0):
        """更新 LLM 文本，并推送到队列。"""

        # 更新单个响应数据对象，并推送到单独的 LLM 文本队列
        self.__push_queue(self.llm_text_queue, [{"index": index, "text": llm_text}])

        # 更新综合响应数据对象，并推送到综合队列
        self.response_data.llm_text = llm_text
        self.__push_queue(self.response_queue, asdict(self.response_data))
        self.response_data.clear()

    def __update_status(self):
        """根据当前组件状态更新整体状态，并记录最后交互时间，需要循环调用以保持状态更新。
        - 如果 TTS 正在播放，认为模型正在说话，更新 last_interface_time。
        - 如果长时间未与 LLM 交互，重置 LLM 模块为 IDLE 状态。
        """
        if self.tts_client.is_active():
            # tts 播放中，代表模型正在说话
            # 更新 last_interface_time
            self.last_interface_time = time.time()

        # 判断是否需要重置唤醒词状态
        if (
            time.time() - self.last_interface_time > self.reactive_kws_threshold
            and self.kws_enabled
            and self.llm_agent_state != ComponentState.IDLE
        ):
            # self.flag_kws = 0
            # if self.llm_agent_state == LLMAgentState.ACTIVE:
            self.llm_agent_state = ComponentState.IDLE
            self.last_interface_time = time.time()
            logger.info("长时间未与 LLM 交互，重置 LLM 模块为 IDLE 状态")

    def _run_inference_sync(self, **kwargs) -> bool:
        """在同步调用栈中桥接执行异步 Inference。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.Inference(**kwargs))

        raise RuntimeError("不能在已运行的事件循环中同步调用 Inference")

    ############# 功能模块激活状态管理 #############
    def activate(self):
        """
        激活助手，进入 ACTIVE 状态
        """
        self.set_state(AssistantState.ACTIVE)

    def idle(self):
        """
        进入空闲状态
        """
        self.set_state(AssistantState.IDLE)

    def activate_asr_client(self):
        """
        激活 ASR Client，进入 ACTIVE 状态
        """
        self.asr_client_state = ComponentState.ACTIVE

    def deactivate_asr_client(self):
        """
        使 ASR Client 进入空闲状态
        """
        self.asr_client_state = ComponentState.IDLE

    def activate_llm_agent(self):
        """
        激活 LLM Agent，进入 ACTIVE 状态
        """
        self.llm_agent_state = ComponentState.ACTIVE
        self.last_interface_time = time.time()

    def deactivate_llm_agent(self):
        """
        使 LLM Agent 进入空闲状态
        """
        self.llm_agent_state = ComponentState.IDLE

    def activate_tts_client(self):
        """
        激活 TTS Client，进入 ACTIVE 状态
        """
        self.tts_client_state = ComponentState.ACTIVE

    def deactivate_tts_client(self):
        """
        使 TTS Client 进入空闲状态
        """
        self.tts_client_state = ComponentState.IDLE

    ###############################################

    ################# 业务功能接口 ##################
    def set_current_user_id(self, user_id: str | None):
        """
        设置当前用户 ID，LLM 推理时会携带该 ID 以支持个性化对话
        """
        self.current_user_id = (
            user_id.strip() if isinstance(user_id, str) and user_id.strip() else None
        )

        # 将当前用户 ID 更新到 ASR Client，以支持个性化识别
        self.asr_client.update_vision_id(self.current_user_id)

        logger.debug(f"当前用户 ID 已设置为: {self.current_user_id}")

    def set_current_user_info(self, user_id: str | None, user_name: str | None):
        """
        设置当前用户信息，包括 ID 和 Name
        """
        self.current_user_id = (
            user_id.strip() if isinstance(user_id, str) and user_id.strip() else None
        )
        self.current_user_name = (
            user_name.strip()
            if isinstance(user_name, str) and user_name.strip()
            else None
        )

        # 将当前用户ID更新到 ASR Client，以支持声纹识别
        self.asr_client.update_vision_id(self.current_user_id)

        logger.debug(
            f"当前用户信息已设置 - ID: {self.current_user_id}, Name: {self.current_user_name}"
        )

    def set_current_user_face_status(self, face_status: bool | None):
        """
        设置当前用户人脸识别状态
        """
        self.current_user_face_status = face_status
        logger.debug(f"当前用户在场状态已设置为: {self.current_user_face_status}")

    def generate_wav(self, text, output_path) -> bool:
        """
        负责调用 TTS 完成文本转语音，保存音频文件
        """
        logger.info("请求 TTS 生成语音文件中...")
        time_now = time.time()
        try:
            tts_result = self.tts_client.generate_wav(text, output_path)
            elapsed_time = time.time() - time_now
            logger.info(f"TTS 生成语音文件耗时: {elapsed_time:.2f} 秒")
            return tts_result
        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"TTS 生成语音文件失败: {e}")
            return False

    def play_audio(self, audio_path):
        """
        负责调用 TTS 播放音频文件
        """
        logger.info(f"开始播放音频文件: {audio_path}")
        try:
            self.tts_client.play_audio(audio_path, block=False)
            return True
        except CLIENT_OPERATION_ERRORS:
            return False

    def interrupt(self) -> bool:
        """
        负责中断 LLM（文本推理），TTS （包括音频播放，语音合成）后台输出
        """
        llm_interrupt_result = self.interrupt_llm()

        time.sleep(0.01)

        tts_interrupt_result = self.interrupt_tts()

        return llm_interrupt_result and tts_interrupt_result

    def interrupt_llm(self) -> bool:
        """
        负责中断 LLM（文本推理）后台输出
        """
        logger.info("正在打断 LLM 后台输出...")
        try:
            self.llm_client.interrupt()
            logger.info("LLM 后台输出已打断")
            return True
        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"打断 LLM 后台输出失败: {e}")
            return False

    def interrupt_tts(self) -> bool:
        """
        负责中断 TTS （包括音频播放，语音合成）后台输出
        """
        logger.info("正在打断 TTS 后台输出...")
        try:
            self.tts_client.interrupt()
            logger.info("TTS 后台输出已打断")
            return True
        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"打断 TTS 后台输出失败: {e}")
            return False

    def check_tts_status(self) -> bool:
        """
        检查 TTS 模块状态并根据当前状态决定是否继续播放

        Returns:
            bool: 如果可以继续播放返回 True，否则返回 False
        """
        # -------- 检查 TTS 模块状态 ----------
        if self.tts_client_state == ComponentState.IDLE:
            logger.warning("TTS 模块未激活，跳过TTS播放")
            self.last_interface_time = time.time()
            time.sleep(0.1)
            return False
        # -------- 检查 TTS 播放状态 如果正在播放且未启用打断功能，则跳过播放 -----------
        if self.tts_client.is_active() and not self.enable_interrupt_tts:
            logger.warning("语音播放中，未启用打断，跳过TTS播放")
            self.last_interface_time = time.time()
            return False
        # --------- 检查 TTS 播放状态，如果正在播放且启用了打断功能，则中断当前播放 -----------
        if self.tts_client.is_active() and self.enable_interrupt_tts:
            logger.info("语音播放中，启用了打断功能，准备中断播放")
            self.tts_client.interrupt()
            time.sleep(0.1)
            return True

        return True

    def check_tts_active(self) -> bool:
        """
        负责检查 TTS 播放状态
        """
        try:
            is_active = self.tts_client.is_active()
            return is_active
        except CLIENT_OPERATION_ERRORS:
            return False

    def asr_infer(self, audio_path: str | None = None, audio_frames=None):
        """
        负责调用 ASR 完成语音识别，支持音频文件路径或 PCM16 字节流输入
         - 如果同时提供了 audio_frames 和 audio_path，则优先使用 audio_frames 进行识别，以提高实时性和效率
         - 如果 audio_frames 为空且提供了 audio_path，则使用音频文件进行识别
         - 如果两者都未提供，则返回空字符串
         - 返回识别文本，失败时返回空字符串
         - 注意：如果同时提供了 audio_frames 和 audio_path，且 audio_frames 识别结果为空，则不会回退到 audio_path 进行识别，以保证流程的确定性和效率。
         - 如果需要在帧识别失败时回退到文件识别，可以在外部调用时先调用一次 asr_infer(audio_frames=...)，如果结果为空再调用一次 asr_infer(audio_path=...)。
        """
        logger.info("ASR 识别中...")
        time_now = time.time()
        try:
            if audio_frames is not None:
                asr_text = self.asr_client.recognize_frames(
                    audio_frames,
                    # sample_rate=self.audio_rate,
                    # channels=self.audio_channels,
                ).strip()

                # # 帧识别失败时回退到文件识别，保证兼容旧流程。
                # if not asr_text and audio_path:
                #     logger.warning("audio_frames 识别为空，回退到音频文件识别")
                #     asr_text = self.asr_client.recognize(audio_path).strip()
            elif audio_path:
                asr_text = self.asr_client.recognize(audio_path).strip()
            else:
                logger.warning("未提供 audio_frames 或 audio_path，跳过 ASR 识别")
                return ""

            logger.info(
                f"ASR 识别结果: [{asr_text}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
            )
            return asr_text
        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"ASR 识别失败: {e}")
            return ""

    async def async_asr_infer(self, audio_frames=None):
        """
        ASR 异步识别接口，支持 PCM16 字节流输入
        - 如果 audio_frames 为空，则返回空字符串
        - 返回识别文本，失败时返回空字符串
        """
        if audio_frames is None:
            logger.warning("未提供 audio_frames，跳过 ASR 识别")
            return ""

        # return await asyncio.to_thread(self.asr_infer, audio_frames=audio_frames)
        return await self.asr_client.async_recognize_frames(audio_frames=audio_frames)

    def llm_infer(
        self,
        input_text: str,
        vision_id: str | None = None,
        voice_id: str | None = None,
        rag_id: str | None = None,
        rag_name: str | None = None,
        is_active_ask: bool = False,
    ) -> str:
        """
        接收输入文本（可选携带用户 ID），调用 LLM 完成推理，返回生成的文本响应
        Parameters:
            input_text (str): 输入文本
            vision_id (str | None): 可选的视觉 ID，用于记忆相同用户的对话上下文，如果为 None 直接与LLM 进行对话
            voice_id (str | None): 可选的语音 ID
            rag_id (str | None): 可选的 RAG 用户 uuid
            rag_name (str | None): 可选的 RAG 用户姓名
            is_active_ask (bool): 是否为主动提问，默认为 False
        Returns:
            str: LLM 生成的文本响应，失败时返回空字符串
        """
        logger.info("LLM 推理中...")
        effective_vision_id = (
            vision_id if vision_id is not None else self.current_user_id
        )
        effective_voice_id = voice_id if voice_id is not None else None
        effective_rag_id = rag_id if rag_id is not None else self.current_user_id
        effective_rag_name = (
            rag_name if rag_name is not None else self.current_user_name
        )
        llm_text = ""
        time_now = time.time()
        try:
            llm_text = self.llm_client.chat_response(
                user_text=input_text,
                vision_id=effective_vision_id,
                voice_id=effective_voice_id,
                rag_id=effective_rag_id,
                rag_name=effective_rag_name,
                is_active_ask=is_active_ask,
            )
            if not llm_text:
                logger.warning("LLM 返回空响应")
                llm_text = ""
            logger.info(
                f"LLM 推理结果: [{llm_text}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
            )

            self._handle_rag_llm_response(llm_text)

            self.last_interface_time = time.time()
            return llm_text

        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"LLM 对话失败: {e}")
            self.last_interface_time = time.time()

            return ""

    def llm_stream_infer(
        self,
        input_text: str,
        vision_id: str | None = None,
        voice_id: str | None = None,
        rag_id: str | None = None,
        rag_name: str | None = None,
    ) -> Iterator[tuple[str, int]]:
        """
        接收输入文本（可选携带用户 ID），调用 LLM 完成流式推理，逐步返回生成的文本响应片段和对应的索引
        Parameters:
            input_text (str): 输入文本
            vision_id (str | None): 可选的视觉 ID，用于记忆相同用户的对话上下文，如果为 None 直接与LLM 进行对话
            voice_id (str | None): 可选的语音 ID
            rag_id (str | None): 可选的 RAG 用户 uuid
            rag_name (str | None): 可选的 RAG 用户姓名
        Returns:
            Iterator[tuple[str, int]]: 生成器，逐步返回LLM 生成的文本响应片段和对应的索引，失败时返回空字符串和当前索引
        """
        logger.info("LLM 流式推理中...")
        effective_vision_id = (
            vision_id if vision_id is not None else self.current_user_id
        )
        effective_voice_id = voice_id if voice_id is not None else None
        effective_rag_id = rag_id if rag_id is not None else self.current_user_id
        effective_rag_name = (
            rag_name if rag_name is not None else self.current_user_name
        )
        time_now = time.time()
        llm_response_chunks = []
        index = 0
        try:
            for (
                llm_response_chunk,
                index,
            ) in self.llm_client.chat_response_stream(
                user_text=input_text,
                vision_id=effective_vision_id,
                voice_id=effective_voice_id,
                rag_id=effective_rag_id,
                rag_name=effective_rag_name,
            ):
                logger.info(
                    f"LLM 流式推理输出 [{index}]: [{llm_response_chunk}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
                )
                llm_response_chunks.append(llm_response_chunk)
                time_now = time.time()

                yield llm_response_chunk, index

            self.last_interface_time = time.time()

        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"LLM 流式对话失败: {e}")
            yield "", index

    async def async_llm_infer(
        self, input_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> str:
        """
        接收输入文本（可选携带用户 ID），调用 LLM 完成推理，返回生成的文本响应
        Parameters:
            input_text (str): 输入文本
            vision_id (str | None): 可选的视觉 ID，用于记忆相同用户的对话上下文，如果为 None 直接与LLM 进行对话
            voice_id (str | None): 可选的语音 ID
        Returns:
            str: LLM 生成的文本响应，失败时返回空字符串
        """
        logger.info("LLM 推理中...")
        effective_vision_id = (
            vision_id if vision_id is not None else self.current_user_id
        )
        effective_voice_id = voice_id if voice_id is not None else None
        llm_text = ""
        time_now = time.time()
        try:
            llm_text = await self.llm_client.async_chat_response(
                input_text, effective_vision_id, effective_voice_id
            )
            if not llm_text:
                logger.warning("LLM 返回空响应")
                llm_text = ""
            logger.info(
                f"LLM 推理结果: [{llm_text}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
            )

            self.last_interface_time = time.time()
            return llm_text

        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"LLM 对话失败: {e}")
            self.last_interface_time = time.time()

            return ""

    async def async_llm_stream_infer(
        self, input_text: str, vision_id: str | None = None, voice_id: str | None = None
    ) -> AsyncIterator[tuple[str, int]]:
        """
        接收输入文本（可选携带用户 ID），调用 LLM 完成流式推理，逐步返回生成的文本响应片段和对应的索引
        Parameters:
            input_text (str): 输入文本
            vision_id (str | None): 可选的视觉 ID，用于记忆相同用户的对话上下文，如果为 None 直接与LLM 进行对话
            voice_id (str | None): 可选的语音 ID
        Returns:
            AsyncIterator[tuple[str, int]]: 异步生成器，逐步返回LLM 生成的文本响应片段和对应的索引，失败时返回空字符串和当前索引
        """
        logger.info("LLM 流式推理中...")
        effective_vision_id = (
            vision_id if vision_id is not None else self.current_user_id
        )
        effective_voice_id = voice_id if voice_id is not None else None
        time_now = time.time()
        llm_response_chunks = []
        index = 0
        try:
            async for (
                llm_response_chunk,
                index,
            ) in self.llm_client.async_chat_response_stream(
                input_text, effective_vision_id, effective_voice_id
            ):
                logger.info(
                    f"LLM 流式推理输出 [{index}]: [{llm_response_chunk}], 耗时: {(time.time() - time_now) * 1000:.2f} ms"
                )
                llm_response_chunks.append(llm_response_chunk)
                time_now = time.time()

                yield llm_response_chunk, index

            self.last_interface_time = time.time()

        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"LLM 流式对话失败: {e}")
            yield "", index

    def tts_infer(self, text):
        """
        负责调用 TTS 完成语音合成和播放
        """

        logger.info("TTS 合成和播放中...")

        text = self.text_processor.unify_text(text)
        logger.debug(f"统一化处理后请求片段: [{text}]")

        time_now = time.time()
        try:
            self.tts_client.speak(text.strip())
            threading.Thread(
                target=self.tts_cost_time,
                args=(time_now,),
                daemon=True,
                name="tts-startup-monitor",
            ).start()
            return True
        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"TTS 播放失败: {e}")
            return False

    def tts_stream_infer(self, llm_response_chunk, index=0):
        """
        负责调用 TTS 完成流式语音片段的合成和推送（非阻塞）
        """
        logger.info(f"TTS 推送流式片段 [{index}]...")

        text = self.text_processor.unify_text(llm_response_chunk)
        logger.debug(f"统一化处理后请求片段 [{index}]: [{text}]")

        time_now = time.time()
        try:
            assert index >= 0, "index 必须为非负整数"

            # tts_client.speak 为异步或基于缓冲队列的非阻塞调用
            if index == 0:

                self.tts_client.speak(text.strip(), interrupt=True)

                if text.strip():  # 只有在文本非空时才启动监控线程
                    threading.Thread(
                        target=self.tts_cost_time,
                        args=(time_now,),
                        daemon=True,
                        name="tts-stream-startup-monitor",
                    ).start()

            else:

                self.tts_client.speak(text.strip(), interrupt=False)

            return True
        except (AssertionError, *CLIENT_OPERATION_ERRORS) as e:
            logger.error(f"TTS 推送流式片段 [{index}] 失败: {e}")
            return False

    def tts_cost_time(self, start_time):
        """
        计算 TTS 合成并播放音频的延迟时间
        """

        # if not self.tts_client.wait_until_playback_starts(timeout_sec=5.0):
        #     logger.error("TTS 播放超时 或者 TTS 播放音频太短")
        #     return False

        while not self.tts_client.output_stream_active():
            if time.time() - start_time > 10.0:
                logger.warning("TTS 播放超时 或者 TTS 播放音频太短")
                return False
            time.sleep(0.02)

        elapsed_time = 0
        # if isinstance(self.tts_client, RealtimeTTSPlayer):
        #     elapsed_time = time.time() - start_time
        # else:
        elapsed_time = (
            time.time() - start_time - self.tts_client.get_playback_start_delay_sec()
        )
        logger.info(f"TTS 首次合成并播放音频延迟: {elapsed_time:.2f} 秒")
        return True

    async def async_tts_infer(self, text):
        """
        TTS 异步接口，负责调用 TTS 完成语音合成和播放
        """
        return await asyncio.to_thread(self.tts_infer, text)

    def kws_infer(self, asr_text):
        """
        负责唤醒词检测逻辑
        """

        # 提取汉字并转换为拼音
        pinyin_text = self.text_processor.extract_chinese_and_convert_to_pinyin(
            asr_text
        )
        logger.info(f"转换为拼音: {pinyin_text}")
        wake_word_matched, best_window, best_score = (
            self.text_processor.is_kws_pinyin_match(pinyin_text)
        )
        if wake_word_matched:
            logger.info(
                "唤醒词近似匹配成功, 窗口拼音: '%s', 相似度: %.3f, 阈值: %.3f",
                best_window,
                best_score,
                self.kws_fuzzy_similarity_threshold,
            )
        else:
            logger.info(
                "唤醒词近似匹配未命中, 最佳窗口: '%s', 最佳相似度: %.3f, 阈值: %.3f",
                best_window,
                best_score,
                self.kws_fuzzy_similarity_threshold,
            )

        if wake_word_matched and self.tts_client.is_active():
            logger.warning("检测到唤醒词， TTS 播放中，打断播放以避免语音叠加")

            # self.flag_kws = 1
            self.llm_agent_state = ComponentState.ACTIVE

            self.interrupt()

            time.sleep(0.1)

            self.last_interface_time = time.time()
            return True

        if self.llm_agent_state == ComponentState.ACTIVE:
            logger.info("LLM 模块已处于 ACTIVE 状态，无需检测唤醒词")
            self.last_interface_time = time.time()
            return True

        if wake_word_matched:
            # self.flag_kws = 1
            self.llm_agent_state = ComponentState.ACTIVE

            self.failed_enable_kws_count = 0

            self.last_interface_time = time.time()

            logger.info("检测到唤醒词，激活 LLM 模块")
            return True
        else:
            # self.flag_kws = 0
            self.llm_agent_state = ComponentState.IDLE

            self.failed_enable_kws_count += 1

            logger.info(f"未检测到唤醒词，失败次数: {self.failed_enable_kws_count}")

            # 如果连续多次未检测到唤醒词，且距离上次提示已超过一定时间，则推送提示语音
            if (
                self.failed_enable_kws_count >= self.failed_kws_counts
                and time.time() - self.last_failed_kws_time > self.failed_kws_threshold
            ):
                self.__update_llm_text(f"你可以说出:{self.set_kws} 来唤醒我!")

                # 只有在 ACTIVE 状态下才播放提示语音
                if self.tts_client_state == ComponentState.ACTIVE:
                    logger.info("TTS处于 ACTIVE 状态，准备播放提示语音")
                    if self.tts_client.is_active() and self.enable_interrupt_tts:
                        logger.info("TTS 播放中，启用了打断功能，准备中断播放")
                        self.interrupt()
                        time.sleep(0.1)

                    self.tts_infer(f"你可以说出:{self.set_kws} 来唤醒我!")

                self.failed_enable_kws_count = 0
                self.last_failed_kws_time = time.time()

            else:
                self.__update_llm_text("")

            self.last_interface_time = time.time()
            return False

        # else:
        #     self.llm_agent_state = LLMAgentState.ACTIVE
        #     self.last_interface_time = time.time()
        #     logger.info("未启用唤醒词激活功能")
        #     return True

    def delete_user_context(self, user_id: str):
        """
        删除指定用户 ID 的对话上下文
        """
        try:
            self.llm_client.delete_thread(thread_id=user_id)
            logger.info(f"已删除用户 ID {user_id} 的对话上下文")
            return True
        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"删除用户 ID {user_id} 的对话上下文失败: {e}")
            return False

    def _log_user_dialog(
        self,
        user_id: str | None,
        user_name: str | None,
        asr_text: str | None,
        llm_text: str | None,
        audio_saved_path: str | None = None,
    ) -> None:
        """
        保存单轮用户对话记录，失败时不影响主交互流程。
        """
        try:
            log_user_dialog(
                user_id=user_id,
                user_name=user_name,
                asr_text=asr_text,
                llm_text=llm_text,
                audio_saved_path=audio_saved_path,
            )
        except CLIENT_OPERATION_ERRORS as e:
            logger.error(f"保存用户对话记录失败: {e}")

    def _handle_rag_llm_response(self, llm_text: str | None) -> None:
        """将 LLM 回复交给 RAG 处理（如 MOVE_TO_WAIT 时重置机器人位置）。
        - @2026-7-9 by liujinyou
        """
        if not llm_text:
            return
        _rag = getattr(self.llm_client, "rag_client", None)
        if _rag is None:
            return
        try:
            if _rag.handle_llm_response(llm_text):
                logger.info("RAG 已根据 LLM 回复更新机器人位置")
        except CLIENT_OPERATION_ERRORS as e:
            logger.warning("RAG 处理 LLM 回复失败: %s", e)

    ##########################################################

    ####################### 核心交互流程 #######################
    async def inference(
        self,
        audio_frames=None,
        audio_path: str | None = None,
        input_text: str | None = None,
        user_id: str | None = None,
        voice_id: str | None = None,
    ) -> bool:
        """
        负责调用 ASR、LLM、TTS 完成一次完整的交互
        Parameters:
            - audio_frames: 可选的 PCM16 字节流输入，用于 ASR 识别，优先级高于 audio_path
            - audio_path: 可选的音频文件路径输入，用于 ASR 识别，当 audio_frames 为空时使用
            - input_text: 可选的文本输入，用于 ASR 识别，当 audio_frames 和 audio_path 都为空时使用
            - user_id: 可选的用户 ID，用于支持个性化对话，如果为 None 则使用当前默认用户 ID
            - voice_id: 可选的语音 ID，用于支持个性化语音识别，如果为 None 则使用当前默认语音 ID
        """

        # # 测试异步的 asr, llm, tts 接口是否能正确协同工作
        # now = time.time()
        # asr_result, llm_result, tts_result = await asyncio.gather(
        #     self.async_asr_infer(audio_frames=audio_frames),
        #     self.async_llm_infer(input_text="你好小特，介绍自己", user_id=user_id),
        #     self.async_tts_infer("你好，我是小特，一个智能语音助手！"),
        # )
        # logger.info(
        #     f"测试异步 ASR 结果: {asr_result}, LLM 结果: {llm_result}, TTS 结果: {tts_result}, 耗时: {(time.time() - now) * 1000:.2f} ms"
        # )
        # return True

        logger.info("\n\n开始一次完整的交互流程...")

        # -------------  检查人脸信息 -------------
        if self.enable_user_face_info and not self.current_user_face_status:
            logger.warning("[启用人脸信息检测] 当前未检测到人脸信息，跳过本次交互")
            self.last_interface_time = time.time()
            return False
        # ----------------------------------------

        current_user_id = user_id if user_id is not None else self.current_user_id
        current_user_name = (
            self.current_user_name if self.current_user_name is not None else None
        )
        current_rag_id = current_user_id
        current_rag_name = current_user_name
        current_voice_id = voice_id if voice_id is not None else None
        logger.info(
            f"本次交互用户 ID: {current_user_id}, 用户 Name: {current_user_name}, Voice_ID: {current_voice_id}, RAG_ID: {current_rag_id}, RAG_Name: {current_rag_name}"
        )

        # current_vision_id = user_id if user_id is not None else self.current_user_id
        # current_voice_id = voice_id if voice_id is not None else None
        # logger.info(f"本次交互视觉用户 ID: {current_vision_id}")
        # logger.info(f"本次交互语音用户 ID: {current_voice_id}")

        # 响应数据，包括 asr_text 和 llm_text
        # self.response_json = {}
        self.response_data.clear()

        self.asr_text = ""
        # -------- 检查 asr client 状态 ----------
        if self.asr_client_state == ComponentState.IDLE:
            self.last_interface_time = time.time()

            logger.warning("ASR 模块未激活，跳过本次交互")
            return False
        # --------------------------------------

        # -------- asr 识别 -----------
        if audio_frames is not None:

            self.asr_text = await self.async_asr_infer(audio_frames=audio_frames)

        elif audio_path:
            self.asr_text = self.asr_infer(audio_path=audio_path)
        elif input_text:
            self.asr_text = input_text
        else:
            logger.warning("未提供音频路径或输入文本，跳过本次交互")
            self.last_interface_time = time.time()
            return False

        # self.asr_text = "你好，小特"  # 测试代码，固定返回唤醒词
        # ## response_json 更新 asr_text
        # response_json["asr_text"] = self.asr_text
        if not self.asr_text:
            logger.warning("ASR 未识别到有效文本，跳过本次交互")
            self.last_interface_time = time.time()
            # self.set_state(AssistantState.LISTENING)
            return False
        # --------------------------------

        # -------- 判断asr_text中汉字数量，过少则忽略 ----------
        chinese_char_count = self.text_processor.count_chinese_characters(self.asr_text)
        if chinese_char_count < 2:
            logger.warning("ASR 识别文本中汉字数量过少，跳过本次交互")
            self.last_interface_time = time.time()
            return False
        # --------------------------------------------------

        # ---------------- 替换特殊词汇 --------------------
        if self.enable_replace_special_characters:
            logger.info(f"替换前 ASR 文本: {self.asr_text}")
            self.asr_text = self.text_processor.replace_special_characters(
                self.asr_text
            )
            logger.info(f"替换后 ASR 文本: {self.asr_text}")
        # ------------------------------------------------

        # -------------- 更新asr_text队列 ------------------
        self.__push_queue(self.asr_text_queue, self.asr_text)
        ##  更新 asr_text
        # self.response_json["asr_text"] = self.asr_text
        self.response_data.asr_text = self.asr_text
        # ------------------------------------------------

        # ----------- 唤醒词检测 -----------
        if self.kws_enabled:
            if not self.kws_infer(self.asr_text):

                self.last_interface_time = time.time()
                return False
        else:
            # self.llm_agent_state = LLMAgentState.ACTIVE

            self.last_interface_time = time.time()
            logger.info("未启用唤醒词激活功能")
        # ---------------------------------

        #  ------------- 检测到人脸信息，打断 LLM，TTS 后台输出 -------------
        if self.current_user_face_status and self.enable_interrupt_by_asr_face:
            self.interrupt()
        # --------------------------------------------------------------

        self.llm_text = ""
        # -------- 检查 LLM Agent 状态 ----------
        if self.llm_agent_state == ComponentState.IDLE:
            self.last_interface_time = time.time()

            logger.warning("LLM 模块未激活，跳过本次交互")

            self.__update_llm_text(self.llm_text)

            return False
        # ---------------------------------------

        if self.llm_stream_infer_enable:
            # -------- llm tts stream --------------
            ## -------- 先确认当前阶段是否允许播放 TTS，避免分段打断自己 ---------
            tts_can_play = self.check_tts_status()

            ## 异步流式推理和播放 require python >=3.11
            # async for chunk, index in self.async_llm_stream_infer(
            #     self.asr_text, vision_id=vision_id, voice_id=voice_id
            # ):
            #     self.llm_text += chunk
            #     if chunk.strip() and tts_can_play:
            #         self.tts_stream_infer(
            #             self.text_processor.remove_intent_tags(chunk.strip()), index
            #         )

            ## 同步流式推理和播放
            for chunk, index in self.llm_stream_infer(
                self.asr_text,
                vision_id=current_user_id,
                voice_id=current_voice_id,
                rag_id=current_rag_id,
                rag_name=current_rag_name,
            ):
                self.__push_queue(
                    self.llm_text_queue, [{"index": index, "text": chunk.strip()}]
                )

                self.llm_text += chunk
                if chunk.strip() and tts_can_play:
                    self.tts_stream_infer(chunk.strip(), index)

            # self.__update_llm_text(self.llm_text)
            self.response_data.llm_text = self.llm_text
            self.__push_queue(self.response_queue, asdict(self.response_data))
            self.response_data.clear()

        else:
            # -------- llm tts -----------
            ## llm异步推理 require python >=3.11
            # self.llm_text = await self.async_llm_infer(
            #     self.asr_text, vision_id=current_vision_id, voice_id=current_voice_id
            # )
            ## --------- llm 推理 ----------
            self.llm_text = self.llm_infer(
                self.asr_text,
                vision_id=current_user_id,
                voice_id=current_voice_id,
                rag_id=current_rag_id,
                rag_name=current_rag_name,
            )

            self.__update_llm_text(self.llm_text)

            ## -------- tts 播放 -----------
            # if not self.check_tts_status():
            #     self.last_interface_time = time.time()
            #     return False
            # self.tts_infer(self.llm_text)

            if self.check_tts_status():
                self.tts_infer(self.llm_text)
            # ------------------------------

        # ---------------- 保存用户对话记录 -----------------
        self._log_user_dialog(
            user_id=current_user_id,
            user_name=current_user_name,
            asr_text=self.asr_text,
            llm_text=self.llm_text,
            audio_saved_path=self.audio_saved_path,
        )
        self.audio_saved_path = None
        # ---------------- 保存用户音频文件 -----------------
        self.asr_client.save_tmp_wav(
            parent_dir_name=current_user_id if current_user_id else "unknown_user",
        )
        # ------------------------------------------------

        # ------------ 语言规则双向标记 + RAG 处理 LLM 回复 ----------------
        ## history:
        ## @2026-7-9 by liujinyou
        _rag = getattr(self.llm_client, "rag_client", None)
        if _rag is not None and self.llm_text:
            try:
                if current_user_id:
                    _rag.visitor_state.mark_steps_from_texts(
                        current_user_id,
                        query=self.asr_text,
                        response=self.llm_text,
                    )
                _rag.handle_llm_response(self.llm_text)
            except CLIENT_OPERATION_ERRORS as _e:
                logger.warning("RAG 后处理 LLM 回复失败: %s", _e)
        # ------------------------------------------------

        # ------------ 查询是否需要再次query to resolve -----------------
        ## history:
        ## @2026-7-9 by liujinyou
        if self.llm_client.get_query_to_resolve():

            logger.info("需要再次查询以解析名称")

            # 重置 query_to_resolve 标志，避免重复查询
            self.llm_client.set_query_to_resolve(False)

            # 调用 LLM 进行查询以解析名称，获取结果后推送到 resolved_user_names_queue 队列
            resolve_name = self.llm_client.single_response(
                self.asr_text, is_obtain_name=True
            )
            # resolve_name = "default_name"  # 测试代码，固定返回名称
            self.__push_queue(self.resolved_user_names_queue, resolve_name)

            logger.info(f"解析得到名称: {resolve_name}")

            if resolve_name and current_user_id:
                _rag = getattr(self.llm_client, "rag_client", None)
                if _rag is not None:
                    try:
                        if _rag.commit_extracted_name(current_user_id, resolve_name):
                            self.current_user_name = resolve_name.strip()
                            logger.info(
                                "抽取姓名已写入 RAG 状态: user_id=%s name=%s",
                                current_user_id,
                                self.current_user_name,
                            )
                    except CLIENT_OPERATION_ERRORS as _e:
                        logger.warning("抽取姓名写入 RAG 状态失败: %s", _e)
        # ----------------------------------------------------------------

        ###############################################################

        logger.info("本次交互完成")
        self.last_interface_time = time.time()
        return True

    async def Inference(
        self,
        audio_frames=None,
        audio_path: str | None = None,
        input_text: str | None = None,
        user_id: str | None = None,
        voice_id: str | None = None,
    ) -> bool:
        return await self.inference(
            audio_frames=audio_frames,
            audio_path=audio_path,
            input_text=input_text,
            user_id=user_id,
            voice_id=voice_id,
        )


if __name__ == "__main__":
    # 获取当前文件所在目录
    current_dir = Path(__file__).resolve().parent
    logger.info(f"当前文件目录: {current_dir}")
    config_yaml_path = (current_dir / "../config/config.yaml").resolve()
    logger.info(f"配置文件路径: {config_yaml_path}")

    assistant = ChatAssistant(config_path=str(config_yaml_path))

    assistant.start()

    # print("ChatAssistant 初始化完成")
    logger.info("ChatAssistant 初始化完成")

    try:
        logger.info("按 Ctrl+C 停止程序")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("停止程序中...")
        assistant.stop()
        logger.info("程序已停止")
