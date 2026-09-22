# TRADES-X

TRadeoff Analysis and DEsign Space EXploration, the trade-off stage of the
IDDMBSE tool chain. It narrows a large design space in two steps:

1. **Model-based optimization (MBO).** Every candidate design is scored by
   first-principles oracles — the parts of the design space that admit a good
   analytical model — and the non-dominated designs are kept. Local metrics for
   the sensor-suite study: effective coverage (maximised), cost, RAM and power
   (minimised).
2. **Data-driven optimization (DDO).** The survivors go into a campaign of
   simulated runs executed by PERFECT, and the metrics come out of the runs:
   how often the design reached its goal, how long it took, how far it
   detoured, how early it saw what was in its way. `tradesx/ddo_api.py` submits
   the campaign to a running PERFECT server over its JSON API and reads the
   trial table back; `tradesx/bag_metrics.py` computes path length, time to
   completion and cumulative elevation gradient from a trajectory.

A Multi-Attribute Value Function (MAVF) then normalises every metric onto
[0, 1] and combines them into a single weighted score, which gives the ranking
and the recommended design.

## Layout

| path | what it is |
|---|---|
| `tradesx/pareto.py` | vectorised non-dominated filter, plus the MATLAB-compatible variant |
| `tradesx/mavf.py` | SAVF normalisation and weighted-sum MAVF ranking |
| `tradesx/ddo.py` | emits (or runs) the PERFECT CLI sequence for a DDO campaign |
| `tradesx/ddo_api.py` | submits a DDO campaign to a live PERFECT server over `/api/v1`, collects the trials and ranks the designs |
| `tradesx/bag_metrics.py` | path length, time to completion, cumulative elevation gradient from a trajectory |
| `tradesx/sensitivity.py` | the four local oracles in Python (numpy batch, JAX derivatives) and the requirement-sensitivity ranking |
| `tradesx/requirements.py` | loads the model-based / data-driven requirement split |
| `mbo/` | the Julia MBO package: sensor oracles, enumeration, sensitivity, plots |
| `mbo-matlab-alt/` | MATLAB alternates of the same MBO, kept as reference |
| `pyjulia-example/` | minimal PyJulia call-through stub |
| `case-studies/sensor-suite/` | the ISSE 2024 sensor-suite study and its recorded data |
| `tests/` | pytest suite |

## Install

Python side (uv project, Python >= 3.11):

```
cd trades-x
uv venv
uv sync
uv run pytest -q
```

57 tests pass as of 2026-09-22. The JAX derivatives are an optional extra; add
them with `uv sync --extra ad`. Without it `tests/test_sensitivity.py` skips and
the rest still runs.

If a ROS 2 environment is sourced in your shell, its site-packages lands on
`PYTHONPATH` and pytest tries to auto-load the ament and `launch_testing`
plugins from it. `pyproject.toml` disables those plugins by name so the suite
runs either way.

Julia side (the MBO package has its own project environment):

```
cd trades-x/mbo
julia --project=. -e 'using Pkg; Pkg.instantiate()'
```

`Manifest.toml` was re-resolved on Julia 1.12.7 on 2026-09-22; the environment
precompiles clean and `src/mbo.jl`, `src/sens_fd.jl` and `src/demo_sens.jl` all
run headless. The `SubmodularGreedy.jl` dependency was
dropped, together with `GLMakie`, `VegaLite` and `BenchmarkTools`; see
`mbo/README.md`.

## Run the case study

```
cd trades-x
uv run python case-studies/sensor-suite/run_case_study.py
```

That reads the recorded design evaluations, reruns the Pareto filter, checks
the result against the recorded MATLAB output, ranks the survivors by MAVF and
writes the figures. See `case-studies/sensor-suite/README.md`.

To regenerate the design evaluations from the oracles instead of reading the
recorded CSV:

```
cd trades-x/mbo
julia --startup-file=no --project=. run_mbo.jl 6 mbo_design_evals.csv
```

To enumerate the whole design space rather than the cardinality-6 slice, and
reproduce the counts in Python:

```
cd trades-x/mbo
julia --startup-file=no --project=. run_mbo.jl 13 \
  ../case-studies/sensor-suite/data/full_enumeration_4met.csv - \
  ../case-studies/sensor-suite/data/pareto_full.csv
cd ..
uv run python case-studies/sensor-suite/run_full_enumeration.py
```

8191 designs, 120 non-dominated. The case-study README has the counts table
beside the recorded 4095-design run.

## Run a DDO campaign

`tradesx/ddo.py` turns a list of surviving design ids and a start/goal grid
into the PERFECT CLI sequence:

```
uv run python tradesx/ddo.py --dry-run --designs 4234,785,549 --grid 3x3
```

Every command it emits maps to a real PERFECT CLI command:

| emitted | where it is defined |
|---|---|
| `db init` / `db migrate` / `db upgrade` | Flask-Migrate, registered in `perfect/perfect/app/__init__.py:47` |
| `components load_components` | `perfect/perfect/app/routes/components.py:144` |
| `components load_component_implementations <file>` | `perfect/perfect/app/routes/components.py:138` |
| `designs create <component ids> --name --tag` | `perfect/perfect/app/routes/designs.py:72` |
| `environments create_templates_from_file <file>` | `perfect/perfect/app/routes/environments.py:41` |
| `environments create_from_template <id> k:=v ... --name --tag` | `perfect/perfect/app/routes/environments.py:65` |
| `experiments create <design tag> <env tag> --tag` | `perfect/perfect/app/routes/experiments.py:86` |
| `experiments run <tag>` | `perfect/perfect/app/routes/experiments.py:113` |

`--execute` runs them instead of printing, against a PERFECT stack that is
already up: Redis, an RQ worker, the experiment runner and the Flask server.

The default environment template is PERFECT's `Navigate to Goal Pose`
(`perfect/perfect/common/templates/nav2_operation_plans/navigate_to_goal_pose.json`),
which parametrises `$x_goal` and `$y_goal`. `--start-grid` also emits
`x_start:=` / `y_start:=`, for a template that declares those arguments.

### Over the API, with the results read back

`tradesx/ddo_api.py` does the same thing over PERFECT's JSON API and then
collects what the campaign measured:

| step | route |
|---|---|
| load the sensor library | `POST /api/v1/component_implementations` |
| create the designs | `POST /api/v1/designs` |
| create the scenario template and the scenarios | `POST /api/v1/environment_templates`, `POST /api/v1/environments` |
| create one experiment per design and scenario, each with a trial enqueued | `POST /api/v1/experiments` |
| watch it run | `GET /api/v1/experiments` |
| read the results | `GET /api/v1/experiments/<id>`, `GET /api/v1/trials/<id>` |

Every create route is idempotent on the name, so re-running a submission
against a database that already holds the campaign returns the ids that are
already there. `POST /api/v1/experiments` has no name to be idempotent on, so
`create_experiments` reads the experiments already carrying the tag and creates
only the design-and-scenario pairs that are missing. The HTTP client is
`urllib.request` from the standard library.

An experiment reports what it measured with
`await self._relay_update("metrics", {...})`, which PERFECT stores as an
`Update` row on the trial; `ddo_api.collect` pulls those rows into one row per
trial, `metric_table` folds them into a designs x scenarios x metrics array and
`rank_designs` hands that to the MAVF together with the model-based attributes.
The weights come from the requirement partition in
`case-studies/sensor-suite/requirements.yaml`: the model-based requirements
carry the attributes known from the catalogue before anything runs (price,
power, RAM) and the data-driven ones carry the measured attributes, each class
weighted by how many requirements it holds.

`case-studies/sensor-suite/run_ddo_campaign.py` is the study that uses it, and
`case-studies/sensor-suite/README.md` records a 180-trial campaign against
the `perfect/examples/sensor-suite-sim` example.

## Built for this release

Four things the IDDMBSE paper describes had no code in the repository. They were
written on 2026-09-22 and are marked as such wherever they appear:

- **`mbo/src/greedy_submodular.jl`** — the greedy submodular search. The
  environment carried a `SubmodularGreedy.jl` dependency that no source file
  called and that does not load on Julia 1.12. `mbo_smo_results` was a copy of
  the exhaustive `mbo_results`. Both are now real.
- **The full enumeration.** The recorded run capped designs at 6 sensors, 4095
  of them. `run_mbo.jl 13` enumerates all 8191 and writes
  `case-studies/sensor-suite/data/full_enumeration_4met.csv` and
  `pareto_full.csv`.
- **`tradesx/sensitivity.py`** — the Python/JAX sensitivity path. Only the Julia
  ForwardDiff one existed. The two agree to better than 1e-6 on all four
  coverage models.
- **`case-studies/sensor-suite/requirements.yaml`** and
  **`tradesx/requirements.py`** — the model-based / data-driven requirement
  split, over the 23 SysML requirements of the AGR_stack model. The SysML model
  carries no such split.
- **`tradesx/ddo_api.py`** and
  **`case-studies/sensor-suite/run_ddo_campaign.py`** — the data-driven stage
  against a live PERFECT server, with the PERFECT example it runs on at
  `perfect/examples/sensor-suite-sim`.

## Provenance

- `mbo/`, `mbo-matlab-alt/` and `pyjulia-example/` were moved out of
  `perfect/perfect_MBO/` and `perfect/pyjulia_example/` on 2026-09-22.
  `run_mbo.jl` and this README are new, and `mbo/README.md` was rewritten to
  describe the enumeration, the oracles and the greedy submodular search that
  the code actually implements. The Julia sources came over unchanged
  and were then edited, the same day, to run on Julia 1.12 without a display:
  `mbo.jl` (headless GR, the greedy call, a stray backtick literal removed, two
  forward references fixed), `utilities.jl` (a forward reference fixed),
  `plotting.jl` (GLMakie to CairoMakie), `sens_fd.jl` (a broken
  `FiniteDifferences.forward_fdm` call replaced by real gradients) and
  `demo_sens.jl` (its results printed rather than discarded).
- `tradesx/pareto.py` and `tradesx/mavf.py` are ports of `prtp` and `MAVF` from
  the MATLAB workbench now at `sysml/workbench/` (`dse/pareto.m`,
  `rosbag/MBO_rosbag_evals.m`).
- `tradesx/bag_metrics.py` is a port of the metric computations in
  `sysml/workbench/rosbag/*.m`.
- `tradesx/ddo.py` is a port of `examples/SEILR1/robustness.bash`, updated from
  the old `simulations` command group to today's `experiments`. That bash script
  was updated to the current command names on 2026-09-22.
- `tradesx/ddo_api.py` is new on 2026-09-22 and talks to the `/api/v1`
  blueprint in `perfect/perfect/app/routes/api.py`.

## Citation

The sensor-suite case study:

> S. Damera, P. Kumar, J. S. Baras. Integrated Data-Driven and Model-Based
> Trade-off Analysis of Sensor Suite System for Autonomous Ground Vehicle
> Navigation. INCOSE International Symposium / ISSE, 2024.

The methodology:

> J. S. Baras, S. Damera, R. Matheu, M. Enwerem, P. Kumar. IDDMBSE:
> Integrating Data-Driven and Model-Based Systems Engineering for Trusted
> Autonomous Cyber-Physical Systems. ISSE, 2026.
