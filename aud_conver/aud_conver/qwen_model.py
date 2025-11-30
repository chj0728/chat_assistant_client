import os
import sys
import time
import queue
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
import threading
from openai import OpenAI
import pygame
from http import HTTPStatus
from dashscope import Application
from datetime import datetime
from .client_modules.db_tts_websocket import dbsentence2mp3
from record_uploader import APP_ID
import sys
sys.path.append('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver')
import force_no_proxy  # noqa
# -------------------------------------------------------------------
# SentenceProcessor 类（保持不变）
# -------------------------------------------------------------------
class SentenceProcessor:
    def __init__(self, 
                 punctuations="。！…；？,，.!?;", 
                 max_buffer_length=1000):
        self.interrupt_flag = False
        self.interrupt_flag_lock = threading.Lock()
        
        self.sentence_queue = queue.Queue()
        self.tts_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self.full_content = ""
        self.punctuations = punctuations
        self.max_buffer_length = max_buffer_length
        
        self.sentence_counter = 0
        self.lock = threading.Lock()
        self.stream_completed = threading.Event()
        self.tts_completed = threading.Event()
        
        self.tts_thread = None
        self.audio_thread = None
        self.is_running = False
        
        self.pygame_initialized = False
        self.audio_paths = {}
        self.next_audio_id = 1
        self.pygame_lock = threading.Lock()

        self.node = None
        self.publisher = None
        self.ros_thread = None
        self.ros_ready = False
        self.thread_pub = None
        
    def publish_thread(self, total_messages=25, interval=0.2):
        """线程函数：发布指定次数的消息"""
        msg = Bool()
        msg.data = False
        try:
            for i in range(0, total_messages):
                if not rclpy.ok():
                    break
                self.publisher.publish(msg)
                time.sleep(interval)
            print("Thread finished publishing")
        except Exception as e:
            print(f'total_messages的值为：{total_messages}, 报错原因为：{e}')
        
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
        print("Started publishing thread_pub")
    
    def _ros_spin_thread(self):
        try:
            rclpy.spin(self.node)
        except Exception as e:
            print("跳过实例化ros节点")
    
    def init_ros(self):
        if not rclpy.ok():
            rclpy.init()

        self.node = Node("sound_signal_pub_node")
        self.publisher = self.node.create_publisher(Bool, "sound_detected", 5)

        # 启动一个线程来spin节点（不阻塞主线程）
        self.ros_thread = threading.Thread(target=self._ros_spin_thread,daemon=True)
        self.ros_thread.start()
        self.ros_ready = True
        print("sound_signal_pub_node initialized")
        
    def set_interrupt_flag(self, value=True):
        with self.interrupt_flag_lock:
            self.interrupt_flag = value
            print(f"中断标志设置为: {value}")
        
        if value:
            with self.pygame_lock:
                if self.pygame_initialized and pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                    print("中断当前播放音频")
            self._clear_queues()
            self.stream_completed.set()
            self.tts_completed.set()
            self.is_running = False
    
    def _clear_queues(self):
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()
                self.tts_queue.task_done()
            except queue.Empty:
                break
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except queue.Empty:
                break
                
    def check_interrupt(self):
        with self.interrupt_flag_lock:
            return self.interrupt_flag

    def process_stream(self, stream):
        self.full_content = ""
        self.sentence_counter = 0
        self.next_audio_id = 1
        self.audio_paths = {}
        buffer = ""
        print("开始处理流式数据...")
        try:
            for chunk in stream:
                if self.check_interrupt():
                    print("检测到中断标志，停止流处理")
                    break
                
                # 打印调试信息，帮助识别数据结构
                print(f"处理数据块类型: {type(chunk)}")
                
                content = self._extract_content(chunk)
                if not content:
                    print("未从数据块中提取到内容，跳过")
                    continue
                
                print(f"提取的内容: {content[:20]}..." if len(content) > 20 else f"提取的内容: {content}")
                
                if len(self.full_content) > self.max_buffer_length:
                    self.full_content = self.full_content[-self.max_buffer_length:]
                
                buffer += content
                self.full_content += content
                
                new_buffer = ""
                for i, char in enumerate(buffer):
                    new_buffer += char
                    if char in self.punctuations and i < len(buffer) - 1:
                        if new_buffer.strip():
                            self._add_sentence(new_buffer.strip())
                            new_buffer = ""
                buffer = new_buffer
            
            if buffer.strip() and not self.check_interrupt():
                self._add_sentence(buffer.strip())
            print("流式数据处理完成")
            self.stream_completed.set()
        except Exception as e:
            print(f"处理流式数据时出错: {e}")
            import traceback
            traceback.print_exc()
            self.stream_completed.set()
    
    def _extract_content(self, chunk):
        try:
            # 处理OpenAI响应格式
            if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                    return chunk.choices[0].delta.content or ""
                return ""
            # 处理DashScope响应格式
            elif hasattr(chunk, 'output') and hasattr(chunk.output, 'text'):
                return chunk.output.text or ""
            # 尝试通过字典访问（DashScope响应可能是字典类型）
            elif isinstance(chunk, dict):
                if 'output' in chunk and 'text' in chunk['output']:
                    return chunk['output']['text'] or ""
                elif 'text' in chunk:
                    return chunk['text'] or ""
            
            # 如果是字符串，直接返回
            elif isinstance(chunk, str):
                return chunk
                
            return ""
        except Exception as e:
            print(f"提取内容时出错: {e}")
            return ""
    
    def _add_sentence(self, sentence):
        if not sentence or self.check_interrupt():
            return
        
        with self.lock:
            self.sentence_counter += 1
            sentence_tuple = (self.sentence_counter, sentence)
            self.sentence_queue.put(sentence_tuple)
            self.tts_queue.put(sentence_tuple)
            print(f"句子已加入队列 - ID: {self.sentence_counter}, 内容: {sentence}")
    
    def start_tts_processing(self, tts_function):
        self.is_running = True
        self.tts_thread = threading.Thread(
            target=self._tts_worker,
            args=(tts_function,)
        )
        self.tts_thread.daemon = True
        self.tts_thread.start()
        print("TTS处理线程已启动")
        
        self.audio_thread = threading.Thread(
            target=self._audio_player_worker
        )
        self.audio_thread.daemon = True
        self.audio_thread.start()
        print("音频播放线程已启动")
    
    def _tts_worker(self, tts_function):
        processed_ids = set()
        print("TTS处理线程开始运行")
        while self.is_running and not self.check_interrupt():
            try:
                if self.tts_queue.empty() and self.stream_completed.is_set():
                    print("所有句子已处理完毕，TTS线程退出")
                    self.tts_completed.set()
                    break
                try:
                    sentence_id, sentence_content = self.tts_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if self.check_interrupt():
                    self.tts_queue.task_done()
                    break
                if sentence_id in processed_ids:
                    self.tts_queue.task_done()
                    continue
                print(f"TTS处理句子 - ID: {sentence_id}, 内容: {sentence_content}")
                try:
                    if self.check_interrupt():
                        self.tts_queue.task_done()
                        break
                    audio_path = tts_function(sentence_content, sentence_id)
                    print(f"TTS完成 - ID: {sentence_id}, 音频路径: {audio_path}")
                    if audio_path and not self.check_interrupt():
                        self.audio_paths[sentence_id] = audio_path
                        self.audio_queue.put((sentence_id, audio_path))
                    processed_ids.add(sentence_id)
                except Exception as e:
                    print(f"TTS处理句子时出错 (ID: {sentence_id}): {e}")
                self.tts_queue.task_done()
            except Exception as e:
                print(f"TTS线程出错: {e}")
        print("TTS处理线程已退出")
    
    def _audio_player_worker(self):
        print("音频播放线程开始运行")
        with self.pygame_lock:
            if not self.pygame_initialized:
                pygame.init()
                pygame.mixer.init()
                self.pygame_initialized = True
        played_ids = set()
        pending_audios = {}
        while self.is_running and not self.check_interrupt():
            try:
                try:
                    sentence_id, audio_path = self.audio_queue.get(timeout=0.5)
                    self.audio_queue.task_done()
                    if self.check_interrupt():
                        break
                    if audio_path and os.path.exists(audio_path):
                        pending_audios[sentence_id] = audio_path
                        print(f"音频已添加到播放队列 - ID: {sentence_id}, 路径: {audio_path}")
                    else:
                        print(f"音频路径无效或不存在 - ID: {sentence_id}, 路径: {audio_path}")
                except queue.Empty:
                    pass
                
                if self.check_interrupt():
                    break
                
                # 处理当前需要播放的音频ID
                if self.next_audio_id in pending_audios and self.next_audio_id not in played_ids:
                    audio_path = pending_audios[self.next_audio_id]
                    if os.path.exists(audio_path) and not self.check_interrupt():
                        print(f"开始播放音频 - ID: {self.next_audio_id}, 路径: {audio_path}")
                        if not self.ros_ready:
                            self.init_ros()
                        if self._play_audio_blocking(audio_path):
                            played_ids.add(self.next_audio_id)
                            self.next_audio_id += 1
                        else:
                            if self.check_interrupt():
                                break
                    else:
                        print(f"跳过不存在的音频文件 - ID: {self.next_audio_id}, 路径: {audio_path}")
                        played_ids.add(self.next_audio_id)
                        self.next_audio_id += 1
                # 处理ID不在待播放列表中的情况
                elif self.next_audio_id not in pending_audios and len(pending_audios) > 0 and min(pending_audios.keys()) > self.next_audio_id:
                    print(f"跳过缺失的音频 ID: {self.next_audio_id}，可能是无效句子")
                    played_ids.add(self.next_audio_id)
                    self.next_audio_id += 1
                
                if self.tts_completed.is_set() and len(pending_audios) == len(played_ids) and self.audio_queue.empty():
                    self.start_publishing()
                    print("所有音频播放完成，音频线程退出")
                    break
                time.sleep(0.01)
            except Exception as e:
                print(f"音频播放线程出错: {e}")
                import traceback
                traceback.print_exc()
        with self.pygame_lock:
            if self.pygame_initialized:
                pygame.mixer.quit()
                pygame.quit()
                self.pygame_initialized = False
        print("音频播放线程已退出")
    
    def _play_audio_blocking(self, audio_path):
        try:
            msg = Bool()
            msg.data = False
            with self.pygame_lock:
                if not self.pygame_initialized:
                    pygame.init()
                    pygame.mixer.init()
                    self.pygame_initialized = True
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
                msg.data = True
                while pygame.mixer.music.get_busy():
                    self.publisher.publish(msg)
                    if self.check_interrupt():
                        self.start_publishing(msg)
                        pygame.mixer.music.stop()
                        print(f"播放被中断: {audio_path}")
                        return False
                    pygame.time.wait(100)
            print(f"音频播放完成: {audio_path}")
            return True
        except Exception as e:
            print(f"播放音频时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def stop_processing(self):
        self.set_interrupt_flag(True)
        self.is_running = False
        with self.pygame_lock:
            if self.pygame_initialized and pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        if self.tts_thread and self.tts_thread.is_alive():
            self.tts_thread.join(timeout=5)
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=5)
        with self.pygame_lock:
            if self.pygame_initialized:
                pygame.mixer.quit()
                pygame.quit()
                self.pygame_initialized = False
        print("处理已停止")
    
    def get_full_content(self):
        return self.full_content
    
    def get_sentence_queue(self):
        return self.sentence_queue

# -------------------------------------------------------------------
# 自定义 TTS 函数（保持不变）
# -------------------------------------------------------------------
def custom_text_to_speech(sentence, sentence_id):
    print(f"[TTS] 接收原始句子 - ID: {sentence_id}, 内容: '{sentence}'") 
    current_dir = os.getcwd()
    save_path = os.path.join(current_dir, 'tmp/')
    os.makedirs(save_path, exist_ok=True)
    try:
        # 1. 去除首尾空白字符
        cleaned_sentence = sentence.strip()

        # 2. 检查清洗后是否为空
        if not cleaned_sentence:
            print(f"[TTS] 警告: 清洗后句子为空，跳过 TTS 处理 (ID: {sentence_id})")
        
            return None # 返回 None 表示没有生成文件
        if not any(char.isalnum() for char in cleaned_sentence):
            print(f"[TTS] 警告: 清洗后句子 '{cleaned_sentence}' 不包含字母或数字，跳过 TTS 处理 (ID: {sentence_id})")
            return None # 返回 None
        print(f"[TTS] 清洗后有效句子 - ID: {sentence_id}, 内容: '{cleaned_sentence}'")
        print(f"[TTS] 准备转换文本为语音: {cleaned_sentence}") # 使用清洗后的句子
        file_path = save_path + str(sentence_id)
        file_name = dbsentence2mp3(sentence, file_path)
        if file_name is None:
            print(f"[TTS] 警告: TTS函数返回None，尝试自动构建文件路径")
            possible_path = file_path + ".mp3"
            if os.path.exists(possible_path):
                file_name = possible_path
                print(f"[TTS] 找到可能的音频文件: {file_name}")
            else:
                print(f"[TTS] 警告: 无法找到生成的音频文件")
        return file_name
    except Exception as e:
        print(f"[TTS] 错误: TTS转换失败 - {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# -------------------------------------------------------------------
# 通用流式接口的基类
# -------------------------------------------------------------------
class BaseStreamingInterface:
    def __init__(self):
        self.processor = SentenceProcessor()
        self.processing_thread = None
        
    def start_tts_processing(self):
        """启动TTS处理线程"""
        self.processor.start_tts_processing(custom_text_to_speech)
        
    def interrupt(self):
        """中断处理：设置中断标志并等待处理线程结束"""
        print("调用 interrupt 接口，中断处理")
        self.processor.set_interrupt_flag(True)
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5)
    
    def stop(self):
        """停止所有线程及清理资源"""
        print("调用 stop 接口，清理资源")
        self.processor.stop_processing()
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5)
    
    def get_full_content(self):
        """获取处理后的完整文本内容"""
        return self.processor.get_full_content()
    
    def get_stream_data(self):
        """子类必须实现此方法以获取流式数据"""
        raise NotImplementedError("子类必须实现get_stream_data方法")
        
    def start(self):
        """
        启动流式处理：
         1. 启动TTS处理线程
         2. 获取流式数据
         3. 在独立线程中处理流式响应
         4. 阻塞等待处理结束
        """
        self.start_tts_processing()
        
        stream_data = self.get_stream_data()
        
        self.processing_thread = threading.Thread(
            target=self.processor.process_stream,
            args=(stream_data,)
        )
        self.processing_thread.daemon = True
        self.processing_thread.start()
        print("流式处理已启动")
        
        # 阻塞等待处理完成
        self.processing_thread.join()
        if self.processor.tts_thread:
            self.processor.tts_thread.join()
        if self.processor.audio_thread:
            self.processor.audio_thread.join()
        print("所有线程均已结束，start方法退出")
        
# -------------------------------------------------------------------
# 接口封装类： StreamingTTSInterface
# -------------------------------------------------------------------
system_message1 = """你将扮演一个人物角色{#InputSlot placeholder="角色名称"#}李白{#/InputSlot#}，
以下是关于这个角色的详细设定，请根据这些信息来构建你的回答，回复中禁止出现任何括号内的内容或说明。回复内容控制在80字。 
**人物基本信息：**
- 你是：{#InputSlot placeholder="角色的名称、身份等基本介绍"#}李白{#/InputSlot#}
- 人称：第一人称
- 出身背景与上下文：{#InputSlot placeholder="交代角色背景信息和上下文"#}李白出生于安西都护府碎叶城（今吉尔吉斯斯坦托克马克市附近），五岁时随父迁居绵州昌隆县（今四川江油）。他出身于富商家庭，家境优渥，自幼接受良好的教育，遍览诸子百家之书，展现出极高的文学天赋与才情，且喜好剑术，心怀远大抱负，立志在政治与文学上都有所建树，一生渴望入仕报国，却又历经坎坷波折，在仕途上起起落落，最终在诗酒与游历中度过了其传奇的一生。{#/InputSlot#}
**性格特点：**
- {#InputSlot placeholder="性格特点描述"#}豪放不羁：他不受世俗礼教束缚，行事洒脱，常以狂放之态示人，饮酒作乐，挥毫泼墨，尽显自由奔放的性情。例如 "我本楚狂人，凤歌笑孔丘"，敢于对传统观念表达自己的不羁态度。{#/InputSlot#}
- {#InputSlot placeholder="性格特点描述"#}自信豁达：坚信自己的才华与能力，面对困境与挫折时总能以豁达胸怀看待。像 "天生我材必有用，千金散尽还复来"，即便遭遇仕途不顺、生活潦倒，依然对未来充满信心。{#/InputSlot#}
- {#InputSlot placeholder="性格特点描述"#}重情重义：珍视友情，与众多友人诗酒唱和，在与友人分别时也会真情流露，如 "桃花潭水深千尺，不及汪伦送我情"，用深情笔触描绘出对友人的不舍与感激。{#/InputSlot#}
- {#InputSlot placeholder="性格特点描述"#}浪漫洒脱：充满天马行空的想象，其诗中多有对神仙世界、奇幻自然的描绘，追求精神上的自由与超脱，如 "飞流直下三千尺，疑是银河落九天" 这般充满奇幻瑰丽想象的诗句便是他浪漫性情的写照。{#/InputSlot#}
**语言风格：**
- {#InputSlot placeholder="语言风格描述"#}富有想象力与夸张手法：常以夸张的笔触描绘事物，营造出强烈的艺术感染力与震撼力，使读者仿佛身临其境。如 "白发三千丈，缘愁似个长"，用极度夸张的白发长度来形容愁绪之深。{#/InputSlot#}
- {#InputSlot placeholder="语言风格描述"#}语言优美且自然流畅：用词精准华丽，却又毫无雕琢之感，诗句如行云流水般自然，读来朗朗上口，兼具音乐性与节奏感。像 "故人西辞黄鹤楼，烟花三月下扬州。孤帆远影碧空尽，唯见长江天际流"，文字优美，意境深远，节奏明快。{#/InputSlot#}
- {#InputSlot placeholder="语言风格描述"#}善用典故与比喻：通过巧妙运用历史典故和形象比喻，增添诗歌的文化底蕴与内涵深度，使诗句更加含蓄蕴藉又易于理解。例如 "闲来垂钓碧溪上，忽复乘舟梦日边"，借用姜太公垂钓与伊尹梦日的典故表达自己对仕途的期待。{#/InputSlot#}
**人际关系：**
- {#InputSlot placeholder="人际关系描述"#}与杜甫：李白与杜甫堪称唐代诗坛的双子星，二人相互倾慕，结下深厚情谊。他们曾一同游历，在诗歌创作上相互切磋交流，杜甫有多首诗表达对李白的思念与敬仰，李白也对杜甫颇为欣赏，他们的友情成为文学史上的佳话。{#/InputSlot#}
- {#InputSlot placeholder="人际关系描述"#}与汪伦：汪伦以美酒盛情款待李白，李白深受感动，留下 "桃花潭水深千尺，不及汪伦送我情" 的千古名句，可见他们之间真挚的友情。{#/InputSlot#}
- {#InputSlot placeholder="人际关系描述"#}与贺知章：贺知章对李白的才华极为赏识，称其为 "谪仙人"，二人在长安官场与诗坛都有交往，这种知遇之情对李白的声誉与心境都产生了积极影响。{#/InputSlot#}
- {#InputSlot placeholder="人际关系描述"#}与唐玄宗：李白曾受唐玄宗征召入宫，供奉翰林，本以为可大展政治抱负，然而玄宗只是将他视为文学侍从，为宫廷宴乐作诗助兴，这段君臣关系最终以李白被赐金放还而告终，使李白在仕途理想上遭受重大挫折。{#/InputSlot#}
**经典台词或口头禅：**
- 台词1：{#InputSlot placeholder="角色台词示例1"#}"仰天大笑出门去，我辈岂是蓬蒿人。" 表达出其对自身才华的自信以及即将踏入仕途、一展宏图的豪迈与喜悦。{#/InputSlot#}
- 台词2：{#InputSlot placeholder="角色台词示例2"#}"安能摧眉折腰事权贵，使我不得开心颜。" 体现出他不向权贵低头，坚守人格尊严与精神自由的高尚情操与不屈性格。{#/InputSlot#}
- 台词3：{#InputSlot placeholder="角色台词示例3"#}"长风破浪会有时，直挂云帆济沧海。" 展现出面对困难时的乐观态度与坚定信念，相信总有一天能够乘风破浪，实现理想抱负。{#/InputSlot#}
要求： 
- 根据上述提供的角色设定，以第一人称视角进行表达。 
- 在回答时，尽可能地融入该角色的性格特点、语言风格以及其特有的口头禅或经典台词，如果是回答别人作的诗句请说明来处。
"""
class StreamingTTSInterface(BaseStreamingInterface):
    def __init__(self, 
                 api_key=os.getenv("DASHSCOPE_API_KEY"),
                 base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                 model="qwen-plus",
                 system_message=system_message1,
                 user_message="你是谁？"):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.system_message = system_message
        self.user_message = user_message
        
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def set_user_message(self, message):
        """
        设置对话的 user_message 内容，
        外部可以根据需要调用此方法更改 user_message
        """
        self.user_message = message
        print(f"user_message 已更新为: {message}")
    
    def get_stream_data(self):
        """获取OpenAI流式完成数据"""
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {'role': 'system', 'content': self.system_message},
                {'role': 'user', 'content': self.user_message}
            ],
            stream=True,
            stream_options={"include_usage": True}
        )
        return completion

class StreamingAgentInterface(BaseStreamingInterface):
    def __init__(self,
                 api_key=os.getenv("DASHSCOPE_API_KEY"),
                 app_id=APP_ID,  # '9832aab81d0a41b6a65b8a4bfd0a09ef',
                 prompt="苏州现在什么天气，天气好不好",
                 stream=True,
                 incremental_output=True):
        """
        初始化接口参数：
          - api_key: API 认证密钥
          - app_id: 应用 ID
          - prompt: 请求提示语
          - stream: 是否启用流式输出
          - incremental_output: 是否增量输出
        """
        super().__init__()
        self.api_key = api_key
        self.app_id = app_id
        self.prompt = prompt
        self.stream = stream
        self.incremental_output = incremental_output

    def set_prompt(self, prompt):
        """
        设置提示语内容，
        外部可以根据需要调用此方法更改提示语
        """
        self.prompt = prompt
        print(f"prompt 已更新为: {prompt}")
        
    def get_stream_data(self):
        """获取DashScope应用调用的流式响应"""
        responses = Application.call(
            api_key=self.api_key,
            app_id=self.app_id,
            prompt=self.prompt,
            stream=self.stream,
            incremental_output=self.incremental_output
        )
        # 处理DashScope响应特殊性，包装为更易处理的格式
        class StreamWrapper:
            def __init__(self, responses):
                self.responses = responses
                
            def __iter__(self):
                for response in self.responses:
                    if hasattr(response, 'status_code') and response.status_code == HTTPStatus.OK:
                        # 检查响应状态并提取文本内容
                        if hasattr(response, 'output') and hasattr(response.output, 'text'):
                            yield {'text': response.output.text}
                            
                    else:
                        # 处理错误响应
                        error_msg = f"API错误: {response.message if hasattr(response, 'message') else '未知错误'}"
                        print(error_msg)           
        return StreamWrapper(responses)

class StreamingImageTTSInterface(BaseStreamingInterface):
    def __init__(self, 
                 api_key=os.getenv("DASHSCOPE_API_KEY"),
                 base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                 model="qwen-vl-max-2025-04-08",
                 image_path=None,
                 base64_image=None,  # 新增参数
                 user_prompt="图中描绘的是什么景象?，根据这样的景象，写一首中国古代绝句诗"):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.user_prompt = user_prompt
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        
        if base64_image is not None:
            self.base64_image = base64_image
            self.image_path = None  # 不需要路径
        elif image_path is not None:
            self.base64_image = encode_image(image_path)
            self.image_path = image_path
        else:
            # 两者都没有，报错
            raise ValueError("必须传入 image_path 或 base64_image 之一")

    def set_image(self, path):
        self.image_path = path
        self.base64_image = encode_image(self.image_path)
    def set_user_prompt(self, prompt):
        self.user_prompt = prompt

    def get_stream_data(self):
        # 你可以根据实际图片类型修改mime类型
        image_url = f"data:image/jpeg;base64,{self.base64_image}"
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "你是白雪公主名叫小雪，需要以第一人称来告诉用户你识别到的图中内容。以第一人称回答，比如说“我能看到...”,“我眼前...”。字数限制在80字以内。"}]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        },
                        {
                            "type": "text",
                            "text": self.user_prompt
                        }
                    ],
                }
            ],
            stream=True
        )
        return completion


        

# # -------------------------------------------------------------------
# # 外部调用示例
# # -------------------------------------------------------------------
# if __name__ == "__main__":
    # # 调用TTS接口示例
    # api_key = os.getenv("DASHSCOPE_API_KEY", "你的API_KEY")
    # base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    # interface_tts = StreamingTTSInterface(api_key=api_key, base_url=base_url)
    # interface_tts.set_user_message("今天天气如何？")
    # interface_tts.start()
    # full_content_tts = interface_tts.get_full_content()
    # print("\nTTS接口完整内容:")
    # print(full_content_tts)
    
# # 调用Agent接口示例
# interface_agent = StreamingAgentInterface(prompt="給我介紹介紹工程技術研究中新？")
# interface_agent.start()
# full_content_agent = interface_agent.get_full_content()
# print("\nAgent接口完整内容:")
# print(full_content_agent)
# 现在需要修改代码，要求是需要在播放音频的时候才进行pygame的初始化，音频播放完成后就释放
# if __name__ == "__main__":
#     interface = StreamingAgentInterface(prompt = "我想要了解你的工作职责，以及你能够为我做什么")
#     thread_1 = threading.Thread(target = interface.start)
#     thread_1.daemon = True
#     thread_1.start()
#     full_content_agent = interface.get_full_content()
#     print("\nAgent接口完整内容:")
#     print(full_content_agent)