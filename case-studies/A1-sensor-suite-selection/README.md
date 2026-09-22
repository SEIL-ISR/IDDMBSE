# A1 — Sensor-suite selection with TRADES-X (paper §IV-A.1)

## What the paper claims

Section IV-A.1 of the manuscript (`sections/case_studies.tex` lines 10-13)
describes sensor-suite selection for the AGR as an end-to-end exercise of
TRADES-X: over $2^{13}=8192$ candidate suites of 3D lidar, 2D laser, RGB and
RGB-D sensors, a model-based optimization stage prunes to 92 Pareto-optimal
candidates by greedy submodular enumeration, PERFECT simulates only the 7
survivors, and a Multi-Attribute Value Function (MAVF) analysis returns the
recommended design. The paper frames this as the prune-then-evaluate economy
of its methodology section, realized at the trade-off step: the campaign
collapses from thousands of configurations to single digits, and because each
simulated candidate carries a fixed setup and run cost, that reduction
translates directly into design-stage schedule and compute savings. This is
the published study behind that subsection, from Damera, Kumar and Baras, ISSE
2024. **These are the paper's own claimed numbers, not results reproduced by
this repository** — see the next section for what actually runs here.

## Where the code lives

* `trades-x/case-studies/sensor-suite/` — the case-study driver
  (`run_case_study.py`, `run_full_enumeration.py`), its data and figures.
* `trades-x/mbo/` — the Julia model-based-optimization package (oracles,
  Pareto filter, greedy submodular search) that produced the recorded data.

## What it produces

`trades-x/case-studies/sensor-suite/README.md` has the full counts table.
Copied from it, measured 2026-09-22:

| | designs | standard Pareto | MATLAB-compat Pareto |
|---|---|---|---|
| recorded run, cardinality 6 | 4095 | 96 | 96 |
| full enumeration, no cap | 8191 | 120 | 120 |
| the paper's text | 8192 | 92 | - |

The paper's 92 Pareto-optimal designs is **not reproduced** by either run in
this repository: the recorded cardinality-6 run gives 96, and the full
8191-design enumeration gives 120. No record of the greedy submodular run that
produced the paper's 92 survives in the repository.

## How to run

```
./run.sh
```

which runs `case-studies/sensor-suite/run_case_study.py` from `trades-x/`.
See `trades-x/case-studies/sensor-suite/README.md` for `run_full_enumeration.py`
and the sensitivity and requirements-partition steps, which `run.sh` does not
invoke.

## Prerequisites

* `uv` (the Python side; `uv run` inside `trades-x/` resolves the environment
  from `trades-x/pyproject.toml` and `trades-x/uv.lock` on first use — no
  separate setup step is required to run `./run.sh`, confirmed by the gate run
  below).
* Julia 1.12.7 — only needed for the Julia path (`mbo/run_mbo.jl`,
  `mbo/src/demo_sens.jl`), which `run.sh` does not invoke.
