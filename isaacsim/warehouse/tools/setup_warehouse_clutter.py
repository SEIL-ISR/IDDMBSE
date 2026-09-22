"""Set up the clutter layer in the running Isaac Sim: static colliders on every group, bounds, people check.

Run once, inside Isaac Sim, with generated/carter_warehouse_clutter_v2.usda freshly opened and the timeline
stopped (tools/open_scene.py --no-play):

    python3 tools/py_server_client.py "exec(open('$PWD/tools/setup_warehouse_clutter.py').read())"

It checks that the root layer is the clutter layer and that the old rack grid is off, gives every mesh of the
17 groups a collider and removes rigid bodies, checks that no two groups' bounding boxes overlap, saves the
layer, then plays three simulated seconds and records where the four workers are. The result goes to
$IDDMBSE_RUN_DIR/warehouse-clutter-setup.json (default /tmp/iddmbse-warehouse). The layer in layers/ already
carries these colliders.

From the authors' C-BASE workspace (2026); here the layer is saved before the timeline plays, so no physics
state is written into it.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import omni.anim.behavior.core as behavior
import omni.kit.app
import omni.timeline
import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, UsdSkel


MAZE_ROOT = "/World/CbaseWarehouseMaze"
CLUTTER_ROOT = f"{MAZE_ROOT}/ClutterV2"
PEOPLE_ROOT = f"{MAZE_ROOT}/People"
LEGACY_STATIC_PROPS = f"{MAZE_ROOT}/StaticProps"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bounds(box):
    extent = box.ComputeAlignedRange()
    low = extent.GetMin()
    high = extent.GetMax()
    return {"min": [low[0], low[1], low[2]], "max": [high[0], high[1], high[2]]}


def _make_static(prim):
    colliders = 0
    removed_rigid_bodies = 0
    for descendant in Usd.PrimRange(prim):
        if descendant.IsA(UsdGeom.Gprim) and not descendant.HasAPI(UsdPhysics.CollisionAPI):
            UsdPhysics.CollisionAPI.Apply(descendant)
        if descendant.HasAPI(UsdPhysics.CollisionAPI):
            colliders += 1
        if descendant.HasAPI(UsdPhysics.RigidBodyAPI):
            if descendant.RemoveAPI(UsdPhysics.RigidBodyAPI):
                removed_rigid_bodies += 1
    return colliders, removed_rigid_bodies


def _overlapping_pairs(bounds):
    lows = np.asarray([item["world_bounds_m"]["min"] for item in bounds], dtype=float)
    highs = np.asarray([item["world_bounds_m"]["max"] for item in bounds], dtype=float)
    overlap = np.logical_and(lows[:, None, :] < highs[None, :, :], highs[:, None, :] > lows[None, :, :]).all(axis=2)
    rows, cols = np.where(np.triu(overlap, k=1))
    return [[bounds[row]["name"], bounds[col]["name"]] for row, col in zip(rows.tolist(), cols.tolist())]


def _position(agent):
    position = agent.get_world_translation()
    return [position.x, position.y, position.z]


async def _setup_warehouse_clutter_v2():
    run_dir = Path(os.environ.get("IDDMBSE_RUN_DIR", "/tmp/iddmbse-warehouse")).resolve()
    receipt = run_dir / "warehouse-clutter-setup.json"
    if receipt.exists():
        raise FileExistsError(receipt)

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("no active USD stage")
    layer = stage.GetRootLayer()
    edit_layer = stage.GetEditTarget().GetLayer()
    if edit_layer != layer:
        raise RuntimeError(f"expected root edit target, got {edit_layer.identifier}")
    layer_path = Path(layer.realPath)
    if layer_path.name != "carter_warehouse_clutter_v2.usda":
        raise RuntimeError(f"expected carter_warehouse_clutter_v2.usda, got {layer_path}")
    layout_path = layer_path.with_name("clutter_layout.json")
    layout = json.loads(layout_path.read_text())
    if layout.get("clutter_root") != CLUTTER_ROOT:
        raise RuntimeError("layout clutter root does not match setup script")

    app = omni.kit.app.get_app()
    groupings = layout["groupings"]
    expected_paths = [f"{CLUTTER_ROOT}/{item['name']}" for item in groupings]
    for _ in range(120):
        missing = [path for path in expected_paths if not stage.GetPrimAtPath(path).IsValid()]
        if not missing:
            break
        await app.next_update_async()
    else:
        raise RuntimeError(f"clutter references did not compose: {missing}")

    legacy = stage.GetPrimAtPath(LEGACY_STATIC_PROPS)
    if not legacy.IsValid() or legacy.IsActive():
        raise RuntimeError("v2 layer did not deactivate the legacy empty rack grid")
    people = stage.GetPrimAtPath(PEOPLE_ROOT)
    if not people.IsValid() or not people.IsActive():
        raise RuntimeError("v2 composition did not retain the people root")

    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    observations = []
    for item, path in zip(groupings, expected_paths):
        prim = stage.GetPrimAtPath(path)
        colliders, removed_bodies = _make_static(prim)
        if colliders == 0:
            raise RuntimeError(f"no collider authored for {path}")
        observations.append(
            {
                "name": item["name"],
                "asset": item["asset"],
                "prim_path": path,
                "translation_m": item["translation_m"],
                "yaw_deg": item["yaw_deg"],
                "world_bounds_m": _bounds(cache.ComputeWorldBound(prim)),
                "collider_count": colliders,
                "removed_rigid_body_count": removed_bodies,
            }
        )
    overlaps = _overlapping_pairs(observations)
    if overlaps:
        raise RuntimeError(f"clutter grouping AABBs overlap: {overlaps}")

    await app.next_update_async()
    if not layer.Save():
        raise RuntimeError(f"could not save {layer_path}")

    skeletons = [str(prim.GetPath()) for prim in Usd.PrimRange(people) if prim.IsA(UsdSkel.Root)]
    if len(skeletons) != 4:
        raise RuntimeError(f"expected four retained IRA skeleton roots, found {len(skeletons)}")
    behavior_interface = behavior.acquire_interface()
    timeline = omni.timeline.get_timeline_interface()
    timeline.play()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 60.0
    agents = {}
    while loop.time() < deadline:
        agents = {path: behavior_interface.get_agent(path) for path in skeletons}
        if all(agent is not None for agent in agents.values()):
            break
        await app.next_update_async()
    else:
        absent = [path for path, agent in agents.items() if agent is None]
        raise RuntimeError(f"retained IRA behavior agents were not ready within 60 seconds: {absent}")

    start_time = timeline.get_current_time()
    initial_positions = {path: _position(agent) for path, agent in agents.items()}
    while timeline.get_current_time() < start_time + 3.0:
        if loop.time() >= deadline:
            raise RuntimeError("timeline did not advance three simulation seconds")
        await app.next_update_async()
    final_positions = {path: _position(agent) for path, agent in agents.items()}
    motion = [
        {
            "skeleton_path": path,
            "initial_world_position": initial_positions[path],
            "final_world_position": final_positions[path],
            "changed": initial_positions[path] != final_positions[path],
        }
        for path in skeletons
    ]

    result = {
        "schema_version": "iddmbse-warehouse-clutter-setup-v1",
        "root_layer": str(layer_path),
        "layout": str(layout_path),
        "source_hashes": {
            "carter_warehouse_clutter_v2.usda": _sha256(layer_path),
            "clutter_layout.json": _sha256(layout_path),
        },
        "stage_metadata": {
            "up_axis": UsdGeom.GetStageUpAxis(stage),
            "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        },
        "legacy_static_props_active": legacy.IsActive(),
        "clutter_groupings": observations,
        "clutter_self_overlap_pairs": overlaps,
        "retained_people": {
            "root": PEOPLE_ROOT,
            "skeleton_roots": skeletons,
            "behavior_agent_ready_paths": sorted(agents),
            "playback": {
                "initial_simulation_time_s": start_time,
                "final_simulation_time_s": timeline.get_current_time(),
                "motion": motion,
            },
            "motion_interpretation": "the wander routine includes idle intervals, so a worker may stand still for three seconds"
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    with receipt.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


_existing_task = globals().get("_iddmbse_clutter_setup_task")
if _existing_task is not None and not _existing_task.done():
    raise RuntimeError("warehouse clutter v2 setup is already running")
_iddmbse_clutter_setup_task = asyncio.ensure_future(_setup_warehouse_clutter_v2())
