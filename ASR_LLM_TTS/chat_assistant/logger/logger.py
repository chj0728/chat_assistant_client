import logging
import logging.handlers

import os
import time
from datetime import time

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# logs 目录路径
logs_dir = os.path.join(current_dir, "..", "logs")

# logs_dir = "logs"
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir, exist_ok=True)

# 设置根日志级别为DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 创建日志格式（文件和控制台共用）
formatter = logging.Formatter(
    # "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    "[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d]: %(message)s"
)

# 控制台处理器
console_handler = logging.StreamHandler()  # 默认输出到sys.stderr（控制台）
console_handler.setLevel(logging.INFO)  # 控制台输出INFO及以上级别日志（可根据需要调整）
console_handler.setFormatter(formatter)


# timed_handler：每小时生成一个新的日志文件，保留48小时的日志文件
timed_handler = logging.handlers.TimedRotatingFileHandler(
    filename=logs_dir + "/asr_llm_tts",
    when="H",  # 滚动间隔：Y=年，M=月，D=日，H=时，m=分，s=秒
    interval=1,  # 间隔倍数（如when="H"，interval=6则每6小时滚动）
    backupCount=48,  # 保留的旧日志文件个数
    encoding="utf-8",
    atTime=time(0, 0, 0),  # 滚动时间点（每天零点）
)
# 设置日志文件后缀格式为年-月-日_时-分
# timed_handler.suffix = "%Y-%m-%d_%H-%M-%S"  # 精确到秒
# timed_handler.suffix = "%Y-%m-%d_%H-%M"  #  精确到分钟即可
timed_handler.suffix = "%Y-%m-%d_%H"  #  精确到小时即可

# 配置Formatter：日志格式包含时间、模块名、级别、内容
timed_handler.setFormatter(formatter)

# 为根日志添加处理器
logger.addHandler(timed_handler)
logger.addHandler(console_handler)


if __name__ == "__main__":

    import time

    while True:
        logger.debug("This is a debug message.")
        logger.info("This is an info message.")
        logger.warning("This is a warning message.")
        logger.error("This is an error message.")
        logger.critical("This is a critical message.")
        time.sleep(0.1)
