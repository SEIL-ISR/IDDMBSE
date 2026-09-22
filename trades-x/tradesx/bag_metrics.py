"""Global (data-driven) metrics computed from a recorded robot trajectory.

Ported from the MATLAB rosbag evaluators in sysml/iddmbse_v2/
(rosbageval_perfect.m, MBO_rosbag_evals.m, pareto_mavf_behav.m,
MBO_rosbag_statisticalMAVF_evals.m), which read /odometry/filtered and reduced
each run to path length, time to completion and cumulative elevation gradient.

These functions take plain arrays, so they carry no bag-reader dependency.
To get the arrays:

  ROS 1 .bag   - rosbag.Bag(path).read_messages("/odometry/filtered") and pull
                 msg.pose.pose.position.{x,y,z} and the header stamp.
  ROS 2 .mcap  - rosbag2_py.SequentialReader over the mcap, deserialise
                 nav_msgs/msg/Odometry, same fields.

Stack each into a 1-D numpy array of equal length and pass them in.
"""

import numpy as np


def path_length(x, y, z=None):
    """Arc length of the trajectory as a sum of chord lengths.

    Matches the 'linear' default of the MATLAB `arclength` helper the
    evaluators used.
    """
    cols = [np.asarray(x, dtype=float), np.asarray(y, dtype=float)]
    if z is not None:
        cols.append(np.asarray(z, dtype=float))
    p = np.column_stack(cols)
    if p.ndim != 2 or p.shape[0] < 2:
        raise ValueError("need at least two trajectory points")
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    return float(seg.sum())


def time_to_completion(t):
    """Last timestamp minus first, in the units of `t` (the MATLAB code used
    the integer seconds field of the header stamp)."""
    tt = np.asarray(t, dtype=float)
    if tt.size < 2:
        raise ValueError("need at least two timestamps")
    return float(tt[-1] - tt[0])


def cumulative_elevation_gradient(z):
    """sum(abs(gradient(z))) with unit sample spacing.

    numpy.gradient uses the same central-difference-interior, one-sided-ends
    scheme as MATLAB's gradient, so this reproduces the MATLAB CEG value.
    """
    zz = np.asarray(z, dtype=float)
    if zz.size < 2:
        raise ValueError("need at least two elevation samples")
    return float(np.abs(np.gradient(zz)).sum())
