# Sensor-suite case study (Damera, Kumar, Baras, ISSE 2024).
# Reproduces the recorded model-based optimization stage from plot4met.csv and
# ranks the surviving designs with the MAVF.

import pathlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tradesx.pareto import non_dominated, non_dominated_matlab_compat
from tradesx.mavf import rank

here = pathlib.Path(__file__).parent
data = here / "data"
figures = here / "figures"
figures.mkdir(exist_ok=True)

# ------------------------------------------------------------------
# recorded data
# columns of plot4met.csv are cost, RAM, power, -coverage; coverage is stored
# negated by mbo.jl, so all four columns are minimised
labels = ["cost [$]", "RAM [MB]", "power [W]", "-coverage [m^3]"]
sense = [-1, -1, -1, -1]

m = np.loadtxt(data / "plot4met.csv", delimiter=",")
rec_idx = np.loadtxt(data / "pareto_designs.csv", delimiter=",").astype(int)
rec_evals = np.loadtxt(data / "pareto_design_evals.csv", delimiter=",")

print("designs evaluated:", m.shape[0])
print("recorded Pareto designs:", rec_idx.size)
print("duplicate metric rows in plot4met.csv:", m.shape[0] - len(np.unique(m, axis=0)))

# ------------------------------------------------------------------
# gate: the standard filter against the recorded MATLAB run
mask, idx = non_dominated(m, sense)
mask_c, idx_c = non_dominated_matlab_compat(m, sense)

# the recorded indices come from MATLAB and are 1-based
rec0 = np.sort(rec_idx - 1)
same_idx = np.array_equal(idx, rec0)
evals_gap = np.abs(m[idx] - rec_evals).max() if same_idx else float("nan")

print("standard non-dominated:", idx.size)
print("matlab-compat non-dominated:", idx_c.size)
print("standard == matlab-compat:", np.array_equal(idx, idx_c))
print("standard index set == recorded:", same_idx)
print("max abs metric difference vs recorded evals:", evals_gap)
print("GATE G2:", "pass" if same_idx and evals_gap < 1e-9 else "fail")

if not same_idx:
    only_mine = np.setdiff1d(idx, rec0)
    only_rec = np.setdiff1d(rec0, idx)
    print("indices only in my set (0-based):", only_mine)
    print("indices only in the recorded set (0-based):", only_rec)

# ------------------------------------------------------------------
# MAVF ranking of the Pareto set
# The only MAVF weighting recorded in the MATLAB workbench is
# weights=[0.5 0.5], optsign=[-1 -1] over the two global rosbag metrics
# (time to completion, path length). No weighting over the four local metrics
# was recorded, so equal weights are used here.
weights = [0.25, 0.25, 0.25, 0.25]
pareto = m[idx]
order, scores = rank(pareto, weights, sense)

print()
print("top 10 by MAVF (equal weights over the four local metrics)")
print("rank design_row cost ram power coverage mavf")
for r in range(10):
    k = order[r]
    row = pareto[k]
    print(r + 1, idx[k] + 1, round(row[0], 1), round(row[1], 1), round(row[2], 2),
          round(-row[3], 1), round(scores[k], 4))

# ------------------------------------------------------------------
# figures
fig, ax = plt.subplots(figsize=(6, 4.5))
ax.scatter(m[:, 0], -m[:, 3], s=3, color="0.75", label="all designs")
ax.scatter(pareto[:, 0], -pareto[:, 3], s=14, color="tab:red", label="Pareto set")
best = pareto[order[0]]
ax.scatter([best[0]], [-best[3]], s=70, facecolor="none", edgecolor="tab:blue",
           linewidth=1.5, label="MAVF best")
ax.set_xlabel("cost [$]")
ax.set_ylabel("effective coverage [m^3]")
ax.set_title("Sensor-suite design space, " + str(m.shape[0]) + " candidates")
ax.legend(loc="lower right", frameon=False)
fig.tight_layout()
fig.savefig(figures / "pareto_scatter.svg")
fig.savefig(figures / "pareto_scatter.pdf")

fig2, ax2 = plt.subplots(figsize=(6, 4.5))
top = order[:15]
ax2.bar(np.arange(top.size), scores[top], color="tab:red")
ax2.set_xticks(np.arange(top.size))
ax2.set_xticklabels([str(i + 1) for i in idx[top]], rotation=90, fontsize=8)
ax2.set_xlabel("design row in plot4met.csv (1-based)")
ax2.set_ylabel("MAVF score")
ax2.set_title("Top 15 Pareto designs by MAVF")
fig2.tight_layout()
fig2.savefig(figures / "mavf_ranking.svg")
fig2.savefig(figures / "mavf_ranking.pdf")

print()
print("figures written to", figures)
