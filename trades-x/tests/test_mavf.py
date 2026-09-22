import numpy as np
import pytest
from tradesx.mavf import savf, mavf, rank


def test_hand_checked_three_by_two():
    m = np.array([[10.0, 1.0], [20.0, 3.0], [30.0, 2.0]])
    sense = [-1, 1]
    v = savf(m, sense)
    assert np.allclose(v, [[1.0, 0.0], [0.5, 1.0], [0.0, 0.5]])
    s = mavf(m, [0.5, 0.5], sense)
    assert np.allclose(s, [0.5, 0.75, 0.25])
    order, scores = rank(m, [0.5, 0.5], sense)
    assert order.tolist() == [1, 0, 2]
    assert np.allclose(scores, s)


def test_constant_column_is_neutral():
    m = np.array([[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]])
    v = savf(m, [-1, -1])
    assert np.allclose(v[:, 1], 1.0)


def test_weights_must_sum_to_one():
    m = np.array([[1.0, 2.0], [3.0, 4.0]])
    with pytest.raises(ValueError):
        mavf(m, [0.5, 0.2], [-1, -1])


def test_shape_mismatch_rejected():
    m = np.array([[1.0, 2.0], [3.0, 4.0]])
    with pytest.raises(ValueError):
        mavf(m, [1.0], [-1])
