#coding=utf-8
'''
可中断的欢迎音频模块
'''
import os
import time
import threading
from datetime import datetime
import pygame
# welcome_audio_top_event = get_stop_event()
# welcome_audio_top_event.set() # 这会中断音频播放
# 创建一个全局标志来控制播放状态
stop_playback = threading.Event()

def interrupt_playback():
    """中断当前正在播放的音频"""
    global stop_playback
    stop_playback.set()
    
    # 确保音频停止
    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
        print("音频播放已中断")

def default_callback(is_completed):
    """默认的音频播放完成回调函数"""
    if is_completed:
        print("✓ 欢迎音频播放完毕，正常完成")
    else:
        print("✗ 欢迎音频播放被中断")

def play_welcome_audio(callback_on_finish=default_callback):
    """
    根据当前时间播放相应的欢迎音频
    
    参数:
        callback_on_finish: 音频结束后要调用的回调函数，接收一个布尔参数，
                           True表示正常播放完成，False表示播放被中断
    
    返回:
        bool: 如果播放成功完成返回True，被中断返回False
    """
    global stop_playback
    
    # 重置停止标志
    stop_playback.clear()
    
    # 初始化音频播放器
    pygame.mixer.init()
    
    # 获取当前脚本所在的目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 欢迎音频文件夹路径
    audio_dir = "/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/client_modules/welcome/welcome_audio"
    
    # 检查文件夹是否存在
    if not os.path.exists(audio_dir):
        print(f"错误: 找不到音频文件夹 {audio_dir}")
        print("请先运行生成欢迎音频的脚本")
        callback_on_finish(False)
        return False
    
    # 定义各时段的音频文件
    audio_files = {
        "morning": os.path.join(audio_dir, "morning.mp3"),    # 早上6:00-12:00
        "afternoon": os.path.join(audio_dir, "afternoon.mp3"), # 中午12:00-18:00
        "evening": os.path.join(audio_dir, "evening.mp3")     # 晚上18:00-6:00
    }
    
    # 获取当前时间
    current_hour = datetime.now().hour
    
    # 根据当前时间确定使用哪个音频文件
    if 6 <= current_hour < 12:
        audio_file = audio_files["morning"]
        time_period = "早上"
    elif 12 <= current_hour < 18:
        audio_file = audio_files["afternoon"]
        time_period = "中午"
    else:  # 18:00-6:00
        audio_file = audio_files["evening"]
        time_period = "晚上"
    
    # 检查音频文件是否存在
    if not os.path.exists(audio_file):
        print(f"错误: 找不到{time_period}的音频文件 {audio_file}")
        callback_on_finish(False)
        return False
    
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"当前时段: {time_period}")
    print(f"播放音频: {os.path.basename(audio_file)}")
    
    playback_completed = False
    
    try:
        # 加载并播放音频
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()
        
        # 等待音频播放完毕或被中断
        while pygame.mixer.music.get_busy():
            if stop_playback.is_set():
                pygame.mixer.music.stop()
                print("音频播放被中断")
                break
            time.sleep(0.1)
        
        if not stop_playback.is_set():
            print("音频播放完成")
            playback_completed = True
        
    except Exception as e:
        print(f"播放音频时出错: {str(e)}")
        playback_completed = False
    finally:
        # 退出pygame
        pygame.mixer.quit()
        
    # 在结束后调用回调函数，传递播放是否完成的状态
    if callback_on_finish:
        callback_on_finish(playback_completed)
        
    return playback_completed

# 提供访问中断标志的方法
def get_stop_event():
    """返回停止播放的事件对象，可以直接调用.set()方法中断播放"""
    global stop_playback
    return stop_playback

# # 直接运行此模块时的测试代码
# if __name__ == "__main__":
#     def custom_callback(is_completed):
#         if is_completed:
#             print("回调函数: 音频播放成功完成!")
#         else:
#             print("回调函数: 音频播放未完成!")
    
#     print("=== 测试欢迎音频模块 ===")
#     play_welcome_audio(callback_on_finish=custom_callback)
