cmake_minimum_required(VERSION 3.8)
project(amr_behavior_tree)

# Default to C++14.
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

include_directories(/usr/local/include/yaml-cpp)

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rcl_interfaces REQUIRED)
find_package(behaviortree_cpp_v3 REQUIRED)
find_package(nav2_behavior_tree REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav2_msgs REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(tf2 REQUIRED)
find_package(yaml-cpp REQUIRED)
find_package(ymrobot_msgs REQUIRED)

include_directories(include)

set(DEPENDS
  rclcpp
  rcl_interfaces
  behaviortree_cpp_v3
  nav2_behavior_tree
  ymrobot_msgs
  tf2
  yaml-cpp
)

add_library(bt_tree_core impl/basic_types.cpp)
target_link_libraries(bt_tree_core behaviortree_cpp_v3 ${YAML_CPP_LIBRARIES})

ament_target_dependencies(bt_tree_core behaviortree_cpp_v3 ${YAML_CPP_LIBRARIES})

################################# ACTION #######################################ode)

add_library(say_something_node SHARED
    plugins/action/say_something_node.cpp)
list(APPEND plugin_libs say_something_node)

add_library(parse_task_node SHARED
    plugins/action/parse_task_node.cpp)
list(APPEND plugin_libs parse_task_node)

add_library(handle_nearby_point_node SHARED
    plugins/action/handle_nearby_point.cpp)
list(APPEND plugin_libs handle_nearby_point_node)

add_library(cloud_chassis_charge_node SHARED
    plugins/action/cloud_chassis_charge_node.cpp)
list(APPEND plugin_libs cloud_chassis_charge_node)

add_library(cloud_chassis_nav_node SHARED
    plugins/action/cloud_chassis_nav_node.cpp)
list(APPEND plugin_libs cloud_chassis_nav_node)

add_library(cloud_chassis_nav_name_node SHARED
    plugins/action/cloud_chassis_nav_name_node.cpp)
list(APPEND plugin_libs cloud_chassis_nav_name_node)

add_library(set_params_node SHARED
    plugins/action/set_params_node.cpp)
list(APPEND plugin_libs set_params_node)

add_library(remove_passed_mark_audios_node SHARED
    plugins/action/remove_passed_mark_audios_node.cpp)
list(APPEND plugin_libs remove_passed_mark_audios_node)

add_library(remove_passed_mark_points_node SHARED
    plugins/action/remove_passed_mark_points_node.cpp)
list(APPEND plugin_libs remove_passed_mark_points_node)

add_library(remove_passed_fixed_up_action_node SHARED
    plugins/action/remove_passed_fixed_up_action_node.cpp)
list(APPEND plugin_libs remove_passed_fixed_up_action_node)

add_library(traverse_guidance_node SHARED
    plugins/action/traverse_guidance_node.cpp)
list(APPEND plugin_libs traverse_guidance_node)

add_library(play_fixed_audio_node SHARED
    plugins/action/play_fixed_audio_node.cpp)
list(APPEND plugin_libs play_fixed_audio_node)

add_library(up_climb_fixed_action_node SHARED
    plugins/action/up_climb_fixed_action_node.cpp)
list(APPEND plugin_libs up_climb_fixed_action_node)

add_library(pub_up_climb_stop_node SHARED
    plugins/action/pub_up_climb_stop_node.cpp)
list(APPEND plugin_libs pub_up_climb_stop_node)

add_library(get_standby_point_node SHARED
    plugins/action/get_standby_point_node.cpp)
list(APPEND plugin_libs get_standby_point_node)

add_library(cloud_chassis_reposition_node SHARED
    plugins/action/cloud_chassis_reposition_node.cpp)
list(APPEND plugin_libs cloud_chassis_reposition_node)

add_library(voice_interaction SHARED
    plugins/action/voice_interaction.cpp)
list(APPEND plugin_libs voice_interaction)

add_library(publish_task_state_node SHARED
    plugins/action/publish_task_state_node.cpp)
list(APPEND plugin_libs publish_task_state_node)

add_library(remove_passed_is_skip_node SHARED
    plugins/action/remove_passed_is_skip_node.cpp)
list(APPEND plugin_libs remove_passed_is_skip_node)

add_library(on_site_inspection_node SHARED
    plugins/action/on_site_inspection_node.cpp)
list(APPEND plugin_libs on_site_inspection_node)

add_library(remove_passed_image_vedio_node SHARED
    plugins/action/remove_passed_image_vedio_node.cpp)
list(APPEND plugin_libs remove_passed_image_vedio_node)

add_library(video_camera_function_node SHARED
    plugins/action/video_camera_function_node.cpp)
list(APPEND plugin_libs video_camera_function_node)

add_library(play_fulled_audio_node SHARED
    plugins/action/play_fulled_audio_node.cpp)
list(APPEND plugin_libs play_fulled_audio_node)

add_library(increment_variable_node SHARED
    plugins/action/increment_variable_node.cpp)
list(APPEND plugin_libs increment_variable_node)

################################ CONDITION #####################################
add_library(need_index_node SHARED
    plugins/condition/need_index_node.cpp)
list(APPEND plugin_libs need_index_node)

add_library(condition_check_node SHARED
    plugins/condition/condition_check_node.cpp)
list(APPEND plugin_libs condition_check_node)

################################ CONTROL #######################################

################################ DECORATOR #####################################


################################################################################
foreach(bt_plugin ${plugin_libs})
  target_link_libraries(${bt_plugin} ${YAML_CPP_LIBRARIES})  # 添加这行
  ament_target_dependencies(${bt_plugin} ${DEPENDS})
  target_compile_definitions(${bt_plugin} PRIVATE BT_PLUGIN_EXPORT)
endforeach()

install(
  DIRECTORY include/
  DESTINATION include
)
install(
  TARGETS bt_tree_core ${plugin_libs}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(FILES amr_tree_nodes.xml DESTINATION
    share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_export_include_directories(include)
ament_export_libraries(bt_tree_core ${plugin_libs})
ament_export_dependencies(${DEPENDS})
ament_package()
