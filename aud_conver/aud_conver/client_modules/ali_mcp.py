import os
from openai import OpenAI
from datetime import datetime
import json
import ast
import sys
sys.path.append('/home/ymrobot/ros2_ws_guidance/src/aud_conver/aud_conver')
import force_no_proxy  # noqa
AGENT_SYS_PROMPT = '''
你是一位以郑和第一人称视角进行导览的智能导游，专业讲解太仓博物馆的展品及相关历史文化。基于历史人物郑和的真实经历和人格特征构建的数字化形象，你具有谦逊平和、知识渊博、富有亲和力的性格特点。  
请你根据我的指令，以JSON形式输出要运行的对应函数，并附上的第一人称回复。  
严格禁止输出除内置函数说明之外的函数！每次返回内置函数 sorr() 最多只能出现一次。如果没有对应的内置函数你需要返回内置函数sorr(),并且在response中返回这首诗词。回复速度要快，切记！

【输出格式】  
直接输出 JSON，从 { 开始，不要输出包含 ```json 的开头或结尾。  
只需要输出两个键：  
- "function"：一个列表，列表中每个元素都是字符串，代表要运行的函数名称和参数；  
- "response"：以第一人称的口吻，对用户指令的进行回应。  

列表元素的先后顺序表示执行函数的顺序。  

例如：  
example1:用户指令：“小诗，你好阿。”  
  你输出应为：  
    {'function': 'Hello‌()', 'response': '你好呀！欢迎你来浙江农历大学参观阿，有什么不懂的都可以咨询我哦！'}  
example2:用户指令：“我能和你握个手吗？？”  
  你输出应为：  
    {'function': 'Handshake()', 'response': '当然可以阿，小诗也很高兴能在今天遇见你！'}  
【内置函数说明】  
- 内置函数分为2个以下2个
1、打招呼对应'function': 'Hello‌()'
2、握手对应'function': 'Handshake()'

【注意事项】  
1. **只有**当用户指令中包含上述内置导航函数时，才在 "function" 列表里输出对应函数，否则必须输出 `sorr()`；  
2. "sorr()" 在整个输出中**最多出现一次**；  
3. “response” 必须通情达理；  
4. 若没有任何有效函数要调用，"function" 应为 `'sorr()'`，并配以风格的回应；  
5. 不要输出除内置函数说明之外的任何函数调用；  
6. 严格遵守 JSON 格式，确保可被程序直接解析。  
7. 当用户希望握手的时候优先在function中的内容中返回Handshake()，严格参考example2进行类似返回！！！

【严格限制】
在'function': ,中符号后面的内容只允许包含一个进行输出！例如'function': 'Hello‌()'/'function': 'Handshake()'/'function': 'sorr()'
'''

client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

def extract_all_functions(json_str):
    """
    从外层 JSON 字符串中提取出 message.content 内嵌的字典中的 "function" 键，
    并返回该列表（顺序与原列表一致）。
    
    参数：
        json_str (str): 外层 JSON 字符串
        
    返回：
        list: 按顺序包含所有函数字符串的列表；解析失败时返回空列表。
    """
    try:
        # 解析外层 JSON
        outer_data = json.loads(json_str)
        # 获取 message.content 内的字符串（注意内容可能使用单引号，不符合标准 JSON 格式）
        inner_str = outer_data["choices"][0]["message"]["content"]
        # 使用 ast.literal_eval 将单引号的字典字符串转换为字典对象
        inner_data = ast.literal_eval(inner_str)
        # 提取 "function" 键对应的列表
        function_list = inner_data.get("function", [])
        return function_list
    except Exception as e:
        print("解析过程中出错:", e)
        return []
def extract_all_response(json_str):
    """
    从外层 JSON 字符串中提取出 message.content 内嵌的字典中的 "function" 键，
    并返回该列表（顺序与原列表一致）。
    
    参数：
        json_str (str): 外层 JSON 字符串
        
    返回：
        list: 按顺序包含所有函数字符串的列表；解析失败时返回空列表。
    """
    try:
        # 解析外层 JSON
        outer_data = json.loads(json_str)
        # 获取 message.content 内的字符串（注意内容可能使用单引号，不符合标准 JSON 格式）
        inner_str = outer_data["choices"][0]["message"]["content"]
        # 使用 ast.literal_eval 将单引号的字典字符串转换为字典对象
        inner_data = ast.literal_eval(inner_str)
        # 提取 "response" 键对应的列表
        response = inner_data.get("response")
        return response
    except Exception as e:
        print("解析过程中出错:", e)
        return []
def get_out(user_message):
    """
    发送用户自定义消息给大模型，并提取返回内容中的函数列表。
    
    参数：
        user_message (str): 用户自定义的指令消息内容
        
    返回：
        list: 模型返回中提取出的按顺序排列的函数字符串列表
    """
    # 调用大模型API，使用用户传入的消息内容更新消息内容
    completion = client.chat.completions.create(
        model="qwen-turbo",  # 可根据需要更换模型
        messages=[
            {'role': 'system', 'content': AGENT_SYS_PROMPT},
            {'role': 'user', 'content': user_message}
        ],
        temperature = 0,
    )
    
    model_output = completion.model_dump_json()
    # print(model_output)
    # print("---------------\n")
    # 解析外层 JSON 输出内容
    # data = json.loads(model_output)
    # content = data["choices"][0]["message"]["content"]
    # print("模型返回的内容：\n", content)
    
    # current_time2 = datetime.now()
    # formatted_time2 = current_time2.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time2.microsecond // 1000:03d}'
    # print("当前时间（精确到毫秒）:", formatted_time2)
    
    functions = extract_all_functions(model_output)
    response = extract_all_response(model_output)
    
    return functions,response
# current_time = datetime.now()
# formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
# print("当前时间（精确到毫秒）:", formatted_time)
# function,response=get_out('你好你好,能和你握个手吗？')
# print(function)
# print(type(function))
# print(response)
# print(type(response))
# current_time = datetime.now()
# formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.') + f'{current_time.microsecond // 1000:03d}'
# print("当前时间（精确到毫秒）:", formatted_time)

