# coding=utf-8
import time
import hashlib
import os
import json
import requests
import sys
from pathlib import Path
src_path = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(src_path))
from config.config_loader import load_config


###  出门问问的语音合成(文本转音频)
 #### 邵的猴子序列账户(tts)
config = load_config()
appkey = config['TTS']['MobvoiTTS']['appkey']
secret = config['TTS']['MobvoiTTS']['secret']
timestamp = str(int(time.time()))

message = '+'.join([appkey,secret, timestamp])
m = hashlib.md5()
m.update(message.encode("utf8"))
signature = m.hexdigest()
http_url = 'https://open.mobvoi.com/api/tts/v1'

# 音色表
tone = {
    'zh':'mohongsheng_meet_24k',        #中文男     魔宏声
    'ar':'mercury_hamdan_48k',          #阿拉伯男   魔亚历
    'id':'mercury_gadis_48k',
    'ri':'mercury_nanami_48k'
}


def text2mp3(input_sentence, file_name, language= 'zh', timeout=10, max_retries=3):
    """
    将文本转换为MP3语音文件，带有重试机制
    
    参数:
        input_sentence: 要转换的文本
        file_name: 输出的MP3文件名
        timeout: 每次请求的超时时间(秒)，默认10秒
        max_retries: 最大重试次数，默认3次
        
    返回:
        bool: 是否成功生成音频文件
    """
    file_name = file_name + '.mp3'
    data = {
        'text': input_sentence,
        'speaker':tone[language],   #默认男声 mercury_fatima_48k为女生
        'audio_type': 'mp3',
        'speed': 1.0,
        #'ignore_limit': True,              限制字符数，开启后最大3000，未开启1000，需充值
        'merge_symbol':True,                # 模拟真人语气
        'appkey': appkey,
        'timestamp': timestamp,
        'signature': signature
    }
    headers = {'Content-Type': 'application/json'}
    retry_count = 0
    
    while retry_count < max_retries:
        retry_count += 1
        try:
            print(f"尝试第 {retry_count} 次合成 (最多 {max_retries} 次)...")
            start_time = time.time()
            
            # 发送请求，带超时设置
            response = requests.post(
                url=http_url,
                headers=headers,
                data=json.dumps(data),
                timeout=timeout
            )
            
            # 检查响应状态
            if response.status_code != 200:
                raise Exception(f"HTTP 错误，错误代码: {response.status_code}")
                
            # 检查响应内容
            if not response.content:
                raise Exception("响应内容为空")
                
            # 写入文件
            with open(file_name, "wb") as f:
                f.write(response.content)
                
            # 验证文件是否成功生成
            if not os.path.exists(file_name) or os.path.getsize(file_name) == 0:
                raise Exception("生成的文件无效")
                
            print(f"成功生成文件: {file_name} (用时: {(time.time()-start_time)*1000:.2f}ms)")
            return file_name
            
        except Exception as e:
            print(f"第 {retry_count} 次尝试失败: {str(e)}")
            
            # 删除可能生成的不完整文件
            if os.path.exists(file_name):
                try:
                    os.remove(file_name)
                except:
                    pass
                    
            time.sleep(0.1)
    
    print(f"合成失败: 达到最大重试次数 {max_retries}")
    return False


def main():
    path = os.path.dirname(os.path.abspath(__file__)) + "/3"
    # text2mp3("اختبار النص" , path ,'ar')  
    # text2mp3("您好！" , path )  
    # text2mp3("私に言ってくれませんか、大丈夫ですか" , path ,'ri')  
    text2mp3("Deposito ada pilihan mata uang apa?" , path ,'id')  

    # text2mp3("Teman baikku adalah seseorang yang menghasilkan yang terbaik dalam diri saya. " , path  )  
    

if __name__ == '__main__':
    main()