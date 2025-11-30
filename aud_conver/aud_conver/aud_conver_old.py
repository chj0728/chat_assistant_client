import sys
import os
print("sys.path:", sys.path)
from .client_modules.xf_audio_transform import transcribe_audio#xf流失
from .client_modules.database_manager_db import add_message_to_db, filter_messages, clean_msg
from .client_modules.processor_achieve import usage_example
from .client_modules.db_tts_websocket import dbsentence2mp3andplay
from .client_modules.welcome.welcome_fortime import play_welcome_audio,get_stop_event
from volcenginesdkarkruntime import Ark#db vlm
from .qwen_model import StreamingTTSInterface,StreamingAgentInterface
from .client_modules.ali_mcp import get_out
import re
import base64
import threading
import queue
import json
from datetime import datetime
import time
import ctypes
import pygame
from playsound import playsound
from concurrent.futures import ThreadPoolExecutor

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Int64  # 修改为Int64
from ymrobot_msgs.srv import LargeModelRequestTask
from rclpy.callback_groups import ReentrantCallbackGroup

lib_path = '/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/wake/bin/wakeup.so'
try:
    wakelib = ctypes.CDLL(lib_path)
except OSError as e:
    print(f"加载库失败: {e}")
    print("尝试设置 LD_LIBRARY_PATH 或安装 xiaoxuekit.so")
    sys.exit(1)
wakelib.start_speech_recognition.argtypes = [ctypes.c_char_p]
wake_flag_lock = threading.Lock()
wake_flag = False
wake_protect_flag = False
# 新的全局变量，表示机器人状态(0-5)
robot_status_lock = threading.Lock()
robot_status = 0  # 默认初始为0（空闲）

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
        with robot_status_lock:
            robot_status = msg.data
        self.get_logger().info(f'[RobotStatus订阅节点] 收到Robot状态: {robot_status}')



def spin_topic_node():
    executor = MultiThreadedExecutor()
    executor.add_node(topic_subscriber_node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        topic_subscriber_node.destroy_node()

def spin_audio_service_node():
    executor = MultiThreadedExecutor()
    executor.add_node(audio_service_client_node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        audio_service_client_node.destroy_node()


class AudioServiceClientNode(Node):
    def __init__(self):
        super().__init__('audio_service_client_node')
        self.client = self.create_client(
            LargeModelRequestTask,
            'large_model_task_service',
        )
        while not self.client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('导航服务不可用，等待中...')
        self.get_logger().info('导航服务客户端已准备就绪')

    def send_request(self, task_type, mark_point_name='', mark_point_name_list=None, guidance_task_name='', upper_climb_fixed_action=0):
        request = LargeModelRequestTask.Request()
        request.larget_mode_task_type = task_type
        request.mark_point_name = mark_point_name
        request.mark_point_name_list = mark_point_name_list or []
        request.guidance_task_name = guidance_task_name
        
        # 确保upper_climb_fixed_action是uint8类型
        # 使用int并确保值在0-255范围内
        upper_climb_fixed_action_value = int(upper_climb_fixed_action) & 0xFF  # 限制在0-255范围
        request.upper_climb_fixed_action = upper_climb_fixed_action_value

        self.get_logger().info(f'发送请求: 类型={task_type}, 点位={mark_point_name}, 点位列表={mark_point_name_list}, 导览任务={guidance_task_name}, 固定动作={upper_climb_fixed_action_value}')

        self.response_event = threading.Event()
        self.response_result = None
        future = self.client.call_async(request)
        future.add_done_callback(self.response_callback)
        self.response_event.wait()
        return self.response_result

    def response_callback(self, future):
        try:
            response = future.result()
            self.response_result = (response.success, response.message)
            self.get_logger().info(f'收到响应: success={response.success}, message={response.message}')
        except Exception as e:
            self.response_result = (False, str(e))
            self.get_logger().error(f'获取响应失败: {e}')
        finally:
            self.response_event.set()



def determine_branch(sentence_user):
    if re.search(r"打[\w]?招呼|握[\w]?手", sentence_user):
        return 1
    else:
        return 2

def switch_case_branch(branch):
    match branch:
        case 1:
            print("当前分支编号：1")
        case 2:
            print("当前分支编号：2")
        case _:
            print("未知分支")
def play_audio(path):
    playsound(path)  # 播放音频

def play_audio_async(path):
    t = threading.Thread(target=play_audio, args=(path,))
    t.daemon = True  # 主线程退出时，音频线程随即退出
    t.start()
#唤醒词检测线程
def wake_detection_worker():
    global wake_flag
    global wake_protect_flag
    keyword_file_path = "/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/wake/ivw_record_sample/xbxb.txt"
    
    while True:
       
        
        #if detected:
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

def run_interface():
    try:
        interface.start()
        return True
    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        return False

def main():
    try:
        rclpy.init()
        global interface
        global wake_flag
        global topic_subscriber_node
        # global audio_service_client_node
        global robot_status

        topic_subscriber_node = TopicSubscriberNode()
        # audio_service_client_node = AudioServiceClientNode()

        topic_thread = threading.Thread(target=spin_topic_node, daemon=True)
        # service_thread = threading.Thread(target=spin_audio_service_node, daemon=True)
        topic_thread.start()
        # service_thread.start()

        wake_thread = threading.Thread(target=wake_detection_worker, daemon=True)
        wake_thread.start()
        # fix = threading.Thread(target=playsound, daemon=True)
        # fix.start()
        time.sleep(3)
        # 创建一个列表来存储时间点
        time_points = []
        detected_keyword = False
        interface_thread = None
        # 初始化一个线程池
        executor = ThreadPoolExecutor(max_workers=2)
        while True:
            # 获取当前状态
            with robot_status_lock:
                cur_status = robot_status

            # 如果不是空闲(0)，停止一切，并阻塞自己!
            if cur_status != 0:
                print(f"[主线程] 当前Robot状态: {cur_status}，非空闲，打断当前流程并等待空闲...")
                # 如果存在对话stream/tts等interface线程，打断并清理
                if interface_thread and interface_thread.is_alive():
                    try:
                        interface.stop()
                        interface_thread.join(timeout=2)
                        print("[主线程] 已打断对话流/任务线程")
                    except Exception as e:
                        print(f"[异常处理] 打断对话流/任务线程出错: {e}")
                detected_keyword = False
                time.sleep(0.2)
                continue
            
            
            
            # 只有在空闲(0)时才能唤醒和对话
            if not detected_keyword:
                if wake_flag:
                    # print("唤醒成功")
                    #playsound('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/wake_first.mp3')
                    detected_keyword = True
                else:
                    time.sleep(0.1)
                    continue

            # 进入主流程（语音识别／命令执行／对话等）
            print('进入语音识别')
            transcribed_text = transcribe_audio(max_retries=3, vad_eos=700, reconnect_delay=0.01)
            print(transcribed_text)
            # transcribed_text = '你是谁'
            sentence_user = transcribed_text
            if not sentence_user:
                print("未检测到有效语音")
                detected_keyword = False
                continue
            
            time_points.append(datetime.now())
            print(f"时间点1: {time_points[0].strftime('%Y-%m-%d %H:%M:%S.') + f'{time_points[0].microsecond // 1000:03d}'}")
            print("檢測到的內容是：****************************************"+sentence_user)
            branch = determine_branch(sentence_user)
            match branch:
                case 1:
                    print("当前分支编号：1")
                    function, response = get_out(sentence_user)
                    #加入思考语音
                    # play_audio_async('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/welcome/wait.mp3')
                    # 先判断sorr且不包含erro
                    if 'sorr()' in function and 'erro' not in function:
                        print("处理sorr函数且没有erro")
                        # 这里写sorr的处理逻辑
                        dbsentence2mp3andplay(response, 'introduction')
                        

                    # 判断不同的有效function
                    

                    elif 'Handshake()' in function:
                        print("Handshake")
                        dbsentence2mp3andplay(response, 'introduction')
                        #play_audio_async('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/sdn.mp3')
                        # success, message = audio_service_client_node.send_request(
                        #     task_type=3,
                        #     upper_climb_fixed_action=6
                        # )
                        # print(f"服务请求结果 - 成功: {success}, 消息: {message}")

                    

                    elif 'Hello‌()' in function:
                        print("Hello‌")
                        dbsentence2mp3andplay(response, 'introduction')
                        #play_audio_async('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/qjj.mp3')
                        # success, message = audio_service_client_node.send_request(
                        #     task_type=3,
                        #     upper_climb_fixed_action=2
                        # )
                        # print(f"服务请求结果 - 成功: {success}, 消息: {message}")
    

                    # 可以加一个默认分支处理未识别的function
                    else:
                        print('未知的function类型: ', function)
                
                case 2:
                    print('进入了对话窗')
                    # current_time = datetime.now()
                    # formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
                    # print("当前时间（精确到毫秒）:", formatted_time)
                    time_points.append(datetime.now())
                    print(f"时间点2: {time_points[1].strftime('%Y-%m-%d %H:%M:%S.') + f'{time_points[1].microsecond // 1000:03d}'}")
                    interface = StreamingAgentInterface(prompt=sentence_user)
                    interface_thread = threading.Thread(target=run_interface)
                    interface_thread.daemon = True
                    interface_thread.start()
                    # play_audio_async('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/welcome/wait2.mp3')
                    #加入思考语音
                    # current_time = datetime.now()
                    # formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
                    # print("当前时间（精确到毫秒）:", formatted_time)
                    
                    while interface.processing_thread is None:
                        time.sleep(0.01)
                    
                    while True:
                        # 1. 检查唤醒标志
                        with wake_flag_lock:
                            current_wake_flag = wake_flag
                            
                        # 2. 检查机器人状态
                        with robot_status_lock:
                            cur_status = robot_status
                            
                        # 3. 检查音频线程状态
                        audio_completed = False
                        if interface.processor and hasattr(interface.processor, 'audio_thread'):
                            audio_completed = not interface.processor.audio_thread or not interface.processor.audio_thread.is_alive()
                            
                        # 组合条件判断
                        if cur_status != 0 or current_wake_flag:
                            print("[对话窗] 收到状态变更信号，停止当前处理")
                            interface.stop()
                            interface_thread.join(timeout=2)
                            break
                            
                        if audio_completed:
                            print("[对话窗] 音频播放线程已完成，退出监控循环")
                            break
                            
                        time.sleep(0.1)
                # 计算总时间差
            total_diff = (time_points[-1] - time_points[0]).total_seconds() * 1000  # 转换为毫秒
            print(f"总时间差: {total_diff:.3f} 毫秒")
            current_time = datetime.now()
            formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
            print("当前时间（精确到毫秒）:", formatted_time)
            print('执行完成')
            # time.sleep(20)
            continue

    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在关闭程序...")
    finally:
        try:
            topic_subscriber_node.destroy_node()
            rclpy.shutdown()
            if wake_thread.is_alive():
                wake_thread.join(timeout=2)
            if interface_thread is not None and interface_thread.is_alive():
                interface_thread.join(timeout=2)
        except Exception as e:
            print(f"[关闭流程] 程序关闭时异常: {e}")
        print("程序已安全关闭")

if __name__ == '__main__':
    main()

#s 426
#n 427
#5.9
#520 xiaoxue
