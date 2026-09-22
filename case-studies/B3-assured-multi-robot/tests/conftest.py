import numpy as np
import pytest

from assured_ma import encode


@pytest.fixture
def small_problem():
    def make(starts, N=8, dt=0.5, v_max=1.0, a_max=1.5, ws=(4.0, 4.0), rho_cap=1.0):
        return encode.Problem(N=N, dt=dt, v_max=v_max, a_max=a_max,
                              ws_lo=np.zeros(2), ws_hi=np.array(ws, float),
                              starts=np.atleast_2d(np.array(starts, float)),
                              rho_cap=rho_cap, effort_weight=1e-3)
    return make
