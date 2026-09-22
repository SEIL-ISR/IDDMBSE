# The cluttered warehouse

A second Isaac Sim scene for in-simulation demonstrations of the autonomy
stack: NVIDIA's Isaac Sim 6.0 ROS 2 navigation sample -- the simple warehouse
and a Nova Carter with its ROS 2 graphs -- under three layers of the authors'
own: a warehouse layout layer, four walking workers, and 17 loaded-pallet and
crate groups from NVIDIA's SimReady catalogue spread over the floor. Beside the
scene are an occupancy map baked from it, a Nav2 configuration that runs on the
host's ROS 2 Jazzy, a goal script that drives the Carter through the clutter,
and the scripts that run all of it in a headless Isaac Sim you watch over
WebRTC.

## What is here

| path | what |
|---|---|
| `layers/carter_warehouse_clutter_v2.usda` | the root layer: the 17 pallet and crate groups under `/World/CbaseWarehouseMaze/ClutterV2`, each a reference to a SimReady asset URL with a static collider on every mesh; switches the layout layer's rack grid off |
| `layers/carter_warehouse_animated.usda` | the four workers (NVIDIA's `People/Characters` with a wander behaviour and NVIDIA's human motion library), an overview camera, a NavMesh volume |
| `layers/carter_warehouse_maze.usda` | the layout layer over the NVIDIA sample: a rack, crate and cone grid (off in this scene) and the Carter's graph fixes |
| `layers/carter_warehouse_people.usda` | the layout layer with a NavMesh volume only, a lighter root without the clutter |
| `layers/clutter_layout.json` | the 17 groups: name, asset, position, yaw |
| `fetch_warehouse.py` | builds `generated/`: the two NVIDIA sample files and the four layers, with the asset root filled in |
| `launch_stream.sh`, `stop.sh` | start a headless streaming Isaac Sim in tmux; stop it and Nav2 |
| `tools/py_server_client.py` | runs Python inside the running Isaac Sim over its python server (port 8236) |
| `tools/open_scene.py` | opens the scene, waits for the SimReady groups to compose, plays |
| `tools/setup_warehouse_clutter.py` | the authors' one-time setup of the clutter layer: collision on every group, bounds, overlap check |
| `tools/bake_map.py` | bakes the Nav2 map with Isaac Sim's Occupancy Map Generator |
| `tools/reset_carter.py` | reads the Carter's pose; pauses and resumes the timeline |
| `tools/capture_chase.py` | records viewport frames from a camera following the Carter and encodes the video |
| `nav2/warehouse_nav2.launch.py`, `nav2/nav2_params.yaml`, `nav2/start_nav2.sh` | Nav2 (AMCL, NavFn, MPPI) plus a scan derived from the Carter's XT-32 lidar |
| `nav2/maps/carter_warehouse_clutter.{pgm,yaml}` | the baked map |
| `nav2/waypoints.json`, `nav2/send_goal.py` | three waypoints in the clutter and the NavigateToPose client that drives them and logs the result |
| `results/` | what the run below produced |
| `tests/` | the rebasing, the layer chain, the map and the waypoints, without Isaac Sim |

The layers and the tools come from the authors' C-BASE workspace (2026), where
the scene was authored; each tool says so in its header. Copied here, the
layers reference each other and the Isaac Sim assets through `generated/`
instead of workstation paths, and the clutter layer no longer carries the
Carter's physics state from a saved session, so the Carter opens at the
sample's spawn, (-6.05, -1.0) facing -x.

## Building the scene

The two NVIDIA files are the sample `Isaac/Samples/ROS2/Scenario/carter_warehouse_navigation.usd`
and the robot it loads, `Isaac/Samples/ROS2/Robots/Nova_Carter_ROS.usd`. With
`usd-core` from `../tools`:

```bash
cd isaacsim/warehouse
export ISAACSIM_ASSET_ROOT=/path/to/Assets/Isaac/6.0     # an unpacked Isaac Sim 6.0 asset pack
uv run --project ../tools python fetch_warehouse.py
```

`fetch_warehouse.py` copies the two sample files into `generated/` with their
four relative asset paths pointed at the asset root (the warehouse, its extras,
the Nova Carter) or at the copy beside them (the robot), writes the four layers
next to them with `${ISAACSIM_ASSET_ROOT}` filled in, and counts every asset
path each file holds. Without `ISAACSIM_ASSET_ROOT` it reads NVIDIA's cloud copy
of the 6.0 assets, `https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0`,
whose two sample files have the same SHA-256 as the asset pack's. The SimReady
groups and the motion library are always read from NVIDIA's content server, so
opening the scene needs network access.

On the asset pack it printed:

```
carter_warehouse_navigation.usd: 3 asset paths, 0 URLs, 3 local found, 0 local missing
Nova_Carter_ROS.usd: 1 asset paths, 0 URLs, 1 local found, 0 local missing
carter_warehouse_maze.usda: 8 asset paths, 7 URLs, 1 local found, 0 local missing
carter_warehouse_people.usda: 1 asset paths, 0 URLs, 1 local found, 0 local missing
carter_warehouse_animated.usda: 6 asset paths, 1 URLs, 5 local found, 0 local missing
carter_warehouse_clutter_v2.usda: 4 asset paths, 3 URLs, 1 local found, 0 local missing
```

## Running it

```bash
./launch_stream.sh                        # Isaac Sim in tmux iddmbse-kit; wait for "app ready" in /tmp/iddmbse-kit.log
python3 tools/open_scene.py               # opens generated/carter_warehouse_clutter_v2.usda and plays
./nav2/start_nav2.sh                      # Nav2 in tmux iddmbse-nav2, log /tmp/iddmbse-nav2.log
python3 tools/reset_carter.py pose        # where the Carter is now: x, y, yaw
python3 nav2/send_goal.py --initial-pose X Y YAW_DEG
./stop.sh                                 # Nav2, then Isaac Sim
```

`launch_stream.sh` runs `isaac-sim.streaming.sh` from `ISAACSIM_PATH` (default a
source build under `~/isaacsim`) on GPU 0 with the ROS 2 bridge and the python
server on `127.0.0.1:8236`, persistent settings off. Isaac Sim and Nav2 share
ROS 2 domain `IDDMBSE_ROS_DOMAIN_ID` (default 87) over `rmw_fastrtps_cpp`, with
discovery kept on the host; both scripts start from a clean environment, so a
shell set up for another domain or middleware does not leak in. `send_goal.py`
runs in a shell with ROS 2 Jazzy sourced and the same three settings:
`ROS_DOMAIN_ID=87 RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`.
It gives AMCL the initial pose, waits until Nav2's navigator is active, sends the
three waypoints of `nav2/waypoints.json` one after another and writes
`results/nav_log.csv`.

To record the video too, arm the capture with the timeline paused, so the first
frame is the first moment of the run:

```bash
python3 tools/reset_carter.py pause
python3 tools/capture_chase.py arm --mode high --fps 8
python3 tools/reset_carter.py resume
python3 nav2/send_goal.py --initial-pose X Y YAW_DEG
python3 tools/capture_chase.py off
uv run --project ../tools python tools/capture_chase.py encode
```

To run again from the spawn, stop Nav2, stop and play the timeline (PhysX puts
every body back where it was at play) and start Nav2 again:

```bash
./stop.sh nav2
python3 tools/py_server_client.py 'import omni.timeline; omni.timeline.get_timeline_interface().stop()'
python3 tools/py_server_client.py 'import omni.timeline; omni.timeline.get_timeline_interface().play()'
./nav2/start_nav2.sh
```

`tools/bake_map.py` rebakes the map from the open scene; the map in `nav2/maps/`
is its output.

## Watching the stream

Connect NVIDIA's Isaac Sim WebRTC Streaming Client to the address in
`IDDMBSE_STREAM_IP` (by default the source address of the host's default route;
`launch_stream.sh` prints it). On a host with several interfaces, set it to the
one the client reaches. The client signals on TCP 49100 and receives the
video on UDP 47998, the ports in Isaac Sim's streaming app settings. The stream
shows the active viewport: the overview camera after `open_scene.py`, the
following camera while a capture is armed. `launch_stream.sh` sets Isaac Sim
to keep running when the client disconnects.

## The run here

Isaac Sim 6.0.1-rc.7 from a source build, headless with WebRTC streaming, on one GPU
shared with another job; ROS 2 Jazzy's Nav2 1.3.13 on the same host.

**Isaac Sim.** A warm start reported "app ready" after 10.3 s (89 s on the
first, cold start). `open_scene.py` printed:

| | |
|---|---|
| stage open | 13.3 s (70 s on the cold start) |
| prims | 7 002 |
| pallet and crate groups composed | 17 of 17 |
| old rack grid | inactive |
| workers | 4 |
| Carter chassis | (-6.052, -1.0), yaw 180° |

**ROS 2**, domain 87, `rmw_fastrtps_cpp`: the scene publishes `/clock`, `/tf`,
`/chassis/odom`, `/chassis/imu`, `/front_3d_lidar/lidar_points`,
`/front_stereo_camera/left/image_raw` and `camera_info`, and four stereo-rig IMUs,
and subscribes `/cmd_vel`. Measured with `ros2 topic hz` over wall-clock time
before Nav2 started: `/clock` 14.0 Hz, the XT-32 point cloud 4.7 Hz (42 416
points in the message sampled); after the run, with the Carter parked, `/clock`
15.2 Hz and `/chassis/odom` 16.4 Hz. Over 20 s of wall time `/clock` advanced 11.1 s, so the
simulation ran at 0.55 of real time; Isaac Sim's timeline advanced 13.8 s in the
same 20 s. The scan `pointcloud_to_laserscan` derives from the cloud had 717 of
720 beams in range.

**The map**, `nav2/maps/carter_warehouse_clutter.pgm`: 479 x 776 cells of 0.05 m,
origin (-12, -18); 57.8 % free, 6.5 % occupied, 35.6 % unknown (outside the
walls, where the generator's flood from (-4, -1) does not reach). Each of the
17 groups fills 74 % to 100 % of the 1.05 m square of cells around its position
in `clutter_layout.json`. The Carter's own footprint (536 cells) and the workers' four
invisible proximity triggers (656 cells) are marked free.

**Nav2**, `results/nav_log.csv`: the Carter started at (-6.06, -1.0) facing -x
and drove the three waypoints.

| goal | waypoint | status | error code | simulated s | wall s | odometry path m | AMCL end to waypoint m |
|---|---|---|---|---|---|---|---|
| 1 | field_east (1.5, 4.5) | SUCCEEDED | 0 | 155.3 | 290.4 | 11.371 | 0.087 |
| 2 | field_north (-1.5, 11.5) | SUCCEEDED | 0 | 115.2 | 216.8 | 8.553 | 0.015 |
| 3 | west_aisle (-6.0, 6.0) | SUCCEEDED | 0 | 64.8 | 123.0 | 7.457 | 0.042 |

27.381 m of odometry in 335.4 simulated seconds (630 s of wall time). The
chassis position read from the stage at every captured frame adds up to
27.372 m, and the last frame has the chassis 0.21 m from the last waypoint. The
controller logged "Failed to make progress" 12 times (6, 5 and 1 for the three
goals) and the navigator ran three recoveries (spin, wait, spin); every goal
ended SUCCEEDED.

**The video**, `results/warehouse_nav_chase.mp4`: H.264, 1280 x 720, 24 fps,
28.75 s, 5.4 MB -- every fifth of the 3 447 frames the following camera took,
one every 1/8 s of Isaac Sim's timeline, so one second of video is 15 s of
timeline. `warehouse_nav_chase_start.png`, `_middle.png` and `_end.png` are the
first, middle and last frames, and `warehouse_nav_chase_manifest.json` lists what
went into the video.

## Tests

```bash
cd isaacsim/warehouse && uv run --project ../tools pytest -q tests
```

11 tests, no Isaac Sim needed: the four sample-path rewrites and the layers'
`${ISAACSIM_ASSET_ROOT}` on a fake asset root with `fetch_warehouse.py`'s check
at 0 missing; every layer parses, the sublayer chain, every asset path a URL,
the asset root or a sibling layer; the 17 groups against `clutter_layout.json`;
the old grid off and no saved Carter state in the root layer; the map's size and
values; each waypoint with 1 m of free cells around it; the orientation of the
generator's buffer; the footprint clearing. `11 passed`.
