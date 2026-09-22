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
8192 -> 92 -> 7 of the paper's text. Whether the 7 simulated designs are the
same in both is not checked here.

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

## Run it

```
cd trades-x
uv run python case-studies/sensor-suite/run_case_study.py
```

Recorded output, 2026-09-22:

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
`writematrix` wrote 15 significant figures.

## Figures

`figures/pareto_scatter.{svg,pdf}` — all 4095 candidates in the cost/coverage
plane, the 96 Pareto designs in red, the MAVF pick circled.

`figures/mavf_ranking.{svg,pdf}` — MAVF score of the top 15 Pareto designs.
