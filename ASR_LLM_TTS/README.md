# A Chat Assistant with ASR, LLM, and TTS capabilities

This project implements a chat assistant that integrates Automatic Speech Recognition (ASR), Large Language Models (LLM), and Text-to-Speech (TTS) functionalities. The assistant can process voice inputs, generate responses using LLMs, and convert text responses back to speech.

## Workflow diagram of the complete chat assistant

![alt text](<workflow.svg>)

## clone the repository

```bash
git clone http://192.168.50.220:8090/external/ymbot.git -b dev-chj
```

## creating a virtual environment

```bash
cd ASR_LLM_TTS
python3 -m venv venv

# deactivate the virtual environment
# deactivate
```

## Install dependencies

```bash
sudo apt install portaudio19-dev

source venv/bin/activate
pip3 install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

## Run the demos to test each module individually

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

- 日志前端浏览器（实时查看 + 删除历史）

```bash
cd ASR_LLM_TTS
source venv/bin/activate
cd chat_assistant

# 方式1：模块启动
python3 -m chat_assistant.log_web_server --host 0.0.0.0 --port 17890

# 方式2：ros2 环境中用入口脚本启动
# cd ASR_LLM_TTS
# source install/setup.bash
# ros2 run chat_assistant chat_assistant_log_web
```

打开浏览器访问：`http://127.0.0.1:17890`

- 实时日志：`chat_assistant/logs/asr_llm_tts`（页面自动轮询增量刷新）
- 历史日志：`chat_assistant/logs/asr_llm_tts.YYYY-MM-DD_HH`（可在页面中删除）

## Run as a ROS2 Node

- build the interfaces and package

```bash
cd ASR_LLM_TTS

deactivate
colcon build --symlink-install
# colcon build --symlink-install --packages-select chat_assistant_interfaces
# colcon build --symlink-install --packages-select chat_assistant

source install/setup.bash
source venv/bin/activate
```

- run the nodes

```bash
## ros2 run chat_assistant chat_assistant_node
## ros2 run chat_assistant chat_assistant_log_web

# use the module way
## cd chat_assistant
## python3 -m chat_assistant.chat_assistant_node
## python3 -m chat_assistant.log_web_server --host 0.0.0.0 --port 17890

# or use the run.sh script
cd  ASR_LLM_TTS

./run.sh
```

### Avilable topics

- `/asr_result`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `asr_publish_topic`，
  - 消息类型：std_msgs/msg/String
  - 发布语音识别结果文本
- `/llm_result`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `llm_publish_topic`
  - 消息类型：std_msgs/msg/String
  - 发布大语言模型生成的文本结果
- `/assistant_response`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `response_publish_topic`
  - 消息类型：chat_assistant_interfaces/msg/Response
  - 发布包含识别文本和生成文本的综合响应
- `/sound_detected_default`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `tts_active_topic`
  - 消息类型：std_msgs/msg/Bool
  - 发布 TTS 播放状态，True 表示正在播放，False 表示空闲

```bash
# 订阅示例
ros2 topic echo /assistant_response

asr_text: 喂喂喂，你好。
llm_text: 您好，我是导购小特，请问有什么可以帮助您的吗？
---
asr_text: 就是但是就是有个新的话题，然后。
llm_text: 好的，请告诉我你想讨论的新话题是什么。
---
```

```bash
# 订阅示例
ros2 topic echo /asr_result 
data: 你好，小白。
---
data: 介绍一下自己。
---
data: 查询当前时间。
---
```

### Available services

#### 重新加载配置文件

```bash
ros2 service call /reload_config std_srvs/srv/Trigger
```

#### 激活ASR

```bash
ros2 service call /activate_asr std_srvs/srv/Trigger
```

#### 停用ASR

```bash
ros2 service call /idle_asr std_srvs/srv/Trigger
```

#### 激活LLM

```bash
ros2 service call /activate_llm std_srvs/srv/Trigger
```

#### 停用LLM

```bash
ros2 service call /idle_llm std_srvs/srv/Trigger
```

#### 激活TTS

```bash
ros2 service call /activate_tts std_srvs/srv/Trigger
```

#### 停用TTS

```bash
ros2 service call /idle_tts std_srvs/srv/Trigger
```

#### 激活对话助手(同时激活LLM和TTS服务)

```bash
ros2 service call /activate_assistant std_srvs/srv/Trigger
```

#### 停止对话助手(同时停用LLM和TTS服务)

```bash
ros2 service call /idle_assistant std_srvs/srv/Trigger
```

#### 打断语音播放

```bash
ros2 service call /interrupt_audio std_srvs/srv/Trigger
```

#### 播放音频（传入音频文件路径，播放该音频文件）

- 服务名称：`/play_audio_file`
- 服务类型：`chat_assistant_interfaces/srv/GetString`
- 请求参数
  - `string input`：音频文件的完整路径
  - 返回参数
    - `bool success`：表示服务调用是否成功
    - `string message`：播放结果描述 or 错误信息  
- 请求示例

```bash
ros2 service call /play_audio_file chat_assistant_interfaces/srv/GetString "{input: '/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/chat_assistant/wavs/enable_kws.wav'}"
```

- 响应示例

```bash
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='/home/xuyao/chj/ws/ymbot/ASR_LLM_TTS/chat_assistant/wavs/enable_kws.wav')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='音频播放成功')
```

#### 语音识别服务（传入音频文件路径，返回识别文本）

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

#### 大语言模型服务（传入文本，返回生成文本）

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

#### 在线文本转语音服务（传入文本，合成语音并播放）

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

#### 离线文本转语音服务（传入文本，保存为 WAV 文件）

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

#### 接收文本输入，调用 ASR、LLM、TTS 完成一次完整的交互服务

- 服务名称：`/chat_assistant_infer`
- 服务类型：`chat_assistant_interfaces/srv/GetString`
- 请求参数
  - `string input`：输入文本
  - 返回参数
    - `bool success`：表示服务调用是否成功
    - `string message`：生成结果文本 or 错误信息  
- 请求示例

```bash
ros2 service call /chat_assistant_infer chat_assistant_interfaces/srv/GetString "{input: '你好小特'}"
```

- 响应示例

``` bash
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='你好小特')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='聊天助手完整交互已完成')
```
