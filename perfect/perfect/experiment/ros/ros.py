import asyncio
import importlib
import os
import pathlib
import subprocess

import perfect.logging
from perfect.experiment.experiment import (
    BaseExperiment,
    edit_working_files,
    extract_kv_pairs
)

logger = perfect.logging.getLogger("core")


class RosExperiment(BaseExperiment):
    _launch_cmd: str
    _launch_file: str
    _recorded_topics: list
    _relayed_topics: list  # list[tuple[topic, Option[mapping], msg_type, Option[preprocessing_func]]]
    _rosbag_cmd_template: str

    def __init__(
        self,
        design,
        environment,
        config,
        **kwargs,
    ):
        super().__init__(design, environment, config, **kwargs)
        self._launch_args = dict(
            extract_kv_pairs(
                "launchargs", "arg", "value", *design, environment,
            )
        )

        self.kwargs = kwargs

        self.ns = ""

        self._env = os.environ
        self._env.update(
            dict(
                extract_kv_pairs(
                    "envvars", "envvar", "value", *design, environment,
                )
            )
        )

        self.rosbag_p = None

        self._last_msg = {}

    def _init(self):
        cmd = f"{self._launch_cmd} {self._launch_file}"
        for k, v in self._launch_args.items():
            cmd += f" {k}:={v}"
        logger.info(f"Starting ROS with command:\n{cmd}")
        self.process = subprocess.Popen(cmd.split(), env=self._env)

    def get_last_msg(self, topic):
        return self._last_msg.get(topic)

    async def _subscription_callback_async(self, topic, preprocessing, msg):
        data = preprocessing(msg) if preprocessing is not None else repr(msg)
        self._last_msg[topic] = data
        await self._relay_update(topic, data)

    def _subscription_callback(self, topic, preprocessing, msg):
        data = preprocessing(msg) if preprocessing is not None else repr(msg)
        self._last_msg[topic] = data
        asyncio.run(self._relay_update(topic, data))

    async def _run(self):
        if not self._records_root:
            logger.debug("No records path given. Will not record a bag file")
        topics = " ".join(self._recorded_topics)
        if topics:
            #self.__setup_recording(self.kwargs)
            dest = f"{self._records_root}/rosbag"
            logger.info(f"Starting to record topics {topics} to {dest}")
            rosbag_cmd = self._rosbag_cmd_template.format(topics=topics, dest=dest)
            self.rosbag_p = subprocess.Popen(rosbag_cmd.split(), env=self._env)
        else:
            logger.warning("No topics to record. Will not create a bag file")
            self.rosbag_p = None
        for topic, mapping, msg_type, preprocessing in self._relayed_topics:
            self.create_subscription(topic, mapping, msg_type, preprocessing)

    @staticmethod
    def json_to_ros_msg(msg: dict):
        def _ros(v):
            if isinstance(v, dict) and (msg_cls := v.get("cls")):
                modules = msg_cls.split(".")
                if msg_cls.endswith("Goal"):
                    msg_mod = importlib.import_module(".".join(modules[:-2]))
                    msg_cls = getattr(getattr(msg_mod, modules[-2]), modules[-1])
                else:
                    msg_mod = importlib.import_module(".".join(modules[:-1]))
                    msg_cls = getattr(msg_mod, modules[-1])
                kwargs = {_k: _ros(_v) for _k, _v in v["kwargs"].items()}
                return msg_cls(**kwargs)
            return v

        return _ros(msg)
