cmake_minimum_required(VERSION 3.8)
project(ymrobot_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_ros REQUIRED)
find_package(rosidl_default_generators REQUIRED)

find_package(rclcpp REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(nav_msgs REQUIRED)

set(msg_files
  "msg/Command.msg"
  "msg/Task.msg"
  "msg/TaskStatus.msg"
  "msg/TaskStatusCode.msg"
  "msg/RobotDeviceStatus.msg"
  "msg/Upper.msg"
  "msg/MapManage.msg"
  "msg/MapTaskCommand.msg"
  "msg/SlamCommand.msg"
  "msg/DotPoints.msg"
  "msg/NavPoint.msg"
  "msg/Movebase.msg"
  "msg/ControlMode.msg"
  "msg/DotPointsList.msg"
  "msg/CurrentPose.msg"
  "msg/BinaryData.msg"
  "msg/EmojiFixed.msg"
  "msg/UpdateList.msg"
  "msg/CloudChassisStatus.msg"
  "msg/LedShow.msg"
  "msg/CloudChassisMarkPoint.msg"
  "msg/CloudChassisMarkPointList.msg"
  "msg/GuideRoute.msg"
  "msg/BTNodeTaskState.msg"
  "msg/VoiceMessage.msg"
  "msg/ImageVideo.msg"
  "msg/WakeUpWordSetting.msg"
  "msg/PatrolMission.msg"
)

set(srv_files
    "srv/SlamTaskManage.srv"
    "srv/MapTaskManage.srv"
    "srv/DotPoint.srv"
    "srv/UpLimb.srv"
    "srv/EMOJI.srv"
    "srv/Audio.srv"
    "srv/MoveTarget.srv"
    "srv/CLoudNav.srv"
    "srv/LargeModelRequestTask.srv"
)

set(action_files
    "action/Recharge.action"
    "action/ArmControl.action"
    "action/AudioControl.action"
    "action/Relcation.action"
    "action/Relocalize.action"
    "action/LoadMap.action"
    "action/PlayMp3.action"
    "action/WaitElevator.action"
    "action/MoveElevator.action"
    "action/UpClimbAction.action"
    "action/DynamicFusParameters.action"
    "action/ResquestMoveFloor.action"
    "action/EnterOutElvatorResult.action"
    "action/ElevatorDetection.action"
    "action/PoseManager.action"
    "action/CloudChassisNav.action"
    "action/CloudChassisCharge.action"
    "action/SetParams.action"
    "action/GetCurrentTask.action"
    "action/CloudChassisNavReposition.action"
    "action/LogUpdate.action"
    "action/CameraFunction.action"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  ${action_files}
  DEPENDENCIES builtin_interfaces std_msgs nav_msgs
  ADD_LINTER_TESTS
)

ament_export_dependencies(rosidl_default_runtime)

ament_package()