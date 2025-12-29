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

    # url = "https://restapi.amap.com/v3/ip"
    # # url = "https://restapi.amap.com/v5/ip/location"
    # params = {"key": "581efe867760a80877991ec818d94ad1"}

    # resp = requests.get(url, params=params, timeout=5)
    # print(resp.json())
    # if resp.status_code == 200:
    #     data = resp.json()
    #     print("基于IP的位置信息:", data.get("province"), data.get("city"))

    #     # 查询天气预报需要adcode
    #     adcode = data.get("adcode")
    #     if adcode:
    #         weather_url = "https://restapi.amap.com/v3/weather/weatherInfo"
    #         weather_params = {
    #             "key": "581efe867760a80877991ec818d94ad1",
    #             "city": adcode,
    #         }
    #         weather_resp = requests.get(weather_url, params=weather_params, timeout=5)
    #         print("天气预报响应:", weather_resp.json())
    #         if weather_resp.status_code == 200:
    #             weather_data = weather_resp.json()
    #             print("天气预报:", weather_data.get("lives"))
    # else:
    #     print("获取位置信息失败:", resp.text)
