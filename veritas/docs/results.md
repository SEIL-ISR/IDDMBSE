# Over the campaigns run here

The [README](../README.md)'s data-driven and runtime sections describe the two modules on
their own demo data. This page is the same two modules pointed at the campaigns the rest of this
repository actually ran: the 180-trial sensor-suite campaign recorded in
[`trades-x/case-studies/sensor-suite/README.md`](../../trades-x/case-studies/sensor-suite/README.md),
the eight-trial Isaac Sim range campaign recorded in [`isaacsim/README.md`](../../isaacsim/README.md),
and the three case-study campaigns summarised at the end. The PERFECT databases were opened
read-only. The reports are in `datadriven/results/` and the replay verdicts in
`runtime/stl-observer/results/range/`. The commands run from `veritas/`.

## Failure rates over the sensor-suite campaign

```
uv run python datadriven/report.py \
    --db ../perfect/examples/sensor-suite-sim/sensor-suite-sim.db --tag ddo \
    --group-by design --failure-metric success_rate --failure-below 1.0 \
    --out datadriven/results/sensor-suite
```

Every one of the 180 trials reached `TrialState.SUCCESSFUL|SHUT_DOWN`, so the state PERFECT
records separates nothing here: the runner finishing a trial says the simulation ran, not that
the robot arrived. `--failure-metric` takes the outcome from the trial's own number instead —
each trial is twelve noise draws of the same scenario and reports the fraction that reached
the goal, so `--failure-below 1.0` counts a trial as a failure when at least one of its twelve
draws did not. 48 of the 180 trials are failures under that criterion. `--group-by design`
folds a design's eighteen scenarios into one group, which is why the environment column reads
`all`.

| design | trials | failures | rate | exact interval | Wilson interval | exact upper | trials for 0.05 |
|---|---|---|---|---|---|---|---|
| design-2185 | 18 | 1 | 0.0556 | [0.0014, 0.2729] | [0.0099, 0.2576] | 0.2377 | 93 |
| design-4 | 18 | 11 | 0.6111 | [0.3575, 0.827] | [0.3862, 0.7969] | 0.801 | 361 |
| design-4234 | 18 | 1 | 0.0556 | [0.0014, 0.2729] | [0.0099, 0.2576] | 0.2377 | 93 |
| design-4370 | 18 | 1 | 0.0556 | [0.0014, 0.2729] | [0.0099, 0.2576] | 0.2377 | 93 |
| design-512 | 18 | 6 | 0.3333 | [0.1334, 0.5901] | [0.1628, 0.5625] | 0.554 | 234 |
| design-549 | 18 | 1 | 0.0556 | [0.0014, 0.2729] | [0.0099, 0.2576] | 0.2377 | 93 |
| design-785 | 18 | 1 | 0.0556 | [0.0014, 0.2729] | [0.0099, 0.2576] | 0.2377 | 93 |
| frontier-1 | 18 | 10 | 0.5556 | [0.3076, 0.7847] | [0.3372, 0.7544] | 0.756 | 336 |
| frontier-3 | 18 | 8 | 0.4444 | [0.2153, 0.6924] | [0.2456, 0.6628] | 0.6594 | 286 |
| frontier-38 | 18 | 8 | 0.4444 | [0.2153, 0.6924] | [0.2456, 0.6628] | 0.6594 | 286 |

The five four-sensor designs sit at one failure in eighteen; `design-4`, the single-camera
design that the catalogue attributes alone rank first, is at eleven. The last column is the
useful one for planning the next campaign: at their observed failure counts these designs need
93 to 361 trials each before a 95% upper bound reaches 0.05, against the 18 they have.
`failure_rates.svg` / `.pdf` draw the same table.

## The runtime observer over the range trajectories

Each of the eight range trials wrote a pose trajectory at 60 Hz. `replay_observer.py` runs the
three obligations of `specs/range_safety.yaml` over all eight at once and writes a verdict
table and a figure:

```
uv run python runtime/stl-observer/replay_observer.py \
    ../isaacsim/results/trajectories/trial_*.csv \
    --spec runtime/stl-observer/specs/range_safety.yaml \
    --points ../isaacsim/results/campaign.csv --point-columns environment \
    --out runtime/stl-observer/results/range
```

The obligations are 0.35 rad (20°) of roll, 0.35 rad of pitch, and reaching 0.2 m/s somewhere
in the last 20 s against the 0.6 m/s the trial commands. `--points` carries each trace's design
point over from the campaign table. The robustness reported is the worst value over the
samples the monitor was actually judging, so the progress monitor's 20 s warm-up window is left
out of it.

| trace | design point | roll_safety | pitch_safety | progress |
|---|---|---|---|---|
| trial_1.csv | density 0.1, slope 15.0 | satisfied, worst rho 0.119 | satisfied, worst rho 0.0658 | satisfied, worst rho 1.2256 |
| trial_2.csv | density 0.1, slope 25.0 | satisfied, worst rho 0.0751 | satisfied, worst rho 0.0563 | satisfied, worst rho 0.5616 |
| trial_3.csv | density 0.4, slope 15.0 | satisfied, worst rho 0.108 | satisfied, worst rho 0.0658 | satisfied, worst rho 1.2256 |
| trial_4.csv | density 0.4, slope 25.0 | satisfied, worst rho 0.0751 | satisfied, worst rho 0.0563 | satisfied, worst rho 0.5616 |
| trial_5.csv | density 0.8, slope 15.0 | satisfied, worst rho 0.2408 | satisfied, worst rho 0.2232 | violated at 25.7 s, worst rho -0.1098 |
| trial_6.csv | density 0.8, slope 25.0 | satisfied, worst rho 0.2001 | satisfied, worst rho 0.1463 | satisfied, worst rho 0.274 |
| trial_7.csv | density 0.3, slope 15.0 | violated at 29.85 s, worst rho -0.1278 | satisfied, worst rho 0.031 | satisfied, worst rho 1.8721 |
| trial_8.csv | density 0.1, authored relief | violated at 0.0 s, worst rho -2.7723 | satisfied, worst rho 0.037 | satisfied, worst rho 0.2508 |

(The design-point column is abbreviated here; `verdicts.md` and `verdicts.csv` carry the full
label, the friction pair and the seed, and `verdicts.csv` splits every cell into its own
numeric columns.)

Three of the eight traces break an obligation, and each break is a different thing happening to
the robot. `trial_8` runs at the terrain's authored relief: its roll is already 1.98 rad at the
first recorded sample and peaks at 3.12 rad half a second in, so the robot is on its side
before the drive starts — that is the −2.77 worst robustness, and it is why the panel is drawn
on a symmetric-log axis. `trial_7` stays upright for 29.8 s of a 30 s run and then catches a
rock at 0.52 rad of roll. `trial_5` is the densest obstacle field at the shallow slope: it never
falls over, but it loses its 20 s progress window at 25.7 s, which is the same 4.2 s of being
stuck that the campaign table reports. Pitch never leaves its bound on any of the eight; the
tightest margin is 0.031 rad on `trial_7`. `robustness.svg` / `.pdf` plot all three obligations
over time, one line per trace, with the progress monitor's warm-up shaded.

## Failure rates over the range campaign

The same report tool on the range campaign's database, with the mission criterion taken from
the distance the robot covered in its 30 s:

```
uv run python datadriven/report.py \
    --db ../perfect/examples/isaacsim-range/isaacsim-range.db \
    --failure-metric distance_m --failure-below 5.0 \
    --out datadriven/results/range
```

| design point | trials | failures | rate | exact interval | exact upper | trials for 0.05 |
|---|---|---|---|---|---|---|
| density 0.1, slope 15.0 | 1 | 0 | 0.0 | [0.0, 0.975] | 0.95 | 59 |
| density 0.1, slope 25.0 | 1 | 0 | 0.0 | [0.0, 0.975] | 0.95 | 59 |
| density 0.1, authored relief | 1 | 1 | 1.0 | [0.025, 1.0] | 1.0 | 93 |
| density 0.3, slope 15.0 | 1 | 0 | 0.0 | [0.0, 0.975] | 0.95 | 59 |
| density 0.4, slope 15.0 | 1 | 0 | 0.0 | [0.0, 0.975] | 0.95 | 59 |
| density 0.4, slope 25.0 | 1 | 0 | 0.0 | [0.0, 0.975] | 0.95 | 59 |
| density 0.8, slope 15.0 | 1 | 1 | 1.0 | [0.025, 1.0] | 1.0 | 93 |
| density 0.8, slope 25.0 | 1 | 0 | 0.0 | [0.0, 0.975] | 0.95 | 59 |

Two of the eight design points fall short of 5 m: the densest obstacle field at the shallow
slope and the authored relief — the same two traces the observer flagged. The intervals are
what a single trial per design point buys: at zero failures and one trial the exact 95%
interval is [0, 0.975] and the one-sided upper bound is 0.95, which rules out almost nothing,
and the last column says such a point needs 59 trials before that bound reaches 0.05. A design
point is a seeded Isaac Sim configuration, so repeats mean new seeds; the campaign script takes
a `--seeds` list for exactly that.

## The three case-study campaigns

The risk-sensitive planner (300 trials), the conformal calibration (270 trials) and the assured
multi-robot study (216 trials) also ran as PERFECT campaigns; their READMEs carry the
`report.py` command and the full tables, and the reports, figure pairs and campaign databases
are in `datadriven/results/rarrt/`, `datadriven/results/conformal/` and
`datadriven/results/multirobot/`.

| campaign | failure criterion | designs | trials per design | failure rates | exact upper bounds | trials for 0.05 |
|---|---|---|---|---|---|---|
| [RA-RRT* planning](../../case-studies/A2-risk-sensitive-planning/README.md) | any of the trial's 400 executions over the traversal budget | 5 policies | 60 | 0.5333 (cvar0.5) to 0.6167 (rrtstar) | 0.6444 to 0.7219 | 855 to 968 |
| [conformal calibration](../../case-studies/B2-conformal-perception/README.md) | the episode ended in a collision | 3 detectors | 90 | 0.5667 (sharp) to 0.9222 (degraded) | 0.6554 to 0.9629 | 1282 to 1985 |
| [assured multi-robot](../../case-studies/B3-assured-multi-robot/README.md) | the executed min rho is below zero (the 162 trials that carry one; 52 fail) | 18 allocation and margin designs | 9 | 0.0 (six designs) to 1.0 (alloc120-m0.15) | 0.2831 to 1.0 | 59 to 311 |

## What runs here

| what | what it printed |
|---|---|
| `uv venv --python 3.10 && uv sync` | 23 packages on CPython 3.10.20 |
| `pytest -q` over the whole suite | 66 passed, 2 skipped in 5.1 s; 67 passed, 1 skipped in 5.9 s with `UPPAAL_HOME` set |
| `demo.py` (behavior tree) | `BT_converted.xml`, md5 `96b2e35c435ce771191351242e29cb77`, the upstream output plus the DOCTYPE line |
| `demo_battery.py` | 2 templates, 9 locations, 9 edges, 12 queries, 4 warnings; `pyuppaal.UModel` parsed the copy back with the same templates and 12 queries |
| `verify.py` on both models, UPPAAL 5.0.0 | 12 verdicts in 0.02 s and 2 in 0.28 s; the verdict table in the README's model-based module |
| `verify.py` with no UPPAAL on the machine | one line naming `UPPAAL_HOME`, exit 2 |
| `demo_campaign.py` | dummy database: 1 trial, 0 failures, exact upper bound 0.95, 59 trials needed for 0.05. Synthetic: 17/200 failures, rate 0.085, exact [0.0503, 0.1326] containing the true 0.10565; at 2000 trials 204 failures and a DKW-corrected 5% quantile of −0.1133 |
| `report.py` on the demo campaign | 240 trials in 4 design/environment groups, 12 failures, the table in the README's data-driven module, `report.{json,md,csv}` and `failure_rates.{svg,pdf}` |
| `report.py` on PERFECT's dummy database | 1 trial in 1 group, exact [0.0, 0.975], upper bound 0.95, 59 trials for the 0.05 target |
| `demo_synthetic.py` | final `(rho, state)` = `(0.012, 1)` and `(-0.03, 0)` for the two traces |
| `uv sync --extra rl` then `main.py --n-rollouts 2 --no-video` | ran headless in 14.0 s, printed `Success Rate: 1.0` |
| `pytest tests/test_ltbt.py` with the `milp` extra | 2 passed; the n=5 solve returned status OPTIMAL |
| `robot.py` unmodified at N=15 | "Model too large for size-limited license" — it wants a full Gurobi license |
| `plot.py` on the saved `robot/` solutions | a 1-page 166 KB PDF, the same size as the upstream figure |
| `stl_observer_node.py` + `test_publisher.py` on ROS 2 Jazzy, domain 87 | `VIOLATION soc_safety [P.1.4] at t=19.9s robustness -0.0015`; the robustness topic ran 0.0045, 0.0030, 0.0015, 0.0000, −0.0015 through the crossing and the violation topic flipped false → true on the same sample; all six `/veritas/…` topics on the graph; `goal_liveness` −0.5 for 56 samples then +0.5 for 75, no violation, warmup 180 s |
| `replay_observer.py` on the range trace | 1200 samples; `roll_safety` clean at 0.2, `pitch_safety` first violated at 21.45 s, `progress` first violated at 45.0 s with robustness −0.18 |
| `report.py` on the sensor-suite campaign database | 180 trials in 10 design groups, 48 failures under the twelve-draw criterion, rates 0.0556 to 0.6111, the table above |
| `report.py` on the range campaign database | 8 trials in 8 design-point groups, 2 failures under the 5 m criterion, exact [0.0, 0.975] at the six that cleared it |
| `replay_observer.py` on all eight range trajectories | 8 verdict rows; `roll_safety` violated on 2 traces (at 29.85 s and at 0.0 s), `progress` on 1 (at 25.7 s), `pitch_safety` on none, tightest pitch margin 0.031 rad |
