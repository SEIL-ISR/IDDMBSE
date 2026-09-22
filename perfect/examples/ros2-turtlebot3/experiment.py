import os

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

from perfect import common
from perfect.app import config as default_config
from perfect.common.implementations.ros2 import nav2
from perfect.experiment.ros.ros2 import Ros2Experiment
import perfect.logging


logger = perfect.logging.getLogger("core")

ORIGINAL_NAV2_YAML = os.path.join(get_package_share_directory("nav2_bringup"), "params/nav2_params.yaml")

class Turtlebot3_Experiment(Ros2Experiment):
    _files = {nav2.FILE: ORIGINAL_NAV2_YAML}
    _launch_file = "nav2_bringup tb3_simulation_launch.py"
    _recorded_topics = []
    _relayed_topics = [
        ("/cmd_vel", None, Twist, None),
        ("/odom", None, Odometry, lambda msg: dict(x=msg.pose.pose.position.x, y=msg.pose.pose.position.y)),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._launch_args["params_file"] = self._working_files[nav2.FILE]
        self._launch_args["use_rviz"] = False
        # self._launch_args["__log_level"] = "warning"


Experiment = Turtlebot3_Experiment

if __name__ == "__main__":
    import json
    import logging
    import os
    from flask import Config
    from perfect.app import config as default_config
    from perfect.experiment.experiment import (
        mock_relay_update_callback,
        mock_stopping_callback,
    )
    from perfect.app.routes.utils import fill_specification_kwargs

    logger.setLevel(logging.DEBUG)

    config = Config(os.path.curdir)
    config.from_object(default_config.Config)
    config.from_pyfile("config.py")
    import pprint
    pprint.pprint(dict(config.items()))

    template = json.load(open(os.path.join(common.PATH, "templates/nav2_operation_plans/navigate_from_initial_pose_to_goal_pose.json"), "r"))
    environment = fill_specification_kwargs(
        template, dict(x_start=-2.0, y_start=-0.5, x_goal=-0.5, y_goal=-0.5)
    )
    Turtlebot3_Experiment.launch(
        design=[
            {"launchargs": [{"arg": "slam", "value": False}]},
            {
                "envvars": [
                    {"envvar": "TURTLEBOT3_MODEL", "value": "waffle"},
                    {
                        "envvar": "GAZEBO_MODEL_PATH",
                        "value": "/opt/ros/humble/share/turtlebot3_gazebo/models",
                    },
                ]
            },
        ],
        environment=environment["specification"],
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=1959,
    )
