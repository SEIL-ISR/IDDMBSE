# rarrt-planning

A PERFECT example with no simulator behind it, in which **the planner is the
design variable**. A design is one planning policy, an environment is one rock
field at one noise level with one seed, and a trial plans a path under that
policy and then executes it many times under fresh noise. The campaign this
example serves is
`case-studies/A2-risk-sensitive-planning/run_perfect_campaign.py`.

The point of it is the wiring: a policy that changes the planner's edge cost is
an ordinary PERFECT component implementation, a noise level is an ordinary
environment argument, and the numbers a trial produces come back through
PERFECT's own trial table, so a design-space tool can submit the whole
comparison and read it back without knowing anything about path planning.

The planner itself is not in this directory. It is the `rarrt` package of
`case-studies/A2-risk-sensitive-planning`, and `planner_trial.py` composes its
pieces into one trial. That is deliberate: the case study and the campaign have
to measure the same thing, and `tests/test_planner_trial.py` holds them to it by
comparing this example's row against `rarrt.campaign.run_trial`'s row field by
field.

## What a trial does

A robot crosses a 64 m square field of rocks from one corner to the other.

1. **Plan.** RRT* grows a tree from the start, 1500 iterations, 3 m steps. The
   only thing a policy changes is the functional applied to a segment's cost
   distribution: `rrtstar` uses the segment length, `neutral` the mean of the
   cost, and `cvar0.1` / `cvar0.5` / `cvar0.9` the conditional value at risk at
   that confidence level. Sampling, steering, collision checking, ChooseParent
   and Rewire are shared, so a difference between two policies' paths is a
   difference in the risk functional and nothing else.
2. **Execute.** The planned path is traversed `n_exec` times under fresh noise,
   independent of the common random numbers the planner optimised against. The
   cost of a segment is its length times a multiplier that carries a Gaussian
   traversal noise and a rare, severe hazard whose chance rises as the segment
   passes closer to a rock. Clearance therefore controls the tail and not just
   the mean, which is what gives a risk-averse planner something to buy.

## What a policy is

`components.json` gives every policy one component implementation of the
`planner` component, whose `implementation` is a single `files` update writing
three values into `policy.yaml`:

| policy | risk | alpha | the edge cost |
|---|---|---|---|
| `rrtstar` | `euclidean` | — | the segment length |
| `neutral` | `cvar` | 0.0 | the mean segment cost |
| `cvar0.1` | `cvar` | 0.1 | CVaR at 0.1 |
| `cvar0.5` | `cvar` | 0.5 | CVaR at 0.5 |
| `cvar0.9` | `cvar` | 0.9 | CVaR at 0.9 |

A design holds exactly one of them, so a campaign over the five policies is five
designs.

## How the design and the environment reach the trial

Through PERFECT's own file-editing mechanism, not through a side channel.

PERFECT copies `policy.yaml` and `scenario.yaml` into the trial's working
directory and then applies, in order, the `files` updates of every component
implementation in the design and then those of the environment specification.
`experiment.py` reads the two files afterwards and hands their contents to
`planner_trial.py`; it never looks at the raw design or environment dictionary.

`environment_template.json` is an environment template with four arguments:

| argument | what it picks |
|---|---|
| `$environment` | `easy`, `medium` or `hard`, naming one of the three rock-field coverages in `scenario.yaml` |
| `$sigma` | the traversal-noise scale |
| `$seed` | the rock field, and the offset of the planner's and the executor's seeds |
| `$n_exec` | how many times the planned path is executed under fresh noise |

Everything else a trial needs — the RRT* settings, the cost model's constants,
the budget factor, the three base seeds and the coverage table — sits in
`scenario.yaml` and is the same in every cell of the campaign.

## What a trial reports

`await self._relay_update("metrics", ...)` sends one dictionary, which PERFECT
stores as an `Update` row on the trial and `GET /api/v1/trials/<id>` returns.
Its keys are the seventeen columns of the case study's own campaign table —
`env`, `coverage`, `sigma`, `policy`, `alpha`, `run`, `found`,
`nominal_length`, `min_clearance`, `planner_cost`, `nodes`, `plan_time`,
`realized_mean`, `realized_p95`, `realized_max`, `over_budget`, `hazard_rate` —
plus two arrays:

- `executed`, every realised traversal cost of the trial. The worst case of a
  cell of the grid is the 95th percentile over all executions of all its trials
  pooled, and that cannot be recovered from per-trial percentiles.
- `path`, the planned polyline, which is what the paths figure draws.

`hazard_rate` is relayed a second time on its own, because a tool that scores a
campaign asks for one named number per trial, and `plan_time` is relayed as
`sim_time` because `Trial` has a column of that name.

## The interpreter and the planner package

The planner is numpy and scipy. The Python environment that carries PERFECT does
not have to be: `experiment.py` starts `planner_trial.py` in a child process,
with the interpreter named by `RARRT_PYTHON` if that is set and the running one
otherwise. The child finds the `rarrt` package at `RARRT_PACKAGE`, which
defaults to the case study's directory in this repository.

## Run one trial without a server

```bash
cd perfect/examples/rarrt-planning
PERFECT_PROJECT_ROOT=$PWD RARRT_PYTHON=$(which python3) python experiment.py
```

That builds a one-component design over `cvar0.9` and one environment off the
template in process and runs the full experiment lifecycle with the mock
callbacks. Recorded on 2026-09-22, at noise level 0.5 in the medium rock field,
seed 0, 32 executions:

```
INFO core experiment._init:75 - policy cvar0.9, environment medium, sigma 0.5, seed 0.0
INFO core experiment._run:99 - cvar0.9 medium sigma 0.5 seed 0 found 1 plan 0.87 s
INFO core experiment.mock_relay_update_callback:357 - Experiment 0 update metrics to {'env': 'medium', 'coverage': 0.16, 'sigma': 0.5, 'policy': 'cvar0.9', 'alpha': 0.9, 'run': 0, 'found': 1, 'nominal_length': 87.76488943924684, 'min_clearance': 3.281095354522826, 'planner_cost': 296.3087966977712, 'nodes': 1183, 'plan_time': 0.8692514019785449, 'realized_mean': 101.6624751408362, 'realized_p95': 135.10808395303025, 'realized_max': 216.61758141389436, 'over_budget': 0.09375, 'hazard_rate': 0.375, 'executed': [...], 'path': [...]}
INFO core experiment.run:293 - Shut down RiskAwarePlanningExperiment
```

The trial itself also runs on its own:

```bash
python3 - <<'EOF'
import json, yaml
policy = yaml.safe_load(open("policy.yaml"))
policy.update(policy="cvar0.9", risk="cvar", alpha=0.9)
scenario = yaml.safe_load(open("scenario.yaml"))
scenario.update(environment="hard", sigma=0.5, seed=0, n_exec=400)
json.dump({"policy": policy, "scenario": scenario}, open("job.json", "w"))
EOF
python3 planner_trial.py job.json metrics.json
# cvar0.9 hard sigma 0.5 seed 0 found 1 plan 0.74 s
```

## Run it under a PERFECT stack

The bring-up is the one `perfect/README.md` records for the `dummy` example,
with this directory as `PERFECT_PROJECT_ROOT` and `RARRT_PYTHON` and
`RARRT_PACKAGE` exported to every process that needs them. After `db upgrade`:

```bash
python -m flask --app perfect.app components load_component_implementations components.json
python -m flask --app perfect.app environments create_templates_from_file environment_template.json
python -m flask --app perfect.app designs create cvar0.9 -i --name cvar0.9 --tag rarrt
python -m flask --app perfect.app environments create_from_template 1 \
    environment:=hard sigma:=0.5 seed:=0 n_exec:=400 -n "hard-sigma0.5-seed0" -t rarrt
python -m flask --app perfect.app experiments create rarrt rarrt -t rarrt
python -m flask --app perfect.app experiments run rarrt
```

The same sequence over HTTP is what `tradesx.ddo_api` does, and
`case-studies/A2-risk-sensitive-planning/README.md` records a 300-trial campaign
run that way.

## Tests

The tests need numpy, scipy, pyyaml and pytest, and they import `rarrt` from the
case study:

```bash
cd perfect/examples/rarrt-planning
python3 -m pytest tests -q
```

They check that this example's row is `rarrt.campaign.run_trial`'s row for six
combinations of policy and rock field, that the relayed summaries are the ones
the relayed executions carry, that the relayed path is the one the lengths were
taken from, that plain RRT* costs a path exactly its own length while CVaR 0.9
costs it more, that the counts survive the float substitution PERFECT applies to
template arguments, and that each entry of `components.json` writes the policy
it is named after into `policy.yaml`. Recorded on 2026-09-22:

```
....................                                                     [100%]
20 passed in 0.61s
```

## Files

| file | what it is |
|---|---|
| `experiment.py` | the PERFECT experiment class; reads the two working files, runs the trial, relays the metrics |
| `planner_trial.py` | one trial: plan under the policy, execute the plan under fresh noise, report the row |
| `components.json` | the planner library, one component implementation per policy |
| `policy.yaml` | the policy defaults; the design overwrites them |
| `scenario.yaml` | the scenario defaults and the settings every cell shares; the environment overwrites the first four |
| `environment_template.json` | the environment template with `$environment`, `$sigma`, `$seed`, `$n_exec` |
| `tests/` | the trial against the case study's own campaign function, and the two working files against the design and the environment |
