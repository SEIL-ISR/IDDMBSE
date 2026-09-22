import json

import numpy as np

import bake_map
from conftest import WAREHOUSE

MAPS = WAREHOUSE / "nav2" / "maps"


def load_map():
    meta = {}
    for line in (MAPS / "carter_warehouse_clutter.yaml").read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    head, dims, _, body = (MAPS / meta["image"]).read_bytes().split(b"\n", 3)
    assert head == b"P5"
    width, height = map(int, dims.split())
    image = np.frombuffer(body, dtype=np.uint8).reshape(height, width)
    origin = [float(v) for v in meta["origin"].strip("[]").split(",")]
    return image, float(meta["resolution"]), origin


def disc_free(image, cell, origin, x, y, radius):
    """True when every cell whose centre lies within radius of (x, y) is free (254)."""
    rows, cols = image.shape
    cx = origin[0] + (np.arange(cols) + 0.5) * cell
    cy = origin[1] + (rows - np.arange(rows) - 0.5) * cell
    inside = (cx[None, :] - x) ** 2 + (cy[:, None] - y) ** 2 <= radius ** 2
    return inside.any() and bool((image[inside] == 254).all())


def test_map_file():
    image, cell, origin = load_map()
    assert image.shape == (776, 479)
    assert cell == 0.05 and origin == [-12.0, -18.0, 0.0]
    assert set(np.unique(image)) <= {0, 205, 254}


def test_waypoints_in_free_space():
    image, cell, origin = load_map()
    plan = json.loads((WAREHOUSE / "nav2" / "waypoints.json").read_text())
    assert len(plan["waypoints"]) == 3
    for wp in plan["waypoints"]:
        assert disc_free(image, cell, origin, wp["x"], wp["y"], plan["min_clearance_m"]), wp["name"]
    start = plan["initial_pose"]
    assert disc_free(image, cell, origin, start["x"], start["y"], 0.6)


def test_generator_buffer_orientation():
    # the generator's buffer: row = y upwards from the smallest y, column = x from the largest x
    nx, ny, cell = 80, 60, 0.05
    x0, y0 = -2.0, -1.0
    raw = np.full((ny, nx), bake_map.FREE, dtype=np.uint8)
    x, y = 1.02, 0.33
    r, c = int((y - y0) / cell), int((x0 + nx * cell - x) / cell)
    raw[r, c] = bake_map.OCCUPIED
    image = bake_map.to_pgm(bake_map.to_ros(raw.reshape(-1), nx, ny))
    rows, cols = np.nonzero(image == 0)
    assert len(rows) == 1
    assert abs(x0 + (cols[0] + 0.5) * cell - x) <= cell
    assert abs(y0 + (ny - rows[0] - 0.5) * cell - y) <= cell


def test_clear_disc():
    image = np.zeros((40, 40), dtype=np.uint8)
    out, n = bake_map.clear_disc(image, (0.0, 0.0), 0.05, (1.0, 1.0), 0.2)
    assert n == int((out == 254).sum()) and 40 < n < 60
