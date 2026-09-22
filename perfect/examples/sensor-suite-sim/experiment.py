"""The PERFECT experiment for the sensor-suite navigation simulation.

Like examples/dummy, this example runs its work in a child process and reports
when the child is done; unlike dummy, the child is a simulation whose result
depends on the design and the environment, and the numbers it produces come back
to the server as a trial update.

Where the design and the environment arrive
-------------------------------------------
PERFECT copies the two files named in `_files` into the trial's own working
directory and then applies, in order, the `files` updates of every component
implementation in the design and then those of the environment specification.
So by the time `_init` runs, `sensors.yaml` holds the suite of the design under
test and `scenario.yaml` holds the scenario of the environment under test. This
class reads those two files and hands their contents to the simulation; it does
not look at the raw design or environment dictionaries at all.

Where the results go
--------------------
`await self._relay_update("metrics", ...)` sends the whole metric dictionary to
the runner, which forwards it to the server, which stores it as an `Update` row
on the trial. `GET /api/v1/trials/<id>` reads it back. `sim_time` is relayed
separately because `Trial` has a column of that name, so it also lands on the
trial row itself.

The interpreter
---------------
The simulation is numpy, and the Python environment that carries PERFECT does
not have to. The child process is started with `SENSOR_SIM_PYTHON` if that is
set and with the running interpreter otherwise, so a PERFECT installation
without numpy runs this example by pointing that variable at a Python that has
it.

To run one trial without a server, from this directory:

    PERFECT_PROJECT_ROOT=$PWD python experiment.py
"""

import asyncio
import json
import os
import subprocess
import sys

import yaml

from perfect.experiment.experiment import BaseExperiment
import perfect.logging

logger = perfect.logging.getLogger("core")

HERE = os.path.dirname(os.path.abspath(__file__))
SIM_PYTHON = os.environ.get("SENSOR_SIM_PYTHON") or sys.executable
POLL_SEC = 0.05
TIMEOUT_SEC = 120


class SensorSuiteExperiment(BaseExperiment):
    _files = {
        "sensors.yaml": os.path.join(HERE, "sensors.yaml"),
        "scenario.yaml": os.path.join(HERE, "scenario.yaml"),
    }

    def __init__(self, *args, **kwargs):
        self.p = None
        self.metrics = None
        super().__init__(*args, **kwargs)

    def _init(self):
        self.suite = yaml.safe_load(open(self._working_files["sensors.yaml"]))["suite"] or []
        self.scenario = yaml.safe_load(open(self._working_files["scenario.yaml"]))
        logger.info(f"{len(self.suite)} sensors, scenario {self.scenario}")

    def _check_if_ready(self) -> bool:
        return True

    async def _run(self):
        work = os.path.dirname(self._working_files["scenario.yaml"])
        job = os.path.join(work, "job.json")
        out = os.path.join(work, "metrics.json")
        with open(job, "w") as f:
            json.dump({"suite": self.suite, "scenario": self.scenario}, f)

        self.p = subprocess.Popen(
            [SIM_PYTHON, os.path.join(HERE, "sensor_sim.py"), job, out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        while self.p.poll() is None:
            await asyncio.sleep(POLL_SEC)
        output = self.p.stdout.read()
        if self.p.returncode != 0:
            logger.error(f"the simulation exited {self.p.returncode}: {output}")
            return
        logger.info(output.strip())

        self.metrics = json.load(open(out))
        await self._relay_update("metrics", self.metrics)
        await self._relay_update("sim_time", self.metrics["sim_time"])

    def _check_if_cancelled(self) -> bool:
        return False

    def _check_if_errored(self) -> bool:
        return self.p is not None and self.p.returncode not in (None, 0)

    def _check_if_successful(self) -> bool:
        return self.metrics is not None

    def _check_if_timed_out(self) -> bool:
        return self.start_age > TIMEOUT_SEC

    def _shut_down(self):
        if self.p is not None and self.p.poll() is None:
            self.p.terminate()
            self.p.wait()


Experiment = SensorSuiteExperiment


if __name__ == "__main__":
    import logging
    from flask import Config
    from perfect.app import config as default_config
    from perfect.experiment.experiment import mock_relay_update_callback, mock_stopping_callback
    from perfect.app.routes.utils import fill_specification_kwargs
    import catalogue

    logger.setLevel(logging.INFO)
    config = Config(os.path.curdir)
    config.from_object(default_config.Config)
    # A design over four sensors, as designs create -i would build it, and one
    # environment off the template, as environments create_from_template would.
    design = [catalogue.component(s)["implementation"] for s in catalogue.SENSORS
              if s["name"] in ("VLP-16-A", "LMS111-b1", "D435", "Blackfly-A")]
    template = json.load(open(os.path.join(HERE, "environment_template.json")))[0]
    environment = fill_specification_kwargs(
        template["specification"],
        {"clutter": 0.5, "visibility": 0.4, "seed": 1, "n_draws": 12},
    )
    Experiment.launch(
        design=design,
        environment=environment,
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=0,
    )
