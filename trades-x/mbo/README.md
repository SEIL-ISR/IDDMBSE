# MBO — the model-based optimization stage of TRADES-X

Julia package that enumerates sensor-suite designs, scores each one with
first-principles oracles, and keeps the non-dominated set. It is the stage that
takes the design space down to a handful of candidates before PERFECT simulates
anything.

There is no genetic algorithm, simulated annealing or particle swarm here; the
search is exhaustive enumeration of subsets under a cardinality limit, plus a
greedy submodular alternative from `SubmodularGreedy.jl`.

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
evaluation table, then reports the size of the Pareto set:

```
julia --project=. run_mbo.jl [cardinality] [out.csv] [reference.csv]
```

Defaults are `CARDINALITY` (6) and `mbo_design_evals.csv`. With a third
argument it compares its own table against a recorded one. Output columns are
`cost, RAM, power, -coverage`; coverage is stored negated so that all four
columns are minimised, which is the convention `plot4met.csv` carries and which
the Pareto filters assume.

`src/mbo.jl` is the original exploratory script: the same enumeration, plus
`mbo_results` / `mbo_smo_results`, the scatter plots and the 3-D animations. It
does `using GLMakie` through `src/utilities.jl` and `src/plotting.jl`, so it
needs a display. Run it from the package root, because `src/utilities.jl` reads
`pareto_design_evals.csv` and `pareto_designs.csv` by relative path and writes
the GIFs there.

`src/sens_fd.jl` and `src/demo_sens.jl` hold the sensitivity work: the coverage
models rewritten as plain functions of their parameters, differentiated with
`ForwardDiff.gradient` and cross-checked with `FiniteDifferences`. That is the
requirement-sensitivity ranking the IDDMBSE paper describes. There is no
Python/JAX version of it anywhere in this repository.

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
0.0 over all 4095 x 4 entries, measured 2026-09-22 on Julia 1.12.7) and reports
a Pareto set of 96 designs, which is what `pareto_designs.csv` records.

Copies of the four CSVs also live under
`../case-studies/sensor-suite/data/`, taken from `sysml/workbench/results/`,
which is where the MATLAB workbench wrote them. The numbers are identical in
both places (checked element by element on 2026-09-22); the formatting is not.
The copies here have CRLF line endings in `plot4met.csv` and `plot3met.csv`, a
header row in `pareto_design_evals.csv`, and one index per line in
`pareto_designs.csv`; the workbench copies have LF, no header, and all 96
indices on a single comma-separated line.

## Install

```
julia --project=. -e 'using Pkg; Pkg.instantiate()'
```

`Manifest.toml` was resolved on Julia 1.10. On Julia 1.12 instantiate succeeds
and the enumeration runs, but several packages fail to precompile:
`SubmodularGreedy` (uses `Core.TypeName.mt`, removed in 1.12), `MbedTLS` (its
`_jll` is missing from the 1.10 manifest) and `GLMakie` (needs an X display).
`run_mbo.jl` avoids all three. Getting `src/mbo.jl` to run on 1.12 needs the
manifest re-resolved, which is a separate job.

## Other files

`jlcalldemo.py`, `jlcalldemonb.ipynb`, `JuliaCall.txt` and
`JuliaCall_README.md` are notes on calling this package from Python through
`juliacall`. `SubmodularGreedy.jl Tutorial.ipynb` is the upstream tutorial for
the greedy submodular maximisation package.
