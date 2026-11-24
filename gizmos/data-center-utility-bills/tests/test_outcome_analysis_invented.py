"""The estimation kernel (pipeline/analysis/outcome_analysis.py) on invented quantities and invented outcomes only.

The core test: on the same design and the same outcome, `estimate` returns the same estimate, 90% range and early-years
p-value as the path step E used (inference_comparison.build_context and run_candidates for candidate C) and the path the
simulation uses (power_simulation.c_reading), to 1e-10. The rest: a planted effect comes back, a rank-deficient design
fails in words before any fit, a numerical failure leaves a descriptive point estimate and nothing else, a host with no
weight is named and not counted, the outcome helper stops in words, the trend arithmetic by hand, the sentences chosen
by the plan's rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import design  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import inference_comparison as icmp  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
STATES = ["AA", "AB", "AC", "AD", "BA", "BB", "BC", "BD"]
FUEL = {s: i % 2 for i, s in enumerate(STATES)}
GAS = {s: g for s, g in zip(STATES, (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75))}
COOP, IOU, PUB = "cooperative", "investor_owned", "public"
HDD_BETA = 0.02
# Hosts: (id, state, residential customers, ownership, cohort). Comparison utilities: (id, state, customers, ownership).
HOSTS = [(1, "AA", 10_000, IOU, 2013), (2, "AC", 12_000, COOP, 2015), (3, "BA", 11_000, PUB, 2015), (4, "BC", 9_000, IOU, 2017)]
COMPS = [(100 + i, STATES[i % 8], 9_000 + 150 * i, (COOP, IOU, PUB)[i % 3]) for i in range(40)]


def world(hosts=HOSTS, comps=COMPS, region=None, seed=3):
    """Invented quantities in the form design.build takes. `region(key, year)` gives a unit's market region (default West)."""
    units = [h[:4] for h in hosts] + list(comps)
    region = region or (lambda key, year: "West")
    q = pd.DataFrame([(u, st, y, own, size, 1.0, True) for u, st, size, own in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    regions = pd.DataFrame([(u, st, y, region((u, st), y)) for u, st, _, _ in units for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(seed)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in STATES for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    treated = pd.DataFrame({"utility_id_eia": [h[0] for h in hosts], "state": [h[1] for h in hosts], "cohort": [h[4] for h in hosts]})
    clean = pd.DataFrame([(u, st) for u, st, *_ in comps], columns=KEY)
    return treated, clean, q, regions, dd


def make(hosts=HOSTS, comps=COMPS, region=None, k=ps.MATCH_K):
    treated, clean, q, regions, dd = world(hosts, comps, region)
    d = design.build(treated, clean, q, regions, FUEL, dd, k)
    d.gas = GAS
    return d, q, regions, dd


def path(e: int, effect: dict) -> float:
    """The planted host path at event time e: zero through event year -1, then `effect` by event year, 3 onward held."""
    return effect.get(min(e, 3), 0.0) if e >= 0 else 0.0


PLANTED = {0: 0.01, 1: 0.03, 2: 0.05, 3: 0.05}           # headline (mean of event years 2 and 3) = 0.05


def outcomes(hosts=HOSTS, comps=COMPS, dd=None, noise=0.0, effect=PLANTED, drift=0.0, seed=7, state_sd=0.0) -> pd.DataFrame:
    """Invented log prices: unit effect + calendar-year effect + 0.02 * heating degree days + a state shock + noise, plus the
    planted path (and a drift of `drift` a year from the reference year) on hosts. Keyed by utility_id_eia, state, year."""
    rng = np.random.default_rng(seed)
    year_fx = dict(zip(YEARS, rng.normal(0, 0.05, len(YEARS))))
    state_fx = {(s, y): rng.normal(0, state_sd) for s in STATES for y in YEARS}
    cohort = {(h[0], h[1]): h[4] for h in hosts}
    rows = []
    for u, st, *_ in [h[:4] for h in hosts] + list(comps):
        a = rng.normal(0, 0.2)
        for y in YEARS:
            v = a + year_fx[y] + HDD_BETA * float(dd.hdd[(st, y)]) + state_fx[(st, y)] + noise * rng.normal()
            g = cohort.get((u, st))
            if g is not None:
                e = y - g
                v += path(e, effect) + drift * (e - ps.REF)
            rows.append((u, st, y, v))
    return pd.DataFrame(rows, columns=KEY + ["year", "log_price"])


# ---- the rows and the outcome vector ---------------------------------------------------------------------------------

def test_stacked_rows_are_the_rows_assemble_stacks():
    d, *_ = make()
    rows = oa.stacked_rows(d)
    f = ic.fixed_parts(d)
    assert len(rows) == len(f["X"])
    codes = np.array([d.unit_code[(u, s)] for u, s in zip(rows.utility_id_eia, rows.state)])
    assert np.array_equal(codes, f["obs_unit"])
    assert np.array_equal(rows.year.to_numpy() - ic.FIRST_YEAR, f["obs_year"])
    # the event-time columns are on the host rows at their event years, and nowhere else
    for i, e in enumerate(ps.EVENT_TIMES):
        assert np.array_equal(f["X"][:, i] == 1, (rows.is_host & (rows.event_year == e)).to_numpy())


def test_outcome_vector_stops_in_words_and_never_fills():
    d, q, regions, dd = make()
    frame = outcomes(dd=dd)
    y = oa.outcome_vector(d, frame, "log_price")
    assert np.isfinite(y).all() and len(y) == len(oa.stacked_rows(d))
    # a missing unit-year
    gone = frame[~((frame.utility_id_eia == 1) & (frame.year == 2010))]
    with pytest.raises(oa.OutcomeMisaligned, match=r"lacks 1 unit-years the design needs, for example \['1:AA in 2010'\]"):
        oa.outcome_vector(d, gone, "log_price")
    # a missing value
    holed = frame.copy()
    holed.loc[(holed.utility_id_eia == 1) & (holed.year == 2010), "log_price"] = np.nan
    with pytest.raises(oa.OutcomeMisaligned, match="missing or not finite for 1 unit-years"):
        oa.outcome_vector(d, holed, "log_price")
    # a repeated key
    with pytest.raises(oa.OutcomeMisaligned, match="repeats a unit-year"):
        oa.outcome_vector(d, pd.concat([frame, frame.iloc[:1]]), "log_price")
    with pytest.raises(oa.OutcomeMisaligned, match="no column"):
        oa.outcome_vector(d, frame, "res_price")
    with pytest.raises(oa.OutcomeMisaligned, match="stacked rows"):
        oa.estimate(d, y[:-1], validated_design=False)


# ---- the core: the same computation as step E -------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [11, 12, 13])
def test_estimate_equals_step_e_path_and_the_simulation_path_to_1e_10(seed):
    """Step E drew a units-by-years matrix P and read y = P[obs_unit, obs_year] (inference_comparison.dataset); the
    candidate C it validated is ctx["candidates"]["C"].run. The same P, written as a long frame, goes through
    outcome_vector and estimate here."""
    d, q, regions, dd = make()
    built = icmp.build_context(d, regions, q, None, None, "invented: no ownership or suppliers", names=("C",))
    ctx = built["ctx"]
    rng = np.random.default_rng(seed)
    keys = list(d.unit_code)
    P = rng.normal(0, 0.2, len(keys))[:, None] + rng.normal(0, 0.05, (len(keys), len(YEARS))) + rng.normal(0, 0.03, len(YEARS))[None, :]
    y_step_e = P[ctx["obs_unit"], ctx["obs_year"]]
    frame = pd.DataFrame([(k[0], k[1], ic.FIRST_YEAR + t, P[d.unit_code[k], t]) for k in keys for t in range(len(YEARS))],
                         columns=KEY + ["year", "log_price"])
    y = oa.outcome_vector(d, frame, "log_price")
    assert np.array_equal(y, y_step_e)                                    # aligned row for row

    r = oa.estimate(d, y, validated_design=False)
    e = icmp.run_candidates(y_step_e, None, ctx, names=("C",))["C"]       # C draws nothing: the bootstrap seed is unused
    assert e["failure"] is None and r["numerical_failure"] is None
    assert abs(r["headline"]["log_points"] - e["estimate"]) < 1e-10
    assert abs(r["headline"]["range_90_log_points"][0] - e["lo"]) < 1e-10
    assert abs(r["headline"]["range_90_log_points"][1] - e["hi"]) < 1e-10
    assert r["early_years_test"]["fails_at_p_below_0.10"] == e["early_rejected"]

    cand = ctx["candidates"]["C"]
    s = ps.c_reading(cand, *cand.fit(y_step_e))
    assert abs(r["early_years_test"]["p_value"] - s["pre_p"]) < 1e-10
    assert abs(r["early_years_test"]["Q"] - s["pre_wald"]) < 1e-10
    assert abs(r["headline"]["standard_error_log_points"] - s["se"]) < 1e-10
    assert abs(r["headline"]["degrees_of_freedom"] - cand.nu) < 1e-10
    assert r["clusters"] == ctx["problem"].G == len({h[1] for h in HOSTS} | {c[1] for c in COMPS})


# ---- planted effects ----------------------------------------------------------------------------------------------

def test_a_planted_path_comes_back_exactly_with_no_noise():
    d, q, regions, dd = make()
    r = oa.estimate(d, oa.outcome_vector(d, outcomes(dd=dd, noise=0.0), "log_price"), validated_design=False)
    c = r["event_year_coefficients"]
    assert list(c) == [str(e) for e in range(-6, 4)] and c["-3"] == 0.0
    for e in range(-6, 4):
        assert abs(c[str(e)] - path(e, PLANTED)) < 1e-10                # tolerance 1e-10: noise is zero
    assert abs(r["headline"]["log_points"] - 0.05) < 1e-10
    assert abs(r["headline"]["percent"] - 100 * np.expm1(0.05)) < 1e-8


def test_a_planted_path_comes_back_within_tolerance_with_small_noise():
    d, q, regions, dd = make()
    r = oa.estimate(d, oa.outcome_vector(d, outcomes(dd=dd, noise=0.002, state_sd=0.002), "log_price"), validated_design=False)
    assert r["numerical_failure"] is None
    assert abs(r["headline"]["log_points"] - 0.05) < 0.005             # stated tolerance: half a point of price, noise sd 0.2%
    lo, hi = r["headline"]["range_90_log_points"]
    assert lo < r["headline"]["log_points"] < hi
    assert r["headline"]["status"].startswith("estimate with its 90% range")
    assert r["count_N"] == 4 and r["hosts_with_zero_weight"] == [] and r["hosts_fully_absorbed"] == []
    assert abs(sum(r["host_headline_weights"].values()) - 1.0) < 1e-10


def test_a_linear_drift_from_the_reference_year_moves_the_headline_by_exactly_5_5_d():
    """The reading coded in trend_illustrations: a drift of d a year on host rows from the reference year moves the
    headline by 5.5 * d exactly in the fit (it is in the span of the event-time columns)."""
    d, q, regions, dd = make()
    base = oa.estimate(d, oa.outcome_vector(d, outcomes(dd=dd, noise=0.01), "log_price"), validated_design=False)
    for drift in (0.005, 0.01, -0.01):
        moved = oa.estimate(d, oa.outcome_vector(d, outcomes(dd=dd, noise=0.01, drift=drift), "log_price"), validated_design=False)
        assert abs(moved["headline"]["log_points"] - base["headline"]["log_points"] - 5.5 * drift) < 1e-10


# ---- failures ---------------------------------------------------------------------------------------------------

ONE_STATE_HOSTS = [(1, "AA", 10_000, IOU, 2013), (2, "AA", 12_000, COOP, 2015)]
ONE_STATE_COMPS = [(100 + i, "AA", 9_000 + 150 * i, COOP) for i in range(24)]


def test_a_rank_deficient_design_fails_in_words_before_any_fit(monkeypatch):
    """Every unit in one state: the degree days vary by year only, so the block-by-region-by-year effects absorb them.
    assemble keeps the degree-day columns so that the fit's own rank test fails in words (screen_controls)."""
    d, q, regions, dd = make(hosts=ONE_STATE_HOSTS, comps=ONE_STATE_COMPS)
    y = oa.outcome_vector(d, outcomes(hosts=ONE_STATE_HOSTS, comps=ONE_STATE_COMPS, dd=dd, noise=0.01), "log_price")
    # nothing is inverted before the rank test fails: any call to an inverse is a failure of this test
    from pipeline.analysis import candidates as cd
    calls = []
    real_inv = np.linalg.inv
    monkeypatch.setattr(cd.np.linalg, "inv", lambda *a, **k: calls.append(1) or real_inv(*a, **k))
    r = oa.estimate(d, y, validated_design=False)
    monkeypatch.setattr(cd.np.linalg, "inv", real_inv)
    assert calls == []
    f = r["numerical_failure"]
    assert f["cause"] == "rank_deficient" and "rank test" in f["in_words"] and "not identified" in f["detail"]
    assert r["event_year_coefficients"] is None and r["headline"]["status"] == oa.NOT_COMPUTED
    assert r["headline"]["range_90_log_points"] is None and r["early_years_test"]["p_value"] is None
    assert r["count_N"] is None and r["host_headline_weights"] is None
    assert oa.trend_illustrations(r)["computed"] is False
    assert "could not be computed" in oa.early_years_reading(r, True)[0]


def test_a_design_where_no_host_has_a_match_fails_in_words():
    d, q, regions, dd = make(hosts=[HOSTS[0]], k=0)
    assert len(oa.stacked_rows(d)) == 0
    r = oa.estimate(d, np.zeros(0), validated_design=False)
    assert r["numerical_failure"]["cause"] == "rank_deficient" and "no host" in r["numerical_failure"]["detail"]
    assert r["hosts_with_no_matches"] == ["1:AA"] and r["count_N"] is None


def test_a_numerical_failure_leaves_a_descriptive_point_estimate_and_no_range_or_test():
    """An outcome identically zero: the residuals are exactly zero, so the CR2 standard error is zero."""
    d, *_ = make()
    r = oa.estimate(d, np.zeros(len(oa.stacked_rows(d))), validated_design=False)
    assert r["numerical_failure"]["cause"] == "non_finite_or_zero_standard_error"
    assert r["headline"]["status"] == oa.DESCRIPTIVE
    assert r["headline"]["log_points"] == 0.0
    assert r["headline"]["range_90_log_points"] is None and r["headline"]["range_90_percent"] is None
    assert r["early_years_test"]["p_value"] is None and r["early_years_test"]["fails_at_p_below_0.10"] is None
    assert r["event_year_coefficients"] is not None


def test_a_host_with_no_comparison_utilities_is_named_not_stacked_and_not_counted():
    """Host 4 is alone in its region, so it has no matches: it is named, not stacked, and not counted; N is 3."""
    region = lambda key, year: "East" if key == (4, "BC") else "West"   # noqa: E731
    d, q, regions, dd = make(region=region)
    assert 4 not in set(oa.stacked_rows(d).block_host_id)
    r = oa.estimate(d, oa.outcome_vector(d, outcomes(dd=dd, noise=0.01), "log_price"), validated_design=False)
    assert r["numerical_failure"] is None
    assert r["hosts_with_no_matches"] == ["4:BC"] and r["count_N"] == 3 and len(r["hosts_in_the_design"]) == 4


def test_a_host_whose_rows_are_absorbed_is_named_has_zero_weight_and_is_not_counted():
    """Host 4 is in its matches' region only in its reference year (2014) and alone in another region in every other year,
    so its block-by-region-by-year effects take its rows: it is absorbed, its weight is zero, and N is 3."""
    region = lambda key, year: "East" if key == (4, "BC") and year != 2014 else "West"   # noqa: E731
    d, q, regions, dd = make(region=region)
    assert len(d.hosts.matches.iloc[3]) == ps.MATCH_K
    r = oa.estimate(d, oa.outcome_vector(d, outcomes(dd=dd, noise=0.01), "log_price"), validated_design=False)
    assert r["numerical_failure"] is None
    assert r["hosts_fully_absorbed"] == ["4:BC"] and r["hosts_with_zero_weight"] == ["4:BC"]
    assert abs(r["host_headline_weights"]["4:BC"]) < 1e-9
    assert r["count_N"] == 3


# ---- the trend illustrations by hand -------------------------------------------------------------------------------

def fake_result(early: tuple, fails=False, status="estimate with its 90% range under the selected procedure"):
    coefs = {str(e): 0.0 for e in range(-6, 4)}
    coefs["-6"], coefs["-5"], coefs["-4"] = early
    return {"event_year_coefficients": coefs, "headline": {"status": status},
            "early_years_test": {"fails_at_p_below_0.10": fails}, "numerical_failure": None}


def test_trend_arithmetic_by_hand():
    # steps: -6 to -5 = -0.03, -5 to -4 = +0.025, -4 to the reference year = -0.005; m = 0.03 from -6 to -5
    t = oa.trend_illustrations(fake_result((0.01, -0.02, 0.005)))
    assert t["computed"] and t["count"] == 6 and not t["crossed"] and len(t["illustrations"]) == 6
    assert abs(t["m_log_points"] - 0.03) < 1e-15 and t["m_from"] == "-6 to -5"
    pts = {i["name"]: i["points"] for i in t["illustrations"]}
    assert abs(pts["half_of_the_largest_early_change"] - 8.25) < 1e-12      # 5.5 * 0.03 / 2 * 100
    assert abs(pts["all_of_the_largest_early_change"] - 16.5) < 1e-12       # 5.5 * 0.03 * 100
    assert pts["fixed_away_0.5pct_a_year"] == pytest.approx(2.75, abs=1e-12)
    assert pts["fixed_toward_0.5pct_a_year"] == pytest.approx(-2.75, abs=1e-12)
    assert pts["fixed_away_1pct_a_year"] == pytest.approx(5.5, abs=1e-12)
    assert pts["fixed_toward_1pct_a_year"] == pytest.approx(-5.5, abs=1e-12)
    half = t["illustrations"][0]["sentences"]
    assert half[0] == ("If hosts had been drifting away from the comparison utilities by half the largest year-to-year change we "
                       "estimated in the early years, the estimate would move by 8.25 points.")
    assert half[1] == oa.IGNORES_UNCERTAINTY and t["illustrations"][1]["sentences"][1] == oa.IGNORES_UNCERTAINTY
    assert t["qualifications"] == list(oa.QUALIFICATIONS)


def test_the_step_to_the_reference_year_counts():
    # steps: -0.01, -0.01, +0.02: the largest is from -4 to the reference year, whose coefficient is zero
    t = oa.trend_illustrations(fake_result((0.0, -0.01, -0.02)))
    assert t["m_from"] == "-4 to the reference year" and abs(t["m_log_points"] - 0.02) < 1e-15


def test_illustrations_on_a_descriptive_estimate_say_so():
    t = oa.trend_illustrations(fake_result((0.0, 0.01, 0.0), status=oa.DESCRIPTIVE))
    assert t["computed"] and t["coefficients_are"] == oa.DESCRIPTIVE


# ---- the early-years sentences ----------------------------------------------------------------------------------------

def test_the_sentences_follow_the_plans_rule():
    assert oa.early_years_reading(fake_result((0, 0, 0), fails=False), False) == [
        "The test did not detect a difference in the years before."]
    assert oa.early_years_reading(fake_result((0, 0, 0), fails=False), True) == [
        "The test did not detect a difference in the years before.", "On a set this small it would miss a large one."]
    fails = ["Prices at hosts were already moving differently before the data centers arrived, so the estimate may reflect that trend."]
    assert oa.early_years_reading(fake_result((0, 0, 0), fails=True), True) == fails
    assert oa.early_years_reading(fake_result((0, 0, 0), fails=True), False) == fails
    with pytest.raises(TypeError):
        oa.early_years_reading(fake_result((0, 0, 0)), None)


# ---- windows of any length: the ten-year equality and the longer horizon ------------------------------------------------

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import side_runs  # noqa: E402


def compare(a: dict, b: dict, tol: float = 1e-10):
    """Every number the two results share, to `tol`; every list and label exactly."""
    for k in ("log_points", "percent", "standard_error_log_points", "degrees_of_freedom"):
        assert abs(a["headline"][k] - b["headline"][k]) < tol, k
    for i in range(2):
        assert abs(a["headline"]["range_90_log_points"][i] - b["headline"]["range_90_log_points"][i]) < tol
    for k in ("Q", "F", "p_value", "denominator_degrees_of_freedom"):
        assert abs(a["early_years_test"][k] - b["early_years_test"][k]) < tol, k
    assert a["early_years_test"]["fails_at_p_below_0.10"] == b["early_years_test"]["fails_at_p_below_0.10"]
    assert a["event_year_coefficients"].keys() == b["event_year_coefficients"].keys()
    for e in a["event_year_coefficients"]:
        assert abs(a["event_year_coefficients"][e] - b["event_year_coefficients"][e]) < tol
    for h in a["host_headline_weights"]:
        assert abs(a["host_headline_weights"][h] - b["host_headline_weights"][h]) < tol
    for k in ("count_N", "clusters", "rows", "regressors", "columns", "control_columns_left_out", "hosts_fully_absorbed",
              "hosts_with_zero_weight", "hosts_with_no_matches", "numerical_failure"):
        assert a[k] == b[k], k


@pytest.mark.parametrize("region", [None, lambda key, year: "East" if key == (4, "BC") and year != 2014 else "West"])
def test_estimate_span_at_six_and_three_is_estimate_to_1e_10(region):
    """The span-general stacking and reading at pre = 6, post = 3, headline (2, 3) on the same design and outcome: the
    second case has an absorbed host with zero weight."""
    d, q, regions, dd = make(region=region)
    y = oa.outcome_vector(d, outcomes(dd=dd, noise=0.02, state_sd=0.01), "log_price")
    ds = oa.stackable(d)
    r10 = oa.estimate(d, y, validated_design=False)
    rs = oa.estimate_span(ds.windows, ds.blocks(), y, 6, 3, (2, 3), gas=GAS)
    compare(rs, r10)
    a = oa.assemble_span(ds.windows, ds.blocks(), 6, 3, gas=GAS)
    f = ic.fixed_parts(ds)
    assert np.array_equal(a["X"], f["X"]) and np.array_equal(a["cluster"], f["cluster"])
    assert all(np.array_equal(x, z) for x, z in zip(a["groups"], f["groups"]))
    # neither claims validation here: estimate_span never can (session 19), and estimate was passed False
    assert rs["validation"] == r10["validation"] == oa.NOT_VALIDATED


LONG_EFFECT = {0: 0.01, 1: 0.03, 2: 0.05, 3: 0.05, 4: 0.06, 5: 0.07, 6: 0.08}     # mean of event years 4 to 6 = 0.07


def long_world(noise=0.0):
    """The invented design, its thirteen-year windows (side_runs.build_windows_span, g - 6 to g + 6) with the same hosts
    and matches, and an outcome frame with LONG_EFFECT planted on hosts."""
    d, q, regions, dd = make()
    keys = list(d.unit_code)
    template = pd.DataFrame([(k[0], k[1], y, 0.0) for k in keys for y in YEARS], columns=KEY + ["year", "log_price"])
    cohorts = sorted(int(g) for g in d.hosts.cohort.unique())
    w13 = side_runs.build_windows_span(cohorts, template, q, regions, FUEL, dd, d.unit_code, d.state_code, 6, 6)
    blocks13 = []
    for h in d.hosts.itertuples():
        idx = {tuple(k): i for i, k in enumerate(w13[int(h.cohort)].keys)}
        blocks13.append((int(h.cohort), np.array([idx[tuple(h.key)]]), np.array([idx[tuple(m)] for m in h.match_keys], dtype=int)))
    frame = outcomes(dd=dd, noise=noise, effect={}, state_sd=noise)
    cohort = {(h[0], h[1]): h[4] for h in HOSTS}
    add = [LONG_EFFECT.get(min(y - cohort[(u, s)], 6), 0.0) if (u, s) in cohort and y >= cohort[(u, s)] else 0.0
           for u, s, y in zip(frame.utility_id_eia, frame.state, frame.year)]
    frame["log_price"] = frame.log_price + np.array(add)
    return side_runs.LongHorizon(d, w13, blocks13, {}), frame


@pytest.mark.parametrize("noise,tol", [(0.0, 1e-10), (0.002, 0.006)])
def test_the_longer_horizon_recovers_event_years_4_to_6_and_the_three_year_number_beside_it(noise, tol):
    """Tolerance 1e-10 with no noise; 0.006 (0.6 points) with noise sd 0.2% per unit-year and state-year."""
    lh, frame = long_world(noise)
    y13 = oa.outcome_vector_span(lh.windows13, lh.blocks13, 6, 6, frame, "log_price")
    y10 = oa.outcome_vector(lh.design, frame, "log_price")
    r = oa.estimate_long_horizon(lh, y13, y10)
    six, three = r["six_years"], r["three_years_same_utilities"]
    assert list(six["event_year_coefficients"]) == [str(e) for e in range(-6, 7)]
    assert six["headline"]["event_years"] == [4, 5, 6] and six["early_years_test"]["event_years"] == [-6, -5, -4]
    assert abs(six["headline"]["log_points"] - 0.07) < tol
    assert abs(three["headline"]["log_points"] - 0.05) < tol
    assert six["validation"] == three["validation"] == r["validation"] == oa.NOT_VALIDATED
    assert oa.NOT_VALIDATED == "under the procedure validated on the headline set; no validation was made on this design"
    assert sorted(three["hosts_in_the_design"]) == sorted(six["hosts_in_the_design"])
    if noise:
        assert six["numerical_failure"] is None and six["headline"]["range_90_log_points"] is not None
        assert six["early_years_test"]["p_value"] is not None and six["count_N"] == 4
    else:
        for e in range(0, 7):
            assert abs(six["event_year_coefficients"][str(e)] - LONG_EFFECT[e]) < 1e-10


# ---- controls the fixed effects absorb exactly (the own-state side run) ------------------------------------------------

def own_state_world():
    """Each unit's region is its state, so every host's matches are in its state and the state-level controls (degree
    days, gas share by year) are constant within each matched set's year."""
    d, q, regions, dd = make(region=lambda key, year: key[1])
    assert all(m[1] == h[1] for h, ms in zip(d.hosts.key, d.hosts.match_keys) for m in ms)
    return d, dd


def test_with_the_option_off_the_own_state_design_fails_its_rank_test_in_words():
    d, dd = own_state_world()
    r = oa.estimate(d, oa.outcome_vector(d, outcomes(dd=dd, noise=0.01), "log_price"), validated_design=False)
    assert r["numerical_failure"]["cause"] == "rank_deficient" and r["controls_left_out_as_exactly_absorbed"] == []


def test_with_the_option_on_the_absorbed_controls_are_named_and_the_fit_is_the_fit_with_no_controls():
    d, dd = own_state_world()
    y = oa.outcome_vector(d, outcomes(dd=dd, noise=0.01, state_sd=0.01), "log_price")
    r = oa.estimate(d, y, absorbed_controls=oa.LEAVE_OUT_IF_EXACTLY_ABSORBED, validated_design=False)
    assert r["numerical_failure"] is None
    gone = [c["column"] for c in r["controls_left_out_as_exactly_absorbed"]]
    assert gone == ["heating_degree_days", "cooling_degree_days"]           # the gas columns were already screened out
    assert all(c["relative_norm_after_projection"] <= 1e-10 for c in r["controls_left_out_as_exactly_absorbed"])
    assert r["columns"] == [f"event_year_{e}" for e in ps.EVENT_TIMES]
    # the fit with no controls, built by power_simulation.assemble(controls=False) and read by candidate C directly
    ds = oa.stackable(d)
    for w in ds.windows.values():
        w.y = np.zeros((len(w.keys), ps.T))
    a = ps.assemble(ds.windows, ds.blocks(), controls=False)
    cand = cd.CandidateC(cd.Problem(a["X"], a["groups"], a["cluster"], combo=ps.headline_combo(a["X"].shape[1])))
    s = ps.c_reading(cand, *cand.fit(y))
    assert abs(r["headline"]["log_points"] - s["est"]) < 1e-10
    assert abs(r["headline"]["range_90_log_points"][0] - s["lo"]) < 1e-10 and abs(r["headline"]["range_90_log_points"][1] - s["hi"]) < 1e-10
    assert abs(r["early_years_test"]["p_value"] - s["pre_p"]) < 1e-10
    with pytest.raises(ValueError, match="unknown absorbed_controls option"):
        oa.estimate(d, y, absorbed_controls="drop_whatever_fails", validated_design=False)


def test_on_the_ordinary_design_the_option_changes_nothing():
    d, q, regions, dd = make()
    y = oa.outcome_vector(d, outcomes(dd=dd, noise=0.02, state_sd=0.01), "log_price")
    off, on = oa.estimate(d, y, validated_design=False), oa.estimate(d, y, absorbed_controls=oa.LEAVE_OUT_IF_EXACTLY_ABSORBED, validated_design=False)
    assert on["controls_left_out_as_exactly_absorbed"] == []
    compare(on, off, tol=0.0 + 1e-15)
