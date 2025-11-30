cmake_minimum_required(VERSION 3.8)
project(cloud_water_chassis_node)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

include_directories(/usr/local/include/yaml-cpp)

# 查找 pkg-config
find_package(PkgConfig REQUIRED)
pkg_check_modules(ZeroMQ REQUIRED libzmq)

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(ymrobot_msgs REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(yaml-cpp REQUIRED)

#指定头文件目录
# 添加头文件
include_directories(
  include
)
include_directories(
        ${CMAKE_CURRENT_SOURCE_DIR}/include/cloud_water_chassis_node
)

add_executable(cloud_water_chassis_node src/cloud_water_chassis_node.cpp)
ament_target_dependencies(cloud_water_chassis_node rclcpp std_msgs ymrobot_msgs rclcpp_action yaml-cpp)

target_include_directories(cloud_water_chassis_node PRIVATE ${ZeroMQ_INCLUDE_DIRS})
target_link_libraries(cloud_water_chassis_node ${ZeroMQ_LIBRARIES} ${YAML_CPP_LIBRARIES})

install(TARGETS
cloud_water_chassis_node
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
