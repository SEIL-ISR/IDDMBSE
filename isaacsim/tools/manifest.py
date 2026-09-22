"""Write MANIFEST.json for a directory: relative path, size in bytes, sha256.

    python manifest.py <directory> [-o MANIFEST.json] [--skip-dir range/assets]

MANIFEST.json itself and README.md are skipped so the manifest does not try to
describe itself; --skip-dir leaves out a whole subtree, which is how the
downloaded content and the built terrain stay out of it.
"""

import argparse
import hashlib
import json
import pathlib

SKIP = {"MANIFEST.json", "README.md"}
SKIP_DIRS = ("__pycache__", ".pytest_cache", ".venv")


def entries(root, skip_dirs=()):
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel in SKIP or any(rel.startswith(d.rstrip("/") + "/") for d in skip_dirs):
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        with open(p, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        out.append({"path": rel, "bytes": p.stat().st_size, "sha256": digest})
    return out


ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("directory")
ap.add_argument("-o", "--out")
ap.add_argument("--skip-dir", action="append", default=[])
args = ap.parse_args()

root = pathlib.Path(args.directory)
items = entries(root, args.skip_dir)
out = pathlib.Path(args.out) if args.out else root / "MANIFEST.json"
out.write_text(json.dumps({"files": items}, indent=2) + "\n")

total = sum(e["bytes"] for e in items)
print(len(items), "files", total, "bytes ->", out)
