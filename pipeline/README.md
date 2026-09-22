# pipeline

One command that runs the tool chain end to end: it brings up a private PERFECT stack, runs
the sensor-suite campaign through TRADES-X's data-driven stage, reports failure rates over the
campaign's database with VERITAS, writes VERITAS's two UPPAAL models and checks them with
UPPAAL, replays the range trajectories through VERITAS's STL observer, writes a summary, and
stops every process it started. Built for this release.

```bash
bash pipeline/run.sh            # the default stages
bash pipeline/run.sh --all      # plus the risk-sensitive planner and conformal-calibration campaigns
bash pipeline/run.sh --range    # plus the Isaac Sim range campaign
```

Everything a run writes goes under `pipeline/out/<date>-<time>/`; the recorded results in the
tool directories are read, never written.

## What it needs

- `uv`, `redis-server` and `redis-cli`, `curl`, `ss`, `python3`;
- the tools' own environments: `perfect/.venv` (`cd perfect && uv venv --python 3.12 && uv pip
  install -e .`), `trades-x/.venv` (`uv sync`), `veritas/.venv` (`uv venv --python 3.10 && uv
  sync`); with `--all` also those of `case-studies/A2-risk-sensitive-planning` and
  `case-studies/B2-conformal-perception`; with `--range` that of `isaacsim/tools`, the range's
  fetched content and built terrain ([`isaacsim/README.md`](../isaacsim/README.md)), and Isaac
  Sim 6.0 found through `ISAACSIM_PYTHON`;
- a Python with numpy, scipy and PyYAML for the trials of the three ROS-free examples
  (`PIPELINE_TRIAL_PYTHON`, default `/usr/bin/python3`): each of those examples runs its
  simulation in a child process with this interpreter, because PERFECT's own environment
  carries neither;
- optionally UPPAAL, found through `UPPAAL_HOME` or `verifyta` on the `PATH`
  ([`veritas/README.md`](../veritas/README.md) has where to get it).

The first stage checks all of this and, for anything it does not find, prints the command
that creates it.

## The stages

Each stage is a file `stages/NN-<name>.sh`; they run in number order, each timed, each
writing under `pipeline/out/<run>/<name>/`.

| stage | runs with | what it does | what it leaves in its directory |
|---|---|---|---|
| `preflight` | always | checks the tools and environments above; reports the UPPAAL version and whether Isaac Sim is set | `stage.log` |
| `sensor-suite` | always | a PERFECT stack on a copy of `perfect/examples/sensor-suite-sim`; `trades-x/case-studies/sensor-suite/run_ddo_campaign.py --submit` (10 designs x 18 scenarios = 180 trials over `/api/v1`), then `--collect`: the trial table, the metric table, the MAVF ranking and three figure pairs | `project/` (the example copy and its database `project.db`), `results/`, `stack-logs/` |
| `rarrt-planning` | `--all` | the same on `perfect/examples/rarrt-planning` with `case-studies/A2-risk-sensitive-planning/run_perfect_campaign.py`: 5 planner policies x 60 environments = 300 trials, the per-cell table and three figure pairs | `project/`, `results/`, `stack-logs/` |
| `conformal-calibration` | `--all` | the same on `perfect/examples/conformal-calibration` with `case-studies/B2-conformal-perception/run_perfect_campaign.py`: 3 detector configurations x 90 environments = 270 trials, split conformal calibration on the detections they return, the coverage sweep and two figure pairs | `project/`, `results/`, `stack-logs/` |
| `isaacsim-range` | `--range` | the same on `perfect/examples/isaacsim-range` with `isaacsim/tools/range_campaign.py`: 8 design points, each trial one headless Isaac Sim process under `timeout`, 30 simulated seconds; the trial table, the pose trajectories and two figure pairs. Skips with one line when `ISAACSIM_PYTHON` is not set | `project/`, `runs/` (one directory per trial: the design-point layer, `metrics.json`, `trajectory.csv`, the simulator log), `results/` |
| `veritas-report` | always | `veritas/datadriven/report.py` over the database of every campaign the run made, with that campaign's failure criterion (below) | one directory per campaign: `report.md`, `report.csv`, `report.json`, `failure_rates.svg`/`.pdf` |
| `uppaal` | always | writes the SysML battery state machine (from `sysml/models/AGR_stack-MB-SensorTrade-mk6.mdzip`) and the example behavior tree as UPPAAL models, then `veritas/formal/verify.py` checks both with `verifyta`; without UPPAAL it writes the models and says the check was skipped | `battery_sm.xml`, `BT_converted.xml`, their `.q` query files, `verification_report.md`/`.json` |
| `stl-replay` | always | `veritas/runtime/stl-observer/replay_observer.py` with `specs/range_safety.yaml` over the eight trajectories in `isaacsim/results/trajectories/`, and over the run's own when `--range` ran | `shipped/` and `this-run/`: `verdicts.md`, `verdicts.csv`, `robustness.svg`/`.pdf` |
| summary | always | `SUMMARY.md`: each stage's status, wall seconds, headline numbers and output directory | `SUMMARY.md` in the run directory |
| teardown | always | stops every process the run started and every process below them (a trial's simulator included), then checks that none is left and nothing listens on the three ports; also after a failure or Ctrl-C | `stack-history.txt` in the run directory lists every process started |

The failure criteria the report uses, one per campaign: sensor suite, a trial fails when fewer
than all of its twelve noise draws reached the goal (`success_rate` below 1.0, grouped by
design); risk-sensitive planner, when any execution went over the traversal budget
(`over_budget` above 0, grouped by design, `hazard_rate` summarised); conformal calibration,
when the episode collided (`collisions` above 0, grouped by design, `coverage_margin`
summarised); range, when the AGR covered less than 5 m in its 30 s (`distance_m` below 5.0).

## What it printed here

Three runs on 2026-09-22, each on Redis 6390, Flask 5001 and the runner on 8003, UPPAAL
5.0.0 on the machine. Wall seconds per stage:

| stage | `run.sh` | `run.sh --range` | `run.sh --all` |
|---|---|---|---|
| preflight | 0.3 | 0.3 | 0.3 |
| sensor-suite | 255.4 | 250.6 | 250.2 |
| rarrt-planning | - | - | 468.1 |
| conformal-calibration | - | - | 481.9 |
| isaacsim-range | - | 461.5 | - |
| veritas-report | 0.7 | 1.4 | 2.2 |
| uppaal | 0.7 | 0.5 | 0.5 |
| stl-replay | 1.2 | 2.0 | 1.0 |
| teardown | 0.1 | 0.1 | 0.1 |
| the whole run | 258.4 | 716.5 | 1204.3 |

The numbers each stage reported (`SUMMARY.md`), and how they compare with the results recorded
in the tool directories:

| stage | what it printed |
|---|---|
| `sensor-suite` | 180 trials, all `TrialState.SUCCESSFUL\|SHUT_DOWN`; the MAVF ranking puts design-4370 first (0.6732) and design-4 last (0.3909); `ddo_metrics.csv` and `mavf_ddo_ranking.csv` byte-identical to the ones in `trades-x/case-studies/sensor-suite/results/`, in all three runs |
| `rarrt-planning` | 300 trials, all `SUCCESSFUL`; the planner found a path in all 300; failure rate in the hard rock field at sigma 0.5: rrtstar 0.4225, cvar0.9 0.2535; every column of `cells.csv` and `campaign.csv` but the planning and trial wall times equal to `case-studies/A2-risk-sensitive-planning/results/perfect/` |
| `conformal-calibration` | 270 trials, all `SUCCESSFUL`; 24 704 detections; held-out coverage 0.9156 at alpha 0.1 (q 0.648 m, calibrated on 5399 detections); `calibration.csv`, `episodes.csv`, `coverage.csv`, `alpha_sweep.csv` and `summary.json` byte-identical to the ones in `case-studies/B2-conformal-perception/results/perfect/` |
| `isaacsim-range` | 8 trials, all `SUCCESSFUL`, each a headless Isaac Sim 6.0.1 process, 53.1 to 59.1 s per trial; 3.21 to 13.45 m covered in 30 simulated seconds, the largest roll 179.0°, stuck on 1; distance, pitch, roll, climb, obstacle encounters and the stuck flag equal to `isaacsim/results/campaign.csv` trial by trial |
| `veritas-report` | trials that fail by the criteria above: sensor suite 48 of 180, planner 169 of 300, calibration 202 of 270, range 2 of 8 |
| `uppaal` | UPPAAL 5.0.0: the battery model, 12 queries, 8 satisfied and 4 not satisfied; the behavior-tree model, 2 queries, both satisfied; both models byte-identical to what `veritas/formal/sysml2uppaal/demo_battery.py` and `veritas/formal/bt2automata/demo.py` write |
| `stl-replay` | the eight shipped trajectories: roll_safety violated on 2, pitch_safety on 0, progress on 1, `verdicts.csv` byte-identical to `veritas/runtime/stl-observer/results/range/verdicts.csv`; the `--range` run's own eight trajectories: the same verdicts, byte for byte |
| teardown | 4, 8 and 12 stack processes started in the three runs; none left afterwards, nothing listening on 6390, 5001 or 8003 |

## Flags

| flag | what it does |
|---|---|
| `--all` | adds the risk-sensitive planner and conformal-calibration campaigns |
| `--range` | adds the Isaac Sim range campaign |
| `--list` | lists every stage with the flag that selects it, and stops |
| `--dry-run` | prints the stages a run with the same flags would make and every command they would run; starts nothing and writes nothing |
| `--keep-stack` | after a run that succeeds, leaves the last campaign's PERFECT stack up, so its web UI at `http://127.0.0.1:5001/` and `/api/v1` can be browsed; the summary prints the command that stops it |
| `--out <dir>` | the run directory, instead of `pipeline/out/<date>-<time>` (it must be empty or new) |

## Environment variables

| variable | default | what it sets |
|---|---|---|
| `PIPELINE_REDIS_PORT`, `PIPELINE_FLASK_PORT`, `PIPELINE_RUNNER_PORT` | 6390, 5001, 8003 | the PERFECT stack's ports; a port that is already listening belongs to someone else, and the run refuses to start |
| `PIPELINE_TRIAL_PYTHON` | `/usr/bin/python3` | the interpreter the ROS-free examples run their trials with |
| `UPPAAL_HOME` | unset | the UPPAAL install `verifyta` is found in |
| `ISAACSIM_PYTHON` | unset | Isaac Sim's `python.sh`, for `--range` |
| `PIPELINE_STAGES` | `pipeline/stages` | a directory of stage files to run instead |

`run.sh` unsets `PYTHONPATH` and `VIRTUAL_ENV` for everything it starts, so a sourced ROS 2
environment or an activated virtual environment does not reach the tools' own environments.

## Where the outputs land

```
pipeline/out/<date>-<time>/
  SUMMARY.md             the table above, for this run
  stack-history.txt      every process a stack started: stage, name, pid
  stack.pids             the processes of the stack that is up now (empty after the run)
  preflight/ sensor-suite/ ... teardown/
    stage.log            every command the stage ran and what it printed
    headline.txt         its line in SUMMARY.md
```

A campaign stage's `project/` is a copy of the PERFECT example it ran, holding the database
the trials were written to (`project.db`) and the migrations beside it. `pipeline/out/` is
git-ignored.

## Adding a stage

A stage is a bash file `stages/NN-<name>.sh`. The number orders it; `<name>` names its output
directory. At top level it only sets two variables and defines one function:

```bash
STAGE_WHEN=all       # default (every run), all (with --all) or range (with --range)
STAGE_TITLE="what the stage does, in one line"

stage_run() {
    stack_up "$REPO/perfect/examples/<example>" || return 1
    uv_python <tool directory> "$REPO/<driver>.py" --submit --url "$PERFECT_URL" || return 1
    uv_python <tool directory> "$REPO/<driver>.py" --collect --url "$PERFECT_URL" --out "$STAGE_DIR/results" || return 1
    veritas_args --failure-metric <metric> --failure-below <value> --group-by design
    stack_release || return 1

    [ "$DRY_RUN" = 1 ] && return 0
    expect_trials <n> || return 1
    headline "<n> trials, <n> SUCCESSFUL; <the numbers worth a line>"
}
```

`run.sh` sources it in a subshell with the helpers of `lib/log.sh` and `lib/stack.sh` and
calls `stage_run`; a non-zero return fails the run, and every stage after it is marked not
run. The helpers:

| helper | what it does |
|---|---|
| `stack_up <example>` | copies the example to `$STAGE_DIR/project` and brings Redis, the worker, the runner and the server up on it (an earlier stage's stack goes down first); `$PERFECT_URL` is the server |
| `stack_release` | takes the stack down at the end of the stage, unless `--keep-stack` |
| `perfect_run <command>` | runs a command in PERFECT's environment, from the project copy (for anything that goes through the Flask CLI) |
| `uv_python <tool directory> <args>` | `uv run --frozen --project <tool directory> python <args>` |
| `step <command>` | shows a command and runs it; every command goes through `step`, `uv_python` or `perfect_run`, so that `--dry-run` prints it and `stage.log` records its output |
| `put <file>` | writes stdin to a file, or on a dry run says it would |
| `veritas_args <args>` | the failure-rate report's arguments for this campaign's database; the `veritas-report` stage picks them up |
| `expect_trials <n>` | fails the stage unless the driver printed `trials collected: n` and `SUCCESSFUL trials: n` |
| `headline <text>` | the stage's line in `SUMMARY.md` |
| `skip_stage <reason>` | marks the stage skipped, with the reason as its headline |
| `selected <name>` | whether another stage is part of this run |

A stage writes only under `$STAGE_DIR`. Add its name to the expected lists in
`tests/run_tests.sh`.

## Tests

```bash
bash pipeline/tests/run_tests.sh
```

It checks that every script parses (`bash -n`); that `--list` names the stages in order and
`--dry-run` selects the right ones for no flag, `--all` and `--range`, prints the campaign,
report and replay commands, and creates no run directory and no Redis; that a port already in
use (a throwaway `python3 -m http.server`) is refused before anything starts; that a stage
which fails with a PERFECT stack up on the `dummy` example and a trial running below the runner
leaves no process and no listening port behind, with the failed stage, the stage after it and
the teardown marked in `SUMMARY.md`; that `--keep-stack` leaves the stack answering on its
Flask port and the command it prints stops it; and that SIGINT sent to the run's process group
(what Ctrl-C does) or SIGTERM sent to `run.sh` in the middle of a stage stops the stage and the
stack and still writes `SUMMARY.md`.
Every port it uses is one the kernel hands out as free. Here it printed `16 passed, 0 failed`
in 26.3 s.
