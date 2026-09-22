# MBO — the model-based optimization stage of TRADES-X

Julia package that enumerates sensor-suite designs, scores each one with
first-principles oracles, and keeps the non-dominated set. It is the stage that
takes the design space down to a handful of candidates before PERFECT simulates
anything.

There is no genetic algorithm, simulated annealing or particle swarm here; the
search is exhaustive enumeration of subsets under a cardinality limit, plus a
greedy submodular alternative in `src/greedy_submodular.jl`.

## Sensors and oracles

`src/util_data.jl` defines four mutable structs — `lidar`, `laser`,
`depth_camera`, `camera` — and the 13 catalogue entries the study uses: 4
lidars (VLP-16 at two update rates, HDL-32E at two), 4 SICK LMS1xx lasers, 3
RealSense depth cameras (D415, D435, D455) and 2 FLIR Blackfly cameras. It also
sets `N_SENSORS = 13`, `CARDINALITY = 6` and `H_PLATFORM = 0.5` m.

`src/oracles.jl` scores a design, given as a `Vector{Bool}` over those 13 slots:

| oracle | what it returns |
|---|---|
| `cost_oracle(design)` | sum of the per-sensor costs, in dollars |
| `ram_oracle(design, T)` | data volume over `T` seconds, in MB |
| `power_oracle(design)` | passive draw plus a storage term, in W |
| `coverage_oracle(design)` | sum of the per-sensor sensed volumes, in m^3 |
| `effective_coverage_oracle(design)` | coverage after subtracting the overlap between sensor types, in m^3 |

The per-sensor coverage models are closed-form sensed volumes clipped at the
ground plane: a truncated cone for a lidar, a thin wedge for a 2-D laser, a
frustum for the depth and RGB cameras.

`effective_coverage_oracle` is the one the study uses. It walks the design in
slot order and, for each sensor it adds, subtracts an overlap term that depends
on which sensor types are already in the set. Note that it mutates the global
`sensors` array as it merges ranges and fields of view, so results depend on
evaluation order; `run_mbo.jl` and `src/mbo.jl` use the same order.

## Entry points

`run_mbo.jl` is the headless one. It enumerates, scores and writes the design
evaluation table, reports the size of the Pareto set, and runs the greedy
submodular search over the same space for comparison:

```
julia --project=. run_mbo.jl [cardinality] [out.csv] [reference.csv] [pareto.csv]
```

Defaults are `CARDINALITY` (6) and `mbo_design_evals.csv`. Pass `-` for
`reference.csv` to skip the comparison but still write the Pareto indices.
Cardinality 13 lifts the cap and enumerates all 8191 non-empty subsets. Output
columns are `cost, RAM, power, -coverage`; coverage is stored negated so that
all four columns are minimised, which is the convention `plot4met.csv` carries
and which the Pareto filters assume.

`src/mbo.jl` is the original exploratory script: the same enumeration, plus
`mbo_results` / `mbo_smo_results`, the scatter plots and the 3-D animations. It
runs headless — `Plots` uses GR with `GKSwstype=100` and `src/plotting.jl` now
uses CairoMakie — but it must be run from the package root, because
`src/utilities.jl` reads `pareto_design_evals.csv` and `pareto_designs.csv` by
relative path and **overwrites** `pareto_optimal_designs.gif` and
`mosmo_approx_pareto.gif` there.

`src/sens_fd.jl` and `src/demo_sens.jl` hold the sensitivity work.
`src/demo_sens.jl` differentiates the coverage models written as plain functions
of their parameters. `src/sens_fd.jl` differentiates `sensor_coverage_oracle`
itself, by loading `src/util_data_mod.jl` instead of `src/util_data.jl`: the two
differ only in that the modified structs declare their numeric fields `Real`, so
ForwardDiff can push dual numbers through the unchanged oracle. Both are
cross-checked with `FiniteDifferences` and both print their gradients. The
Python/JAX side of the same calculation is `tradesx/sensitivity.py`, added for
this release; `tests/test_sensitivity.py` checks the two agree.

`src/fetch_data.jl` is a stub that would pull design evaluations from a web
endpoint; the URL is a placeholder.

## Recorded outputs in this directory

| file | what it is |
|---|---|
| `plot4met.csv` | 4095 rows: every non-empty subset of the 13 sensors with at most 6 members, as `cost, RAM, power, -coverage` |
| `plot3met.csv` | 8191 rows: all non-empty subsets, cost/RAM/power only |
| `pareto_designs.csv` | the 96 Pareto row indices, 1-based, as MATLAB wrote them |
| `pareto_design_evals.csv` | the metric rows of those 96 designs |
| `plot_*.svg`, `*.gif`, `movie_info.jld2` | figures and animation state from that run |

`run_mbo.jl 6` reproduces `plot4met.csv` exactly (maximum absolute difference
0.0 over all 4095 x 4 entries, measured 2026-09-22 on Julia 1.12.7 after the
manifest was re-resolved) and reports a Pareto set of 96 designs, which is what
`pareto_designs.csv` records. `run_mbo.jl 13` lifts the cardinality cap; its
first 4095 rows are identical to `plot4met.csv` as well, which is the check that
the enumeration order and the oracle's mutation history are unchanged. Its
output lives in `../case-studies/sensor-suite/data/`.

Copies of the four CSVs also live under
`../case-studies/sensor-suite/data/`, taken from `sysml/workbench/results/`,
which is where the MATLAB workbench wrote them. The numbers are identical in
both places (checked element by element on 2026-09-22); the formatting is not.
The copies here have CRLF line endings in `plot4met.csv` and `plot3met.csv`, a
header row in `pareto_design_evals.csv`, and one index per line in
`pareto_designs.csv`; the workbench copies have LF, no header, and all 96
indices on a single comma-separated line.

## The greedy submodular search

`src/greedy_submodular.jl` replaces the `SubmodularGreedy.jl` dependency, which
the environment used to carry. That package does not load on Julia 1.12 (it
reaches for `Core.TypeName.mt`, removed in 1.12) and is unmaintained upstream
(github.com/crharshaw/SubmodularGreedy.jl). Nothing under `src/` ever called it:
the only references were `Project.toml`, `Manifest.toml` and the upstream
tutorial notebook kept beside this README.

The replacement keeps the upstream calling convention — a marginal-gain oracle
`f_diff(elm, sol)` and an independence oracle `ind_add_oracle(elm, sol)` — and
provides `greedy`, `repeated_greedy` and `card_add_ind`. It is the plain
(non-lazy) greedy rather than upstream's priority-queue version, it returns four
values instead of five because there are no knapsack constraints, and the
sample-greedy and simultaneous-greedy variants are not carried over. For a
monotone submodular objective under a cardinality constraint this is the classic
(1 - 1/e) greedy.

`coverage_gain` is the marginal-gain oracle over the sensor catalogue. It goes
through `set_coverage`, which saves and restores the catalogue around every call
because `effective_coverage_oracle` mutates it.

`mbo_smo_results(sensors, C)` in `src/mbo.jl` is the greedy counterpart of
`mbo_results`: it runs `repeated_greedy` at every cardinality budget k = 1..C
with three rounds each, dedupes, scores the survivors on all four metrics and
hands back the table. `pareto_rows` then gives the approximate frontier. Before
this release that function was a copy of `mbo_results` and did no greedy search
at all.

Sizing the greedy against the exhaustive run, measured 2026-09-22:

| budget | exhaustive designs | Pareto | greedy candidates | greedy frontier | coverage-oracle calls greedy spent |
|---|---|---|---|---|---|
| 6 | 4095 | 96 | 17 | 11 | 454 |
| 13 (no cap) | 8191 | 120 | 24 | 15 | 1114 |

## Install

```
julia --project=. -e 'using Pkg; Pkg.instantiate()'
```

`Manifest.toml` was re-resolved on Julia 1.12.7 on 2026-09-22 and the
environment precompiles clean (`Pkg.precompile()`: 248 dependencies compiled,
132 already cached, no failures). Four packages were dropped from `Project.toml` in the
process: `SubmodularGreedy` (replaced, see above), `GLMakie` (needs an X
display; `src/plotting.jl` uses CairoMakie instead), and `VegaLite` and
`BenchmarkTools`, neither of which any source file uses.

## Other files

`jlcalldemo.py`, `jlcalldemonb.ipynb`, `JuliaCall.txt` and
`JuliaCall_README.md` are notes on calling this package from Python through
`juliacall`. `SubmodularGreedy.jl Tutorial.ipynb` is the upstream tutorial for
the package `src/greedy_submodular.jl` replaced; it is kept as the reference for
the oracle convention and does not run here.
