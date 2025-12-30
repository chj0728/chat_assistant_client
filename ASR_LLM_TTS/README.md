# A Chat Assistant with ASR, LLM, and TTS capabilities

This project implements a chat assistant that integrates Automatic Speech Recognition (ASR), Large Language Models (LLM), and Text-to-Speech (TTS) functionalities. The assistant can process voice inputs, generate responses using LLMs, and convert text responses back to speech.


## creating a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

## Install dependencies

```bash
pip3 install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

## Run the demos

- ASR Demo(语音识别)
```bash
python3 -m asr.asrclient
```

- LLM Demo(大语言模型)
```bash
python3 -m llm.llmclient
```

- TTS Demo(文本转语音)
```bash
python3 -m tts.ttsplay
```
- Chat Assistant Demo(集成语音识别、大语言模型、文本转语音)
```bash
python3 -m chat_assistant_v1
```