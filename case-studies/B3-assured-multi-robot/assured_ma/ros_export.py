"""Export a synthesised trajectory as a nav_msgs/msg/Path.

The MILP produces waypoints; what the robots run them through is Nav2. The files
written here use the ROS 2 field layout of nav_msgs/msg/Path exactly, so each one
loads as a message - for instance

    ros2 topic pub --once /agr_1/plan nav_msgs/msg/Path "$(cat robot_1_path.yaml)"

and can be handed to a FollowPath action. The heading at each pose is the direction
of the next segment; the final pose keeps the previous heading.
"""

from pathlib import Path

import numpy as np
import yaml


def _stamp(t):
    sec = int(np.floor(t))
    return {"sec": sec, "nanosec": int(round((t - sec) * 1e9))}


def path_dict(traj, dt, frame_id="map", t0=0.0):
    """nav_msgs/msg/Path as nested dicts, from an array of shape (T, 2)."""
    traj = np.asarray(traj, float)
    d = np.diff(traj, axis=0)
    yaw = np.arctan2(d[:, 1], d[:, 0])
    moving = np.linalg.norm(d, axis=1) > 1e-9
    hold = np.maximum.accumulate(np.where(moving, np.arange(len(yaw)), 0))
    yaw = np.append(yaw[hold], yaw[hold][-1] if len(yaw) else 0.0)
    t = t0 + dt * np.arange(len(traj))
    qz, qw = np.sin(yaw / 2.0), np.cos(yaw / 2.0)
    poses = [{"header": {"stamp": _stamp(t[k]), "frame_id": frame_id},
              "pose": {"position": {"x": round(float(traj[k, 0]), 6),
                                    "y": round(float(traj[k, 1]), 6), "z": 0.0},
                       "orientation": {"x": 0.0, "y": 0.0,
                                       "z": round(float(qz[k]), 6),
                                       "w": round(float(qw[k]), 6)}}}
             for k in range(len(traj))]
    return {"header": {"stamp": _stamp(t0), "frame_id": frame_id}, "poses": poses}


def write_path(path, traj, dt, frame_id="map", t0=0.0, comment=""):
    msg = path_dict(traj, dt, frame_id, t0)
    head = "".join("# " + line + "\n" for line in comment.splitlines()) if comment else ""
    Path(path).write_text(head + yaml.safe_dump(msg, sort_keys=False, default_flow_style=False))
    return msg
