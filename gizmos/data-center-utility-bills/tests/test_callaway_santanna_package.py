"""What diff-diff 4.0.0 actually does under the pinned call (pipeline/analysis/callaway_santanna.py, module docstring,
"What the installed package does"). Invented inputs only; nothing under data/ is read. Every test here runs the real
package and is skipped as a whole where diff-diff 4.0.0 is not installed (the machine's own Python); run it with the
gizmo folder's isolated environment:

    .venv/bin/python -I -m pytest -q -p no:cacheprovider tests/test_callaway_santanna_package.py

Three behaviours, each pinned by a test that would fail if the package did otherwise:
  (a) covariates are read at the base period g-3, not at t;
  (b) with n_bootstrap=999 the event-study covariance is the covariance of the bootstrap draws (its diagonal the squared
      bootstrap standard errors), not the analytic one, and the package's own intervals are 95% percentile intervals
      with no degrees of freedom;
  (c) event-study weights are each cohort's units in the whole frame with cluster="state", and the cohort's units
      observed at g-3 and t with cluster=None.
And the run's promises: the version refusal against the real package, state-clustered and unit-level standard errors
both returned, the seed 20261204 reproducing the bootstrap, and a covariate the package drops reported as a failure.

Tolerances, stated:
  point estimates on noise-free worlds against the planted answer or a hand formula      1e-6
  the covariance's diagonal against the squared standard errors (same draws)            1e-10 relative
  the headline's standard error against w' V w from the package's own covariance       1e-12
  "differs" means by more than 1e-3 for point estimates and 1% for standard errors
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

dd = pytest.importorskip("diff_diff", reason="diff-diff 4.0.0 is not installed")

from pipeline.analysis import callaway_santanna as cs  # noqa: E402

TOL = 1e-6
DIFFERS = 1e-3
FIT_KW = dict(outcome="outcome", unit="unit_id", time="year", first_treat="first_treat")
YEARS = list(range(2001, 2026))


def fit(data, covariates, **over):
    est = dd.CallawaySantAnna(**{**cs.PINNED_CALL, **over})
    with _quiet():
        res = est.fit(data, covariates=covariates, **FIT_KW)
        es = res.aggregate("event_study")
    return res, es


class _quiet:
    """Silence the package's expected warnings (unbalanced panel, cells outside a host's window, degenerate bootstrap
    on noise-free worlds) inside a direct fit. run() records them itself."""

    def __enter__(self):
        import warnings
        self._cm = warnings.catch_warnings()
        self._cm.__enter__()
        warnings.simplefilter("ignore")

    def __exit__(self, *a):
        return self._cm.__exit__(*a)


def es_at(es, e):
    return float(es.att[list(es.event_time).index(e)])


def frame_from(rows, extra_cols=()):
    return pd.DataFrame(rows, columns=["unit_id", "state", "year", "first_treat", "outcome", *extra_cols])


# ---- a hand reference that can read the covariate at any year (test-local, for (a)) --------------------------------

def att_reading_at(data, g, t, cov, read_at):
    """ATT(g, t) by outcome regression on never-treated units, the change from g-3 to t, with the covariate read at
    `read_at` ("base" = g-3, or "t"). Units with rows at both g-3 and t."""
    b = g + cs.BASE_OFFSET
    def side(cohort):
        sub = data[data.first_treat == cohort]
        base, now = sub[sub.year == b].set_index("unit_id"), sub[sub.year == t].set_index("unit_id")
        ids = base.index.intersection(now.index)
        x = (base if read_at == "base" else now).loc[ids, cov].to_numpy(float)
        return (now.loc[ids, "outcome"] - base.loc[ids, "outcome"]).to_numpy(float), np.column_stack([np.ones(len(ids)), x])
    dy1, X1 = side(g)
    dy0, X0 = side(0)
    beta = np.linalg.lstsq(X0, dy0, rcond=None)[0]
    return float(np.mean(dy1 - X1 @ beta))


# ---- (a) covariate timing --------------------------------------------------------------------------------------------

TAU, B, G_A, SHIFT_YEAR = 0.05, 0.01, 2014, 2012     # base g-3 = 2011, before the covariate shifts in 2012


def timing_world():
    """One cohort (2014, so every event year is measured against 2011). Each unit has a type z; the covariate equals z
    up to 2011 and z + s from 2012, with s larger for hosts. The untreated change from 2011 to t is B x z x (t - 2011),
    exactly linear in the covariate AT THE BASE PERIOD, so reading it at g-3 recovers TAU exactly, and reading it at t
    (z + s) does not. Noise-free."""
    rows, uid = [], 0
    for i in range(30):                                     # never-treated, 10 states
        uid += 1
        z, s = 0.2 + 0.05 * i, 0.1 * (i % 4)
        for y in YEARS:
            rows.append((uid, f"N{i % 10}", y, 0, 1.0 + 0.3 * np.sin(y) + B * z * (y - 2011), z + (s if y >= SHIFT_YEAR else 0.0)))
    for j in range(5):                                       # hosts, rows only in their window g-6 .. g+3
        uid += 1
        z, s = 1.0 + 0.1 * j, 0.6 + 0.05 * j
        for y in range(G_A - 6, G_A + 4):
            v = 1.0 + 0.3 * np.sin(y) + B * z * (y - 2011) + (TAU if (y - G_A) in (2, 3) else 0.0)
            rows.append((uid, f"N{j % 10}", y, G_A, v, z + (s if y >= SHIFT_YEAR else 0.0)))
    return frame_from(rows, ["x"])


@pytest.mark.parametrize("cluster", ["state", None])
def test_a_covariates_are_read_at_the_base_period_not_at_t(cluster):
    d = timing_world()
    _, es = fit(d, ["x"], cluster=cluster)
    for e in (2, 3):
        at_base = att_reading_at(d, G_A, G_A + e, "x", "base")
        at_t = att_reading_at(d, G_A, G_A + e, "x", "t")
        assert abs(at_base - TAU) < TOL                       # the world is built so that g-3 is right
        assert abs(at_t - TAU) > DIFFERS                     # and reading at t is measurably wrong
        assert abs(es_at(es, e) - at_base) < TOL             # the package matches the base-period reading
        assert abs(es_at(es, e) - at_t) > DIFFERS
    for e in (-1, 0, 1):                                     # after the shift but before the effect: zero at g-3
        assert abs(es_at(es, e)) < TOL
    assert abs(cs.reference_event_study(d, 2, ["x"]) - es_at(es, 2)) < TOL      # the module's reference agrees


# ---- a noisy world for the covariance and the run's promises ---------------------------------------------------------

def noisy_world(seed=7):
    """Two cohorts, 60 never-treated units in 12 states, state-year shocks and unit noise, a covariate."""
    rng = np.random.default_rng(seed)
    states = [f"S{k}" for k in range(12)]
    shock = {(s, y): rng.normal(0, 0.02) for s in states for y in YEARS}
    rows, uid = [], 0
    for i in range(60):
        uid += 1
        st, x = states[i % 12], rng.uniform(0, 1)
        for y in YEARS:
            rows.append((uid, st, y, 0, 0.01 * (y - 2000) + 0.005 * x * (y - 2000) + shock[(st, y)] + rng.normal(0, 0.02), x))
    for g in (2014, 2018):
        for j in range(6):
            uid += 1
            st, x = states[(j + (g == 2018) * 6) % 12], rng.uniform(0.3, 1.3)
            for y in range(g - 6, g + 4):
                v = 0.01 * (y - 2000) + 0.005 * x * (y - 2000) + shock[(st, y)] + rng.normal(0, 0.02)
                rows.append((uid, st, y, g, v + (0.05 if (y - g) in (2, 3) else 0.0), x))
    return frame_from(rows, ["x"])


# ---- (b) event-study covariance ---------------------------------------------------------------------------------------

def test_b_the_event_study_covariance_is_the_bootstraps_and_not_the_analytic_one():
    d = noisy_world()
    res, es = fit(d, ["x"])
    assert res.bootstrap_results is not None and res.bootstrap_results.n_bootstrap == 999
    assert res.bootstrap_results.weight_type == "rademacher" and res.n_clusters == 12
    idx = [int(e) for e in es.vcov_index]
    assert -3 not in idx and {2, 3} <= set(idx)                # the reference year has no draws and no row
    se = {int(e): float(s) for e, s in zip(es.event_time, es.se)}
    diag = np.diag(np.asarray(es.vcov, float))
    for k, e in enumerate(idx):                               # diagonal = squared bootstrap SEs (same draws)
        assert abs(diag[k] - se[e] ** 2) <= 1e-10 * se[e] ** 2
    assert np.all(np.isnan(np.asarray(es.df, float)))         # no degrees of freedom govern bootstrap inference
    assert es.alpha == 0.05                                   # the package's own intervals are 95%

    _, es_a = fit(d, ["x"], n_bootstrap=0)                     # the analytic influence-function covariance
    assert list(es_a.vcov_index) == list(es.vcov_index)
    Va, Vb = np.asarray(es_a.vcov, float), np.asarray(es.vcov, float)
    assert np.max(np.abs(Va - Vb) / np.sqrt(np.outer(np.diag(Va), np.diag(Va)))) > 0.01
    assert np.all(np.asarray(es_a.df, float)[np.isfinite(np.asarray(es_a.se, float))] == 11)   # G - 1, analytic only

    w = np.array([0.5 if e in (2, 3) else 0.0 for e in idx])
    out = cs.run(pd.DataFrame(d), covariates=["x"])
    assert out["numerical_failure"] is None and out["covariate_warnings"] == []
    assert abs(out["se_state_clustered"] - np.sqrt(w @ Vb @ w)) < 1e-12       # the module uses the bootstrap's
    assert abs(out["se_state_clustered"] - np.sqrt(w @ Va @ w)) > 0.01 * np.sqrt(w @ Va @ w)
    assert abs(out["headline"] - 0.5 * (es_at(es, 2) + es_at(es, 3))) < 1e-15
    from scipy import stats
    crit = stats.t.ppf(0.95, 11)
    assert np.allclose(out["range_90"], [out["headline"] - crit * out["se_state_clustered"],
                                         out["headline"] + crit * out["se_state_clustered"]], rtol=0, atol=1e-15)


def test_b_the_packages_own_event_year_interval_is_a_percentile_interval_not_a_t_or_normal_one():
    d = noisy_world()
    _, es = fit(d, ["x"])
    from scipy import stats
    k = list(es.event_time).index(2)
    att, se, lo, hi = float(es.att[k]), float(es.se[k]), float(es.conf_int_lower[k]), float(es.conf_int_upper[k])
    for crit in (stats.norm.ppf(0.975), stats.t.ppf(0.975, 11)):
        assert abs((hi - lo) - 2 * crit * se) > 1e-9 or abs((hi - att) - (att - lo)) > 1e-9
    assert abs((hi - att) - (att - lo)) > 1e-9                # not symmetric about the estimate


# ---- (c) aggregation weights ------------------------------------------------------------------------------------------

T1, T2 = 0.05, 0.15


def weights_world():
    """Two cohorts of four hosts, effects T1 (2014) and T2 (2018) in event years 2 and 3. One 2014 host has no row in
    2016 (its event year 2), as a unit-year the usable flag would mark unusable. Noise-free, with a covariate."""
    rows, uid = [], 0
    for i in range(30):
        uid += 1
        x = 0.1 + 0.03 * i
        for y in YEARS:
            rows.append((uid, f"N{i % 10}", y, 0, 1.0 + 0.2 * np.cos(y) + 0.01 * x * (y - 2000), x))
    gap = None
    for g, tau in ((2014, T1), (2018, T2)):
        for j in range(4):
            uid += 1
            x = 0.5 + 0.1 * j
            if gap is None:
                gap = uid
            for y in range(g - 6, g + 4):
                if uid == gap and y == 2016:
                    continue
                rows.append((uid, f"N{j}", y, g, 1.0 + 0.2 * np.cos(y) + 0.01 * x * (y - 2000) + (tau if (y - g) in (2, 3) else 0.0), x))
    return frame_from(rows, ["x"])


def test_c_state_clustered_weights_are_cohort_sizes_over_the_whole_frame():
    d = weights_world()
    _, es = fit(d, ["x"], cluster="state")
    assert abs(es_at(es, 2) - (4 * T1 + 4 * T2) / 8) < TOL
    assert abs(es_at(es, 2) - (3 * T1 + 4 * T2) / 7) > DIFFERS
    assert abs(es_at(es, 2) - cs.reference_event_study(d, 2, ["x"], weights=cs.COHORT_WEIGHTS)) < TOL
    assert abs(es_at(es, 3) - (T1 + T2) / 2) < TOL


def test_c_unit_level_weights_are_the_units_observed_at_g_minus_3_and_t():
    d = weights_world()
    _, es = fit(d, ["x"], cluster=None)
    assert abs(es_at(es, 2) - (3 * T1 + 4 * T2) / 7) < TOL
    assert abs(es_at(es, 2) - cs.reference_event_study(d, 2, ["x"], weights=cs.CELL_WEIGHTS)) < TOL
    assert abs(es_at(es, 3) - (T1 + T2) / 2) < TOL


def test_c_run_reports_that_the_two_calls_disagree_when_a_host_lacks_a_window_row_and_agree_otherwise():
    out = cs.run(weights_world(), covariates=["x"])
    assert abs(out["headline"] - cs.reference_headline(weights_world(), ["x"], weights=cs.COHORT_WEIGHTS)) < TOL
    assert abs(out["headline_unit_level_call"] - cs.reference_headline(weights_world(), ["x"], weights=cs.CELL_WEIGHTS)) < TOL
    assert out["headlines_agree"] is False
    full = noisy_world()
    assert cs.run(full, covariates=["x"])["headlines_agree"] is True


# ---- the run's promises -------------------------------------------------------------------------------------------------

def test_run_refuses_another_version_of_the_real_package(monkeypatch):
    monkeypatch.setattr(dd, "__version__", "4.0.1")
    with pytest.raises(cs.PackageVersionRefused, match=r"'4\.0\.1', not the pinned 4\.0\.0"):
        cs.run(noisy_world(), covariates=["x"])


def test_run_returns_state_clustered_and_unit_level_standard_errors():
    out = cs.run(noisy_world(), covariates=["x"])
    s, u = out["se_state_clustered"], out["se_unit_level"]
    assert s is not None and u is not None and np.isfinite(s) and np.isfinite(u) and s > 0 and u > 0
    assert abs(s - u) > 0.01 * u                              # different clustering, different draws
    assert out["package_clusters_state_call"] == 12 and out["clusters"] == 12
    assert out["bootstrap_state_call"] == {"n_bootstrap": 999, "weight_type": "rademacher"}
    assert out["range_label"] == cs.RANGE_LABEL and out["numerical_failure_unit_level"] is None
    # Joe, 2026-11-19 (D-105): the range is the module's t-based construction, secondary and uncalibrated, and the run's
    # labels never call it the package's interval
    assert "secondary" in out["range_label"] and "uncalibrated" in out["range_label"] and out["range_text"] == cs.RANGE_TEXT
    import scipy.stats
    crit = float(scipy.stats.t.ppf(0.95, out["clusters"] - 1))
    lo, hi = out["range_90"]
    assert abs(lo - (out["headline"] - crit * s)) < 1e-12 and abs(hi - (out["headline"] + crit * s)) < 1e-12
    assert not any("package's interval" in str(out.get(k, "")) for k in ("range_label", "range_text", "headline_label"))


def test_the_seed_reproduces_the_bootstrap_and_another_seed_does_not(monkeypatch):
    d = noisy_world()
    a, b = cs.run(d, covariates=["x"]), cs.run(d, covariates=["x"])
    assert a["bootstrap_weight_backend"] == b["bootstrap_weight_backend"]
    assert a["se_state_clustered"] == b["se_state_clustered"] and a["se_unit_level"] == b["se_unit_level"]
    assert a["range_90"] == b["range_90"]
    monkeypatch.setattr(cs, "PINNED_CALL", {**cs.PINNED_CALL, "seed": cs.SEED + 1})
    c = cs.run(d, covariates=["x"])
    assert c["headline"] == a["headline"]                     # the seed moves only the bootstrap
    assert c["se_state_clustered"] != a["se_state_clustered"] and c["se_unit_level"] != a["se_unit_level"]


def test_a_covariate_the_package_drops_is_a_reported_failure_and_gets_no_range():
    d = noisy_world().assign(x_copy=lambda f: f.x)            # linearly dependent: the package drops a column
    out = cs.run(d, covariates=["x", "x_copy"])
    assert out["covariate_warnings"] and out["covariate_warnings_unit_level"]
    assert "covariate warning" in out["numerical_failure"] and "covariate warning" in out["numerical_failure_unit_level"]
    assert out["range_90"] is None and out["range_label"].startswith("no range")
    assert out["headline_label"].startswith("not the specified estimator")
