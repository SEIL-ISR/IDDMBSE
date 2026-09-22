import numpy as np
from tradesx.bag_metrics import path_length, time_to_completion, cumulative_elevation_gradient


def test_straight_line_path_length():
    x = np.linspace(0.0, 3.0, 4)
    y = np.zeros(4)
    z = np.zeros(4)
    assert np.isclose(path_length(x, y, z), 3.0)


def test_diagonal_path_length():
    t = np.linspace(0.0, 1.0, 5)
    assert np.isclose(path_length(t, t, t), np.sqrt(3.0))


def test_time_to_completion():
    t = np.array([100.0, 101.0, 105.5])
    assert np.isclose(time_to_completion(t), 5.5)


def test_ramp_elevation_gradient():
    # unit-spaced ramp: every central difference equals the step
    z = np.arange(10) * 0.25
    assert np.isclose(cumulative_elevation_gradient(z), 10 * 0.25)


def test_sine_elevation_gradient():
    n = 64
    amp = 2.0
    th = 2 * np.pi * np.arange(n) / n
    z = amp * np.sin(th)
    # closed form for numpy/MATLAB gradient on unit spacing:
    # interior central difference (z[k+1]-z[k-1])/2 = amp*cos(th[k])*sin(2*pi/n)
    interior = amp * np.cos(th[1:-1]) * np.sin(2 * np.pi / n)
    expected = abs(z[1] - z[0]) + abs(z[-1] - z[-2]) + np.abs(interior).sum()
    assert np.isclose(cumulative_elevation_gradient(z), expected)
