import logging
import logging.config
import logging.handlers
import os
import re
import threading
import time
from datetime import time as dt_time
from pathlib import Path

# 获取环境变量中的 DEBUG_MODE，默认为 false
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# 获取当前文件所在目录: ...ASR_LLM_TTS/chat_assistant/logger
logger_dir = Path(__file__).resolve().parent

# logs 目录路径: ...ASR_LLM_TTS/logs
logs_dir = logger_dir.parents[1] / "logs"

# logs_dir = os.path.join(current_dir, "../../../", "logs")
# 年月日目录
# logs_dir = os.path.join(logs_dir, time.strftime("%Y-%m-%d"))
user_dialog_logs_dir = logs_dir / "user_dialogs"

# logs_dir = "logs"
if not logs_dir.exists():
    logs_dir.mkdir(parents=True, exist_ok=True)
if not user_dialog_logs_dir.exists():
    user_dialog_logs_dir.mkdir(parents=True, exist_ok=True)

# 定义宏，在日志消息中使用不同的颜色来区分不同级别的日志（需要支持 ANSI 转义序列的终端）
LOG_COLORS = {
    logging.DEBUG: "\033[36m",  # 青色
    # logging.INFO: "\033[32m",  # 绿色
    logging.WARNING: "\033[33m",  # 黄色
    logging.ERROR: "\033[31m",  # 红色
    logging.CRITICAL: "\033[35m",  # 紫色
}


class ColoredFormatter(logging.Formatter):
    def format(self, record):
        log_color = LOG_COLORS.get(record.levelno, "\033[0m")  # 默认颜色
        message = super().format(record)
        return f"{log_color}{message}\033[0m"  # 添加颜色并重置


DEFAULT_LOG_FORMAT = (
    "[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d]: %(message)s"
)


USER_DIALOG_LOG_FORMAT = (
    # # default format
    # "[%(asctime)s] \n用户姓名: %(user_name)s\nASR: %(asr_text)s\nLLM: %(llm_text)s"
    # # xml standard format
    # "<log><time>%(asctime)s</time><user_name>%(user_name)s</user_name><asr_text>%(asr_text)s</asr_text><llm_text>%(llm_text)s</llm_text></log>"
    # json standard format
    # '{"time": "%(asctime)s", "user_name": "%(user_name)s", "asr_text": "%(asr_text)s", "llm_text": "%(llm_text)s", "audio_saved_path": "%(audio_saved_path)s"}'
    '{"audio_saved_path": "%(audio_saved_path)s", "asr_text": "%(asr_text)s", "llm_text": "%(llm_text)s", "time": "%(asctime)s", "user_name": "%(user_name)s"}'
    # json.dumps(
    #     {
    #         "time": "%(asctime)s",
    #         "user_name": "%(user_name)s",
    #         "asr_text": "%(asr_text)s",
    #         "llm_text": "%(llm_text)s",
    #     },
    #     ensure_ascii=False,
    #     sort_keys=True,
    #     indent=4,
    #     separators=(",", ": "),
    # )
)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": DEFAULT_LOG_FORMAT,
        },
        "colored": {
            "()": ColoredFormatter,
            "format": DEFAULT_LOG_FORMAT,
        },
        "user_dialog": {
            "format": USER_DIALOG_LOG_FORMAT,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG" if DEBUG_MODE else "INFO",
            "formatter": "colored",
        },
        "timed_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "level": "INFO",
            "formatter": "default",
            "filename": os.path.join(logs_dir, "asr_llm_tts"),
            "when": "H",  # 滚动间隔：Y=年，M=月，D=日，H=时，m=分，s=秒
            "interval": 1,  # 间隔倍数（如when="H"，interval=6则每6小时滚动）
            "backupCount": 48,  # 保留的旧日志文件个数
            "encoding": "utf-8",
            "atTime": dt_time(0, 0, 0),  # 滚动时间点（每天零点）
        },
    },
    "loggers": {
        __name__: {
            "level": "DEBUG",
            "handlers": ["timed_file", "console"],
            "propagate": False,
        },
    },
}


logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

timed_handler = next(
    (
        handler
        for handler in logger.handlers
        if isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    ),
    None,
)
if timed_handler is not None:
    # 设置日志文件后缀格式为年-月-日_时-分
    # timed_handler.suffix = "%Y-%m-%d_%H-%M-%S"  # 精确到秒
    # timed_handler.suffix = "%Y-%m-%d_%H-%M"  #  精确到分钟即可
    timed_handler.suffix = "%Y-%m-%d_%H"  #  精确到小时即可

_dialog_logger_lock = threading.Lock()
_dialog_logger_cache = {}
_dialog_formatter = logging.Formatter(USER_DIALOG_LOG_FORMAT)


def _safe_path_name(value: str | None, default: str) -> str:
    if not value:
        return default

    safe_value = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]+", "_", str(value).strip())
    safe_value = safe_value.strip("._-")
    return safe_value or default


def _normalize_dialog_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def get_user_dialog_logger(user_id: str | None) -> logging.Logger:
    """
    按用户 ID 获取专用对话 logger，并动态创建对应日志目录。
    """
    safe_user_id = _safe_path_name(user_id, "unknown_user")

    with _dialog_logger_lock:
        if safe_user_id in _dialog_logger_cache:
            return _dialog_logger_cache[safe_user_id]

        user_log_dir = os.path.join(user_dialog_logs_dir, safe_user_id)
        os.makedirs(user_log_dir, exist_ok=True)

        dialog_logger = logging.getLogger(f"user_dialog.{safe_user_id}")
        dialog_logger.setLevel(logging.INFO)
        dialog_logger.propagate = False

        if not dialog_logger.handlers:
            dialog_handler = logging.handlers.TimedRotatingFileHandler(
                filename=os.path.join(user_log_dir, "dialog.jsonl"),
                when="H",
                interval=1,
                backupCount=48,
                encoding="utf-8",
                atTime=dt_time(0, 0, 0),
            )
            dialog_handler.suffix = "%Y-%m-%d_%H"
            dialog_handler.setFormatter(_dialog_formatter)
            dialog_handler.setLevel(logging.INFO)
            dialog_logger.addHandler(dialog_handler)

        _dialog_logger_cache[safe_user_id] = dialog_logger
        return dialog_logger


def log_user_dialog(
    user_id: str | None,
    user_name: str | None,
    asr_text: str | None,
    llm_text: str | None,
    audio_saved_path: str | None = None,
) -> None:
    """
    记录单轮用户对话，只保存时间、用户姓名、ASR 结果和 LLM 回复。
    """
    dialog_logger = get_user_dialog_logger(user_id)
    dialog_logger.info(
        "",
        extra={
            "user_name": _normalize_dialog_text(user_name) or "未知用户",
            "asr_text": _normalize_dialog_text(asr_text),
            "llm_text": _normalize_dialog_text(llm_text),
            "audio_saved_path": _normalize_dialog_text(audio_saved_path),
        },
    )


def get_logs_dir() -> Path:
    """
    获取日志目录路径。
    """
    return logs_dir


if __name__ == "__main__":

    import time

    while True:
        logger.debug("This is a debug message.")
        logger.info("This is an info message.")
        logger.warning("This is a warning message.")
        logger.error("This is an error message.")
        logger.critical("This is a critical message.")
        log_user_dialog(
            user_id="test_user",
            user_name="Test User",
            asr_text="Test ASR",
            llm_text="Test LLM",
            audio_saved_path="path/to/audio",
        )
        time.sleep(0.1)
