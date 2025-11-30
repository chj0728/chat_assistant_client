import os
import sys
import time
import queue
import threading
from openai import OpenAI
from .processor_achieve import StreamProcessor

# 创建一个自定义的StreamProcessor子类
class QwenStreamProcessor(StreamProcessor):
    def _extract_content(self, chunk):
        """
        从数据流的chunk中提取内容
        重写以适应Qwen API响应格式
        """
        try:
            # 尝试提取content
            if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                    return chunk.choices[0].delta.content or ""
            return ""
        except (AttributeError, IndexError) as e:
            # 更详细的错误日志
            print(f"提取内容时出错: {str(e)}, chunk类型: {type(chunk)}")
            return ""

# 定义自定义TTS函数，修复路径问题
def custom_text_to_speech(sentence, sentence_id):
    """自定义文本转语音函数，使用正确路径"""
    print(f"[TTS] 转语音: {sentence}")
    
    # 使用当前目录下的tmp文件夹，确保有写入权限
    current_dir = os.getcwd()
    save_path = os.path.join(current_dir, 'tmp/')
    
    # 创建目录（如果不存在）
    os.makedirs(save_path, exist_ok=True)
    
    try:
        # 导入TTS函数
        from client_modules.db_tts_websocket import dbsentence2mp3
        file_path = save_path + str(sentence_id)
        file_name = dbsentence2mp3(sentence, file_path)
        
        # 如果返回None，尝试自行构建路径
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

# 主函数示例
def main():
    # 设置API客户端
    client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    
    # 创建流式API调用
    completion = client.chat.completions.create(
        model="qwen-plus",
        messages=[
            {'role': 'system', 'content': '''你将扮演一个人物角色李白，以下是关于这个角色的详细设定，请根据这些信息来构建你的回答，回复中禁止出现任何括号内的内容或说明。回复内容控制在80字。'''},
            {'role': 'user', 'content': '你是谁？'}
        ],
        stream=True,
        stream_options={"include_usage": True}
    )
    
    # 创建自定义处理器实例
    processor = QwenStreamProcessor(text_to_speech_func=custom_text_to_speech)
    
    # 创建一个线程用于处理数据流
    processing_thread = threading.Thread(target=processor.process_stream, args=(completion,))
    processing_thread.daemon = True  # 设为守护线程，当主程序退出时自动终止
    processing_thread.start()
    
    # 收集完整内容
    full_sentences = []
    
    # 在主线程中，持续检查队列
    print("开始从队列获取处理结果...")
    try:
        while True:
            try:
                # 非阻塞方式获取，设置超时
                sentence_tuple = processor.get_real_time_results().get(timeout=0.1)
                
                # 处理每个句子（sentence_tuple是(id, content)的元组）
                sentence_id, sentence_content = sentence_tuple
                print(f"主线程获取到句子 ID: {sentence_id}, 内容: {sentence_content}")
                
                # 添加到完整内容列表
                full_sentences.append(sentence_content)
                
                # 标记任务完成
                processor.get_real_time_results().task_done()
                
            except queue.Empty:
                # 检查处理是否完成
                if not processing_thread.is_alive():
                    print("处理线程已结束，退出主循环")
                    break
                    
                # 短暂睡眠减少CPU使用
                time.sleep(0.01)
    except KeyboardInterrupt:
        print("用户中断，正在停止...")
        processor.set_wake_flag(True)  # 发送停止信号
    
    # 等待处理线程完全结束
    processing_thread.join(timeout=5)
    
    # 打印完整的响应
    print("\n完整的内容:")
    full_content = "".join(full_sentences)
    print(full_content)
    
    print("程序执行完毕")

if __name__ == "__main__":
    main()