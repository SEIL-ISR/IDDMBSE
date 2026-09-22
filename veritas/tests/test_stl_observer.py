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
