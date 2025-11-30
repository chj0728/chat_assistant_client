import pygame
import subprocess
import os
import sys
import playsound

def mpg_play_audio(audio_file):
    """
    跨平台音频播放函数
    
    参数:
    audio_file (str): 音频文件的完整路径
    
    返回:
    bool: 播放是否成功
    """
    # 检查文件是否存在
    if not os.path.exists(audio_file):
        print(f"错误：文件 {audio_file} 不存在")
        return False
    
    try:
        # 根据系统选择适当的播放器
        if sys.platform.startswith('linux'):
            cmd = ['mpg123', audio_file]
        elif sys.platform == 'darwin':  # macOS
            cmd = ['afplay', audio_file]
        elif sys.platform == 'win32':  # Windows
            cmd = ['start', '', audio_file]
        else:
            print(f"错误：不支持的平台: {sys.platform}")
            return False
        
        # 启动播放进程
        subprocess.Popen(cmd)
        return True
    
    except Exception as e:
        print(f"播放音频失败: {str(e)}")
        return False
    
def play_audio(audio_path):
    """
    验证并播放指定路径的音频文件
    
    参数:
    audio_path (str): 音频文件的完整路径
    
    返回:
    bool: 播放是否成功
    """
    # 检查文件是否存在
    if not os.path.exists(audio_path):
        print(f"错误：文件 {audio_path} 不存在")
        return False
    
    try:
        # 尝试播放音频
        playsound(audio_path)
        return True
    except Exception as e:
        print(f"播放音频时发生错误：{e}")
        return False

def game_play_audio(audio_path):
    """播放音频，支持实时打断"""


    print(f"[播放音频] 播放: {audio_path}")

    # 检查文件是否存在
    if not os.path.exists(audio_path):
        print(f"音频文件不存在: {audio_path}")
        return

    # 加载音频文件
    try:
        pygame.init()
        pygame.mixer.init(devicename="default")
        pygame.mixer.music.load(audio_path)
    except pygame.error as e:
        print(f"无法加载音频文件: {e}")
        return

    # 播放音频
    pygame.mixer.music.play()

    # 实时检测 wake_flag
    while pygame.mixer.music.get_busy():  # 检查音频是否正在播放
                break
        
    pygame.quit()










#这是音频播放函数接口 
# pygame 支持多种音频播放能够实现异步 
# 
# playsound 阻塞执行专播mp3
#
# mpg123