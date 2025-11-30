#!/usr/bin/env python3
"""整个文件干两件事：
    1.接收一个话题，只要收到就播放“让一让“/“电量过低，需要回充”音频
    2.编写一个action服务器，根据传过来的任务类型，确定0为播放（播放指定的音频名字，但是这个名字直接在这个Mappingfixed_audio_mapping = {
                "0": "dh",
                "1": "0",
                "2": "1",
                "3": "2",
                "4": "3",
                "5": "4",
                "6": "5",
                "7": "6",
                "8": "7",
                "9": "8"
            }中, 还需要确定和唯一的那个.csv文件的联系）；1为暂停播放；其余不做处理
    3.编写一个服务，这个服务用于调用：合成固定音频；播放在线音频；删除音频"""
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
import threading
import os
import csv
import time
import shutil
import pygame
import rclpy.action
from std_msgs.msg import Int32, String
from std_msgs.msg import Bool
from .record_uploader import TIMBRE  
from .client_modules.db_tts_websocket import dbsentence2mp3
from .tts.cosyvoice import text2mp3
from .record_uploader import upload_file
from ymrobot_msgs.action import AudioControl
from ymrobot_msgs.srv import Audio


class AudioPlayerNode(Node):
    def __init__(self):
        super().__init__('audio_player_node')
        self.topic_playing = False  # 记录topic是否在播放（可选，重点其实 action 那个lock）
        self.topic_subscription = self.create_subscription(
            Int32,
            '/play_fixed_audio',
            self.topic_play_callback,
            1
        )
        self.topic_subscription_wakeupkeywords_update = self.create_subscription(
            String,
            '/welcome_word_update',
            self.topic_welcome_word_update,
            1
        )
        self.action_end_time = 0  # 记录action结束时间
        self.topic_cooldown = 2.0  # topic冷却时间（秒）
        self.get_logger().info("已订阅 /play_fixed_audio topic (Int32)，接收到消息将尝试播放 ryr.mp3")
        self.audio_dir = '/home/ymrobot/ymzz_into'
        os.makedirs(self.audio_dir, exist_ok=True)
        self.audio_files = self._scan_audio_files(self.audio_dir)   # 获取当前文件夹下的全部mp3文件名
        self.get_logger().info(f"可用音频文件: {self.audio_files}")

        self.player_lock = threading.Lock()
        self.stop_event = threading.Event()

        self.player_thread = None
        self.current_audio = None

        self._action_server = ActionServer(
            self,
            AudioControl,
            'audio_control_action',
            self.execute_callback,
            callback_group=ReentrantCallbackGroup(),
            cancel_callback=self.on_cancel_callback
        )

        self._txt_to_audio_server = self.create_service(
            Audio, 
            "audio_control_action_srv", 
            self.tts_callback,
            callback_group=ReentrantCallbackGroup()
        )

        input_sentence = """
        你好呀
        """
        file_path_ = '/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/wake.mp3'
        text2mp3(input_sentence, file_path_, )
        # input_sentence = """
        # 好的，之后有什么问题随时呼唤我哦
        # """
        # file_path_ = '/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male/byebye.mp3'
        # dbsentence2mp3(input_sentence,file_path_)

        
        self.get_logger().info('AudioPlayerNode 已启动。')

    def on_cancel_callback(self, goal_handle):
        """action取消服务函数"""
        self.get_logger().info("Action收到cancel请求，立即停止音频(stop_event set)")
        self.stop_event.set()   # 只需设置事件，主线程会检测后from client_modules调用stop
        # 无需Join! 提前join可能死锁或阻慢cancel响应
        return rclpy.action.CancelResponse.ACCEPT

    def tts_callback(self, request, response):
        """文字转语音服务回调函数"""
        start_time = time.time()
        response.success = False
        response.message = "未处理"
        response.total_elapsed_time = 0.0
        print("处理本次语音转文字服务")
        
        try:
            
            # 根据任务类型处理
            task_type = request.audio_task_type

            match task_type:
                case 0:  # 播放固定音频
                    audio_name = request.fixed_audio_name.strip()
                    if not audio_name:
                        response.message = "音频名称不能为空"
                        self.get_logger().error(response.message)
                    else:
                        # 确保有扩展名
                        if not audio_name.endswith('.mp3'):
                            audio_name += '.mp3'
                        
                        audio_path = os.path.join(self.audio_dir, audio_name)
                        self.get_logger().info(f"播放固定音频: '{audio_path}'")
                        
                        if os.path.exists(audio_path):
                            if self.player_thread and self.player_thread.is_alive():
                                self.get_logger().info("当前正在进行音频播放，忽略 service 播放请求。")
                                response.message = f"当前正在进行音频播放，忽略本次播放请求。"
                            else:
                                # 播放音频
                                with self.player_lock:
                                    # 清理现有线程
                                    if self.player_thread and self.player_thread.is_alive():
                                        self.get_logger().info("发现仍有播放线程存在，终止！")
                                        self.stop_event.set()
                                        self.player_thread.join(timeout=2)
                                    self.stop_event.clear()
                                    self.player_thread = threading.Thread(
                                        target=self._play_audio_thread,
                                        args=(audio_path,),
                                        daemon=True
                                    )
                                    self.player_thread.start()
                                    self.current_audio = audio_name
                                response.success = True
                                response.message = f"已播放固定音频: {audio_name}"
                        else:
                            response.message = f"固定音频不存在: {audio_name}"

                case 1:  # 合成音频
                    text = request.synthetic_audio_txt.strip()
                    if not text:
                        response.message = "合成文本不能为空"
                        self.get_logger().error(response.message)
                    else:
                        audio_name = request.synthetic_audio_title.strip()
                        if not audio_name:
                            audio_name = "合成音频"
                        if not audio_name.endswith('.mp3'):
                            audio_name += '.mp3'
                        
                        # 语音音色
                        voice_type = request.timbre.strip()
                        self.get_logger().info(f"合成音频: 标题='{audio_name}', 音色代码='{voice_type}', '内容='{text}'")

                        output_path = os.path.join(self.audio_dir, audio_name)
                        dbsentence2mp3(text, output_path, voice_type)            
                        # 验证文件生成
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                            # 准备数据
                            data = [audio_name, request.timbre, text]
                            
                            # 获取当前工作目录和绝对路径
                            audios_dir = "/home/ymrobot/ymzz_into"
                            file_name = "audios.csv"
                            file_name = os.path.join(audios_dir, file_name)
                            
                            re = self.update_csv(audio_name[:-4], voice_type, text)
                            if re:             
                                response.success = True
                                response.message = f"音频合成成功: {output_path}"
                            else:
                                response.success = False
                                response.message = f"音频合成成功,但是保存csv文件失败"
                        else:
                            response.message = "音频文件生成失败"

                case 2:  # 删除固定音频
                    audio_name = request.delete_fixed_audio.strip()
                    if not audio_name:
                        response.message = "音频名称不能为空"
                        self.get_logger().error(response.message)
                    else:
                        # 确保有扩展名
                        if not audio_name.endswith('.mp3'):
                            audio_name += '.mp3'
                        
                        audio_path = os.path.join(self.audio_dir, audio_name)
                        self.get_logger().info(f"删除固定音频: '{audio_path}'")
                        
                        if os.path.exists(audio_path):
                            try:
                                os.remove(audio_path)
                                csv_file = "/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/audios.csv" # 文件
                                temp_file = csv_file + ".tmp"   # 中间文件
                                rows_deleted = 0
                                total_rows = 0

                                try:
                                    with open(csv_file, 'r', newline='', encoding='utf-8') as infile, \
                                            open(temp_file, 'w', newline='', encoding='utf-8') as outfile:
                                        
                                        reader = csv.reader(infile)
                                        writer = csv.writer(outfile)

                                        
                                        # 处理数据行
                                        for row in reader:
                                            total_rows += 1
                                            if not row:  # 跳过空行
                                                continue
                                                
                                            # 检查第一列是否匹配目标值
                                            if str(row[0]).strip() == str(audio_name).strip():
                                                rows_deleted += 1
                                                continue  # 跳过匹配的行
                                            
                                            writer.writerow(row)
                                    shutil.move(temp_file, csv_file)
                                    print(f"处理完成! 总行数: {total_rows}, 删除行数: {rows_deleted}")

                                except Exception as e:
                                    print(f"处理失败: {str(e)}")
                                    # 清理临时文件
                                    if os.path.exists(temp_file):
                                        os.remove(temp_file)
                                    return False
                                response.success = True
                                response.message = f"已删除固定音频: {audio_name}"
                            except Exception as e:
                                response.message = f"删除失败: {str(e)}"
                        else:
                            response.message = f"固定音频不存在: {audio_name}"

                case 3:  # 上传对话记录
                    """上传逻辑"""
                    file_path = '/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/records.csv'
                    result = upload_file(file_path)
                    if result:
                        response.success = True
                    """删除records.csv文件"""
                    try:
                        os.remove(file_path)
                        self.get_logger().info("聊天记录csv文件上传成功，删除本地文件")
                        response.message = "上传成功"
                    except Exception as e:
                        self.get_logger().error(f"删除失败：{e}")
                        response.message = "上传成功，但删除本地文件失败"

                    
                case 4:  # 播放在线音频
                    text = request.play_online_audio.strip()
                    if not text:
                        response.message = "合成文本不能为空"
                        self.get_logger().error(response.message)
                    else:
                        audio_name = "online"
                        if not audio_name.endswith('.mp3'):
                            audio_name += '.mp3'
    
                        # 设置语音音色
                        voice_type = request.timbre.strip()
                        self.get_logger().info(f"合成音频: 标题='{audio_name}', 音色代码='{voice_type}', '内容='{text}'")

                        output_path = os.path.join(self.audio_dir, audio_name)
                        dbsentence2mp3(text, output_path, voice_type)
                        
                        # 验证文件生成
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                            response.message = f"音频合成成功: {output_path}"
                            if self.player_thread and self.player_thread.is_alive():
                                self.get_logger().info("当前正在进行音频播放，忽略 service 播放请求。")
                                response.message = f"当前正在进行音频播放，忽略本次播放请求。"
                            else:
                                # 播放音频
                                with self.player_lock:
                                    # 清理现有线程
                                    if self.player_thread and self.player_thread.is_alive():
                                        self.get_logger().info("发现仍有播放线程存在，终止！")
                                        self.stop_event.set()
                                        self.player_thread.join(timeout=2)
                                    self.stop_event.clear()
                                    self.player_thread = threading.Thread(
                                        target=self._play_audio_thread,
                                        args=(output_path,),
                                        daemon=True
                                    )
                                    self.player_thread.start()
                                    self.current_audio = audio_name
                                
                                while self.player_thread.is_alive():
                                    time.sleep(0.5)
                                self.get_logger().info(f"删除固定音频: '{output_path}'")
                                
                                if os.path.exists(output_path):
                                    try:
                                        os.remove(output_path)
                                        response.success = True
                                        response.message = f"已播放在线音频: {audio_name}"
                                    except Exception as e:
                                        response.message = f"删除失败: {str(e)}"
                                else:
                                    response.success = True
                                    response.message = f"已播放在线音频，删除时发现固定音频不存在: {audio_name}"
                        else:
                            response.message = "音频文件生成失败"

                case _:  # 默认处理未知类型
                    response.message = f"未知任务类型: {task_type}"
                    self.get_logger().error(response.message)
        
        except Exception as e:
            response.message = f"处理失败: {str(e)}"
            self.get_logger().error(f"处理请求时出错: {str(e)}", exc_info=True)
        
        finally:
            # 计算总耗时
            response.total_elapsed_time = time.time() - start_time
            
            # 记录结果
            if response.success:
                self.get_logger().info(f"任务成功: {response.message} (耗时: {response.total_elapsed_time:.2f}s)")
            else:
                self.get_logger().error(f"任务失败: {response.message} (耗时: {response.total_elapsed_time:.2f}s)")
            
            self.get_logger().info(f"response:{response}")
            return response
    


    def update_csv(self, title, timbre, text, flag = False, csv_file="/home/ymrobot/ros2_ws_guidance/src/guided-robot/assets/audios.csv"):
        """
        更新CSV文件的函数（无标题行版本）
        
        参数:
        title (str): synthetic_audio_title 列的值
        timbre (int/str): timbre 列的值
        text (str): synthetic_audio_txt 列的值
        flag (bool): 是否开启检索（查询是否有完美吻合前三项数据的行）功能，
        csv_file (str): CSV文件路径
        
        返回:
        bool: 操作是否成功
        """
        # 如果文件不存在，创建空文件
        if not os.path.exists(csv_file):
            open(csv_file, 'w', encoding='utf-8').close()
        
        # 读取现有数据
        rows = []
        try:
            with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) == 3:  # 确保每行都有三列
                        rows.append(row)
        except Exception as e:
            print(f"读取文件时出错: {str(e)}")
            return False
        
        # 检查是否有完全匹配的行
        for row in rows:
            if row == [title, str(timbre), text]:
                return True  # 存在完全匹配的行，返回True
        
        # 检查是否有标题匹配的行
        title_match_index = None
        for i, row in enumerate(rows):
            if row[0] == title:
                title_match_index = i
                if flag:
                    return True
                else:
                    break
        if flag:
            return False
        
        # 处理不同情况
        if title_match_index is not None:
            # 情况1: 标题相同但其他列不同，覆盖该行
            rows[title_match_index] = [title, str(timbre), text]
        else:
            # 情况2: 没有标题匹配，添加新行
            rows.append([title, str(timbre), text])
        
        # 写回文件（不包含标题行）
        try:
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(rows)  # 只写入数据行
            return 1    # 存在写入操作，（也就是说音频做了修改）
        except Exception as e:
            print(f"写入文件时出错: {str(e)}")
            return -1 


    def topic_play_callback(self, msg):
        """topic回调函数，猜测可能是接收到这个话题就播放这个ryr.mp3音频，是“让一让”
            msg.data : Int32        
        """
        current_time = time.time()
        
        # 检查是否在冷却期内
        if current_time - self.action_end_time < self.topic_cooldown:
            self.get_logger().info(f"Action刚结束，还在冷却期内，忽略topic请求。剩余冷却时间: {self.topic_cooldown - (current_time - self.action_end_time):.1f}秒")
            return
        self.get_logger().info(f"收到topic请求: {msg.data}")
        # 优先检测 action 是否在播放
        # 用 player_thread 有无 + action goal handle 或直接 player_thread 逻辑即可
        if self.player_thread and self.player_thread.is_alive():
            self.get_logger().info("当前正在进行 action 音频播放，忽略 topic 播放请求。")
            return

        # 若不在播放，直接用线程播放 ryr.mp3/ hc.mp3
        if msg.data == 1:
            audio_name = 'hc.mp3'
            audio_path = os.path.join(self.audio_dir, audio_name)
        elif msg.data == 0:
            audio_name = 'ryr.mp3'
            audio_path = os.path.join(self.audio_dir, audio_name)
        if not os.path.exists(audio_path):
            self.get_logger().error(f"音频文件 ryr.mp3 不存在，无法播放。")
            return

        with self.player_lock:
            # 双保险再清理一次
            if self.player_thread and self.player_thread.is_alive():
                self.get_logger().info("发现 still 有播放线程存在（非预期），终止！")
                self.stop_event.set()
                self.player_thread.join(timeout=2)
            self.stop_event.clear()
            self.player_thread = threading.Thread(
                target=self._play_audio_thread,
                args=(audio_path,),
                daemon=True
            )
            self.player_thread.start()
            self.current_audio = audio_name
        self.get_logger().info("已通过 topic 请求开始播放 ryr.mp3")
    
    def topic_welcome_word_update(self, msg):
        """欢迎词音频合成
        """
        text = msg.data.strip()
        if not text:
            self.get_logger().error("合成文本不能为空")
        else:
            audio_name = "welcome_ymzz_makabaka.mp3"
            
            self.get_logger().info(f"合成欢迎词......, 内容='{text}'")
            
            output_path = os.path.join(self.audio_dir, audio_name)           
                
            # 获取当前工作目录和绝对路径
            audios_dir = "/home/ymrobot/ymzz_into"
            file_name = "audios.csv"
            file_name = os.path.join(audios_dir, file_name)
            re = self.update_csv(audio_name[:-4], TIMBRE, text)
            if re == 0:
                self.get_logger().info("当前已存在一样的欢迎词音频")
            elif re == 1:
                dbsentence2mp3(text, output_path) 
                self.get_logger().info("合成新欢迎词成功")
            else:
                self.get_logger().error("合成写入音频csv文件失败，合成新欢迎词失败")

    def _scan_audio_files(self, audio_dir):
        """将传入的路径文件夹下的全部.mp3文件的文件名返回，若文件夹不存在则返回[]"""
        if not os.path.isdir(audio_dir):
            return []
        return [f for f in os.listdir(audio_dir) if f.lower().endswith('.mp3')]

        
    def execute_callback(self, goal_handle):
        """action服务函数"""
        self.get_logger().info("【DEBUG】execute_callback: 收到新Goal!")
        start_time = time.time()
        self.get_logger().info(f"DEBUG: stop_event.is_set()={self.stop_event.is_set()}")
        
        # 【新增】设置action播放状态为True
        self.action_playing = True
        self.get_logger().info("设置action_playing=True，阻止topic播放")
        
        # 打印请求ID，避免访问内部属性
        if hasattr(goal_handle, 'goal_id'):
            self.get_logger().info(f"DEBUG: goal_handle ID={goal_handle.goal_id}")
        
        # 不调用任何接受方法 - ROS2会自动处理

        req = goal_handle.request

        for att in dir(req):
            if not att.startswith('_') and att not in ["audio_task_type", "fixed_audio_name"]:
                val = getattr(req, att)
                self.get_logger().info(f"未用参数 {att}: {val}")

        try:  # 【新增】添加try-finally确保状态重置
            audio_task_type = req.audio_task_type
            fixed_audio_name = req.fixed_audio_name.strip()
            self.get_logger().info(f"发过来：{fixed_audio_name}")
            if fixed_audio_name.endswith('.mp3'):
                fixed_audio_name = fixed_audio_name[:-4]
            self.get_logger().info(f"发过来：{fixed_audio_name}")
            re = self.update_csv(fixed_audio_name, "test", "test", True)
            if not re:
                self.get_logger().error(f"未定义的fixed_audio_name: {fixed_audio_name}")
                result = AudioControl.Result()
                result.success = False
                result.message = f"未定义的fixed_audio_name: {fixed_audio_name}"
                result.total_elapsed_time = time.time() - start_time
                
                # 尝试调用succeed，但捕获异常
                try:
                    goal_handle.abort()
                    self.get_logger().info("已调用goal_handle.abort()")
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.abort()出错: {e}")
                    
                self.get_logger().info("【DEBUG】即将return结果")
                return result
            if not fixed_audio_name.endswith('.mp3'):
                fixed_audio_name += '.mp3'
            audio_path = os.path.join(self.audio_dir, fixed_audio_name)
            """接下来处理接收到的action中的 音频任务类型 0|1|其他 """
            """播放音频任务类型0"""
            if audio_task_type == 0:
                if not os.path.exists(audio_path):
                    """如果这个音频不存在文件夹中，跳过，返回报错信息"""
                    msg = f"音频 {fixed_audio_name} 不存在"
                    self.get_logger().error(msg)
                    result = AudioControl.Result()
                    result.success = False
                    result.message = msg
                    result.total_elapsed_time = time.time() - start_time
                    
                    # 尝试调用succeed，但捕获异常
                    try:
                        goal_handle.abort()
                        self.get_logger().info("已调用goal_handle.abort()")
                    except Exception as e:
                        self.get_logger().error(f"调用goal_handle.abort()出错: {e}")
                        
                    self.get_logger().info("【DEBUG】即将return结果")
                    return result

                """直接播放这段音频"""
                with self.player_lock:
                    if self.player_thread and self.player_thread.is_alive():
                        self.stop_event.set()
                        self.player_thread.join(timeout=2)
                    self.stop_event.clear()
                    self.player_thread = threading.Thread(target=self._play_audio_thread, args=(audio_path,), daemon=True)
                    self.player_thread.start()
                    self.current_audio = fixed_audio_name

                self.get_logger().info(f"[Action] 播放音频: {fixed_audio_name}")

                feedback = AudioControl.Feedback()
                """检查是否需要被中断，并时刻返回状态"""
                while self.player_thread.is_alive():
                    # 直接检查stop_event，这是最可靠的中断方法
                    if self.stop_event.is_set():
                        self.get_logger().info("检测到stop_event，停止音频播放")
                        feedback.message = "播放被中断"
                        
                        # 尝试发送反馈
                        try:
                            goal_handle.publish_feedback(feedback)
                        except Exception as e:
                            self.get_logger().error(f"发送反馈时出错: {e}")
                        
                        # 确保音频停止
                        pygame.mixer.music.stop()
                        self.player_thread.join(timeout=2)
                        
                        if self.player_thread.is_alive():
                            self.get_logger().warning("取消时播放线程未及时退出！")
                            
                        result = AudioControl.Result()
                        result.success = False
                        result.message = "播放被中断"
                        result.total_elapsed_time = time.time() - start_time
                        
                        # 尝试设置cancel状态但捕获异常
                        try:
                            goal_handle.canceled()
                            self.get_logger().info("已调用goal_handle.canceled()")
                        except Exception as e:
                            self.get_logger().error(f"调用goal_handle.canceled()出错: {e}")
                            # 尝试替代方法
                            try:
                                goal_handle.abort()
                                self.get_logger().info("已调用goal_handle.abort()")
                            except Exception as e2:
                                self.get_logger().error(f"调用goal_handle.abort()也出错: {e2}")
                                
                        self.get_logger().info("【DEBUG】即将return结果")
                        return result
                    
                    # 发送播放中的反馈
                    feedback.message = f"正在播放 {fixed_audio_name}"
                    try:
                        goal_handle.publish_feedback(feedback)
                    except Exception as e:
                        self.get_logger().error(f"发送反馈时出错: {e}")
                        
                    time.sleep(0.5)
                
                # 播放线程结束
                result = AudioControl.Result()
                # 成功or中断通过stop_event判别
                if self.stop_event.is_set():
                    result.success = False
                    result.message = "播放被中断(stop_event)"
                else:
                    result.success = True
                    result.message = f"完成播放: {fixed_audio_name}"
                result.total_elapsed_time = time.time() - start_time
                
                # 尝试调用succeed，但捕获异常
                try:
                    goal_handle.succeed()
                    self.get_logger().info("已调用goal_handle.succeed()")
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                    
                self.get_logger().info("【DEBUG】即将return结果")
                return result

            elif audio_task_type == 1:
                """暂停的音频任务类型1"""
                self.get_logger().info("收到Action停止任务(主动)，设置停止音频信号。")
                self.stop_event.set()
                with self.player_lock:
                    if self.player_thread and self.player_thread.is_alive():
                        self.player_thread.join(timeout=2)
                result = AudioControl.Result()
                result.success = True
                result.message = "播放中断/已停止"
                result.total_elapsed_time = time.time() - start_time
                
                # 尝试调用succeed，但捕获异常
                try:
                    goal_handle.succeed()
                    self.get_logger().info("已调用goal_handle.succeed()")
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                    
                self.get_logger().info("【DEBUG】即将return结果")
                return result

            else:
                """不支持的音频任务类型"""
                self.get_logger().info(f"收到非0/1的 audio_task_type: {audio_task_type}")
                result = AudioControl.Result()
                result.success = False
                result.message = f"收到不支持的任务类型: {audio_task_type}"
                result.total_elapsed_time = time.time() - start_time
                
                # 尝试调用succeed，但捕获异常
                try:
                    goal_handle.succeed()
                    self.get_logger().info("已调用goal_handle.succeed()")
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                    
                self.get_logger().info("【DEBUG】即将return结果")
                return result
                
        finally:  # 【新增】确保无论如何都重置action状态
            self.action_playing = False
            self.get_logger().info("重置action_playing=False，允许topic播放")

    def _play_audio_thread(self, audio_path):
        """topic回调函数 和 action服务中调用的函数，这个函数是用来播放指定路径的音频的，同时这个音频播放也可以被中断"""
        self.get_logger().info(f"DEBUG: stop_event.is_set()={self.stop_event.is_set()}")
        pygame_initialized = False
        try:
            req = Bool()
            self.cli = self.create_publisher(Bool, 'sound_data', 3)
            """# 延迟逻辑开始
            # base_name = os.path.basename(audio_path)
            # if base_name == "qjj-2.mp3":
            #     self.get_logger().info("检测到是qjj，将延迟0.4秒再播放")
            #     time.sleep(0.4)
            # elif base_name == "sdn.mp3":
            #     self.get_logger().info("检测到是sdn，将延迟1秒再播放")
            #     time.sleep(1)"""
            pygame.init()
            pygame.mixer.init()
            pygame_initialized = True
            pygame.mixer.music.load(audio_path)            
            req.data = True
            self.cli.publish(req)
            pygame.mixer.music.play()
            self.get_logger().info(f"开始播放: {os.path.basename(audio_path)}")
            while pygame.mixer.music.get_busy():
                if self.stop_event.is_set():
                    self.get_logger().info("stop_event已被置位，立即stop音乐")
                    pygame.mixer.music.stop()
                    self.get_logger().info("音频被打断")
                    break
                time.sleep(0.1)
            req.data = False
            self.cli.publish(req)
            self.get_logger().info("音频播放完成或被中断")
        except Exception as e:
            req.data = False
            self.cli.publish(req)
            self.get_logger().error(f"播放失败: {e}")
        finally:
        # 释放 pygame 资源
            self._cleanup_pygame(pygame_initialized)
    def _cleanup_pygame(self, initialized=True):
        """释放 pygame 资源"""
        if initialized:
            try:
                pygame.mixer.music.unload()  # 卸载音乐（如果支持）
            except:
                pass  # 某些版本可能不支持 unload 方法
                
            try:
                pygame.mixer.quit()  # 关闭混音器
                pygame.quit()  # 关闭 pygame
                self.get_logger().info("pygame 资源已释放")
            except Exception as e:
                self.get_logger().error(f"释放 pygame 资源时出错: {e}")
def main(args=None):
    rclpy.init(args=args)
    node = AudioPlayerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("主程序收到KeyboardInterrupt，准备退出。")
    finally:
        if node.player_thread and node.player_thread.is_alive():
            node.get_logger().info("main退出：发现有线程未结束，stop.")
            node.stop_event.set()
            node.player_thread.join(timeout=2)
        pygame.mixer.quit()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

#s 426
#n 427
