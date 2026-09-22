# MATLAB workbench

The MATLAB side of the 2023-24 SysML work: the two functions the SysML model calls, the
design-space scripts that scored the results, and the CSVs and plots they produced.
These are the originals, kept as the record of how the bridge worked. The Python port of
the Pareto and MAVF scoring lives in `trades-x/`.

Nothing here has been run on this workstation; there is no MATLAB on it. Treat every
script as 2024 code that has not been re-executed since.

## How the bridge worked

1. A row of a SysML instance table (a sensor configuration, or a planner plus
   environment) is fed to a simulation configuration in the `PerfECT Analysis` package.
2. Magic Model Analyst evaluates the constraint block bound to it. The constraint is an
   opaque expression whose language is `Matlab`, so the engine hands it to MATLAB:
   `mat_out_sen = MatSensorTrade(Amod,Arate,...)` or
   `mat_out = roslaunchtrade(envkey,lpkey,gpkey)`.
3. The MATLAB function turns the numeric keys into names (`d435`, `vlp16`,
   `teb_local_planner/TebLocalPlannerROS`, `orchard`, ...), builds a struct, and POSTs it
   as JSON to the PERFECT server's `/run` endpoint with `webwrite`.
4. PERFECT launches the ROS 1 stack (`ros1-husky-config/navigation.launch`) with those
   launch arguments or that sensor update, records a rosbag, and the scripts in
   `rosbag/` score it afterwards.

Both functions return a hard-coded `1.0`. The measured result never came back through
the bridge; it came back as rosbags that were scored offline. That is the honest shape of
the 2023-24 loop.

The POST body has two shapes:

- `{"launch_file": ..., "launch_args": {"base_global_planner": ..., "base_local_planner": ..., "domain": ...}}`
  -- `roslaunchtrade.m`
- `{"launch_file": ..., "sensor_update": {"laser_3d": {...}, "camera": {...}, "laser_2d": {...}, "depth_camera": {...}}}`
  -- `MatSensorTrade.m`. The `sensor_update` keys match the top-level keys of
  `../ros1-husky-config/sensor.yaml`.

**[unverified]**: the `perfect/` snapshot in this repository (2025) is a Flask app whose
routes are blueprint-scoped (`/experiments/run/<id>`, `/experiments/run_locally`, ...).
It has no bare `/run` endpoint taking a `launch_file`. The server these scripts talked to
in 2023-24 was an earlier PERFECT. The closest thing in the current tree is
`perfect/examples/SEILR1/experiment.py`, which consumes a sensor YAML of the same shape
and launches the same workspace, so the configuration vocabulary carried over even though
the endpoint did not.

## Substitutions made here

The originals hard-coded the lab's server (a host on the 10.229 subnet, port 5000) and
one user's absolute workspace path. Both were replaced with environment variables, in
`bridge/MatSensorTrade.m`, `bridge/roslaunchtrade.m`, `bridge/testhttpPost.m` and (inside
the commented-out block) `bridge/DemoMatFun.m`:

| variable | default when unset | replaces |
|---|---|---|
| `PERFECT_SERVER_URL` | `http://127.0.0.1:5000` | the lab server's address |
| `AUTO_STACK_WS` | `~/auto_stack_ws` | the absolute path to the ROS 1 workspace |

The pattern in every file is:

```matlab
server = string(getenv("PERFECT_SERVER_URL"));
if strlength(server) == 0
    server = "http://127.0.0.1:5000";
end
uri = matlab.net.URI(server + "/run");

ws = string(getenv("AUTO_STACK_WS"));
if strlength(ws) == 0
    ws = "~/auto_stack_ws";
end
launch_file = ws + "/src/hardware_launch/launch/navigation_rosbridge.launch";
```

`AUTO_STACK_WS` follows the convention `perfect/examples/SEILR1/experiment.py` already
uses (`WS_PATH = os.environ["SEILR1_WS"]`), except that it has a default instead of
raising.

One more line was deleted from `MatSensorTrade.m` and `roslaunchtrade.m`: a
commented-out `s = struct(...)` naming a different lab member's home directory and an
older launch file (`navigation.launch` with `timeout` 600 and launch arguments
`rtabmap_viz`, `camera`, `lidar3d`, `slam2d`, `icp_odometry`). Those same launch
arguments survive in `bridge/testhttpPost.m`, so nothing was lost.

Nothing else in any script was changed. The scripts in `dse/`, `rosbag/` and the files in
`../ros1-husky-config/` contained no addresses or absolute paths to scrub (checked with
`grep -nE '10\.229\.|/home/|C:\\'`, which returned nothing on all of them).

## The files

### `bridge/`

| file | what it does |
|---|---|
| `MatSensorTrade.m` | the sensor trade study. 15 arguments (depth camera model/rate/FoV/resolution, camera, 2D laser, 3D lidar), maps model keys to `d415`/`d435`/`d455` and `vlp16`/`hdl32e`, POSTs a `sensor_update`. Returns 1.0. |
| `roslaunchtrade.m` | the autonomy-configuration trade study. Maps keys to environment (`inspection`/`playpen`/`orchard`/`agriculture`), local planner (DWA/TEB/Trajectory Rollout) and global planner (`navfn/NavfnROS`/`global_planner/GlobalPlanner`), POSTs them as `launch_args`. Returns 1.0. |
| `testhttpPost.m` | the scratch POST the two functions were derived from: one launch file and five boolean launch arguments. Useful as the minimal example of the request. |
| `DemoMatFun.m` | the teaching stub used on the demo diagrams: takes four parameters and sums them, with the whole HTTP path commented out. As delivered, its last line reads `mat_fun_out = 1parA1+parA2+parB1+parB2`, which is not valid MATLAB (a stray `1`). Left as delivered; it is a stub, and fixing it is a modelling decision, not a packaging one. |

Both trade functions also build a `dictionary(...)` object they never use, and
`MatSensorTrade.m` builds `Dmod_dict` from the wrong key/value pair
(`dictionary(Amod_keys, Amodels)` where `Dmod_keys, Dmodels` was meant). Neither affects
the POST, which uses the plain arrays. Left as delivered.

### `dse/`

| file | what it does |
|---|---|
| `mbo_trial1.m` | reads `results/plot4met.csv`, applies the Pareto filter `prtp` (defined at the bottom of the file), writes `pareto_designs.csv` and `pareto_design_evals.csv` |
| `pareto.m` | the same filter applied to a `RESULTS` matrix in the workspace, plus the 3-D scatter of cost, battery life and charging time |
| `pareto_mavf_behav.m` | despite the name, no MAVF in it: reads every bag in the relative folder `LatestBags`, plots the `/odometry/filtered` trajectories, and computes three behavioural metrics per run -- path length relative to an oracle run, time to completion, and cumulative elevation change. It will not run as delivered: `arclen_oracle` is only defined in the oracle block at the top, which is commented out |
| `cost_dummy.m` | enumerates the 4x4x2x3 sensor cost combinations used as a placeholder cost model |

### `rosbag/`

| file | what it does |
|---|---|
| `rosbageval_perfect.m` | reads every bag in the relative folder `SensorBags`, extracts `/odometry/filtered`, computes time to completion and path length, and applies the Pareto filter `prtp` (defined at the bottom of the file, same as in `dse/mbo_trial1.m`) |
| `MBO_rosbag_evals.m` | the same over the MBO run bags, with the multi-attribute value function added |
| `MBO_rosbag_statisticalMAVF_evals.m` | the statistical version: 3 runs per configuration, goals listed in a comment, single-attribute value functions per metric combined into an MAVF with weights `[0.5 0.5]`, and the best configuration taken as the maximum |
| `rosbagreadtest.m` | the first read of a single bag (`test_run_1-001.bag`), kept because it documents the topic names |

The bags themselves are not in the drop and are not shipped. All four scripts use the
relative folder `SensorBags`, so they expect the bags beside them.

### `results/`

`plot3met.csv` (8191 rows x 3 columns) and `plot4met.csv` (4095 rows x 4 columns) are
the design evaluation matrices, one design per row, one measure of effectiveness per
column, with the measures to be maximised already negated. `mbo_trial1.m` reads
`plot4met.csv` and writes the two outputs of `prtp`: `pareto_design_evals.csv` (96 rows x
4 columns, the non-dominated rows) and `pareto_designs.csv` (1 row x 96 columns, their
row indices into `plot4met.csv`). `pareto2.svg` and `paretoplot.svg` are the plots.

The MAVF is only in `rosbag/MBO_rosbag_evals.m` and
`rosbag/MBO_rosbag_statisticalMAVF_evals.m`; the `dse/` scripts stop at the Pareto
front.

The drop also held `plot4met (2).csv`, `pareto_designs (2).csv` and
`pareto_design_evals (2).csv`. Each is byte-identical to its sibling (`cmp` reports no
difference; see `analysis-scratch/packaging/C-gate.txt`), so only one copy of each is
shipped.

## Left out of the repository

| left out | why |
|---|---|
| `untitled.m`, `untitled2.m`, `untitled6.m`, `untitled8.m`, `untitled10.m` | unnamed scratch drafts |
| `roslaunchtrademat.m` | a 302-byte stub that calls an undefined `m5` |
| `DemoMatFun.asv` | MATLAB editor autosave of `DemoMatFun.m` |
| `perfect_snippet.py` | a Python 2 `urllib2` rosbridge publish snippet whose JSON body is malformed |
| `testhttp.m` | a six-line bare GET against the server's `/publish` endpoint with no payload. The only thing it records is that the server exposed `/publish` as well as `/run`, which is written down here instead. |
| `testimg.mat` | a 676 KB binary MAT file with no script referring to it |
| `pareto2.jpg`, `paretoplot2.jpg` | raster duplicates of the two SVG plots |
| `plot4met (2).csv`, `pareto_designs (2).csv`, `pareto_design_evals (2).csv` | byte-identical duplicates |

All of them are kept, unmodified, at
`/mnt/sabrent-ssd/sandeep/research/iddmbse/sysml-iddmbse_v2-original/iddmbse_v2/`.
