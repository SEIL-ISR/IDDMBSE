# isaacsim-range

A PERFECT example whose trials are headless Isaac Sim runs on the contested
terrain test range in this repository's `isaacsim/` directory. One trial writes
a design point as a USD layer, opens it in Isaac Sim, drives the AGR open loop
for a stretch of simulated time, and returns the traverse as trial metrics. A
grid of design points is a PERFECT campaign: `isaacsim/tools/range_campaign.py`
creates the designs, the environments and the experiments, runs them through
`/api/v1`, and reads the trials back into a table and two figures.

## What a trial is

```
design       an AGR variant                         -> components.json
environment  one design point of the experiment     -> templates/contested_terrain.json
experiment   the two of them, run by the runner     -> experiment.py, sim_trial.py
```

`experiment.py` runs inside the PERFECT runner and starts two subprocesses.

1. `isaacsim/tools/range_doe.py`, through `uv run --project <range>/tools`,
   writes the design point to `<runs>/trial_<id>/layer.usda` and prints its
   report. The layer sublayers `range/sim_world2.usd`, so every trial composes
   the range from scratch and nothing carries over between them.
2. `sim_trial.py`, through Isaac Sim's own `python.sh`, opens that layer with
   `SimulationApp({"headless": True})`, deactivates the scene's teleop and ROS
   clock graphs so nothing else writes to the articulation, lets the robot
   settle, then drives it and writes `metrics.json` and `trajectory.csv` beside
   the layer. It runs under `timeout` in its own session, one process per
   trial.

`experiment.py` then relays every number in `metrics.json` as a trial update,
which is what `GET /api/v1/trials/<id>` returns and what the campaign driver
collects. `sim_time` is relayed under that name so it lands in the trial's own
column.

## What it needs

- a PERFECT stack: Redis, an RQ worker, the experiment runner and the Flask
  server, brought up as `perfect/README.md` describes, with
  `PERFECT_PROJECT_ROOT` set to this directory;
- Isaac Sim, found through `ISAACSIM_PYTHON` (default
  `~/isaacsim/_build/linux-x86_64/release/python.sh`);
- the range directory, found through `IDDMBSE_RANGE_ROOT` (default: the
  `isaacsim/` directory of this checkout) with its content fetched and its
  terrain built -- see `isaacsim/README.md`;
- `uv`, found through `UV`, to run the range tools in their own environment.

Run directories go to `IDDMBSE_RANGE_RUNS`, by default
`isaacsim/range/doe/runs/trial_<id>/`, which holds `layer.usda`,
`doe_report.json`, `trajectory.csv`, `metrics.json` and `sim.log`.

## The parameters

The environment template takes one value per design point:

| template argument | what it does |
|---|---|
| `obstacle_density` | fraction of the terrain footprint covered by rock silhouettes |
| `max_slope_deg` | scales the terrain height to put the 99th-percentile cell slope here; `authored` keeps the terrain's own relief |
| `friction_static`, `friction_dynamic`, `restitution` | the PhysX material on the terrain and on every obstacle |
| `seed` | the obstacle scatter |
| `duration_s` | simulated seconds to drive |

The rest of the specification is fixed in the template: the drive profile
(0.6 m/s forward with a 0.3 rad/s yaw sweep on a 10 s period, wheel radius
0.14 m, 1 s to settle) and the AGR's start on the terrain.

The design carries the AGR variant as environment variables. `components.json`
holds two implementations of one `agr` component:

| implementation | what it is |
|---|---|
| `Carter v2.4` | the base scene's robot, a 7-degree-of-freedom articulation |
| `Carter v2.4 x3` | the same, with two more Carters on a ring around it (`range_doe.py --multi-agr 2`) |

## The metrics a trial returns

From the trajectory: `distance_m`, `net_displacement_m`, `mean_speed_mps`,
`max_speed_mps`, `mean_pitch_deg` and `max_pitch_deg`, `mean_roll_deg` and
`max_roll_deg`, `max_climb_m`, `z_range_m`, `settle_z_m`.

About the terrain and the obstacles: `obstacle_encounters` (how many distinct
DOE obstacles the robot came within 1.5 m of), `nearest_obstacle_m`, `stuck`
and `stuck_seconds` (the longest stretch below 0.05 m/s; `stuck` is that
stretch over 2 s), `unstable` and `max_speed_mps` (a step speed over 10 m/s
means the contact solver threw the robot rather than the robot driving).

About the run: `prim_count`, `mesh_count`, `unresolved_references`,
`obstacle_count`, `sim_time_s`, `open_seconds`, `physics_init_seconds`,
`first_step_seconds`, `wall_per_sim_s`, `wall_total_seconds`, and the design
point's own report (`height_scale`, `realised_coverage`, the slope percentiles,
the friction pair).

`trajectory.csv` has one row per physics step: `t, x, y, z, roll, pitch, yaw, v`.

## Running one design point

`load.bash` is the manual sequence: reset the database, load
`components.json`, create the design, load the environment template, create one
environment, create the experiment. Then `experiments run range`, or
`POST /api/v1/experiments` with the design and environment ids.

## Running a campaign

From the range tools:

```bash
python range_campaign.py --plan
python range_campaign.py --submit --project-root <this directory> \
    --densities 0.1,0.4,0.8 --slopes 15,25 --duration 30 --robots "Carter v2.4"
python range_campaign.py --collect --out ../results/campaign.csv
python range_campaign.py --plot    --out ../results/campaign.csv
```

`--submit` runs in the PERFECT environment, because the setup goes through the
Flask CLI; `--collect` and `--plot` run in the range tools' environment,
because they need numpy and matplotlib.

## The campaign that was run here

Eight trials on 2026-09-22, through a PERFECT stack on Redis 6390, Flask 5001
and the runner on 8003, with headless Isaac Sim 6.0.1 launched by the runner's
job: densities 0.1, 0.4 and 0.8 crossed with 99th-percentile slope targets of
15° and 25°, plus the shipped baseline design point (density 0.3 at 15°) and
one run at the terrain's authored relief. Friction 0.6 / 0.5, restitution 0.1,
seed 7, 30 simulated seconds each, one AGR. Every trial reached
`TrialState.SUCCESSFUL|SHUT_DOWN`.

| trial | density | slope | obstacles | distance m | mean speed m/s | max pitch | max roll | max climb m | encounters | stuck | wall / sim s | trial wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.1 | 15° | 285 | 12.99 | 0.43 | 16.3° | 14.5° | 0.738 | 0 | no | 0.187 | 42.9 |
| 2 | 0.1 | 25° | 285 | 9.72 | 0.32 | 16.9° | 15.8° | 0.334 | 0 | no | 0.213 | 42.8 |
| 3 | 0.4 | 15° | 1147 | 13.45 | 0.45 | 16.3° | 14.5° | 0.738 | 3 | no | 0.179 | 41.8 |
| 4 | 0.4 | 25° | 1147 | 9.72 | 0.32 | 16.9° | 15.8° | 0.334 | 0 | no | 0.201 | 42.5 |
| 5 | 0.8 | 15° | 2267 | 3.21 | 0.11 | 7.3° | 6.3° | 0.011 | 0 | yes, 4.2 s | 0.181 | 41.8 |
| 6 | 0.8 | 25° | 2267 | 5.54 | 0.18 | 11.7° | 8.8° | 0.017 | 0 | no | 0.208 | 43.1 |
| 7 | 0.3 | 15° | 857 | 13.20 | 0.44 | 18.3° | 29.7° | 0.674 | 2 | no | 0.182 | 42.5 |
| 8 | 0.1 | authored | 285 | 3.71 | 0.12 | 17.9° | 179.0° | 0.542 | 0 | no | 0.383 | 48.6 |

Reading the table: at the 15° target the AGR covers 13 m of the 30 s run at the
two lower densities and 3.2 m at 0.8, where it spends 4.2 s below 0.05 m/s --
the obstacle field is close to the minimum spacing there, about 1 m between
rock centres. The 25° target costs about a quarter of the distance at the
lower densities and, at density 0.1, raises the mean pitch from 6.3° to 10.8°. At the terrain's
authored relief the run ends with a maximum roll of 179°: the AGR turns over
after 3.7 m. Trials 2 and 4 return the same numbers because neither traverse
touched an obstacle; trials 1 and 3 differ where trial 3's three contacts
redirected it.

The table is `isaacsim/results/campaign.csv`, one row per trial with every
relayed metric; the per-trial pose trajectories are in
`isaacsim/results/trajectories/`. The two figure pairs are
`campaign_metrics.svg`/`.pdf` (distance and maximum pitch against obstacle
density, one line per slope target) and
`campaign_trajectories.svg`/`.pdf` (the eight traverses over the terrain).

Wall times: stage open 13.8 to 14.2 s, physics initialisation 5.75 to 6.14 s,
first physics step 6.91 to 7.29 s, 0.179 to 0.383 s of wall per simulated
second, 41.8 to 48.6 s per trial. The eight trials took 346 s of the campaign's
411 s; the rest is the database, the library, the designs, the environments and
the eight API calls.

## Timeouts

`config.py` sets `TIMEOUT_SEC` to 260 s, and `experiment.py` gives
`sim_trial.py` 20 s less than that, so the simulator is the first thing to go
and the trial ends itself well inside the 300 s timeout the RQ job carries. A
trial in the campaign above took 48.6 s at most.

PhysX cooks the terrain's collision mesh on the first load and caches it. On a
cold cache that first load takes about 165 s longer than the numbers above;
run one trial by hand first
(`sim_trial.py --layer <a layer> --out /tmp/warm --duration 1`) if you want
that cost outside a campaign.
