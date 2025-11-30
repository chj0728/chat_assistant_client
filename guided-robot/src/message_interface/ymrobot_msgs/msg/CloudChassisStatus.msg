# 云迹底盘状态信息msg
bool    charge_state        # 充电状态
bool    soft_estop_state    # 软急停状态 true->急停中，false->非急停中
bool    hard_estop_state    # 硬急停状态 true->急停中，false->非急停中
bool    estop_state         # 急停状态 true->急停中，false->非急停中
uint8   power_percent       # 电量百分比
float64 x                   # 当前位置x
float64 y                   # 当前位置y
float64 yaw                 # 当前位置yaw
uint8   current_floor       # 当前楼层  --  当前地图
uint8   error_code          # 错误码
string  move_target         # 导航目标点
string  move_status         # 导航状态
string  running_status      # 机器人运行状态
string  target_floor        # 目标楼层   -- 目标地图