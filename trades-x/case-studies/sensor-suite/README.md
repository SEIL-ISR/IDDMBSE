# Case study: sensor suite for an autonomous ground vehicle

The study published as Damera, Kumar and Baras, *Integrated Data-Driven and
Model-Based Trade-off Analysis of Sensor Suite System for Autonomous Ground
Vehicle Navigation*, ISSE 2024.

## Design space

13 catalogue sensors: 4 3-D lidars (VLP-16 at 15 and 20 Hz, HDL-32E at 15 and
20 Hz), 4 SICK LMS1xx 2-D lasers, 3 RealSense depth cameras (D415, D435, D455)
and 2 FLIR Blackfly RGB cameras. A design is any subset. The paper counts the
full power set, 2^13 = 8192.

The recorded run did not enumerate all of them. `mbo/src/util_data.jl` sets
`CARDINALITY = 6`, so the run kept every non-empty subset of at most 6 sensors:

    sum over k = 1..6 of C(13, k) = 13 + 78 + 286 + 715 + 1287 + 1716 = 4095

`data/plot4met.csv` has exactly those 4095 rows. `data/plot3met.csv` has 8191
rows, which is every non-empty subset with no cardinality limit, but only three
metric columns. So the recorded pipeline is **4095 -> 96 -> 7**, not the
8192 -> 92 -> 7 of the paper's text.

The full enumeration was run for this release. `mbo/run_mbo.jl 13` lifts the
cardinality cap and writes `data/full_enumeration_4met.csv` (8191 rows) and
`data/pareto_full.csv` (the non-dominated row indices).
`run_full_enumeration.py` reproduces the counts from those CSVs with the Python
filter. See the counts table below.

## Metrics

Local metrics, from the first-principles oracles in `mbo/src/oracles.jl`:
effective sensor coverage in m^3 (maximised), cost in dollars, RAM in MB over a
5 second window, and power in W (all minimised). `plot4met.csv` stores them as
`cost, RAM, power, -coverage`, coverage already negated, so all four columns
are minimised.

Global metrics, from the simulated runs PERFECT executes: time to completion,
path length, cumulative elevation gradient. `tradesx/bag_metrics.py` computes
them from a trajectory. No recorded rosbags are in this repository, so the
data-driven stage is not reproduced here.

## Counts: recorded run, full enumeration, the paper's figures

Measured 2026-09-22. "standard" is `tradesx.pareto.non_dominated`,
"MATLAB-compat" is `tradesx.pareto.non_dominated_matlab_compat`, "greedy" is
the greedy submodular search in `mbo/src/greedy_submodular.jl`.

| | designs | standard Pareto | MATLAB-compat Pareto | greedy candidates | greedy frontier |
|---|---|---|---|---|---|
| recorded run, cardinality 6 | 4095 | 96 | 96 | 17 | 11 |
| full enumeration, no cap | 8191 | 120 | 120 | 24 | 15 |
| the paper's text | 8192 | 92 | - | - | - |

The paper counts 2^13 = 8192, which includes the empty design; the enumeration
here drops it, so 8191. The paper's 92 is not reproduced by either run: the
capped run gives 96 and the full run 120. The paper attributes its 92 to greedy
submodular enumeration, and no record of that run survives in the repository —
`mbo_smo_results` was a copy of the exhaustive `mbo_results` until this release.

The first 4095 rows of `data/full_enumeration_4met.csv` are identical to
`data/plot4met.csv`, and both Pareto index sets computed in Python match the
ones Julia wrote. All 96 designs of the capped Pareto set are still
non-dominated when the other 4096 designs are added.

The greedy search spends 454 coverage-oracle calls at cardinality 6 and 1114
with no cap, against 4095 and 8191 full design evaluations.

## The seven simulated designs

`perfect/examples/SEILR1/robustness.bash` hard-codes seven designs. A design id
is the decimal encoding of the 13-bit selection vector,
`evalpoly(2, reverse(design_id))` in `mbo/src/mbo.jl`. Decoded and looked up in
the full enumeration:

| design id | components | row | on the full frontier | on the capped frontier |
|---|---|---|---|---|
| 4234 | 1, 6, 10, 12 | 558 | no | no |
| 785 | 4, 5, 9, 13 | 904 | no | no |
| 549 | 4, 8, 11, 13 | 955 | no | no |
| 2185 | 2, 6, 10, 13 | 724 | no | no |
| 4370 | 1, 5, 9, 12 | 534 | no | no |
| 4 | 11 | 11 | yes | yes |
| 512 | 4 | 4 | no | no |

One of the seven is Pareto-optimal. That is consistent with how
`mbo/src/utilities.jl` labels them: the same seven appear there as `demo_des`
under the legend "Approximate Pareto Frontier Designs", so they came from an
approximate search rather than the exact filter. The search that produced them
is not in the repository.

## Pipeline

1. **Enumerate and score.** `mbo/run_mbo.jl 6` rebuilds `plot4met.csv` from the
   oracles. Checked on 2026-09-22: maximum absolute difference 0.0 across all
   4095 x 4 entries.
2. **Pareto filter.** 96 of the 4095 designs are non-dominated.
   `data/pareto_designs.csv` holds their 1-based row indices and
   `data/pareto_design_evals.csv` their metric rows, as MATLAB wrote them.
3. **Simulate the survivors.** The published run simulated 7 designs. The
   seven hard-coded in `perfect/examples/SEILR1/robustness.bash` are design ids
   4234, 785, 549, 2185, 4370, 4 and 512. A design id is the decimal encoding
   of the 13-bit selection vector, `evalpoly(2, reverse(design_id))` in
   `mbo/src/mbo.jl`; `tradesx.ddo.design_components` decodes it, so 4234 becomes
   sensors 1, 6, 10, 12.
4. **MAVF.** Normalise each metric to [0, 1] and take the weighted sum. The
   only weighting recorded in the MATLAB workbench is `weights = [0.5 0.5]`,
   `optsign = [-1 -1]` over the two global metrics (time to completion, path
   length). No weighting over the four local metrics was recorded, so
   `run_case_study.py` uses equal weights of 0.25 there and says so.

## The MATLAB Pareto filter is not the standard test

`sysml/workbench/dse/pareto.m` defines `prtp`, which keeps design k when, for
every other design i, k is strictly better than i on at least one metric. That
drops a design as soon as any other design is weakly better on every metric,
with no strictness requirement — so exact duplicates and weakly dominated ties
are both removed, which the standard non-dominance test does not do. Its result
is always a subset of the standard one.

On this data the two agree: 96 designs either way, and the same 96.
`plot4met.csv` does contain 256 duplicate metric rows, but none of them is
non-dominated, so the difference never bites here.
`tradesx.pareto.non_dominated` implements the standard test and
`tradesx.pareto.non_dominated_matlab_compat` the MATLAB one;
`run_case_study.py` reports both.

## The requirement partition

`requirements.yaml` holds the 23 SysML requirements of the AGR_stack model with
the split the IDDMBSE methodology asks for before any trade-off runs:
model-based when satisfaction is checkable offline from datasheets or a
first-principles model, data-driven when it can only be established by running
the stack. Each entry carries the reason and the tool stage that checks it (MBO,
DDO through PERFECT, or MAVF for the roll-ups). Ids and texts come from the
`sysml:Requirement` elements in
`sysml/models/AGR_stack-MB-SensorTrade-mk6.mdzip`; the split itself was built
for this release, since the model carries none.

7 requirements are model-based and 16 data-driven; by stage, 5 MBO, 15 DDO, 3
MAVF. `tradesx.requirements` loads and checks the file and
`run_case_study.py` prints the table.

## Sensitivity

`tradesx/sensitivity.py`, added for this release, is the Python side of the
sensitivity ranking: the cost, RAM, power and coverage oracles ported from
`mbo/src/oracles.jl`, vectorised over a batch of designs with numpy and
differentiated with JAX. `sensitivities(design)` returns the (4, 13, 6) Jacobian
of the four local metrics with respect to the design parameters
(update rate, h_fov, v_fov, max range, cost, power per sensor), and
`rank_requirements` orders the requirements by the sensitivity of the metric
that checks them.

The Julia path (`mbo/src/demo_sens.jl`, ForwardDiff) and the JAX path agree to
better than 1e-6 on all four coverage models; `tests/test_sensitivity.py`
carries the Julia reference numbers and checks it, and cross-checks JAX against
a central finite difference. `effective_coverage_oracle` is not ported: it
mutates the sensor catalogue as it runs, so it is not a pure function of the
design.

## Run it

```
cd trades-x
uv sync --extra ad
uv run python case-studies/sensor-suite/run_case_study.py
uv run python case-studies/sensor-suite/run_full_enumeration.py
```

Recorded output of `run_case_study.py`, 2026-09-22, first block:

```
designs evaluated: 4095
recorded Pareto designs: 96
duplicate metric rows in plot4met.csv: 256
standard non-dominated: 96
matlab-compat non-dominated: 96
standard == matlab-compat: True
standard index set == recorded: True
max abs metric difference vs recorded evals: 4.656612873077393e-10
GATE G2: pass
```

The residual 4.7e-10 is the recorded CSV's print precision: MATLAB's
`writematrix` wrote 15 significant figures. The rest of the run prints the MAVF
ranking, the requirement partition table and the sensitivity ranking of the
MAVF-best design.

Recorded output of `run_full_enumeration.py`, same day, first block:

```
full enumeration rows: 8191
capped enumeration rows: 4095
first 4095 rows of the full run equal plot4met.csv: True
cost max abs difference vs Julia: 0.0
RAM max abs difference vs Julia: 1.8189894035458565e-12
power max abs difference vs Julia: 0.0

full 8191 standard non-dominated: 120
full 8191 matlab-compat non-dominated: 120
full set equals the Julia pareto_full.csv: True
capped 4095 standard non-dominated: 96
capped set equals the recorded pareto_designs.csv: True
capped Pareto designs still non-dominated in the full space: 96 of 96
```

The 1.8e-12 on RAM is floating-point summation order between the Julia and the
numpy oracle; cost and power agree bit for bit.

## Figures

`figures/pareto_scatter.{svg,pdf}` — all 4095 candidates in the cost/coverage
plane, the 96 Pareto designs in red, the MAVF pick circled.

`figures/mavf_ranking.{svg,pdf}` — MAVF score of the top 15 Pareto designs.
