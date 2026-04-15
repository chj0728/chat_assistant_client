# Test each module individually

```bash
cd {workspace_root}
source ./venv/bin/activate

cd {workspace_root}/ASR_LLM_TTS/chat_assistant
```

- ASR Demo(语音识别)

```bash
python3 -m asr.asrclient_v1
```

- LLM Demo(大语言模型)

```bash
# 原始版本
#python3 -m llm.llmclient

# 基于Langchain的智能体版本
python3 -m llm.llmagent
```

- TTS Demo(文本转语音)

```bash
# cosyvoice TTS
python3 -m tts.ttsplay

# sherpa-onnx TTS
python3 -m tts.ttsclient
```

- LLM + TTS Demo(大语言模型 + 文本转语音)

```bash
python3 -m app.llm_tts_stream
```

- Chat Assistant Demo(集成语音识别、大语言模型、文本转语音)

```bash
python3 -m app.chat_assistant_v3
```

- 前端日志与配置管理界面

```bash
# 方式1：模块启动
python3 -m chat_assistant.web.web_server --host 0.0.0.0 --port 17890
```

打开浏览器访问：`http://127.0.0.1:17890`

- 实时日志：`chat_assistant/logs/asr_llm_tts`（页面自动轮询增量刷新）
- 历史日志：`chat_assistant/logs/asr_llm_tts.YYYY-MM-DD_HH`（可在页面中删除）
