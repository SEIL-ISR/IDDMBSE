"""The PERFECT experiment for the risk-sensitive planning campaign.

The planner is the design variable. A design holds one implementation of the
`planner` component -- plain RRT*, the risk-neutral functional, or CVaR at 0.1,
0.5 or 0.9 -- and an environment holds a rock field, a noise level, a seed and
how many times the planned path is executed under fresh noise. One trial is one
plan followed by its executions, and the numbers it measures come back to the
server as a trial update.

Where the design and the environment arrive
-------------------------------------------
PERFECT copies the two files named in `_files` into the trial's own working
directory and then applies, in order, the `files` updates of every component
implementation in the design and then those of the environment specification.
So by the time `_init` runs, `policy.yaml` holds the policy under test and
`scenario.yaml` holds the scenario under test. This class reads those two files
and hands their contents to the trial; it does not look at the raw design or
environment dictionaries at all.

Where the results go
--------------------
`await self._relay_update("metrics", ...)` sends the whole metric dictionary to
the runner, which forwards it to the server, which stores it as an `Update` row
on the trial. `GET /api/v1/trials/<id>` reads it back. `hazard_rate` is relayed
on its own as well, because a tool that scores a campaign asks for one named
number per trial, and `sim_time` because `Trial` has a column of that name, so
it also lands on the trial row itself.

The interpreter and the planner package
---------------------------------------
The planner is numpy and scipy, and the Python environment that carries PERFECT
does not have to be. The child process is started with `RARRT_PYTHON` if that is
set and with the running interpreter otherwise, and it finds the `rarrt` package
at `RARRT_PACKAGE`, which defaults to the case study's directory in this
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
TRIAL_PYTHON = os.environ.get("RARRT_PYTHON") or sys.executable
POLL_SEC = 0.05
TIMEOUT_SEC = 600


class RiskAwarePlanningExperiment(BaseExperiment):
    _files = {
        "policy.yaml": os.path.join(HERE, "policy.yaml"),
        "scenario.yaml": os.path.join(HERE, "scenario.yaml"),
    }

    def __init__(self, *args, **kwargs):
        self.p = None
        self.metrics = None
        super().__init__(*args, **kwargs)

    def _init(self):
        self.policy = yaml.safe_load(open(self._working_files["policy.yaml"]))
        self.scenario = yaml.safe_load(open(self._working_files["scenario.yaml"]))
        logger.info(f"policy {self.policy['policy']}, environment "
                    f"{self.scenario['environment']}, sigma {self.scenario['sigma']}, "
                    f"seed {self.scenario['seed']}")

    def _check_if_ready(self) -> bool:
        return True

    async def _run(self):
        work = os.path.dirname(self._working_files["scenario.yaml"])
        job = os.path.join(work, "job.json")
        out = os.path.join(work, "metrics.json")
        with open(job, "w") as f:
            json.dump({"policy": self.policy, "scenario": self.scenario}, f)

        self.p = subprocess.Popen(
            [TRIAL_PYTHON, os.path.join(HERE, "planner_trial.py"), job, out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        while self.p.poll() is None:
            await asyncio.sleep(POLL_SEC)
        output = self.p.stdout.read()
        if self.p.returncode != 0:
            logger.error(f"the planner trial exited {self.p.returncode}: {output}")
            return
        logger.info(output.strip())

        self.metrics = json.load(open(out))
        await self._relay_update("metrics", self.metrics)
        await self._relay_update("hazard_rate", self.metrics["hazard_rate"])
        await self._relay_update("sim_time", self.metrics["plan_time"])

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


Experiment = RiskAwarePlanningExperiment


if __name__ == "__main__":
    import logging
    from flask import Config
    from perfect.app import config as default_config
    from perfect.experiment.experiment import mock_relay_update_callback, mock_stopping_callback
    from perfect.app.routes.utils import fill_specification_kwargs

    logger.setLevel(logging.INFO)
    config = Config(os.path.curdir)
    config.from_object(default_config.Config)
    # One design over the CVaR 0.9 planner, as designs create -i would build it,
    # and one environment off the template, as environments create_from_template
    # would. n_exec is small here so that one trial by hand is quick.
    library = json.load(open(os.path.join(HERE, "components.json")))
    design = [c["implementation"] for c in library if c["name"] == "cvar0.9"]
    template = json.load(open(os.path.join(HERE, "environment_template.json")))[0]
    environment = fill_specification_kwargs(
        template["specification"],
        {"environment": "medium", "sigma": 0.5, "seed": 0, "n_exec": 32},
    )
    Experiment.launch(
        design=design,
        environment=environment,
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=0,
    )
