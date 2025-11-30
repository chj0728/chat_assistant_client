import os
from openai import OpenAI

os.environ['ARK_API_KEY'] = '055d1797-f249-4357-b61b-04b30f4a4223'
# 请确保您已将 API Key 存储在环境变量 ARK_API_KEY 中
# 初始化Ark客户端，从环境变量中读取您的API Key
client = OpenAI(
    # 此为默认路径，您可根据业务所在地域进行配置
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    # 从环境变量中获取您的 API Key。此为默认方式，您可根据需要进行修改
    api_key=os.environ.get("ARK_API_KEY"),
)
from datetime import datetime

# 获取当前时间并格式化到毫秒
current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
print(current_time)

response = client.chat.completions.create(
    # 指定您创建的方舟推理接入点 ID，此处已帮您修改为您的推理接入点 ID
    model="ep-20250327133100-c5s44",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "现在几点了？"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://ark-project.tos-cn-beijing.volces.com/images/view.jpeg"
                    },
                },
            ],
        }
    ],
)

# 获取当前时间并格式化到毫秒
current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
print(current_time)

print(response.choices[0])

#pip install --upgrade "openai>=1.0"