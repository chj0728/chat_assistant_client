import os
import requests
import json
from typing import List, Dict, Optional, Union, Generator, Callable, Any
from datetime import datetime
# 设置默认 API Key
DEFAULT_API_KEY = "sk-oexebbnkwwnniwzsnoxihehdtfqmcaazdbmistpplkbzusdy"
os.environ["SILICONFLOW_API_KEY"] = DEFAULT_API_KEY



class StreamProcessor:
    """
    流式响应处理器，用于处理和转换来自API的流式响应
    """
    def __init__(self, response: requests.Response, on_chunk: Optional[Callable] = None):
        """
        初始化流式处理器
        
        Args:
            response: 来自API的流式响应对象
            on_chunk: 可选的回调函数，每获取一个数据块时调用
        """
        self.response = response
        self.on_chunk = on_chunk
        self.complete_content = ""
        self.is_done = False
        self.error = None
        
    def __iter__(self) -> Generator[Dict[str, Any], None, None]:
        """
        使StreamProcessor实例可迭代，让用户能够通过for循环迭代每个数据块
        
        Returns:
            生成器，产生解析后的JSON数据块
        """
        try:
            if not hasattr(self.response, 'iter_lines'):
                self.error = "无效的响应对象"
                yield {"error": self.error}
                return
                
            for line in self.response.iter_lines():
                if not line:
                    continue
                    
                # 处理常见的流式格式
                if line.startswith(b"data: "):
                    line = line[6:]  # 去掉 "data: " 前缀
                    
                if line.strip() == b"[DONE]":
                    self.is_done = True
                    break
                    
                try:
                    chunk = json.loads(line)
                    
                    # 提取内容
                    content = self._extract_content(chunk)
                    if content:
                        self.complete_content += content
                        
                    # 如果提供了回调函数，调用它
                    if self.on_chunk:
                        self.on_chunk(chunk)
                        
                    yield chunk
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            self.error = str(e)
            yield {"error": f"处理流式响应时出错: {self.error}"}
    
    def _extract_content(self, chunk: Dict) -> str:
        """
        从数据块中提取文本内容
        
        Args:
            chunk: 解析后的JSON数据块
            
        Returns:
            从数据块中提取的文本内容，如果没有则返回空字符串
        """
        # 处理标准格式的响应
        if "choices" in chunk and len(chunk["choices"]) > 0:
            delta = chunk["choices"][0].get("delta", {})
            return delta.get("content", "")
            
        # 处理其他可能的格式（可根据需要扩展）
        return ""
    
    def get_full_content(self) -> str:
        """
        获取完整的文本内容
        
        Returns:
            所有数据块中累积的文本内容
        """
        return self.complete_content
    
    def has_error(self) -> bool:
        """
        检查处理过程中是否发生错误
        
        Returns:
            是否发生错误
        """
        return self.error is not None


def get_available_models(api_key=None):
    """
    获取Silicon Flow可用的模型列表
    
    Args:
        api_key: API密钥，如果未提供则尝试从环境变量获取
    
    Returns:
        可用模型的列表或None
    """
    api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
    url = "https://api.siliconflow.cn/v1/models"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"获取模型列表失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None
    except Exception as e:
        print(f"获取模型列表时发生错误: {e}")
        return None

class SiliconFlowChatClient:
    """
    Silicon Flow Chat Completions API 客户端
    """
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.siliconflow.cn/v1"):
        """
        初始化 Silicon Flow Chat 客户端
        
        Args:
            api_key: API密钥，如果未提供则尝试从环境变量 SILICONFLOW_API_KEY 获取
            base_url: API基础URL
        """
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise ValueError("API密钥必须通过参数或环境变量SILICONFLOW_API_KEY提供")
        
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def chat_completion(self, 
                        messages: List[Dict[str, str]], 
                        model: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", 
                        temperature: float = 0.7,
                        top_p: float = 0.8, 
                        max_tokens: int = 16384,
                        stream: bool = False) -> Union[Dict, StreamProcessor]:
        """
        创建聊天完成请求
        
        Args:
            messages: 聊天消息列表，格式为 [{"role": "user", "content": "你好"}]
            model: 模型名称
            temperature: 采样温度
            top_p: 核采样
            max_tokens: 生成的最大token数
            stream: 是否使用流式返回
            
        Returns:
            如果 stream=False，返回完整的API响应字典
            如果 stream=True，返回StreamProcessor对象
        """
        url = f"{self.base_url}/chat/completions"
        
        # 确保messages列表中有至少一条消息
        if not messages:
            messages = [{"role": "user", "content": "你好"}]
        
        # 确保每个消息都有正确的格式
        for msg in messages:
            if "role" not in msg:
                msg["role"] = "user"
            if "content" not in msg:
                msg["content"] = ""
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        try:
            if not stream:
                response = requests.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                return response.json()
            else:
                # 流式响应使用StreamProcessor处理
                response = requests.post(url, headers=self.headers, json=payload, stream=True)
                response.raise_for_status()
                return StreamProcessor(response)
        except Exception as e:
            print(f"请求处理过程中出错: {e}")
            print(f"请求载荷: {json.dumps(payload, ensure_ascii=False)}")
            print(f"请检查API密钥、模型名称和其他参数是否正确")
            raise


def quick_chat(message, model="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", use_stream=True):
    """
    快速聊天函数 - 单次请求并返回结果
    
    Args:
        message: 用户输入的消息
        model: 使用的模型
        use_stream: 是否使用流式返回
        
    Returns:
        模型的回复内容
    """
    # 使用默认 API Key
    api_key = os.environ.get("SILICONFLOW_API_KEY", DEFAULT_API_KEY)
    
    # 初始化客户端
    client = SiliconFlowChatClient(api_key=api_key)
    
    # 准备消息
    messages = [
        {"role": "system", "content": """你是数字济南馆的瞰小宝。专门为顾客答疑解惑服务并可以为顾客提供六种饮料。
        如果有人让你介绍你所在的数字济南馆，你需要按如下方式介绍：
        "数字济南体验馆创享公园正式开馆。该馆位于济南市历下区科技金融大厦裙楼，馆内布设艺术门厅、序厅、数字经济、数字政务数字生活等5大展区，包含展项225个，并设置5D影院元宇宙空间、AI智能绘画、格子大战等互动体验项目，可服务商业路演、展示展览、培训研学、亲子体验等各类活动。"
        你所在的便利店仅售卖六种饮料：可乐、雪碧、咖啡、奶茶、果汁和矿泉水。如顾客询问商品介绍，回复：可乐、雪碧3元，奶茶4元，矿泉水2元，咖啡和果汁5元！
        你对每种饮品的口味、价格、库存以及促销活动都十分熟悉。当顾客前来咨询时，请以亲切、专业且正式的语气提供准确的信息。
        描述图片时请以'我能看到…'开头，禁止使用'这张图片'。切勿使用'哎呀呀'、'哎呀'等口头禅。
        请直接回答问题或提供帮助，避免使用无关的语气词或冗余表达。
        """},
        {"role": "user", "content": message}
    ]
    
    # 记录开始时间
    start_time = datetime.now()
    
    try:
        if use_stream:
            print("使用流式返回...")
            stream_processor = client.chat_completion(messages, model=model, stream=True)
            
            full_content = ""
            for chunk in stream_processor:
                if "error" in chunk:
                    print(f"错误: {chunk['error']}")
                    return None
                
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        print(content, end="", flush=True)
                        full_content += content
            
            # 记录结束时间
            end_time = datetime.now()
            process_time = (end_time - start_time).total_seconds()
            print(f"\n\n处理时间: {process_time:.2f}秒")
            
            # 也可以使用StreamProcessor内置的方法获取完整内容
            # full_content = stream_processor.get_full_content()
            
            return full_content
        else:
            print("使用普通请求...")
            response = client.chat_completion(messages, model=model, stream=False)
            
            # 记录结束时间
            end_time = datetime.now()
            process_time = (end_time - start_time).total_seconds()
            
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"\n{content}")
            print(f"\n处理时间: {process_time:.2f}秒")
            
            return content
    except Exception as e:
        print(f"请求失败: {e}")
        return None


def stream_callback_example(message, model="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"):
    """
    使用回调函数处理流式返回示例
    
    Args:
        message: 用户输入的消息
        model: 使用的模型
    """
    api_key = os.environ.get("SILICONFLOW_API_KEY", DEFAULT_API_KEY)
    client = SiliconFlowChatClient(api_key=api_key)
    
    messages = [
        {"role": "system", "content": "你是一个有用的助手。"},
        {"role": "user", "content": message}
    ]
    
    # 定义回调函数
    def on_chunk(chunk):
        if "choices" in chunk and len(chunk["choices"]) > 0:
            delta = chunk["choices"][0].get("delta", {})
            content = delta.get("content", "")
            if content:
                print(content, end="", flush=True)
    
    # 创建带有回调的StreamProcessor
    response = client.chat_completion(messages, model=model, stream=True)
    stream_processor = StreamProcessor(response.response, on_chunk=on_chunk)
    
    # 消费流
    for _ in stream_processor:
        pass  # 处理已经在回调函数中完成
    
    print(f"\n\n完整内容: {stream_processor.get_full_content()}")
    
    if stream_processor.has_error():
        print(f"发生错误: {stream_processor.error}")


def main():
    """
    主函数，提供交互式模型选择和聊天
    """
    print("Silicon Flow 快速聊天示例")
    print("-----------------------")
    
    # 获取并显示可用模型
    models_info = get_available_models()
    default_model = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    
    if models_info and "data" in models_info:
        print("\n可用模型:")
        available_models = [model["id"] for model in models_info["data"]]
        for i, model in enumerate(available_models, 1):
            print(f"{i}. {model}")
        
        model_choice = input("\n请选择模型编号 (直接回车使用默认模型): ")
        
        if model_choice.strip() and model_choice.isdigit():
            idx = int(model_choice) - 1
            if 0 <= idx < len(available_models):
                selected_model = available_models[idx]
                print(f"已选择模型: {selected_model}")
            else:
                selected_model = default_model
                print(f"无效选择，将使用默认模型: {selected_model}")
        else:
            selected_model = default_model
            print(f"使用默认模型: {selected_model}")
    else:
        selected_model = default_model
        print(f"无法获取模型列表，将使用默认模型: {selected_model}")
    
    # 选择是否使用流式返回
    stream_choice = input("\n是否使用流式返回? (y/n, 默认y): ").lower()
    use_stream = stream_choice != 'n'
    
    # 获取用户输入
    user_message = input("\n请输入您的问题: ")
    
    if not user_message:
        user_message = '''
【我现在的指令是】
我问你答，你告诉我关于2025年新能源汽车的销售行情！
'''
        print(f"使用默认问题: {user_message}")
    
    print("\n处理中...\n")
    response = quick_chat(user_message, model=selected_model, use_stream=use_stream)
    print(response)
    current_time = datetime.now()
    formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
    print("当前时间（精确到毫秒）:", formatted_time)

if __name__ == "__main__":
    main()
