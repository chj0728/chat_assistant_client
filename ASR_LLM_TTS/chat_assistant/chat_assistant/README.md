# chat_assistant 节点说明

本文档面向后续开发者，简要说明当前 chat_assistant 节点里 ROS 服务、话题发布、话题订阅和 Agent tool 的组织方式，方便后续维护和扩展。

## 1. 模块职责

当前节点已经按职责拆成 4 个模块：

- [`chat_assistant_node.py`](chat_assistant_node.py)
  节点入口，只负责把 Node、ROS 接口注册器和处理逻辑组装起来，并启动主循环。
- [`node_interfaces.py`](node_interfaces.py)
  ROS 接口定义和注册逻辑，包括配置对象、服务/发布/订阅规格表，以及统一的创建和重置流程。
- [`node_handlers.py`](node_handlers.py)
  服务处理函数、订阅回调、状态维护和主循环里的发布逻辑。
- [`node_tools.py`](node_tools.py)
  LangChain tool 和动态 middleware。

简要说明：

- 接口长什么样：查看 [`node_interfaces.py`](node_interfaces.py)
- 接口收到数据后做什么：查看 [`node_handlers.py`](node_handlers.py)
- 节点怎么启动和串起来：查看 [`chat_assistant_node.py`](chat_assistant_node.py)
- Agent 可以额外调用哪些工具：查看 [`node_tools.py`](node_tools.py)

## 2. 节点整体流程

chat_assistant_node 启动后主要做 4 件事：

1. 创建 ROS 节点对象 ChatAssistantNode。
2. 初始化 RosInterfaceRegistry，加载 ROS 配置并创建服务、发布者、订阅者。
3. 初始化 ChatAssistant 核心对象，并注入 dynamic_middlewares。
4. 在主循环中持续处理状态、队列和工具事件，把结果发布到对应话题。

## 3. 可用服务

服务定义集中在 [`node_interfaces.py`](node_interfaces.py) 的 SERVICE_SPECS 中，实际处理逻辑在 [`node_handlers.py`](node_handlers.py) 的 ChatAssistantServiceHandlersMixin 中。

### 状态控制类服务

- reload_config
  重新加载配置，并重建相关 ROS topic 接口。
- activate_assistant
  同时激活 LLM 和 TTS。
- idle_assistant
  同时停用 LLM 和 TTS。
- activate_asr / idle_asr
  激活或停用 ASR。
- activate_llm / idle_llm
  激活或停用 LLM。
- activate_tts / idle_tts
  激活或停用 TTS。

### 推理类服务

- asr_infer
  输入音频路径，只做 ASR 识别。
- llm_infer
  输入文本，只做 LLM 生成。
- tts_infer
  输入文本分片，只做 TTS 播放。
- tts_generate_wav
  输入文本和保存路径，生成 wav 文件。
- chat_assistant_infer
  输入文本，走一次完整的聊天处理流程。

### 运行辅助类服务

- play_audio_file
  直接播放一个音频文件。
- interrupt_audio
  打断当前播放。
- delete_user_context
  删除指定用户的上下文。

## 4. 发布话题

发布者定义集中在 [`node_interfaces.py`](node_interfaces.py) 的 PUBLISHER_SPECS 中。

- asr_publish_topic
  发布 ASR 识别结果，消息类型为 String。
- llm_publish_topic
  发布 LLM 输出结果，消息类型为 LLMResponse。
- response_publish_topic
  发布一次完整交互的结果，消息类型为 Response。
- tts_active_topic
  发布当前 TTS 是否处于播放状态，消息类型为 Bool。
- resolved_user_name_topic
  发布解析后的用户名，消息类型为 String。

这些话题名称来自 NodeRosConfig，对应值来自 [`config.yaml`](../config/config.yaml) 的 `ros_cfg` 字段，通常改配置即可，不需要改业务逻辑。

## 5. 订阅话题

订阅者定义集中在 [`node_interfaces.py`](node_interfaces.py) 的 SUBSCRIPTION_SPECS 中。

- user_id_subscribe_topic
  接收当前用户 ID。
- user_face_subscribe_topic
  接收当前是否检测到人脸。

订阅回调在 [`node_handlers.py`](node_handlers.py) 的 ChatAssistantTopicHandlersMixin 中：

- handle_user_id
  更新当前用户 ID。
- handle_user_face
  更新当前人脸状态。

节点内部还会根据超时时间自动把旧状态判定为失效，避免一直使用过期数据。

## 6. 主循环

主循环的入口是 `process_runtime_once`，定义在 [`node_handlers.py`](node_handlers.py) 的 ChatAssistantStateHandlersMixin 中。

每次循环主要做这些事情：

1. 处理工具事件队列。
2. 检查用户 ID 是否过期。
3. 检查人脸状态是否过期。
4. 如果 ASR 队列里有新结果，发布到 ASR 话题。
5. 如果 LLM 队列里有新结果，发布到 LLM 话题。
6. 如果完整响应队列里有新结果，发布到综合响应话题。
7. 发布当前 TTS 状态。
8. 如果有解析后的用户名，发布出去。

- ChatAssistant 核心对象专注处理业务。
- ROS 节点专注对外通信。
- 两边通过队列解耦，后续更容易替换实现。

## 7. 配置从哪里来

ROS 相关配置统一收敛为 NodeRosConfig，定义在 [`node_interfaces.py`](node_interfaces.py) 中。

它负责管理这些配置项：

- 发布话题名
- 订阅话题名
- 用户 ID 过期时间
- 人脸状态过期时间

RosInterfaceRegistry 初始化时会读取 ros_cfg，并通过 NodeRosConfig.from_mapping 转成一个明确的配置对象，然后据此创建接口。

- 配置项集中，不容易漏。
- IDE 更容易补全和跳转。
- 后续新增配置项时更容易维护。

## 8. 如何新增一个服务

推荐按下面顺序改：

1. 在 [`node_handlers.py`](node_handlers.py) 里增加对应的回调函数。
2. 在 [`node_interfaces.py`](node_interfaces.py) 的 SERVICE_SPECS 里增加一条 ServiceSpec。
3. 如果需要新的 callback group，再在 RosInterfaceRegistry 中准备对应成员。
4. 重启节点后验证。

如果只是普通服务，通常只需要前两步。

## 9. 如何新增一个发布话题

推荐按下面顺序改：

1. 在 [`node_interfaces.py`](node_interfaces.py) 的 NodeRosConfig 中增加配置字段。
2. 在 PUBLISHER_SPECS 中增加一条 PublisherSpec。
3. 在 [`node_handlers.py`](node_handlers.py) 的主循环或相关处理函数里补发布逻辑。
4. 在配置文件 [`config.yaml`](../config/config.yaml) 的 `ros_cfg` 字段中补上可选配置项。

## 10. 如何新增一个订阅话题

推荐按下面顺序改：

1. 在 [`node_handlers.py`](node_handlers.py) 的 ChatAssistantTopicHandlersMixin 中增加订阅回调。
2. 在 [`node_interfaces.py`](node_interfaces.py) 的 NodeRosConfig 中增加对应配置字段。
3. 在 SUBSCRIPTION_SPECS 中增加一条 SubscriptionSpec。
4. 如果这个状态会过期，再补对应的超时处理逻辑。

## 11. 如何新增一个 Agent tool

Agent 相关工具统一放在 [`node_tools.py`](node_tools.py) 中。

新增步骤：

1. 在 [`node_tools.py`](node_tools.py) 中增加一个 @tool 函数。
2. 如果需要主循环处理额外动作，可以把事件写入 tool_event_queue。
3. 在 DynamicToolMiddleware.wrap_model_call 中把新 tool 加入 tools 列表。
4. 在 wrap_tool_call 中按名称绑定到具体实现。
5. 如果需要节点真正执行动作，再到 [`node_handlers.py`](node_handlers.py) 的 handle_tool_events 中补处理逻辑。

## 12. 开发建议

- 新增 ROS 接口时，优先改规格表，不要直接在节点类里手写 create_service 或 create_publisher。
- 新增业务逻辑时，优先放到 [`node_handlers.py`](node_handlers.py) 对应的处理类里，不要直接在节点类里写回调函数。
- 如果修改 ros_cfg 中的 topic 名称或超时配置，优先通过 reload_config 验证是否符合预期。
- 如果发现重复订阅、重复发布的问题，优先检查是否绕过了统一的 `_create_topic_interfaces` 和 `_destroy_topic_interfaces` 流程。
