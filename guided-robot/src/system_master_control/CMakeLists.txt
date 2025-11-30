cmake_minimum_required(VERSION 3.8)
project(system_master_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(executable_name system_master_control)

#指定头文件目录
# 添加头文件
include_directories(
  include
  #/usr/local/include
)
include_directories(
        ${CMAKE_CURRENT_SOURCE_DIR}/include/system_master_control
)
link_directories(${CMAKE_CURRENT_SOURCE_DIR}/lib)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(nav2_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(ymrobot_msgs REQUIRED)

add_executable(system_master_control src/system_master_control.cpp src/robot_device_status.cpp)
ament_target_dependencies(system_master_control rclcpp nav2_msgs   std_msgs  geometry_msgs tf2 tf2_ros ymrobot_msgs)

find_library(PAHO_MQTT_LIB paho-mqtt3as PATHS ${CMAKE_CURRENT_SOURCE_DIR}/lib)
find_library(PAHO_MQTTPP_LIB paho-mqttpp3 PATHS ${CMAKE_CURRENT_SOURCE_DIR}/lib)
target_link_libraries(${executable_name} ${PAHO_MQTT_LIB} ${PAHO_MQTTPP_LIB} fmt)

# target_link_libraries(${executable_name}
# ${CMAKE_CURRENT_SOURCE_DIR}/lib/libpaho-mqtt3as.so.1
#   ${CMAKE_CURRENT_SOURCE_DIR}/lib/libpaho-mqttpp3.so.1.2.0
#   fmt
# )

install(
  DIRECTORY lib/                       
  DESTINATION lib/${PROJECT_NAME}      
)
install(TARGETS
system_master_control
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
