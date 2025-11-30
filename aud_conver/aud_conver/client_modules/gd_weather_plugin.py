import requests
def get_weather(api_key='3559d6b41e7ae6de02b13f6bd031da3b', city_name = '太仓'):
    url = f'http://restapi.amap.com/v3/weather/weatherInfo'
    
    params = {
        'key': api_key,  # 你的高德API密钥
        'city': city_name,  # 城市名
        'extensions': 'base',  # 只获取基本天气信息
        'output': 'JSON'  # 返回JSON格式数据
    }

    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        weather_data = response.json()
        
        if weather_data['status'] == '1':
            # 获取天气信息
            city = weather_data['lives'][0]['city']
            temperature = weather_data['lives'][0]['temperature']
            weather = weather_data['lives'][0]['weather']
            wind_direction = weather_data['lives'][0]['winddirection']
            wind_power = weather_data['lives'][0]['windpower']
            now_weather = f'{city} 当前天气: {weather}, 温度: {temperature}°C, 风向: {wind_direction}风, 风力: {wind_power}级'
            
            # 输出当前天气情况
            return f'{city} 当前天气: {weather}, 温度: {temperature}°C, 风向: {wind_direction}风, 风力: {wind_power}级'
        else:
            return '天气查询失败，请检查城市名或API密钥'
    else:
        return '请求失败，请稍后再试'