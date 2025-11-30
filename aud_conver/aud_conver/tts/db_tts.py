#coding=utf-8

'''
requires Python 3.6 or later
pip install tenacity
pip install asyncio
pip install websockets
'''

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import asyncio
import websockets
import uuid
import json
import gzip
import copy
import time
import os
from datetime import datetime
from collections import deque


MESSAGE_TYPES = {11: "audio-only server response", 12: "frontend server response", 15: "error message from server"}
MESSAGE_TYPE_SPECIFIC_FLAGS = {0: "no sequence number", 1: "sequence number > 0",
                               2: "last message from server (seq < 0)", 3: "sequence number < 0"}
MESSAGE_SERIALIZATION_METHODS = {0: "no serialization", 1: "JSON", 15: "custom type"}
MESSAGE_COMPRESSIONS = {0: "no compression", 1: "gzip", 15: "custom compression method"}

appid = "9339997294"
token = "pu9fn_z0KxHfPUmjtx7jKAokNgeiFjQh"
cluster = "volcano_tts"
voice_type = "ICL_zh_male_huzi_v1_tob"   ## 音色
host = "openspeech.bytedance.com"
api_url = f"wss://{host}/api/v1/tts/ws_binary"


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
async def submit_with_retry(input_sentence, file_path, timeout=30):
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
    print(f"Output file path: {output_path}")
    
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
                        # print("\n连接正常关闭")
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
    print("--------------------------- response ---------------------------")
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
    # print(f"Message serialization method: {serialization_method:#x} - {MESSAGE_SERIALIZATION_METHODS[serialization_method]}")
    # print(f"         Message compression: {message_compression:#x} - {MESSAGE_COMPRESSIONS[message_compression]}")
    # print(f"                    Reserved: {reserved:#04x}")
    
    if header_size != 1:
        print(f"           Header extensions: {header_extensions}")
    
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
        print(f"            Frontend message: {payload}")
    
    else:
        print("undefined message type!")
        return True

def sentence2mp3(input_sentence, file_name, timeout=10):
    """
    将文本转换为MP3文件，包含内置重试机制
    
    Args:
        input_sentence: 要转换的文本内容
        file_name: 输出文件名（可以包含路径，不需要扩展名）
        timeout: 每次尝试的超时时间（秒）
        
    Returns:
        成功时返回生成的音频文件完整路径，失败时返回False
    """
    

    try:
        loop = asyncio.get_event_loop()
        # print("Using existing event loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # print("Created a new event loop")

    # 添加日志追踪
    # print(f"Starting sentence2mp3 with sentence: {input_sentence}")
    
    # 确保文件名处理一致性
    if file_name.lower().endswith('.mp3'):
        file_path = file_name
    else:
        file_path = file_name
    
    # 内置重试逻辑
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        start_time = time.time()
        print(f"尝试 {attempt}/{max_attempts} 合成: {input_sentence[:30]}...")
        
        try:
            # 为每次尝试使用不同的文件名，以避免覆盖
            attempt_file_path = f"{file_path}_attempt{attempt}" if attempt > 1 else file_path
            
            # 调用底层的提交函数
            result = loop.run_until_complete(submit_with_retry(input_sentence, attempt_file_path, timeout))
            
            process_time = time.time() - start_time
            print(f"尝试 {attempt} 成功! 用时: {process_time:.2f}秒")
            
            # 如果不是第一次尝试成功，并且使用了不同的文件名，将最终结果复制到原始请求的文件名
            if attempt > 1 and attempt_file_path != file_path:
                import shutil
                try:
                    # 如果目标文件已存在，先删除
                    if os.path.exists(f"{file_path}.mp3"):
                        os.remove(f"{file_path}.mp3")
                    # 复制文件
                    shutil.copy2(f"{attempt_file_path}.mp3", f"{file_path}.mp3")
                    print(f"将成功结果从 {attempt_file_path}.mp3 复制到 {file_path}.mp3")                    
                    # 删除临时尝试文件
                    os.remove(f"{attempt_file_path}.mp3")
                except Exception as copy_error:
                    print(f"复制文件过程中出错: {str(copy_error)}")
                    # 即使复制失败，仍然返回成功获取的文件路径
                    return f"{attempt_file_path}.mp3"
                
            return f"{file_path}.mp3"  # 成功返回
            
        except Exception as e:
            process_time = time.time() - start_time
            print(f"尝试 {attempt} 失败: {str(e)}, 用时: {process_time:.2f}秒")
            
            # 如果不是最后一次尝试，等待短暂时间后重试
            if attempt < max_attempts:
                retry_wait = 1  # 等待1秒后重试
                print(f"将在 {retry_wait} 秒后进行第 {attempt+1} 次尝试...")
                time.sleep(retry_wait)
            else:
                print(f"所有 {max_attempts} 次尝试均失败，放弃合成")
    
    # 所有尝试都失败，返回False
    return False


if __name__ == "__main__":
    text = """

卿且畅言

    """
    filename = os.path.join("/mnt/d/wake.mp3")
    sentence2mp3(text,filename)


