# coding=utf-8
'''
sambert语音合成&嘴型序列
开发文档：https://help.aliyun.com/zh/model-studio/sambert-python-sdk?spm=a2c4g.11186623.help-menu-2400256.d_2_6_1_1.4bf33dfcvPx6N0#3639e1cb40mxi
'''

import dashscope
from dashscope.api_entities.dashscope_response import SpeechSynthesisResponse
from dashscope.audio.tts import ResultCallback, SpeechSynthesizer, SpeechSynthesisResult
import time
import queue

# 全局变量
APIKEY = 'sk-2644a4c474384b208706d83bad25b0a7'
VOICE_NAME = 'sambert-zhichu-v1'
timestamps_queue = queue.Queue()  # 语音播放的任务队列

dashscope.api_key = APIKEY

start_time = None
class Callback(ResultCallback):
    def __init__(self):
        super().__init__()
        self.len = 0 
        self.timestamp_printed = False  # 👈 新增：标记时间戳是否已打印

    def on_open(self):
        print('和服务器成功建立连接')

    def on_complete(self):
        process_time = time.time() - start_time
        print(f'任务完成,耗时: {process_time*1000:.2f}ms')

    def on_error(self, response: SpeechSynthesisResponse):
        print('报错：%s' % (str(response)))

    def on_close(self):
        print('和服务器之间的连接已关闭')

    def on_event(self, result: SpeechSynthesisResult):
        process_time = time.time() - start_time
        # if result.get_audio_frame() is not None:
        #     self.len += len(result.get_audio_frame())
        #     print(f'收到二进制音频数据：{self.len},耗时：{process_time*1000:.2f}ms',)

        if result.get_timestamp() is not None and not self.timestamp_printed:  # 👈 检查是否已打印
            global timestamps_queue
            timestamps_queue.put(result.get_timestamp())
            print('收到时间戳数据：', str(result.get_timestamp()),f'耗时：{process_time*1000:.2f}ms')
            self.timestamp_printed = True  # 👈 标记为已打印


def text2mp3(text, output_file='output.wav', **synth_kwargs):
    """
    Args:
        voice: 合成音色
        text: 要合成的文本
        output_file: 输出文件路径
        **synth_kwargs: 其他参数（如 sample_rate, format,volume,rate,pitch 等）
    
    Returns:
        成功返回文件路径，失败返回 None
    """
    # 构建调用参数
    callback = Callback()
    call_kwargs = {
        'model': VOICE_NAME,
        'text': text,
        'format': 'mp3',
        'callback':callback,
        'word_timestamp_enabled': True,
        'phoneme_timestamp_enabled': True,
    }
    call_kwargs.update(synth_kwargs)
    
    try:
        global start_time
        start_time = time.time()

        result = SpeechSynthesizer.call(**call_kwargs)
        if result.get_response()["status_code"] != 200:
            print('ERROR: response is %s' % (result.get_response()))
        
        # 保存音频文件
        audio_data = result.get_audio_data()
        with open(output_file, 'wb') as f:
            f.write(audio_data)

        process_time = time.time() - start_time
        print(f'SUCCESS: 语音合成成功！音频数据大小: {len(audio_data)} bytes，已保存至 {output_file}，耗时: {process_time:.3f}s')
        return output_file
        
    except Exception as e:
        print(f'ERROR: {str(e)}')
        return None

# ====== 调用示例 ======
if __name__ == "__main__":
    text = "今天天气怎么样"
    filename = "output.mp3"
    result_path = text2mp3(
        text=text,
        output_file=filename, 
        # sample_rate = 24000,  # 覆盖默认参数
    )
    
    if result_path:
        print(f"音频已生成: {result_path}")
    else:
        print("语音合成失败。")

