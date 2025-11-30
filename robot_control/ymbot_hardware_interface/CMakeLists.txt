cmake_minimum_required(VERSION 3.8)
project(ymbot_hardware_interface)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 查找依赖项
find_package(ament_cmake REQUIRED)
find_package(hardware_interface REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(ymbot_hardware_driver REQUIRED)
find_package(pal_statistics REQUIRED)


# 添加库
add_library(ymbot_hardware_interface SHARED
  src/ymbot_hardware_interface.cpp
)
# 设置目标编译特性
target_compile_features(ymbot_hardware_interface PUBLIC cxx_std_17)

# 设置包含目录
target_include_directories(ymbot_hardware_interface PUBLIC
  $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/ymbot_hardware_interface>
)

# 设置目标依赖项
ament_target_dependencies(ymbot_hardware_interface PUBLIC
  hardware_interface
  pluginlib
  rclcpp
  rclcpp_lifecycle
  ymbot_hardware_driver
)

# 导出插件描述文件
pluginlib_export_plugin_description_file(hardware_interface ymbot_hardware_interface.xml)

# 安装目标
install(
  TARGETS ymbot_hardware_interface
  EXPORT export_ymbot_hardware_interface
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
  RUNTIME DESTINATION bin
  INCLUDES DESTINATION include
)
# 安装包含目录
install(
  DIRECTORY include/
  DESTINATION include/ymbot_hardware_interface
)

# 导出依赖项、包含目录和库
ament_export_dependencies(
  hardware_interface
  pluginlib
  rclcpp
  rclcpp_lifecycle
  ymbot_hardware_driver
)
ament_export_include_directories(include)
ament_export_libraries(ymbot_hardware_interface)

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
