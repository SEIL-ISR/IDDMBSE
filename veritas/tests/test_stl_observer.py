"""The runtime observer's monitors, over a recorded trace (no ROS needed).

The trace is the same scenario `test_publisher.py` publishes on the live graph: the battery
state of charge decays linearly through 0.6 at t = 20 s, the goal is reached at t = 28 s, and
the obstacle distance never drops below 0.8.  Each monitor's robustness is checked against a
closed-form oracle for its operator: `historically (x >= c)` is the running minimum of x - c
and `once[0,T] (x >= c)` over a window longer than the trace is the running maximum.
"""

from pathlib import Path

import numpy as np
import pytest
import yaml

import monitors as mon
from replay_observer import replay

root = Path(__file__).resolve().parents[1]
spec_path = root / "runtime" / "stl-observer" / "specs" / "agr_safety.yaml"

RATE = 10.0
DURATION = 32.0
SOC0, SLOPE, GOAL_AT = 0.9, 0.015, 28.0


def scenario():
    t = np.arange(0.0, DURATION, 1.0 / RATE)
    return {
        "time": t,
        "soc": SOC0 - SLOPE * t,
        "goal": (t >= GOAL_AT).astype(float),
        "obstacle_distance": 1.2 + 0.4 * np.sin(0.5 * t),
    }


@pytest.fixture(scope="module")
def trace_csv(tmp_path_factory):
    s = scenario()
    p = tmp_path_factory.mktemp("trace") / "agr.csv"
    cols = list(s)
    np.savetxt(p, np.column_stack([s[c] for c in cols]), delimiter=",",
               header=",".join(cols), comments="")
    return p


def test_every_formula_in_the_spec_parses():
    cfg = yaml.safe_load(spec_path.read_text())
    assert cfg["rate"] == RATE
    names = [m["name"] for m in cfg["monitors"]]
    assert names == ["soc_safety", "goal_liveness", "obstacle_safety"]
    # load_spec parses each formula with RTAMT; a bad formula raises here
    rate, ms, sources = mon.load_spec(str(spec_path))
    assert [m.name for m in ms] == names
    assert set(sources) == {"soc", "goal", "obstacle_distance"}
    assert sources["soc"]["type"] == "sensor_msgs/msg/BatteryState"
    assert sources["soc"]["field"] == "percentage"
    assert sources["goal"]["type"] == "std_msgs/msg/Bool"


def test_read_field_walks_a_dotted_path():
    class Inner:
        x = 2.5

    class Msg:
        percentage = 0.75
        data = True
        inner = Inner()
        ranges = [1.0, 4.0]

    assert mon.read_field(Msg(), "percentage") == 0.75
    assert mon.read_field(Msg(), "data") == 1.0          # a Bool field becomes 1.0 / 0.0
    assert mon.read_field(Msg(), "inner.x") == 2.5
    assert mon.read_field(Msg(), "ranges.1") == 4.0


def test_safety_monitor_matches_the_running_minimum(trace_csv):
    s = scenario()
    r = replay(str(spec_path), str(trace_csv))["soc_safety"]
    expected = np.minimum.accumulate(s["soc"] - 0.6)
    assert np.allclose(r["rho"], expected, atol=1e-9)

    # the state of charge reaches exactly 0.6 at t = 20.0, so the first negative robustness is
    # the next sample
    k = r["first_violation_index"]
    assert k == 201
    assert r["first_violation_time"] == pytest.approx(20.1)
    assert s["soc"][200] == pytest.approx(0.6)
    assert r["rho"][200] == pytest.approx(0.0, abs=1e-9)
    assert r["rho"][201] < 0
    # once violated it stays violated, because the running minimum never recovers
    assert all(r["violated"][k:])
    assert not any(r["violated"][:k])


def test_obstacle_monitor_stays_satisfied(trace_csv):
    s = scenario()
    r = replay(str(spec_path), str(trace_csv))["obstacle_safety"]
    assert np.allclose(r["rho"], np.minimum.accumulate(s["obstacle_distance"] - 0.5), atol=1e-9)
    assert r["first_violation_index"] is None
    assert min(r["rho"]) > 0


def test_liveness_monitor_flips_at_the_goal_and_respects_warmup(trace_csv):
    s = scenario()
    r = replay(str(spec_path), str(trace_csv))["goal_liveness"]
    # the window is 180 s and the trace is 32 s, so once[0,180] is the running maximum
    assert np.allclose(r["rho"], np.maximum.accumulate(s["goal"] - 0.5), atol=1e-9)
    assert r["rho"][279] == pytest.approx(-0.5)   # t = 27.9, goal not yet reached
    assert r["rho"][280] == pytest.approx(0.5)    # t = 28.0, goal reached
    # negative robustness before t = 28, but warmup is 180 s so nothing is reported in 32 s
    assert r["first_violation_index"] is None


def test_a_missing_signal_is_reported_not_guessed(tmp_path):
    p = tmp_path / "partial.csv"
    p.write_text("time,soc\n0.0,0.9\n0.1,0.5\n")
    res = replay(str(spec_path), str(p))
    assert res["goal_liveness"]["skipped"] == ["goal"]
    assert res["obstacle_safety"]["skipped"] == ["obstacle_distance"]
    assert res["soc_safety"]["first_violation_index"] == 1


def test_warmup_suppresses_a_violation_until_its_time():
    m = mon.Monitor("w", "historically (x >= 1)", ["x"], 0.1, warmup=0.5)
    out = [m.step({"x": 0.0})[1] for _ in range(8)]
    # samples at t = 0.0 .. 0.4 are inside the warmup, t = 0.5 onwards is not
    assert out == [False] * 5 + [True] * 3


# ------------------------------------------------------------------
# the range spec, over a trajectory in the range trial's CSV format

range_spec = root / "runtime" / "stl-observer" / "specs" / "range_safety.yaml"

RANGE_RATE = 60.0          # the range trial writes one row per physics step, at 60 Hz
SPEC_RATE = 20.0           # and the spec samples at 20 Hz


def range_trace(duration=40.0):
    """A run in the range trial's column order: t,x,y,z,roll,pitch,yaw,v."""
    t = np.arange(0.0, duration, 1.0 / RANGE_RATE)
    v = np.where(t >= 15.0, 0.02, 0.6)                    # stuck from 15 s on
    roll = 0.10 * np.sin(2 * np.pi * t / 7.0)             # never past 0.35
    pitch = 0.40 * np.exp(-((t - 10.0) / 1.0) ** 2)       # one excursion past 0.35
    yaw = np.zeros_like(t)
    x = np.cumsum(v / RANGE_RATE)
    return {"t": t, "x": x, "y": np.zeros_like(t), "z": np.zeros_like(t),
            "roll": roll, "pitch": pitch, "yaw": yaw, "v": v}


@pytest.fixture(scope="module")
def range_csv(tmp_path_factory):
    s = range_trace()
    p = tmp_path_factory.mktemp("range") / "trajectory.csv"
    cols = ["t", "x", "y", "z", "roll", "pitch", "yaw", "v"]
    np.savetxt(p, np.column_stack([s[c] for c in cols]), delimiter=",", fmt="%.6f",
               header=",".join(cols), comments="")
    return p


def test_the_range_spec_parses_and_names_its_three_obligations():
    cfg = yaml.safe_load(range_spec.read_text())
    assert cfg["rate"] == SPEC_RATE
    rate, ms, _ = mon.load_spec(str(range_spec))
    assert [m.name for m in ms] == ["roll_safety", "pitch_safety", "progress"]
    assert rate == SPEC_RATE


def test_a_60hz_trace_is_sampled_onto_the_spec_rate(range_csv):
    from replay_observer import read_csv, resample
    raw = read_csv(str(range_csv))
    assert len(raw["t"]) == 2400                      # 40 s at 60 Hz
    s = resample(raw, SPEC_RATE)
    assert len(s["t"]) == 800                         # 40 s at 20 Hz
    # every third row of the original, because 60 Hz decimates 3:1 onto 20 Hz
    assert np.allclose(s["v"], np.asarray(raw["v"])[::3])
    assert np.allclose(s["t"], np.asarray(raw["t"])[::3])


def test_a_trace_already_at_the_spec_rate_is_passed_through(trace_csv):
    from replay_observer import read_csv, resample
    raw = read_csv(str(trace_csv))
    s = resample(raw, RATE)
    assert len(s["soc"]) == len(raw["soc"])
    assert np.allclose(s["soc"], raw["soc"])


def test_the_attitude_obligations_are_the_running_minimum_of_the_margin(range_csv):
    from replay_observer import read_csv, resample
    s = resample(read_csv(str(range_csv)), SPEC_RATE)
    res = replay(str(range_spec), str(range_csv))

    r = res["roll_safety"]
    assert np.allclose(r["rho"], np.minimum.accumulate(0.35 - np.abs(s["roll"])), atol=1e-9)
    assert r["first_violation_index"] is None

    p = res["pitch_safety"]
    assert np.allclose(p["rho"], np.minimum.accumulate(0.35 - np.abs(s["pitch"])), atol=1e-9)
    # the excursion peaks at 0.40 rad at t = 10 s, so the margin goes negative on the way up
    k = p["first_violation_index"]
    assert k is not None
    assert abs(s["pitch"][k]) > 0.35
    assert abs(s["pitch"][k - 1]) <= 0.35
    assert p["first_violation_time"] == pytest.approx(k / SPEC_RATE)
    assert all(p["violated"][k:])


def test_the_progress_obligation_fires_one_window_after_the_robot_stops(range_csv):
    r = replay(str(range_spec), str(range_csv))["progress"]
    # v drops to 0.02 at t = 15 s and the window is 20 s, so the last fast sample leaves the
    # window at t = 35 s; warmup is 20 s, which is already past by then
    k = r["first_violation_index"]
    assert r["first_violation_time"] == pytest.approx(35.0, abs=1.0 / SPEC_RATE)
    assert r["rho"][k] == pytest.approx(0.02 - 0.2)
    assert not any(r["violated"][:k])


def test_the_range_trace_writer_uses_the_trial_column_order(tmp_path):
    import demo_range_trace
    p = demo_range_trace.write(str(tmp_path / "out" / "range_trajectory.csv"))
    header = open(p).readline().strip()
    assert header == "t,x,y,z,roll,pitch,yaw,v"
    table = np.loadtxt(p, delimiter=",", skiprows=1)
    assert table.shape == (3600, 8)
    assert table[1, 0] == pytest.approx(1.0 / 60.0, abs=1e-6)
