
# Task type constants
uint8   REG                 = 0  
uint8   TASK_GUIDANCE       = 1
uint8   BT_TASK             = 2
uint8   CHSSIS              = 3
uint8   CLOUD_CHASSIS       = 4  # 云迹底盘
uint8   UP_LIMB             = 5
uint8   MOVE                = 6
uint8   VIDEO_IMAGE         = 7
uint8   VOICE               = 8
uint8   HUMANOID            = 9
uint8   EMOJI_TASK          = 10
uint8   SYSTEM_MANAGEMENT   = 11 # 系统管理


string                platform_id
string                amr_id
string                task_id
uint8                 task_type   0
uint8                 control_mode
NavPoint[]            nav_points
Command[]             commands
string                behavior_tree   ""      # behavior tree, either .xml files or texts
bool                  reload          false   # force reload of behavior tree
string                index
BinaryData            binary_file