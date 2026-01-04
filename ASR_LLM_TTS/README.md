# A Chat Assistant with ASR, LLM, and TTS capabilities

This project implements a chat assistant that integrates Automatic Speech Recognition (ASR), Large Language Models (LLM), and Text-to-Speech (TTS) functionalities. The assistant can process voice inputs, generate responses using LLMs, and convert text responses back to speech.


## creating a virtual environment

```bash
cd ASR_LLM_TTS
python3 -m venv venv
source venv/bin/activate

# deactivate the virtual environment
# deactivate
```

## Install dependencies

```bash
pip3 install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

## Run the demos

```bash
source venv/bin/activate

cd chat_assistant
```

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

- LLM + TTS Demo(大语言模型 + 文本转语音)
```bash
python3 -m app.llm_tts_stream
```
- Chat Assistant Demo(集成语音识别、大语言模型、文本转语音)
```bash
python3 -m app.chat_assistant_v1
```

## Ros services
- build the interfaces and package
```bash
cd ASR_LLM_TTS

colcon build --symlink-install
# colcon build --symlink-install --packages-select chat_assistant_interfaces
# colcon build --symlink-install --packages-select chat_assistant

source install/setup.bash
source venv/bin/activate
```
- run the node
```bash
## ros2 run chat_assistant chat_assistant_node

# use the module way
## cd chat_assistant
## python3 -m chat_assistant.chat_assistant_node

# or use the run.sh script
cd  ASR_LLM_TTS

./run.sh
```

## Available services


### 重新加载配置文件
```bash
ros2 service call /reload_config std_srvs/srv/Trigger
```

### 激活
```bash 
ros2 service call /activate_assistant std_srvs/srv/Trigger
```
### 停止
```bash 
ros2 service call /idle_assistant std_srvs/srv/Trigger
```

### 单独调用语音识别服务（传入音频文件路径，返回识别文本）
- 服务名称：`/asr_infer`
- 服务类型：`chat_assistant_interfaces/srv/GetString`
- 请求参数
  - `string input`：音频文件的完整路径
  - 返回参数
    - `bool success`：表示服务调用是否成功
    - `string message`：识别结果文本 or 错误信息
  
- 请求示例
```bash 
ros2 service call /asr_infer chat_assistant_interfaces/srv/GetString "{input: '/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/chat_assistant/wavs/enable_kws.wav'}"
```
  - 响应示例
```bash
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/chat_assistant/wavs/enable_kws.wav')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='请说出正确的唤醒词号，再进行对话。😊')
```

### 单独调用大语言模型服务（传入文本，返回生成文本）
- 服务名称：`/llm_infer`
- 服务类型：`chat_assistant_interfaces/srv/GetString`
- 请求参数
  - `string input`：输入文本
  - 返回参数
    - `bool success`：表示服务调用是否成功
    - `string message`：生成结果文本 or 错误信息  
- 请求示例
```bash 
ros2 service call /llm_infer chat_assistant_interfaces/srv/GetString "{input: '你好，今天天气怎么样？'}"
```
  - 响应示例
```bash
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='你好，今天天气怎么样？')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='今天天气晴朗，适合外出。')
```

### 单独调用文本转语音服务（传入文本，合成语音并播放）
- 服务名称：`/tts_infer`
- 服务类型：`chat_assistant_interfaces/srv/GetString`
- 请求参数
  - `string input`：输入文本
  - 返回参数
    - `bool success`：表示服务调用是否成功
    - `string message`：合成结果描述 or 错误信息  
- 请求示例
```bash 
ros2 service call /tts_infer chat_assistant_interfaces/srv/GetString "{input: '你好，这是一个文本转语音的测试。'}"
```
  - 响应示例
```bash
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='你好，这是一个文本转语音的测试。')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='TTS 合成并播放音频成功')
``` 

### 单独调用文本转语音服务（传入文本，保存为 WAV 文件）
- 服务名称：`/tts_generate_wav`
- 服务类型：`chat_assistant_interfaces/srv/GenerateWav`
- 请求参数
  - `string input_text`：输入文本
  - `string input_filename`：保存的音频文件路径
  - 返回参数
    - `bool success`：表示服务调用是否成功
    - `string message`：合成结果描述 or 错误信息  
- 请求示例
```bash 
ros2 service call /tts_generate_wav chat_assistant_interfaces/srv/GenerateWav "{input_text: '你好，这是一个文本转语音的测试。', input_filename: '/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/chat_assistant/wavs/tts_output.wav'}"
```
  - 响应示例
```bash
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GenerateWav_Request(input_text='你好，这是一个文本转语音的测试。', input_filename='/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/chat_assistant/wavs/tts_output.wav')

response:
chat_assistant_interfaces.srv.GenerateWav_Response(success=True, message='WAV 文件已保存到 /home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/chat_assistant/wavs/tts_output.wav')
```