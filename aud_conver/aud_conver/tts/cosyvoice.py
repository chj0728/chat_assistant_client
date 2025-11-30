import os,sys
import dashscope
from dashscope.audio.tts_v2 import VoiceEnrollmentService, SpeechSynthesizer,AudioFormat
import requests
project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(str(project_dir))
from config.config_loader import write_timbre

APIKEY = 'sk-2644a4c474384b208706d83bad25b0a7'

target_model = "cosyvoice-v2"

def upload_voice(voice_path):
    url = "http://47.110.253.191:8080/robot/audioFiles/uploadTimbre"
    files = {'file': open(voice_path, 'rb')}

    response = requests.post(url, files=files)
    if response.status_code == 200:
        result = response.json()
        download_url = result['data']
        print(f"下载URL: {download_url}")
        return download_url
    else:
        print(f"上传失败: {response.text}")

def create_voice(voice_path,prefix ='prefix'):
    """
    创建音色
    param: voice_path 声音复刻所需要的音频文件
    param: prefix 音色自定义前缀，仅允许数字和小写字母，小于十个字符。
    """
    dashscope.api_key = APIKEY  # 如果您没有配置环境变量，请在此处用您的API-KEY进行替换
    url = upload_voice(voice_path)
    prefix = prefix
    # 创建语音注册服务实例
    service = VoiceEnrollmentService()
    # 调用create_voice方法复刻声音，并生成voice_id
    voice_id = service.create_voice(target_model=target_model, prefix=prefix, url=url)
    print("requestId: ", service.get_last_request_id())
    print(f"your voice id is {voice_id}")
    return voice_id

def search_voice(prefix = None):
    dashscope.api_key = APIKEY  # 如果您没有配置环境变量，请在此处用您的API-KEY进行替换
    prefix = prefix # 请按实际情况进行替换

    # 创建语音注册服务实例
    service = VoiceEnrollmentService()
    voices = service.list_voices(prefix=prefix, page_index=0, page_size=10)
    print("request id为：", service.get_last_request_id())
    print(f"查询到的音色为：{voices}")

def update_voice(voice_path,voice_id ='cosyvoice-v2-prefix-xxx'):
    dashscope.api_key = APIKEY  # 如果您没有配置环境变量，请在此处用您的API-KEY进行替换
    url = upload_voice(voice_path)

    # 创建语音注册服务实例
    service = VoiceEnrollmentService()
    service.update_voice(voice_id=voice_id, url=url)
    print("request id为：", service.get_last_request_id())

def text2mp3(text,audio_path,voice_id):
    """
    将给定文本转换为 MP3 音频文件并保存到指定路径。
    Args:
        text (str): 需要转换为语音的文本内容，例如："今天天气怎么样？"。
        audio_path (str): 输出音频文件的完整路径，例如："/path/to/output.mp3"。注意：必须是文件路径，不能是目录路径。
        voice_id (str): 语音合成引擎使用的音色 ID，例如："xiaoyun" 或 "sambert-xxx"。
    Returns:
        None: 音频文件会直接保存 audio_path，不返回内容。
    """
    dashscope.api_key = APIKEY
    synthesizer = SpeechSynthesizer(model=target_model, voice=voice_id,speech_rate=1.0)
    audio = synthesizer.call(text)
    print("合成成功，文件路径 ", audio_path)

    # 将合成的音频文件保存到本地文件
    with open(audio_path, "wb") as f:
        f.write(audio)


def text2pcm(text,audio_path,voice_id):
    dashscope.api_key = APIKEY
    synthesizer = SpeechSynthesizer(model=target_model, voice=voice_id,speech_rate=1.0 ,format=AudioFormat.PCM_48000HZ_MONO_16BIT)
    audio = synthesizer.call(text)
    print("合成成功，文件路径 ", audio_path)

    # 将合成的音频文件保存到本地文件
    with open(audio_path, "wb") as f:
        f.write(audio)

def main():
    
    timbre_path = "/mnt/d/ymzz/ws_ros/郑和纪念馆-郑小和/audio/30.mp3"
    # 创建音色
    # prefix = 'kid'
    # voice_id = create_voice(timbre_path,prefix)
    # write_timbre(prefix,voice_id)
    # 更新音色
    # update_voice(timbre_path,'cosyvoice-v2-kid-fabfd30cbd284250b10c4dcad265476d')
    # 语音合成
    text = """
        "您好，我是智能语音助手。今天天气真不错，阳光明媚，微风拂面。我想和您分享一些关于人工智能的有趣知识。机器学习、深度学习、自然语言处理，这些技术正在改变我们的生活方式。您知道吗？语音合成技术已经可以高度还原人类的声音特征，包括音调、节奏和情感表达。这真是一项令人惊叹的技术进步！无论是日常对话、讲故事还是专业讲解，现代语音系统都能提供自然流畅的体验。希望我的声音能让您感到舒适和愉悦。如果您有任何问题或需要帮助，随时都可以告诉我。谢谢您的聆听，祝您有美好的一天！"
    """
    audio_path = '/mnt/d/ymzz/ws_ros/realtime_conversation/voice.mp3'
    voice_id = 'libai_v2'
    text2mp3(text,audio_path,voice_id)


if __name__ == "__main__":
    main()
