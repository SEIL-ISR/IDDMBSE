# Case studies

Six directories mirror the paper's Section IV. A1, A2 and A3 are the demonstrations
of Section IV-A and point into the tool directories at the repository root rather than
carrying their own algorithm code. B1, B2 and B3 are the demonstrations of Section
IV-B, each a self-contained project under this directory. A1 runs the Python and Julia
code in `trades-x/` over a recorded design-evaluation table; A3 runs a demo vendored
from VERITAS's own repositories. A2, B2 and B3 implement the paper's descriptions as
self-contained simulations, each with its own project and its own README describing
what it is and what it produced.

| id | paper | directory | run | needs | what it produces | checked here (2026-09-22) |
|---|---|---|---|---|---|---|
| A1 | IV-A.1, sensor-suite selection | [`A1-sensor-suite-selection/`](A1-sensor-suite-selection/README.md) | `./run.sh` | uv (the `trades-x/` project; no separate setup step) | the sensor-suite Pareto filter and MAVF ranking, run over the recorded 4095-design evaluation table | `run_case_study.py` prints `GATE G2: pass`; the recorded 4095-design run gives 96 Pareto designs (standard and MATLAB-compatible filters agree), the full 8191-design enumeration gives 120, and all 96 capped Pareto designs are still non-dominated in the full space. The data-driven stage then ran ten of those designs across eighteen scenarios as 180 PERFECT trials, all reaching `TrialState.SUCCESSFUL\|SHUT_DOWN` in 4 min 35 s on one runner, and ranked them by MAVF from what the trials reported |
| A2 | IV-A.2, risk-sensitive path planning | [`A2-risk-sensitive-planning/`](A2-risk-sensitive-planning/README.md) | `uv run python run_case_study.py` | uv (its own project) | a 3000-run risk-sensitive planning campaign on a synthetic world generator: failure and hazard rates, worst-case path length, three figure pairs (SVG + PDF) | 37 tests pass (`uv run pytest -q`); the recorded campaign ran 3000 planner runs in about 109 s and reproduces byte-identically run to run except plan time |
| A3 | IV-A.3, behavior-tree verification | [`A3-behavior-tree-verification/`](A3-behavior-tree-verification/README.md) | `./run.sh` | uv (the `veritas/` project); UPPAAL only to check the written model, not to run the demo | an UPPAAL network of timed automata (`BT_converted.xml`) composed from a behavior tree, for model checking and control synthesis in UPPAAL | the demo's output is byte-identical to the vendored upstream script's own output (md5 `9f1da760f65674818d156546092e6118`); `pytest tests/test_bt2automata.py tests/test_tbt_monitor.py` is 4 passed in 0.26 s (both from `veritas/README.md`) |
| B1 | IV-B.1, the contested-terrain range | [`B1-contested-terrain-range/`](B1-contested-terrain-range/README.md) | the `isaacsim/tools` quick start (fetch, build the terrain, open the scene, `range_doe.py` for a design point) | Isaac Sim, a local install with a GPU, to open the scene; `uv` for the tools | the range: compacted scene layers, a heightmap-rebuilt terrain, three design-of-experiments layers, two showcases (24 MB shipped; ~4.9 GiB of NVIDIA and Poly Haven content fetched locally) | 49 tests pass in `isaacsim/tools`; the base scene loads headless in Isaac Sim 6.0.1 with 22 978 prims and 0 unresolved references; an eight-point design-of-experiments campaign ran through PERFECT, each trial a headless Isaac Sim process, 411 s for the campaign, leaving a metric table, two figure pairs and eight pose trajectories |
| B2 | IV-B.2, robust perception via conformal prediction | [`B2-conformal-perception/`](B2-conformal-perception/README.md) | `uv run python run_case_study.py` | uv (its own project) | a closed-loop conformal-prediction navigation campaign on a synthetic detector and world: a coverage table, collision and success rates, two figure pairs | 19 tests pass (`uv run pytest -q`); the recorded campaign: 90 calibration episodes -> 2039 detection rows, held-out coverage 0.9037 at alpha = 0.10, closed-loop collisions 168 -> 16 of 200 episodes |
| B3 | IV-B.3, assured multi-robot coordination | [`B3-assured-multi-robot/`](B3-assured-multi-robot/README.md) | `uv run python run_case_study.py` | uv (its own project); HiGHS through scipy, no license needed | a fleet MILP synthesis, STL robustness scoring and model write-back: goal-satisfaction verdicts, three figure pairs, a `nav_msgs/Path` export | the joint MILP (1841 variables, 2390 constraints) reaches HiGHS status Optimal at relative gap 0.0 in about three and a half minutes, an identical solution across three runs; the STL robustness code agrees with an independent RTAMT computation to 1e-6 |

## Conventions

- A2, B2 and B3 are self-contained `uv` projects, each with its own `pyproject.toml` and
  `uv.lock`. A1 and A3 carry no project of their own: their `run.sh` changes directory
  into `trades-x/` or `veritas/` and runs a script that already lives there. B1 carries
  no code at all and points at `isaacsim/`.
- Plots are always SVG and PDF, never a raster format.
- `run.sh` exists for A1 and A3 only; A2, B2 and B3 are run with
  `uv run python run_case_study.py` from inside their own directory.
- If a ROS 2 environment is sourced in the shell, prefix `pytest` with
  `env -u PYTHONPATH` (its `site-packages` otherwise lands on `PYTHONPATH` and pytest
  tries to auto-load ROS's own plugins into an environment that does not have them).
