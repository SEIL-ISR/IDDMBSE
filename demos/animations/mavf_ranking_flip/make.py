# The sensor-suite designs ranked by MAVF: first on the catalogue attributes alone,
# then re-ranked as PERFECT's 180 trials arrive in campaign order.
#
# The joint MAVF is the one trades-x/tradesx/ddo_api.rank_designs computes: min-max
# value functions over the ten designs, the model-based attributes (price, power, RAM)
# weighted 7/23 and the six measured ones 16/23, as the requirement partition splits
# them. While the campaign is running, a design's measured attributes are the mean of
# the trials it has so far, the value functions span the designs measured so far, and a
# design with no trial yet scores zero on the measured attributes. Before the first
# trial the joint score is therefore 7/23 of the catalogue-only score, in the same
# order; after the last one it is the recorded mavf_ddo_ranking.csv score.

import csv
import sys
import pathlib
import warnings

import numpy as np
import matplotlib.pyplot as plt
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render  # noqa: E402

NAME = "mavf_ranking_flip"
CASE = render.ROOT / "trades-x" / "case-studies" / "sensor-suite"
CAMPAIGN = CASE / "results" / "ddo_campaign.csv"
RANKING = CASE / "results" / "mavf_ddo_ranking.csv"
REQUIREMENTS = CASE / "requirements.yaml"

MBO = ["cost", "power", "ram"]
MBO_SENSE = np.array([-1.0, -1.0, -1.0])
DDO = ["success_rate", "collision_rate", "time_to_goal", "tortuosity",
       "detection_distance", "battery_soc"]
DDO_SENSE = np.array([1.0, -1.0, -1.0, -1.0, 1.0, 1.0])

INTRO, TRIALS, OUTRO = 2.5, 15.0, 3.5


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def savf(x, sense, axis):
    """Min-max value functions along `axis`, 1 = best, NaN-aware, flat columns = 1."""
    lo = np.nanmin(x, axis=axis, keepdims=True)
    hi = np.nanmax(x, axis=axis, keepdims=True)
    span = hi - lo
    flat = span == 0
    safe = np.where(flat, 1.0, span)
    v = np.where(sense > 0, (x - lo) / safe, (hi - x) / safe)
    return np.where(flat, 1.0, v)


def load():
    ranking = read_csv(RANKING)
    names = [r["design"] for r in ranking]
    trials = sorted(read_csv(CAMPAIGN), key=lambda r: int(r["experiment_id"]))
    reqs = yaml.safe_load(open(REQUIREMENTS))
    n_mbo_req = sum(r["class"] == "model-based" for r in reqs)
    n_ddo_req = sum(r["class"] == "data-driven" for r in reqs)

    design = np.array([names.index(r["design"]) for r in trials])
    values = np.array([[float(r[m]) for m in DDO] for r in trials])
    env_names = sorted({r["environment"] for r in trials})
    env = np.array([env_names.index(r["environment"]) for r in trials])
    catalogue = np.array([[float(r[m]) for m in MBO] for r in ranking])
    return {
        "names": names,
        "ranking": ranking,
        "design": design,
        "env": env,
        "env_names": env_names,
        "values": values,
        "success": values[:, 0],
        "catalogue": catalogue,
        "w_mbo": n_mbo_req / (n_mbo_req + n_ddo_req),
        "w_ddo": n_ddo_req / (n_mbo_req + n_ddo_req),
        "n_req": (n_mbo_req, n_ddo_req),
    }


def scores_by_step(d):
    """(181, 10) joint MAVF after 0, 1, ..., 180 trials, and the catalogue-only scores."""
    n_designs = len(d["names"])
    onehot = np.eye(n_designs)[d["design"]]                       # (180, 10)
    sums = np.cumsum(onehot[:, :, None] * d["values"][:, None, :], axis=0)
    counts = np.cumsum(onehot, axis=0)
    sums = np.concatenate([np.zeros((1,) + sums.shape[1:]), sums])
    counts = np.concatenate([np.zeros((1, n_designs)), counts])
    measured = counts > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = sums / counts[:, :, None]
    mean = np.where(measured[:, :, None], mean, np.nan)
    # a step with no measured design has all-NaN columns; nanmin warns and returns NaN
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        v_ddo = savf(mean, DDO_SENSE, axis=1)
    v_ddo = np.where(measured[:, :, None], v_ddo, 0.0)
    v_mbo = savf(d["catalogue"], MBO_SENSE, axis=0)                # (10, 3)
    mbo_only = v_mbo.mean(axis=1)
    joint = (d["w_mbo"] * v_mbo.mean(axis=1))[None, :] + d["w_ddo"] * v_ddo.mean(axis=2)
    return joint, mbo_only, counts


def ranks(scores):
    """Place of each design (0 = best) per row, ties broken by row order as argsort does."""
    order = np.argsort(-scores, axis=-1, kind="stable")
    place = np.empty_like(order)
    np.put_along_axis(place, order, np.arange(scores.shape[-1])[None, :].repeat(len(scores), 0),
                      axis=-1)
    return place


def reductions():
    d = load()
    joint, mbo_only, counts = scores_by_step(d)
    return {"data": d, "joint": joint, "mbo_only": mbo_only, "counts": counts,
            "final_order": [d["names"][k] for k in np.argsort(-joint[-1], kind="stable")],
            "catalogue_order": [d["names"][k] for k in np.argsort(-mbo_only, kind="stable")]}


def build(fps):
    r = reductions()
    d = r["data"]
    names, joint, counts = d["names"], r["joint"], r["counts"]
    n_designs, n_trials = len(names), len(d["design"])
    n_full = int(round((INTRO + TRIALS + OUTRO) * fps))

    # trial count at every frame of the full timeline, and the smoothed bar positions
    sec = np.arange(n_full) / fps
    k_float = np.clip((sec - INTRO) / TRIALS, 0.0, 1.0) * n_trials
    step = np.floor(k_float).astype(int)
    place = ranks(joint[step]).astype(float)
    width = max(1, int(0.35 * fps))
    pad = np.concatenate([np.repeat(place[:1], width, 0), place, np.repeat(place[-1:], width, 0)])
    c = np.cumsum(np.concatenate([np.zeros((1, n_designs)), pad]), axis=0)
    smooth = (c[2 * width + 1:] - c[:-2 * width - 1]) / (2 * width + 1)
    ypos = smooth[:n_full]

    fig = render.figure()
    ax = fig.add_axes([0.03, 0.20, 0.47, 0.66])
    hx = fig.add_axes([0.62, 0.20, 0.30, 0.66])
    cx = fig.add_axes([0.935, 0.20, 0.012, 0.66])

    colours = np.array(["#4c72b0"] * n_designs, dtype=object)
    colours[names.index("design-4")] = "#c44e52"
    bars = ax.barh(np.arange(n_designs), joint[0], height=0.72, color="0.75")
    labels = [ax.text(0, 0, "", va="center", ha="right", fontsize=9.5) for _ in names]
    values = [ax.text(0, 0, "", va="center", ha="left", fontsize=9, color="0.25") for _ in names]
    catalogue_place = ranks(r["mbo_only"][None, :])[0]
    ax.set_xlim(-0.40, 1.05)
    ax.set_ylim(n_designs - 0.4, -0.6)
    ax.set_yticks([])
    ax.spines[["left", "top", "right"]].set_visible(False)
    ax.set_xticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("MAVF score")
    ax.axvline(0.0, color="0.3", lw=0.8)
    title = ax.set_title("", loc="left", fontsize=13)

    # success-rate heat, rows in campaign order, columns in scenario order
    campaign_rows = list(dict.fromkeys(d["design"].tolist()))
    row_of = np.empty(n_designs, dtype=int)
    row_of[campaign_rows] = np.arange(n_designs)
    heat = np.full((n_designs, len(d["env_names"])), np.nan)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#f2f2f2")
    im = hx.imshow(heat, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")
    hx.set_yticks(np.arange(n_designs))
    hx.set_yticklabels([names[k] for k in campaign_rows], fontsize=9)
    hx.get_yticklabels()[campaign_rows.index(names.index("design-4"))].set_color("#c44e52")
    hx.set_xticks(np.arange(len(d["env_names"])))
    hx.set_xticklabels(d["env_names"], rotation=90, fontsize=7)
    hx.set_title("PERFECT trials: success rate per scenario", loc="left", fontsize=12)
    fig.colorbar(im, cax=cx, label="success rate")
    cursor = hx.add_patch(plt.Rectangle((-0.5, -0.5), 1, 1, fill=False, ec="#c44e52", lw=2.0))

    head = fig.text(0.03, 0.94, "", fontsize=15, weight="bold")
    note = fig.text(0.03, 0.03, "", fontsize=10.5, color="0.2")
    w_mbo, w_ddo = d["n_req"]
    per = "/" + str(w_mbo + w_ddo)
    rank_row = {row["design"]: row for row in d["ranking"]}
    lone = rank_row["design-4"]

    def draw(t):
        i = int(round(t * (n_full - 1)))
        k = step[i]
        s = joint[k]
        measured = counts[k] > 0
        for j in range(n_designs):
            bars[j].set_y(ypos[i, j] - 0.36)
            bars[j].set_width(s[j])
            bars[j].set_color(colours[j] if measured[j] else "0.72")
            labels[j].set_position((-0.015, ypos[i, j]))
            labels[j].set_text(names[j] + "  (cat. #" + str(catalogue_place[j] + 1) + ")")
            labels[j].set_color("#c44e52" if names[j] == "design-4" else "0.1")
            values[j].set_position((s[j] + 0.008, ypos[i, j]))
            values[j].set_text(str(round(float(s[j]), 3)))
        heat[:] = np.nan
        heat[row_of[d["design"][:k]], d["env"][:k]] = d["success"][:k]
        im.set_data(heat)
        if 0 < k < n_trials:
            cursor.set_visible(True)
            cursor.set_xy((d["env"][k - 1] - 0.5, row_of[d["design"][k - 1]] - 0.5))
        else:
            cursor.set_visible(False)
        if k == 0:
            head.set_text("Ranked on the catalogue: price, power, RAM")
            title.set_text("before any trial (catalogue-only order)")
            note.set_text("design-4 (one D455 depth camera) is first on the catalogue attributes. "
                          "Until a design has run, its measured attributes count 0,\n"
                          "so each bar is " + str(w_mbo) + per + " of its catalogue-only score")
        elif k < n_trials:
            head.set_text("PERFECT trials arriving: " + str(k) + " / " + str(n_trials))
            title.set_text("joint MAVF, trial " + str(k) + ": " + names[d["design"][k - 1]]
                           + " on " + d["env_names"][d["env"][k - 1]])
            note.set_text("weights: model-based attributes " + str(w_mbo) + per + ", measured "
                          + str(w_ddo) + per + " (requirement partition); grey = no trial yet (measured "
                          "attributes count 0);\nvalue functions span the designs measured so far, "
                          "so the order among them moves as new designs widen the ranges; cat. = catalogue-only rank")
        else:
            head.set_text("After all " + str(n_trials) + " PERFECT trials")
            title.set_text("joint MAVF over catalogue and measured attributes")
            note.set_text("design-4: catalogue rank " + lone["mbo_only_rank"] + ", MAVF rank "
                          + lone["mavf_rank"] + " (score " + str(round(float(lone["mavf_score"]), 4))
                          + ", success rate " + str(round(float(lone["success_rate"]), 3)) + ")")

    return fig, draw, n_full


def main():
    a = render.arguments(NAME)
    fig, draw, n_full = build(a.fps)
    ts = render.timeline(n_full, a.frames)
    render.render(fig, draw, ts, a.out, NAME, a.fps, poster_t=1.0,
                  gif_width=a.gif_width, gif_fps=a.gif_fps, gif_speed=a.gif_speed,
                  height=a.height)


if __name__ == "__main__":
    main()
