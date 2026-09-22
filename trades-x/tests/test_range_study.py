"""The test-range study: the analytic model, the frontier, the ranking, the tables."""

import csv
import importlib.util
import json
import math
import pathlib

import numpy as np
import pytest

from tradesx import range_model as rm
from tradesx import requirements as reqs

STUDY = pathlib.Path(__file__).resolve().parent.parent / "case-studies" / "range"


def load_study():
    spec = importlib.util.spec_from_file_location("run_range_study",
                                                  STUDY / "run_range_study.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------
# the analytic attributes against a brute-force oracle

def oracle(density, k, mu_s, mu_d, e, cells, cells_p90):
    """Brute-force oracle: one configuration, one cell at a time, plain floats."""
    L = rm.SPEED * rm.DURATION
    footprint = math.pi / 4 * rm.ROCK_SIZE ** 2 * (1 + rm.ROCK_JITTER ** 2 / 3)
    rate = density / footprint * (1 - (rm.KEEPOUT_RADIUS / rm.START_RADIUS) ** 2)
    enc = rate * 2 * rm.ENCOUNTER_RADIUS
    blocks = rate * (rm.ROCK_SIZE + rm.WHEEL_TRACK)
    mfp = 1 / blocks
    back = (e * rm.SPEED) ** 2 / (2 * mu_d * rm.GRAVITY)
    p_block = 1 - math.exp(-L / mfp)
    progress = max(p_block * (mfp - back), 0.0) / L
    bound = math.degrees(0.35)
    theta_sum = over = demand = relief = lost = 0.0
    for g in cells:
        t = k * g
        theta = math.degrees(math.atan(t))
        theta_sum += theta
        demand += t
        over += max(t - mu_s, 0.0)
        relief += min(theta / bound, 1.0)
        lost += min(max((theta - bound) / bound, 0.0), 1.0)
    n = len(cells)
    slip = over / demand
    attitude = 1 - lost / n
    p_enc = 1 - math.exp(-enc * L)
    return {
        "encounters_per_m": enc,
        "p_encounter": p_enc,
        "mean_free_path_m": mfp,
        "progress_fraction": progress,
        "grade_mean_deg": theta_sum / n,
        "grade_p90_deg": math.degrees(math.atan(k * cells_p90)),
        "no_slip_margin": mu_s - k * cells_p90,
        "slip_share": slip,
        "relief": relief / n,
        "attitude": attitude,
        "contestedness": (p_enc + relief / n + slip) / 3,
        "traversability": progress * (1 - slip) * attitude,
    }


def test_attributes_match_the_oracle():
    cells = np.array([0.05, 0.2, 0.35, 0.5, 0.9, 1.4, 2.2])
    p90 = float(np.percentile(cells, 90))
    d, k, mu, e = np.meshgrid([0.05, 0.3, 0.8], [0.2, 0.6, 1.0], [0.3, 0.9], [0.0, 0.3],
                              indexing="ij")
    mu_d = mu - 0.1
    got = rm.attributes(d, k, mu, mu_d, e, cells, p90)
    for idx in np.ndindex(d.shape):
        want = oracle(d[idx], k[idx], mu[idx], mu_d[idx], e[idx], cells, p90)
        for name, value in want.items():
            assert got[name][idx] == pytest.approx(value, rel=1e-12, abs=1e-14), name


def test_gradient_of_a_plane():
    # a tilted plane has the same gradient everywhere, at any window
    rows, cols = 64, 48
    r, c = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    terrain = {"h": 3.0 * r - 2.0 * c, "x0": 0.0, "y0": 0.0, "dx": -0.5, "dy": 0.25,
               "hz": 0.1}
    want = math.hypot(0.3 / 0.5, 0.2 / 0.25)
    for window in (1, 4, 16):
        g, x, y = rm.gradient(terrain, window)
        assert np.allclose(g, want)
        assert g.shape == x.shape == y.shape


def test_height_scale_matches_the_recorded_campaign():
    ctx = rm.context()
    rows = list(csv.DictReader(open(rm.ROOT / "isaacsim" / "results" / "campaign.csv")))
    for row in rows:
        if row["max_slope_deg"] == "authored":
            assert float(row["height_scale"]) == 1.0
            continue
        k = rm.height_scale(float(row["max_slope_deg"]), ctx["g99"])
        assert k == pytest.approx(float(row["height_scale"]), rel=1e-9)
    assert len(ctx["cells"]) == 191


def test_derivatives_agree_with_central_differences():
    pytest.importorskip("jax")
    ctx = rm.context()
    points = np.array([[0.1, 15.0, 0.6, 0.5, 0.1], [0.45, 22.5, 0.4, 0.3, 0.3]])
    dc, dt = rm.relative_sensitivities(points, ctx)
    fc, ft = rm.relative_sensitivities_fd(points, ctx)
    assert np.allclose(dc, fc, atol=1e-7)
    assert np.allclose(dt, ft, atol=1e-7)


# ------------------------------------------------------------------
# the frontier and the ranking by hand

def test_frontier_on_a_hand_built_case():
    study = load_study()
    model_reqs = [{"id": "A", "attribute": "obstacle_density", "bound": "0.1 .. 0.6"}]
    knobs = {"obstacle_density": np.array([0.1, 0.2, 0.3, 0.4, 0.7, 0.5])}
    attrs = {"contestedness": np.array([0.2, 0.4, 0.3, 0.6, 0.9, 0.4]),
             "traversability": np.array([0.9, 0.7, 0.6, 0.3, 0.9, 0.7])}
    flags, feasible, frontier = study.model_based(model_reqs, knobs, attrs)
    # row 4 dominates everything but fails the band; row 2 is dominated by row 1;
    # rows 1 and 5 tie and both stay
    assert feasible.tolist() == [True, True, True, True, False, True]
    assert frontier.tolist() == [0, 1, 5, 3]


def test_ranking_against_a_hand_computation():
    study = load_study()
    all_reqs = reqs.load(STUDY / "requirements.yaml")
    model = {"contestedness": np.array([0.2, 0.5, 0.4]),
             "traversability": np.array([0.6, 0.2, 0.4])}
    measured = {"distance_m": np.array([10.0, 4.0, 7.0]),
                "obstacle_encounters": np.array([0.0, 2.0, 1.0]),
                "mean_pitch_deg": np.array([5.0, 9.0, 5.0]),
                "max_roll_deg": np.array([10.0, 30.0, 20.0]),
                "stuck": np.array([0.0, 1.0, 0.0]),
                "unstable": np.array([0.0, 0.0, 0.0])}
    order, scores, place, mbo_scores, mbo_place = study.rank(model, measured, all_reqs)

    # SAVFs by hand, 1 = best. Model-based: C up, T up. Measured: distance,
    # encounters, pitch up; roll, stuck, unstable down (unstable is flat -> 1).
    c = [0.0, 1.0, 2 / 3]
    t = [1.0, 0.0, 0.5]
    dist = [1.0, 0.0, 0.5]
    enc = [0.0, 1.0, 0.5]
    pitch = [0.0, 1.0, 0.0]
    roll = [1.0, 0.0, 0.5]
    stuck = [1.0, 0.0, 1.0]
    flat = [1.0, 1.0, 1.0]
    # 3 of the 8 requirements are model-based, 5 data-driven
    wm, wd = 3 / 8 / 2, 5 / 8 / 6
    want = [wm * (c[i] + t[i]) + wd * (dist[i] + enc[i] + pitch[i] + roll[i] + stuck[i] + flat[i])
            for i in range(3)]
    want_mbo = [0.5 * (c[i] + t[i]) for i in range(3)]
    assert np.allclose(scores, want)
    assert np.allclose(mbo_scores, want_mbo)
    assert order.tolist() == list(np.argsort(-np.array(want), kind="stable"))
    assert sorted(place.tolist()) == [1, 2, 3]
    assert place[order[0]] == 1


def test_requirement_partition():
    model_based, data_driven = reqs.partition(reqs.load(STUDY / "requirements.yaml"))
    assert [r["id"] for r in model_based] == ["RR.1", "RR.2", "RR.3"]
    assert [r["attribute"] for r in data_driven] == ["distance_m", "max_roll_deg",
                                                    "max_pitch_deg", "stuck", "unstable"]


# ------------------------------------------------------------------
# the tables the study writes

def read(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def test_study_writes_the_shipped_tables(tmp_path, monkeypatch):
    pytest.importorskip("jax")
    study = load_study()
    monkeypatch.setattr(study, "results", tmp_path / "results")
    monkeypatch.setattr(study, "figures", tmp_path / "figures")
    assert study.main() == 0

    out = tmp_path / "results"
    grid = read(out / "mbo_grid.csv")
    assert len(grid) == 1 + 18 * 13 * 8 * 3
    assert len(set(len(r) for r in grid)) == 1 and len(grid[0]) == 24
    frontier = read(out / "mbo_frontier.csv")
    on = [r for r in grid[1:] if r[-1] == "1"]
    # the frontier table is the grid's on_frontier rows, ordered by contestedness
    assert sorted(frontier[1:]) == sorted(on) and all(r[-2] == "1" for r in on)
    c = [float(r[grid[0].index("contestedness")]) for r in frontier[1:]]
    assert c == sorted(c)

    ddo = read(out / "ddo_metrics.csv")
    assert len(ddo) == 9
    ranking = read(out / "mavf_ranking.csv")
    assert len(ranking) == 9
    assert sorted(int(r[2]) for r in ranking[1:]) == list(range(1, 9))
    assert sorted(int(r[4]) for r in ranking[1:]) == list(range(1, 9))
    sens = read(out / "sensitivity.csv")
    assert [r[0] for r in sens[1:]] == ["knob"] * 5 + ["requirement"] * 4

    points = json.loads((out / "next_campaign_points.json").read_text())
    assert len(points) == 8
    assert all(sorted(p) == sorted(rm.KNOBS + ["seed", "duration_s"]) for p in points)
    assert "--extra" in (out / "next_campaign.txt").read_text()

    for name in ("mbo_grid.csv", "mbo_frontier.csv", "ddo_metrics.csv", "mavf_ranking.csv",
                 "sensitivity.csv", "next_campaign_points.json", "next_campaign.txt"):
        assert (out / name).read_bytes() == (STUDY / "results" / name).read_bytes(), name
    for stem in ("mbo_grid_frontier", "mavf_ranking", "sensitivity"):
        assert (tmp_path / "figures" / (stem + ".svg")).exists()
        assert (tmp_path / "figures" / (stem + ".pdf")).exists()
