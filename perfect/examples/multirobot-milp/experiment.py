"""The PERFECT experiment for the assured multi-robot coordination campaign.

The coordination configuration is the design variable. A design holds one
implementation of the `coordinator` component -- a station allocation and a
required STL robustness margin -- and an environment holds a disturbance level
and a seed. One trial synthesises the three robots' joint plan as a big-M MILP,
executes it once under the environment's disturbance, scores each robot's
executed trace with the quantitative STL robustness, writes the verdicts back into
a copy of the fleet model, and relays what it measured to the server.

Where the design and the environment arrive
-------------------------------------------
PERFECT copies the files named in `_files` into the trial's own working directory
and then applies, in order, the `files` updates of every component implementation
in the design and then those of the environment specification. By the time
`_init` runs, `config.yaml` holds the configuration under test and
`execution.yaml` the execution condition under test. The third working file,
`agr_fleet.yaml`, is the case study's fleet model; no update touches it, and the
trial writes the goal-satisfaction values into this copy, never into the case
study's own file.

Where the results go
--------------------
`await self._relay_update("metrics", ...)` sends the whole metric dictionary to the
runner, which forwards it to the server, which stores it as an `Update` row on the
trial; `GET /api/v1/trials/<id>` reads it back. `min_rho`, the smallest executed
robustness over the three robots, is relayed on its own as well, because a tool
that scores a campaign asks for one named number per trial, and the solve time as
`sim_time` because `Trial` has a column of that name.

The interpreter and the coordination package
--------------------------------------------
Synthesis and scoring are numpy and scipy, and the Python environment that carries
PERFECT does not have to have either. The child process is started with the
command in `MULTIROBOT_PYTHON` if that is set (an interpreter path, or a command
such as `uv run --project <dir> python`), and otherwise with
`uv run --project <package> python`, the case study's own uv environment. It finds
the `assured_ma` package at `MULTIROBOT_PACKAGE`, which defaults to the case
study's directory in this repository. PYTHONPATH and VIRTUAL_ENV are not passed to
the child, so neither a sourced ROS environment nor the activated PERFECT
environment can stand in front of the case study's own.

To run one trial without a server, from this directory:

    PERFECT_PROJECT_ROOT=$PWD python experiment.py
"""

import asyncio
import json
import os
import shlex
import subprocess

import yaml

from perfect.experiment.experiment import BaseExperiment
import perfect.logging

logger = perfect.logging.getLogger("core")

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.environ.get("MULTIROBOT_PACKAGE") or os.path.normpath(os.path.join(
    HERE, os.pardir, os.pardir, os.pardir, "case-studies", "B3-assured-multi-robot"))
TRIAL_COMMAND = (shlex.split(os.environ["MULTIROBOT_PYTHON"]) if os.environ.get("MULTIROBOT_PYTHON")
                 else ["uv", "run", "--project", PACKAGE, "python"])
POLL_SEC = 0.1
# The RQ job that carries a trial is given 300 s (perfect/app/models.py), so the
# experiment ends a trial itself before that; the solver's own wall-clock cap in
# config.yaml (240 s) is below both.
TIMEOUT_SEC = 270


def child_environment():
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV")}
    env["MULTIROBOT_PACKAGE"] = PACKAGE
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env.setdefault(k, "1")
    return env


class MultiRobotCoordinationExperiment(BaseExperiment):
    _files = {
        "config.yaml": os.path.join(HERE, "config.yaml"),
        "execution.yaml": os.path.join(HERE, "execution.yaml"),
        "agr_fleet.yaml": os.path.join(PACKAGE, "model", "agr_fleet.yaml"),
    }

    def __init__(self, *args, **kwargs):
        self.p = None
        self.metrics = None
        super().__init__(*args, **kwargs)

    def _init(self):
        self.config = yaml.safe_load(open(self._working_files["config.yaml"]))
        self.execution = yaml.safe_load(open(self._working_files["execution.yaml"]))
        logger.info(f"allocation {self.config['allocation']}, margin "
                    f"{self.config['required_margin']}, sigma {self.execution['sigma']}, "
                    f"seed {self.execution['seed']}")

    def _check_if_ready(self) -> bool:
        return True

    async def _run(self):
        work = os.path.dirname(self._working_files["config.yaml"])
        job = os.path.join(work, "job.json")
        out = os.path.join(work, "metrics.json")
        with open(job, "w") as f:
            json.dump({"config": self.config, "execution": self.execution,
                       "fleet": os.path.join(PACKAGE, "model", "fleet_requirements.yaml"),
                       "model": str(self._working_files["agr_fleet.yaml"])}, f)

        self.p = subprocess.Popen(
            TRIAL_COMMAND + [os.path.join(HERE, "coordination_trial.py"), job, out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env=child_environment(),
        )
        while self.p.poll() is None:
            await asyncio.sleep(POLL_SEC)
        output = self.p.stdout.read()
        if self.p.returncode != 0:
            logger.error(f"the coordination trial exited {self.p.returncode}: {output}")
            return
        logger.info(output.strip())

        self.metrics = json.load(open(out))
        await self._relay_update("metrics", self.metrics)
        if self.metrics["min_rho"] is not None:
            await self._relay_update("min_rho", self.metrics["min_rho"])
        await self._relay_update("sim_time", self.metrics["solve_wall"])

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


Experiment = MultiRobotCoordinationExperiment


if __name__ == "__main__":
    import logging
    from flask import Config
    from perfect.app import config as default_config
    from perfect.experiment.experiment import mock_relay_update_callback, mock_stopping_callback
    from perfect.app.routes.utils import fill_specification_kwargs

    logger.setLevel(logging.INFO)
    config = Config(os.path.curdir)
    config.from_object(default_config.Config)
    # One design over the 1, 0, 2 allocation at a 0.35 m margin, as designs create -i
    # would build it, and one environment off the template, as environments
    # create_from_template would.
    library = json.load(open(os.path.join(HERE, "components.json")))
    design = [c["implementation"] for c in library if c["name"] == "alloc102-m0.35"]
    template = json.load(open(os.path.join(HERE, "environment_template.json")))[0]
    environment = fill_specification_kwargs(template["specification"], {"sigma": 0.09, "seed": 0})
    Experiment.launch(
        design=design,
        environment=environment,
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=0,
    )
