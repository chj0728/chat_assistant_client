from datetime import datetime

class Message:
    def __init__(self, chat_id: str, role: str, content: list, created_at: str):
        self.chat_id = chat_id
        self.role = role
        self.content = content  # 支持多类型内容
        self.created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        #self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @classmethod
    def from_dict(cls, data: dict):
        """
        从字典创建一个 Message 实例
        """
        return cls(
            chat_id=data["chat_id"],
            role=data["role"],
            content=data["content"],
            created_at=data["created_at"]
        )
    
    def to_dict(self) -> dict:
        """
        将 Message 对象转换为字典
        """
        return {
            "chat_id": self.chat_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    def __repr__(self):
        """
        定义对象的打印格式
        """
        return (f"Message(chat_id='{self.chat_id}', role='{self.role}', "
                f"content='{self.content}', created_at='{self.created_at}')")



# 定义添加消息的函数
def add_message_to_db(messages_db, chat_id, role, content):
    """
    创建一个新的 Message 并添加到数据库中
    :param messages_db: 数据库（列表）
    :param chat_id: 消息所属的 chat_id
    :param role: 消息角色（如 system, user, assistant）
    :param content: 消息内容（列表，支持 text 和 image_url）
    """
    # 获取当前时间作为 created_at
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 创建新的 Message 对象
    new_message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        created_at=created_at
    )
    
    # 将 Message 转换为字典并添加到数据库
    messages_db.append(new_message.to_dict())
    #print(f"成功添加消息：{new_message}")

def filter_messages(messages: list, max_messages: int = 10, max_images: int = 5) -> list:
    """
    限制消息列表，只保留第一条 system 消息和最新的 2*max_messages 条非 system 消息。
    同时限制最终消息列表中最多包含 max_images 个 image 类型的 content，超出的部分会移除。
    
    :param messages: 原始消息列表（字典格式或 Message 对象列表）
    :param max_messages: 限制的最大非 system 消息条数
    :param max_images: 限制的最大图片数量
    :return: 新的消息列表（字典格式）
    """
    # 确保 messages 是 Message 对象的列表
    if isinstance(messages[0], dict):
        messages = [Message.from_dict(msg) for msg in messages]
    
    # 提取第一条 system 消息
    system_message = next((msg for msg in messages if msg.role == "system"), None)
    
    # 提取最新的非 system 消息
    non_system_messages = [msg for msg in messages if msg.role != "system"]
    latest_messages = sorted(non_system_messages, key=lambda x: x.created_at, reverse=True)[:2*max_messages]
    
    # 统计图片的数量并处理 content
    total_images = 0
    for msg in latest_messages:
        new_content = []
        if msg.role == "user" :
            for item in msg.content:
                if item["type"] == "image_url":
                    if total_images < max_images:
                        new_content.append(item)
                        total_images += 1
                else:
                    new_content.append(item)
        else :
            for item in msg.content:
                new_content = item["text"]
        msg.content = new_content  # 更新消息的 content

    # 组合新的消息列表
    filtered_messages = []
    if system_message:
        filtered_messages.append(system_message)
    filtered_messages.extend(reversed(latest_messages))  # 保持时间顺序

    # 返回字典列表
    return [msg.to_dict() for msg in filtered_messages]



def clean_msg(msg):
    msg_copy = msg.copy()  # 创建副本
    del msg_copy["chat_id"]
    del msg_copy["created_at"]
    return msg_copy
    

# 将字典列表转换为 Message 对象列表
#messages = [Message.from_dict(msg) for msg in messages_from_db]
#print(messages)

# 将 Message 对象列表转换回字典列表
#messages_dict = [msg.to_dict() for msg in messages]
#print(messages_dict)


