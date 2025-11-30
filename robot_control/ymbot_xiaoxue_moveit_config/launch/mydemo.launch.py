from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from moveit_configs_utils import MoveItConfigsBuilder
from moveit_configs_utils.launches import generate_demo_launch


def generate_launch_description():
    # Load SRDF file manually
    srdf_file_path = PathJoinSubstitution(
        [FindPackageShare("ymbot_xiaoxue_moveit_config"), "config", "ymbot_xiaoxue_description.srdf"]
    )

    # Load SRDF content
    with open(srdf_file_path.perform(None), 'r') as f:
        srdf_content = f.read()

    # Build MoveIt config
    moveit_config = MoveItConfigsBuilder("ymbot_xiaoxue_description", package_name="ymbot_xiaoxue_moveit_config").to_moveit_configs()

    # Generate demo launch
    demo_launch = generate_demo_launch(moveit_config)

    # Add SRDF parameter
    demo_launch.append(Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            {"robot_description_semantic": srdf_content}
        ]
    ))

    return LaunchDescription(demo_launch)