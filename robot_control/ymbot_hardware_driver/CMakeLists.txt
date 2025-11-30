cmake_minimum_required(VERSION 3.8)
project(ymbot_hardware_driver)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 查找依赖
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)

# 获取系统架构类型
if(CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64")
  set(LIBRARY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/lib_x86_64)
elseif(CMAKE_SYSTEM_PROCESSOR STREQUAL "aarch64")
  set(LIBRARY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/lib_arm)
else()
  message(WARNING "Unknown system architecture: ${CMAKE_SYSTEM_PROCESSOR}. Defaulting to x86_64 libraries.")
  set(LIBRARY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/lib_x86_64)  # 默认使用 x86_64 库
endif()

# 创建库，只调用一次 add_library
add_library(ymbot_hardware_driver SHARED 
  src/ymbot_joint_eu.cpp
  src/ymbot_head_RTrobot_api.cpp
  src/ymbot_hands_RTrobot_api.cpp
)


# 设置头文件路径
target_include_directories(ymbot_hardware_driver PUBLIC include)

# 链接第三方库
target_link_libraries(ymbot_hardware_driver PUBLIC ${LIBRARY_DIR}/libeu_planet.so)

# 设置依赖
ament_target_dependencies(ymbot_hardware_driver)

# 安装头文件
install(DIRECTORY include/
  DESTINATION include
)

# 安装第三方库
install(DIRECTORY ${LIBRARY_DIR}/
  DESTINATION lib
)

# 安装库
install(TARGETS ymbot_hardware_driver
  EXPORT export_ymbot_hardware_driver
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
  RUNTIME DESTINATION bin
)

# 导出 CMake 配置
ament_export_include_directories(include)
ament_export_libraries(ymbot_hardware_driver ${LIBRARY_DIR}/libeu_planet.so)
ament_export_libraries(ymbot_hardware_driver)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # 跳过版权检查（如果文件中未包含版权和许可证）
  set(ament_cmake_copyright_FOUND TRUE)
  # 跳过 cpplint（仅适用于 Git 仓库）
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()

