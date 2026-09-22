import numpy as np
import pytest
from scipy.stats import norm

from rarrt.risk import value_at_risk, conditional_value_at_risk, entropic_value_at_risk

BIG = np.random.default_rng(0).standard_normal(2_000_000)


@pytest.mark.parametrize("alpha", [0.5, 0.8, 0.9, 0.95, 0.99])
def test_cvar_matches_the_gaussian_closed_form(alpha):
    # CVaR_alpha(N(0,1)) = phi(Phi^-1(alpha)) / (1 - alpha)
    exact = norm.pdf(norm.ppf(alpha)) / (1.0 - alpha)
    got = conditional_value_at_risk(BIG, alpha)
    # 2e6 samples; 0.01 is about 0.6 % of the smallest of these values
    assert abs(got - exact) < 0.01


@pytest.mark.parametrize("alpha", [0.5, 0.9, 0.99])
def test_var_matches_the_gaussian_closed_form(alpha):
    assert abs(value_at_risk(BIG, alpha) - norm.ppf(alpha)) < 0.01


def test_cvar_at_alpha_zero_is_the_mean():
    assert conditional_value_at_risk(BIG, 0.0) == pytest.approx(BIG.mean())


def test_cvar_is_at_least_the_mean_and_rises_with_alpha():
    levels = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
    values = np.array([conditional_value_at_risk(BIG, a) for a in levels])
    assert (values >= BIG.mean() - 1e-12).all()
    assert (np.diff(values) > 0.0).all()


def test_cvar_dominates_var():
    for alpha in [0.5, 0.9, 0.99]:
        assert conditional_value_at_risk(BIG, alpha) > value_at_risk(BIG, alpha)


def test_cvar_is_positively_homogeneous():
    # the planner relies on this: CVaR(L * M) = L * CVaR(M) for L > 0
    x = np.random.default_rng(1).standard_normal(50_000) + 3.0
    assert conditional_value_at_risk(7.5 * x, 0.9) == pytest.approx(
        7.5 * conditional_value_at_risk(x, 0.9))


def test_cvar_vectorises_over_rows():
    x = np.random.default_rng(2).standard_normal((17, 4000))
    batched = conditional_value_at_risk(x, 0.9, axis=-1)
    # brute-force oracle: one row at a time
    one_by_one = np.array([conditional_value_at_risk(row, 0.9) for row in x])
    assert np.allclose(batched, one_by_one)


@pytest.mark.parametrize("alpha", [0.5, 0.9, 0.95])
def test_evar_matches_the_gaussian_closed_form(alpha):
    # EVaR_alpha(N(mu, s^2)) = mu + s * sqrt(2 log(1/(1-alpha)))
    exact = 2.0 + 1.5 * np.sqrt(2.0 * np.log(1.0 / (1.0 - alpha)))
    got = entropic_value_at_risk(2.0 + 1.5 * BIG[:400_000], alpha)
    assert abs(got - exact) < 0.05


def test_evar_dominates_cvar():
    for alpha in [0.5, 0.9, 0.95]:
        sample = BIG[:400_000]
        assert entropic_value_at_risk(sample, alpha) > conditional_value_at_risk(sample, alpha)
