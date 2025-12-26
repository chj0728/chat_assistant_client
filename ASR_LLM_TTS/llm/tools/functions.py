from datetime import datetime
from zoneinfo import ZoneInfo


def get_shanghai_time():
    """获取当前上海时间"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    print("当前上海时间:", get_shanghai_time())
