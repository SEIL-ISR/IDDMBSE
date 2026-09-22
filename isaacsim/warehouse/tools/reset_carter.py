"""Read the Carter's pose, pause or resume the running Isaac Sim.

    python3 tools/reset_carter.py pose      # the chassis pose (x, y, yaw) and the timeline time
    python3 tools/reset_carter.py pause     # pause the timeline
    python3 tools/reset_carter.py resume    # play and wait until the timeline advances

To put the Carter back at the spawn, stop and play the timeline (see README.md).

Adapted from the reset script of the authors' C-BASE workspace (2026).
"""

import argparse
import json
from pathlib import Path

from py_server_client import run_async

BODY = """
import math, time
import omni.kit.app, omni.timeline
from isaacsim.core.experimental.utils import xform

CHASSIS = "/World/Nova_Carter_ROS/chassis_link"

def pose():
    p, q = xform.get_world_pose(CHASSIS)
    p, q = p.numpy().reshape(-1), q.numpy().reshape(-1)
    yaw = math.atan2(2.0 * (q[0] * q[3] + q[1] * q[2]), 1.0 - 2.0 * (q[2] ** 2 + q[3] ** 2))
    return {"x": float(p[0]), "y": float(p[1]), "z": float(p[2]), "yaw_rad": yaw}

async def _iddmbse_body():
    app = omni.kit.app.get_app()
    timeline = omni.timeline.get_timeline_interface()
    before = pose()
    t0 = timeline.get_current_time()
    action = %(action)r
    if action == "pause":
        timeline.pause()
    if action == "resume":
        timeline.play()
        deadline = time.monotonic() + 30.0
        while timeline.get_current_time() <= t0 and time.monotonic() < deadline:
            await app.next_update_async()
    for _ in range(2):
        await app.next_update_async()
    return {"action": action, "before": before, "after": pose(), "playing": timeline.is_playing(),
            "sim_time_s": timeline.get_current_time()}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("pose", "pause", "resume"))
    parser.add_argument("--out", default="/tmp/iddmbse-warehouse/carter.json")
    args = parser.parse_args()
    body = BODY % {"action": args.action}
    print(json.dumps(run_async(body, Path(args.out), 60.0), indent=2))


if __name__ == "__main__":
    main()
