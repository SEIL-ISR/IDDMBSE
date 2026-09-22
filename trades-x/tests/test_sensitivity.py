import numpy as np
import pytest

from tradesx import sensitivity as sens

jax = pytest.importorskip("jax", reason="needs the ad extra: uv sync --extra ad")


# Julia reference values, printed by
#   julia --startup-file=no --project=. src/demo_sens.jl
# in trades-x/mbo on 2026-09-22, Julia 1.12.7, ForwardDiff.
DEMO_REFERENCE = {
    "lidar": (sens.lidar_coverage_demo, [100.0, 0.526, 0.5], 512570.7113782411,
              [15328.51710448496, 804868.0437228794, 9749.740263584072]),
    "rgb camera": (sens.cam_coverage_demo, [60.0, 1.047, 1.273, 0.5], 49338.69032334568,
                   [2448.81757184699, 56978.302689041404, 50472.87906023696, 2174.709800650854]),
    "depth camera": (sens.cam_coverage_demo, [6.0, 1.501, 0.9948, 0.5], 74.37853063569361,
                     [34.48986501200955, 75.02165488760312, 68.82687895442021, 33.313730481282235]),
    "laser": (sens.laser_coverage_demo, [4.71, 20.0, 0.1], 94.2,
              [20.0, 9.42, 942.0]),
}

# per-sensor oracle values, printed by
#   julia --startup-file=no --project=. -e 'include("src/util_data.jl"); ...'
# in trades-x/mbo on 2026-09-22.
JULIA_COVERAGE = np.array([512576.12879532785, 512576.12879532785, 884326.8222987555,
                           884326.8222987555, 471.0, 471.0, 2943.75, 2943.75,
                           37.54621381448355, 76.91871586737105, 74.37853063569361,
                           28678.26988444874, 49338.69032334568])
JULIA_COST = np.array([10000, 12000, 15000, 16000, 1000, 1500, 1500, 2000,
                       2000, 2500, 3000, 1500, 3000], dtype=float)
JULIA_RAM = np.array([33.75, 60.0, 78.732, 139.96800000000002, 4.5, 18.0, 4.5, 18.0,
                      3499.2, 4147.2, 2332.7999999999997, 3499.2, 3742.2000000000003])
JULIA_POWER = np.array([80.000000925155, 80.00000123354, 100.00000215820158,
                        100.00000287760211, 30.0000000740124, 30.0000001480248,
                        50.0000000740124, 50.0000001480248, 8.0000239800176,
                        8.0000568415232, 10.0000639467136, 3.0000479600352,
                        6.0001025811864])

EYE = np.eye(13)


@pytest.mark.parametrize("name", list(DEMO_REFERENCE))
def test_jax_gradient_matches_julia_forwarddiff(name):
    f, p, value, grad = DEMO_REFERENCE[name]
    assert abs(float(f(np.asarray(p))) - value) < 1e-6
    g = sens.demo_gradient(f, p)
    assert np.abs(g - np.asarray(grad)).max() < 1e-6


@pytest.mark.parametrize("name", list(DEMO_REFERENCE))
def test_jax_gradient_matches_finite_difference(name):
    f, p, _, _ = DEMO_REFERENCE[name]
    g = sens.demo_gradient(f, p)
    fd = sens.demo_finite_difference(f, p)
    assert np.abs(g - fd).max() <= 1e-4 * max(1.0, np.abs(g).max())


def test_oracles_match_julia_on_single_sensor_designs():
    assert np.abs(sens.coverage(EYE) - JULIA_COVERAGE).max() < 1e-9
    assert np.abs(sens.cost(EYE) - JULIA_COST).max() == 0.0
    assert np.abs(sens.ram(EYE) - JULIA_RAM).max() < 1e-9
    assert np.abs(sens.power(EYE) - JULIA_POWER).max() < 1e-9


def test_metrics_are_additive_over_slots():
    design = np.zeros(13)
    design[[0, 5, 9, 11]] = 1
    m = sens.metrics(design)[0]
    assert m[0] == JULIA_COST[[0, 5, 9, 11]].sum()
    assert m[3] == pytest.approx(-JULIA_COVERAGE[[0, 5, 9, 11]].sum())


def test_sensitivities_shape_and_support():
    design = np.zeros(13)
    design[[0, 10]] = 1
    j = sens.sensitivities(design)
    assert j.shape == (4, 13, 6)
    # a slot the design does not select cannot move any metric
    off = np.ones(13, dtype=bool)
    off[[0, 10]] = False
    assert np.abs(j[:, off, :]).max() == 0.0
    # cost depends only on the cost column
    cost_row = j[0]
    assert np.abs(np.delete(cost_row, 4, axis=1)).max() == 0.0
    assert cost_row[0, 4] == 1.0


def test_sensitivities_match_finite_difference_of_the_numpy_oracles():
    design = np.zeros(13)
    design[[2, 6, 10]] = 1
    j = sens.sensitivities(design)

    step = 1e-6 * np.maximum(np.abs(sens.PARAMS), 1.0)
    bumps = np.eye(sens.PARAMS.size).reshape(-1, 13, 6) * step
    up = sens.metrics_batch(design, sens.PARAMS + bumps)
    down = sens.metrics_batch(design, sens.PARAMS - bumps)
    fd = ((up - down) / (2 * step.reshape(-1)[:, None])).T.reshape(4, 13, 6)
    scale = np.maximum(np.abs(j), 1.0)
    assert (np.abs(j - fd) / scale).max() < 1e-5


def test_rank_parameters_is_ordered_by_magnitude():
    design = np.zeros(13)
    design[[0, 5, 9, 11]] = 1
    ranked = sens.rank_parameters(design, metric=3)
    values = [abs(e[3]) for e in ranked]
    assert values == sorted(values, reverse=True)
    assert ranked[0][1] == "VLP-16-A"


def test_rank_requirements_uses_the_metric_map():
    design = np.zeros(13)
    design[[0]] = 1
    out = sens.rank_requirements(design, {"Pr.1.2": "cost", "P.2": "coverage"})
    assert [e[0] for e in out] == ["P.2", "Pr.1.2"]
