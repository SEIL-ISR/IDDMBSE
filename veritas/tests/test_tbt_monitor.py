"""The behavior-tree monitor on the synthetic pick-and-place traces.

The expected verdicts are read off the vendored code, not off a recorded run:

* panda_specifications.py:51-55

      def get_status(rho):
          if rho > 0:
              return 1
          else:
              return 0

  so a leaf reports only 1 (satisfied) or 0 (running). It never reports -1.

* tbt_monitor.py:34-39 is the only route by which compose_seq reaches -1:

      if state==-1: # failure
          ...
          self._prev_state=-1
          ...
          return min(self._rob), -1

  Its guard is the leaf's state, so with these leaf specifications the sequence can
  never report failure. A trace that never grasps therefore stays at 0 (running, i.e.
  the verdict is still unknown) for the whole episode.

* tbt_monitor.py:29-30

      if self._prev_state==1: # seq has succeeded
          return min(self._rob), 1

  latches success, so the state sequence is non-decreasing.
"""

import numpy as np

import demo_synthetic


def test_full_trace_succeeds():
    out = demo_synthetic.run(demo_synthetic.make_trace(grasp_closes=True))
    states = np.array([state for _, state in out])

    assert set(np.unique(states)) <= {0, 1}
    assert np.all(np.diff(states) >= 0)
    assert states[-1] == 1
    # the sequence reports success exactly once, and stays there
    assert np.all(states[np.argmax(states == 1):] == 1)

    rho = out[-1][0]
    assert rho > 0


def test_ungrasped_trace_stays_unknown():
    out = demo_synthetic.run(demo_synthetic.make_trace(grasp_closes=False))
    states = np.array([state for _, state in out])

    # no failure verdict is reachable with these leaf specifications, and the grasp leaf
    # never succeeds, so the sequence never leaves 0
    assert np.all(states == 0)

    # the reported robustness is the grasp margin, which is negative for a gripper that
    # stays open at 0.08 against the threshold 0.05
    rho = out[-1][0]
    assert rho < 0
    assert np.isclose(rho, 0.05 - 0.08)


def test_reach_leaf_succeeds_before_the_sequence_does():
    trace = demo_synthetic.make_trace(grasp_closes=True)
    out = demo_synthetic.run(trace)
    rhos = np.array([rho for rho, _ in out])
    states = np.array([state for _, state in out])

    # the first positive robustness is the reach leaf clearing its threshold; the
    # sequence is still running there because two leaves remain
    first_positive = int(np.argmax(rhos > 0))
    assert states[first_positive] == 0
    assert first_positive < int(np.argmax(states == 1))
