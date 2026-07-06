"""
自定义回调函数处理器模块

description:
    这里定义了一些自定义回调函数处理器，这些处理器会被注册到 Agent 中，供 Agent 在对话过程中调用。
    这些回调函数处理器可以实现一些特定的功能，比如记录日志、统计使用情况、处理模型生成的消息块等。
reference:
  - https://reference.langchain.com/python/langchain-core/callbacks/base/BaseCallbackHandler
  - https://reference.langchain.org.cn/python/langchain_core/callbacks/
  - https://docs.langchain.com/oss/python/langchain/models#token-usage
"""

from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler
from logger import logger


class my_callback_handler(BaseCallbackHandler):
    """自定义回调函数示例，用于处理模型生成的消息块。"""

    logger.debug("初始化自定义回调处理器")

    # def on_chain_start(self, serialized, inputs, **kwargs):
    #     logger.debug("链开始")

    # # 查看日志专用
    def on_chat_model_start(self, serialized, messages, **kwargs):
        logger.debug("\n========== on_chat_model_start MESSAGES START ==========")

        for batch_index, batch in enumerate(messages):
            logger.debug(f"\n--- Batch {batch_index} ---")

            for msg in batch:
                logger.debug(f"\n{msg.type}:\n{msg.content}")
                logger.debug("--------------------------------")

        logger.debug("============= on_chat_model_start MESSAGES END =============\n")


def get_callback_handlers():
    """返回默认启用的回调处理器列表。"""
    return [
        my_callback_handler(),
        UsageMetadataCallbackHandler(),
    ]
