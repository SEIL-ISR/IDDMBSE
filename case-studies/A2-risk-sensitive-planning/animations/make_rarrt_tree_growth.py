"""RRT* and risk-averse RA-RRT* growing their trees on the same rock field.

Replays campaign run `--seed` (default 0) of the hard environment at noise level
0.5 through `rarrt`: the same world, common random numbers and sampling seed as
that row of results/campaign.csv, once with the plain RRT* edge cost and once
with CVaR 0.9.  The planner's `on_iteration` hook keeps the tree at every
iteration a frame shows; the best path at each frame is the one `plan` would
return if it stopped there.  The final numbers (nominal length, smallest
clearance, share of 400 executions over the traversal budget) come from the
same run and are checked against the campaign table when the row exists.

    uv run python animations/make_rarrt_tree_growth.py --out animations

writes rarrt_tree_growth.mp4, .gif and rarrt_tree_growth_poster.svg/.pdf.
"""

import argparse
import csv
import os
import pathlib
import shutil
import subprocess
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.collections import LineCollection, PatchCollection

from rarrt.growth import best_path, record_growth
from rarrt.rrtstar import CostModel, execute, path_geometry
from rarrt.world import make_world

here = pathlib.Path(__file__).resolve().parent
root = here.parent

p = argparse.ArgumentParser()
p.add_argument("--out", default=str(here))
p.add_argument("--frames", type=int, default=480)
p.add_argument("--fps", type=int, default=24)
p.add_argument("--seed", type=int, default=0, help="campaign run index")
a = p.parse_args()

started = time.time()
out = pathlib.Path(a.out)
out.mkdir(parents=True, exist_ok=True)
plt.rcParams["svg.hashsalt"] = "rarrt_tree_growth"

cfg = yaml.safe_load((root / "campaign.yaml").read_text())
env, coverage = "hard", 0.26
sigma = cfg["noise_levels"][-1]
policies = [("rrtstar", None, "RRT* (path length)", "#444444"),
            ("cvar0.9", 0.9, "RA-RRT* risk-averse (CVaR 0.9)", "#d62728")]
world = make_world(coverage, seed=a.seed, half_width=cfg["half_width"])
budget = cfg["budget_factor"] * float(np.linalg.norm(world.goal - world.start))

# ------------------------------------------------------------------
# timeline: field alone, growth, final paths, hold

n = a.frames
n_intro = int(round(0.05 * n))
n_grow = max(int(round(0.70 * n)), 1)
n_reveal = int(round(0.10 * n))
grow_iter = np.round(cfg["iterations"] * np.arange(1, n_grow + 1) / n_grow).astype(int)
frame_iter = np.concatenate([np.zeros(n_intro, int), grow_iter,
                             np.full(n - n_intro - n_grow, cfg["iterations"])])
phase = np.concatenate([np.zeros(n_intro), np.ones(n_grow), np.full(n_reveal, 2.0),
                        np.full(max(n - n_intro - n_grow - n_reveal, 0), 3.0)])[:n]

# ------------------------------------------------------------------
# the two planner runs, recorded

reference = {}
with open(root / "results" / "campaign.csv") as f:
    for r in csv.DictReader(f):
        if r["env"] == env and float(r["sigma"]) == sigma and int(r["run"]) == a.seed:
            reference[r["policy"]] = r

runs = []
for name, alpha, label, colour in policies:
    cost = CostModel(sigma=sigma, alpha=alpha, n_samples=cfg["n_samples"], kappa=cfg["kappa"],
                     d_hazard=cfg["d_hazard"], p_max=cfg["p_max"], seed=cfg["crn_seed"] + a.seed)
    result, snaps = record_growth(world, cost, np.unique(frame_iter), iterations=cfg["iterations"],
                                  step=cfg["step"], goal_bias=cfg["goal_bias"],
                                  seed=cfg["plan_seed"] + a.seed)
    by_iter = {s["iteration"]: s for s in snaps}
    lengths, clearances = path_geometry(world, result["path"])
    rng = np.random.default_rng(cfg["exec_seed"] + a.seed)
    realized, _ = execute(cost, lengths, clearances, cfg["n_exec"], rng)
    final = {"length": float(lengths.sum()), "clearance": float(clearances.min()),
             "over": float((realized > budget).mean())}
    row = reference.get(name)
    if row is not None:
        print(name, "run", a.seed, "length", round(final["length"], 3), "csv",
              round(float(row["nominal_length"]), 3), "| clearance", round(final["clearance"], 4),
              "csv", round(float(row["min_clearance"]), 4), "| over budget", final["over"],
              "csv", row["over_budget"])
        assert np.isclose(final["length"], float(row["nominal_length"]))
        assert np.isclose(final["clearance"], float(row["min_clearance"]))
        assert np.isclose(final["over"], float(row["over_budget"]))
    paths = {}
    for it, s in by_iter.items():
        path, _ = best_path(world, cost, s["points"], s["parent"], s["cost_to"], cfg["step"])
        paths[it] = path
    runs.append({"name": name, "label": label, "colour": colour, "cost": cost,
                 "snaps": by_iter, "paths": paths, "final": final, "result": result})

# ------------------------------------------------------------------
# the figure

fig, axes = plt.subplots(1, 2, figsize=(12.8, 7.2), dpi=100)
fig.subplots_adjust(left=0.04, right=0.98, top=0.86, bottom=0.05, wspace=0.08)
fig.suptitle("RRT* and RA-RRT* on the same rock field: hard environment, " + str(world.n_obstacles)
             + " discs, noise level " + str(sigma) + ", campaign run " + str(a.seed), fontsize=14)
hw = cfg["half_width"]
artists = []
for ax, run in zip(axes, runs):
    halo = [plt.Circle(c, r + cfg["d_hazard"]) for c, r in zip(world.centers, world.radii)]
    ax.add_collection(PatchCollection(halo, facecolor="#f6e3c8", edgecolor="none", zorder=0))
    discs = [plt.Circle(c, r) for c, r in zip(world.centers, world.radii)]
    ax.add_collection(PatchCollection(discs, facecolor="0.25", edgecolor="none", zorder=1))
    tree = LineCollection([], colors="0.55", linewidths=0.5, zorder=2)
    ax.add_collection(tree)
    best, = ax.plot([], [], color=run["colour"], lw=2.6, zorder=4)
    ax.plot(*world.start, "o", color="#00a000", ms=9, zorder=5)
    ax.plot(*world.goal, "*", color="#1f77b4", ms=16, zorder=5)
    ax.set_xlim(-hw, hw)
    ax.set_ylim(-hw, hw)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(run["label"], fontsize=13, color=run["colour"])
    status = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top", ha="left",
                     fontsize=10, zorder=6,
                     bbox=dict(facecolor="white", edgecolor="0.7", alpha=0.9))
    verdict = ax.text(0.98, 0.02, "", transform=ax.transAxes, va="bottom", ha="right",
                      fontsize=11, zorder=6,
                      bbox=dict(facecolor="white", edgecolor=run["colour"], alpha=0.95))
    verdict.set_visible(False)
    artists.append((tree, best, status, verdict))
fig.text(0.5, 0.905, "shaded: within " + str(cfg["d_hazard"]) + " m of a rock, where the hazard "
         "chance of a segment is highest   |   grey: the tree   |   line: the best path so far",
         ha="center", fontsize=10, color="0.3")


def draw(i):
    it = int(frame_iter[i])
    for run, (tree, best, status, verdict) in zip(runs, artists):
        s = run["snaps"][it]
        pts, parent = s["points"], s["parent"]
        child = np.nonzero(parent >= 0)[0]
        tree.set_segments(np.stack([pts[child], pts[parent[child]]], axis=1))
        tree.set_alpha(0.35 if phase[i] >= 2 else 1.0)
        path = run["paths"][it]
        text = "iteration " + str(it) + " of " + str(cfg["iterations"]) \
            + "\nnodes " + str(pts.shape[0])
        if path is None:
            best.set_data([], [])
            text += "\nno path to the goal yet"
        else:
            best.set_data(path[:, 0], path[:, 1])
            lengths, clearances = path_geometry(world, path)
            text += "\nbest path " + str(round(float(lengths.sum()), 1)) + " m, clearance " \
                + str(round(float(clearances.min()), 2)) + " m"
        status.set_text(text)
        best.set_linewidth(3.4 if phase[i] >= 2 else 2.6)
        f = run["final"]
        verdict.set_text("nominal length " + str(round(f["length"], 2)) + " m\n"
                         + "smallest clearance " + str(round(f["clearance"], 3)) + " m\n"
                         + str(cfg["n_exec"]) + " executions over the " + str(round(budget, 1))
                         + " m budget: " + str(round(100 * f["over"], 1)) + " %")
        verdict.set_visible(bool(phase[i] >= 2))


ffmpeg = shutil.which("ffmpeg")
width, height = fig.canvas.get_width_height()
mp4 = out / "rarrt_tree_growth.mp4"
gif = out / "rarrt_tree_growth.gif"
enc = subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                        "-s", str(width) + "x" + str(height), "-r", str(a.fps), "-i", "-",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
                        "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
for i in range(n):
    draw(i)
    fig.canvas.draw()
    enc.stdin.write(bytes(fig.canvas.buffer_rgba()))
enc.stdin.close()
enc.wait()

fig.savefig(out / "rarrt_tree_growth_poster.svg", metadata={"Date": None})
fig.savefig(out / "rarrt_tree_growth_poster.pdf", metadata={"CreationDate": None})
plt.close(fig)

for gif_fps in [12, 8]:
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    "fps=" + str(gif_fps) + ",scale=640:-1:flags=lanczos,split[a][b];"
                    "[a]palettegen=max_colors=64:stats_mode=diff[p];"
                    "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                    str(gif)], check=True)
    if gif.stat().st_size <= 3 * 1024 * 1024:
        break

print("frames", n, "fps", a.fps, "duration", round(n / a.fps, 2), "s")
print("mp4", mp4.stat().st_size, "bytes; gif", gif.stat().st_size, "bytes at", gif_fps, "fps")
print("wall time", round(time.time() - started, 1), "s")
