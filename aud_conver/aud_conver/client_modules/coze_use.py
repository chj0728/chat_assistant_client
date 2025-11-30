import requests
import json
import time
import datetime

api_key = "pat_fZ8zDBN4udYpxYS88QzPYQz2jzkptNbOgo7J8p4W1LwWmOfLurIdu9sU5oCMdufK"
botid = "7490941404483485734"
baseUrl = 'https://api.coze.cn/v3/chat'
headers = {
    "Authorization": f"Bearer {api_key}",
    'Content-Type': 'application/json'
}

def is_json(text):
    """检查文本是否为有效的JSON格式"""
    try:
        json.loads(text)
        return True
    except (ValueError, TypeError):
        return None

def getQuesyionAnswer(conversationID, chatID):
    params = {"bot_id": botid, "task_id": chatID}
    getChatStatusUrl = baseUrl + f'/retrieve?conversation_id={conversationID}&chat_id={chatID}&'
    # 减少轮询间隔到0.2秒，加快检查频率
    polling_interval = 0.2
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            response = requests.get(getChatStatusUrl, headers=headers, params=None, timeout=10)
            if response.status_code == 200:
                response_data = response.json()
                
                # 检查响应数据结构是否完整
                if 'data' not in response_data:
                    print(f"警告: API响应中缺少'data'字段，等待重试... ({retry_count+1}/{max_retries})")
                    retry_count += 1
                    time.sleep(1)  # 稍微延长重试间隔
                    continue
                
                status = response_data['data'].get('status')
                if not status:
                    print(f"警告: API响应中缺少'status'字段，等待重试... ({retry_count+1}/{max_retries})")
                    retry_count += 1
                    time.sleep(1)
                    continue
                
                # 如果状态为completed或者response_data中已经包含了答案，直接提取答案
                if status == 'completed' or ('answer' in response_data['data'] and response_data['data']['answer']):
                    # 如果直接从状态响应中获取到了答案
                    if 'answer' in response_data['data'] and response_data['data']['answer']:
                        answer = response_data['data']['answer']
                        print("大模型应答：", answer)
                        return answer
                    
                    # 否则从消息列表中获取答案
                    try:
                        getChatAnswerUrl = baseUrl + f'/message/list?chat_id={chatID}&conversation_id={conversationID}'
                        response = requests.get(getChatAnswerUrl, headers=headers, params=params, timeout=10)
                        if response.status_code == 200:
                            answer_data = response.json()
                            if not answer_data.get('code') and 'data' in answer_data:
                                for item in answer_data['data']:
                                    if item['type'] == 'answer':
                                        answer = item['content']
                                        print("大模型应答：", answer)
                                        return answer
                            else:
                                print("获取消息列表失败：", answer_data)
                        else:
                            print(f"获取消息列表请求失败，状态码: {response.status_code}")
                    except Exception as e:
                        print(f"获取消息列表异常: {str(e)}")
                    
                    # 如果获取消息列表失败但状态已完成，返回可能有限的信息
                    if 'answer' in response_data['data']:
                        return response_data['data'].get('answer', "未能获取完整答案")
                    break
                else:
                    # 检查是否有部分答案可用
                    if 'answer' in response_data['data'] and response_data['data']['answer']:
                        answer = response_data['data']['answer']
                        print("大模型应答：", answer)
                        return answer
                    
                    time.sleep(polling_interval)  # 减少等待时间，继续轮询
            else:
                print(f"请求失败，状态码: {response.status_code}")
                retry_count += 1
                time.sleep(1)
        except Exception as e:
            print(f"请求异常: {str(e)}")
            retry_count += 1
            time.sleep(1)
    
    return "未能获取到答案"  # 如果没有获取到答案，返回提示信息

def questionService(questionText):
    # 记录开始时间
    start_time = datetime.datetime.now()
    print(f"开始请求时间: {start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    
    data = {
        "bot_id": botid,
        "user_id": "jiangwp",
        "stream": False,  # 确保非流式返回
        "auto_save_history": True,
        "additional_messages": [
            {
                "role": "user",
                "content": questionText,
                "content_type": "text"
            }
        ]
    }
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # 发送POST请求
            response = requests.post(baseUrl, headers=headers, data=json.dumps(data), timeout=10)
            
            # 检查响应状态码
            if response.status_code == 200:
                # 解析响应内容
                response_data = response.json()
                
                if 'data' not in response_data:
                    print(f"警告: 初始响应中缺少'data'字段，重试中... ({retry_count+1}/{max_retries})")
                    retry_count += 1
                    time.sleep(1)
                    continue
                
                chatid = response_data['data'].get('id')
                conversation_id = response_data['data'].get('conversation_id')
                
                if not chatid or not conversation_id:
                    print(f"警告: 缺少必要的ID字段，重试中... ({retry_count+1}/{max_retries})")
                    retry_count += 1
                    time.sleep(1)
                    continue
                
                # 检查初始响应中是否已经包含答案
                if 'answer' in response_data['data'] and response_data['data']['answer']:
                    answer = response_data['data']['answer']
                    print("大模型应答：", answer)
                    result = answer
                else:
                    result = getQuesyionAnswer(conversation_id, chatid)
                
                # 记录结束时间并计算时间差
                end_time = datetime.datetime.now()
                print(f"结束请求时间: {end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                time_diff = end_time - start_time
                print(f"请求耗时: {time_diff.total_seconds():.3f} 秒")
                
                return result  # 返回获取到的答案
            else:
                print(f"请求失败，状态码: {response.status_code}，重试中... ({retry_count+1}/{max_retries})")
                retry_count += 1
                time.sleep(1)
        except Exception as e:
            print(f"请求异常: {str(e)}，重试中... ({retry_count+1}/{max_retries})")
            retry_count += 1
            time.sleep(1)
    
    print("请求失败，达到最大重试次数")
    # 记录结束时间并计算时间差
    end_time = datetime.datetime.now()
    print(f"结束请求时间: {end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    time_diff = end_time - start_time
    print(f"请求耗时: {time_diff.total_seconds():.3f} 秒")
    
    return "请求失败，无法获取回答"  # 请求全部失败时返回提示信息

# # 执行问题查询
# try:
#     txt = questionService("你是谁")
#     # print("获取到的答案:", txt)
#     print("是否是JSON格式:", is_json(txt))
# except Exception as e:
#     print(f"程序执行异常: {str(e)}")

# 执行问题查询
txt = questionService("带我去厕所")
# print("获取到的答案:", txt)
print("是否是JSON格式:", is_json(txt))