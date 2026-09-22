# IDDMBSE

This is the companion repository for **"IDDMBSE: Integrating Data-Driven and Model-Based
Systems Engineering for Trusted Autonomous Cyber-Physical Systems,"** by John S. Baras,
Sai Sandeep Damera, Ryan Matheu, Clinton Enwerem and Praveen M.S. Kumar, Institute for
Systems Research, University of Maryland, College Park. The paper appears at the IEEE
International Symposium on Systems Engineering (ISSE), 2026; [`CITATION.cff`](CITATION.cff)
carries the citation. The paper's contributions footnote reads: "The IDDMBSE tool chain and
contested-terrain test range will be released at https://github.com/seil-umd/IDDMBSE." —
this is that release. IDDMBSE extends the MBSE V-process with a data-driven loop at every
step, anchored in SysML, the autonomy stack, and a hybrid model-based plus data-driven
trade-off architecture, instantiated here as an open-source tool chain (PERFECT,
TRADES-X, VERITAS) and demonstrated on a Trusted Autonomous Ground Robot in a
contested-terrain Isaac Sim test range.

## What is here

| directory | what it is | origin | what ran here (2026-09-22) |
|---|---|---|---|
| [`perfect/`](perfect/README.md) | SysML-to-ROS 2 performance-evaluation tool: a Flask server, an RQ/Redis job queue and distributed runners | recovered lab code, from the University of Maryland lab's GitLab branch `example-isaacsim-husky` | the `dummy` example end to end — one trial to `TrialState.SUCCESSFUL\|SHUT_DOWN` in 19.3 s, `devtools/smoke_dummy.sh` printing `PASS` in 46.3 s — and four campaigns driven over `/api/v1`: 180 sensor-suite trials, 8 headless Isaac Sim range trials, 300 risk-sensitive planner trials and 270 conformal-calibration trials |
| [`trades-x/`](trades-x/README.md) | the trade-off stage: model-based optimization (Julia) then data-driven optimization and a Multi-Attribute Value Function ranking (Python) | recovered lab code (the Julia MBO package) plus code built for this release (the greedy submodular search, the full design-space enumeration, the Python/JAX sensitivity path, the requirement partition) | 57 tests; the full 8191-design enumeration gives 120 non-dominated designs; a 180-trial data-driven campaign against a live PERFECT stack, ranked by MAVF from PERFECT's own trial table |
| [`veritas/`](veritas/README.md) | the verification layer: a model-based module (SysML/behavior-tree to UPPAAL), a data-driven module (failure-rate and STL-robustness statistics over a PERFECT campaign) and a runtime module (an STL observer plus a behavior-tree monitor) | vendored from a coauthor's two repositories (the behavior-tree modules, see [`veritas/ATTRIBUTION.md`](veritas/ATTRIBUTION.md)) plus code built for this release (the SysML-to-UPPAAL front end, the whole data-driven module, the deployed-stack observer) | 62 tests, 63 with UPPAAL on the machine; UPPAAL 5.0.0 returned 12 verdicts on the battery model and 2 on the behavior-tree network; failure-rate reports over both PERFECT campaigns; the STL observer live on a ROS 2 graph and replayed over all eight range trajectories |
| [`sysml/`](sysml/README.md) | the SysML v1 model of the AGR stack (Magic Systems of Systems Architect) and the MATLAB workbench that calls PERFECT from it | recovered lab code | the shipped model's checksum matches the lab's drop; 69 blocks, 3 constraint blocks, 23 requirements and 51 diagrams read out of it, and all 23 requirements are carried into the UPPAAL model VERITAS writes from it; the bridge scripts take the server URL and the workspace path from the environment and post to `/api/v1/run` |
| [`isaacsim/`](isaacsim/README.md) | the contested-terrain test range: compacted USD scene layers, the rock meshes, a 14.8 MB heightmap of the terrain (rebuilt locally by `isaacsim/tools/build_terrain.py`), the design-of-experiments layers written by `isaacsim/tools/range_doe.py` (obstacle density, slope scaling, PhysX friction/restitution, extra robots, sensor payload) and two showcase scenes; NVIDIA's and Poly Haven's content is fetched to your machine by `isaacsim/tools/fetch_assets.py` from a hash-verified manifest, not redistributed | the scene, terrain and showcases are the lab's earlier authoring, compacted and relinked; the design-of-experiments script, the heightmap pipeline, the campaign driver and the fetch tooling were built for this release | 49 tests in `isaacsim/tools`; an eight-trial campaign driven by PERFECT, each trial a headless Isaac Sim 6.0.1 process, 411 s for the campaign, leaving a metric table, two figure pairs and eight pose trajectories; the base scene loads with 22 978 prims and 0 unresolved references |
| [`case-studies/`](case-studies/README.md) | six directories mirroring the paper's Section IV: three demonstrations pointing into the tool directories above, three self-contained projects released with the paper | mixed — see [`case-studies/README.md`](case-studies/README.md) | the per-case-study numbers are in that file's table and in the bullets below |
| [`seil-r2/`](seil-r2/README.md) | a ROS 2 colcon workspace: an Isaac Sim Carter navigation baseline (Nav2, AMCL) plus the container it builds in | recovered lab code, with the container rebuilt for this release | both images build, about 3 GB each; `colcon build` inside them prints `Summary: 6 packages finished [4.77s]`; `ros2 pkg list` in the container lists all six and `ros2 launch -s` parses every launch file |
| [`plugins/`](plugins/README.md) | an rviz2 panel for controller and planner selection | recovered lab code | the ament package as the lab wrote it: the panel header and source, `plugins_description.xml`, the `switch.xml` behavior tree with the `ControllerSelector` and `PlannerSelector` nodes it drives, and a parameter file listing the controller and planner plugins it reads |

## Map to the paper

Section titles are quoted from the camera-ready; its numbering is I Introduction, II Related
Work, III The IDDMBSE Framework, IV Case Studies, V Conclusion.

| paper section | what it describes | where in this repository |
|---|---|---|
| III-A, "Methodology: Data-Driven Augmentation of MBSE" | the requirements-driven data-driven loop over the MBSE V-process, and the SysML modeling hub | [`sysml/`](sysml/README.md) |
| III-B, "PERFECT: SysML-to-ROS2 Performance Evaluation" | SysML-to-ROS 2 mapping and distributed performance evaluation | [`perfect/`](perfect/README.md), and [`perfect/docs/sysml-binding.md`](perfect/docs/sysml-binding.md) for how a model binds to it |
| III-C, "TRADES-X: Hybrid Design-Space Exploration" | the model-based then data-driven design-space exploration and the MAVF ranking | [`trades-x/`](trades-x/README.md) |
| III-D, "VERITAS: Three-Module Verification of Trusted Autonomy" | the three verification modules | `veritas/formal/` (model-based), `veritas/datadriven/` (data-driven), `veritas/runtime/` (runtime) |
| IV-A.1, "Sensor-Suite Selection with TRADES-X" | published demonstration | [`case-studies/A1-sensor-suite-selection/`](case-studies/A1-sensor-suite-selection/README.md) -> [`trades-x/case-studies/sensor-suite/`](trades-x/case-studies/sensor-suite/README.md) |
| IV-A.2, "Risk-Sensitive Path Planning with PERFECT" | published demonstration | [`case-studies/A2-risk-sensitive-planning/`](case-studies/A2-risk-sensitive-planning/README.md) |
| IV-A.3, "Behavior Tree Task Specifications with VERITAS" | published demonstration | [`case-studies/A3-behavior-tree-verification/`](case-studies/A3-behavior-tree-verification/README.md) -> `veritas/formal/bt2automata/`, `veritas/runtime/tbt-monitor/` |
| IV-B.1, "A Contested-Terrain Test Range in Isaac Sim" | released demonstration, the shared environment for the other two | [`case-studies/B1-contested-terrain-range/`](case-studies/B1-contested-terrain-range/README.md) -> `isaacsim/` |
| IV-B.2, "Robust Perception via Conformal Prediction" | released demonstration | [`case-studies/B2-conformal-perception/`](case-studies/B2-conformal-perception/README.md) |
| IV-B.3, "Assured Multi-Robot Coordination" | released demonstration | [`case-studies/B3-assured-multi-robot/`](case-studies/B3-assured-multi-robot/README.md) |

## Getting started

| component | needs | command |
|---|---|---|
| PERFECT | Python 3.12, a uv virtual environment inside `perfect/` (a ROS 2 environment on the path only for the examples that drive ROS; `dummy` does not) | `cd perfect && uv venv --python 3.12 && uv pip install -e .` — then Redis (`redis-server --port 6390 --save '' --appendonly no --dir /tmp/perfect-redis`), the queue worker (`rq worker perfect-tasks --url redis://127.0.0.1:6390`), the runner (`python -m perfect.experiment.runner`) and the server (`python -m flask --app perfect.app run --port 5001`), each in its own terminal — see [`perfect/README.md`](perfect/README.md) for the full bring-up and the example list |
| the whole PERFECT stack in one command | the same virtual environment, plus `redis-server` on the path | `bash perfect/devtools/smoke_dummy.sh` — brings the stack up on its own ports, runs two `dummy` trials and tears it down |
| TRADES-X (Python) | Python >= 3.11, uv | `cd trades-x && uv venv && uv sync && uv run pytest -q` |
| TRADES-X (Julia MBO) | Julia 1.12 | `cd trades-x/mbo && julia --project=. -e 'using Pkg; Pkg.instantiate()'` |
| the data-driven campaign, against a running PERFECT stack | the PERFECT stack above, with `PERFECT_PROJECT_ROOT` set to `perfect/examples/sensor-suite-sim` | `cd trades-x/case-studies/sensor-suite && uv run python run_ddo_campaign.py --submit --url http://127.0.0.1:5001` then `--collect` |
| the Isaac Sim range campaign, against a running PERFECT stack | the PERFECT stack above with `PERFECT_PROJECT_ROOT` set to `perfect/examples/isaacsim-range`; Isaac Sim 6.0 and a GPU | `cd isaacsim/tools && uv run python range_campaign.py --submit --project-root ../../perfect/examples/isaacsim-range`, then `--collect` and `--plot` |
| VERITAS | Python 3.10, uv | `cd veritas && uv venv --python 3.10 && uv sync` |
| the case studies with their own uv project (A2, B2, B3) | uv | `cd case-studies/<directory> && uv sync && uv run pytest -q && uv run python run_case_study.py` |
| the case studies that call into a tool directory (A1, A3) | the tool directory's own environment (`trades-x/` or `veritas/`) | `./case-studies/<directory>/run.sh` |
| `isaacsim/tools/` | uv | `cd isaacsim/tools && uv sync` (see [`isaacsim/README.md`](isaacsim/README.md) for the fetch and build steps) |
| `seil-r2/`, in its container | Docker | `cd seil-r2 && docker build -f docker/Dockerfile.base -t iddmbse-seil-r2-base . && docker build -f docker/Dockerfile.ros2 -t iddmbse-seil-r2-ros2 .` — the second image comes with the workspace built; `python3 docker/container.py start ros2` does the same through Docker Compose |
| ROS 2, for PERFECT's ROS-backed examples and the VERITAS runtime observer | `rclpy` on the interpreter's path; the VERITAS observer was run live on ROS 2 Jazzy ([`veritas/README.md`](veritas/README.md)); `seil-r2/` pins ROS 2 Humble | source the distribution's `setup.bash` before running those pieces |
| Isaac Sim, for `isaacsim/` and `seil-r2/` | a local install with a GPU; `seil-r2/` pins Isaac Sim 4.1.0 | see [`isaacsim/README.md`](isaacsim/README.md) and [`seil-r2/README.md`](seil-r2/README.md) |
| optional: UPPAAL, for checking the models VERITAS's model-based module writes | download separately, register an academic key; point `UPPAAL_HOME` at the install | <https://uppaal.org/downloads/>, <https://uppaal.veriaal.dk/> |
| optional: Gurobi, for `veritas/synthesis/ltbt/` | a full academic license (the pip package's size-limited license is too small for these models) | `cd veritas && uv sync --extra milp` |
| optional: MATLAB + Magic Systems of Systems Architect 2022x or later, for `sysml/workbench/` | commercial licenses | see [`sysml/README.md`](sysml/README.md) |

If a ROS 2 environment is sourced in the shell, its `site-packages` lands on
`PYTHONPATH` and pytest tries to auto-load ROS's own plugins into a Python environment
that does not have them; run tests as `env -u PYTHONPATH uv run pytest`
([`trades-x/README.md`](trades-x/README.md), [`veritas/README.md`](veritas/README.md) say
why).

To run a case study end to end, see [`case-studies/README.md`](case-studies/README.md);
for example `./case-studies/A1-sensor-suite-selection/run.sh`.

## What ran here

Every number below is recorded, with the command that printed it, in the README of the
directory it names or of the one that directory points into (2026-09-22).

- **`perfect/`** — the `dummy` example ran end to end on a private Redis/Flask/runner stack:
  one trial from enqueue to `TrialState.SUCCESSFUL|SHUT_DOWN` in 19.3 s, and
  `devtools/smoke_dummy.sh`, which brings the whole stack up, runs two trials — one through
  `experiments run`, one through `POST /api/v1/run` with the payload the MATLAB bridge sends
  — and tears it down, printed `PASS` in 46.3 s. Four more examples ran as whole campaigns:
  `sensor-suite-sim` (180 trials in 4 min 35 s on one runner), `isaacsim-range` (8 trials,
  each a headless Isaac Sim process, 411 s), `rarrt-planning` (300 trials in 7 min 44 s) and
  `conformal-calibration` (270 trials in 6 min 22 s). `/api/v1` carries four library and environment POST
  routes beside the experiment ones, which is what lets a design-space tool build a whole
  campaign over HTTP without touching the CLI.
- **`trades-x/`** — 57 tests pass. The sensor-suite study enumerates the whole 8191-design
  space and finds 120 non-dominated designs (the cardinality-6 cap gives 4095 and 96, and
  every one of those 96 is still non-dominated in the full space); the greedy submodular
  search reaches its set in 1114 coverage-oracle calls against 8191 full evaluations. The
  data-driven stage then ran ten of those designs across eighteen scenarios as 180 PERFECT
  trials, all `SUCCESSFUL`, and ranked them by MAVF from what the trials reported: the
  single-camera design that the catalogue attributes alone rank first comes last once it has
  been run, reaching the goal in 44% of its draws.
- **`veritas/`** — 62 tests pass and 2 skip; with UPPAAL on the machine the suite is 63 and
  1. UPPAAL 5.0.0 returned 12 verdicts on the battery state machine translated from the SysML
  model (the state-of-charge invariant satisfied, the 180 s completion bound not satisfied)
  and 2 on the behavior-tree network (both `Success` and `Failure` reachable). The
  data-driven module reported failure rates with exact and Wilson intervals over both PERFECT
  campaigns above — per design for the sensor suite, per design point for the range — and the
  runtime observer replayed its three range obligations over all eight recorded trajectories:
  roll broken on two of them, progress on one, pitch on none. The observer also ran live on a
  ROS 2 graph and logged the violation on the sample where the state of charge crossed its
  bound.
- **`sysml/`** — the shipped `.mdzip` matches the checksum of the lab's drop, and its md5 is
  unchanged after translation. Read out of it: 69 blocks, 3 constraint blocks, 23
  requirements and 51 diagrams. All 23 requirements are carried into the UPPAAL model VERITAS
  writes out of it, two of them as queries, and the MATLAB bridge scripts take the PERFECT
  server URL and the workspace path from the environment.
- **`isaacsim/`** — 49 tests pass in `isaacsim/tools`. The range ran an eight-point
  design-of-experiments campaign through PERFECT: obstacle densities 0.1, 0.4 and 0.8 crossed
  with 99th-percentile slope targets of 15° and 25°, plus the shipped baseline point and one
  at the terrain's authored relief, 30 simulated seconds each. Every trial finished; the
  campaign left `results/campaign.csv`, two figure pairs and eight pose trajectories. The
  base scene loads headless in Isaac Sim 6.0.1 with 22 978 prims, 4 607 meshes, 0 unresolved
  references and the Carter articulation found with 7 degrees of freedom; the heightmap round
  trip reproduces the terrain mesh to a maximum point error of 1.52e-5.
- **`seil-r2/`** — both container images build, about 3 GB each, and `colcon build` inside
  them prints `Summary: 6 packages finished [4.77s]`. `ros2 pkg list` in the container lists
  all six packages, and `ros2 launch -s` parses every launch file and prints its arguments.
- **`plugins/`** — the ament package carries the panel header and source,
  `plugins_description.xml`, the `switch.xml` behavior tree with the `ControllerSelector` and
  `PlannerSelector` nodes the panel drives, and `params/test_params.yaml` with the controller
  and planner plugin lists it reads.
- **`case-studies/A1-sensor-suite-selection/`** — `./run.sh` prints `GATE G2: pass`: the
  recorded 4095-design evaluation table reproduces to a maximum absolute difference of
  4.7e-10, gives 96 Pareto designs with the standard and MATLAB-compatible filters agreeing
  exactly, and the full 8191-design enumeration gives 120.
- **`case-studies/A2-risk-sensitive-planning/`** — 45 tests pass; the standalone campaign is
  3 environments x 4 noise levels x 5 policies x 50 runs = 3000 planner runs, which took 109 s
  across 16 worker processes and reproduces byte-identically run to run except for plan time.
  Through PERFECT, the five policies are one component's implementations and the campaign is
  5 policies x 60 environments (3 rock fields x 4 noise levels x 5 seeds) = 300 trials, all
  `SUCCESSFUL` in 7 min 44 s on one runner, with the cell table and the three figures redrawn
  from PERFECT's trial data and a VERITAS failure-rate report over its database.
- **`case-studies/A3-behavior-tree-verification/`** — `./run.sh` composes the behavior tree
  into a network of three timed-automata templates, md5
  `96b2e35c435ce771191351242e29cb77`, and `./run.sh --verify` hands it to UPPAAL, which
  returns both queries satisfied in 0.28 s.
- **`case-studies/B1-contested-terrain-range/`** — the range and its campaign, above.
- **`case-studies/B2-conformal-perception/`** — 30 tests pass; 90 calibration episodes give
  2039 detection rows, held-out coverage is 0.9037 at alpha = 0.10, and in the closed loop
  the conformal margin takes collisions from 168 to 16 of 200 episodes. Through PERFECT, the
  calibration data comes from 3 detector configurations x 90 environments = 270 trials, all
  `SUCCESSFUL` in 6 min 22 s, 24 704 detection rows collected; calibrated on 5399 nominal
  detections, the held-out coverage is 0.9156 at alpha = 0.10, and the report tables carry a
  coverage column per detector configuration.
- **`case-studies/B3-assured-multi-robot/`** — the joint MILP is 1841 variables of which 1043
  binary, 2390 constraints and 7988 nonzeros; HiGHS reaches `Optimal` at relative gap 0.0 in
  about three and a half minutes, with an identical solution across three runs, and the STL
  robustness code agrees with an independent RTAMT computation to 1e-6.

## Provenance and license

MIT ([`LICENSE`](LICENSE)). PERFECT is recovered from the lab's GitLab branch, as
[`perfect/README.md`](perfect/README.md) states. VERITAS's `formal/`, `runtime/` and
`synthesis/` code is vendored from a coauthor's two repositories at pinned commits, per
[`veritas/ATTRIBUTION.md`](veritas/ATTRIBUTION.md); neither upstream repository carries a
license file; the upstream author is a coauthor of the paper, and the vendored copies carry
his attribution and the pinned commit hashes. Components built
for this release are labeled as such in their own READMEs. The SysML model files and
their lineage are recorded in [`sysml/models/LINEAGE.md`](sysml/models/LINEAGE.md).

## Citing

```bibtex
@inproceedings{baras2026iddmbse,
  author    = {Baras, John S. and Damera, Sai Sandeep and Matheu, Ryan and Enwerem, Clinton and Kumar, Praveen M.S.},
  title     = {IDDMBSE: Integrating Data-Driven and Model-Based Systems Engineering for Trusted Autonomous Cyber-Physical Systems},
  booktitle = {IEEE International Symposium on Systems Engineering (ISSE)},
  year      = {2026},
  note      = {\url{https://github.com/seil-umd/IDDMBSE}}
}
```

See [`CITATION.cff`](CITATION.cff) for the machine-readable form.
