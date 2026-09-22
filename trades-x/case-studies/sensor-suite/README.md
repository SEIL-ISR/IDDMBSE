# Case study: sensor suite for an autonomous ground vehicle

The study published as Damera, Kumar and Baras, *Integrated Data-Driven and
Model-Based Trade-off Analysis of Sensor Suite System for Autonomous Ground
Vehicle Navigation*, ISSE 2024.

## Design space

13 catalogue sensors: 4 3-D lidars (VLP-16 at 15 and 20 Hz, HDL-32E at 15 and
20 Hz), 4 SICK LMS1xx 2-D lasers, 3 RealSense depth cameras (D415, D435, D455)
and 2 FLIR Blackfly RGB cameras. A design is any non-empty subset, 2^13 - 1 =
8191 of them.

The recorded run capped the size of a design. `mbo/src/util_data.jl` sets
`CARDINALITY = 6`, so it kept every non-empty subset of at most 6 sensors:

    sum over k = 1..6 of C(13, k) = 13 + 78 + 286 + 715 + 1287 + 1716 = 4095

`data/plot4met.csv` has exactly those 4095 rows. `data/plot3met.csv` has 8191
rows, which is every non-empty subset with no cardinality limit, but only three
metric columns. The recorded pipeline is **4095 -> 96 -> 7**.

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

Global metrics, from the simulated runs PERFECT executes. The campaign below
measures how often a design reached its goal, how long it took, how far it
detoured, how often it hit something, how early it saw what was in its way, and
what that left in the battery. `tradesx/bag_metrics.py` computes path length,
time to completion and cumulative elevation gradient from a trajectory.

## Counts: recorded run and full enumeration

Measured 2026-09-22. "standard" is `tradesx.pareto.non_dominated`,
"MATLAB-compat" is `tradesx.pareto.non_dominated_matlab_compat`, "greedy" is
the greedy submodular search in `mbo/src/greedy_submodular.jl`.

| | designs | standard Pareto | MATLAB-compat Pareto | greedy candidates | greedy frontier |
|---|---|---|---|---|---|
| recorded run, cardinality 6 | 4095 | 96 | 96 | 17 | 11 |
| full enumeration, no cap | 8191 | 120 | 120 | 24 | 15 |

The enumeration drops the empty design, so 8191 rather than 2^13.
`mbo/src/greedy_submodular.jl`, the greedy submodular search, was written for
this release; `mbo_smo_results` had been a copy of the exhaustive `mbo_results`.

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
approximate search rather than the exact filter.

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
4. **Run the campaign.** `run_ddo_campaign.py` submits the designs and the
   scenarios to a live PERFECT server and reads the trials back. The section
   below records a run.
5. **MAVF.** Normalise each metric to [0, 1] and take the weighted sum. The
   weighting the MATLAB workbench carries is `weights = [0.5 0.5]`,
   `optsign = [-1 -1]` over the two global metrics (time to completion, path
   length); `run_case_study.py` uses equal weights of 0.25 over the four local
   metrics and says so, and `run_ddo_campaign.py` takes its weights from the
   requirement partition.

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
for this release.

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
a central finite difference. The Julia `effective_coverage_oracle`, which merges
overlapping ranges and fields of view as it walks a design, stays on the Julia
side: it mutates the sensor catalogue as it runs, so it is not a pure function
of the design. `data/full_enumeration_4met.csv` carries its values.

## Data-driven stage through PERFECT

The model-based stage ranks a design from its datasheet: what it costs, what it
draws, how much of the on-board memory its streams take. The data-driven stage
puts the same designs in a simulation and ranks them by what they did. This
section records a campaign run on 2026-09-22.

**The example.** `perfect/examples/sensor-suite-sim` is a PERFECT example with
no simulator behind it: a planar navigation simulation in plain Python where a
robot crosses a 30 m field of rocks, plans on an occupancy grid holding only the
rocks its sensors have reported, and re-plans every sixth control step. Its
component library is the same thirteen sensors this study's design space is
built from, its environment template takes rock density, ambient light, a seed
and a number of noise draws, and a trial reports what the robot achieved. Its
README has the sensing model and the metric definitions.

**The campaign.** Ten designs: the seven above, plus the three best of the full
model-based frontier under an equal-weight MAVF over the four model-based
metrics that are not already among the seven — `frontier-1` (VLP-16-A),
`frontier-3` (HDL-32E-A) and `frontier-38` (HDL-32E-A + LMS111-a2). Eighteen
scenarios: rock density 0.2, 0.5 and 0.8, ambient light 1.0 and 0.4, three
seeds each, twelve noise draws per trial. One trial per pair, 180 trials.

**The submission.** `tradesx/ddo_api.py` loads the sensor library, creates the
ten designs, the scenario template and the eighteen scenarios, and creates the
180 experiments with a trial each, all over `POST /api/v1/...` on a running
PERFECT server. It then polls `GET /api/v1/experiments` until every trial has
shut down and reads each one back through `GET /api/v1/trials/<id>`, where the
experiment left its metrics as an `Update` row.

**What came back.** All 180 trials reached
`TrialState.SUCCESSFUL|SHUT_DOWN`; the campaign took 4 min 35 s wall on one
runner, about 1.5 s per trial. The suite totals the trials reported agree with
`tradesx.sensitivity`'s cost, power and RAM to 4.9e-07, which is the rounding in
the example's own catalogue.

**The ranking.** The MAVF runs over the three model-based attributes (price,
power, RAM, all minimised) and the six measured ones (success rate, collision
rate, time to goal, tortuosity, detection distance, state of charge). The
weights come from the requirement partition: 7 of the 23 requirements are
model-based and 16 data-driven, so the model-based attributes carry 7/23 of the
weight and the measured ones 16/23, split equally inside each class.
`results/mavf_ddo_ranking.csv` holds the whole table; the printed ranking was

```
rank design            mavf   mbo-only  success  time[s]  tort   det[m]  cost[$]
   1 design-4370       0.6732       6    0.981     41.7  1.156   15.33    14500
   2 design-4234       0.6696       7    0.991     40.9  1.135   15.33    15500
   3 design-2185       0.6633       8    0.991     40.9  1.134   17.51    19000
   4 design-512        0.6626       4     0.88     49.8   1.38   12.77    16000
   5 frontier-1        0.6572       2    0.824     54.4  1.508   11.16    10000
   6 frontier-3        0.6462       3    0.861     51.3  1.423   12.42    15000
   7 design-785        0.6286       9    0.991     40.9  1.133   17.67    22000
   8 frontier-38       0.6217       5    0.889     49.0   1.36   12.48    16000
   9 design-549        0.6019      10    0.991     40.9  1.133   17.67    24000
  10 design-4          0.3909       1     0.44     84.9  2.353    3.62     3000
```

`design-4` is the one design of the seven that sits on the model-based frontier,
and on the model-based attributes alone it ranks first: a single D455 depth
camera is the cheapest suite in the study, draws 10 W and buffers 2.3 GB. In the
campaign it reached the goal in 44% of its draws, took twice as long as the
four-sensor suites and wandered 2.35 times the straight-line distance, because a
D455 sees six metres and, in the dark scenarios, less than three. It comes last
once the measured attributes are in. The four-sensor suites, which the
model-based ranking puts sixth to tenth, take the top three places and seventh
and ninth; the one- and two-sensor lidar designs land in between, reaching the
goal 82% to 89% of the time.

`results/ddo_campaign.csv` is one row per trial, `results/ddo_metrics.csv` the
designs-by-scenarios table of the six measured metrics.

### Run the campaign

Bring a PERFECT stack up on the `sensor-suite-sim` example (that example's
README has the sequence), then:

```
cd trades-x
uv run python case-studies/sensor-suite/run_ddo_campaign.py --submit --url http://127.0.0.1:5001
uv run python case-studies/sensor-suite/run_ddo_campaign.py --collect --url http://127.0.0.1:5001
```

`--submit` can be re-run against a database that already holds the campaign:
the library, the designs and the scenarios are matched by name, and the
experiments by their design-and-scenario pair, so a second submission creates
nothing and enqueues no trial. `--collect` reads the database and rewrites the
tables and the figures; two collections of the same database give
byte-identical CSVs.

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

`figures/ddo_success_heatmap.{svg,pdf}` — success rate of each campaign design
in each of the eighteen scenarios.

`figures/ddo_mavf_ranking.{svg,pdf}` — the campaign ranking, with the score the
model-based attributes alone give each design beside it.

`figures/ddo_pareto_scatter.{svg,pdf}` — all 8191 designs in the cost/coverage
plane, the 120 model-based frontier designs in red, the ten campaign designs in
blue, the campaign's top three circled.
