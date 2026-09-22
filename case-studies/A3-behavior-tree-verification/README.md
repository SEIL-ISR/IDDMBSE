# A3 — Behavior-tree task specifications with VERITAS (paper §IV-A.3)

## What the paper claims

Section IV-A.3 of the manuscript (`sections/case_studies.tex` lines 26-31)
describes Behavior Trees (BTs) as a prominent high-level framework for
specifying autonomous robot task plans, and notes that their widespread
adoption has driven growing emphasis on formal verification for safe and
correct operation. VERITAS's BT modules, exercised below, support automated
model generation [BT2Automata, HSCC 2025] and the synthesis of online monitors
[OMTBT, ECC 2025] directly from BT specifications: the formal models are used
"for verification of task plans and formal control synthesis in UPPAAL", and
the greedy online monitors "for quantitative task monitoring and to provide
feedback for learning-based controllers."

## Where the code lives

* `veritas/formal/bt2automata/` — composes a behavior tree into a UPPAAL
  network of timed automata for model checking and control synthesis
  (BT2Automata, HSCC'25).
* `veritas/runtime/tbt-monitor/` — the ternary temporal-BT runtime monitor,
  with RTAMT STL leaf specifications; returns a quantitative robustness and a
  three-valued node state at every step (OMTBT, ECC'25).
* `veritas/synthesis/ltbt/` — three-valued (Kleene) encodings of temporal
  behavior trees as Gurobi MILP constraints, and trajectory-synthesis scripts
  built on them. Optional: needs a full Gurobi license (see below).

`veritas/README.md` and `veritas/ATTRIBUTION.md` describe the provenance:
everything under `formal/`, `runtime/` and `synthesis/` "was written by Ryan
Matheu … a coauthor of the IDDMBSE paper, and is copied here from his two
research repositories at the commits named below" — `formal/bt2automata/` and
`runtime/tbt-monitor/` from `github.com/rymatheu/hscc25-rp` at commit
`e63fa448b4b06cf137b9f0f462a4ae1021e19c4a`, and `synthesis/ltbt/` from
`github.com/rymatheu/ltbt` at commit `6f2be3f9dc521dc075131ed01fce20c79b8fc797`
(`veritas/ATTRIBUTION.md`). Neither upstream repository carries a LICENSE
file; the code is used here with the author's agreement as a coauthor of the
IDDMBSE paper.

The exact demo commands, from `veritas/README.md`:

```
uv run python formal/bt2automata/demo.py            # writes BT_converted.xml
uv run python runtime/tbt-monitor/demo_synthetic.py # needs only the base install
```

`synthesis/ltbt/` needs `uv sync --extra milp` and a Gurobi license; see
`veritas/README.md` for its commands.

## Checking the output in UPPAAL

UPPAAL's redistribution terms do not permit including it here (see
`veritas/README.md`, "Licenses"). Download it from
<https://uppaal.org/downloads/>, register for an academic license at
<https://uppaal.veriaal.dk/>, and open `BT_converted.xml` there to check the
queries.

## How to run

```
./run.sh
```

runs the `formal/bt2automata/demo.py` command above from `veritas/`, writing
`BT_converted.xml` next to that script by default, or to the path given as
`./run.sh <path>`.
