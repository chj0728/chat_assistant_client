# 更新日志

- 修改 [`__init__.py`](./__init__.py) 文件以切换不同版本的 ChatAssistant 类。

## chat_assistant_v3.py - 2026年1月23日
- ✨ feat: 优化录音与 VAD 流程，改进静音段处理逻辑，确保在静音结束后正确保存音频段。
- ✨ feat: 添加录音时长限制，防止过长录音段未及时保存。


## chat_assistant_v2.py - 2026年1月6日
- ✨ feat: 采用 pathlib 重构配置加载，并将交互队列改为有界队列以避免无限增长。
重写录音与 VAD 流程，引入分贝计算、PCM 转换等辅助函数，规范静音段收尾逻辑
...
其他详细改动记录见git提交历史。
## chat_assistant_v1.py - 2025年12月29日
- 初始版本，集成ASR、LLM、TTS功能，实现基本的语音交互流程。