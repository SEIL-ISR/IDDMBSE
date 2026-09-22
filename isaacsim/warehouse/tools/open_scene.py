"""Open the cluttered warehouse in the running Isaac Sim and start the timeline.

Opens generated/carter_warehouse_clutter_v2.usda through the python server, waits
until the 17 cloud-referenced pallet and crate groups have composed, points the
viewport at the overview camera, plays, and prints what composed as JSON.

    python3 tools/open_scene.py [--no-play] [--out /tmp/iddmbse-warehouse/scene-open.json]

Adapted from the scene-open script of the authors' C-BASE workspace (2026).
"""

import argparse
import json
from pathlib import Path

from py_server_client import run_async

HERE = Path(__file__).resolve().parent.parent

BODY = """
import asyncio, math
import omni.kit.app, omni.timeline, omni.usd
from pxr import Usd, UsdGeom
from omni.kit.viewport.utility import get_active_viewport

SCENE = %(scene)r
CLUTTER = "/World/CbaseWarehouseMaze/ClutterV2"
CHASSIS = "/World/Nova_Carter_ROS/chassis_link"

async def _iddmbse_body():
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    loop = asyncio.get_running_loop()
    started = loop.time()
    opened = await context.open_stage_async(SCENE)
    if not opened[0]:
        raise RuntimeError("stage open failed: " + str(opened))
    stage = context.get_stage()
    frames = 0
    # the cloud-referenced crates compose after open returns
    for frames in range(%(frames)d):
        children = stage.GetPrimAtPath(CLUTTER).GetChildren()
        composed = [p for p in children if len(list(Usd.PrimRange(p))) > 1]
        if children and len(composed) == len(children) and context.get_stage_loading_status()[2] == 0:
            break
        await app.next_update_async()
    timeline = omni.timeline.get_timeline_interface()
    timeline.set_end_time(86400.0)
    timeline.set_looping(False)
    viewport = get_active_viewport()
    viewport.camera_path = "/World/CbaseWarehouseMaze/OverviewCamera"
    if %(play)r:
        timeline.play()
    for _ in range(30):
        await app.next_update_async()
    m = UsdGeom.Xformable(stage.GetPrimAtPath(CHASSIS)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    p = m.ExtractTranslation()
    return {
        "root_layer": stage.GetRootLayer().identifier,
        "open_wall_s": round(loop.time() - started, 1),
        "update_frames_waited": frames,
        "prims": len(list(stage.Traverse())),
        "clutter_groups": len(children),
        "clutter_groups_composed": len(composed),
        "static_props_active": stage.GetPrimAtPath("/World/CbaseWarehouseMaze/StaticProps").IsActive(),
        "people": len(stage.GetPrimAtPath("/World/CbaseWarehouseMaze/People/warehouse_workers").GetChildren()),
        "ros_clock_graph": stage.GetPrimAtPath("/World/ROS_Clock").IsValid(),
        "chassis_xyz_m": [round(float(v), 4) for v in p],
        "chassis_yaw_rad": round(math.atan2(m[0][1], m[0][0]), 4),
        "timeline_playing": timeline.is_playing(),
        "sim_time_s": timeline.get_current_time(),
    }
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scene", default=str(HERE / "generated" / "carter_warehouse_clutter_v2.usda"))
    parser.add_argument("--no-play", action="store_true")
    parser.add_argument("--frames", type=int, default=3000, help="update frames to wait for the crates to compose")
    parser.add_argument("--out", default="/tmp/iddmbse-warehouse/scene-open.json")
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()
    body = BODY % {"scene": args.scene, "frames": args.frames, "play": not args.no_play}
    print(json.dumps(run_async(body, args.out, args.timeout), indent=2))


if __name__ == "__main__":
    main()
