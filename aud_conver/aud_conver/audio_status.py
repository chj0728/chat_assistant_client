import threading

class AudioStatus:
    """线程安全的音频状态类"""
    def __init__(self):
        self.value = False
        self.lock = threading.Lock()
    
    def set_value(self, value):
        """设置音频状态"""
        with self.lock:
            # 仅在值实际变化时打印
            if self.value != value:
                self.value = value
                print(f"[AudioStatus] 设置音频状态: {value}")
    
    def get_value(self):
        """获取当前音频状态"""
        with self.lock:
            return self.value

# 创建全局共享状态实例
audio_status = AudioStatus()