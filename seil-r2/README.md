# seil-r2

ROS2-based Autonomous Ground Robot Navigation Stack. 
**_This branch is based off of the baseline carter navigation packages provided by Isaac Sim 4.x. If you want to use Isaac Sim 2023.x, you will need to cfork the `legacy-IS-2023.x`_ branch of the repo that uses the old Isaac Sim ROS Workspace configured for 2023.1**

> **This is an open-source project. Please do not include any ARL proprietary material.** 

Current working environment:

![alt text](docs/figures/isaacworld.png)

The local seil-r2 repo is in the SEIL HPC admin profile and has been pre-built. Just source it and you are ready to run:

```
cd research/seil-r2
source install/local_setup.bash
```

If using on a different machine, make sure to build and source the workspace.

```
cd seil-r2
colcon build
source install/local_setup.bash
```

## General Guidelines

The _main_ branch serves as the baseline implementation of IsaacSim carter navigation. It is currently configured to run Nav2 using AMCL and an apriori map to navigate.

There are dedicated branches available for different configurations. 

The IsaacSim environments can be found in the _isaac_envs_ folder. Gazebo worlds in the _gazebo_envs_ folder. Both these folders have world files taht are too big and cannot be added to the online repo-- added the folders to .gitignore. 

We will merge branches gradually improving the baseline. 

## Tasks

* [ ] Add new launch files for various GP+LC combinations: NavFn+MPPI, Smac-A*+MPPI, Smac-SL+MPPI, etc. 
* [ ] Configure the Carter bot to publish the depth image and the depth point cloud from its stereo Cameras.
* [ ] Get the slam-toolbox_Nav2 branch working reliably and merge it with main to create the new baseline. 
* [ ] Get the rtabmap slam branch working and merge with main for more SLAM options.
* [ ] Implement BTs for complex mission scenarios and add corresponding launch files.
* [ ] Create a new branch for multi-robot spawn and launches.
* [ ] Create a new branch for implementing ros2-security profiles.
* [ ] Create a new branch for Gazebo based development.
* [ ] Create a new branch for Robust path planning- Clinton
* [ ] Create a new branch for lambda mapping. - Dimitris
* [ ] Create new branches for TRADES-X and VERITAS implementations. 

## Branches

* **main**: Baseline implementation of Isaac Sim carter navigation.
* **rtabmap**: Branch for testing rtabmap with Nav2.
* **multi-robot**: Branch for multi-robot spawn and launches.
* **secure-sel-r2**: Branch for implementing ros2-security profiles.
* **trades-x-prob-inference**: Branch for TRADES-X implementation.
* **robust-path-planning**: Branch for robust path planning.
* **lambda-mapping**: Branch for lambda mapping.

## Updates

### Depth Image and Point Cloud

We have a working demo using the nvblox demo warehouse scene that comes packaged with the Isaac SDK. The stereo camera on this carter is configured to publish the depth image and the depth point cloud. The depth pointcloud is published as the topic `depth/ground_truth/point_cloud`. You will need to select the `front_hawk` action graph and select the `depth_pcl` output pipeline to enable the depth point cloud. By default, it is set to publish the 2D depth image.

See the demo below:

![depth_demo](docs/figures/depth_camera.png)

The rviz config shown here can be found in the `rviz` folder in `src`, titled 'rviz-depth-nvblox.rviz'. You can load this config in rviz2 to visualize the depth point cloud after setting up Isaac Sim to publish the relevant topics.

Kashif is currently working on getting the depth image and point cloud from the carter bot in the terrain world scene. The documentation also has guidelines on adding sensor noise to the cameras and RTX lidars in Isaac Sim. Dimitris might find this useful for his lambda mapping implementation. Daniel will also need this to interact with Isaac Sim and configure the sensors from PERFECT. 

https://docs.omniverse.nvidia.com/isaacsim/latest/ros2_tutorials/tutorial_ros2_camera_publishing.html#publish-pointcloud-from-depth-images

https://docs.omniverse.nvidia.com/isaacsim/latest/ros2_tutorials/tutorial_ros2_rtx_lidar.html#multiple-sensors-in-rviz2

https://docs.omniverse.nvidia.com/isaacsim/latest/replicator_tutorials/tutorial_replicator_augmentation.html

https://docs.omniverse.nvidia.com/extensions/latest/ext_replicator/augmentation_examples.html

https://docs.omniverse.nvidia.com/isaacsim/latest/ros2_tutorials/tutorial_ros2_camera.html#depth-and-other-perception-ground-truth-data

https://docs.omniverse.nvidia.com/isaacsim/latest/ros2_tutorials/tutorial_ros2_python.html#isaac-sim-app-tutorial-ros2-python-camera

