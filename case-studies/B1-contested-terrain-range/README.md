# B1 — A contested-terrain test range in Isaac Sim (paper §IV-B.1)

## What the paper claims

Section IV-B.1 of the paper describes a high-fidelity test range built in NVIDIA
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

The range is released under [`isaacsim/`](../../isaacsim/README.md), not here.
That README is authoritative: what ships (the compacted scene layers, the rock
meshes, a 14.8 MB heightmap of the terrain, three design-of-experiments layers
and two showcase scenes — 34 files, 24 MB), what is fetched to your machine
instead of redistributed (NVIDIA's vegetation, materials, characters and the
Carter robot from NVIDIA's content CDN; the sky HDRI from Poly Haven), and
what was and was not checked.

## Requirements and steps

Isaac Sim (a local install, with a GPU) is required to open the scene. The
tools under `isaacsim/tools/` need only `usd-core` and numpy. This directory
holds no scripts of its own; the steps, verbatim from `isaacsim/README.md`:

```bash
cd isaacsim/tools
uv sync
uv run python fetch_assets.py --group range   # ~4.9 GiB from NVIDIA's CDN and Poly Haven, hash-verified
uv run python build_terrain.py                # rebuilds range/generated/terrain_low.usd from the heightmap
```

Then open `isaacsim/range/sim_world2.usd` in Isaac Sim. A design point over
the paper's parameters (obstacle density, slope, PhysX friction and
restitution, extra robots, sensor payload) is one call to
`isaacsim/tools/range_doe.py`, which writes a layer that sublayers the base
scene; the flags and the three shipped design points are in
`isaacsim/README.md`.

## What was checked here (2026-09-22)

- `isaacsim/tools`: 22 tests pass (`uv run pytest -q`); the heightmap round
  trip reproduces the terrain mesh to a maximum point error of 1.5e-5.
- One headless load of the base scene and of one design-of-experiments layer
  in Isaac Sim 6.0.1: 22 978 prims, 0 unresolved references, the Carter
  articulation found with 7 degrees of freedom. The RTX 3D lidar of the
  2023-era Carter does not initialise under Isaac Sim 6.0 (stated in
  `isaacsim/README.md`); no campaign was run in the range.
- The paper's numbers against what is measured: the authored terrain is
  steeper than the 15° the paper names (the DOE script rescales it to a target
  slope); obstacle coverage is realised within 0.0004 of the request; the
  design-of-experiments is not wired to PERFECT in this release.
