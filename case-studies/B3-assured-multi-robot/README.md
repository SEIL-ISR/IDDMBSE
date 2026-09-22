# B3 — Assured multi-robot coordination

This directory implements Section IV-B.3 of the IDDMBSE paper as a self-contained
simulation: a three-robot indoor team whose fleet requirement is decomposed into per-robot
missions, allocated onto structural AGR blocks, parsed into reach-avoid STL
specifications, synthesised as one joint Mixed-Integer Linear Program, executed, scored
by VERITAS with the quantitative STL robustness, and written back into the model. The map,
the missions, the timing windows and the noise model below are its own. `dump/ltbt` solves
a different problem (three agents against one shared spec, no robustness scoring, no
write-back) and needs Gurobi; this directory uses HiGHS and its own encoding.

## The chain, end to end

| step | what happens | where it lives |
|---|---|---|
| 1. decompose | one fleet requirement becomes three quantitative per-robot missions with stations and time windows | `model/fleet_requirements.yaml` |
| 2. allocate | each mission is tied by a satisfy relation to a structural AGR block | `model/agr_fleet.yaml` |
| 3. parse | each mission becomes a reach-avoid STL formula phi_1, phi_2, phi_3 | `specs.load_fleet` |
| 4. synthesise | the three formulas plus the linearised dynamics become one MILP, solved with HiGHS | `encode.py`, `synth.py` |
| 5. execute | the plan is tracked with bounded process noise, so the executed trace is not the plan | `execute.py` |
| 6. score | VERITAS computes the quantitative STL robustness rho of each executed trace | `robustness.py` |
| 7. write back | rho becomes the goal-satisfaction value of the AGR block | `writeback.py`, `model/agr_fleet.yaml` |
| 8. hand off | the plan is exported as `nav_msgs/msg/Path` for Nav2 | `ros_export.py`, `results/robot_*_path.yaml` |

`run_case_study.py` runs all eight in order, seeded.

## The specifications

Each robot gets the same shape of formula, over its own two stations and the shared map:

    phi_i = F_[a1,b1]( x_i in Goal_i^1 )
          & F_[a2,b2]( x_i in Goal_i^2 )
          & G_[0,N] ( &_j ( x_i not in Obs_j ) & &_{j != i} ( ||x_i - x_j||_inf >= d ) )

Intervals are closed and in time steps. Goals and obstacles are polytopes in halfspace
(H-) representation, `{x : A x <= b}`, with the rows normalised so a predicate's
robustness is a signed distance in metres. Three of the four obstacles are axis-aligned
boxes forming a wall with two doorways; the fourth is a square pillar rotated 45 degrees,
given as A and b directly, so the general H-representation path is exercised and not just
the box path.

The quantitative semantics are the usual ones: `min` for conjunction, `max` for
disjunction, `min` over the window for `G`, `max` over the window for `F`; a predicate
`x in {A x <= b}` scores `min_j (b_j - a_j . x)` and its negation `max_j (a_j . x - b_j)`.
rho is positive if and only if the trace satisfies the formula.

## The MILP

**Dynamics.** Discrete-time double integrator per robot, position and velocity in the
plane, acceleration as the input:

    p_{k+1} = p_k + dt v_k + 0.5 dt^2 u_k,    v_{k+1} = v_k + dt u_k

with `|v| <= v_max` and `|u| <= a_max` per axis. Velocity starts at zero.

**Horizon.** N = 16 steps at dt = 0.9 s, a 14.4 s plan, with `v_max` = 0.9 m/s and
`a_max` = 1.0 m/s^2. The discretisation is not free in either direction. `v_max dt` =
0.81 m has to stay below the 1.0 m thickness of the thinnest obstacle, or a single step
could put a robot on the far side of a wall. And dt has to stay coarse enough for the
joint instance to be solvable at all: measured on this workstation, N = 20 at dt = 0.75 s
was still at a 48% gap after 300 s, while N = 16 at dt = 0.9 s and N = 14 at dt = 1.0 s
both closed to gap 0.0 in about three minutes and N = 12 at dt = 1.2 s in 56 s. N = 16 is
the finest of those, so that is what the model file uses.

Satisfaction is enforced at the sample times, which is what discrete-time STL means. A
straight segment between two clear waypoints can still clip an obstacle corner, so the run
prints the smallest obstacle clearance along the interpolated path as a separate number —
it is much smaller than the sample-time margin and is reported as measured.

**Encoding.** Following the robustness encoding of Raman et al. (2014), every node of
every formula gets a continuous variable `z` that the constraints bound above by that
node's robustness:

* conjunction, and `G_[a,b]`: `z <= z_child` for each conjunct and each step in the
  window — no binaries needed;
* disjunction, `F_[a,b]`, staying outside a polytope, and separation: one binary `y` per
  disjunct with `z <= e + M (1 - y)` and `sum_disjuncts y >= 1`. Staying outside
  `{A x <= b}` is the disjunction "at least one halfspace is violated", one binary per
  row; infinity-norm separation is the disjunction over `+/-(x_i - x_j)_c >= d`, four
  binaries per pair per step.

The fragment has no negation, so every `z` appears only in upper-bound rows. Two
consequences, and the case study uses both. `z_root <= rho` always, so bounding `z_root`
below by a margin is a sound way to demand that the plan hold that margin — that is the
mode the case study runs in, and the run's own printout confirms it from the other side by
recomputing the plan's robustness and getting exactly 0.35. And when the objective pushes
`z_root` up instead, each `z` is tight at an optimum and `z_root` equals the robustness
that `robustness.py` computes independently on the returned trajectory —
`tests/test_encode.py::test_z_is_tight_on_the_returned_trajectory` checks that equality,
and `test_matches_a_brute_force_grid_oracle` checks the optimum itself against a
brute-force enumeration of input sequences on a small instance.

**Big-M.** No global constant. Each row's M is computed from the box the robot can
actually be in at that step: `M = ub(z) - lb(e)`, where `lb(e)` is the exact minimum of
that expression over the box and `ub(z)` the node's upper bound. The per-step box is the
workspace intersected with `start +/- v_max dt k`, which is exact because the discrete
update gives `p_{k+1} - p_k = 0.5 dt (v_k + v_{k+1})`. Velocities are bounded the same
way by `a_max dt k`. These bounds are what the branch-and-bound search works from, and
they are the difference between a tractable and an intractable instance here.

**Objective and margin.** Satisfaction is a hard constraint: every robot's root `z` is
bounded below by a required margin (`synthesis.required_margin` in the model file,
0.35 m), and the objective is the total control effort, the 1-norm of the accelerations,
through the usual epigraph variables. This is the manuscript's reading — "STL-satisfaction
constraints ... into a MILP" — and it is also the tractable one. With the robustness itself
as the objective the joint instance barely moves: measured at N = 20, after 90 s HiGHS was
at a dual bound of 2.82 against an incumbent near 0. One robot at a time it closes to gap
0.0 in about two seconds (0.500, 0.467, 0.467 m; see below). The encoder supports both: leave
`Problem.rho_required` at `None` and it maximises robustness instead, which is the mode
the unit tests use.

**Solver.** HiGHS through `scipy.optimize.milp`, open source (MIT); nothing here needs a
licence.

## Execution

A plan that satisfies its specification by construction is not something a data-driven
check can fail, so the case study runs the plan through a tracking-error process:

    e_0 = 0,   e_{k+1} = a e_k + w_k,   w_k ~ N(0, sigma^2) clipped at 3 sigma,
    executed_k = plan_k + e_k

per axis and per robot, with a = 0.8 (the closed-loop pole of a proportional path
follower) and sigma = 0.09 m, giving a steady-state error standard deviation of
`sigma / sqrt(1 - a^2)` = 0.15 m — the order of magnitude of Nav2 cross-track error in a
cluttered indoor map. The 3-sigma clip pulls the realised figure to about 0.14 m
(measured). **Those two numbers were fixed before the first run and were not adjusted
afterwards.** Whatever verdicts they produce are reported as they came out,
together with a 20-seed sweep of the same noise model so the single seed is not mistaken
for a result about the method.

The recursion is a convolution, so the whole sweep — every seed, robot, step and axis —
is one matrix product.

## Robustness and the write-back

`robustness.py` evaluates the formula tree with whole-array numpy operations (the only
loops are over formula nodes), returning the robustness signal and, through `explain`,
the leaf and step that the value came from — so a violation can be named, not just
counted. `tests/test_robustness_rtamt.py` checks it against RTAMT's
`StlDiscreteTimeSpecification` to 1e-6 on hand-built traces, on random two-robot traces,
and on the case study's own phi_1..phi_3.

`writeback.py` writes each executed trace's rho into the matching AGR block in
`model/agr_fleet.yaml` as `goal_satisfaction`, with the verdict and the binding conjunct
beside it, and `results/goal_satisfaction.json` carries the same values in machine form.
Re-running the case study rewrites those fields in place.

## ROS handoff

`results/robot_<i>_path.yaml` is a `nav_msgs/msg/Path` in the ROS 2 field layout, one per
robot, headings taken from the segment directions:

    ros2 topic pub --once /agr_1/plan nav_msgs/msg/Path "$(cat results/robot_1_path.yaml)"

This is the MILP output converted to Path waypoints for three Nav2 instances.
`tests/test_writeback.py::test_path_export_has_the_ros_field_layout` checks the files for
the message layout.

## Running it

    uv sync
    uv run pytest -q
    uv run python run_case_study.py

Options: `--margin` (required robustness margin, metres), `--mip-gap`, `--time-limit`,
`--per-robot-optima` (how much robustness the map affords each robot on its own), and
`--allocation-sweep` for the TRADES-X hook below. The joint solve takes about three and a
half minutes on this workstation; the run prints its own exact figure.

## Results

Measured on this workstation on 2026-09-22 with `uv run python run_case_study.py
--per-robot-optima`. The run is seeded and HiGHS is deterministic here, so re-running against the same model
file reproduces these numbers.

**What the map affords.** Each robot solved on its own, without the team-separation
conjunct, maximising robustness: AGR_1 0.500 m, AGR_2 0.467 m, AGR_3 0.467 m, HiGHS
Optimal in 1.8, 2.0 and 1.0 s. AGR_1's 0.500 m is the half-width of the 1.0 m doorway it
has to pass. The required margin in the model file is 0.35 m, below all three, so the
joint problem is not margin-starved before coordination is even considered.

**The joint MILP.** 1841 variables of which 1043 binary, 2390 constraints, 7988 nonzeros.
HiGHS returned status 0, `Optimization terminated successfully (HiGHS Status 7: Optimal)`,
relative gap 0.0, in about three and a half minutes (210.6 s, 223.8 s and 224.7 s in three
runs of the same instance on a loaded workstation; the solution itself is identical in all
three). Minimum control effort 5.32 (1-norm of the accelerations).
The smallest obstacle clearance along the straight-line interpolation between waypoints is
0.150 m: positive, but well under the 0.35 m held at the sample times. That difference is
what discrete-time semantics costs, and it is reported rather than hidden.

| robot | spec | planned rho | executed rho, seed 0 | verdict | binding conjunct |
|---|---|---|---|---|---|
| AGR_1 | phi_1 | 0.350 | -0.052 | violated | `sep(1,2)` at k = 8 |
| AGR_2 | phi_2 | 0.350 | -0.052 | violated | `sep(1,2)` at k = 8 |
| AGR_3 | phi_3 | 0.350 | +0.266 | satisfied | `OBS_WALL_SOUTH` at k = 6 |

Three things in that table are worth reading carefully.

*The planned values are all exactly the required margin.* Satisfaction is a constraint and
the objective is effort, so the solver buys no margin it was not asked for and the plan
sits on the 0.35 m boundary wherever that is cheapest. Nothing about the plan distinguishes
the three robots.

*AGR_1 and AGR_2 fail with the same number.* `sep(1,2)` is one node shared by phi_1 and
phi_2, so a separation breach is a breach of both specifications and both blocks get the
same goal-satisfaction value. That is the semantics working, not a bug.

*The conjunct that fails is the team one.* Both robots take the upper doorway, one behind
the other (`figures/trajectories`), and their tracking errors are independent, so the
relative error between them has 1.41 times the standard deviation of either — the pairwise
constraint is the most fragile thing in the specification even though the plan holds it
with the same 0.35 m as everything else. A single-robot analysis of either plan would not
have found this. That is the case the paper makes for the data-driven check, reproduced
here on its own numbers.

**Over 20 seeds** of the same noise model, with no change to `pole` or `sigma`: AGR_1
violated in 3 runs of 20, AGR_2 in 4, AGR_3 in 1; mean executed robustness 0.114, 0.052,
0.138 m and worst -0.191, -0.220, -0.007 m. The single seed is not the result; the spread
is (`figures/seed_sweep`).

The chain produces plans that satisfy their specifications by construction, executions
that do not all survive the scoring, and negative goal-satisfaction values written back
into the model beside positive ones: two of the three robots violate their specification
once noise is applied, both through the same shared separation conjunct.

**Figures** (SVG and PDF in `figures/`):

* `trajectories` — the map in H-representation, the six stations with their time windows,
  the three plans and the three executed traces. The paper's lower-right panel analogue.
* `robustness` — planned against executed rho per robot, with the zero line.
* `seed_sweep` — every seed's executed rho per robot.

**What a run writes.** `model/agr_fleet.yaml` (goal_satisfaction, verdict and binding
conjunct on each block, in place), `results/goal_satisfaction.json`, `results/summary.json`
(solver numbers, both trajectories, the whole sweep) and `results/robot_<i>_path.yaml`.

## TRADES-X hook: allocation as a design variable

Which robot gets which pair of stations is a design variable, not a given, and the failure
above is a coordination failure — so it is exactly the kind of thing a different allocation
might remove. `--allocation-sweep` runs the two TRADES-X stages over all 3! = 6
assignments: the model-based stage solves one MILP per assignment at the same required
margin, the data-driven stage scores each assignment's executions over the 20-seed sweep,
and the assignments are ranked by worst-case executed robustness with the minimum control
effort beside it. The table goes to `results/allocation_sweep.json`.

Measured with a 40 s budget and a 15% gap target per assignment (`--sweep-time-limit 40
--sweep-mip-gap 0.15`), 7m50s for the whole run including the main solve:

| allocation | effort | worst executed rho | violating runs of 60 |
|---|---|---|---|
| 0, 1, 2 (the model file's) | 9.09 | -0.094 | 4 |
| 0, 2, 1 | 7.10 | -0.094 | 6 |
| **1, 0, 2** | **6.65** | **+0.002** | **0** |
| 1, 2, 0 | 5.39 | -0.214 | 7 |
| 2, 0, 1 | 7.55 | -0.198 | 11 |
| 2, 1, 0 | 8.97 | -0.079 | 6 |

Sixty runs is three robots over the 20 seeds.

Swapping AGR_1's and AGR_2's station pairs is the only assignment under which no seed in
the sweep violates, and it is the design answer to the coordination failure above. It is
also an answer the model-based stage could not have given. All six plans hold exactly the
same 0.35 m margin by construction, so the only thing that stage can rank them by is
effort — and on effort it would pick `1, 2, 0` at 5.39, which is the worst of the six once
the executions are scored (-0.214). The two stages disagree, which is the case for having
both.

**Reading the ranking.** All six hit the 40 s limit — HiGHS returned status 1, not
Optimal — so these are incumbents, not optima, and the efforts are not comparable to the
5.32 of the main run, which was solved to gap 0.0. The ranking mixes the effect of the
allocation with the luck of the incumbent it stopped at. Raising `--sweep-time-limit` to
the few minutes each assignment needs would tighten it, at the cost of a much longer run.
A wall-clock limit is also not a reproducible stopping rule on its own: these numbers came
out the same in two consecutive runs on this workstation, while the main solve's gap-0.0
result is reproducible by construction.

## Layout

    assured_ma/specs.py       the STL fragment, the H-representation polytopes, the RTAMT export,
                              and the parse from fleet requirements into phi_1..phi_3
    assured_ma/encode.py      the big-M MILP: dynamics, STL, obstacles, separation
    assured_ma/synth.py       the HiGHS call and the trajectory extraction
    assured_ma/execute.py     the tracking-error process
    assured_ma/robustness.py  vectorised quantitative STL robustness, and `explain`
    assured_ma/writeback.py   the goal-satisfaction write-back into the AGR model
    assured_ma/ros_export.py  nav_msgs/msg/Path export
    run_case_study.py         the eight steps of the chain, in order, seeded
    model/                    the fleet requirements and the AGR fleet model
    tests/                    the RTAMT cross-check, the encoding tests and the oracle,
                              the execution tests, the write-back and export tests
    results/, figures/        what a run produces, kept in the repository

## References

* A. Donzé and O. Maler. Robust satisfaction of temporal logic over real-valued signals.
  FORMATS 2010. — the quantitative robustness semantics `robustness.py` implements.
* V. Raman, A. Donzé, M. Maasoumy, R. M. Murray, A. Sangiovanni-Vincentelli and
  S. A. Seshia. Model predictive control with signal temporal logic specifications.
  CDC 2014. — the big-M MILP encoding of STL that `encode.py` follows.
* D. Ničković and T. Yamaguchi. RTAMT: online robustness monitors from STL. ATVA 2020. —
  the independent implementation used as the cross-check.
* Q. Huangfu and J. A. J. Hall. Parallelizing the dual revised simplex method.
  Mathematical Programming Computation, 2018. — HiGHS, the solver behind
  `scipy.optimize.milp`.
