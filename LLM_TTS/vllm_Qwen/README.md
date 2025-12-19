# Vllm + Qwen
已经在5090服务器上通过docker部署了Vllm + Qwen/Qwen3-8B 模型 
参考[部署文档](https://jcn384z2w5xc.feishu.cn/wiki/LJqnw4iMFiw4y3kBlkscuK4ynFT)


## 使用示例

- 激活环境
```bash
conda create -n vllm_qwen_client_env python=3.9 -y
conda activate vllm_qwen_client_env
pip install requests json -i https://mirrors.aliyun.com/pypi/simple/
```
### 测试文本对话脚本
```bash
python3 continue_chat.py
```
终端输出如下，表示调用成功
```bash
开始与模型对话（输入 exit 或 quit 退出）
你：你好
助手：你好！😊 有什么我可以帮助你的吗？

你：简单介绍自己
助手：你好！我是Qwen，阿里巴巴集团旗下的超大规模语言模型。我能够理解并生成多种语言，具备广泛的知识和强大的语言处理能力。我可以帮助你解答问题、创作文字、编程、分析数据等。我的目标是成为你可靠的助手，提供高效、准确和友好的服务。有什么我可以帮你的吗？😊

你：exit
对话结束
```

### 测试文本对话 + TTS脚本
```bash
python3 continue_chat_tts.py
```
终端输出如下，表示调用成功
```bash
开始与模型对话（输入 exit 或 quit 退出）
你：你好
助手：你好！😊 有什么我可以帮助你的吗？


 正在合成语音...

 正在播放语音...
你：简单介绍自己
助手：你好！我是Qwen，由通义实验室开发的超大规模语言模型。我擅长多种语言，可以进行文本生成、回答问题、创作故事、写代码等任务。我致力于提供准确、有用和友好的帮助，让每个与我互动的人都能感受到温暖和支持。有什么我可以帮你的吗？😊


 正在合成语音...

 正在播放语音...
你：quit
对话结束
```