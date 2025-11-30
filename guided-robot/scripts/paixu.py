import pandas as pd
import re

data = """
uint8 NONE                     = 0  # 无命令
uint8 REGISTER                 = 1  # 注册
uint8 LOG_OFF                  = 2  # 注销
uint8 PAUSE                    = 3  # 暂停操作
uint8 RESUME                   = 4  # 恢复操作
uint8 CANCLE                   = 5  # 取消任务操作
uint8 WAIT                     = 6  # 进入休眠模式
uint8 FINISH_WAIT              = 7  # 从休眠模式唤醒
uint8 CHARGE                   = 8  # 回冲
uint8 FINISH_CHARGE            = 9  # 结束回冲
uint8 BUILD_MAP                = 10 # 建图
uint8 UPLOAD_MAP               = 11 # 更新地图
uint8 DOWNLOAD_MAP             = 12 # 下载地图
uint8 SAVE_MAP                 = 13 # 保存地图
uint8 RELOCALIZE               = 14 # 重定位
uint8 NAVIGATION               = 15 # 导航
uint8 MULIT_POINTS_NAVIGATION  = 16 # 多点导航
uint8 MULIT_FLOOR_NAVIGATION   = 17 # 跨楼层导航（只适合单点）
uint8 DOT                      = 18 # 打点
uint8 CLOUD_NAVIGATION  = 19  # 云迹单点导航
uint8 CLOUD_MULIT_POINTS_NAVIGATION = 20 # 云迹多点导航
uint8 CLOUD_NAVIGATION_NAME = 21 # 云迹单点点位名称导航
uint8 CLOUD_MULIT_POINTS_NAVIGATION_NAME = 22 # 云迹多点点位名导航
uint8 MANUAL_CONTROL_MOVE      = 19 # 遥控控制移动
uint8 EXE_BEHAVIOR_TREE        = 20 # 执行行为树
uint8 PLACE_CARTESIAN          = 21 # 末端变化（笛卡尔坐标）导航
uint8 PLACE_JOINT              = 22 # 关节变化导航
uint8 PLACE_FIXED              = 23 # 上肢预设动作执行
uint8 PLACE_CONTROL_MODE       = 24 # 上肢控制模式切换
uint8 GRASP                    = 25 # 夹爪动作
uint8 CAMERA                   = 26 # 相机
uint8 PLAY_FIX_AUDIO           = 27 # 播放固定音频
uint8 SPEECH_2_TXT             = 28 # 语音转文字（在线和离线都有）
uint8 EXPRESSION_FIXED         = 29 # 表情预设执行动作
uint8 WAKE_UP                  = 30 # 唤醒
uint8 POWER_OFF                = 31 # 远程关机
"""

# 解析数据
rows = []
for line in data.strip().split('\n'):
    # 正则匹配关键字段
    match = re.match(r'(\w+)\s+(\w+)\s*=\s*(\d+)\s*#\s*(.+)', line)
    if match:
        dtype, name, num, comment = match.groups()
        comment = re.sub(r'\s*--.*', '', comment)  # 清理注释‌:ml-citation{ref="7" data="citationList"}
        rows.append([dtype, name, int(num), comment.strip()])

# 创建DataFrame并导出Excel
df = pd.DataFrame(rows, columns=["消息格式", "消息名", "序号", "注册名"])
df.to_excel("ros2_commands.xlsx", index=False)
