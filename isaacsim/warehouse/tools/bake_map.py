"""Bake the Nav2 occupancy map of the open warehouse with Isaac Sim's Occupancy Map Generator.

Runs isaacsim.asset.gen.omap inside the running Isaac Sim (through the python
server) over the warehouse floor: 0.05 m cells, the height band 0.1-0.62 m
above the floor, x -12..12 m, y -18..20.85 m, starting from (-4, -1). The raw
buffer comes back as .npy; this script turns it into a ROS map (row 0 = the
largest y, column 0 = the smallest x), marks free what is not part of the static
world -- the Carter's own footprint and the invisible 0.3 m proximity triggers
the four workers carry -- and writes nav2/maps/carter_warehouse_clutter.{pgm,yaml}.

    uv run --project ../tools python tools/bake_map.py
    uv run --project ../tools python tools/bake_map.py --from-raw /tmp/iddmbse-warehouse/omap_raw.npy

The second form redoes the conversion from a saved buffer without Isaac Sim.
"""

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
CELL = 0.05
BOUNDS = (-12.0, -18.0, 12.0, 20.85)
Z_BAND = (0.1, 0.62)
START = (-4.0, -1.0)
OCCUPIED, FREE, UNKNOWN = 4, 5, 6
FOOTPRINT_RADIUS = 0.65
TRIGGER_RADIUS = 0.36

BODY = """
import numpy as np
import omni.kit.app, omni.physx, omni.timeline, omni.usd
from pxr import Usd, UsdGeom
from isaacsim.asset.gen.omap.bindings import _omap

async def _iddmbse_body():
    app = omni.kit.app.get_app()
    context = omni.usd.get_context()
    stage = context.get_stage()
    timeline = omni.timeline.get_timeline_interface()
    if not timeline.is_playing():
        timeline.play()
    for _ in range(10):
        await app.next_update_async()
    x0, y0, x1, y1 = %(bounds)r
    ox, oy = %(start)r
    z0, z1 = %(z_band)r
    generator = _omap.Generator(omni.physx.get_physx_interface(), context.get_stage_id())
    generator.update_settings(%(cell)r, %(occupied)r, %(free)r, %(unknown)r)
    generator.set_transform((ox, oy, 0.0), (x0 - ox, y0 - oy, z0), (x1 - ox, y1 - oy, z1))
    await app.next_update_async()
    generator.generate2d()
    buffer = np.asarray(generator.get_buffer(), dtype=np.float32).astype(np.uint8)
    np.save(%(raw)r, buffer)
    m = UsdGeom.Xformable(stage.GetPrimAtPath("/World/Nova_Carter_ROS/chassis_link")).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    p = m.ExtractTranslation()
    triggers = []
    for prim in Usd.PrimRange(stage.GetPrimAtPath("/World/CbaseWarehouseMaze/People")):
        if prim.GetName() == "worker_proximity_trigger":
            t = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation()
            triggers.append([float(t[0]), float(t[1])])
    return {
        "dimensions": [int(v) for v in generator.get_dimensions()],
        "min_bound": [float(v) for v in generator.get_min_bound()],
        "max_bound": [float(v) for v in generator.get_max_bound()],
        "cells": int(buffer.size),
        "chassis_xy_m": [float(p[0]), float(p[1])],
        "trigger_xy_m": triggers,
        "sim_time_s": timeline.get_current_time(),
    }
"""


def to_ros(raw, nx, ny):
    """The generator's buffer (row = y from the smallest, column = x from the largest) as a ROS image."""
    return raw.reshape(ny, nx)[::-1, ::-1]


def to_pgm(grid):
    return np.select([grid == OCCUPIED, grid == FREE], [0, 254], 205).astype(np.uint8)


def clear_disc(image, origin, cell, centre, radius):
    """Mark every cell whose centre lies within radius of centre (x, y in metres) free."""
    rows, cols = image.shape
    x = origin[0] + (np.arange(cols) + 0.5) * cell
    y = origin[1] + (rows - np.arange(rows) - 0.5) * cell
    inside = (x[None, :] - centre[0]) ** 2 + (y[:, None] - centre[1]) ** 2 <= radius ** 2
    out = image.copy()
    out[inside] = 254
    return out, int(inside.sum())


def write_map(image, origin, cell, stem, header):
    rows, cols = image.shape
    stem.parent.mkdir(parents=True, exist_ok=True)
    with open(stem.with_suffix(".pgm"), "wb") as f:
        f.write(f"P5\n{cols} {rows}\n255\n".encode())
        f.write(image.tobytes())
    lines = ["# " + line for line in header]
    lines += [
        f"image: {stem.name}.pgm",
        "mode: trinary",
        f"resolution: {cell}",
        f"origin: [{origin[0]}, {origin[1]}, 0.0]",
        "negate: 0",
        "occupied_thresh: 0.65",
        "free_thresh: 0.196",
    ]
    stem.with_suffix(".yaml").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-raw", type=Path, help="convert a saved buffer instead of baking")
    parser.add_argument("--raw", type=Path, default=Path("/tmp/iddmbse-warehouse/omap_raw.npy"))
    parser.add_argument("--stem", type=Path, default=HERE / "nav2" / "maps" / "carter_warehouse_clutter")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()
    meta_path = args.raw.with_suffix(".json")
    if args.from_raw:
        raw = np.load(args.from_raw)
        meta = json.loads(args.from_raw.with_suffix(".json").read_text())
    else:
        from py_server_client import run_async

        values = {
            "bounds": BOUNDS, "start": START, "z_band": Z_BAND, "cell": CELL,
            "occupied": OCCUPIED, "free": FREE, "unknown": UNKNOWN, "raw": str(args.raw.resolve()),
        }
        meta = run_async(BODY % values, meta_path, args.timeout)
        raw = np.load(args.raw)
    nx, ny = meta["dimensions"][0], meta["dimensions"][1]
    origin = (round(meta["min_bound"][0], 4), round(meta["min_bound"][1], 4))
    image = to_pgm(to_ros(raw, nx, ny))
    image, cleared = clear_disc(image, origin, CELL, meta["chassis_xy_m"], FOOTPRINT_RADIUS)
    trigger_cells = 0
    for centre in meta["trigger_xy_m"]:
        image, n = clear_disc(image, origin, CELL, centre, TRIGGER_RADIUS)
        trigger_cells += n
    header = [
        "Occupancy map of the cluttered warehouse (generated/carter_warehouse_clutter_v2.usda),",
        "baked by tools/bake_map.py with isaacsim.asset.gen.omap in Isaac Sim 6.0:",
        f"cell {CELL} m, height band {Z_BAND[0]}-{Z_BAND[1]} m, start ({START[0]}, {START[1]}),",
        f"x {BOUNDS[0]}..{BOUNDS[2]} m, y {BOUNDS[1]}..{BOUNDS[3]} m;",
        f"the parked Carter's footprint (r {FOOTPRINT_RADIUS} m around"
        f" ({round(meta['chassis_xy_m'][0], 3)}, {round(meta['chassis_xy_m'][1], 3)})) marked free,",
        f"and the {len(meta['trigger_xy_m'])} workers' proximity triggers (r {TRIGGER_RADIUS} m) marked free.",
    ]
    write_map(image, origin, CELL, args.stem, header)
    total = image.size
    print(json.dumps({
        "map": str(args.stem.with_suffix(".pgm")),
        "width": image.shape[1], "height": image.shape[0], "resolution": CELL, "origin": list(origin),
        "free_fraction": round(float((image == 254).sum()) / total, 4),
        "occupied_fraction": round(float((image == 0).sum()) / total, 4),
        "unknown_fraction": round(float((image == 205).sum()) / total, 4),
        "footprint_cells_cleared": cleared,
        "trigger_cells_cleared": trigger_cells,
        "raw_values": {str(int(v)): int(c) for v, c in zip(*np.unique(raw, return_counts=True))},
    }, indent=2))


if __name__ == "__main__":
    main()
