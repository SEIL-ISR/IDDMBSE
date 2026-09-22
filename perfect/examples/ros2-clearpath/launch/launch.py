import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


NAMESPACE = "a200_0000"

def generate_launch_description():
    use_rviz = LaunchConfiguration('use_rviz')
    declare_use_rviz_cmd = DeclareLaunchArgument(
        'use_rviz',
        default_value='True',
        description='Whether to start RVIZ')
    nav2_params = LaunchConfiguration("nav2_params")
    setup_path = LaunchConfiguration("setup_path")

    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('clearpath_gz'),
                'launch/simulation.launch.py',
            )
        ),
        launch_arguments=[("setup_path", setup_path)],
    )
    viz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('clearpath_viz'),
                'launch/view_navigation.launch.py',
            )
        ),
        condition=IfCondition(use_rviz),
        launch_arguments=[("namespace", NAMESPACE)],
    )
    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('clearpath_nav2_demos'),
                'launch/localization.launch.py',
            )
        ),
        launch_arguments=[("setup_path", setup_path), ("use_sim_time", "true")],
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('clearpath_nav2_demos'),
                'launch/nav2.launch.py',
            )
        ),
        launch_arguments=[("nav2_params", nav2_params), ("setup_path", setup_path), ("use_sim_time", "true")],
    )
    return LaunchDescription([
        declare_use_rviz_cmd,
        simulation,
        viz,
        localization,
        nav2,
    ])
