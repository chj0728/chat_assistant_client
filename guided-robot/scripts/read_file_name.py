import os

# 目标文件夹路径（需修改为实际路径）
folder_path = "/home/ymrobot/项目/唐伯虎配音0.8倍速"

# 获取所有文件名（不含路径）
file_names = os.listdir(folder_path)

# 处理文件名并写入txt
with open("output.txt", "w") as f:
    for name in file_names:
        # 去除文件扩展名
        if '.' in name and not name.startswith('.'):  # 排除隐藏文件
            clean_name = name[:name.rfind('.')]
        else:
            clean_name = name
        f.write(f"{clean_name}\n")
