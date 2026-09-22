"""One headless Isaac Sim trial on a test-range design point.

Runs inside Isaac Sim's own Python (`python.sh sim_trial.py ...`), because it
needs `isaacsim.SimulationApp`. `experiment.py` starts it as a subprocess, one
process per trial, and reads back the two files it writes:

    <out>/trajectory.csv   t, x, y, z, roll, pitch, yaw, v  per physics step
    <out>/metrics.json     the numbers the PERFECT trial result carries

The robot is driven open loop: a constant forward speed with a sinusoidal yaw
sweep, applied as velocity targets on the two drive wheels. The scene's teleop
OmniGraph is deactivated first so that nothing else writes to the articulation
and no ROS bridge is needed.

The stepping loop advances the simulator, which is sequential by nature; every
number below it is computed from the recorded arrays with whole-array numpy.
"""

import argparse
import json
import math
import pathlib
import time

from isaacsim import SimulationApp

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--layer", required=True, help="the USD layer to open")
ap.add_argument("--out", required=True, help="directory for trajectory.csv and metrics.json")
ap.add_argument("--duration", type=float, default=20.0, help="simulated seconds to drive")
ap.add_argument("--settle", type=float, default=1.0, help="simulated seconds to settle first")
ap.add_argument("--speed", type=float, default=0.6, help="forward speed, m/s")
ap.add_argument("--yaw-amplitude", type=float, default=0.3, help="yaw rate amplitude, rad/s")
ap.add_argument("--yaw-period", type=float, default=10.0, help="yaw sweep period, s")
ap.add_argument("--physics-dt", type=float, default=1.0 / 60.0)
ap.add_argument("--wheel-radius", type=float, default=0.28)
ap.add_argument("--wheel-distance", type=float, default=0.413)
ap.add_argument("--encounter-radius", type=float, default=1.5,
                help="how close to an obstacle centre counts as an encounter, m")
ap.add_argument("--stuck-speed", type=float, default=0.05, help="m/s")
ap.add_argument("--stuck-window", type=float, default=2.0, help="s below --stuck-speed to count as stuck")
ap.add_argument("--unstable-speed", type=float, default=10.0,
                help="a step speed above this means the contact solver threw the robot, m/s")
ap.add_argument("--robot-prim", default=None, help="articulation root; default is the first one found")
ap.add_argument("--load-frames", type=int, default=400, help="app updates allowed for asset loading")
args = ap.parse_args()

out = pathlib.Path(args.out)
out.mkdir(parents=True, exist_ok=True)

wall0 = time.time()
sim = SimulationApp({"headless": True})

import numpy as np                                             # noqa: E402
import omni.usd                                                # noqa: E402
from pxr import Sdf, UsdGeom, UsdPhysics                       # noqa: E402

from isaacsim.core.api import SimulationContext                # noqa: E402
from isaacsim.core.prims import SingleArticulation             # noqa: E402
from isaacsim.core.utils.types import ArticulationAction       # noqa: E402


# ------------------------------------------------------------------
# helpers

def euler_from_quat(q):
    """roll, pitch, yaw from an (N, 4) array of (w, x, y, z) quaternions."""
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    roll = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2 * (w * y - z * x), -1.0, 1.0))
    yaw = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def longest_run(mask):
    """Length of the longest run of True in a boolean array."""
    if not mask.any():
        return 0
    padded = np.concatenate([[False], mask, [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return int((edges[1::2] - edges[0::2]).max())


def obstacle_centres(stage):
    """World-space xy of every DOE obstacle in the layer, as an (N, 2) array."""
    root = stage.GetPrimAtPath("/World/doe_obstacles")
    if not (root and root.IsValid()):
        return np.zeros((0, 2))
    xy = [p.GetAttribute("xformOp:translate").Get() for p in root.GetChildren()]
    xy = [t for t in xy if t is not None]
    if not xy:
        return np.zeros((0, 2))
    return np.array([[float(t[0]), float(t[1])] for t in xy])


# ------------------------------------------------------------------
# the stage

ctx = omni.usd.get_context()
t0 = time.time()
ctx.open_stage(args.layer)
for _ in range(args.load_frames):
    sim.update()
    files_loaded, total_files = ctx.get_stage_loading_status()[1:3]
    if total_files == 0:
        break
open_seconds = time.time() - t0

stage = ctx.get_stage()
prims = list(stage.Traverse())
prim_count = len(prims)
mesh_count = sum(1 for p in prims if p.IsA(UsdGeom.Mesh))
unresolved = [str(p.GetPath()) for p in prims if not p.IsDefined()]

roots = [str(p.GetPath()) for p in prims if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
robot_prim = args.robot_prim or (roots[0] if roots else None)
if robot_prim is None:
    raise SystemExit("no articulation root in " + args.layer)

obstacles = obstacle_centres(stage)

# Nothing but this script should write to the articulation, and without a ROS
# graph the teleop nodes have nothing to read anyway. Deactivating expires the
# prims underneath, so nothing may hold on to the traversal after this point.
prims = None
for path in ("/World/teleop", "/World/ROS_Clock"):
    p = stage.GetPrimAtPath(path)
    if p and p.IsValid():
        p.SetActive(False)

t1 = time.time()
sc = SimulationContext(physics_dt=args.physics_dt, rendering_dt=args.physics_dt,
                       stage_units_in_meters=1.0)
sc.initialize_physics()
physics_init_seconds = time.time() - t1

t2 = time.time()
sc.play()
sc.step(render=False)
first_step_seconds = time.time() - t2

art = SingleArticulation(robot_prim)
art.initialize()
dof_names = list(art.dof_names)
left = dof_names.index("joint_wheel_left")
right = dof_names.index("joint_wheel_right")

# ------------------------------------------------------------------
# settle, then drive

settle_steps = int(round(args.settle / args.physics_dt))
zero = ArticulationAction(joint_velocities=np.zeros(2), joint_indices=np.array([left, right]))
for _ in range(settle_steps):
    art.apply_action(zero)
    sc.step(render=False)
settled_pos, _ = art.get_world_pose()
settled_z = float(settled_pos[2])

steps = int(round(args.duration / args.physics_dt))
pos = np.zeros((steps, 3))
quat = np.zeros((steps, 4))
cmd = np.zeros((steps, 2))
indices = np.array([left, right])

t3 = time.time()
for i in range(steps):
    t = i * args.physics_dt
    omega = args.yaw_amplitude * math.sin(2 * math.pi * t / args.yaw_period)
    wl = (args.speed - omega * args.wheel_distance / 2) / args.wheel_radius
    wr = (args.speed + omega * args.wheel_distance / 2) / args.wheel_radius
    art.apply_action(ArticulationAction(joint_velocities=np.array([wl, wr]),
                                        joint_indices=indices))
    sc.step(render=False)
    p, q = art.get_world_pose()
    pos[i] = p
    quat[i] = q
    cmd[i] = (args.speed, omega)
drive_wall_seconds = time.time() - t3

sc.stop()

# ------------------------------------------------------------------
# the numbers

t = np.arange(steps) * args.physics_dt
roll, pitch, yaw = euler_from_quat(quat)
step_xy = np.diff(pos[:, :2], axis=0)
step_len = np.hypot(step_xy[:, 0], step_xy[:, 1])
v = np.concatenate([[0.0], step_len / args.physics_dt])
distance = float(step_len.sum())
net_displacement = float(np.hypot(*(pos[-1, :2] - pos[0, :2])))

stuck_mask = v < args.stuck_speed
stuck_run = longest_run(stuck_mask) * args.physics_dt

if len(obstacles):
    d = np.hypot(pos[:, 0][None, :] - obstacles[:, 0][:, None],
                 pos[:, 1][None, :] - obstacles[:, 1][:, None])
    encounters = int((d.min(axis=1) < args.encounter_radius).sum())
    nearest_obstacle = float(d.min())
else:
    encounters = 0
    nearest_obstacle = float("nan")

sim_seconds = steps * args.physics_dt
metrics = {
    "layer": str(args.layer),
    "robot_prim": robot_prim,
    "dof": int(art.num_dof),
    "prim_count": prim_count,
    "mesh_count": mesh_count,
    "unresolved_references": len(unresolved),
    "obstacle_count": int(len(obstacles)),
    "sim_time_s": sim_seconds,
    "distance_m": distance,
    "net_displacement_m": net_displacement,
    "mean_speed_mps": float(v[1:].mean()),
    "max_speed_mps": float(v.max()),
    "unstable": bool(v.max() > args.unstable_speed),
    "mean_pitch_deg": float(np.degrees(np.abs(pitch)).mean()),
    "max_pitch_deg": float(np.degrees(np.abs(pitch)).max()),
    "mean_roll_deg": float(np.degrees(np.abs(roll)).mean()),
    "max_roll_deg": float(np.degrees(np.abs(roll)).max()),
    "max_climb_m": float((pos[:, 2] - pos[0, 2]).max()),
    "z_range_m": float(pos[:, 2].max() - pos[:, 2].min()),
    "settle_z_m": settled_z,
    "obstacle_encounters": encounters,
    "nearest_obstacle_m": nearest_obstacle,
    "stuck": bool(stuck_run > args.stuck_window),
    "stuck_seconds": float(stuck_run),
    "open_seconds": open_seconds,
    "physics_init_seconds": physics_init_seconds,
    "first_step_seconds": first_step_seconds,
    "drive_wall_seconds": drive_wall_seconds,
    "wall_per_sim_s": drive_wall_seconds / sim_seconds,
    "wall_total_seconds": time.time() - wall0,
    "command": {"speed_mps": args.speed, "yaw_amplitude_radps": args.yaw_amplitude,
                "yaw_period_s": args.yaw_period, "physics_dt": args.physics_dt},
}

table = np.column_stack([t, pos[:, 0], pos[:, 1], pos[:, 2], roll, pitch, yaw, v])
np.savetxt(out / "trajectory.csv", table, delimiter=",", fmt="%.6f",
           header="t,x,y,z,roll,pitch,yaw,v", comments="")
(out / "metrics.json").write_text(json.dumps(metrics, indent=2))

for k, val in metrics.items():
    if not isinstance(val, dict):
        print("RESULT " + k + " " + str(val))
print("RESULT done")
sim.close()
