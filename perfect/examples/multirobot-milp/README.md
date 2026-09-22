# multirobot-milp

A PERFECT example with no simulator behind it, in which **the coordination
configuration of a three-robot team is the design variable**. A design is one
station allocation (which robot visits which pair of inspection stations) with
one required STL robustness margin, an environment is one tracking-disturbance
level with one seed, and a trial synthesises the team's joint plan as a big-M
MILP, executes it once under that disturbance, scores every robot's executed
trace with the quantitative STL robustness, and writes the verdicts back into
the fleet model. The campaign this example serves is
`case-studies/B3-assured-multi-robot/run_perfect_campaign.py`.

The synthesis and the scoring are not in this directory. They are the
`assured_ma` package of `case-studies/B3-assured-multi-robot`, and
`coordination_trial.py` composes its pieces into one trial in the order of that
case study's chain. `tests/test_coordination_trial.py` holds every relayed
number to the number the package's own functions give on the same input.

## What a trial does

The map, the missions, the dynamics and the noise model are the case study's
`model/fleet_requirements.yaml`: an 8 m x 6 m floor, a wall with two doorways,
a pillar rotated 45 degrees, three robots with two stations each and a time
window per station, 0.5 m of separation between any two robots at all times.

1. **Parse.** The fleet requirement becomes one reach-avoid STL formula per
   robot, `phi_i = F_[a1,b1](station 1) & F_[a2,b2](station 2) & G_[0,16](no
   obstacle & separated from the others)`. The allocation decides whose
   stations robot `i` gets.
2. **Synthesise.** The three formulas and the double-integrator dynamics
   (N = 16 steps of 0.9 s) become one MILP: 1841 variables, 1043 of them
   binary, 2390 constraints. Every robot's formula is required to hold in the
   plan with at least the design's margin, and the objective is the total
   control effort. HiGHS solves it through `scipy.optimize.milp`. The search
   stops after 8000 branch-and-bound nodes, or earlier once the relative gap is
   below 0.05, with a 240 s wall-clock cap above both. A node limit rather than
   a time limit is what makes a design's plan the same in every one of its
   trials, however many other trials share the machine.
3. **Execute.** The plan is tracked once through the case study's
   tracking-error process, `e_{k+1} = 0.8 e_k + w_k`, `w_k ~ N(0, sigma^2)`
   clipped at 3 sigma, per robot and axis, drawn from the environment's seed.
4. **Score.** Each robot's executed trace gets its robustness `rho_i`
   (positive if and only if the formula holds) and the conjunct and step that
   set it. The trial's verdict number is `min_rho`, the smallest of the three.
5. **Write back.** `rho_i` is written into the trial's own copy of the case
   study's `model/agr_fleet.yaml` as block `AGR_i`'s goal-satisfaction value,
   with the verdict and the binding conjunct beside it, and read back from that
   file into the trial's result.

## What a design is

`components.json` holds 24 implementations of one component, `coordinator`:
every allocation of the three station pairs to the three robots, at every
margin of 0.15, 0.35, 0.45 and 0.5 m. Each is a single `files` update writing
four values into `config.yaml`. The allocation is written as a mapping from
robot to station pair, because PERFECT's file update appends to a list instead
of replacing it:

| station pair | stations, in visiting order |
|---|---|
| 0 | `ST_N1` in steps 6-10, then `ST_N2` in steps 13-16 |
| 1 | `ST_C1` in steps 7-10, then `ST_S2` in steps 14-16 |
| 2 | `ST_S1` in steps 7-10, then `ST_C2` in steps 14-16 |

A design is named after its allocation and its margin: `alloc102-m0.35` gives
`AGR_1` pair 1, `AGR_2` pair 0 and `AGR_3` pair 2, at 0.35 m. `alloc012` is the
allocation the model file itself makes.

## How the design and the environment reach the trial

Through PERFECT's own file-editing mechanism. PERFECT copies the three files in
`_files` into the trial's working directory and then applies the design's and
the environment's `files` updates:

| working file | written by | holds |
|---|---|---|
| `config.yaml` | the design | the allocation, the required margin, and the stopping rule every design shares (node limit, gap, wall-clock cap) |
| `execution.yaml` | the environment | the disturbance level `sigma` and the `seed`, and the path follower every environment shares (pole 0.8, clip at 3 sigma) |
| `agr_fleet.yaml` | nobody | the case study's fleet model, copied so that the trial's write-back lands in the copy |

`environment_template.json` is an environment template with two arguments,
`$sigma` (metres per step, per axis; before the clip, the steady-state tracking
error has standard deviation `sigma / sqrt(1 - 0.8^2) = sigma / 0.6`) and
`$seed`. PERFECT turns a numeric template argument into a float, so the trial
casts the seed back to an integer.

## What a trial reports

`await self._relay_update("metrics", ...)` sends one dictionary, which PERFECT
stores as an `Update` row on the trial and `GET /api/v1/trials/<id>` returns:

- the design and environment it ran under: `allocation`, `stations`,
  `required_margin`, `sigma`, `seed`;
- the solve: `n_var`, `n_bin`, `n_con`, `mip_status`, `mip_message`, `stop`
  (`optimal`, `node limit`, `time limit` or `infeasible`), `nodes`, `mip_gap`,
  `dual_bound`, `solve_wall`, `feasible`, `effort` (1-norm of the
  accelerations) and `dense_margin` (the plan's smallest obstacle clearance
  along the straight segments between waypoints);
- the verdicts: `planned_rho` and `executed_rho` per robot, `min_rho`,
  `violations` (robots with `rho < 0`), `verdicts`, `binding` (the conjunct and
  step each robot's value came from) and `goal_satisfaction` (read back from
  the written model);
- the trajectories: `plan` and `executed`, three robots x 17 steps x 2.

A design whose margin the map cannot afford has no plan; its trials report
`feasible` false, `stop` `infeasible`, and nothing under the verdict keys.
`min_rho` is relayed a second time on its own, because a tool that scores a
campaign asks for one named number per trial, and `solve_wall` is relayed as
`sim_time` because `Trial` has a column of that name.

## The interpreter and the coordination package

Synthesis and scoring need numpy and scipy, and the Python environment that
carries PERFECT does not have to have them: `experiment.py` starts
`coordination_trial.py` in a child process. By default the child runs as
`uv run --project <package> python`, in the case study's own uv environment;
`MULTIROBOT_PYTHON` replaces that command (an interpreter path, or any command
line). The child finds `assured_ma` at `MULTIROBOT_PACKAGE`, which defaults to
`case-studies/B3-assured-multi-robot` in this repository. `PYTHONPATH` and
`VIRTUAL_ENV` are not passed to the child, so neither a sourced ROS
environment nor the activated PERFECT environment can stand in front of the
case study's own. A trial holds about one core: single solves of this MILP
measured here used 1.02 to 1.06 CPU seconds per wall-clock second.

## Several runners

PERFECT runs one trial per runner at a time, and the RQ worker that dispatches
a trial checks a runner's availability and then launches on it over two
separate connections (`perfect/app/tasks.py`). Two workers that share a runner
list can both find the same runner free; the second launch is then answered
"Already running an experiment" and that trial never runs. Pairing each runner
with its own worker avoids that: start runner `k` with `RUNNER_PORT=800k` and
its worker with `RUNNER_URIS=ws://localhost:800k`, as many pairs as there are
runners.

`config.py` gives SQLite a 60 s busy timeout (`SQLALCHEMY_ENGINE_OPTIONS`) in
place of the default 5 s, because every worker writes its trials' updates into
the one database file while the server may still be committing the campaign's
experiments.

## Run one trial without a server

```bash
cd perfect/examples/multirobot-milp
PERFECT_PROJECT_ROOT=$PWD python experiment.py
```

with the PERFECT environment active. That builds a one-component design over
`alloc102-m0.35` and one environment off the template (`sigma` 0.09, seed 0) in
process and runs the full experiment lifecycle with the mock callbacks. Recorded
on 2026-09-22 (the relayed dictionary shortened here):

```
INFO core experiment._init:96 - allocation {'AGR_1': 1, 'AGR_2': 0, 'AGR_3': 2}, margin 0.35, sigma 0.09, seed 0.0
INFO core experiment._run:123 - allocation [1, 0, 2] margin 0.35 sigma 0.09 seed 0 stop node limit nodes 8000 solve 55.4 s min rho 0.0545
INFO core experiment.mock_relay_update_callback:357 - Experiment 0 update metrics to {'robots': ['AGR_1', 'AGR_2', 'AGR_3'], 'allocation': [1, 0, 2], 'stations': [['ST_C1', 'ST_S2'], ['ST_N1', 'ST_N2'], ['ST_S1', 'ST_C2']], ..., 'n_var': 1841, 'n_bin': 1043, 'n_con': 2390, ..., 'stop': 'node limit', 'mip_gap': 0.48154186834321117, ..., 'effort': 5.207753608988183, 'dense_margin': 0.17125000000000012, 'planned_rho': [0.34999999999999254, 0.3499999999999934, 0.34999999999999254], ..., 'executed_rho': [0.11753090625051854, 0.054478993727993696, 0.16800181855536], 'min_rho': 0.054478993727993696, 'violations': 0, ..., 'binding': ['OBS_WALL_MID@k=7', 'OBS_WALL_NORTH@k=8', 'OBS_WALL_SOUTH@k=5'], 'goal_satisfaction': [0.117531, 0.054479, 0.168002], 'plan': [...], 'executed': [...]}
INFO core experiment.mock_relay_update_callback:357 - Experiment 0 update min_rho to 0.054478993727993696
INFO core experiment.mock_relay_update_callback:357 - Experiment 0 update sim_time to 55.35361741500674
INFO core experiment.run:293 - Shut down MultiRobotCoordinationExperiment
```

56.5 s wall for the whole run, 55.4 s of it the solve. An earlier run of the same
trial on a quieter machine took 52.9 s and relayed the same effort, the same
three robustness values and the same goal-satisfaction values to the last digit:
the node limit fixes the incumbent.

## Run it under a PERFECT stack

The bring-up is the one `perfect/README.md` records for the `dummy` example,
with this directory as `PERFECT_PROJECT_ROOT`, `MULTIROBOT_PACKAGE` exported if
the case study lives elsewhere, and the runner/worker pairs above. After
`db upgrade`:

```bash
python -m flask --app perfect.app components load_component_implementations components.json
python -m flask --app perfect.app environments create_templates_from_file environment_template.json
python -m flask --app perfect.app designs create alloc102-m0.35 -i --name alloc102-m0.35 --tag multirobot
python -m flask --app perfect.app environments create_from_template 1 \
    sigma:=0.09 seed:=0 -n "sigma0.09-seed0" -t multirobot
python -m flask --app perfect.app experiments create multirobot multirobot -t multirobot
python -m flask --app perfect.app experiments run multirobot
```

Run here on 2026-09-22 against a fresh database, up to `experiments create`: the
library load logs `Committed 24 Components from components.json`, and
`experiments create` prints `Patterns matched 1 designs and 1 environments, so 1
experiments total`.

The same sequence over HTTP is what `tradesx.ddo_api` does, and
`case-studies/B3-assured-multi-robot/README.md` records a 216-trial campaign
run that way: 24 designs x 9 environments on four runner/worker pairs, 38 min
27 s from the first trial's start to the last shutdown, every trial
`TrialState.SUCCESSFUL|SHUT_DOWN`, and each design's nine trials returning the
same plan.

## Tests

The tests need numpy, scipy, pyyaml and pytest and import `assured_ma` from the
case study, so they run in the case study's uv environment:

```bash
cd perfect/examples/multirobot-milp
uv run --project ../../../case-studies/B3-assured-multi-robot pytest tests -q
```

They run the trial on a two-robot fleet small enough to solve in a fraction of a
second and check that the relayed plan, execution, planned and executed
robustness, binding conjuncts, effort and interpolated clearance are the ones the
package's own functions give; that the verdicts land in the trial's copy of the
model and are read back from it; that swapping the allocation swaps the stations
and makes the separation conjunct bind; that a margin the map cannot afford
reports no plan and leaves the model untouched; that the seed survives the float
substitution PERFECT applies to template arguments; and that each of the 24
entries of `components.json` writes the allocation and the margin it is named
after. Recorded on 2026-09-22:

```
.....................................                                    [100%]
37 passed in 1.27s
```

## Files

| file | what it is |
|---|---|
| `experiment.py` | the PERFECT experiment class; reads the working files, runs the trial in a child process, relays the metrics |
| `coordination_trial.py` | one trial: parse, synthesise, execute, score, write back |
| `components.json` | the coordinator library, one implementation per allocation and margin |
| `config.yaml` | the coordination defaults and the stopping rule; the design overwrites the first four values |
| `execution.yaml` | the disturbance defaults and the path follower; the environment overwrites the first two |
| `environment_template.json` | the environment template with `$sigma` and `$seed` |
| `config.py` | PERFECT's project configuration: the SQLite busy timeout |
| `tests/` | the trial against the coordination package's own functions, and the working files against the designs and the environment |
