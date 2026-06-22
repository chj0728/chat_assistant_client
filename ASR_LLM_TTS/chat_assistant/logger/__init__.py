# 从当前模块的 logger.py 中导入 logger 实例
from .logger import log_user_dialog, logger

# 可选：限制模块的公共接口
__all__ = ["logger", "log_user_dialog"]
