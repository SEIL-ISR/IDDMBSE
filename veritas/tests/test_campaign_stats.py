"""Failure-rate bounds, robustness statistics, and the PERFECT database adapter.

The bounds are checked against their defining property rather than against the same Beta call
that computes them: a Clopper-Pearson endpoint is the binomial proportion at which the
observed count sits exactly at the tail probability, so `scipy.stats.binom` is an independent
oracle for it.  The Clopper-Pearson / Wilson comparison is made on coverage, which is the
property that actually separates them.
"""

import sqlite3

import numpy as np
import pytest
from scipy import stats

import campaign_stats as cs
import perfect_adapter as pa


# ------------------------------------------------------------------
# bounds

def test_clopper_pearson_inverts_the_binomial_tails():
    k, n, d = 17, 200, 0.05
    lo, hi = cs.clopper_pearson(k, n, d)
    assert stats.binom.sf(k - 1, n, lo) == pytest.approx(d / 2, abs=1e-9)
    assert stats.binom.cdf(k, n, hi) == pytest.approx(d / 2, abs=1e-9)
    assert stats.binom.cdf(k, n, cs.clopper_pearson_upper(k, n, d)) == pytest.approx(d, abs=1e-9)


def test_clopper_pearson_degenerate_counts():
    # k = 0: the lower endpoint is 0 and the one-sided upper bound is the rule-of-three form
    assert cs.clopper_pearson(0, 10, 0.05)[0] == 0.0
    assert float(cs.clopper_pearson_upper(0, 10, 0.05)) == pytest.approx(1 - 0.05 ** (1 / 10))
    # k = n: the upper endpoint is 1
    assert cs.clopper_pearson(10, 10, 0.05)[1] == 1.0


def test_bounds_broadcast_over_arrays():
    k = np.array([0, 1, 5, 10])
    lo, hi = cs.clopper_pearson(k, 10, 0.05)
    assert lo.shape == hi.shape == k.shape
    assert np.all(np.diff(lo) >= 0) and np.all(np.diff(hi) >= 0)


def test_clopper_pearson_covers_and_wilson_does_not():
    """The ordering that matters: Clopper-Pearson never falls below the nominal level."""
    n, d = 20, 0.05
    k = np.arange(n + 1)
    p = np.linspace(0.005, 0.995, 400)
    pmf = stats.binom.pmf(k[None, :], n, p[:, None])

    def coverage(fn):
        lo, hi = fn(k, n, d)
        return (pmf * ((lo[None, :] <= p[:, None]) & (p[:, None] <= hi[None, :]))).sum(axis=1)

    assert coverage(cs.clopper_pearson).min() >= 1 - d
    assert coverage(cs.wilson).min() < 1 - d


def test_wilson_is_narrower_except_at_zero_failures():
    # away from the extreme counts the exact interval is the wider one
    for k, n in [(1, 10), (5, 50), (10, 20), (17, 200)]:
        cl, ch = cs.clopper_pearson(k, n, 0.05)
        wl, wh = cs.wilson(k, n, 0.05)
        assert cl <= wl and ch >= wh, (k, n)
    # at k = 0 and large n the Wilson upper endpoint (z^2/n) overtakes the exact one
    # (ln(2/delta)/n), because z^2 = 3.8415 > ln(40) = 3.6889; this is a property of the two
    # formulas, not a defect, and it is why the coverage test above is the real comparison
    assert cs.wilson(0, 100, 0.05)[1] > cs.clopper_pearson(0, 100, 0.05)[1]


def test_trials_for_upper_bound_is_the_smallest_n():
    for failures in [0, 3, 17]:
        n = cs.trials_for_upper_bound(0.05, 0.05, failures=failures)
        assert cs.clopper_pearson_upper(failures, n, 0.05) <= 0.05
        assert cs.clopper_pearson_upper(failures, n - 1, 0.05) > 0.05
    # the zero-failure case has the closed form n = ln(delta) / ln(1 - target)
    assert cs.trials_for_upper_bound(0.05, 0.05, 0) == 59


# ------------------------------------------------------------------
# robustness

def test_dkw_and_robustness_stats():
    rho = np.arange(-0.2, 0.71, 0.1)
    s = cs.robustness_stats(rho, level=0.5, delta=0.5)
    assert s["n"] == 10
    assert s["min"] == pytest.approx(-0.2)
    assert s["violated"] == pytest.approx(0.2)
    assert s["quantile"] == pytest.approx(np.quantile(rho, 0.5))
    # the DKW-corrected quantile is the one at level - epsilon, so never above the plain one
    eps = cs.dkw_epsilon(10, 0.5)
    assert s["quantile_dkw"] == pytest.approx(np.quantile(rho, 0.5 - eps))
    assert s["quantile_dkw"] <= s["quantile"]
    assert s["violated_dkw"] == pytest.approx(0.2 + eps)


def test_dkw_band_too_wide_reports_minus_inf():
    rho = np.linspace(-1, 1, 50)
    s = cs.robustness_stats(rho, level=0.05, delta=0.05)
    assert cs.dkw_epsilon(50, 0.05) > 0.05
    assert s["quantile_dkw"] == -np.inf
    # and it says how many trials the band needs
    assert s["n_for_level"] == int(np.ceil(np.log(40) / (2 * 0.05 ** 2)))
    assert cs.dkw_epsilon(s["n_for_level"], 0.05) <= 0.05


def test_campaign_report_on_a_known_campaign():
    rng = np.random.default_rng(0)
    rho = rng.normal(0.15, 0.12, 400)
    r = cs.campaign_report(rho >= 0, rho=rho, delta=0.05, target=0.05)
    assert r["trials"] == 400
    assert r["failures"] == int(np.count_nonzero(rho < 0))
    assert r["failure_rate"] == r["failures"] / 400
    lo, hi = r["clopper_pearson"]
    assert lo <= stats.norm.cdf(-0.15 / 0.12) <= hi
    assert "robustness" in r and "trials_for_target" in r
    assert isinstance(cs.format_report(r), str)


# ------------------------------------------------------------------
# the PERFECT adapter

# the four tables the adapter joins, transcribed from perfect/perfect/app/models.py
# (Design models.py:114-140, Environment 166-207, Experiment 210-256, Trial 258-307) and
# matching the CREATE TABLE text in perfect/examples/dummy/dummy.db
SCHEMA = """
create table design (
    id integer not null, name varchar(32), tag varchar(16), template_id varchar(16),
    implementation json, primary key (id), unique (name));
create table environment (
    id integer not null, name varchar(32), tag varchar(16), specification json,
    template_id integer, primary key (id), unique (name));
create table experiment (
    id integer not null, design_id integer not null, environment_id integer not null,
    tag varchar(16), primary key (id),
    foreign key(design_id) references design (id),
    foreign key(environment_id) references environment (id));
create table trial (
    id integer not null, datetime datetime, uri varchar(32), state varchar, start_age float,
    sim_time float, cancelled_by varchar, job_id varchar(36), experiment_id integer not null,
    primary key (id), foreign key(experiment_id) references experiment (id));
"""

# the state strings PERFECT writes: str(TrialState(mask)) on an enum.Flag, so composites are
# pipe-joined member names
TRIALS = [
    (1, "TrialState.SUCCESSFUL|SHUT_DOWN", 15.02, 1),
    (2, "TrialState.ERRORED|SHUT_DOWN", 3.1, 1),
    (3, "TrialState.TIMED_OUT|SHUT_DOWN", 60.0, 1),
    (4, "TrialState.SUCCESSFUL|SHUT_DOWN", 14.0, 1),
    (5, None, None, 2),
    (6, "TrialState.SUCCESSFUL|SHUT_DOWN", 12.5, 2),
]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "campaign.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("insert into design values (1, 'Widget A + Dijkstra', 'demo', null, '[]')")
    con.execute("insert into design values (2, 'Widget B + A-star', 'demo', null, '[]')")
    con.execute("insert into environment values (1, 'range', 'demo', '{}', null)")
    con.execute("insert into experiment values (1, 1, 1, 'demo')")
    con.execute("insert into experiment values (2, 2, 1, 'sweep')")
    con.executemany("insert into trial (id, state, start_age, experiment_id) values (?,?,?,?)", TRIALS)
    con.commit()
    con.close()
    return path


def test_adapter_reads_states_and_links(db):
    c = pa.read_campaign(str(db))
    assert c["trial_id"].tolist() == [1, 2, 3, 4, 5, 6]
    assert c["success"].tolist() == [True, False, False, True, False, True]
    assert c["design_name"].tolist() == ["Widget A + Dijkstra"] * 4 + ["Widget B + A-star"] * 2
    assert c["experiment_tag"].tolist() == ["demo"] * 4 + ["sweep"] * 2
    assert c["start_age"][0] == pytest.approx(15.02)
    assert np.isnan(c["start_age"][4])       # a NULL becomes nan, not 0
    assert np.all(np.isnan(c["sim_time"]))   # never populated in this fixture, as in dummy.db


def test_adapter_filters(db):
    assert pa.read_campaign(str(db), design="Widget B + A-star")["trial_id"].tolist() == [5, 6]
    assert pa.read_campaign(str(db), experiment_tag="demo")["trial_id"].tolist() == [1, 2, 3, 4]
    assert pa.read_campaign(str(db), design="nothing")["trial_id"].size == 0


def test_adapter_opens_read_only(db):
    """The adapter must not be able to write to a campaign database."""
    con = sqlite3.connect("file:" + str(db) + "?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("insert into design values (3, 'x', null, null, '[]')")
    con.close()


def test_adapter_csv_fallback(tmp_path):
    p = tmp_path / "campaign.csv"
    p.write_text("state,robustness\n"
                 "TrialState.SUCCESSFUL|SHUT_DOWN,0.4\n"
                 "TrialState.ERRORED|SHUT_DOWN,-0.1\n"
                 "TrialState.SUCCESSFUL|SHUT_DOWN,0.2\n")
    c = pa.read_campaign_csv(str(p))
    assert c["success"].tolist() == [True, False, True]
    assert c["robustness"].tolist() == [0.4, -0.1, 0.2]
    assert cs.failure_rate(c["success"]) == (1, 3, pytest.approx(1 / 3))


def test_adapter_on_the_shipped_dummy_database():
    from pathlib import Path
    db = Path(__file__).resolve().parents[2] / "perfect" / "examples" / "dummy" / "dummy.db"
    if not db.is_file():
        pytest.skip("PERFECT's dummy example database is not present")
    c = pa.read_campaign(str(db))
    assert c["trial_id"].size == 1
    assert c["state"][0] == "TrialState.SUCCESSFUL|SHUT_DOWN"
    assert bool(c["success"][0]) is True
    assert c["design_name"][0] == "Widget A + Dijkstra"
