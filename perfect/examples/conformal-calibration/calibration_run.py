"""One calibration trial: closed-loop episodes that write down what the detector saw.

The perception stack and the planner are not in this file. They are the `cpnav`
package of the conformal-perception case study, and this script runs its
campaign function -- draw arenas the goal is reachable in, run the nominal
closed loop, and record one row per detection per frame with the ground-truth
box beside it. `CPNAV_PACKAGE` says where that package lives; without it the
case study's directory in this repository is used.

The whole file is the mapping from two working files to one trial's data:

    detector.yaml  what the design chose: the detector configuration
    scenario.yaml  what the environment chose: the clutter band, the seed, and
                   how many episodes the trial runs

Calibration data has to come from the closed-loop states the robot actually
visits, which is why every row here is produced by running the planner rather
than by drawing boxes in the abstract.

The obstacle count is a module constant of `cpnav.world`, so the clutter band is
applied by setting it before the arenas are drawn. That is the only value this
script writes inside the package.

`experiment.py` runs this in a child process, so numpy does not have to be
installed in the Python environment that carries PERFECT:

    python calibration_run.py job.json metrics.json

`job.json` holds {"detector": ..., "scenario": ...} and `metrics.json` receives
the rows and the episode outcomes that the trial reports back to the server.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACKAGE = os.path.normpath(os.path.join(
    HERE, os.pardir, os.pardir, os.pardir, "case-studies", "B2-conformal-perception"))
PACKAGE = os.environ.get("CPNAV_PACKAGE") or DEFAULT_PACKAGE
if PACKAGE not in sys.path:
    sys.path.insert(0, PACKAGE)

import numpy as np

from cpnav import campaign, conformal, planner, world

# The columns of the detection table, in the order the case study writes them.
ROW_COLUMNS = list(planner.ROW_COLUMNS)

# The rows are reported at the precision the case study's own row table is
# written at, which is what its round-trip test holds it to.
DECIMALS = 4


def settings(scenario, detector):
    """What one trial runs under, read out of the two working files.

    PERFECT's template substitution turns every numeric environment argument
    into a float, so the counts and the seeds are cast back to integers here.
    """
    band = scenario["bands"][scenario["clutter"]]
    return {
        "clutter": scenario["clutter"],
        "band": (int(band[0]), int(band[1])),
        "seed": int(scenario["seed"]),
        "n_episodes": int(scenario["n_episodes"]),
        "frame_every": int(scenario["frame_every"]),
        "base_seed": int(scenario["base_seed"]),
        "detector": detector["configuration"],
        "shift": float(detector["shift"]),
    }


def run(scenario, detector):
    """Run the episodes. -> settings, the detection rows, the closed-loop output."""
    s = settings(scenario, detector)
    world.MIN_OBSTACLES, world.MAX_OBSTACLES = s["band"]
    rng = np.random.default_rng(s["base_seed"] + s["seed"])
    rows, out = campaign.run_campaign(rng, s["n_episodes"], shift=s["shift"],
                                      every=s["frame_every"])
    return s, rows, out


def metrics(scenario, detector):
    """The detection rows, the episode outcomes, and the summaries of both.

    `rows` is the flat per-detection table the rest of the case study consumes:
    one row per detection per frame, the true box beside the detected one. The
    conformal calibration is run on these rows once the whole campaign is in.

    `coverage_margin` is the worst nonconformity score of the trial, negated, so
    it is positive exactly when every detection of the trial already covered its
    object without any inflation.
    """
    s, rows, out = run(scenario, detector)
    status = out["status"]
    truth, detected = campaign.boxes_from_rows(rows)
    scores = conformal.scores(detected, truth)

    m = dict(s)
    m["band"] = list(s["band"])
    m["episodes"] = int(status.size)
    m["detections"] = int(rows.shape[0])
    m["collisions"] = int((status == planner.COLLISION).sum())
    m["successes"] = int((status == planner.SUCCESS).sum())
    m["stalls"] = int((status == planner.STALLED).sum())
    m["collision_rate"] = float((status == planner.COLLISION).mean())
    m["success_rate"] = float((status == planner.SUCCESS).mean())
    m["mean_length"] = float(out["length"].mean())
    m["mean_waits"] = float(out["waits"].mean())
    m["score_mean"] = float(scores.mean()) if scores.size else 0.0
    m["score_max"] = float(scores.max()) if scores.size else 0.0
    m["coverage_margin"] = -m["score_max"]
    m["status"] = status.tolist()
    m["length"] = np.round(out["length"], DECIMALS).tolist()
    m["steps"] = out["steps"].tolist()
    m["waits"] = out["waits"].tolist()
    m["rows"] = np.round(rows, DECIMALS).tolist()
    return m


def main():
    job = json.load(open(sys.argv[1]))
    out = metrics(job["scenario"], job["detector"])
    with open(sys.argv[2], "w") as f:
        json.dump(out, f)
    print(out["detector"], out["clutter"], "seed", out["seed"],
          out["episodes"], "episodes,", out["detections"], "detections,",
          out["collisions"], "collisions")


if __name__ == "__main__":
    main()
