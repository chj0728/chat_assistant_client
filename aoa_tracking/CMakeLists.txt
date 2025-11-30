cmake_minimum_required(VERSION 3.8)
project(aoa_tracking)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(ymrobot_msgs REQUIRED)
find_package(serial REQUIRED)

add_executable(aoa_tracking_node src/aoa_tracking_node.cpp)
ament_target_dependencies(aoa_tracking_node rclcpp ymrobot_msgs serial)

install(TARGETS
    aoa_tracking_node
    DESTINATION lib/${PROJECT_NAME})

include_directories(
        ${CMAKE_CURRENT_SOURCE_DIR}/include/aoa_tracking
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
