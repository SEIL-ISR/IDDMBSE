# PERFECT

## Description

The PERFormance Evaluation Composible Toolsuite (PERFECT) project is for design space exploration for and simulated testing of systems implemented with the Robot Operating System (ROS). System definitions (for example, of a UGV) are broken into cohesive, decoupled "components" such as sensors, planners, and controllers. A "design" consists of a subset of components sufficient for defining an instance of a general design that may be tested and evaluated. Simulated environments and operation plans (i.e., instructions and scenarios) are also represented as a subset of cohesive, decoupled components.

One important goal for PERFECT is that it may be used via the Systems Modeling Language (SysML) so that the SysML-defined model of the robot system is mapped to the actual implementation in ROS. Applications such as Magic Systems of Systems Architect, which can be used to simulate SysML-defined models, may control and receive data from ROS simulations, brokered by PERFECT. This is done with the RESTful API provided by PERFECT using Flask and is the same used in a browser.

An "experiment" is a combination of design, environment, and operation plan sufficient to run a ROS simulation to completion, with well-defined success and failure states (usually, these will be the result of a ROS action specified by the operation plan). Information about a robot's state or the state of its environment can be collected and analysed in real time; the results of these analyses may inform decisions about cancelling an experiment early if a failure state (defined at a higher level than the ROS action) is reached or, potentially, simulating human intervention or environmental changes.

PERFECT uses a SQLite database to maintain the definitions of components, designs, environmental/instructional components, and experiments.


## Bring-up, as measured

This section records a bring-up that was actually run end to end on the `dummy` example on
2026-09-22 (Ubuntu, Python 3.12.11, ROS 2 Jazzy on the machine but not used by `dummy`).
Every command below was run in the order shown, and every quoted line is copied from that
run. The full log is `analysis-scratch/packaging/F-gate.txt`.

The `dummy` example needs no simulator: it runs `countdown.bash`, which counts to 15 and
exits. It is the right thing to run first when checking that the server, the queue, the
worker and the runner are talking to each other.

### Conventions this project uses

- **`PERFECT_PROJECT_ROOT`** — every PERFECT process (the Flask server, the RQ worker, the
  runner) reads this environment variable. `perfect/app/config.py` uses `os.environ[...]`,
  so a process without it raises `KeyError` at import. Set it to the example directory, and
  make that directory the working directory too: the runner does `__import__("experiment")`
  (`perfect/experiment/runner.py`), which only finds `experiment.py` if it is the cwd.
- **`REDIS_URL`** — `perfect/app/config.py` reads it and falls back to `redis://`. The
  `rq worker` command does not read the Flask config, so it needs `--url` on the command line.
- **The database** lands at `$PERFECT_PROJECT_ROOT/<dirname>.db` (here `examples/dummy/dummy.db`)
  and Alembic's `migrations/` directory beside it. Both are git-ignored. To start over:
  `rm -rf migrations/ *.db*`.
- **`config.py`** — each example may carry one to override defaults from
  `perfect/app/config.py`. `dummy` has none, so the defaults apply and the app logs
  `Did not find .../config.py. Using application defaults`. That line is expected.

### Ports used here

| what | port | why |
|---|---|---|
| Redis | 6390 | this workstation already runs a system `redis-server` on 6379 that belongs to something else. A private Redis on 6390 keeps the two apart. Use 6379 only if it is yours. |
| Flask server | 5001 | 5000 is the upstream default; 5001 was free here. |
| PERFECT runner | 8003 | hard-coded in `perfect/experiment/runner.py`, and matched by the default `RUNNER_URIS` in `perfect/app/config.py`. Changing it means changing both. |

### The environment

A uv virtual environment inside `perfect/`. `setup.py` stays the package definition; no
`pyproject.toml` is needed.

```bash
cd /path/to/IDDMBSE/perfect
uv venv --python 3.12          # -> "Creating virtual environment at: .venv"            (0.01 s)
uv pip install -e .            # -> "+ perfect==0.0.2 (from file:///.../perfect)"       (0.78 s)
source .venv/bin/activate
```

Check it:

```bash
python -c "import perfect, flask, rq, redis; print(perfect.__file__)"
# /path/to/IDDMBSE/perfect/perfect/__init__.py
```

The versions resolved on 2026-09-22 were flask 3.1.3, flask-migrate 4.1.0, flask-sqlalchemy
3.1.1, rq 2.12.0, redis 8.1.0, sqlalchemy 2.0.54, websockets 17.1.

PERFECT's ROS experiment classes (`perfect/experiment/ros/`) additionally need `rclpy`, so an
example that drives ROS has to be run from a Python environment that has ROS 2 on its path.
`dummy` does not touch ROS.

### Redis

In its own terminal. On a machine where 6379 is already taken by something you do not own,
run your own instance instead of sharing:

```bash
redis-server --port 6390 --save '' --appendonly no --dir /tmp/perfect-redis
```

### The four terminals

All four need the same two environment variables and the same working directory:

```bash
export PERFECT_PROJECT_ROOT=/path/to/IDDMBSE/perfect/examples/dummy
export REDIS_URL=redis://127.0.0.1:6390
source /path/to/IDDMBSE/perfect/.venv/bin/activate
cd $PERFECT_PROJECT_ROOT
```

Every `python -m flask --app perfect.app ...` call first prints three lines from
`create_app` ("Welcome to the PERFECT Application!", the missing-`config.py` warning, and
"No custom model module found. Using base PERFECT models"). The comments below show only the
line that is specific to each command, and the bracketed number is that command's wall time.

**Database and components** (one-off, in any terminal):

```bash
python -m flask --app perfect.app db init
# Please edit configuration/connection/logging settings in
#     .../examples/dummy/migrations/alembic.ini before proceeding.                      (0.35 s)

python -m flask --app perfect.app db migrate -m "Initial migration."
# Generating .../migrations/versions/e724411eaff6_initial_migration.py ...  done        (0.38 s)

python -m flask --app perfect.app db upgrade
# INFO  [alembic.runtime.migration]
#     Running upgrade  -> e724411eaff6, Initial_migration.                              (0.42 s)

python -m flask --app perfect.app components load_component_implementations components.json
# INFO app components._load_component_implementations:104 -
#     Committed 4 Components from components.json                                       (0.37 s)
```

The revision hash (`e724411eaff6`) is new on every `db migrate`, and the text after it is
whatever `-m` was given; the run recorded here passed it without quotes, hence
`Initial_migration.`. `db init` says "Please edit ... before proceeding" — nothing needs
editing for this example.

Note the command name: it is `components load_component_implementations <file>`, not
`components load`. There is a separate `components load_components` that takes no argument
and reads the built-in library under `perfect/common/components/`.

**One design, one environment, one experiment.** `experiments create` matches designs and
environments **by tag**, not by name (see the FIXME in `perfect/app/routes/experiments.py`),
so everything below carries the tag `demo`:

```bash
python -m flask --app perfect.app designs create "Widget A" "Dijkstra" -i \
    --name "Widget A + Dijkstra" --tag demo
# INFO app designs._create_design:170 - Committed Design <id=1 components=[]>           (0.37 s)

python -m flask --app perfect.app environments create_explicit "Nothing" '{}' -t demo
# (no output; writes environment id 1)                                                  (0.37 s)

python -m flask --app perfect.app experiments create demo demo -t demo
# Patterns matched 1 designs and 1 environments, so 1 experiments total                 (0.39 s)
```

`-i` tells `designs create` to select `ComponentImplementation` rows rather than `Component`
rows. `components=[]` in the log is expected for a design built that way: the WARNING comment
in `_create_design` explains that such designs keep no link back to `Component`.

**The three long-lived processes**, one terminal each:

```bash
rq worker perfect-tasks --url redis://127.0.0.1:6390
# *** Listening on perfect-tasks...

python -m perfect.experiment.runner
# INFO runner runner._run_websocket:195 - Starting server on port 8003
# INFO runner runner._run_websocket:197 - Started server and awaiting stop

python -m flask --app perfect.app run --port 5001
#  * Serving Flask app 'perfect.app'
#  * Debug mode: off
```

Add `--host 0.0.0.0` to the last one to reach the UI from another machine.

The server prints no `* Running on http://...` line: `create_app` sets the werkzeug logger to
WARNING, which suppresses it. `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5001/`
returning `200` is the way to tell it came up.

**Run one experiment:**

```bash
python -m flask --app perfect.app experiments run demo
# INFO app models.run:292 - Enqueued job 137f8109-...-68c00f790812 for Trial(1, 1)      (0.40 s)
```

The worker picks the job up, asks the runner whether it is free, and hands the trial over.
The runner's terminal then shows the experiment's own output:

```
INFO core experiment.run:273 - Initializing DummyExperiment(1489c686-...)
INFO core experiment.run:275 - Initialized DummyExperiment(1489c686-...)
INFO core experiment.run:281 - Ready to start DummyExperiment(1489c686-...)
INFO core experiment.run:282 - Starting DummyExperiment(1489c686-...)
Counting up to 15
1
...
15
Done!
INFO core experiment.__callbacks_loop:269 - Exiting checks loop
INFO core experiment.run:293 - Shut down DummyExperiment(1489c686-...)
```

`DummyExperiment._init` also prints `Initialized in 4...` down to `1...` between the first two
lines. In a terminal they appear there; in the log above, captured through a pipe, they were
flushed at the end instead, because Python block-buffers `print` when stdout is not a tty.
`countdown.bash` is a separate process and its lines are not affected.

The whole trial took 19.3 s wall (`Successfully completed perfect.app.tasks.run_trial(...)
job in 0:00:19.295072s`): 4 s of `_init`, then the 15 s countdown.

**Read the result back.** In a browser, `http://localhost:5001/` is the project home and
`http://localhost:5001/experiments/` lists experiments with a live State column. The same
pages are the REST surface, so `curl` works on them:

```bash
curl -s http://127.0.0.1:5001/experiments/ | grep -- '-state'
# <td id="1-state">TrialState.SUCCESSFUL|SHUT_DOWN</td>
```

Or read the `state` column of the `trial` table directly:

```bash
python -c "import sqlite3; print(sqlite3.connect('dummy.db').execute('select id, state, start_age from trial').fetchall())"
# [(1, 'TrialState.SUCCESSFUL|SHUT_DOWN', 15.024981260299683)]
```

`start_age` is the time from the start of `_run` to completion: 15.02 s, which is the
countdown. `TrialState` is a `Flag` (`perfect/experiment/experiment.py`), so a terminal state
is a combination: `SUCCESSFUL|SHUT_DOWN` here.

One caution: `GET /experiments/updates` is what the pages poll, and it **deletes** the
`Update` rows it returns. Do not use it as a read-only API.

### Time for the whole thing

| step | wall |
|---|---|
| `uv venv` | 0.01 s |
| `uv pip install -e .` | 0.78 s |
| `db init` | 0.35 s |
| `db migrate` | 0.38 s |
| `db upgrade` | 0.42 s |
| `components load_component_implementations` | 0.37 s |
| `designs create` | 0.37 s |
| `environments create_explicit` | 0.37 s |
| `experiments create` | 0.39 s |
| `experiments run demo` (enqueue only) | 0.40 s |
| the trial itself, enqueue to `SHUT_DOWN` | 19.3 s |

## Provenance

- Upstream: `https://code.umd.edu/drhunter/perfect` (UMD GitLab), author Daniel Robert Hunter
  (`drhunter@umd.edu`), package version 0.0.2.
- This directory is a snapshot of the upstream `example-isaacsim-husky` branch, tip of
  2025-01-02, imported into the IDDMBSE mono-repository on 2026-09-21.
- The design-space-exploration work that used to live here as `perfect_MBO/` (Julia MBO plus
  the MATLAB alternative) and `pyjulia_example/` now lives in `trades-x/` at the repository
  root, as `trades-x/mbo`, `trades-x/mbo-matlab-alt` and `trades-x/pyjulia-example`.

### Changes made here to get the bring-up above to run

The snapshot did not run as imported against current dependency versions. Five small changes,
all of them either version compatibility or a plain defect; none changes what PERFECT does:

1. `perfect/experiment/experiment.py` — `from pxr import Usd` moved from module scope into
   `edit_local_usd()`, the only function that uses it. OpenUSD is not in `setup.py` and is
   only present in Isaac Sim's Python, so the top-level import made every PERFECT process
   (including the Flask server and the RQ worker) unimportable without Isaac Sim.
2. `perfect/app/models.py` — `rq_job.get_id()` to `rq_job.id` in `Trial.run()`. rq 2.x removed
   `Job.get_id()`; `Job.id` has been there in both 1.x and 2.x.
3. `perfect/experiment/runner.py` — `websockets.serve` returns an
   `websockets.asyncio.server.ServerConnection` from websockets 14 on, which has no `.open`
   or `.closed`. The `info` op now derives those two booleans from `.state`, so the JSON it
   replies with is unchanged. The type import moved off the deprecated
   `websockets.server.WebSocketServerProtocol`.
4. `perfect/app/routes/components.py` — a misplaced parenthesis meant the "Committed N
   Components" log line was replaced by an empty string whenever nothing was invalid, so a
   successful load reported nothing. Now parenthesised as intended.
5. `examples/dummy/` — `experiment.py` gained `_files = {}` (`BaseExperiment` iterates
   `self._files`, and the class-level annotation creates no attribute, so `DummyExperiment`
   raised `AttributeError` before it could start; every other example sets it).
   `components.json` was rewritten from a `specification` key, which no current loader reads,
   to the `implementation` key that `load_component_implementations` validates against
   `perfect/app/schema/implementation_schema.json`, each with `"parameters": []` as the other
   examples' `impl.py` produce.
