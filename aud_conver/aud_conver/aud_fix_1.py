#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
import threading
import os
import time
import pygame
import rclpy.action
import csv
import pandas as pd

from ymrobot_msgs.action import AudioControl
from .client_modules.db_tts_websocket import dbsentence2mp3

class AudioPlayerNode(Node):
    def __init__(self):
        super().__init__('audio_player_node')

        # 配置文件路径
        self.csv_file_path = '/home/ymrobot/ros2_ws_guidance/file.csv'  # CSV文件路径
        self.audio_dir = '/home/ymrobot/ymzz_into'  # 音频文件基础路径
        
        # 确保音频目录存在
        os.makedirs(self.audio_dir, exist_ok=True)
        
        # 加载音频映射
        self.audio_mapping = self._load_audio_mapping()
        if not self.audio_mapping:
            self.get_logger().warn(f"无法加载音频映射文件，将在首次使用时创建: {self.csv_file_path}")
        else:
            self.get_logger().info(f"成功加载 {len(self.audio_mapping)} 个音频映射")
            # 打印前几个映射示例
            for i, (name, audio_id) in enumerate(list(self.audio_mapping.items())[:5]):
                self.get_logger().info(f"音频映射示例 {i+1}: '{name}' -> ID:{audio_id}")

        self.player_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.player_thread = None
        self.current_audio = None
        
        # 添加CSV写入锁，确保线程安全
        self.csv_lock = threading.Lock()

        self._action_server = ActionServer(
            self,
            AudioControl,
            'audio_control_action',
            self.execute_callback,
            callback_group=ReentrantCallbackGroup(),
            cancel_callback=self.on_cancel_callback
        )

        self.get_logger().info('AudioPlayerNode 已启动。')
        self.get_logger().info('支持的音频任务类型:')
        self.get_logger().info('  0: 播放固定音频')
        self.get_logger().info('  1: 合成音频')
        self.get_logger().info('  2: 删除固定音频')

    def _load_audio_mapping(self):
        """从CSV文件加载音频名称到ID的映射"""
        audio_mapping = {}
        
        if not os.path.exists(self.csv_file_path):
            self.get_logger().warn(f"CSV文件不存在，将在首次使用时创建: {self.csv_file_path}")
            return audio_mapping
        
        try:
            # 使用pandas读取CSV文件，这样可以更好地处理各种格式
            df = pd.read_csv(self.csv_file_path)
            
            # 检查必需的列
            if 'audio_id' not in df.columns or 'audio_name' not in df.columns:
                self.get_logger().error("CSV文件必须包含 'audio_id' 和 'audio_name' 列")
                return audio_mapping
            
            # 创建映射字典
            for _, row in df.iterrows():
                audio_id = str(row['audio_id']).strip()
                audio_name = str(row['audio_name']).strip()
                
                if audio_name and audio_id:
                    audio_mapping[audio_name] = audio_id
                    
            self.get_logger().info(f"从CSV加载了 {len(audio_mapping)} 个音频映射")
            
        except Exception as e:
            self.get_logger().error(f"读取CSV文件时出错: {e}")
            
            # 备用方案：使用标准csv库
            try:
                with open(self.csv_file_path, 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        audio_id = str(row.get('audio_id', '')).strip()
                        audio_name = str(row.get('audio_name', '')).strip()
                        
                        if audio_name and audio_id:
                            audio_mapping[audio_name] = audio_id
                            
                self.get_logger().info(f"使用备用方法从CSV加载了 {len(audio_mapping)} 个音频映射")
                
            except Exception as e2:
                self.get_logger().error(f"使用备用方法读取CSV文件也失败: {e2}")
        
        return audio_mapping

    def _get_next_audio_id(self):
        """获取下一个可用的音频ID"""
        with self.csv_lock:
            if not self.audio_mapping:
                return "0"
            
            # 获取当前最大的ID并加1
            try:
                max_id = max(int(audio_id) for audio_id in self.audio_mapping.values() if audio_id.isdigit())
                return str(max_id + 1)
            except ValueError:
                # 如果没有数字ID，从0开始
                return "0"

    def _add_audio_to_csv(self, audio_name, audio_id):
        """将新的音频映射添加到CSV文件中"""
        with self.csv_lock:
            try:
                # 检查CSV文件是否存在，如果不存在则创建
                if not os.path.exists(self.csv_file_path):
                    # 创建新的CSV文件
                    df = pd.DataFrame(columns=['audio_id', 'audio_name'])
                    df.to_csv(self.csv_file_path, index=False)
                    self.get_logger().info(f"创建新的CSV文件: {self.csv_file_path}")
                
                # 读取现有数据
                df = pd.read_csv(self.csv_file_path)
                
                # 检查音频名称是否已存在
                if audio_name in df['audio_name'].values:
                    self.get_logger().warning(f"音频名称 '{audio_name}' 已存在，跳过添加")
                    return False
                
                # 添加新行
                new_row = pd.DataFrame({'audio_id': [audio_id], 'audio_name': [audio_name]})
                df = pd.concat([df, new_row], ignore_index=True)
                
                # 保存到CSV
                df.to_csv(self.csv_file_path, index=False)
                
                # 更新内存中的映射
                self.audio_mapping[audio_name] = audio_id
                
                self.get_logger().info(f"成功添加音频映射到CSV: '{audio_name}' -> ID:{audio_id}")
                return True
                
            except Exception as e:
                self.get_logger().error(f"添加音频映射到CSV时出错: {e}")
                return False

    def _remove_audio_from_csv(self, audio_name):
        """从CSV文件中删除音频映射，返回(success, audio_id)"""
        with self.csv_lock:
            try:
                # 检查CSV文件是否存在
                if not os.path.exists(self.csv_file_path):
                    self.get_logger().error(f"CSV文件不存在: {self.csv_file_path}")
                    return False, None
                
                # 读取现有数据
                df = pd.read_csv(self.csv_file_path)
                
                # 检查音频名称是否存在
                if audio_name not in df['audio_name'].values:
                    self.get_logger().error(f"音频名称 '{audio_name}' 不存在于CSV文件中")
                    return False, None
                
                # 获取要删除的音频ID
                audio_id = str(df[df['audio_name'] == audio_name]['audio_id'].iloc[0])
                
                # 删除行
                df = df[df['audio_name'] != audio_name]
                
                # 保存更新后的CSV
                df.to_csv(self.csv_file_path, index=False)
                
                # 更新内存中的映射
                if audio_name in self.audio_mapping:
                    del self.audio_mapping[audio_name]
                
                self.get_logger().info(f"成功从CSV删除音频映射: '{audio_name}' (ID: {audio_id})")
                return True, audio_id
                
            except Exception as e:
                self.get_logger().error(f"从CSV删除音频映射时出错: {e}")
                return False, None
    
    def _delete_audio_file(self, audio_name, goal_handle):
        """删除音频文件和CSV记录"""
        start_time = time.time()
        
        try:
            # 验证输入参数
            if not audio_name.strip():
                return self._create_result(False, "要删除的音频名称不能为空", start_time)
            
            self.get_logger().info(f"开始删除音频: '{audio_name}'")
            
            # 检查音频是否存在于CSV中
            if audio_name not in self.audio_mapping:
                msg = f"音频 '{audio_name}' 不存在于音频列表中"
                self.get_logger().error(msg)
                return self._create_result(False, msg, start_time)
            
            # 获取音频ID
            audio_id = self.audio_mapping[audio_name]
            
            # 构建音频文件路径
            audio_filename = f"{audio_id}.mp3"
            audio_path = os.path.join(self.audio_dir, audio_filename)
            
            self.get_logger().info(f"准备删除:")
            self.get_logger().info(f"  音频名称: '{audio_name}'")
            self.get_logger().info(f"  音频ID: {audio_id}")
            self.get_logger().info(f"  文件路径: {audio_path}")
            
            # 发送反馈
            feedback = AudioControl.Feedback()
            feedback.message = f"正在删除音频: '{audio_name}'"
            feedback.total_elapsed_time = time.time() - start_time
            try:
                goal_handle.publish_feedback(feedback)
            except Exception as e:
                self.get_logger().error(f"发送反馈时出错: {e}")
            
            # 检查文件是否存在
            file_exists = os.path.exists(audio_path)
            self.get_logger().info(f"音频文件是否存在: {file_exists} - {audio_path}")
            
            # 从CSV删除记录
            csv_success, csv_audio_id = self._remove_audio_from_csv(audio_name)
            
            if not csv_success:
                return self._create_result(False, f"从CSV删除音频记录失败: '{audio_name}'", start_time)
            
            # 删除音频文件（如果存在）
            if file_exists:
                try:
                    os.remove(audio_path)
                    self.get_logger().info(f"成功删除音频文件: {audio_path}")
                    file_deleted = True
                except Exception as e:
                    self.get_logger().error(f"删除音频文件失败: {e}")
                    file_deleted = False
            else:
                self.get_logger().warning(f"音频文件不存在，跳过文件删除: {audio_path}")
                file_deleted = True  # 文件本来就不存在，认为删除成功
            
            # 检查当前播放的音频
            if self.current_audio == audio_name:
                self.get_logger().info(f"当前正在播放要删除的音频，停止播放")
                self.stop_event.set()
                with self.player_lock:
                    if self.player_thread and self.player_thread.is_alive():
                        self.player_thread.join(timeout=2)
            
            # 发送完成反馈
            feedback.message = f"音频删除完成: '{audio_name}'"
            feedback.total_elapsed_time = time.time() - start_time
            try:
                goal_handle.publish_feedback(feedback)
            except Exception as e:
                self.get_logger().error(f"发送反馈时出错: {e}")
            
            # 生成结果消息
            if file_deleted:
                message = f"成功删除音频: '{audio_name}' (ID: {audio_id})"
                if not file_exists:
                    message += " (音频文件未找到，仅删除了CSV记录)"
            else:
                message = f"删除音频记录成功，但文件删除失败: '{audio_name}' (ID: {audio_id})"
            
            self.get_logger().info(f"音频删除操作完成: {message}")
            return self._create_result(True, message, start_time)
                
        except Exception as e:
            self.get_logger().error(f"删除音频时出现异常: {e}")
            return self._create_result(False, f"删除音频异常: {str(e)}", start_time)

    def _synthesize_audio(self, synthetic_text, audio_name, goal_handle):
        """语音合成功能"""
        start_time = time.time()
        
        try:
            # 验证输入参数
            if not synthetic_text.strip():
                return self._create_result(False, "合成音频内容不能为空", start_time)
            
            if not audio_name.strip():
                return self._create_result(False, "音频名称不能为空", start_time)
            
            # 检查音频名称是否已存在
            if audio_name in self.audio_mapping:
                msg = f"音频名称 '{audio_name}' 已存在，请使用不同的名称"
                self.get_logger().warning(msg)
                return self._create_result(False, msg, start_time)
            
            # 获取下一个可用的音频ID
            audio_id = self._get_next_audio_id()
            
            # 构建音频文件路径
            audio_filename = f"{audio_id}.mp3"
            audio_path = os.path.join(self.audio_dir, audio_filename)
            
            self.get_logger().info(f"开始语音合成:")
            self.get_logger().info(f"  文本内容: '{synthetic_text}'")
            self.get_logger().info(f"  音频名称: '{audio_name}'")
            self.get_logger().info(f"  目标ID: {audio_id}")
            self.get_logger().info(f"  音频路径: {audio_path}")
            
            # 发送反馈
            feedback = AudioControl.Feedback()
            feedback.message = f"正在合成语音: '{audio_name}'"
            feedback.total_elapsed_time = time.time() - start_time
            try:
                goal_handle.publish_feedback(feedback)
            except Exception as e:
                self.get_logger().error(f"发送反馈时出错: {e}")
            
            # 调用语音合成函数
            # dbsentence2mp3期望的是不带扩展名的路径
            target_path_without_ext = audio_path[:-4] if audio_path.endswith('.mp3') else audio_path
            synthesis_result = dbsentence2mp3(synthetic_text, target_path_without_ext)
            
            if synthesis_result is None:
                # 合成失败
                self.get_logger().error(f"语音合成失败: {audio_name}")
                return self._create_result(False, f"语音合成失败: '{audio_name}'", start_time)
            
            # 检查生成的文件是否存在
            if not os.path.exists(synthesis_result):
                self.get_logger().error(f"合成的音频文件不存在: {synthesis_result}")
                return self._create_result(False, f"合成的音频文件不存在: {synthesis_result}", start_time)
            
            # 如果生成的文件路径与期望的不同，移动文件
            if synthesis_result != audio_path:
                try:
                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
                    os.rename(synthesis_result, audio_path)
                    self.get_logger().info(f"移动音频文件: {synthesis_result} -> {audio_path}")
                except Exception as e:
                    self.get_logger().error(f"移动音频文件失败: {e}")
                    # 如果移动失败，使用原路径
                    audio_path = synthesis_result
            
            # 发送合成完成反馈
            feedback.message = f"语音合成完成，正在保存到CSV: '{audio_name}'"
            feedback.total_elapsed_time = time.time() - start_time
            try:
                goal_handle.publish_feedback(feedback)
            except Exception as e:
                self.get_logger().error(f"发送反馈时出错: {e}")
            
            # 合成成功，添加到CSV
            if self._add_audio_to_csv(audio_name, audio_id):
                self.get_logger().info(f"语音合成并保存成功:")
                self.get_logger().info(f"  音频名称: '{audio_name}'")
                self.get_logger().info(f"  音频ID: {audio_id}")
                self.get_logger().info(f"  文件路径: {audio_path}")
                return self._create_result(True, f"语音合成成功: '{audio_name}' (ID: {audio_id})", start_time)
            else:
                # 这种情况理论上不应该发生，因为我们已经提前检查了
                # 但如果发生了，需要清理生成的音频文件
                self.get_logger().error(f"语音合成成功但添加到CSV失败: {audio_name}")
                # 清理生成的音频文件
                try:
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                        self.get_logger().info(f"清理生成的音频文件: {audio_path}")
                except Exception as e:
                    self.get_logger().error(f"清理音频文件失败: {e}")
                
                return self._create_result(False, f"语音合成成功但保存失败，可能是并发操作导致音频名称冲突: '{audio_name}'", start_time)
                
        except Exception as e:
            self.get_logger().error(f"语音合成异常: {e}")
            return self._create_result(False, f"语音合成异常: {str(e)}", start_time)

    def _create_result(self, success, message, start_time):
        """创建Action结果"""
        result = AudioControl.Result()
        result.success = success
        result.message = message
        result.total_elapsed_time = time.time() - start_time
        return result

    def _get_audio_id_by_name(self, audio_name):
        """根据音频名称获取音频ID"""
        # 去除首尾空格
        audio_name = audio_name.strip()
        
        # 精确匹配
        if audio_name in self.audio_mapping:
            return self.audio_mapping[audio_name]
        
        # 如果精确匹配失败，尝试模糊匹配
        for name, audio_id in self.audio_mapping.items():
            if audio_name.lower() in name.lower() or name.lower() in audio_name.lower():
                self.get_logger().info(f"使用模糊匹配: '{audio_name}' -> '{name}' (ID: {audio_id})")
                return audio_id
        
        return None

    def on_cancel_callback(self, goal_handle):
        self.get_logger().info("Action收到cancel请求，立即停止音频(stop_event set)")
        self.stop_event.set()
        return rclpy.action.CancelResponse.ACCEPT

    def execute_callback(self, goal_handle):
        self.get_logger().info("【DEBUG】execute_callback: 收到新Goal!")
        start_time = time.time()
        
        req = goal_handle.request
        audio_task_type = req.audio_task_type

        # 打印接收到的参数
        self.get_logger().info(f"任务类型: {audio_task_type}")
        if hasattr(req, 'fixed_audio_name'):
            self.get_logger().info(f"音频名称: '{req.fixed_audio_name}'")
        if hasattr(req, 'synthetic_audio_txt'):
            self.get_logger().info(f"合成音频内容: '{req.synthetic_audio_txt}'")
        if hasattr(req, 'synthetic_audio_title'):
            self.get_logger().info(f"合成音频标题: '{req.synthetic_audio_title}'")
        if hasattr(req, 'delete_fixed_audio'):
            self.get_logger().info(f"要删除的音频: '{req.delete_fixed_audio}'")

        if audio_task_type == 0:  # 播放固定音频
            if not hasattr(req, 'fixed_audio_name'):
                result = self._create_result(False, "缺少required参数: fixed_audio_name", start_time)
                try:
                    goal_handle.succeed()
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                return result
                
            audio_name_req = req.fixed_audio_name.strip()
            self.get_logger().info(f"收到播放请求，音频名称: '{audio_name_req}'")
            
            # 从CSV中查找音频ID
            audio_id = self._get_audio_id_by_name(audio_name_req)
            
            if audio_id is None:
                msg = f"未找到音频名称 '{audio_name_req}' 对应的ID"
                self.get_logger().error(msg)
                result = self._create_result(False, msg, start_time)
                try:
                    goal_handle.succeed()
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                return result

            # 构建音频文件路径
            audio_filename = f"{audio_id}.mp3"
            audio_path = os.path.join(self.audio_dir, audio_filename)
            
            self.get_logger().info(f"音频名称 '{audio_name_req}' -> ID: {audio_id} -> 路径: {audio_path}")

            if not os.path.exists(audio_path):
                msg = f"音频文件不存在: {audio_path}"
                self.get_logger().error(msg)
                result = self._create_result(False, msg, start_time)
                try:
                    goal_handle.succeed()
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                return result

            # 停止当前播放并开始新的播放
            with self.player_lock:
                if self.player_thread and self.player_thread.is_alive():
                    self.stop_event.set()
                    self.player_thread.join(timeout=2)
                self.stop_event.clear()
                self.player_thread = threading.Thread(
                    target=self._play_audio_thread, 
                    args=(audio_path,), 
                    daemon=True
                )
                self.player_thread.start()
                self.current_audio = audio_name_req

            self.get_logger().info(f"[Action] 开始播放音频: {audio_name_req} (ID: {audio_id})")

            # 发送反馈并等待播放完成
            feedback = AudioControl.Feedback()
            while self.player_thread.is_alive():
                if self.stop_event.is_set():
                    self.get_logger().info("检测到stop_event，停止音频播放")
                    feedback.message = f"播放被中断: {audio_name_req}"
                    feedback.total_elapsed_time = time.time() - start_time
                    
                    try:
                        goal_handle.publish_feedback(feedback)
                    except Exception as e:
                        self.get_logger().error(f"发送反馈时出错: {e}")
                    
                    pygame.mixer.music.stop()
                    self.player_thread.join(timeout=2)
                    
                    if self.player_thread.is_alive():
                        self.get_logger().warning("取消时播放线程未及时退出！")
                        
                    result = self._create_result(False, f"播放被中断: {audio_name_req}", start_time)
                    try:
                        goal_handle.canceled()
                    except Exception as e:
                        self.get_logger().error(f"调用goal_handle.canceled()出错: {e}")
                        try:
                            goal_handle.abort()
                        except Exception as e2:
                            self.get_logger().error(f"调用goal_handle.abort()也出错: {e2}")
                    return result
                
                feedback.message = f"正在播放: {audio_name_req} (ID: {audio_id})"
                feedback.total_elapsed_time = time.time() - start_time
                try:
                    goal_handle.publish_feedback(feedback)
                except Exception as e:
                    self.get_logger().error(f"发送反馈时出错: {e}")
                    
                time.sleep(0.5)
            
            # 播放完成
            if self.stop_event.is_set():
                result = self._create_result(False, f"播放被中断: {audio_name_req}", start_time)
            else:
                result = self._create_result(True, f"完成播放: {audio_name_req} (ID: {audio_id})", start_time)
            
            try:
                goal_handle.succeed()
            except Exception as e:
                self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
            return result

        elif audio_task_type == 1:  # 合成音频
            # 检查必需参数
            missing_params = []
            if not hasattr(req, 'synthetic_audio_txt'):
                missing_params.append('synthetic_audio_txt')
            if not hasattr(req, 'synthetic_audio_title'):
                missing_params.append('synthetic_audio_title')
            
            if missing_params:
                msg = f"缺少必需参数: {', '.join(missing_params)}"
                self.get_logger().error(msg)
                result = self._create_result(False, msg, start_time)
                try:
                    goal_handle.succeed()
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                return result
            
            synthetic_audio = req.synthetic_audio_txt.strip()
            audio_name = req.synthetic_audio_title.strip()
            
            self.get_logger().info(f"收到语音合成请求:")
            self.get_logger().info(f"  音频内容: '{synthetic_audio}'")
            self.get_logger().info(f"  音频名称: '{audio_name}'")
            
            # 执行语音合成
            result = self._synthesize_audio(synthetic_audio, audio_name, goal_handle)
            
            try:
                goal_handle.succeed()
            except Exception as e:
                self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
            return result

        elif audio_task_type == 2:  # 删除固定音频
            # 检查必需参数
            if not hasattr(req, 'delete_fixed_audio'):
                msg = "缺少必需参数: delete_fixed_audio"
                self.get_logger().error(msg)
                result = self._create_result(False, msg, start_time)
                try:
                    goal_handle.succeed()
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                return result
            
            audio_name_to_delete = req.delete_fixed_audio.strip()
            
            self.get_logger().info(f"收到删除音频请求:")
            self.get_logger().info(f"  要删除的音频: '{audio_name_to_delete}'")
            
            # 执行删除操作
            result = self._delete_audio_file(audio_name_to_delete, goal_handle)
            
            try:
                goal_handle.succeed()
            except Exception as e:
                self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
            return result

        else:
            self.get_logger().error(f"不支持的任务类型: {audio_task_type}")
            result = self._create_result(False, f"不支持的任务类型: {audio_task_type}", start_time)
            try:
                goal_handle.succeed()
            except Exception as e:
                self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
            return result

    def _play_audio_thread(self, audio_path):
        """音频播放线程"""
        pygame_initialized = False
        try:
            pygame.init()
            pygame.mixer.init()
            pygame_initialized = True
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            self.get_logger().info(f"开始播放: {os.path.basename(audio_path)}")
            
            while pygame.mixer.music.get_busy():
                if self.stop_event.is_set():
                    self.get_logger().info("stop_event已被置位，立即停止音乐")
                    pygame.mixer.music.stop()
                    self.get_logger().info("音频被打断")
                    break
                time.sleep(0.1)
                
            self.get_logger().info("音频播放完成")
        except Exception as e:
            self.get_logger().error(f"播放失败: {e}")
        finally:
            self._cleanup_pygame(pygame_initialized)
    
    def _cleanup_pygame(self, initialized=True):
        """释放pygame资源"""
        if initialized:
            try:
                pygame.mixer.music.unload()
            except:
                pass
                
            try:
                pygame.mixer.quit()
                pygame.quit()
                self.get_logger().info("pygame 资源已释放")
            except Exception as e:
                self.get_logger().error(f"释放 pygame 资源时出错: {e}")

    def reload_audio_mapping(self):
        """重新加载音频映射（可用于动态更新）"""
        self.get_logger().info("重新加载音频映射...")
        self.audio_mapping = self._load_audio_mapping()
        self.get_logger().info(f"重新加载完成，当前有 {len(self.audio_mapping)} 个音频映射")

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