"""Write the VERITAS verdict back into the AGR fleet model.

The last step of the chain: each executed trajectory's robustness becomes the
goal-satisfaction value of the AGR block the mission was allocated to. The model
file is rewritten in place, which is what a SysML tool would do to the block's
value property; the leading comment block is kept so the file stays self-describing.
"""

import json
from pathlib import Path

import yaml


def _header(text):
    lines = text.splitlines(keepends=True)
    n = 0
    while n < len(lines) and (lines[n].startswith("#") or not lines[n].strip()):
        n += 1
    return "".join(lines[:n])


def write_model(model_path, verdicts, scored_by="VERITAS quantitative STL robustness"):
    """Set goal_satisfaction, verdict and binding_conjunct on each scored AGR block.

    `verdicts` maps a block id to {"rho": float, "verdict": str, "binding": str}.
    """
    path = Path(model_path)
    text = path.read_text()
    doc = yaml.safe_load(text)
    for blk in doc["blocks"]:
        v = verdicts.get(blk["id"])
        if v is None:
            continue
        blk["goal_satisfaction"] = round(float(v["rho"]), 6)
        blk["verdict"] = v["verdict"]
        blk["binding_conjunct"] = v["binding"]
        blk["scored_by"] = scored_by
    body = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False, width=100)
    path.write_text(_header(text) + body)
    return doc


def read_goal_satisfaction(model_path):
    doc = yaml.safe_load(Path(model_path).read_text())
    return {b["id"]: b.get("goal_satisfaction") for b in doc["blocks"] if b.get("kind") == "part"}


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
