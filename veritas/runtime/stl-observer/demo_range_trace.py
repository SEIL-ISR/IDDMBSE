"""Write a range trajectory CSV for the replay observer to run over.

The file has the header the Isaac Sim range trial writes -- `t,x,y,z,roll,pitch,yaw,v`, the
pose in metres and radians and the speed in m/s -- and holds a run made up here, at the range
trial's 60 Hz over 60 simulated seconds: the robot drives at its commanded 0.6 m/s, crosses a
slope that tilts it past 20 degrees in pitch at about 22 s, and then sits at 0.02 m/s from
25 s to 50 s, which is longer than the progress obligation's 20 s window.

    uv run python runtime/stl-observer/demo_range_trace.py
    uv run python runtime/stl-observer/replay_observer.py \
        runtime/stl-observer/demo_out/range_trajectory.csv \
        --spec runtime/stl-observer/specs/range_safety.yaml --every 200
"""

import os

import numpy as np

RATE, DURATION = 60.0, 60.0


def trace(rate=RATE, duration=DURATION):
    """The run as whole arrays, one row per physics step."""
    t = np.arange(0.0, duration, 1.0 / rate)
    v = np.where((t >= 25.0) & (t < 50.0), 0.02, 0.6)
    roll = 0.15 * np.sin(2 * np.pi * t / 9.0)
    pitch = 0.10 * np.sin(2 * np.pi * t / 15.0) + 0.38 * np.exp(-((t - 22.0) / 1.2) ** 2)
    yaw = 0.10 * np.sin(2 * np.pi * t / 20.0)
    step = v / rate
    x = np.cumsum(step * np.cos(yaw))
    y = np.cumsum(step * np.sin(yaw))
    z = 0.4 * np.sin(2 * np.pi * t / 40.0)
    return np.column_stack([t, x, y, z, roll, pitch, yaw, v])


def write(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savetxt(path, trace(), delimiter=",", fmt="%.6f",
               header="t,x,y,z,roll,pitch,yaw,v", comments="")
    return path


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = write(os.path.join(here, "demo_out", "range_trajectory.csv"))
    table = trace()
    print("wrote " + out + ": " + str(table.shape[0]) + " rows at " + str(RATE) + " Hz over "
          + str(DURATION) + " s")
    print("max |roll| " + str(round(np.abs(table[:, 4]).max(), 4))
          + " rad, max |pitch| " + str(round(np.abs(table[:, 5]).max(), 4))
          + " rad, speed " + str(round(table[:, 7].min(), 3)) + " to "
          + str(round(table[:, 7].max(), 3)) + " m/s")
