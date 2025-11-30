cmake_minimum_required(VERSION 3.8)
project(ymbot_basic_control)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 查找并包含 ROS2 包
find_package(moveit_ros_planning_interface REQUIRED)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(ymbot_hardware_driver REQUIRED)
find_package(std_msgs REQUIRED)
find_package(PythonLibs 3 REQUIRED)
find_package(ymrobot_msgs REQUIRED)

# find_package(launch_ros REQUIRED)
# find_package(launch REQUIRED)

# 创建可执行文件
add_executable(ymbot_joint_eu_keyboard_multiple_canables src/ymbot_joint_eu_keyboard_multiple_canables.cpp)
add_executable(ymbot_xiaoxue_face_expression src/ymbot_xiaoxue_face_expression.cpp)
add_executable(ymbot_xiaoxue_hands src/ymbot_xiaoxue_hands.cpp)
add_executable(ymbot_audio_detection src/ymbot_audio_detection.cpp)
add_executable(hello_moveit_node src/hello_moveit.cpp)
add_executable(ymbot_neck_contorl src/ymbot_neck_contorl.cpp)
# 添加新的可执行文件
# add_executable(ymbot_head_RTrobot_api src/ymbot_head_RTrobot_api.cpp)

# 设置目标的依赖项
ament_target_dependencies(ymbot_joint_eu_keyboard_multiple_canables PUBLIC
  rclcpp
  ymbot_hardware_driver
  std_msgs
  ymrobot_msgs
)

ament_target_dependencies(ymbot_neck_contorl PUBLIC
  rclcpp
  ymbot_hardware_driver
  std_msgs
  ymrobot_msgs
)

ament_target_dependencies(ymbot_xiaoxue_face_expression PUBLIC
  rclcpp
  ymbot_hardware_driver
  std_msgs
  ymrobot_msgs
)

ament_target_dependencies(ymbot_xiaoxue_hands PUBLIC
  rclcpp
  ymbot_hardware_driver
  std_msgs
  ymrobot_msgs
)

ament_target_dependencies(ymbot_audio_detection PUBLIC
  rclcpp
  ymbot_hardware_driver
  std_msgs
  ymrobot_msgs
)

ament_target_dependencies(hello_moveit_node PUBLIC
  rclcpp
  std_msgs
  ymrobot_msgs
  moveit_ros_planning_interface
  ymbot_hardware_driver  # 如果实际需要硬件驱动支持
)


# ament_target_dependencies(ymbot_head_RTrobot_api PUBLIC
#   rclcpp
#   ymbot_hardware_driver
#   std_msgs
# )

# 包含头文件目录
include_directories(
  include
  ${ymrobot_msgs_INCLUDE_DIRS}
  ${ymbot_hardware_driver_INCLUDE_DIRS}  # 确保包含依赖包的头文件路径
)

# 安装可执行文件
install(TARGETS 
  ymbot_joint_eu_keyboard_multiple_canables
  ymbot_xiaoxue_face_expression
  ymbot_xiaoxue_hands
  ymbot_audio_detection
  hello_moveit_node
  ymbot_neck_contorl
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
