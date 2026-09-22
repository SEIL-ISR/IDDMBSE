"""Rewrite a USD layer into a fresh crate file, optionally dropping attributes.

    python compact.py IN.usd OUT.usd [--drop-attr-prefix physxCookedData] ...

A crate file that has been edited in place keeps the space its old versions
occupied; writing the same content into a new file gives it back. The copy is
made with Sdf.Layer.TransferContent, which moves every spec and every field,
so nothing but the free space is lost.

--drop-attr-prefix removes attribute specs whose name starts with the given
string, after the transfer. The one this is for is physxCookedData, PhysX's
cached collision mesh: it is derived data, Kit recooks it on load, and on the
test-range terrain it is 750 MB of the 1.5 GB layer. The collision setup
itself -- the PhysicsCollisionAPI, PhysicsMeshCollisionAPI and the
physics:approximation attribute -- is not touched.
"""

import argparse
import time

from pxr import Sdf


def dropped_attrs(layer, prefixes):
    """Attribute spec paths whose name starts with one of the prefixes."""
    hits = []

    def visit(path):
        spec = layer.GetObjectAtPath(path)
        if isinstance(spec, Sdf.AttributeSpec) and spec.name.startswith(prefixes):
            size = len(spec.default) if spec.default is not None else 0
            hits.append((path, size))

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return hits


def compact(src_path, dst_path, prefixes=()):
    src = Sdf.Layer.FindOrOpen(src_path)
    if src is None:
        raise SystemExit("cannot open " + src_path)
    dst = Sdf.Layer.CreateNew(dst_path, args={"format": "usdc"})
    dst.TransferContent(src)

    hits = dropped_attrs(dst, tuple(prefixes)) if prefixes else []
    for path, _ in hits:
        prim = dst.GetPrimAtPath(path.GetPrimPath())
        prim.RemoveProperty(prim.properties[path.name])

    dst.Save()
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--drop-attr-prefix", action="append", default=[])
    args = ap.parse_args()

    t0 = time.time()
    hits = compact(args.src, args.dst, args.drop_attr_prefix)
    dt = time.time() - t0

    import os
    a, b = os.path.getsize(args.src), os.path.getsize(args.dst)
    for path, size in sorted(hits, key=lambda h: -h[1]):
        print("dropped", path, size, "bytes")
    print("dropped attributes:", len(hits), "holding", sum(h[1] for h in hits), "bytes")
    print(args.src, a, "bytes ->", args.dst, b, "bytes  in", round(dt, 1), "s")


main()
