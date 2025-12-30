# 从当前模块的 logger.py 中导入 logger 实例
from .logger import logger

# 可选：限制模块的公共接口（只暴露 logger）
__all__ = ["logger"]
