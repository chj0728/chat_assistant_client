import requests

from datetime import datetime
from zoneinfo import ZoneInfo


def get_shanghai_time():
    """获取当前上海时间"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%Y-%m-%d %H:%M:%S")


def get_current_location():
    """获取当前位置信息（示例返回固定值）
    这里可以集成实际的定位服务API来获取当前位置信息
    """

    return "上海市嘉定区曹安公路的同济大学国家大学科技园"


if __name__ == "__main__":
    print("当前上海时间:", get_shanghai_time())

    print("当前位置信息:", get_current_location())
