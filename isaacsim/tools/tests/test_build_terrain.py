import json
import pathlib

import numpy as np
import pytest
from pxr import Usd, UsdGeom

import build_terrain as bt

HERE = pathlib.Path(__file__).resolve().parents[1]
RANGE = HERE.parent / "range"
NPZ = RANGE / "terrain" / "heightmap.npz"
META = RANGE / "terrain" / "terrain_meta.json"
needs_terrain = pytest.mark.skipif(not (NPZ.exists() and META.exists()),
                                   reason="range/terrain/heightmap.npz is not built")


def test_grid_uv_corners():
    uv = bt.grid_uv(4, 8)
    assert uv.shape == (4, 8, 2)
    assert uv[0, 0].tolist() == [0.0, 0.0]
    assert uv[-1, -1].tolist() == [1.0, 1.0]
    assert uv[0, -1].tolist() == [1.0, 0.0]


def test_grid_mesh_topology_is_the_row_major_quad_grid():
    h = np.zeros((4, 5), dtype=np.float32)
    meta = {"x0": 0.0, "dx": -2.0, "z0": 0.0, "dz": 2.0}
    pts, faces, normals, st = bt.grid_mesh(h, meta)
    assert len(pts) == 20
    assert faces.shape == (12, 4)
    assert faces[0].tolist() == [0, 5, 6, 1]
    assert np.allclose(normals, [0, 1, 0])
    assert pts[:, 0].min() == -6.0 and pts[:, 2].max() == 8.0


def test_grid_mesh_decimates_by_stride():
    h = np.zeros((9, 9), dtype=np.float32)
    meta = {"x0": 0.0, "dx": -1.0, "z0": 0.0, "dz": 1.0}
    pts, faces, _, _ = bt.grid_mesh(h, meta, stride=4)
    assert len(pts) == 9
    assert faces.shape == (4, 4)


def test_normals_of_a_known_ramp():
    """y = 0.5 x, so the normal leans by atan(0.5) from vertical."""
    x = np.arange(16) * 2.0
    h = np.tile((0.5 * -x)[:, None], (1, 16)).astype(np.float32)
    meta = {"x0": 0.0, "dx": -2.0, "z0": 0.0, "dz": 2.0}
    _, _, normals, _ = bt.grid_mesh(h, meta)
    want = np.array([-0.5, 1.0, 0.0])
    want = want / np.linalg.norm(want)
    assert np.allclose(normals, want, atol=1e-6)


@needs_terrain
def test_shipped_heightmap_matches_its_metadata():
    h = np.load(NPZ)["height"]
    meta = json.loads(META.read_text())
    assert h.dtype == np.float32
    assert h.shape == (meta["rows"], meta["cols"])
    assert float(h.min()) == pytest.approx(meta["height_min"])
    assert float(h.max()) == pytest.approx(meta["height_max"])
    assert meta["scene_xform"]["scale"][:2] == [2.42, 2.37976]


@needs_terrain
def test_built_mesh_bbox_matches_the_metadata(tmp_path):
    out = tmp_path / "terrain.usd"
    bt.build(NPZ, META, out, stride=16)
    stage = Usd.Stage.Open(str(out))
    assert stage.GetRootLayer().defaultPrim == "terrain"
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/terrain/terrain_low/mesh"))
    pts = np.array(mesh.GetPointsAttr().Get())
    meta = json.loads(META.read_text())
    assert pts[:, 0].min() >= meta["x_extent"][0] - 1e-6
    assert pts[:, 2].max() <= meta["z_extent"][1] + 1e-6
    assert float(pts[:, 1].min()) >= meta["height_min"] - 1e-3
    prim = mesh.GetPrim()
    assert prim.GetAttribute("physics:collisionEnabled").Get() is True
    assert prim.GetAttribute("physics:approximation").Get() == "none"
