# ROS 1 configuration for the SEIL-R1 Husky stack

These are the launch, parameter and URDF files the SysML trade studies ran against in
2023-24. The stack is **ROS 1**, `move_base` plus `rtabmap`, on a Clearpath-Husky-derived
platform (SEIL-R1). It is a different and earlier stack from the ROS 2 work in
`seil-r2/`.

They are copies of what was on the robot workspace at the time, kept here because the
SysML model's design variables map directly onto them: `sensor.yaml` is the file the
sensor trade study rewrites, and the `domain`, `base_global_planner` and
`base_local_planner` arguments of `navigation.launch` are the three design variables of
the ROS-launch trade study.

Nothing here has been built or launched on this workstation.

## What they expect

The files reference ROS 1 packages that are **not** in this repository:

| package | used for |
|---|---|
| `hardware_description` | the URDF tree; `sensors.urdf.xacro` loads `$(find hardware_description)/config/sensor.yaml` and includes the sensor mount xacros from `$(find hardware_description)/urdf/sensors/...` |
| `hardware_navigation` | `navigation.launch` includes `$(find hardware_navigation)/launch/rtabmap_slam.launch`, which is where the move_base and planner parameter files below are loaded |
| `hardware_launch` | the workspace path the MATLAB bridge POSTs (`$AUTO_STACK_WS/src/hardware_launch/launch/navigation_rosbridge.launch`), a rosbridge-enabled sibling of `navigation.launch` that is not in the drop |
| `hardware_viz` | the RViz config (`rviz/robot.rviz`) |
| `cpr_inspection_gazebo`, `cpr_agriculture_gazebo`, `cpr_orchard_gazebo`, `cpr_playpen_gazebo` | the four Clearpath simulation worlds, one per `domain` value |
| `cpr_robot_customizer`, `realsense`, `urg_node` | sensor xacros included by `sensors.urdf.xacro` |

The workspace was called `auto_stack_ws`. `perfect/examples/SEILR1/experiment.py` drives
this same stack from the PERFECT side and expects the workspace path in the environment
variable `SEILR1_WS`.

## `navigation.launch`

Brings up one of the four simulation worlds, RViz, and the rtabmap SLAM plus navigation
stack. The arguments the trade studies varied:

- `domain` (default `inspection`) -- `inspection | agriculture | orchard | playpen`.
  It selects which `cpr_*_gazebo` world launch file is included.
- `base_global_planner` (default `global_planner/GlobalPlanner`) --
  `navfn/NavfnROS | global_planner/GlobalPlanner`.
- `base_local_planner` (default `teb_local_planner/TebLocalPlannerROS`) --
  `dwa_local_planner/DWAPlannerROS | teb_local_planner/TebLocalPlannerROS |
  base_local_planner/TrajectoryPlannerROS`.

The rest are the robot spawn pose, the sensor enable flags (`camera`, `lidar2d`,
`lidar3d`, `slam2d`, `icp_odometry`, `rtabmap_viz`, `depth_from_lidar`,
`lidar3d_ray_tracing`), and the topic and frame names, all passed straight through to
`rtabmap_slam.launch`.

## Parameter files

| file | contents |
|---|---|
| `move_base_params.yaml` | controller and planner frequencies and patience |
| `global_planner_params.yaml` | the `GlobalPlanner` block, including `use_dijkstra` (false selects A*) -- this is how the Dijkstra and A* alternatives in the SysML global planner library are realised |
| `local_planner_params.yaml` | the local planner blocks |
| `sensor.yaml` | the sensor configuration: four top-level keys `depth_camera`, `camera`, `laser_2d`, `laser_3d`, each with model, pose, topic, rate and range fields. These are exactly the four keys the SysML sensor trade study sends as `sensor_update` (see `../workbench/README.md`) |

`move_base_params.yaml`, `global_planner_params.yaml` and `local_planner_params.yaml`
are not loaded by `navigation.launch` itself; they are loaded downstream in
`hardware_navigation`, which is not in the drop. [unverified] how each is namespaced.

## URDF

`sensors.urdf.xacro` reads `sensor.yaml` and conditionally includes the mount and sensor
xacros for whichever models are enabled. The per-sensor xacros shipped beside it are
`VLP-16.urdf.xacro`, `HDL-32E.urdf.xacro`, `sick_lms1xx.urdf.xacro`,
`hokuyo_ust10.urdf.xacro`, `intel_realsense.urdf.xacro` and `flir_blackflys.urdf.xacro`.
They are third-party files carrying their own copyright headers (`sick_lms1xx.urdf.xacro`
is Goncalo Cabrita / ISR University of Coimbra 2013 and Clearpath Robotics 2014-2015,
BSD); the headers are left intact.
