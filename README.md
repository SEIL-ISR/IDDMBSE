# IDDMBSE

This is the companion repository for **"IDDMBSE: Integrating Data-Driven and Model-Based
Systems Engineering for Trusted Autonomous Cyber-Physical Systems,"** by John S. Baras,
Sai Sandeep Damera, Ryan Matheu, Clinton Enwerem and Praveen M.S. Kumar, Institute for
Systems Research, University of Maryland, College Park. The paper appears at the IEEE
International Symposium on Systems Engineering (ISSE), 2026; [`CITATION.cff`](CITATION.cff)
carries the citation. The paper's contributions footnote reads: "The IDDMBSE tool chain and
contested-terrain test range will be released at https://github.com/seil-umd/IDDMBSE." —
this is that release. IDDMBSE extends the MBSE V-process with a data-driven loop at every
step, anchored in SysML, the autonomy stack, and a hybrid model-based plus data-driven
trade-off architecture, instantiated here as an open-source tool chain (PERFECT,
TRADES-X, VERITAS) and demonstrated on a Trusted Autonomous Ground Robot in a
contested-terrain Isaac Sim test range.

## What is here

| directory | what it is | origin | how it was checked here (2026-09-22) |
|---|---|---|---|
| [`perfect/`](perfect/README.md) | SysML-to-ROS 2 performance-evaluation tool: a Flask server, an RQ/Redis job queue and distributed runners | recovered lab code, from the University of Maryland lab's GitLab branch `example-isaacsim-husky` | the `dummy` example ran end to end on a private Redis/Flask/runner stack; the trial reached `TrialState.SUCCESSFUL\|SHUT_DOWN` in 19.3 s, and `devtools/smoke_dummy.sh` printed `PASS` in 46.3 s |
| [`trades-x/`](trades-x/README.md) | the trade-off stage: model-based optimization (Julia) then data-driven optimization and a Multi-Attribute Value Function ranking (Python) | recovered lab code (the Julia MBO package) plus code built for this release (the greedy submodular search, the full design-space enumeration, the Python/JAX sensitivity path, the requirement partition) | 42 tests pass (`uv run pytest -q`); the case-study driver prints `GATE G2: pass`, matching the recorded 4095-design Pareto set to a maximum absolute difference of 4.7e-10 |
| [`veritas/`](veritas/README.md) | the verification layer: a model-based module (SysML/behavior-tree to UPPAAL), a data-driven module (failure-rate and STL-robustness statistics over a PERFECT campaign) and a runtime module (an STL observer plus a behavior-tree monitor) | vendored from a coauthor's two repositories (the behavior-tree modules, see [`veritas/ATTRIBUTION.md`](veritas/ATTRIBUTION.md)) plus code built for this release (the SysML-to-UPPAAL front end, the whole data-driven module, the deployed-stack observer) | 32 tests pass, 1 skipped (no full Gurobi license here); the SysML-to-UPPAAL translator produces 2 templates / 9 locations / 12 queries on the AGR stack model; the runtime observer, run live on a private ROS 2 graph, logged a requirement violation at the expected crossing; no UPPAAL query has been checked (UPPAAL is not installed here) |
| [`sysml/`](sysml/README.md) | the SysML v1 model of the AGR stack (Magic Systems of Systems Architect) and the MATLAB workbench that calls PERFECT from it | recovered lab code | the shipped model file's checksum matches the lab's original drop, and the MATLAB bridge scripts were grep-checked clean of the lab's address and home paths after the environment-variable substitution; nothing here has been run — there is no Magic SoSA or MATLAB on this workstation |
| [`isaacsim/`](isaacsim/README.md) | the contested-terrain test range: compacted USD scene layers, the rock meshes, a 14.8 MB heightmap of the terrain (rebuilt locally by `isaacsim/tools/build_terrain.py`), three design-of-experiments layers written by `isaacsim/tools/range_doe.py` (obstacle density, slope scaling, PhysX friction/restitution, extra robots, sensor payload) and two showcase scenes; NVIDIA's and Poly Haven's content is fetched to your machine by `isaacsim/tools/fetch_assets.py` from a hash-verified manifest, not redistributed | the scene, terrain and showcases are the lab's earlier authoring, compacted and relinked; the DOE script, the heightmap pipeline and the fetch tooling were built for this release | 22 tests pass; one headless load of the base scene and one DOE layer in Isaac Sim 6.0.1 found 0 unresolved references and the 7-DOF Carter articulation; the heightmap round trip reproduces the terrain to 1.5e-5; the RTX 3D lidar does not initialise under Isaac Sim 6.0 and no campaign was run in the range |
| [`case-studies/`](case-studies/README.md) | six directories mirroring the paper's Section IV: three published demonstrations pointing into the tool directories above, three demonstrations released with the paper | mixed — see `case-studies/README.md` | see `case-studies/README.md` |
| [`seil-r2/`](seil-r2/README.md) | a ROS 2 colcon workspace: an Isaac Sim Carter navigation baseline (Nav2, AMCL) plus its docker files | recovered lab code | not built here; it pins ROS 2 Humble and Isaac Sim 4.1.0, and this workstation has neither |
| [`plugins/`](plugins/README.md) | an rviz2 panel plugin for controller/planner selection | recovered lab code | not built here |

The digital-twin material for the ARL range (a placeholder `digital-twin/` directory) is
not part of this release.

## Map to the paper

Section titles are quoted from the camera-ready; its numbering is I Introduction, II Related
Work, III The IDDMBSE Framework, IV Case Studies, V Conclusion.

| paper section | what it describes | where in this repository |
|---|---|---|
| III-A, "Methodology: Data-Driven Augmentation of MBSE" | the requirements-driven data-driven loop over the MBSE V-process, and the SysML modeling hub | [`sysml/`](sysml/README.md) |
| III-B, "PERFECT: SysML-to-ROS2 Performance Evaluation" | SysML-to-ROS 2 mapping and distributed performance evaluation | [`perfect/`](perfect/README.md) |
| III-C, "TRADES-X: Hybrid Design-Space Exploration" | the model-based then data-driven design-space exploration and the MAVF ranking | [`trades-x/`](trades-x/README.md) |
| III-D, "VERITAS: Three-Module Verification of Trusted Autonomy" | the three verification modules | `veritas/formal/` (model-based), `veritas/datadriven/` (data-driven), `veritas/runtime/` (runtime) |
| IV-A.1, "Sensor-Suite Selection with TRADES-X" | published demonstration | [`case-studies/A1-sensor-suite-selection/`](case-studies/A1-sensor-suite-selection/README.md) -> [`trades-x/case-studies/sensor-suite/`](trades-x/case-studies/sensor-suite/README.md) |
| IV-A.2, "Risk-Sensitive Path Planning with PERFECT" | published demonstration | [`case-studies/A2-risk-sensitive-planning/`](case-studies/A2-risk-sensitive-planning/README.md) |
| IV-A.3, "Behavior Tree Task Specifications with VERITAS" | published demonstration | [`case-studies/A3-behavior-tree-verification/`](case-studies/A3-behavior-tree-verification/README.md) -> `veritas/formal/bt2automata/`, `veritas/runtime/tbt-monitor/` |
| IV-B.1, "A Contested-Terrain Test Range in Isaac Sim" | released demonstration, the shared environment for the other two | [`case-studies/B1-contested-terrain-range/`](case-studies/B1-contested-terrain-range/README.md) -> `isaacsim/` |
| IV-B.2, "Robust Perception via Conformal Prediction" | released demonstration | [`case-studies/B2-conformal-perception/`](case-studies/B2-conformal-perception/README.md) |
| IV-B.3, "Assured Multi-Robot Coordination" | released demonstration | [`case-studies/B3-assured-multi-robot/`](case-studies/B3-assured-multi-robot/README.md) |

## Getting started

| component | needs | command |
|---|---|---|
| PERFECT | Python 3.12, a uv virtual environment inside `perfect/` (a ROS 2 environment on the path only for the examples that drive ROS; `dummy` does not) | `cd perfect && uv venv --python 3.12 && uv pip install -e .` — then Redis (`redis-server --port 6390 --save '' --appendonly no --dir /tmp/perfect-redis`), the queue worker (`rq worker perfect-tasks --url redis://127.0.0.1:6390`), the runner (`python -m perfect.experiment.runner`) and the server (`python -m flask --app perfect.app run --port 5001`), each in its own terminal — see `perfect/README.md` for the full bring-up |
| TRADES-X (Python) | Python >= 3.11, uv | `cd trades-x && uv venv && uv sync && uv run pytest -q` |
| TRADES-X (Julia MBO) | Julia 1.12 | `cd trades-x/mbo && julia --project=. -e 'using Pkg; Pkg.instantiate()'` |
| VERITAS | Python 3.10, uv | `cd veritas && uv venv --python 3.10 && uv sync` |
| the case studies with their own uv project (A2, B2, B3) | uv | `cd case-studies/<directory> && uv sync && uv run pytest -q && uv run python run_case_study.py` |
| the case studies that call into a tool directory (A1, A3) | the tool directory's own environment (`trades-x/` or `veritas/`) | `./case-studies/<directory>/run.sh` |
| `isaacsim/tools/` | uv | `cd isaacsim/tools && uv sync` (see `isaacsim/README.md` for the fetch and build steps) |
| ROS 2, for PERFECT's ROS-backed examples and the VERITAS runtime observer | `rclpy` on the interpreter's path; the VERITAS observer was run live on ROS 2 Jazzy (`veritas/README.md`); `seil-r2/` pins ROS 2 Humble | source the distribution's `setup.bash` before running those pieces |
| Isaac Sim, for `isaacsim/` and `seil-r2/` | a local install with a GPU; `seil-r2/` pins Isaac Sim 4.1.0 | see `isaacsim/README.md` and `seil-r2/README.md` |
| optional: UPPAAL, for checking the files VERITAS's model-based module writes | download separately, register an academic key | <https://uppaal.org/downloads/>, <https://uppaal.veriaal.dk/> |
| optional: Gurobi, for `veritas/synthesis/ltbt/` | a full academic license (the pip package's size-limited license is too small for these models) | `cd veritas && uv sync --extra milp` |
| optional: MATLAB + Magic Systems of Systems Architect 2022x or later, for `sysml/workbench/` | commercial licenses, neither installed here | see `sysml/README.md` |

If a ROS 2 environment is sourced in the shell, its `site-packages` lands on
`PYTHONPATH` and pytest tries to auto-load ROS's own plugins into a Python environment
that does not have them; run tests as `env -u PYTHONPATH uv run pytest` (`trades-x/README.md`,
`veritas/README.md` say why).

To run a case study end to end, see [`case-studies/README.md`](case-studies/README.md);
for example `./case-studies/A1-sensor-suite-selection/run.sh`.

## What was verified, and what was not

Verified, with the evidence named (2026-09-22):

- `perfect/`: the `dummy` example ran end to end on a private Redis/Flask/runner stack; the trial reached `TrialState.SUCCESSFUL|SHUT_DOWN` in 19.3 s and `devtools/smoke_dummy.sh` printed `PASS` in 46.3 s.
- `trades-x/`: 42 tests pass (`uv run pytest -q`); the case-study driver prints `GATE G2: pass`, matching the recorded 4095-design Pareto set to a maximum absolute difference of 4.7e-10.
- `veritas/`: 32 tests pass, 1 skipped; both UPPAAL translators write well-formed files that load back into `pyuppaal`; the runtime STL observer, run live on a private ROS 2 graph (domain 87), logged the expected violation at the state-of-charge crossing.
- `sysml/`: the shipped model file's checksum matches the lab's original drop, and the MATLAB workbench scripts were grep-checked clean of the lab's address and home paths after the environment-variable substitution.
- `case-studies/A1-sensor-suite-selection/` and `case-studies/A3-behavior-tree-verification/`: each runs the tool directory's own gated demo unmodified through `run.sh`.
- `case-studies/A2-risk-sensitive-planning/`: 37 tests pass; the 3000-run campaign completed in about 109 s and reproduces byte-identically run to run except plan time.
- `case-studies/B2-conformal-perception/`: 19 tests pass; the closed-loop campaign's result files are byte-identical across runs.
- `isaacsim/`: 22 tests pass in `isaacsim/tools`; the compaction of every scene layer was checked field by field against the source; one headless load in Isaac Sim 6.0.1 of the base scene and of one design-of-experiments layer reported 0 unresolved references.
- `case-studies/B3-assured-multi-robot/`: the joint MILP solves to relative gap 0.0 with an identical solution across three runs, and the STL robustness code agrees with an independent RTAMT computation to 1e-6.

Not verified, or not in this release:

- UPPAAL verdicts — UPPAAL is not installed here, so no query either translator writes has been checked.
- None of the case studies ran on hardware, in Gazebo or in Isaac Sim; each directory's README states what stands in for the real pipeline (a synthetic detector and world, an independent planner implementation, and so on). The range itself was only loaded headless in Isaac Sim to check its references; no campaign was run in it, and its RTX 3D lidar does not initialise under Isaac Sim 6.0.
- PERFECT's simulator examples beyond `dummy` were load-checked only, not run to completion (`perfect/README.md`'s list of changes).
- `seil-r2/` was not built here; it pins ROS 2 Humble and Isaac Sim 4.1.0, which this workstation does not have.
- The paper's own headline numbers — the sensor-suite enumeration counts, the multi-robot robustness values, the range's 15° slope bound (the authored terrain is steeper; the design-of-experiments script rescales it) — are not reproduced by the shipped code, and each directory's README states what it produces instead.
- The BagWorld GUI and the bisimulation-function statistics that the paper's long-form description names for the data-driven verification module are described in `veritas/README.md`, not shipped.
- The SysML model needs a commercial tool (Magic Systems of Systems Architect) that is not installed here; opening it on a fresh install is unverified.

## Provenance and license

MIT ([`LICENSE`](LICENSE)). PERFECT is recovered from the lab's GitLab branch, as
`perfect/README.md` states. VERITAS's `formal/`, `runtime/` and `synthesis/` code is
vendored from a coauthor's two repositories at pinned commits, per
[`veritas/ATTRIBUTION.md`](veritas/ATTRIBUTION.md); neither upstream repository carries a
license file; the upstream author is a coauthor of the paper, and the vendored copies carry
his attribution and the pinned commit hashes. Components built
for this release are labeled as such in their own READMEs. The SysML model files and
their lineage are recorded in [`sysml/models/LINEAGE.md`](sysml/models/LINEAGE.md).

## Citing

```bibtex
@inproceedings{baras2026iddmbse,
  author    = {Baras, John S. and Damera, Sai Sandeep and Matheu, Ryan and Enwerem, Clinton and Kumar, Praveen M.S.},
  title     = {IDDMBSE: Integrating Data-Driven and Model-Based Systems Engineering for Trusted Autonomous Cyber-Physical Systems},
  booktitle = {IEEE International Symposium on Systems Engineering (ISSE)},
  year      = {2026},
  note      = {\url{https://github.com/seil-umd/IDDMBSE}}
}
```

See [`CITATION.cff`](CITATION.cff) for the machine-readable form.
