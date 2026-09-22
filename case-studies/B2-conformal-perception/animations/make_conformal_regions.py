"""One closed-loop episode with and without the conformal regions.

Replays the episode behind figures/trajectories.svg (cpnav.replay repeats the
case study's seeded draws, so the calibrated q and the worlds are the study's
own) with the planner's per-step hook switched on. Left: the robot plans
against its raw detections. Right: it plans against the conformal regions, each
detection grown by the calibrated q. At every control step the frame shows the
detections, the regions, the path the planner would follow from the current
cell and the trajectory so far.

    uv run python animations/make_conformal_regions.py --out animations

writes conformal_regions.mp4, .gif and conformal_regions_poster.svg/.pdf.
`--seed` picks the test episode (default: the study's figure episode).
"""

import argparse
import pathlib
import shutil
import subprocess
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle

from cpnav import conformal, planner, replay, world

here = pathlib.Path(__file__).resolve().parent

p = argparse.ArgumentParser()
p.add_argument("--out", default=str(here))
p.add_argument("--frames", type=int, default=480)
p.add_argument("--fps", type=int, default=24)
p.add_argument("--height", type=int, default=1080, choices=[720, 1080],
               help="MP4 height; the width follows at 16:9")
p.add_argument("--gif-width", type=int, default=640, help="GIF width in pixels")
p.add_argument("--gif-fps", type=int, default=None,
               help="GIF frame rate (default: 12, or 8 when the GIF is over 3 MB at 12)")
p.add_argument("--seed", type=int, default=None,
               help="test episode to show, 0 to 23 (default: the study's figure episode)")
a = p.parse_args()

started = time.time()
out = pathlib.Path(a.out)
out.mkdir(parents=True, exist_ok=True)
plt.rcParams["svg.hashsalt"] = "conformal_regions"

# ------------------------------------------------------------------
# the replayed pair, recorded step by step

steps = []
r = replay.figure_pair(on_step=lambda s: steps.append(s))
summary, q, pair = r["summary"], r["q"], r["pair"]
episode = summary["figure_episode"] if a.seed is None else a.seed
print("q", q, "summary q_m", summary["operating_point"]["q_m"])
print("closed-loop coverage", r["closed_loop_coverage"], "summary",
      summary["operating_point"]["closed_loop_coverage"])
assert q == summary["operating_point"]["q_m"]

arms = [episode, replay.N_FIGURE + episode]
boxes, valid = r["boxes"][episode], r["valid"][episode]
# control steps until each arm's episode ended (a waiting step counts too)
ended = np.stack([s["status"][arms] != planner.RUNNING for s in steps])
n_steps = [int(np.argmax(ended[:, j])) + 1 if ended[:, j].any() else len(steps) for j in range(2)]
status = [int(pair["status"][k]) for k in arms]
last = max(n_steps)
print("episode", episode, "steps", n_steps, "status", status,
      "lengths", [float(pair["length"][k]) for k in arms])

# per arm and step: pose before and after, detections, conformal regions, planned path
rec = []
for k in arms:
    arm = []
    for s in steps[:last]:
        cells, used = planner.descend(s["cost_to_go"][k:k + 1], s["rc_before"][k:k + 1])
        plan_xy = (cells[0, :used[0], ::-1] + 0.5) * world.RES
        dv = s["det_valid"][k]
        arm.append({"before": s["xy_before"][k], "after": s["xy"][k], "det": s["det"][k][dv],
                    "region": conformal.inflate(s["det"][k][dv], q), "plan": plan_xy})
    rec.append(arm)

# the true box the nominal arm ran into, if it did
hit = np.zeros(len(boxes), dtype=bool)
if status[0] == planner.COLLISION:
    end = pair["traj"][arms[0]][n_steps[0]]
    grown = conformal.inflate(boxes, world.ROBOT_HALF)
    hit = valid & np.all((grown[:, :2] <= end) & (end <= grown[:, 2:]), axis=1)

# ------------------------------------------------------------------
# timeline: world alone, the steps, the closing numbers

n = a.frames
n_intro = int(round(0.05 * n))
n_run = max(int(round(0.78 * n)), 1)
clock = np.concatenate([np.zeros(n_intro), last * np.arange(1, n_run + 1) / n_run,
                        np.full(n - n_intro - n_run, float(last))])
closing = np.arange(n) >= n_intro + n_run

# ------------------------------------------------------------------
# the figure

fig, axes = plt.subplots(1, 2, figsize=(12.8, 7.2), dpi=100)
fig.subplots_adjust(left=0.04, right=0.98, top=0.82, bottom=0.12, wspace=0.1)
fig.suptitle("Conformal regions in the loop: test episode " + str(episode) + ", alpha = "
             + str(summary["operating_point"]["alpha"]) + ", calibrated q = "
             + str(round(q, 3)) + " m", fontsize=14)
fig.text(0.5, 0.87, "grey: true obstacle, unknown to the robot (red once struck)   "
         "orange dashed: detection\npurple: conformal region, the detection grown by q   "
         "blue dashed: the current plan   blue square: the robot's footprint",
         ha="center", fontsize=10, color="0.3", linespacing=1.4)
titles = ["planning on the raw detections", "planning on the conformal regions"]
art = []
for j, ax in enumerate(axes):
    truth = PatchCollection([Rectangle(b[:2], b[2] - b[0], b[3] - b[1]) for b in boxes[valid]],
                            facecolor="0.78", edgecolor="0.35", lw=1.0, zorder=1)
    ax.add_collection(truth)
    det = PatchCollection([], facecolor="none", edgecolor="darkorange", lw=1.4, ls="--", zorder=3)
    region = PatchCollection([], facecolor="#8e44ad22", edgecolor="#8e44ad", lw=1.2, zorder=2)
    ax.add_collection(region)
    ax.add_collection(det)
    region.set_visible(j == 1)
    plan_line, = ax.plot([], [], color="tab:blue", lw=1.3, ls="--", zorder=4)
    trail, = ax.plot([], [], color="tab:blue", lw=2.2, zorder=5)
    robot = Rectangle((0, 0), 2 * world.ROBOT_HALF, 2 * world.ROBOT_HALF, facecolor="tab:blue",
                      edgecolor="navy", zorder=6)
    ax.add_patch(robot)
    crash, = ax.plot([], [], "X", color="red", ms=16, zorder=7)
    ax.plot(*world.GOAL_XY, "*", color="crimson", ms=16, zorder=5)
    ax.set_xlim(0, world.SIZE)
    ax.set_ylim(0, world.SIZE)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_title(titles[j], fontsize=13)
    label = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top", fontsize=11, zorder=8,
                    bbox=dict(facecolor="white", edgecolor="0.7", alpha=0.9))
    art.append((truth, det, region, plan_line, trail, robot, crash, label))
axes[0].set_ylabel("y (m)")
closing_text = fig.text(
    0.5, 0.025,
    "over the study's " + str(summary["test_episodes"]) + " test episodes: collisions "
    + str(int(round(summary["nominal"]["collision_rate"] * summary["test_episodes"])))
    + " on the raw detections, "
    + str(int(round(summary["conformalized"]["collision_rate"] * summary["test_episodes"])))
    + " on the conformal regions; held-out coverage "
    + str(round(summary["operating_point"]["holdout_coverage"], 4)) + " at target "
    + str(round(1 - summary["operating_point"]["alpha"], 2)),
    ha="center", fontsize=12)


def rects(b):
    return [Rectangle(x[:2], x[2] - x[0], x[3] - x[1]) for x in b]


def draw(i):
    c = clock[i]
    for j, (truth, det, region, plan_line, trail, robot, crash, label) in enumerate(art):
        done = n_steps[j]
        t = min(int(c), done - 1) if c < done else done - 1
        frac = min(c - t, 1.0) if c > 0 else 0.0
        s = rec[j][t]
        pos = s["before"] + frac * (s["after"] - s["before"])
        det.set_paths(rects(s["det"]))
        region.set_paths(rects(s["region"]))
        plan_line.set_data(s["plan"][:, 0], s["plan"][:, 1])
        plan_line.set_visible(c < done)
        path = np.vstack([world.START_XY] + [x["after"] for x in rec[j][:t]] + [pos])
        trail.set_data(path[:, 0], path[:, 1])
        robot.set_xy(pos - world.ROBOT_HALF)
        finished = c >= done
        struck = finished and status[j] == planner.COLLISION
        truth.set_facecolor(np.where(hit[valid] & struck, "#e8a0a0", "0.78"))
        if struck:
            crash.set_data([pos[0]], [pos[1]])
            text = "collision at step " + str(done)
        elif finished and status[j] == planner.SUCCESS:
            crash.set_data([], [])
            text = "goal reached at step " + str(done) + ", path " \
                + str(round(float(pair["length"][arms[j]]), 2)) + " m"
        else:
            crash.set_data([], [])
            text = "step " + str(min(int(c) + 1, done)) if c > 0 else "start"
        label.set_text(text)
    closing_text.set_visible(bool(closing[i]))


ffmpeg = shutil.which("ffmpeg")
mp4 = out / "conformal_regions.mp4"
gif = out / "conformal_regions.gif"
# The figure is laid out at 1280 x 720 (100 dpi); 1080p is the same figure at 150 dpi. A GIF
# up to 1280 px wide is scaled from 720p frames, encoded beside the MP4 and deleted after.
streams = [(mp4, 100 * a.height / 720)]
if a.height != 720 and a.gif_width <= 1280:
    streams.append((out / "conformal_regions_720p.mp4", 100))


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

fig.savefig(out / "conformal_regions_poster.svg", metadata={"Date": None})
fig.savefig(out / "conformal_regions_poster.pdf", metadata={"CreationDate": None})
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
