# VERITAS

VERIfication of Trusted Autonomous Systems — the assurance layer of IDDMBSE.

The paper (`manuscript/.../sections/framework.tex`, §"VERITAS: Three-Module Verification of
Trusted Autonomy") describes three modules: a **model-based** module that compiles SysML
state-machine and activity diagrams into UPPAAL networks of timed automata; a **data-driven**
module that uses PERFECT simulation campaigns to estimate failure rates and confidence bounds;
and a **runtime** module that synthesizes STL/MITL monitors for the deployed stack. For behavior
trees specifically, `sections/case_studies.tex` says VERITAS "supports automated model generation
[BT2Automata, HSCC 2025] and the synthesis of online monitors [OMTBT, ECC 2025] directly from BT
specifications", uses the formal models "for verification of task plans and formal control
synthesis in UPPAAL", and uses the online monitors "for quantitative task monitoring and to
provide feedback for learning-based controllers".

Two kinds of code sit here. Three code bases are **vendored** from two of the coauthor's research
repositories at pinned commits (see `ATTRIBUTION.md`) and cover the behavior-tree half of the
paper. Three more were **built for this release** to fill the parts of the paper's description
that the vendored code does not reach: the SysML front end of the model-based module, the whole
data-driven module, and the deployed-stack observer of the runtime module.

| module in the paper | what ships here | origin | what it does |
|---|---|---|---|
| model-based (§III-D (i)) | `formal/sysml2uppaal/` | built for this release | compiles SysML state machines and activities out of a MagicDraw `.mdzip` into an UPPAAL network of timed automata, and turns requirements into proof obligations in its queries block |
| model-based (§III-D (i)) | `formal/bt2automata/` | vendored, HSCC'25 | composes a behavior tree into a UPPAAL network of timed automata, for model checking and control synthesis in the UPPAAL GUI |
| data-driven (§III-D (ii)) | `datadriven/` | built for this release | failure rate, Clopper-Pearson and Wilson confidence bounds, campaign-size design and post-hoc STL robustness statistics over a PERFECT simulation campaign, read straight out of PERFECT's SQLite database |
| runtime (§III-D (iii)) | `runtime/stl-observer/` | built for this release | a generic-subscriber ROS 2 node that watches the deployed stack against STL obligations written in YAML, publishes robustness and a violation flag per obligation, and logs an alarm; plus the same monitors over a recorded CSV |
| runtime (§III-D (iii)) | `runtime/tbt-monitor/` | vendored, ECC'25 | greedy online monitor for a behavior tree, with RTAMT STL leaf specifications; returns a quantitative robustness and a three-valued node state at every step |
| (control synthesis, not one of the three modules) | `synthesis/ltbt/` | vendored | three-valued (Kleene) encodings of temporal behavior trees as Gurobi MILP constraints, and trajectory-synthesis scripts built on them |

The multi-robot STL/MILP demonstration of the paper is not here; it is being built separately in
`case-studies/B3-assured-multi-robot/`.

## Install

This is a self-contained uv project on Python 3.10 (the upstream pins need it).

```
cd veritas
uv venv --python 3.10
uv sync
```

Two optional extras, neither needed by any of the demos below except the last one:

```
uv sync --extra rl      # torch, stable-baselines3, panda-gym — for the RL rollout
uv sync --extra milp    # gurobipy, scipy, matplotlib — for the synthesis scripts
```

`uv sync` makes the environment exact, so the two extras replace each other unless you ask for
both at once (`uv sync --extra rl --extra milp`).

**If you have a ROS 2 environment sourced**, `PYTHONPATH` points at ROS's `site-packages`, pytest
autoloads ROS's `launch_testing` plugin into this Python 3.10 venv and the run dies with
`ModuleNotFoundError: No module named 'yaml'`. Prefix the commands with `env -u PYTHONPATH`, or
open a shell with ROS not sourced. Everything here runs without ROS, **except** the observer node
`runtime/stl-observer/stl_observer_node.py`, which needs `rclpy` and therefore runs in ROS's own
Python — see its section below, which is the one place the two environments meet.

## Demos

### 1. SysML to UPPAAL — `formal/sysml2uppaal/`

```
uv run python formal/sysml2uppaal/demo_battery.py
```

Reads `sysml/models/AGR_stack-MB-SensorTrade-mk6.mdzip` (read-only; the demo checks the file's
md5 is unchanged), translates its one state machine and the small `Demo AD` activity, and writes
`battery_sm.xml` next to the script.

**What it reads.** MagicDraw writes UML 2.5 XMI inside the `.mdzip`, in the zip member
`com.nomagic.magicdraw.uml_model.model`. In that dialect the XML tag is the element's *role*
(`packagedElement`, `ownedBehavior`, `region`, `subvertex`, `transition`, `node`, `edge`) and the
metaclass is the attribute `xmi:type`, so a state machine is `<ownedBehavior
xmi:type='uml:StateMachine'>`, never `<uml:StateMachine>`. Requirements are the exception: they
are stereotype applications literally tagged `<sysml:Requirement Id='…' Text='…'
base_Class='…'/>`, with `Id` and `Text` as attributes. There is no `<guard>` element anywhere in
this model — a transition's condition lives on its `trigger`'s event, which is a top-level
`uml:ChangeEvent` (`changeExpression > body`) or a `uml:TimeEvent` (`when > expr @value`).

**The supported fragment.** Conditions and effects of the form `var OP const`, with `OP` one of
`< <= > >= == != =` and `const` a decimal number, plus `&&`-joined conjunctions of those. UPPAAL
has no reals, so a real variable is scaled to an integer by a documented factor (default 100) and
declared `int`: `current_soc < 0.6` becomes `current_soc < 60`. Each template gets a local
`clock t`, reset on every edge, so `t` is the time spent in the current location; the network
shares one `clock gt` that is never reset. A TimeEvent with `isRelative='true'` and value V
becomes the guard `t >= V`, and the source location gets the invariant `t <= V` when *all* its
outgoing edges are relative TimeEvents, which is UML's `after(V)`. A TimeEvent without
`isRelative` becomes `gt >= V`. Entry behaviours become assignments on every edge entering the
state. Anything outside the fragment is copied into an UPPAAL `comments` label and reported as a
warning, never silently dropped.

**What it produces on the mk6 model.** One template `ee_hv_battery_charge_discharge` with five
locations (`Pseudostate`, `Operational`, `Enter_Power_Saving_Mode`, `Charging` with the invariant
`t <= 1200`, `Quick_Charge_Complete`) and five edges, and one template `Demo_AD` with four
locations and four edges. Four warnings, all of them about the source model rather than the
translator:

* the initial `uml:Pseudostate` has no `kind` attribute, so it is read as `initial`, the UML default;
* the `doActivity` of `Quick Charge Complete` (`current_soc=0.7`) is applied once on entry, because a timed automaton has no do-while-in-state behaviour;
* the TimeEvent on `Enter Power Saving Mode -> Charging` has no `isRelative`, so its 3600 is read as an absolute time on `gt`, which UPPAAL cannot bound from above;
* the transition `Quick Charge Complete -> Operational` carries the informal label `when (current_soc=0.7) && after(100)` in its `name` attribute, and only its structured trigger (the ChangeEvent half) is translated — the `after(100)` has no `uml:TimeEvent` behind it in the model.

Translating all three activities instead of just `Demo AD` adds twelve more warnings: nine
`ForkNode`s and one `JoinNode` in `Perception Module Activity Diagram` become ordinary locations,
so their branches read as a nondeterministic choice and not as concurrency (that activity is
therefore **not** faithfully translated); nine of its object flows start or end on a pin and are
lifted to the owning action; and `Sensor Suite` has no nodes at all and is skipped.

**The two proof obligations.** The model carries no structured satisfy/verify link between a
requirement and a state-machine variable — the guards are free-text OpaqueExpressions — so the
demo supplies the binding explicitly as an alias table, and only requirements whose `Text`
matches one of those phrases become queries:

```
A[] current_soc > 60    // P.1.4 AGR Battery State of Charge: "The AGR Battery State of Charge
                        //   during operation shall always be more than 0.6."
A[] gt < 180            // P.1.2 Time to Completion: "The AGR shall complete the entire path in
                        //   the test environments in less than 180 seconds."
```

plus `A[] not deadlock` and one `E<> …` reachability query per location.

What these two mean, honestly. **P.1.4 is the real obligation**, and on this model it is
discharged for an uninteresting reason: the only assignments to `current_soc` set it to 70, and
the only guard that would leave `Operational` needs `current_soc < 60`, so nothing in the
authored state machine ever lowers the state of charge. The battery discharge is not modelled at
all, and the safety property holds vacuously. That is a finding about the SysML model, and it is
exactly the sort of thing the translation is for; it is read off the generated automaton here,
not checked with UPPAAL. **P.1.2 is the clock path demonstrated on a requirement this state
machine does not implement** — the battery machine has no notion of completing a path — so it is
there to show that a time-bounded requirement maps onto `gt` rather than onto a scaled integer,
and it is expected to fail on this model.

**Checking them needs UPPAAL, which is not shipped** (see *Licenses*). Download it from
<https://uppaal.org/downloads/>, register an academic key at <https://uppaal.veriaal.dk/>, then
`File > Open` the generated `battery_sm.xml`, go to the `Verifier` tab, pick a query and press
`Check`. **No query in this file has been checked**: no UPPAAL was available on the machine that
ran the gates. What *was* checked is that the file is a well-formed NTA whose every edge endpoint
resolves and that `pyuppaal.UModel` parses it back with the same templates and queries.

One trap: `pyuppaal` 1.2.0 **rewrites the file you point it at** — `UModel.__init__` round-trips
the XML back to disk, which drops the DOCTYPE line and the `<comment>` text of every query. The
demo and the test therefore load a *copy*, so `battery_sm.xml` stays as the translator wrote it.

The translator is also a command-line tool for any other model:

```
uv run python formal/sysml2uppaal/sysml2uppaal.py model.mdzip out.xml --scale 100
```

### 2. Behavior tree to UPPAAL — `formal/bt2automata/`

```
uv run python formal/bt2automata/demo.py
```

Composes the behavior tree of the BT2Automata paper's §6.1 example — `Sequence(FA,
Sequence(Selector(CBatt, FCharger), FB))`, read as *go to A; if the battery is low go to the
charger first; then go to B* — from the leaf automata in `leaf_node_templates.xml`, and writes
`BT_converted.xml` next to the script. The composition follows Alg. 1 of the paper and its
complement for selectors; `bt2ta/bt2ta.py` also has the parallel composition (Alg. 2), the
`Eventually`/`Always`/`Condition` leaf constructors and a grid-world transition-system generator,
none of which this demo exercises.

The written model is a UPPAAL NTA with three templates — `BT` (the composed tree, with the
`Success` and `Failure` locations), `Battery` and `Grid` — instantiated as `spec=BT(20)`,
`battery=Battery(75)`, `grid=Grid()`, and carries two queries:

```
E<> spec.Success
E<> spec.Failure
```

To check them you need UPPAAL, which is **not** shipped here (see *Licenses* below). Download it
from <https://uppaal.org/downloads/>, register for an academic license at
<https://uppaal.veriaal.dk/>, and enter the key on first launch. Then: `File > Open` the
generated `BT_converted.xml`, go to the `Verifier` tab, select a query and press `Check`. To read
off a control sequence rather than a yes/no, set `Options > Diagnostic Trace` (for example
`Fastest`) before checking, and open the returned trace in the `Simulator` tab.

Both queries are expected to be satisfied: the first witnesses a trace in which the robot
completes the task, the second a trace in which it does not (a robot that sits still violates the
specification). That is what the upstream comment in the script says the queries demonstrate; it
is **not verified here**, because no UPPAAL installation was available on the machine that ran the
gates.

### 3. Failure rates and confidence bounds over a PERFECT campaign — `datadriven/`

```
uv run python datadriven/demo_campaign.py
```

The paper's data-driven module "uses PERFECT simulation campaigns to estimate failure rates and
confidence bounds for parts of the system where formal models are intractable". `campaign_stats.py`
is that estimation, `perfect_adapter.py` gets the campaign out of PERFECT, and the demo runs both
on PERFECT's own dummy example and on a seeded synthetic campaign.

**Reading a campaign.** `perfect_adapter.read_campaign(db)` opens PERFECT's SQLite file read-only
(`file:…?mode=ro`) and joins `trial` to `experiment` to `design`. Two things about that schema
are worth knowing because they are not what you would guess:

* `trial.state` is a **plain string column**, not an enum column. `TrialState` in
  `perfect/perfect/experiment/experiment.py` is an `enum.Flag`, the runner sends the integer
  bitmask, and `perfect/perfect/app/tasks.py` stores `str(TrialState(mask))` — Python's
  `Flag.__str__`, which pipe-joins the member names. A finished successful trial therefore reads
  `TrialState.SUCCESSFUL|SHUT_DOWN`, and a trial counts as a success exactly when `SUCCESSFUL` is
  one of the joined members.
* there is **no `duration` column**. The two time columns are `start_age` (wall-clock seconds the
  trial ran) and `sim_time` (simulated seconds off the `/clock` topic, which is NULL in the dummy
  example). The adapter returns both, with NULL as `nan` rather than 0.

`read_campaign_csv` is the fallback for a campaign exported to CSV rather than read live.

**The statistics.** `failure_rate` is the point estimate; `clopper_pearson` is the exact interval
(it inverts the binomial tails through the Beta quantile, so its coverage is at least 1 − δ for
every true p) and `clopper_pearson_upper` its one-sided form, which is the number a safety case
wants; `wilson` is the score interval, narrower and only asymptotically covering.
`trials_for_upper_bound(target, delta, failures)` is the campaign-size design: the smallest n
whose exact upper bound reaches `target` if the campaign ends with that many failures — at zero
failures it is the closed form n = ln δ / ln(1 − target). `robustness_stats` summarises post-hoc
STL robustness over the recorded trajectories: mean, min, the empirical violation fraction, the
empirical lower quantile, and a distribution-free (DKW) correction of that quantile, which is
−inf and says so when the campaign is too small for the band to be narrower than the quantile
level. Everything is whole-array numpy and the bound functions broadcast over arrays of k and n.

**What the demo prints.** On `perfect/examples/dummy/dummy.db` — one trial, state
`TrialState.SUCCESSFUL|SHUT_DOWN`, `start_age` 15.025 s, `sim_time` NULL — the table is
degenerate and the point of printing it is to show how little one trial buys: failure rate 0, but
the exact upper bound is 1 − 0.05^(1/1) = 0.95, and it takes 59 zero-failure trials before that
bound reaches 0.05. On the synthetic campaign of 200 trials (each draws a robustness from
N(0.15, 0.12) and fails exactly when it is negative, so the true failure probability is
Φ(−1.25) = 0.10565) the estimate is 0.085 with the exact interval [0.0503, 0.1326], which
contains the truth, and the Wilson interval [0.0537, 0.1319] inside it. The same campaign at 2000
trials is printed too, because that is where the DKW band finally becomes narrower than a 5%
quantile level (it takes 738 trials).

#### Bisimulation functions

The long-form report describes, for this module, **bisimulation functions** that bound the
distance between the trajectories of repeated runs, so that a finite campaign can be turned into
a guarantee about the runs it did not execute. That idea is **described here and not
implemented**: nothing in `datadriven/` computes a bisimulation function or a trajectory-distance
bound, and the statistics above make no such assumption — they are the ordinary i.i.d. binomial
and empirical-CDF bounds over independent trials.

### 4. The STL observer on a live ROS 2 stack — `runtime/stl-observer/`

The paper's runtime module "synthesizes observers, typically expressed as Signal Temporal Logic
(STL) or Metric Interval Temporal Logic (MITL) monitors, that watch the deployed stack and raise
alarms on specification violations", and the long-form report calls its front end a **generic
subscriber**: one node that discovers and subscribes to topics without being recompiled for each
one. That is what `stl_observer_node.py` is. The message type is a string in the YAML spec,
resolved at run time with `rosidl_runtime_py.utilities.get_message`, so adding a signal on a new
topic of a new type is an edit to the YAML and nothing else.

**The spec.** `specs/agr_safety.yaml` carries three obligations. Two come from requirements in
`sysml/models/AGR_stack-MB-SensorTrade-mk6.mdzip`, quoted verbatim in the file:

| monitor | requirement | formula | signal |
|---|---|---|---|
| `soc_safety` | P.1.4, "…state of charge…shall always be more than 0.6" | `historically (soc >= 0.6)` | `/battery_state` `sensor_msgs/msg/BatteryState.percentage` |
| `goal_liveness` | P.1.2, "…shall complete the entire path…in less than 180 seconds" | `once[0,180] (goal >= 0.5)` | `/goal_reached` `std_msgs/msg/Bool.data` |
| `obstacle_safety` | — (no numbered requirement; a local safety obligation) | `historically (obstacle_distance >= 0.5)` | `/obstacle_distance` `std_msgs/msg/Float64.data` |

RTAMT's online monitor implements past-time operators only, so a safety obligation is written
directly as `historically (p)` and a bounded-future one as `always[0,T] (p)` with `pastify: true`,
which RTAMT rewrites into the past. Interval bounds are in **seconds**: the sampling period is
handed to RTAMT, so `once[0,180]` really means the last 180 seconds. A field path is dotted
(`percentage`, `pose.position.x`, `ranges.0`) and the value is cast to float, which turns a Bool
field into 1.0 / 0.0 — the "Booleanizer" direction of the report, a predicate over the real signal
(`goal >= 0.5`) standing in for the Boolean. `warmup` holds the violation flag down for the first
N seconds, which is what keeps `goal_liveness` from reporting a violation simply because the run
has only just started.

**The node** publishes `std_msgs/Float64` on `/veritas/<monitor>/robustness` and `std_msgs/Bool`
on `/veritas/<monitor>/violation`, samples every signal at the spec's `rate` with a zero-order
hold between messages, starts a monitor once all of its signals have arrived at least once, and
logs a warning on every entry into and exit from violation.

**Running it.** The node needs `rclpy`, so it runs in ROS's Python, not in this venv. RTAMT is not
in ROS's Python either; install it into a directory of your own and put that on `PYTHONPATH`
(never into the system Python or into `/opt/ros`):

```
uv pip install --python /usr/bin/python3 --target /tmp/veritas-ros-deps 'rtamt==0.3.5' 'antlr4-python3-runtime==4.7'
source /opt/ros/jazzy/setup.bash
export PYTHONPATH=/tmp/veritas-ros-deps:$PYTHONPATH
export ROS_DOMAIN_ID=87 RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=1
python3 runtime/stl-observer/stl_observer_node.py --spec runtime/stl-observer/specs/agr_safety.yaml --duration 34
```

and, in a second shell with the same environment, the synthetic scenario the spec is written
against — the state of charge decays linearly through 0.6 at t = 20 s, the goal is reached at
t = 28 s, the obstacle distance never drops below 0.8:

```
python3 runtime/stl-observer/test_publisher.py --duration 32
```

Pick a `ROS_DOMAIN_ID` nobody else on the machine is using; the domain and RMW above are what the
gate run used to keep its graph off the workstation's shared one.

**Replaying instead.** `replay_observer.py` runs the same `Monitor` objects over a CSV with a
`time` column and one column per signal, entirely inside this venv with no ROS:

```
uv run python runtime/stl-observer/replay_observer.py trace.csv --spec runtime/stl-observer/specs/agr_safety.yaml
```

so an obligation can be developed and tested offline and then deployed unchanged.

### 5. Behavior-tree runtime monitor — `runtime/tbt-monitor/`

```
uv run python runtime/tbt-monitor/demo_synthetic.py
```

Runs the monitor on a hand-made pick-and-place trace, so it needs only the base install — no
torch, no simulator, no display. The behavior tree is `Sequence(reach object, grasp, reach goal)`;
the leaf specifications are `eventually(d2obj < 0.1)`, `eventually(gripper width < 0.05)` and
`eventually(d2goal < 0.05)`, each evaluated by RTAMT over the signal window since the previous
leaf succeeded. The demo prints `(rho, state)` at every step, for two traces:

* a trace that reaches, grasps and places, which ends at `state 1` (success) with `rho 0.012`;
* a trace whose gripper never closes, which stays at `state 0` for the whole episode with
  `rho -0.03` (the grasp margin, 0.05 − 0.08).

The second trace never reports failure, and that is the semantics, not a bug: `get_status` in
`panda_specifications.py` maps a robustness to 1 if positive and 0 otherwise, so a leaf here never
returns −1, and −1 is the only value that drives `compose_seq` to a failure verdict. A leaf that
has not yet been satisfied is *running*, i.e. the verdict is still unknown.

The RL rollout the OMTBT paper reports is `main.py`, kept as documentation of the published
experiment. It needs the `rl` extra:

```
uv sync --extra rl
uv run python runtime/tbt-monitor/main.py --n-rollouts 2 --no-video
```

It loads the trained TQC policy `tqc_pandp.zip` (24 MB, shipped), wraps
`PandaPickAndPlaceDense-v3` in a wrapper whose `step()` returns the monitor's robustness **as the
reward**, and rolls out episodes. This is inference-time substitution on an already-trained
policy, not retraining. Drop `--no-video` to record episode videos into
`runtime/tbt-monitor/videos/` and write slow-motion copies with moviepy. Note that the
`Success Rate` it prints sums `info['is_success']` over every simulation step and divides by the
number of episodes, so it is not the fraction of successful episodes.

### 6. MILP synthesis from temporal behavior trees — `synthesis/ltbt/`

```
uv sync --extra milp
cd synthesis/ltbt && uv run python robot.py
```

`ltbt/boolean.py` is the two-valued encoding and `ltbt/ternary.py` the three-valued (Kleene)
one, both building a semantics tree — linear predicates, box constraints, `Not`/`Or`/`And`,
`Always`/`Eventually`, `Sequence`/`Selector` — out of gurobipy indicator constraints, with one
upper-triangular satisfaction variable block per node. `robot.py` (N=15) and `robot2.py` (N=20)
synthesise a trajectory for one double-integrator robot against
`Sequence(ebox1, Selector(Batt, ebox3), ebox2)`, minimising control effort; `multiagent.py`
(N=30) and `multiagent2.py` (N=20) do three double integrators against a shared
`Sequence(Eventually(box1), Eventually(box2))` with big-M halfspace obstacle avoidance and
pairwise collision avoidance. `plot.py`, `plot2.py` and `plot3.py` are the figure scripts.

These scripts need a full Gurobi license; they do not fit the size-limited license that ships with
pip `gurobipy` (`robot.py` is 4190 variables and 2292 constraints, and a quadratic objective caps
that license at 200 variables). Runtimes recorded in the upstream solver logs, on the author's
machine: 22.96 s and objective 1.1243 for `robot2.py` (341 rows by 2888 columns; the upstream
`temp.sh` is what pairs that log with that script), and 309.42 s (objective 7.9662) and 790.00 s
(objective 12.3665) for two multi-agent runs of 901 rows by 2394 columns. Those logs are not
shipped.

`robot.py` writes `robot/{x,u,z}.npy` and `test.png` into `synthesis/ltbt/`; the shipped
`robot/{true,false,true_tern,false_tern}/` are the author's saved solutions, which is what
`plot.py` reads. `plot2.py` and `plot3.py` read `multiagent/x.npy`, which is **not** shipped —
regenerate it with `multiagent2.py` first.

The repository is named `ltbt` and carries no README and no paper reference. The manuscript's
bibliography has an entry that matches its content closely — Matheu, Baras and Belta, *Ternary
Logic Encodings of Temporal Behavior Trees with Application to Control Synthesis*,
arXiv:2604.12092, 2026 — so that is most likely the companion paper, but the code never says so
`[inferred]`.

## What is not shipped

* **UPPAAL verdicts.** `formal/sysml2uppaal/` and `formal/bt2automata/` both write models and
  queries; neither has been *checked*, because no UPPAAL was installed on the machine that ran the
  gates. What is verified is the XML, not the properties.
* **PRISM and Lean.** The paper's figure names UPPAAL, PRISM and Lean as the mathematical
  verification tools. Only the UPPAAL path has code here.
* **Concurrency in the activity translation.** `ForkNode` and `JoinNode` become ordinary
  locations, so a forked activity — including `Perception Module Activity Diagram` in the mk6
  model — reads as a nondeterministic choice and is not faithfully translated. Channel-synchronised
  parallel templates would be the fix.
* **Bisimulation functions.** Described in the data-driven section above, not implemented.
* **A write-back into the SysML model.** Nothing here edits a `.mdzip`; the translator opens the
  model read-only and the observer never touches it. The paper's "single source" for an assurance
  argument is a one-way read at this point: requirements come out of the model into queries and
  into the observer's YAML, and no verdict goes back in.
* **BagWorld.** Not in this directory and not needed by any demo here.
* **The multi-robot STL/MILP demo of the paper.** The paper's released demonstration has three
  per-robot reach-avoid specifications φ1, φ2, φ3, STL robustness scored per executed trajectory
  (ρ = 0.199, −0.04, 0.999) and written back into the SysML block. The `multiagent*.py` scripts
  here solve a different problem — three agents against one shared two-box sequence spec, with no
  robustness scoring and no model write-back. That demonstration is being built separately in
  `case-studies/B3-assured-multi-robot/`.
* **The UPPAAL binary** and **any UPPAAL license key**. See below.
* **The upstream `UPPAAL Instructions.pdf`**, which the source repository says contains a license
  key. The steps it covers are summarised in the bt2automata section above instead.

## Licenses

* **UPPAAL** — required for the bt2automata demo's verification step, not bundled. Free for
  non-commercial academic use: "The Uppaal toolkit is free for non-commercial applications for
  academic institutions that deliver academic degrees" (<https://uppaal.org/downloads/>).
  Redistribution by a third party is not permitted — "We will never distribute or modify any part
  of the UPPAAL code (i.e. the source code and the object code) without a written permission from
  Veriaal ApS" (<https://uppaal.veriaal.dk/academic.html>) — which is why the 38 MB binary
  distribution in the upstream repository was not carried over. Download it yourself and register
  for a key at <https://uppaal.veriaal.dk/>.
* **Gurobi** — optional, only for `synthesis/ltbt/`. `pip install gurobipy` ships a size-limited,
  non-commercial license (2000 variables and 2000 constraints, 200 variables once the model has
  quadratic terms). A free academic named-user license, unlimited in model size, is at
  <https://www.gurobi.com/academia/academic-program-and-licenses/>.
* **RTAMT** — BSD-3-Clause, installed by `uv sync` from PyPI. pyuppaal, stable-baselines3,
  sb3-contrib, panda-gym, gymnasium and moviepy are all MIT.
* **The vendored code itself** — neither upstream repository carries a LICENSE file. The code is
  used here with the author's agreement as a coauthor of the IDDMBSE paper; anyone wanting to
  reuse it beyond that should ask him. See `ATTRIBUTION.md`.

## Citations

* R. Matheu, A. G. Puranic, J. S. Baras and C. Belta. *BT2Automata: Expressing Behavior Trees as
  Automata for Formal Control Synthesis.* Proceedings of the 28th ACM International Conference on
  Hybrid Systems: Computation and Control (HSCC '25), 2025, pp. 1–11.
  DOI 10.1145/3716863.3718042.
* R. Matheu, A. G. Puranic, J. S. Baras and C. Belta. *OMTBT: Online Monitoring of Temporal
  Behavior Trees with Applications to Closed-Loop Learning.* 2025 European Control Conference
  (ECC), 2025, pp. 2129–2135. DOI 10.23919/ECC65951.2025.11187275.
* T. Yamaguchi, B. Hoxha and D. Ničković. *RTAMT — runtime robustness monitors with application to
  CPS and robotics.* International Journal on Software Tools for Technology Transfer 26(1),
  2024, pp. 79–99.
* R. Matheu, J. S. Baras and C. Belta. *Ternary Logic Encodings of Temporal Behavior Trees with
  Application to Control Synthesis.* arXiv:2604.12092, 2026. (The likely companion of
  `synthesis/ltbt/`; see the note there.)

## Tests

```
uv run pytest -q
```

(again, prefix with `env -u PYTHONPATH` if you have ROS 2 sourced).

`tests/test_bt2automata.py` runs the demo into a temporary directory and checks that the written
file parses as an NTA with the three expected templates and both queries.
`tests/test_tbt_monitor.py` checks the monitor's verdicts on the two synthetic traces; the
docstring quotes the vendored lines each expectation is read off.
`tests/test_ltbt.py` checks the three-valued constants, and solves a five-step double-integrator
problem if the `milp` extra is installed and Gurobi accepts the model; otherwise it skips with the
Gurobi error text.

For the three modules built for this release:

`tests/test_sysml2uppaal.py` translates the mk6 model and checks it against what the model
actually contains — the five locations and five transitions, `current_soc < 60` from the
ChangeEvent body, `gt >= 3600` and `t >= 1200` with the `t <= 1200` invariant from the two
TimeEvents, the entry assignment on every edge into `Operational`, all 23 requirements with
P.1.4's verbatim text, the two requirement-derived queries, and the four warnings. It also
asserts the source `.mdzip`'s md5 is unchanged after the translation, walks the written NTA to
check every edge endpoint resolves to a location of its own template, and loads a copy in
`pyuppaal.UModel`.

`tests/test_campaign_stats.py` checks the Clopper-Pearson endpoints against their defining
binomial tail probabilities with `scipy.stats.binom` as an independent oracle (rather than
against the same Beta call that computes them), and compares Clopper-Pearson with Wilson on
**coverage**, which is the property that separates them: at n = 20, δ = 0.05 the exact interval's
worst-case coverage over p is 0.958 and Wilson's is 0.8605. It also pins the one place the
ordering reverses — at k = 0 and large n the Wilson upper endpoint (≈ z²/n = 3.8415/n) overtakes
the exact one (≈ ln(2/δ)/n = 3.6889/n) — and checks `trials_for_upper_bound` really returns the
smallest n. The adapter is exercised against a temporary SQLite database built from PERFECT's own
`CREATE TABLE` text, with the pipe-joined `TrialState` strings, a NULL state and NULL times, and
against `perfect/examples/dummy/dummy.db` when it is present.

`tests/test_stl_observer.py` replays the synthetic scenario through the shipped spec and compares
each monitor's robustness against a closed-form oracle for its operator: `historically (x >= c)`
is the running minimum of x − c and `once[0,T] (x >= c)` over a window longer than the trace is
the running maximum. It pins the crossing sample exactly (the state of charge is 0.6 at t = 20.0
with robustness 0, and the first negative sample is t = 20.1), checks that a missing signal is
reported rather than guessed, and checks the warmup gate.

## What was checked, and how

The gate output for the packaging run of 2026-09-22 is in
`analysis-scratch/packaging/B-gate.txt`, and for the three modules built for this release in
`analysis-scratch/packaging/B2-gate.txt` (both untracked). In summary:

| check | result |
|---|---|
| `uv venv --python 3.10 && uv sync` | 12 packages installed, exit 0 |
| `pytest tests/test_bt2automata.py tests/test_tbt_monitor.py` | 4 passed in 0.26 s |
| `demo.py` output vs the upstream script's output | byte-identical, md5 `9f1da760f65674818d156546092e6118` |
| `demo_synthetic.py` | final `(rho, state)` = `(0.012, 1)` and `(-0.03, 0)` for the two traces |
| `uv sync --extra rl` then `main.py --n-rollouts 2 --no-video` | ran headless in 14.0 s, printed `Success Rate: 1.0` |
| `pytest tests/test_ltbt.py` with the `milp` extra | 2 passed; the n=5 solve returned status OPTIMAL |
| `robot.py` unmodified at N=15 | refused: "Model too large for size-limited license" — needs a full Gurobi license |
| `plot.py` on the shipped `robot/` solutions | wrote a 1-page 166 KB PDF, the same size as the upstream figure |
| the two UPPAAL queries | **not checked**: no UPPAAL on the machine that ran the gates |
| `uv add scipy pyyaml` | scipy 1.15.3 and PyYAML 6.0.3 added to the base dependencies |
| `pytest -q` over the whole suite | 32 passed, 1 skipped (the Gurobi one) in 0.89 s |
| `demo_battery.py` | 2 templates, 9 locations, 9 edges, 12 queries, 4 warnings; `pyuppaal.UModel` parsed the copy back with the same templates and 12 queries |
| the `battery_sm.xml` queries | **not checked**: still no UPPAAL |
| `demo_campaign.py` | dummy DB: 1 trial, 0 failures, exact upper bound 0.95, 59 trials needed for 0.05. Synthetic: 17/200 failures, rate 0.085, exact [0.0503, 0.1326] containing the true 0.10565 |
| `stl_observer_node.py` + `test_publisher.py` on ROS 2 Jazzy, domain 87 | the observer logged `VIOLATION soc_safety [P.1.4] at t=19.9s robustness -0.0015`; the robustness topic ran 0.0045, 0.0030, 0.0015, 0.0000, −0.0015 through the crossing and the violation topic flipped false → true on the same sample |
| the observer's topic graph | all six `/veritas/<monitor>/{robustness,violation}` topics present alongside the three input topics |
| `goal_liveness` live | robustness −0.5 for 56 samples then +0.5 for 75, and no violation reported, because its warmup is 180 s |
