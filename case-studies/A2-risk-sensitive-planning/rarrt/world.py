"""Seeded planar worlds with circular obstacles, and exact segment clearance.

The world generator is synthetic: it is not a map of anything.  Obstacles are
discs placed by a Boolean model whose intensity is set from a target coverage,
with a keep-out around the start and the goal.
"""

import numpy as np


class World:
    def __init__(self, half_width, centers, radii, start, goal):
        self.half_width = float(half_width)
        self.centers = np.asarray(centers, dtype=float).reshape(-1, 2)
        self.radii = np.asarray(radii, dtype=float).reshape(-1)
        self.start = np.asarray(start, dtype=float)
        self.goal = np.asarray(goal, dtype=float)

    @property
    def n_obstacles(self):
        return self.radii.size

    def segment_clearance(self, a, b):
        """Smallest clearance along each segment a[i] -> b[i], shape (B,).

        Clearance is the distance to the nearest obstacle surface, negative
        inside an obstacle, and is also capped by the distance to the domain
        boundary.  For discs the minimum over a segment is exact: the closest
        point of the segment to a disc centre is the projection, clamped to the
        segment.  For the box boundary the distance is concave inside, so its
        minimum over a segment is attained at an endpoint.
        """
        a = np.atleast_2d(np.asarray(a, dtype=float))
        b = np.atleast_2d(np.asarray(b, dtype=float))
        d = b - a
        dd = np.maximum((d * d).sum(axis=1), 1e-18)

        if self.n_obstacles:
            ac = self.centers[None, :, :] - a[:, None, :]
            t = np.clip((ac * d[:, None, :]).sum(axis=-1) / dd[:, None], 0.0, 1.0)
            closest = a[:, None, :] + t[..., None] * d[:, None, :]
            dist = np.linalg.norm(self.centers[None, :, :] - closest, axis=-1)
            obstacle = (dist - self.radii[None, :]).min(axis=1)
        else:
            obstacle = np.full(a.shape[0], np.inf)

        border = np.minimum(
            (self.half_width - np.abs(a)).min(axis=1),
            (self.half_width - np.abs(b)).min(axis=1),
        )
        return np.minimum(obstacle, border)

    def collision_free(self, a, b):
        return self.segment_clearance(a, b) > 0.0


def make_world(coverage, seed, half_width=32.0, r_min=1.2, r_max=4.0,
               start=(-28.0, -28.0), goal=(28.0, 28.0), keep_out=4.0):
    """A world whose obstacle discs cover about `coverage` of the domain.

    A Boolean model of intensity lam covers a fraction 1 - exp(-lam * E[area]),
    so the obstacle count follows from the target coverage.  Discs that would
    swallow the start or the goal are dropped, which lowers the realised
    coverage slightly; `free_fraction` measures what was actually achieved.
    """
    rng = np.random.default_rng(seed)
    area = (2.0 * half_width) ** 2
    mean_disc = np.pi * (r_max ** 3 - r_min ** 3) / (3.0 * (r_max - r_min))
    count = int(round(-area * np.log1p(-coverage) / mean_disc))

    centers = rng.uniform(-half_width, half_width, size=(count, 2))
    radii = rng.uniform(r_min, r_max, size=count)
    ends = np.array([start, goal], dtype=float)
    gap = np.linalg.norm(centers[:, None, :] - ends[None, :, :], axis=-1) - radii[:, None]
    keep = (gap > keep_out).all(axis=1)
    return World(half_width, centers[keep], radii[keep], start, goal)


def free_fraction(world, resolution=512):
    """Fraction of the domain not inside an obstacle, on a regular grid."""
    axis = np.linspace(-world.half_width, world.half_width, resolution)
    gx, gy = np.meshgrid(axis, axis, indexing="ij")
    pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
    blocked = np.zeros(pts.shape[0], dtype=bool)
    # tiled over obstacles only to bound the size of the distance array
    for lo in range(0, world.n_obstacles, 16):
        c = world.centers[lo:lo + 16]
        r = world.radii[lo:lo + 16]
        dist = np.linalg.norm(pts[:, None, :] - c[None, :, :], axis=-1)
        blocked |= (dist <= r[None, :]).any(axis=1)
    return float(1.0 - blocked.mean())
