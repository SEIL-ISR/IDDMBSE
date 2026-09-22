import numpy as np
from tradesx.pareto import non_dominated, non_dominated_matlab_compat


def brute_force_non_dominated(x, sense):
    """Brute-force test oracle: explicit double loop over designs.

    This is the only place in the package where designs are looped over in
    native Python. It exists to differential-test the vectorised filter.
    """
    y = x * np.asarray(sense, dtype=float)
    n = y.shape[0]
    keep = []
    for j in range(n):
        dominated = False
        for i in range(n):
            if i == j:
                continue
            if all(y[i, m] >= y[j, m] for m in range(y.shape[1])) and \
               any(y[i, m] > y[j, m] for m in range(y.shape[1])):
                dominated = True
                break
        if not dominated:
            keep.append(j)
    return np.array(keep)


def test_hand_checked_five_points():
    # minimise both metrics
    m = np.array([[1.0, 5.0], [2.0, 3.0], [3.0, 1.0], [4.0, 4.0], [5.0, 6.0]])
    mask, idx = non_dominated(m, [-1, -1])
    assert idx.tolist() == [0, 1, 2]
    assert mask.tolist() == [True, True, True, False, False]


def test_sense_vector_flips_the_answer():
    m = np.array([[1.0, 5.0], [2.0, 3.0], [3.0, 1.0], [4.0, 4.0], [5.0, 6.0]])
    _, idx = non_dominated(m, [1, 1])
    assert idx.tolist() == [4]


def test_matlab_compat_drops_duplicates():
    # same five points with a duplicate of row 1
    m = np.array([[1.0, 5.0], [2.0, 3.0], [2.0, 3.0], [3.0, 1.0], [4.0, 4.0]])
    _, std = non_dominated(m, [-1, -1])
    _, compat = non_dominated_matlab_compat(m, [-1, -1])
    assert std.tolist() == [0, 1, 2, 3]
    assert compat.tolist() == [0, 3]


def test_matches_brute_force_on_random_data():
    rng = np.random.default_rng(0)
    m = rng.normal(size=(300, 4))
    sense = [-1, -1, -1, 1]
    _, idx = non_dominated(m, sense)
    assert np.array_equal(idx, brute_force_non_dominated(m, sense))


def test_matches_brute_force_with_ties():
    rng = np.random.default_rng(1)
    m = rng.integers(0, 3, size=(300, 4)).astype(float)
    sense = [-1, -1, -1, -1]
    _, idx = non_dominated(m, sense)
    assert np.array_equal(idx, brute_force_non_dominated(m, sense))


def test_default_sense_is_minimise_all():
    m = np.array([[1.0, 1.0], [2.0, 2.0]])
    _, idx = non_dominated(m)
    assert idx.tolist() == [0]
