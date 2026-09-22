from functools import partial
import json
import signal
import subprocess

from  ws4py.client.threadedclient import WebSocketClient

import roslibpy

from perfect.experiment.ros.ros import RosExperiment
import perfect.logging


logger = perfect.logging.getLogger("core")

class RosWebSocketClient(WebSocketClient):
    def __init__(self, url):
        WebSocketClient.__init__(self, url)
        self.publish_callbacks = {}
        self.action_result_callbacks = {}
    def received_message(self, message):
        message = json.loads(str(message))
        logger.debug(f"Received message {message}")
        if message["op"] == "publish":
            logger.debug(f"Received publication of {message['topic']}")
            if message["topic"] in self.publish_callbacks:
                logger.debug(f"Running callback for topic {message['topic']}")
                self.publish_callbacks[message["topic"]](message["msg"])
        elif message["op"] == "action_result":
            logger.debug(f"Received action_result from {message['action']}")
            if message["action"] in self.action_result_callbacks:
                logger.debug(f"Running callback for {message['action']}")
                self.action_result_callbacks[message["action"]](message["values"], message["result"])


class Ros1Experiment(RosExperiment):
    _launch_cmd = "roslaunch"
    _launch_file: str
    _rosbag_cmd_template = "rosbag record {topics} -o {dest} --duration=300 __name:=perfect_recording"

    def __init__(
        self,
        design,
        environment,
        connection="roslibpy",
        **kwargs,
    ):
        super().__init__(design, environment,  **kwargs)

        if connection == "roslibpy":
            self._rosbridgeclient = roslibpy.Ros(host="localhost", port=9090)
        elif connection == "ws4py":
            self._wsclient = RosWebSocketClient("ws://{host}:{port}".format(host="localhost", port=9090))
        else:
            raise ValueError("connection must be one of roslibpy or ws4py")
        self._listeners: dict[str, roslibpy.Topic] = {}
        # The initial sim_time might be set (to non-zero) in the world file! TODO: can the sim_time be set to zero after initialization?
        self._relayed_topics.append(("/clock", "sim_time", "rosgraph_msgs/Clock", lambda msg: msg["clock"]["secs"] + msg["clock"]["nsecs"]/1e9))

    def _check_if_ready(self) -> bool:
        if self.init_age < self._config["PAUSE_BEFORE_READY_SEC"]:
            logger.debug(f"ROS launched less than {self._config['PAUSE_BEFORE_READY_SEC']} seconds ago, so won't try to connect to rosbridge yet")
            return False
        # TODO Gazebo, RViz, rosbridge, etc. all ready
        if hasattr(self, "_rosbridgeclient"):
            try:
                self._rosbridgeclient.run()
            except Exception as e:
                logger.error(f"Failed to run roslibpy client: {e}")
            else:
                if self._rosbridgeclient.is_connected:
                    return True
                else:
                    logger.warning("Not connected to ROS yet")
        elif hasattr(self, "_wsclient"):
            try:
                self._wsclient.connect()
            except Exception as e:
                logger.error(f"Failed to run WebsocketClient: {e}")
            else:
                return True
        return False

    def create_subscription(self, topic: str, mapping: str, msg_type: str, preprocessing=None):
        self._listeners[topic] = roslibpy.Topic(
            self._rosbridgeclient,
            topic,
            msg_type,
            throttle_rate=100,
        )
        self._listeners[topic].subscribe(partial(self._subscription_callback, mapping or topic, preprocessing))

    def _shut_down(self):
        if hasattr(self, "_rosbridgeclient"):
            logger.info("Terminating rosbridge client")
            try:
                self._rosbridgeclient.terminate()
            except Exception as e:
                logger.error(f"Tried to terminate rosbridge client but got {e}")
        if hasattr(self, "_wsclient"):
            logger.info("Closing websocket client")
            self._wsclient.close()
            #logger.info("Terminating websocket client")
            #self._wsclient.terminate()
        if self.rosbag_p is not None:
            logger.info("Killing rosbag node perfect_recording")
            roskill_p = subprocess.Popen("rosnode kill /perfect_recording".split(), env=self._env)
            roskill_p.wait()
            self.rosbag_p.wait()
        #logger.info("Sending SIGTERM to roslaunch process")
        #self.process.send_signal(signal.SIGTERM)
        logger.info("Sending SIGINT to roslaunch process")
        self.process.send_signal(signal.SIGINT)
        #logger.info("Killing all ROS nodes")
        #roskill_p = subprocess.Popen("rosnode kill --all".split(), env=self._env)
        #roskill_p.wait()
        logger.info("Waiting for roslaunch process to end")
        self.process.wait()
        returncode = self.process.returncode
        logger.debug(f"roslaunch process {returncode=}")
        # Restore sensor.yaml?
        return returncode
