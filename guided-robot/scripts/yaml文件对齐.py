import ruamel.yaml

def format_yaml_with_aligned_comments(file_path):
    yaml = ruamel.yaml.YAML()
    yaml.preserve_quotes = True  # 保留引号

    # 读取 YAML 文件
    with open(file_path, 'r', encoding='utf-8') as file:
        data = yaml.load(file)

    # 将 YAML 数据转换为字符串
    from io import StringIO
    string_stream = StringIO()
    yaml.dump(data, string_stream)
    yaml_str = string_stream.getvalue()

    # 按行分割
    lines = yaml_str.splitlines()

    # 计算每行的键值对部分的最大长度
    max_length = 0
    for i, line in enumerate(lines):
        if '#' in line:
            key_value_part, comment = line.split('#', 1)
            key_value_length = len(key_value_part.rstrip())
            if key_value_length > max_length:
                max_length = key_value_length

    # 对齐注释
    formatted_lines = []
    for line in lines:
        if '#' in line:
            key_value_part, comment = line.split('#', 1)
            key_value_part = key_value_part.rstrip()
            # 填充空格，使注释对齐到固定列
            formatted_line = f"{key_value_part.ljust(max_length)}  # {comment.strip()}"
            formatted_lines.append(formatted_line)
        else:
            formatted_lines.append(line)

    # 将格式化后的行重新组合为字符串
    formatted_yaml = '\n'.join(formatted_lines)

    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(formatted_yaml)

    print("YAML 文件已格式化对齐并保存，注释已对齐。")

# 示例 YAML 文件路径
yaml_file_path = '/home/ymrobot/ros2_ws/controller_driver.yaml'

# 格式化 YAML 文件
format_yaml_with_aligned_comments(yaml_file_path)