import argparse
import math
import pathlib

import numpy as np
import pytest
from pxr import Sdf, Usd

import range_doe

ROOT = pathlib.Path(range_doe.ROOT)
HAVE_TERRAIN = range_doe.NPZ.exists() and range_doe.META.exists()
needs_terrain = pytest.mark.skipif(not HAVE_TERRAIN,
                                   reason="range/terrain/heightmap.npz is not built")


# ------------------------------------------------------------------
# the footprint estimator

def box(sx, sy, sz):
    """A closed axis-aligned box as (points, faceVertexCounts, indices)."""
    p = np.array([[x, y, z] for x in (0, sx) for y in (0, sy) for z in (0, sz)],
                 dtype=np.float64)
    # index = 4*ix + 2*iy + iz
    quads = [(0, 1, 3, 2), (4, 6, 7, 5),          # x = 0 and x = sx
             (0, 4, 5, 1), (2, 3, 7, 6),          # y = 0 and y = sy
             (0, 2, 6, 4), (1, 5, 7, 3)]          # z = 0 and z = sz
    idx = np.array(quads, dtype=np.int64).reshape(-1)
    return p, np.full(6, 4, dtype=np.int64), idx


def test_silhouette_area_of_a_box_is_its_horizontal_cross_section():
    p, c, i = box(3.0, 7.0, 5.0)
    # the horizontal plane is (x, z) in the mesh's Y-up convention
    assert range_doe.silhouette_area(p, c, i) == pytest.approx(3.0 * 5.0)


def test_silhouette_area_ignores_height():
    a = range_doe.silhouette_area(*box(2.0, 1.0, 4.0))
    b = range_doe.silhouette_area(*box(2.0, 90.0, 4.0))
    assert a == pytest.approx(b)


def test_silhouette_area_handles_triangles():
    """The same box, every quad split into two triangles."""
    p, c, i = box(3.0, 7.0, 5.0)
    quads = i.reshape(-1, 4)
    tris = np.concatenate([quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]]).reshape(-1)
    counts = np.full(12, 3, dtype=np.int64)
    assert range_doe.silhouette_area(p, counts, tris) == pytest.approx(3.0 * 5.0)


@needs_terrain
def test_requested_density_is_met_by_the_placed_obstacles():
    t = range_doe.Terrain()
    shapes = range_doe.rock_shapes()
    for d in (0.1, 0.4, 0.8):
        r = range_doe.scatter(t, shapes, d, 2.0, 0.5, 0.5,
                              np.random.default_rng(3), 1.0)
        assert r["coverage"] == pytest.approx(d, abs=0.01)


@needs_terrain
def test_obstacles_keep_the_minimum_spacing_they_promise():
    t = range_doe.Terrain()
    shapes = range_doe.rock_shapes()
    r = range_doe.scatter(t, shapes, 0.4, 2.0, 0.5, 0.5,
                          np.random.default_rng(11), 1.0)
    measured = range_doe.min_pair_distance(r["x"], r["y"])
    assert measured >= r["min_spacing_guaranteed"] - 1e-9


# ------------------------------------------------------------------
# the slope scaling

@needs_terrain
@pytest.mark.parametrize("target", [5.0, 10.0, 15.0, 25.0])
def test_slope_scaling_hits_the_target_99th_percentile(target):
    t = range_doe.Terrain()
    k, _ = range_doe.slope_scale_for(t, target)
    measured = range_doe.slope_summary(t, k)["p99"]
    assert abs(measured - target) < 0.5


@needs_terrain
def test_slope_scaling_is_monotone_in_the_target():
    t = range_doe.Terrain()
    ks = [range_doe.slope_scale_for(t, d)[0] for d in (5.0, 10.0, 20.0)]
    assert ks[0] < ks[1] < ks[2]


def test_slope_of_a_synthetic_ramp():
    """A plane at a known angle, read back through the same code path."""
    t = range_doe.Terrain.__new__(range_doe.Terrain)
    t.rows = t.cols = 64
    t.sx = t.sy = 0.5
    t.hz = 1.0
    t.dx, t.dy, t.x0, t.y0, t.z0 = -0.5, -0.5, 0.0, 0.0, 0.0
    t.lx = t.ly = 0.5 * 63
    t.area = t.lx * t.ly
    grade = math.tan(math.radians(12.0))
    t.h = (np.arange(64)[:, None] * 0.5 * grade * np.ones(64)[None, :])
    assert np.allclose(t.slope_deg(1.0), 12.0, atol=1e-6)
    k, _ = range_doe.slope_scale_for(t, 30.0)
    assert range_doe.slope_summary(t, k)["p99"] == pytest.approx(30.0, abs=1e-6)


# ------------------------------------------------------------------
# the generated layer

def doe_args(out, **kw):
    a = argparse.Namespace(
        obstacle_density=0.1, max_slope_deg=15.0, slope_window=1,
        slope_percentile=99.0, friction_static=0.7, friction_dynamic=0.6,
        restitution=0.05, rock_size=2.0, rock_size_jitter=0.5,
        min_spacing_factor=0.5, multi_agr=2, agr_ring_radius=4.0,
        agr_clearance=0.3, sensor_payload=False, nova_carter_version="4.1",
        nova_carter_local=False, seed=5, base=range_doe.BASE,
        npz=range_doe.NPZ, meta=range_doe.META, out=str(out), json=False)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


@needs_terrain
def test_generated_layer_parses(tmp_path):
    out = tmp_path / "doe.usda"
    report = range_doe.run(doe_args(out))
    layer = Sdf.Layer.FindOrOpen(str(out))
    assert layer is not None
    assert len(layer.subLayerPaths) == 1
    assert layer.subLayerPaths[0].endswith("sim_world2.usd")
    assert report["obstacle_count"] > 0
    assert layer.GetPrimAtPath("/World/doe_obstacles/rock_0000") is not None
    assert layer.GetPrimAtPath("/World/doe_agr_1") is not None
    assert layer.GetPrimAtPath("/World/doe_agr_2") is not None


@needs_terrain
def test_layer_overs_target_prims_that_exist_in_the_base_scene(tmp_path):
    out = tmp_path / "doe.usda"
    range_doe.run(doe_args(out))
    layer = Sdf.Layer.FindOrOpen(str(out))

    overs = []
    layer.Traverse(Sdf.Path.absoluteRootPath, lambda p: overs.append(p))
    overs = [p for p in overs
             if isinstance(layer.GetObjectAtPath(p), Sdf.PrimSpec)
             and layer.GetPrimAtPath(p).specifier == Sdf.SpecifierOver]
    assert str(Sdf.Path(range_doe.TERRAIN_PRIM)) in [str(p) for p in overs]
    assert str(Sdf.Path(range_doe.TERRAIN_MESH)) in [str(p) for p in overs]

    # the base scene payloads range/terrain1_world.usd under /World/terrain1_world,
    # so an over there has to exist under /World in that layer
    base = Sdf.Layer.FindOrOpen(str(range_doe.BASE))
    terrain_layer = Sdf.Layer.FindOrOpen(str(range_doe.RANGE / "terrain1_world.usd"))
    prefix = "/World/terrain1_world"
    for p in overs:
        s = str(p)
        if s.startswith(prefix):
            inner = "/World" + s[len(prefix):]
            assert terrain_layer.GetPrimAtPath(inner) is not None, inner
        else:
            assert base.GetPrimAtPath(s) is not None, s


@needs_terrain
def test_composed_stage_sees_the_doe_obstacles_and_the_scaled_terrain(tmp_path):
    out = tmp_path / "doe.usda"
    report = range_doe.run(doe_args(out, multi_agr=0))
    stage = Usd.Stage.Open(str(out), load=Usd.Stage.LoadNone)
    stage.Load("/World/terrain1_world")
    terrain = stage.GetPrimAtPath(range_doe.TERRAIN_PRIM)
    assert terrain.IsValid()
    scale = terrain.GetAttribute("xformOp:scale").Get()
    assert scale[2] == pytest.approx(report["height_scale"], rel=1e-5)
    obstacles = stage.GetPrimAtPath("/World/doe_obstacles")
    assert obstacles.IsValid()
    assert len(obstacles.GetChildren()) == report["obstacle_count"]
    mat = stage.GetPrimAtPath("/World/doe_physics_material")
    assert mat.GetAttribute("physics:staticFriction").Get() == pytest.approx(0.7)
    assert mat.GetAttribute("physics:restitution").Get() == pytest.approx(0.05)


@needs_terrain
def test_the_same_seed_gives_the_same_layer(tmp_path):
    a, b = tmp_path / "a.usda", tmp_path / "b.usda"
    range_doe.run(doe_args(a, seed=42))
    range_doe.run(doe_args(b, seed=42))
    assert a.read_text() == b.read_text()


@needs_terrain
def test_a_different_seed_moves_the_obstacles(tmp_path):
    a, b = tmp_path / "a.usda", tmp_path / "b.usda"
    range_doe.run(doe_args(a, seed=1))
    range_doe.run(doe_args(b, seed=2))
    assert a.read_text() != b.read_text()
