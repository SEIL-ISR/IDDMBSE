"""Set attribute defaults in a USD layer from a JSON table.

    python set_attrs.py TABLE.json LAYER.usd

The table is a list of {"path": "/prim.attribute", "value": ...} and an
optional "why". Only attributes that already exist in the layer are written;
anything else is reported and skipped, so a table cannot quietly introduce a
property the scene never had.

This is here for the handful of scalar constants in the range that were wrong
for the robot in it -- the teleop graph's wheel geometry, which was still
TurtleBot3's.
"""

import argparse
import json
import sys

from pxr import Sdf


def apply_table(layer, table):
    done, skipped = [], []
    for entry in table:
        spec = layer.GetObjectAtPath(Sdf.Path(entry["path"]))
        if not isinstance(spec, Sdf.AttributeSpec):
            skipped.append((entry["path"], "no such attribute in this layer"))
            continue
        old = spec.default
        spec.default = entry["value"]
        done.append((entry["path"], old, spec.default, entry.get("why", "")))
    return done, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table")
    ap.add_argument("layer")
    args = ap.parse_args()

    layer = Sdf.Layer.FindOrOpen(args.layer)
    if layer is None:
        return 2
    done, skipped = apply_table(layer, json.load(open(args.table)))
    for path, old, new, why in done:
        print("set", path, old, "->", new, why)
    for path, why in skipped:
        print("SKIPPED", path, why)
    if done:
        layer.Save()
        print("saved", args.layer)
    return 1 if skipped else 0


sys.exit(main())
