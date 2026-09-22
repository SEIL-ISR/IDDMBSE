"""Build the test-range terrain mesh from the shipped heightmap.

    python build_terrain.py                        # full resolution
    python build_terrain.py --decimate 4           # every 4th grid line
    python build_terrain.py --from-obj terrain_low.obj   # re-extract the heightmap

The range terrain was authored in WorldCreator and exported as a 2048x2048
quad grid in a 467 MB Wavefront OBJ. Only the height column of that file is
not implied by the grid, so what this repository ships is the height column --
range/terrain/heightmap.npz, float32, plus range/terrain/terrain_meta.json --
and this script rebuilds the mesh from it into range/generated/terrain_low.usd.

The rebuilt mesh has the OBJ's point order and face topology exactly, so the
scene's existing opinions on /World/terrain1/terrain_low/mesh -- the collision
APIs, the physics material binding -- land on the same prim as before, and the
scene's own transform on /World/terrain1 still places it correctly.

Axis convention: the OBJ is Y-up in centimetres, which is what the scene's
xformOp:rotateX:unitsResolve and xformOp:scale:unitsResolve on /World/terrain1
undo. The heightmap keeps the OBJ's own units and axes, so nothing here has to
know about that transform; terrain_meta.json records it for the tools that do.
"""

import argparse
import io
import json
import mmap
import pathlib
import time

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

HERE = pathlib.Path(__file__).resolve().parent
RANGE = HERE.parent / "range"
DEFAULT_NPZ = RANGE / "terrain" / "heightmap.npz"
DEFAULT_META = RANGE / "terrain" / "terrain_meta.json"
DEFAULT_OUT = RANGE / "generated" / "terrain_low.usd"

# the scene's transform on /World/terrain1, read out of range/terrain1_world.usd
SCENE_XFORM = {
    "prim": "/World/terrain1",
    "xformOpOrder": ["xformOp:translate", "xformOp:orient", "xformOp:scale",
                     "xformOp:rotateX:unitsResolve", "xformOp:scale:unitsResolve"],
    "translate": [49.32903289251568, 49.11372589076184, 0.0],
    "orient": [1.0, 0.0, 0.0, 0.0],
    "scale": [2.42, 2.37976, 1.0],
    "rotateX_unitsResolve_deg": 90.0,
    "scale_unitsResolve": [0.01, 0.01, 0.01],
    # the composed local-to-world map, obj (x, y, z) -> world (x, y, z), as
    # UsdGeom computes it: x_w = 0.0242*x + 49.329033, y_w = -0.023798*z +
    # 49.113726, z_w = 0.01*y
    "obj_to_world": {"x_from_obj_x": 0.0242, "x_offset": 49.32903289251568,
                     "y_from_obj_z": -0.0237976, "y_offset": 49.11372589076184,
                     "z_from_obj_y": 0.01, "z_offset": 0.0},
}


# ------------------------------------------------------------------
# reading the OBJ

def read_obj(path):
    """(vertices, faces) from a Wavefront OBJ of quads with v/vt indices."""
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        v0 = mm.find(b"\nv ") + 1
        vt0 = mm.find(b"\nvt ") + 1
        f0 = mm.find(b"\nf ") + 1
        verts = np.loadtxt(io.BytesIO(mm[v0:vt0]), usecols=(1, 2, 3))
        uvs = np.loadtxt(io.BytesIO(mm[vt0:f0]), usecols=(1, 2))
        face_block = mm[f0:].replace(b"/", b" ")
        faces = np.loadtxt(io.BytesIO(face_block), usecols=(1, 3, 5, 7),
                           dtype=np.int64)
        mm.close()
    return verts, uvs, faces


def infer_grid(verts, faces):
    """Grid shape and spacing, checked against the face indices.

    The exporter writes the points in row-major order with x on the slow axis
    and z on the fast one; this reads that back off the data rather than
    assuming it, and then checks every quad against the grid it implies.
    """
    n = len(verts)
    # the fast axis runs until x changes
    stride = int(np.argmax(verts[:, 0] != verts[0, 0]))
    rows = n // stride
    assert rows * stride == n, "vertex count is not a multiple of the row stride"

    x = verts[:, 0].reshape(rows, stride)
    z = verts[:, 2].reshape(rows, stride)
    dx = x[1, 0] - x[0, 0]
    dz = z[0, 1] - z[0, 0]
    ok_x = np.allclose(x, x[0, 0] + dx * np.arange(rows)[:, None])
    ok_z = np.allclose(z, z[0, 0] + dz * np.arange(stride)[None, :])

    i = (np.arange(rows - 1)[:, None] * stride + np.arange(stride - 1)[None, :])
    want = np.stack([i, i + stride, i + stride + 1, i + 1], -1).reshape(-1, 4) + 1
    ok_f = faces.shape == want.shape and bool(np.array_equal(faces, want))
    return {"rows": rows, "cols": stride, "dx": float(dx), "dz": float(dz),
            "x0": float(x[0, 0]), "z0": float(z[0, 0]),
            "x_regular": bool(ok_x), "z_regular": bool(ok_z),
            "faces_match_grid": ok_f}


def extract(obj_path, npz_path, meta_path):
    t0 = time.time()
    verts, uvs, faces = read_obj(obj_path)
    grid = infer_grid(verts, faces)
    print("vertices", len(verts), "faces", len(faces), "grid", grid)
    if not (grid["x_regular"] and grid["z_regular"] and grid["faces_match_grid"]):
        raise SystemExit("the OBJ is not the regular quad grid this script assumes")

    rows, cols = grid["rows"], grid["cols"]
    h = verts[:, 1].reshape(rows, cols).astype(np.float32)

    # the uvs are implied by the grid too, so they are regenerated rather than
    # stored; check that before throwing them away
    want_uv = grid_uv(rows, cols).reshape(-1, 2)
    uv_err = float(np.abs(uvs - want_uv).max())
    print("uv max abs error against (col/(cols-1), row/(rows-1)):", uv_err)

    meta = {
        "source_obj": pathlib.Path(obj_path).name,
        "rows": rows, "cols": cols,
        "axis_convention": "OBJ is Y-up: column 0 is x, column 1 is height, "
                           "column 2 is z; heights are stored in the OBJ's own units",
        "row_axis": "x", "col_axis": "z",
        "x0": grid["x0"], "dx": grid["dx"],
        "z0": grid["z0"], "dz": grid["dz"],
        "x_extent": [float(min(grid["x0"], grid["x0"] + grid["dx"] * (rows - 1))),
                     float(max(grid["x0"], grid["x0"] + grid["dx"] * (rows - 1)))],
        "z_extent": [float(min(grid["z0"], grid["z0"] + grid["dz"] * (cols - 1))),
                     float(max(grid["z0"], grid["z0"] + grid["dz"] * (cols - 1)))],
        "height_min": float(h.min()), "height_max": float(h.max()),
        "height_offset": 0.0,
        "uv": "regenerated as (col/(cols-1), row/(rows-1)); max abs error "
              "against the OBJ's vt block at extraction time: " + str(uv_err),
        "prim_path_in_scene": "/World/terrain1/terrain_low/mesh",
        "default_prim": "terrain",
        "scene_xform": SCENE_XFORM,
    }
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz_path, height=h)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print("wrote", npz_path, npz_path.stat().st_size, "bytes")
    print("wrote", meta_path)
    print("extraction took", round(time.time() - t0, 1), "s")


# ------------------------------------------------------------------
# building the USD

def grid_uv(rows, cols):
    """(u, v) per grid point: u runs along the columns, v along the rows."""
    uv = np.empty((rows, cols, 2), dtype=np.float64)
    uv[..., 0] = np.arange(cols) / max(cols - 1, 1)
    uv[..., 1] = (np.arange(rows) / max(rows - 1, 1))[:, None]
    return uv


def grid_mesh(h, meta, stride=1):
    """points, faceVertexIndices, normals, st for the (decimated) heightfield."""
    h = h[::stride, ::stride]
    rows, cols = h.shape
    x = meta["x0"] + meta["dx"] * stride * np.arange(rows, dtype=np.float64)
    z = meta["z0"] + meta["dz"] * stride * np.arange(cols, dtype=np.float64)

    points = np.empty((rows, cols, 3), dtype=np.float32)
    points[..., 0] = x[:, None]
    points[..., 1] = h
    points[..., 2] = z[None, :]

    i = (np.arange(rows - 1)[:, None] * cols + np.arange(cols - 1)[None, :])
    faces = np.stack([i, i + cols, i + cols + 1, i + 1], -1).reshape(-1, 4)

    # y = h(x, z) so the surface normal is proportional to (-dh/dx, 1, -dh/dz)
    dh_dx = np.gradient(h.astype(np.float64), meta["dx"] * stride, axis=0)
    dh_dz = np.gradient(h.astype(np.float64), meta["dz"] * stride, axis=1)
    normals = np.stack([-dh_dx, np.ones_like(dh_dx), -dh_dz], -1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)

    st = grid_uv(rows, cols)

    return (points.reshape(-1, 3), faces.astype(np.int32),
            normals.reshape(-1, 3).astype(np.float32),
            st.reshape(-1, 2).astype(np.float32))


def build(npz_path, meta_path, out_path, stride=1):
    t0 = time.time()
    h = np.load(npz_path)["height"]
    meta = json.loads(meta_path.read_text())
    points, faces, normals, st = grid_mesh(h, meta, stride)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    stage = Usd.Stage.CreateNew(str(out_path))
    root = UsdGeom.Xform.Define(stage, "/terrain")
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.Xform.Define(stage, "/terrain/terrain_low")
    mesh = UsdGeom.Mesh.Define(stage, "/terrain/terrain_low/mesh")

    mesh.CreatePointsAttr(Vt_vec3f(points))
    mesh.CreateFaceVertexCountsAttr(Vt_int(np.full(len(faces), 4, np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt_int(faces.reshape(-1)))
    mesh.CreateNormalsAttr(Vt_vec3f(normals))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    lo, hi = points.min(0), points.max(0)
    mesh.CreateExtentAttr([Gf.Vec3f(*lo.tolist()), Gf.Vec3f(*hi.tolist())])

    api = UsdGeom.PrimvarsAPI(mesh)
    pv = api.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                           UsdGeom.Tokens.vertex)
    pv.Set(Vt_vec2f(st))

    prim = mesh.GetPrim()
    UsdPhysics.CollisionAPI.Apply(prim)
    UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr(
        UsdPhysics.Tokens.none)
    prim.GetAttribute("physics:collisionEnabled").Set(True)

    stage.GetRootLayer().Save()
    dt = time.time() - t0
    print("grid", h.shape, "stride", stride, "-> points", len(points),
          "faces", len(faces))
    print("bbox obj-space min", [round(float(v), 4) for v in lo],
          "max", [round(float(v), 4) for v in hi])
    print("wrote", out_path, out_path.stat().st_size, "bytes in", round(dt, 1), "s")


def Vt_vec3f(a):
    from pxr import Vt
    return Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(a, dtype=np.float32))


def Vt_vec2f(a):
    from pxr import Vt
    return Vt.Vec2fArray.FromNumpy(np.ascontiguousarray(a, dtype=np.float32))


def Vt_int(a):
    from pxr import Vt
    return Vt.IntArray.FromNumpy(np.ascontiguousarray(a, dtype=np.int32))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-obj", metavar="OBJ")
    ap.add_argument("--npz", type=pathlib.Path, default=DEFAULT_NPZ)
    ap.add_argument("--meta", type=pathlib.Path, default=DEFAULT_META)
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    ap.add_argument("--decimate", type=int, default=1)
    args = ap.parse_args()

    if args.from_obj:
        extract(args.from_obj, args.npz, args.meta)
    else:
        build(args.npz, args.meta, args.out, args.decimate)


if __name__ == "__main__":
    main()
