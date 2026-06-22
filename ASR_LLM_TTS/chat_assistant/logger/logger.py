import logging
import logging.handlers
import os
import re
import threading
import time
from datetime import time as dt_time

# 获取环境变量中的 DEBUG_MODE，默认为 false
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# logs 目录路径
logs_dir = os.path.join(current_dir, "..", "logs")
user_dialog_logs_dir = os.path.join(logs_dir, "user_dialogs")

# logs_dir = "logs"
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir, exist_ok=True)
if not os.path.exists(user_dialog_logs_dir):
    os.makedirs(user_dialog_logs_dir, exist_ok=True)

# 设置根日志级别为DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 创建日志格式（文件和控制台共用）
formatter = logging.Formatter(
    # "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    "[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d]: %(message)s"
)

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


# 控制台处理器
console_handler = logging.StreamHandler()  # 默认输出到sys.stderr（控制台）
console_handler.setLevel(
    logging.DEBUG if DEBUG_MODE else logging.INFO
)  # 控制台输出DEBUG或INFO及以上级别日志
console_handler.setFormatter(ColoredFormatter(formatter._fmt))

# timed_handler：每小时生成一个新的日志文件，保留48小时的日志文件
timed_handler = logging.handlers.TimedRotatingFileHandler(
    filename=logs_dir + "/asr_llm_tts",
    when="H",  # 滚动间隔：Y=年，M=月，D=日，H=时，m=分，s=秒
    interval=1,  # 间隔倍数（如when="H"，interval=6则每6小时滚动）
    backupCount=48,  # 保留的旧日志文件个数
    encoding="utf-8",
    atTime=dt_time(0, 0, 0),  # 滚动时间点（每天零点）
)
# 设置日志文件后缀格式为年-月-日_时-分
# timed_handler.suffix = "%Y-%m-%d_%H-%M-%S"  # 精确到秒
# timed_handler.suffix = "%Y-%m-%d_%H-%M"  #  精确到分钟即可
timed_handler.suffix = "%Y-%m-%d_%H"  #  精确到小时即可

# 配置Formatter：日志格式包含时间、模块名、级别、内容
timed_handler.setFormatter(formatter)
timed_handler.setLevel(logging.INFO)  # 文件输出INFO及以上级别日志

# 为根日志添加处理器
logger.addHandler(timed_handler)
logger.addHandler(console_handler)


_dialog_logger_lock = threading.Lock()
_dialog_logger_cache = {}
_dialog_formatter = logging.Formatter(
    "[%(asctime)s] 用户姓名: %(user_name)s | ASR结果: %(asr_text)s | LLM回复: %(llm_text)s"
)


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
                filename=os.path.join(user_log_dir, "dialog"),
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
        },
    )


if __name__ == "__main__":

    import time

    while True:
        logger.debug("This is a debug message.")
        logger.info("This is an info message.")
        logger.warning("This is a warning message.")
        logger.error("This is an error message.")
        logger.critical("This is a critical message.")
        time.sleep(0.1)
