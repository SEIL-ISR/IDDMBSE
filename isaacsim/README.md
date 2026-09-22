# The IDDMBSE Isaac Sim test range

The contested-terrain test range the IDDMBSE paper's demonstrations run on: a
99 x 97 m off-road site in NVIDIA Isaac Sim with a Carter v2.4 carrying a
multi-modal sensor payload, vegetation, rocks, two walking characters, a water
feature and a warehouse platform, plus a script that turns the site into a
design of experiments over obstacle density, slope and PhysX contact
parameters.

**What is in git is the scene, not the content it stands on.** The layers here
are 21 MB. The vegetation, the materials, the characters and the robot are
NVIDIA's, published on NVIDIA's content CDN; the sky is a Poly Haven HDRI.
Those are downloaded to your own machine and the scene picks them up from
there. See [Getting the content](#getting-the-content).

Everything in `tools/` needs only `usd-core` -- no Kit, no GPU -- except where
this file says otherwise.

---

## Quick start

```bash
cd tools
uv sync                                  # usd-core and numpy
uv run python fetch_assets.py --group range     # ~4.9 GiB from NVIDIA's CDN and Poly Haven
uv run python build_terrain.py                  # writes ../range/generated/terrain_low.usd
uv run python fetch_assets.py --isaacsim-path ~/isaacsim   # optional, see Characters
```

Then open `range/sim_world2.usd` in Isaac Sim. To generate a design point:

```bash
uv run python range_doe.py --obstacle-density 0.3 --max-slope-deg 15 \
    --friction-static 0.4 --friction-dynamic 0.35 --seed 7 --out ../range/doe/run07.usda
```

and open `range/doe/run07.usda`, which sublayers the base scene.

---

## What ships here

| path | bytes | what |
|---|---|---|
| `range/sim_world2.usd` | 9 558 | the scene: physics, ROS clock, the Carter, the two characters, the teleop graph, and a payload of the terrain world |
| `range/terrain1_world.usd` | 383 613 | the site: terrain, 27 rock instances, 5 276 vegetation instances, water, the warehouse platform, the dome light |
| `range/teleop.usd` | 4 459 | the keyboard teleop OmniGraph |
| `range/terrain/heightmap.npz` | 14 804 748 | the terrain, as a 2048 x 2048 float32 height grid |
| `range/terrain/terrain_meta.json` | 1 463 | grid spacing, extents, axis convention and the scene transform that places it |
| `range/rocks/Rock_{1,5,9}.usd` | 73 157 / 56 391 / 56 635 | the three rock meshes the site and the DOE script instance |
| `range/doe/density_0p{1,4,8}.usda` | 200 909 / 845 016 / 1 731 993 | three generated design points |
| `range/doe/doe_manifest.json` | 4 105 | what each of them measured |
| `range/assets/MANIFEST.json` | 2 305 198 | every external file the scene needs: url, size, SHA-256, and which part of the repository needs it |
| `showcases/warehouse_iros_v1.usd` | 3 167 398 | a warehouse showcase scene |
| `showcases/warehouse_nvblox.usd` | 5 751 | a warehouse showcase set up for nvblox |
| `thumbnails/*.png` | 378 644 | three viewport captures |
| `tools/*.py` | 79 713 | the scripts this file documents |
| `.gitignore`, `MANIFEST.json` | | what the tools write, and sizes and hashes of everything above |

34 files, 24 MB. `MANIFEST.json` gives the size and SHA-256 of 31 of them --
it does not describe itself, `README.md`, or the download manifest -- and adds
up to 21 857 128 bytes. Largest shipped file: `range/terrain/heightmap.npz`,
14 804 748 bytes. Nothing shipped here is over 20 MB.

Not in git, written by the tools, listed in `.gitignore`:
`range/assets/` (4.9 GiB downloaded), `range/HDRI/` (183 MB downloaded),
`range/generated/` (129 MB built).

---

## Getting the content

### The script

```bash
cd tools && uv run python fetch_assets.py --group range
```

reads `range/assets/MANIFEST.json`, downloads each file into
`range/assets/<the same path it has on the CDN>` and checks it against the
recorded size and SHA-256. `--check` verifies what is already there without
downloading. `--group showcases` fetches what the two showcase scenes need
instead; with no `--group`, everything.

| group | files | bytes |
|---|---|---|
| range | 1 545 | 5 261 349 606 (4.90 GiB) |
| showcases | 2 363 | 1 672 740 508 (1.56 GiB) |

The scene layers reference these by relative path. `relink.py --mode cloud`
rewrites them back to the CDN URLs if you would rather stream, and
`relink.py --mode local` puts the relative paths back.

### The official packs instead

The same files are in NVIDIA's own distributions, and if you already have them
there is no reason to download them twice:

- **the Isaac Sim asset pack** covers everything under
  `range/assets/Assets/Isaac/...` -- the Carter v2.4 and its sensors, the two
  animated characters, the warehouse props. NVIDIA publishes it from the Isaac
  Sim download page as `isaac-sim-assets-complete-<version>.zip` (5 parts for
  6.1.0) `[verified: docs.isaacsim.omniverse.nvidia.com/latest/installation/download.html,
  read 2026-09-22]`. Unpack it and point Isaac Sim at it with
  `--/persistent/isaac/asset_root/default="<your path>"`
  `[verified: docs.isaacsim.omniverse.nvidia.com .../installation/install_faq.html, 5.0.0]`.
  The scene's paths are relative, so to use the pack rather than the mirror,
  symlink `range/assets/Assets/Isaac` at the pack's `Isaac` folder.
- **the Omniverse vegetation and base-material content** covers
  `range/assets/Assets/Vegetation/...` and `range/assets/Materials/...`. These
  are served from the same `omniverse-content-production` CDN the script uses;
  the Omniverse Launcher's content exchange carries the vegetation pack.
  `[unverified: the launcher exchange page did not resolve from this
  workstation on 2026-09-22; the CDN paths in the manifest did]`
- **the sky** is Poly Haven's `industrial_sunset_puresky` at 16k. The lab's
  copy of this file and the one Poly Haven serves today are the same bytes --
  SHA-256 `6044c004de79dfb9dc6a614dedaa11c5b5548da9b6252e3599c07505b5f3493c`,
  191 750 746 bytes, MD5 matching the one Poly Haven's API reports -- so it is
  not shipped here. `fetch_assets.py` gets it from
  `https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/16k+/industrial_sunset_puresky_16k.hdr`.

### What does not resolve

54 of the referenced files do not come back from the CDN and are listed under
`"unresolved"` in `range/assets/MANIFEST.json`:

- 48 HTTP 404s. 37 are `OmniPBR.mdl` and `OmniGlass.mdl` next to an asset,
  which Kit resolves out of its own MDL search path instead, and those are
  harmless. Six more are URL templates rather than files -- `<UDIM>` tile
  patterns and paths into a `.usdz` -- belonging to showcase props. The
  remaining five are real textures that NVIDIA's CDN does not serve: three for
  `Golden_Malay_Palm` and two for `Windmill_Palm`, which is why those two
  plants log material errors (see [The headless load](#the-headless-load)).
- 6 are the two characters' `character_behavior.py` scripting paths, which are
  absolute paths into somebody else's Isaac Sim install. See
  [Characters](#characters).

### Characters

Two prims in `sim_world2.usd` carry `omni:scripting:scripts` pointing at
`/opt/isaacsim/ov/pkg/isaac_sim-2023.1.1/extscache/omni.anim.people-0.2.4/omni/anim/people/scripts/character_behavior.py`
-- the machine the scene was authored on. USD has no environment-variable
expansion, so the path has to be written in. Left alone, the characters load
and stand still, and `relink.py --check` prints the two paths as warnings.

```bash
uv run python fetch_assets.py --isaacsim-path ~/isaacsim
```

globs `extscache/omni.anim.people-*/omni/anim/people/scripts/character_behavior.py`
under your install and writes what it finds.

---

## The terrain

The terrain was authored in WorldCreator and exported as a 2048 x 2048 quad
grid in a 467 MB Wavefront OBJ. Only the height column of that file is not
implied by the grid, so this repository ships the heights
(`range/terrain/heightmap.npz`, float32, 14.8 MB) and rebuilds the mesh:

```bash
cd tools
uv run python build_terrain.py                # 4 194 304 points, 129 MB, ~1 s
uv run python build_terrain.py --decimate 8   # 65 536 points, 2.1 MB
```

The rebuilt mesh has the OBJ's point order and face topology exactly, so the
scene's own opinions on `/World/terrain1/terrain_low/mesh` -- the collision
APIs, `physics:approximation = none`, the physics material binding -- still
land on the same prim. Checked against the source OBJ: maximum absolute point
error 1.52e-05 in OBJ units, face indices identical, bounding boxes agreeing
to 8.35e-06.

`terrain_meta.json` records the grid (2048 x 2048, spacing 2 OBJ units, x on
the slow axis and z on the fast one, Y up) and the transform the scene applies
to it, which works out to

```
world x = 0.0242 * obj x + 49.329033      (+1 from /World/terrain1_world)
world y = -0.0237976 * obj z + 49.113726  (+1)
world z = 0.01 * k * obj y                 (k is the DOE height scale)
```

giving a 99.075 x 97.427 m footprint, 9 652.6 m², with 4.84 x 4.76 cm cells
and relief from -1.322 to 5.055 m.

### Measured slope

Slope is the arctangent of the height gradient of each grid cell after the
scene's transform. The grid is 4.8 cm across, so the window matters: a window
of 1 measures the terrain's own roughness, a window of 16 averages the heights
into 77 cm blocks first and measures what a wheel climbs.

| window | cell | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| 1 | 4.8 cm | 11.79° | 31.28° | 38.10° | 51.51° | 84.68° |
| 4 | 19.4 cm | 10.41° | 26.87° | 32.67° | 44.97° | 75.66° |
| 16 | 77.4 cm | 8.95° | 23.62° | 28.31° | 39.70° | 63.70° |
| 32 | 154.9 cm | 8.05° | 21.50° | 25.71° | 35.15° | 50.39° |

`--max-slope-deg T` scales the terrain's height so the 99th percentile comes
out at T. Scaling the height scales every gradient by the same factor and
arctan is monotone, so the scale follows from one percentile of the unscaled
gradient with nothing to search for:

| target | window | height scale | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|
| 15° | 1 | 0.21305 | 2.55° | 7.38° | 9.48° | 15.00° | 66.40° |
| 15° | 16 | 0.32278 | 2.91° | 8.03° | 9.86° | 15.00° | 33.15° |
| 10° | 1 | 0.14020 | 1.68° | 4.87° | 6.27° | 10.00° | 56.42° |
| 10° | 16 | 0.21241 | 1.92° | 5.31° | 6.53° | 10.00° | 23.26° |

---

## The design-of-experiments script

`tools/range_doe.py` writes one USD layer per design point. The layer
sublayers `range/sim_world2.usd`, so opening it opens the whole range with
that design on top and the base scene keeps no state from any run. It is pure
`usd-core`: about 0.6 s of CPU per point, which is what makes a sweep a
distributed campaign rather than a collection of hand-built worlds.

```
--obstacle-density F    fraction of the terrain footprint covered by rock silhouettes
--rock-size M           obstacle footprint diameter in metres (default 2.0)
--rock-size-jitter F    uniform spread around it (default 0.5, so 1 m to 3 m)
--min-spacing-factor F  minimum centre spacing, as a fraction of the median diameter
--max-slope-deg T       scale the terrain height to put the 99th percentile slope at T
--slope-window N        average the heightmap into NxN blocks before measuring slope
--slope-percentile P    which percentile --max-slope-deg targets (default 99)
--friction-static F     PhysicsMaterialAPI on the terrain and the obstacles
--friction-dynamic F
--restitution F
--multi-agr N           N more Carters on a ring around the one in the base scene
--agr-ring-radius M     the ring (default 4.0 m)
--sensor-payload        a Nova Carter as an alternative robot
--seed N
--out PATH.usda
--json                  the full report, including both slope distributions
```

**Obstacles.** Each obstacle references one of the three shipped rock meshes,
scaled so its horizontal silhouette matches a drawn footprint diameter, yawed
at random and seated with its lowest point on the terrain. The silhouette is
computed from the mesh itself: for a closed surface every vertical line
crosses it twice, so the absolute projected area of all its faces is twice the
silhouette. Sizes are drawn first and cut where the covered area reaches the
target, so the count follows from the sizes. Positions come from a jittered
grid -- one obstacle per cell, jogged by at most half the slack between the
cell size and the minimum spacing -- which makes the minimum spacing a
guarantee rather than a hope.

**Physics.** `--friction-*` and `--restitution` define a `Material` with
`PhysicsMaterialAPI` at `/World/doe_physics_material` and bind it as
`material:binding:physics` on the terrain mesh and on every obstacle, over the
base scene's own material.

### The three shipped design points

Generated with `--seed 0` at the terrain's authored height (no
`--max-slope-deg`); `range/doe/doe_manifest.json` has the full reports.

| layer | obstacles | coverage asked | coverage realised | obstacle diameter min/median/max | min spacing guaranteed / measured | slope p50 / p99 | bytes |
|---|---|---|---|---|---|---|---|
| `density_0p1.usda` | 264 | 0.1 | 0.1002 | 1.01 / 2.12 / 2.99 m | 1.061 / 1.482 m | 11.79° / 51.51° | 200 909 |
| `density_0p4.usda` | 1 114 | 0.4 | 0.4004 | 1.00 / 2.04 / 3.00 m | 1.019 / 1.142 m | 11.79° / 51.51° | 845 016 |
| `density_0p8.usda` | 2 285 | 0.8 | 0.8001 | 1.00 / 1.98 / 3.00 m | 0.992 / 1.003 m | 11.79° / 51.51° | 1 731 993 |

### Tests

```bash
cd tools && PYTHONPATH= uv run python -m pytest -q tests
```

22 tests: the silhouette estimator against boxes and against the same boxes
triangulated, the density estimator against the requested coverage, the
minimum-spacing guarantee, the slope scaling against a synthetic ramp and
against the four targets above, the generated layer parsing, its over targets
existing in the base scene, the composed stage reading back the scale and the
obstacle count, and seed reproducibility; plus the heightmap and the built
mesh against their metadata.

`PYTHONPATH=` is there because a sourced ROS 2 environment puts
`launch_testing` on the path and pytest tries to load it as a plugin.

---

## The showcases

`showcases/warehouse_iros_v1.usd` and `showcases/warehouse_nvblox.usd` are
thin scenes over Isaac Sim 4.1 stock warehouse content; the nvblox one adds a
Nova Carter set up for nvblox. They are here because the paper's earlier
demonstrations used them. `fetch_assets.py --group showcases` gets what they
need (1.56 GiB); they are not part of the test range and the DOE script does
not touch them.

---

## The headless load

Measured on this workstation on 2026-09-22 with Isaac Sim **6.0.1-rc.7**,
headless, 60 physics steps, using the local mirror:

| | `range/sim_world2.usd` | `range/doe/density_0p4.usda` |
|---|---|---|
| stage open | 17.1 s | 17.7 s |
| prims | 22 978 | 26 322 |
| meshes | 4 607 | 5 721 |
| rock meshes | 4 | 1 118 (1 114 from the DOE layer) |
| terrain mesh | defined, 4 194 304 points, `physics:approximation = none` | same |
| unresolved references | 0 | 0 |
| physics init | 5.4 s | 8.0 s |
| first physics step | 0.7 s | 17.7 s |
| 60 further steps | 0.13 s | 0.14 s |
| articulation | `/World/Carter_v2_4_ROS/Carter_V24`, 7 DOF | same |

The terrain's cooked collision mesh is not shipped -- it was 750 MB of the
1.5 GB original layer and PhysX regenerates it. The first load on a cold PhysX
cook cache took 164.6 s at `initialize_physics`; with the cache warm it is the
numbers above. The DOE layer's 17.7 s first step is the 1 114 obstacle convex
hulls.

### Errors the load reports

Three families, none of them a missing file in the mirror:

- **`omni.rtx.materials [UsdToMdl] ... References an asset that can not be
  found`**, 25 in the base scene and 41 in the DOE layer. These are the five
  textures belonging to `Golden_Malay_Palm` and `Windmill_Palm` that return
  HTTP 404 from NVIDIA's CDN. Those two plants render with the missing
  roughness and normal maps left at their defaults.
- **`omni.rtx: RTXSensor: Provided Lib 'omni.sensors.nv.lidar.lidar_core.plugin'
  does not implement a supported RTXSensor Interface version`**, with
  `Sensor Model creation failed for RtxSensor`. This is the version boundary:
  the Carter in this scene is the **Isaac Sim 2023.1.0** `Carter_v2_4_ROS`
  asset, and its RTX lidar description is not one Isaac Sim 6.0's lidar plugin
  accepts. The robot, its articulation and its cameras load; the RTX 3D lidar
  does not produce a sensor model. `range_doe.py --sensor-payload` adds a
  4.1-era Nova Carter as the alternative rig for work that needs the lidar.
- **`omni.graph.core.plugin: Articulation controller failed for prim` /
  `No robot prim found for the articulation controller`**, twice, at stage
  open. They fire before physics is initialised; the articulation is found
  afterwards, with 7 degrees of freedom.

---

## What the paper claims, and what is measured here

The paper's Section IV-B.1 describes the range. Read against what this
directory actually contains:

| the paper | here |
|---|---|
| "released as USD assets with the tool chain" | the scene is; NVIDIA's and Poly Haven's content is downloaded, not redistributed |
| "supports multiple AGRs" | `range_doe.py --multi-agr N` adds N more Carters on a ring; the base scene has one |
| "a full multi-modal sensor payload" | the base scene's Carter v2.4 carries 4 Hawk stereo cameras, 4 Owl fisheyes, an XT-32 3D lidar and 2 RPLidars, and publishes a front stereo camera, two 2D lidar scans and one 3D lidar scan over ROS 2. The 3D lidar does not initialise under Isaac Sim 6.0 (above). `--sensor-payload` adds a Nova Carter instead |
| "slopes up to 15°" | reachable with `--max-slope-deg 15`. The terrain as authored is steeper than that: 99th-percentile cell slope 51.5° at 4.8 cm, 39.7° at 77 cm; median 11.8° and 9.0° |
| "obstacle densities swept from 10 to 80 % coverage" | `--obstacle-density 0.1 .. 0.8`; three layers are shipped and the realised coverage is within 0.0004 of the request |
| "tunable PhysX physics (surface friction, restitution, and wheel-terrain contact)" | `--friction-static`, `--friction-dynamic`, `--restitution` write a `PhysicsMaterialAPI` on the terrain and the obstacles. Wheel-terrain contact is that material plus the robot's own wheel material, which is the Carter asset's and is not exposed as a flag |
| "a single Isaac Sim script parameterises the scene and physics" | `tools/range_doe.py`, **built for this release**; it needs `usd-core` only, not Isaac Sim |
| "a DOE over terrain conditions becomes a distributed PERFECT campaign" | not wired to PERFECT here. `range_doe.py` writes a layer and a JSON report; nothing in this directory submits them |

The DOE script, the heightmap pipeline, the asset manifest and the fetch and
relink tooling were built for this release. The scene, the terrain and the
showcases are the lab's earlier authoring, compacted and relinked.

---

## Licensing

- The scene layers, the heightmap, `terrain_meta.json`, the DOE layers and
  everything in `tools/` are the lab's, under the repository's licence.
- The three rock meshes came from a free asset pack the authoring machine had;
  their origin is recorded only as the directory names in the original file
  (`uploads_files_2886016_Free+rock`, `uploads_files_2372587_Rock_5`,
  `uploads_files_2372785_Rock_9`). `[unverified: no licence text travelled
  with them]`
- Everything `fetch_assets.py` downloads from
  `omniverse-content-production.s3-us-west-2.amazonaws.com` is NVIDIA's and
  stays under NVIDIA's own terms. Nothing of it is redistributed here; the
  manifest records URLs and hashes only. `[unverified: the NVIDIA Omniverse
  licence text did not fetch from this workstation on 2026-09-22 -- three
  mirrors returned 403 or a navigation stub]`
- `industrial_sunset_puresky_16k.hdr` is Poly Haven's, CC0 on their site. It
  is fetched, not shipped.

---

## The tools

| script | what it does |
|---|---|
| `fetch_assets.py` | downloads and verifies the external content; `--build-manifest` crawls the scene and writes the manifest; `--regroup` re-labels it from a local mirror; `--isaacsim-path` fixes the character scripting paths |
| `build_terrain.py` | rebuilds the terrain mesh from the heightmap; `--from-obj` re-extracts the heightmap from the source OBJ |
| `range_doe.py` | writes one design point as a USD layer |
| `relink.py` | lists, checks and rewrites a layer's external asset paths; `--mode local\|cloud` swaps between the mirror and the CDN |
| `compact.py` | rewrites a layer into a fresh crate, optionally dropping an attribute family |
| `set_attrs.py` | sets attribute defaults from a JSON table |
| `manifest.py` | sizes and hashes of a directory |

### How the layers here were produced

From the lab's originals, in this order: drop the dead reference entries that
recorded the authoring machine's directory layout; rewrite the terrain's
`./terrain1/terrain_low.obj` reference to `./generated/terrain_low.usd` and
the 23 rock `.obj` references to the shipped `.usd` equivalents, which carry
the same meshes (737 / 391 / 393 points, identical bounding boxes) and compose
to the same prim paths; set the teleop graph's differential-drive constants to
the Carter's; rewrite the CDN URLs to the local mirror; then rewrite each
layer into a fresh crate, dropping the four `physxCookedData` attributes.

| layer | before | after |
|---|---|---|
| `range/terrain1_world.usd` | 1 504 262 884 | 383 613 |
| `range/sim_world2.usd` | 180 193 938 | 9 558 |
| `showcases/warehouse_iros_v1.usd` | 3 171 436 | 3 167 398 |

A spec-by-spec, field-by-field comparison of each layer before and after the
compaction reports every spec and every field identical, apart from the four
removed `physxCookedData` attributes (35 149 -> 35 145 specs, 126 542 fields
equal on the terrain layer).

The teleop graph's differential controller carried TurtleBot3 constants on a
Carter. They now match NVIDIA's own `Carter_v2_4_ROS.usd` differential
controller, read out of the asset:

| input | was | now |
|---|---|---|
| `wheelRadius` | 0.025 | 0.28 |
| `wheelDistance` | 0.16 | 0.413 |
| `maxLinearSpeed` | 0.22 | 1.8 |
| `maxAngularSpeed` | unauthored | 1.2 |

Six of the 27 rock instances have their mesh deactivated in the original
scene and three more have the mesh prim itself deactivated, so 18 render.
That is the scene's own authoring and the compaction preserves it.
