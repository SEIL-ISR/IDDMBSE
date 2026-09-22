"""PERFECT experiment: one design point of the Isaac Sim test range.

A trial is two subprocesses.

1. `range_doe.py` writes the design point as a USD layer under the trial's own
   run directory. The layer sublayers the base scene, so the range is composed
   fresh for every trial and nothing carries over between them. It needs
   usd-core, which the range tools' own environment has, so it runs through
   `uv run --project <range>/tools`.
2. `sim_trial.py` opens that layer in headless Isaac Sim, drives the AGR open
   loop for the requested simulated seconds and writes `metrics.json` and
   `trajectory.csv` beside the layer. It needs `isaacsim`, so it runs through
   Isaac Sim's own `python.sh`. One process per trial, under `timeout`, in its
   own session so that shutting the trial down takes the whole simulator with
   it.

The numbers in `metrics.json` are then relayed as trial updates, which is what
PERFECT stores and what `/api/v1/trials/<id>` gives back.

Where things are:

    IDDMBSE_RANGE_ROOT   the range directory (default: the one in this checkout)
    IDDMBSE_RANGE_RUNS   where run directories go (default: <range>/range/doe/runs)
    ISAACSIM_PYTHON      Isaac Sim's python.sh (default: ~/isaacsim/.../python.sh)
    UV                   the uv binary (default: uv)

The design carries the AGR variant as environment variables (`RANGE_ROBOT`,
`RANGE_SENSOR_PAYLOAD`, `RANGE_MULTI_AGR`); the environment carries the DOE
knobs and the drive profile in its specification.
"""

import asyncio
import json
import os
import pathlib
import signal
import subprocess
import time

from perfect.experiment.experiment import BaseExperiment, extract_kv_pairs
import perfect.logging


logger = perfect.logging.getLogger("core")

HERE = pathlib.Path(__file__).resolve().parent
RANGE_ROOT = pathlib.Path(os.environ.get("IDDMBSE_RANGE_ROOT") or HERE.parents[2] / "isaacsim")
RUNS_ROOT = pathlib.Path(os.environ.get("IDDMBSE_RANGE_RUNS") or RANGE_ROOT / "range" / "doe" / "runs")
ISAACSIM_PYTHON = os.environ.get("ISAACSIM_PYTHON") or os.path.expanduser(
    "~/isaacsim/_build/linux-x86_64/release/python.sh"
)
UV = os.environ.get("UV") or "uv"

# Metrics that are also Trial columns keep their name so that they land there;
# everything else is stored as an Update row only.
SIM_TIME = "sim_time"


class IsaacSimRangeExperiment(BaseExperiment):
    _files = {}  # the design point is a generated layer, not an edited file

    def __init__(self, design, environment, config, **kwargs):
        super().__init__(design, environment, config, **kwargs)
        # designs create coerces implementation strings to numbers where it
        # can, so "0" arrives as 0; environment variables have to be strings.
        self._settings = {
            k: str(v) for k, v in
            extract_kv_pairs("envvars", "envvar", "value", *design, environment)
        }
        self._doe = environment.get("doe", {})
        self._drive = environment.get("drive", {})
        self._start = environment.get("start", {})
        self._run_dir = RUNS_ROOT / ("trial_%s" % (self.id if self.id is not None else "local"))
        self._layer = self._run_dir / "layer.usda"
        self._report = {}
        self._metrics = {}
        self._returncode = None
        self._proc = None
        self._done = False
        self._sim_timeout = max(60, int(self._config["TIMEOUT_SEC"]) - 20)

    @property
    def name(self):
        return "%s_%s" % (self.__class__.__name__, self.id)

    # --------------------------------------------------------------
    # the design point

    def _doe_command(self):
        cmd = [UV, "run", "--project", str(RANGE_ROOT / "tools"), "python",
               str(RANGE_ROOT / "tools" / "range_doe.py"),
               "--out", str(self._layer), "--json"]
        for flag, key in (("--obstacle-density", "obstacle_density"),
                          ("--friction-static", "friction_static"),
                          ("--friction-dynamic", "friction_dynamic"),
                          ("--restitution", "restitution"),
                          ("--seed", "seed")):
            value = self._doe.get(key)
            if value is not None:
                cmd += [flag, str(int(value) if key == "seed" else value)]
        slope = self._doe.get("max_slope_deg")
        if slope not in (None, "", "none", "authored"):
            cmd += ["--max-slope-deg", str(slope)]
        if self._start:
            cmd += ["--agr-start-x", str(self._start["x"]),
                    "--agr-start-y", str(self._start["y"])]
        if self._settings.get("RANGE_SENSOR_PAYLOAD") == "1":
            cmd += ["--sensor-payload"]
        if int(self._settings.get("RANGE_MULTI_AGR", 0)):
            cmd += ["--multi-agr", str(int(self._settings["RANGE_MULTI_AGR"]))]
        return cmd

    def _init(self):
        self._run_dir.mkdir(parents=True, exist_ok=True)
        cmd = self._doe_command()
        logger.info("Writing the design point:\n%s", " ".join(cmd))
        done = subprocess.run(cmd, capture_output=True, text=True, env=self._subprocess_env())
        (self._run_dir / "doe.log").write_text(done.stderr)
        if done.returncode != 0:
            raise RuntimeError("range_doe.py exited %d: %s" % (done.returncode, done.stderr[-2000:]))
        self._report = json.loads(done.stdout)
        (self._run_dir / "doe_report.json").write_text(json.dumps(self._report, indent=2))
        logger.info("Design point: %d obstacles, height scale %s",
                    self._report["obstacle_count"], self._report["height_scale"])

    def _check_if_ready(self) -> bool:
        return self._layer.exists()

    def _subprocess_env(self):
        env = dict(os.environ)
        env.update(self._settings)
        # The login shell sources ROS 2, whose PYTHONPATH must not reach either
        # the range tools' environment or Isaac Sim's.
        env.pop("PYTHONPATH", None)
        return env

    # --------------------------------------------------------------
    # the simulation

    def _sim_command(self):
        cmd = ["timeout", "-k", "30", str(self._sim_timeout), ISAACSIM_PYTHON,
               str(HERE / "sim_trial.py"),
               "--layer", str(self._layer), "--out", str(self._run_dir)]
        for flag, key in (("--duration", "duration_s"), ("--speed", "speed_mps"),
                          ("--yaw-amplitude", "yaw_amplitude_radps"),
                          ("--yaw-period", "yaw_period_s"),
                          ("--wheel-radius", "wheel_radius_m"),
                          ("--settle", "settle_s")):
            value = self._drive.get(key)
            if value is not None:
                cmd += [flag, str(value)]
        return cmd

    async def _run(self):
        cmd = self._sim_command()
        logger.info("Starting headless Isaac Sim:\n%s", " ".join(cmd))
        with open(self._run_dir / "sim.log", "wb") as log:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=log, stderr=asyncio.subprocess.STDOUT,
                cwd=str(HERE), env=self._subprocess_env(), start_new_session=True,
            )
            self._returncode = await self._proc.wait()
        logger.info("Isaac Sim exited with %s", self._returncode)
        metrics_path = self._run_dir / "metrics.json"
        if metrics_path.exists():
            self._metrics = json.loads(metrics_path.read_text())
        await self._relay_metrics()
        self._done = True

    async def _relay_metrics(self):
        await self._relay_update("run_dir", str(self._run_dir))
        await self._relay_update("design_point", self._report.get("out"))
        for key in ("height_scale", "obstacle_count", "realised_coverage",
                    "requested_density", "min_spacing_measured_m", "seed"):
            if key in self._report:
                await self._relay_update(key, self._report[key])
        for key in ("slope_deg_after", "physics"):
            for sub, value in (self._report.get(key) or {}).items():
                await self._relay_update("%s_%s" % (key, sub), value)
        for key, value in self._metrics.items():
            if isinstance(value, dict):
                continue
            await self._relay_update(SIM_TIME if key == "sim_time_s" else key, value)

    # --------------------------------------------------------------
    # completion

    def _check_if_cancelled(self) -> bool:
        return False

    def _check_if_errored(self) -> bool:
        return self._done and not (self._returncode == 0 and self._metrics)

    def _check_if_successful(self) -> bool:
        return self._done and self._returncode == 0 and bool(self._metrics)

    def _check_if_timed_out(self) -> bool:
        return self.start_age >= self._config["TIMEOUT_SEC"]

    def _shut_down(self):
        # In the ordinary case _run has already waited for the simulator and
        # there is nothing here to do. This is for the case where the trial was
        # torn down around it.
        if self._proc is None or self._proc.returncode is not None:
            return
        logger.info("Isaac Sim is still up; signalling its process group")
        group = os.getpgid(self._proc.pid)
        for sig, pause in ((signal.SIGTERM, 10.0), (signal.SIGKILL, 0.0)):
            try:
                os.killpg(group, sig)
            except ProcessLookupError:
                return
            time.sleep(pause)


Experiment = IsaacSimRangeExperiment


if __name__ == "__main__":
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

    template = json.load(open(HERE / "templates" / "contested_terrain.json"))
    environment = fill_specification_kwargs(template["specification"], dict(
        obstacle_density=0.1, max_slope_deg=15, friction_static=0.6,
        friction_dynamic=0.5, restitution=0.1, seed=7, duration_s=10,
    ))
    design = json.load(open(HERE / "components.json"))[0]["implementation"]
    Experiment.launch(
        design=[design],
        environment=environment,
        config=config,
        relay_update_callback=mock_relay_update_callback,
        stopping_callback=mock_stopping_callback,
        trial_id=0,
    )
