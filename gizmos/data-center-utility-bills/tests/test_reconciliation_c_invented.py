"""Reconciliation row C (pipeline/analysis/reconciliation_c.py) on invented inputs only.

Every estimator test plants a known answer and states its tolerance. The within estimator is checked against a
brute-force regression with every fixed effect as a dummy column; two-stage least squares against the same and
against the ratio of reduced form to first stage, which is exact with one instrument. No file under data/ is read.
"""
from __future__ import annotations

import ast
import inspect
import math
import re
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import reconciliation_c as rc  # noqa: E402

CH = rc.SPECIFICATION
YEARS = list(rc.YEARS)


# ---------------------------------------------------------------------------------------------------------------
# Invented worlds
# ---------------------------------------------------------------------------------------------------------------
def world(seed=0, states=("AA", "BB", "CC", "DD"), per_state=25, beta=0.2, pi=0.85, rho=0.6, direct=0.0,
          own_beta=None, spending=None, share_mult=1.0):
    """A balanced panel with an endogenous regressor d and the paper's instrument.

    d = unit + state-year + pi * Z + v;  y = unit + state-year + beta * d + direct * Z + e,  e = rho * v + noise.
    share_mult scales the shares (a stronger instrument for tight checks).
    own_beta {class: beta} plants a different effect by ownership class (units alternate investor_owned / other).
    Returns outcome frame, regressor frame, share map, spending map, ownership map.
    """
    rng = np.random.default_rng(seed)
    spending = spending or {2021: 11.5, 2022: 13.5, 2023: 20.6, 2024: 31.1}
    rows, share, own = [], {}, {}
    uid = 100
    for st in states:
        sy = {y: rng.normal(0, 1) for y in YEARS}
        sy_d = {y: rng.normal(0, 1) for y in YEARS}
        for k in range(per_state):
            uid += 1
            share[(uid, st)] = float(rng.lognormal(-5, 1.0)) * share_mult
            own[(uid, st)] = "investor_owned" if k % 2 == 0 else ("cooperative" if k % 4 == 1 else "public")
            a, a_d = rng.normal(10, 2), rng.normal(0, 1)
            for y in YEARS:
                z = (math.log(spending[y]) if y >= 2021 else 0.0) * share[(uid, st)] * 100
                v = rng.normal(0, 1)
                d = a_d + sy_d[y] + pi * z + v
                b = beta if own_beta is None else own_beta[own[(uid, st)] == "investor_owned"]
                yv = a + sy[y] + b * d + direct * z + rho * v + rng.normal(0, 0.5)
                rows.append((uid, st, y, yv, d))
    f = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "value", "d"])
    return (f[["utility_id_eia", "state", "year", "value"]], f[["utility_id_eia", "state", "year", "d"]]
            .rename(columns={"d": "value"}), share, spending, own)


def dummies(f):
    """Unit dummies and state-year dummies, dropping each state's first year (full column rank)."""
    U = pd.get_dummies(list(zip(f.utility_id_eia, f.state))).to_numpy(float)
    sy = pd.Series([f"{s}|{y}" for s, y in zip(f.state, f.year)])
    first = {s: min(f.year[f.state == s]) for s in f.state.unique()}
    keep = [c for c in sorted(sy.unique()) if int(c.split("|")[1]) != first[c.split("|")[0]]]
    S = np.column_stack([(sy == c).to_numpy(float) for c in keep])
    return np.hstack([U, S]), U.shape[1]


def brute(y, X, Z, D, cluster, small, n_nested):
    """Dummy-variable OLS / 2SLS with a cluster sandwich; returns coef and SE of the first column of X."""
    Xa = np.hstack([X, D])
    Za = Xa if Z is None else np.hstack([Z, D])
    Xh = Za @ np.linalg.lstsq(Za, Xa, rcond=None)[0]
    beta = np.linalg.solve(Xh.T @ Xa, Xh.T @ y)
    u = y - Xa @ beta
    cl = pd.factorize(pd.Series(list(cluster)))[0]
    G = cl.max() + 1
    S = np.zeros((G, Xa.shape[1]))
    np.add.at(S, cl, Xh * u[:, None])
    bread = np.linalg.inv(Xh.T @ Xh)
    V = bread @ S.T @ S @ bread
    N, K = len(y), Xa.shape[1] - n_nested
    c = {"none": 1.0, "cr1_cluster": G / (G - 1), "cr1_stata": G / (G - 1) * (N - 1) / (N - K)}[small]
    return beta[0], math.sqrt(c * V[0, 0])


def transformed(out, reg, share, sp, choices=CH):
    p = rc.build_panel(out, reg, share, sp, choices, None)
    f, g1, g2, _ = rc._design(p, choices)
    return f, g1, g2


# ---------------------------------------------------------------------------------------------------------------
# The estimator against brute force
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("small", ["none", "cr1_cluster", "cr1_stata"])
def test_within_ols_equals_dummy_regression(small):
    """Coefficient and clustered SE equal the dummy-variable fit to 1e-8 (relative), under each correction."""
    out, reg, share, sp, _ = world(seed=1, beta=0.3)
    f, g1, g2 = transformed(out, reg, share, sp)
    M = rc.within(f[["y", "d"]].to_numpy(float), g1, g2)
    fit = rc.iv_fit(M[:, 0], M[:, 1:2], None, g1, small, rc.absorbed_df_not_nested(g1, g2))
    D, nU = dummies(f)
    b, se = brute(f.y.to_numpy(), f[["d"]].to_numpy(), None, D, g1, small, nU)
    assert fit.coef[0] == pytest.approx(b, rel=1e-8)
    assert fit.se[0] == pytest.approx(se, rel=1e-8)


@pytest.mark.parametrize("small", ["none", "cr1_stata"])
def test_2sls_equals_dummy_2sls_and_ratio(small):
    """2SLS equals the dummy-variable 2SLS (coef and SE, 1e-8 relative) and RF/FS exactly (1e-10 relative)."""
    out, reg, share, sp, _ = world(seed=2)
    f, g1, g2 = transformed(out, reg, share, sp)
    M = rc.within(f[["y", "d", "z"]].to_numpy(float), g1, g2)
    k = rc.absorbed_df_not_nested(g1, g2)
    fit = rc.iv_fit(M[:, 0], M[:, 1:2], M[:, 2:3], g1, small, k)
    D, nU = dummies(f)
    b, se = brute(f.y.to_numpy(), f[["d"]].to_numpy(), f[["z"]].to_numpy(), D, g1, small, nU)
    assert fit.coef[0] == pytest.approx(b, rel=1e-8)
    assert fit.se[0] == pytest.approx(se, rel=1e-8)
    rf = rc.iv_fit(M[:, 0], M[:, 2:3], None, g1, small, k).coef[0]
    fs = rc.iv_fit(M[:, 1], M[:, 2:3], None, g1, small, k).coef[0]
    assert fit.coef[0] == pytest.approx(rf / fs, rel=1e-10)


def test_first_stage_f_is_cluster_robust_t_squared():
    """With one instrument the cluster-robust F is the first stage's t squared (1e-10 relative)."""
    out, reg, share, sp, _ = world(seed=3)
    f, g1, g2 = transformed(out, reg, share, sp)
    M = rc.within(f[["y", "d", "z"]].to_numpy(float), g1, g2)
    k = rc.absorbed_df_not_nested(g1, g2)
    fit = rc.iv_fit(M[:, 0], M[:, 1:2], M[:, 2:3], g1, "cr1_stata", k)
    fs = rc.iv_fit(M[:, 1], M[:, 2:3], None, g1, "cr1_stata", k)
    assert fit.first_stage_f == pytest.approx((fs.coef[0] / fs.se[0]) ** 2, rel=1e-10)
    assert fit.first_stage_coef[0] == pytest.approx(fs.coef[0], rel=1e-12)


def test_planted_effect_recovered_by_2sls_not_by_ols():
    """Planted 0.2 with an endogenous regressor, no cap: 2SLS within 0.03; OLS biased upward by more than 0.1.

    Uncapped on purpose: capping the regressor is part of the paper's specification and moves a 2SLS estimate away
    from the uncapped slope when the planted effect runs through the uncapped value.
    """
    out, reg, share, sp, _ = world(seed=4, states=tuple("ABCDEFGH"), per_state=100, beta=0.2, rho=1.0)
    r1 = rc.run_step("C1u", "", out, reg, share, sp, "paper", CH, None, True, None, None)
    r0 = rc.run_step("C0u", "", out, reg, share, None, None, CH, None, False, None, None)
    assert r1.failure is None and abs(r1.estimate - 0.2) < 0.03
    assert r0.estimate - 0.2 > 0.1


def test_absorbed_df_equals_numeric_rank():
    """K's state-by-year part equals rank([units, state-years]) less the unit count, exactly."""
    out, reg, share, sp, _ = world(seed=5, per_state=6)
    f, g1, g2 = transformed(out, reg, share, sp)
    U = pd.get_dummies(g1).to_numpy(float)
    S = pd.get_dummies(g2).to_numpy(float)
    assert rc.absorbed_df_not_nested(g1, g2) == np.linalg.matrix_rank(np.hstack([U, S])) - U.shape[1]


def test_within_is_exact_on_an_unbalanced_layout():
    """Alternating projections reach the dummy-variable residuals on an unbalanced layout (1e-9 absolute)."""
    rng = np.random.default_rng(6)
    out, reg, share, sp, _ = world(seed=6, per_state=8)
    f, g1, g2 = transformed(out, reg, share, sp)
    keep = rng.random(len(f)) > 0.2
    f = f[keep].reset_index(drop=True)
    g1, g2 = rc._codes(zip(f.utility_id_eia, f.state)), rc._codes(zip(f.state, f.year))
    M = rc.within(f[["y"]].to_numpy(float), g1, g2)[:, 0]
    D = np.hstack([pd.get_dummies(g1).to_numpy(float), pd.get_dummies(g2).to_numpy(float)])
    resid = f.y.to_numpy() - D @ np.linalg.lstsq(D, f.y.to_numpy(), rcond=None)[0]
    assert np.abs(M - resid).max() < 1e-9


def test_singletons_dropped_iteratively():
    """A state with one unit is all singletons in its state-years: all ten rows go when drop_singletons is on."""
    out, reg, share, sp, _ = world(seed=7, per_state=5)
    extra = pd.DataFrame({"utility_id_eia": 999, "state": "ZZ", "year": YEARS, "value": 1.0})
    share = {**share, (999, "ZZ"): 0.01}
    out2 = pd.concat([out, extra], ignore_index=True)
    p = rc.build_panel(out2, reg, share, sp, CH, None)
    _, _, _, dropped = rc._design(p, CH)
    assert dropped == 10
    _, _, _, kept = rc._design(p, replace(CH, drop_singletons=False))
    assert kept == 0


# ---------------------------------------------------------------------------------------------------------------
# Counts, cap, balanced panel, instrument
# ---------------------------------------------------------------------------------------------------------------
def test_operating_counts_rules():
    """Counted from the energized year on; crypto, undated and unassigned sites not counted and reported."""
    sites = pd.DataFrame({"fid": list("abcdef"), "energized_year": [2016, 2020, 2020, np.nan, 2018, 2022],
                          "is_crypto": [False, False, True, False, False, False]})
    asg = pd.DataFrame({"fid": list("abcde") + ["e"], "utility_id_eia": [1, 1, 1, 1, np.nan, 2],
                        "state": ["VA"] * 5 + ["MD"]})
    c, rep = rc.operating_counts(sites, asg)
    va = c[(c.utility_id_eia == 1)].set_index("year").value
    assert 2015 not in va.index
    assert va.loc[2016] == 1 and va.loc[2019] == 1 and va.loc[2020] == 2 and va.loc[2024] == 2
    md = c[(c.utility_id_eia == 2)].set_index("year").value
    assert md.loc[2018] == 1 and 2017 not in md.index
    assert rep["crypto_sites_not_counted"] == 1
    assert rep["data_center_sites_without_energized_year"] == 1
    assert rep["data_center_sites_without_an_assigned_utility"] == 1   # f
    assert set(c.year) <= set(YEARS)


def test_percentile_methods_hand_computed():
    v = np.arange(1, 11, dtype=float)
    assert rc.percentile(v, 50, "stata_default") == 5.5 and rc.percentile(v, 50, "linear") == 5.5
    assert rc.percentile(v, 95, "stata_default") == 10.0          # i = 9.5, the 10th
    assert rc.percentile(v, 95, "linear") == pytest.approx(9.55, abs=1e-12)
    w = np.arange(1, 201, dtype=float)
    assert rc.percentile(w, 99.5, "stata_default") == 199.5       # i = 199, mean of 199th and 200th
    assert rc.percentile(w, 99, "stata_default") == 198.5
    with pytest.raises(ValueError):
        rc.percentile(v, 50, "nearest")


def test_cap_is_within_year_and_top_only():
    f = pd.DataFrame({"year": [2020] * 10 + [2021] * 10,
                      "value": list(range(10)) + [x * 10 for x in range(10)]})
    caps = rc.yearly_caps(f, 90, "stata_default")
    assert caps == {2020: 8.5, 2021: 85.0}
    g = rc.apply_cap(f, caps)
    assert g.value.max() == 85.0 and g[g.year == 2020].value.max() == 8.5 and g.value.min() == 0


def test_balanced_units_rule():
    rows = [(1, "VA", y) for y in YEARS] + [(2, "VA", y) for y in YEARS[1:]] + [(3, "MD", y) for y in YEARS + [2014]]
    o = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year"])
    assert rc.balanced_units(o) == {(1, "VA"), (3, "MD")}
    with pytest.raises(ValueError):
        rc.balanced_units(pd.concat([o, o.head(1)]))


def test_instrument_values_and_spending_unit():
    uy = pd.DataFrame({"utility_id_eia": [1, 1, 1], "state": ["VA"] * 3, "year": [2020, 2021, 2024]})
    sp = {2021: 11.5, 2024: 31.1}
    z = rc.instrument(uy, {(1, "VA"): 0.002}, sp, CH)
    assert z[0] == 0.0
    assert z[1] == pytest.approx(math.log(11.5) * 0.2, rel=1e-12)
    assert z[2] == pytest.approx(math.log(31.1) * 0.2, rel=1e-12)
    with pytest.raises(ValueError, match="spending_log_unit"):         # billions inside the log: ours, D-107
        rc.instrument(uy, {(1, "VA"): 0.002}, sp, replace(CH, spending_log_unit="millions"))
    with pytest.raises(ValueError):
        rc.instrument(uy, {(1, "VA"): 0.002}, {2021: 11.5}, CH)


def test_spending_series_reads_both_columns():
    t = pd.DataFrame({"year": [2020, 2021, 2024, 2025], "real_2024_musd": [11188.3, 11517.5, 34797.0, 48461.8],
                      "paper_table_s3_real_2024_bn": [11.2, 11.5, 31.1, np.nan]})
    assert rc.spending_series(t, "paper") == {2020: 11.2, 2021: 11.5, 2024: 31.1}
    assert rc.spending_series(t, "current")[2024] == pytest.approx(34.797)


def test_choices_reject_unknown_values():
    with pytest.raises(ValueError):
        replace(CH, small_sample="hc3")


# ---------------------------------------------------------------------------------------------------------------
# Steps and the plan's readings
# ---------------------------------------------------------------------------------------------------------------
def test_c0_and_c1_return_labelled_comparisons_inside_and_outside_the_band():
    """Planted 0.182 with a strong instrument: C1 lands inside the plan's band with F above 10 and still returns the
    labelled comparison and no verdict (D-107). Planted 0.5: outside the band, the same. C0 inside its band: the C0
    label with the band beside it, no verdict."""
    out, reg, share, sp, _ = world(seed=8, states=tuple("ABCDEF"), per_state=60, beta=0.182, share_mult=3)
    r = rc.c1(out, reg, share, sp, "paper", CH)
    assert 0.114 <= r.estimate <= 0.250 and r.first_stage_f >= 10            # inside the band, strong first stage
    assert r.band == (0.114, 0.250) and r.comparison["label"] == rc.C_INSTRUMENTED_COMPARISON_LABEL
    assert r.comparison["verdict"] is None and r.paper["estimate"] == 0.182 and r.paper["se"] == 0.034
    assert not hasattr(r, "reproduced") and not hasattr(r, "in_band") and not hasattr(r, "sentence")
    out2, reg2, share2, sp2, _ = world(seed=8, states=tuple("ABCDEF"), per_state=60, beta=0.5, share_mult=3)
    m = rc.c1(out2, reg2, share2, sp2, "paper", CH)
    assert m.estimate > 0.25 and m.comparison["label"] == rc.C_INSTRUMENTED_COMPARISON_LABEL
    assert m.comparison["verdict"] is None
    o0, r0, s0, _, _ = world(seed=9, states=tuple("ABCDEF"), per_state=60, beta=0.061, rho=0.0)
    c0 = rc.c0(o0, r0, s0, CH)
    assert 0.025 <= c0.estimate <= 0.097 and c0.band == (0.025, 0.097) and c0.first_stage_f is None
    assert c0.comparison["label"] == rc.C0_COMPARISON_LABEL and c0.comparison["verdict"] is None
    assert c0.comparison["band_beside"] == (0.025, 0.097)


def test_compare_sets_no_verdict_whatever_the_estimate_and_f():
    for est, f in ((0.2, 9.99), (0.2, 59.0), (0.5, 59.0), (-0.1, 1.0)):
        r = rc._compare(rc.StepResult(step="C1", label="", estimator="2sls", spending_series="paper", estimate=est,
                                      se=0.05, first_stage_f=f), "C1")
        assert r.comparison["verdict"] is None and r.comparison["label"] == rc.C_INSTRUMENTED_COMPARISON_LABEL
        assert r.comparison["first_stage_f_ours"] == f and r.comparison["first_stage_f_floor_in_the_plans_band"] == 10.0
    r = rc._compare(rc.StepResult(step="C0", label="", estimator="ols", spending_series=None, estimate=0.06), "C0")
    assert r.comparison["label"] == rc.C0_COMPARISON_LABEL and r.comparison["first_stage_f_floor_in_the_plans_band"] is None


def test_c2_three_caps_in_order_no_band():
    out, reg, share, sp, _ = world(seed=10)
    reg = reg.assign(value=np.abs(reg.value) * 3)
    res = rc.c2(out, reg, share, sp, "current", CH)
    assert [r.step for r in res] == ["C2_none", "C2_99.9", "C2_99.0"]
    assert [r.paper["estimate"] for r in res] == [0.110, 0.150, 0.236]
    assert all(r.band is None and r.comparison["label"] == rc.C_INSTRUMENTED_COMPARISON_LABEL for r in res)
    assert res[0].caps == {} and res[2].accounting["unit_years_changed_by_cap"] > 0


def test_c4_cap_is_a_required_argument():
    assert inspect.signature(rc.c4).parameters["cap"].default is inspect.Parameter.empty


def test_numerical_failure_is_reported_in_words():
    """An instrument with no variation (every share zero) gives a worded failure, not an exception or a number."""
    out, reg, share, sp, _ = world(seed=11, per_state=5)
    r = rc.c1(out, reg, {k: 0.0 for k in share}, sp, "paper", CH)
    assert r.failure and "C1 could not be estimated" in r.failure and math.isnan(r.estimate)
    assert r.comparison["verdict"] is None


def test_ownership_split_recovers_planted_effects():
    """Planted 0.30 at investor-owned and 0.05 elsewhere: the paper's interaction form recovers each within 0.06."""
    out, reg, share, sp, own = world(seed=12, states=tuple("ABCDEF"), per_state=60, own_beta={True: 0.30, False: 0.05},
                             share_mult=3)
    i = rc.ownership_split("C1", out, reg, share, sp, "paper", CH, None, own)
    assert i["method"] == "interaction" and i["paper"]["sw_f_baseline"] == 55.44
    assert abs(i["investor_owned"]["estimate"] - 0.30) < 0.06 and abs(i["all_other"]["estimate"] - 0.05) < 0.06
    assert i["other_minus_investor_owned"]["estimate"] == pytest.approx(
        i["all_other"]["estimate"] - i["investor_owned"]["estimate"], abs=1e-12)
    with pytest.raises(ValueError, match="separate samples are not the paper's specification"):
        rc.ownership_split("C1", out, reg, share, sp, "paper", replace(CH, ownership_method="split_samples"), None, own)


# ---------------------------------------------------------------------------------------------------------------
# What the bounded read settled (docs/gate1/bounded-read-row-c-2026-11-19.md)
# ---------------------------------------------------------------------------------------------------------------
def test_settled_choices_are_accepted_and_checked_in_words():
    """The three settled fields stay accepted by Choices; any other value stops where used, naming the paper's place."""
    out, reg, share, sp, _ = world(seed=17, per_state=6)
    for field, bad, words in (("share_in_percent", False, "Table S4"), ("contiguous_only", False, "section 2.1"),
                              ("ownership_method", "split_samples", "Table 3 col 1")):
        ch = replace(CH, **{field: bad})          # construction still works (callers keep working)
        with pytest.raises(ValueError, match=words):
            rc.check_paper_settled(ch)
        with pytest.raises(ValueError, match="a choice the paper settles"):
            rc.run_row_c(out, reg, reg, reg, share, {"paper": sp}, ch, {}, None, set(), "x")
    with pytest.raises(ValueError, match="Table S4"):
        rc.instrument(out.head(3), share, sp, replace(CH, share_in_percent=False))
    with pytest.raises(ValueError, match="contiguous"):
        rc.build_panel(out, reg, share, sp, replace(CH, contiguous_only=False), None)
    rc.check_paper_settled(CH)                    # the specification carries the paper's values


def test_paper_constants_are_the_printed_values():
    """The constants carry the paper's printed numbers; the printed F is the first stage's t squared to rounding."""
    assert (rc.POST_FROM, rc.CAP_MAIN, rc.C2_CAPS, rc.YEARS[0], rc.YEARS[-1]) == (2021, 99.5, (None, 99.9, 99.0), 2015, 2024)
    assert rc.SHARE_IN_PERCENT is True and rc.CONTIGUOUS_ONLY is True and rc.OWNERSHIP_METHOD == "interaction"
    assert rc.FIBER_TECHNOLOGY_CODE == 50 and rc.FIBER_YEARS == (2017, 2018, 2019)
    P = rc.PAPER
    assert (P["C0"]["estimate"], P["C0"]["se"], P["C1"]["estimate"], P["C1"]["se"], P["C1"]["first_stage_f"]) == \
        (0.061, 0.018, 0.182, 0.034, 59.43)
    assert [P[k]["estimate"] for k in ("C2_none", "C2_99.9", "C2_99.0")] == [0.110, 0.150, 0.236]
    assert [P[k]["max_stock"] for k in ("C2_none", "C2_99.9", "C1", "C2_99.0")] == [280, 127, 62, 38]
    fs = P["first_stage_coef_count"]
    assert fs["estimate"] / math.sqrt(fs["first_stage_f"]) == pytest.approx(fs["se"], abs=0.0005)   # 0.1101 vs 0.11
    rf = P["C5_full_reduced_form"]["estimate"]
    assert rf / fs["estimate"] == pytest.approx(P["C1"]["estimate"], abs=0.001)                     # RF / FS = 2SLS
    t = P["thirteen_percent"]
    assert t["effect_cents"] / t["post_2021_mean_price_cents"] == pytest.approx(0.13, abs=0.001)
    assert P["sample"]["regression_obs"] == 10 * P["sample"]["regression_units"]
    s3 = P["spending_table_s3_bn_real_2024"]
    assert [s3[y] for y in range(2021, 2025)] == [11.5, 13.5, 20.6, 31.1]


def test_cap_accounting_reports_max_before_and_after():
    """One unit with a planted outlier: after a 90th-percentile cap the maximum is the year's cap, before it the raw."""
    out, reg, share, sp, _ = world(seed=18, per_state=10)
    reg = reg.assign(value=np.abs(reg.value).round())
    u = (reg.utility_id_eia == reg.utility_id_eia.iloc[0]) & (reg.year == 2024)
    reg.loc[u, "value"] = 500.0
    p = rc.build_panel(out, reg, share, None, CH, 90.0)
    assert p.accounting["max_regressor_before_cap"] == 500.0
    assert p.accounting["max_regressor_after_cap"] == pytest.approx(max(p.caps.values()), abs=1e-12)
    assert p.accounting["max_regressor_after_cap"] < 500.0 and p.accounting["units_changed_by_cap"] >= 1


def test_zero_share_units_stay_and_missing_share_units_go():
    """The paper keeps territories with no fiber (Table S4 minimum 0): a zero share stays, a missing share drops."""
    out, reg, share, sp, _ = world(seed=19, per_state=5)
    ks = sorted(share)
    share2 = {**share, ks[0]: 0.0}
    del share2[ks[1]]
    p = rc.build_panel(out, reg, share2, sp, CH, None)
    units = set(zip(p.frame.utility_id_eia, p.frame.state))
    assert ks[0] in units and ks[1] not in units
    assert p.accounting["balanced_units_dropped_no_fiber_share"] == 1
    assert (p.frame.loc[(p.frame.utility_id_eia == ks[0][0]), "z"] == 0).all()


def test_non_contiguous_units_are_always_dropped():
    out, reg, share, sp, _ = world(seed=20, states=("AA", "HI"), per_state=5)
    p = rc.build_panel(out, reg, share, sp, CH, None)
    assert set(p.frame.state) == {"AA"} and p.accounting["balanced_units_contiguous"] == 5


def test_open_choices_have_no_default():
    """Every Choices field is required: the open ones because the paper does not settle them."""
    for name, prm in inspect.signature(rc.Choices).parameters.items():
        assert prm.default is inspect.Parameter.empty, name
    assert rc.SPECIFICATION.never_host_basis == "zero_count_panel_years" and not hasattr(rc, "AGENT_READING")


def test_sw_f_equals_ordinary_f_with_one_endogenous():
    out, reg, share, sp, _ = world(seed=13)
    f, g1, g2 = transformed(out, reg, share, sp)
    M = rc.within(f[["y", "d", "z"]].to_numpy(float), g1, g2)
    k = rc.absorbed_df_not_nested(g1, g2)
    fit = rc.iv_fit(M[:, 0], M[:, 1:2], M[:, 2:3], g1, "cr1_stata", k)
    assert rc.sw_conditional_f(M[:, 1:2], M[:, 2:3], g1, "cr1_stata", k)[0] == pytest.approx(fit.first_stage_f, rel=1e-10)


def test_interaction_2sls_equals_dummy_2sls():
    """Two endogenous, two instruments: equal to the dummy-variable fit (1e-8 relative)."""
    out, reg, share, sp, own = world(seed=14, own_beta={True: 0.3, False: 0.1})
    f, g1, g2 = transformed(out, reg, share, sp)
    o = np.array([own[u] != "investor_owned" for u in zip(f.utility_id_eia, f.state)], float)
    X = np.column_stack([f.d, f.d * o]); Z = np.column_stack([f.z, f.z * o])
    M = rc.within(np.column_stack([f.y, X, Z]), g1, g2)
    fit = rc.iv_fit(M[:, 0], M[:, 1:3], M[:, 3:5], g1, "none", 0)
    D, nU = dummies(f)
    b, se = brute(f.y.to_numpy(), X, Z, D, g1, "none", nU)
    assert fit.coef[0] == pytest.approx(b, rel=1e-8) and fit.se[0] == pytest.approx(se, rel=1e-8)


# ---------------------------------------------------------------------------------------------------------------
# C5
# ---------------------------------------------------------------------------------------------------------------
A, B = rc.C5_SENTENCE_INSTRUMENT_REACHES, rc.C5_SENTENCE_NOT_DETECTED


@pytest.mark.parametrize("never,lo,hi,full,reading,sentence", [
    (0.10, 0.02, 0.18, 0.15, "instrument_reaches_non_hosts", A),     # >= half, excludes zero
    (0.075, 0.01, 0.14, 0.15, "instrument_reaches_non_hosts", A),    # exactly half counts as at least half
    (-0.20, -0.30, -0.10, 0.15, "unresolved", None),                 # excludes zero but under half
    (0.02, -0.05, 0.09, 0.15, "not_detected", B),                    # includes zero, under half
    (0.0749, 0.0, 0.15, 0.15, "not_detected", B),                    # endpoint at zero includes zero
    (0.075, -0.01, 0.16, 0.15, "unresolved", None),                  # includes zero, exactly half: not under half
    (0.12, -0.01, 0.25, 0.15, "unresolved", None),                   # includes zero, above half
    (0.05, 0.01, 0.09, 0.15, "unresolved", None),                    # excludes zero, under half
])
def test_c5_reading_branches(never, lo, hi, full, reading, sentence):
    r = rc.c5_reading(never, lo, hi, full)
    assert r["reading"] == reading and r["sentence"] == sentence
    if reading == "not_detected":
        assert "failure to detect" in r["sentence"] and r["note"] is None and "passes" not in r["sentence"]


def test_c5_reading_edges():
    assert rc.c5_reading(0.1, 0.05, 0.15, 0.0)["reading"] == "unresolved_plan_silent"
    neg = rc.c5_reading(-0.05, -0.08, -0.02, -0.15)
    assert neg["reading"] == "unresolved_plan_silent" and neg["literal_branch"] == "instrument_reaches_non_hosts"
    assert rc.c5_reading(float("nan"), 0, 1, 0.1)["reading"] == "numerical_failure"
    with pytest.raises(ValueError):
        rc.c5_reading(0.1, 0.2, 0.1, 0.1)


def _hosts_by_share(share, frac=0.5):
    """The units with the larger shares host; the rest never do."""
    ks = sorted(share, key=share.get)
    return set(ks[int(len(ks) * frac):])


def test_c5_end_to_end_direct_effect_at_non_hosts():
    """Instrument moves price directly everywhere (planted 0.2 per unit of Z): the first sentence."""
    out, reg, share, sp, _ = world(seed=15, states=tuple("ABCDEF"), per_state=60, beta=0.0, direct=0.2, share_mult=3)
    r = rc.c5(out, share, sp, "paper", CH, _hosts_by_share(share))
    assert abs(r["full_sample"]["estimate"] - 0.2) < 0.05
    assert r["reading"]["reading"] == "instrument_reaches_non_hosts" and r["reading"]["sentence"] == A
    assert r["paper_full_sample"]["estimate"] == 0.155
    lo, hi = r["never_host"]["extra"]["interval_90"]
    assert lo < r["never_host"]["estimate"] < hi


def test_c5_end_to_end_effect_only_through_hosts():
    """Price moves only through d, and d is zero at never-hosts: the never-host relationship is not detected."""
    out, reg, share, sp, _ = world(seed=16, states=tuple("ABCDEF"), per_state=60, beta=0.2, rho=0.0, share_mult=3)
    hosts = _hosts_by_share(share)
    never = {k for k in share if k not in hosts}
    # never-hosts' price carries no d: rebuild their outcome without the beta * d term
    o = out.merge(reg.rename(columns={"value": "d"}), on=["utility_id_eia", "state", "year"])
    nh = pd.Series([(u, s) in never for u, s in zip(o.utility_id_eia, o.state)])
    o.loc[nh.values, "value"] = o.loc[nh.values, "value"] - 0.2 * o.loc[nh.values, "d"]
    r = rc.c5(o[["utility_id_eia", "state", "year", "value"]], share, sp, "paper", CH, hosts)
    assert r["full_sample"]["estimate"] > 0.1
    assert r["reading"]["reading"] == "not_detected" and r["reading"]["sentence"] == B


def test_never_host_bases():
    sites = pd.DataFrame({"fid": ["a", "b", "c"], "energized_year": [np.nan, 2026, 2018],
                          "is_crypto": [False, False, True]})
    asg = pd.DataFrame({"fid": ["a", "b", "c"], "utility_id_eia": [1, 2, 3], "state": ["VA", "VA", "TX"]})
    counts, _ = rc.operating_counts(sites, asg)
    assert rc.never_host_units(sites, asg, counts, "no_assigned_site") == {(1, "VA"), (2, "VA")}
    assert rc.never_host_units(sites, asg, counts, "zero_count_panel_years") == set()


def test_module_names_no_price_source():
    """The module never names a price file or a price loader."""
    src = Path(rc.__file__).read_text()
    for bad in ("data/blind", "load_outcomes", "read_listed_outcomes", "availability/", "DECISIONS.md"):
        assert bad not in src


# ---------------------------------------------------------------------------------------------------------------
# Row C's specification since D-107, and what may be claimed
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("field,bad", [("percentile_method", "linear"), ("cap_population", "supplied_universe"),
                                       ("spending_log_unit", "millions"), ("small_sample", "cr1_cluster"),
                                       ("drop_singletons", False), ("interval", "normal"),
                                       ("never_host_basis", "no_assigned_site")])
def test_each_approximation_of_ours_is_refused_in_words_if_departed_from(field, bad):
    out, reg, share, sp, _ = world(seed=17, per_state=6)
    ch = replace(CH, **{field: bad})
    with pytest.raises(ValueError, match="refuses to depart from its specification") as e:
        rc.check_specification(ch)
    assert field in str(e.value) and "ours and not the paper's" in str(e.value) and "D-107" in str(e.value)
    with pytest.raises(ValueError, match="refuses to depart"):
        rc.build_panel(out, reg, share, sp, ch, None)


def test_the_specification_is_the_constants_and_each_carries_its_label():
    assert rc.SPECIFICATION == rc.Choices(percentile_method="stata_default", cap_population="estimation_sample",
                                          spending_log_unit="billions", small_sample="cr1_stata", drop_singletons=True,
                                          share_in_percent=True, ownership_method="interaction",
                                          interval="t_G_minus_1", never_host_basis="zero_count_panel_years",
                                          contiguous_only=True, price_deflator="cpi_u_annual_average",
                                          price_series="res_price")
    assert rc.OURS_C4_CAP == rc.CAP_MAIN == 99.5 and rc.SHARE_COLUMN == "fiber_share_dec"
    assert rc.OURS_C5_SPENDING == ("paper", "current")
    for k, v in rc.OURS_APPROXIMATIONS.items():
        if k == "price_series":   # D-117: "our comparison specification", not a claim about the paper either way
            assert v["label"].startswith("Our comparison specification") and "D-117" in v["label"], k
            continue
        assert "ours, not the paper's" in v["label"], k
        assert ("D-111" in v["label"]) if k == "price_deflator" else ("D-107" in v["label"]), k
    assert len(rc.UNAVAILABLE) == 3 and any("1,243" in u for u in rc.UNAVAILABLE)


def test_c4_cap_is_the_count_cap_and_nothing_else():
    out, reg, share, sp, _ = world(seed=10)
    for bad in (None, 99.0, 99.9):
        with pytest.raises(ValueError, match="caps the load share at the 99.5th"):
            rc.c4(out, reg, share, sp, "paper", CH, bad)
    r = rc.c4(out, reg.assign(value=np.abs(reg.value)), share, sp, "paper", CH, rc.OURS_C4_CAP)
    assert r.caps and r.comparison["label"] == rc.C_INSTRUMENTED_COMPARISON_LABEL


def _row_c_world(beta, seed=8):
    """A world for the whole row: half the units (larger shares) host, the rest carry no facility in any year."""
    out, reg, share, sp, own = world(seed=seed, states=tuple("ABCDEF"), per_state=60, beta=beta, rho=0.0,
                                     share_mult=3)
    hosts = _hosts_by_share(share)
    d = reg.copy()
    d["value"] = [abs(v) if (u, st) in hosts else 0.0 for u, st, v in zip(d.utility_id_eia, d.state, d.value)]
    o = out.merge(reg.rename(columns={"value": "d_old"}), on=["utility_id_eia", "state", "year"])
    o = o.merge(d.rename(columns={"value": "d_new"}), on=["utility_id_eia", "state", "year"])
    o["value"] = o.value + beta * (o.d_new - o.d_old)
    counts = d[d.value > 0]
    return o[["utility_id_eia", "state", "year", "value"]], counts, share, sp, own


VERDICT = re.compile(r"\breproduced\b|\bsurviv|matches the paper|\bas a miss\b|\bnot reproduce\b", re.IGNORECASE)
VERDICT_KEYS = {"reproduced", "in_band", "f_at_least_10", "survives"}


def _walk(x, path="r"):
    if isinstance(x, dict):
        for k, v in x.items():
            yield path, str(k), "key"
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(x, str):
        yield path, x, "text"


def _verdicts(res):
    return [(p, v) for p, v, kind in _walk(res) if (kind == "text" and VERDICT.search(v)) or
            (kind == "key" and v in VERDICT_KEYS)]


@pytest.mark.parametrize("beta", [0.182, 0.061, 0.5])
def test_no_row_c_output_carries_a_reproduction_verdict(beta):
    """The whole row on both spending series, with C1 inside the plan's band (0.182), C0 inside its band (0.061), and
    both outside (0.5): every instrumented result (C1, C2, C3, C4, both ownership splits, C5's yardstick) carries the
    instrumented label, C0 the C0 label with its band beside it, and no output carries a verdict word or key."""
    o, counts, share, sp, own = _row_c_world(beta)
    tables = {"paper": sp, "current": {y: v * 1.1 for y, v in sp.items()}}
    hosts = rc.never_host_units(None, None, counts, rc.OURS_NEVER_HOST_BASIS)
    res = rc.run_row_c(o, counts, counts, counts.assign(value=counts.value * 0.01), share, tables, CH, own,
                       rc.OURS_C4_CAP, hosts, "the invented verified counts")
    assert _verdicts(res) == []
    assert [t for _, t, k in _walk(res) if k == "text" and ("until Joe rules" in t or "waits on" in t)] == []
    assert res["missing_coverage"] == rc.rt.MISSING_COVERAGE_QUALIFICATION
    assert res["assignment_c0_to_c2"] == rc.rt.ROW_U_C_COINCIDENCE
    steps = res["steps"]
    for x in steps:
        if x["step"] == "C0":
            assert x["comparison"]["label"] == rc.C0_COMPARISON_LABEL and x["comparison"]["band_beside"] == (0.025, 0.097)
        elif x["step"] == "C5":
            assert x["yardstick_comparison"]["label"] == rc.C_INSTRUMENTED_COMPARISON_LABEL
            assert x["yardstick_comparison"]["verdict"] is None
            assert x["missing_coverage"] == rc.rt.MISSING_COVERAGE_QUALIFICATION
            assert x["never_host_limitation"] == rc.C5_NEVER_HOST_LIMITATION
        else:
            assert x["comparison"]["label"] == rc.C_INSTRUMENTED_COMPARISON_LABEL and x["comparison"]["verdict"] is None
        if x["step"] != "C5":
            assert x["comparison"]["missing_coverage"] == rc.rt.MISSING_COVERAGE_QUALIFICATION
    c1 = [x for x in steps if x["step"] == "C1" and "estimate" in x]
    assert [x["spending_series"] for x in c1] == ["paper", "current"]
    assert res["specification"]["ours_adopted_2026_11_19_d107"] == rc.OURS_APPROXIMATIONS
    if beta == 0.182:
        assert 0.114 <= c1[0]["estimate"] <= 0.250                     # inside the band, and still no verdict
    if beta == 0.061:
        assert 0.025 <= steps[0]["estimate"] <= 0.097


def test_run_row_c_refuses_a_departure_and_notes_a_missing_current_series():
    o, counts, share, sp, own = _row_c_world(0.182)
    hosts = rc.never_host_units(None, None, counts, rc.OURS_NEVER_HOST_BASIS)
    args = (o, counts, counts, counts.assign(value=counts.value * 0.01), share)
    with pytest.raises(ValueError, match="c4_cap"):
        rc.run_row_c(*args, {"paper": sp}, CH, own, None, hosts, "x")
    with pytest.raises(ValueError, match="must carry 'paper'"):
        rc.run_row_c(*args, {"current": sp}, CH, own, rc.OURS_C4_CAP, hosts, "x")
    with pytest.raises(ValueError, match="must carry 'paper'"):
        rc.run_row_c(*args, {"paper": sp, "revised": sp}, CH, own, rc.OURS_C4_CAP, hosts, "x")
    with pytest.raises(ValueError, match="inventory's own assignment"):
        rc.run_row_c(*args, {"paper": sp}, CH, own, rc.OURS_C4_CAP, set(list(hosts)[:-1]), "x")
    r = rc.run_row_c(*args, {"paper": sp}, CH, own, rc.OURS_C4_CAP, hosts, "x")
    assert "current Census spending series was not supplied" in r["notes"][0]


def test_c5_first_sentence_carries_its_wording_status():
    out, reg, share, sp, _ = world(seed=15, states=tuple("ABCDEF"), per_state=60, beta=0.0, direct=0.2, share_mult=3)
    r = rc.c5(out, share, sp, "paper", CH, _hosts_by_share(share))
    assert r["reading"]["sentence"] == A and r["reading"]["wording_status"] == rc.C5_WORDING_STATUS
    assert r["yardstick_comparison"]["paper_full_sample"]["estimate"] == 0.155


def test_the_row_c_labels_carry_no_verdict_word_and_no_verdict_constant_remains():
    for name in ("C_INSTRUMENTED_COMPARISON_LABEL", "C0_COMPARISON_LABEL", "C5_WORDING_STATUS", "FACILITY_LIST_CAVEAT",
                 "C5_SENTENCE_INSTRUMENT_REACHES", "C5_SENTENCE_NOT_DETECTED", "C5_NEVER_HOST_LIMITATION"):
        assert not VERDICT.search(getattr(rc, name)), name
        assert "until Joe rules" not in getattr(rc, name) and "waits on" not in getattr(rc, name), name
    assert not hasattr(rc, "C5_NOT_DETECTED_QUALIFIER")          # its words are inside the adopted sentence (D-109)
    assert "unit by unit" in rc.C_INSTRUMENTED_COMPARISON_LABEL and "billions" in rc.C_INSTRUMENTED_COMPARISON_LABEL
    assert not hasattr(rc, "PLAN_MISS_CAVEAT") and not hasattr(rc, "_judge")
    # every non-docstring string literal in the module
    tree = ast.parse(Path(rc.__file__).read_text())
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    lits = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs]
    assert [x for x in lits if VERDICT.search(x)] == []


def test_a_singular_clustered_variance_is_a_numerical_failure_in_words(monkeypatch):
    """b' V^-1 b with a singular V raises NumericalFailure in words, not a LinAlgError; in the ownership split the
    coefficients stand and the conditional F is reported as not computed."""
    with pytest.raises(rc.NumericalFailure, match="singular"):
        rc._wald(np.array([1.0, 1.0]), np.array([[1.0, 1.0], [1.0, 1.0]]))
    assert rc._wald(np.array([2.0]), np.array([[4.0]])) == pytest.approx(1.0, abs=1e-12)
    out, reg, share, sp, own = world(seed=12, states=tuple("ABCDEF"), per_state=60, own_beta={True: 0.30, False: 0.05},
                                     share_mult=3)

    def singular(*a, **k):
        raise rc.NumericalFailure("the clustered variance of the excluded instruments is singular (test)")
    monkeypatch.setattr(rc, "sw_conditional_f", singular)
    i = rc.ownership_split("C1", out, reg, share, sp, "paper", CH, None, own)
    assert i["failure"] is None and abs(i["investor_owned"]["estimate"] - 0.30) < 0.06
    assert i["investor_owned"]["sw_f"] is None and "could not be computed" in i["sw_f_failure"]


# ---------------------------------------------------------------------------------------------------------------
# Joe's ruling of 2026-11-19 (D-109): comparison-only labels, C5's adopted wording, the missing-coverage
# qualification kept apart from the operational never-host classification
# ---------------------------------------------------------------------------------------------------------------
C5_DETECTED_AS_RULED = (
    "If a relationship is detected, our instrument also predicts price changes among utilities classified as never "
    "hosting a data center. This does not distinguish spillovers from other correlated influences, and it does not "
    "establish whether the paper’s differently constructed instrument identifies an effect of hosting.")
C5_NOT_DETECTED_AS_ADOPTED = (
    "The test did not detect a relationship between our instrument and price among utilities classified as never "
    "hosting a data center. That is a failure to detect, with a test that may have low power, and it does not show "
    "that our instrument or the paper's is valid.")


def test_c5_text_is_the_adopted_wording_character_for_character():
    assert rc.C5_SENTENCE_INSTRUMENT_REACHES == C5_DETECTED_AS_RULED
    assert "paper’s" in rc.C5_SENTENCE_INSTRUMENT_REACHES and "paper's" not in rc.C5_SENTENCE_INSTRUMENT_REACHES
    assert rc.C5_SENTENCE_NOT_DETECTED == C5_NOT_DETECTED_AS_ADOPTED
    assert "13%" not in rc.C5_SENTENCE_INSTRUMENT_REACHES + rc.C5_SENTENCE_NOT_DETECTED
    st = rc.C5_WORDING_STATUS
    assert "Adopted by Joe on 2026-11-19 (D-109)" in st and "neither is a draft" in st and "unresolved" in st
    # the branch logic is unchanged and only the text moved: the same inputs pick the same branches as before
    assert rc.c5_reading(0.10, 0.02, 0.18, 0.15)["sentence"] == C5_DETECTED_AS_RULED
    assert rc.c5_reading(0.02, -0.05, 0.09, 0.15)["sentence"] == C5_NOT_DETECTED_AS_ADOPTED
    assert rc.c5_reading(0.05, 0.01, 0.09, 0.15)["sentence"] is None
    assert "Reported as unresolved" in rc.c5_reading(0.05, 0.01, 0.09, 0.15)["note"]


def test_both_c5_sentences_carry_the_adopted_wording_status():
    out, reg, share, sp, _ = world(seed=16, states=tuple("ABCDEF"), per_state=60, beta=0.2, rho=0.0, share_mult=3)
    hosts = _hosts_by_share(share)
    never = {k for k in share if k not in hosts}
    o = out.merge(reg.rename(columns={"value": "d"}), on=["utility_id_eia", "state", "year"])
    nh = pd.Series([(u, s) in never for u, s in zip(o.utility_id_eia, o.state)])
    o.loc[nh.values, "value"] = o.loc[nh.values, "value"] - 0.2 * o.loc[nh.values, "d"]
    r = rc.c5(o[["utility_id_eia", "state", "year", "value"]], share, sp, "paper", CH, hosts)
    assert r["reading"]["sentence"] == C5_NOT_DETECTED_AS_ADOPTED and r["reading"]["wording_status"] == rc.C5_WORDING_STATUS


def test_c0_and_instrumented_labels_are_comparison_only_by_d109():
    for lab in (rc.C0_COMPARISON_LABEL, rc.C_INSTRUMENTED_COMPARISON_LABEL):
        assert lab.startswith("Comparison-only, by Joe's ruling of 2026-11-19 (D-109)") and "until Joe rules" not in lab
    # the C0 label's figures are the paper's printed C0 and the plan's band
    assert f"{rc.PAPER['C0']['estimate']:.3f} ({rc.PAPER['C0']['se']:.3f}" in rc.C0_COMPARISON_LABEL
    assert f"{rc.BANDS['C0'][0]} to {rc.BANDS['C0'][1]}" in rc.C0_COMPARISON_LABEL
    assert "No verdict is given" in rc.C0_COMPARISON_LABEL and "same rule as row U's U0" in rc.C0_COMPARISON_LABEL


# An invented world for the never-host classification, with its expected sample written out by hand. Counts by unit and
# year (positive rows only), 2015-2024 being the panel years:
#   (1, AA) operates from 2018: a host.         (2, AA) a row in 2014 only (outside the panel years): never-host.
#   (3, AA) no row at all: never-host.          (4, BB) operates in 2024 only: a host.
#   (5, BB) a row in 2025 only (outside): never-host.
NH_COUNTS = pd.DataFrame({"utility_id_eia": [1, 1, 2, 4, 5], "state": ["AA", "AA", "AA", "BB", "BB"],
                          "year": [2018, 2024, 2014, 2024, 2025], "value": [1.0, 2.0, 1.0, 1.0, 3.0]})
NH_HOSTS_EXPECTED = {(1, "AA"), (4, "BB")}
NH_NEVER_EXPECTED = {(2, "AA"), (3, "AA"), (5, "BB")}


def test_the_never_host_sample_is_unchanged_and_the_qualification_redefines_nothing():
    """The operational classification (no facility counted in any panel year under the inventory's own assignment) is
    the same set as written out by hand, and C5 restricts its never-host fit to exactly those units; the
    qualification is carried beside it and changes no unit."""
    hosts = rc.never_host_units(None, None, NH_COUNTS, rc.OURS_NEVER_HOST_BASIS)
    assert hosts == NH_HOSTS_EXPECTED
    assert rc.OURS_NEVER_HOST_BASIS == "zero_count_panel_years"
    units = sorted({(1, "AA"), (2, "AA"), (3, "AA"), (4, "BB"), (5, "BB")})
    rng = np.random.default_rng(3)
    o = pd.DataFrame([(u, s, y, 10.0 + rng.normal()) for u, s in units for y in YEARS],
                     columns=["utility_id_eia", "state", "year", "value"])
    share = {k: 0.001 * (i + 1) for i, k in enumerate(units)}
    sp = {2021: 11.5, 2022: 13.5, 2023: 20.6, 2024: 31.1}
    r = rc.c5(o, share, sp, "paper", CH, hosts)
    assert r["never_host_units_in_outcome"] == len(NH_NEVER_EXPECTED)
    assert r["never_host"]["accounting"]["units_after_restriction"] == len(NH_NEVER_EXPECTED)
    assert r["full_sample"]["accounting"]["units"] == len(units)
    assert r["never_host_limitation"] == rc.C5_NEVER_HOST_LIMITATION
    assert "unchanged" in rc.C5_NEVER_HOST_LIMITATION and "redefines nothing" in rc.C5_NEVER_HOST_LIMITATION
    assert "no assigned site is not proof of no facility" in rc.C5_NEVER_HOST_LIMITATION
    assert r["missing_coverage"] == rc.rt.MISSING_COVERAGE_QUALIFICATION
    assert set(units) - hosts == NH_NEVER_EXPECTED


# ---------------------------------------------------------------------------------------------------------------
# Row C's price deflator (Joe, 2026-11-19, D-111): the CPI-U annual average on file, ours, not the caller's choice
# ---------------------------------------------------------------------------------------------------------------
def test_the_deflator_is_a_named_constant_with_its_label():
    assert rc.OURS_PRICE_DEFLATOR == "cpi_u_annual_average" and rc.SPECIFICATION.price_deflator == rc.OURS_PRICE_DEFLATOR
    assert rc.DEFLATOR_SERIES_ID == "CUUR0000SA0" and rc.DEFLATOR_COLUMN == "cpi_u" and rc.DEFLATOR_BASE_YEAR == 2024
    assert rc.DEFLATOR_TABLE == "data/frozen/dc_construction_spending.csv"
    assert rc.OURS_D111_DEFLATOR == ("ours, not the paper's: this study's convention, adopted by Joe on 2026-11-19 "
                                     "(D-111)")
    lab = rc.PRICE_DEFLATOR_LABEL
    assert lab.startswith(rc.OURS_D111_DEFLATOR)
    assert rc.OURS_APPROXIMATIONS["price_deflator"]["label"] == lab
    assert "adopted by Joe on 2026-11-19 (D-111)" in lab and "ours, not the paper's" in lab
    assert "does not establish that it is the paper's series" in lab and "not established" in lab
    assert "the CPI" in lab and "2015 to 2023" in lab and "CUUR0000SA0" in lab and "nothing is fetched" in lab
    assert "agent's reading" not in lab
    assert "That the paper used this same series is the agent's reading" not in inspect.getdoc(rc)
    assert "supports and does not establish that it is the paper's series" in inspect.getdoc(rc)
    assert not VERDICT.search(lab)                                    # the label carries no verdict phrase


@pytest.mark.parametrize("bad", ["pce_chain", "cpi_u_rs", "caller_supplied", ""])
def test_a_caller_that_supplies_another_deflator_is_refused_in_words(bad):
    out, reg, share, sp, _ = world(seed=17, per_state=6)
    ch = replace(CH, price_deflator=bad)
    with pytest.raises(ValueError, match="refuses to depart from its specification") as e:
        rc.check_specification(ch)
    msg = str(e.value)
    assert "price_deflator" in msg and repr(bad) in msg and "does not choose row C's deflator" in msg
    assert "D-111" in msg and "D-107" not in msg                     # only the deflator departs here
    with pytest.raises(ValueError, match="does not choose row C's deflator"):
        rc.build_panel(out, reg, share, sp, ch, None)
    with pytest.raises(ValueError, match="does not choose row C's deflator"):
        rc.c0(out, reg, share, ch)
    o, counts, share2, sp2, own = _row_c_world(0.182)
    hosts = rc.never_host_units(None, None, counts, rc.OURS_NEVER_HOST_BASIS)
    with pytest.raises(ValueError, match="does not choose row C's deflator"):
        rc.run_row_c(o, counts, counts, counts.assign(value=counts.value * 0.01), share2, {"paper": sp2}, ch, own,
                     rc.OURS_C4_CAP, hosts, "x")


def test_a_deflator_and_a_d107_departure_are_both_named():
    with pytest.raises(ValueError) as e:
        rc.check_specification(replace(CH, price_deflator="pce_chain", interval="normal"))
    assert "D-107" in str(e.value) and "D-111" in str(e.value) and "interval" in str(e.value)


def test_the_choices_have_no_default_deflator():
    """A caller building Choices by hand must state the deflator; there is no default to fall back on."""
    kw = {k: getattr(CH, k) for k in CH.__dataclass_fields__ if k != "price_deflator"}
    with pytest.raises(TypeError):
        rc.Choices(**kw)


def test_the_factors_are_the_arithmetic_on_an_invented_table():
    """An invented spending file: factor for year t is cpi[2024] / cpi[t], to 1e-12 relative."""
    cpi = {2014: 200.0, 2015: 201.0, 2016: 204.5, 2017: 210.0, 2018: 215.0, 2019: 219.0, 2020: 222.0,
           2021: 232.0, 2022: 250.0, 2023: 260.0, 2024: 270.0, 2025: 277.0}
    t = pd.DataFrame({"year": list(cpi), "nominal_musd": 1.0, "cpi_u": list(cpi.values()),
                      "real_2024_musd": 1.0, "paper_table_s3_real_2024_bn": np.nan})
    f = rc.cpi_factors_to_2024(t)
    assert set(f) == set(cpi)
    for y, v in cpi.items():
        assert f[y] == pytest.approx(270.0 / v, rel=1e-12)
    assert f[2024] == 1.0 and f[2015] == pytest.approx(1.3432835820895523, rel=1e-12)
    # a nominal price of 10 cents in 2015 is 13.43 cents in 2024 dollars
    assert 10.0 * f[2015] == pytest.approx(13.432835820895523, rel=1e-12)


@pytest.mark.parametrize("drop", [2015, 2020, 2024])
def test_a_table_missing_a_window_year_is_refused_in_words(drop):
    cpi = {y: 200.0 + y - 2014 for y in range(2014, 2026)}
    t = pd.DataFrame({"year": [y for y in cpi if y != drop], "cpi_u": [v for y, v in cpi.items() if y != drop]})
    with pytest.raises(ValueError, match=rf"no positive value for \[{drop}\].*Nothing is fetched"):
        rc.cpi_factors_to_2024(t)
    t2 = pd.DataFrame({"year": list(cpi), "cpi_u": [np.nan if y == drop else v for y, v in cpi.items()]})
    with pytest.raises(ValueError, match="no positive value"):
        rc.cpi_factors_to_2024(t2)


# ---------------------------------------------------------------------------------------------------------------
# Row C's nominal price series (Joe, 2026-11-20, D-117): the panel's res_price, our comparison specification
# ---------------------------------------------------------------------------------------------------------------
def test_the_price_series_is_a_named_constant_with_its_label():
    assert rc.OURS_PRICE_SERIES == "res_price" and rc.SPECIFICATION.price_series == rc.OURS_PRICE_SERIES
    lab = rc.PRICE_SERIES_LABEL
    assert rc.OURS_APPROXIMATIONS["price_series"]["label"] == lab
    assert lab.startswith("Our comparison specification, settled by Joe on 2026-11-20 (D-117)")
    assert "not a claim that the paper used exactly this construction" in lab
    assert "cents per kWh" in lab and "real 2024 cents per kWh" in lab and "res_revenue_full / res_mwh / 10.0" in lab
    assert "delivery-inclusive" in lab and "D-111" in lab and "nothing is fetched or read" in lab
    assert "is the paper's" not in lab and "the paper's series" not in lab and "—" not in lab
    assert not VERDICT.search(lab)
    assert "cannot detect an outcome frame that was in fact built from another column" in rc.PRICE_SERIES_NOT_CHECKED
    for text in (inspect.getdoc(rc), inspect.getdoc(rc.build_panel), inspect.getdoc(rc.Choices)):
        assert "D-117" in text and "res_price" in text
    flat = [" ".join(inspect.getdoc(x).split()) for x in (rc, rc.build_panel)]
    assert "cannot detect a frame" in flat[0] and "nothing here can detect a frame" in flat[1]
    assert "Turning dollars per MWh into cents per kWh" not in flat[0] and "No change of unit is needed" in flat[0]


def test_the_price_series_construction_named_is_the_panels_code():
    """The construction the label names is the line pipeline/electricity/panel.py build() carries (read as code; the
    module is imported, nothing is run and no file is read)."""
    from pipeline.electricity import panel
    src = inspect.getsource(panel.build)
    assert 'p["res_price"] = p.res_revenue_full / p.res_mwh / 10.0' in src
    assert "res_revenue_full / res_mwh / 10.0" in rc.PRICE_SERIES_CONSTRUCTION


@pytest.mark.parametrize("bad", ["res_price_default_service", "res_price_delivery_only", "res_revenue_full", ""])
def test_a_caller_that_states_another_price_series_is_refused_in_words(bad):
    out, reg, share, sp, _ = world(seed=17, per_state=6)
    ch = replace(CH, price_series=bad)
    with pytest.raises(ValueError, match="refuses to depart from its specification") as e:
        rc.check_specification(ch)
    msg = str(e.value)
    assert "price_series" in msg and repr(bad) in msg and "does not choose row C's nominal price series" in msg
    assert "D-117" in msg and "D-107" not in msg and "cannot detect an outcome frame" in msg
    with pytest.raises(ValueError, match="does not choose row C's nominal price series"):
        rc.build_panel(out, reg, share, sp, ch, None)
    o, counts, share2, sp2, own = _row_c_world(0.182)
    hosts = rc.never_host_units(None, None, counts, rc.OURS_NEVER_HOST_BASIS)
    with pytest.raises(ValueError, match="does not choose row C's nominal price series"):
        rc.run_row_c(o, counts, counts, counts.assign(value=counts.value * 0.01), share2, {"paper": sp2}, ch, own,
                     rc.OURS_C4_CAP, hosts, "x")


def test_the_price_series_refusal_can_fail(monkeypatch):
    """Break, made in the test process: OURS_PRICE_SERIES set to the departing value; the refusal then does not
    happen and the refusal test's pytest.raises fails."""
    monkeypatch.setattr(rc, "OURS_PRICE_SERIES", "res_price_default_service")
    with pytest.raises(pytest.fail.Exception):
        with pytest.raises(ValueError):
            rc.check_specification(replace(CH, price_series="res_price_default_service"))


def test_the_paper_settled_check_is_unaffected_by_the_price_series():
    rc.check_paper_settled(replace(CH, price_series="anything"))           # not a paper-settled value: passes
    with pytest.raises(ValueError, match="a choice the paper settles"):
        rc.check_paper_settled(replace(CH, price_series="anything", share_in_percent=False))
    with pytest.raises(ValueError, match="a choice the paper settles") as e:   # the paper's values are checked first
        rc.check_specification(replace(CH, price_series="anything", contiguous_only=False))
    assert "price_series" not in str(e.value)
    rc.check_specification(CH)


def test_the_choices_have_no_default_price_series():
    kw = {k: getattr(CH, k) for k in CH.__dataclass_fields__ if k != "price_series"}
    with pytest.raises(TypeError):
        rc.Choices(**kw)
    from dataclasses import asdict
    assert asdict(rc.SPECIFICATION)["price_series"] == "res_price"


def test_a_price_series_and_a_deflator_departure_are_both_named():
    with pytest.raises(ValueError) as e:
        rc.check_specification(replace(CH, price_series="res_price_default_service", price_deflator="pce_chain"))
    assert "D-111" in str(e.value) and "D-117" in str(e.value) and "price_deflator" in str(e.value)


# ---------------------------------------------------------------------------------------------------------------
# Row C's ownership classes (Joe, 2026-11-20, D-117): the last nonmissing reported entity type over 2001 to 2025
# ---------------------------------------------------------------------------------------------------------------
def q_world_c() -> pd.DataFrame:
    """Invented quantities over exactly 2001 to 2025, with the panel-style ownership column mapped row by row.
    (1, TX) Cooperative, missing in 2025              -> cooperative
    (2, TX) Municipal 2001-2019, Investor Owned after -> investor_owned (first row's ownership: public)
    (3, TX) no type in any year                       -> absent from the mapping
    (4, OK) Federal                                   -> public
    (6, TX) Cooperative 2001-2020, Municipal after    -> public (first row's ownership: cooperative)"""
    from pipeline.electricity import panel
    rows = []
    for y in range(2001, 2026):
        rows.append((1, "TX", y, None if y == 2025 else "Cooperative"))
        rows.append((2, "TX", y, "Municipal" if y < 2020 else "Investor Owned"))
        rows.append((3, "TX", y, None))
        rows.append((4, "OK", y, "Federal"))
        rows.append((6, "TX", y, "Cooperative" if y <= 2020 else "Municipal"))
    q = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "entity_type"])
    q["ownership"] = q.entity_type.map(panel.OWNERSHIP_GROUP)
    return q


Q_WORLD_C = {(1, "TX"): "cooperative", (2, "TX"): "investor_owned", (4, "OK"): "public", (6, "TX"): "public"}


def test_row_c_ownership_known_answers_and_a_unit_with_no_type_is_absent():
    m = rc.adopted_row_c_ownership(q_world_c())
    assert m == Q_WORLD_C and (3, "TX") not in m


def test_row_c_ownership_can_fail(monkeypatch):
    """Break, made in the test process: the map sends Municipal to investor_owned; the known answers then fail."""
    monkeypatch.setattr(rc, "ROW_C_OWNERSHIP_MAP", {**rc.ROW_C_OWNERSHIP_MAP, "Municipal": "investor_owned"})
    assert rc.adopted_row_c_ownership(q_world_c()) != Q_WORLD_C


def test_row_c_mapping_equals_the_panels_grouping():
    from pipeline.electricity import panel
    assert rc.ROW_C_OWNERSHIP_MAP == panel.OWNERSHIP_GROUP
    assert set(rc.ROW_C_OWNERSHIP_MAP) == set(panel.DISTRIBUTION_ENTITIES)
    assert rc.OWNERSHIP_OTHER_RULE == "every class except investor_owned"


def test_row_c_ownership_takes_no_pick_and_refuses_other_years():
    assert list(inspect.signature(rc.adopted_row_c_ownership).parameters) == ["quantities"]
    with pytest.raises(ValueError, match="searches exactly 2001 to 2025"):
        rc.adopted_row_c_ownership(q_world_c()[lambda d: d.year != 2019])
    with pytest.raises(ValueError, match=r"outside that range \[2000\]"):
        rc.adopted_row_c_ownership(pd.concat([q_world_c(), q_world_c()[lambda d: d.year == 2001].assign(year=2000)]))


def test_row_c_an_unknown_entity_type_stops_in_words():
    q = q_world_c()
    q.loc[(q.utility_id_eia == 4), "entity_type"] = "Wholesale Power Marketer"
    with pytest.raises(ValueError, match=r"not among the six row C's mapping knows.*no class is guessed"):
        rc.adopted_row_c_ownership(q)


def test_row_c_unknown_type_guard_can_fail(monkeypatch):
    """Break: the map extended in the test process to know the invented type; then nothing stops."""
    monkeypatch.setattr(rc, "ROW_C_OWNERSHIP_MAP", {**rc.ROW_C_OWNERSHIP_MAP, "Wholesale Power Marketer": "public"})
    q = q_world_c()
    q.loc[(q.utility_id_eia == 4), "entity_type"] = "Wholesale Power Marketer"
    with pytest.raises(pytest.fail.Exception):
        with pytest.raises(ValueError):
            rc.adopted_row_c_ownership(q)


def test_row_c_the_split_stops_on_a_unit_with_no_type_and_never_puts_it_on_the_other_side():
    """The world's units take their types from invented quantities; one unit has no type in any year, so it is absent
    from the adopted mapping and ownership_split stops in words."""
    out, reg, share, sp, own = world(seed=12, own_beta={True: 0.3, False: 0.1})
    units = sorted(own)
    gone = units[0]
    to_type = {"investor_owned": "Investor Owned", "cooperative": "Cooperative", "public": "Municipal"}
    q = pd.DataFrame([(u, s, y, None if (u, s) == gone else to_type[own[(u, s)]])
                      for (u, s) in units for y in range(2001, 2026)],
                     columns=["utility_id_eia", "state", "year", "entity_type"])
    adopted = rc.adopted_row_c_ownership(q)
    assert gone not in adopted and len(adopted) == len(units) - 1
    with pytest.raises(ValueError, match="1 units have no ownership class.*not put on the investor-owned side or the "
                                         "all-other side"):
        rc.ownership_split("C1", out, reg, share, sp, "paper", CH, None, adopted)
    full = {k: v for k, v in own.items()}
    r = rc.ownership_split("C1", out, reg, share, sp, "paper", CH, None, full)
    assert r["failure"] is None


def test_row_c_the_class_is_the_same_for_every_year():
    q = q_world_c()
    m = rc.adopted_row_c_ownership(q)
    per = q[[k in m for k in zip(q.utility_id_eia, q.state)]].assign(
        c=lambda d: [m[k] for k in zip(d.utility_id_eia, d.state)]).groupby(["utility_id_eia", "state"]).c.nunique()
    assert (per == 1).all()


def test_row_c_comparison_block_known_counts():
    q = q_world_c()
    m = rc.adopted_row_c_ownership(q)
    b = rc.ownership_comparison_block(q, {(1, "TX"), (2, "TX"), (3, "TX")}, m)
    assert b["all_panel_units"] == {"units": 5, "units_with_no_class_under_d117": 1,
                                    "units_with_a_class_under_d117_and_no_value_in_the_panel_ownership_column": 0,
                                    "units_compared": 4, "units_whose_class_differs": 2,
                                    "units_whose_investor_owned_side_differs": 1}
    assert b["balanced_stand_in_sample_units"] == {"units": 3, "units_with_no_class_under_d117": 1,
                                                   "units_with_a_class_under_d117_and_no_value_in_the_panel_ownership_"
                                                   "column": 0, "units_compared": 2, "units_whose_class_differs": 1,
                                                   "units_whose_investor_owned_side_differs": 1}
    assert b["years_present_in_the_panel"] == {"first": 2001, "last": 2025, "count": 25,
                                               "equal_to_the_years_searched": True}
    assert b["units_with_more_than_one_distinct_entity_type_across_years"] == 2         # 2 TX, 6 TX
    assert b["units_with_more_than_one_distinct_ownership_value_across_years"] == 2
    assert b["units_with_no_entity_type_in_any_year"] == 1
    assert "NOT established" in b["what_the_panel_column_is"] and "C1's and C3's" in b["steps_a_difference_would_touch"]
    assert "equivalen" not in b["not_established"]
    __import__("json").dumps(b)


def test_row_c_comparison_block_can_fail(monkeypatch):
    """Break: the adopted mapping replaced by the first row's ownership (what the summary read before); the known
    count of units whose class differs then falls to zero."""
    q = q_world_c()
    before = {(u, s): o for (u, s), o in q.drop_duplicates(["utility_id_eia", "state"])
              .set_index(["utility_id_eia", "state"]).ownership.items() if isinstance(o, str)}
    b = rc.ownership_comparison_block(q, {(1, "TX")}, before)
    assert b["all_panel_units"]["units_whose_class_differs"] != 2


def test_row_c_main_reads_entity_type_and_uses_the_adopted_classes():
    src = inspect.getsource(rc.main)
    assert '"entity_type"' in src and "own_c = adopted_row_c_ownership(q)" in src
    assert "row_c_ownership_classification_d117" in src and "price_series_specification_d117" in src
    assert ".ownership.items()" not in src


# ---- Joe's ruling of 2026-11-20 on what rows U and C's ownership type is (D-119) -------------------------------------
def _c_ownership_texts(b: dict) -> dict:
    src = inspect.getsource(rc.main)
    return {"module": rc.__doc__.split("Ownership (Joe, 2026-11-20")[1].split("The estimator is self-contained")[0],
            "adopted_doc": inspect.getdoc(rc.adopted_row_c_ownership),
            "split_doc": inspect.getdoc(rc.ownership_split).split("ownership: {(utility_id_eia, state): class}")[1],
            "block_statement": b["what_the_panel_column_is"], "block_not_established": b["not_established"],
            "block_pick": b["specification"]["pick"],
            "main_what_this_is": src.split('"Provisional quantity-side summary for reconciliation row C')[1]
            .split('"choices_specification_d107"')[0]}


def _c_ownership_problems(texts: dict) -> list:
    from pipeline.analysis import reconciliation_mu as rmu
    words = rmu.OWNERSHIP_RULING_D119_WORDS
    bad = []
    for name, t in texts.items():
        t = " ".join(str(t).split()).replace('" "', "")
        rest = t.replace(words, "").replace("not the latest year-by-year EIA classification", "")
        low = rest.lower()
        for phrase in ("latest", "most recent", "last nonmissing reported", "pick is open", "caller's choice"):
            if phrase in low:
                bad.append((name, phrase))
        if "D-119" not in t:
            bad.append((name, "no D-119"))
        if name not in ("block_not_established",) and "modal" not in t:
            bad.append((name, "no 'modal'"))
    return bad


def test_d119_row_c_ownership_texts_carry_the_ruling():
    from pipeline.analysis import reconciliation_mu as rmu
    q = q_world_c()
    b = rc.ownership_comparison_block(q, {(1, "TX")}, rc.adopted_row_c_ownership(q))
    assert _c_ownership_problems(_c_ownership_texts(b)) == []
    assert rmu.OWNERSHIP_RULING_D119_WORDS in b["what_the_panel_column_is"]
    assert "no further raw-data investigation" in b["not_established"] and "equivalen" not in b["not_established"]


def test_d119_row_c_ownership_texts_can_fail(monkeypatch):
    """Break: the panel statement and the not-established text put back to their D-117 wording in the test process."""
    from pipeline.analysis import reconciliation_mu as rmu
    q = q_world_c()
    monkeypatch.setattr(rmu, "PANEL_ENTITY_TYPE_STATEMENT",
                        "Whether the last type EIA reports year by year would differ is NOT established.")
    b = rc.ownership_comparison_block(q, {(1, "TX")}, rc.adopted_row_c_ownership(q))
    bad = _c_ownership_problems(_c_ownership_texts(b))
    assert ("block_statement", "no D-119") in bad and ("block_statement", "no 'modal'") in bad
    assert _c_ownership_problems({"x": "the last nonmissing reported entity type over 2001 to 2025 (D-117)"}) == [
        ("x", "last nonmissing reported"), ("x", "no D-119"), ("x", "no 'modal'")]
