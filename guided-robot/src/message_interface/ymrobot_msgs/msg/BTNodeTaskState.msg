# BTNodeState.msg
string task_id                    # 任务类型 -- 1. guide_explanation 类似行为树的任务类型
string task_type                    # 任务类型 -- 1. guide_explanation 类似行为树的任务类型
string node_name                    # 节点名称 导航、语音播报、拍照、录像
string node_task_state              # started, successed, failure, running
string node_task_error              # 错误代码
string node_task_error_message      # 错误描述
string node_action_content          # 动作内容