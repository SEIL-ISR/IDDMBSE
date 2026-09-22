# VERITAS module notes

The full walk-through of each module and of the test suite, kept beside the
[README](../README.md), which carries the summaries, the result tables and the commands. Paths
are relative to `veritas/`; the commands run from there.

## 1. SysML to UPPAAL — `formal/sysml2uppaal/`

```
uv run python formal/sysml2uppaal/demo_battery.py
```

Reads `sysml/models/AGR_stack-MB-SensorTrade-mk6.mdzip` (read-only; the demo checks the file's
md5 is unchanged), translates its one state machine and the small `Demo AD` activity, and
writes `battery_sm.xml` next to the script.

**What it reads.** MagicDraw writes UML 2.5 XMI inside the `.mdzip`, in the zip member
`com.nomagic.magicdraw.uml_model.model`. In that dialect the XML tag is the element's *role*
(`packagedElement`, `ownedBehavior`, `region`, `subvertex`, `transition`, `node`, `edge`) and
the metaclass is the attribute `xmi:type`, so a state machine is `<ownedBehavior
xmi:type='uml:StateMachine'>`, never `<uml:StateMachine>`. Requirements are the exception: they
are stereotype applications literally tagged `<sysml:Requirement Id='…' Text='…'
base_Class='…'/>`, with `Id` and `Text` as attributes. A transition's condition lives on its
`trigger`'s event, which is a top-level `uml:ChangeEvent` (`changeExpression > body`) or a
`uml:TimeEvent` (`when > expr @value`).

**The supported fragment.** Conditions and effects of the form `var OP const`, with `OP` one of
`< <= > >= == != =` and `const` a decimal number, plus `&&`-joined conjunctions of those.
UPPAAL has no reals, so a real variable is scaled to an integer by a documented factor (default
100) and declared `int`: `current_soc < 0.6` becomes `current_soc < 60`. Each template gets a
local `clock t`, reset on every edge, so `t` is the time spent in the current location; the
network shares one `clock gt` that is never reset. A TimeEvent with `isRelative='true'` and
value V becomes the guard `t >= V`, and the source location gets the invariant `t <= V` when
*all* its outgoing edges are relative TimeEvents, which is UML's `after(V)`. A TimeEvent
without `isRelative` becomes `gt >= V`. Entry behaviours become assignments on every edge
entering the state. Anything outside the fragment is copied into an UPPAAL `comments` label and
reported as a warning.

**What it produces on the mk6 model.** One template `ee_hv_battery_charge_discharge` with five
locations (`Pseudostate`, `Operational`, `Enter_Power_Saving_Mode`, `Charging` with the
invariant `t <= 1200`, `Quick_Charge_Complete`) and five edges, and one template `Demo_AD` with
four locations and four edges — 2 templates, 9 locations, 9 edges and 12 queries in all, with
four warnings, all of them about the source model rather than the translator:

* the initial `uml:Pseudostate` has no `kind` attribute, so it is read as `initial`, the UML default;
* the `doActivity` of `Quick Charge Complete` (`current_soc=0.7`) is applied once on entry, because a timed automaton has no do-while-in-state behaviour;
* the TimeEvent on `Enter Power Saving Mode -> Charging` has no `isRelative`, so its 3600 is read as an absolute time on `gt`, which UPPAAL cannot bound from above;
* the transition `Quick Charge Complete -> Operational` carries the informal label `when (current_soc=0.7) && after(100)` in its `name` attribute, and only its structured trigger (the ChangeEvent half) is translated — the `after(100)` has no `uml:TimeEvent` behind it in the model.

Translating all three activities instead of just `Demo AD` adds twelve more warnings: nine
`ForkNode`s and one `JoinNode` in `Perception Module Activity Diagram` become ordinary
locations, so their branches read as a nondeterministic choice rather than as concurrency; nine
of its object flows start or end on a pin and are lifted to the owning action; and `Sensor
Suite` has no nodes at all and is skipped.

**The two proof obligations.** The model carries a free-text OpaqueExpression rather than a
structured satisfy/verify link between a requirement and a state-machine variable, so the demo
supplies the binding explicitly as an alias table, and of the 23 requirements in the model only
those whose `Text` matches one of those phrases become queries:

```
A[] current_soc > 60    // P.1.4 AGR Battery State of Charge: "The AGR Battery State of Charge
                        //   during operation shall always be more than 0.6."
A[] gt < 180            // P.1.2 Time to Completion: "The AGR shall complete the entire path in
                        //   the test environments in less than 180 seconds."
```

plus `A[] not deadlock` and one `E<> …` reachability query per location. Section 3 below is
what UPPAAL says about them.

One trap: `pyuppaal` 1.2.0 **rewrites the file you point it at** — `UModel.__init__`
round-trips the XML back to disk, which drops the DOCTYPE line and the `<comment>` text of
every query. The demo and the test therefore load a *copy*, so `battery_sm.xml` stays as the
translator wrote it.

The translator is also a command-line tool for any other model:

```
uv run python formal/sysml2uppaal/sysml2uppaal.py model.mdzip out.xml --scale 100
```

## 2. Behavior tree to UPPAAL — `formal/bt2automata/`

```
uv run python formal/bt2automata/demo.py
```

Composes the behavior tree of the BT2Automata paper's §6.1 example — `Sequence(FA,
Sequence(Selector(CBatt, FCharger), FB))`, read as *go to A; if the battery is low go to the
charger first; then go to B* — from the leaf automata in `leaf_node_templates.xml`, and writes
`BT_converted.xml` next to the script. The composition follows Alg. 1 of the paper and its
complement for selectors; `bt2ta/bt2ta.py` also carries the parallel composition (Alg. 2), the
`Eventually`/`Always`/`Condition` leaf constructors and a grid-world transition-system
generator.

The written model is a UPPAAL NTA with three templates — `BT` (the composed tree, with the
`Success` and `Failure` locations), `Battery` and `Grid` — instantiated as `spec=BT(20)`,
`battery=Battery(75)`, `grid=Grid()`, and carries two queries:

```
E<> spec.Success
E<> spec.Failure
```

The file is the upstream script's output plus one line: the flat-system 1.1 DOCTYPE
declaration, which pyuppaal's writer leaves out and which the demo puts back, so both models in
`formal/` declare the same DTD. Its md5 is `96b2e35c435ce771191351242e29cb77`, and
`9f1da760f65674818d156546092e6118` with that one line removed, which is the upstream output
byte for byte.

## 3. Checking the models — `formal/verify.py`

```
export UPPAAL_HOME=/path/to/your/uppaal
uv run python formal/verify.py formal/sysml2uppaal/battery_sm.xml formal/bt2automata/BT_converted.xml
```

The driver reads each model's `<queries>` block, writes it beside the model as a `.q` file (one
formula per line, each query's comment above it as `//` lines), finds `verifyta` —
`--verifyta`, then `$UPPAAL_HOME/bin-Linux/verifyta` (4.1's layout), then
`$UPPAAL_HOME/bin/verifyta` (5.x's), then `PATH` — runs `verifyta -t0 MODEL QUERIES`, parses
the per-query verdict lines, and writes `verification_report.json` and
`verification_report.md` with the version string, the wall time and one row per query. `-t0` is
the `--diagnostic` option with argument 0, so a failing query comes back with a trace. UPPAAL
5.x also reads the queries out of the model itself; `--embedded-queries` asks for that and
gives the same verdicts. With no UPPAAL on the machine the driver prints one line saying to set
`UPPAAL_HOME` and exits 2.

UPPAAL is free for non-commercial academic use and is downloaded separately: get it from
<https://uppaal.org/downloads/> and register for an academic key at
<https://uppaal.veriaal.dk/>.

**What UPPAAL 5.0.0 printed here.** Both models, one driver run each, `verifyta -t0` with the
extracted query file: 12 queries on the battery model in 0.02 s, 2 queries on the behavior-tree
model in 0.28 s.

| # | query | requirement | verdict |
|---|---|---|---|
| 1 | `A[] gt < 180` | P.1.2 Time to Completion | not satisfied |
| 2 | `A[] current_soc > 60` | P.1.4 AGR Battery State of Charge | satisfied |
| 3 | `A[] not deadlock` | structural | satisfied |
| 4 | `E<> ee_hv_battery_charge_discharge_p.Pseudostate` | reachability | satisfied |
| 5 | `E<> ee_hv_battery_charge_discharge_p.Operational` | reachability | satisfied |
| 6 | `E<> ee_hv_battery_charge_discharge_p.Enter_Power_Saving_Mode` | reachability | not satisfied |
| 7 | `E<> ee_hv_battery_charge_discharge_p.Charging` | reachability | not satisfied |
| 8 | `E<> ee_hv_battery_charge_discharge_p.Quick_Charge_Complete` | reachability | not satisfied |
| 9 | `E<> demo_ad_p.InitialNode` | reachability | satisfied |
| 10 | `E<> demo_ad_p.Opaque_Action_Matlab_Script` | reachability | satisfied |
| 11 | `E<> demo_ad_p.Opaque_Action_Python_Script` | reachability | satisfied |
| 12 | `E<> demo_ad_p.MergeNode` | reachability | satisfied |

and on `BT_converted.xml`, `E<> spec.Success` satisfied and `E<> spec.Failure` satisfied —
the first witnesses a trace in which the robot completes the task, the second a trace in which
it does not, which is what the upstream comment says the two queries demonstrate.

What that table says about the SysML model is the point of the exercise. **P.1.4 holds for an
uninteresting reason**: the only assignments to `current_soc` set it to 70, and the only guard
that would leave `Operational` needs `current_soc < 60`, so nothing in the authored state
machine ever lowers the state of charge and the safety property holds vacuously. Queries 6, 7
and 8 are the same finding seen from the other side: the three states behind that guard —
`Enter_Power_Saving_Mode`, `Charging`, `Quick_Charge_Complete` — are unreachable, so the
battery discharge the diagram draws is never exercised. **P.1.2 fails** because the battery
machine has no notion of completing a path: `gt` runs on without bound, and UPPAAL returns the
trace that delays 180 time units in the initial state. The query is there to show that a
time-bounded requirement maps onto `gt` rather than onto a scaled integer.

## 4. Failure rates and confidence bounds over a PERFECT campaign — `datadriven/`

```
uv run python datadriven/demo_campaign.py
uv run python datadriven/report.py --db datadriven/demo_out/campaign.db --out datadriven/demo_out
```

The data-driven module estimates failure rates and confidence bounds for the parts of the
system where formal models are intractable. `campaign_stats.py` is that estimation,
`perfect_adapter.py` gets the campaign out of PERFECT, `demo_campaign.py` runs both on
PERFECT's own dummy example and on seeded synthetic campaigns, and `report.py` is the tool you
point at a campaign database of your own.

**Reading a campaign.** `perfect_adapter.read_campaign(db)` opens PERFECT's SQLite file
read-only (`file:…?mode=ro`) and joins `trial` to `experiment` to `design` and `environment`.
Three things about that schema are worth knowing because they are not what you would guess:

* `trial.state` is a **plain string column**, not an enum column. `TrialState` in
  `perfect/perfect/experiment/experiment.py` is an `enum.Flag`, the runner sends the integer
  bitmask, and `perfect/perfect/app/tasks.py` stores `str(TrialState(mask))` — Python's
  `Flag.__str__`, which pipe-joins the member names. A finished successful trial therefore
  reads `TrialState.SUCCESSFUL|SHUT_DOWN`, and a trial counts as a success exactly when
  `SUCCESSFUL` is one of the joined members.
* the two time columns are `start_age` (wall-clock seconds the trial ran) and `sim_time`
  (simulated seconds off the `/clock` topic, which is NULL in the dummy example). The adapter
  returns both, with NULL as `nan` rather than 0.
* any other per-trial number the runner reports arrives as a row of the `update` table, one
  JSON payload each (`{"update": <name>, "trial_id": n, "data": <value>}`).
  `read_metric(db, trial_ids, name)` pulls one named number back out of that stream, taking the
  last payload of each trial and `nan` where a trial has none.

`read_campaign_csv` is the fallback for a campaign exported to CSV rather than read live.

**The statistics.** `failure_rate` is the point estimate; `clopper_pearson` is the exact
interval (it inverts the binomial tails through the Beta quantile, so its coverage is at least
1 − δ for every true p) and `clopper_pearson_upper` its one-sided form, which is the number a
safety case wants; `wilson` is the score interval, narrower and only asymptotically covering.
`trials_for_upper_bound(target, delta, failures)` is the campaign-size design: the smallest n
whose exact upper bound reaches `target` if the campaign ends with that many failures — at zero
failures it is the closed form n = ln δ / ln(1 − target). `robustness_stats` summarises
post-hoc STL robustness over the recorded trajectories: mean, min, the empirical violation
fraction, the empirical lower quantile, and a distribution-free (DKW) correction of that
quantile, which is −inf and says so while the campaign is too small for the band to be narrower
than the quantile level. Everything is whole-array numpy: the bound functions broadcast over
arrays of k and n, and `robustness_stats_by_group` and `trials_for_upper_bound_array` evaluate
a whole campaign's groups in one pass.

**What the demo prints.** On `perfect/examples/dummy/dummy.db` — one trial, state
`TrialState.SUCCESSFUL|SHUT_DOWN`, `start_age` 15.025 s — the table is degenerate and the point
of printing it is to show how little one trial buys: failure rate 0, but the exact upper bound
is 1 − 0.05^(1/1) = 0.95, and it takes 59 zero-failure trials before that bound reaches 0.05.
On the synthetic campaign of 200 trials (each draws a robustness from N(0.15, 0.12) and fails
exactly when it is negative, so the true failure probability is Φ(−1.25) = 0.10565) the
estimate is 0.085 from 17 failures, with the exact interval [0.0503, 0.1326], which contains
the truth, and the Wilson interval [0.0537, 0.1319] inside it. The same campaign at 2000 trials
gives 204 failures, rate 0.102, exact [0.0891, 0.1161], and is where the DKW band finally
becomes narrower than a 5% quantile level (it takes 738 trials): the empirical 5% quantile of
the robustness is −0.0526 and its DKW-corrected value −0.1133.

The demo then writes `datadriven/demo_out/campaign.db`, a campaign in PERFECT's own schema —
two designs across two environments, 60 trials each, 240 trials and 12 failures in all, every
trial carrying a robustness update — so that `report.py` can be exercised on the same code path
it takes on a database a real campaign left behind.

**The report tool.** `report.py --db <database>` (or `--csv <export>`) groups the trials by
design and environment and writes `report.json`, `report.md`, `report.csv` and the figure pair
`failure_rates.svg` / `failure_rates.pdf` — the failure rate per group with its exact and
Wilson intervals and the target line. On the demo campaign:

| design | environment | trials | failures | rate | exact interval | exact upper | trials for 0.05 |
|---|---|---|---|---|---|---|---|
| AGR + A-star | range dense | 60 | 3 | 0.05 | [0.0104, 0.1392] | 0.1242 | 153 |
| AGR + A-star | range sparse | 60 | 1 | 0.0167 | [0.0004, 0.0894] | 0.0766 | 93 |
| AGR + Dijkstra | range dense | 60 | 6 | 0.1 | [0.0376, 0.2051] | 0.1879 | 234 |
| AGR + Dijkstra | range sparse | 60 | 2 | 0.0333 | [0.0041, 0.1153] | 0.1012 | 124 |

with the robustness table beside it (mean 0.2037 / 0.2996 / 0.1295 / 0.2262 per group, 5%
quantiles 0.0403 / 0.1026 / −0.0123 / 0.0237, and the DKW correction reporting −inf at 60
trials per group, which is the honest answer at that campaign size). On PERFECT's dummy
database the same command reports its one group: 1 trial, 0 failures, exact [0.0, 0.975], upper
bound 0.95, 59 trials to reach the 0.05 target.

## 5. The STL observer — `runtime/stl-observer/`

The runtime module synthesizes observers, expressed as Signal Temporal Logic (STL) or Metric
Interval Temporal Logic (MITL) monitors, that watch the deployed stack and raise alarms on
specification violations; its front end is a **generic subscriber**, one node that discovers
and subscribes to topics without being recompiled for each one. That is what
`stl_observer_node.py` is. The message type is a string in the YAML spec, resolved at run time
with `rosidl_runtime_py.utilities.get_message`, so adding a signal on a new topic of a new type
is an edit to the YAML and nothing else.

**The live spec.** `specs/agr_safety.yaml` carries three obligations. Two come from
requirements in `sysml/models/AGR_stack-MB-SensorTrade-mk6.mdzip`, quoted verbatim in the file:

| monitor | requirement | formula | signal |
|---|---|---|---|
| `soc_safety` | P.1.4, "…state of charge…shall always be more than 0.6" | `historically (soc >= 0.6)` | `/battery_state` `sensor_msgs/msg/BatteryState.percentage` |
| `goal_liveness` | P.1.2, "…shall complete the entire path…in less than 180 seconds" | `once[0,180] (goal >= 0.5)` | `/goal_reached` `std_msgs/msg/Bool.data` |
| `obstacle_safety` | a local safety obligation | `historically (obstacle_distance >= 0.5)` | `/obstacle_distance` `std_msgs/msg/Float64.data` |

RTAMT's online monitor implements past-time operators, so a safety obligation is written
directly as `historically (p)` and a bounded-future one as `always[0,T] (p)` or
`eventually[0,T] (p)` with `pastify: true`, which RTAMT rewrites into the past. Interval bounds
are in **seconds** and must be a whole number of sampling periods: the period is handed to
RTAMT, so `once[0,180]` at 10 Hz really means the last 180 seconds. A field path is dotted
(`percentage`, `pose.position.x`, `ranges.0`) and the value is cast to float, which turns a
Bool field into 1.0 / 0.0 — a predicate over the real signal (`goal >= 0.5`) standing for the
Boolean. `warmup` holds the violation flag down for the first N seconds, which is what keeps
`goal_liveness` from reporting a violation simply because the run has only just started.

**The node** publishes `std_msgs/Float64` on `/veritas/<monitor>/robustness` and
`std_msgs/Bool` on `/veritas/<monitor>/violation`, samples every signal at the spec's `rate`
with a zero-order hold between messages, starts a monitor once all of its signals have arrived
at least once, and logs a warning on every entry into and exit from violation.

**Running it.** The node needs `rclpy`, so it runs in ROS's Python, not in this venv. RTAMT is
in this venv rather than ROS's; install it into a directory of your own and put that on
`PYTHONPATH` (never into the system Python or into `/opt/ros`):

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

Pick a `ROS_DOMAIN_ID` nobody else on the machine is using; the domain and RMW above are what
the run recorded below used, to keep its graph off the shared one.

**What that run printed.** On ROS 2 Jazzy, domain 87, the observer logged `VIOLATION
soc_safety [P.1.4] at t=19.9s robustness -0.0015`; the robustness topic ran 0.0045, 0.0030,
0.0015, 0.0000, −0.0015 through the crossing and the violation topic flipped false → true on
the same sample. All six `/veritas/<monitor>/{robustness,violation}` topics were on the graph
beside the three input topics. `goal_liveness` published −0.5 for 56 samples and then +0.5 for
75, and reported no violation, because its warmup is 180 s.

**Replaying instead.** `replay_observer.py` runs the same `Monitor` objects over a recorded
CSV, entirely inside this venv with no ROS. The CSV needs a time column (`time` or `t`) and one
column per signal; the trace is sampled onto the spec's rate, each step taking the nearest
recorded sample, so a trace recorded at one rate and a spec written at another agree on what a
bound of "20 seconds" means.

```
uv run python runtime/stl-observer/replay_observer.py trace.csv --spec runtime/stl-observer/specs/agr_safety.yaml
```

**The range spec.** `specs/range_safety.yaml` is written against the trajectory CSV the Isaac
Sim range trial writes, whose header is `t,x,y,z,roll,pitch,yaw,v` — the pose in metres and
radians, the speed in m/s, one row per physics step at 60 Hz. It samples at 20 Hz (RTAMT wants
the operator bound to be a whole number of periods, and 50 ms divides 20 s) and carries three
obligations: `historically (abs(roll) <= 0.35)` and `historically (abs(pitch) <= 0.35)`, the
0.35 rad being 20 degrees of tilt, beyond which a ground vehicle of this class is at risk of
sliding or rolling over; and `eventually[0,20] (v >= 0.2)` with a 20 s warmup, the progress
obligation — the range trial commands 0.6 m/s, so a robot that never reaches a third of that
inside 20 seconds is stuck on an obstacle rather than driving.

`demo_range_trace.py` writes a trajectory in that format to run the spec against: 3600 rows at
60 Hz over 60 simulated seconds, driving at 0.6 m/s, crossing a slope that tilts it to 0.4024
rad in pitch at about 22 s, then sitting at 0.02 m/s from 25 s to 50 s.

```
uv run python runtime/stl-observer/demo_range_trace.py
uv run python runtime/stl-observer/replay_observer.py \
    runtime/stl-observer/demo_out/range_trajectory.csv \
    --spec runtime/stl-observer/specs/range_safety.yaml --every 200
```

Over that trace's 1200 monitor samples the three verdicts are: `roll_safety` holds throughout,
its robustness settling at 0.2; `pitch_safety` first violated at sample 429, monitor time
21.45 s, robustness −0.0006 and then −0.0522 for the rest of the run; and `progress` first
violated at sample 900, monitor time 45.0 s, robustness −0.18 — exactly 20 seconds, one window,
after the robot stopped, recovering to 0.4 when it moves again at 50 s.

## 6. Behavior-tree runtime monitor — `runtime/tbt-monitor/`

```
uv run python runtime/tbt-monitor/demo_synthetic.py
```

Runs the monitor on a hand-made pick-and-place trace, so it needs only the base install — no
torch, no simulator, no display. The behavior tree is `Sequence(reach object, grasp, reach
goal)`; the leaf specifications are `eventually(d2obj < 0.1)`, `eventually(gripper width <
0.05)` and `eventually(d2goal < 0.05)`, each evaluated by RTAMT over the signal window since
the previous leaf succeeded. The demo prints `(rho, state)` at every step, for two traces:

* a trace that reaches, grasps and places, which ends at `state 1` (success) with `rho 0.012`;
* a trace whose gripper never closes, which stays at `state 0` for the whole episode with
  `rho -0.03` (the grasp margin, 0.05 − 0.08).

The second trace reports *running* rather than failure, and that is the semantics: `get_status`
in `panda_specifications.py` maps a robustness to 1 if positive and 0 otherwise, so a leaf here
returns 0 while it is unsatisfied, and −1 is the only value that drives `compose_seq` to a
failure verdict. A leaf that has not yet been satisfied is running, i.e. the verdict is still
unknown.

The RL rollout the OMTBT paper reports is `main.py`. It needs the `rl` extra:

```
uv sync --extra rl
uv run python runtime/tbt-monitor/main.py --n-rollouts 2 --no-video
```

It loads the trained TQC policy `tqc_pandp.zip` (24 MB), wraps `PandaPickAndPlaceDense-v3` in a
wrapper whose `step()` returns the monitor's robustness **as the reward**, and rolls out
episodes — inference-time substitution on an already-trained policy. Here it ran headless in
14.0 s and printed `Success Rate: 1.0`. Drop `--no-video` to record episode videos into
`runtime/tbt-monitor/videos/` and write slow-motion copies with moviepy. Note that the
`Success Rate` it prints sums `info['is_success']` over every simulation step and divides by
the number of episodes, so it is not the fraction of successful episodes.

## 7. MILP synthesis from temporal behavior trees — `synthesis/ltbt/`

```
uv sync --extra milp
cd synthesis/ltbt && uv run python robot.py
```

`ltbt/boolean.py` is the two-valued encoding and `ltbt/ternary.py` the three-valued (Kleene)
one, both building a semantics tree — linear predicates, box constraints, `Not`/`Or`/`And`,
`Always`/`Eventually`, `Sequence`/`Selector` — out of gurobipy indicator constraints, with one
upper-triangular satisfaction variable block per node. `robot.py` (N=15) and `robot2.py` (N=20)
synthesise a trajectory for one double-integrator robot against `Sequence(ebox1, Selector(Batt,
ebox3), ebox2)`, minimising control effort; `multiagent.py` (N=30) and `multiagent2.py` (N=20)
do three double integrators against a shared `Sequence(Eventually(box1), Eventually(box2))`
with big-M halfspace obstacle avoidance and pairwise collision avoidance. `plot.py`, `plot2.py`
and `plot3.py` are the figure scripts.

These scripts need a full Gurobi license; they exceed the size-limited license that ships with
pip `gurobipy` (`robot.py` is 4190 variables and 2292 constraints, and a quadratic objective
caps that license at 200 variables). Runtimes recorded in the upstream solver logs, on the
author's machine: 22.96 s and objective 1.1243 for `robot2.py` (341 rows by 2888 columns), and
309.42 s (objective 7.9662) and 790.00 s (objective 12.3665) for two multi-agent runs of 901
rows by 2394 columns.

`robot.py` writes `robot/{x,u,z}.npy` and `test.png` into `synthesis/ltbt/`; the
`robot/{true,false,true_tern,false_tern}/` directories hold the author's saved solutions, which
is what `plot.py` reads — run here, it wrote a 1-page 166 KB PDF, the same size as the upstream
figure. `plot2.py` and `plot3.py` read `multiagent/x.npy`; regenerate it with `multiagent2.py`
first.

The `ltbt` repository carries no README and names no paper. The manuscript's bibliography has
an entry that matches its content closely — Matheu, Baras and Belta, *Ternary Logic Encodings
of Temporal Behavior Trees with Application to Control Synthesis*, arXiv:2604.12092, 2026 — so
that is most likely its companion paper.

## What each test checks

`tests/test_bt2automata.py` runs the demo into a temporary directory and checks that the
written file carries the flat-1.1 DOCTYPE and parses as an NTA with the three expected
templates and both queries.

`tests/test_verify.py` exercises the driver end to end against `tests/fake_verifyta.py`, a stub
that writes the same shape of output and decides verdicts by a trivial rule, so extraction,
invocation, parsing and the report are covered with no UPPAAL on the machine: the four-query
toy model comes back satisfied / not satisfied / may be satisfied / satisfied, and the
behavior-tree model generated by the demo comes back with both its queries. The parser is
checked separately on output captured from UPPAAL 5.0.0 — including the erase-line escape its
progress indicator leaves in front of each verdict — and on the 4.x shape reproduced in
pyuppaal's own wrapper. The lookup order and the exit-2 path are tested too.

`tests/test_tbt_monitor.py` checks the monitor's verdicts on the two synthetic traces; the
docstring quotes the vendored lines each expectation is read off. `tests/test_ltbt.py` checks
the three-valued constants, and solves a five-step double-integrator problem when the `milp`
extra is installed and Gurobi accepts the model; otherwise it skips with the Gurobi error text.

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
**coverage**, which is the property that separates them: at n = 20, δ = 0.05 the exact
interval's worst-case coverage over p is 0.958 and Wilson's is 0.8605. It also pins the one
place the ordering reverses — at k = 0 and large n the Wilson upper endpoint (≈ z²/n =
3.8415/n) overtakes the exact one (≈ ln(2/δ)/n = 3.6889/n) — and checks
`trials_for_upper_bound` really returns the smallest n. The adapter is exercised against a
temporary SQLite database built from PERFECT's own `CREATE TABLE` text, with the pipe-joined
`TrialState` strings, a NULL state and NULL times, and against `perfect/examples/dummy/dummy.db`
when it is present.

`tests/test_report.py` builds a four-group campaign database in PERFECT's schema with a
robustness payload per trial and checks the grouped numbers against the single-campaign report
run on each group by hand, the exact interval against `scipy.stats.binom`, and the vectorised
trials-needed table against the scalar function it replaces; it also covers a trial with no
payload, a database with no `update` table, empty and single-trial groups, and the four output
files plus the figure pair.

`tests/test_stl_observer.py` replays the synthetic scenario through the shipped live spec and
compares each monitor's robustness against a closed-form oracle for its operator: `historically
(x >= c)` is the running minimum of x − c and `once[0,T] (x >= c)` over a window longer than
the trace is the running maximum. It pins the crossing sample exactly (the state of charge is
0.6 at t = 20.0 with robustness 0, and the first negative sample is t = 20.1), checks that a
missing signal is reported rather than guessed, and checks the warmup gate. The range spec gets
the same treatment over a 60 Hz trajectory in the range trial's column order: the 3:1
resampling onto the spec's 20 Hz, the two attitude obligations against the running minimum of
their margin, and the progress obligation firing one 20 s window after the robot stops.

## The behavior-tree animation

`formal/animations/bt_to_automaton.mp4` is 25 s at 1920 x 1080 and 24 fps; the GIF above is
the same at 640 px and 12 fps, and `bt_to_automaton_poster.{svg,pdf}` is the end of its first
scene. The first scene draws the demo tree `Sequence(FA, Sequence(Selector(CBatt, FCharger),
FB))` node by node, then the network `demo.py` composes from it, template by template and
location by location: `BT` (`spec = BT(20)`, 6 locations with `Success`, `Failure` and one
urgent location, 11 edges), `Battery` (`battery = Battery(75)`, 2 locations, 3 edges) and `Grid`
(`grid = Grid()`, 86 locations on a 10 x 10 grid, 362 edges of which 86 are self-loops and are
left out of the drawing; the cells `A`, `B` and `Charger` are the targets of the edges that set
those flags). It ends with `E<> spec.Success` and `E<> spec.Failure`, both satisfied. The second
scene draws the two templates `sysml2uppaal` writes for the battery state machine and the
`Demo AD` activity, then lists the twelve queries of the verdict table in section 3 one by one with their
verdicts; each reachability verdict colours its location, so `Enter_Power_Saving_Mode`,
`Charging` and `Quick_Charge_Complete` turn red and the other six locations green.

Both models are regenerated into a temporary directory by the tools themselves: `demo.py`, and
`sysml2uppaal.translate` with `demo_battery.py`'s arguments. `formal/animations/nta_layout.py`
reads each model's XML; `BT`, `Battery` and the two SysML templates are laid out by Graphviz
`dot` (its JSON output gives the location, name, spline and label positions), and `Grid` is
drawn at the coordinates its XML carries. The verdicts come from a live `verifyta` run through
`verify.py` when it finds one, and otherwise from `formal/animations/uppaal_verdicts.json`,
which `--record-verdicts` wrote from such a run. The render here used the live run, UPPAAL
5.0.0 (rev. 714BA9DB36F49691); its verdicts are the ones listed above.
