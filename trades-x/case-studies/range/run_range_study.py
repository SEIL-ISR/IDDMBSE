# TRADES-X over the test range: the range configuration as the design under trade.
#
#   uv run python case-studies/range/run_range_study.py
#
# Model-based stage: tradesx/range_model.py scores every point of the DOE grid
# isaacsim/tools/range_doe.py can build (obstacle coverage x slope target x
# friction pair x restitution) for contestedness and predicted traversability,
# the model-based requirements in requirements.yaml prune the grid, and the
# Pareto filter keeps the non-dominated configurations.
#
# Data-driven stage: the eight trials PERFECT ran on the range
# (isaacsim/results/campaign.csv) are checked against the data-driven
# requirements and the eight configurations are ranked by MAVF, first on the
# model's two scores alone and then with the measured attributes added.
#
# Then the sensitivity of the frontier, and the next campaign: the frontier
# points no trial has covered, as a range_campaign.py command line.

import csv
import importlib.util
import json
import os
import pathlib

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tradesx import ddo_api
from tradesx import range_model as rm
from tradesx import requirements as reqs
from tradesx.pareto import non_dominated

here = pathlib.Path(__file__).resolve().parent
results = here / "results"
figures = here / "figures"
CAMPAIGN = here.parents[2] / "isaacsim" / "results" / "campaign.csv"

DENSITIES = np.round(np.arange(1, 19) * 0.05, 2)
SLOPES = np.arange(5.0, 35.01, 2.5)
FRICTION_STATIC = np.round(np.arange(3, 11) / 10, 1)
FRICTION_DYNAMIC = np.round(FRICTION_STATIC - 0.1, 1)
RESTITUTIONS = np.array([0.0, 0.1, 0.3])

ATTRIBUTES = ["rocks_per_m2", "encounters_per_m", "p_encounter", "mean_free_path_m",
              "progress_fraction", "grade_mean_deg", "grade_p90_deg", "no_slip_margin",
              "slip_share", "relief", "attitude", "contestedness", "traversability"]

MBO_METRICS = ["contestedness", "traversability"]
MBO_SENSE = [1, 1]
DDO_METRICS = ["distance_m", "obstacle_encounters", "mean_pitch_deg", "max_roll_deg",
               "stuck", "unstable"]
DDO_SENSE = [1, 1, 1, -1, -1, -1]
NEXT_SIZE = 8
SEED = 7

plt.rcParams["svg.hashsalt"] = "range-study"


def fmt(v):
    # plain Python numbers rounded to six places, so two runs write the same bytes
    if isinstance(v, (bool, np.bool_)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return repr(round(float(v), 6))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return v


def write_csv(path, columns, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow([fmt(v) for v in r])


def check(values, bound):
    """Apply a requirements.yaml bound string to an array."""
    b = bound.split()
    if b[0] == "<=":
        return values <= float(b[1])
    if b[0] == ">=":
        return values >= float(b[1])
    if b[0] == "==":
        return values == float(b[1])
    return (values >= float(b[0]) - 1e-9) & (values <= float(b[2]) + 1e-9)


# ------------------------------------------------------------------
# model-based stage

def grid():
    """Every DOE point as flat arrays, density slowest, restitution fastest."""
    i = np.arange(len(FRICTION_STATIC))
    d, s, f, e = np.meshgrid(DENSITIES, SLOPES, i, RESTITUTIONS, indexing="ij")
    f = f.ravel()
    return {"obstacle_density": d.ravel(), "max_slope_deg": s.ravel(),
            "friction_static": FRICTION_STATIC[f], "friction_dynamic": FRICTION_DYNAMIC[f],
            "restitution": e.ravel()}


def evaluate(knobs, ctx):
    k = rm.height_scale(knobs["max_slope_deg"], ctx["g99"])
    a = rm.attributes(knobs["obstacle_density"], k, knobs["friction_static"],
                      knobs["friction_dynamic"], knobs["restitution"],
                      ctx["cells"], ctx["cells_p90"])
    a["height_scale"] = k
    return a


def model_based(model_reqs, knobs, attrs, thresholds=None):
    """Requirement flags, the feasible set and the frontier over it.

    `thresholds` overrides a requirement's bound string by id, which is how the
    sensitivity stage moves one threshold at a time.
    """
    thresholds = thresholds or {}
    values = dict(knobs)
    values.update(attrs)
    flags = {}
    for r in model_reqs:
        flags[r["id"]] = check(values[r["attribute"]], thresholds.get(r["id"], r["bound"]))
    feasible = np.logical_and.reduce(list(flags.values()))
    idx = np.flatnonzero(feasible)
    m = np.column_stack([attrs[n][idx] for n in MBO_METRICS])
    _, keep = non_dominated(m, MBO_SENSE)
    frontier = idx[keep]
    frontier = frontier[np.argsort(attrs["contestedness"][frontier], kind="stable")]
    return flags, feasible, frontier


def write_grid(knobs, attrs, flags, feasible, frontier, model_reqs):
    on = np.zeros(len(feasible), dtype=bool)
    on[frontier] = True
    columns = (rm.KNOBS + ["height_scale"] + ATTRIBUTES
               + [r["id"] for r in model_reqs] + ["feasible", "on_frontier"])
    table = ([knobs[n] for n in rm.KNOBS] + [attrs["height_scale"]]
             + [attrs[n] for n in ATTRIBUTES] + [flags[r["id"]] for r in model_reqs]
             + [feasible, on])
    rows = list(zip(*table))
    write_csv(results / "mbo_grid.csv", columns, rows)
    write_csv(results / "mbo_frontier.csv", columns, [rows[i] for i in frontier])


# ------------------------------------------------------------------
# data-driven stage

def read_campaign():
    with open(CAMPAIGN, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["stuck"] = 1.0 if r["stuck"] == "True" else 0.0
        r["unstable"] = 1.0 if r["unstable"] == "True" else 0.0
    return rows


def config_name(r):
    slope = r["max_slope_deg"]
    slope = "authored" if slope == "authored" else "s" + str(float(slope))
    return "d" + r["obstacle_density"] + " " + slope + " f" + r["friction_static"] \
        + "/" + r["friction_dynamic"] + " e" + r["restitution"]


def trial_knobs(rows, ctx):
    """The measured configurations as model inputs.

    `authored` is not a slope target: range_doe.py writes no height scale for
    it, so the terrain keeps k = 1. Its knob row carries the 99th-percentile
    slope the trial measured, which is the target that would give k = 1.
    """
    col = lambda name: np.array([r[name] for r in rows])
    target = col("max_slope_deg")
    authored = target == "authored"
    slope = np.where(authored, col("slope_deg_after_p99"), target)
    knobs = {"obstacle_density": col("obstacle_density").astype(float),
             "max_slope_deg": slope.astype(float),
             "friction_static": col("friction_static").astype(float),
             "friction_dynamic": col("friction_dynamic").astype(float),
             "restitution": col("restitution").astype(float)}
    k = np.where(authored, 1.0, rm.height_scale(knobs["max_slope_deg"], ctx["g99"]))
    attrs = rm.attributes(knobs["obstacle_density"], k, knobs["friction_static"],
                          knobs["friction_dynamic"], knobs["restitution"],
                          ctx["cells"], ctx["cells_p90"])
    attrs["height_scale"] = k
    return knobs, attrs, authored


def data_driven(rows, names, data_reqs):
    for r, n in zip(rows, names):
        r["environment"] = n
    table = ddo_api.metric_table(rows, ["Carter v2.4"], names,
                                 sorted(set(DDO_METRICS + [r["attribute"] for r in data_reqs])))
    columns = sorted(set(DDO_METRICS + [r["attribute"] for r in data_reqs]))
    measured = {c: table[0, :, j] for j, c in enumerate(columns)}
    flags = {r["id"]: check(measured[r["attribute"]], r["bound"]) for r in data_reqs}
    return measured, flags


def rank(model_attrs, measured, all_reqs):
    mbo = np.column_stack([model_attrs[n] for n in MBO_METRICS])
    ddo = np.column_stack([measured[n] for n in DDO_METRICS])
    order, scores, mbo_order, mbo_scores = ddo_api.rank_designs(
        mbo, ddo, MBO_SENSE, DDO_SENSE, reqs=all_reqs)
    place = np.empty(len(scores), dtype=int)
    place[order] = np.arange(1, len(scores) + 1)
    mbo_place = np.empty(len(scores), dtype=int)
    mbo_place[mbo_order] = np.arange(1, len(scores) + 1)
    return order, scores, place, mbo_scores, mbo_place


# ------------------------------------------------------------------
# sensitivity

def sensitivity(knobs, frontier, ctx, model_reqs, attrs, base_frontier):
    points = np.column_stack([knobs[n][frontier] for n in rm.KNOBS])
    fc, ft = rm.relative_sensitivities_fd(points, ctx)
    if importlib.util.find_spec("jax") is None:
        # without the `ad` extra the central differences stand in
        dc, dt, gap = fc, ft, None
    else:
        dc, dt = rm.relative_sensitivities(points, ctx)
        gap = float(max(np.abs(dc - fc).max(), np.abs(dt - ft).max()))
    requirement_of = {"obstacle_density": "RR.2", "max_slope_deg": "RR.1",
                      "friction_static": "RR.3", "friction_dynamic": "",
                      "restitution": ""}
    rows = []
    for j, n in enumerate(rm.KNOBS):
        rows.append(["knob", n, requirement_of[n], np.abs(dc[:, j]).mean(),
                     np.abs(dt[:, j]).mean(), "", ""])

    # each model-based threshold moved by 10 % either way, the frontier recomputed
    base = set(base_frontier.tolist())
    for r in model_reqs:
        parts = r["bound"].split()
        ends = [(0, parts[0])] if parts[1] == ".." else [(1, parts[1])]
        if parts[1] == "..":
            ends.append((2, parts[2]))
        for pos, value in ends:
            change = []
            for factor in (0.9, 1.1):
                moved = list(parts)
                v = float(value)
                moved[pos] = repr(round(v * factor if v != 0 else (factor - 1.0), 6))
                _, _, f = model_based(model_reqs, knobs, attrs, {r["id"]: " ".join(moved)})
                new = set(f.tolist())
                change.append(len(base ^ new) / len(base | new))
            label = r["id"] + (" lower" if pos == 0 else " upper" if pos == 2 else "")
            rows.append(["requirement", label + " (" + r["bound"] + ")", r["id"], "", "",
                         change[0], change[1]])
    write_csv(results / "sensitivity.csv",
              ["kind", "name", "requirement", "mean_abs_rel_dC", "mean_abs_rel_dT",
               "frontier_change_minus10", "frontier_change_plus10"], rows)
    return rows, gap


# ------------------------------------------------------------------
# the next campaign

def next_campaign(knobs, attrs, frontier, trial):
    # covered: a trial ran the same coverage, slope target and friction pair.
    # Restitution is left out of the match; the model moves it only through
    # the millimetres of slide-back after a rebound.
    f = np.column_stack([knobs[n][frontier] for n in rm.KNOBS[:4]])
    t = np.column_stack([trial[n] for n in rm.KNOBS[:4]])
    covered = (np.abs(f[:, None, :] - t[None, :, :]) < 1e-9).all(-1).any(-1)
    open_points = frontier[~covered]
    # Configurations that differ only in a friction the start area never needs
    # score the same. One per distinct score pair, the lowest static friction
    # of the tie, so the campaign also moves the friction knob; then NEXT_SIZE
    # of those, evenly spaced along the frontier.
    pairs = np.round(np.column_stack([attrs["contestedness"][open_points],
                                      attrs["traversability"][open_points]]), 9)
    by_friction = np.lexsort((knobs["friction_static"][open_points], pairs[:, 1], pairs[:, 0]))
    _, first = np.unique(pairs[by_friction], axis=0, return_index=True)
    distinct = open_points[by_friction[first]]
    distinct = distinct[np.argsort(attrs["contestedness"][distinct], kind="stable")]
    pick = np.unique(np.round(np.linspace(0, len(distinct) - 1, NEXT_SIZE)).astype(int))
    chosen = distinct[pick]
    points = [{"obstacle_density": float(knobs["obstacle_density"][i]),
               "max_slope_deg": float(knobs["max_slope_deg"][i]),
               "friction_static": float(knobs["friction_static"][i]),
               "friction_dynamic": float(knobs["friction_dynamic"][i]),
               "restitution": float(knobs["restitution"][i]),
               "seed": SEED, "duration_s": 30.0} for i in chosen]
    (results / "next_campaign_points.json").write_text(json.dumps(points, indent=2) + "\n")
    first = points[0]
    command = ("cd isaacsim/tools\n"
               "python range_campaign.py --submit "
               "--project-root ../../perfect/examples/isaacsim-range \\\n"
               "    --densities " + str(first["obstacle_density"])
               + " --slopes " + str(first["max_slope_deg"])
               + " --frictions " + str(first["friction_static"]) + "/"
               + str(first["friction_dynamic"])
               + " --restitutions " + str(first["restitution"])
               + " --seeds " + str(SEED) + " --duration 30 \\\n"
               "    --robots \"Carter v2.4\" --tag range-next \\\n"
               "    --extra ../../trades-x/case-studies/range/results/next_campaign_points.json\n")
    (results / "next_campaign.txt").write_text(command)
    return open_points, distinct, chosen, points, command


# ------------------------------------------------------------------
# figures

def save(fig, stem):
    fig.tight_layout()
    fig.savefig(figures / (stem + ".svg"), metadata={"Date": None})
    fig.savefig(figures / (stem + ".pdf"), metadata={"CreationDate": None})
    plt.close(fig)


def draw_grid(knobs, attrs, feasible, frontier, trial, trial_attrs, authored, next_idx):
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0))

    # left: density x slope at the recorded friction and restitution
    ax = axes[0]
    at = ((knobs["friction_static"] == 0.6) & (knobs["friction_dynamic"] == 0.5)
          & (knobs["restitution"] == 0.1))
    c = attrs["contestedness"][at].reshape(len(DENSITIES), len(SLOPES))
    step_d, step_s = DENSITIES[1] - DENSITIES[0], SLOPES[1] - SLOPES[0]
    im = ax.imshow(c.T, origin="lower", aspect="auto", cmap="viridis",
                   extent=(DENSITIES[0] - step_d / 2, DENSITIES[-1] + step_d / 2,
                           SLOPES[0] - step_s / 2, SLOPES[-1] + step_s / 2))
    fig.colorbar(im, ax=ax, label="contestedness")
    infeasible = at & ~feasible
    ax.scatter(knobs["obstacle_density"][infeasible], knobs["max_slope_deg"][infeasible],
               marker="x", s=10, color="white", linewidth=0.6,
               label="fails a model-based requirement")
    on = np.zeros(len(feasible), dtype=bool)
    on[frontier] = True
    ax.scatter(knobs["obstacle_density"][on], knobs["max_slope_deg"][on], s=40,
               facecolor="none", edgecolor="tab:red", linewidth=1.4,
               label="frontier (any friction, restitution)")
    ax.scatter(trial["obstacle_density"][~authored], trial["max_slope_deg"][~authored],
               marker="*", s=150, color="white", edgecolor="black", linewidth=0.8,
               label="measured in the campaign")
    ax.set_xlabel("obstacle coverage (fraction of footprint)")
    ax.set_ylabel("99th-percentile slope target [deg]")
    ax.set_title("DOE grid at friction 0.6/0.5, restitution 0.1")
    # a grey box, so the white markers show in the legend
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=7,
              facecolor="0.55", edgecolor="0.55", framealpha=1.0)

    # right: the objective space
    ax = axes[1]
    ax.scatter(attrs["contestedness"][~feasible], attrs["traversability"][~feasible],
               s=3, color="0.85", label="fails a model-based requirement")
    ax.scatter(attrs["contestedness"][feasible], attrs["traversability"][feasible],
               s=3, color="0.55", label="feasible")
    ax.plot(attrs["contestedness"][frontier], attrs["traversability"][frontier], "-o",
            color="tab:red", markersize=3, linewidth=1.2, label="frontier")
    ax.scatter(attrs["contestedness"][next_idx], attrs["traversability"][next_idx],
               s=90, facecolor="none", edgecolor="tab:blue", linewidth=1.5,
               label="next campaign")
    ax.scatter(trial_attrs["contestedness"], trial_attrs["traversability"], marker="*",
               s=150, color="gold", edgecolor="black", linewidth=0.8,
               label="measured configurations")
    for i in range(len(trial_attrs["contestedness"])):
        ax.annotate(str(i + 1), (trial_attrs["contestedness"][i],
                                 trial_attrs["traversability"][i]),
                    xytext=(5, 4), textcoords="offset points", fontsize=8)
    ax.set_xlabel("contestedness")
    ax.set_ylabel("predicted traversability")
    ax.set_title("Model-based stage: " + str(len(feasible)) + " configurations")
    ax.legend(loc="upper right", fontsize=7, framealpha=0.85)
    save(fig, "mbo_grid_frontier")


def draw_ranking(names, scores, mbo_scores, order):
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    x = np.arange(len(names))
    ax.bar(x - 0.2, mbo_scores[order], width=0.4, color="0.6",
           label="model-based attributes alone")
    ax.bar(x + 0.2, scores[order], width=0.4, color="tab:red",
           label="model-based and measured attributes")
    ax.set_xticks(x)
    ax.set_xticklabels([names[k] for k in order], rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("MAVF score")
    ax.set_ylim(0.0, 1.15)
    ax.set_title("The eight measured range configurations, before and after the campaign")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    save(fig, "mavf_ranking")


def draw_sensitivity(rows):
    knob_rows = [r for r in rows if r[0] == "knob"]
    req_rows = [r for r in rows if r[0] == "requirement"]
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.4))
    ax = axes[0]
    x = np.arange(len(knob_rows))
    ax.bar(x - 0.2, [r[3] for r in knob_rows], width=0.4, color="tab:purple",
           label="contestedness")
    ax.bar(x + 0.2, [r[4] for r in knob_rows], width=0.4, color="tab:green",
           label="predicted traversability")
    ax.set_xticks(x)
    ax.set_xticklabels([r[1] for r in knob_rows], rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("mean |x d(score)/dx| over the frontier")
    ax.set_title("Knobs (JAX forward mode)")
    ax.legend(frameon=False, fontsize=8)
    ax = axes[1]
    x = np.arange(len(req_rows))
    ax.bar(x - 0.2, [r[5] for r in req_rows], width=0.4, color="0.5",
           label="threshold moved down 10 % (0.1 on a zero bound)")
    ax.bar(x + 0.2, [r[6] for r in req_rows], width=0.4, color="tab:orange",
           label="threshold moved up 10 % (0.1 on a zero bound)")
    ax.set_xticks(x)
    ax.set_xticklabels([r[1] for r in req_rows], rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("share of the frontier that changes")
    ax.set_ylim(0.0, 1.0)
    ax.set_title("Model-based requirements")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "sensitivity")


# ------------------------------------------------------------------

def main():
    results.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)
    all_reqs = reqs.load(here / "requirements.yaml")
    model_reqs, data_reqs = reqs.partition(all_reqs)
    ctx = rm.context()
    print("heightmap: g99", round(ctx["g99"], 6), "start-area cells", len(ctx["cells"]),
          "cell p90 gradient", round(ctx["cells_p90"], 6))
    print("model-based requirements:", [r["id"] for r in model_reqs],
          "data-driven:", [r["id"] for r in data_reqs])

    # model-based stage
    knobs = grid()
    attrs = evaluate(knobs, ctx)
    flags, feasible, frontier = model_based(model_reqs, knobs, attrs)
    write_grid(knobs, attrs, flags, feasible, frontier, model_reqs)
    print()
    print("DOE grid:", len(feasible), "configurations;",
          ", ".join(r["id"] + " passes " + str(int(flags[r["id"]].sum())) for r in model_reqs))
    pairs = np.unique(np.round(np.column_stack([attrs[n][frontier] for n in MBO_METRICS]), 9),
                      axis=0)
    print("feasible:", int(feasible.sum()), " frontier:", len(frontier),
          "configurations,", len(pairs), "distinct score pairs")
    print()
    print("frontier (contestedness ascending)")
    print("density slope  mu_s/mu_d  e    C      T      p_enc  mfp[m] grade90 margin slip")
    for i in frontier:
        print(str(knobs["obstacle_density"][i]).ljust(7),
              str(knobs["max_slope_deg"][i]).ljust(6),
              (str(knobs["friction_static"][i]) + "/" + str(knobs["friction_dynamic"][i])).ljust(10),
              str(knobs["restitution"][i]).ljust(4),
              str(round(float(attrs["contestedness"][i]), 4)).ljust(6),
              str(round(float(attrs["traversability"][i]), 4)).ljust(6),
              str(round(float(attrs["p_encounter"][i]), 3)).ljust(6),
              str(round(float(attrs["mean_free_path_m"][i]), 2)).ljust(6),
              str(round(float(attrs["grade_p90_deg"][i]), 2)).ljust(7),
              str(round(float(attrs["no_slip_margin"][i]), 3)).ljust(6),
              round(float(attrs["slip_share"][i]), 4))

    # data-driven stage
    rows = read_campaign()
    names = [config_name(r) for r in rows]
    tk, ta, authored = trial_knobs(rows, ctx)
    tflags = {r["id"]: check(dict(tk, **ta)[r["attribute"]], r["bound"]) for r in model_reqs}
    measured, dflags = data_driven(rows, names, data_reqs)
    order, scores, place, mbo_scores, mbo_place = rank(ta, measured, all_reqs)

    write_csv(results / "ddo_metrics.csv",
              ["trial_id", "configuration", "height_scale"] + DDO_METRICS
              + [r["attribute"] for r in data_reqs if r["attribute"] not in DDO_METRICS]
              + [r["id"] for r in data_reqs] + ["model_" + n for n in MBO_METRICS]
              + [r["id"] for r in model_reqs],
              [[rows[i]["trial_id"], names[i], ta["height_scale"][i]]
               + [measured[n][i] for n in DDO_METRICS]
               + [measured[r["attribute"]][i] for r in data_reqs
                  if r["attribute"] not in DDO_METRICS]
               + [dflags[r["id"]][i] for r in data_reqs]
               + [ta[n][i] for n in MBO_METRICS]
               + [tflags[r["id"]][i] for r in model_reqs] for i in range(len(rows))])
    write_csv(results / "mavf_ranking.csv",
              ["configuration", "trial_id", "mavf_rank", "mavf_score", "mbo_only_rank",
               "mbo_only_score"] + MBO_METRICS + DDO_METRICS,
              [[names[k], rows[k]["trial_id"], place[k], scores[k], mbo_place[k],
                mbo_scores[k]] + [ta[n][k] for n in MBO_METRICS]
               + [measured[n][k] for n in DDO_METRICS] for k in order])

    w_mbo, w_ddo = ddo_api.class_weights(all_reqs)
    print()
    print("campaign:", len(rows), "trials from", CAMPAIGN.name,
          " class weights model-based", round(w_mbo, 4), "data-driven", round(w_ddo, 4))
    print("requirements per trial (1 = met)")
    print("trial configuration                 " + " ".join(r["id"] for r in all_reqs))
    for i in range(len(rows)):
        print(rows[i]["trial_id"].ljust(5), names[i].ljust(30),
              "  ".join(str(int(flags_i)).rjust(3) for flags_i in
                        [tflags[r["id"]][i] for r in model_reqs]
                        + [dflags[r["id"]][i] for r in data_reqs]))
    print()
    print("rank configuration                 mavf    mbo-only  C      T      dist[m] enc pitch roll")
    for k in order:
        print(str(place[k]).rjust(4), names[k].ljust(30),
              str(round(float(scores[k]), 4)).ljust(7),
              str(mbo_place[k]).rjust(3), str(round(float(mbo_scores[k]), 4)).ljust(6),
              str(round(float(ta["contestedness"][k]), 3)).ljust(6),
              str(round(float(ta["traversability"][k]), 3)).ljust(6),
              str(round(float(measured["distance_m"][k]), 2)).ljust(7),
              str(int(measured["obstacle_encounters"][k])).ljust(3),
              str(round(float(measured["mean_pitch_deg"][k]), 1)).ljust(5),
              round(float(measured["max_roll_deg"][k]), 1))

    # sensitivity
    srows, gap = sensitivity(knobs, frontier, ctx, model_reqs, attrs, frontier)
    print()
    print("sensitivity over the", len(frontier), "frontier points; JAX against central "
          "differences, largest gap", gap)
    for r in srows:
        if r[0] == "knob":
            print("  knob", r[1].ljust(17), "req", (r[2] or "-").ljust(5),
                  "dC", round(float(r[3]), 5), " dT", round(float(r[4]), 5))
        else:
            print("  requirement", r[1].ljust(26), "frontier change -10%",
                  round(float(r[5]), 4), " +10%", round(float(r[6]), 4))

    # next campaign
    open_points, distinct, chosen, points, command = next_campaign(knobs, attrs, frontier, tk)
    print()
    print("frontier points no trial covers:", len(open_points), " distinct score pairs:",
          len(distinct), " next campaign:", len(chosen))
    print(command, end="")

    draw_grid(knobs, attrs, feasible, frontier, tk, ta, authored, chosen)
    draw_ranking(names, scores, mbo_scores, order)
    draw_sensitivity(srows)
    print()
    print("results written to", os.path.relpath(results, here.parents[1]))
    print("figures written to", os.path.relpath(figures, here.parents[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
