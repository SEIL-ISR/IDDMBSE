"""A synthetic stand-in for the learned detector.

In the lab pipeline this is YOLOv8 + DeepSORT running inside the SEIL-R2 Nav2
stack, and the ground truth comes from the Isaac Sim asset attributes. Here it
is a seeded noise model applied to the true boxes, chosen so that it reproduces
the two failure modes the paper points at: boxes that are displaced, and boxes
that are too small.

Noise model, per object and per frame, all draws independent:

  range r          distance from the robot to the object centre
  centre jitter    N(0, sigma) per axis, sigma = SIGMA0 + SIGMA_RANGE * r
  size factor      s ~ N(mu, sd) per axis, clipped to [S_MIN, S_MAX];
                   the detected half extent is s times the true half extent
  easy objects     mu = MU_EASY, sd = SD_EASY
  hard objects     mu = MU_HARD, sd = SD_HARD  (a fixed fraction of objects,
                   flagged once per world in cpnav.world.sample_worlds)
  range gate       objects farther than MAX_RANGE are not reported at all

The distribution-shift knob `shift` stands for the clutter and lighting sweeps
PERFECT would re-run the campaign under: it scales the jitter by (1 + shift)
and lowers the mean size factor by SHIFT_SHRINK * shift.
"""

import numpy as np

SIGMA0 = 0.04
SIGMA_RANGE = 0.010
MU_EASY = 0.95
SD_EASY = 0.02
MU_HARD = 0.50
SD_HARD = 0.10
S_MIN = 0.25
S_MAX = 1.10
MAX_RANGE = 10.0
SHIFT_SHRINK = 0.15


def detect(rng, boxes, valid, hard, robot_xy, shift=0.0):
    """One frame of detections.

    boxes (K, M, 4), valid (K, M), hard (K, M), robot_xy (K, 2).
    Returns det (K, M, 4), det_valid (K, M), rng_to_obj (K, M).
    """
    centre = 0.5 * (boxes[:, :, :2] + boxes[:, :, 2:])
    half = 0.5 * (boxes[:, :, 2:] - boxes[:, :, :2])

    dist = np.linalg.norm(centre - robot_xy[:, None, :], axis=2)
    sigma = (SIGMA0 + SIGMA_RANGE * dist) * (1.0 + shift)
    jitter = rng.normal(0.0, 1.0, size=centre.shape) * sigma[:, :, None]

    mu = np.where(hard, MU_HARD, MU_EASY) - SHIFT_SHRINK * shift
    sd = np.where(hard, SD_HARD, SD_EASY)
    factor = rng.normal(0.0, 1.0, size=half.shape) * sd[:, :, None] + mu[:, :, None]
    factor = np.clip(factor, S_MIN, S_MAX)

    det_centre = centre + jitter
    det_half = half * factor
    det = np.concatenate([det_centre - det_half, det_centre + det_half], axis=2)
    return det, valid & (dist <= MAX_RANGE), dist
