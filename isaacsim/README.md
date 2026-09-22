# The IDDMBSE Isaac Sim test range

The contested-terrain test range the IDDMBSE paper's demonstrations run on: a
99 x 97 m off-road site in NVIDIA Isaac Sim with a Carter v2.4 carrying a
multi-modal sensor payload, vegetation, rocks, two walking characters, a water
feature and a warehouse platform, plus a script that turns the site into a
design of experiments over obstacle density, slope and PhysX contact
parameters, and a driver that runs that design of experiments as a PERFECT
campaign.

**What is in git is the scene, not the content it stands on.** What ships here
is 28 MB. The vegetation, the materials, the characters and the robot are
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

and open `range/doe/run07.usda`, which sublayers the base scene. To run a grid
of design points through PERFECT instead, see [The campaign](#the-campaign).

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
| `range/doe/density_0p{1,4,8}.usda` | 293 312 / 1 234 922 / 2 531 747 | three generated design points |
| `range/doe/paper_baseline.usda` | 950 703 | the baseline design point the campaign runs |
| `range/doe/doe_manifest.json` | 6 066 | what each of the four measured |
| `results/` | 1 307 566 | the campaign table, its two figure pairs and the eight pose trajectories |
| `range/assets/MANIFEST.json` | 2 305 198 | every external file the scene needs: url, size, SHA-256, and which part of the repository needs it |
| `showcases/warehouse_iros_v1.usd` | 3 167 398 | a warehouse showcase scene |
| `showcases/warehouse_nvblox.usd` | 5 751 | a warehouse showcase set up for nvblox |
| `thumbnails/*.png` | 378 644 | three viewport captures |
| `warehouse/` | 8 816 972 | the cluttered warehouse with the Nova Carter and Nav2: layers, map, scripts, the recorded run. See [The warehouse](#the-warehouse) |
| `tools/*.py` | 115 922 | the scripts this file documents |
| `.gitignore`, `MANIFEST.json` | | what the tools write, and sizes and hashes of everything above |

Without `warehouse/`, 50 files, 27.9 MB. `MANIFEST.json` gives the size and SHA-256 of 47 of them --
it does not describe itself, `README.md`, or the download manifest -- and adds
up to 25 586 434 bytes. Largest shipped file: `range/terrain/heightmap.npz`,
14 804 748 bytes. Nothing shipped here is over 20 MB.

Not in git, written by the tools, listed in `.gitignore`:
`range/assets/` (4.9 GiB downloaded), `range/HDRI/` (183 MB downloaded),
`range/generated/` (129 MB built), `range/doe/runs/` (one directory per
PERFECT trial) and `warehouse/generated/` (built by `warehouse/fetch_warehouse.py`).

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
  Sim download page as `isaac-sim-assets-complete-<version>.zip`, five parts
  for 6.1.0 (`docs.isaacsim.omniverse.nvidia.com/latest/installation/download.html`).
  Unpack it and point Isaac Sim at it with
  `--/persistent/isaac/asset_root/default="<your path>"`
  (`.../installation/install_faq.html`). The scene's paths are relative, so to
  use the pack rather than the mirror, symlink `range/assets/Assets/Isaac` at
  the pack's `Isaac` folder.
- **the Omniverse vegetation and base-material content** covers
  `range/assets/Assets/Vegetation/...` and `range/assets/Materials/...`. These
  are served from the same `omniverse-content-production` CDN the script uses,
  and the Omniverse Launcher's content exchange carries the vegetation pack.
  The CDN paths in the manifest are the ones this repository fetches and
  checks.
- **the sky** is Poly Haven's `industrial_sunset_puresky` at 16k. The lab's
  copy of this file and the one Poly Haven serves today are the same bytes --
  SHA-256 `6044c004de79dfb9dc6a614dedaa11c5b5548da9b6252e3599c07505b5f3493c`,
  191 750 746 bytes, MD5 matching the one Poly Haven's API reports -- so
  `fetch_assets.py` gets it straight from Poly Haven,
  `https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/16k+/industrial_sunset_puresky_16k.hdr`.

### What the fetch leaves to Kit

54 of the referenced files are listed under `"unresolved"` in
`range/assets/MANIFEST.json`, and the script skips them:

- 37 are `OmniPBR.mdl` and `OmniGlass.mdl` next to an asset. Kit resolves those
  out of its own MDL search path.
- 6 are URL templates rather than files -- `<UDIM>` tile patterns and paths
  into a `.usdz` -- belonging to showcase props, which Kit expands itself.
- 5 are textures for `Golden_Malay_Palm` and `Windmill_Palm`. Those two plants
  render with their roughness and normal maps at the material defaults, and the
  load logs one line per texture (see [The headless load](#the-headless-load)).
- 6 are the two characters' `character_behavior.py` scripting paths, which
  point into the Isaac Sim install of the machine the scene was authored on.
  `fetch_assets.py --isaacsim-path` writes yours instead; see
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
base scene's own material. Each obstacle's mesh also gets
`PhysicsCollisionAPI` and `PhysicsMeshCollisionAPI` with
`physics:approximation = convexHull`, applied by the layer: the rock assets
carry geometry only, so without it the obstacles would be scenery and a robot
would drive through them.

**Where the robot starts.** `--agr-start-x` and `--agr-start-y` move the base
scene's AGR and seat it on the terrain, `--agr-clearance` above the surface.
`--agr-keepout-radius` (3 m by default) is a clear disc around wherever the AGR
starts: the grid cells that could put a rock inside it are taken out of the
draw before the rocks are dealt, so the obstacle count and the realised
coverage are unchanged and nothing is spawned on top of the robot.

### The four shipped design points

The three density layers are generated with `--seed 0` at the terrain's
authored height (no `--max-slope-deg`); `paper_baseline.usda` is the design
point the campaign below uses. `range/doe/doe_manifest.json` has the full
reports.

| layer | obstacles | coverage asked | coverage realised | obstacle diameter min/median/max | min spacing guaranteed / measured | slope p50 / p99 | bytes |
|---|---|---|---|---|---|---|---|
| `density_0p1.usda` | 264 | 0.1 | 0.1002 | 1.01 / 2.12 / 2.99 m | 1.061 / 1.163 m | 11.79° / 51.51° | 293 312 |
| `density_0p4.usda` | 1 114 | 0.4 | 0.4004 | 1.00 / 2.04 / 3.00 m | 1.019 / 1.097 m | 11.79° / 51.51° | 1 234 922 |
| `density_0p8.usda` | 2 285 | 0.8 | 0.8001 | 1.00 / 1.98 / 3.00 m | 0.992 / 1.028 m | 11.79° / 51.51° | 2 531 747 |
| `paper_baseline.usda` | 857 | 0.3 | 0.3003 | 1.01 / 1.99 / 3.00 m | 0.997 / 1.169 m | 2.55° / 15.00° | 950 703 |

`paper_baseline.usda` is `--obstacle-density 0.3 --max-slope-deg 15
--friction-static 0.6 --friction-dynamic 0.5 --restitution 0.1 --seed 7
--agr-start-x -18.75 --agr-start-y -5.31`: height scale 0.21305, the AGR seated
at z 0.5469.

### Tests

```bash
cd tools && PYTHONPATH= uv run python -m pytest -q tests
```

49 tests. On the design points: the silhouette estimator against boxes and
against the same boxes triangulated, the density estimator against the
requested coverage, the minimum-spacing guarantee, the slope scaling against a
synthetic ramp and against the four targets above, the generated layer parsing,
its over targets existing in the base scene, the composed stage reading back the
scale and the obstacle count, every obstacle carrying a convex-hull collider,
the keep-out holding at all three densities, the AGR start seated on the terrain
and the scale it was computed at, and seed reproducibility. On the campaign
driver: the grid expansion and the distinctness of the point names, the CLI
setup commands, the `/api/v1` payloads and the wait against a stand-in server,
the last-value-wins rule for relayed metrics, the CSV round trip and the
trajectory copies. Plus the heightmap and the built mesh against their
metadata. Nothing in the suite opens a socket or starts Isaac Sim.

`PYTHONPATH=` is there because a sourced ROS 2 environment puts
`launch_testing` on the path and pytest tries to load it as a plugin.

---

## The campaign

`tools/range_campaign.py` turns a grid of design points into a PERFECT
campaign: one environment per design point, one design per AGR variant, one
experiment each, run and read back through PERFECT's `/api/v1`. The PERFECT
side of it -- the component library, the environment template and the
experiment class that launches headless Isaac Sim -- is
`perfect/examples/isaacsim-range/`, which has its own README.

```bash
cd tools
uv run python range_campaign.py --plan
python range_campaign.py --submit --project-root <perfect>/examples/isaacsim-range \
    --densities 0.1,0.4,0.8 --slopes 15,25 --duration 30 --robots "Carter v2.4"
uv run python range_campaign.py --collect --out ../results/campaign.csv
uv run python range_campaign.py --plot    --out ../results/campaign.csv
```

`--plan` prints the grid. `--submit` creates the database, loads the component
implementations, creates the designs, loads the environment template, creates
one environment per design point, then POSTs one experiment per point and waits,
bounded by `--timeout`, until every trial is in a terminal state. It runs in
the PERFECT environment, because the setup goes through the Flask CLI; the
other two run here, because they need numpy and matplotlib. `--collect` reads
every trial's updates back through the API, keeps the last value of each metric
and writes one row per trial. `--plot` writes the two figure pairs.

A trial writes its design point, its pose trajectory, its metrics and its
simulator log to `range/doe/runs/trial_<id>/`, which is not in git.

### The campaign that was run here

Eight trials on 2026-09-22 through a PERFECT stack on Redis 6390, Flask 5001
and the runner on 8003, each one a headless Isaac Sim 6.0.1 process started by
the runner's job: densities 0.1, 0.4 and 0.8 crossed with 99th-percentile slope
targets of 15 and 25 degrees, plus the shipped `paper_baseline.usda` design
point and one run at the terrain's authored relief. Friction 0.6 / 0.5,
restitution 0.1, seed 7, 30 simulated seconds each, one AGR driven open loop at
0.6 m/s with a 0.3 rad/s yaw sweep. Every trial reached
`TrialState.SUCCESSFUL|SHUT_DOWN`.

| trial | density | slope | obstacles | distance m | mean speed m/s | max pitch | max roll | max climb m | encounters | stuck | wall / sim s | trial wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.1 | 15° | 285 | 12.99 | 0.43 | 16.3° | 14.5° | 0.738 | 0 | no | 0.187 | 42.9 |
| 2 | 0.1 | 25° | 285 | 9.72 | 0.32 | 16.9° | 15.8° | 0.334 | 0 | no | 0.213 | 42.8 |
| 3 | 0.4 | 15° | 1147 | 13.45 | 0.45 | 16.3° | 14.5° | 0.738 | 3 | no | 0.179 | 41.8 |
| 4 | 0.4 | 25° | 1147 | 9.72 | 0.32 | 16.9° | 15.8° | 0.334 | 0 | no | 0.201 | 42.5 |
| 5 | 0.8 | 15° | 2267 | 3.21 | 0.11 | 7.3° | 6.3° | 0.011 | 0 | yes, 4.2 s | 0.181 | 41.8 |
| 6 | 0.8 | 25° | 2267 | 5.54 | 0.18 | 11.7° | 8.8° | 0.017 | 0 | no | 0.208 | 43.1 |
| 7 | 0.3 | 15° | 857 | 13.20 | 0.44 | 18.3° | 29.7° | 0.674 | 2 | no | 0.182 | 42.5 |
| 8 | 0.1 | authored | 285 | 3.71 | 0.12 | 17.9° | 179.0° | 0.542 | 0 | no | 0.383 | 48.6 |

"encounters" counts the distinct DOE obstacles the AGR came within 1.5 m of;
"stuck" is the longest stretch below 0.05 m/s when it runs past 2 s.

At the 15 degree target the AGR covers about 13 m of the 30 s run at the two
lower densities and 3.2 m at 0.8, where it spends 4.2 s below 0.05 m/s: at that
density the rock centres are about a metre apart. The 25 degree target costs
about a quarter of the distance at the lower densities and, at density 0.1,
takes the mean pitch from 6.3 to 10.8 degrees. At the terrain's authored relief the traverse ends
with a maximum roll of 179 degrees after 3.7 m. Trials 2 and 4 return the same
numbers because neither traverse touched an obstacle; 1 and 3 differ where
trial 3's three contacts redirected it.

`results/campaign.csv` is the table, one row per trial with every relayed
metric; `results/trajectories/trial_<id>.csv` are the pose trajectories, one
row per physics step. The figures are `results/campaign_metrics.svg`/`.pdf`
(distance and maximum pitch against obstacle density, one line per slope
target) and `results/campaign_trajectories.svg`/`.pdf` (the eight traverses
over the terrain, coloured by density and dashed by slope target).

The eight trials took 346 s of the campaign's 411 s; the rest is the database,
the component library, the designs, the environments and the eight API calls.

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

Isaac Sim **6.0.1-rc.7**, headless, on the local mirror, 2026-09-22. The base
scene column is one load of `range/sim_world2.usd`; the design-point column is
the eight trials of [the campaign](#the-campaign), whose layers carry 285 to
2 267 obstacles.

| | `range/sim_world2.usd` | the campaign's design points |
|---|---|---|
| stage open | 14.2 s | 13.8 to 14.2 s |
| prims | 22 978 | 23 835 / 26 421 / 29 781 at density 0.1 / 0.4 / 0.8 |
| meshes | 4 607 | 4 892 to 6 874 |
| terrain mesh | defined, 4 194 304 points, `physics:approximation = none` | same |
| unresolved references | 0 | 0 |
| physics init | 4.5 s | 5.75 to 6.14 s |
| first physics step | 0.67 s | 6.91 to 7.29 s |
| 60 further steps | 0.09 s | -- |
| articulation | `/World/Carter_v2_4_ROS/Carter_V24`, 7 DOF | same |
| wall per simulated second | -- | 0.179 to 0.383 s |

The articulation's seven degrees of freedom are `joint_caster_base`,
`joint_swing_left`, `joint_swing_right`, `joint_wheel_left`,
`joint_wheel_right`, `joint_caster_left` and `joint_caster_right`; the two
wheel joints are the ones the campaign drives.

PhysX cooks the terrain's collision mesh on the first load and caches it. That
cooked buffer was 750 MB of the 1.5 GB original layer, and leaving PhysX to
regenerate it is what makes `terrain1_world.usd` 384 kB. On a cold cook cache
the first load spends 164.6 s in `initialize_physics`; with the cache warm it
is the numbers above, and the same cook serves every terrain height scale, so
the slope knob costs nothing extra.

### The sensors the load finds

On the base scene, from the loaded stage:

| | |
|---|---|
| cameras on the robot | 15 `UsdGeom.Camera` prims: the left and right eye of the four Hawk stereo rigs (`front`, `left`, `right`, `back`), the four Owl fisheyes, the two `RPLIDAR_S2E` and the `PandarXT_32_10hz` |
| lidar prims | 11 under `chassis_link`: the two `front`/`rear_RPLidar` rigs with their meshes, the two `Carter_Sen_Pos_Ctrl_Doc/RPLidar_S2E` placements and the XT-32 |
| ROS 2 publisher nodes | 9 in the scene's own OmniGraph: `ROS2PublishClock` on `clock`, four `ROS2PublishImu` on `front`/`left`/`rear`/`right_stereo_camera/imu/data`, `ROS2PublishOdometry`, `ROS2PublishRawTransformTree` and two `ROS2PublishTransformTree` |

The campaign does not use them: `sim_trial.py` deactivates `/World/teleop` and
`/World/ROS_Clock` and drives the wheel joints directly, so a trial needs no
ROS 2 graph at all.

### Errors the load reports

Three families, all of them expected on a complete mirror:

- **`omni.rtx.materials [UsdToMdl] ... References an asset that can not be
  found`**, 25 of them in the base scene. These are the five textures belonging
  to `Golden_Malay_Palm` and `Windmill_Palm` that NVIDIA's CDN does not serve.
  Those two plants render with their roughness and normal maps at the material
  defaults.
- **`omni.rtx: RTXSensor: Provided Lib 'omni.sensors.nv.lidar.lidar_core.plugin'
  does not implement a supported RTXSensor Interface version`**, with
  `Sensor Model creation failed for RtxSensor`. This is the version boundary:
  the Carter in this scene is the **Isaac Sim 2023.1.0** `Carter_v2_4_ROS`
  asset, and its RTX lidar description is not one Isaac Sim 6.0's lidar plugin
  accepts, so no sensor model is created for it. The robot, its articulation
  and the camera prims listed above load and the campaign drives the robot
  from them. `range_doe.py --sensor-payload` places a Nova Carter instead, from
  the Isaac Sim 4.1 asset in the `showcases` fetch group.
- **`omni.graph.core.plugin: Articulation controller failed for prim` /
  `No robot prim found for the articulation controller`**, twice, at stage
  open. They fire before physics is initialised; the articulation is found
  afterwards, with 7 degrees of freedom.

---

## What runs here

| part | what it is |
|---|---|
| the range as USD | `range/sim_world2.usd` and the layers beside it are in this repository; NVIDIA's and Poly Haven's content is downloaded to your machine by `fetch_assets.py` and picked up from there |
| the AGR | a Carter v2.4 at `/World/Carter_v2_4_ROS/Carter_V24`, a 7-degree-of-freedom articulation. `range_doe.py --multi-agr N` puts N more on a ring around it, and `--agr-start-x/-y` seats it anywhere on the terrain |
| the sensor payload | the Carter v2.4 asset carries four Hawk stereo rigs, four Owl fisheye cameras, an XT-32 3D lidar and two RPLidars. A headless load of the base scene under Isaac Sim 6.0 finds 15 camera prims on the robot, 11 lidar prims and nine ROS 2 publisher nodes: [The sensors the load finds](#the-sensors-the-load-finds) |
| slope | `--max-slope-deg T` scales the terrain height so the 99th-percentile cell slope comes out at T. The terrain as authored measures 51.5° at the 4.8 cm cell and 39.7° at 77 cm, median 11.8° and 9.0°; at `--max-slope-deg 15` the height scale is 0.213 and the median falls to 2.6° |
| obstacle density | `--obstacle-density 0.1 .. 0.8`; the realised coverage is within 0.0004 of the request, and every obstacle is a static convex-hull collider |
| PhysX contact | `--friction-static`, `--friction-dynamic` and `--restitution` write a `PhysicsMaterialAPI` at `/World/doe_physics_material` and bind it on the terrain mesh and on every obstacle. The wheel side of the contact is the Carter asset's own wheel material |
| one script for the scene and the physics | `tools/range_doe.py`: one design point is one USD layer, about 0.6 s of CPU, `usd-core` only |
| the DOE as a PERFECT campaign | `tools/range_campaign.py` turns the grid into PERFECT designs, environments and experiments and reads the trials back. See [The campaign](#the-campaign) |

The DOE script, the campaign driver, the heightmap pipeline, the asset manifest
and the fetch and relink tooling were built for this release. The scene, the
terrain and the showcases are the lab's earlier authoring, compacted and
relinked.

---

## The warehouse

`warehouse/` is a second scene, for demonstrations of the autonomy stack inside
Isaac Sim: NVIDIA's Isaac Sim 6.0 ROS 2 navigation sample -- the simple
warehouse and a Nova Carter with its ROS 2 graphs -- under the authors' own
layers, which add four walking workers and 17 loaded-pallet and crate groups
from NVIDIA's SimReady catalogue, with an occupancy map baked from the scene, a
Nav2 configuration for ROS 2 Jazzy, and scripts that run it all in a headless
Isaac Sim streamed over WebRTC. [warehouse/README.md](warehouse/README.md) has
the commands and the full record of the run; in short:

```bash
cd warehouse
uv run --project ../tools python fetch_warehouse.py   # builds generated/ from ISAACSIM_ASSET_ROOT or NVIDIA's cloud copy
./launch_stream.sh                                    # Isaac Sim in tmux iddmbse-kit, WebRTC on port 49100
python3 tools/open_scene.py
./nav2/start_nav2.sh                                  # Nav2 in tmux iddmbse-nav2, ROS 2 domain 87, rmw_fastrtps_cpp
python3 nav2/send_goal.py --initial-pose X Y YAW_DEG
./stop.sh
```

`fetch_warehouse.py` reads the two NVIDIA sample files from the asset root and
rewrites their four relative asset paths, so the repository carries only the
authored layers. Run here on Isaac Sim 6.0.1-rc.7: the scene opened with 7 002
prims and all 17 groups composed; the Occupancy Map Generator gave a 479 x 776
map at 0.05 m; Nav2 took the Carter to all three waypoints -- three SUCCEEDED
results, 27.4 m of odometry in 335 simulated seconds -- and
`warehouse/results/warehouse_nav_chase.mp4` (28.75 s) shows the drive from a
following camera.

---

## Licensing

- The scene layers, the heightmap, `terrain_meta.json`, the DOE layers and
  everything in `tools/` are the lab's, under the repository's licence.
- The three rock meshes came from a free asset pack the authoring machine had.
  Their origin is recorded as the directory names in the original file:
  `uploads_files_2886016_Free+rock`, `uploads_files_2372587_Rock_5`,
  `uploads_files_2372785_Rock_9`. No licence text travelled with them.
- Everything `fetch_assets.py` downloads from
  `omniverse-content-production.s3-us-west-2.amazonaws.com` is NVIDIA's and
  stays under NVIDIA's own terms. Nothing of it is redistributed here; the
  manifest records URLs and hashes only.
- `industrial_sunset_puresky_16k.hdr` is Poly Haven's, CC0 on their site.
  `fetch_assets.py` downloads it from Poly Haven.

---

## The tools

| script | what it does |
|---|---|
| `fetch_assets.py` | downloads and verifies the external content; `--build-manifest` crawls the scene and writes the manifest; `--regroup` re-labels it from a local mirror; `--isaacsim-path` fixes the character scripting paths |
| `build_terrain.py` | rebuilds the terrain mesh from the heightmap; `--from-obj` re-extracts the heightmap from the source OBJ |
| `range_doe.py` | writes one design point as a USD layer |
| `range_campaign.py` | turns a grid of design points into a PERFECT campaign, reads the trials back into a CSV and plots them |
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
