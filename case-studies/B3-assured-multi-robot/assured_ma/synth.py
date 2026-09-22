"""Solve the STL-constrained MILP with HiGHS and pull the planned trajectories out.

`scipy.optimize.milp` is a wrapper around HiGHS, which is open source (MIT). The
lab's own scripts for the nearest relative of this problem use Gurobi; nothing here
needs a commercial licence. See README.md.
"""

import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from . import encode


def synthesise(prob, spec_by_robot, mip_rel_gap=0.0, time_limit=600.0):
    """Build and solve the MILP. Returns the plan plus the solver's own numbers."""
    enc = encode.build(prob, spec_by_robot)
    t0 = time.perf_counter()
    res = milp(c=enc.c,
               constraints=LinearConstraint(enc.A, enc.blo, enc.bhi),
               integrality=enc.integrality,
               bounds=Bounds(enc.vlb, enc.vub),
               options={"mip_rel_gap": mip_rel_gap, "time_limit": time_limit,
                        "presolve": True, "disp": False})
    out = {"status": int(res.status), "message": str(res.message),
           "wall_s": time.perf_counter() - t0,
           "n_var": int(enc.pool.n), "n_bin": enc.n_binary, "n_con": int(enc.rows.n),
           "nnz": int(enc.A.nnz), "mip_gap": getattr(res, "mip_gap", None),
           "encoding": enc}
    if res.x is not None:
        x = np.asarray(res.x, float)
        out["plan"] = x[enc.ipos]
        out["vel"] = x[enc.ivel]
        out["acc"] = x[enc.iacc]
        out["z_root"] = x[enc.roots]
    return out
