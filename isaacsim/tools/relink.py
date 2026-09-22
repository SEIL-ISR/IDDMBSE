"""List and rewrite the external asset paths of a USD layer.

Five modes:
  --dry-run          print every external asset path, bucketed, with counts
  --check            exit 1 if any path, live or dead, is an omniverse:// URL,
                     an http(s) URL, or points into a user home directory;
                     --allow-http excuses the URLs, which is what a layer left
                     in cloud mode needs; other absolute paths are warnings
  --apply            rewrite paths using a JSON table of {"old": ..., "new": ...}
  --strip-dead-paths drop dead entries whose path starts with one of the
                     prefixes in a JSON list, then save
  --mode local|cloud swap between the downloaded mirror under range/assets and
                     the content CDN, using range/assets/MANIFEST.json as the
                     table. Local paths are relative to each layer's own
                     directory, so the mirror can sit anywhere the repository
                     does.

A reference or payload list op has several item lists. Everything except
"deleted" composes into the stage; a "deleted" entry only removes a matching
arc contributed by a stronger layer, so those paths resolve to nothing here.
This script calls them dead and keeps them apart from the live ones.

Dropping a dead entry that nothing contributes is a composition no-op, which
is what --strip-dead-paths relies on: it is for getting an authoring machine's
directory layout out of a file that is about to be published, not for changing
what the layer composes to. Prim-path invariance is worth re-checking after it
either way.

Only asset paths are touched. Prims, attributes, and every other opinion in
the layer are left as they are.
"""

import argparse
import json
import pathlib
import sys

from pxr import Sdf

BUCKETS = ["relative", "absolute-file", "omniverse", "http", "other"]


def bucket(path):
    if path.startswith("omniverse://"):
        return "omniverse"
    if path.startswith("http:/") or path.startswith("https:/"):
        return "http"
    if path.startswith("file:/") or path.startswith("/"):
        return "absolute-file"
    if "://" not in path:
        return "relative"
    return "other"


def in_home(path):
    return path.startswith("/home/") or path.startswith("file:/home/")


def listop_items(listop):
    """(item, live) for every item in a reference or payload list op."""
    items = []
    for group in (listop.explicitItems, listop.addedItems, listop.prependedItems,
                  listop.appendedItems, listop.orderedItems):
        items.extend((i, True) for i in group)
    items.extend((i, False) for i in listop.deletedItems)
    return items


def collect(layer):
    """Every external asset path, as (kind, spec path, asset path, live)."""
    found = []
    for p in layer.subLayerPaths:
        found.append(("sublayer", "/", p, True))

    asset_types = (Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray)

    def visit(path):
        spec = layer.GetObjectAtPath(path)
        if isinstance(spec, Sdf.PrimSpec):
            for kind, listop in (("reference", spec.referenceList),
                                 ("payload", spec.payloadList)):
                for item, live in listop_items(listop):
                    if item.assetPath:
                        found.append((kind, str(path), item.assetPath, live))
        elif isinstance(spec, Sdf.AttributeSpec):
            if spec.typeName in asset_types:
                value = spec.default
                if value is None:
                    return
                values = value if isinstance(value, Sdf.AssetPathArray) else [value]
                for v in values:
                    if v.path:
                        found.append(("attribute", str(path), v.path, True))

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return found


def report(name, found):
    live = [f for f in found if f[3]]
    dead = [f for f in found if not f[3]]
    print(name)
    print("  external asset paths:", len(found), "live:", len(live), "dead:", len(dead))
    for label, group in (("live", live), ("dead", dead)):
        c = dict.fromkeys(BUCKETS, 0)
        for _, _, path, _ in group:
            c[bucket(path)] += 1
        print("   ", label, " ".join(b + "=" + str(c[b]) for b in BUCKETS))
    seen = {}
    for kind, spec, path, is_live in found:
        seen.setdefault((bucket(path), "live" if is_live else "dead", path), []).append((kind, spec))
    for (b, label, path), uses in sorted(seen.items()):
        print("   ", b, label, len(uses), path)
        if b != "relative":
            for kind, spec in uses:
                print("        ", kind, spec)


def rewrite_attributes(layer, table):
    """Rewrite asset-valued attributes; UpdateExternalReference covers only arcs."""
    asset_types = (Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray)
    edits = []

    def visit(path):
        spec = layer.GetObjectAtPath(path)
        if not isinstance(spec, Sdf.AttributeSpec):
            return
        if spec.typeName not in asset_types:
            return
        value = spec.default
        if value is None:
            return
        if isinstance(value, Sdf.AssetPathArray):
            paths = [v.path for v in value]
            if any(p in table for p in paths):
                edits.append((path, Sdf.AssetPathArray(
                    [Sdf.AssetPath(table.get(p, p)) for p in paths])))
        elif value.path in table:
            edits.append((path, Sdf.AssetPath(table[value.path])))

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    for path, new_value in edits:
        layer.GetObjectAtPath(path).default = new_value
    return len(edits)


def apply(layer, table):
    present = {path for _, _, path, _ in collect(layer)}
    applied = []
    for old, new in table.items():
        if old not in present:
            continue
        layer.UpdateExternalReference(old, new)
        applied.append((old, new))
    n_attr = rewrite_attributes(layer, table)
    return applied, n_attr


def strip_dead_paths(layer, prefixes):
    """Drop dead reference and payload entries matching any of the prefixes."""
    dropped = []

    def visit(path):
        spec = layer.GetObjectAtPath(path)
        if not isinstance(spec, Sdf.PrimSpec):
            return
        for listop in (spec.referenceList, spec.payloadList):
            dead = list(listop.deletedItems)
            hit = [i.assetPath.startswith(tuple(prefixes)) for i in dead]
            if any(hit):
                dropped.extend((str(path), i.assetPath)
                               for i, h in zip(dead, hit) if h)
                listop.deletedItems = [i for i, h in zip(dead, hit) if not h]

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return dropped


def mode_table(manifest_path, layer_path, to_local, layer_home=None):
    """url <-> relative local path, for one layer's directory.

    layer_home overrides that directory, for rewriting a working copy that
    will be installed somewhere else.
    """
    import os
    manifest = pathlib.Path(manifest_path).resolve()
    root = manifest.parents[2]
    here = pathlib.Path(layer_home or layer_path).resolve().parent
    table = {}
    for e in json.loads(manifest.read_text())["files"]:
        local = os.path.relpath(str(root / e["path"]), str(here))
        if not local.startswith("."):
            local = "./" + local
        if to_local:
            table[e["url"]] = local
        else:
            table[local] = e["url"]
    return table


def check(name, found, allow_http=False):
    def is_bad(path):
        if bucket(path) == "omniverse" or in_home(path):
            return True
        return bucket(path) == "http" and not allow_http

    counts = {"omniverse": 0, "http": 0, "home": 0}
    for _, _, path, _ in found:
        if bucket(path) == "omniverse":
            counts["omniverse"] += 1
        elif bucket(path) == "http":
            counts["http"] += 1
        if in_home(path):
            counts["home"] += 1

    bad = [f for f in found if is_bad(f[2])]
    warn = [f for f in found
            if bucket(f[2]) == "absolute-file" and not in_home(f[2])]
    for kind, spec, path, is_live in warn:
        print("   WARN", "live" if is_live else "dead", kind, spec, path)
    print("   counts: omniverse=%d http=%d home=%d warnings=%d"
          % (counts["omniverse"], counts["http"], counts["home"], len(warn)))
    if bad:
        print("FAIL", name, len(bad), "disallowed paths")
        seen = set()
        for kind, spec, path, is_live in bad:
            if path not in seen:
                seen.add(path)
                print("   ", "live" if is_live else "dead", kind, spec, path)
    else:
        print("OK", name)
    return len(bad)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layers", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", metavar="TABLE.json")
    ap.add_argument("--strip-dead-paths", metavar="PREFIXES.json")
    ap.add_argument("--mode", choices=("local", "cloud"))
    ap.add_argument("--manifest", default=str(
        pathlib.Path(__file__).resolve().parent.parent / "range" / "assets"
        / "MANIFEST.json"))
    ap.add_argument("--allow-http", action="store_true")
    ap.add_argument("--layer-home", help="compute --mode paths as if the layer "
                                         "lived here")
    args = ap.parse_args()

    bad = 0
    for path in args.layers:
        layer = Sdf.Layer.FindOrOpen(path)
        if layer is None:
            print("cannot open", path)
            return 2

        if args.mode:
            table = mode_table(args.manifest, path, args.mode == "local",
                               args.layer_home)
            applied, n_attr = apply(layer, table)
            print("mode", args.mode, "arc rewrites:", len(applied),
                  "attribute rewrites:", n_attr, path)
            if applied or n_attr:
                layer.Save()

        if args.apply:
            table = {e["old"]: e["new"] for e in json.load(open(args.apply))}
            applied, n_attr = apply(layer, table)
            for old, new in applied:
                print("rewrote", old, "->", new)
            print("arc rewrites:", len(applied), "attribute rewrites:", n_attr)
            if applied or n_attr:
                layer.Save()
                print("saved", path)
            else:
                print("no change", path)

        if args.strip_dead_paths:
            prefixes = json.load(open(args.strip_dead_paths))
            dropped = strip_dead_paths(layer, prefixes)
            for spec, asset in dropped:
                print("dropped dead", spec, asset)
            print("dead entries dropped:", len(dropped))
            if dropped:
                layer.Save()
                print("saved", path)
            else:
                print("no change", path)

        if args.dry_run:
            report(path, collect(layer))

        if args.check:
            bad += check(path, collect(layer), args.allow_http)

    return 1 if bad else 0


sys.exit(main())
