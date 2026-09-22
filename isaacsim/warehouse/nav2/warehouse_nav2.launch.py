# Nav2 for the Nova Carter in the cluttered Isaac Sim warehouse.
#
# nav2_bringup's bringup_launch.py (AMCL + the Nav2 servers, lifecycle-managed,
# autostarted) with nav2_params.yaml and maps/carter_warehouse_clutter.yaml, plus
# pointcloud_to_laserscan deriving /scan from the Carter's XT-32 point cloud
# /front_3d_lidar/lidar_points in base_link over the map's height band
# (0.1-0.62 m). Everything runs on the simulation clock.
#
#   ros2 launch nav2/warehouse_nav2.launch.py
#   ros2 launch nav2/warehouse_nav2.launch.py map:=/path/to/other.yaml
#
# Adapted from the Nav2 bringup of the authors' C-BASE workspace (2026), which
# follows NVIDIA's Isaac Sim ROS 2 navigation tutorial.

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

HERE = os.path.dirname(os.path.abspath(__file__))


def generate_launch_description():
    bringup = get_package_share_directory("nav2_bringup")
    use_sim_time = LaunchConfiguration("use_sim_time")

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup, "launch", "bringup_launch.py")),
        launch_arguments={
            "map": LaunchConfiguration("map"),
            "params_file": LaunchConfiguration("params_file"),
            "use_sim_time": use_sim_time,
            "autostart": "true",
        }.items(),
    )

    scan = Node(
        package="pointcloud_to_laserscan",
        executable="pointcloud_to_laserscan_node",
        name="pointcloud_to_laserscan",
        remappings=[("cloud_in", "/front_3d_lidar/lidar_points"), ("scan", "/scan")],
        parameters=[{
            "use_sim_time": use_sim_time,
            "target_frame": "base_link",
            "transform_tolerance": 0.01,
            "min_height": 0.1,
            "max_height": 0.62,
            "angle_min": -3.141592653589793,
            "angle_max": 3.141592653589793,
            "angle_increment": 0.008726646259971648,
            "scan_time": 0.0333,
            "range_min": 0.2,
            "range_max": 100.0,
            "use_inf": True,
        }],
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("map", default_value=os.path.join(HERE, "maps", "carter_warehouse_clutter.yaml")),
        DeclareLaunchArgument("params_file", default_value=os.path.join(HERE, "nav2_params.yaml")),
        nav2,
        scan,
    ])
