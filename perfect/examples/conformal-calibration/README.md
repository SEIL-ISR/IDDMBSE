# conformal-calibration

A PERFECT example with no simulator behind it, in which **the detector is the
design variable and what a trial produces is labelled data**. A design is one
detector configuration, an environment is one clutter band with one seed, and a
trial runs the closed loop and writes down every detection it made with the
ground-truth box beside it. The campaign this example serves is
`case-studies/B2-conformal-perception/run_perfect_campaign.py`.

Conformal prediction is only as sound as its calibration data, and that data has
to be ground-truth-labelled and drawn from the closed-loop states the robot will
actually visit — not from boxes sampled in the abstract. Producing exactly that,
at scale and under a stated distribution shift, is what this example asks
PERFECT for.

The perception stack and the planner are not in this directory. They are the
`cpnav` package of `case-studies/B2-conformal-perception`, and
`calibration_run.py` runs its campaign function. That is deliberate: the case
study calibrates on these rows, so they have to be the rows the case study's own
code produces, and `tests/test_calibration_run.py` holds them to it.

## What a trial does

A robot crosses a 20 m square arena with rectangular obstacles, from one corner
to the other. Every control step it detects the obstacles, inflates them by its
own footprint, rasterises them onto a grid, recomputes the cost-to-go field and
moves one cell down it. An episode ends when the robot reaches the goal, drives
into a true obstacle, or runs out of steps. Arenas in which the goal is
unreachable even with perfect perception are dropped before the episode starts,
so a failure is the detector's and not the arena's.

The detector is a seeded noise model over the true boxes: the centre is jittered
by an amount that grows with range, and the reported box is a random fraction of
the true size, badly underestimated for a fixed minority of objects. It
reproduces the two failure modes that matter — boxes that are displaced and
boxes that are too small — and it has one knob, `shift`, that makes both worse.

The trial runs with no conformal inflation at all. That is the point: the raw
detections are what has to be calibrated, and the states the raw policy visits
are the states the calibration has to cover.

## What a detector configuration is

`components.json` gives every configuration one component implementation of the
`detector` component, whose `implementation` is a single `files` update writing
two values into `detector.yaml`:

| design | shift | what it is |
|---|---|---|
| `sharp` | -0.6 | less jitter and less shrink than nominal |
| `nominal` | 0.0 | the detector the model was written around |
| `degraded` | 1.0 | twice the jitter and a further 15% shrink |

A design holds exactly one of them, so a campaign over the three configurations
is three designs.

## How the design and the environment reach the trial

Through PERFECT's own file-editing mechanism, not through a side channel.

PERFECT copies `detector.yaml` and `scenario.yaml` into the trial's working
directory and then applies, in order, the `files` updates of every component
implementation in the design and then those of the environment specification.
`experiment.py` reads the two files afterwards and hands their contents to
`calibration_run.py`; it never looks at the raw design or environment
dictionary.

`environment_template.json` is an environment template with three arguments:

| argument | what it picks |
|---|---|
| `$clutter` | `sparse`, `nominal` or `dense`, naming one of the three obstacle-count bands in `scenario.yaml` |
| `$seed` | the arena and every draw the detector makes in it |
| `$n_episodes` | how many closed-loop episodes the trial runs |

The obstacle count is a module constant of `cpnav.world`, so
`calibration_run.py` sets it from the chosen band before the arenas are drawn.
That is the only value it writes inside the package.

## What a trial reports

`await self._relay_update("metrics", ...)` sends one dictionary, which PERFECT
stores as an `Update` row on the trial and `GET /api/v1/trials/<id>` returns.

The data is `rows`: the flat per-detection table, one row per detection per
frame, with the fourteen columns `cpnav.planner.ROW_COLUMNS` names — `episode`,
`step`, `object`, `robot_x`, `robot_y`, `range`, the four `true_*` corners and
the four `det_*` corners. They are reported to four decimals, the precision the
case study's own row table is written at. Beside them:

| key | what it is |
|---|---|
| `status`, `length`, `steps`, `waits` | one entry per episode: how it ended, how far the robot went, how many steps it moved, how many it stood still |
| `collisions`, `successes`, `stalls`, `collision_rate`, `success_rate` | the same, counted |
| `detections`, `score_mean`, `score_max` | how many detections, and their nonconformity scores |
| `coverage_margin` | `-score_max`: positive exactly when every detection of the trial already covered its object with no inflation at all |
| `detector`, `shift`, `clutter`, `band`, `seed`, `episodes` | what the trial ran under |

`collision_rate` and `coverage_margin` are relayed a second time on their own,
because a tool that scores a campaign asks for one named number per trial.

## The interpreter and the perception package

The closed loop is numpy. The Python environment that carries PERFECT does not
have to be: `experiment.py` starts `calibration_run.py` in a child process, with
the interpreter named by `CPNAV_PYTHON` if that is set and the running one
otherwise. The child finds the `cpnav` package at `CPNAV_PACKAGE`, which
defaults to the case study's directory in this repository.

## Run one trial without a server

```bash
cd perfect/examples/conformal-calibration
PERFECT_PROJECT_ROOT=$PWD CPNAV_PYTHON=$(which python3) python experiment.py
```

That builds a one-component design over the `nominal` detector and one
environment off the template in process and runs the full experiment lifecycle
with the mock callbacks. Recorded on 2026-09-22, two episodes in the dense
band, seed 4:

```
INFO core experiment._init:75 - detector nominal, clutter dense, seed 4.0, 2.0 episodes
INFO core experiment._run:99 - nominal dense seed 4 2 episodes, 207 detections, 2 collisions
INFO core experiment.run:293 - Shut down ConformalCalibrationExperiment
```

Both episodes ended in a collision, which is what the raw detections do in a
dense arena and what the rest of the case study is about.

The trial itself also runs on its own:

```bash
python3 - <<'EOF'
import json, yaml
detector = yaml.safe_load(open("detector.yaml"))
scenario = yaml.safe_load(open("scenario.yaml"))
scenario.update(clutter="dense", seed=4, n_episodes=2)
json.dump({"detector": detector, "scenario": scenario}, open("job.json", "w"))
EOF
python3 calibration_run.py job.json metrics.json
```

## Run it under a PERFECT stack

The bring-up is the one `perfect/README.md` records for the `dummy` example,
with this directory as `PERFECT_PROJECT_ROOT` and `CPNAV_PYTHON` and
`CPNAV_PACKAGE` exported to every process that needs them. After `db upgrade`:

```bash
python -m flask --app perfect.app components load_component_implementations components.json
python -m flask --app perfect.app environments create_templates_from_file environment_template.json
python -m flask --app perfect.app designs create nominal -i --name nominal --tag conformal
python -m flask --app perfect.app environments create_from_template 1 \
    clutter:=dense seed:=4 n_episodes:=1 -n "dense-seed4" -t conformal
python -m flask --app perfect.app experiments create conformal conformal -t conformal
python -m flask --app perfect.app experiments run conformal
```

The same sequence over HTTP is what `tradesx.ddo_api` does, and
`case-studies/B2-conformal-perception/README.md` records a 270-trial campaign
run that way.

## Tests

The tests need numpy, pyyaml and pytest, and they import `cpnav` from the case
study:

```bash
cd perfect/examples/conformal-calibration
python3 -m pytest tests -q
```

They check that the rows a trial relays are `cpnav.campaign.run_campaign`'s own
rows to the precision they are reported at, that a denser clutter band puts more
obstacles in front of the robot, that the relayed summaries are the ones the
relayed rows and episodes carry, that a degraded detector scores worse than a
sharp one, that the counts survive the float substitution PERFECT applies to
template arguments, and that each entry of `components.json` writes the detector
it is named after into `detector.yaml`. Recorded on 2026-09-22:

```
.............                                                            [100%]
13 passed in 1.00s
```

## Files

| file | what it is |
|---|---|
| `experiment.py` | the PERFECT experiment class; reads the two working files, runs the episodes, relays the rows |
| `calibration_run.py` | one trial: set the clutter band, run the closed loop, report the detections and the outcomes |
| `components.json` | the detector library, one component implementation per configuration |
| `detector.yaml` | the detector defaults; the design overwrites them |
| `scenario.yaml` | the scenario defaults, the clutter bands and the base seed; the environment overwrites the first three |
| `environment_template.json` | the environment template with `$clutter`, `$seed`, `$n_episodes` |
| `tests/` | the trial against the case study's own campaign function, and the two working files against the design and the environment |
