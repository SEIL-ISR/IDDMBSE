# B1 — A contested-terrain test range in Isaac Sim (paper §IV-B.1)

## What the paper claims

Section IV-B.1 of the manuscript (`sections/case_studies.tex` lines 35-58,
`\label{sssec:range}`) describes a high-fidelity test range built in NVIDIA
Isaac Sim and released as USD assets with the tool chain. It "supports
multiple AGRs, a full multi-modal sensor payload, and contested off-road
terrain with slopes up to $15^\circ$ and obstacle densities swept from $10$
to $80\%$ coverage, all under tunable PhysX physics (surface friction,
restitution, and wheel-terrain contact)." PERFECT is said to drive the range
"through its Python and USD interface: a single Isaac Sim script parameterizes
the scene and physics, so a Design of Experiments over terrain conditions
becomes a distributed PERFECT campaign rather than a collection of hand-built
worlds." The Design-of-Experiments parameters the text names are: **obstacle
density**, **slope**, **surface friction and restitution** (and
wheel-terrain contact), plus the **multiple AGRs** and **multi-modal sensor
payload** the range is built to support. **This is the paper's description of
the range as designed; it is not a claim verified by this directory.**

## Where the range actually is

The range is released under `isaacsim/` in this repository, not here.
`isaacsim/README.md` is authoritative for it: what USD files ship, what is
fetched separately as a release asset, how to open the scene, and what is and
is not verified about it. In particular, as of this writing `isaacsim/README.md`
states there is **no parameterising script and no obstacle-density sweep
shipped** — the range is one fixed scene, not the family the paper's DOE
describes — and that terrain slopes have not been characterised numerically.

## Requirements

Isaac Sim (a local install, with a GPU) is required. **Nothing in this
directory runs without it.** This directory holds no scripts of its own; it
points at the steps that belong in `isaacsim/`:

1. Fetch the NVIDIA and Poly Haven assets locally with a fetch script,
   `isaacsim/tools/fetch_assets.py` `[planned; verify against
   isaacsim/README.md]`.
2. Build the terrain from the shipped heightmap with
   `isaacsim/tools/build_terrain.py` `[planned; verify against
   isaacsim/README.md]`, then open the assembled scene in Isaac Sim.
3. Generate DOE variants over the terrain conditions with
   `isaacsim/tools/range_doe.py` `[planned; verify against
   isaacsim/README.md]`.

The `isaacsim/` layout was being finalised when this README was written
(2026-09-22), so those three script names are as planned, not as verified
present — check them against the `isaacsim/README.md` current at read time.
As of this same date, `isaacsim/README.md` documents working asset-fetch
tooling under a different name, `isaacsim/tools/download_assets.sh`, and
generic USD-relink/manifest tooling (`tools/relink.py`, `tools/manifest.py`);
it states plainly that there is **no parameterising script and no
obstacle-density sweep shipped yet** — the range is one fixed scene. So step 1
above may already be covered by `download_assets.sh` rather than
`fetch_assets.py`; steps 2 and 3 are not yet covered by anything shipped
there.
