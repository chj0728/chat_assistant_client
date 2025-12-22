# 远程调用CosyVoice TTS服务

- CosyVoice 已通过docker部署在远程服务器上，提供TTS服务。
参考[CosyVoice部署文档](https://jcn384z2w5xc.feishu.cn/wiki/XZJzwavx2iaJv7k12iQcPOYUn6D)

- 可通过浏览器打开 http://192.168.50.125:50000/docs#/ 查看API文档


## 使用示例

- 激活环境
```bash
conda create -n cosyvoice_client_env python=3.9 -y
conda activate cosyvoice_client_env

pip install requests playsound3 -i https://mirrors.aliyun.com/pypi/simple/
pip install sounddevice numpy -i https://mirrors.aliyun.com/pypi/simple/
```

### 客户端请求返回wav格式音频示例
```bash
python3 client.py
```
终端输出如下，表示调用成功
```bash
测试 POST 请求，返回 wav 格式...
状态码: 200
Content-Type: audio/wav
POST 请求成功，保存到 output_post.wav
音频信息:
  声道数: 1
  采样宽度: 2 字节
  采样率: 24000 Hz
  帧数: 188160
  时长: 7.84 秒
播放完成！
```

### 实时播放TTS音频示例
- 服务端边 yield PCM → 客户端边 recv → 直接送声卡播放
- 客户端使用 `sounddevice` 库进行实时播放
```bash
python3 client_stream.py
```


### 集成到 RealtimeTTSPlayer 示例
```bash
python3 ttsplay.py
```