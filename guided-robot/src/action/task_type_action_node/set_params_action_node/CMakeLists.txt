cmake_minimum_required(VERSION 3.8)
project(set_params_action_node)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

#指定头文件目录
# 添加头文件
include_directories(
  include
)
include_directories(
        ${CMAKE_CURRENT_SOURCE_DIR}/include/set_params_action_node
)
include_directories(/usr/local/include/yaml-cpp)

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(std_msgs REQUIRED)
find_package(ymrobot_msgs REQUIRED)
find_package(yaml-cpp REQUIRED)

add_executable(set_params_action_node src/set_params_action_node.cpp)
ament_target_dependencies(set_params_action_node rclcpp std_msgs ymrobot_msgs rclcpp_action yaml-cpp)
target_link_libraries(set_params_action_node
  ${YAML_CPP_LIBRARIES}
)
install(TARGETS
set_params_action_node
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}/
)
install(DIRECTORY
  config
  DESTINATION share/${PROJECT_NAME}/
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
