"""Case study B2, end to end.

Calibrate conformal box inflation on a PERFECT-shaped campaign, check coverage
on held-out episodes, run the closed loop with and without the inflation, sweep
the coverage level as a TRADES-X design variable, and write the figures and the
results table.
"""

import json
import pathlib
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from cpnav import campaign, conformal, detector, planner, tradeoff, world

SEED = 20260922
N_CAMPAIGN = 90          # episodes in the campaign
N_CALIBRATION = 60       # of those, the ones used to calibrate
FRAME_EVERY = 4          # keep one frame in three, to hold the table down
K_TEST = 200             # test episodes per arm
N_FIGURE = 24            # episodes re-run with recording, for the trajectory figure
ALPHA = 0.10
ALPHAS = [0.30, 0.20, 0.15, 0.10, 0.05, 0.02, 0.01]

HERE = pathlib.Path(__file__).parent
FIGURES = HERE / "figures"
RESULTS = HERE / "results"

t_start = time.time()
FIGURES.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)
rng = np.random.default_rng(SEED)

# ------------------------------------------------------------------
# campaign: the labelled closed-loop data PERFECT would produce

rows, _ = campaign.run_campaign(rng, N_CAMPAIGN, every=FRAME_EVERY)
campaign.write_rows(RESULTS / "campaign.csv", rows)
cal_rows, hold_rows = campaign.split_by_episode(rows, N_CALIBRATION)
cal_true, cal_det = campaign.boxes_from_rows(cal_rows)
hold_true, hold_det = campaign.boxes_from_rows(hold_rows)
cal_scores = conformal.scores(cal_det, cal_true)

print("campaign episodes", N_CAMPAIGN, "detection rows", rows.shape[0])
print("calibration rows", cal_scores.size, "held-out rows", hold_rows.shape[0])
print("score median", round(float(np.median(cal_scores)), 3),
      "mean", round(float(cal_scores.mean()), 3),
      "max", round(float(cal_scores.max()), 3))

# ------------------------------------------------------------------
# calibrate and check coverage

qs = [conformal.quantile(cal_scores, a) for a in ALPHAS]
q_main = conformal.quantile(cal_scores, ALPHA)
hold_cov = [conformal.coverage(hold_det, hold_true, q) for q in qs]
boot_rng = np.random.default_rng(SEED + 2)
hold_ci = [
    conformal.bootstrap_coverage(hold_det, hold_true, q, hold_rows[:, 0], boot_rng)
    for q in qs
]
cov_main = conformal.coverage(hold_det, hold_true, q_main)
ci_main = hold_ci[ALPHAS.index(ALPHA)]

print()
print("alpha  target   q (m)   held-out coverage   90% episode-bootstrap interval")
for a, q, c, (lo, hi) in zip(ALPHAS, qs, hold_cov, hold_ci):
    print(" ", a, "  ", round(1 - a, 3), "  ", round(q, 3), "  ", round(c, 4),
          "  ", round(lo, 4), round(hi, 4))

# ------------------------------------------------------------------
# closed loop: nominal against conformal, and the alpha sweep

test_boxes, test_valid, test_hard = campaign.feasible_worlds(rng, K_TEST)
arm_q = [0.0] + qs
table, raw = tradeoff.sweep(rng, test_boxes, test_valid, test_hard, arm_q)
nominal = table[0]
conformalized = table[1 + ALPHAS.index(ALPHA)]

print()
print("closed loop over", K_TEST, "test episodes")
print("arm          q (m)  collisions  success  stalls  mean path (m)  mean waits")
labels = ["nominal"] + ["alpha=" + str(a) for a in ALPHAS]
for lab, r in zip(labels, table):
    print(" ", lab.ljust(11),
          round(r["q"], 3),
          int(round(r["collision_rate"] * K_TEST)),
          "   ", round(r["success_rate"], 3),
          "  ", int(round(r["stall_rate"] * K_TEST)),
          "   ", round(r["mean_path_length"], 2),
          "   ", round(r["mean_waits"], 2))

# ------------------------------------------------------------------
# a recorded pair of episodes for the trajectory figure

fig_boxes = test_boxes[:N_FIGURE]
fig_valid = test_valid[:N_FIGURE]
fig_hard = test_hard[:N_FIGURE]
pair_rng = np.random.default_rng(SEED + 1)
pair = planner.run_episodes(
    pair_rng,
    np.tile(fig_boxes, (2, 1, 1)),
    np.tile(fig_valid, (2, 1)),
    np.tile(fig_hard, (2, 1)),
    q=np.repeat([0.0, q_main], N_FIGURE),
    record=True,
)
pair_status = pair["status"].reshape(2, N_FIGURE)
picked = np.nonzero(
    (pair_status[0] == planner.COLLISION) & (pair_status[1] == planner.SUCCESS)
)[0]
episode = int(picked[0]) if picked.size else 0

# realised coverage of the conformal arm, on the states its own planner visits
cp_rows = pair["rows"][pair["rows"][:, 0] >= N_FIGURE]
cp_true, cp_det = campaign.boxes_from_rows(cp_rows)
cov_closed_loop = conformal.coverage(cp_det, cp_true, q_main)
print()
print("held-out coverage at alpha", ALPHA, round(cov_main, 4),
      "| realised in the conformal closed loop", round(cov_closed_loop, 4))
print("figure episode", episode,
      "nominal", int(pair_status[0][episode]), "conformal", int(pair_status[1][episode]))


def draw_boxes(ax, boxes, valid, **kw):
    lo = boxes[valid]
    for b in lo:
        ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], **kw))


frame = min(int(pair["steps"][episode]), len(pair["frames"]) - 1)
det_f, inf_f, dv_f = pair["frames"][frame]

fig, axes = plt.subplots(1, 2, figsize=(10.5, 5.2), sharey=True)
for ax, arm, title in zip(axes, [0, 1], ["without conformalized detections",
                                         "with conformalized detections"]):
    idx = arm * N_FIGURE + episode
    draw_boxes(ax, fig_boxes[episode], fig_valid[episode],
               facecolor="0.72", edgecolor="0.25", lw=1.0, zorder=1)
    draw_boxes(ax, det_f[idx], dv_f[idx],
               facecolor="none", edgecolor="darkorange", lw=1.2, ls="--", zorder=3)
    if arm == 1:
        draw_boxes(ax, inf_f[idx], dv_f[idx],
                   facecolor="none", edgecolor="purple", lw=1.2, ls=":", zorder=3)
    t = pair["traj"][idx][: int(pair["steps"][idx]) + 1]
    ax.plot(t[:, 0], t[:, 1], color="tab:blue", lw=1.8, zorder=4)
    ax.plot(*world.START_XY, "o", color="green", ms=7, zorder=5)
    ax.plot(*world.GOAL_XY, "*", color="crimson", ms=13, zorder=5)
    if pair["status"][idx] == planner.COLLISION:
        ax.plot(t[-1, 0], t[-1, 1], "X", color="red", ms=11, zorder=6)
    ax.set_xlim(0, world.SIZE)
    ax.set_ylim(0, world.SIZE)
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.set_xlabel("x (m)")
axes[0].set_ylabel("y (m)")
handles = [
    Rectangle((0, 0), 1, 1, facecolor="0.72", edgecolor="0.25", label="true obstacle"),
    Rectangle((0, 0), 1, 1, facecolor="none", edgecolor="darkorange", ls="--", label="detection"),
    Rectangle((0, 0), 1, 1, facecolor="none", edgecolor="purple", ls=":", label="conformal region"),
    plt.Line2D([], [], color="tab:blue", lw=1.8, label="realized trajectory"),
    plt.Line2D([], [], color="red", marker="X", ls="none", label="collision"),
]
axes[1].legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.9)
fig.suptitle("Robust perception via conformal prediction, alpha = " + str(ALPHA)
             + ", q = " + str(round(q_main, 2)) + " m"
             + "\nboxes are one frame, at step " + str(frame)
             + "; the trajectory is the whole episode", fontsize=11)
fig.tight_layout()
fig.savefig(FIGURES / "trajectories.svg")
fig.savefig(FIGURES / "trajectories.pdf")
plt.close(fig)

# ------------------------------------------------------------------
# the trade-off figure

target = 1 - np.array(ALPHAS)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.4))
ax1.plot([target.min(), 1.0], [target.min(), 1.0], color="0.6", lw=1, ls="--",
         label="target 1 - alpha")
err = np.array([[c - lo, hi - c] for c, (lo, hi) in zip(hold_cov, hold_ci)]).T
ax1.errorbar(target, hold_cov, yerr=err, fmt="o-", color="tab:blue", capsize=3,
             label="held-out coverage, 90% episode bootstrap")
ax1.plot(target, [conformal.coverage(cp_det, cp_true, q) for q in qs], "s--",
         color="tab:red",
         label="on the closed-loop states of the alpha = " + str(ALPHA) + " policy")
ax1.set_xlabel("target coverage 1 - alpha")
ax1.set_ylabel("empirical coverage")
ax1.legend(fontsize=8)

coll = [r["collision_rate"] for r in table[1:]]
plen = [r["mean_path_length"] for r in table[1:]]
ax2.plot(target, coll, "o-", color="tab:red", label="collision rate")
ax2.axhline(nominal["collision_rate"], color="tab:red", lw=1, ls=":",
            label="collision rate, nominal")
ax2.set_xlabel("target coverage 1 - alpha")
ax2.set_ylabel("collision rate over " + str(K_TEST) + " episodes")
ax2.set_ylim(0, max(coll + [nominal["collision_rate"]]) * 1.15)
ax3 = ax2.twinx()
ax3.plot(target, plen, "s--", color="tab:green", label="mean path length")
ax3.axhline(nominal["mean_path_length"], color="tab:green", lw=1, ls=":",
            label="mean path length, nominal")
ax3.set_ylabel("mean path length (m)")
lines = ax2.get_lines() + ax3.get_lines()
ax2.legend(lines, [l.get_label() for l in lines], fontsize=8, loc="center right")
fig.suptitle("Coverage bought against navigation conservativeness")
fig.tight_layout()
fig.savefig(FIGURES / "tradeoff.svg")
fig.savefig(FIGURES / "tradeoff.pdf")
plt.close(fig)

# ------------------------------------------------------------------
# results

sweep_csv = np.column_stack(
    [
        np.array(ALPHAS),
        target,
        np.array(qs),
        np.array(hold_cov),
        np.array([lo for lo, _ in hold_ci]),
        np.array([hi for _, hi in hold_ci]),
        np.array([r["collision_rate"] for r in table[1:]]),
        np.array([r["success_rate"] for r in table[1:]]),
        np.array([r["stall_rate"] for r in table[1:]]),
        np.array([r["mean_path_length"] for r in table[1:]]),
        np.array([r["mean_waits"] for r in table[1:]]),
    ]
)
np.savetxt(
    RESULTS / "alpha_sweep.csv", sweep_csv, delimiter=",", fmt="%.6f", comments="",
    header="alpha,target_coverage,q,holdout_coverage,holdout_coverage_lo,"
           "holdout_coverage_hi,collision_rate,success_rate,"
           "stall_rate,mean_path_length,mean_waits",
)

summary = {
    "seed": SEED,
    "campaign": {
        "episodes": N_CAMPAIGN,
        "calibration_episodes": N_CALIBRATION,
        "frame_every": FRAME_EVERY,
        "detection_rows": int(rows.shape[0]),
        "calibration_rows": int(cal_scores.size),
        "holdout_rows": int(hold_rows.shape[0]),
        "score_median": float(np.median(cal_scores)),
        "score_mean": float(cal_scores.mean()),
        "score_max": float(cal_scores.max()),
    },
    "detector": {
        "sigma0": detector.SIGMA0,
        "sigma_range": detector.SIGMA_RANGE,
        "mu_easy": detector.MU_EASY,
        "sd_easy": detector.SD_EASY,
        "mu_hard": detector.MU_HARD,
        "sd_hard": detector.SD_HARD,
        "p_hard": world.P_HARD,
        "max_range": detector.MAX_RANGE,
    },
    "world": {
        "size_m": world.SIZE,
        "grid_resolution_m": world.RES,
        "robot_half_side_m": world.ROBOT_HALF,
        "obstacles_per_world": [world.MIN_OBSTACLES, world.MAX_OBSTACLES],
    },
    "operating_point": {
        "alpha": ALPHA,
        "q_m": q_main,
        "holdout_coverage": cov_main,
        "holdout_coverage_interval": ci_main,
        "closed_loop_coverage": cov_closed_loop,
    },
    "test_episodes": K_TEST,
    "nominal": nominal,
    "conformalized": conformalized,
    "sweep": [
        dict(r, alpha=a, target_coverage=float(1 - a), holdout_coverage=c,
             holdout_coverage_lo=lo, holdout_coverage_hi=hi)
        for a, c, (lo, hi), r in zip(ALPHAS, hold_cov, hold_ci, table[1:])
    ],
    "figure_episode": episode,
}
# the runtime is printed but kept out of the file, so that two runs of this
# script produce byte-identical results/ files
(RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

print()
print("collisions nominal", int(round(nominal["collision_rate"] * K_TEST)),
      "-> conformal", int(round(conformalized["collision_rate"] * K_TEST)),
      "of", K_TEST, "episodes")
print("mean path length nominal", round(nominal["mean_path_length"], 2),
      "-> conformal", round(conformalized["mean_path_length"], 2), "m")
print("runtime", round(time.time() - t_start, 1), "s")
