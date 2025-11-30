from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    config_file_path = os.path.join(
        get_package_share_directory('pedestrian_detector_node'),
        'config',
        'pedestrian_detector_node.yaml'
    )
    return LaunchDescription([
        Node(
            package='pedestrian_detector_node',
            executable='pedestrian_detector_node',
            name='pedestrian_detector_node',
            parameters=[{'config_file': config_file_path}],
            output='screen'
        ),
    ])
