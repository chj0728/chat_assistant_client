import requests
import time
import os
import yaml
import hashlib
import chardet
from datetime import datetime


def load_yaml_config(file_path = "/home/ymrobot/ros2_ws_guidance/config.yaml"):
    """加载 YAML 配置文件"""
    try:
        with open(file_path, 'r') as file:
            config = yaml.safe_load(file)
            return config
    except FileNotFoundError:
        print(f"错误: 文件 {file_path} 不存在")
        return None
    except yaml.YAMLError as e:
        print(f"YAML 解析错误: {e}")
        return None

config = load_yaml_config()  
FILE_PATH = config["aud_http_upload"].get("FILE_PATH", '/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/records.csv')
UPLOAD_URL = config["aud_http_upload"].get("UPLOAD_URL", 'http://47.110.253.191:8080/robot/robotVoiceDialogue/upload')
AUTH_TOKEN = config["aud_http_upload"].get("AUTH_TOKEN", 'u1nWHkDh1ukkuIhMiXe7Tq9CiX2iOxyEECD-sUqmIfA')  # 授权token, 从配置文件获取
ROBOT_ID = config["aud_http_upload"].get("ROBOT_ID", 'YMZZ202500007')  # 机器人ID（新增常量）, 从配置文件获取
TIMBRE = config["audio_config"].get("TIMBRE", "BV700_streaming")    # 默认对话音色
APP_ID = config["audio_config"].get("APP_ID", "9832aab81d0a41b6a65b8a4bfd0a09ef")   # 默认为小雪人设
MAX_RETRIES = 3  # 上传重试次数


def generate_signature(timestamp):
    """生成签名: md5(robotId + timestamp + token)"""
    print("当前时间戳： ",timestamp)
    sign_str = f"{ROBOT_ID}{timestamp}{AUTH_TOKEN}"
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def upload_file(file_path = FILE_PATH):
    """通过HTTP上传文件（更新签名逻辑）"""
    timestamp = str(int(time.time() * 1000))  # 当前毫秒时间戳
    sign = generate_signature(timestamp)
    
    try:
        with open(file_path, 'rb') as f:
            rawdata = f.read()
            result = chardet.detect(rawdata)
        
        with open(file_path, 'r', encoding=result['encoding']) as f:
            content = f.read()
            encoded_content = content.encode('utf-8')

        files = {
            'file': (f'records_{str(datetime.now().strftime("%Y%m%d%H%M%S"))}.csv', encoded_content),
        }
        
        data = {
            'robotId': ROBOT_ID,
            'timestamp': timestamp,
            'sign': sign
        }
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    UPLOAD_URL,
                    files=files,
                    data=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    print("records.csv upload sucess")
                    return True
                else:
                    print(f"Upload failed with status code: {response.status_code}, response: {response.text}")
                    if attempt == MAX_RETRIES - 1:
                        return False
                    time.sleep(5)
                    
            except requests.exceptions.RequestException as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == MAX_RETRIES - 1:
                    return False
                time.sleep(5)
            
    except Exception as e:
        print("upload failed")
        return False

# config = load_yaml_config()
# if config:
#     print(config["aud_http_upload"].get("FILE_PATH_", "你好"))
#     print(type(config))
# else:
#     print("null")