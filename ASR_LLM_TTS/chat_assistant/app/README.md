# 更新日志

- 修改 [`__init__.py`](./__init__.py) 文件以切换不同版本的 ChatAssistant 类。

## chat_assistant_v3.py - 2026年年4月15日

没有订阅到用户ID话题数据时，最终用于推理的 user_id 会回退为 None。

改动如下：

1. 在节点里增加了“用户ID超时失效”机制

   - 初始化默认值为 None，并记录最后一次收到话题时间
   - 从配置读取超时参数 user_id_stale_timeout_sec（默认 1.0 秒）
   - 新增 get_latest_user_id，若超时未收到新消息就清空为 None
   - 主循环每轮都会检查一次，保证自动录音推理链路也会超时回退
2. 订阅回调中对空字符串做了归一化

   - 收到消息时会 strip，空值直接当作 None，并同步到 ChatAssistant
3. 服务调用优先级调整

   - chat_assistant_infer / llm_infer 现在是：请求里显式 user_id 优先，否则用最新订阅值；如果无订阅或超时则是 None
4. ChatAssistant 内部增加兜底
   - 增加 current_user_id 默认 None
   - set_current_user_id 支持 None，并统一清洗空字符串
   - llm_infer / llm_stream_infer / Inference 都改为未显式传入时回退到 current_user_id（因此可自然得到 None）

----

其余改动查看 git 提交历史

----

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
