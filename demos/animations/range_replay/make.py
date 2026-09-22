# The eight Carter traverses of the range campaign replayed together, at real time,
# over the relief of the range heightmap, with each traverse's pitch and roll and the
# VERITAS STL observer's three verdict lamps.
#
# The trajectories are the ones the headless Isaac Sim trials wrote
# (isaacsim/results/trajectories/trial_<n>.csv, 60 Hz, t x y z roll pitch yaw v); the
# design point of each is its campaign.csv row; the attitude bound is the one in
# veritas/runtime/stl-observer/specs/range_safety.yaml; a lamp turns red at the
# first-violation time the observer's replay recorded in results/range/verdicts.csv.

import csv
import json
import sys
import pathlib

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render  # noqa: E402

NAME = "range_replay"
ISAAC = render.ROOT / "isaacsim"
CAMPAIGN = ISAAC / "results" / "campaign.csv"
TRAJ = ISAAC / "results" / "trajectories"
HEIGHTMAP = ISAAC / "range" / "terrain" / "heightmap.npz"
META = ISAAC / "range" / "terrain" / "terrain_meta.json"
OBSERVER = render.ROOT / "veritas" / "runtime" / "stl-observer"
VERDICTS = OBSERVER / "results" / "range" / "verdicts.csv"
SPEC = OBSERVER / "specs" / "range_safety.yaml"

# The translate on /World/terrain1_world in isaacsim/range/sim_world2.usd (a binary USD
# layer; isaacsim/tools/range_doe.base_offset reads it with pxr and returns (1, 1, 0)).
BASE_OFFSET = (1.0, 1.0)
HALF = 12.0          # the campaign figure's window: start +/- 12 m
SIM_SECONDS = 30.0
GAUGE_MAX = 45.0
MONITORS = [("roll_safety", "roll"), ("pitch_safety", "pitch"), ("progress", "progress")]
COLOURS = plt.get_cmap("tab10").colors


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def load():
    rows = sorted(read_csv(CAMPAIGN), key=lambda r: int(r["trial_id"]))
    traces = np.stack([np.loadtxt(TRAJ / ("trial_" + r["trial_id"] + ".csv"), delimiter=",",
                                  skiprows=1) for r in rows])        # (8, 1801, 8)
    verdicts = {r["trace"]: r for r in read_csv(VERDICTS)}
    spec = yaml.safe_load(open(SPEC))
    bounds = {m["name"]: m["formula"] for m in spec["monitors"]}
    first = np.full((len(rows), len(MONITORS)), np.inf)
    for i, r in enumerate(rows):
        v = verdicts["trial_" + r["trial_id"] + ".csv"]
        for j, (name, _) in enumerate(MONITORS):
            if v[name + "_verdict"] == "violated":
                first[i, j] = float(v[name + "_first_violation_s"])
    return {"rows": rows, "traces": traces, "first": first, "formulas": bounds,
            "attitude_bound_rad": attitude_bound(spec)}


def attitude_bound(spec):
    """The roll/pitch bound in radians, read out of `historically (abs(roll) <= 0.35)`."""
    f = next(m["formula"] for m in spec["monitors"] if m["name"] == "roll_safety")
    return float(f.split("<=")[1].strip(" )"))


def label(row):
    slope = row["max_slope_deg"]
    slope = "authored slope" if slope == "authored" else "slope " + str(int(float(slope))) + " deg"
    return "density " + row["obstacle_density"] + ", " + slope


def relief(x0, y0):
    """Hillshaded crop of the heightmap over start +/- HALF, in the campaign figure's axes."""
    h = np.load(HEIGHTMAP)["height"].astype(np.float64)
    meta = json.loads(META.read_text())
    m = meta["scene_xform"]["obj_to_world"]
    gx0 = m["x_offset"] + m["x_from_obj_x"] * meta["x0"] + BASE_OFFSET[0]
    gy0 = m["y_offset"] + m["y_from_obj_z"] * meta["z0"] + BASE_OFFSET[1]
    dx = m["x_from_obj_x"] * meta["dx"]
    dy = m["y_from_obj_z"] * meta["dz"]
    # world x decreases with the row index, world y with the column index
    rows = np.sort(np.round((np.array([x0 - HALF, x0 + HALF]) - gx0) / dx).astype(int))
    cols = np.sort(np.round((np.array([y0 - HALF, y0 + HALF]) - gy0) / dy).astype(int))
    crop = h[rows[0]:rows[1] + 1, cols[0]:cols[1] + 1] * m["z_from_obj_y"]
    img = crop[::-1, ::-1].T
    xs = gx0 + dx * rows
    ys = gy0 + dy * cols
    shade = LightSource(azdeg=315, altdeg=40).hillshade(img, vert_exag=4.0, dx=abs(dx), dy=abs(dy))
    return shade, (xs.min(), xs.max(), ys.min(), ys.max())


def build(fps):
    d = load()
    rows, tr, first = d["rows"], d["traces"], d["first"]
    n = len(rows)
    n_full = int(round(SIM_SECONDS * fps))
    t_rec = tr[0, :, 0]
    bound_deg = np.degrees(d["attitude_bound_rad"])
    x0, y0 = tr[0, 0, 1], tr[0, 0, 2]

    fig = render.figure()
    ax = fig.add_axes([0.06, 0.08, 0.40, 0.80])
    shade, extent = relief(x0, y0)
    ax.imshow(shade, origin="lower", extent=extent, cmap="Greys_r", vmin=-0.3, vmax=1.3,
              aspect="equal")
    ax.plot([x0], [y0], marker="*", markersize=13, color="crimson", zorder=5)
    ax.set_xlim(x0 - HALF, x0 + HALF)
    ax.set_ylim(y0 - HALF, y0 + HALF)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    trails = [ax.plot([], [], lw=2.0, color=COLOURS[i], zorder=3)[0] for i in range(n)]
    dots = [ax.plot([], [], "o", ms=7, color=COLOURS[i], mec="k", mew=0.7, zorder=6)[0]
            for i in range(n)]
    tags = [ax.text(0, 0, str(i + 1), fontsize=8, weight="bold", zorder=7) for i in range(n)]
    clock = ax.set_title("", loc="left", fontsize=12)
    fig.text(0.06, 0.94, "Range campaign: eight headless Isaac Sim traverses, replayed together",
             fontsize=14, weight="bold")

    # one tile per traverse: two attitude gauges and the three verdict lamps
    gauges, readouts, lamps, lamp_notes = [], [], [], []
    for i, row in enumerate(rows):
        c, r = i % 2, i // 2
        left, bottom = 0.51 + c * 0.25, 0.715 - r * 0.2
        g = fig.add_axes([left + 0.04, bottom + 0.035, 0.12, 0.075])
        g.set_xlim(0, GAUGE_MAX)
        g.set_ylim(-0.6, 1.6)
        g.set_yticks([0, 1])
        g.set_yticklabels(["roll", "pitch"], fontsize=8)
        g.set_xticks([0, 20, 40])
        g.tick_params(labelsize=7, length=2, pad=1)
        g.axvline(bound_deg, color="#c44e52", lw=1.2, ls="--")
        g.set_title(str(i + 1) + "  " + label(row), fontsize=9, loc="left", color=COLOURS[i],
                    weight="bold", x=-0.33, pad=3)
        gauges.append(g.barh([0, 1], [0, 0], height=0.6, color=["0.45", "0.45"]))
        readouts.append(g.text(GAUGE_MAX * 1.03, 0.5, "", fontsize=7.5, va="center", ha="left"))
        la = fig.add_axes([left + 0.02, bottom - 0.03, 0.22, 0.035])
        la.set_xlim(-0.3, 3.0)
        la.set_ylim(-1, 1)
        la.axis("off")
        lamps.append(la.scatter(np.arange(3) * 0.9, np.zeros(3), s=90, c=["#55a868"] * 3,
                                edgecolors="k", linewidths=0.5))
        note_row = []
        for j, (_, short) in enumerate(MONITORS):
            la.text(j * 0.9 + 0.1, 0.0, short, fontsize=7.5, va="center")
            note_row.append(la.text(j * 0.9 - 0.12, -1.25, "", fontsize=7, color="#c44e52",
                                    va="top"))
        lamp_notes.append(note_row)
    fig.text(0.51, 0.018, "|roll|, |pitch| in deg; dashed: observer bound " + str(d["attitude_bound_rad"])
             + " rad (" + str(round(float(bound_deg), 1)) + " deg); lamps: VERITAS STL verdicts",
             fontsize=8, color="0.25")

    def draw(t):
        sim = t * SIM_SECONDS
        k = int(np.searchsorted(t_rec, sim - 1e-9))
        k = min(k, len(t_rec) - 1)
        att = np.degrees(np.abs(tr[:, k, 4:6]))              # (8, 2): roll, pitch
        for i in range(n):
            trails[i].set_data(tr[i, :k + 1, 1], tr[i, :k + 1, 2])
            dots[i].set_data([tr[i, k, 1]], [tr[i, k, 2]])
            tags[i].set_position((tr[i, k, 1] + 0.35, tr[i, k, 2] + 0.35))
            for b, v in zip(gauges[i], att[i]):
                b.set_width(min(v, GAUGE_MAX))
                b.set_color("#c44e52" if v > bound_deg else "0.45")
            readouts[i].set_text("roll " + str(round(float(att[i, 0]), 1)) + "\npitch "
                                 + str(round(float(att[i, 1]), 1)))
            red = sim >= first[i]
            lamps[i].set_facecolor(np.where(red, "#c44e52", "#55a868"))
            for j in range(len(MONITORS)):
                lamp_notes[i][j].set_text("at " + str(first[i, j]) + " s" if red[j] else "")
        clock.set_text("t = " + str(round(sim, 1)) + " s of " + str(int(SIM_SECONDS))
                       + " s simulated")

    return fig, draw, n_full, d


def main():
    a = render.arguments(NAME, gif_speed=2.0)
    fig, draw, n_full, _ = build(a.fps)
    ts = render.timeline(n_full, a.frames)
    render.render(fig, draw, ts, a.out, NAME, a.fps, poster_t=1.0,
                  gif_width=a.gif_width, gif_fps=a.gif_fps, gif_speed=a.gif_speed,
                  height=a.height)


if __name__ == "__main__":
    main()
