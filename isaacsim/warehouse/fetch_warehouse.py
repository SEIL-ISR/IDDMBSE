"""Build the cluttered warehouse scene in generated/.

Two files of the scene are NVIDIA's Isaac Sim 6.0 ROS 2 navigation sample -- the
warehouse stage and the Nova Carter with its ROS 2 graphs -- and are not kept in
this repository. This script reads them from an Isaac Sim 6.0 asset root, rewrites
their four relative asset paths so that they resolve from generated/, and writes
the authored layers from layers/ next to them with ${ISAACSIM_ASSET_ROOT} filled
in. Open generated/carter_warehouse_clutter_v2.usda afterwards.

The asset root is --asset-root, else $ISAACSIM_ASSET_ROOT, else NVIDIA's cloud
copy of the Isaac Sim 6.0 assets.

    uv run --project ../tools python fetch_warehouse.py
"""

import argparse
import hashlib
import json
import os
import posixpath
import sys
import urllib.request
from pathlib import Path

from pxr import Sdf, UsdUtils

HERE = Path(__file__).resolve().parent
CLOUD_ROOT = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0"
TOKEN = "${ISAACSIM_ASSET_ROOT}"
ROOT_LAYER = "carter_warehouse_clutter_v2.usda"
LAYERS = [
    "carter_warehouse_maze.usda",
    "carter_warehouse_people.usda",
    "carter_warehouse_animated.usda",
    ROOT_LAYER,
]
# the two NVIDIA sample files: where they sit under the asset root, and the SHA-256 of the 6.0 copies
SAMPLES = {
    "carter_warehouse_navigation.usd": (
        "Isaac/Samples/ROS2/Scenario/carter_warehouse_navigation.usd",
        "2a699e593474b6967c39f31df0b74bcec4190a8b28a0e3e47b380beb0026eaa2",
    ),
    "Nova_Carter_ROS.usd": (
        "Isaac/Samples/ROS2/Robots/Nova_Carter_ROS.usd",
        "00585ed68ddb9f9cb8b42b45cf23488c1215fcbaf193529e5a9313a4dcdfa8d7",
    ),
}


def is_url(path):
    return "://" in path


def rebase(asset_path, sample_dir, root):
    """Where one asset path points once its layer sits in generated/.

    sample_dir is the directory, relative to the asset root, of the NVIDIA sample
    the path was read from, or None for an authored layer. A path into the other
    sample file points at its copy in generated/; any other relative path inside a
    sample goes under root; ${ISAACSIM_ASSET_ROOT} becomes root; URLs, absolute
    paths and the authored layers' own file names stay as they are.
    """
    if asset_path.startswith(TOKEN):
        return root + asset_path[len(TOKEN):]
    if not asset_path or is_url(asset_path) or asset_path.startswith("/") or sample_dir is None:
        return asset_path
    target = posixpath.normpath(posixpath.join(sample_dir, asset_path))
    for name, (rel, _) in SAMPLES.items():
        if target == rel:
            return "./" + name
    return root + "/" + target


def asset_paths(layer):
    seen = []

    def record(path):
        seen.append(path)
        return path

    UsdUtils.ModifyAssetPaths(layer, record)
    return seen


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_sample(root, rel, download_dir):
    if not is_url(root):
        return Path(root) / rel
    download_dir.mkdir(parents=True, exist_ok=True)
    local = download_dir / Path(rel).name
    urllib.request.urlretrieve(root + "/" + rel, local)
    return local


def build(root, out):
    out.mkdir(parents=True, exist_ok=True)
    for name, (rel, digest) in SAMPLES.items():
        src = read_sample(root, rel, out / "download")
        got = sha256(src)
        note = "the Isaac Sim 6.0 sample" if got == digest else "differs from the Isaac Sim 6.0 sample"
        print(f"{name}: {root}/{rel} sha256 {got} ({note})")
        layer = Sdf.Layer.OpenAsAnonymous(str(src))
        sample_dir = posixpath.dirname(rel)
        UsdUtils.ModifyAssetPaths(layer, lambda path: rebase(path, sample_dir, root))
        layer.Export(str(out / name))
    for name in LAYERS:
        layer = Sdf.Layer.OpenAsAnonymous(str(HERE / "layers" / name))
        UsdUtils.ModifyAssetPaths(layer, lambda path: rebase(path, None, root))
        layer.Export(str(out / name))
    layout = json.loads((HERE / "layers" / "clutter_layout.json").read_text())
    (out / "clutter_layout.json").write_text(json.dumps(layout, indent=2) + "\n")


def check(out):
    """Count, per generated layer, the asset paths that are URLs, local and present, local and missing."""
    missing = []
    for name in list(SAMPLES) + LAYERS:
        paths = asset_paths(Sdf.Layer.FindOrOpen(str(out / name)))
        urls = [p for p in paths if is_url(p)]
        local = [p for p in paths if not is_url(p)]
        absent = [p for p in local if not (out / p).exists()]
        missing += [(name, p) for p in absent]
        print(f"{name}: {len(paths)} asset paths, {len(urls)} URLs, {len(local) - len(absent)} local found, {len(absent)} local missing")
    for name, path in missing:
        print("missing", name, path)
    return len(missing)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--asset-root", default=os.environ.get("ISAACSIM_ASSET_ROOT", CLOUD_ROOT))
    parser.add_argument("--out", type=Path, default=HERE / "generated")
    args = parser.parse_args()
    root = args.asset_root.rstrip("/")
    if not is_url(root):
        root = os.path.abspath(os.path.expanduser(root))
    build(root, args.out)
    missing = check(args.out)
    print(f"open {args.out / ROOT_LAYER}")
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
