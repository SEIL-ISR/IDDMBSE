# The five planner policies of the risk-sensitive planning study, in PERFECT's 300-trial
# campaign: the failure rate and the worst-case realised cost (95th percentile) in the
# three rock fields, as the execution noise sigma rises one level at a time.
#
# Every bar is a row of case-studies/A2-risk-sensitive-planning/results/perfect/cells.csv
# (five trials per cell, 400 executions per trial); the traversal budget line is
# budget_factor x straight_line from summary.json.

import csv
import json
import sys
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render  # noqa: E402

NAME = "rarrt_noise_sweep"
RESULTS = render.ROOT / "case-studies" / "A2-risk-sensitive-planning" / "results" / "perfect"
CELLS = RESULTS / "cells.csv"
SUMMARY = RESULTS / "summary.json"

POLICY_COLOUR = {"rrtstar": "#444444", "neutral": "#1f77b4", "cvar0.1": "#2ca02c",
                 "cvar0.5": "#ff7f0e", "cvar0.9": "#d62728"}
INTRO, STEP, GROW, OUTRO = 1.0, 3.5, 1.2, 3.0


def load():
    cfg = json.load(open(SUMMARY))["config"]
    envs = [e[0] for e in cfg["environments"]]
    sigmas = cfg["noise_levels"]
    policies = cfg["policies"]
    with open(CELLS) as f:
        rows = list(csv.DictReader(f))
    index = {(r["env"], float(r["sigma"]), r["policy"]): r for r in rows}
    shape = (len(envs), len(sigmas), len(policies))
    failure = np.array([float(index[(e, s, p)]["failure_rate"])
                        for e in envs for s in sigmas for p in policies]).reshape(shape)
    worst = np.array([float(index[(e, s, p)]["worst_case_p95"])
                      for e in envs for s in sigmas for p in policies]).reshape(shape)
    return {"envs": envs, "sigmas": sigmas, "policies": policies, "failure": failure,
            "worst": worst, "coverage": dict(cfg["environments"]),
            "budget": cfg["budget_factor"] * cfg["straight_line"]}


def build(fps):
    d = load()
    envs, sigmas, policies = d["envs"], d["sigmas"], d["policies"]
    n_sig, n_pol = len(sigmas), len(policies)
    n_full = int(round((INTRO + n_sig * STEP + OUTRO) * fps))

    fig = render.figure()
    fig.text(0.06, 0.945, "Risk-sensitive RRT* through PERFECT: 300 trials, "
             "five policies, three rock fields, noise rising", fontsize=14, weight="bold")
    width = 0.8 / n_pol
    offsets = (np.arange(n_pol) - (n_pol - 1) / 2) * width
    axes, bars = [], []
    for r, (key, ylabel, top) in enumerate([
            ("failure", "failure rate\n(over budget or no path)", 0.46),
            ("worst", "worst-case cost [m]\n(95th percentile realised)", 280.0)]):
        for c, env in enumerate(envs):
            ax = fig.add_axes([0.08 + c * 0.305, 0.49 - r * 0.40, 0.27, 0.31])
            group = []
            for p, policy in enumerate(policies):
                group.append(ax.bar(np.arange(n_sig) + offsets[p], np.zeros(n_sig), width,
                                    color=POLICY_COLOUR[policy],
                                    label=policy if (r == 0 and c == 0) else None))
            ax.set_xticks(np.arange(n_sig))
            ax.set_xticklabels(["sigma " + str(s) for s in sigmas], fontsize=9)
            ax.set_xlim(-0.5, n_sig - 0.5)
            ax.set_ylim(0, top)
            ax.tick_params(labelsize=9)
            if c == 0:
                ax.set_ylabel(ylabel, fontsize=10)
            if r == 0:
                ax.set_title(env + " field (target rock coverage " + str(d["coverage"][env]) + ")",
                             fontsize=11)
            if key == "worst":
                ax.axhline(d["budget"], color="0.4", ls="--", lw=1.0)
                ax.text(-0.45, d["budget"] + 4, "budget " + str(round(d["budget"], 1)) + " m",
                        fontsize=8, color="0.3")
            axes.append(ax)
            bars.append((key, c, group))
    fig.legend(ncol=5, fontsize=10, frameon=False, loc="upper center",
               bbox_to_anchor=(0.5, 0.925))
    status = fig.text(0.06, 0.02, "", fontsize=10.5, color="0.2")
    labels = {}

    sec = np.arange(n_full) / fps
    # grow fraction of each sigma group at every frame, (n_full, n_sig)
    grow = render.ease((sec[:, None] - INTRO - np.arange(n_sig)[None, :] * STEP) / GROW)

    def draw(t):
        i = int(round(t * (n_full - 1)))
        g = grow[i]
        for key, c, group in bars:
            values = d[key][c]                                   # (n_sig, n_pol)
            for p, container in enumerate(group):
                for s, rect in enumerate(container):
                    rect.set_height(values[s, p] * g[s])
        level = int(np.sum(g > 0)) - 1
        for ax, (key, c, _) in zip(axes, bars):
            if (key, c) in labels:
                labels[(key, c)].remove()
                del labels[(key, c)]
            if level >= 0 and g[level] >= 1.0:
                values = d[key][c][level]
                worst_policy = int(np.argmax(values))
                best_policy = int(np.argmin(values))
                digits = 4 if key == "failure" else 1
                text = ("lowest " + policies[best_policy] + " " + str(round(float(values[best_policy]), digits))
                        + ", highest " + policies[worst_policy] + " "
                        + str(round(float(values[worst_policy]), digits)))
                labels[(key, c)] = ax.text(0.02, 0.96, "sigma " + str(sigmas[level]) + ": " + text,
                                           transform=ax.transAxes, fontsize=7.5, va="top")
        if level < 0:
            status.set_text("cells.csv: one bar per (field, sigma, policy) cell, 5 trials x 400 executions each")
        else:
            status.set_text("noise level sigma = " + str(sigmas[level]) + "; cells.csv: 5 trials "
                            "x 400 executions per cell, failure = realised cost over the "
                            + str(round(d["budget"], 1)) + " m budget or no path found")

    return fig, draw, n_full, d


def main():
    a = render.arguments(NAME)
    fig, draw, n_full, _ = build(a.fps)
    ts = render.timeline(n_full, a.frames)
    render.render(fig, draw, ts, a.out, NAME, a.fps, poster_t=1.0)


if __name__ == "__main__":
    main()
