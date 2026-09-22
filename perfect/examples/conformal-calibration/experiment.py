"""The PERFECT experiment for the conformal calibration campaign.

Conformal prediction is only as sound as its calibration data: the data has to
be ground-truth-labelled and drawn from the closed-loop states the robot will
actually visit. That is what this campaign produces. A design holds one
implementation of the `detector` component -- sharp, nominal or degraded -- and
an environment holds a clutter band, a seed and how many episodes to run. One
trial is a run of the closed loop; what it reports is every detection it made
with the true box beside it, plus how the episodes ended.

Where the design and the environment arrive
-------------------------------------------
PERFECT copies the two files named in `_files` into the trial's own working
directory and then applies, in order, the `files` updates of every component
implementation in the design and then those of the environment specification.
So by the time `_init` runs, `detector.yaml` holds the detector under test and
`scenario.yaml` holds the scenario under test. This class reads those two files
and hands their contents to the trial; it does not look at the raw design or
environment dictionaries at all.

Where the results go
--------------------
`await self._relay_update("metrics", ...)` sends the whole metric dictionary,
detection rows included, to the runner, which forwards it to the server, which
stores it as an `Update` row on the trial. `GET /api/v1/trials/<id>` reads it
back. `collision_rate` and `coverage_margin` are relayed on their own as well,
because a tool that scores a campaign asks for one named number per trial.

The interpreter and the perception package
------------------------------------------
The closed loop is numpy, and the Python environment that carries PERFECT does
not have to be. The child process is started with `CPNAV_PYTHON` if that is set
and with the running interpreter otherwise, and it finds the `cpnav` package at
`CPNAV_PACKAGE`, which defaults to the case study's directory in this
repository. Both variables are passed through to the child.

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
TRIAL_PYTHON = os.environ.get("CPNAV_PYTHON") or sys.executable
POLL_SEC = 0.05
TIMEOUT_SEC = 600


class ConformalCalibrationExperiment(BaseExperiment):
    _files = {
        "detector.yaml": os.path.join(HERE, "detector.yaml"),
        "scenario.yaml": os.path.join(HERE, "scenario.yaml"),
    }

    def __init__(self, *args, **kwargs):
        self.p = None
        self.metrics = None
        super().__init__(*args, **kwargs)

    def _init(self):
        self.detector = yaml.safe_load(open(self._working_files["detector.yaml"]))
        self.scenario = yaml.safe_load(open(self._working_files["scenario.yaml"]))
        logger.info(f"detector {self.detector['configuration']}, clutter "
                    f"{self.scenario['clutter']}, seed {self.scenario['seed']}, "
                    f"{self.scenario['n_episodes']} episodes")

    def _check_if_ready(self) -> bool:
        return True

    async def _run(self):
        work = os.path.dirname(self._working_files["scenario.yaml"])
        job = os.path.join(work, "job.json")
        out = os.path.join(work, "metrics.json")
        with open(job, "w") as f:
            json.dump({"detector": self.detector, "scenario": self.scenario}, f)

        self.p = subprocess.Popen(
            [TRIAL_PYTHON, os.path.join(HERE, "calibration_run.py"), job, out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        while self.p.poll() is None:
            await asyncio.sleep(POLL_SEC)
        output = self.p.stdout.read()
        if self.p.returncode != 0:
            logger.error(f"the calibration run exited {self.p.returncode}: {output}")
            return
        logger.info(output.strip())

        self.metrics = json.load(open(out))
        await self._relay_update("metrics", self.metrics)
        await self._relay_update("collision_rate", self.metrics["collision_rate"])
        await self._relay_update("coverage_margin", self.metrics["coverage_margin"])

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


Experiment = ConformalCalibrationExperiment


if __name__ == "__main__":
    import logging
    from flask import Config
    from perfect.app import config as default_config
    from perfect.experiment.experiment import mock_relay_update_callback, mock_stopping_callback
    from perfect.app.routes.utils import fill_specification_kwargs

    logger.setLevel(logging.INFO)
    config = Config(os.path.curdir)
    config.from_object(default_config.Config)
    # One design over the nominal detector, as designs create -i would build it,
    # and one environment off the template, as environments create_from_template
    # would.
    library = json.load(open(os.path.join(HERE, "components.json")))
    design = [c["implementation"] for c in library if c["name"] == "nominal"]
    template = json.load(open(os.path.join(HERE, "environment_template.json")))[0]
    environment = fill_specification_kwargs(
        template["specification"],
        {"clutter": "dense", "seed": 4, "n_episodes": 2},
    )
    Experiment.launch(
        design=design,
        environment=environment,
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=0,
    )
