import os
import signal

from ament_index_python import get_package_share_directory
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

from perfect import common
from perfect.common.implementations.ros2 import nav2
import perfect.logging
from perfect.experiment.ros.ros2 import Ros2Experiment

logger = perfect.logging.getLogger("core")

LAUNCH_FILE = os.path.abspath("./launch/launch.py")
ORIGINAL_NAV2_YAML = os.path.join(get_package_share_directory("clearpath_nav2_demos"), "config/a200/nav2.yaml")
ORIGINAL_ROBOT_YAML = os.path.abspath("./launch/clearpath/original_robot.yaml")

class Clearpath_Experiment(Ros2Experiment):
    _files = {nav2.FILE: ORIGINAL_NAV2_YAML, "robot.yaml": ORIGINAL_ROBOT_YAML}
    _launch_file = LAUNCH_FILE
    _recorded_topics = []
    _relayed_topics = [
        ("/cmd_vel", None, Twist, None),
        ("/odom", None, Odometry, lambda msg: dict(x=msg.pose.pose.position.x, y=msg.pose.pose.position.y)),
    ]
    _ns = "/a200_0000"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._launch_args["headless"] = "true"
        self._launch_args["use_rviz"] = False
        self._launch_args["nav2_params"] = self._working_files[nav2.FILE]

        # Warning: clearpath is dumb and doesn't think to put a '/' between the directory path and 'robot.yaml', so we need to do it ourselves.
        self._launch_args["setup_path"] = os.path.dirname(self._working_files["robot.yaml"]) + "/"

    def _shut_down(self):
        returncode = super()._shut_down()
        # Make certain that Ignition Gazebo is shut down between experiments
        for p in os.popen("ps ax | grep gazebo | grep -v grep"):
            pid = p.split()[0]
            os.kill(int(pid), signal.SIGQUIT)
        logger.info("Sent SIGQUIT to Ignition Gazebo processes")
        return returncode


Experiment = Clearpath_Experiment


if __name__ == "__main__":
    import json
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

    from perfect.app import create_app
    app = create_app()
    with app.app_context():
        from perfect.app.routes.designs import get_default_robot_design_implementation
        design = get_default_robot_design_implementation("clearpath_husky_vision")
    pprint.pprint(design)
    template = json.load(
        open(os.path.join(common.PATH, "templates/nav2_operation_plans/navigate_from_initial_pose_to_goal_pose.json"), "r")
    )
    environment = fill_specification_kwargs(
        template["specification"],
        dict(x_start=0.0, y_start=0.0, x_goal=5.0, y_goal=0.0),
    )
    Experiment.launch(
        design=design,
        environment=environment,
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=1959,
    )
