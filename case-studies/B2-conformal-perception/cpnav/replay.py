"""Replay the pair of episodes behind figures/trajectories.svg.

run_case_study.py draws its seeded campaign, calibrates q on it, draws the
test worlds from the same generator, and then re-runs the first N_FIGURE test
worlds twice, once without inflation and once with q, from a second seeded
generator. This module repeats exactly that sequence of draws, reading the seed
and the sizes from results/summary.json, and hands the per-step hook to the
recorded pair run. Used by animations/make_conformal_regions.py.
"""

import json
import pathlib

import numpy as np

from . import campaign, conformal, planner

N_FIGURE = 24    # episodes re-run for the trajectory figure, as in run_case_study.py

SUMMARY = pathlib.Path(__file__).resolve().parent.parent / "results" / "summary.json"


def figure_pair(on_step=None, summary_path=SUMMARY):
    """Re-run the calibration and the recorded pair.

    Returns a dict with the summary it read, the recomputed q, the pair run's
    output (arm-major: nominal episodes first, then conformal), the figure
    worlds, and the closed-loop coverage of the conformal arm.
    """
    summary = json.loads(pathlib.Path(summary_path).read_text())
    seed = summary["seed"]
    c = summary["campaign"]
    alpha = summary["operating_point"]["alpha"]

    rng = np.random.default_rng(seed)
    rows, _ = campaign.run_campaign(rng, c["episodes"], every=c["frame_every"])
    cal_rows, _ = campaign.split_by_episode(rows, c["calibration_episodes"])
    cal_true, cal_det = campaign.boxes_from_rows(cal_rows)
    q = conformal.quantile(conformal.scores(cal_det, cal_true), alpha)

    boxes, valid, hard = campaign.feasible_worlds(rng, summary["test_episodes"])
    boxes, valid, hard = boxes[:N_FIGURE], valid[:N_FIGURE], hard[:N_FIGURE]
    pair = planner.run_episodes(
        np.random.default_rng(seed + 1),
        np.tile(boxes, (2, 1, 1)),
        np.tile(valid, (2, 1)),
        np.tile(hard, (2, 1)),
        q=np.repeat([0.0, q], N_FIGURE),
        record=True,
        on_step=on_step,
    )
    cp_rows = pair["rows"][pair["rows"][:, 0] >= N_FIGURE]
    cp_true, cp_det = campaign.boxes_from_rows(cp_rows)
    return {"summary": summary, "q": q, "pair": pair, "boxes": boxes, "valid": valid,
            "closed_loop_coverage": conformal.coverage(cp_det, cp_true, q)}
