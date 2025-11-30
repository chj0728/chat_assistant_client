import pandas as pd

# def excel_to_rosmsg(input_excel: str, output_txt: str):
#     # 读取Excel数据并校验格式
#     try:
#         df = pd.read_excel(input_excel, usecols=["消息格式", "消息名", "序号", "注册名"])
#     except KeyError as e:
#         raise ValueError(f"Excel缺少必要列: {e}") from None
    
#     # 生成消息行
#     msg_lines = []
#     for _, row in df.iterrows():
#         line = f"{row['消息格式']} {row['消息名']} = {row['序号']} # {row['注册名']}"
#         msg_lines.append(line)
    
#     # 写入文件
#     with open(output_txt, 'w', encoding='utf-8') as f:
#         f.write('\n'.join(msg_lines))
        
def excel_to_rosmsg(input_excel: str, output_txt: str):
    df = pd.read_excel(input_excel)
    
    # 动态计算列宽‌:ml-citation{ref="3" data="citationList"}
    type_width = max(len(str(t)) for t in df['消息格式']) + 1  # uint8固定可设5
    name_width = max(len(n) for n in df['消息名']) + 2
    num_width = 4  # 序号最大值位数+1
    
    # 格式化模板‌:ml-citation{ref="2" data="citationList"}
    template = (f"{{:{type_width}}}"  # 消息格式
                f"{{:{name_width}}}"  # 消息名
                "= {:<3}"            # 序号
                "# {:<}")            # 注册名

    with open(output_txt, 'w', encoding='utf-8') as f:
        for row in df.itertuples():
            line = template.format(
                row.消息格式, 
                row.消息名, 
                row.序号, 
                row.注册名
            )
            f.write(line + '\n')


# 使用示例
excel_to_rosmsg("/home/ymrobnot/ros2_ws_guidance/ros2_commands.xlsx", "output.msg")
