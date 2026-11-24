"""Callaway and Sant'Anna's run (pipeline/analysis/callaway_santanna.py): the sample's restrictions, the frame's
observation rule, the reference computation with a planted answer, the pinned call, and its refusals. Invented inputs
only; nothing under data/ is read.

Tolerances, stated:
  reference computation, planted effect recovered with the gas share      1e-8 (exact arithmetic on a noise-free panel)
  reference computation, the bias without the gas share against its formula 1e-10
  package against the planted effect and against the reference            1e-6 for the point estimate
The two package tests are skipped while diff-diff 4.0.0 is not installed (it may not be installed on this machine).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import callaway_santanna as cs  # noqa: E402
from pipeline.analysis import ownership  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
IOU, COOP, PUBLIC = "investor_owned", "cooperative", "public"
TOL_RECOVER = 1e-8
TOL_FORMULA = 1e-10
TOL_PACKAGE = 1e-6
SKIP_REASON = "diff-diff 4.0.0 is not installed"


# ---- an invented world for the sample ---------------------------------------------------------------------------------

H1, H2, H3 = (100, "AA"), (200, "BB"), (300, "AA")             # H3 lacks a full usable window
EARLY, LATE = (400, "AA"), (500, "AA")
C_OK = [(1000 + i, "AA") for i in range(3)]
C_LOAD, C_CRYPTO, C_ASIDE, C_UNKNOWN = (2001, "AA"), (2002, "AA"), (2003, "AA"), (2004, "AA")
C_FLOOR, C_HOLD, C_INPUTS, C_OWN = (2005, "AA"), (2006, "AA"), (2007, "AK"), (100, "BB")
C_AFF, C_AFF_OUTSIDE, C_NOROW, C_ASSUMED, C_IOUROW = (2008, "AA"), (2009, "AA"), (2010, "AA"), (2011, "AA"), (2012, "AA")
C_GAP = (2013, "AA")                                             # usable except in 2013

CLASS = {H1: IOU, H2: PUBLIC, H3: COOP, EARLY: COOP, LATE: COOP, C_LOAD: COOP, C_CRYPTO: COOP, C_ASIDE: COOP,
         C_UNKNOWN: COOP, C_FLOOR: COOP, C_HOLD: COOP, C_INPUTS: COOP, C_OWN: IOU, C_AFF: IOU, C_AFF_OUTSIDE: IOU,
         C_NOROW: IOU, C_ASSUMED: IOU, C_IOUROW: IOU, C_GAP: COOP, **{c: COOP for c in C_OK}}
COHORT = {H1: 2015, H2: 2018, H3: 2016}


def own_table(rows):
    base = {"name": "x", "how_it_changed": "", "source_url": "https://example.org/filing", "source_kind": "sec_filing",
            "quote": "a quoted line", "date_opened": "2026-11-19", "from_year_basis": "documented", "to_year_basis": "documented"}
    t = pd.DataFrame([{**base, **r} for r in rows], columns=ownership.COLUMNS + list(ownership.BASIS))
    return t.astype({"utility_id_eia": int, "from_year": int, "to_year": int})


TABLE = own_table([
    {"utility_id_eia": 100, "state": "AA", "ultimate_parent": "P1", "from_year": 2001, "to_year": 2025},
    {"utility_id_eia": C_AFF[0], "state": "AA", "ultimate_parent": "P1", "from_year": 2001, "to_year": 2025},
    {"utility_id_eia": C_AFF_OUTSIDE[0], "state": "AA", "ultimate_parent": "P1", "from_year": 2001, "to_year": 2006},
    {"utility_id_eia": C_AFF_OUTSIDE[0], "state": "AA", "ultimate_parent": "P7", "from_year": 2007, "to_year": 2025},
    {"utility_id_eia": C_ASSUMED[0], "state": "AA", "ultimate_parent": "P1", "from_year": 2001, "to_year": 2025,
     "from_year_basis": "assumed", "to_year_basis": "assumed"},
    {"utility_id_eia": C_IOUROW[0], "state": "AA", "ultimate_parent": "P9", "from_year": 2001, "to_year": 2025},
    {"utility_id_eia": C_OWN[0], "state": "BB", "ultimate_parent": "P1", "from_year": 2001, "to_year": 2025},
])


def world(classes=None):
    classes = {**CLASS, **(classes or {})}
    units = list(classes)
    q = pd.DataFrame([(u, st, y, classes[(u, st)], 50_000, 1.0, (u, st) != C_FLOOR, f"utility {u} {st}")
                      for (u, st) in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor", "utility_name"])
    first = {H1: 2015, H2: 2018, H3: 2016, EARLY: 2008, LATE: 2024}
    rows = []
    for k, g in first.items():
        rows += [(k[0], k[1], y, 0.03 if y >= g else 0.0, 0.0, 1000.0) for y in YEARS]
    rows += [(C_LOAD[0], C_LOAD[1], y, 0.006 if y == 2020 else 0.0, 0.0, 1000.0) for y in YEARS]
    rows += [(C_CRYPTO[0], C_CRYPTO[1], y, 0.0, 3.0 if y == 2021 else 0.0, 1000.0) for y in YEARS]   # 3 MW: 2.6% of 1,000 GWh
    dose = pd.DataFrame(rows, columns=KEY + ["year", "dose", "crypto_mw", "base_retail_gwh"])
    usable = {(u, st, y) for (u, st) in units for y in YEARS if (u, st) != C_FLOOR}
    usable -= {(H3[0], H3[1], 2013)}
    usable -= {(C_GAP[0], C_GAP[1], 2013)}
    return q, dose, usable


def unknown(affected=(C_UNKNOWN,)):
    return ps.UnknownLoad(frozenset(affected), {"2%": frozenset()}, "invented", 1)


def build(classes=None, table=TABLE, **kw):
    q, dose, usable = world(classes)
    args = dict(host_aside=set(), comparison_aside={C_ASIDE}, hold={C_HOLD}, unknown_load=unknown(), ownership=table,
                ownership_of=ps.ownership_classes(q), usable=usable, gas={"AA": 0.3, "BB": 0.5, "AK": 0.1},
                dd_states={"AA", "BB"}, names=q.groupby(KEY).utility_name.last())
    args.update(kw)
    return cs.sample(0.02, "invented", q, dose, **args), q, usable


def nt(s):
    return {(int(u), st) for u, st in zip(s.never_treated.utility_id_eia, s.never_treated.state)}


HOSTS_FOR_LOAD = {H1, H2, H3, EARLY, LATE}


def test_each_restriction_removes_the_unit_built_to_violate_it_and_no_other():
    s, _, _ = build()
    removed = {st["step"]: s.removed_by(st["step"]) for st in s.steps}
    assert removed[cs.STEP_LOAD] - HOSTS_FOR_LOAD == {C_LOAD, C_CRYPTO}
    assert HOSTS_FOR_LOAD <= removed[cs.STEP_LOAD]                       # every host, early and late ones too, is on neither side
    assert removed[cs.STEP_ASIDE] == {C_ASIDE}
    assert removed[cs.STEP_UNKNOWN] == {C_UNKNOWN}
    assert removed[cs.STEP_FLOOR] == {C_FLOOR}
    assert removed[cs.STEP_HOLD] == {C_HOLD}
    assert removed[cs.STEP_INPUTS] == {C_INPUTS}
    assert removed[cs.STEP_OWN] == {C_OWN}
    assert removed[cs.STEP_OWNERSHIP] == {C_AFF, C_NOROW, C_ASSUMED}
    assert nt(s) == set(C_OK) | {C_AFF_OUTSIDE, C_IOUROW, C_GAP}
    counts = [st["removed"] for st in s.steps]
    assert counts == [len(removed[st["step"]]) for st in s.steps]
    assert s.steps[-1]["remaining"] == len(nt(s))


def test_hosts_early_and_late_hosts_and_a_host_without_a_full_usable_window():
    s, _, _ = build()
    assert {(int(u), st): int(g) for u, st, g in zip(s.hosts.utility_id_eia, s.hosts.state, s.hosts.cohort)} == {H1: 2015, H2: 2018}
    assert s.hosts_neither_side[cs.HOST_EARLY] == ["400:AA"] and s.hosts_neither_side[cs.HOST_LATE] == ["500:AA"]
    assert [d["utility"] for d in s.hosts_dropped] == ["300:AA"] and s.hosts_dropped[0]["why"] == cs.HOST_NOT_USABLE


def test_an_affiliate_of_host_a_is_excluded_though_unaffiliated_with_host_b():
    s, _, _ = build()
    recs = s.ownership_exclusions[C_AFF]
    assert [r["host"] for r in recs] == ["100:AA"] and recs[0]["why"] == ownership.SAME_PARENT
    assert recs[0]["basis"]["label"] == "documented at both ends"
    assert not ownership.affiliated(TABLE, C_AFF, H2, ownership.window_years(2018))     # unaffiliated with host B
    assert C_AFF_OUTSIDE in nt(s)                                                     # shared parent only before H1's window


def test_an_investor_owned_unit_with_no_row_is_excluded_when_any_host_is_investor_owned():
    s, _, _ = build()
    recs = s.ownership_exclusions[C_NOROW]
    assert [r["host"] for r in recs] == ["100:AA"] and recs[0]["why"] == ownership.NO_ROW
    assert "not evidence of independence" in recs[0]["basis"]["label"]


def test_an_investor_owned_unit_with_no_row_is_kept_when_every_host_is_public():
    s, _, _ = build(classes={H1: PUBLIC}, table=TABLE[TABLE.utility_id_eia != 100])
    assert C_NOROW in nt(s) and C_NOROW not in s.ownership_exclusions
    assert s.removed_by(cs.STEP_OWNERSHIP) == set()


def test_an_assumed_spell_excludes_and_is_labelled():
    s, _, _ = build()
    recs = s.ownership_exclusions[C_ASSUMED]
    assert recs[0]["why"] == ownership.SAME_PARENT
    assert recs[0]["basis"]["label"] == "assumed at both ends (ownership convention)"
    assert any(r.get("from_year_basis") == "assumed" for r in recs[0]["basis"]["rows"])
    step = [st for st in s.steps if st["step"] == cs.STEP_OWNERSHIP][0]
    assert step["resting_on_an_assumed_spell"] == ["2011:AA"]


def with_rows(extra):
    return own_table(list(TABLE.to_dict("records")) + extra)


def test_a_unit_with_rows_for_part_of_an_investor_owned_hosts_window_is_removed_and_labelled():
    # H1's window is 2009-2018; a row for 2009-2014 (g-6..g-1) only leaves 2015-2018 unknown
    t = with_rows([{"utility_id_eia": 3000, "state": "AA", "ultimate_parent": "P5", "from_year": 2009, "to_year": 2014}])
    s, _, _ = build(classes={(3000, "AA"): IOU}, table=t)
    assert (3000, "AA") not in nt(s)
    # rule 2.2 read year by year (D-107): ownership.ineligible_for removes it in the ownership step, named apart
    assert (3000, "AA") in s.removed_by(cs.STEP_OWNERSHIP)
    recs = s.unknown_ownership_year_exclusions[(3000, "AA")]
    assert [r["host"] for r in recs] == ["100:AA"] and recs[0]["uncovered_years"] == [2015, 2016, 2017, 2018]
    assert recs[0]["label"] == "unknown ownership in these years is not evidence of independence"
    ex = s.ownership_exclusions[(3000, "AA")]
    assert [x["why"] for x in ex] == [ownership.NO_ROW] and ex[0]["basis"]["uncovered_years"] == [2015, 2016, 2017, 2018]
    step = [st for st in s.steps if st["step"] == cs.STEP_OWNERSHIP][0]
    assert step["removed_only_for_a_row_for_part_of_a_window"] == ["3000:AA"]


def test_the_same_unit_is_kept_when_every_host_is_public():
    t = with_rows([{"utility_id_eia": 3000, "state": "AA", "ultimate_parent": "P5", "from_year": 2009, "to_year": 2014}])
    s, _, _ = build(classes={H1: PUBLIC, (3000, "AA"): IOU}, table=t[t.utility_id_eia != 100])
    assert (3000, "AA") in nt(s) and (3000, "AA") not in s.unknown_ownership_year_exclusions


def test_a_unit_covered_in_every_window_year_by_two_consecutive_rows_is_kept():
    t = with_rows([{"utility_id_eia": 3000, "state": "AA", "ultimate_parent": "P5", "from_year": 2001, "to_year": 2012},
                   {"utility_id_eia": 3000, "state": "AA", "ultimate_parent": "P6", "from_year": 2013, "to_year": 2025}])
    s, _, _ = build(classes={(3000, "AA"): IOU}, table=t)
    assert (3000, "AA") in nt(s) and (3000, "AA") not in s.unknown_ownership_year_exclusions


def test_units_with_a_row_for_part_of_the_window_are_counted_in_the_ownership_step_and_named_apart():
    # Before D-107 these two were removed by a separate ninth step; rule 2.2 read year by year now removes them in the
    # ownership step, under the no-row reason, and they are named apart with their uncovered years.
    t = with_rows([{"utility_id_eia": 3000, "state": "AA", "ultimate_parent": "P5", "from_year": 2009, "to_year": 2014},
                   {"utility_id_eia": 3001, "state": "AA", "ultimate_parent": "P5", "from_year": 2016, "to_year": 2025}])
    s, _, _ = build(classes={(3000, "AA"): IOU, (3001, "AA"): IOU, (3002, "AA"): PUBLIC}, table=t)
    steps = {st["step"]: st for st in s.steps}
    own = steps[cs.STEP_OWNERSHIP]
    assert own["removed"] == 5 and own["by_reason"] == {ownership.SAME_PARENT: 2, ownership.NO_ROW: 3}
    assert own["with_a_row_for_part_of_an_investor_owned_hosts_window"] == ["3000:AA", "3001:AA"]
    assert own["removed_only_for_a_row_for_part_of_a_window"] == ["3000:AA", "3001:AA"]
    assert s.unknown_ownership_year_exclusions[(3001, "AA")][0]["uncovered_years"] == [2009, 2010, 2011, 2012, 2013, 2014, 2015]
    assert (3002, "AA") in nt(s)                               # a public unit with no row is untouched
    assert [st["step"] for st in s.steps][-1] == cs.STEP_OWNERSHIP and list(cs.STEPS)[-1] == cs.STEP_OWNERSHIP


def test_the_sample_difference_names_units_the_main_design_keeps_for_some_host():
    s, _, _ = build()
    diff = cs.sample_difference(s, matched={C_AFF, C_OK[0]}, pool={C_AFF, C_OWN, C_OK[0], C_OK[1]}, main_hosts={H1, H2})
    assert [x["utility"] for x in diff["removed_by_the_any_host_ownership_exclusion_that_the_main_design_keeps_for_some_host"]] == ["2008:AA"]
    assert [x["utility"] for x in diff["removed_by_the_any_host_own_utility_exclusion_that_the_main_design_keeps_for_some_host"]] == ["100:BB"]
    assert diff["matched_units_not_never_treated_here"] == ["2008:AA"]
    assert diff["main_design_matched_comparison_units"] == 2 and diff["never_treated_units"] == len(nt(s))
    # since D-107 both bar a unit with a year of unknown ownership; the difference left is the union over hosts
    assert "year by year" in diff["unknown_ownership_years_difference"] and "union" in diff["unknown_ownership_years_difference"]


def test_the_sample_difference_names_units_removed_for_unknown_years_that_the_main_design_keeps():
    t = with_rows([{"utility_id_eia": 3000, "state": "AA", "ultimate_parent": "P5", "from_year": 2009, "to_year": 2014}])
    s, _, _ = build(classes={(3000, "AA"): IOU}, table=t)
    diff = cs.sample_difference(s, matched={(3000, "AA")}, pool={(3000, "AA")}, main_hosts={H1, H2})
    named = diff["removed_for_a_year_of_unknown_ownership_that_the_main_design_keeps_for_some_host"]
    assert [x["utility"] for x in named] == ["3000:AA"] and named[0]["excluded_here_for"][0]["uncovered_years"] == [2015, 2016, 2017, 2018]


def outcomes_for(units, value=lambda k, y: 0.01 * y):
    return pd.DataFrame([(k[0], k[1], y, value(k, y)) for k in units for y in YEARS], columns=KEY + ["year", "outcome"])


def regions_for(units, region=lambda k, y: "West"):
    return pd.DataFrame([(k[0], k[1], y, region(k, y)) for k in units for y in YEARS], columns=KEY + ["year", "region"])


def test_an_unusable_unit_year_has_no_observation_even_with_an_outcome_supplied():
    s, q, usable = build()
    units = list(CLASS)
    f = cs.frame(s, regions_for(units), {"AA": 0.3, "BB": 0.5, "AK": 0.1}, outcomes_for(units), usable)
    d = f.data
    gap = d[(d.utility_id_eia == C_GAP[0]) & (d.state == C_GAP[1])]
    assert 2013 not in set(gap.year) and {2012, 2014} <= set(gap.year)
    h1 = d[(d.utility_id_eia == H1[0]) & (d.state == H1[1])]
    assert sorted(h1.year) == list(range(2009, 2019)) and set(h1.first_treat) == {2015}
    assert set(d[d.first_treat == 0].year) <= set(cs.YEARS)
    assert f.report["outcome_values_supplied_for_unit_years_without_a_row"] > 0
    assert set(d.columns) >= {"unit_id", "year", "first_treat", "state", "outcome", "gas_share"}


def test_a_usable_unit_year_without_an_outcome_stops():
    s, q, usable = build()
    units = list(CLASS)
    o = outcomes_for(units)
    o = o[~((o.utility_id_eia == C_GAP[0]) & (o.year == 2014))]
    with pytest.raises(ValueError, match="no finite outcome"):
        cs.frame(s, regions_for(units), {"AA": 0.3, "BB": 0.5, "AK": 0.1}, o, usable)


def test_a_state_with_no_gas_share_stops_rather_than_dropping_the_covariate():
    s, q, usable = build()
    units = list(CLASS)
    with pytest.raises(ValueError, match="gas share"):
        cs.frame(s, regions_for(units), {"AA": 0.3}, outcomes_for(units), usable)


# ---- the reference computation: a planted answer with the gas share ----------------------------------------------------

TAU, B = 0.05, 0.004


def region_effect(r, t):
    return {"R1": 0.01 * (t - 2000) + 0.02 * np.sin(t), "R2": 0.03 * np.cos(t) - 0.002 * (t - 2000)}[r]


def gas_world(movers=False):
    """Never-treated units with low gas shares, hosts with high ones, two regions, two cohorts (one if `movers`). The
    untreated change from g-3 to t is a region effect plus B x gas share x (t - (g-3)); the planted effect is TAU in event
    years 2 and 3 only. No noise. With `movers`, one never-treated unit and one host change region inside the window, and
    every unit's trend follows its region in the cohort's reference year (the region the package should read)."""
    cohorts = {2016: 4} if movers else {2014: 4, 2019: 3}
    gas, units, base_region = {}, [], {}
    for i in range(30):
        k = (5000 + i, f"N{i % 10}")
        gas[k[1]] = 0.10 + 0.04 * (i % 10)
        units.append((k, 0, "R1" if i % 2 else "R2"))
    j = 0
    for g, n in cohorts.items():
        for _ in range(n):
            k = (6000 + j, f"T{j}")
            gas[k[1]] = 0.55 + 0.05 * j
            units.append((k, g, "R1" if j % 2 else "R2"))
            j += 1
    mover_keys = {units[0][0], units[30][0]} if movers else set()
    switch_year = 2017

    def region_of(k, y):
        r0 = next(r for kk, _, r in units if kk == k)
        if k in mover_keys and y >= switch_year:
            return "R2" if r0 == "R1" else "R1"
        return r0

    rows = []
    for k, g, r0 in units:
        for y in YEARS:
            v = 1.0 + 0.001 * k[0] + region_effect(r0, y) + B * gas[k[1]] * (y - 2000)
            if g and (y - g) in (2, 3):
                v += TAU
            rows.append((k[0], k[1], y, v))
    outcomes = pd.DataFrame(rows, columns=KEY + ["year", "outcome"])
    regions = pd.DataFrame([(k[0], k[1], y, region_of(k, y)) for k, _, _ in units for y in YEARS], columns=KEY + ["year", "region"])
    s = cs.Sample(0.02, "invented",
                  pd.DataFrame([(k[0], k[1], g) for k, g, _ in units if g], columns=KEY + ["cohort"]),
                  pd.DataFrame([(k[0], k[1]) for k, g, _ in units if not g], columns=KEY))
    usable = {(k[0], k[1], y) for k, _, _ in units for y in YEARS}
    f = cs.frame(s, regions, gas, outcomes, usable)
    return f, units, gas, cohorts


def expected_bias_without_gas(units, gas, cohorts, e):
    """With region dummies only, the never-treated fit at a host is its region's mean change, so the host's error is
    B x (t-(g-3)) x (its gas share - the mean gas share of never-treated units in its region). Group-size weights."""
    ctrl = {r: np.mean([gas[k[1]] for k, g, rr in units if not g and rr == r]) for r in ("R1", "R2")}
    num = den = 0.0
    for g in cohorts:
        mine = [(k, r) for k, gg, r in units if gg == g]
        dev = np.mean([gas[k[1]] - ctrl[r] for k, r in mine])
        num += len(mine) * B * (e + 3) * dev
        den += len(mine)
    return num / den


def test_the_reference_recovers_the_planted_effect_with_the_gas_share_and_is_biased_by_a_known_amount_without_it():
    f, units, gas, cohorts = gas_world()
    regions_only = [c for c in f.covariates if c != "gas_share"]
    assert "gas_share" in f.covariates and len(regions_only) == 1
    for e in (2, 3):
        with_gas = cs.reference_event_study(f.data, e, f.covariates)
        without = cs.reference_event_study(f.data, e, regions_only)
        bias = expected_bias_without_gas(units, gas, cohorts, e)
        assert abs(with_gas - TAU) < TOL_RECOVER
        assert abs(without - (TAU + bias)) < TOL_FORMULA
        assert abs(bias) > 1e-3                      # the covariate matters in this world
    for e in (-6, -5, -4, -2, -1, 0, 1):
        assert abs(cs.reference_event_study(f.data, e, f.covariates)) < TOL_RECOVER
    assert abs(cs.reference_headline(f.data, f.covariates) - TAU) < TOL_RECOVER


def test_the_reference_reads_region_at_g_minus_3_for_a_unit_that_changes_region_inside_a_window():
    f, units, gas, cohorts = gas_world(movers=True)
    assert f.report["units_whose_region_changes_inside_the_frame"] == 2
    assert abs(cs.reference_headline(f.data, f.covariates) - TAU) < TOL_RECOVER
    # the same frame with each mover's region frozen at its LAST year: the reference no longer recovers TAU, so the test
    # can tell which year's region is read
    d = f.data.copy()
    rcols = [c for c in f.covariates if c.startswith("region_")]
    for uid, grp in d.groupby("unit_id"):
        if grp.region.nunique() > 1:
            last = grp.sort_values("year").iloc[-1]
            d.loc[grp.index, rcols] = last[rcols].values
    assert abs(cs.reference_headline(d, f.covariates) - TAU) > 1e-3


def test_the_reference_counts_a_rank_deficient_comparison_regression_as_a_failure():
    f, *_ = gas_world()
    d = f.data.assign(dup=f.data.gas_share)
    with pytest.raises(cs.ReferenceFailure, match="rank deficient"):
        cs.reference_att(d, 2014, 2016, f.covariates + ["dup"])


# ---- the package (skipped while diff-diff 4.0.0 is not installed) ------------------------------------------------------

def test_the_package_returns_the_planted_effect_and_agrees_with_the_reference():
    pytest.importorskip("diff_diff", reason=SKIP_REASON)
    f, *_ = gas_world()
    out = cs.run(f)
    ref = cs.reference_headline(f.data, f.covariates)
    assert out["numerical_failure"] is None
    assert abs(out["headline"] - TAU) < TOL_PACKAGE
    assert abs(out["headline"] - ref) < TOL_PACKAGE
    for e in (2, 3):
        assert abs(out["event_years"][str(e)] - cs.reference_event_study(f.data, e, f.covariates)) < TOL_PACKAGE
    assert out["range_label"] == cs.RANGE_LABEL and out["se_unit_level"] is not None
    assert out["call"] == cs.PINNED_CALL


def test_the_package_reads_region_at_the_base_period_for_a_unit_that_changes_region_inside_a_window():
    """The frame keeps each unit-year's own region (the movers' dummies flip in 2017, after g-3 = 2013). Every unit's trend
    follows its region in the reference year, so the package returns TAU only if it reads covariates at g-3."""
    pytest.importorskip("diff_diff", reason=SKIP_REASON)
    f, *_ = gas_world(movers=True)
    out = cs.run(f)
    assert abs(out["headline"] - TAU) < TOL_PACKAGE
    assert abs(out["headline"] - cs.reference_headline(f.data, f.covariates)) < TOL_PACKAGE


# ---- refusals --------------------------------------------------------------------------------------------------------

def test_run_refuses_in_words_when_the_package_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "diff_diff", None)          # import diff_diff raises ImportError
    f, *_ = gas_world()
    with pytest.raises(cs.PackageMissing, match=r"diff-diff==4\.0\.0.*not installed.*Nothing is substituted"):
        cs.run(f)


def test_run_refuses_in_words_when_the_version_differs(monkeypatch):
    fake = types.ModuleType("diff_diff")
    fake.__version__ = "3.13.0"
    fake.CallawaySantAnna = lambda **kw: pytest.fail("the estimator must not be constructed at another version")
    monkeypatch.setitem(sys.modules, "diff_diff", fake)
    f, *_ = gas_world()
    with pytest.raises(cs.PackageVersionRefused, match=r"'3\.13\.0', not the pinned 4\.0\.0"):
        cs.run(f)


def test_the_pinned_call_is_the_plans():
    assert cs.PINNED_CALL == dict(control_group="never_treated", anticipation=2, base_period="universal",
                                  estimation_method="reg", cluster="state", n_bootstrap=999, bootstrap_weights="rademacher",
                                  seed=20261204, cband=False, allow_unbalanced_panel=False)


def test_the_headline_and_its_standard_error_come_from_the_event_study_covariance():
    es = types.SimpleNamespace(event_time=np.array([-6, -5, -4, -3, -2, -1, 0, 1, 2, 3]),
                               att=np.array([0, 0, 0, 0, 0, 0, 0.01, 0.02, 0.04, 0.06]),
                               vcov_index=np.array([-6, -5, -4, -2, -1, 0, 1, 2, 3]),
                               vcov=np.diag([1, 1, 1, 1, 1, 1, 1, 0.04, 0.09]) + np.pad([[0, 0.01], [0.01, 0]], ((7, 0), (7, 0))))
    h = cs.headline_from_event_study(es)
    assert abs(h["headline"] - 0.05) < 1e-15
    assert abs(h["se"] - np.sqrt(0.25 * (0.04 + 0.09 + 2 * 0.01))) < 1e-15
    es.vcov = es.vcov.copy()
    es.vcov[-1, -1] = np.nan
    h = cs.headline_from_event_study(es)
    assert h["se"] is None and "not finite" in h["numerical_failure"] and h["headline_label"].startswith("descriptive")


# ---- Joe's ruling of 2026-11-19 (D-105): the range as labelled --------------------------------------------------------

def labels_of_the_range() -> dict:
    """Every string in the module that labels or describes the range."""
    s, _, _ = build()
    diff = cs.sample_difference(s, matched=set(), pool=set(), main_hosts={H1, H2})
    stated = [x for x in diff["stated_differences_from_the_main_estimate"] if "range" in x]
    return {"RANGE_LABEL": cs.RANGE_LABEL, "RANGE_TEXT": cs.RANGE_TEXT, "RANGE_DIFFERENCE": cs.RANGE_DIFFERENCE,
            **{f"stated_difference_{i}": x for i, x in enumerate(stated)}}


def check_range_wording(labels: dict):
    assert labels
    for name, text in labels.items():
        low = text.lower()
        assert "secondary" in low and "uncalibrated" in low, name
        assert "t-based" in low and "t critical value" in low, name
        assert "package's interval" not in low and "package’s interval" not in low, name
        assert "rests on the package" not in low, name


def test_every_label_of_the_range_says_secondary_and_uncalibrated_and_t_based_and_never_the_packages_interval():
    check_range_wording(labels_of_the_range())
    assert cs.RANGE_LABEL.endswith(cs.PLAN_UNCALIBRATED_WORDS)        # the plan's words end the label
    assert "number of states less one" in cs.RANGE_LABEL and "bootstrap standard error" in cs.RANGE_LABEL
    doc = " ".join(cs.__doc__.split())
    assert "the range rests on the package's multiplier bootstrap" not in doc


def test_the_wording_check_fails_on_the_label_of_before_2026_11_19(monkeypatch):
    """A deliberate break in the test process: the old label and the old stated difference put back."""
    monkeypatch.setattr(cs, "RANGE_LABEL", "not calibrated by the inference comparison")
    with pytest.raises(AssertionError):
        check_range_wording(labels_of_the_range())
    monkeypatch.undo()
    monkeypatch.setattr(cs, "RANGE_DIFFERENCE", "the range rests on the package's multiplier bootstrap, not calibrated by "
                                                "the inference comparison")
    with pytest.raises(AssertionError):
        check_range_wording(labels_of_the_range())


# ---- Joe's ruling of 2026-11-19 (D-111): the comparison sample against the headline's, disclosed first -------------------

ATTRIBUTION = "A difference between this run's estimate and the headline estimate cannot be attributed solely to the estimator."


def check_sample_disclosure(diff: dict, *, with_count: bool):
    assert next(iter(diff)) == "comparison_sample_difference_disclosed"        # first, so prominent
    text = diff["comparison_sample_difference_disclosed"]
    assert text.endswith(ATTRIBUTION) and "D-111" in text and "differs from the headline's" in text
    if with_count:
        assert "680 of the 1,670 never-treated units" in text and "605 of them" in text
    else:
        assert "was not made for this set" in text
    stated = [x for x in diff["stated_differences_from_the_main_estimate"] if "region with no host" in x]
    assert len(stated) == 1 and "D-111" in stated[0] and stated[0].endswith(ATTRIBUTION)


def test_the_sample_difference_discloses_the_never_treated_units_in_no_hosts_region_first():
    s, _, _ = build()
    s.which, s.theta = ps.HEADLINE_SET, 0.02
    diff = cs.sample_difference(s, matched=set(), pool=set(), main_hosts={H1, H2})
    check_sample_disclosure(diff, with_count=True)
    assert diff["comparison_sample_difference_disclosed"] == cs.REGION_SAMPLE_DIFFERENCE
    assert cs.ESTIMATOR_ATTRIBUTION == ATTRIBUTION
    # on any other set the count on file, made for the headline set at 2%, is not stated as this set's
    s.which = "every_cohort_utility"
    other = cs.sample_difference(s, matched=set(), pool=set(), main_hosts={H1, H2})
    check_sample_disclosure(other, with_count=False)
    assert other["comparison_sample_difference_disclosed"] == cs.REGION_SAMPLE_DIFFERENCE_OTHER_SET
    # the sample itself is not changed by the disclosure: no step names region
    assert not any("region" in st["step"] for st in s.steps)


def test_the_disclosure_check_can_fail(monkeypatch):
    """A deliberate break in the test process: the attribution sentence dropped, then the count dropped."""
    s, _, _ = build()
    s.which, s.theta = ps.HEADLINE_SET, 0.02
    monkeypatch.setattr(cs, "REGION_SAMPLE_DIFFERENCE", cs.REGION_SAMPLE_DIFFERENCE.replace(ATTRIBUTION, ""))
    with pytest.raises(AssertionError):
        check_sample_disclosure(cs.sample_difference(s, matched=set(), pool=set(), main_hosts={H1, H2}), with_count=True)
    monkeypatch.undo()
    monkeypatch.setattr(cs, "REGION_SAMPLE_DIFFERENCE", cs.REGION_SAMPLE_DIFFERENCE.replace("680 of the", "some of the"))
    with pytest.raises(AssertionError):
        check_sample_disclosure(cs.sample_difference(s, matched=set(), pool=set(), main_hosts={H1, H2}), with_count=True)
