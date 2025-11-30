#coding=utf-8

'''
requires Python 3.6 or later
pip install asyncio
pip install websockets
pip install tenacity
'''
import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential
import asyncio
import websockets
import uuid
import json
import gzip
import copy
import os
from datetime import datetime

MESSAGE_TYPES = {11: "audio-only server response", 12: "frontend server response", 15: "error message from server"}
MESSAGE_TYPE_SPECIFIC_FLAGS = {0: "no sequence number", 1: "sequence number > 0",
                               2: "last message from server (seq < 0)", 3: "sequence number < 0"}
MESSAGE_SERIALIZATION_METHODS = {0: "no serialization", 1: "JSON", 15: "custom type"}
MESSAGE_COMPRESSIONS = {0: "no compression", 1: "gzip", 15: "custom compression method"}

appid = "9339997294"
token = "pu9fn_z0KxHfPUmjtx7jKAokNgeiFjQh"
cluster = "volcano_tts"
voice_type = "BV700_streaming"  # 免费的
host = "openspeech.bytedance.com"
api_url = f"wss://{host}/api/v1/tts/ws_binary"

# version: b0001 (4 bits)
# header size: b0001 (4 bits)
# message type: b0001 (Full client request) (4bits)
# message type specific flags: b0000 (none) (4bits)
# message serialization method: b0001 (JSON) (4 bits)
# message compression: b0001 (gzip) (4bits)
# reserved data: 0x00 (1 byte)
default_header = bytearray(b'\x11\x10\x11\x00')

request_json = {
    "app": {
        "appid": appid,
        "token": "access_token",
        "cluster": cluster
    },
    "user": {
        "uid": "388808087185088"
    },
    "audio": {
        "voice_type": "xxx",
        "encoding": "mp3",
        "speed_ratio": 0.98,
        "volume_ratio": 1.0,
        "pitch_ratio": 1.0,
    },
    "request": {
        "reqid": "xxx",
        "text": "哈哈，这位朋友。",
        "text_type": "plain",
        "operation": "xxx"
    }
}


async def test_submit(input_sentence, file_name):
    submit_request_json = copy.deepcopy(request_json)
    submit_request_json["audio"]["voice_type"] = voice_type
    submit_request_json["request"]["reqid"] = str(uuid.uuid4())
    submit_request_json["request"]["text"] = input_sentence
    submit_request_json["request"]["operation"] = "submit"
    payload_bytes = str.encode(json.dumps(submit_request_json))
    payload_bytes = gzip.compress(payload_bytes)  # if no compression, comment this line
    full_client_request = bytearray(default_header)
    full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))  # payload size(4 bytes)
    full_client_request.extend(payload_bytes)  # payload
    print("\n------------------------ test 'submit' -------------------------")
    print("request json: ", submit_request_json)
    print("\nrequest bytes: ", full_client_request)
    file_to_save = open(file_name, "wb")
    header = {"Authorization": f"Bearer; {token}"}
    async with websockets.connect(api_url, extra_headers=header, ping_interval=None) as ws:
        await ws.send(full_client_request)
        while True:
            res = await ws.recv()
            done = parse_response(res, file_to_save)
            if done:
                file_to_save.close()
                break
        print("\nclosing the connection...")


def parse_response(res, file):
    print("--------------------------- response ---------------------------")
    # print(f"response raw bytes: {res}")
    protocol_version = res[0] >> 4
    header_size = res[0] & 0x0f
    message_type = res[1] >> 4
    message_type_specific_flags = res[1] & 0x0f
    serialization_method = res[2] >> 4
    message_compression = res[2] & 0x0f
    reserved = res[3]
    header_extensions = res[4:header_size*4]
    payload = res[header_size*4:]
    print(f"            Protocol version: {protocol_version:#x} - version {protocol_version}")
    print(f"                 Header size: {header_size:#x} - {header_size * 4} bytes ")
    print(f"                Message type: {message_type:#x} - {MESSAGE_TYPES[message_type]}")
    print(f" Message type specific flags: {message_type_specific_flags:#x} - {MESSAGE_TYPE_SPECIFIC_FLAGS[message_type_specific_flags]}")
    print(f"Message serialization method: {serialization_method:#x} - {MESSAGE_SERIALIZATION_METHODS[serialization_method]}")
    print(f"         Message compression: {message_compression:#x} - {MESSAGE_COMPRESSIONS[message_compression]}")
    print(f"                    Reserved: {reserved:#04x}")
    if header_size != 1:
        print(f"           Header extensions: {header_extensions}")
    if message_type == 0xb:  # audio-only server response
        if message_type_specific_flags == 0:  # no sequence number as ACK
            print("                Payload size: 0")
            return False
        else:
            sequence_number = int.from_bytes(payload[:4], "big", signed=True)
            payload_size = int.from_bytes(payload[4:8], "big", signed=False)
            payload = payload[8:]
            print(f"             Sequence number: {sequence_number}")
            print(f"                Payload size: {payload_size} bytes")
        file.write(payload)
        if sequence_number < 0:
            return True
        else:
            return False
    elif message_type == 0xf:
        code = int.from_bytes(payload[:4], "big", signed=False)
        msg_size = int.from_bytes(payload[4:8], "big", signed=False)
        error_msg = payload[8:]
        if message_compression == 1:
            error_msg = gzip.decompress(error_msg)
        error_msg = str(error_msg, "utf-8")
        print(f"          Error message code: {code}")
        print(f"          Error message size: {msg_size} bytes")
        print(f"               Error message: {error_msg}")
        return True
    elif message_type == 0xc:
        msg_size = int.from_bytes(payload[:4], "big", signed=False)
        payload = payload[4:]
        if message_compression == 1:
            payload = gzip.decompress(payload)
        print(f"            Frontend message: {payload}")
    else:
        print("undefined message type!")
        return True

def sentence2mp3(input_sentence, file_name):
    """将文本转换为MP3音频文件"""
    try:
        loop = asyncio.get_event_loop()
        print("Using existing event loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print("Created a new event loop")

    print(f"Starting sentence2mp3 with sentence: {input_sentence}")
    loop.run_until_complete(test_submit(input_sentence, file_name))
    print(f"Completed sentence2mp3 for file: {file_name}")
    return file_name

def create_welcome_audio():
    """创建欢迎音频文件，可通过信号控制退出"""
    # 获取当前脚本所在的目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 在脚本所在目录下创建welcome_audio文件夹
    audio_dir = os.path.join(script_dir, "welcome_audio")
    if not os.path.exists(audio_dir):
        os.makedirs(audio_dir)
        print(f"创建文件夹: {audio_dir}")
    else:
        print(f"文件夹已存在: {audio_dir}")
    
    # 定义早中晚问候语
    greetings = {
        "1": {
            "name": "morning",
            "text": "早上好，欢迎光临，祝您有个美好的一天。"
        },
        "2": {
            "name": "afternoon",
            "text": "中午好，欢迎光临，午休时光请享用我们的服务。"
        },
        "3": {
            "name": "evening",
            "text": "晚上好，欢迎光临，感谢您在繁忙的一天后选择我们。"
        }
    }
    
    print("欢迎使用欢迎语音生成系统!")
    print("请选择要生成的欢迎语类型:")
    print("1 - 早上好")
    print("2 - 中午好")
    print("3 - 晚上好")
    print("输入'exit'退出")
    
    try:
        while True:
            choice = input("> ")
            
            if choice.lower() == 'exit':
                print("感谢使用，再见!")
                break
                
            if choice not in ["1", "2", "3"]:
                print("无效的选择，请输入1, 2, 3 或 exit")
                continue
            
            greeting = greetings[choice]
            print(f"已选择: {greeting['name']} - {greeting['text']}")
            
            # 用户可自定义问候语
            custom_text = input("请输入自定义问候语(直接回车使用默认问候语): ")
            if custom_text.strip():
                greeting_text = custom_text
            else:
                greeting_text = greeting['text']
            
            # 生成文件
            file_name = os.path.join(audio_dir, f"{greeting['name']}.mp3")
            try:
                sentence2mp3(greeting_text, file_name)
                print(f"已生成{greeting['name']}问候音频文件: {file_name}")
            except Exception as e:
                print(f"生成音频时出错: {str(e)}")
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，程序退出")

def signal_handler(sig, frame):
    print("\n收到退出信号，程序正在退出...")
    exit(0)

if __name__ == "__main__":
    # 注册信号处理函数
    import signal
    signal.signal(signal.SIGINT, signal_handler)  # 处理 Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 处理终止信号
    
    print("提示: 随时可以按 Ctrl+C 退出程序")
    create_welcome_audio()

#用来设置欢迎词的脚本