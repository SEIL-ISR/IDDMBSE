"""Parameterise the test range: obstacles, slope, physics, robots.

    python range_doe.py --obstacle-density 0.4 --out ../range/doe/density_0.4.usda
    python range_doe.py --obstacle-density 0.2 --max-slope-deg 15 \
        --friction-static 0.4 --friction-dynamic 0.35 --restitution 0.1 \
        --multi-agr 3 --seed 7 --out /tmp/run07.usda

One design point of the experiment is one USD layer. The layer sublayers
range/sim_world2.usd, so opening it opens the whole range with that design on
top, and the base scene keeps no state from any run. Everything here is
usd-core; no Kit, no GPU, so a design-of-experiments sweep is a few hundred
milliseconds of CPU per point and can be farmed out.

What the flags do:

--obstacle-density   the fraction of the terrain footprint covered by rock
                     silhouettes. Rocks are drawn from the three shipped
                     meshes, scaled to a target footprint diameter, and
                     scattered on a jittered grid so that the minimum spacing
                     is a guarantee rather than a hope. Each one is seated
                     with its lowest point on the terrain.
--max-slope-deg      scales the terrain's height so that the 99th percentile
                     of the per-cell slope comes out at the target. Slope is
                     computed on the heightmap in world units, so it already
                     accounts for the scene's own transform.
--friction-*         a physics material on the terrain and on the obstacles.
--obstacle-approximation
                     the PhysX collision approximation the obstacles get.
                     The rock assets carry geometry only, so the layer applies
                     the collision APIs itself.
--multi-agr N        N more Carters on a ring around the one in the base scene.
--agr-keepout-radius
                     the clear disc the AGR starts in. Obstacles are dealt
                     cells outside it, so the count and the coverage do not
                     change and nothing is spawned on top of the robot.
--sensor-payload     a Nova Carter, which carries the stereo cameras, the 3D
                     lidar and the IMUs.

The heightmap and its metadata come from range/terrain/; see build_terrain.py.
"""

import argparse
import json
import math
import os
import pathlib

import numpy as np
from pxr import Gf, Sdf, Vt

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
RANGE = ROOT / "range"
BASE = RANGE / "sim_world2.usd"
NPZ = RANGE / "terrain" / "heightmap.npz"
META = RANGE / "terrain" / "terrain_meta.json"

ROCK_KINDS = [1, 5, 9]
UNITS_SCALE = 0.01          # the scene's xformOp:scale:unitsResolve on every instance
XFORM_OPS = ["xformOp:translate", "xformOp:orient", "xformOp:scale",
             "xformOp:rotateX:unitsResolve", "xformOp:scale:unitsResolve"]

TERRAIN_PRIM = "/World/terrain1_world/terrain1"
TERRAIN_MESH = "/World/terrain1_world/terrain1/terrain_low/mesh"
CARTER_PRIM = "/World/Carter_v2_4_ROS"
CARTER_ASSET = ("range/assets/Assets/Isaac/2023.1.0/Isaac/Samples/ROS2/Robots/"
                "Carter_v2_4_ROS.usd")
NOVA_CARTER_URL = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
                   "/Assets/Isaac/{ver}/Isaac/Samples/ROS2/Robots/Nova_Carter_ROS.usd")


# ------------------------------------------------------------------
# the terrain, in world coordinates

class Terrain:
    """The heightmap plus everything the scene does to it before it is world."""

    def __init__(self, npz=NPZ, meta=META, base=BASE):
        self.h = np.load(npz)["height"].astype(np.float64)
        self.meta = json.loads(pathlib.Path(meta).read_text())
        m = self.meta["scene_xform"]["obj_to_world"]
        off = base_offset(base)

        self.rows, self.cols = self.h.shape
        # world x decreases with the row index, world y with the column index
        self.x0 = m["x_offset"] + m["x_from_obj_x"] * self.meta["x0"] + off[0]
        self.y0 = m["y_offset"] + m["y_from_obj_z"] * self.meta["z0"] + off[1]
        self.dx = m["x_from_obj_x"] * self.meta["dx"]
        self.dy = m["y_from_obj_z"] * self.meta["dz"]
        self.hz = m["z_from_obj_y"]
        self.z0 = m["z_offset"] + off[2]

        self.sx = abs(self.dx)
        self.sy = abs(self.dy)
        self.lx = self.sx * (self.rows - 1)
        self.ly = self.sy * (self.cols - 1)
        self.area = self.lx * self.ly

    def bounds(self):
        xs = sorted([self.x0, self.x0 + self.dx * (self.rows - 1)])
        ys = sorted([self.y0, self.y0 + self.dy * (self.cols - 1)])
        return xs, ys

    def gradient(self, k=1.0, window=1):
        """|grad h| per grid cell, in world units: the tangent of the slope.

        The grid is 4.8 cm across, so a window of 1 measures the slope of the
        terrain's own roughness. A window of 8 or 16 averages the height into
        blocks first and measures the slope a wheel would actually climb.
        """
        H = self.h * (self.hz * k)
        sx, sy = self.sx, self.sy
        if window > 1:
            r, c = (self.rows // window) * window, (self.cols // window) * window
            H = H[:r, :c].reshape(r // window, window, c // window, window).mean((1, 3))
            sx, sy = sx * window, sy * window
        gx = ((H[1:, :-1] + H[1:, 1:]) - (H[:-1, :-1] + H[:-1, 1:])) / (2 * sx)
        gy = ((H[:-1, 1:] + H[1:, 1:]) - (H[:-1, :-1] + H[1:, :-1])) / (2 * sy)
        return np.hypot(gx, gy)

    def slope_deg(self, k=1.0, window=1):
        return np.degrees(np.arctan(self.gradient(k, window)))

    def height_at(self, x, y, k=1.0):
        """Bilinear sample of the world height at world (x, y)."""
        r = (x - self.x0) / self.dx
        c = (y - self.y0) / self.dy
        r = np.clip(r, 0, self.rows - 1 - 1e-9)
        c = np.clip(c, 0, self.cols - 1 - 1e-9)
        r0 = np.floor(r).astype(np.int64)
        c0 = np.floor(c).astype(np.int64)
        fr = r - r0
        fc = c - c0
        h = (self.h[r0, c0] * (1 - fr) * (1 - fc) + self.h[r0 + 1, c0] * fr * (1 - fc)
             + self.h[r0, c0 + 1] * (1 - fr) * fc + self.h[r0 + 1, c0 + 1] * fr * fc)
        return self.hz * k * h + self.z0


def base_offset(base):
    """The translate on /World/terrain1_world in the base scene."""
    layer = Sdf.Layer.FindOrOpen(str(base))
    prim = layer.GetPrimAtPath("/World/terrain1_world")
    t = prim.properties["xformOp:translate"].default if prim else None
    return np.array([float(v) for v in t]) if t is not None else np.zeros(3)


def slope_scale_for(terrain, target_deg, pct=99.0, window=1):
    """The height scale k that puts the pct-th percentile slope at the target.

    Scaling the height scales every gradient by the same factor and arctan is
    monotone, so the scale follows from one percentile of the unscaled
    gradient; there is nothing to search for.
    """
    g = terrain.gradient(1.0, window)
    g_pct = float(np.percentile(g, pct))
    return math.tan(math.radians(target_deg)) / g_pct, g_pct


def slope_summary(terrain, k, window=1):
    s = terrain.slope_deg(k, window)
    q = np.percentile(s, [50, 90, 95, 99])
    return {"p50": float(q[0]), "p90": float(q[1]), "p95": float(q[2]),
            "p99": float(q[3]), "max": float(s.max()), "mean": float(s.mean())}


# ------------------------------------------------------------------
# the obstacles

def silhouette_area(points, counts, indices):
    """Horizontal silhouette area of a closed mesh, in the mesh's own units.

    Every vertical line through a rock crosses its surface twice, once up and
    once down, so the absolute projected area of all the faces is twice the
    silhouette. The shoelace runs over all faces at once; faces may have
    different vertex counts.
    """
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    base = np.repeat(starts, counts)
    nxt = base + (np.arange(len(indices)) - base + 1) % np.repeat(counts, counts)
    x = points[indices, 0]
    y = points[indices, 2]
    cross = x * y[nxt] - x[nxt] * y
    return 0.5 * float(np.abs(0.5 * np.add.reduceat(cross, starts)).sum())


def rock_shapes(range_dir=RANGE):
    """(silhouette area, lowest point) per shipped rock, in the mesh's units."""
    from pxr import Usd, UsdGeom
    out = []
    for n in ROCK_KINDS:
        stage = Usd.Stage.Open(str(pathlib.Path(range_dir) / "rocks" / ("Rock_%d.usd" % n)))
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/World/Rock_%d/Rock_%d" % (n, n)))
        pts = np.array(mesh.GetPointsAttr().Get(), dtype=np.float64)
        cnt = np.array(mesh.GetFaceVertexCountsAttr().Get())
        idx = np.array(mesh.GetFaceVertexIndicesAttr().Get())
        out.append({"kind": n, "area": silhouette_area(pts, cnt, idx),
                    "min_y": float(pts[:, 1].min())})
    return out


def scatter(terrain, shapes, density, size_m, jitter, min_spacing_factor, rng, k,
            keepout=None):
    """Place rocks to cover `density` of the terrain footprint.

    Sizes are drawn first and cut at the point where the covered area reaches
    the target, so the count follows from the sizes rather than the other way
    round. Positions come from a jittered grid: one rock per cell, each jogged
    by at most half the slack between the cell size and the minimum spacing,
    which bounds how close two of them can end up.

    `keepout` is (x, y, radius): the cells that could put a rock inside that
    radius are taken out of the draw before the rocks are dealt, so no obstacle
    centre comes closer to the AGR than the radius and the count is unchanged.
    """
    target = density * terrain.area
    areas = np.array([s["area"] for s in shapes])
    cap = int(target / (math.pi / 4 * (size_m * (1 - jitter)) ** 2)) + 8

    diam = size_m * rng.uniform(1 - jitter, 1 + jitter, cap)
    kind = rng.integers(0, len(shapes), cap)
    foot = math.pi / 4 * diam ** 2
    n = int(np.searchsorted(np.cumsum(foot), target) + 1)
    n = min(n, cap)
    diam, kind, foot = diam[:n], kind[:n], foot[:n]
    # the uniform scale that turns the mesh's own silhouette into `foot`
    scale = np.sqrt(foot / areas[kind]) / UNITS_SCALE

    (xlo, xhi), (ylo, yhi) = terrain.bounds()
    margin = diam / 2
    lx, ly = xhi - xlo, yhi - ylo
    nx = max(1, int(math.ceil(math.sqrt(n * lx / ly))))
    ny = max(1, int(math.ceil(n / nx)))
    cx, cy = lx / nx, ly / ny

    dmin = min_spacing_factor * float(np.median(diam))
    jx = max(0.0, (cx - dmin) / 2)
    jy = max(0.0, (cy - dmin) / 2)

    usable = np.arange(nx * ny)
    if keepout is not None:
        kx, ky, kr = keepout
        ccx = xlo + (usable // ny + 0.5) * cx
        ccy = ylo + (usable % ny + 0.5) * cy
        # a rock sits at its cell centre plus up to (jx, jy) of jitter, so the
        # cells have to be excluded out to the radius plus that jitter for the
        # radius itself to be a guarantee
        usable = usable[np.hypot(ccx - kx, ccy - ky) > kr + max(jx, jy)]
    cells = rng.permutation(usable)[:n]
    n = len(cells)
    diam, kind, foot, scale, margin = diam[:n], kind[:n], foot[:n], scale[:n], margin[:n]
    ix, iy = cells // ny, cells % ny
    x = xlo + (ix + 0.5) * cx + rng.uniform(-jx, jx, n)
    y = ylo + (iy + 0.5) * cy + rng.uniform(-jy, jy, n)
    x = np.clip(x, xlo + margin, xhi - margin)
    y = np.clip(y, ylo + margin, yhi - margin)

    z = terrain.height_at(x, y, k) - UNITS_SCALE * scale * np.array(
        [shapes[i]["min_y"] for i in kind])
    yaw = rng.uniform(0, 2 * math.pi, n)

    return {"x": x, "y": y, "z": z, "yaw": yaw, "scale": scale, "kind": kind,
            "diam": diam, "foot": foot,
            "coverage": float(foot.sum() / terrain.area),
            "grid": (nx, ny), "cell": (cx, cy), "min_spacing_target": dmin,
            "min_spacing_guaranteed": min(cx - 2 * jx, cy - 2 * jy)}


def min_pair_distance(x, y):
    n = len(x)
    if n < 2:
        return float("inf")
    if n > 6000:
        return float("nan")
    d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    np.fill_diagonal(d, np.inf)
    return float(d.min())


# ------------------------------------------------------------------
# writing the layer

def prim(layer, path, typename="Xform", specifier=Sdf.SpecifierDef):
    spec = Sdf.CreatePrimInLayer(layer, Sdf.Path(path))
    spec.specifier = specifier
    if typename:
        spec.typeName = typename
    return spec


def attr(spec, name, typename, value):
    a = Sdf.AttributeSpec(spec, name, typename)
    a.default = value
    return a


def place(spec, x, y, z, yaw, scale):
    attr(spec, "xformOp:translate", Sdf.ValueTypeNames.Double3,
         Gf.Vec3d(float(x), float(y), float(z)))
    attr(spec, "xformOp:orient", Sdf.ValueTypeNames.Quatf,
         Gf.Quatf(math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)))
    attr(spec, "xformOp:scale", Sdf.ValueTypeNames.Float3,
         Gf.Vec3f(float(scale), float(scale), float(scale)))
    attr(spec, "xformOp:rotateX:unitsResolve", Sdf.ValueTypeNames.Double, 90.0)
    attr(spec, "xformOp:scale:unitsResolve", Sdf.ValueTypeNames.Double3,
         Gf.Vec3d(UNITS_SCALE, UNITS_SCALE, UNITS_SCALE))
    attr(spec, "xformOpOrder", Sdf.ValueTypeNames.TokenArray, Vt.TokenArray(XFORM_OPS))


def write_layer(out, args, terrain, k, rocks, shapes, base=BASE):
    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    layer = Sdf.Layer.CreateNew(str(out))
    here = out.parent
    layer.subLayerPaths = [rel(here, base)]
    layer.comment = ("IDDMBSE test-range design of experiments: " + summary_line(args))

    # the terrain's height scale
    t = prim(layer, TERRAIN_PRIM, "", Sdf.SpecifierOver)
    s = terrain.meta["scene_xform"]["scale"]
    attr(t, "xformOp:scale", Sdf.ValueTypeNames.Float3,
         Gf.Vec3f(float(s[0]), float(s[1]), float(k)))

    # the physics material, on the terrain and on the obstacles
    mat_path = "/World/doe_physics_material"
    mat = prim(layer, mat_path, "Material")
    mat.SetInfo("apiSchemas", Sdf.TokenListOp.CreateExplicit(["PhysicsMaterialAPI"]))
    attr(mat, "physics:staticFriction", Sdf.ValueTypeNames.Float, args.friction_static)
    attr(mat, "physics:dynamicFriction", Sdf.ValueTypeNames.Float, args.friction_dynamic)
    attr(mat, "physics:restitution", Sdf.ValueTypeNames.Float, args.restitution)

    mesh = prim(layer, TERRAIN_MESH, "", Sdf.SpecifierOver)
    bind_physics(mesh, mat_path)

    # the obstacles
    if rocks is not None and len(rocks["x"]):
        prim(layer, "/World/doe_obstacles", "Xform")
        for i in range(len(rocks["x"])):
            n = shapes[rocks["kind"][i]]["kind"]
            p = prim(layer, "/World/doe_obstacles/rock_%04d" % i, "Xform")
            p.referenceList.prependedItems.append(
                Sdf.Reference(rel(here, RANGE / "rocks" / ("Rock_%d.usd" % n))))
            place(p, rocks["x"][i], rocks["y"][i], rocks["z"][i],
                  rocks["yaw"][i], rocks["scale"][i])
            bind_physics(p, mat_path)
            collide(layer, "/World/doe_obstacles/rock_%04d/Rock_%d/Rock_%d" % (i, n, n),
                    args.obstacle_approximation)

    # where the base scene's AGR starts. Only the translate is overridden, so
    # the base scene keeps its heading and its transform order.
    if args.agr_start_x is not None and args.agr_start_y is not None:
        z = float(terrain.height_at(np.array([args.agr_start_x]),
                                    np.array([args.agr_start_y]), k)[0]) + args.agr_clearance
        p = prim(layer, CARTER_PRIM, "", Sdf.SpecifierOver)
        attr(p, "xformOp:translate", Sdf.ValueTypeNames.Double3,
             Gf.Vec3d(args.agr_start_x, args.agr_start_y, z))

    # more Carters, on a ring around the one in the base scene
    if args.multi_agr:
        cx, cy, cyaw = carter_pose(base)
        for i in range(args.multi_agr):
            a = 2 * math.pi * i / args.multi_agr
            x = cx + args.agr_ring_radius * math.cos(a)
            y = cy + args.agr_ring_radius * math.sin(a)
            z = float(terrain.height_at(np.array([x]), np.array([y]), k)[0]) \
                + args.agr_clearance
            p = prim(layer, "/World/doe_agr_%d" % (i + 1), "Xform")
            p.payloadList.prependedItems.append(
                Sdf.Payload(rel(here, ROOT / CARTER_ASSET)))
            attr(p, "xformOp:translate", Sdf.ValueTypeNames.Double3, Gf.Vec3d(x, y, z))
            attr(p, "xformOp:orient", Sdf.ValueTypeNames.Quatf,
                 Gf.Quatf(math.cos(cyaw / 2), 0.0, 0.0, math.sin(cyaw / 2)))
            attr(p, "xformOp:scale", Sdf.ValueTypeNames.Float3, Gf.Vec3f(1, 1, 1))
            attr(p, "xformOpOrder", Sdf.ValueTypeNames.TokenArray,
                 Vt.TokenArray(["xformOp:translate", "xformOp:orient", "xformOp:scale"]))

    # the multi-modal sensor rig
    if args.sensor_payload:
        cx, cy, cyaw = carter_pose(base)
        x, y = cx + args.agr_ring_radius, cy
        z = float(terrain.height_at(np.array([x]), np.array([y]), k)[0]) + args.agr_clearance
        p = prim(layer, "/World/doe_nova_carter", "Xform")
        asset = NOVA_CARTER_URL.format(ver=args.nova_carter_version)
        if args.nova_carter_local:
            asset = rel(here, ROOT / "range" / "assets" / "Assets" / "Isaac"
                        / args.nova_carter_version / "Isaac" / "Samples" / "ROS2"
                        / "Robots" / "Nova_Carter_ROS.usd")
        p.payloadList.prependedItems.append(Sdf.Payload(asset))
        attr(p, "xformOp:translate", Sdf.ValueTypeNames.Double3, Gf.Vec3d(x, y, z))
        attr(p, "xformOp:orient", Sdf.ValueTypeNames.Quatf,
             Gf.Quatf(math.cos(cyaw / 2), 0.0, 0.0, math.sin(cyaw / 2)))
        attr(p, "xformOp:scale", Sdf.ValueTypeNames.Float3, Gf.Vec3f(1, 1, 1))
        attr(p, "xformOpOrder", Sdf.ValueTypeNames.TokenArray,
             Vt.TokenArray(["xformOp:translate", "xformOp:orient", "xformOp:scale"]))

    layer.Save()
    return out


def collide(layer, mesh_path, approximation):
    """Make a referenced rock mesh a static collider.

    The rock assets carry geometry only, so without this the obstacles are
    scenery: the robot drives through them and the density knob changes
    nothing a trial can measure.
    """
    spec = prim(layer, mesh_path, "", Sdf.SpecifierOver)
    op = Sdf.TokenListOp()
    op.prependedItems = ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI"]
    spec.SetInfo("apiSchemas", op)
    attr(spec, "physics:collisionEnabled", Sdf.ValueTypeNames.Bool, True)
    attr(spec, "physics:approximation", Sdf.ValueTypeNames.Token, approximation)
    return spec


def bind_physics(spec, mat_path):
    """Bind a physics material, adding MaterialBindingAPI without replacing
    whatever the weaker layers already applied."""
    op = Sdf.TokenListOp()
    op.prependedItems = ["MaterialBindingAPI"]
    spec.SetInfo("apiSchemas", op)
    rel_spec = Sdf.RelationshipSpec(spec, "material:binding:physics", False)
    rel_spec.targetPathList.explicitItems.append(Sdf.Path(mat_path))


def carter_pose(base):
    layer = Sdf.Layer.FindOrOpen(str(base))
    spec = layer.GetPrimAtPath(CARTER_PRIM)
    t = spec.properties["xformOp:translate"].default
    q = spec.properties["xformOp:orient"].default
    yaw = 2 * math.atan2(q.GetImaginary()[2], q.GetReal())
    return float(t[0]), float(t[1]), yaw


def rel(here, target):
    """A relative path when the output sits near the assets, absolute if not."""
    p = os.path.relpath(str(target), str(here))
    if p.count("..") > 3:
        return str(pathlib.Path(target).resolve())
    return p if p.startswith(".") else "./" + p


def summary_line(args):
    return ("density=%s slope_p99=%s friction=%s/%s restitution=%s seed=%s"
            % (args.obstacle_density, args.max_slope_deg, args.friction_static,
               args.friction_dynamic, args.restitution, args.seed))


# ------------------------------------------------------------------

def run(args):
    terrain = Terrain(args.npz, args.meta, args.base)
    w = args.slope_window
    before = slope_summary(terrain, 1.0, w)
    if args.max_slope_deg is None:
        k = 1.0
    else:
        k, _ = slope_scale_for(terrain, args.max_slope_deg, args.slope_percentile, w)
    after = slope_summary(terrain, k, w)

    rng = np.random.default_rng(args.seed)
    shapes = rock_shapes(pathlib.Path(args.base).parent)
    if args.agr_start_x is not None and args.agr_start_y is not None:
        agr = (args.agr_start_x, args.agr_start_y)
    else:
        agr = carter_pose(args.base)[:2]
    keepout = (agr[0], agr[1], args.agr_keepout_radius)
    rocks = None
    if args.obstacle_density > 0:
        rocks = scatter(terrain, shapes, args.obstacle_density, args.rock_size,
                        args.rock_size_jitter, args.min_spacing_factor, rng, k,
                        keepout=keepout)

    out = write_layer(args.out, args, terrain, k, rocks, shapes, args.base)

    report = {
        "out": str(out), "seed": args.seed,
        "terrain_footprint_m2": terrain.area,
        "height_scale": k,
        "slope_window_cells": w,
        "slope_window_m": [terrain.sx * w, terrain.sy * w],
        "slope_percentile": args.slope_percentile,
        "slope_deg_before": before, "slope_deg_after": after,
        "requested_density": args.obstacle_density,
        "obstacle_count": 0 if rocks is None else int(len(rocks["x"])),
        "obstacle_approximation": args.obstacle_approximation,
        "agr_keepout": [float(keepout[0]), float(keepout[1]), float(keepout[2])],
        "realised_coverage": 0.0 if rocks is None else rocks["coverage"],
        "obstacle_diameter_m": None if rocks is None else
            [float(rocks["diam"].min()), float(np.median(rocks["diam"])),
             float(rocks["diam"].max())],
        "min_spacing_guaranteed_m": None if rocks is None else
            float(rocks["min_spacing_guaranteed"]),
        "min_spacing_measured_m": None if rocks is None else
            min_pair_distance(rocks["x"], rocks["y"]),
        "physics": {"static_friction": args.friction_static,
                    "dynamic_friction": args.friction_dynamic,
                    "restitution": args.restitution},
        "agr_start": None if args.agr_start_x is None or args.agr_start_y is None else
            [args.agr_start_x, args.agr_start_y,
             float(terrain.height_at(np.array([args.agr_start_x]),
                                     np.array([args.agr_start_y]), k)[0]) + args.agr_clearance],
        "extra_agr": args.multi_agr,
        "sensor_payload": bool(args.sensor_payload),
        "layer_bytes": out.stat().st_size,
    }
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--obstacle-density", type=float, default=0.4)
    ap.add_argument("--max-slope-deg", type=float)
    ap.add_argument("--slope-window", type=int, default=1,
                    help="average the heightmap into NxN blocks before measuring slope")
    ap.add_argument("--slope-percentile", type=float, default=99.0)
    ap.add_argument("--friction-static", type=float, default=0.7)
    ap.add_argument("--friction-dynamic", type=float, default=0.6)
    ap.add_argument("--restitution", type=float, default=0.0)
    ap.add_argument("--rock-size", type=float, default=2.0,
                    help="obstacle footprint diameter in metres")
    ap.add_argument("--rock-size-jitter", type=float, default=0.5)
    ap.add_argument("--min-spacing-factor", type=float, default=0.5)
    ap.add_argument("--obstacle-approximation", default="convexHull",
                    help="PhysX collision approximation for the obstacles")
    ap.add_argument("--agr-start-x", type=float,
                    help="move the base scene's AGR here and seat it on the terrain")
    ap.add_argument("--agr-start-y", type=float)
    ap.add_argument("--multi-agr", type=int, default=0)
    ap.add_argument("--agr-ring-radius", type=float, default=4.0)
    ap.add_argument("--agr-clearance", type=float, default=0.3)
    ap.add_argument("--agr-keepout-radius", type=float, default=3.0,
                    help="no obstacle is dealt a cell whose centre is this close "
                         "to the AGR's start, in metres")
    ap.add_argument("--sensor-payload", action="store_true")
    ap.add_argument("--nova-carter-version", default="4.1")
    ap.add_argument("--nova-carter-local", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--base", type=pathlib.Path, default=BASE)
    ap.add_argument("--npz", type=pathlib.Path, default=NPZ)
    ap.add_argument("--meta", type=pathlib.Path, default=META)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not 0 <= args.obstacle_density <= 0.9:
        raise SystemExit("--obstacle-density is a fraction, 0 to 0.9")
    if not 0 <= args.rock_size_jitter < 1:
        raise SystemExit("--rock-size-jitter is a fraction of the size, 0 to 1")

    report = run(args)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        b, a = report["slope_deg_before"], report["slope_deg_after"]
        print("terrain footprint", round(report["terrain_footprint_m2"], 1), "m2")
        print("slope before  p50", round(b["p50"], 2), "p90", round(b["p90"], 2),
              "p99", round(b["p99"], 2), "max", round(b["max"], 2))
        print("height scale", round(report["height_scale"], 5))
        print("slope after   p50", round(a["p50"], 2), "p90", round(a["p90"], 2),
              "p99", round(a["p99"], 2), "max", round(a["max"], 2))
        print("obstacles", report["obstacle_count"], "covering",
              round(report["realised_coverage"], 4), "of the footprint",
              "(asked for", str(report["requested_density"]) + ")")
        if report["obstacle_diameter_m"]:
            print("obstacle diameter m: min/median/max",
                  [round(v, 2) for v in report["obstacle_diameter_m"]],
                  " min spacing guaranteed", round(report["min_spacing_guaranteed_m"], 3),
                  "measured", round(report["min_spacing_measured_m"], 3))
        print("wrote", report["out"], report["layer_bytes"], "bytes")


if __name__ == "__main__":
    main()
