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

This directory is the behavior-tree half of that. It ships three code bases, vendored from two of
the coauthor's research repositories at pinned commits (see `ATTRIBUTION.md`).

| module in the paper | what ships here | what it does |
|---|---|---|
| model-based | `formal/bt2automata/` | composes a behavior tree into a UPPAAL network of timed automata, for model checking and control synthesis in the UPPAAL GUI |
| runtime | `runtime/tbt-monitor/` | greedy online monitor for a behavior tree, with RTAMT STL leaf specifications; returns a quantitative robustness and a three-valued node state at every step |
| data-driven | — | nothing ships here yet |
| (control synthesis, not one of the three modules) | `synthesis/ltbt/` | three-valued (Kleene) encodings of temporal behavior trees as Gurobi MILP constraints, and trajectory-synthesis scripts built on them |

## Install

This is a self-contained uv project on Python 3.10 (the upstream pins need it).

```
cd veritas
uv venv --python 3.10
uv sync
```

Two optional extras, neither needed for the two default demos:

```
uv sync --extra rl      # torch, stable-baselines3, panda-gym — for the RL rollout
uv sync --extra milp    # gurobipy, scipy, matplotlib — for the synthesis scripts
```

`uv sync` makes the environment exact, so the two extras replace each other unless you ask for
both at once (`uv sync --extra rl --extra milp`).

**If you have a ROS 2 environment sourced**, `PYTHONPATH` points at ROS's `site-packages`, pytest
autoloads ROS's `launch_testing` plugin into this Python 3.10 venv and the run dies with
`ModuleNotFoundError: No module named 'yaml'`. Prefix the commands with `env -u PYTHONPATH`, or
open a shell with ROS not sourced. Nothing here needs ROS.

## Demos

### 1. Behavior tree to UPPAAL — `formal/bt2automata/`

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

### 2. Behavior-tree runtime monitor — `runtime/tbt-monitor/`

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

### 3. MILP synthesis from temporal behavior trees — `synthesis/ltbt/`

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

* **The SysML → UPPAAL compiler.** The paper's model-based module compiles SysML state-machine and
  activity diagrams into timed automata; only the behavior-tree front end exists here.
* **The generic subscriber.** Not in this directory and not needed by any demo here.
* **BagWorld.** Not in this directory and not needed by any demo here.
* **The data-driven module.** Estimating failure rates and confidence bounds from PERFECT
  campaigns has no code in this repository yet.
* **The multi-robot STL/MILP demo of the paper.** The paper's released demonstration has three
  per-robot reach-avoid specifications φ1, φ2, φ3, STL robustness scored per executed trajectory
  (ρ = 0.199, −0.04, 0.999) and written back into the SysML block. The `multiagent*.py` scripts
  here solve a different problem — three agents against one shared two-box sequence spec, with no
  robustness scoring and no model write-back.
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

## What was checked, and how

The gate output for the packaging run of 2026-09-22 is in
`analysis-scratch/packaging/B-gate.txt` (untracked). In summary:

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
