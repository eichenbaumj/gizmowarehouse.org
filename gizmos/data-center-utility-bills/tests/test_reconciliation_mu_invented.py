"""Reconciliation rows M and U (pipeline/analysis/reconciliation_mu.py) on invented worlds only. Nothing here reads data/.

Row M: the group-time estimator recovers a planted effect (exactly with no noise, to a stated tolerance with noise),
each cell equals a brute-force two-period dummy-variable regression and its clustered error, the overall effect equals
the cohort-weighted average of those regressions, the influence-function error agrees with a delete-one-unit jackknife
and with the multiplier bootstrap, ownership runs keep every never-treated unit as a comparison, and the steps use
2010-2024 (M0 to M2) and 2010-2025 (M3, M4). Row U: the two-way fixed-effects fit equals a dummy-variable regression
with statsmodels' clustered errors, recovers planted coefficients pooled and by ownership both ways, carries a
multi-state utility's MW in each state, and uses 2015-2024 (U0 to U2) and 2015-2025 (U3). Row U's specification since
D-107: each approximation of ours is refused in words if departed from, the paper's two row filters commute when the
three-year count comes last, a site left out for an ambiguous polygon is named in the step, and no row U output can
carry a reproduction verdict (the ownership ordering and the pooled estimate come back as labelled comparisons, with
the paper's band beside the pooled one, whether inside or outside it). Bands at their edges, row M's sentence, and no
step opens a file.
"""
from __future__ import annotations

import builtins
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import reconciliation_mu as mu  # noqa: E402
from pipeline.analysis import reconciliation_treatment as rt  # noqa: E402

KEY = mu.KEY
M_STATES = ["TX", "OK", "KS", "NE", "IA", "MO", "AR", "LA"]


def mspec(**kw) -> mu.MeeksSpec:
    """Row M's spec for tests. The paper's settled values (file dated 2026-10-23) and, for the open elements, one
    accepted candidate each; the open values here are test inputs, not choices."""
    base = dict(covariates=(), aggregation="simple", se_method="influence_function", anticipation=0,
                unbalanced="pairwise", treated_after_window="never_treated", jurisdictions=mu.CONTIGUOUS_48,
                customer_floor=None, exclude_short_form=True, require_three_classes=True,
                short_form_years=(2010, 2024), three_classes_level="unit", three_classes_test="positive_sales",
                retail_component="implied_by_a_residential_price", window_start_cohort="left_out_and_counted",
                weighting="unweighted")
    base.update(kw)
    return mu.MeeksSpec(**base)


def mflags(o: pd.DataFrame, spec: mu.MeeksSpec | None = None, by_year: bool = False, **cols) -> pd.DataFrame:
    """Sample flags that pass every unit (no Short Form filer, three classes served), declared under spec's years and
    test. by_year: one row per unit-year (for three_classes_level="unit_year"). cols: columns to override."""
    spec = spec or mspec()
    base = o[KEY + (["year"] if by_year else [])].drop_duplicates()
    f = base.assign(ever_short_form=False, short_form_first_year_read=spec.short_form_years[0],
                    short_form_last_year_read=spec.short_form_years[1], has_three_classes=True,
                    three_classes_test=spec.three_classes_test)
    for k, v in cols.items():
        f[k] = v(f) if callable(v) else v
    return f


def run_m(step, o, price, tr, own, spec, **kw):
    """run_m_step with flags that pass every unit unless the test gives its own."""
    kw.setdefault("sample_flags", mflags(o, spec, by_year=spec.three_classes_level == "unit_year"))
    return mu.run_m_step(step, o, price, tr, own, spec, **kw)


def uspec(**kw) -> mu.RyuSpec:
    base = dict(ownership_spec="separate_subsamples", ss_correction="clusters_and_parameters",
                min_years=(3, "utility", "every_other_restriction"), jurisdictions=mu.FIFTY_STATES_AND_DC,
                short_form_exclusion="none_in_outcome_frame", weighting="unweighted")
    base.update(kw)
    return mu.RyuSpec(**base)


# --------------------------------------------------------------------------------------------------------------------
# Row M world
# --------------------------------------------------------------------------------------------------------------------

def m_world(seed=0, noise=0.0, tau=None, cohorts=None, n_never=80, years=range(2009, 2026), missing=0.0, tau_cohort=None):
    """Units with a unit effect, a year effect, noise and a planted effect from the first treated year on.
    tau: by ownership class. cohorts: {first_year: count}. tau_cohort: an extra effect by cohort (heterogeneity)."""
    rng = np.random.default_rng(seed)
    tau = tau or {"investor_owned": 0.03, "public": 0.03, "cooperative": 0.03}
    cohorts = cohorts or {2012: 12, 2015: 12, 2018: 12, 2021: 9, 2010: 3, 2025: 6, 2005: 3}
    classes = list(tau)
    rows, treat, own = [], [], []
    uid = 0
    ye = {t: 0.01 * (t - 2009) + rng.normal(0, 0.02) for t in years}
    for g, n in list(cohorts.items()) + [(np.nan, n_never)]:
        for k in range(n):
            uid += 1
            st = M_STATES[uid % len(M_STATES)]
            cls = classes[uid % len(classes)]
            a = rng.normal(2.3, 0.2)
            for t in years:
                if missing and rng.random() < missing:
                    continue
                eff = tau[cls] + (tau_cohort or {}).get(g, 0.0) if (g == g and t >= g) else 0.0
                rows.append({"utility_id_eia": uid, "state": st, "year": t,
                             "value": float(np.exp(a + ye[t] + eff + (rng.normal(0, noise) if noise else 0.0)))})
            treat.append({"utility_id_eia": uid, "state": st, "first_year": g})
            own.append({"utility_id_eia": uid, "state": st, "ownership_class": cls})
    return pd.DataFrame(rows), pd.DataFrame(treat), pd.DataFrame(own)


def mtreat(t: pd.DataFrame, rule="verified|above_5mw|site|mw_full") -> rt.Treatment:
    return rt.Treatment(rule, t.assign(rule=rule), pd.DataFrame(columns=["fid", "reason"]))


def matrix(outcome: pd.DataFrame, treat: pd.DataFrame):
    o = outcome.assign(unit=mu._unit_label(outcome), y=np.log(outcome.value))
    Y = o.pivot(index="unit", columns="year", values="y")
    fy = pd.Series(treat.first_year.values.astype(float), index=mu._unit_label(treat)).reindex(Y.index)
    return Y, fy


def brute_cell(Y: pd.DataFrame, fy: pd.Series, g: int, t: int):
    """Two-period dummy-variable regression on cohort g and never-treated units observed at g-1 and t:
    y = unit dummies + post + D, D = cohort x post. Returns (coefficient on D, clustered-by-unit error, no correction)."""
    fy = fy.reindex(Y.index)
    keep = ((fy == g) | fy.isna()) & Y[g - 1].notna() & Y[t].notna()
    sub = Y.loc[keep, [g - 1, t]]
    n = len(sub)
    yv = np.concatenate([sub[g - 1].values, sub[t].values])
    unit = np.tile(np.arange(n), 2)
    post = np.repeat([0.0, 1.0], n)
    D = post * np.tile((fy[keep] == g).values.astype(float), 2)
    X = np.column_stack([np.eye(n)[unit], post, D])
    b, *_ = np.linalg.lstsq(X, yv, rcond=None)
    e = yv - X @ b
    A = np.linalg.pinv(X.T @ X)
    S = np.zeros((n, X.shape[1]))
    np.add.at(S, unit, X * e[:, None])
    V = A @ S.T @ S @ A
    return b[-1], np.sqrt(V[-1, -1])


def window_cut(Y, fy, window, after="never_treated"):
    lo, hi = window
    Y = Y[[c for c in Y.columns if lo - 0 <= c <= hi]]
    fy = fy.reindex(Y.index)
    keep = ~(fy < lo)
    if after == "never_treated":
        fy = fy.where(~(fy > hi), np.nan)
    else:
        keep &= ~(fy > hi)
    keep &= ~(fy == lo)                      # no base year inside the window
    return Y[keep], fy[keep]


# --------------------------------------------------------------------------------------------------------------------
# The group-time estimator
# --------------------------------------------------------------------------------------------------------------------

def test_cs_recovers_a_planted_effect_exactly_without_noise():
    o, t, _ = m_world(noise=0.0)
    Y, fy = matrix(o, t)
    for agg in ("simple", "group"):
        r = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(aggregation=agg))
        assert abs(r["estimate"] - 0.03) < 1e-10           # tolerance: floating point
        assert r["se"] < 1e-10


def test_cs_recovers_a_planted_effect_with_noise():
    o, t, _ = m_world(seed=3, noise=0.03, n_never=300,
                      cohorts={2012: 60, 2015: 60, 2018: 60, 2021: 60})
    Y, fy = matrix(o, t)
    r = mu.callaway_santanna(Y, fy, (2010, 2024), mspec())
    # tolerance: three standard errors (about 0.0045 here); the estimate must also be within 0.01 of 0.03
    assert abs(r["estimate"] - 0.03) < 3 * r["se"] and abs(r["estimate"] - 0.03) < 0.01


def test_each_cell_equals_a_brute_force_dummy_regression_and_its_clustered_error():
    o, t, _ = m_world(seed=1, noise=0.05, missing=0.1)
    Y, fy = matrix(o, t)
    Yc, fyc = window_cut(Y, fy, (2010, 2024))
    r = mu.callaway_santanna(Y, fy, (2010, 2024), mspec())
    assert r["cells"]
    for c in r["cells"]:
        b, _ = brute_cell(Yc, fyc, c["cohort"], c["year"])
        assert abs(c["att"] - b) < 1e-10                    # tolerance: floating point
    # one cohort, one post year: the overall error is the cell's, and equals the brute-force clustered error
    g = 2015
    keep_units = fy.isna() | (fy == g)
    Ys, fys = Y[keep_units], fy[keep_units]
    single = mu.callaway_santanna(Ys, fys, (g - 1, g), mspec())
    b, se = brute_cell(Ys, fys, g, g)
    assert abs(single["estimate"] - b) < 1e-10 and abs(single["se"] - se) < 1e-10


def test_the_overall_effect_is_the_cohort_weighted_average_of_the_brute_force_cells():
    o, t, _ = m_world(seed=2, noise=0.05, missing=0.1)
    Y, fy = matrix(o, t)
    Yc, fyc = window_cut(Y, fy, (2010, 2024))
    cohorts = sorted(fyc.dropna().unique())
    num = den = 0.0
    grp = {}
    for g in cohorts:
        n_g = int((fyc == g).sum())
        cells = [brute_cell(Yc, fyc, int(g), yr)[0] for yr in range(int(g), 2025)]
        num += n_g * sum(cells)
        den += n_g * len(cells)
        grp[g] = (n_g, np.mean(cells))
    r = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(aggregation="simple"))
    assert abs(r["estimate"] - num / den) < 1e-10
    r = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(aggregation="group"))
    tot = sum(n for n, _ in grp.values())
    assert abs(r["estimate"] - sum(n * m for n, m in grp.values()) / tot) < 1e-10


@pytest.mark.parametrize("agg", ["simple", "group"])
def test_influence_function_error_agrees_with_a_jackknife_and_the_bootstrap(agg):
    # effects differ by cohort (0.03, 0.13, 0.23), so the estimated cohort weights matter to the error
    o, t, _ = m_world(seed=4, noise=0.04, n_never=120, cohorts={2012: 25, 2016: 25, 2020: 25},
                      tau_cohort={2016: 0.1, 2020: 0.2})
    Y, fy = matrix(o, t)
    r = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(aggregation=agg))
    loo = np.array([mu.callaway_santanna(Y.drop(index=u), fy.drop(index=u), (2010, 2024), mspec(aggregation=agg))["estimate"]
                    for u in Y.index])
    n = len(loo)
    jack = np.sqrt((n - 1) / n * np.sum((loo - loo.mean()) ** 2))
    assert abs(jack / r["se"] - 1) < 0.05                   # tolerance: 5% (the two agree to first order)
    b = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(aggregation=agg, se_method="multiplier_bootstrap",
                                                        bootstrap_draws=40000, bootstrap_weights="rademacher", seed=7))
    assert abs(b["se"] / r["se"] - 1) < 0.03 and b["estimate"] == r["estimate"]   # tolerance: 3% (simulation error)


def test_pairwise_and_balanced_panels_and_later_treated_units():
    o, t, _ = m_world(seed=5, noise=0.0, missing=0.15)
    Y, fy = matrix(o, t)
    pw = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(unbalanced="pairwise"))
    bal = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(unbalanced="balance"))
    assert bal["n_units"] < pw["n_units"]
    assert abs(pw["estimate"] - 0.03) < 1e-10 and (bal["estimate"] is None or abs(bal["estimate"] - 0.03) < 1e-10)
    nv = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(treated_after_window="never_treated"))
    dr = mu.callaway_santanna(Y, fy, (2010, 2024), mspec(treated_after_window="dropped"))
    assert nv["n_comparison_units"] == dr["n_comparison_units"] + 6        # the six 2025 units
    assert any("2010" in f and "base year 2009" in f for f in nv["failures"])  # cohort 2010 reported, not dropped silently
    assert any("before 2010" in n for n in nv["notes"])


def test_a_cell_with_no_comparison_is_a_reported_failure():
    o, t, _ = m_world(seed=6, noise=0.0, n_never=5, cohorts={2015: 5})
    o = o[~((o.year == 2020) & o.utility_id_eia.isin(range(6, 11)))]       # never-treated missing in 2020
    Y, fy = matrix(o, t)
    r = mu.callaway_santanna(Y, fy, (2010, 2024), mspec())
    assert any("cell (2015, 2020)" in f and "not estimable" in f for f in r["failures"])
    assert abs(r["estimate"] - 0.03) < 1e-10


def test_spec_has_no_defaults_and_covariates_are_not_built():
    with pytest.raises(TypeError):
        mu.MeeksSpec()
    with pytest.raises(TypeError):
        mu.RyuSpec()
    o, t, _ = m_world()
    Y, fy = matrix(o, t)
    with pytest.raises(NotImplementedError):
        mu.callaway_santanna(Y, fy, (2010, 2024), mspec(covariates=("population",)))


# --------------------------------------------------------------------------------------------------------------------
# Row M steps
# --------------------------------------------------------------------------------------------------------------------

M_RULES = {"M0": "county_touch|above_5mw|site|mw_full", "M1": "verified|above_5mw|site|mw_full",
           "M2": "verified|above_5mw|site|mw_full", "M3": "verified|above_5mw|site|mw_full", "M4": "verified|dose_at_least_0.02"}


@pytest.mark.parametrize("step", ["M0", "M1", "M2", "M3", "M4"])
def test_each_m_step_recovers_a_planted_effect_and_matches_brute_force(step):
    tau = {"investor_owned": 0.05, "public": 0.01, "cooperative": 0.0}
    o, t, own = m_world(seed=8, noise=0.0, tau=tau)
    price = mu.M_STEPS[step]["price"]
    r = run_m(step, o, price, mtreat(t, M_RULES[step]), own, mspec())
    for c, v in tau.items():
        assert abs(r["by_ownership"][c]["estimate"] - v) < 1e-10          # tolerance: floating point
    assert r["ownership_ordering_holds"] is True
    # every ownership run keeps every never-treated unit as a comparison
    assert len({r["by_ownership"][c]["n_comparison_units"] for c in tau} | {r["pooled"]["n_comparison_units"]}) == 1
    # noisy: pooled equals the cohort-weighted brute-force average
    o2, t2, own2 = m_world(seed=9, noise=0.05, tau=tau)
    r2 = run_m(step, o2, price, mtreat(t2, M_RULES[step]), own2, mspec())
    Y, fy = matrix(o2, t2)
    Yc, fyc = window_cut(Y, fy, tuple(mu.M_STEPS[step]["window"]))
    num = den = 0.0
    for g in sorted(fyc.dropna().unique()):
        cells = [brute_cell(Yc, fyc, int(g), yr)[0] for yr in range(int(g), mu.M_STEPS[step]["window"][1] + 1)]
        num += (fyc == g).sum() * sum(cells)
        den += (fyc == g).sum() * len(cells)
    assert abs(r2["pooled"]["estimate"] - num / den) < 1e-10


def test_m_years_2010_to_2024_then_2025_added():
    o, t, own = m_world(seed=10, noise=0.0)
    for step in ("M0", "M1", "M2", "M3", "M4"):
        r = run_m(step, o, mu.M_STEPS[step]["price"], mtreat(t, M_RULES[step]), own, mspec())
        last = 2024 if step in ("M0", "M1", "M2") else 2025
        assert r["years"] == [2010, last]
        assert max(c["year"] for c in r["pooled"]["cells"]) == last
        assert min(c["year"] for c in r["pooled"]["cells"]) >= 2011
        assert (2025 in r["pooled"]["cohorts"]) == (last == 2025)


def test_m_step_refuses_the_wrong_price_or_treatment():
    o, t, own = m_world()
    with pytest.raises(ValueError):
        run_m("M2", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec())
    with pytest.raises(ValueError):
        run_m("M0", o, mu.DEFAULT_SERVICE, mtreat(t, "verified|above_5mw|site|mw_full"), own, mspec())
    with pytest.raises(ValueError, match="no customer floor"):
        run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec(customer_floor=2000))
    with pytest.raises(ValueError, match="needs sample_flags"):
        mu.run_m_step("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec())                   # no flags given


def test_m_sample_rules_and_a_price_that_is_not_positive():
    o, t, own = m_world(seed=11, noise=0.0)
    o.loc[o.index[5], "value"] = 0.0
    cust = o[KEY + ["year"]].assign(res_customers=np.where(o.utility_id_eia % 5 == 0, 1500, 9000))
    flags = mflags(o, ever_short_form=lambda d: d.utility_id_eia % 7 == 0,
                   has_three_classes=lambda d: d.utility_id_eia % 11 != 0)
    r = mu.run_m_step("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec(), customers=cust, sample_flags=flags)
    assert any("not positive" in f for f in r["numerical_failures"])
    assert not any("customers" in n for n in r["notes"])            # row M has no customer floor; customers unused
    assert any("ever_short_form" in n for n in r["notes"]) and any("has_three_classes" in n for n in r["notes"])
    assert abs(r["pooled"]["estimate"] - 0.03) < 1e-10              # tolerance: floating point


def test_m0_reproduced_and_not_reproduced_and_the_row_description():
    o, t, own = m_world(seed=12, noise=0.0, tau={"investor_owned": 0.05, "public": 0.01, "cooperative": 0.0})
    r = run_m("M0", o, mu.DEFAULT_SERVICE, mtreat(t, M_RULES["M0"]), own, mspec())
    assert mu.BAND_M[0] <= r["pooled"]["estimate"] <= mu.BAND_M[1]
    assert r["reproduced"] is True and r["sentence"] is None
    o2, t2, own2 = m_world(seed=12, noise=0.0, tau={"investor_owned": 0.0, "public": 0.01, "cooperative": 0.05})
    r2 = run_m("M0", o2, mu.DEFAULT_SERVICE, mtreat(t2, M_RULES["M0"]), own2, mspec())
    assert r2["in_band"] is True and r2["ownership_ordering_holds"] is False and r2["reproduced"] is False
    assert r2["sentence"].startswith(M0_TEXT) and "0.021" in r2["sentence"]
    r3 = run_m("M1", o2, mu.DEFAULT_SERVICE, mtreat(t2, M_RULES["M1"]), own2, mspec())
    lines = mu.describe_row_m([r, r3])
    assert "above both" in lines[0] and "not above both" in lines[1] and "from M0" in lines[1]


def test_bands_at_their_edges_and_equal_to_the_paper_plus_or_minus_two_errors():
    est, se = mu.PAPER_M["pooled"]
    assert np.allclose(mu.BAND_M, (est - 2 * se, est + 2 * se))
    est, se = mu.PAPER_U["pooled_no_controls"]
    assert np.allclose(mu.BAND_U, (est - 2 * se, est + 2 * se))
    for band in (mu.BAND_M, mu.BAND_U):
        assert mu._band(band[0], band) and mu._band(band[1], band)
        assert not mu._band(np.nextafter(band[0], -1), band) and not mu._band(np.nextafter(band[1], 1), band)
        assert mu._band(None, band) is None


# --------------------------------------------------------------------------------------------------------------------
# Row U world
# --------------------------------------------------------------------------------------------------------------------

U_STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
            "ME", "MD", "MA", "MI", "MN", "MS"]


def u_world(seed=0, noise=0.0, beta=None, n_util=180, years=range(2014, 2026)):
    """Utilities with a utility effect (shared across a multi-state utility's states), a year effect, noise and
    y = ... + beta[class] * ln(MW + 1), MW at the utility level. Every tenth utility also reports in a second state."""
    rng = np.random.default_rng(seed)
    beta = beta or {"cooperative": 0.01, "municipal": 0.01, "investor_owned": 0.01, "other": 0.01}
    classes = list(beta)
    ye = {t: rng.normal(0, 0.03) for t in years}
    rows, mw_rows, own = [], [], []
    for u in range(1, n_util + 1):
        states = [U_STATES[u % len(U_STATES)]] + ([U_STATES[(u + 5) % len(U_STATES)]] if u % 10 == 0 else [])
        cls = classes[u % len(classes)]
        a = rng.normal(2.5, 0.2)
        start = rng.integers(2012, 2030)
        for t in years:
            mw = 0.0 if (u % 3 == 0 or t < start) else float(rng.uniform(1, 400))
            for s in states:
                rows.append({"utility_id_eia": u, "state": s, "year": t,
                             "value": float(np.exp(a + ye[t] + beta[cls] * np.log(mw + 1) + (rng.normal(0, noise) if noise else 0)))})
                mw_rows.append({"utility_id_eia": u, "state": s, "year": t, "mw": mw})
        for s in states:
            own.append({"utility_id_eia": u, "state": s, "ownership_class": cls})
    return pd.DataFrame(rows), pd.DataFrame(mw_rows), pd.DataFrame(own)


def utreat(mw: pd.DataFrame, rule="verified|site_year_load") -> rt.Treatment:
    return rt.Treatment(rule, mw.assign(rule=rule), pd.DataFrame(columns=["fid", "reason"]))


def test_twfe_equals_a_dummy_variable_regression_with_statsmodels_clustered_errors():
    import statsmodels.api as sm
    o, mw, _ = u_world(seed=1, noise=0.05)
    d = o.merge(mw, on=KEY + ["year"])
    d["y"], d["x"] = np.log(d.value), np.log(d.mw + 1)
    r = mu.twfe(d, ["x"], "utility_id_eia", "year", "state", "clusters_and_parameters")
    X = pd.concat([d[["x"]], pd.get_dummies(d.utility_id_eia, prefix="u").astype(float),
                   pd.get_dummies(d.year, prefix="y", drop_first=True).astype(float)], axis=1)
    fit = sm.OLS(d.y.values, X.values).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.state)[0]})
    assert abs(r["coef"]["x"] - fit.params[0]) < 1e-10                    # tolerance: floating point
    assert abs(r["se"]["x"] / fit.bse[0] - 1) < 1e-8
    G, n, K = d.state.nunique(), len(d), X.shape[1]
    r0 = mu.twfe(d, ["x"], "utility_id_eia", "year", "state", "none")
    r1 = mu.twfe(d, ["x"], "utility_id_eia", "year", "state", "clusters")
    assert abs(r1["se"]["x"] / r0["se"]["x"] - np.sqrt(G / (G - 1))) < 1e-10
    assert abs(r["se"]["x"] / r0["se"]["x"] - np.sqrt(G / (G - 1) * (n - 1) / (n - K))) < 1e-10


def test_twfe_reports_a_regressor_with_no_variation():
    o, mw, _ = u_world(seed=2)
    d = o.merge(mw, on=KEY + ["year"]).assign(y=lambda x: np.log(x.value), x=0.0)
    r = mu.twfe(d, ["x"], "utility_id_eia", "year", "state", "none")
    assert r["coef"]["x"] is None and "no variation" in r["failures"][0]


U_RULE = {"U0": "polygon_smallest_any_type|site_year_load", "U1": "verified|site_year_load", "U2": "verified|site_year_load",
          "U3": "verified|site_year_load"}


@pytest.mark.parametrize("step", ["U0", "U1", "U2", "U3"])
def test_each_u_step_recovers_planted_coefficients_pooled_and_by_ownership(step):
    beta = {"cooperative": 0.008, "municipal": 0.012, "investor_owned": 0.001, "other": 0.004}
    o, mw, own = u_world(seed=3, noise=0.0, beta=beta)
    r = mu.run_u_step(step, o, mu.U_STEPS[step]["price"], utreat(mw, U_RULE[step]), own, uspec())
    for c in mu.U_CLASSES:
        assert abs(r["by_ownership"][c]["estimate"] - beta[c]) < 1e-10      # tolerance: floating point
    assert r["ownership_comparison"]["co_op_and_municipal_each_above_investor_owned_in_our_estimates"] is True
    o1, mw1, own1 = u_world(seed=3, noise=0.0)
    r1 = mu.run_u_step(step, o1, mu.U_STEPS[step]["price"], utreat(mw1, U_RULE[step]), own1, uspec())
    assert abs(r1["pooled"]["estimate"] - 0.01) < 1e-10
    # with noise, within three standard errors and within 0.003
    o2, mw2, own2 = u_world(seed=4, noise=0.03)
    r2 = mu.run_u_step(step, o2, mu.U_STEPS[step]["price"], utreat(mw2, U_RULE[step]), own2, uspec())
    assert abs(r2["pooled"]["estimate"] - 0.01) < min(3 * r2["pooled"]["se"], 0.003)
    assert "reproduced" not in r2 and "in_band" not in r2
    assert ("pooled_comparison" in r2) is (step == "U0")


def test_u_years_2015_to_2024_then_2025_added():
    o, mw, own = u_world(seed=5, noise=0.01)
    n_util_years = {w: int(((o.year >= w[0]) & (o.year <= w[1])).sum()) for w in ((2015, 2024), (2015, 2025))}
    for step in ("U0", "U1", "U2", "U3"):
        r = mu.run_u_step(step, o, mu.U_STEPS[step]["price"], utreat(mw, U_RULE[step]), own, uspec())
        w = (2015, 2025) if step == "U3" else (2015, 2024)
        assert r["years"] == list(w) and r["pooled"]["n"] == n_util_years[w]


def test_u_multi_state_capacity_is_entered_in_each_state_end_to_end():
    # one utility (7) in two states, its one site in AA; the price in BB moves with the AA site's MW
    sites = pd.DataFrame({"fid": ["a"], "state": ["AA"], "energized_year": [2018.0], "mw_full": [99.0],
                          "is_crypto": [False], "utility_id_eia": [7.0]})
    units = pd.DataFrame({"utility_id_eia": [7, 7] + list(range(20, 60)), "state": ["AL", "AK"] + U_STATES[:20] * 2})
    sites["state"] = "AL"
    ver = rt.assign_verified(sites)
    sy = pd.DataFrame({"fid": "a", "year": range(2018, 2025), "mw": 99.0})
    tr = rt.cumulative_mw(ver, units, range(2015, 2025), "site_year_load", site_year=sy)
    m = tr.table.set_index(KEY + ["year"]).mw
    assert m[(7, "AK", 2018)] == 99.0 and m[(7, "AK", 2017)] == 0.0
    rng = np.random.default_rng(0)
    rows = []
    for (u, s, yr), v in m.items():
        rows.append({"utility_id_eia": u, "state": s, "year": yr,
                     "value": float(np.exp(2 + 0.01 * np.log(v + 1) + rng.normal(0, 0.0) + 0.02 * (yr - 2015)))})
    own = units.assign(ownership_class="cooperative")
    r = mu.run_u_step("U1", pd.DataFrame(rows), mu.DEFAULT_SERVICE, tr, own, uspec())
    assert abs(r["pooled"]["estimate"] - 0.01) < 1e-10


def test_u_min_years_rule_and_refusals():
    o, mw, own = u_world(seed=6)
    short = o[(o.utility_id_eia == 1) & (o.year >= 2017)].index
    o2 = o.drop(index=short)
    r = mu.run_u_step("U1", o2, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    assert any("fewer than 3 years" in n and n.startswith("2 ") for n in r["notes"])
    assert r["pooled"]["n"] == int(((o2.year >= 2015) & (o2.year <= 2024)).sum()) - 2
    with pytest.raises(ValueError):
        mu.run_u_step("U2", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    with pytest.raises(ValueError):
        mu.run_u_step("U0", o, mu.DEFAULT_SERVICE, utreat(mw, "verified|site_year_load"), own, uspec())
    with pytest.raises(ValueError):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw[mw.year != 2020]), own, uspec())   # missing MW: stops


@pytest.mark.parametrize("bad", [None, (3, "utility"), (2, "utility", "every_other_restriction"),
                                 (3, "utility_state", "every_other_restriction"), (3, "utility", "whenever"),
                                 (3, "utility", "window_and_jurisdictions_only")])
def test_u_min_years_is_the_papers_rule_and_anything_else_is_refused_in_words(bad):
    # the paper: "dropping utilities that appear in fewer than 3 years of the panel" (p. 6, Sec. 2.2)
    assert (mu.RYU_MIN_YEARS, mu.RYU_MIN_YEARS_LEVEL) == (3, "utility")
    o, mw, own = u_world(seed=6)
    with pytest.raises(ValueError, match="fewer than 3 years"):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec(min_years=bad))


def test_u_three_years_are_counted_after_every_other_restriction():
    # utility 1 has rows in 2015, 2016 and 2017 only, and no price in 2017: two years with a price, so it leaves
    o, mw, own = u_world(seed=6)
    o = o[(o.utility_id_eia != 1) | o.year.isin([2015, 2016, 2017])].copy()
    o.loc[(o.utility_id_eia == 1) & (o.year == 2017), "value"] = np.nan
    r = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    full = mu.run_u_step("U1", o[o.utility_id_eia != 1], mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    assert r["pooled"]["n"] == full["pooled"]["n"]                       # utility 1's two priced years are out
    assert any(n.startswith("2 unit-years") and "fewer than 3 years" in n for n in r["notes"])
    with pytest.raises(TypeError):
        mu.RyuSpec(ownership_spec="separate_subsamples", ss_correction="clusters_and_parameters",
                   min_years=mu.RYU_OURS_MIN_YEARS, jurisdictions=mu.FIFTY_STATES_AND_DC)


def _sample_world():
    """Twelve utilities: some with no ownership class, some filing the Short Form in some years, some with few years,
    and utility 9 with three years of which one is a Short Form year (so the order of the three-year count matters)."""
    rows, own, flags = [], [], []
    st = "AL"
    for u in range(1, 13):
        years = range(2015, 2025) if u not in (7, 9) else ((2015, 2016) if u == 7 else (2015, 2016, 2017))
        for t in years:
            rows.append((u, st, t, 10.0))
            flags.append((u, st, t, (u in (3, 4) and t in (2016, 2019)) or (u == 9 and t == 2017) or (u == 10)))
        if u not in (5, 6):
            own.append((u, st, ("cooperative", "municipal", "investor_owned", "other")[u % 4]))
    o = pd.DataFrame(rows, columns=KEY + ["year", "value"])
    return (o, pd.DataFrame(own, columns=KEY + ["ownership_class"]),
            pd.DataFrame(flags, columns=KEY + ["year", "short_form"]))


@pytest.mark.parametrize("sf", ["unit_years_filed", "utilities_ever_filed"])
def test_u_the_two_row_filters_commute_when_the_three_year_count_is_last(sf):
    """Item to confirm (D-107): with the three-year count taken after every other restriction, the order of the other
    two rules (ownership reported; Short Form filers out) does not change who is in. Both are row filters, each reading
    only the row's own unit and year (or, for utilities_ever_filed, the flags table over the window), so they commute.
    Taking the count before the Short Form rule would keep utility 9 on three years, two of them left after the rule."""
    o, own, flags = _sample_world()
    spec = uspec(short_form_exclusion=sf)
    a, na = mu.u_sample_rules(o, own, spec, flags, (2015, 2024), order=("ownership", "short_form"))
    b, nb = mu.u_sample_rules(o, own, spec, flags, (2015, 2024), order=("short_form", "ownership"))
    key = lambda f: sorted(zip(f.utility_id_eia, f.state, f.year))
    assert key(a) == key(b) and len(a) > 0
    assert sorted(na) == sorted(nb)
    assert set(a.utility_id_eia).isdisjoint({5, 6, 7, 9, 10})            # no class; two years; 9 left with two; 10 filed
    assert mu.U_SAMPLE_FILTER_ORDER == ("ownership", "short_form")
    # the count taken before the Short Form rule would keep utility 9 (three years, one of them a Short Form year)
    early, _ = mu._min_years(mu._u_drop_no_ownership(o, own)[0], 3, "utility")
    early, _ = mu._u_drop_short_form(early, spec, flags, (2015, 2024))
    if sf == "unit_years_filed":
        assert 9 in set(early.utility_id_eia) and 9 not in set(a.utility_id_eia)
    with pytest.raises(ValueError, match="three-year count is always taken last"):
        mu.u_sample_rules(o, own, spec, flags, (2015, 2024), order=("ownership", "three_years", "short_form"))


@pytest.mark.parametrize("field,bad,words", [
    ("ownership_spec", "interacted", "separate regressions on each of the three ownership classes"),
    ("ownership_spec", "interacted_three_classes", "separate regressions"),
    ("ss_correction", "none", "the usual clustered correction"),
    ("ss_correction", "clusters", "the usual clustered correction"),
    ("jurisdictions", mu.CONTIGUOUS_48_AND_DC, "50 states and the District of Columbia"),
    ("weighting", "customers", "states no weights"),
])
def test_u_each_approximation_of_ours_is_refused_in_words_if_departed_from(field, bad, words):
    o, mw, own = u_world(seed=6)
    with pytest.raises(ValueError, match=words) as e:
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec(**{field: bad}))
    assert "ours and not the paper's" in str(e.value) and "D-107" in str(e.value)


def test_u_the_specification_is_the_constants_and_each_carries_its_label():
    sp = mu.ryu_spec("none_in_outcome_frame")
    assert sp == uspec()
    assert (mu.RYU_OURS_OWNERSHIP_SPEC, mu.RYU_OURS_SS_CORRECTION, mu.RYU_OURS_WEIGHTING, mu.RYU_OURS_MW_SOURCE,
            mu.RYU_OURS_OUTCOME) == ("separate_subsamples", "clusters_and_parameters", "unweighted", "site_year_load",
                                     "res_price_default_service")
    assert mu.RYU_OURS_MIN_YEARS == (3, "utility", "every_other_restriction")
    assert mu.RYU_OURS_JURISDICTIONS == mu.FIFTY_STATES_AND_DC and len(mu.FIFTY_STATES_AND_DC) == 51
    assert mu.RYU_OURS_POLYGON == rt.ROW_U_POLYGON
    assert set(mu.RYU_APPROXIMATIONS) == {"ownership_estimates", "three_year_rule_counted", "jurisdictions",
                                          "capacity_dating", "assignment", "outcome_columns", "weights",
                                          "standard_errors"}
    for k, v in mu.RYU_APPROXIMATIONS.items():
        ruling = "D-109" if k == "assignment" else "D-107"          # U0's assignment was replaced by D-109
        assert "ours, not the paper's" in v["label"] and ruling in v["label"], k
    assert "retail priority is not applied" in mu.RYU_APPROXIMATIONS["assignment"]["label"]
    assert mu.RYU_APPROXIMATIONS["assignment"]["value"] == rt.ROW_U_POLYGON_LABEL
    assert all(mu.U_STEPS[s]["rule"].endswith("|site_year_load") for s in mu.U_STEPS)
    assert mu.U_STEPS["U1"]["change"] == "the inventory's own assignment in place of the polygon"
    o, mw, own = u_world(seed=6)
    r = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, sp)
    assert r["specification"]["ours_adopted_2026_11_19_d107"] == mu.RYU_APPROXIMATIONS
    assert r["specification"]["exact_reproduction_unavailable"] == list(mu.RYU_UNAVAILABLE)
    with pytest.raises(ValueError, match="needs a treatment built under"):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw, "verified|full_size_from_energized_year"), own, sp)


def test_u_a_step_names_the_sites_its_result_depends_on():
    o, mw, own = u_world(seed=6)
    tr = rt.Treatment("polygon_smallest_any_type|site_year_load", mw.assign(rule="x"), pd.DataFrame(columns=["fid", "reason"]),
                      [], ["site_a", "site_c"])
    r = mu.run_u_step("U0", o, mu.DEFAULT_SERVICE, tr, own, uspec())
    assert r["sites_depending_on_ambiguous_polygon_classes"] == ["site_a", "site_c"]
    assert any("depends on 2 sites" in n and "ambiguous" in n for n in r["notes"])
    r0 = mu.run_u_step("U0", o, mu.DEFAULT_SERVICE, utreat(mw, U_RULE["U0"]), own, uspec())
    assert r0["sites_depending_on_ambiguous_polygon_classes"] == []


def test_u_units_with_no_ownership_class_leave_and_other_classes_stay_pooled():
    # the paper keeps utilities "reporting ownership-type data" (p. 6); other classes enter the pooled run only (p. 8)
    o, mw, own = u_world(seed=9)
    win = int(((o.year >= 2015) & (o.year <= 2024)).sum())
    full = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    assert full["pooled"]["n"] == win
    dropped = own[own.utility_id_eia.isin([4, 8])]
    n_drop = int((o.utility_id_eia.isin([4, 8]) & (o.year >= 2015) & (o.year <= 2024)).sum())
    r = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own.drop(index=dropped.index), uspec())
    assert r["pooled"]["n"] == win - n_drop and any("no ownership class" in n for n in r["notes"])
    own2 = own.copy()
    own2.loc[own2.utility_id_eia == 4, "ownership_class"] = None
    r2 = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own2, uspec())
    assert r2["pooled"]["n"] == win - int((o.utility_id_eia.eq(4) & (o.year >= 2015) & (o.year <= 2024)).sum())
    q = pd.DataFrame({"utility_id_eia": [1, 1, 2, 3], "state": ["AL", "AL", "AL", "AL"], "year": [2015, 2016, 2015, 2015],
                      "entity_type": [None, None, "Cooperative", "Federal"]})
    oc = mu.ownership_classes(q, "U", "last").set_index("utility_id_eia").ownership_class
    assert oc[1] is None and oc[2] == "cooperative" and oc[3] == "other"


def test_u_short_form_rules():
    o, mw, own = u_world(seed=10)
    flags = o[KEY + ["year"]].assign(short_form=False)
    flags.loc[(flags.utility_id_eia == 5) & (flags.year == 2016), "short_form"] = True
    w = (o.year >= 2015) & (o.year <= 2024)
    base = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())["pooled"]["n"]
    by_year = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec(short_form_exclusion="unit_years_filed"),
                            sample_flags=flags)
    assert by_year["pooled"]["n"] == base - 1
    ever = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec(short_form_exclusion="utilities_ever_filed"),
                         sample_flags=flags)
    assert ever["pooled"]["n"] == base - int((o.utility_id_eia.eq(5) & w).sum())
    with pytest.raises(ValueError, match="sample_flags"):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec(short_form_exclusion="unit_years_filed"))
    with pytest.raises(ValueError):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec(short_form_exclusion="drop_small"))
    with pytest.raises(ValueError, match="no weights"):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec(weighting="sales"))


def test_u_separate_regressions_leave_the_other_classes_out_of_every_ownership_fit():
    # the other classes get their own year shocks; each class's own regression has its own year effects, so the planted
    # coefficients come back exactly (separate regressions, ours, D-107)
    beta = {"cooperative": 0.008, "municipal": 0.012, "investor_owned": 0.001, "other": 0.004}
    o, mw, own = u_world(seed=3, beta=beta)
    other = set(own[own.ownership_class == "other"].utility_id_eia)
    rng = np.random.default_rng(1)
    shock = {t: rng.normal(0, 0.1) for t in range(2014, 2026)}
    o["value"] = [v * np.exp(shock[t]) if u in other else v for u, t, v in zip(o.utility_id_eia, o.year, o.value)]
    r = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    for c in mu.U_CLASSES:
        assert abs(r["by_ownership"][c]["estimate"] - beta[c]) < 1e-10           # tolerance: floating point


def test_u_paper_constants_are_the_plans_numbers_and_the_papers_sample_sizes():
    # PREANALYSIS.md row U; the paper: Table A4a p. 25, Table A3 p. 23, Table A3a Panel B p. 24, Table A4b p. 25
    assert mu.PAPER_U["pooled_no_controls"] == (0.0095, 0.0026)
    assert mu.PAPER_U["pooled_with_controls"] == (0.0094, 0.0026)
    assert mu.PAPER_U["cooperative_with_controls"] == (0.0067, 0.0024)
    assert mu.PAPER_U["municipal_with_controls"] == (0.0080, 0.0044)
    assert mu.PAPER_U["investor_owned_with_controls"] == (0.0006, 0.0043)
    n = mu.PAPER_U_N
    assert (n["pooled_observations"], n["pooled_utilities"], n["clusters"]) == (16163, 1798, 51)
    assert n["cooperative_observations"] + n["municipal_observations"] + n["investor_owned_observations"] == 15445
    assert mu.RYU_WINDOW == (2015, 2024) and all(mu.U_STEPS[s]["window"] == mu.RYU_WINDOW for s in ("U0", "U1", "U2"))
    assert mu.RYU_CLUSTER == "state" and mu.RYU_UNIT_EFFECT == "utility_id_eia" and mu.RYU_N_JURISDICTIONS == 51
    o, mw, own = u_world(seed=11)
    r = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    assert r["paper_printed_sample_sizes"] == n and r["jurisdictions_in_sample"] == len(U_STATES)


M0_TEXT = "On an open facility list the closest published design does not return its published answer"   # row M

# Words that amount to a reproduction verdict. No row U output may carry one (Joe, 2026-11-19, D-107).
VERDICT = re.compile(r"\breproduced\b|\bsurviv|matches the paper|\bas a miss\b|\bnot reproduce\b", re.IGNORECASE)
VERDICT_KEYS = {"reproduced", "in_band", "ownership_ordering_holds", "survives"}


def walk(x, path="r"):
    """Every (path, key or string) in a result, recursively."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield path, str(k), "key"
            yield from walk(v, f"{path}.{k}")
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(x, str):
        yield path, x, "text"


def verdicts_in(result) -> list:
    return [(p, v) for p, v, kind in walk(result) if (kind == "text" and VERDICT.search(v)) or
            (kind == "key" and v in VERDICT_KEYS)]


# beta pairs: the pooled estimate inside and outside the band, the ordering holding and reversed
U_OUTCOMES = {
    "inside_band_ordering_holds": {"cooperative": 0.010, "municipal": 0.012, "investor_owned": 0.002, "other": 0.009},
    "inside_band_ordering_reversed": {"cooperative": 0.004, "municipal": 0.005, "investor_owned": 0.020, "other": 0.009},
    "above_band_ordering_holds": {"cooperative": 0.040, "municipal": 0.050, "investor_owned": 0.010, "other": 0.040},
    "below_band_ordering_reversed": {"cooperative": -0.010, "municipal": -0.005, "investor_owned": 0.010, "other": 0.0},
}


@pytest.mark.parametrize("case", list(U_OUTCOMES))
def test_no_row_u_output_carries_a_reproduction_verdict(case):
    """Every step, every outcome: the pooled estimate inside and outside the paper's band, the ordering holding and
    reversed. U0 returns the pooled comparison with the band beside it whatever the estimate; every step returns the
    ownership comparison with its label and the missing-coverage qualification; u1_sentence returns the adopted
    sentence the one fact picks (D-109), the same for every value of indistinguishable, with no verdict word."""
    o, mw, own = u_world(seed=21, beta=U_OUTCOMES[case])
    seen_inside = []
    for step in mu.U_STEPS:
        r = mu.run_u_step(step, o, mu.U_STEPS[step]["price"], utreat(mw, U_RULE[step]), own, uspec())
        assert verdicts_in(r) == [], (step, verdicts_in(r))
        assert [t for _, t, k in walk(r) if k == "text" and "until Joe rules" in t] == []
        assert r["missing_coverage"] == rt.MISSING_COVERAGE_QUALIFICATION
        oc = r["ownership_comparison"]
        assert oc["label"] == mu.U_OWNERSHIP_COMPARISON_LABEL and oc["verdict"] is None
        assert "six controls" in oc["label"] and "neither" in oc["label"] and "Comparison-only" in oc["label"]
        if step == "U0":
            pc = r["pooled_comparison"]
            assert pc["label"] == mu.U_POOLED_COMPARISON_LABEL and pc["verdict"] is None
            assert pc["paper_band_beside"] == list(mu.BAND_U) and pc["paper_no_controls"] == (0.0095, 0.0026)
            assert pc["missing_coverage"] == rt.MISSING_COVERAGE_QUALIFICATION
            assert r["assignment_rule"] == {"label": rt.ROW_U_POLYGON_LABEL,
                                            "coincidence_with_row_c": rt.ROW_U_C_COINCIDENCE}
            est = r["pooled"]["estimate"]
            seen_inside.append(mu.BAND_U[0] <= est <= mu.BAND_U[1])
        if step == "U1":
            holds = case.endswith("ordering_holds")
            assert oc["co_op_and_municipal_each_above_investor_owned_in_our_estimates"] is holds
            want = (mu.U1_SENTENCE_EACH_ABOVE if holds else mu.U1_SENTENCE_NOT_EACH_ABOVE) + " " + mu.U1_CONTROLS_SENTENCE
            for ind in (True, False, None):
                u1 = mu.u1_sentence(r, ind)
                assert u1["sentence"] == want and verdicts_in(u1) == []
                assert u1["comparison"] == oc and u1["indistinguishable_as_passed"] is ind
    assert seen_inside == [case.startswith("inside")]                   # the world puts U0 where the case says


U_TEXT_CONSTANTS = ("U_OWNERSHIP_COMPARISON_LABEL", "U_POOLED_COMPARISON_LABEL", "U1_NO_SENTENCE", "OURS_D107",
                    "U1_SENTENCE_EACH_ABOVE", "U1_SENTENCE_NOT_EACH_ABOVE", "U1_CONTROLS_SENTENCE", "U1_WORDING_STATUS",
                    "U_SHORT_FORM_NO_SUBSTITUTE", "U_SHORT_FORM_NOT_APPLIED_LABEL", "U_SHORT_FORM_ADOPTED_LABEL")
STATS_WORDS = re.compile(r"significan|p-value|confidence interval|z-score|indistinguishab|\bt-test\b|\btest(ed|s)?\b",
                         re.IGNORECASE)


def test_the_row_u_labels_and_constants_carry_no_verdict_word():
    for name in U_TEXT_CONSTANTS:
        assert not VERDICT.search(getattr(mu, name)), name
        assert "until Joe rules" not in getattr(mu, name) and "waits on" not in getattr(mu, name), name
    for v in list(mu.RYU_UNAVAILABLE) + [x["value"] + x["label"] + x["paper"] for x in mu.RYU_APPROXIMATIONS.values()]:
        assert not VERDICT.search(v), v
    for v in (rt.ROW_U_POLYGON_LABEL, rt.ROW_U_C_COINCIDENCE, rt.MISSING_COVERAGE_QUALIFICATION,
              rt.ENTITY_TYPE_LIST_LABEL):
        assert not VERDICT.search(v), v
    assert not hasattr(mu, "U1_SURVIVES") and not hasattr(mu, "U1_DOES_NOT")


def test_u1_sentences_are_the_adopted_drafts_word_for_word():
    """Joe, 2026-11-19 (D-109): the drafted U1 wording (docs/gate1/rows-u-c-reproduction-assessment-2026-11-19.md
    section 3), chosen by one fact, each followed by the sentence on the paper's six controls. No statistical-test word
    enters them."""
    assert mu.U1_SENTENCE_EACH_ABOVE == ("In our estimates without controls, the co-op and municipal coefficients are "
                                         "each above the investor-owned one when the inventory's own assignment "
                                         "replaces the polygon.")
    assert mu.U1_SENTENCE_NOT_EACH_ABOVE == ("In our estimates without controls, the co-op and municipal coefficients "
                                             "are not each above the investor-owned one when the inventory's own "
                                             "assignment replaces the polygon.")
    assert mu.U1_CONTROLS_SENTENCE == ("The paper estimates its ownership split with six controls that we do not "
                                       "build, so this neither confirms nor contradicts its result.")
    for s in (mu.U1_SENTENCE_EACH_ABOVE, mu.U1_SENTENCE_NOT_EACH_ABOVE, mu.U1_CONTROLS_SENTENCE):
        assert not STATS_WORDS.search(s), s
    base = {"step": "U1"}
    for fact, first in ((True, mu.U1_SENTENCE_EACH_ABOVE), (False, mu.U1_SENTENCE_NOT_EACH_ABOVE)):
        comp = {"co_op_and_municipal_each_above_investor_owned_in_our_estimates": fact}
        u1 = mu.u1_sentence({**base, "ownership_comparison": comp}, None)
        assert u1["sentence"] == first + " " + mu.U1_CONTROLS_SENTENCE and "D-109" in u1["wording_status"]
    u1 = mu.u1_sentence({**base, "ownership_comparison": {
        "co_op_and_municipal_each_above_investor_owned_in_our_estimates": None}}, True)
    assert u1["sentence"] is None and u1["why"] == mu.U1_NO_SENTENCE


def test_u_short_form_never_uses_outcome_availability():
    """Joe, 2026-11-19 (D-109): outcome availability is not a substitute for the paper's Short Form exclusion. Under
    'none_in_outcome_frame' no exclusion is applied and the result says it is not the paper's sample. Under
    'utilities_ever_filed' a utility flagged in a year whose price is MISSING still leaves in every year: the flag
    table decides, not which unit-years have a price."""
    o, mw, own = u_world(seed=10)
    r = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    assert r["short_form_status"] == mu.U_SHORT_FORM_NOT_APPLIED_LABEL
    assert "not the paper's sample" in r["short_form_status"] and "Outcome availability" in r["short_form_status"]
    assert any(n.startswith("Short Form: no exclusion applied") and "not the paper's sample" in n for n in r["notes"])
    flags = o[KEY + ["year"]].assign(short_form=False)
    flags.loc[(flags.utility_id_eia == 5) & (flags.year == 2016), "short_form"] = True
    o2 = o.copy()
    o2.loc[(o2.utility_id_eia == 5) & (o2.year == 2016), "value"] = np.nan     # the flagged year has no price
    ever = mu.run_u_step("U1", o2, mu.DEFAULT_SERVICE, utreat(mw), own, uspec(short_form_exclusion="utilities_ever_filed"),
                         sample_flags=flags)
    w = (o2.year >= 2015) & (o2.year <= 2024) & o2.value.notna()
    assert ever["pooled"]["n"] == int(w.sum()) - int((w & o2.utility_id_eia.eq(5)).sum())
    assert "Outcome availability" in ever["short_form_status"]


def _adopted_status_problems(r) -> list:
    bad = []
    if not r["short_form_status"].endswith(mu.U_SHORT_FORM_ADOPTED_LABEL):
        bad.append("label")
    if "short_form_filers.adopted_row_u_flags" not in r["short_form_status"]:
        bad.append("builder")
    if r["specification"]["short_form_exclusion"] != {"as_supplied": "unit_years_filed", "adopted_code": "unit_years_filed",
                                                      "adopted": "by Joe on 2026-11-20 (D-115)"}:
        bad.append("specification")
    if "still_open" in r["specification"]:
        bad.append("still open")
    return bad


def test_u_the_adopted_code_carries_the_adopted_label():
    """Joe, 2026-11-20 (D-115): under the adopted code 'unit_years_filed' the result carries U_SHORT_FORM_ADOPTED_LABEL
    and names the flags' builder; 'none_in_outcome_frame' keeps U_SHORT_FORM_NOT_APPLIED_LABEL; nothing says the rule is
    open."""
    o, mw, own = u_world(seed=10)
    flags = o[KEY + ["year"]].assign(short_form=False)
    flags.loc[(flags.utility_id_eia == 5) & (flags.year == 2016), "short_form"] = True
    r = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, mu.ryu_spec(mu.U_SHORT_FORM_ADOPTED_CODE),
                      sample_flags=flags)
    assert _adopted_status_problems(r) == []
    assert any("1 unit-years left out as Short Form filers (unit_years_filed)" in n for n in r["notes"])
    assert verdicts_in(r) == []
    low = " ".join(t for _, t, k in walk(r) if k == "text").lower()
    for bad in ("still open", "stopped", "undecided", "did not file", "non-filer", "not a filer"):
        assert bad not in low, bad
    n = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, uspec())
    assert n["short_form_status"] == mu.U_SHORT_FORM_NOT_APPLIED_LABEL
    assert n["specification"]["short_form_exclusion"]["as_supplied"] == "none_in_outcome_frame"


def test_u_the_adopted_label_check_can_fail(monkeypatch):
    """Break: the adopted label replaced in the test process after the result is built; the check then fails."""
    o, mw, own = u_world(seed=10)
    flags = o[KEY + ["year"]].assign(short_form=False)
    r = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, mu.ryu_spec(mu.U_SHORT_FORM_ADOPTED_CODE),
                      sample_flags=flags)
    monkeypatch.setattr(mu, "U_SHORT_FORM_ADOPTED_LABEL", "another label")
    assert "label" in _adopted_status_problems(r)


def test_u_module_strings_no_longer_say_the_short_form_rule_is_open():
    """Session 25, Joe's ruling D-115: the strings that said the rule was open or stopped are brought to it."""
    src = Path(mu.__file__).read_text()
    for bad in ("STILL OPEN", "the one element still open", "STOPPED outside 2019", "Still open, a required field"):
        assert bad not in src, bad
    for name in ("RyuSpec", "ryu_spec", "_u_drop_short_form"):
        assert "D-115" in getattr(mu, name).__doc__, name


def test_u1_sentence_is_for_u1_only():
    o, mw, own = u_world(seed=7)
    r = mu.run_u_step("U2", o, mu.DELIVERY_INCLUSIVE, utreat(mw), own, uspec())
    with pytest.raises(ValueError, match="U1 only"):
        mu.u1_sentence(r)


def test_no_step_opens_a_file(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a step tried to read a file")
    o, t, own = m_world(seed=13)
    uo, mw, uown = u_world(seed=13)
    for mod, name in ((builtins, "open"), (pd, "read_parquet"), (pd, "read_csv"), (np, "load"), (pd, "read_json")):
        monkeypatch.setattr(mod, name, refuse)
    run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec())
    mu.run_u_step("U1", uo, mu.DEFAULT_SERVICE, utreat(mw), uown, uspec())


@pytest.mark.parametrize("sf", ["unit_years_filed", "utilities_ever_filed"])
def test_u_a_missing_or_absent_flag_is_never_read_as_anything(sf):
    """Session 21: how a missing Short Form flag, or a unit-year with no flag row, is to be read is not settled, so the
    step stops in words; rows that share a unit-year must agree."""
    o, mw, own = u_world(seed=10)
    flags = o[KEY + ["year"]].assign(short_form=False)
    spec = uspec(short_form_exclusion=sf)
    ok = mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, spec, sample_flags=flags)
    assert ok["pooled"]["n"] > 0
    miss = flags.assign(short_form=flags.short_form.astype("boolean"))
    miss.loc[(miss.utility_id_eia == 5) & (miss.year == 2017), "short_form"] = pd.NA
    with pytest.raises(ValueError, match="missing flag"):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, spec, sample_flags=miss)
    gone = flags[~((flags.utility_id_eia == 5) & (flags.year == 2017))]
    with pytest.raises(ValueError, match="no row in sample_flags"):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, spec, sample_flags=gone)
    clash = pd.concat([flags, flags[(flags.utility_id_eia == 5) & (flags.year == 2017)].assign(short_form=True)])
    with pytest.raises(ValueError, match="disagree"):
        mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, spec, sample_flags=clash)
    same = pd.concat([flags, flags.head(3)])                               # identical duplicates are accepted
    assert mu.run_u_step("U1", o, mu.DEFAULT_SERVICE, utreat(mw), own, spec, sample_flags=same)["pooled"]["n"] == ok["pooled"]["n"]


# --------------------------------------------------------------------------------------------------------------------
# Row M after the bounded read of the paper (session 21; file dated 2026-10-23,
# docs/gate1/bounded-read-row-m-2026-11-19.md): settled constants refused when departed from, the new required
# arguments refused when missing, the two readings of the 5 MW count, and the sample rules end to end.
# --------------------------------------------------------------------------------------------------------------------

def test_m_settled_constants_are_the_papers():
    assert mu.MEEKS_FILE_DATE == "2026-10-23" and "2026-10-23" in mu.MEEKS_FILE
    assert mu.MEEKS_WINDOW == (2010, 2024) and mu.MEEKS_DROPS_FIRST_TREATED_BEFORE == 2010
    assert all(tuple(mu.M_STEPS[s]["window"]) == mu.MEEKS_WINDOW for s in ("M0", "M1", "M2"))
    assert mu.M_STEPS["M0"]["price"] == mu.M_STEPS["M1"]["price"] == mu.MEEKS_OUTCOME == mu.DEFAULT_SERVICE
    assert mu.MEEKS_SIZE_THRESHOLD_MW == 5.0 and mu.MEEKS_CUSTOMER_FLOOR is None
    assert mu.MEEKS_EXCLUDES_SHORT_FORM is True and mu.MEEKS_SHORT_FORM_LEVEL == "utility_ever"
    assert mu.MEEKS_REQUIRES_THREE_CLASSES is True and mu.MEEKS_REQUIRES_RETAIL_COMPONENT is True
    assert mu.MEEKS_COMPARISON == "never_treated" and mu.MEEKS_CLUSTER == "utility_state_pair"
    assert set(mu.MEEKS_PUBLIC_ENTITY_TYPES) == {"Federal", "State", "Municipal", "Political Subdivision"}
    assert set(mu.MEEKS_SIZE_COUNTING_READINGS) == set(rt.SIZE_COUNTING)       # both readings stay expressible
    assert "Joe" in mu.MEEKS_SIZE_COUNTING_STATUS and "not settled" in mu.MEEKS_SIZE_COUNTING_STATUS
    assert mu.PAPER_M == {"pooled": (0.021, 0.008), "investor_owned": (0.052, 0.014), "public": (0.017, 0.015),
                          "cooperative": (-0.007, 0.010)}
    assert mu.PAPER_M_N["observations"] == 14733 and mu.PAPER_M_N["utility_state_pairs"] == 1048
    assert mu.PAPER_M_N["treated_utilities"] == 112 and mu.PAPER_M_N["states"] == 48


@pytest.mark.parametrize("field,bad,words", [
    ("jurisdictions", mu.FIFTY_STATES_AND_DC, "contiguous United States"),
    ("jurisdictions", tuple(s for s in mu.CONTIGUOUS_48 if s != "TX"), "contiguous United States"),
    ("customer_floor", 2000, "no customer floor"),
    ("exclude_short_form", False, "ever file the EIA-861 Short Form"),
    ("require_three_classes", False, "residential, commercial and industrial"),
])
def test_m_each_settled_value_is_refused_in_words_if_departed_from(field, bad, words):
    mspec().check()
    mspec(jurisdictions=mu.CONTIGUOUS_48_AND_DC).check()          # whether DC is in stays the caller's choice
    with pytest.raises(ValueError, match=words):
        mspec(**{field: bad}).check()


NEW_M_FIELDS = ("short_form_years", "three_classes_level", "three_classes_test", "retail_component",
                "window_start_cohort", "weighting")


@pytest.mark.parametrize("field", NEW_M_FIELDS)
def test_m_each_new_required_argument_has_no_default(field):
    kw = dict(mspec().__dict__)
    kw.pop(field)
    with pytest.raises(TypeError, match=field):
        mu.MeeksSpec(**kw)


@pytest.mark.parametrize("field,bad,words", [
    ("short_form_years", None, "short_form_years"), ("short_form_years", (2024, 2010), "short_form_years"),
    ("short_form_years", (2010,), "short_form_years"),
    ("three_classes_level", "pair_ever", "three_classes_level"), ("three_classes_test", "positive_revenue", "serve"),
    ("retail_component", "entity_type", "retail component"), ("window_start_cohort", "guess", "first year"),
    ("weighting", "customers", "unweighted"),
])
def test_m_each_new_required_argument_is_refused_in_words_when_not_a_built_candidate(field, bad, words):
    with pytest.raises(ValueError, match=words):
        mspec(**{field: bad}).check()


def test_m_the_5mw_threshold_is_refused_if_departed_from_and_an_unknown_count_is_refused():
    o, t, own = m_world(seed=21)
    with pytest.raises(ValueError, match="above 5 MW"):
        run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t, "verified|above_6mw|site|mw_full"), own, mspec())
    with pytest.raises(ValueError, match="not settled"):
        run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t, "verified|above_5mw|by_campus|mw_full"), own, mspec())
    r4 = run_m("M4", o, mu.M_STEPS["M4"]["price"], mtreat(t, "verified|dose_at_least_0.02"), own, mspec())
    assert r4["size_counting"] is None and r4["size_counting_status"] is None


def test_m_the_two_readings_of_the_5mw_count_give_different_treated_sets():
    """An invented county with two 3 MW sites activated the same year (6 MW together) and one unit serving it: by site
    no data center is above 5 MW; summed over the county-year it is. Both readings run through run_m_step and the result
    names the reading and that the difference is with Joe."""
    sites = pd.DataFrame({"fid": [1, 2, 3], "state": ["TX", "TX", "OK"], "energized_year": [2015, 2015, 2018],
                          "mw_full": [3.0, 3.0, 8.0], "is_crypto": False})
    units = pd.DataFrame({"utility_id_eia": [10, 20, 30], "state": ["TX", "OK", "KS"]})
    a = rt.Assignment("county_touch", pd.DataFrame({"fid": [1, 2, 3], "utility_id_eia": [10, 10, 20],
                                                    "state": ["TX", "TX", "OK"], "rule": "county_touch"}),
                      pd.DataFrame(columns=["fid", "reason"]))
    sc = pd.DataFrame({"fid": [1, 2, 3], "county": ["48001", "48001", "40001"]})
    by_site = rt.first_year_above_size(sites, a, units, size_column="mw_full", counting="site")
    by_cy = rt.first_year_above_size(sites, a, units, size_column="mw_full", counting="county_year_new_capacity",
                                     site_county=sc)
    fs = by_site.table.set_index(KEY).first_year
    fc = by_cy.table.set_index(KEY).first_year
    assert np.isnan(fs[(10, "TX")]) and fc[(10, "TX")] == 2015          # the readings differ on the small sites
    assert fs[(20, "OK")] == fc[(20, "OK")] == 2018                       # and agree on one site above 5 MW
    treated_site = set(fs.dropna().index)
    treated_cy = set(fc.dropna().index)
    assert treated_site == {(20, "OK")} and treated_cy == {(10, "TX"), (20, "OK")}
    # both readings are accepted by row M, and the result says which and that it is with Joe
    rows = [{"utility_id_eia": u, "state": s, "year": y, "value": 10.0 + (0.5 if (u, s) in treated_cy and y >= 2015 else 0)}
            for u, s in zip(units.utility_id_eia, units.state) for y in range(2010, 2025)]
    o = pd.DataFrame(rows)
    own = units.assign(ownership_class=["investor_owned", "public", "cooperative"])
    for tr, reading in ((by_site, "site"), (by_cy, "county_year_new_capacity")):
        r = run_m("M0", o, mu.DEFAULT_SERVICE, tr, own, mspec())
        assert r["size_counting"] == reading and "Joe" in r["size_counting_status"]
        assert r["pooled"]["n_treated_units"] == (1 if reading == "site" else 2)


def test_m_public_class_is_the_papers_four_types():
    mu._check_m_public_types()
    bad = dict(mu.M_MAP)
    bad.pop("Federal")
    with pytest.raises(ValueError, match="political subdivision"):
        mu._check_m_public_types(bad)
    bad2 = dict(mu.M_MAP, **{"Retail Power Marketer": "public"})
    with pytest.raises(ValueError, match="p. 16"):
        mu._check_m_public_types(bad2)


def test_m_short_form_drops_every_state_pair_of_a_utility_that_ever_filed():
    o, t, own = m_world(seed=22, noise=0.0)
    # utility 5 also has a second state pair (copy its rows into another state); only its first pair is flagged
    u5 = o[o.utility_id_eia == 5]
    other = "NM" if u5.state.iloc[0] != "NM" else "CO"
    o2 = pd.concat([o, u5.assign(state=other)], ignore_index=True)
    t2 = pd.concat([t, t[t.utility_id_eia == 5].assign(state=other)], ignore_index=True)
    own2 = pd.concat([own, own[own.utility_id_eia == 5].assign(state=other)], ignore_index=True)
    first_state = u5.state.iloc[0]
    flags = mflags(o2, ever_short_form=lambda d: (d.utility_id_eia == 5) & (d.state == first_state))
    base = run_m("M1", o2, mu.DEFAULT_SERVICE, mtreat(t2), own2, mspec())
    r = run_m("M1", o2, mu.DEFAULT_SERVICE, mtreat(t2), own2, mspec(), sample_flags=flags)
    assert r["pooled"]["n_units"] == base["pooled"]["n_units"] - 2              # both of utility 5's pairs leave
    assert any("1 utilities, every state pair" in n for n in r["notes"])
    assert abs(r["pooled"]["estimate"] - 0.03) < 1e-10                        # tolerance: floating point


def test_m_three_classes_by_unit_year_drops_only_the_failing_years():
    o, t, own = m_world(seed=23, noise=0.0)
    sp = mspec(three_classes_level="unit_year")
    fail = (o.utility_id_eia == 7) & (o.year.isin([2016, 2017]))
    n_fail = int((fail & o.year.between(2010, 2024)).sum())
    flags = mflags(o, sp, by_year=True)
    flags["has_three_classes"] = ~((flags.utility_id_eia == 7) & flags.year.isin([2016, 2017]))
    r = run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, sp, sample_flags=flags)
    assert any(f"{n_fail} unit-years left out by has_three_classes (unit_year" in n for n in r["notes"])
    # the same flag read once per unit is refused: two values for one pair
    with pytest.raises(ValueError, match="more than one has_three_classes"):
        run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec(), sample_flags=flags)


@pytest.mark.parametrize("change,words", [
    (lambda f: f.drop(columns="short_form_last_year_read"), "lacks"),
    (lambda f: f.assign(short_form_first_year_read=2012), "Short Form flag was not read over"),
    (lambda f: f.assign(three_classes_test="positive_customers"), "not built under the spec's test"),
    (lambda f: f.iloc[1:], "has no ever_short_form"),
])
def test_m_sample_flags_that_do_not_match_the_spec_are_refused_in_words(change, words):
    o, t, own = m_world(seed=24)
    with pytest.raises(ValueError, match=words):
        run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec(), sample_flags=change(mflags(o)))
    sp = mspec(three_classes_level="unit_year")
    with pytest.raises(ValueError, match="year"):
        run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, sp, sample_flags=mflags(o, sp))      # no year column
    with pytest.raises(ValueError, match="has_retail_component"):
        run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec(retail_component="flag"))


def test_m_retail_component_flag_drops_pairs_and_the_implied_rule_says_so():
    o, t, own = m_world(seed=25, noise=0.0)
    sp = mspec(retail_component="flag")
    flags = mflags(o, sp, has_retail_component=lambda d: d.utility_id_eia % 13 != 0)
    n_drop = int(((o.utility_id_eia % 13 == 0) & o.year.between(2010, 2024)).sum())
    r = run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, sp, sample_flags=flags)
    assert any(f"{n_drop} unit-years left out by has_retail_component" in n for n in r["notes"])
    r2 = run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec())
    assert any("retail component: no separate filter" in n for n in r2["notes"])


def test_m_window_start_cohort_left_out_or_estimated_on_a_base_year_before_the_window():
    o, t, own = m_world(seed=26, noise=0.0)                 # the world has 2009 outcomes and a 2010 cohort of 3 units
    left = run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec())
    assert 2010 not in left["pooled"]["cohorts"]
    assert any(f.startswith("cohort 2010") for f in left["numerical_failures"])
    used = run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec(window_start_cohort="base_year_before_window"))
    assert 2010 in used["pooled"]["cohorts"] and not any(f.startswith("cohort 2010") for f in used["numerical_failures"])
    assert min(c["year"] for c in used["pooled"]["cells"]) == 2010                # 2009 is a base year, never a cell
    assert abs(used["pooled"]["estimate"] - 0.03) < 1e-10                       # tolerance: floating point
    assert any("read as base years only" in n for n in used["notes"])
    assert used["years"] == [2010, 2024]
    # pairs first treated before 2010 still leave under either choice (p. 20)
    assert any("before 2010 are dropped" in n for n in used["pooled"]["notes"])


def test_m_results_name_the_paper_file_and_carry_no_customer_floor():
    o, t, own = m_world(seed=27)
    r = run_m("M1", o, mu.DEFAULT_SERVICE, mtreat(t), own, mspec())
    assert r["paper_file"] == mu.MEEKS_FILE and r["spec"]["customer_floor"] is None
    assert r["spec"]["exclude_short_form"] is True and r["spec"]["require_three_classes"] is True


# --------------------------------------------------------------------------------------------------------------------
# Ownership for row U under Joe's ruling of 2026-11-20 (D-117): the last nonmissing reported entity type over 2001 to
# 2025, time-invariant, U_MAP unchanged, a unit with no type in any year left with no class. Invented quantities only.
# --------------------------------------------------------------------------------------------------------------------
ALL_YEARS = range(2001, 2026)


def q_world() -> pd.DataFrame:
    """Invented quantities over exactly 2001 to 2025, each unit with a known answer.
    (1, TX) Cooperative every year but 2025, missing in 2025      -> Cooperative (from 2024)
    (2, TX) Municipal 2001-2019, Investor Owned 2020-2025          -> Investor Owned (most often: Municipal)
    (3, TX) no type in any year                                   -> no type, no class
    (4, OK) Federal every year                                    -> Federal (row U: other)
    (2, OK) Investor Owned 2010-2022, missing 2023-2025           -> Investor Owned (from 2022)
    (5, TX) Municipal, Cooperative in 2011-2012, Municipal again  -> Municipal
    (6, TX) Cooperative 2001-2020, Municipal 2021-2025            -> Municipal (most often: Cooperative)"""
    rows = []
    for y in ALL_YEARS:
        rows.append((1, "TX", y, None if y == 2025 else "Cooperative"))
        rows.append((2, "TX", y, "Municipal" if y < 2020 else "Investor Owned"))
        rows.append((3, "TX", y, None))
        rows.append((4, "OK", y, "Federal"))
        if y >= 2010:
            rows.append((2, "OK", y, "Investor Owned" if y <= 2022 else None))
        rows.append((5, "TX", y, "Cooperative" if y in (2011, 2012) else "Municipal"))
        rows.append((6, "TX", y, "Cooperative" if y <= 2020 else "Municipal"))
    return pd.DataFrame(rows, columns=KEY + ["year", "entity_type"])


Q_WORLD_TYPES = {(1, "TX"): ("Cooperative", 2024), (2, "TX"): ("Investor Owned", 2025), (3, "TX"): (None, None),
                 (4, "OK"): ("Federal", 2025), (2, "OK"): ("Investor Owned", 2022), (5, "TX"): ("Municipal", 2025),
                 (6, "TX"): ("Municipal", 2025)}
Q_WORLD_U = {(1, "TX"): "cooperative", (2, "TX"): "investor_owned", (3, "TX"): None, (4, "OK"): "other",
             (2, "OK"): "investor_owned", (5, "TX"): "municipal", (6, "TX"): "municipal"}


def _type_mismatches(f=None) -> list:
    """Units whose last nonmissing type or its year differ from the known answer."""
    f = mu.last_nonmissing_entity_type(q_world()) if f is None else f
    got = {(int(u), s): (e, y) for u, s, e, y in zip(f.utility_id_eia, f.state, f.entity_type, f.entity_type_year)}
    return [k for k, v in Q_WORLD_TYPES.items() if got.get(k) != v] + sorted(set(got) - set(Q_WORLD_TYPES))


def test_d117_last_nonmissing_type_known_answers():
    """A missing type in the unit's last year takes the previous nonmissing one (unit 1 TX, and 2 OK whose last three
    years are missing); a type that changes takes the last (2 TX, 6 TX); a unit with no type stays with None (3 TX)."""
    f = mu.last_nonmissing_entity_type(q_world())
    assert _type_mismatches(f) == []
    assert len(f) == 7 and list(f.columns) == KEY + ["entity_type", "entity_type_year"]
    none_row = f[(f.utility_id_eia == 3) & (f.state == "TX")]
    assert none_row.entity_type.iloc[0] is None and none_row.entity_type_year.iloc[0] is None


def test_d117_missing_types_are_dropped_explicitly_not_by_a_pandas_default():
    """The last row of unit 1 TX has a missing type. Taking the last row's type without dropping missing values first
    (what a careless version would do) gives None there; the function gives Cooperative from 2024. The source drops
    missing types itself, by notna(), before taking the last."""
    q = q_world()
    careless = q.sort_values(KEY + ["year"]).groupby(KEY).tail(1).set_index(KEY).entity_type
    assert careless[(1, "TX")] is None                         # the trap is real in this world
    f = mu.last_nonmissing_entity_type(q).set_index(KEY)
    assert f.loc[(1, "TX"), "entity_type"] == "Cooperative" and f.loc[(1, "TX"), "entity_type_year"] == 2024
    src = __import__("inspect").getsource(mu.last_nonmissing_entity_type)
    assert "entity_type.notna()" in src and ".last()" not in src


def test_d117_the_pick_can_fail_when_missing_values_are_not_dropped(monkeypatch):
    """Break, made in the test process: a version that keeps missing types and takes each unit's last row. The known
    answers then fail for 1 TX and 2 OK."""
    def careless(q):
        g = q.sort_values(KEY + ["year"]).groupby(KEY).tail(1)
        return g.rename(columns={"year": "entity_type_year"})[KEY + ["entity_type", "entity_type_year"]]
    monkeypatch.setattr(mu, "last_nonmissing_entity_type", careless)
    assert set(_type_mismatches()) >= {(1, "TX"), (2, "OK")}


@pytest.mark.parametrize("change,outside,absent", [
    (lambda q: q[q.year != 2013], [], [2013]),
    (lambda q: q[q.year >= 2015], [], list(range(2001, 2015))),
    (lambda q: pd.concat([q, q[q.year == 2001].assign(year=2000)]), [2000], []),
    (lambda q: pd.concat([q, q[q.year == 2025].assign(year=2026)]), [2026], []),
])
def test_d117_years_other_than_2001_to_2025_are_refused_in_words(change, outside, absent):
    q = change(q_world())
    for fn in (mu.last_nonmissing_entity_type, mu.adopted_row_u_ownership_classes):
        with pytest.raises(ValueError) as e:
            fn(q)
        msg = str(e.value)
        assert "searches exactly 2001 to 2025" in msg and "A subset of years is not accepted" in msg
        assert f"outside that range {outside}" in msg and f"lack years of that range {absent}" in msg
        assert "D-117" in msg


def test_d117_year_refusal_can_fail(monkeypatch):
    """Break, made in the test process: the years searched set to the frame's own years (2013 missing). The frame
    lacking 2013 then passes silently, so the refusal test's pytest.raises fails."""
    q = q_world()[lambda d: d.year != 2013]
    monkeypatch.setattr(mu, "OWNERSHIP_YEARS_SEARCHED", tuple(sorted(int(y) for y in q.year.unique())))
    with pytest.raises(pytest.fail.Exception):
        with pytest.raises(ValueError):
            mu.last_nonmissing_entity_type(q)


def test_d117_two_types_in_one_unit_year_stop_in_words():
    q = pd.concat([q_world(), pd.DataFrame([(1, "TX", 2010, "Municipal")], columns=KEY + ["year", "entity_type"])])
    with pytest.raises(ValueError, match="carry two different entity types"):
        mu.last_nonmissing_entity_type(q)
    dup = pd.concat([q_world(), pd.DataFrame([(1, "TX", 2010, "Cooperative")], columns=KEY + ["year", "entity_type"])])
    assert _type_mismatches(mu.last_nonmissing_entity_type(dup)) == []        # an identical repeat is accepted


def test_d117_row_u_classes_known_answers_and_no_class_is_none():
    c = mu.adopted_row_u_ownership_classes(q_world())
    got = {(int(u), s): v for u, s, v in zip(c.utility_id_eia, c.state, c.ownership_class)}
    assert got == Q_WORLD_U
    assert got[(3, "TX")] is None                                  # None itself, not NaN and not "other"
    assert list(c.columns) == KEY + ["ownership_class"] and not c[KEY].duplicated().any()


def test_d117_row_u_classes_can_fail(monkeypatch):
    """Break: U_MAP replaced in the test process by one that sends Municipal to investor_owned; the known answers
    then fail."""
    monkeypatch.setattr(mu, "U_MAP", {**mu.U_MAP, "Municipal": "investor_owned"})
    c = mu.adopted_row_u_ownership_classes(q_world())
    assert {(int(u), s): v for u, s, v in zip(c.utility_id_eia, c.state, c.ownership_class)} != Q_WORLD_U


def test_d117_the_class_is_the_same_in_every_year_of_a_unit():
    q = q_world()
    c = mu.adopted_row_u_ownership_classes(q)
    m = q.merge(c, on=KEY, how="left")
    per_unit = m.groupby(KEY).ownership_class.apply(lambda s: len(set(s.astype(object).where(s.notna(), "none"))))
    assert (per_unit == 1).all() and len(m) == len(q)


def test_d117_adopted_call_takes_no_pick_and_u_map_is_unchanged():
    import inspect
    assert list(inspect.signature(mu.adopted_row_u_ownership_classes).parameters) == ["quantities"]
    assert list(inspect.signature(mu.last_nonmissing_entity_type).parameters) == ["quantities"]
    assert mu.U_MAP == {"Investor Owned": "investor_owned", "Cooperative": "cooperative", "Municipal": "municipal"}
    assert mu.OWNERSHIP_YEARS_SEARCHED == tuple(range(2001, 2026))
    # D-119 (Joe, 2026-11-20): the pick's text is the panel's type as he described it, then how the code reads it
    assert mu.OWNERSHIP_PICK_D117 == mu.OWNERSHIP_DESCRIPTION_D119 + " (D-119), " + mu.OWNERSHIP_HOW_READ_D117
    assert "time-invariant" in mu.OWNERSHIP_TIME_INVARIANT and "D-117" in mu.OWNERSHIP_SETTLED_D117
    assert "D-119" in mu.OWNERSHIP_SETTLED_D117
    doc = inspect.getdoc(mu.ownership_classes)
    assert "the Ryu and Hiatt paper does not say" not in doc and "settled" in doc and "D-117" in doc


def test_d117_a_unit_with_no_type_leaves_row_us_sample_and_is_never_other():
    """run_u_step's row filter on the adopted classes: 3 TX (no type in any year) leaves; 4 OK (Federal) stays as
    'other' for the pooled run."""
    own = mu.adopted_row_u_ownership_classes(q_world())
    o = q_world()[KEY + ["year"]]
    o = o[(o.year >= 2015) & (o.year <= 2024)]
    kept, note = mu._u_drop_no_ownership(o, own)
    assert (3, "TX") not in set(zip(kept.utility_id_eia, kept.state))
    assert set(kept[kept.utility_id_eia == 4].cls) == {"other"}
    assert note.startswith("10 unit-years with no ownership class are left out")
    assert "other" not in set(kept[(kept.utility_id_eia == 3)].cls)


def test_d117_the_old_ownership_classes_still_works_for_dormant_row_m():
    """Row M is dormant and outside D-117: ownership_classes keeps its signature, takes a pick and checks no years."""
    q = q_world()[lambda d: d.year >= 2015]                         # not 2001-2025, accepted here
    m = mu.ownership_classes(q, "M", "last").set_index(KEY).ownership_class
    assert m[(4, "OK")] == "public" and m[(2, "TX")] == "investor_owned" and m[(1, "TX")] == "cooperative"
    mo = mu.ownership_classes(q[q.entity_type.notna()], "M", "most_often").set_index(KEY).ownership_class
    assert mo[(6, "TX")] == "cooperative" and mo[(5, "TX")] == "public"
    with pytest.raises(ValueError, match="pick 'last' or 'most_often'"):
        mu.ownership_classes(q, "M", "first")


def test_d117_row_u_block_known_counts():
    b = mu._row_u_ownership_block(q_world())
    assert b["utility_states"] == 7 and b["years_present_in_the_quantities"] == list(range(2001, 2026))
    assert b["utility_states_with_more_than_one_distinct_entity_type_across_years"] == 3       # 2 TX, 5 TX, 6 TX
    assert b["utilities_with_more_than_one_distinct_entity_type_across_years_and_states"] == 3  # utilities 2, 5, 6
    assert b["utility_states_with_no_entity_type_in_any_year"] == 1                            # 3 TX
    assert b["utility_states_whose_class_differs_last_nonmissing_against_most_often"] == 2     # 2 TX, 6 TX
    assert b["utility_states_whose_class_differs_from_the_summarys_earlier_classes"] == 0
    assert b["class_counts"] == {"municipal": 2, "investor_owned": 2, "cooperative": 1, "other": 1,
                                 "no class (no entity type in any year)": 1}
    assert b["pick"] == mu.OWNERSHIP_PICK_D117 and b["years_searched"] == [2001, 2025]
    assert "utility-level modal reported type" in b["pick"] and mu.OWNERSHIP_RULING_D119_WORDS in b[
        "what_the_panel_column_is"]
    assert "NOT established" in b["what_the_panel_column_is"] and "data/raw" in b["what_the_panel_column_is"]
    assert "value_counts().index[0]" in b["what_the_panel_column_is"]
    __import__("json").dumps(b)


def test_d117_row_u_block_can_fail(monkeypatch):
    """Break: the adopted classes replaced in the test process by the most-often pick; the count of units differing
    between last nonmissing and most often then falls to zero and the known count fails."""
    monkeypatch.setattr(mu, "adopted_row_u_ownership_classes",
                        lambda q: mu.ownership_classes(q[q.entity_type.notna()], "U", "most_often"))
    assert mu._row_u_ownership_block(q_world())[
        "utility_states_whose_class_differs_last_nonmissing_against_most_often"] != 2


def test_d117_main_and_the_row_u_frame_use_the_adopted_call():
    import inspect
    from pipeline.analysis import short_form_filers as sff
    src = inspect.getsource(mu.main)
    assert "own_u = adopted_row_u_ownership_classes(q)" in src and 'ownership_classes(q, "U"' not in src
    assert "row_u_ownership_classification_d117" in src
    fsrc = inspect.getsource(sff.row_u_quantity_frame)
    assert "mu.adopted_row_u_ownership_classes(q)" in fsrc and "ownership_classes(q, \"U\"" not in fsrc


def test_d117_no_text_calls_the_pick_open_or_reads_no_type_as_a_class():
    import inspect
    from pipeline.analysis import reconciliation_c as rc
    from pipeline.analysis import short_form_filers as sff
    for m in (mu, rc, sff):
        src = inspect.getsource(m)
        assert "pick is open" not in src and "the Ryu and Hiatt paper does not say" not in src
        for bad in ("no entity type is independent", "no type is independent", "no entity type is public",
                    "no type is public"):
            assert bad not in src


# ---- Joe's ruling of 2026-11-20 on what rows U and C's ownership type is (D-119) -------------------------------------
# "Keep the existing panel entity type for rows U and C, accurately described as the utility-level modal reported type
# carried across the panel, not the latest year-by-year EIA classification. No further raw-data investigation."
D119_WORDS = ("Keep the existing panel entity type for rows U and C, accurately described as the utility-level modal "
              "reported type carried across the panel, not the latest year-by-year EIA classification. No further "
              "raw-data investigation.")
# the negations the ruling itself uses, removed before a text is searched for "latest"
D119_NEGATIONS = ("not the latest year-by-year EIA classification", "not as the latest year-by-year EIA classification")


def _flat(t: str) -> str:
    """Whitespace collapsed; for a text cut from source, the joins of adjacent string literals removed."""
    return " ".join(str(t).split()).replace('" "', "")


def d119_text_problems(texts: dict) -> list:
    """The texts of rows U and C's ownership that (a) do not describe the type as the panel's modal type, (b) leave a
    reader thinking the class is the latest year-by-year type, or (c) call the pick open or the caller's choice."""
    bad = []
    for name, t in texts.items():
        t = _flat(t)
        rest = t.replace(D119_WORDS, "")
        for n in D119_NEGATIONS:
            rest = rest.replace(n, "")
        low = rest.lower()
        for phrase in ("latest", "most recent", "last reported by eia", "last nonmissing reported", "pick is open",
                       "caller's choice", "still the caller's"):
            if phrase in low:
                bad.append((name, phrase))
        if "modal" not in t and name != "how_read":
            bad.append((name, "no 'modal'"))
    return bad


def d119_texts() -> dict:
    import inspect
    b = mu._row_u_ownership_block(q_world())
    texts = {"description": mu.OWNERSHIP_DESCRIPTION_D119, "pick": mu.OWNERSHIP_PICK_D117,
             "how_read": mu.OWNERSHIP_HOW_READ_D117, "spec_pick": mu.OWNERSHIP_SPECIFICATION_D117["pick"],
             "statement": mu.PANEL_ENTITY_TYPE_STATEMENT, "block_pick": b["pick"],
             "block_statement": b["what_the_panel_column_is"],
             "doc_last_nonmissing": inspect.getdoc(mu.last_nonmissing_entity_type),
             "doc_adopted": inspect.getdoc(mu.adopted_row_u_ownership_classes)}
    src = inspect.getsource(mu.main)
    texts["main_ownership_classes_used_here"] = src.split('"ownership_classes_used_here": (')[1].split("Row M")[0]
    sf = inspect.getsource(mu._short_form_for_row_u)
    texts["main_row_u_frame"] = sf.split('"row_u_quantity_sample_in_the_window": {')[1].split("NOT the paper's")[0]
    return texts


def test_d119_his_words_are_carried_verbatim():
    assert mu.OWNERSHIP_RULING_D119_WORDS == D119_WORDS
    assert mu.OWNERSHIP_RULED_D119 == "Joe, 2026-11-20 (D-119)"
    assert D119_WORDS in mu.PANEL_ENTITY_TYPE_STATEMENT and "D-119" in mu.PANEL_ENTITY_TYPE_STATEMENT
    assert "no further raw-data investigation is made" in mu.PANEL_ENTITY_TYPE_STATEMENT
    d = mu.OWNERSHIP_DESCRIPTION_D119
    assert "utility-level modal reported type carried across the panel" in d
    assert d.endswith("not the latest year-by-year EIA classification")
    assert mu.OWNERSHIP_HOW_READ_D117.startswith("read as the last nonmissing value") and "(D-117)" in \
        mu.OWNERSHIP_HOW_READ_D117
    assert mu.OWNERSHIP_SPECIFICATION_D117["pick"].startswith(mu.OWNERSHIP_PICK_D117)
    assert "D-119" in mu.OWNERSHIP_SPECIFICATION_D117["settled"]
    assert "D-119" in mu.__doc__ and "OWNERSHIP_DESCRIPTION_D119" in mu.__doc__


def test_d119_no_text_of_row_u_reads_as_latest_or_open():
    assert d119_text_problems(d119_texts()) == []


def test_d119_the_text_checks_can_fail(monkeypatch):
    """Break: each text put back to its D-117 wording in the test process; the checks then fail."""
    old_pick = "last nonmissing reported entity type"
    old_statement = ("The panel's entity_type column is not a year-by-year report. Whether the last type EIA reports "
                     "year by year in its own table would differ for some utility is NOT established.")
    assert d119_text_problems({"pick": old_pick}) == [("pick", "last nonmissing reported"), ("pick", "no 'modal'")]
    assert d119_text_problems({"x": "the latest type EIA reported"})[0] == ("x", "latest")
    assert d119_text_problems({"x": "the utility-level modal type; the pick is open"}) == [("x", "pick is open")]
    monkeypatch.setattr(mu, "OWNERSHIP_PICK_D117", old_pick)
    assert ("pick", "no 'modal'") in d119_text_problems(d119_texts())
    monkeypatch.setattr(mu, "PANEL_ENTITY_TYPE_STATEMENT", old_statement)
    with pytest.raises(AssertionError):
        test_d119_his_words_are_carried_verbatim()
    monkeypatch.setattr(mu, "OWNERSHIP_RULING_D119_WORDS", D119_WORDS.replace("modal", "latest"))
    with pytest.raises(AssertionError):
        test_d119_his_words_are_carried_verbatim()
