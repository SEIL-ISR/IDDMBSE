# The three robots of the assured multi-robot case study moving through the room along
# their executed trajectories (seed 0), with the six station windows on a timeline, the
# separation breach marked at the step it happens, and each robot's STL robustness
# accumulating to the value VERITAS wrote back into the fleet model.
#
# Geometry, windows and separation distance come from model/fleet_requirements.yaml,
# the plans and executed traces from results/summary.json, the recorded robustness from
# results/goal_satisfaction.json and model/agr_fleet.yaml. The running robustness is
# the formula phi_i = F(goal 1) & F(goal 2) & G(outside every obstacle & separated)
# evaluated on the prefix seen so far: the G part as a running minimum, and a station
# term (its best value inside its window) once that window has closed. The value can
# only fall as the trace grows; at the last step it is the robustness of the whole trace.

import json
import sys
import pathlib

import numpy as np
import matplotlib.pyplot as plt
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render  # noqa: E402

NAME = "multirobot_room"
CASE = render.ROOT / "case-studies" / "B3-assured-multi-robot"
FLEET = CASE / "model" / "fleet_requirements.yaml"
AGR = CASE / "model" / "agr_fleet.yaml"
SUMMARY = CASE / "results" / "summary.json"
GOALS = CASE / "results" / "goal_satisfaction.json"

COLORS = ["#1f77b4", "#d62728", "#2ca02c"]      # the case study's own figure colours
INTRO, OUTRO = 1.5, 3.5


def halfspaces(entry):
    """Rows normalised so a predicate's value is a signed distance, as specs.Polytope does."""
    if entry.get("type", "box") == "box":
        A = np.array([[-1.0, 0.0], [1.0, 0.0], [0.0, -1.0], [0.0, 1.0]])
        b = np.array([-entry["x"][0], entry["x"][1], -entry["y"][0], entry["y"][1]], float)
    else:
        A = np.asarray(entry["A"], float)
        b = np.asarray(entry["b"], float)
    n = np.linalg.norm(A, axis=1)
    return A / n[:, None], b / n


def vertices(A, b):
    """Vertices of a bounded 2-D polytope, counter-clockwise (every row pair intersected)."""
    i, j = np.triu_indices(len(A), k=1)
    M = np.stack([A[i], A[j]], axis=1)
    ok = np.abs(np.linalg.det(M)) > 1e-9
    pts = np.linalg.solve(M[ok], np.stack([b[i], b[j]], axis=1)[ok][..., None])[..., 0]
    pts = np.unique(np.round(pts[np.all(pts @ A.T <= b + 1e-7, axis=1)], 9), axis=0)
    c = pts.mean(axis=0)
    return pts[np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))]


def load():
    cfg = yaml.safe_load(open(FLEET))
    s = json.load(open(SUMMARY))
    return {"cfg": cfg, "executed": np.asarray(s["executed"], float),
            "plan": np.asarray(s["plan"], float), "summary": s,
            "goals": json.load(open(GOALS)), "agr": yaml.safe_load(open(AGR))}


def signals(cfg, traj):
    """Per-robot leaf signals over the steps: stations (R, 2, T), safety (R, T), sep (R, R, T)."""
    obstacles = [halfspaces(o) for o in cfg["obstacles"]]
    R, T = traj.shape[0], traj.shape[1]
    outside = np.stack([(traj @ A.T - b).max(axis=-1) for A, b in obstacles])   # (O, R, T)
    diff = np.abs(traj[:, None] - traj[None, :]).max(axis=-1) - cfg["separation"]["d_min"]
    diff[np.arange(R), np.arange(R)] = np.inf
    safety = np.minimum(outside.min(axis=0), diff.min(axis=1))                  # (R, T)
    station = np.stack([np.stack([(halfspaces({**g, "type": "box"})[1]
                                   - traj[i] @ halfspaces({**g, "type": "box"})[0].T).min(axis=-1)
                                  for g in r["goals"]]) for i, r in enumerate(cfg["robots"])])
    return station, safety, diff


def running_rho(cfg, traj):
    """(R, T) robustness of phi_i on the prefix up to each step."""
    station, safety, _ = signals(cfg, traj)
    R, T = safety.shape
    k = np.arange(T)
    terms = [np.minimum.accumulate(safety, axis=1)]
    for g in range(station.shape[1]):
        win = np.array([r["goals"][g]["window"] for r in cfg["robots"]])            # (R, 2)
        inside = (k[None, :] >= win[:, :1]) & (k[None, :] <= win[:, 1:])
        best = np.where(inside, station[:, g], -np.inf).max(axis=1, keepdims=True)
        terms.append(np.where(k[None, :] >= win[:, 1:], best, np.inf))
    return np.min(np.stack(terms), axis=0)


def breaches(cfg, traj):
    """(i, j, k, value) for every sample step where a pair is closer than d_min."""
    _, _, diff = signals(cfg, traj)
    i, j, k = np.nonzero(np.triu(np.ones(diff.shape[:2]), 1)[:, :, None] * (diff < 0))
    return [(int(a), int(b), int(c), float(diff[a, b, c])) for a, b, c in zip(i, j, k)]


def build(fps):
    d = load()
    cfg, ex, plan = d["cfg"], d["executed"], d["plan"]
    R, T = ex.shape[0], ex.shape[1]
    dt = cfg["horizon"]["dt"]
    horizon = dt * (T - 1)
    n_full = int(round((INTRO + horizon + OUTRO) * fps))
    rho = running_rho(cfg, ex)
    hits = breaches(cfg, ex)
    recorded = d["goals"]["blocks"]
    half = cfg["separation"]["d_min"] / 2.0

    fig = render.figure()
    ax = fig.add_axes([0.05, 0.30, 0.52, 0.60])
    for o in cfg["obstacles"]:
        v = vertices(*halfspaces(o))
        ax.fill(v[:, 0], v[:, 1], color="0.65", edgecolor="0.3", zorder=1)
        ax.text(v[:, 0].mean(), v[:, 1].mean(), o["id"].replace("OBS_", ""), ha="center",
                va="center", fontsize=7, color="0.15", zorder=3)
    boxes = []
    for i, r in enumerate(cfg["robots"]):
        for g in r["goals"]:
            v = vertices(*halfspaces({**g, "type": "box"}))
            patch = ax.fill(v[:, 0], v[:, 1], color=COLORS[i], alpha=0.10, zorder=1)[0]
            ax.plot(np.append(v[:, 0], v[0, 0]), np.append(v[:, 1], v[0, 1]), ls="--", lw=1.0,
                    color=COLORS[i], zorder=2)
            ax.text(v[:, 0].mean(), v[:, 1].max() + 0.1, g["id"], ha="center", fontsize=7.5,
                    color=COLORS[i], zorder=3)
            boxes.append((patch, i, g["window"]))
    for i in range(R):
        ax.plot(plan[i, :, 0], plan[i, :, 1], ls="--", lw=1.0, color=COLORS[i], alpha=0.45, zorder=4)
    trails = [ax.plot([], [], lw=2.0, color=COLORS[i], zorder=5)[0] for i in range(R)]
    feet = [ax.add_patch(plt.Rectangle((0, 0), 2 * half, 2 * half, fc=COLORS[i], alpha=0.35,
                                       ec=COLORS[i], lw=1.2, zorder=6)) for i in range(R)]
    dots = [ax.plot([], [], "o", ms=6, color=COLORS[i], mec="k", mew=0.6, zorder=7)[0]
            for i in range(R)]
    link = ax.plot([], [], color="black", lw=2.5, zorder=8)[0]
    marks = ax.plot([], [], "o", ms=16, mfc="none", mec="#b00000", mew=2.0, zorder=8)[0]
    breach_text = ax.text(0.1, 5.75, "", fontsize=10, color="#b00000", weight="bold", zorder=9)
    ax.set_xlim(cfg["workspace"]["x"])
    ax.set_ylim(cfg["workspace"]["y"])
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    clock = ax.set_title("", loc="left", fontsize=12)
    fig.text(0.05, 0.945, "Assured multi-robot coordination: executed traces (seed 0) and "
             "their STL robustness", fontsize=14, weight="bold")

    # station windows on a timeline
    tl = fig.add_axes([0.05, 0.07, 0.52, 0.15])
    bars = []
    rows = [(i, g) for i, r in enumerate(cfg["robots"]) for g in r["goals"]]
    for y, (i, g) in enumerate(rows):
        a, b = g["window"]
        bars.append(tl.barh(y, (b - a) * dt, left=a * dt, height=0.7, color=COLORS[i], alpha=0.25)[0])
    tl.set_yticks(np.arange(len(rows)))
    tl.set_yticklabels([g["id"] for _, g in rows], fontsize=7.5)
    tl.set_ylim(len(rows) - 0.5, -0.5)
    tl.set_xlim(0, horizon)
    tl.set_xlabel("time [s]  (station windows k in [a, b], dt = " + str(dt) + " s)", fontsize=9)
    tl.tick_params(labelsize=8)
    cursor = tl.axvline(0, color="k", lw=1.2)
    for _, _, k, _ in hits:
        tl.axvline(k * dt, color="#b00000", lw=1.0, ls=":")

    # running robustness per robot
    rx = fig.add_axes([0.66, 0.30, 0.30, 0.52])
    finals = np.array([recorded[b["id"]]["goal_satisfaction"] for b in d["agr"]["blocks"]
                       if b["id"].startswith("AGR_") and b["id"] != "AGR_Fleet_Assembly"])
    rbars = rx.bar(np.arange(R), np.zeros(R), color=COLORS, width=0.6)
    rx.scatter(np.arange(R), finals, marker="_", s=900, color="k", zorder=5)
    rx.axhline(0.0, color="k", lw=0.9)
    rx.axhline(d["summary"]["required_margin"], color="0.5", lw=0.9, ls="--")
    rx.text(R - 0.5, d["summary"]["required_margin"] + 0.01, "planned margin "
            + str(d["summary"]["required_margin"]) + " m", ha="right", fontsize=8, color="0.4")
    rx.set_xticks(np.arange(R))
    rx.set_xticklabels([r["id"] + "\nphi_" + str(i + 1) for i, r in enumerate(cfg["robots"])])
    rx.set_ylim(-0.2, 1.1)
    rx.set_ylabel("STL robustness rho [m]")
    rx.set_title("robustness of the trace so far (a station counts once\nits window closes; "
                 "black tick: the value written back)",
                 fontsize=10)
    rvals = [rx.text(i, 0, "", ha="center", fontsize=9) for i in range(R)]
    verdict = fig.text(0.66, 0.12, "", fontsize=9.5, va="top")

    sec = np.arange(n_full) / fps
    s_all = np.clip(sec - INTRO, 0.0, horizon)

    def draw(t):
        i = int(round(t * (n_full - 1)))
        s = s_all[i]
        u = s / dt
        k = int(np.floor(u + 1e-9))
        k1 = min(k + 1, T - 1)
        f = u - k
        pos = (1 - f) * ex[:, k] + f * ex[:, k1]
        for r in range(R):
            trails[r].set_data(np.append(ex[r, :k + 1, 0], pos[r, 0]),
                               np.append(ex[r, :k + 1, 1], pos[r, 1]))
            dots[r].set_data([pos[r, 0]], [pos[r, 1]])
            feet[r].set_xy((pos[r, 0] - half, pos[r, 1] - half))
            v = rho[r, k]
            shown = min(v, 1.05)
            rbars[r].set_height(shown)
            rvals[r].set_position((r, shown + (0.02 if shown >= 0 else -0.06)))
            rvals[r].set_text(str(round(float(v), 3)) if np.isfinite(v) else "")
        for patch, r, (a, b) in boxes:
            patch.set_alpha(0.35 if a <= u <= b else 0.10)
        for bar, (r, g) in zip(bars, rows):
            a, b = g["window"]
            bar.set_alpha(0.85 if a <= u <= b else (0.45 if u > b else 0.25))
        cursor.set_xdata([s, s])
        seen = [h for h in hits if h[2] <= k]
        if seen:
            a, b, kk, val = seen[0]
            link.set_data([ex[a, kk, 0], ex[b, kk, 0]], [ex[a, kk, 1], ex[b, kk, 1]])
            marks.set_data([ex[a, kk, 0], ex[b, kk, 0]], [ex[a, kk, 1], ex[b, kk, 1]])
            breach_text.set_text("separation breach: sep(" + str(a + 1) + "," + str(b + 1) + ") = "
                                 + str(round(val, 3)) + " m at k = " + str(kk)
                                 + " (t = " + str(round(kk * dt, 1)) + " s)")
        else:
            link.set_data([], [])
            marks.set_data([], [])
            breach_text.set_text("")
        clock.set_text("t = " + str(round(float(s), 1)) + " s, step k = " + str(k) + " of " + str(T - 1))
        if k == T - 1 and s >= horizon:
            lines = [r["id"] + ": " + str(recorded[r["id"]]["goal_satisfaction"]) + " m, "
                     + recorded[r["id"]]["verdict"] + " (" + recorded[r["id"]]["binding_conjunct"] + ")"
                     for r in cfg["robots"]]
            verdict.set_text("written back to model/agr_fleet.yaml\n" + "\n".join(lines))
        else:
            verdict.set_text("")

    return fig, draw, n_full, {"rho": rho, "hits": hits, "finals": finals}


def main():
    a = render.arguments(NAME)
    fig, draw, n_full, _ = build(a.fps)
    ts = render.timeline(n_full, a.frames)
    render.render(fig, draw, ts, a.out, NAME, a.fps, poster_t=1.0,
                  gif_width=a.gif_width, gif_fps=a.gif_fps, gif_speed=a.gif_speed,
                  height=a.height)


if __name__ == "__main__":
    main()
