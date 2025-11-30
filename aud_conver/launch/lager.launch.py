from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    # 定义启动参数（可选）
    namespace = DeclareLaunchArgument(
        'namespace',
        default_value='',
        description='Namespace for all nodes in this launch file'
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


    # 返回 LaunchDescription 对象
    return LaunchDescription([
        namespace,
        audio_auto_node,
        audio_player_node_node,
    ])
