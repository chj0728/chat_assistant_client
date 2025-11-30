import threading

from openai import OpenAI
import os
import base64


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


class ChatClient:
    def __init__(self,api_key,base_url,image_path):
        self.api_key=api_key
        self.base_url=base_url
        self.base64_image_path=encode_image(image_path)
        self.client=OpenAI(api_key=self.api_key,base_url=self.base_url)
        self.thread=None
        self.stop_event=threading.Event()

    def run_chat(self):
        self.stop_event.clear()
        self.thread=threading.Thread(target=self._run_chat_thread)
        self.thread.start()

    def _run_chat_thread(self):
        try:
            completion=self.client.chat.completions.create(
                model="qwen-vl-max-2025-04-08",
                messages=[
                            {
                                "role": "system",
                                "content": [{"type": "text", "text": "You are a helpful assistant."}]
                            },
                            {
                                "role": "user",
                                "content": [
                                                {
                                                    "type": "image_url",
                                                    # 需要注意，传入Base64图像格式
                                                    # PNG图像：  f"data:image/png;base64,{base64_image}"
                                                    # JPEG图像： f"data:image/jpeg;base64,{base64_image}"
                                                    # WEBP图像： f"data:image/webp;base64,{base64_image}"
                                                    "image_url": {"url": f"data:image/jpeg;base64,{self.base64_image_path}"},
                                                },
                                                {
                                                    "type": "text",
                                                    "text": "图中描绘的是什么景象?，根据这样的景象，写一首中国古代绝句诗"#！！组长，这里需要你根据场景写提示词，此处已经可以识别图片内容
                                                },
                                            ],
                            }
                        ],
                stream=True
            )
            full_content = ""
            print("流式输出内容为：")

            for chunk in completion:
                if not self.stop_event.is_set():#流式输出时，检查是否要线程中断，无线程中断，就继续输出
                    if chunk.choices[0].delta.content is None:
                        continue
                    full_content += chunk.choices[0].delta.content
                    print(chunk.choices[0].delta.content, end='')
        except Exception as e:
            if not self.stop_event.is_set():
                print(f"An error occurred: {e}")


    def stop_chat(self):#一旦调用stop_chat，就发生线程中断
        self.stop_event.set()#线程间通信，告诉图片交互线程，中断



if __name__ == '__main__':

    chat_client_thread=ChatClient(
        api_key="sk-dad025bee21a42ddbdc308d3377c07a2",#公司账号的api-key
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        image_path="/home/yyds/图片/离婚.jpeg"#！！这是我电脑的图片存储路径，需要更改
    )
    chat_client_thread.run_chat()

    import time

    time.sleep(10)#模拟的是，图片交互线程开启10秒后，进行线程中断，若不需要，可以删除紧邻的2行
    chat_client_thread.stop_chat()#这一行是中断图片交互的线程

#print(completion.choices[0].message.content)