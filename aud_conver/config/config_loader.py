import os
import yaml



def get_project_dir():
    """获取项目根目录"""
    return os.path.dirname(os.path.abspath(__file__)) 


def read_config():
    config_path = os.path.join(get_project_dir(),"conversation.yaml")
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    return config


def load_config():
    """加载配置文件"""
    # 加载默认配置
    config = read_config()
    # 初始化目录
    return config

def write_timbre(prefix,voice_id):
    config_path = os.path.join(get_project_dir(), "conversation.yaml")
    config = read_config()
    # 2. 确保 TIMBRE 和 ALI 结构存在
    if 'TIMBRE' not in config:
        config['TIMBRE'] = {}
    if 'Ali' not in config['TIMBRE']:
        config['TIMBRE']['Ali'] = {}

    # 3. 写入新音色
    config['TIMBRE']['Ali'][prefix] = voice_id

    # 4. 写回文件
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(config, file, allow_unicode=True, default_flow_style=False, indent=2)


