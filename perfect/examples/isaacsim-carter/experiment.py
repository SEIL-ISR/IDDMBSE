import os
import signal

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from perfect.common.implementations.ros2 import nav2

from perfect import common
import perfect.logging
from perfect.app import config as default_config
from perfect.experiment.ros.ros2 import Ros2Experiment


logger = perfect.logging.getLogger("core")

LAUNCH_FILE = os.path.abspath("./launch/launch.py")

ORIGINAL_NAV2_YAML = os.path.join(
    get_package_share_directory("carter_navigation"), "params", "carter_navigation_params.yaml",
)

USD_ROOT = os.path.expanduser("~/perfect_carter_usd")

ORIGINAL_ROBOT_USD = f"{USD_ROOT}/Nova_Carter_ROS_perfectbase.usd"

class IsaacSimCarter_Experiment(Ros2Experiment):
    _files = {
        nav2.FILE: ORIGINAL_NAV2_YAML,
        "robot.usd": ORIGINAL_ROBOT_USD,
    }
    _launch_file = LAUNCH_FILE
    _recorded_topics = []
    _relayed_topics = [
        ("/cmd_vel", None, Twist, lambda msg: "(x={:.2f}, y={:.2f})".format(msg.linear.x, msg.linear.y)),
        ("/chassis/odom", "/odom", Odometry, lambda msg: "(x={:.2f}, y={:.2f})".format(msg.pose.pose.position.x, msg.pose.pose.position.y)),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._launch_args["headless"] = "native"
        self._launch_args["params_file"] = self._working_files[nav2.FILE]
        self._launch_args["use_rviz"] = "False"
        self._launch_args["gui"] = f"{USD_ROOT}/carter_warehouse_navigation_localNova.usd"

    def _shut_down(self):
        returncode = super()._shut_down()
        # Make certain that Isaac Sim is shut down between experiments
        for p in os.popen("ps ax | grep isaac | grep -v grep"):
            pid = p.split()[0]
            os.kill(int(pid), signal.SIGQUIT)
        logger.info("Sent SIGQUIT to Isaac Sim processes")
        return returncode

Experiment = IsaacSimCarter_Experiment


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

    import impl
    import perfect.common.implementations.ros2.nav2 as nav2_impl
    design = [
        nav2_impl.planner({"name": "A*"}),
        nav2_impl.controller({"name": "MPPI"}),
        impl._sensor_component({"name": "VLS-128"})
    ]
    pprint.pprint(design)
    template = json.load(
        open(os.path.join(common.PATH, "templates/nav2_operation_plans/navigate_to_goal_pose.json"), "r")
    )
    environment = fill_specification_kwargs(
        template["specification"],
        dict(x_goal=4.5, y_goal=-4.5),
    )
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
