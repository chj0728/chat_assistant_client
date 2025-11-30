#coding=utf-8

'''
requires Python 3.6 or later
pip install tenacity
pip install asyncio
pip install websockets
'''

import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import asyncio
import websockets
import uuid
import json
import gzip
import copy
import time
import sys
from playsound import playsound
import os
from datetime import datetime
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# 添加到系统路径
sys.path.insert(0, parent_dir)
from record_uploader import TIMBRE

MESSAGE_TYPES = {11: "audio-only server response", 12: "frontend server response", 15: "error message from server"}
MESSAGE_TYPE_SPECIFIC_FLAGS = {0: "no sequence number", 1: "sequence number > 0",
                               2: "last message from server (seq < 0)", 3: "sequence number < 0"}
MESSAGE_SERIALIZATION_METHODS = {0: "no serialization", 1: "JSON", 15: "custom type"}
MESSAGE_COMPRESSIONS = {0: "no compression", 1: "gzip", 15: "custom compression method"}

appid = "9339997294"
token = "pu9fn_z0KxHfPUmjtx7jKAokNgeiFjQh"
cluster = "volcano_tts"
voice_type_1 = TIMBRE   # "BV700_streaming" 免费的,女声  "BV705_streaming" 男声|| "ICL_zh_female_zhixingwenwan_tob"  # 程程音色
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
        "speed_ratio": 1.0,
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

# 配置重试装饰器
@retry(
    # 重试条件：websocket错误、连接错误或超时
    retry=retry_if_exception_type((
        websockets.ConnectionClosed,  # 替换为具体的异常类
        ConnectionError,
        asyncio.TimeoutError
    )),
    # 最大重试次数
    stop=stop_after_attempt(3),
    # 指数退避策略：初始等待1秒，之后翻倍，最大等待8秒
    wait=wait_exponential(multiplier=1, min=1, max=8),
    # 重试前将执行的回调
    before_sleep=lambda retry_state: print(f"连接失败，{retry_state.attempt_number}秒后重试... (尝试 {retry_state.attempt_number}/{3})"),
)
async def submit_with_retry(input_sentence, file_path, voice_type=voice_type_1, timeout=30):
    """带有超时和重试机制的文本转语音提交函数
    
    Args:
        input_sentence: 要转换的文本
        file_path: 输出文件路径（不含扩展名）
        timeout: 请求总超时时间（秒）
        
    Returns:
        完整的输出文件路径
    """
    # 确保文件路径不重复添加扩展名
    if file_path.lower().endswith('.mp3'):
        output_path = file_path
    else:
        output_path = file_path + ".mp3"
    
    # 确保目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
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
    
    # print("\n------------------------ test 'submit' -------------------------")
    # print("request json: ", submit_request_json)
    # print("\nrequest bytes: ", full_client_request)
    # print(f"Output file path: {output_path}")
    
    file_to_save = open(output_path, "wb")
    header = {"Authorization": f"Bearer; {token}"}
    
    start_time = time.time()
    
    try:
        # 设置连接超时
        async with websockets.connect(
            api_url, 
            extra_headers=header, 
            ping_interval=None,
            close_timeout=10,  # 10秒关闭超时
            open_timeout=10,   # 10秒连接超时
        ) as ws:
            # 发送请求
            await ws.send(full_client_request)
            
            # 接收响应，添加超时控制
            while True:
                if time.time() - start_time > timeout:
                    raise asyncio.TimeoutError(f"请求总超时，已经过了{timeout}秒")
                
                try:
                    # 为每次接收设置5秒超时
                    res = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    done = parse_response(res, file_to_save)
                    if done:
                        file_to_save.close()
                        print("\合成成功")
                        break
                except asyncio.TimeoutError:
                    print("接收超时，检查连接状态...")
                    # 检查连接是否仍然开放
                    if not ws.open:
                        raise ConnectionError("WebSocket连接已关闭")
                    # 继续尝试接收
                    continue
                    
    except Exception as e:
        print(f"发生错误: {str(e)}")
        # 确保文件被关闭
        if not file_to_save.closed:
            file_to_save.close()
        raise  # 重新抛出异常以触发重试
    
    return output_path

def parse_response(res, file):
    """解析服务器响应"""
    # print("--------------------------- response ---------------------------")
    protocol_version = res[0] >> 4
    header_size = res[0] & 0x0f
    message_type = res[1] >> 4
    message_type_specific_flags = res[1] & 0x0f
    serialization_method = res[2] >> 4
    message_compression = res[2] & 0x0f
    reserved = res[3]
    header_extensions = res[4:header_size*4]
    payload = res[header_size*4:]
    
    # print(f"            Protocol version: {protocol_version:#x} - version {protocol_version}")
    # print(f"                 Header size: {header_size:#x} - {header_size * 4} bytes ")
    # print(f"                Message type: {message_type:#x} - {MESSAGE_TYPES[message_type]}")
    # print(f" Message type specific flags: {message_type_specific_flags:#x} - {MESSAGE_TYPE_SPECIFIC_FLAGS[message_type_specific_flags]}")
    # print(f"Message serialization method: {serialization_methodvoice_type")
    
    if message_type == 0xb:  # audio-only server response
        if message_type_specific_flags == 0:  # no sequence number as ACK
            # print("                Payload size: 0")
            return False
        else:
            sequence_number = int.from_bytes(payload[:4], "big", signed=True)
            payload_size = int.from_bytes(payload[4:8], "big", signed=False)
            payload = payload[8:]
            # print(f"             Sequence number: {sequence_number}")
            # print(f"                Payload size: {payload_size} bytes")
        
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
        # print(f"            Frontend message: {payload}")
    
    else:
        # print("undefined message type!")
        return True

def dbsentence2mp3(input_sentence, file_name, voice_type=voice_type_1, timeout=30):
    """
    将文本转换为MP3文件，包含超时和重试机制
    
    Args:
        input_sentence: 要转换的文本内容
        file_name: 输出文件名（可以包含路径，不需要扩展名）
        timeout: 超时时间（秒）
        
    Returns:
        生成的音频文件完整路径，失败时返回None
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        # print("Using existing event loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # print("Created a new event loop")

    # 添加日志追踪
    # print(f"Starting sentence2mp3 with sentence: {input_sentence}")
    # print(f"Target file name: {file_name}")
    start_time = time.time()
    
    try:
        # 确保文件名处理一致性
        if file_name.lower().endswith('.mp3'):
            file_path = file_name
        else:
            file_path = file_name
        
        result = loop.run_until_complete(submit_with_retry(input_sentence, file_path, voice_type, timeout))
        process_time = time.time() - start_time
        # print(f"Completed sentence2mp3 for file: {result} in {process_time:.2f} seconds")
        return result
    except Exception as e:
        process_time = time.time() - start_time
        # print(f"Failed to generate audio after {process_time:.2f} seconds: {str(e)}")
        # 返回错误状态
        return None


def dbsentence2mp3andplay(input_sentence, file_name, voice_type=voice_type_1, timeout=30):
    """
    将文本转换为MP3文件，包含超时和重试机制
    
    Args:
        input_sentence: 要转换的文本内容
        file_name: 输出文件名（可以包含路径，不需要扩展名）
        timeout: 超时时间（秒）
        
    Returns:
        生成的音频文件完整路径，失败时返回None
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        print("Using existing event loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print("Created a new event loop")

    # 添加日志追踪
    print(f"Starting sentence2mp3 with sentence: {input_sentence}")
    print(f"Target file name: {file_name}")
    start_time = time.time()
    
    try:
        # 确保文件名处理一致性
        if file_name.lower().endswith('.mp3'):
            file_path = file_name
        else:
            file_path = file_name
            
        result = loop.run_until_complete(submit_with_retry(input_sentence, file_path, voice_type, timeout))
        process_time = time.time() - start_time
        print(f"Completed sentence2mp3 for file: {result} in {process_time:.2f} seconds")
        playsound(result)
        return result
    except Exception as e:
        process_time = time.time() - start_time
        print(f"Failed to generate audio after {process_time:.2f} seconds: {str(e)}")
        # 返回错误状态
        return None

# input_sentence = """
# 随着海运繁荣，太仓从"居民鲜少"的渔村迅速发展为"通都大邑"。大家看这幅元代城区示意图，致和塘沿岸商肆林立，各地商贾云集。而随着海运、海贸的蓬勃发展，元廷渐次设立起管理机构，加强了对太仓港口的控制。并且据学者统计，明代弘治年间太仓城内的25座桥梁中，有20座建于元代。时至今日，太仓仍有五座元代石桥存世，均为全国重点文物保护单位。元代太仓官方、私人在短时间内集中建造如此多的桥梁，足见人口鼎盛、交通发达、贸易繁荣之盛。
# """
# input_sentence = """
# 到了永乐三年，即公元1405年，历史的机遇,将太仓推向巅峰：我带领船队从这里扬帆启航，奉永乐皇帝“宣德化而怀柔远人”的敕令，开启了七下西洋的行程。可以说，没有元代海运打下的基础，就没有永乐时代的辉煌。这座港口，正是古代中国开放包容、联通世界的见证！
# 在我身后的是我所带领的“海上巨无霸”船队上！这支史诗级船队包含了水船，战船，座船，粮船，马船，宝船，其中最大的宝船长四十四丈四尺，宽十八丈，是当时世界上最先进的木帆船之一。这一支功能完备的海上编队，保证了远行官兵的衣食住行和各个方面的需求。
# """
# input_sentence = """
# 这里呈现的是元代海运仓储系统的珍贵实物证据。位于太仓南郊的海运仓遗址，它始建于元代，后经明代扩建，形成了规模宏大的国家粮仓体系。根据史料记载，这座海运仓共建有91座仓廪，可储存江南各地征集而来的漕粮数百万石，是目前我国发现的规模最大的元明时期国家仓储遗址。
# """

# input_sentence = """
# 我在呢
# """
# input_sentence = """
# 尊敬的各位领导，下午好！我是智能机器人小雪，欢迎来到江苏星瀚航天科技有限公司。我司始终致力于科技创新，在“星瀚计划”全球泛在感知卫星系统与应用服务平台研发及产业化、人形机器人研发及产业化等领域积极探索，努力为高新区的航空航天和智能制造产业发展贡献力量。今天，我们非常荣幸能向各位领导展示最新的技术成果，也衷心期待您的宝贵意见和建议，助力我们在高质量发展的道路上走得更稳、更远。谢谢大家！
# """
# input_sentence = """
# 你好呀
# """
# file_path = '/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/wake.mp3'
# dbsentence2mp3(input_sentence,file_path)
# while True:
# 	input_sentence = input("请输入音频内容：")
# 	file_path = input("请输入音频名：")
# 	if not file_path.endswith(".mp3"):
# 		file_path += ".mp3"
# 	file_path = "/home/ymrobot/ymzz_into/" + file_path
# 	dbsentence2mp3(input_sentence,file_path)

