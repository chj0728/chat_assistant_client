import launch
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node  # 正确导入 Node

def generate_launch_description():
    return LaunchDescription([
        # 声明参数（参数传递方式在 ROS 2 中为 Python 脚本）
        DeclareLaunchArgument('head_serial_port', default_value='/dev/ttyCH341USB1', description='Head serial port'),
        DeclareLaunchArgument('left_hand_serial_port', default_value='/dev/ttyCH341USB0', description='Left hand serial port'),
        DeclareLaunchArgument('right_hand_serial_port', default_value='/dev/ttyCH341USB2', description='Right hand serial port'),
        
        # 启动音频检测和控制嘴巴
    #    Node(
    #        package='ymbot_basic_control',
    #        executable='ymbot_audio_detection',
    #        name='ymbot_audio_detection',
    #        output='screen'
    #     ),
        
        # 启动头部舵机
        Node(
            package='ymbot_basic_control',
            executable='ymbot_xiaoxue_face_expression',
            name='ymbot_xiaoxue_face_expression',
            output='screen'
        ),

        # 如果有需要，可以加入其它功能模块启动
        Node(
            package='ymbot_basic_control',
            executable='ymbot_xiaoxue_hands',
            name='ymbot_xiaoxue_hands',
            output='screen'
        ),

        # 你可以继续添加你需要的其它模块
        Node(
            package='ymbot_basic_control',
            executable='hello_moveit_node',
            name='hello_moveit_node',
            output='screen'
        ),
    ])
