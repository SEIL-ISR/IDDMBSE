# Each animation renders four frames, its poster exists and its frames carry ink, and the
# numbers it puts on screen equal the ones computed here straight from the input files.

import csv
import json

import numpy as np
import yaml

from conftest import module, render


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------
# mavf_ranking_flip

def test_mavf_ranking_flip_renders(check_render):
    check_render("mavf_ranking_flip")


def test_mavf_final_ranking_matches_the_recorded_table():
    m = module("mavf_ranking_flip")
    r = m.reductions()
    trials = read_csv(m.CAMPAIGN)
    ranking = read_csv(m.RANKING)
    names = [row["design"] for row in ranking]
    reqs = yaml.safe_load(open(m.REQUIREMENTS))
    w_mbo = sum(q["class"] == "model-based" for q in reqs) / len(reqs)

    # the per-design means of the six measured attributes, from the trial rows
    di = np.array([names.index(t["design"]) for t in trials])
    x = np.array([[float(t[c]) for c in m.DDO] for t in trials])
    mean = np.stack([np.bincount(di, weights=x[:, c]) for c in range(x.shape[1])], 1)
    mean /= np.bincount(di)[:, None]
    cat = np.array([[float(row[c]) for c in m.MBO] for row in ranking])
    both = np.hstack([cat, mean])
    sense = np.array([-1, -1, -1, 1, -1, -1, -1, 1, 1])
    lo, hi = both.min(0), both.max(0)
    v = np.where(sense > 0, (both - lo) / (hi - lo), (hi - both) / (hi - lo))
    w = np.r_[np.full(3, w_mbo / 3), np.full(6, (1 - w_mbo) / 6)]
    score = v @ w

    recorded = np.array([float(row["mavf_score"]) for row in ranking])
    assert np.allclose(score, recorded, atol=2e-6)
    assert np.allclose(r["joint"][-1], recorded, atol=2e-6)
    by_rank = sorted(ranking, key=lambda row: int(row["mavf_rank"]))
    assert r["final_order"] == [row["design"] for row in by_rank]
    by_cat = sorted(ranking, key=lambda row: int(row["mbo_only_rank"]))
    assert r["catalogue_order"] == [row["design"] for row in by_cat]
    assert r["catalogue_order"][0] == "design-4" and r["final_order"][-1] == "design-4"
    # before any trial the joint score is 7/23 of the catalogue-only score
    assert np.allclose(r["joint"][0] / w_mbo,
                       [float(row["mbo_only_score"]) for row in ranking], atol=2e-6)


def test_mavf_trials_arrive_in_campaign_order():
    m = module("mavf_ranking_flip")
    r = m.reductions()
    assert r["counts"].shape == (181, 10)
    assert r["counts"][-1].tolist() == [18.0] * 10
    assert np.all(np.diff(r["counts"].sum(axis=1)) == 1)


# ------------------------------------------------------------------
# range_replay

def test_range_replay_renders(check_render):
    check_render("range_replay")


def first_violations(trace, bound, rate=20.0, window=20.0, v_min=0.2):
    """Roll, pitch and progress first-violation times, from the trajectory alone."""
    t = trace[:, 0]
    grid = np.arange(int(np.floor(t[-1] * rate + 1e-6)) + 1) / rate
    j = np.clip(np.searchsorted(t, grid), 1, t.size - 1)
    near = np.where(np.abs(t[j - 1] - grid) <= np.abs(t[j] - grid), j - 1, j)
    s = trace[near]
    out = []
    for col in (4, 5):
        bad = np.nonzero(np.abs(s[:, col]) > bound)[0]
        out.append(bad[0] / rate if bad.size else np.inf)
    ok = np.r_[0, np.cumsum(s[:, 7] >= v_min)]
    w = int(round(window * rate))
    k = np.arange(len(s))
    seen = ok[k + 1] - ok[np.maximum(k - w, 0)]
    bad = np.nonzero((seen == 0) & (k / rate >= window))[0]
    out.append(bad[0] / rate if bad.size else np.inf)
    return np.array(out)


def test_range_verdict_times_match_the_trajectories():
    m = module("range_replay")
    d = m.load()
    spec = yaml.safe_load(open(m.SPEC))
    assert "abs(roll) <= 0.35" in spec["monitors"][0]["formula"]
    assert d["attitude_bound_rad"] == 0.35
    ours = np.stack([first_violations(tr, 0.35) for tr in d["traces"]])
    assert np.allclose(np.where(np.isinf(ours), -1, ours), np.where(np.isinf(d["first"]), -1, d["first"]),
                       atol=1e-9)
    # the three violations the observer recorded: roll on trials 7 and 8, progress on 5
    assert d["first"][6, 0] == 29.85 and d["first"][7, 0] == 0.0 and d["first"][4, 2] == 25.7
    assert np.isinf(d["first"]).sum() == 24 - 3


# ------------------------------------------------------------------
# multirobot_room

def test_multirobot_room_renders(check_render):
    check_render("multirobot_room")


def oracle_rho(cfg, traj):
    """Brute-force test oracle: phi_i on the whole trace, one step at a time."""
    m = module("multirobot_room")
    obstacles = [m.halfspaces(o) for o in cfg["obstacles"]]
    d = cfg["separation"]["d_min"]
    R, T = traj.shape[0], traj.shape[1]
    out = []
    for i, r in enumerate(cfg["robots"]):
        terms = []
        for g in r["goals"]:
            A, b = m.halfspaces({**g, "type": "box"})
            a0, b0 = g["window"]
            terms.append(max(min(b - A @ traj[i, k]) for k in range(a0, b0 + 1)))
        for k in range(T):
            for A, b in obstacles:
                terms.append(max(A @ traj[i, k] - b))
            for j in range(R):
                if j != i:
                    terms.append(max(abs(traj[i, k] - traj[j, k])) - d)
        out.append(min(terms))
    return np.array(out)


def test_multirobot_robustness_reaches_the_recorded_values():
    m = module("multirobot_room")
    d = m.load()
    rho = m.running_rho(d["cfg"], d["executed"])
    recorded = np.array([d["goals"]["blocks"][r["id"]]["goal_satisfaction"]
                         for r in d["cfg"]["robots"]])
    assert np.allclose(rho[:, -1], recorded, atol=1e-6)
    assert np.allclose(oracle_rho(d["cfg"], d["executed"]), recorded, atol=1e-6)
    assert np.all(np.diff(rho, axis=1) <= 1e-12)
    hits = m.breaches(d["cfg"], d["executed"])
    assert [(a, b, k) for a, b, k, _ in hits] == [(0, 1, 8)]
    assert d["goals"]["blocks"]["AGR_1"]["binding_conjunct"] == "sep(1,2)@k=8"
    assert abs(hits[0][3] - d["goals"]["blocks"]["AGR_1"]["goal_satisfaction"]) < 1e-6


# ------------------------------------------------------------------
# rarrt_noise_sweep

def test_rarrt_noise_sweep_renders(check_render):
    check_render("rarrt_noise_sweep")


def test_rarrt_failure_rates_match_the_trial_table():
    m = module("rarrt_noise_sweep")
    d = m.load()
    trials = read_csv(m.RESULTS / "campaign.csv")
    assert len(trials) == 300 and all(t["found"] == "1" for t in trials)
    key = np.array([d["envs"].index(t["env"]) * 100 + d["sigmas"].index(float(t["sigma"])) * 10
                    + d["policies"].index(t["policy"]) for t in trials])
    over = np.array([float(t["over_budget"]) for t in trials])
    size = 100 * len(d["envs"])
    mean = np.bincount(key, weights=over, minlength=size) / np.maximum(np.bincount(key, minlength=size), 1)
    e, s, p = np.meshgrid(np.arange(3), np.arange(4), np.arange(5), indexing="ij")
    assert np.allclose(mean[e * 100 + s * 10 + p], d["failure"], atol=1e-9)
    cells = {(c["env"], float(c["sigma"]), c["policy"]): float(c["worst_case_p95"])
             for c in read_csv(m.CELLS)}
    assert d["worst"][2, 3, 0] == cells[("hard", 0.5, "rrtstar")]
    assert round(d["budget"], 1) == 118.8
    # at the highest noise level plain RRT* fails most in every field
    assert np.all(np.argmax(d["failure"][:, -1], axis=1) == d["policies"].index("rrtstar"))


# ------------------------------------------------------------------
# calibration_curve

def test_calibration_curve_renders(check_render):
    check_render("calibration_curve")


def test_calibration_converges_to_the_recorded_coverage():
    m = module("calibration_curve")
    r = m.reductions(50)
    summary = json.load(open(m.SUMMARY))["operating_point"]
    assert r["ns"][-1] == 5399 and r["hold"].size == 2441
    assert abs(r["q"][-1] - summary["q_m"]) < 1e-12
    assert abs(r["cover"][-1] - summary["holdout_coverage"]) < 1e-12
    rows = read_csv(m.COVERAGE)
    alpha01 = next(row for row in rows if float(row["alpha"]) == 0.1)
    assert round(r["cover"][-1], 6) == round(float(alpha01["holdout_coverage"]), 6)


def test_prefix_quantiles_match_a_brute_force_oracle():
    m = module("calibration_curve")
    r = m.reductions(50)
    cal = r["cal"]
    for n in (10, 57, 800, 5399):
        # brute-force oracle: sort the prefix, take the ceil((n + 1)(1 - alpha))-th value
        s = sorted(cal[:n])
        k = int(np.ceil((n + 1) * 0.9))
        assert m.prefix_quantiles(cal, np.array([n]), 0.1)[0] == s[k - 1]
