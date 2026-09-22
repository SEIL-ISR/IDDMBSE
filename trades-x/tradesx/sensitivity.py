"""Sensor-suite oracles in Python, and their sensitivity to the design parameters.

Built for this release. The recorded study did the differentiation in Julia
(`mbo/src/demo_sens.jl`, `mbo/src/sens_fd.jl`, ForwardDiff cross-checked with
FiniteDifferences). This module is the Python side of the same calculation:
numpy for the batch scoring, JAX for the derivatives.

The oracles are ports of `mbo/src/oracles.jl`:

    cost_oracle        sum of the per-sensor prices
    ram_oracle         T * update_rate * per-sensor data rate, in MB
    power_oracle       passive draw plus a storage term
    coverage_oracle    sum of the per-sensor sensed volumes, in m^3

`effective_coverage_oracle` is deliberately not ported. It walks the design in
slot order and mutates the sensor catalogue as it merges ranges and fields of
view, so it is neither a pure function of the design nor differentiable in the
usual sense. The MBO enumeration uses it; the sensitivity analysis uses the
plain `coverage` above, which is what the Julia sensitivity scripts differentiate
as well.

JAX is an optional dependency, installed with the `ad` extra:

    uv sync --extra ad

Everything in this module that does not differentiate works without it.
"""

import numpy as np

H_PLATFORM = 0.5
V_FOV_CAMERA = 1.273

LIDAR, LASER, DEPTH, CAMERA = 0, 1, 2, 3

NAMES = ["VLP-16-A", "VLP-16-B", "HDL-32E-A", "HDL-32E-B",
         "LMS111-a2", "LMS111-b1", "LMS151-a2", "LMS151-b2",
         "D415", "D435", "D455", "Blackfly-A", "Blackfly-B"]

KIND = np.array([LIDAR, LIDAR, LIDAR, LIDAR,
                 LASER, LASER, LASER, LASER,
                 DEPTH, DEPTH, DEPTH,
                 CAMERA, CAMERA])

# fixed integer specification, not part of the differentiable parameter vector
CHANNELS = np.array([16, 16, 32, 32, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype=float)
SAMPLES = np.array([1875, 1875, 2187, 2187, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype=float)
WIDTH = np.array([0, 0, 0, 0, 0, 0, 0, 0, 540, 1280, 1920, 720, 1540], dtype=float)
HEIGHT = np.array([0, 0, 0, 0, 0, 0, 0, 0, 360, 720, 1080, 540, 1080], dtype=float)
LASER_SAMPLES = 720.0

# the differentiable parameter vector, one row per sensor
PARAM_NAMES = ["update_rate", "h_fov", "v_fov", "max_range", "cost", "power"]

PARAMS = np.array([
    [15.0, 2 * np.pi, 0.526, 100.0, 10000.0, 80.0],
    [20.0, 2 * np.pi, 0.526, 100.0, 12000.0, 80.0],
    [15.0, 2 * np.pi, 0.526, 120.0, 15000.0, 100.0],
    [20.0, 2 * np.pi, 0.526, 120.0, 16000.0, 100.0],
    [25.0, 4.71, 1.57, 20.0, 1000.0, 30.0],
    [50.0, 4.71, 1.57, 20.0, 1500.0, 30.0],
    [25.0, 4.71, 1.57, 50.0, 1500.0, 50.0],
    [50.0, 4.71, 1.57, 50.0, 2000.0, 50.0],
    [60.0, 1.1345, 0.6981, 6.0, 2000.0, 8.0],
    [30.0, 1.5184, 1.0122, 6.0, 2500.0, 8.0],
    [15.0, 1.501, 0.9948, 6.0, 3000.0, 10.0],
    [30.0, 1.047, 0.5, 50.0, 1500.0, 3.0],
    [15.0, 1.047, 0.5, 60.0, 3000.0, 6.0],
])

N_SENSORS = PARAMS.shape[0]


# ------------------------------------------------------------------
# per-sensor quantities, written against a numerical module so the same code
# serves numpy (batch scoring) and jax.numpy (differentiation)

def _sensor_data_rate(params, xp):
    """Per-sensor data rate in MB per update, the `sensor_ram_oracle` of oracles.jl."""
    rate = params[..., 0]
    lidar = rate * SAMPLES * CHANNELS / 1e6
    laser = rate * LASER_SAMPLES * 2 / 1e6
    depth = rate * WIDTH * HEIGHT * 8 / (8 * 1e6)
    camera = rate * WIDTH * HEIGHT * 16 / (8 * 1e6)
    return xp.where(KIND == LIDAR, lidar,
                    xp.where(KIND == LASER, laser,
                             xp.where(KIND == DEPTH, depth, camera)))


def _sensor_coverage(params, xp):
    """Per-sensor sensed volume in m^3, the `sensor_coverage_oracle` of oracles.jl."""
    h_fov = params[..., 1]
    v_fov = params[..., 2]
    r = params[..., 3]
    b = H_PLATFORM

    th = v_fov / 2
    lidar = (2 * (np.pi / 3) * (h_fov / (2 * np.pi)) * r ** 3 * xp.cos(th) ** 2 * xp.sin(th)
             + (np.pi / 3) * r ** 2 * b * xp.cos(th) ** 2
             - (np.pi / 3) * b ** 3 / xp.tan(th) ** 2)

    laser = (h_fov / 2) * r ** 2 * b

    depth = ((np.pi / 6) * r * xp.tan(h_fov / 2) * (r ** 2 * xp.tan(th) + 2 * b * r)
             - b ** 2 / xp.tan(th))

    tv = V_FOV_CAMERA / 2
    camera = ((np.pi / 6) * r * xp.tan(h_fov / 2) * (r ** 2 * np.tan(tv) + 2 * b * r)
              - b ** 2 / np.tan(tv))

    return xp.where(KIND == LIDAR, lidar,
                    xp.where(KIND == LASER, laser,
                             xp.where(KIND == DEPTH, depth, camera)))


# ------------------------------------------------------------------
# design-level oracles, vectorised over a batch of designs

def _as_designs(designs):
    d = np.atleast_2d(np.asarray(designs, dtype=float))
    if d.shape[1] != N_SENSORS:
        raise ValueError("a design is a 13-slot selection vector")
    return d


def cost(designs, params=PARAMS):
    """Total price of every design, in dollars. designs: (n, 13) selection matrix."""
    return _as_designs(designs) @ params[:, 4]


def ram(designs, t_storage=5.0, params=PARAMS):
    """Data volume over `t_storage` seconds, in MB."""
    per = t_storage * params[:, 0] * _sensor_data_rate(params, np)
    return _as_designs(designs) @ per


def power(designs, params=PARAMS):
    """Passive draw plus the storage term, in W."""
    d = _as_designs(designs)
    passive = d @ params[:, 5]
    storage = d @ _sensor_data_rate(params, np)
    return passive + 0.77 * 2.67 * storage / 1e6


def coverage(designs, params=PARAMS):
    """Sum of the per-sensor sensed volumes, in m^3. No overlap subtraction."""
    return _as_designs(designs) @ _sensor_coverage(params, np)


def metrics(designs, t_storage=5.0, params=PARAMS):
    """(n, 4) table as cost, RAM, power, -coverage, the plot4met.csv convention."""
    return np.column_stack([cost(designs, params), ram(designs, t_storage, params),
                            power(designs, params), -coverage(designs, params)])


def metrics_batch(design, params_batch, t_storage=5.0):
    """The four metrics of one design over a batch of parameter matrices.

    `params_batch` has shape (..., 13, 6); the result has shape (..., 4). This
    is what lets the finite-difference check on `sensitivities` evaluate all
    2 * 13 * 6 perturbed parameter sets in two calls instead of a loop.
    """
    d = np.asarray(design, dtype=float)
    p = np.asarray(params_batch, dtype=float)
    rate = _sensor_data_rate(p, np)
    c = (p[..., 4] * d).sum(-1)
    r = (t_storage * p[..., 0] * rate * d).sum(-1)
    w = (p[..., 5] * d).sum(-1) + 0.77 * 2.67 * (rate * d).sum(-1) / 1e6
    v = (_sensor_coverage(p, np) * d).sum(-1)
    return np.stack([c, r, w, -v], axis=-1)


# ------------------------------------------------------------------
# derivatives

def _jax():
    import jax
    jax.config.update("jax_enable_x64", True)
    return jax


def metrics_one(params, design, t_storage=5.0):
    """The four metrics of one design, as a length-4 jax array of `params`.

    Written for `jax.jacfwd`: `params` is the (13, 6) parameter matrix and
    `design` the fixed 13-slot selection vector.
    """
    import jax.numpy as jnp
    d = jnp.asarray(design, dtype=float)
    rate = _sensor_data_rate(params, jnp)
    c = d @ params[..., 4]
    r = d @ (t_storage * params[..., 0] * rate)
    p = d @ params[..., 5] + 0.77 * 2.67 * (d @ rate) / 1e6
    v = d @ _sensor_coverage(params, jnp)
    return jnp.stack([c, r, p, -v])


def sensitivities(design, params=PARAMS, t_storage=5.0):
    """Jacobian of the four local metrics with respect to the design parameters.

    Returns a (4, 13, 6) array: entry [m, i, j] is d(metric m)/d(parameter j of
    sensor i), taken at `params`. Metric order is cost, RAM, power, -coverage;
    parameter order is `PARAM_NAMES`.
    """
    jax = _jax()
    import jax.numpy as jnp
    f = lambda p: metrics_one(p, design, t_storage)
    return np.asarray(jax.jacfwd(f)(jnp.asarray(params, dtype=float)))


def relative_sensitivities(design, params=PARAMS, t_storage=5.0):
    """`sensitivities` scaled by the parameter value: p * d(metric)/dp.

    That scaling is what makes parameters in different units comparable; the
    entry is how much the metric moves for a unit relative move in the
    parameter. Only the slots the design selects are non-zero.
    """
    j = sensitivities(design, params, t_storage)
    return j * np.asarray(params)[None, :, :]


def rank_parameters(design, params=PARAMS, t_storage=5.0, metric=None):
    """Design parameters ordered by relative sensitivity magnitude, largest first.

    Returns a list of (metric name, sensor name, parameter name, value). With
    `metric` given (0..3) only that metric's row is ranked.
    """
    rel = relative_sensitivities(design, params, t_storage)
    names = ["cost", "RAM", "power", "-coverage"]
    rows = range(4) if metric is None else [metric]
    out = []
    for m in rows:
        block = rel[m]
        order = np.argsort(-np.abs(block), axis=None)
        for flat in order:
            i, j = np.unravel_index(flat, block.shape)
            if block[i, j] == 0:
                continue
            out.append((names[m], NAMES[i], PARAM_NAMES[j], float(block[i, j])))
    out.sort(key=lambda e: -abs(e[3]))
    return out


def rank_requirements(design, metric_of, params=PARAMS, t_storage=5.0):
    """Requirements ordered by the sensitivity of the metric that checks them.

    `metric_of` maps a requirement id to one of "cost", "RAM", "power",
    "coverage" — `tradesx.requirements.metric_map` builds it from
    requirements.yaml. A requirement's score is the largest relative sensitivity
    magnitude over the parameters its metric depends on.

    Returns a list of (requirement id, metric, score), largest first.
    """
    rel = relative_sensitivities(design, params, t_storage)
    index = {"cost": 0, "RAM": 1, "power": 2, "coverage": 3}
    peak = np.abs(rel).max(axis=(1, 2))
    out = [(rid, name, float(peak[index[name]]))
           for rid, name in metric_of.items() if name in index]
    out.sort(key=lambda e: -e[2])
    return out


# ------------------------------------------------------------------
# the closed forms demo_sens.jl differentiates, for the cross-check against
# Julia ForwardDiff. They are the coverage models with the platform height `b`
# left free, and they are not identical to the oracles above: the lidar form
# here drops the h_fov/(2*pi) factor (it assumes a full 2*pi sweep) and its last
# term carries b rather than b**3, exactly as demo_sens.jl has it.

def lidar_coverage_demo(p, xp=np):
    """p = (max_range, v_fov, b). `coverage` in demo_sens.jl."""
    r, vfov, b = p[..., 0], p[..., 1], p[..., 2]
    th = vfov / 2
    return (2 * (np.pi / 3) * r ** 3 * xp.cos(th) ** 2 * xp.sin(th)
            + (np.pi / 3) * r ** 2 * b * xp.cos(th) ** 2
            - (np.pi / 3) * b / xp.tan(th) ** 2)


def cam_coverage_demo(p, xp=np):
    """p = (max_range, h_fov, v_fov, b). `cam_coverage` in demo_sens.jl."""
    r, hfov, vfov, b = p[..., 0], p[..., 1], p[..., 2], p[..., 3]
    return ((np.pi / 6) * r * xp.tan(hfov / 2) * (r ** 2 * xp.tan(vfov / 2) + 2 * b * r)
            - b ** 2 / xp.tan(vfov / 2))


def laser_coverage_demo(p, xp=np):
    """p = (h_fov, max_range, b). `laser_coverage` in demo_sens.jl."""
    hfov, r, b = p[..., 0], p[..., 1], p[..., 2]
    return (hfov / 2) * r ** 2 * b


def demo_gradient(f, p):
    """Gradient of one of the demo_sens closed forms by jax.grad, in float64."""
    jax = _jax()
    import jax.numpy as jnp
    g = jax.grad(lambda x: f(x, jnp))(jnp.asarray(p, dtype=float))
    return np.asarray(g)


def demo_finite_difference(f, p, rel_step=1e-6):
    """Central-difference gradient of a demo_sens closed form.

    The whole gradient comes out of two batched evaluations: the perturbation
    matrix is a diagonal, so `p + E` and `p - E` are the two shifted parameter
    batches and no loop over components is needed.
    """
    x = np.asarray(p, dtype=float)
    h = rel_step * np.maximum(np.abs(x), 1.0)
    e = np.diag(h)
    return (f(x + e) - f(x - e)) / (2 * h)
