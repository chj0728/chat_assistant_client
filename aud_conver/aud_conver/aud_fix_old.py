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
from std_msgs.msg import Int32, String, Bool  
from ymrobot_msgs.action import AudioControl

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
        self.action_end_time = 0  # 记录action结束时间
        self.topic_cooldown = 2.0  # topic冷却时间（秒）
        self.get_logger().info("已订阅 /play_fixed_audio topic (Int32)，接收到消息将尝试播放 ryr.mp3")
        self.audio_dir = '/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver/fix_aud_male'
        os.makedirs(self.audio_dir, exist_ok=True)
        self.audio_files = self._scan_audio_files(self.audio_dir)
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

        
        self.get_logger().info('AudioPlayerNode 已启动。')

    def on_cancel_callback(self, goal_handle):
        self.get_logger().info("Action收到cancel请求，立即停止音频(stop_event set)")
        self.stop_event.set()   # 只需设置事件，主线程会检测后调用stop
        # 无需Join! 提前join可能死锁或阻慢cancel响应
        return rclpy.action.CancelResponse.ACCEPT
    def topic_play_callback(self, msg):
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

        # 若不在播放，直接用线程播放 ryr.mp3
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

    def _scan_audio_files(self, audio_dir):
        if not os.path.isdir(audio_dir):
            return []
        return [f for f in os.listdir(audio_dir) if f.lower().endswith('.mp3')]

        
    def execute_callback(self, goal_handle):
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
            fixed_audio_name_req = req.fixed_audio_name.strip()
            fixed_audio_mapping = {
                "0": "xiaoxue",
                "1": "seadata",
                "2": "tf_ls",
                "3": "dayi",
                "4": "zongjiao",
                "5": "last",
            }
            if fixed_audio_name_req in fixed_audio_mapping:
                fixed_audio_name = fixed_audio_mapping[fixed_audio_name_req]
            else:
                self.get_logger().error(f"未定义的fixed_audio_name: {fixed_audio_name_req}")
                result = AudioControl.Result()
                result.success = False
                result.message = f"未定义的fixed_audio_name: {fixed_audio_name_req}"
                result.total_elapsed_time = time.time() - start_time
                
                # 尝试调用succeed，但捕获异常
                try:
                    goal_handle.succeed()
                    self.get_logger().info("已调用goal_handle.succeed()")
                except Exception as e:
                    self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                    
                self.get_logger().info("【DEBUG】即将return结果")
                return result

            if not fixed_audio_name.endswith('.mp3'):
                fixed_audio_name += '.mp3'
            audio_path = os.path.join(self.audio_dir, fixed_audio_name)

            if audio_task_type == 0:
                if not os.path.exists(audio_path):
                    msg = f"音频 {fixed_audio_name} 不存在"
                    self.get_logger().error(msg)
                    result = AudioControl.Result()
                    result.success = False
                    result.message = msg
                    result.total_elapsed_time = time.time() - start_time
                    
                    # 尝试调用succeed，但捕获异常
                    try:
                        goal_handle.succeed()
                        self.get_logger().info("已调用goal_handle.succeed()")
                    except Exception as e:
                        self.get_logger().error(f"调用goal_handle.succeed()出错: {e}")
                        
                    self.get_logger().info("【DEBUG】即将return结果")
                    return result

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
                while self.player_thread.is_alive():
                    # 直接检查stop_event，这是最可靠的取消方法
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
        self.get_logger().info(f"DEBUG: stop_event.is_set()={self.stop_event.is_set()}")
        pygame_initialized = False
        try:
            
            # 延迟逻辑开始
            # base_name = os.path.basename(audio_path)
            # if base_name == "qjj-2.mp3":
            #     self.get_logger().info("检测到是qjj，将延迟0.4秒再播放")
            #     time.sleep(0.4)
            # elif base_name == "sdn.mp3":
            #     self.get_logger().info("检测到是sdn，将延迟1秒再播放")
            #     time.sleep(1)
            pygame.init()
            pygame.mixer.init()
            pygame_initialized = True
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            self.get_logger().info(f"开始播放: {os.path.basename(audio_path)}")
            while pygame.mixer.music.get_busy():
                if self.stop_event.is_set():
                    self.get_logger().info("stop_event已被置位，立即stop音乐")
                    pygame.mixer.music.stop()
                    self.get_logger().info("音频被打断")
                    break
                time.sleep(0.1)
            self.get_logger().info("音频播放完成")
        except Exception as e:
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
