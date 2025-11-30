# 电池状态
float32 battery_voltage          # 电池电压（单位：V）
float32 battery_percentage       # 电池剩余电量百分比（范围：0.0-100.0）
float32 battery_temperature      # 电池温度（可选，单位：摄氏度）

# 电机状态
int32 left_motor_speed           # 电机转速（单位：RPM）
int32 right_motor_speed          # 电机转速（单位：RPM）
float32 left_motor_temperature
float32 right_motor_temperature

# 系统状态
float32 cpu_usage                # CPU使用率（范围：0.0-100.0）
float32 memory_usage             # 内存占用率（范围：0.0-100.0）
float32  cpu_temperature          # CPU温度（单位：摄氏度）
float32 disk_space_percentage    # 磁盘剩余空间占比（范围：0.0-100.0）
float32 mainboard_temperature    # 主控板温度（单位：摄氏度）