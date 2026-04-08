import requests

from datetime import datetime
from zoneinfo import ZoneInfo


def get_shanghai_time():
    """获取当前上海时间"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return f"当前上海时间是{now.strftime('%Y-%m-%d %H:%M:%S')}"


def get_current_location():
    """获取当前位置信息（示例返回固定值）
    这里可以集成实际的定位服务API来获取当前位置信息
    """
    url = "https://restapi.amap.com/v3/ip"
    params = {"key": "581efe867760a80877991ec818d94ad1"}
    resp = requests.get(url, params=params, timeout=3)
    if resp.status_code == 200:
        data = resp.json()
        city = data.get("city", "未知城市")
        return f"当前位于{city}"
    else:

        return "上海市嘉定区曹安公路的同济大学国家大学科技园"


def get_weather_info():
    """获取天气预报信息"""

    adcode = ""

    url = "https://restapi.amap.com/v3/ip"
    params = {"key": "581efe867760a80877991ec818d94ad1"}
    resp = requests.get(url, params=params, timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        adcode = data.get("adcode", "310000")
    else:
        adcode = "310000"  # 上海市的adcode

    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    params = {
        "key": "581efe867760a80877991ec818d94ad1",
        "city": adcode,
    }
    resp = requests.get(url, params=params, timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        lives = data.get("lives", [])
        return (
            f"当前天气:{lives[0]['weather']}, 温度:{lives[0]['temperature']}°C, 湿度:{lives[0]['humidity']}%, 风向:{lives[0]['winddirection']}, 风力:{lives[0]['windpower']}级"
            if lives
            else "无法获取天气信息"
        )
    else:
        return "获取天气信息失败"


if __name__ == "__main__":
    print("当前上海时间:", get_shanghai_time())

    print("当前位置信息:", get_current_location())

    url = "https://restapi.amap.com/v3/ip"
    # url = "https://restapi.amap.com/v5/ip/location"
    params = {"key": "581efe867760a80877991ec818d94ad1"}

    resp = requests.get(url, params=params, timeout=5)
    print(resp.json())
    if resp.status_code == 200:
        data = resp.json()
        print("基于IP的位置信息:", data.get("province"), data.get("city"))

        # 查询天气预报需要adcode
        adcode = data.get("adcode")
        if adcode:
            weather_url = "https://restapi.amap.com/v3/weather/weatherInfo"
            weather_params = {
                "key": "581efe867760a80877991ec818d94ad1",
                "city": adcode,
            }
            weather_resp = requests.get(weather_url, params=weather_params, timeout=5)
            print("天气预报响应:", weather_resp.json())
            if weather_resp.status_code == 200:
                weather_data = weather_resp.json()
                print("天气预报:", weather_data.get("lives"))
    else:
        print("获取位置信息失败:", resp.text)

    print("天气预报:", get_weather_info())
