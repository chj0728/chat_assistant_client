# launch/robot_state_publisher.launch.py
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import Command

def generate_launch_description():
    package_name = 'ymbot_xiaoxue_description'
    package_path = get_package_share_directory(package_name)

    # 加载 URDF 文件
    urdf_file = os.path.join(package_path, 'urdf', 'ymbot_xiaoxue_description.urdf')
    with open(urdf_file, 'r') as f:
        robot_description = f.read()

    # # 或者使用 Xacro 文件
    # xacro_file = os.path.join(package_path, 'xacro', 'your_robot.urdf.xacro')
    # robot_description = Command(['xacro ', xacro_file])

    # 启动 robot_state_publisher
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': robot_description}]
    )

    rviz2_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        )
    
    joint_state_publisher_node = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        parameters=[{'robot_description': robot_description}]
        )
    return LaunchDescription([
        robot_state_publisher_node,
        joint_state_publisher_node,
        rviz2_node
    ])