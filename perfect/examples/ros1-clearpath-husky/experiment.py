import json
import os

from pprint import pprint

import roslibpy

from perfect.experiment.ros.ros1 import Ros1Experiment
import perfect.logging


logger = perfect.logging.getLogger("core")

LAUNCH_FILE = os.path.abspath("./launch/entrypoint.launch")

class ClearpathHusky_Experiment(Ros1Experiment):
    _launch_file = LAUNCH_FILE
    _recorded_topics = ["/cmd_vel", "/odom"]
    _relayed_topics = []
    def __init__(self, design, environment, **kwargs):
        super().__init__(design, environment, **kwargs)
        self._launch_args["world"] = environment["world"]
        self._launch_args["robot_x"] = environment["start"]["x"]
        self._launch_args["robot_y"] = environment["start"]["y"]
        self._launch_args["robot_z"] = environment["start"]["z"]
        self._launch_args["gui"] = "false"
        self._launch_args["rviz"] = "false"
        self._launch_args["rtabmap_viz"] = "false"
        self._goal = environment["goal"]
        self.status = None

    async def _run(self):
        await super()._run()
        self._goal_talker = roslibpy.Topic(
            self._rosbridgeclient,
            "/move_base_simple/goal",
            "geometry_msgs/PoseStamped",
        )
        pose = {
            "position": self._goal,
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.5},
        }
        logger.info(f"Setting goal to {pose}")
        self._goal_talker.publish(roslibpy.Message({
            "header": roslibpy.Header(frame_id="map", seq=0, stamp=roslibpy.Time.now()),
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
        if self.status and len(self.status) > 0 and self.status[-1]["status"] > 3:
            logger.info(f"Goal failed {self.status[-1]['status']}")
            return True
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

Experiment = ClearpathHusky_Experiment

if __name__ == "__main__":
    import logging
    from flask import Config
    from perfect.app import config as default_config
    from perfect.app.routes.utils import fill_specification_kwargs
    from perfect.experiment.experiment import (
        mock_relay_update_callback,
        mock_stopping_callback,
    )

    logger.setLevel(logging.DEBUG)

    config = Config(os.path.curdir)
    config.from_object(default_config.Config)
    config.from_pyfile("config.py")
    import pprint
    pprint.pprint(dict(config.items()))

    from perfect.app import create_app, db, models
    app = create_app()
    with app.app_context():
        from perfect.app.routes.designs import get_default_robot_design_implementation
        design = [
            {
                "envvars": [{"envvar": "HUSKY_LASER_3D_ENABLED", "value": "true"},
                            {"envvar": "HUSKY_LASER_3D_XYZ", "value": "0.0 0.0 0.0"},
                            {"envvar": "HUSKY_LASER_3D_RPY", "value": "0.0 0.0 0.0"},
                            {"envvar": "HUSKY_LASER_3D_TOPIC", "value": "velodyne_points"}],
                "launchargs": [{"arg": "rtabmap_lidar3d", "value": "true"}]
            },
            {
                "envvars": [{"envvar": "HUSKY_REALSENSE_ENABLED", "value": "true"}],
                "launchargs": [{"arg": "rtabmap_camera", "value": "true"}]
            },
            {
                "launchargs": [{"arg": "rtabmap_depth_from_lidar", "value": "false"},
                               {"arg": "rtabmap_icp_odometry", "value": "false"},
                               {"arg": "rtabmap_lidar3d_ray_tracing", "value": "true"},
                               {"arg": "rtabmap_slam2d", "value": "true"}]
            }
        ] if False else get_default_robot_design_implementation("clearpath_husky")
        environment: models.Environment = db.session.query(models.Environment).filter(models.Environment.name == "Kashif Difficult").one()
        environment = json.loads(environment.specification)
    pprint.pprint(design)
    pprint.pprint(environment)

    if environment["world"] == "playpen":
        config["PAUSE_BEFORE_READY_SEC"] = 10

    Experiment.launch(
        design=design,
        environment=environment,
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=1959,
    )

    pprint.pprint(design)
    pprint.pprint(environment)
