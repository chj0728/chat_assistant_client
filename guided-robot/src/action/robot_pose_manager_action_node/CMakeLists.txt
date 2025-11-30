cmake_minimum_required(VERSION 3.8)
project(robot_pose_manager_action_node)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(ymrobot_msgs REQUIRED)

include_directories(
  include
)
include_directories(
        ${CMAKE_CURRENT_SOURCE_DIR}/include/robot_pose_manager_action_node
)

add_executable(robot_pose_manager_action_node src/robot_pose_manager_action_node.cpp)
ament_target_dependencies(robot_pose_manager_action_node rclcpp tf2 tf2_ros geometry_msgs ymrobot_msgs)

install(TARGETS
robot_pose_manager_action_node
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
