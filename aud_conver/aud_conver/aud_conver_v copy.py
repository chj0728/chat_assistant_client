import sys
import os
# print("sys.path:", sys.path)
from .client_modules.xf_audio_transform import transcribe_audio#xf流失
from .client_modules.database_manager_db import add_message_to_db, filter_messages, clean_msg
from .client_modules.processor_achieve import usage_example
from .client_modules.db_tts_websocket import dbsentence2mp3andplay
from .client_modules.welcome.welcome_fortime import play_welcome_audio,get_stop_event
from volcenginesdkarkruntime import Ark#db vlm
from .qwen_model import StreamingTTSInterface,StreamingAgentInterface,StreamingImageTTSInterface
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
from cv_bridge import CvBridge  # 新增: 导入图像处理库
import cv2  # 新增: 导入OpenCV
import numpy as np  # 新增: 导入numpy

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Int64, Bool  # 修改为Int64
from ymrobot_msgs.srv import LargeModelRequestTask
from ymrobot_msgs.msg import WakeUpWordSetting
from rclpy.callback_groups import ReentrantCallbackGroup
from sensor_msgs.msg import Image  # 新增: 导入Image消息类型
import csv
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

# 新增: 图像相关全局变量
current_frame_lock = threading.Lock()
current_frame = None
frame_ready = False

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

        self.subscription_update_wakeupword = self.create_subscription(
            WakeUpWordSetting,
            'modify_wakeup_word',
            self.update_wakeupword_callback,
            1
        )

    def listener_callback(self, msg):
        """
        接收到状态消息的回调，更新全局robot_status
        """
        global robot_status
        with robot_status_lock:
            robot_status = msg.data
        self.get_logger().info(f'[RobotStatus订阅节点] 收到Robot状态: {robot_status}')
    
    def update_wakeupword_callback(self, msg):
        """
        接收欢迎词的回调，更新欢迎词，重启生效
        """
        try:
            self.get_logger().info(f"接收到{len(msg.wake_up_word)}个字符串")
            keyword_file_path = "/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/wake/ivw_record_sample/xbxb.txt"
            lines = []
            for text in msg.wake_up_word:
                lines.append(f"{text};nCM:500")
            with open(keyword_file_path, 'w', encoding='UTF-8') as f:
                f.write('\n'.join(lines))
            self.get_logger().info(f"成功更新唤醒词文件内容")
        except Exception as e:
            self.get_logger().error(f"处理消息时出错：{str(e)}")

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
        self.get_logger().info("音频检测topic发布者已创建，等待调用...")
        self.thread_pub = None
        
    def publish_thread(self, total_messages=25, interval=0.2):
        """线程函数：发布指定次数的消息"""
        msg = Bool()
        msg.data = False
        for i in range(0, total_messages):
            if not rclpy.ok():
                break
            self.publisher.publish(msg)
            time.sleep(interval)
        self.get_logger().info("Thread finished publishing")
        
    def start_publishing(self, total_messages=25, interval=0.2):
        """启动线程发布消息"""
        if self.thread_pub and self.thread_pub.is_alive():
            self.get_logger().warn("Publishing already in progress")
            return
            
        self.thread_pub = threading.Thread(
            target=self.publish_thread,
            args=(total_messages, interval),
            daemon=True
        )
        self.thread_pub.start()
        self.get_logger().info("Started publishing thread_pub")

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

# 新增: 图像节点线程函数
def spin_image_node():
    executor = MultiThreadedExecutor()
    executor.add_node(image_capture_node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        image_capture_node.destroy_node()

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
        return 2
    if ("看到" in sentence_user) or ("眼前" in sentence_user):
        return 3  # 图像识别分支 - 触发于询问机器人看到什么内容
    if ("停止对话" in sentence_user) or ("退出语音交互" in sentence_user) or ("退出" in sentence_user) or ("退下" in sentence_user) or ("停止" in sentence_user):
        return 4
    else:
        return 2

def switch_case_branch(branch):
    match branch:
        case 1:
            print("当前分支编号：1")
        case 2:
            print("当前分支编号：2")
        case 3:
            print("当前分支编号：3 - 图像捕获")
        case _:
            print("未知分支")

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
        """获取唤醒词，将唤醒词写入聊天记录中"""
        file_path = "/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/wake/ivw_record_sample/xbxb.txt"
        with open(file_path, 'r', encoding='utf-8') as file:
            # 读取第一行
            first_line = file.readline().strip()
            
            # 提取中文字符
            chinese_chars = [char for char in first_line if '\u4e00' <= char <= '\u9fff']
            
            # 获取前四个中文字符
            result = ''.join(chinese_chars[:4])
        write_csv(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "user", result)
        print("唤醒词检测到，设置 wake_flag 为 True")
        
        # 保持 0.5 秒
        time.sleep(0.5)
        
        with wake_flag_lock:
            wake_flag = False  # 恢复标志位
        print("恢复 wake_flag 为 False")
        time.sleep(0.5)

def write_csv(time, role, sentence):
    """
    将数据写入CSV文件
    :param time: 开始时间字符串 (格式: "%Y-%m-%d %H:%M:%S")
    :param role: 角色标识
    :param sentence: 句子内容
    """
    # 准备数据
    data = [time, role, sentence]
    
    # 获取当前工作目录和绝对路径
    records_dir = "/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver"
    file_name = "records.csv"
    file_name = os.path.join(records_dir, file_name)
    
    print(f"当前工作目录: {records_dir}")
    print(f"文件路径: {file_name}")
    
    try:
        # 检查文件是否存在
        file_exists = os.path.exists(file_name)
        
        # 打开文件（追加模式）
        with open(file_name, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # 如果是新文件，先写入表头
            if not file_exists:
                print("文件不存在，创建新文件并添加表头")
                header = ["StartTime", "Role", "Sentence"]
                writer.writerow(header)
                print(f"已写入表头: {header}")
            
            # 写入数据行
            print(f"准备写入数据: {data}")
            writer.writerow(data)
            f.flush()  # 确保数据立即写入磁盘
            print("数据已成功写入")
        
        # 验证写入结果
        if os.path.exists(file_name):
            size = os.path.getsize(file_name)
            print(f"文件验证成功! 大小: {size} 字节")
            
            # 打印文件最后几行内容
            print("\n文件最新内容:")
            with open(file_name, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 显示最后5行内容
                for line in lines[-5:]:
                    print(line.strip())
                    
            return True
        else:
            print("错误: 文件未创建")
            return False
            
    except Exception as e:
        print(f"\n!!! 写入失败: {type(e).__name__} !!!")
        print(f"错误详情: {str(e)}")
        print("\n可能原因:")
        print("1. 目录权限不足 - 尝试: sudo chown $USER .")
        print("2. 磁盘空间不足 - 检查: df -h")
        print("3. 文件系统只读 - 尝试: mount | grep ' / '")
        print("4. 文件被其他进程占用")
        return False

def run_image_tts_async(base64_image, prompt="图中描绘的是什么景象?，根据这样的景象，写一首中国古代绝句诗", api_key=None):
    interface = StreamingImageTTSInterface(
        api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
        base64_image=base64_image,
        user_prompt=prompt
    )
    thread = threading.Thread(target=interface.start)
    thread.daemon = True
    thread.start()
    return interface, thread


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
        global image_capture_node  # 新增: 全局图像节点
        global robot_status

        sound_node = Sound()

        topic_subscriber_node = TopicSubscriberNode()
        
        image_capture_node = ImageCaptureNode()  # 新增: 创建图像节点

        topic_thread = threading.Thread(target=spin_topic_node, daemon=True)
        
        image_thread = threading.Thread(target=spin_image_node, daemon=True)  # 新增: 创建图像线程
        
        topic_thread.start()
        
        image_thread.start() 

        wake_thread = threading.Thread(target=wake_detection_worker, daemon=True)
        wake_thread.start()
        # fix = threading.Thread(target=playsound, daemon=True)
        # fix.start()
        time.sleep(3)
        
        time_points = []
        detected_keyword = False
        interface_thread = None
        
        executor = ThreadPoolExecutor(max_workers=2)
        
        
        captured_image = None
        
        while True:
            
            with robot_status_lock:
                cur_status = robot_status

            
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
                    msg = Bool()
                    msg.data = True
                    sound_node.publisher.publish(msg)
                    playsound('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/wake.mp3')
                    sound_node.start_publishing()
                    write_csv(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "llm", "我在呢")
                    detected_keyword = True
                else:
                    time.sleep(0.1)
                    continue

            # 进入主流程（语音识别／命令执行／对话等）
            # print('进入语音识别')
            transcribed_text = transcribe_audio(max_retries=3, vad_eos=700, reconnect_delay=0.01)
            print(transcribed_text)
            #transcribed_text = '你是谁'
            sentence_user = transcribed_text
            if not sentence_user:
                print("未检测到有效语音")
                detected_keyword = False
                continue
            write_csv(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "user", sentence_user)
            # sentence_user = '你能看到什么？'
            time_points.append(datetime.now())
            
            branch = determine_branch(sentence_user)
            match branch:
                case 1:
                    pass
                
                case 2:
                    print('进入了对话窗')
                    
                    time_points.append(datetime.now())
                    print(f"时间点2: {time_points[1].strftime('%Y-%m-%d %H:%M:%S.') + f'{time_points[1].microsecond // 1000:03d}'}")
                    interface = StreamingAgentInterface(prompt=sentence_user)
                    interface_thread = threading.Thread(target=run_interface)
                    interface_thread.daemon = True
                    interface_thread.start()
                    
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
                            sound_node.start_publishing()
                            interface_thread.join(timeout=2)
                            break
                            
                        if audio_completed:
                            print("[对话窗] 音频播放线程已完成，退出监控循环")
                            write_csv(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "llm", interface.get_full_content())
                            break
                            
                        time.sleep(0.1)
                
                # 新增: Case 3 - 图像捕获分支
                case 3:
                    print("当前分支编号：3 - 图像捕获")
                    success, image_frame, base64_image = capture_current_frame(image_format='jpeg')
                    if success:
                        print("开始调用视觉模型处理图像...")
                        print(sentence_user)
                        interface, tts_thread = run_image_tts_async(base64_image, prompt=sentence_user)
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
                                sound_node.start_publishing()
                                break    # 只break，外面再join
                        
                            if audio_completed:
                                print("[对话窗] 音频播放线程已完成，退出监控循环")
                                write_csv(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "llm", interface.get_full_content())
                                break
                            
                            time.sleep(0.1)
                        
                        tts_thread.join(timeout=2)  # 离开监控循环后再join。防止死循环中一直join。

                    else:
                        print("帧捕获失败")
                
                case 4:
                    print("当前分支编号4, 退出本次对话")
                    msg = Bool()
                    msg.data = True
                    sound_node.publisher.publish(msg)
                    playsound('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/byebye.mp3')
                    sound_node.start_publishing()
                    write_csv(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "llm", "好的，之后有什么问题随时呼唤我哦")
                    detected_keyword = False
  
                        
                        
                                    
            


            
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
            if interface_thread is not None and interface_thread.is_alive():
                interface_thread.join(timeout=2)
        except Exception as e:
            print(f"[关闭流程] 程序关闭时异常: {e}")
        print("程序已安全关闭")

if __name__ == '__main__':
    main()


#520 视觉版
