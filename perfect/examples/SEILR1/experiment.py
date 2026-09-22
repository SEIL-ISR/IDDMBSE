import os
import shutil
import yaml

from pprint import pprint
from pydantic.utils import deep_update
from typing import Optional

import roslibpy

from perfect.experiment.ros.ros1 import Ros1Experiment
import perfect.logging


logger = perfect.logging.getLogger("core")

WS_PATH = os.environ["SEILR1_WS"]

def _edit_yaml(target: str|os.PathLike, update: Optional[dict] = None, base: Optional[str|os.PathLike] = None):
    if base:
        shutil.copyfile(
            base,
            target,
        )
    if not update:
        return
    with open(target, "r") as f:
        config = yaml.safe_load(f)
        config = deep_update(config, update)
    with open(target, "w") as f:
        yaml.dump(config, f)
    logger.info(f"Updated {target}:")
    pprint(config)

COMMON_LAUNCH_ARGS = {
    "rtabmap_viz": "true",
    "slam2d": "true",
    "icp_odometry": "true",
    "base_global_planner": "global_planner/GlobalPlanner",
    "base_local_planner": "teb_local_planner/TebLocalPlannerROS",
    "domain": "playpen",
    "rosbridge": "true",
}

def get_launch_args(sensor_yaml: dict) -> dict:
    launch_args = COMMON_LAUNCH_ARGS.copy()
    camera = sensor_yaml["camera"]["enabled"]
    depth_camera = sensor_yaml["depth_camera"]["enabled"]
    laser_3d = sensor_yaml["laser_3d"]["enabled"]
    laser_2d = sensor_yaml["laser_2d"]["enabled"]
    if camera:
        launch_args["camera"] = "true"
        launch_args["camera_info_topic"] = "/blackfly/camera_info"
        launch_args["rgb_topic"] = "/blackfly/image_raw"
        if not depth_camera:
            launch_args["depth_topic"] = ""
    if depth_camera:
        launch_args["camera"] = "true"
        launch_args["camera_info_topic"] = "/realsense/color/camera_info"
        launch_args["depth_topic"] = "/realsense/depth/image_rect_raw"
        if not camera:
            launch_args["rgb_topic"] = "/realsense/color/image_raw"
    if not camera and not depth_camera:
        launch_args["camera"] = "false"
        launch_args["camera_info_topic"] = ""
        launch_args["rgb_topic"] = ""
        launch_args["depth_topic"] = ""
    if laser_3d:  # "lidar"
        launch_args["depth_from_lidar"] = "true" if not camera and not depth_camera else "false"
        launch_args["lidar3d"] = "true"
        launch_args["lidar3d_ray_tracing"] = "true"
    else:
        launch_args["depth_from_lidar"] = "false"
        launch_args["lidar3d"] = "false"
        launch_args["lidar3d_ray_tracing"] = "false"
    launch_args["lidar2d"] = "true" if laser_2d else "false"
    return launch_args

class SEILR1_Experiment(Ros1Experiment):
    def __init__(self, design, environment, **kwargs):
        super().__init__(design, environment, **kwargs)
        self._sensor_update = {}
        for t in ("camera", "depth_camera", "laser_3d", "laser_2d"):
            if t in design:
                self._sensor_update[t] = design[t]
                self._sensor_update[t]["enabled"] = True
            else:
                self._sensor_update[t] = {"enabled": False}
        self._launch_file = f"{WS_PATH}/src/hardware_launch/launch/navigation.launch"
        self._launch_args = get_launch_args(self._sensor_update)
        try:
            self._launch_args["base_global_planner"] = design["planner"]["base_global_planner"]
        except KeyError:
            pass
        try:
            self._launch_args["base_local_planner"] = design["controller"]["base_local_planner"]
        except KeyError:
            pass
        self._launch_args["world"] = environment["world"]
        self._launch_args["robot_x"] = environment["start"]["x"]
        self._launch_args["robot_y"] = environment["start"]["y"]
        self._launch_args["robot_z"] = environment["start"]["z"]
        self._goal = environment["goal"]
        self._recorded_topics = []
        self.status = None

    def _init(self):
        super()._init()
        _edit_yaml(
            f"{self._WS_PATH}/src/hardware_description/config/sensor.yaml",
            self._sensor_update,
            f"{self._WS_PATH}/src/hardware_description/config/sensor.yaml.original",
        )

    def _run(self):
        super()._run()
        self._goal_talker = roslibpy.Topic(
            self._rosbridgeclient,
            "/move_base_simple/goal",
            "geometry_msgs/PoseStamped",
        )
        pose = {
            "position": self._goal,
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.5},
        }
        logger.info(f"Setting goal to {pose}.")
        self._goal_talker.publish(roslibpy.Message({
            "header": roslibpy.Header(frame_id="odom", seq=0, stamp=roslibpy.Time.now()),
            "pose": pose,
        }))
        self._status_listener = roslibpy.Topic(
            self._rosbridgeclient,
            "/move_base/status",
            "actionlib_msgs/GoalStatusArray",
            throttle_rate=100,
        )
        def status_callback(msg):
            self.status = msg["status_list"]
        self._status_listener.subscribe(status_callback)

    def _check_if_cancelled(self) -> bool:
        # TODO
        return False

    def _check_if_errored(self) -> bool:
        return self.process.poll() is not None  #FIXME check return code

    def _check_if_successful(self) -> bool:
        if not self.status:
            return False
        if self.status[-1]["status"] == 3:
            logger.info("FINISHED")
            return True
        return False


    def _check_if_timed_out(self) -> bool:
        timeout = 250
        if self.start_age >= timeout:
            logger.info(f"Timed out after {timeout} seconds.")
            return True
        return False

Experiment = SEILR1_Experiment

if __name__ == "__main__":
    import asyncio
    import json
    import logging
    logger.setLevel(logging.DEBUG)
    components = json.load(open("components.json", "r"))
    design = {}
    design["laser_3d"] = components[1]["specification"]  # Velodyne Puck (20 Hz)
    design["depth_camera"] = components[10]["specification"]  # Intel RealSense Depth Camera D455
    design["planner"] = components[14]["specification"]  # navfn/NavfnROS
    environment = {
        "world": "playpen",
        "start": {"x": 0.0, "y": 0.0, "z": 0.0},
        "goal": {"x": 6.0, "y": 3.0, "z": 0.0},
    }
    exp = Experiment(
        design=design,
        environment=environment,
        #connection="ws4py",
        stopwatch_callback=lambda stopwatch, trial_id: logger.debug(f"Duration {stopwatch} seconds"),
        # stopping_callback=lambda trial_id: True,  # cancel immediately
        state_callback=lambda trial_state, trial_id: logger.debug(f"State changed to {trial_state}"),
        trial_id=1959,
        design_name="test",
        environment_id=1,
    )
    asyncio.run(exp.run())
