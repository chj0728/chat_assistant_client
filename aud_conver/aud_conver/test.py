# import csv
# import os
# import sys
# import time
# import datetime

# def write_csv():
#     # 1. 准备数据 - 将数据放入列表中
#     a = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     b = 2
#     c = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     d = 4
    
#     # 2. 获取当前工作目录和绝对路径
#     current_dir = os.getcwd()
#     file_name = "output.csv"
#     abs_path = os.path.join(current_dir, file_name)
    
#     print(f"当前工作目录: {current_dir}")
#     print(f"文件将写入到: {abs_path}")
    
#     try:
#         # 3. 尝试写入文件
#         print("尝试打开文件...")
#         with open(file_name, 'a', newline='', encoding='utf-8') as f:
#             print("文件已成功打开")
#             writer = csv.writer(f)
            
            
#             # 将数据放入列表中写入
#             print("开始写入一行数据...")
#             row_data = [a, b, c, d]  # 将所有数据放入一个列表
#             writer.writerow(row_data)  # 写入一行
            
#             print(f"已写入行: {row_data}")
#             f.flush()  # 强制刷新缓冲区
#             time.sleep(0.1)  # 添加延迟确保写入完成
            
#             print("所有数据已写入")
#             f.flush()  # 最终刷新
        
#         # 4. 验证文件是否创建
#         if os.path.exists(file_name):
#             size = os.path.getsize(file_name)
#             print(f"文件已创建! 大小: {size} 字节")
            
#             # 读取文件内容验证
#             print("\n文件内容:")
#             with open(file_name, 'r', encoding='utf-8') as f:
#                 content = f.read()
#                 print(content)
#         else:
#             print("错误: 文件未创建")
            
#         return True
#     except Exception as e:
#         print(f"\n!!! 写入失败: {type(e).__name__} !!!")
#         print(f"错误详情: {str(e)}")
#         print("\n可能原因:")
#         print("1. 目录权限不足 - 尝试: sudo chown $USER .")
#         print("2. 磁盘空间不足 - 检查: df -h")
#         print("3. 文件系统只读 - 尝试: mount | grep ' / '")
#         return False

# if __name__ == "__main__":
#     print("===== CSV 写入诊断程序 =====")
#     success = True
#     for i in range(5):
#         if not write_csv():
#             success = False
#         time.sleep(5)
    
#     if success:
#         print("\nCSV文件已生成: output.csv")
#     else:
#         print("\n文件写入失败，请检查上述错误信息")
    
#     # 防止终端窗口立即关闭
#     input("\n按 Enter 键退出程序...")
# import os
# import csv
# import datetime
# import time

# def write_csv(start_time, role, sentence):
#     """
#     将数据写入CSV文件
#     :param start_time: 开始时间字符串 (格式: "%Y-%m-%d %H:%M:%S")
#     :param role: 角色标识
#     :param sentence: 句子内容
#     """
#     # 准备数据
#     data = [start_time, role, sentence]
    
#     # 获取当前工作目录和绝对路径
#     records_dir = "/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver"
#     file_name = "records.csv"
#     file_name = os.path.join(records_dir, file_name)
    
#     print(f"当前工作目录: {records_dir}")
#     print(f"文件路径: {file_name}")
    
#     try:
#         # 检查文件是否存在
#         file_exists = os.path.exists(file_name)
        
#         # 打开文件（追加模式）
#         with open(file_name, 'a', newline='', encoding='utf-8') as f:
#             writer = csv.writer(f)
            
#             # 如果是新文件，先写入表头
#             if not file_exists:
#                 print("文件不存在，创建新文件并添加表头")
#                 header = ["StartTime", "Role", "Sentence"]
#                 writer.writerow(header)
#                 print(f"已写入表头: {header}")
            
#             # 写入数据行
#             print(f"准备写入数据: {data}")
#             writer.writerow(data)
#             f.flush()  # 确保数据立即写入磁盘
#             print("数据已成功写入")
        
#         # 验证写入结果
#         if os.path.exists(file_name):
#             size = os.path.getsize(file_name)
#             print(f"文件验证成功! 大小: {size} 字节")
            
#             # 打印文件最后几行内容
#             print("\n文件最新内容:")
#             with open(file_name, 'r', encoding='utf-8') as f:
#                 lines = f.readlines()
#                 # 显示最后5行内容
#                 for line in lines[-5:]:
#                     print(line.strip())
                    
#             return True
#         else:
#             print("错误: 文件未创建")
#             return False
            
#     except Exception as e:
#         print(f"\n!!! 写入失败: {type(e).__name__} !!!")
#         print(f"错误详情: {str(e)}")
#         print("\n可能原因:")
#         print("1. 目录权限不足 - 尝试: sudo chown $USER .")
#         print("2. 磁盘空间不足 - 检查: df -h")
#         print("3. 文件系统只读 - 尝试: mount | grep ' / '")
#         print("4. 文件被其他进程占用")
#         return False
    
# import csv
# import os
# import shutil

# def delete_rows_by_first_column(csv_file, target_value, output_file=None, has_header=False):
#     """
#     根据CSV文件第一列的值删除整行
    
#     参数:
#     csv_file -- 输入的CSV文件路径
#     target_value -- 要匹配的第一列的值
#     output_file -- 输出文件路径(可选)，默认为覆盖原文件
#     has_header -- 是否包含标题行(可选)，默认为False
#     """
#     # 设置默认输出文件为输入文件
#     if output_file is None:
#         output_file = csv_file
#         temp_file = csv_file + ".tmp"
#     else:
#         temp_file = output_file + ".tmp"
    
#     rows_deleted = 0
#     total_rows = 0
    
#     try:
#         with open(csv_file, 'r', newline='', encoding='utf-8') as infile, \
#              open(temp_file, 'w', newline='', encoding='utf-8') as outfile:
            
#             reader = csv.reader(infile)
#             writer = csv.writer(outfile)
            
#             # 处理标题行
#             if has_header:
#                 header = next(reader)
#                 writer.writerow(header)
#                 total_rows += 1
            
#             # 处理数据行
#             for row in reader:
#                 total_rows += 1
#                 if not row:  # 跳过空行
#                     continue
                    
#                 # 检查第一列是否匹配目标值
#                 if str(row[0]).strip() == str(target_value).strip():
#                     rows_deleted += 1
#                     continue  # 跳过匹配的行
                
#                 writer.writerow(row)
        
#         # 如果是覆盖原文件，则替换文件
#         if output_file == csv_file:
#             shutil.move(temp_file, csv_file)
#         else:
#             shutil.move(temp_file, output_file)
            
#         print(f"处理完成! 总行数: {total_rows}, 删除行数: {rows_deleted}")
#         return True
    
#     except Exception as e:
#         print(f"处理失败: {str(e)}")
#         # 清理临时文件
#         if os.path.exists(temp_file):
#             os.remove(temp_file)
#         return False

# # 使用示例
# if __name__ == "__main__":
#     # 生成当前时间戳
#     timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
#     # 第一次调用 - 创建文件
#     print("\n===== 第一次调用 =====")
#     write_csv(timestamp, "user", "你好小雪")
    
#     # 等待1秒
#     time.sleep(1)
    
#     # 第二次调用 - 追加数据
#     print("\n===== 第二次调用 =====")
#     timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     write_csv(timestamp, "system", "你好")

# # # 使用示例
# # if __name__ == "__main__":
# #     # 示例1: 覆盖原文件
# #     # delete_rows_by_first_column("data.csv", "1001")
    
# #     # 示例2: 保存到新文件
# #     # delete_rows_by_first_column("data.csv", "1002", "new_data.csv")
    
# #     # 示例3: 包含标题行
# #     # delete_rows_by_first_column("data.csv", "1003", has_header=True)
    
# #     # 从用户获取输入
# #     input_file = input("请输入CSV文件路径: ")
# #     target_value = input("请输入要删除的第一列的值: ")
# #     has_header = input("文件是否有标题行? (y/n): ").lower() == 'y'
    
# #     # 是否保存到新文件
# #     save_new = input("保存到新文件? (y/n): ").lower() == 'y'
# #     output_file = None
# #     if save_new:
# #         output_file = input("请输入新文件路径: ")
    
# #     # 执行删除操作
# #     delete_rows_by_first_column(input_file, target_value, output_file, has_header)
# """ 原语音转文字的合成音频的保存至.csv文件的内容
#  # try:
#                                 # 检查文件是否存在
#                                 #     file_exists = os.path.exists(file_name)
                                    
#                                 #     # 打开文件（追加模式）
#                                 #     with open(file_name, 'a', newline='', encoding='utf-8') as f:
#                                 #         writer = csv.writer(f)
                                        
#                                 #         # 如果是新文件，先写入表头
#                                 #         if not file_exists:
#                                 #             print("音频文件不存在，创建新文件并添加表头")
#                                 #             header = ["synthetic_audio_title", "timbre", "synthetic_audio_txt"]
#                                 #             writer.writerow(header)

#                                 #         writer.writerow(data)
#                                 #         f.flush()  # 确保数据立即写入磁盘
#                                 #         print("数据已成功写入")
                                    
#                                 #     # # 验证写入结果
#                                 #     # if os.path.exists(file_name):
#                                 #     #     size = os.path.getsize(file_name)
#                                 #     #     print(f"文件验证成功! 大小: {size} 字节")
                                        
#                                 #     #     # 打印文件最后几行内容
#                                 #     #     print("\n文件最新内容:")
#                                 #     #     with open(file_name, 'r', encoding='utf-8') as f:
#                                 #     #         lines = f.readlines()
#                                 #     #         # 显示最后5行内容
#                                 #     #         for line in lines[-5:]:
#                                 #     #             print(line.strip())
                                                
#                                 #     #     return True
#                                 #     # else:
#                                 #     #     print("错误: 文件未创建")
#                                 #     #     return False
                                        
#                                 # except Exception as e:
#                                 #     print(f"\n!!! 写入失败: {type(e).__name__} !!!")
#                                 #     print(f"错误详情: {str(e)}")
#                                 #     print("\n可能原因:")
#                                 #     print("1. 目录权限不足 - 尝试: sudo chown $USER .")
#                                 #     print("2. 磁盘空间不足 - 检查: df -h")
#                                 #     print("3. 文件系统只读 - 尝试: mount | grep ' / '")
#                                 #     print("4. 文件被其他进程占用")
#                                 #     return False
# """
# import pygame
# import time

# while True:
#     print("开始播放")
#     pygame.init()
#     pygame.mixer.init()
#     time.sleep(5)
#     pygame.mixer.music.load("/home/ymrobot/ros2_ws_guidance/introduction.mp3")
#     pygame.mixer.music.play()
#     while pygame.mixer.music.get_busy():
#         print("音频仍然在播放")
#         time.sleep(0.5)
#     pygame.mixer.music.stop()
#     pygame.mixer.quit()
#     print("音频资源已释放")
#     time.sleep(5)
# import rclpy
# import time
# from rclpy.node import Node
# from std_msgs.msg import Bool
# import threading

# class MyClass:
#     def __init__(self):
#         self.node = None
#         self.publisher = None
#         self.ros_thread = None
#         self.ros_ready = False
#         self.do_something()

#     def _ros_spin_thread(self):
#         rclpy.spin(self.node)

#     def init_ros(self):
#         if not rclpy.ok():
#             rclpy.init()

#         self.node = Node("my_hidden_ros_node")
#         self.publisher = self.node.create_publisher(Bool, "my_topic", 10)

#         # 启动一个线程来spin节点（不阻塞主线程）
#         self.ros_thread = threading.Thread(target=self._ros_spin_thread, daemon=True)
#         self.ros_thread.start()
#         self.ros_ready = True
#         print("ROS Node initialized.")

#     def do_something(self):
#         print("Doing something...")
        
#         # 第一次使用时初始化 ROS
#         if not self.ros_ready:
#             self.init_ros()

#         i = 0
#         while True:
#             # 发布消息
#             msg = Bool()
#             if i % 2 == 0:
#                 msg.data = False
#                 i += 1
#             else:
#                 msg.data = True
#                 i += 1
#             self.publisher.publish(msg)
#             self.node.get_logger().info(f"Published: {msg.data}")
#             time.sleep(2)

# m = MyClass()

# """

# ros2 service call /audio_control_action_srv/ ymrobot_msgs/srv/Audio "{audio_task_type : 1, timbre : "BV700_streaming", synthetic_audio_title : "问候6.0",synthetic_audio_txt : "我是一名普通的“伙夫”，今天是我第一天上班的日子，所有人都“冷漠”的看着我。"}"


# """
# def remove_all_but_last_newline(s):
#     # 找到最后一个换行符的位置
#     last_newline_index = s.rfind('\n')
    
#     # 如果没有换行符，直接返回原字符串
#     if last_newline_index == -1:
#         return s
    
#     # 分割字符串
#     before_last = s[:last_newline_index]  # 最后一个\n之前的部分
#     after_last = s[last_newline_index:]   # 最后一个\n及其之后的部分
    
#     # 删除before_last中的所有换行符，并拼接结果
#     return before_last.replace('\n', '') + after_last

# a = remove_all_but_last_newline("你好，joey！\n当你看到这封信时，我已经回来了，\n哈哈哈，没想到吧今天就是你的忌日。\n")
# print(a)

import pyaudio

mic_name_keyword = "FY-SP003"
selected_index = None

p = pyaudio.PyAudio()

# 遍历设备查找包含关键字的设备
# for i in range(p.get_device_count()):
#     info = p.get_device_info_by_index(i)
#     print(f"Index {i}: {info['name']} - Input Channels: {info['maxInputChannels']}")
#     if mic_name_keyword in info['name'] and info['maxInputChannels'] > 0:
#         selected_index = i
#         print(f"✅ Found target device at index {i}")
#         break

# if selected_index is None:
#     raise RuntimeError(f"❌ Could not find input device with name containing '{mic_name_keyword}'")

# # 使用找到的设备索引打开流
# stream = p.open(format=pyaudio.paInt16,
#                 channels=1,
#                 rate=16000,
#                 input=True,
#                 input_device_index=selected_index,
#                 frames_per_buffer=1024)
# import pyaudio
# import wave

# def find_usable_input_device():
#     p = pyaudio.PyAudio()
#     for i in range(p.get_device_count()):
#         info = p.get_device_info_by_index(i)
#         if info['maxInputChannels'] > 0:
#             try:
#                 stream = p.open(format=pyaudio.paInt16,
#                                 channels=1,
#                                 rate=int(info['defaultSampleRate']),
#                                 input=True,
#                                 input_device_index=i,
#                                 frames_per_buffer=1024)
#                 stream.close()
#                 print(f"设备可用: Index {i}, Name: {info['name']}")
#                 p.terminate()
#                 return i, int(info['defaultSampleRate'])
#             except Exception as e:
#                 print(f"设备不可用: Index {i}, Name: {info['name']}, 错误: {e}")
#     p.terminate()
#     print("没有可用的麦克风设备")
#     return None, None

# def record_audio(device_index, rate, duration=5, output_filename="output.wav"):
#     p = pyaudio.PyAudio()
#     stream = p.open(format=pyaudio.paInt16,
#                     channels=1,
#                     rate=rate,
#                     input=True,
#                     input_device_index=device_index,
#                     frames_per_buffer=1024)
#     print(f"开始录音，时长{duration}秒，设备索引: {device_index}")
#     frames = []

#     for _ in range(0, int(rate / 1024 * duration)):
#         data = stream.read(1024, exception_on_overflow=False)
#         frames.append(data)

#     print("录音结束，保存文件中...")
#     stream.stop_stream()
#     stream.close()
#     p.terminate()

#     wf = wave.open(output_filename, 'wb')
#     wf.setnchannels(1)
#     wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
#     wf.setframerate(rate)
#     wf.writeframes(b''.join(frames))
#     wf.close()
#     print(f"录音文件已保存: {output_filename}")

# if __name__ == "__main__":
#     device_index, rate = find_usable_input_device()
#     if device_index is not None:
#         record_audio(device_index, rate, duration=5)
#     else:
#         print("未找到可用麦克风设备，无法录音。")

# import pyaudio
# import wave

# def find_all_usable_input_devices():
#     p = pyaudio.PyAudio()
#     usable_devices = []
#     for i in range(p.get_device_count()):
#         info = p.get_device_info_by_index(i)
#         if info['maxInputChannels'] > 0:
#             try:
#                 stream = p.open(format=pyaudio.paInt16,
#                                 channels=1,
#                                 rate=int(info['defaultSampleRate']),
#                                 input=True,
#                                 input_device_index=i,
#                                 frames_per_buffer=1024)
#                 stream.close()
#                 usable_devices.append((i, info['name'], int(info['defaultSampleRate'])))
#             except Exception as e:
#                 # 设备不能用时也打印出来
#                 print(f"设备不可用: Index {i}, Name: {info['name']}, 错误: {e}")
#     p.terminate()
#     if not usable_devices:
#         print("没有可用的麦克风设备")
#     else:
#         print("可用麦克风设备列表:")
#         for idx, name, rate in usable_devices:
#             print(f"Index: {idx}, Name: {name}, 默认采样率: {rate}")
#     return usable_devices

# def record_audio(device_index, rate, duration=5, output_filename="output.wav"):
#     p = pyaudio.PyAudio()
#     stream = p.open(format=pyaudio.paInt16,
#                     channels=1,
#                     rate=rate,
#                     input=True,
#                     input_device_index=device_index,
#                     frames_per_buffer=1024)
#     print(f"开始录音，时长{duration}秒，设备索引: {device_index}")
#     frames = []

#     for _ in range(0, int(rate / 1024 * duration)):
#         data = stream.read(1024, exception_on_overflow=False)
#         frames.append(data)

#     print("录音结束，保存文件中...")
#     stream.stop_stream()
#     stream.close()
#     p.terminate()

#     wf = wave.open(output_filename, 'wb')
#     wf.setnchannels(1)
#     wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
#     wf.setframerate(rate)
#     wf.writeframes(b''.join(frames))
#     wf.close()
#     print(f"录音文件已保存: {output_filename}")

# if __name__ == "__main__":
#     devices = find_all_usable_input_devices()
#     if not devices:
#         print("未找到可用麦克风设备，无法录音。")
#     else:
#         # 这里自动用第一个设备录音，你可以自己改成选择哪个设备
#         device_index, device_name, rate = devices[0]
#         print(f"自动选择设备录音：Index {device_index}, Name {device_name}")
#         record_audio(device_index, rate, duration=5)

# import pyaudio
# import wave

# def find_all_usable_input_devices():
#     p = pyaudio.PyAudio()
#     usable_devices = []
#     for i in range(p.get_device_count()):
#         info = p.get_device_info_by_index(i)
#         if info['maxInputChannels'] > 0:
#             try:
#                 stream = p.open(format=pyaudio.paInt16,
#                                 channels=1,
#                                 rate=int(info['defaultSampleRate']),
#                                 input=True,
#                                 input_device_index=i,
#                                 frames_per_buffer=1024)
#                 stream.close()
#                 usable_devices.append((i, info['name'], int(info['defaultSampleRate'])))
#             except Exception as e:
#                 print(f"设备不可用: Index {i}, Name: {info['name']}, 错误: {e}")
#     p.terminate()
#     if not usable_devices:
#         print("没有可用的麦克风设备")
#     else:
#         print("可用麦克风设备列表:")
#         for idx, name, rate in usable_devices:
#             print(f"Index: {idx}, Name: {name}, 默认采样率: {rate}")
#     return usable_devices

# def record_audio(device_index, rate, duration=5, output_filename="output.wav"):
#     p = pyaudio.PyAudio()
#     stream = p.open(format=pyaudio.paInt16,
#                     channels=1,
#                     rate=rate,
#                     input=True,
#                     input_device_index=device_index,
#                     frames_per_buffer=1024)
#     print(f"开始录音，时长{duration}秒，设备索引: {device_index}")
#     frames = []

#     for _ in range(0, int(rate / 1024 * duration)):
#         data = stream.read(1024, exception_on_overflow=False)
#         frames.append(data)

#     print("录音结束，保存文件中...")
#     stream.stop_stream()
#     stream.close()
#     p.terminate()

#     wf = wave.open(output_filename, 'wb')
#     wf.setnchannels(1)
#     wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
#     wf.setframerate(rate)
#     wf.writeframes(b''.join(frames))
#     wf.close()
#     print(f"录音文件已保存: {output_filename}")

# if __name__ == "__main__":
#     devices = find_all_usable_input_devices()
#     if not devices:
#         print("未找到可用麦克风设备，无法录音。")
#     else:
#         while True:
#             try:
#                 selected_index = int(input("请输入要录音的设备Index: "))
#                 device = next((d for d in devices if d[0] == selected_index), None)
#                 if device:
#                     record_audio(device[0], device[2], duration=5)
#                     break
#                 else:
#                     print("无效的设备Index，请重新输入。")
#             except ValueError:
#                 print("输入无效，请输入数字。")


def find_pulse_device_index():
    p = pyaudio.PyAudio()
    target_name = "pulse"
    device_index = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0 and target_name in info['name'].lower():
            device_index = i
            print(f"找到匹配设备: Index={i}, Name={info['name']}")
            break
    p.terminate()
    return device_index

p = pyaudio.PyAudio()
device_index = find_pulse_device_index()
if device_index is None:
    print("未找到名称包含 'pulse' 的录音设备，使用默认设备")
    device_index = None  # 也可以不传

stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=device_index,  # 如果None则用默认设备
                frames_per_buffer=1024)