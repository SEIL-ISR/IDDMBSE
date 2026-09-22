import numpy as np
import pytest

from cpnav import conformal


def test_quantile_hand_checked_ten_scores():
    # Ten scores, already sorted for readability. k = ceil((n + 1)(1 - alpha))
    # with n = 10, so k = ceil(11 * (1 - alpha)) and the answer is the k-th
    # smallest score.
    s = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    assert conformal.quantile(s, 0.5) == pytest.approx(0.6)      # k = ceil(5.5) = 6
    assert conformal.quantile(s, 0.3) == pytest.approx(0.8)      # k = ceil(7.7) = 8
    assert conformal.quantile(s, 0.2) == pytest.approx(0.9)      # k = ceil(8.8) = 9
    assert conformal.quantile(s, 0.1) == pytest.approx(1.0)      # k = ceil(9.9) = 10
    assert conformal.quantile(s, 0.05) == np.inf                 # k = ceil(10.45) = 11 > n


def test_quantile_ignores_input_order():
    s = np.array([0.7, 0.1, 1.0, 0.3, 0.9, 0.2, 0.6, 0.4, 0.8, 0.5])
    assert conformal.quantile(s, 0.3) == pytest.approx(0.8)


def test_inflate_contains_truth_exactly_when_score_leq_q():
    rng = np.random.default_rng(3)
    truth = np.array([2.0, 3.0, 5.0, 6.5])
    det = truth + rng.normal(0.0, 0.5, size=(4000, 4))
    s = conformal.scores(det, truth)
    q = 0.37
    grown = conformal.inflate(det, q)
    contains = np.all(
        (grown[:, :2] <= truth[:2]) & (truth[2:] <= grown[:, 2:]), axis=1
    )
    assert np.array_equal(contains, s <= q)


def test_score_is_the_smallest_covering_inflation():
    truth = np.array([0.0, 0.0, 2.0, 2.0])
    det = np.array([0.3, -0.1, 1.5, 2.4])
    # edges needed: 0.3 - 0 = 0.3, -0.1 - 0 = -0.1, 2 - 1.5 = 0.5, 2 - 2.4 = -0.4
    assert conformal.scores(det, truth) == pytest.approx(0.5)


def test_coverage_reaches_the_target_on_a_calibration_split():
    # n = 2000 calibration scores and 20000 test scores from the same law.
    # Marginal coverage should be at least 1 - alpha up to sampling error; the
    # binomial tolerance below is 4 standard deviations of the test mean.
    rng = np.random.default_rng(11)
    truth = np.array([1.0, 1.0, 3.0, 4.0])
    alpha = 0.1
    cal = truth + rng.normal(0.0, 0.4, size=(2000, 4))
    test = truth + rng.normal(0.0, 0.4, size=(20000, 4))
    q = conformal.quantile(conformal.scores(cal, truth), alpha)
    cov = conformal.coverage(test, truth, q)
    tol = 4.0 * np.sqrt(alpha * (1 - alpha) / 20000)
    assert cov >= 1 - alpha - tol
    assert cov <= 1 - alpha + 0.03
