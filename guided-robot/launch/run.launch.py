import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    GroupAction,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import LoadComposableNodes
from launch_ros.actions import Node
from launch_ros.actions import PushRosNamespace
from launch_ros.descriptions import ComposableNode, ParameterFile
from nav2_common.launch import RewrittenYaml


def get_workspace_path() -> str:
    default_workspace = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    return os.environ.get("WORKSPACE", default_workspace)


def generate_launch_description():
    namespace = LaunchConfiguration("namespace")
    use_sim_time = LaunchConfiguration("use_sim_time")
    use_respawn = LaunchConfiguration("use_respawn")
    params_file = LaunchConfiguration("params_file")

    declare_namespace_cmd = DeclareLaunchArgument(
        "namespace",
        default_value="",
        description="Top-level namespace",
    )
    declare_use_sim_time_cmd = DeclareLaunchArgument(
        "use_sim_time",
        default_value="false",
        description="Use simulation (Gazebo) clock if true",
    )
    declare_use_respawn_cmd = DeclareLaunchArgument(
        "use_respawn",
        default_value="False",
        description="Whether to respawn if a node crashes.",
    )

    declare_params_file_cmd = DeclareLaunchArgument(
        "params_file",
        default_value=os.path.join(
            get_workspace_path(), "params", "nodes_xiugai.yaml"
        ),
        description="Full path to the ROS2 parameters file to use nodes",
    )

    # First action: cloud_water_chassis_node
    cloud_water_chassis = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("cloud_water_chassis_node"),
                "launch",
                "cloud_water_chassis_node.launch.py",
            )
        ),
        launch_arguments={
            "namespace": namespace,
            "use_sim_time": use_sim_time,
            "use_respawn": use_respawn,
            "params_file": params_file,
        }.items(),
    )

    # 定义 audio_auto 节点
    audio_auto_node = Node(
        package='aud_conver',
        executable='audio_auto',
        name='audio_auto',
        namespace=LaunchConfiguration('namespace'),
        output='screen',
        
    )

    # 定义 audio_player_node 节点
    audio_player_node_node = Node(
        package='aud_conver',
        executable='audio_player_node',
        name='audio_player_node',
        namespace=LaunchConfiguration('namespace'),
        output='screen'
    )

    # Remaining nodes grouped with a 2-second delay
    remaining_nodes = TimerAction(
        period=2.0,
        actions=[
            GroupAction(
                [
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(
                            os.path.join(
                                get_package_share_directory("system_master_control"),
                                "launch",
                                "system_master_control.launch.py",
                            )
                        ),
                        launch_arguments={
                            "namespace": namespace,
                            "use_sim_time": use_sim_time,
                            "use_respawn": use_respawn,
                            "params_file": params_file,
                        }.items(),
                    ),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(
                            os.path.join(
                                get_package_share_directory("up_climb_action_node"),
                                "launch",
                                "up_climb_action_node.launch.py",
                            )
                        ),
                        launch_arguments={
                            "namespace": namespace,
                            "use_sim_time": use_sim_time,
                            "use_respawn": use_respawn,
                            "params_file": params_file,
                        }.items(),
                    ),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(
                            os.path.join(
                                get_package_share_directory("set_params_action_node"),
                                "launch",
                                "set_params_action_node.launch.py",
                            )
                        ),
                        launch_arguments={
                            "namespace": namespace,
                            "use_sim_time": use_sim_time,
                            "use_respawn": use_respawn,
                            "params_file": params_file,
                        }.items(),
                    ),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(
                            os.path.join(
                                get_package_share_directory("task_guidance"),
                                "launch",
                                "task_guidance.launch.py",
                            )
                        ),
                        launch_arguments={
                            "namespace": namespace,
                            "use_sim_time": use_sim_time,
                            "use_respawn": use_respawn,
                            "params_file": params_file,
                        }.items(),
                    ),
                ]
            )
        ]
    )

    ld = LaunchDescription()
    ld.add_action(declare_namespace_cmd)
    ld.add_action(declare_use_sim_time_cmd)
    ld.add_action(declare_use_respawn_cmd)
    ld.add_action(declare_params_file_cmd)
    ld.add_action(cloud_water_chassis)
    # ld.add_action(audio_auto_node)
    # ld.add_action(audio_player_node_node)
    ld.add_action(remaining_nodes)

    return ld