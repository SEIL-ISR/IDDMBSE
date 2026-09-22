"""A behavior tree becoming an UPPAAL network, then the verdicts.

Scene one: the demo tree of formal/bt2automata/demo.py, Sequence(FA,
Sequence(Selector(CBatt, FCharger), FB)), drawn node by node; the network the
demo composes from it (templates BT, Battery and Grid) appearing template by
template, location by location and edge by edge; the model's two queries with
UPPAAL's verdicts.  Scene two: the SysML battery state machine and activity
that formal/sysml2uppaal translates, and its twelve queries with their verdicts.

Both models are regenerated into a temporary directory by the tools themselves
(demo.py, and sysml2uppaal.translate with demo_battery.py's arguments).  BT,
Battery and the two SysML templates are laid out by Graphviz dot; Grid is drawn
at the coordinates its XML carries.  The verdicts come from verifyta when
formal/verify.py finds it (UPPAAL_HOME, PATH), else from uppaal_verdicts.json
beside this script, which --record-verdicts writes from a live run.

    uv run python formal/animations/make_bt_to_automaton.py --out formal/animations

writes bt_to_automaton.mp4, .gif and bt_to_automaton_poster.svg/.pdf.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch
from matplotlib.path import Path

here = pathlib.Path(__file__).resolve().parent
formal = here.parent
sys.path.insert(0, str(here))
sys.path.insert(0, str(formal))
sys.path.insert(0, str(formal / "sysml2uppaal"))
import verify  # noqa: E402
from nta_layout import dot_layout, read_nta  # noqa: E402
from sysml2uppaal import translate  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--out", default=str(here))
p.add_argument("--frames", type=int, default=600)
p.add_argument("--fps", type=int, default=24)
p.add_argument("--height", type=int, default=1080, choices=[720, 1080],
               help="MP4 height; the width follows at 16:9")
p.add_argument("--gif-width", type=int, default=640, help="GIF width in pixels")
p.add_argument("--gif-fps", type=int, default=None,
               help="GIF frame rate (default: 12, or 8 when the GIF is over 3 MB at 12)")
p.add_argument("--seed", type=int, default=0, help="unused: nothing here is random")
p.add_argument("--record-verdicts", action="store_true",
               help="write uppaal_verdicts.json beside this script from a live verifyta run")
a = p.parse_args()

started = time.time()
out = pathlib.Path(a.out)
out.mkdir(parents=True, exist_ok=True)
plt.rcParams["svg.hashsalt"] = "bt_to_automaton"

# ------------------------------------------------------------------
# the two models, regenerated, and their verdicts

work = pathlib.Path(tempfile.mkdtemp())
bt_xml = work / "BT_converted.xml"
sm_xml = work / "battery_sm.xml"
subprocess.run([sys.executable, str(formal / "bt2automata" / "demo.py"), str(bt_xml)],
               check=True, capture_output=True)
# the arguments of formal/sysml2uppaal/demo_battery.py
translate(str(formal.parent.parent / "sysml" / "models" / "AGR_stack-MB-SensorTrade-mk6.mdzip"),
          str(sm_xml), scale=100,
          aliases={"current_soc": ["state of charge"], "gt": ["complete the entire path"]},
          state_machines=["ee_hv_battery_charge_discharge"], activities=["Demo AD"])
bt = read_nta(bt_xml)
sm = read_nta(sm_xml)

recorded = here / "uppaal_verdicts.json"
verifyta = verify.find_verifyta()
if verifyta is not None:
    version = verify.verifyta_version(verifyta)
    checked = {}
    for key, path in [("bt", bt_xml), ("sm", sm_xml)]:
        res = verify.check_model(verifyta, str(path))
        checked[key] = [[q["formula"], q["verdict"]] for q in res["queries"]]
    verdicts = {"version": version, "bt": checked["bt"], "sm": checked["sm"]}
    source = "live verifyta run"
    if a.record_verdicts:
        recorded.write_text(json.dumps(verdicts, indent=2) + "\n")
else:
    verdicts = json.loads(recorded.read_text())
    source = recorded.name
shutil.rmtree(work)
assert [f for f, _ in verdicts["bt"]] == bt["queries"]
assert [f for f, _ in verdicts["sm"]] == sm["queries"]
print("verdicts from", source + ":", verdicts["version"])
for f, v in verdicts["bt"] + verdicts["sm"]:
    print("  " + f + "  ->  " + v)


def instances(system):
    """instance name -> (template name, argument text), from the system declaration."""
    return {m.group(1): (m.group(2), m.group(3))
            for m in re.finditer(r"(\w+)\s*=\s*(\w+)\s*\(([^)]*)\)", system)}


# ------------------------------------------------------------------
# timeline, in fractions of the whole

n = a.frames
u = np.arange(n) / max(n - 1, 1)
T_TREE = (0.0, 0.13)
T_BT = (0.14, 0.25)
T_BATT = (0.25, 0.30)
T_GRID = (0.30, 0.41)
T_QBT = (0.42, 0.49)
T_SWITCH = 0.54
T_SM = (0.55, 0.66)
T_QSM = (0.67, 0.92)


def spread(count, span):
    """Reveal times of `count` items spread evenly over `span`."""
    return span[0] + (span[1] - span[0]) * np.arange(count) / max(count, 1)


# ------------------------------------------------------------------
# the figure and every artist, each with the time it appears

fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
title = fig.text(0.5, 0.955, "", ha="center", fontsize=15)
stage = fig.text(0.5, 0.915, "", ha="center", fontsize=11, color="0.3")
timed = []      # (artist, reveal time, scene)


def show(artist, t0, scene):
    artist.set_visible(False)
    timed.append((artist, t0, scene))
    return artist


def blank(rect):
    ax = fig.add_axes(rect)
    ax.set_axis_off()
    return ax


# the behavior tree, as demo.py composes it
tree = [("seq", "Sequence", None, 1.2, 3.0), ("FA", "FA\ngo to A", "seq", 0.0, 2.0),
        ("seq2", "Sequence", "seq", 2.4, 2.0), ("sel", "Selector", "seq2", 1.5, 1.0),
        ("CBatt", "CBatt\nBatt > 80", "sel", 0.95, 0.0),
        ("FCharger", "FCharger\nto charger", "sel", 2.05, 0.0),
        ("FB", "FB\ngo to B", "seq2", 3.3, 1.0)]
ax_tree = blank([0.01, 0.40, 0.28, 0.47])
ax_tree.set_xlim(-0.55, 3.85)
ax_tree.set_ylim(-0.6, 3.5)
where = {k: (x, y) for k, _, _, x, y in tree}
for t0, (key, label, parent, x, y) in zip(spread(len(tree), T_TREE), tree):
    control = key.startswith("se")
    show(ax_tree.add_patch(FancyBboxPatch(
        (x - 0.42, y - 0.28), 0.84, 0.56, boxstyle="round,pad=0.02",
        facecolor="#dbe8f5" if control else "#fdf1d8", edgecolor="0.3")), t0, 0)
    text = {"Sequence": "Sequence  →", "Selector": "Selector  ?"}.get(label, label)
    show(ax_tree.text(x, y, text, ha="center", va="center", fontsize=9), t0, 0)
    if parent is not None:
        px, py = where[parent]
        show(ax_tree.plot([px, x], [py - 0.28, y + 0.28], color="0.4", lw=1.2)[0], t0, 0)
show(ax_tree.text(1.65, 3.45, "behavior tree (bt2automata/demo.py)", ha="center",
                  fontsize=11, weight="bold"), T_TREE[0], 0)


def draw_template(ax, template, layout, span, scene, instance=""):
    """Locations, then edges, of one template laid out by dot; returns the location circles."""
    w, h = layout["size"]
    ax.set_xlim(-0.3, w + 0.3)
    ax.set_ylim(-0.3, h + 0.3)
    ax.set_aspect("equal")
    locs = template["locations"]
    edges = layout["edges"]
    times = spread(len(locs) + len(edges), span)
    circles = {}
    for t0, loc in zip(times, locs):
        x, y = layout["nodes"][loc["id"]]
        c = show(ax.add_patch(Circle((x, y), 0.16, facecolor="white", edgecolor="0.15",
                                     lw=1.3, zorder=3)), t0, scene)
        circles[loc["id"]] = c
        if loc["id"] == template["init"]:
            show(ax.add_patch(Circle((x, y), 0.11, facecolor="none", edgecolor="0.15",
                                     lw=1.0, zorder=4)), t0, scene)
        mark = "U" if loc["urgent"] else "C" if loc["committed"] else ""
        if mark:
            show(ax.text(x, y, mark, ha="center", va="center", fontsize=8, zorder=5), t0, scene)
        tag = loc["name"] + ("\n" + loc["invariant"] if loc["invariant"] else "")
        if tag and loc["id"] in layout["names"]:
            nx, ny = layout["names"][loc["id"]]
            show(ax.text(nx, ny, tag, ha="center", va="center", fontsize=8,
                         color="#1f4e79", zorder=5), t0, scene)
    for t0, (src, dst, pts, tip, label, lxy) in zip(times[len(locs):], edges):
        verts = np.vstack([pts, tip[None, :]]) if tip is not None else pts
        codes = [Path.MOVETO] + [Path.CURVE4] * (len(pts) - 1) + [Path.LINETO] * (len(verts) - len(pts))
        show(ax.add_patch(FancyArrowPatch(path=Path(verts, codes), arrowstyle="-|>",
                                          mutation_scale=9, color="0.35", lw=0.9,
                                          zorder=2)), t0, scene)
        if lxy is not None and label:
            show(ax.text(lxy[0], lxy[1], label, ha="center", va="center", fontsize=6.5,
                         color="0.2", zorder=4), t0, scene)
    head = "template " + template["name"] + (", instance " + instance if instance else "") \
        + ": " + str(len(locs)) + " locations, " + str(len(template["edges"])) + " edges"
    show(ax.set_title(head, fontsize=10), span[0], scene)
    return circles


bt_inst = instances(bt["system"])
by_template = {tpl: (name, args) for name, (tpl, args) in bt_inst.items()}


def inst_text(tpl):
    name, args = by_template.get(tpl, ("", ""))
    return name + " = " + tpl + "(" + args + ")" if name else ""


tpl = {t["name"]: t for t in bt["templates"]}
ax_bt = blank([0.31, 0.49, 0.68, 0.38])
draw_template(ax_bt, tpl["BT"], dot_layout(tpl["BT"]), T_BT, 0, inst_text("BT"))
ax_batt = blank([0.31, 0.05, 0.25, 0.36])
draw_template(ax_batt, tpl["Battery"], dot_layout(tpl["Battery"]), T_BATT, 0,
              inst_text("Battery"))

# Grid: at its own XML coordinates (UPPAAL's y points down)
grid = tpl["Grid"]
ax_grid = blank([0.60, 0.04, 0.38, 0.40])
gxy = {loc["id"]: (loc["x"] / 100.0, -loc["y"] / 100.0) for loc in grid["locations"]}
ids = [loc["id"] for loc in grid["locations"]]
pts = np.array([gxy[i] for i in ids])
moves = [e for e in grid["edges"] if e["source"] != e["target"]]
segs = np.array([[gxy[e["source"]], gxy[e["target"]]] for e in moves])
loc_t = spread(len(ids), (T_GRID[0], 0.5 * (T_GRID[0] + T_GRID[1])))
seg_t = spread(len(segs), (0.5 * (T_GRID[0] + T_GRID[1]), T_GRID[1]))
grid_lines = LineCollection([], colors="0.55", lw=0.8, zorder=1)
ax_grid.add_collection(grid_lines)
grid_dots = ax_grid.scatter([], [], s=22, facecolor="white", edgecolor="0.15", zorder=2)
ax_grid.set_xlim(-0.6, 9.6)
ax_grid.set_ylim(-9.6, 0.6)
ax_grid.set_aspect("equal")
for flag in ["A", "B", "Charger"]:
    cell = [gxy[e["target"]] for e in grid["edges"] if flag + "=true" in e["assignment"]]
    x, y = cell[0]
    show(ax_grid.text(x + 0.25, y + 0.25, flag, fontsize=9, color="#b03a2e", weight="bold",
                      zorder=4), T_GRID[1], 0)
x, y = gxy[grid["init"]]
show(ax_grid.add_patch(Circle((x, y), 0.3, facecolor="none", edgecolor="#00a000", lw=1.5,
                              zorder=3)), T_GRID[1], 0)
show(ax_grid.set_title("template Grid, instance " + inst_text("Grid") + ": " + str(len(ids))
                       + " locations,\n" + str(len(grid["edges"])) + " edges, of which "
                       + str(len(grid["edges"]) - len(moves)) + " self-loops (not drawn)",
                       fontsize=10), T_GRID[0], 0)


def verdict_colour(v):
    return "#1e8449" if v == "satisfied" else "#b03a2e"


# the BT queries
ax_qbt = blank([0.01, 0.04, 0.28, 0.32])
ax_qbt.set_xlim(0, 1)
ax_qbt.set_ylim(0, 1)
show(ax_qbt.text(0.0, 0.95, "queries, " + verdicts["version"].split(" (")[0], fontsize=11,
                 weight="bold", va="top"), T_QBT[0], 0)
for k, (t0, (f, v)) in enumerate(zip(spread(len(verdicts["bt"]), T_QBT), verdicts["bt"])):
    y = 0.72 - 0.2 * k
    show(ax_qbt.text(0.0, y, f, fontsize=11, family="monospace", va="center"), t0, 0)
    show(ax_qbt.text(0.0, y - 0.09, v, fontsize=11, color=verdict_colour(v), weight="bold",
                     va="center"), t0 + 0.4 * (T_QBT[1] - T_QBT[0]) / len(verdicts["bt"]), 0)

# scene two: the SysML translation and its twelve verdicts
sm_tpl = {t["name"]: t for t in sm["templates"]}
sm_names = list(sm_tpl)
ax_sm = [blank([0.02, 0.62, 0.96, 0.24]), blank([0.02, 0.39, 0.96, 0.21])]
spans = [(T_SM[0], 0.5 * (T_SM[0] + T_SM[1])), (0.5 * (T_SM[0] + T_SM[1]), T_SM[1])]
sm_inst = instances(sm["system"])
circles = {}
for ax, name, span in zip(ax_sm, sm_names, spans):
    inst = [k for k, (t, _) in sm_inst.items() if t == name]
    c = draw_template(ax, sm_tpl[name], dot_layout(sm_tpl[name]), span, 1,
                      inst[0] if inst else "")
    circles.update({(inst[0] if inst else name, loc["name"]): c[loc["id"]]
                    for loc in sm_tpl[name]["locations"]})
ax_q = blank([0.02, 0.01, 0.96, 0.36])
ax_q.set_xlim(0, 1)
ax_q.set_ylim(0, 1)
q_t = spread(len(verdicts["sm"]), T_QSM)
paint = []      # (circle, reveal time, verdict)
for k, (t0, (f, v)) in enumerate(zip(q_t, verdicts["sm"])):
    y = 0.96 - 0.083 * k
    show(ax_q.text(0.02, y, str(k + 1), fontsize=9, ha="right", va="center"), t0, 1)
    show(ax_q.text(0.04, y, f, fontsize=9, family="monospace", va="center"), t0, 1)
    show(ax_q.text(0.62, y, v, fontsize=9, color=verdict_colour(v), weight="bold",
                   va="center"), t0, 1)
    m = re.match(r"E<>\s*(\w+)\.(\w+)$", f)
    if m and (m.group(1), m.group(2)) in circles:
        paint.append((circles[(m.group(1), m.group(2))], t0, v))

titles = ["Behavior tree to timed automata: formal/bt2automata",
          "SysML state machine and activity to timed automata: formal/sysml2uppaal"]


def draw(i):
    scene = 0 if u[i] < T_SWITCH else 1
    for artist, t0, s in timed:
        artist.set_visible(s == scene and u[i] >= t0)
    grid_dots.set_offsets(pts[loc_t <= u[i]] if scene == 0 else np.empty((0, 2)))
    grid_lines.set_segments(segs[seg_t <= u[i]] if scene == 0 else [])
    for c, t0, v in paint:
        lit = u[i] >= t0
        c.set_facecolor(("#d5f5e3" if v == "satisfied" else "#f5b7b1") if lit else "white")
        c.set_edgecolor(verdict_colour(v) if lit else "0.15")
    title.set_text(titles[scene])
    if scene == 0:
        steps = ["the tree", "the composed network: " + ", ".join(
                     k + " = " + t + "(" + x + ")" for k, (t, x) in bt_inst.items()),
                 "UPPAAL's verdicts on the model's own queries"]
        stage.set_text(steps[0 if u[i] < T_BT[0] else 1 if u[i] < T_QBT[0] else 2])
    else:
        stage.set_text("the battery state machine of the AGR SysML model, 2 templates, "
                       + str(len(verdicts["sm"])) + " queries; a reachability verdict "
                       "colours its location")


ffmpeg = shutil.which("ffmpeg")
mp4 = out / "bt_to_automaton.mp4"
gif = out / "bt_to_automaton.gif"
# The figure is laid out at 1280 x 720 (100 dpi); 1080p is the same figure at 150 dpi. A GIF
# up to 1280 px wide is scaled from 720p frames, encoded beside the MP4 and deleted after.
streams = [(mp4, 100 * a.height / 720)]
if a.height != 720 and a.gif_width <= 1280:
    streams.append((out / "bt_to_automaton_720p.mp4", 100))


def encoder(path, dpi):
    fig.set_dpi(dpi)
    width, height = fig.canvas.get_width_height()
    return subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                             "-s", str(width) + "x" + str(height), "-r", str(a.fps), "-i", "-",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
                             "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)


encs = [encoder(path, dpi) for path, dpi in streams]
for i in range(n):
    draw(i)
    for enc, (path, dpi) in zip(encs, streams):
        fig.set_dpi(dpi)
        fig.canvas.draw()
        enc.stdin.write(bytes(fig.canvas.buffer_rgba()))
fig.set_dpi(100)
for enc in encs:
    enc.stdin.close()
    enc.wait()

# the poster: the end of scene one, the tree and its network with both verdicts
draw(int(np.searchsorted(u, T_SWITCH)) - 1)
fig.savefig(out / "bt_to_automaton_poster.svg", metadata={"Date": None})
fig.savefig(out / "bt_to_automaton_poster.pdf", metadata={"CreationDate": None})
plt.close(fig)

for gif_fps in ([a.gif_fps] if a.gif_fps else [12, 8]):
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(streams[-1][0]), "-vf",
                    "fps=" + str(gif_fps) + ",scale=" + str(a.gif_width) + ":-1:flags=lanczos,split[a][b];"
                    "[a]palettegen=max_colors=64:stats_mode=diff[p];"
                    "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                    str(gif)], check=True)
    if gif.stat().st_size <= 3 * 1024 * 1024:
        break
if streams[-1][0] != mp4:
    streams[-1][0].unlink()

print("frames", n, "fps", a.fps, "duration", round(n / a.fps, 2), "s")
print("mp4", mp4.stat().st_size, "bytes; gif", gif.stat().st_size, "bytes at", gif_fps, "fps")
print("wall time", round(time.time() - started, 1), "s")
