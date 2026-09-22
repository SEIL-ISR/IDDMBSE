import asyncio
import importlib
import signal
import subprocess
import time
from functools import partial

import rclpy.node
from action_msgs.msg import GoalStatus
from rclpy.action.client import ActionClient
from rosgraph_msgs.msg import Clock

import perfect.logging
from perfect.experiment.ros.ros import RosExperiment

logger = perfect.logging.getLogger("core")

class Ros2Experiment(RosExperiment, rclpy.node.Node):
    _launch_cmd = "ros2 launch"
    _launch_file: str
    _ns = ""
    _rosbag_cmd_template = "ros2 bag record {topics} -o {dest} --max-bag-duration=300"

    def __init__(
        self,
        design,
        environment,
        config,
        **kwargs,
    ):
        self.__goal = environment.pop("goal")
        self.__on_init = environment.pop("init", [])
        RosExperiment.__init__(self, design, environment, config, **kwargs)
        rclpy.node.Node.__init__(
            self, node_name=self.__class__.__name__, namespace="/perfect"
        )
        self.status = GoalStatus.STATUS_UNKNOWN
        self._relayed_topics.append(("/clock", "sim_time", Clock, lambda msg: msg.clock.sec + msg.clock.nanosec/1e9))

    def _check_if_ready(self) -> bool:
        # TODO check for nav2 server and/or sensor data
        time.sleep(1.0)
        logger.info(f"{self.init_age=}")
        return self.init_age >= self._config["PAUSE_BEFORE_READY_SEC"]

    async def _run(self):
        await super()._run()
        for todo in self.__on_init:
            if eval(todo.get("condition", True)):
                logger.debug(f"Condition `{todo['condition']}` evaluated to True")
                if publish := todo.get("publish"):
                    self.__handle_publish(**publish)
            else:
                logger.debug(f"Condition `{todo['condition']}` evaluated to False")
            await asyncio.sleep(self._config["PAUSE_AFTER_INITS_SEC"])
        await self.__handle_action(**self.__goal)

    def create_subscription(self, topic: str, mapping: str, msg_type: str, preprocessing=None):
        topic = self._ns + topic
        if isinstance(msg_type, str):
            msg_type = getattr(
                importlib.import_module(".".join(msg_type.split(".")[:-1])),
                msg_type.split(".")[-1],
            )
        logger.info(f"Subscribing to {topic=}")
        super().create_subscription(
            msg_type,
            topic,
            partial(self._subscription_callback_async, mapping or topic, preprocessing),
            qos_profile=0,
        )

    def _shut_down(self):
        if getattr(self, "rosbag_p", None) is not None:
            logger.info("Sending SIGINT to ros2 bag process")
            self.rosbag_p.send_signal(signal.SIGINT)
            self.rosbag_p.wait()
        # logger.info("Sending SIGTERM to roslaunch process")
        # self.process.send_signal(signal.SIGTERM)
        logger.info("Sending SIGINT to ros2 launch process")
        self.process.send_signal(signal.SIGINT)
        # logger.info("Killing all ROS nodes")
        # roskill_p = subprocess.Popen("rosnode kill --all".split(), env=self._env)
        # roskill_p.wait()
        logger.info("Waiting for ros2 launch process to end")
        if False:
            try:
                self.process.wait(30)
            except subprocess.TimeoutExpired:
                logger.warning("Timeout expired after SIGINT. Escalating to SIGTERM")
                self.process.terminate()
                self.process.wait()
        else:
            self.process.wait()
        returncode = self.process.returncode
        logger.debug(f"ros2 launch process {returncode=}")
        # Restore sensor.yaml?
        return returncode

    def _check_if_cancelled(self) -> bool:
        # TODO
        return False

    def _check_if_errored(self) -> bool:
        if self.status == GoalStatus.STATUS_ABORTED:
            logger.error("Action aborted. -_-")
            return True
        elif self.status == GoalStatus.STATUS_CANCELED:
            logger.error("Action cancelled. o_<")
            return True
        return self.process.poll() is not None  # FIXME check return code

    def _check_if_successful(self) -> bool:
        if self.status == GoalStatus.STATUS_SUCCEEDED:
            logger.info("Action successful! ^_^")
            return True
        return False

    def _check_if_timed_out(self) -> bool:
        timeout = self._config["TIMEOUT_SEC"]
        if self.start_age >= timeout:
            logger.info(f"Timed out after {timeout} seconds.")
            return True
        return False

    def __handle_publish(self, msg_type, topic, msg):
        topic = f"{self._ns}{topic}"
        msg_type = getattr(
            importlib.import_module(".".join(msg_type.split(".")[:-1])),
            msg_type.split(".")[-1],
        )
        msg = self.json_to_ros_msg(msg)
        logger.info(f"Setting {topic} to {msg}")
        publisher = self.create_publisher(
            msg_type,
            topic,
            qos_profile=0,
        )
        publisher.publish(msg)

    async def __handle_action(self, action_type, action_name, goal_msg):
        action_name = f"{self._ns}{action_name}"
        action_type = getattr(
            importlib.import_module(".".join(action_type.split(".")[:-1])),
            action_type.split(".")[-1],
        )
        goal_msg = self.json_to_ros_msg(goal_msg)
        action_client = ActionClient(
            self,
            action_type=action_type,
            action_name=action_name,
        )
        logger.info("Waiting for action server...")
        action_client.wait_for_server()

        logger.info(f"Sending {goal_msg=} to {action_name=}")
        goal_handle = await action_client.send_goal_async(goal_msg)

        if not goal_handle.accepted:
            logger.info("Goal rejected :(")
            self.status = GoalStatus.STATUS_CANCELED
            return
        logger.info("Goal accepted :)")

        result = goal_handle.get_result_async()
        while self.is_running and not result.done():  # while not timed out and goal task not done
            await asyncio.sleep(1.0)

        if result.done():
            result = await result
            self.status = result.status

        # Very important! If this isn't done, the Ros2Experiment node will hang around after `destroy` until Python exits.
        action_client.destroy()

    @staticmethod
    async def __spinning(node, rclpy_spin_timeout_sec, rclpy_spin_period_sec):
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=rclpy_spin_timeout_sec)
            await asyncio.sleep(rclpy_spin_period_sec)

    @classmethod
    async def launch_async(cls, loop, exp_callback=None, **kwargs):
        logger.info("Starting rclpy")
        rclpy.init()
        logger.debug(f"Instantiating {cls.__name__}")
        exp = cls(**kwargs)
        if exp_callback:
            exp_callback(exp)

        spin_task = loop.create_task(cls.__spinning(exp, kwargs["config"]["RCLPY_SPIN_TIMEOUT_SEC"], kwargs["config"]["RCLPY_SPIN_PERIOD_SEC"]))
        exp_task = loop.create_task(exp.run())

        logger.debug("Awaiting experiment task...")
        await exp_task

        logger.debug("Experiment task is done. Cancelling spin task...")
        spin_task.cancel()
        try:
            await spin_task
        except asyncio.exceptions.CancelledError:
            pass
        logger.info(f"Destroying {exp.__class__.__name__} Node")
        exp.destroy_node()
        logger.info("Shutting down rclpy...")
        rclpy.shutdown()
        logger.info("Done")
