"""Read an UPPAAL NTA file and lay its templates out for drawing.

`read_nta` returns the templates (locations, initial location, edges with their
guard, synchronisation and assignment labels) and the queries.  `dot_layout`
hands one template to Graphviz `dot` and reads back, from its JSON output,
where every location and its name sit and the spline and label position of
every edge, in inches with y pointing up.
"""

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

import numpy as np


def read_nta(path):
    nta = ET.parse(path).getroot()
    templates = []
    for t in nta.findall("template"):
        locations = []
        for loc in t.findall("location"):
            inv = [lab.text for lab in loc.findall("label") if lab.get("kind") == "invariant"]
            locations.append({
                "id": loc.get("id"),
                "name": (loc.findtext("name") or "").strip(),
                "x": float(loc.get("x") or 0.0),
                "y": float(loc.get("y") or 0.0),
                "urgent": loc.find("urgent") is not None,
                "committed": loc.find("committed") is not None,
                "invariant": inv[0] if inv else "",
            })
        edges = []
        for tr in t.findall("transition"):
            labels = {lab.get("kind"): (lab.text or "").strip() for lab in tr.findall("label")}
            edges.append({
                "source": tr.find("source").get("ref"),
                "target": tr.find("target").get("ref"),
                "guard": labels.get("guard", ""),
                "sync": labels.get("synchronisation", ""),
                "assignment": labels.get("assignment", ""),
            })
        init = t.find("init")
        templates.append({"name": t.findtext("name"), "locations": locations, "edges": edges,
                          "init": init.get("ref") if init is not None else None})
    block = nta.find("queries")
    queries = [(q.findtext("formula") or "").strip()
               for q in (block.findall("query") if block is not None else [])]
    return {"templates": templates, "queries": queries, "system": nta.findtext("system") or ""}


def edge_label(edge):
    """guard, sync and assignment joined on one line, the way the UPPAAL editor lists them."""
    parts = [edge["guard"], edge["sync"], edge["assignment"]]
    return "  ".join(p for p in parts if p)


def quote(text):
    """A DOT string; a backslash is left alone, so "\\n" stays dot's line break."""
    return '"' + text.replace('"', '\\"') + '"'


def dot_layout(template, rankdir="LR", names=True, dot=None):
    """Positions of the locations, their name labels and the edge splines of one template.

    Returns {"nodes": {id: (x, y)}, "names": {id: (x, y)}, "edges": [(source,
    target, spline (n, 2), arrow tip (2,) or None, label, label_xy or None)],
    "size": (width, height)}, in inches.  The names are placed by dot as external
    labels, so the layout leaves room for them.
    """
    dot = dot or shutil.which("dot")
    lines = ["digraph T {", "rankdir=" + rankdir + ";", "nodesep=0.35; ranksep=0.6;",
             'node [shape=circle, width=0.32, fixedsize=true, label=""];',
             "edge [fontsize=9];"]
    for loc in template["locations"]:
        tag = loc["name"] + ("\\n" + loc["invariant"] if loc["invariant"] else "")
        xlabel = (" xlabel=" + quote(tag)) if names and tag else ""
        lines.append(loc["id"] + " [fontsize=10" + xlabel + "];")
    for e in template["edges"]:
        lines.append(e["source"] + " -> " + e["target"] + " [label=" + quote(edge_label(e)) + "];")
    lines.append("}")
    graph = json.loads(subprocess.run([dot, "-Tjson"], input="\n".join(lines),
                                      capture_output=True, text=True, check=True).stdout)

    def point(text):
        x, y = text.split(",")[-2:]
        return float(x) / 72.0, float(y) / 72.0

    objects = graph.get("objects", [])
    nodes = {o["name"]: point(o["pos"]) for o in objects}
    names = {o["name"]: point(o["xlp"]) for o in objects if "xlp" in o}
    edges = []
    for e in graph.get("edges", []):
        tip, spline = None, []
        for tok in e["pos"].split():
            if tok.startswith("e,"):
                tip = np.array(point(tok[2:]))
            elif not tok.startswith("s,"):
                spline.append(point(tok))
        edges.append((objects[e["tail"]]["name"], objects[e["head"]]["name"], np.array(spline),
                      tip, e.get("label", ""), point(e["lp"]) if "lp" in e else None))
    x0, y0, x1, y1 = (float(v) / 72.0 for v in graph["bb"].split(","))
    return {"nodes": nodes, "names": names, "edges": edges, "size": (x1 - x0, y1 - y0)}
