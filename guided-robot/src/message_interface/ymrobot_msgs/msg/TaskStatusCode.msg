# Task status code from robot to platform
uint8   RUNNING     =   0   # 0x00  任务执行中
uint8   DONDE       =   1   # 0x01  任务已完成
uint8   SUCCEEDED   =   2   # 0x02  任务成功
uint8   ABORTED     =   3   # 0x03  任务失败
uint8   CANCLE      =   4   # 0x04  任务取消
uint8   HELD        =   5   # 0x05  任务挂起/任务等待
uint8   REFUSE      =   6   # 0x05  任务拒绝
uint8   NONE        =   7   # 0x06  当前没有任务
