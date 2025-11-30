uint8 NONE                                = 0  # 无命令
uint8 REGISTER                            = 1  # 注册
uint8 LOG_OFF                             = 2  # 注销
uint8 PAUSE                               = 3  # 暂停操作
uint8 RESUME                              = 4  # 恢复操作
uint8 CANCLE                              = 5  # 取消任务操作
uint8 WAIT                                = 6  # 进入休眠模式
uint8 FINISH_WAIT                         = 7  # 从休眠模式唤醒
uint8 CHARGE                              = 8  # 回冲
uint8 FINISH_CHARGE                       = 9  # 结束回冲
uint8 BUILD_MAP                           = 10 # 建图
uint8 UPLOAD_MAP                          = 11 # 更新地图
uint8 DOWNLOAD_MAP                        = 12 # 下载地图
uint8 SAVE_MAP                            = 13 # 保存地图
uint8 RELOCALIZE                          = 14 # 重定位
uint8 NAVIGATION                          = 15 # 导航
uint8 MULIT_POINTS_NAVIGATION             = 16 # 多点导航
uint8 MULIT_FLOOR_NAVIGATION              = 17 # 跨楼层导航（只适合单点）
uint8 DOT                                 = 18 # 打点
uint8 CLOUD_NAVIGATION                    = 19 # 云迹单点导航
uint8 CLOUD_MULIT_POINTS_NAVIGATION       = 20 # 云迹多点导航
uint8 CLOUD_NAVIGATION_NAME               = 21 # 云迹单点点位名称导航
uint8 CLOUD_MULIT_POINTS_NAVIGATION_NAME  = 22 # 云迹多点点位名导航
uint8 MANUAL_CONTROL_MOVE                 = 23 # 遥控控制移动
uint8 EXE_BEHAVIOR_TREE                   = 24 # 执行行为树
uint8 PLACE_CARTESIAN                     = 25 # 末端变化（笛卡尔坐标）导航
uint8 PLACE_JOINT                         = 26 # 关节变化导航
uint8 PLACE_FIXED                         = 27 # 上肢预设动作执行
uint8 PLACE_CONTROL_MODE                  = 28 # 上肢控制模式切换
uint8 GRASP                               = 29 # 夹爪动作
uint8 CAMERA                              = 30 # 相机 -- 录制视频
uint8 PLAY_FIX_AUDIO                      = 31 # 播放固定音频
uint8 TXT_2_AUDIO                         = 32 # 文字合成语音
uint8 SPEECH_2_TXT                        = 33 # 语音转文字（在线和离线都有）
uint8 EXPRESSION_FIXED                    = 34 # 表情预设执行动作
uint8 WAKE_UP                             = 35 # 唤醒
uint8 POWER_OFF                           = 36 # 远程关机
uint8 SETTING_PARAMETERS                  = 37 # 设置参数
uint8 SYNTHETIC_AUDIO                     = 38 # 删掉固定音频
uint8 VOICE_INTERACTION_FUNCTION_SWITCH   = 39 # 启动/关闭 语音交互功能开关
uint8 UPLOAD_VOICE_CONVERSATION_LOGS      = 40 # 上传语音对话日志
uint8 UPLOAD_OPERATION_LOGS               = 41 # 上传运行日志
uint8 PLAY_ONLINE_AUDIO                   = 42 # 播放在线音频
uint8 PHOTOGRAPH                          = 43 # 相机 -- 拍照

uint8       code           # 命令代码
string      params_code    # 命令参数
string[]    params         # 命令的参数值