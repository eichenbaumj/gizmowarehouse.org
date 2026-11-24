"""Numerical failures are never dropped (D-95 section 3 item 7; docs/gate1/step-e-rules-2026-11-18.md, E4.1 and E4.3).

Any non-finite bootstrap replication or rank-deficient fit marks the dataset as a numerical failure with a cause code. It
stays in the denominator, counted as a miss and a rejection, and the failure counts and causes are reported apart.
Nothing is dropped or replaced. Invented data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import estimator as es  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_estimator import unbalanced  # noqa: E402


def fit_and_v(seed=3, boot=99):
    y, X, groups, cl = unbalanced(seed=seed)
    fit = es.Fit(y, X, groups, cl)
    return fit, es.rademacher(np.random.default_rng(seed), boot, fit.G)


COMBO, PRE = np.array([0.0, 0.5, 0.5]), [0, 1]


# ---- the shared estimator ---------------------------------------------------------------------------------

def test_a_clean_dataset_has_no_failure_and_its_range_is_the_plain_quantile():
    fit, v = fit_and_v()
    s = fit.summary(v, COMBO, PRE)
    bs = fit.bootstrap(v, COMBO, PRE)
    lo_q, hi_q = np.quantile(bs["t"], [0.05, 0.95])
    assert s["numerical_failure"] is None and s["analytic_failure"] is None
    assert (s["lo"], s["hi"]) == pytest.approx((s["est"] - hi_q * s["se"], s["est"] - lo_q * s["se"]))
    assert s["pre_p_bootstrap"] == pytest.approx(float(np.mean(bs["wald"] >= s["pre_wald"])))


def test_one_non_finite_replication_fails_the_dataset_and_nothing_is_quantiled_over_the_rest(monkeypatch):
    fit, v = fit_and_v()
    real = fit.bootstrap(v, COMBO, PRE)
    t = real["t"].copy()
    t[7] = np.nan
    monkeypatch.setattr(fit, "bootstrap", lambda *a, **k: {"t": t, "wald": real["wald"]})
    s = fit.summary(v, COMBO, PRE)
    assert s["numerical_failure"] == es.NON_FINITE_BOOTSTRAP_T and s["analytic_failure"] is None
    assert np.isnan(s["lo"]) and np.isnan(s["hi"]) and np.isnan(s["pre_p_bootstrap"])
    assert np.isfinite(s["est"]) and np.isfinite(s["pre_wald"])         # the analytic readings still stand


def test_an_infinite_replication_of_the_early_years_statistic_fails_the_dataset(monkeypatch):
    fit, v = fit_and_v()
    real = fit.bootstrap(v, COMBO, PRE)
    w = real["wald"].copy()
    w[0] = np.inf
    monkeypatch.setattr(fit, "bootstrap", lambda *a, **k: {"t": real["t"], "wald": w})
    s = fit.summary(v, COMBO, PRE)
    assert s["numerical_failure"] == es.NON_FINITE_BOOTSTRAP_WALD and np.isnan(s["lo"])


def test_a_singular_replication_variance_is_marked_and_never_replaced_by_a_pseudo_inverse(monkeypatch):
    fit, v = fit_and_v()
    good = fit.bootstrap(v, COMBO, PRE)["wald"]
    solve = np.linalg.solve
    calls = {"n": 0}

    def flaky(a, b):
        if np.ndim(a) == 3:
            raise np.linalg.LinAlgError("batched")
        calls["n"] += 1
        if calls["n"] == 1:
            raise np.linalg.LinAlgError("singular")
        return solve(a, b)

    monkeypatch.setattr(es.np.linalg, "solve", flaky)
    out = fit.bootstrap(v, COMBO, PRE)
    assert np.isnan(out["wald"][0]) and out["singular_replications"] == 1
    assert out["wald"][1:] == pytest.approx(good[1:])
    assert es.bootstrap_failure(out, PRE) == es.NON_FINITE_BOOTSTRAP_WALD


def test_a_singular_early_years_variance_fails_the_analytic_readings_too(monkeypatch):
    fit, v = fit_and_v()

    def singular(a, b):
        raise np.linalg.LinAlgError("singular")

    monkeypatch.setattr(es.np.linalg, "solve", singular)
    s = fit.summary(v, COMBO, PRE)
    assert s["numerical_failure"] == es.SINGULAR_WALD_VARIANCE == s["analytic_failure"]
    assert np.isnan(s["pre_wald"]) and np.isnan(s["lo"])


def test_a_zero_standard_error_is_a_failure_not_a_division():
    fit, v = fit_and_v()
    s = fit.summary(v, np.zeros(3), PRE)
    assert s["numerical_failure"] == es.NON_FINITE_STANDARD_ERROR


def test_no_nanquantile_is_left_where_replications_are_read():
    for f in ("pipeline/analysis/estimator.py", "pipeline/analysis/power_simulation.py", "pipeline/analysis/inference_check.py"):
        assert "nanquantile" not in (ROOT / f).read_text(), f


# ---- the closed form -------------------------------------------------------------------------------------

def test_the_closed_form_range_is_nan_when_a_replication_is_not_finite():
    t = np.linspace(-2, 2, 99)
    assert np.isfinite(ps.interval(0.0, 1.0, t)).all() and ps.closed_form_failure(t, 1.0) is None
    t[3] = np.nan
    assert np.isnan(ps.interval(0.0, 1.0, t)).all()
    assert ps.closed_form_failure(t, 1.0) == "non_finite_bootstrap_replication"
    assert ps.closed_form_failure(np.zeros(3), 0.0) == "non_finite_or_zero_standard_error"


def test_a_failed_draw_never_detects_anything():
    est0, half = np.zeros(10), np.full(10, 0.01)
    assert ps.smallest_detectable(est0, half, bar=0.8) == pytest.approx(0.01)
    half[[0, 1, 2]] = np.nan                                          # three of ten failed: 80% cannot be reached
    assert ps.smallest_detectable(est0, half, bar=0.8) == np.inf


def test_the_closed_form_summary_counts_failures():
    rows = pd.DataFrame({"est": [0.0, 0.0], "se": [1.0, np.nan], "lo": [-1.0, np.nan], "hi": [1.0, np.nan], "clusters": [6, 6],
                         "numerical_failure": [None, "non_finite_bootstrap_replication"]})
    out = ps.summarise(rows)
    assert out["interval_covers_zero"] == 0.5 and out["numerical_failures"]["count"] == 1


# ---- the simulation's reading ------------------------------------------------------------------------------

def good_reading(lo=-0.01, hi=0.01, p=0.5, est=0.0):
    return {"est": est, "se": 0.005, "lo": lo, "hi": hi, "clusters": 6, "pre_wald": 1.0, "pre_p_bootstrap": p, "max_abs_early": 0.0,
            "lo_analytic": lo, "hi_analytic": hi, "numerical_failure": None, "analytic_failure": None}


def draws_with_one_failure():
    draws = []
    for _ in range(9):
        exact = [good_reading()] + [good_reading(lo=0.001 + t / 100, hi=0.05 + t / 100, est=t / 100) for t in ps.TAUS_PCT[1:]]
        draws.append({"exact": exact, "misdated": list(exact)})
    bad = ps.failed_reading(es.RANK_DEFICIENT, 6)
    draws.append({"exact": [dict(bad) for _ in ps.TAUS_PCT], "misdated": [dict(bad) for _ in ps.TAUS_PCT]})
    return draws


def test_read_draws_keeps_a_failed_draw_as_a_miss_a_rejection_and_no_detection():
    out = ps.read_draws(draws_with_one_failure(), hosts=3)
    assert out["draws"] == 10 and out["rates_include_numerical_failures"] is True
    assert out["numerical_failures"]["bootstrap"]["count"] == 1
    assert out["numerical_failures"]["bootstrap"]["by_cause"] == {es.RANK_DEFICIENT: 1}
    assert out["nothing_planted"]["range_covers_zero"] == 0.9                         # the failure is a miss
    assert out["nothing_planted"]["analytic_range_covers_zero"] == 0.9
    assert out["early_years_test"]["share_of_flat_histories_failing_at_p_below_0.10"] == 0.1   # and a rejection
    assert out["early_years_test"]["share_failing_at_the_chi_square_10pct_value"] == 0.1
    assert out["start_years_exact"]["range_entirely_above_zero_by_planted_pct"]["5"] == 0.9    # and no detection
    assert out["nothing_planted"]["moments_are_over"].startswith("every draw whose value for the moment is not NaN")


def test_moments_keep_a_failed_draws_finite_estimate_and_leave_out_a_nan_one():
    """The label of 2026-11-19, pinned on invented draws: a draw that failed after its estimate was computed keeps that
    estimate in the moments, while a draw with no estimate (NaN) drops out of them; both stay failures in the counts and
    the rates. Nine good draws read 0.0; the tenth is a failure with an estimate of 0.10, or a failure with NaN."""
    label = ps.read_draws(draws_with_one_failure(), hosts=3)["nothing_planted"]["moments_are_over"]
    assert "failed before an estimate existed has none and is left out" in label
    assert "failed after its estimate was computed keeps its estimate" in label
    assert "draws without a numerical failure" not in label
    def ten_draws():                                                   # pre_p as well, which C's readings carry
        return [{k: [dict(r, pre_p=r["pre_p_bootstrap"]) for r in v] for k, v in d.items()} for d in draws_with_one_failure()]

    for procedure in (ps.AS_BUILT, ps.SELECTED):
        with_estimate = ten_draws()
        late = dict(good_reading(est=0.10), lo=float("nan"), hi=float("nan"),
                    numerical_failure=es.NON_FINITE_BOOTSTRAP_T, analytic_failure=None, pre_p=float("nan"))
        with_estimate[-1] = {"exact": [dict(late) for _ in ps.TAUS_PCT], "misdated": [dict(late) for _ in ps.TAUS_PCT]}
        nan_estimate = ten_draws()                                     # the tenth is failed_reading: NaN everywhere
        a = ps.read_draws(with_estimate, hosts=3, procedure=procedure)
        b = ps.read_draws(nan_estimate, hosts=3, procedure=procedure)
        failures = "selected_procedure" if procedure == ps.SELECTED else "bootstrap"
        assert a["numerical_failures"][failures]["count"] == 1 and b["numerical_failures"][failures]["count"] == 1
        # the failed draw with a finite estimate moves the mean: (9 * 0.0 + 0.10) / 10 = 1.0 percent, tolerance 1e-9
        assert abs(a["nothing_planted"]["mean_estimate"] - 1.0) < 1e-9
        # the failed draw with NaN does not: the mean is over the nine good draws, 0.0
        assert abs(b["nothing_planted"]["mean_estimate"] - 0.0) < 1e-9
        # its standard error (finite) enters the mean standard error in both cases where it is not NaN
        assert abs(a["nothing_planted"]["mean_standard_error"] - 0.5) < 1e-9
        # neither failed draw has a range, so the range widths are over the nine good draws (width 0.02, half 1.0 percent)
        assert abs(a["nothing_planted"]["range_half_width_mean"] - 1.0) < 1e-9
        assert abs(b["nothing_planted"]["range_half_width_mean"] - 1.0) < 1e-9
        # and both failures are misses in the rate
        assert a["nothing_planted"]["range_covers_zero"] == 0.9 and b["nothing_planted"]["range_covers_zero"] == 0.9


def test_summarise_label_and_its_moments_on_invented_rows():
    """summarise (the closed-form runs): a failed row with a finite estimate and NaN range moves the mean estimate and
    is left out of the range widths. Tolerance 1e-9."""
    rows = pd.DataFrame({"est": [0.0] * 9 + [0.10], "se": [0.005] * 10, "lo": [-0.01] * 9 + [np.nan],
                         "hi": [0.01] * 9 + [np.nan], "clusters": [6] * 10,
                         "numerical_failure": [None] * 9 + [es.NON_FINITE_BOOTSTRAP_T]})
    out = ps.summarise(rows)
    assert out["moments_are_over"].startswith("each mean, standard deviation and median is over the draws whose value")
    assert abs(out["mean_estimate_nothing_planted"] - 1.0) < 1e-9
    assert abs(out["range_half_width_mean"] - 1.0) < 1e-9
    assert out["interval_covers_zero"] == 0.9 and out["numerical_failures"]["count"] == 1


def test_one_draw_turns_a_rank_deficient_fit_into_counted_failures():
    from test_gas_share import GAS, make
    from test_matching_rules import COOP, ladder
    d = make([(1, "AA", 10_000, COOP)], ladder(10, 12, state="BB"))
    draw = ps.one_draw(d.windows, d.blocks(), {}, np.random.default_rng(1), boot=9, gas=GAS, taus=(0, 5))
    assert [r["numerical_failure"] for r in draw["exact"] + draw["misdated"]] == [es.RANK_DEFICIENT] * 4


# ---- the inference check -----------------------------------------------------------------------------------

def test_fit_dataset_records_a_rank_deficient_fit_instead_of_raising():
    y, X, groups, cl = unbalanced()
    absorbed = np.column_stack([X, (groups[0] % 4 == 0) * 1.0])
    f = {"X": absorbed, "groups": groups, "cluster": cl, "trend": X[:, 2], "combo": np.array([0.0, 0.5, 0.5, 0.0]), "projection": None}
    out = ic.fit_dataset(y, f, np.random.default_rng(0), 19, trends=(0.01,))
    assert out["numerical_failure"] == es.RANK_DEFICIENT == out["analytic_failure"] and np.isnan(out["lo"])
    assert out["trend_0.01_failure"] == es.RANK_DEFICIENT
    ok = ic.fit_dataset(y, {**f, "X": X, "combo": COMBO}, np.random.default_rng(0), 19, trends=(0.01,))
    assert ok["numerical_failure"] is None and np.isfinite(ok["lo"])


def test_summarise_counts_failures_against_the_procedure_and_reports_them_apart():
    good = {"est": 0.0, "se": 1.0, "lo": -1.0, "hi": 1.0, "lo_analytic": -1.0, "hi_analytic": 1.0, "pre_wald": 1.0, "pre_p": 0.5,
            "pre_p_chi2": 0.5, "clusters": 6, "numerical_failure": None, "analytic_failure": None,
            "trend_0.01_pre_p": 0.01, "trend_0.01_pre_p_chi2": 0.01, "trend_0.01_est": 0.05, "trend_0.01_failure": None}
    bad = {**{k: np.nan for k in good}, "clusters": 6, "numerical_failure": es.NON_FINITE_BOOTSTRAP_T, "analytic_failure": None,
           "lo_analytic": -1.0, "hi_analytic": 1.0, "pre_p_chi2": 0.5, "trend_0.01_failure": es.NON_FINITE_BOOTSTRAP_T,
           "trend_0.01_pre_p_chi2": 0.01}
    z = pd.DataFrame([good] * 3 + [bad])
    out = ic.summarise(z, trends=(0.01,))
    assert out["datasets"] == 4 and out["rates_include_numerical_failures"] is True
    assert out["early_years_test_fails_a_flat_history"]["bootstrap_p_below_0.10"]["share"] == 0.25
    assert out["range_misses_zero_nominal_10pct"]["bootstrap"]["share"] == 0.25
    assert out["range_misses_zero_nominal_10pct"]["analytic_clustered_t"]["share"] == 0.0   # the analytic reading did not fail
    assert out["numerical_failures"]["bootstrap"] == {**out["numerical_failures"]["bootstrap"], "count": 1,
                                                       "by_cause": {es.NON_FINITE_BOOTSTRAP_T: 1}}
    trend = out["with_a_pre_trend_of_1pct_a_year"]
    assert trend["early_years_test_fails"]["bootstrap_p_below_0.10"]["share"] == 0.75        # a failure is no detection
    assert trend["numerical_failures_counted_as_no_detection"]["count"] == 1
