import queue
import threading
import os
import sys
import time
from datetime import datetime

# 导入必要的模块
from .db_tts_websocket import dbsentence2mp3
# 导入音频播放模块

import pygame  # 确保已安装pygame

class StreamProcessor:
    def __init__(self,
                 punctuations="。！…；？,，",
                 first_split_chars="，,",
                 max_buffer_length=1000,
                 text_to_speech_func=None):
        """
        初始化流式数据处理器
        参数:
        - punctuations: 断句标点符号
        - first_split_chars: 首次分割的字符
        - max_buffer_length: 最大缓冲区长度，防止内存泄漏
        - text_to_speech_func: 文本转语音函数
        """
        # 实时处理的队列 - 存储(id, content)元组
        self.real_time_queue = queue.Queue()
        self.sentence_queue = queue.Queue()
        # 新增：音频文件播放队列
        self.audio_queue = queue.Queue()
        self.long_sentence = ""
        self.punctuations = punctuations
        self.first_split_chars = first_split_chars
        self.max_buffer_length = max_buffer_length
        # 编号计数器
        self.sentence_counter = 0
        # 中断控制
        self.wake_flag = False
        self.wake_flag_lock = threading.Lock()
        # TTS 函数
        self.text_to_speech_func = text_to_speech_func
        # TTS 线程
        self.tts_thread = None
        # 音频播放线程
        self.audio_player_thread = None
        # 控制标志
        self.tts_running = False
        self.audio_running = False
        self.tts_running_lock = threading.Lock()
        self.audio_running_lock = threading.Lock()
        # 播放控制信号量 - 确保一次只有一个音频在播放
        self.audio_playing_semaphore = threading.Semaphore(1)
        # 当前播放的音频ID
        self.current_playing_id = None
        # 用于防止pygame全局状态冲突
        self.pygame_lock = threading.Lock()

    def process_stream(self, stream):
        """
        实时处理流式数据
        参数:
        stream: 数据流对象，支持迭代
        返回:
        queue.Queue: 包含处理后句子的队列
        """
        # 重置状态
        self.long_sentence = ""
        self.sentence_queue = queue.Queue()
        self.real_time_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self.wake_flag = False
        self.sentence_counter = 0  # 重置句子计数器
        buffer = ""
        first_split_done = False
        
        # 启动 TTS 线程
        if self.text_to_speech_func:
            self._start_tts_thread()
            self._start_audio_player_thread()
        
        try:
            for chunk in stream:
                # 根据实际流的结构提取内容，这里需要根据具体使用场景调整
                content = self._extract_content(chunk)
                if not content:
                    continue
                    
                # 检查是否超过最大缓冲区长度
                if len(self.long_sentence) > self.max_buffer_length:
                    self.long_sentence = self.long_sentence[-self.max_buffer_length:]
                    
                # 累积内容
                buffer += content
                self.long_sentence += content
                
                # 第一次分割逻辑
                if not first_split_done and any(char in buffer for char in self.first_split_chars):
                    self._process_sentence(buffer.strip())
                    buffer = ""
                    first_split_done = True
                    
                # 常规分割逻辑
                for char in content:
                    if char in self.punctuations:
                        self._process_sentence(buffer.strip())
                        buffer = ""
                        
                # 检查中断标志
                with self.wake_flag_lock:
                    if self.wake_flag:
                        print("检测到打断信号，停止流式处理")
                        break
        except Exception as e:
            print(f"流处理异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 处理最后剩余的内容
            if buffer.strip():
                self._process_sentence(buffer.strip())
                
            print("流处理完成，等待TTS和音频播放完成...")
            
            # 等待所有队列处理完成
            try:
                # 首先等待tts队列处理完所有内容
                if not self.real_time_queue.empty():
                    print(f"等待TTS队列处理完成，当前剩余{self.real_time_queue.qsize()}个项目...")
                    self.real_time_queue.join()
                    
                # 给TTS一些额外时间处理
                time.sleep(0.5)
                
                # 然后停止TTS线程
                with self.tts_running_lock:
                    self.tts_running = False
                print("TTS队列处理完成，TTS线程已标记退出")
                
                # 等待音频队列处理完所有内容
                if not self.audio_queue.empty():
                    print(f"等待音频队列处理完成，当前剩余{self.audio_queue.qsize()}个项目...")
                    self.audio_queue.join()
                
                # 给播放线程一些额外时间
                time.sleep(0.5)
                
                # 最后停止音频播放线程
                with self.audio_running_lock:
                    self.audio_running = False
                print("音频队列处理完成，音频播放线程已标记退出")
                
                # 短暂等待线程退出
                if self.tts_thread and self.tts_thread.is_alive():
                    self.tts_thread.join(timeout=5)
                    
                if self.audio_player_thread and self.audio_player_thread.is_alive():
                    self.audio_player_thread.join(timeout=5)
                    
                print("所有处理线程已退出或超时")
            except Exception as e:
                print(f"等待队列处理时出错: {e}")
                
            print("流处理全部完成")
                
        return self.sentence_queue

    def _process_sentence(self, sentence):
        """
        处理单个句子
        将句子加入队列并实时打印
        """
        if sentence:
            # 递增编号计数器
            self.sentence_counter += 1
            
            # 将(id, sentence)元组加入队列
            sentence_tuple = (self.sentence_counter, sentence)
            self.sentence_queue.put(sentence_tuple)
            self.real_time_queue.put(sentence_tuple)
            
            # 格式化时间，精确到毫秒
            current_time = datetime.now()
            formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'

            print(f"句子分割时间: {formatted_time}")
            # 实时打印句子信息
            print(f"句子ID: {self.sentence_counter}, 内容: {sentence}")

    def _extract_content(self, chunk):
        """
        从数据流的chunk中提取内容
        需要根据实际数据流结构重写
        """
        try:
            return chunk.choices[0].delta.content or ""
        except AttributeError:
            # 如果无法提取内容，返回空字符串
            return ""

    def get_real_time_results(self):
        """
        获取实时处理的结果队列
        返回:
        queue.Queue: 包含(id, content)元组的实时处理队列
        """
        return self.real_time_queue

    def set_wake_flag(self, flag=True):
        """
        设置中断标志
        参数:
        flag (bool): 是否中断处理
        """
        with self.wake_flag_lock:
            self.wake_flag = flag
            
        # 如果设置了中断标志，也停止音频播放
        with self.pygame_lock:
            if flag and pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()

    def get_long_sentence(self):
        """
        获取累积的长句
        返回:
        str: 累积的长句
        """
        return self.long_sentence
        
    def _start_tts_thread(self):
        """
        启动TTS线程
        """
        with self.tts_running_lock:
            self.tts_running = True
        
        self.tts_thread = threading.Thread(target=self._tts_worker)
        self.tts_thread.daemon = True  # 设为守护线程
        self.tts_thread.start()
    
    def _start_audio_player_thread(self):
        """
        启动音频播放线程
        """
        with self.audio_running_lock:
            self.audio_running = True
        
        self.audio_player_thread = threading.Thread(target=self._audio_player_worker)
        self.audio_player_thread.daemon = True  # 设为守护线程
        self.audio_player_thread.start()
        
    def _tts_worker(self):
        """
        TTS工作线程，处理实时结果并传递给文本转语音函数
        """
        # 获取实时结果队列
        results_queue = self.real_time_queue
        processed_ids = set()  # 用于跟踪已处理的句子ID
        waiting_empty_count = 0  # 用于检测队列持续为空的次数
        
        while True:
            # 检查是否应该继续运行
            with self.tts_running_lock:
                if not self.tts_running:
                    print("[TTS] TTS线程收到退出信号")
                    break
            
            try:
                # 非阻塞方式获取，设置超时
                try:
                    sentence_id, sentence_content = results_queue.get(timeout=3)  # 增加超时时间
                    waiting_empty_count = 0  # 重置空队列计数
                    
                    # 确保不重复处理同一句子
                    if sentence_id in processed_ids:
                        results_queue.task_done()
                        continue
                        
                    processed_ids.add(sentence_id)
                    
                    # 打印调试信息
                    print(f"Processing - Sentence ID: {sentence_id}")
                    print(f"Sentence Content: {sentence_content}")
                    
                    # 将内容传递给TTS函数
                    if self.text_to_speech_func:
                        audio_path = self.text_to_speech_func(sentence_content, sentence_id)
                        
                        # 格式化时间，精确到毫秒
                        current_time = datetime.now()
                        formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
                        print("TTS完成时间（精确到毫秒）:", formatted_time)
                        
                        # 打印生成的音频路径
                        print(f"Generated audio path: {audio_path}")
                        
                        # 将音频路径添加到播放队列
                        self.audio_queue.put((sentence_id, audio_path))
                        time.sleep(0.5)
                    # 标记任务完成
                    results_queue.task_done()
                
                except queue.Empty:
                    # 如果队列持续为空，考虑退出
                    waiting_empty_count += 1
                    if waiting_empty_count > 10:  # 连续10次检查都为空
                        print("[TTS] 队列持续为空，无更多句子，退出TTS线程")
                        break
                    continue
                
            except Exception as e:
                print(f"处理结果时发生错误: {e}")
                import traceback
                traceback.print_exc()
                break
        
        print("[TTS] TTS线程正常退出")
    
    def _audio_player_worker(self):
        """
        音频播放线程，严格按顺序播放生成的音频文件，一次只播放一个
        """
        played_ids = set()  # 用于跟踪已播放的句子ID
        expected_id = 1  # 期望播放的下一个ID
        pending_audios = {}  # 存储待播放的音频 {id: path}
        waiting_empty_count = 0  # 用于检测队列持续为空的次数
        
        while True:
            # 检查是否应该继续运行
            with self.audio_running_lock:
                if not self.audio_running:
                    print("[音频播放] 播放线程收到退出信号")
                    break
            
            try:
                # 检查是否有新音频
                try:
                    sentence_id, audio_path = self.audio_queue.get(timeout=2)  # 增加超时时间
                    waiting_empty_count = 0  # 重置空队列计数
                    pending_audios[sentence_id] = audio_path
                    self.audio_queue.task_done()
                    print(f"[音频队列] 添加音频 ID: {sentence_id}, 路径: {audio_path}")
                except queue.Empty:
                    # 如果队列持续为空，且TTS已经不在运行，则考虑退出
                    with self.tts_running_lock:
                        tts_still_running = self.tts_running
                    
                    if not tts_still_running and len(pending_audios) == 0:
                        waiting_empty_count += 1
                        if waiting_empty_count > 5:  # 连续5次检查都为空，且没有待播放的音频
                            print("[音频播放] 队列持续为空且TTS已停止，无更多音频，退出线程")
                            break
                
                # 检查打断标志
                with self.wake_flag_lock:
                    if self.wake_flag:
                        print("[音频播放] 检测到打断标志，退出播放线程")
                        break
                
                # 按顺序播放音频，严格一个接一个
                if expected_id in pending_audios and expected_id not in played_ids:
                    audio_path = pending_audios[expected_id]
                    
                    # 格式化时间，精确到毫秒
                    current_time = datetime.now()
                    formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
                    print(f"开始播放音频 ID: {expected_id}, 时间: {formatted_time}")
                    
                    # 获取信号量，确保一次只播放一个音频
                    self.audio_playing_semaphore.acquire()
                    self.current_playing_id = expected_id
                    
                    try:
                        # 阻塞式播放音频，确保完全播放完毕后才继续
                        self._play_audio_blocking(audio_path)
                        
                        # 音频播放完成后处理
                        print(f"[顺序播放] 音频 ID: {expected_id} 播放完成")
                        
                        # 标记为已播放
                        played_ids.add(expected_id)
                        expected_id += 1
                        
                        # 如果不是最后一个音频，添加0.2秒延迟
                        if any(id > expected_id - 1 for id in pending_audios.keys()):
                            print(f"[顺序播放] 添加0.2秒播放间隔...")
                            time.sleep(0.2)
                            print(f"[顺序播放] 间隔结束，继续下一音频")
                    finally:
                        # 释放信号量
                        self.current_playing_id = None
                        self.audio_playing_semaphore.release()
                    
                    # 检查打断标志
                    with self.wake_flag_lock:
                        if self.wake_flag:
                            break
                
                # 短暂休眠，避免CPU占用过高
                time.sleep(0.01)
                
            except Exception as e:
                print(f"音频播放时发生错误: {e}")
                import traceback
                traceback.print_exc()
                # 确保释放信号量
                if self.audio_playing_semaphore._value == 0:
                    self.audio_playing_semaphore.release()
                continue  # 继续尝试播放下一个音频
        
        print("[音频播放] 播放线程正常退出")
    
    def _play_audio_blocking(self, audio_path):
        """
        阻塞式播放音频，确保一个音频完全播放完毕后才返回
        """
        print(f"[播放音频] 开始阻塞式播放: {audio_path}")
        
        # 检查文件是否存在
        if not os.path.exists(audio_path):
            print(f"[播放音频] 错误：音频文件不存在: {audio_path}")
            return
        
        played_successfully = False
        
        # 使用子进程来播放音频，确保完全阻塞直到播放完成
        try:
            print(f"[播放音频] 使用子进程mpg123播放...")
            import subprocess
            
            # 使用subprocess运行mpg123播放音频，等待完成
            cmd = ["mpg123", "-q", audio_path]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 等待进程完成
            while process.poll() is None:
                # 检查打断标志
                with self.wake_flag_lock:
                    if self.wake_flag:
                        process.terminate()
                        print(f"[播放音频] 被打断: {audio_path}")
                        break
                # 小延迟降低CPU使用率
                time.sleep(0.01)
            
            # 获取返回码
            return_code = process.returncode
            if return_code == 0:
                played_successfully = True
                print(f"[播放音频] 成功：mpg123播放完成: {audio_path}")
            else:
                stdout, stderr = process.communicate()
                print(f"[播放音频] 警告：mpg123播放返回非零值 {return_code}: {stderr.decode('utf-8', errors='ignore')}")
                print(f"[播放音频] 尝试使用pygame播放...")
        except Exception as e:
            print(f"[播放音频] 警告：子进程播放失败，错误信息: {e}")
            print(f"[播放音频] 尝试使用pygame播放...")
        
        # 如果mpg123失败，回退到pygame
        if not played_successfully:
            try:
                with self.pygame_lock:
                    # 确保pygame已初始化
                    if not pygame.get_init():
                        pygame.init()
                    if not pygame.mixer.get_init():
                        pygame.mixer.init(devicename="default")
                    
                    # 打印pygame初始化信息
                    print(f"[播放音频] pygame音频设备: {pygame.mixer.get_init()}")
                    
                    # 加载并播放音频
                    pygame.mixer.music.load(audio_path)
                    pygame.mixer.music.play()
                    
                    print(f"[播放音频] pygame开始播放: {audio_path}")
                    
                    # 等待音频播放完成或被打断
                    while pygame.mixer.music.get_busy():
                        # 检查打断标志
                        with self.wake_flag_lock:
                            if self.wake_flag:
                                pygame.mixer.music.stop()
                                print(f"[播放音频] 被打断: {audio_path}")
                                break
                        # 小延迟降低CPU使用率
                        pygame.time.delay(10)
                    
                    played_successfully = True
                    print(f"[播放音频] 成功：pygame播放完成: {audio_path}")
                    
            except Exception as e:
                print(f"[播放音频] 错误：pygame播放失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 最终播放状态报告
        if not played_successfully:
            print(f"[播放音频] 严重错误：所有播放方法都失败，无法播放: {audio_path}")
        else:
            print(f"[播放音频] ✓ 播放完成: {audio_path}")
            # 格式化时间，精确到毫秒
            current_time = datetime.now()
            formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
            print(f"[播放音频] 完成时间: {formatted_time}")

# 实际使用的文本转语音函数
def text_to_speech(sentence, sentence_id):
    """文字转语音，返回音频文件路径"""
    print(f"[TTS] 转语音: {sentence}")
    package_path = '/home/fs/ymzz/src/aud_conver/aud_conver/tmp/'
    save_path = package_path  # 确保/tmp/正确拼接
    file_name = dbsentence2mp3(sentence, save_path + str(sentence_id))
    return file_name

# 使用示例
def usage_example(stream, text_to_speech_func=text_to_speech):
    """
    处理流并自动退出
    参数:
    - stream: 数据流对象
    - text_to_speech_func: 文本转语音函数
    返回:
    - processor: 处理器实例
    """
    # 创建处理器实例
    processor = StreamProcessor(text_to_speech_func=text_to_speech_func)
    
    # 直接在当前线程处理流，不创建额外线程
    try:
        # 处理流并等待完成
        processor.process_stream(stream)
        
        # 清理资源
        try:
            pygame.quit()
        except:
            pass
        
        print("处理完成，程序正常退出！")
    except KeyboardInterrupt:
        print("用户中断，正在退出...")
        processor.set_wake_flag(True)
    except Exception as e:
        print(f"处理时发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    return processor



# 调试函数
def debug_audio_playback(audio_file_path):
    """测试音频播放功能"""
    print("\n===== 音频播放调试 =====")
    print(f"Python版本: {sys.version}")
    print(f"当前工作目录: {os.getcwd()}")
    print(f"测试文件路径: {audio_file_path}")
    
    # 检查文件是否存在
    if os.path.exists(audio_file_path):
        print(f"文件存在，大小: {os.path.getsize(audio_file_path)} 字节")
    else:
        print(f"错误: 文件不存在!")
        return
    
    # 测试mpg_play_audio
    try:
        print("\n测试 mpg_play_audio:")
        from client_modules.aud_player import mpg_play_audio
        print("导入成功，开始播放...")
        mpg_play_audio(audio_file_path)
        print("mpg_play_audio播放完成")
    except Exception as e:
        print(f"mpg_play_audio测试失败: {e}")
    
    # 测试pygame
    try:
        print("\n测试 pygame:")
        import pygame
        print(f"pygame版本: {pygame.version.ver}")
        
        pygame.init()
        pygame.mixer.init()
        print(f"pygame初始化成功，音频设备: {pygame.mixer.get_init()}")
        
        # 创建事件来跟踪音频播放结束
        MUSIC_END_EVENT = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(MUSIC_END_EVENT)
        
        pygame.mixer.music.load(audio_file_path)
        print("加载音频成功，开始播放...")
        pygame.mixer.music.play()
        
        # 等待播放完成
        playing = True
        while playing:
            for event in pygame.event.get():
                if event.type == MUSIC_END_EVENT:
                    playing = False
                    break
            
            if not pygame.mixer.music.get_busy():
                playing = False
            
            # 小延迟
            pygame.time.delay(100)
        
        print("pygame播放完成")
        pygame.quit()
    except Exception as e:
        print(f"pygame测试失败: {e}")
    
    print("===== 调试完成 =====\n")

# 如果直接运行，可以使用模拟的数据流进行测试




# 修改main函数以集成StreamProcessor


# # 如果直接运行，可以使用模拟的数据流进行测试
# if __name__ == "__main__":
#     # 导入所需模块
#     import time
    
#     # 模拟数据流
#     class MockStream:
#         def __init__(self, text_chunks):
#             self.text_chunks = text_chunks
            
#         def __iter__(self):
#             for chunk in self.text_chunks:
#                 class MockChunk:
#                     def __init__(self, content):
#                         self.choices = [type('obj', (object,), {
#                             'delta': type('obj', (object,), {
#                                 'content': content
#                             })
#                         })]
                        
#                 yield MockChunk(chunk)
    
#     # 创建模拟数据流
#     mock_text = ["这是一个", "测试", "，", "用于演示", "流式处理", "。", "另一个句子", "，", "用于测试", "。"]
#     mock_stream = MockStream(mock_text)
    
#     # 运行示例
#     usage_example(mock_stream)

'''
#使用实例
processor = StreamProcessor()
# 创建一个线程用于处理数据流
processing_thread = threading.Thread(target=processor.process_stream, args=(stream,))
processing_thread.daemon = True  # 设为守护线程，当主程序退出时自动终止
processing_thread.start()

# 在主线程中，可以持续检查队列
while True:
    try:
        # 非阻塞方式获取，设置超时
        sentence = processor.get_real_time_results().get(timeout=0.1)
        # 处理每个句子
        print(sentence)
    except queue.Empty:
        # 检查处理是否完成
        if not processing_thread.is_alive():
            break
'''
#更新于 25.3.24  流式分割句子来用于合成yy 语音合成 package_path需要改成本地保存路径