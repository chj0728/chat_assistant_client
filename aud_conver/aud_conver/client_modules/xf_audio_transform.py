import websocket
import datetime
import hashlib
import base64
import hmac
import json
import time
import ssl
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
import _thread as thread
import pyaudio
import queue
from urllib.parse import urlencode
import ctypes
# 加载共享库
import time
from datetime import datetime

# 常量
STATUS_FIRST_FRAME = 0
STATUS_CONTINUE_FRAME = 1
STATUS_LAST_FRAME = 2
# 初始化语音识别参数


class Ws_Param(object):
    def __init__(self, APPID='65d73228', APIKey='9b400d55ae282e46c878f38bed712542', APISecret='OTVlNzgzNzExN2FhZDlmZjVjZDY5ZTgx', vad_eos=1500):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret

        self.CommonArgs = {"app_id": self.APPID}
        self.BusinessArgs = {
            "domain": "iat",
            "language": "zh_cn",
            "accent": "mandarin",
            "vinfo": 0,
            "vad_eos": vad_eos,  # 自定义 VAD 时长
        }

    def create_url(self):
        url = 'wss://ws-api.xfyun.cn/v2/iat'
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = f"host: ws-api.xfyun.cn\n" \
                           f"date: {date}\n" \
                           "GET /v2/iat HTTP/1.1"

        signature_sha = hmac.new(self.APISecret.encode('utf-8'), signature_origin.encode('utf-8'), hashlib.sha256).digest()
        signature = base64.b64encode(signature_sha).decode()

        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode()

        params = {
            "authorization": authorization,
            "date": date,
            "host": "ws-api.xfyun.cn"
        }
        return f"{url}?{urlencode(params)}"

def transcribe_audio(ws_param=None, max_retries=3, vad_eos=1500, reconnect_delay=0.01):
    """
    语音转录函数接口，返回转录后的文字。
    
    :param ws_param: Ws_Param对象，包含API相关信息
    :param max_retries: 最大重试次数
    :param vad_eos: VAD时长（ms）
    :param reconnect_delay: 重连延时（秒）
    :return: 转录后的文字
    """
    if ws_param is None:
        ws_param =  Ws_Param()
    all_results = ""
    empty_count = 0  # 记录连续未检测到识别内容的次数
    # 传递路径作为字节类型
    # wakelib.start_speech_recognition(b"/home/ymzz/ws_ros/src/realtime_conversation/src/client_modules/wake/bin/resource/many-keywords.txt")
    # # 调用 start_speech_recognition 函数
    # wakelib.start_speech_recognition.argtypes = [ctypes.c_char_p]
    def on_message(ws, message):
        nonlocal all_results, empty_count
        try:
            msg = json.loads(message)
            code = msg.get("code")
            sid = msg.get("sid")

            if code != 0:
                errMsg = msg.get("message")
                print(f"sid:{sid} call error:{errMsg} code is:{code}")
                return

            data = msg.get("data", {})
            result_data = data.get("result", {})
            ws_list = result_data.get("ws", [])

            if not ws_list:
                return

            for ws_item in ws_list:
                cw_list = ws_item.get("cw", [])
                for cw in cw_list:
                    word = cw.get("w", "")
                    all_results += word

            status = data.get("status")
            if status == STATUS_LAST_FRAME:  # 识别完成时
                print("\n识别完成！")
                print(all_results)  # 打印完整句子
                if all_results == "":
                    empty_count += 1
                    print(f"识别内容为空，计数器增加至: {empty_count}")
                    ws.close()
                    
                else:
                    empty_count = max_retries #0
                    ws.close()  # 识别完成后关闭连接并返回结果
                    time2 = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    print(time2)
                    return all_results  # 返回转录结果
                    
        except Exception as e:
            print("接收消息时发生异常:", e)

    def on_error(ws, error):
        print("### error:", error)

    def on_close(ws, a, b):
        nonlocal empty_count
        print("### closed ###")
        print("WebSocket连接关闭，准备重新连接...")

        # 检查是否达到最大连续未检测次数
        if empty_count >= max_retries:
            print("达到最大连续未检测次数，不再重连，程序结束。")
            return  # 退出on_close，不再尝试重连

        print(f"尝试在 {reconnect_delay} 秒后重新连接...")
        time.sleep(reconnect_delay)
        wsUrl = ws_param.create_url()
        new_ws = websocket.WebSocketApp(
            wsUrl,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        new_ws.on_open = on_open
        new_ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def on_open(ws):
        print("WebSocket连接成功，开始语音识别...")
        
        def run(*args):
            status = STATUS_FIRST_FRAME
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16,
                            channels=1,
                            rate=16000,
                            input=True,
                            # input_device_index=0,  # 指定设备索引
                            frames_per_buffer=1024)
            time1 = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(time1)
            print("麦克风已打开，开始实时捕捉音频流...")

            try:
                while True:
                    buf = stream.read(8000, exception_on_overflow=False)
                    if not buf:
                        status = STATUS_LAST_FRAME

                    if status == STATUS_FIRST_FRAME:
                        audio_data = {
                            "common": ws_param.CommonArgs,
                            "business": ws_param.BusinessArgs,
                            "data": {
                                "status": 0,
                                "format": "audio/L16;rate=16000",
                                "audio": str(base64.b64encode(buf), 'utf-8'),
                                "encoding": "raw"
                            }
                        }
                        ws.send(json.dumps(audio_data))
                        status = STATUS_CONTINUE_FRAME
                    elif status == STATUS_CONTINUE_FRAME:
                        audio_data = {
                            "data": {
                                "status": 1,
                                "format": "audio/L16;rate=16000",
                                "audio": str(base64.b64encode(buf), 'utf-8'),
                                "encoding": "raw"
                            }
                        }
                        ws.send(json.dumps(audio_data))
                    elif status == STATUS_LAST_FRAME:
                        audio_data = {
                            "data": {
                                "status": 2,
                                "format": "audio/L16;rate=16000",
                                "audio": str(base64.b64encode(buf), 'utf-8'),
                                "encoding": "raw"
                            }
                        }
                        ws.send(json.dumps(audio_data))
                        break
            except Exception as e:
                # print("发送音频时发生异常:", e)
                pass
            finally:
                stream.stop_stream()
                stream.close()
                p.terminate()

        thread.start_new_thread(run, ())

    # 启动WebSocket连接
    wsUrl = ws_param.create_url()
    # 格式化时间，精确到毫秒
    current_time = datetime.now()
    formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'

    print("当前时间（精确到毫秒）:", formatted_time)
    ws = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.on_open = on_open
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    # 如果所有处理都成功，返回转录后的文字
    return all_results


if __name__ == "__main__":
    # 创建WebSocket参数对象
    ws_param = Ws_Param(
        APPID='65d73228',
        APIKey='9b400d55ae282e46c878f38bed712542',
        APISecret='OTVlNzgzNzExN2FhZDlmZjVjZDY5ZTgx',
        vad_eos=500  # 可根据需求调整
    )
    transcribed_text = transcribe_audio(ws_param, max_retries=3, vad_eos=500, reconnect_delay=0.5)
    print("转录结果:", transcribed_text)


#这是一个基于kdxf的流式websocket语音识别代码  更新时间25.3.20