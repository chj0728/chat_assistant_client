import os
import requests
import json
from typing import List, Dict, Generator, Any, Optional, Union

# 设置默认 API Key
DEFAULT_API_KEY = "sk-oexebbnkwwnniwzsnoxihehdtfqmcaazdbmistpplkbzusdy"
os.environ["SILICONFLOW_API_KEY"] = DEFAULT_API_KEY

class SiliconFlowClient:
    def __init__(self, api_key: str = None):
        """
        初始化Silicon Flow聊天客户端
        :param api_key: API密钥，默认从环境变量获取
        """
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise ValueError("必须提供API密钥")
            
        self.base_url = "https://api.siliconflow.cn/v1"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        # 默认模型
        self.default_model = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
        
        # 添加与豆包API兼容的chat属性
        self.chat = ChatCompletions(self)

    def stream_chat(self,
                   message: str,
                   system_prompt: str = "你是一个智能助手。") -> Generator[str, None, None]:
        """
        流式聊天接口函数
        :param message: 用户消息
        :param system_prompt: 系统提示词，默认为通用助手
        :return: 流式生成的文本生成器
        """
        # 准备消息列表
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
        
        # 请求载荷
        payload = {
            "model": self.default_model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
            "top_p": 0.8,
            "max_tokens": 16384
        }
        
        url = f"{self.base_url}/chat/completions"
        
        try:
            # 发送流式请求
            with requests.post(url,
                              headers=self.headers,
                              json=payload,
                              stream=True) as response:
                response.raise_for_status()
                
                # 存储完整响应
                full_response = ""
                
                # 处理流式响应
                for line in response.iter_lines():
                    if line:
                        # 跳过 "data: " 前缀
                        if line.startswith(b'data: '):
                            line = line[6:]
                            
                        # 跳过结束标志
                        if line.strip() == b'[DONE]':
                            break
                            
                        try:
                            chunk = json.loads(line)
                            # 提取内容片段
                            if chunk.get('choices'):
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    # 打印并生成内容片段
                                    print(content, end='', flush=True)
                                    full_response += content
                                    yield content
                        except (json.JSONDecodeError, KeyError):
                            continue
                
                # 换行，确保输出美观
                print()  # 在流式输出结束后添加换行
        except Exception as e:
            print(f"\n流式聊天请求错误: {e}")
            yield f"错误: {e}"


# 定义兼容豆包API的ChatCompletions类
class ChatCompletions:
    def __init__(self, client: SiliconFlowClient):
        self.client = client
    
    def create(self, 
              model: str, 
              messages: List[Dict[str, Any]], 
              max_tokens: int = 1024, 
              temperature: float = 1.0, 
              top_p: float = 0.7,
              frequency_penalty: float = 0.05,
              stream: bool = False) -> Union[Dict, "StreamingResponse"]:
        """
        兼容豆包API的create方法
        :param model: 模型ID (在这里会被忽略，使用SiliconFlow默认模型)
        :param messages: 消息列表
        :param max_tokens: 最大生成token数
        :param temperature: 温度参数
        :param top_p: top_p参数
        :param frequency_penalty: 频率惩罚参数
        :param stream: 是否流式输出
        :return: 响应对象或流式响应对象
        """
        # 请求载荷
        payload = {
            "model": self.client.default_model,  # 使用SiliconFlow默认模型
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens
        }
        
        url = f"{self.client.base_url}/chat/completions"
        
        # 非流式请求
        if not stream:
            try:
                response = requests.post(
                    url,
                    headers=self.client.headers,
                    json=payload
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"请求错误: {e}")
                return {"error": str(e)}
        
        # 流式请求
        try:
            response = requests.post(
                url,
                headers=self.client.headers,
                json=payload,
                stream=True
            )
            response.raise_for_status()
            
            # 返回流式响应对象
            return StreamingResponse(response)
            
        except Exception as e:
            print(f"流式请求错误: {e}")
            # 创建一个包含错误信息的流式响应
            return ErrorStreamingResponse(str(e))


# 定义流式响应类，与豆包API兼容
class StreamingResponse:
    def __init__(self, response):
        self.response = response
        self.iterator = response.iter_lines()
        self.choices = []
        self._buffer = ""
    
    def __iter__(self):
        return self
    
    def __next__(self):
        """
        从迭代器中获取下一个响应块
        与豆包API响应格式兼容
        """
        try:
            line = next(self.iterator)
            
            if not line:
                return self.__next__()
            
            # 跳过 "data: " 前缀
            if line.startswith(b'data: '):
                line = line[6:]
            
            # 跳过结束标志
            if line.strip() == b'[DONE]':
                raise StopIteration
            
            try:
                # 解析JSON响应
                chunk_data = json.loads(line)
                
                # 转换为豆包API兼容格式
                if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                    delta = chunk_data['choices'][0].get('delta', {})
                    content = delta.get('content', '')
                    
                    # 创建豆包API兼容的响应对象
                    response_obj = type('DoubanResponse', (), {})()
                    response_obj.choices = []
                    
                    # 创建Choice对象
                    choice = type('Choice', (), {})()
                    choice.delta = type('Delta', (), {})()
                    choice.delta.content = content
                    
                    response_obj.choices.append(choice)
                    
                    return response_obj
                else:
                    # 如果没有有效内容，继续获取下一个
                    return self.__next__()
                    
            except json.JSONDecodeError:
                # 如果JSON解析失败，继续获取下一个
                return self.__next__()
                
        except StopIteration:
            self.response.close()
            raise


# 错误流式响应类
class ErrorStreamingResponse:
    def __init__(self, error_message):
        self.error_message = error_message
        self.returned_error = False
    
    def __iter__(self):
        return self
    
    def __next__(self):
        """只返回一次错误消息，然后结束迭代"""
        if not self.returned_error:
            self.returned_error = True
            
            # 创建豆包API兼容的错误响应对象
            response_obj = type('DoubanErrorResponse', (), {})()
            response_obj.choices = []
            
            # 创建Choice对象
            choice = type('Choice', (), {})()
            choice.delta = type('Delta', (), {})()
            choice.delta.content = f"错误: {self.error_message}"
            
            response_obj.choices.append(choice)
            
            return response_obj
        else:
            raise StopIteration


# 全局函数，方便直接调用
def chat(message: str, system_prompt: str = """你是数字济南馆的瞰小宝。专门为顾客答疑解惑服务并可以为顾客提供六种饮料。
        如果有人让你介绍你所在的数字济南馆，你需要按如下方式介绍：
        “数字济南体验馆创享公园正式开馆。该馆位于济南市历下区科技金融大厦裙楼，馆内布设艺术门厅、序厅、数字经济、数字政务数字生活等5大展区，包含展项225个，并设置5D影院元宇宙空间、AI智能绘画、格子大战等互动体验项目，可服务商业路演、展示展览、培训研学、亲子体验等各类活动。”
        你所在的便利店仅售卖六种饮料：可乐、雪碧、咖啡、奶茶、果汁和矿泉水。如顾客询问商品介绍，回复：可乐、雪碧3元，奶茶4元，矿泉水2元，咖啡和果汁5元！
        你对每种饮品的口味、价格、库存以及促销活动都十分熟悉。当顾客前来咨询时，请以亲切、专业且正式的语气提供准确的信息，且回复内容控制再80字以内！
        请直接回答问题或提供帮助，避免使用无关的语气词或冗余表达""", stream=False):
    """
    简单的聊天接口函数
    :param message: 用户消息
    :param system_prompt: 系统提示词
    :param stream: 是否返回流式对象
    :return: 完整的响应文本或流式对象
    """
    # 创建客户端
    client = SiliconFlowClient()
    
    # 如果需要流式返回
    if stream:
        # 消息列表
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
        # 直接返回流式对象，注意是client.chat.create而不是client.chat.completions.create
        return client.chat.create(
            model="任意值",  # 这个值会被忽略
            messages=messages,
            stream=True
        )
    
    # 否则返回完整文本
    full_response = ""
    for chunk in client.stream_chat(message, system_prompt):
        full_response += chunk
    return full_response

# 创建全局客户端实例，以便使用 ai_client.chat.completions.create() 方式调用

#这是基于诡计流东的调用方法


