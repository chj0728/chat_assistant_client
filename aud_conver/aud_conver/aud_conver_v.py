#!/usr/bin/env python3
#coding=utf-8

"""
@brief      Enables a robot to engage in voice conversations by implementing 
            the ASR (Automatic Speech Recognition), VLLM (Vison-Language Large Model),
            and TTS (Text-to-Speech) processes.
@file       rosnode.py
@author     FinnShaw
@date       2025-08-05

This script provides a complete solution for robotic voice interaction. It includes:
- ASR: Captures human voice from a microphone and converts it into text.
- VLLM: Processes the recognized text through a vision-language large model to generate intelligent responses.
- TTS: Converts the generated text back into speech that can be played out loud.

The main purpose is to enable seamless voice communication between humans and robots, enhancing user experience with natural language processing capabilities.
"""

import sys
import os
import base64
import threading
from queue import Queue
import time
import ctypes
from playsound import playsound
from cv_bridge import CvBridge  # 新增: 导入图像处理库
import cv2  # 新增: 导入OpenCV
import numpy as np  # 新增: 导入numpy
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Float32,Int64, Bool  # 修改为Int64
from std_srvs.srv import SetBool
from sensor_msgs.msg import Image  # 新增: 导入Image消息类型
import csv
import pyaudio
from typing import Optional, Dict, Any
from dashscope.common.logging import logger
from dashscope.multimodal.dialog_state import DialogState
from dashscope.multimodal.multimodal_dialog import MultiModalDialog, MultiModalCallback
from dashscope.multimodal.multimodal_request_params import (
    Upstream, Downstream, ClientInfo, RequestParameters, 
    Device, RequestToRespondParameters,BizParams
)

lib_path = '/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/wake/bin/wakeup.so'
try:
    wakelib = ctypes.CDLL(lib_path)
except OSError as e:
    print(f"加载库失败: {e}")
    print("尝试设置 LD_LIBRARY_PATH 或安装 xiaoxuekit.so")
    sys.exit(1)
wakelib.start_speech_recognition.argtypes = [ctypes.c_char_p]
# 获取当前脚本所在的目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 全局变量
g_dialog_id: Optional[str] = ''  # 当前对话ID
conver_instance: Optional['TMultiModalConversation'] = None  # 当前对话实例
detected_keyword = False
wake_flag = False  # 唤醒标志位 应该为false
wake_protect_flag = False  # 处于唤醒保护时间
wake_flag_lock = threading.Lock()  # 用于线程安全的锁
node = None
p = pyaudio.PyAudio()



audio_queue = Queue()

# 配置常量
APP_ID = 'mm_a5cbe63940f1461b8686d3b00bcb'  # 应用ID 
WORKSPACE_ID = 'llm-g17nzmm0a07pdziu'  # 工作空间ID  
API_KEY = 'sk-dad025bee21a42ddbdc308d3377c07a2'  # API密钥
VOICE_NAME = 'cosyvoice-v2-xiaoxue-0dc0455651e64b01b32898a268f1de7e'  # 语音名称
WEBSOCKET_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"  # WebSocket端点
MODEL_NAME = "multimodal-dialog"  # 使用的模型名称
AUDIO_SLEEP_INTERVAL = 0.01  # 音频发送间隔(秒)
AUDIO_CHUNK_SIZE = 3200  # 音频数据块大小
SAMPLE_RATE = 48000  # 采样率
FORMAT = pyaudio.paInt16 
CHANNELS = 1
# 新的全局变量，表示机器人状态(0-5)
robot_status_lock = threading.Lock()
robot_status = 0  # 默认初始为0（空闲）

# 新增: 图像相关全局变量
current_frame_lock = threading.Lock()
current_frame = None
frame_ready = False

# 新增: 图像捕获函数
def capture_current_frame(image_format='jpeg'):
    """
    捕获当前帧并转换为base64编码
    参数:
        image_format: 图像格式，默认为'jpeg'，也可以是'png'
    返回:
        (success, cv_image, base64_image) 元组
    """
    global current_frame, frame_ready
    
    with current_frame_lock:
        if not frame_ready:
            print("无可用图像帧")
            return (False, None, None)
        
        # 复制当前帧以便处理
        frame = current_frame.copy()
    
    try:
        # 根据指定格式编码图像
        if image_format.lower() == 'jpeg':
            # JPEG编码，可以指定压缩质量(0-100)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
            ret, img_data = cv2.imencode('.jpg', frame, encode_param)
        else:
            # PNG编码
            ret, img_data = cv2.imencode('.png', frame)
        
        if not ret:
            print(f"{image_format}编码失败")
            return (False, None, None)
        
        # 转换为base64编码
        base64_data = base64.b64encode(img_data.tobytes()).decode('utf-8')
        
        return (True, frame, base64_data)
        
    except Exception as e:
        print(f'捕获帧时出错: {str(e)}')
        return (False, None, None)


#唤醒词检测线程
def wake_detection_worker():
    global wake_flag
    global wake_protect_flag
    keyword_file_path = "/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/wake/ivw_record_sample/xbxb.txt"
    while True:
        wakelib.start_speech_recognition(keyword_file_path.encode('utf-8'))
        if wake_protect_flag:
            continue
        with wake_flag_lock:
            wake_flag = True  # 检测到唤醒词，设置标志位
        print("唤醒词检测到，设置 wake_flag 为 True")
        
        # 保持 0.5 秒
        time.sleep(0.5)
        
        with wake_flag_lock:
            wake_flag = False  # 恢复标志位
        print("恢复 wake_flag 为 False")
        time.sleep(0.5)

class TopicSubscriberNode(Node):
    def __init__(self):
        super().__init__('topic_subscriber_node')
        self.subscription = self.create_subscription(
            Int64,  # 改为Int64
            'current_robot_status',  # 修改topic名称
            self.listener_callback,
            qos_profile = rclpy.qos.QoSProfile(
                depth=10,
                reliability=rclpy.qos.ReliabilityPolicy.BEST_EFFORT
            )
        )
        self.get_logger().info('[RobotStatus订阅节点] 已启动')

    def listener_callback(self, msg):
        """
        接收到状态消息的回调，更新全局robot_status
        """
        global robot_status
        global conver_instance
        with robot_status_lock:
            robot_status = msg.data
        self.get_logger().info(f'[RobotStatus订阅节点] 收到Robot状态: {robot_status},{time.time()}')
        if conver_instance and robot_status != 0:
            conver_instance.stop_input = True


# 新增: 图像捕获节点类
class ImageCaptureNode(Node):
    def __init__(self):
        super().__init__('image_capture_node')
        
        # 初始化工具
        self.bridge = CvBridge()
        
        # 订阅图像topic
        self.subscription = self.create_subscription(
            Image,
            '/image_raw',
            self.image_callback,
            10)
        
        self.get_logger().info("图像捕获节点已启动，等待数据...")

    def image_callback(self, msg):
        """图像回调函数，持续更新最新帧"""
        global current_frame, frame_ready
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            with current_frame_lock:
                current_frame = cv_image
                frame_ready = True
            
            # 打印帧信息（可选，调试用）
            # self.print_frame_info(cv_image)
            
        except Exception as e:
            self.get_logger().error(f'图像转换失败: {str(e)}')

    def print_frame_info(self, frame):
        """打印当前帧信息到终端"""
        if frame is not None:
            print("\n=== 当前帧信息 ===")
            print(f"尺寸: {frame.shape[1]}x{frame.shape[0]}")
            print(f"通道数: {frame.shape[2] if len(frame.shape) > 2 else 1}")
            print(f"数据类型: {frame.dtype}")
            print(f"像素值范围: B[{np.min(frame[:,:,0])}-{np.max(frame[:,:,0])}] "
                  f"G[{np.min(frame[:,:,1])}-{np.max(frame[:,:,1])}] "
                  f"R[{np.min(frame[:,:,2])}-{np.max(frame[:,:,2])}]")
            print("=================\n")

class Sound(Node):
    def __init__(self):
        super().__init__('sound_detected_node')
        self.publisher = self.create_publisher(Bool, "sound_detected", 5)
        self.is_sounding_detected = self.create_subscription(
            Bool, 
            "is_sounding", 
            self.sounding_callback,
            5
        )
        self.get_logger().info("音频检测topic")
        self.thread_pub = None
        self.is_sounding = False

    def sounding_callback(self, msg):
        self.is_sounding = msg.data
        self.get_logger().info(f"接收到msg值: {is_sounding}")

    def publish_thread(self, interval=0.1):
        msg = Bool()
        while rclpy.ok(): # 无限循环，直到 rclpy 关闭
            rclpy.spin_once(self, timeout_sec=0)  # 非阻塞方式处理回调
            msg.data = self.is_sounding # 每次都检查最新状态
            self.publisher.publish(msg)
            time.sleep(interval)
        self.get_logger().info("Publishing thread stopped.")

    def start_publishing(self, interval=0.1):
        if self.thread_pub and self.thread_pub.is_alive():
            self.get_logger().warn("already in progress")
            return
        self.thread_pub = threading.Thread(
            target=self.publish_thread,
            args=(interval,),
            daemon=True
        )
        self.thread_pub.start()
        self.get_logger().info("start publish thread")

class ListeningStateMonitor:
    """监听状态监控器，用于跟踪对话的LISTENING状态"""
    
    def __init__(self):
        """初始化监控器"""
        self.listening_event = threading.Event()  # 监听状态事件
        self.listening_count = 0  # 监听状态计数
        self.lock = threading.Lock()  # 线程锁
    
    def on_listening_state(self):
        """当进入LISTENING状态时调用，更新计数并设置事件"""
        with self.lock:
            self.listening_count += 1
            print(f"检测到LISTENING状态 (计数: {self.listening_count})")
            self.listening_event.set()
    
    def wait_for_next_listening(self, timeout: float = 30.0) -> bool:
        """
        等待下一次LISTENING状态
        
        参数:
            timeout: 超时时间(秒)
            
        返回:
            bool: 是否成功等到LISTENING状态
        """
        self.listening_event.clear()
        print(f"等待下一次LISTENING状态 (超时: {timeout}s)...")
        success = self.listening_event.wait(timeout)
        
        if success:
            print("检测到LISTENING状态!")
        else:
            print(f"等待LISTENING状态超时 ({timeout}s)")
        
        return success
    
    def get_listening_count(self) -> int:
        """获取LISTENING状态的计数"""
        with self.lock:
            return self.listening_count 

class AudioPlayer:
    def __init__(self,sound_node):
        self.sound_node = sound_node
        self.output_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=SAMPLE_RATE,
                        output=True,
                        )

        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()

    def _play_loop(self):
        while True:
            if not audio_queue.empty():
                self.sound_node.is_sounding = True
            else:
                self.sound_node.is_sounding = False
            data = audio_queue.get()
            try:
                self.output_stream.write(data)
            except Exception as e:
                print("音频播放出错:", e)
    
    def audio_clear(self):
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except:
                break

                
class ChatCallback(MultiModalCallback):
    """多模态对话回调处理器，处理各种对话事件"""
    
    def __init__(self, listening_monitor: ListeningStateMonitor, vqa_handler_func = None,sound_node= None):
        """初始化回调处理器"""
        self.first_listening = True
        self.listening_monitor = listening_monitor  # 监听状态监控器
        self.vqa_handler_func = vqa_handler_func  # VQA处理函数
        self.audio_player = AudioPlayer(sound_node=sound_node)
        
    def on_connected(self):
        """连接建立时调用"""
        print("✅ WebSocket 连接已建立")

    def on_started(self, dialog_id: str):
        """对话开始时调用"""
        global g_dialog_id
        g_dialog_id = dialog_id
        print(f"对话开始: {dialog_id}")

    def on_stopped(self):
        """对话结束时调用"""
        print("对话已停止")

    def on_state_changed(self, state: DialogState):
        """对话状态变化时调用"""
        state_messages = {
            DialogState.LISTENING: "正在监听输入...",
            DialogState.THINKING: "正在处理请求...",
            DialogState.RESPONDING: "正在生成响应..."
        }
        if state in state_messages:
            print(state_messages[state],"时间：",time.time())
        
        # 监控LISTENING状态
        if state == DialogState.LISTENING:
            self.listening_monitor.on_listening_state()

    def on_speech_audio_data(self, data: bytes):
        """收到语音音频数据时调用"""
        # print(f"收到音频数据: {len(data)} 字节")
        try:
            audio_queue.put(data)
        except Exception as e:
            print("音频播放出错:", e)

    def on_error(self, error: Exception):
        """发生错误时调用"""
        print(f"❌ 错误: {error}")
        sys.exit(1)

    def on_speech_content(self, payload: Dict[str, Any]):
        """收到语音内容时调用"""
        global conver_instance
        if payload:
            print(f"语音内容: {payload},{time.time}")
            if '休息' in payload["output"]["text"]:
                global detected_keyword
                detected_keyword = False
                if conver_instance:
                    conver_instance.stop_input = True
            self.audio_player.audio_clear()

    def on_responding_content(self, payload: Dict[str, Any]):
        """收到响应内容时调用"""
        if payload:
            print(f"响应内容: {payload},{time.time}")
            try:
                commands_str = payload["output"]["extra_info"]["commands"]
                if "visual_qa" in commands_str:  # 检测到VQA命令
                    if self.vqa_handler_func:
                        self.vqa_handler_func()  # 调用VQA处理函数
                    print("处理visual_qa命令>>>>")
            except:
                return

    def on_request_accepted(self):
        """请求被接受时调用"""
        print("请求已接受")

    def on_close(self, close_status_code: int, close_msg: str):
        """连接关闭时调用"""
        print(f"连接已关闭 - 状态码: {close_status_code}, 消息: {close_msg}")

class TMultiModalConversation:
    """多模态对话管理器，处理整个对话流程"""
    
    def __init__(self, app_id: str, workspace_id: str, api_key: str, 
                 dialog_id: str = "", conversation_mode: str = "duplex",sound_node = None):
        """初始化对话管理器"""
        print("初始化对话")
        
        # 初始化监听状态监控器
        self.listening_monitor = ListeningStateMonitor()
        self.stop_input = False

        # 配置请求参数input
        up_stream = Upstream(type="AudioAndVideo", mode="duplex", audio_format="pcm")
        client_info = ClientInfo(user_id="demo_user", device=Device(uuid="demo_device_12345"))
        biz_params = BizParams(user_prompt_params={"user_name":"大米"})
        request_params = RequestParameters(
            upstream=up_stream,
            downstream=Downstream(voice=VOICE_NAME, sample_rate=SAMPLE_RATE),
            client_info=client_info,
            biz_params=biz_params
        )

        self.callback = ChatCallback(self.listening_monitor, vqa_handler_func=self.send_image_vqa,sound_node=sound_node)
        self.conversation = MultiModalDialog(
            app_id=app_id,
            workspace_id=workspace_id,
            url=WEBSOCKET_URL,
            request_params=request_params,
            multimodal_callback=self.callback,
            api_key=api_key,
            dialog_id=dialog_id,
            model=MODEL_NAME
        )
        
        # 视频相关状态
        self.video_mode_active = False
        self.video_thread_running = False

    def start_conversation(self):
        """开始对话会话"""
        self.conversation.start("")
        print(" 对话已开始")

    def get_conversation_mode(self) -> str:
        """获取当前对话模式"""
        return self.conversation.get_conversation_mode()

    def wait_for_listening_state(self, timeout: float = 30.0) -> bool:
        """
        等待系统进入LISTENING状态
        
        参数:
            timeout: 超时时间(秒)
            
        返回:
            bool: 是否成功等到LISTENING状态
        """
        return self.listening_monitor.wait_for_next_listening(timeout)

    def get_listening_count(self) -> int:
        """获取LISTENING状态的计数"""
        return self.listening_monitor.get_listening_count()


    def stop_conversation(self):
        """停止对话会话"""
        # 停止视频帧发送
        self.video_thread_running = False
        self.conversation.stop()
        print("对话已停止")

    def send_image_vqa(self):
        """发送图片进行视觉问答(VQA)"""
                
        # 保存图像
        success, image_frame, base64_image = capture_current_frame(image_format='jpeg')
        if success:
            print("开始调用视觉处理图像问题...")
            image = {"type": "base64", "value":base64_image}
            images_params = RequestToRespondParameters(images=[image])
            self.conversation.request_to_respond("prompt", "", parameters=images_params)
        else:
            print("帧捕获失败")

    def send_stream_audio(self):
        """流式传输音频文件到对话"""
        print(f"工作进程 正在流式传输音频 开始时间:",time.time())
        input_stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=16000,
            input=True,
            frames_per_buffer=1600
        )
        try:
            while not self.stop_input:
                data = input_stream.read(1600, exception_on_overflow=False)
                self.conversation.send_audio_data(data)
                time.sleep(AUDIO_SLEEP_INTERVAL)
        except Exception as e:
            print(f"音频流发送异常: {e}")
        finally:
            input_stream.stop_stream()
            input_stream.close()
            print("音频输入流已关闭")

def spin_topic_node():
    executor = MultiThreadedExecutor()
    executor.add_node(topic_subscriber_node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        topic_subscriber_node.destroy_node()

# 新增: 图像节点线程函数
def spin_image_node():
    executor = MultiThreadedExecutor()
    executor.add_node(image_capture_node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        image_capture_node.destroy_node()

def play_audio(file_path,sound_node):
    try:
        sound_node.is_sounding = True       
        playsound(file_path)
        sound_node.is_sounding = False 
    except Exception as e:
        print(f"播放失败 {file_path}: {e}")

def main():
    try:
        rclpy.init()
        global topic_subscriber_node
        global image_capture_node  # 新增: 全局图像节点
        global robot_status
        global conver_instance
        global wake_flag ,detected_keyword

        sound_node = Sound()    # 上肢和面部表情动作发布者
        sound_node.start_publishing()

        topic_subscriber_node = TopicSubscriberNode()   # 机器人状态订阅
        image_capture_node = ImageCaptureNode()  # 新增: 创建图像节点
        
        topic_thread = threading.Thread(target=spin_topic_node, daemon=True)
        image_thread = threading.Thread(target=spin_image_node, daemon=True)  # 新增: 创建图像线程
        topic_thread.start()
        image_thread.start()

        wake_thread = threading.Thread(target=wake_detection_worker, daemon=True)
        wake_thread.start()

        time.sleep(3)
        detected_keyword = False

        # 初始化对话实例
        conver_instance = TMultiModalConversation(
            app_id=APP_ID,
            workspace_id=WORKSPACE_ID,
            api_key=API_KEY,
            dialog_id= g_dialog_id,
            conversation_mode="duplex",  # 可选: push2talk, tap2talk, duplex
            sound_node = sound_node
        )
    
        while rclpy.ok():
            
            with robot_status_lock:
                cur_status = robot_status
            
            if cur_status != 0 or cur_status != 2:
                print(f"[主线程] 当前Robot状态: {cur_status}，非空闲，打断当前流程并等待空闲...")
                detected_keyword = False
                time.sleep(0.2)
                continue
            
            # 只有在空闲(0)时才能唤醒和对话
            if not detected_keyword:
                if wake_flag:
                    print("唤醒成功") 
                    play_audio('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/wake.mp3',sound_node)
                    detected_keyword = True
                    wake_flag = False
                else:
                    time.sleep(0.1)
                    continue

            conver_instance.stop_input = False
            # 开始对话
            conver_instance.start_conversation()

            # 等待第一次LISTENING状态
            print(f" 等待第一次LISTENING状态...")
            if not conver_instance.wait_for_listening_state(timeout=30.0):
                print(f" 等待第一次LISTENING状态超时")
                return

            # 发送第一次音频
            conver_instance.send_stream_audio()
            
            # 显示统计信息
            listening_count = conver_instance.get_listening_count()
            print(f"工作进程完成. 总LISTENING状态次数: {listening_count}",time.time())
            
            # 清理
            conver_instance.stop_conversation()
            time.sleep(1)  # 清理延迟   
     
            continue

    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在关闭程序...")
    finally:
        try:
            topic_subscriber_node.destroy_node()
            if 'image_capture_node' in globals():
                image_capture_node.destroy_node()
            cv2.destroyAllWindows()  # 关闭所有OpenCV窗口
            rclpy.shutdown()
            if wake_thread.is_alive():
                wake_thread.join(timeout=2)

        except Exception as e:
            print(f"[关闭流程] 程序关闭时异常: {e}")
            sys.exit(1)
        print("程序已安全关闭")

if __name__ == '__main__':
    main()

