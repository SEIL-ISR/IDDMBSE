# The split-conformal calibration of the conformal-perception study, drawn from the
# detections PERFECT's 270-trial campaign wrote back.
#
# First the nominal detector's calibration detections (seeds 0-19, in the order the
# campaign table holds them) accumulate as a scatter of nonconformity score against
# range, the (1 - alpha) conformal quantile of the detections seen so far settles, and
# the coverage that quantile gives on the held-out detections (seeds 20-29) converges.
# Then the alpha sweep: held-out coverage as a function of the margin q, with the seven
# calibrated levels of coverage.csv on it, and the degraded detector's curve beside it.
#
# The score is cpnav.conformal.scores (the largest amount by which the detected box
# falls inside the true one on any edge), the quantile cpnav.conformal.quantile
# (the ceil((n + 1)(1 - alpha))-th smallest score).

import csv
import json
import sys
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render  # noqa: E402

NAME = "calibration_curve"
RESULTS = render.ROOT / "case-studies" / "B2-conformal-perception" / "results" / "perfect"
CALIBRATION = RESULTS / "calibration.csv"
COVERAGE = RESULTS / "coverage.csv"
SUMMARY = RESULTS / "summary.json"

N_CALIBRATION_SEEDS = 20
DETECTOR = "nominal"
ALPHA = 0.1
FIRST_N = 10
GROW, HOLD1, SWEEP, HOLD2 = 12.0, 1.5, 6.0, 2.5


def scores(a):
    return np.max(np.stack([a["det_xmin"] - a["true_xmin"], a["det_ymin"] - a["true_ymin"],
                            a["true_xmax"] - a["det_xmax"], a["true_ymax"] - a["det_ymax"]]), axis=0)


def prefix_quantiles(cal, ns, alpha):
    """Conformal quantile of cal[:n] for every n in ns, as one masked sort."""
    idx = np.arange(cal.size)
    masked = np.where(idx[None, :] < ns[:, None], cal[None, :], np.inf)
    ranked = np.sort(masked, axis=1)
    k = np.ceil((ns + 1) * (1.0 - alpha)).astype(int)
    return np.where(k <= ns, ranked[np.arange(len(ns)), np.minimum(k, ns) - 1], np.inf)


def load():
    a = np.genfromtxt(CALIBRATION, delimiter=",", names=True, dtype=None, encoding="utf-8")
    s = scores(a)
    nominal = a["detector"] == DETECTOR
    cal = nominal & (a["seed"] < N_CALIBRATION_SEEDS)
    hold = nominal & (a["seed"] >= N_CALIBRATION_SEEDS)
    with open(COVERAGE) as f:
        coverage = list(csv.DictReader(f))
    return {"score": s, "range": a["range"], "cal": cal, "hold": hold,
            "degraded": a["detector"] == "degraded", "coverage": coverage,
            "summary": json.load(open(SUMMARY))}


def reductions(n_steps=200):
    d = load()
    cal = d["score"][d["cal"]]
    hold = d["score"][d["hold"]]
    ns = np.unique(np.round(np.linspace(FIRST_N, cal.size, n_steps)).astype(int))
    q = prefix_quantiles(cal, ns, ALPHA)
    cover = (hold[None, :] <= q[:, None]).mean(axis=1)
    return {"data": d, "ns": ns, "q": q, "cover": cover, "cal": cal, "hold": hold,
            "cal_range": d["range"][d["cal"]]}


def build(fps):
    r = reductions(int(GROW * fps))
    d = r["data"]
    ns, q, cover = r["ns"], r["q"], r["cover"]
    cal, hold, rng = r["cal"], r["hold"], r["cal_range"]
    degraded = np.sort(d["score"][d["degraded"]])
    hold_sorted = np.sort(hold)
    rows = d["coverage"]
    alphas = np.array([float(x["alpha"]) for x in rows])
    q_rec = np.array([float(x["q"]) for x in rows])
    c_rec = np.array([float(x["holdout_coverage"]) for x in rows])
    c_deg = np.array([float(x["coverage_degraded"]) for x in rows])
    op = d["summary"]["operating_point"]
    n_full = int(round((GROW + HOLD1 + SWEEP + HOLD2) * fps))
    sec = np.arange(n_full) / fps
    step = np.minimum((np.clip(sec / GROW, 0, 1) * (len(ns) - 1)).round().astype(int), len(ns) - 1)
    sweep = render.ease((sec - GROW - HOLD1) / SWEEP)
    qgrid = np.linspace(0.0, 1.6, 400)
    curve_hold = np.searchsorted(hold_sorted, qgrid, side="right") / hold_sorted.size
    curve_deg = np.searchsorted(degraded, qgrid, side="right") / degraded.size

    fig = render.figure()
    fig.text(0.06, 0.945, "Split-conformal calibration on PERFECT's campaign detections",
             fontsize=14, weight="bold")
    ax = fig.add_axes([0.06, 0.12, 0.42, 0.72])
    ax.set_xlim(0, float(np.ceil(rng.max())))
    ax.set_ylim(float(np.floor(cal.min() * 10) / 10), 1.8)
    ax.set_xlabel("range to the object (m)")
    ax.set_ylabel("nonconformity score (m)")
    pts = ax.scatter(rng, cal, s=4, color="#1f77b4", alpha=0.35, lw=0)
    qline = ax.axhline(0.0, color="#c44e52", lw=2.0)
    qtext = ax.text(0.02, 0.96, "", transform=ax.transAxes, fontsize=11, va="top")
    ax.set_title("calibration detections of the " + DETECTOR + " detector (seeds 0-"
                 + str(N_CALIBRATION_SEEDS - 1) + ")", fontsize=11, loc="left")

    bx = fig.add_axes([0.57, 0.12, 0.40, 0.72])
    conv = bx.plot([], [], color="#1f77b4", lw=2.0, label="held-out coverage at q(n)")[0]
    target = bx.axhline(1.0 - ALPHA, color="0.4", ls="--", lw=1.0)
    ttext = bx.text(0, 0, "", fontsize=9, color="0.3")
    hold_line = bx.plot([], [], color="#1f77b4", lw=2.0, label="nominal, held out")[0]
    deg_line = bx.plot([], [], color="#d62728", lw=2.0, label="degraded detector")[0]
    hold_pts = bx.scatter([], [], s=40, color="#1f77b4", ec="k", lw=0.6, zorder=5)
    deg_pts = bx.scatter([], [], s=40, color="#d62728", ec="k", lw=0.6, zorder=5)
    table = bx.text(0.38, 0.30, "", transform=bx.transAxes, fontsize=9, family="monospace",
                    va="bottom")
    btext = bx.text(0.02, 0.04, "", transform=bx.transAxes, fontsize=10.5)
    title_b = bx.set_title("", fontsize=11, loc="left")

    def draw(t):
        i = int(round(t * (n_full - 1)))
        j = step[i]
        n = ns[j]
        pts.set_offsets(np.column_stack([rng[:n], cal[:n]]))
        qline.set_ydata([q[j], q[j]])
        qtext.set_text("n = " + str(n) + " of " + str(cal.size) + " detections\n"
                       + "q(n) at alpha " + str(ALPHA) + " = " + str(round(float(q[j]), 4)) + " m")
        if sweep[i] <= 0:
            conv.set_data(ns[:j + 1], cover[:j + 1])
            bx.set_xlim(0, cal.size)
            bx.set_ylim(0.8, 1.0)
            bx.set_xlabel("calibration detections seen, n")
            bx.set_ylabel("coverage of the " + str(hold.size) + " held-out detections")
            target.set_ydata([1.0 - ALPHA, 1.0 - ALPHA])
            ttext.set_position((cal.size * 0.62, 1.0 - ALPHA - 0.009))
            ttext.set_text("target " + str(1.0 - ALPHA))
            title_b.set_text("held-out coverage as the quantile settles")
            btext.set_text("held-out coverage " + str(round(float(cover[j]), 4))
                           + (" (recorded " + str(round(op["holdout_coverage"], 4)) + ", q = "
                              + str(round(op["q_m"], 4)) + " m)" if j == len(ns) - 1 else ""))
            for line in (hold_line, deg_line):
                line.set_data([], [])
            hold_pts.set_offsets(np.empty((0, 2)))
            deg_pts.set_offsets(np.empty((0, 2)))
            table.set_text("")
        else:
            m = int(np.ceil(sweep[i] * len(qgrid)))
            conv.set_data([], [])
            bx.set_xlim(0.0, 1.6)
            bx.set_ylim(0.0, 1.02)
            bx.set_xlabel("margin q added to every box edge (m)")
            bx.set_ylabel("coverage")
            target.set_ydata([np.nan, np.nan])
            ttext.set_text("")
            title_b.set_text("the alpha sweep: coverage against margin")
            hold_line.set_data(qgrid[:m], curve_hold[:m])
            deg_line.set_data(qgrid[:m], curve_deg[:m])
            shown = q_rec <= qgrid[m - 1]
            hold_pts.set_offsets(np.column_stack([q_rec[shown], c_rec[shown]]))
            deg_pts.set_offsets(np.column_stack([q_rec[shown], c_deg[shown]]))
            lines = ["alpha    q (m)  held-out  degraded"]
            lines += [str(alphas[k]).ljust(6) + str(round(q_rec[k], 4)).rjust(8)
                      + str(round(c_rec[k], 4)).rjust(10) + str(round(c_deg[k], 4)).rjust(10)
                      for k in np.nonzero(shown)[0]]
            table.set_text("\n".join(lines))
            btext.set_text("")
            if bx.get_legend() is None:
                bx.legend(handles=[hold_line, deg_line], loc="lower right", fontsize=9, frameon=False)
        if sweep[i] <= 0 and bx.get_legend() is not None:
            bx.get_legend().remove()

    return fig, draw, n_full, r


def main():
    a = render.arguments(NAME)
    fig, draw, n_full, _ = build(a.fps)
    ts = render.timeline(n_full, a.frames)
    render.render(fig, draw, ts, a.out, NAME, a.fps, poster_t=1.0)


if __name__ == "__main__":
    main()
