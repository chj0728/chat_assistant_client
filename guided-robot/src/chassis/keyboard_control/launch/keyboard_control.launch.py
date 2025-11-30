import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.descriptions import ParameterFile
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml, ReplaceString
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    package_dir = get_package_share_directory("keyboard_control")

    namespace = LaunchConfiguration("namespace")
    params_file = LaunchConfiguration("params_file")
    use_sim_time = LaunchConfiguration("use_sim_time")

    param_substitutions = {'use_sim_time': use_sim_time}

    declare_namespace_cmd = DeclareLaunchArgument(
        "namespace",
        default_value="",
        description="Top-level namespace for the node",
    )

    configured_params = ParameterFile(
        RewrittenYaml(
            source_file=params_file,
            root_key=namespace,
            param_rewrites=param_substitutions,
            convert_types=True),
        allow_substs=True)

    declare_params_file_cmd = DeclareLaunchArgument(
        "params_file",
        default_value=os.path.join(
            package_dir, "config", "keyboard_control.yaml"
        ),
        description="Full path to the ROS2 parameters file",
    )

    declare_use_sim_time_cmd = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation (Gazebo) clock if true')


    task_guidance_node = Node(
        package="keyboard_control",
        executable="keyboard_control",
        namespace=namespace,
        parameters=[configured_params],
        output="screen",
        respawn=True,
    )

    # 返回 LaunchDescription
    return LaunchDescription([
        declare_namespace_cmd,  
        declare_params_file_cmd, 
        declare_use_sim_time_cmd,
        task_guidance_node,      
    ])
