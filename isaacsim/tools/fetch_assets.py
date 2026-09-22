"""Download the external content the test-range scene references.

    python fetch_assets.py --group range   # the test range's own content
    python fetch_assets.py                 # everything the manifest lists
    python fetch_assets.py --check         # hash what is already on disk, download nothing
    python fetch_assets.py --build-manifest   # crawl the scene, download, write the manifest
    python fetch_assets.py --regroup       # re-label the manifest from a local mirror
    python fetch_assets.py --isaacsim-path ~/isaacsim   # also fix the two character scripts

The repository ships the scene, not the content it stands on. The vegetation,
the ground and wall materials, the two animated characters and the Carter
robot are NVIDIA's, published on NVIDIA's content CDN; the sky is a Poly Haven
HDRI. This downloads them into range/assets/ (and range/HDRI/ for the sky),
laid out under the same relative paths they have on the CDN, and checks each
file against the size and SHA-256 in range/assets/MANIFEST.json.

The scene layers refer to these files by relative path once relink.py has been
run in local mode, which is how they are shipped. `relink.py --mode cloud`
puts the CDN URLs back if you would rather stream them.

Each entry carries the group it belongs to: "range" for what the test range
itself needs, "showcases" for what the two warehouse showcase layers pull in,
"range+showcases" for the files both reach. The showcases sit on Isaac Sim
stock environments and are much the larger download, so --group range is the
one to start with.

Both of those read the CDN urls out of the shipped layers, so run
`relink.py --mode cloud` on them first if they are in local mode.

--build-manifest is the authoring side: it walks the shipped layers, follows
every USD reference and every MDL texture it finds, downloads each once and
records what came back. --regroup redoes only the labelling, from files that
are already downloaded, without touching the network. Re-run them when the
scene's content changes.
"""

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from pxr import Sdf

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = ROOT / "range" / "assets" / "MANIFEST.json"

# the layers the crawl starts from, and the group each one feeds
SEED_LAYERS = ["range/sim_world2.usd", "range/terrain1_world.usd", "range/teleop.usd",
               "showcases/warehouse_iros_v1.usd", "showcases/warehouse_nvblox.usd"]


def group_of(layer_rel):
    return "showcases" if layer_rel.startswith("showcases/") else "range"

# the sky. The lab's copy of this file is byte-identical to Poly Haven's, which
# is where it came from; it is CC0 there, and 192 MB, so it is fetched rather
# than shipped.
POLYHAVEN_HDR = {
    "path": "range/HDRI/industrial_sunset_puresky_16k.hdr",
    "url": "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/16k%2B/industrial_sunset_puresky_16k.hdr",
    "source": "polyhaven",
    "group": "range",
}

USD_SUFFIXES = (".usd", ".usda", ".usdc", ".usdz")
TEXTURE_IN_MDL = re.compile(rb'texture_2d\s*\(\s*"([^"]+)"')
# a relative MDL module, as in: using ..::Templates::GlassWithVolume import ...
MODULE_IN_MDL = re.compile(rb'(?:using|import)\s+(\.{1,2}(?:::[A-Za-z0-9_]+)+)')
# a sibling MDL module named without a leading ::, as in: import GlassUtils::foo
SIBLING_IN_MDL = re.compile(rb'(?:using|import)\s+([A-Za-z_][A-Za-z0-9_]*)(?=::)')

CHARACTER_SCRIPT = "character_behavior.py"


# ------------------------------------------------------------------
# http

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "iddmbse-fetch-assets/1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def cdn_path(url):
    """The path part of a CDN url, used as the local path under range/assets."""
    return urllib.parse.unquote(urllib.parse.urlparse(url).path).lstrip("/")


def join_url(base, rel):
    """Resolve a reference found inside a downloaded file against its url."""
    if rel.startswith(("http://", "https://")):
        return rel
    if "://" in rel or rel.startswith("/"):
        return None          # omniverse:// and absolute local paths are not ours
    return urllib.parse.urljoin(base, urllib.parse.quote(rel, safe="/:.@+~-"))


# ------------------------------------------------------------------
# what a downloaded file itself refers to

def live_items(listop):
    """Every composing item of a reference or payload list op.

    A "deleted" item removes an arc a weaker layer contributed; it never
    brings a file in, so it is not followed.
    """
    out = []
    for group in (listop.explicitItems, listop.addedItems, listop.prependedItems,
                  listop.appendedItems, listop.orderedItems):
        out.extend(group)
    return out


def layer_asset_paths(layer):
    """Sublayers, references, payloads and asset-valued attributes of a layer.

    Sublayers matter here: NVIDIA's carter_v2_4.usd brings the whole robot
    body in as one, and a crawl that only follows references and payloads
    loads the sensor mounts and no chassis.
    """
    out = list(layer.subLayerPaths)

    def visit(path):
        spec = layer.GetObjectAtPath(path)
        if isinstance(spec, Sdf.PrimSpec):
            for listop in (spec.referenceList, spec.payloadList):
                out.extend(i.assetPath for i in live_items(listop) if i.assetPath)
        elif isinstance(spec, Sdf.AttributeSpec):
            if spec.typeName in (Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray):
                value = spec.default
                if value is None:
                    return
                values = value if isinstance(value, Sdf.AssetPathArray) else [value]
                out.extend(v.path for v in values if v.path)

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return out


def refs_in_usd(blob, tmp):
    tmp.write_bytes(blob)
    layer = Sdf.Layer.OpenAsAnonymous(str(tmp))
    if layer is None:
        return []
    out = layer_asset_paths(layer)
    del layer
    tmp.unlink(missing_ok=True)
    return out


def refs_in_mdl(blob):
    """Textures, and the sibling modules an MDL file imports by relative path.

    An absolute module path like ::OmniPBR::OmniPBR is resolved out of the Kit
    installation's own MDL search path, so there is nothing to download for it.
    """
    out = [m.group(1).decode() for m in TEXTURE_IN_MDL.finditer(blob)]
    for m in MODULE_IN_MDL.finditer(blob):
        mod = m.group(1).decode()
        up = "../" if mod.startswith("..") else "./"
        out.append(up + "/".join(mod.lstrip(".").split("::")[1:]) + ".mdl")
    for m in SIBLING_IN_MDL.finditer(blob):
        out.append("./" + m.group(1).decode() + ".mdl")
    return out


def child_refs(url, blob, tmp):
    name = cdn_path(url).lower()
    if name.endswith(USD_SUFFIXES):
        return refs_in_usd(blob, tmp)
    if name.endswith(".mdl"):
        return refs_in_mdl(blob)
    return []


# ------------------------------------------------------------------
# building the manifest

def seed_urls(root):
    """Every http(s) asset path in the shipped layers, and where it is used."""
    seen = {}
    for rel in SEED_LAYERS:
        path = root / rel
        if not path.exists():
            continue
        layer = Sdf.Layer.FindOrOpen(str(path))

        for a in layer_asset_paths(layer):
            if a.startswith(("http://", "https://")):
                seen.setdefault(a, set()).add(rel)
    return seen


def build_manifest(root, out_path, scratch, refresh=False):
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / "_probe.usd"

    seeds = seed_urls(root)
    print("seed urls in the shipped layers:", len(seeds))

    entries = {}
    unresolved = []
    queue = [(u, sorted(seeds[u])) for u in sorted(seeds)]
    done = set()
    while queue:
        url, why = queue.pop(0)
        key = url.split("?")[0]
        if key in done:
            continue
        done.add(key)
        local = scratch / cdn_path(url)
        if refresh or not local.exists() or local.stat().st_size == 0:
            try:
                blob = get(url)
            except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
                unresolved.append({"url": url, "error": str(e), "referenced_by": why})
                print("  UNRESOLVED", url, e)
                continue
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(blob)
        else:
            blob = local.read_bytes()
        rel = "range/assets/" + cdn_path(url)
        entries[key] = {
            "path": rel, "url": url, "bytes": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "source": "omniverse-content-production",
            "group": "range",
            "referenced_by": why,
        }
        for child in child_refs(url, blob, tmp):
            child_url = join_url(url, child)
            if child_url:
                queue.append((child_url, [cdn_path(url)]))
            else:
                unresolved.append({"url": child, "error": "not an http reference",
                                   "referenced_by": [cdn_path(url)]})
        if len(entries) % 50 == 0:
            print("  ", len(entries), "files,", sum(e["bytes"] for e in entries.values()), "bytes")

    # the sky, from Poly Haven
    try:
        sky_local = scratch / "industrial_sunset_puresky_16k.hdr"
        blob = (sky_local.read_bytes() if not refresh and sky_local.exists()
                and sky_local.stat().st_size else get(POLYHAVEN_HDR["url"]))
        sky = dict(POLYHAVEN_HDR, bytes=len(blob),
                   sha256=hashlib.sha256(blob).hexdigest(),
                   referenced_by=["range/terrain1_world.usd"])
        sky_local.write_bytes(blob)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        unresolved.append({"url": POLYHAVEN_HDR["url"], "error": str(e),
                           "referenced_by": ["range/terrain1_world.usd"]})
        sky = None

    files = sorted(entries.values(), key=lambda e: e["path"])
    if sky:
        files.append(sky)
    label_groups(root, files, scratch)
    total = sum(e["bytes"] for e in files)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"files": files, "unresolved": unresolved}, indent=2) + "\n")
    print("manifest:", len(files), "files", total, "bytes,",
          len(unresolved), "unresolved ->", out_path)
    return files, unresolved


# ------------------------------------------------------------------
# which seed layer needs which file

def label_groups(root, files, scratch):
    """Walk the reference graph again, from the local copies, one seed at a time.

    The crawl only records the first prim that asked for a file, so a file the
    range and a showcase both need would otherwise look like it belonged to
    whichever was reached first.
    """
    by_key = {e["url"].split("?")[0]: e for e in files
              if e.get("source") == "omniverse-content-production"}
    tmp = scratch / "_regroup.usd"

    children = {}
    for key, e in by_key.items():
        local = scratch / cdn_path(e["url"])
        name = local.name.lower()
        if not local.exists() or not name.endswith(USD_SUFFIXES + (".mdl",)):
            children[key] = []
            continue
        kids = []
        for c in child_refs(e["url"], local.read_bytes(), tmp):
            u = join_url(e["url"], c)
            if u and u.split("?")[0] in by_key:
                kids.append(u.split("?")[0])
        children[key] = kids

    seeds_by_url = seed_urls(root)
    reach = {}
    for rel in SEED_LAYERS:
        g = group_of(rel)
        seeds = [u.split("?")[0] for u, where in seeds_by_url.items()
                 if rel in where and u.split("?")[0] in by_key]
        stack = list(seeds)
        seen = set()
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            stack.extend(children.get(k, []))
        for k in seen:
            reach.setdefault(k, set()).add(g)

    for key, e in by_key.items():
        e["group"] = "+".join(sorted(reach.get(key, {"range"})))
    for e in files:
        e.setdefault("group", "range")
    return files


def regroup(root, manifest, scratch):
    data = json.loads(manifest.read_text())
    label_groups(root, data["files"], scratch)
    manifest.write_text(json.dumps(data, indent=2) + "\n")
    totals = {}
    for e in data["files"]:
        g = e.get("group", "range")
        n, b = totals.get(g, (0, 0))
        totals[g] = (n + 1, b + e["bytes"])
    for g in sorted(totals):
        print(g, totals[g][0], "files", totals[g][1], "bytes")
    return 0


# ------------------------------------------------------------------
# downloading and checking

def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def download(root, manifest, check_only, group=None):
    data = json.loads(manifest.read_text())
    ok = missing = bad = 0
    fetched = 0
    wanted = [e for e in data["files"]
              if group is None or group in e.get("group", "range").split("+")]
    print("files in this group:", len(wanted), "of", len(data["files"]),
          sum(e["bytes"] for e in wanted), "bytes")
    for e in wanted:
        dest = root / e["path"]
        if dest.exists() and dest.stat().st_size == e["bytes"]:
            if sha256_file(dest) == e["sha256"]:
                ok += 1
                continue
        if check_only:
            print("  MISSING or CHANGED", e["path"])
            missing += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            blob = get(e["url"])
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as err:
            print("  FAILED", e["url"], err)
            missing += 1
            continue
        got = hashlib.sha256(blob).hexdigest()
        if got != e["sha256"]:
            print("  HASH MISMATCH", e["path"], "expected", e["sha256"], "got", got)
            bad += 1
            continue
        dest.write_bytes(blob)
        fetched += 1
        if fetched % 50 == 0:
            print("  ", fetched, "downloaded")
    print("already present and verified:", ok, " downloaded:", fetched,
          " missing or failed:", missing, " hash mismatches:", bad)
    if data.get("unresolved"):
        print("unresolved urls in the manifest:", len(data["unresolved"]))
        for u in data["unresolved"]:
            print("   ", u["url"], u["error"])
    return missing + bad


# ------------------------------------------------------------------
# the two character scripting paths

def set_character_scripts(root, isaacsim_path):
    """Point the anim.people scripting attributes at the reader's own install."""
    matches = sorted(pathlib.Path(isaacsim_path).glob(
        "extscache/omni.anim.people-*/omni/anim/people/scripts/" + CHARACTER_SCRIPT))
    if not matches:
        matches = sorted(pathlib.Path(isaacsim_path).glob(
            "exts/omni.anim.people/omni/anim/people/scripts/" + CHARACTER_SCRIPT))
    if not matches:
        print("no", CHARACTER_SCRIPT, "under", isaacsim_path, "- nothing written")
        return 1
    target = str(matches[-1])
    n = 0
    for rel in SEED_LAYERS:
        path = root / rel
        if not path.exists():
            continue
        layer = Sdf.Layer.FindOrOpen(str(path))
        edits = []

        def visit(p, layer=layer):
            spec = layer.GetObjectAtPath(p)
            if not isinstance(spec, Sdf.AttributeSpec):
                return
            if spec.typeName not in (Sdf.ValueTypeNames.Asset,
                                     Sdf.ValueTypeNames.AssetArray):
                return
            v = spec.default
            if v is None:
                return
            vs = v if isinstance(v, Sdf.AssetPathArray) else [v]
            if any(x.path.endswith(CHARACTER_SCRIPT) for x in vs):
                edits.append((p, isinstance(v, Sdf.AssetPathArray)))

        layer.Traverse(Sdf.Path.absoluteRootPath, visit)
        for p, is_array in edits:
            spec = layer.GetObjectAtPath(p)
            spec.default = (Sdf.AssetPathArray([Sdf.AssetPath(target)])
                            if is_array else Sdf.AssetPath(target))
            n += 1
        if edits:
            layer.Save()
            print("  ", rel, len(edits), "scripting attributes ->", target)
    print("character scripting attributes rewritten:", n)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=pathlib.Path, default=ROOT)
    ap.add_argument("--manifest", type=pathlib.Path, default=MANIFEST)
    ap.add_argument("--build-manifest", action="store_true")
    ap.add_argument("--scratch", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "iddmbse-assets")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--regroup", action="store_true")
    ap.add_argument("--refresh", action="store_true",
                    help="with --build-manifest, download again instead of reusing "
                         "what is in the scratch directory")
    ap.add_argument("--group", choices=("range", "showcases"))
    ap.add_argument("--isaacsim-path")
    args = ap.parse_args()

    rc = 0
    if args.build_manifest:
        build_manifest(args.root, args.manifest, args.scratch, args.refresh)
    elif args.regroup:
        rc = regroup(args.root, args.manifest, args.scratch)
    elif args.isaacsim_path and not args.check:
        rc = set_character_scripts(args.root, args.isaacsim_path)
    else:
        rc = download(args.root, args.manifest, args.check, args.group)
        if args.isaacsim_path:
            rc += set_character_scripts(args.root, args.isaacsim_path)
    return rc


sys.exit(main())
