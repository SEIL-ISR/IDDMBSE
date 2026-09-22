import os
import signal
import subprocess
import time
import uuid

from perfect.experiment.experiment import BaseExperiment
import perfect.logging


logger = perfect.logging.getLogger("core")

class DummyExperiment(BaseExperiment):
    def __init__(self, *args, **kwargs):
        self.uuid = str(uuid.uuid1())
        super().__init__(*args, **kwargs)

    @property
    def name(self):
        return f"{self.__class__.__name__}({self.uuid})"

    def _init(self):
        for i in [4,3,2,1]:
            print(f"Initialized in {i}...")
            time.sleep(1)

    def _check_if_ready(self) -> bool:
        return self.init_age < 3

    async def _run(self):
        self.p = subprocess.Popen(["./countdown.bash"], cwd=os.path.dirname(os.path.abspath(__file__)))

    def _check_if_cancelled(self) -> bool:
        return False

    def _check_if_errored(self) -> bool:
        return False

    def _check_if_successful(self) -> bool:
        return self.p.poll() is not None

    def _check_if_timed_out(self) -> bool:
        return False

    def _shut_down(self):
        self.p.send_signal(signal.SIGTERM)
        self.p.wait()  # TODO Should this be moved to a _clean_up method?

Experiment = DummyExperiment


if __name__ == "__main__":
    import logging
    from flask import Config
    from perfect.app import config as default_config
    from perfect.experiment.experiment import mock_relay_update_callback, mock_stopping_callback
    logger.setLevel(logging.DEBUG)
    config = Config(os.path.curdir)
    config.from_object(default_config.Config)
    Experiment.launch(
        design={},
        environment={},
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=1959,
    )
