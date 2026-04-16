# A Chat Assistant with ASR, LLM, and TTS capabilities

This project implements a chat assistant that integrates Automatic Speech Recognition (ASR), Large Language Models (LLM), and Text-to-Speech (TTS) functionalities. The assistant can process voice inputs, generate responses using LLMs, and convert text responses back to speech.

## Workflow diagram of the complete chat assistant

![alt text](<workflow.svg>)

## Clone the repository

```bash
git clone http://192.168.50.220:8090/external/ymbot.git -b dev-chj
```

## Creating a virtual environment && install dependencies

```bash
sudo apt install portaudio19-dev

# use pip + virtualenv to manage dependencies and virtual environment
python3 -m venv venv
source venv/bin/activate
pip3 install -r ./ASR_LLM_TTS/requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# (Recommended)or use uv to manage dependencies and virtual environment
## install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv venv --system-site-packages
source venv/bin/activate
uv pip install -r ./ASR_LLM_TTS/requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
```

## Build with ROS2

- build the interfaces and package

```bash
cd ASR_LLM_TTS
colcon build --symlink-install && source install/setup.bash

# colcon build --symlink-install --packages-select chat_assistant_interfaces
# colcon build --symlink-install --packages-select chat_assistant
```

## Run the chat assistant

```bash
# use the module way to run the chat assistant, you can run each module in a separate terminal
## source ./venv/bin/activate
## cd ./ASR_LLM_TTS/chat_assistant
## python3 -m chat_assistant.chat_assistant_node
## python3 -m chat_assistant.web.web_server --host 0.0.0.0 --port 17890

# or use the run.sh script
./ASR_LLM_TTS/run.sh

# debug mode
# ./ASR_LLM_TTS/run.sh debug
```

## Test each module individually

Refer to [chat_assistant/README.md](chat_assistant/README.md) for detailed instructions on testing each module (ASR, LLM, TTS) and the integrated chat assistant.

## 话题与服务列表

### 发布话题

- 语音识别推理结果: `/asr_result`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `asr_publish_topic`，
  - 消息类型：std_msgs/msg/String

- 大语言模型推理结果: `/llm_result`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `llm_publish_topic`
  - 消息类型：std_msgs/msg/String
  - 发布大语言模型生成的文本结果
  
- 发布综合推理结果（包含ASR和LLM结果）: `/assistant_response`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `response_publish_topic`
  - 消息类型：chat_assistant_interfaces/msg/Response

- 发布 TTS 播放状态: `/sound_detected_default`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `tts_active_topic`
  - 消息类型：std_msgs/msg/Bool
  - True 表示正在播放，False 表示空闲

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

### 订阅话题

- `/user_id`
  - 话题名称：读取[配置文件](chat_assistant/config/config.yaml)中的 `user_id_subscribe_topic`
  - 消息类型：std_msgs/msg/String
  - 订阅用户ID信息，LLM 可以根据用户ID进行上下文记忆
  - 若无话题发布用户ID信息，LLM 将无法进行上下文记忆，每次请求将被视为独立的单轮对话

### 服务列表

#### 在线重载配置文件

```bash
ros2 service call /reload_config std_srvs/srv/Trigger
```

#### 激活/非激活 ASR

```bash
# 激活ASR服务
ros2 service call /activate_asr std_srvs/srv/Trigger

# 停用ASR服务
ros2 service call /idle_asr std_srvs/srv/Trigger
```

#### 激活/非激活 LLM

```bash
# 激活LLM服务
ros2 service call /activate_llm std_srvs/srv/Trigger

# 停用LLM服务
ros2 service call /idle_llm std_srvs/srv/Trigger
```

#### 激活/非激活 TTS

```bash
# 激活TTS服务
ros2 service call /activate_tts std_srvs/srv/Trigger

# 停用TTS服务
ros2 service call /idle_tts std_srvs/srv/Trigger
```

#### 激活/非激活 对话助手(同时激活/非激活 LLM和TTS服务)

```bash
# 激活对话助手服务
ros2 service call /activate_assistant std_srvs/srv/Trigger

# 停用对话助手服务
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
  - `string user_id`：用户ID（可选，提供后LLM会使用上下文记忆）
  - 返回参数
    - `bool success`：表示服务调用是否成功
    - `string message`：生成结果文本 or 错误信息  
- 请求与响应示例
  - 未提供 user_id，LLM 不会使用上下文记忆，直接根据输入文本生成回答，适合单轮对话

```bash
#--------------requests without user_id, no context memory --------------
ros2 service call /llm_infer chat_assistant_interfaces/srv/GetString "{input: '请记住我喜欢蓝色',user_id: ''}"
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='请记住我喜欢蓝色', user_id='')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='好的，我会记住您喜欢蓝色<INTENT>WAIT_FOR_TALK</INTENT>')

ros2 service call /llm_infer chat_assistant_interfaces/srv/GetString "{input: '请问我喜欢什么颜色',user_id: ''}"
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='请问我喜欢什么颜色', user_id='')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='我目前无法获取您的个人偏好信息。请问有什么我可以帮助您的吗？<INTENT>WAIT_FOR_TALK</INTENT>')
```

- 请求与响应示例
  - 提供 user_id，LLM 会使用上下文记忆，适合连续对话
  - 同一个 user_id 的请求可以共享上下文记忆，LLM 可以回忆之前的对话内容
  - 不同 user_id 的请求上下文独立

```bash
#--------------requests with user_id:'1'--------------
ros2 service call /llm_infer chat_assistant_interfaces/srv/GetString "{input: '请记住我喜欢蓝色',user_id: '1'}"
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='请记住我喜欢蓝色', user_id='1')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='好的，我记住了您喜欢蓝色<INTENT>WAIT_FOR_TALK</INTENT>')

ros2 service call /llm_infer chat_assistant_interfaces/srv/GetString "{input: '请问我喜欢什么颜色',user_id: '1'}"
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='请问我喜欢什么颜色', user_id='1')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='您喜欢蓝色<INTENT>WAIT_FOR_TALK</INTENT>')


# --------------requests with different user_id: '2' --------------
ros2 service call /llm_infer chat_assistant_interfaces/srv/GetString "{input: '请记住我喜欢红色',user_id: '2'}"
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='请记住我喜欢红色', user_id='2')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='好的，我会记住您喜欢红色<INTENT>WAIT_FOR_TALK</INTENT>')

ros2 service call /llm_infer chat_assistant_interfaces/srv/GetString "{input: '请问我喜欢什么颜色',user_id: '2'}"

waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='请问我喜欢什么颜色', user_id='2')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='我记得您喜欢红色<INTENT>WAIT_FOR_TALK</INTENT>')
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
  - `string user_id`：用户ID（可选，提供后LLM会使用上下文记忆）
  - 返回参数
    - `bool success`：表示服务调用是否成功
    - `string message`：生成结果文本 or 错误信息  
- 请求示例

```bash
ros2 service call /chat_assistant_infer chat_assistant_interfaces/srv/GetString "{input: '你好小特',user_id: ''}"
```

- 响应示例

``` bash
waiting for service to become available...
requester: making request: chat_assistant_interfaces.srv.GetString_Request(input='你好小特')

response:
chat_assistant_interfaces.srv.GetString_Response(success=True, message='聊天助手完整交互已完成')
```
