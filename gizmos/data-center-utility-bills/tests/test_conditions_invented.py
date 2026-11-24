"""The four conditions (pipeline/analysis/conditions.py) on invented quantities and invented outcomes only.

Grouping rules at their boundaries (exactly 10%; a unit with zero or no delivery-only sales; a unit missing its
reference year fails in words), the contrast recovers a planted difference between groups, a one-host group is described
as driven by that utility, an empty group and a design the fit cannot estimate are "not estimable" and stay in the
record, and condition 4 is unavailable. Condition 4's comparable-footprint tests (the owner's ruling of 2026-11-19; the
session's reading): one state over the ratio's history, no succession inside it, customer continuity with its 10% line.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import conditions as cn  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from test_outcome_analysis_invented import (COMPS, HOSTS, IOU, ONE_STATE_COMPS, ONE_STATE_HOSTS, YEARS, make,  # noqa: E402
                                            outcomes, path)

KEY = ps.KEY
HOST_KEYS = [((h[0], h[1]), h[4]) for h in HOSTS]       # 1:AA 2013, 2:AC 2015, 3:BA 2015, 4:BC 2017


def dose_frame(values: dict) -> pd.DataFrame:
    """A dose row for every host and year; `values` sets (id, state, year) -> dose, everything else 0.001."""
    rows = [(k[0], k[1], y, values.get((k[0], k[1], y), 0.001)) for k, _ in HOST_KEYS for y in YEARS]
    return pd.DataFrame(rows, columns=KEY + ["year", "dose"])


def quantities(delivery: dict, others=()) -> pd.DataFrame:
    """Quantities rows (id, state, year, res_mwh_delivery) for every host and year: `delivery` sets (id, state, year) -> MWh
    (np.nan allowed); everything else 0.0. `others` adds (id, state, year, MWh) rows for other units."""
    rows = [(k[0], k[1], y, delivery.get((k[0], k[1], y), 0.0)) for k, _ in HOST_KEYS for y in YEARS] + list(others)
    return pd.DataFrame(rows, columns=KEY + ["year", "res_mwh_delivery"])


# ---- condition 1 ----------------------------------------------------------------------------------------------------

def test_load_share_reads_event_year_3_and_exactly_ten_percent_is_in_the_upper_group():
    v = {(1, "AA", 2016): 0.10, (2, "AC", 2018): 0.0999999, (3, "BA", 2018): 0.25, (4, "BC", 2020): 0.02,
         (2, "AC", 2017): 0.50}                                         # event year 2 for host 2: not read
    g = cn.load_share_grouping(HOST_KEYS, dose_frame(v))
    assert g.member == {"1:AA": True, "2:AC": False, "3:BA": True, "4:BC": False}
    assert g.value["1:AA"] == {"year": 2016, "load_share": 0.10}
    assert g.value["2:AC"]["year"] == 2018


def test_load_share_missing_year_or_value_fails_in_words():
    f = dose_frame({})
    with pytest.raises(cn.ConditionInputError, match=r"1:AA has no dose row in event year 3 \(2016\)"):
        cn.load_share_grouping(HOST_KEYS, f[~((f.utility_id_eia == 1) & (f.year == 2016))])
    f.loc[(f.utility_id_eia == 4) & (f.year == 2020), "dose"] = np.nan
    with pytest.raises(cn.ConditionInputError, match="4:BC's dose in 2020 is missing or not finite"):
        cn.load_share_grouping(HOST_KEYS, f)


# ---- condition 2 ----------------------------------------------------------------------------------------------------

def test_ownership_is_investor_owned_against_public_and_cooperative_and_an_unknown_class_stops():
    own = {(h[0], h[1]): h[3] for h in HOSTS}
    g = cn.ownership_grouping(HOST_KEYS, own)
    assert g.member == {"1:AA": True, "2:AC": False, "3:BA": False, "4:BC": True}
    with pytest.raises(cn.ConditionInputError, match="has ownership class None"):
        cn.ownership_grouping(HOST_KEYS, {**own, (3, "BA"): None})


# ---- condition 3 ----------------------------------------------------------------------------------------------------

def test_retail_choice_proxy_reads_the_reference_year_and_only_sales_above_zero_count():
    delivery = {(1, "AA", 2010): 5.0,          # host 1, reference year 2010: above zero
                (2, "AC", 2012): 0.0,          # host 2: exactly zero
                (3, "BA", 2012): np.nan,       # host 3: no delivery-only rows reported
                (4, "BC", 2013): 0.0, (4, "BC", 2014): 9.0}   # host 4: activity only after its reference year (2014 is cohort - 3)
    g = cn.retail_choice_grouping(HOST_KEYS, quantities(delivery))
    assert g.member == {"1:AA": True, "2:AC": False, "3:BA": False, "4:BC": True}
    assert g.value["3:BA"]["host_res_mwh_delivery"] is None and g.value["2:AC"]["host_res_mwh_delivery"] == 0.0
    assert g.value["1:AA"]["reference_year"] == 2010 and g.label == cn.PROXY_LABEL
    delivery[(4, "BC", 2014)] = 0.0
    delivery[(4, "BC", 2015)] = 9.0
    assert cn.retail_choice_grouping(HOST_KEYS, quantities(delivery)).member["4:BC"] is False


def test_the_state_reading_counts_any_unit_in_the_state_and_is_reported_beside_not_instead():
    q = quantities({}, others=[(900, "AC", 2012, 3.0), (901, "BA", 2011, 3.0)])   # 901's activity is not in host 3's reference year
    own = cn.retail_choice_grouping(HOST_KEYS, q, cn.HOST_OWN)
    st = cn.retail_choice_grouping(HOST_KEYS, q, cn.STATE_ANY)
    assert not any(own.member.values())
    assert st.member == {"1:AA": False, "2:AC": True, "3:BA": False, "4:BC": False}
    assert st.value["2:AC"]["units_in_state_with_delivery_only_residential_sales"] == 1
    assert st.extra["reading"] == cn.STATE_ANY and own.extra["reading"] == cn.HOST_OWN


def test_a_host_missing_its_reference_year_fails_in_words():
    q = quantities({})
    q = q[~((q.utility_id_eia == 2) & (q.year == 2012))]
    for reading in (cn.HOST_OWN, cn.STATE_ANY):
        with pytest.raises(cn.ConditionInputError, match=r"2:AC has no row in the quantities file in its reference year \(2012\)"):
            cn.retail_choice_grouping(HOST_KEYS, q, reading)


# ---- condition 4 ----------------------------------------------------------------------------------------------------

class OnlyListedColumns:
    """A source that hands over the listed columns and raises on any other request: pins what read_peaks asks for."""

    def __init__(self, frame):
        self._frame = frame

    def __getitem__(self, cols):
        cols = [cols] if isinstance(cols, str) else list(cols)
        extra = [c for c in cols if c not in cn.PEAK_COLUMNS]
        if extra:
            raise AssertionError(f"read_peaks asked for columns outside the list: {extra}")
        return self._frame[cols]

    def __getattr__(self, name):
        raise AssertionError(f"read_peaks touched {name!r} on the source")


def peak_source(rows, extra_column=True):
    """rows: (id, state, year, summer, winter[, data_observed]). The frame also carries a column read_peaks must not ask for."""
    out = []
    for r in rows:
        u, s, y, su, wi = r[:5]
        out.append({"utility_id_eia": u, "state": s, "report_date": pd.Timestamp(f"{y}-01-01"), "summer_peak_demand_mw": su,
                    "winter_peak_demand_mw": wi, "short_form": None, "data_observed": r[5] if len(r) > 5 else True,
                    **({"retail_sales_mwh": 1.0} if extra_column else {})})
    return OnlyListedColumns(pd.DataFrame(out))


PANEL = pd.DataFrame([(k[0], k[1], y, 1000.0) for k, _ in HOST_KEYS for y in YEARS],
                     columns=KEY + ["year", "res_customers"])          # one state each, a steady customer count

PEAK_ROWS = [
    (1, "AA", 2005, 100.0, 0.0), (1, "AA", 2008, 120.0, 90.0), (1, "AA", 2010, 108.0, 0.0),     # 108 / 120 = 0.90
    (1, "AA", 2011, 500.0, 0.0),                                                                # after the reference year: not read
    (2, "AC", 2009, 50.0, 80.0), (2, "AC", 2012, 70.0, 100.0),                                  # winter larger: 100 / 80 = 1.25
    (3, "BA", 2011, 100.0, np.nan), (3, "BA", 2012, 95.0, np.nan),                              # 0.95, the median
    (3, "BA", 2004, 999.0, 0.0, False),                                                          # EIA-imputed: no report
    (4, "BC", 2014, 40.0, 30.0),                                                                # no earlier report
]


def test_past_utilization_ratio_by_hand_winter_larger_and_the_median_host_goes_second():
    g = cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(PEAK_ROWS)), panel_units=PANEL)
    v = g.value
    assert v["1:AA"]["ratio"] == pytest.approx(0.90, abs=1e-15) and v["1:AA"]["prior_maximum_year"] == 2008
    assert v["2:AC"]["ratio"] == pytest.approx(1.25, abs=1e-15) and v["2:AC"]["peak_mw_in_reference_year"] == 100.0
    assert v["2:AC"]["prior_maximum_mw"] == 80.0
    assert v["3:BA"]["ratio"] == pytest.approx(0.95, abs=1e-15)          # the imputed 2004 row (999) is not the prior maximum
    assert g.extra["median"] == pytest.approx(0.95)
    assert g.member == {"1:AA": False, "2:AC": True, "3:BA": False}          # at the median: second group
    assert g.extra["not_classifiable"] == {"4:BC": cn.NO_EARLIER}


def test_no_reference_year_report_and_zero_in_both_are_not_classifiable():
    rows = [r for r in PEAK_ROWS if r[:3] != (1, "AA", 2010)] + [(1, "AA", 2010, 0.0, np.nan)]
    g = cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(rows)), panel_units=PANEL)
    assert g.extra["not_classifiable"]["1:AA"] == cn.NO_REF and "1:AA" not in g.member


def test_a_host_filed_under_another_state_is_not_classifiable_and_named():
    rows = [r for r in PEAK_ROWS if r[0] != 4] + [(4, "ZZ", y, 40.0 + y - 2001, 0.0) for y in range(2001, 2026)]
    g = cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(rows)), panel_units=PANEL)
    assert g.extra["not_classifiable"]["4:BC"] == ("not classifiable on this condition: its operational record is filed for the "
                                                   "utility as a whole under another state (ZZ)")
    assert "4:BC" not in g.member


def test_a_two_state_utility_is_not_classifiable_even_in_the_state_its_record_is_filed_under():
    """Host 2's utility also has a panel unit in BB in its window: its AC record (the filing state) is the whole utility's."""
    two = pd.concat([PANEL, pd.DataFrame([(2, "BB", y, 50.0) for y in range(2009, 2019)], columns=KEY + ["year", "res_customers"])])
    g = cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(PEAK_ROWS)), panel_units=two)
    assert g.extra["not_classifiable"]["2:AC"] == cn.MULTI_STATE and "2:AC" not in g.member
    assert g.value["2:AC"]["panel_states_of_its_utility_in_its_window"] == ["AC", "BB"]
    # a second state only outside the window (2009 to 2018 for cohort 2015) leaves it classifiable
    late = pd.concat([PANEL, pd.DataFrame([(2, "BB", 2020, 50.0)], columns=KEY + ["year", "res_customers"])])
    assert "2:AC" in cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(PEAK_ROWS)), panel_units=late).member


def test_read_peaks_asks_for_the_listed_columns_and_nothing_else():
    src = peak_source(PEAK_ROWS)
    with pytest.raises(AssertionError, match="outside the list"):
        src[["utility_id_eia", "retail_sales_mwh"]]                     # the guard works
    out = cn.read_peaks(src)                                           # and read_peaks passes it
    assert list(out.columns) == ["utility_id_eia", "state", "year", "peak_mw", "short_form", "data_observed"]


def test_a_repeated_key_for_a_host_stops_in_words():
    with pytest.raises(cn.ConditionInputError, match="more than one operational row"):
        cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(PEAK_ROWS + [(2, "AC", 2012, 1.0, 1.0)])), panel_units=PANEL)


def test_the_contrast_leaves_unclassifiable_hosts_out_of_this_contrast_only():
    d, q, regions, dd = make()
    g = cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(PEAK_ROWS)), panel_units=PANEL)   # 2 above; 1, 3 at or below; 4 not classifiable
    y = oa.outcome_vector(d, two_group_outcome(dd, {(2, "AC")}), "log_price")
    r = cn.contrast(d, y, g)
    assert r["estimable"] and abs(r["difference_log_points"] - 0.05) < 1e-10      # host 4 out; the planted 0.05 back
    assert r["hosts_not_classifiable_left_out_of_this_contrast"] == {"4:BC": cn.NO_EARLIER}
    assert r["groups"]["first"]["hosts"] == 1 and r["groups"]["second"]["hosts"] == 2
    assert "not_classifiable" not in r["groups"]                         # the design the contrast fits no longer has host 4
    # the same hosts on another condition keep host 4
    r2 = cn.contrast(d, y, grouping_of({"1:AA": False, "2:AC": True, "3:BA": False, "4:BC": False}))
    assert r2["groups"]["second"]["hosts"] == 3


def test_a_set_where_one_group_has_no_classifiable_host_is_not_estimable():
    rows = [r for r in PEAK_ROWS if r[0] in (1, 4)]                       # only host 1 has a ratio: it is the median, second group
    d, q, regions, dd = make()
    g = cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(rows)), panel_units=PANEL)
    assert g.member == {"1:AA": False}
    r = cn.contrast(d, oa.outcome_vector(d, outcomes(dd=dd, noise=0.01), "log_price"), g)
    assert r["estimable"] is False and r["not_estimable_because"].startswith(
        "no host in this design is in the group(s) ['past utilization above the median']")
    assert "counted in neither group" in r["not_estimable_because"]


# ---- the contrast ----------------------------------------------------------------------------------------------------

EFFECT_A = {0: 0.02, 1: 0.06, 2: 0.08, 3: 0.08}          # headline 0.08 (event year 1 differs, so years 1 and 2 would not give 0.05)
EFFECT_B = {0: 0.0, 1: 0.01, 2: 0.02, 3: 0.04}           # headline 0.03; difference A minus B = 0.05


def two_group_outcome(dd, group_a: set, noise=0.0, seed=7):
    f = outcomes(dd=dd, noise=noise, effect=EFFECT_B, seed=seed, state_sd=noise)
    cohort = {(h[0], h[1]): h[4] for h in HOSTS}
    for (u, s) in group_a:
        m = (f.utility_id_eia == u) & (f.state == s)
        f.loc[m, "log_price"] += [path(y - cohort[(u, s)], EFFECT_A) - path(y - cohort[(u, s)], EFFECT_B) for y in f.year[m]]
    return f


def grouping_of(members: dict) -> cn.Grouping:
    return cn.Grouping("test", "group A", "group B", members, {k: None for k in members}, "invented", kind="invented")


@pytest.mark.parametrize("noise,tol", [(0.0, 1e-10), (0.002, 0.006)])
def test_the_contrast_recovers_a_planted_difference_between_groups(noise, tol):
    """Tolerance 1e-10 with no noise; 0.006 (0.6 points) with noise sd 0.2% per unit-year and state-year."""
    d, q, regions, dd = make()
    a = {(1, "AA"), (3, "BA")}
    y = oa.outcome_vector(d, two_group_outcome(dd, a, noise), "log_price")
    g = grouping_of({"1:AA": True, "2:AC": False, "3:BA": True, "4:BC": False})
    r = cn.contrast(d, y, g)
    assert r["estimable"] and r["not_estimable_because"] is None
    assert abs(r["difference_log_points"] - 0.05) < tol
    assert r["difference_is"] == "group A minus group B" and r["what_this_is"] == cn.DESCRIPTIVE_LABEL
    assert not any(("range" in k or "p_value" in k or "test" in k) for k in r)          # no range, no test
    # beside it: counts, names, states, weight; two hosts a group, so each is described as driven by its two
    for side, labels in (("first", ["1:AA", "3:BA"]), ("second", ["2:AC", "4:BC"])):
        grp = r["groups"][side]
        assert grp["hosts"] == 2 and [x["utility"] for x in grp["named"]] == labels and grp["number_of_states"] == 2
        assert "driven by those particular utilities" in grp["driven_by"]
    shares = r["groups"]["first"]["share_of_host_side_weight"] + r["groups"]["second"]["share_of_host_side_weight"]
    assert abs(shares - 1.0) < 1e-10


def test_a_one_host_group_is_described_as_driven_by_that_utility_and_three_are_not():
    d, q, regions, dd = make()
    y = oa.outcome_vector(d, two_group_outcome(dd, {(4, "BC")}), "log_price")
    r = cn.contrast(d, y, grouping_of({"1:AA": False, "2:AC": False, "3:BA": False, "4:BC": True}), names={(4, "BC"): "Fourth Utility"})
    assert r["estimable"] and abs(r["difference_log_points"] - 0.05) < 1e-10
    assert r["groups"]["first"]["hosts"] == 1
    assert r["groups"]["first"]["driven_by"].startswith("this contrast is driven by those particular utilities (Fourth Utility)")
    assert "driven_by" not in r["groups"]["second"]
    assert r["groups"]["first"]["largest_single_host_share_within_group"] == pytest.approx(1.0)


def test_a_condition_with_an_empty_group_is_not_estimable_and_stays_in_the_record():
    d, q, regions, dd = make()
    y = oa.outcome_vector(d, outcomes(dd=dd, noise=0.01), "log_price")
    r = cn.contrast(d, y, grouping_of({h: True for h in ("1:AA", "2:AC", "3:BA", "4:BC")}))
    assert r["estimable"] is False and r["difference_log_points"] is None
    assert r["not_estimable_because"] == "no host in this design is in the group(s) ['group B']"
    assert r["groups"]["first"]["hosts"] == 4 and r["groups"]["second"]["hosts"] == 0


def test_a_contrast_the_fit_cannot_estimate_is_not_estimable_in_words():
    d, q, regions, dd = make(hosts=ONE_STATE_HOSTS, comps=ONE_STATE_COMPS)
    y = oa.outcome_vector(d, outcomes(hosts=ONE_STATE_HOSTS, comps=ONE_STATE_COMPS, dd=dd, noise=0.01), "log_price")
    r = cn.contrast(d, y, grouping_of({"1:AA": True, "2:AA": False}))
    assert r["estimable"] is False and r["not_estimable_because"].startswith("the fit fails its rank test before any inverse")
    assert r["groups"]["first"]["share_of_host_side_weight"] is None          # no weights from a design that fails the rank test


def test_a_host_without_a_value_stops_the_contrast():
    d, q, regions, dd = make()
    y = oa.outcome_vector(d, outcomes(dd=dd), "log_price")
    with pytest.raises(cn.ConditionInputError, match=r"no value for hosts \['4:BC'\]"):
        cn.contrast(d, y, grouping_of({"1:AA": True, "2:AC": False, "3:BA": True}))


# ---- condition 4: comparable footprints over the ratio's history (the owner's ruling of 2026-11-19) -------------------

SUCC_COLUMNS = ["predecessor_id", "state", "predecessor_name", "action", "successor_id", "successor_name", "effective_date",
                "source_url", "source_type", "source_quote", "confidence", "checked_on", "note"]


def succession(rows=()):
    """An invented succession table: rows (predecessor, state, action, successor or None, effective_date)."""
    out = [{"predecessor_id": p, "state": st, "predecessor_name": "x", "action": a, "successor_id": n, "successor_name": "y",
            "effective_date": d, "source_url": "https://example.org", "source_type": "filing", "source_quote": "q",
            "confidence": "high", "checked_on": "2026-11-19", "note": "n"} for p, st, a, n, d in rows]
    return pd.DataFrame(out, columns=SUCC_COLUMNS).astype({"predecessor_id": "Int64", "successor_id": "Int64"})


NO_SUCC = succession()
# Host 3 (BA, cohort 2015): reference year 2012, history 2001 to 2012, ratio 0.95 from PEAK_ROWS.
H3 = (3, "BA")


def customers(changes: dict, base=1000.0, drop=()):
    """PANEL with host 3's customer count set year by year: `changes` {year: count} from that year on; `drop` removes years."""
    f = PANEL.copy()
    m = (f.utility_id_eia == 3)
    for y, c in sorted(changes.items()):
        f.loc[m & (f.year >= y), "res_customers"] = c
    return f[~(m & f.year.isin(list(drop)))]


def group(panel=PANEL, succ=NO_SUCC, has_pred=None, rows=PEAK_ROWS):
    return cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(rows)), has_pred, panel, succession=succ)


def test_all_three_footprint_tests_pass_on_a_steady_single_state_unit_and_every_host_lists_its_peaks():
    g = group()
    assert g.member == {"1:AA": False, "2:AC": True, "3:BA": False}            # as before the footprint tests
    for lab in ("1:AA", "2:AC", "3:BA", "4:BC"):
        assert g.value[lab]["footprint_tests_failed"] == []
        assert set(g.value[lab]["footprint_tests"]) == set(cn.FOOTPRINT_TESTS)
    assert g.value["4:BC"]["peak_mw_in_reference_year"] == 40.0 and g.value["4:BC"]["prior_maximum_mw"] is None
    assert g.value["3:BA"]["prior_maximum_year"] == 2011


def test_one_state_fails_when_the_utility_has_a_unit_elsewhere_in_any_year_of_the_history():
    """A unit in another state in 2003 is outside the event window (2009 to 2018), so rule 5 does not see it; test (i) does.
    One in 2019, after the reference year 2012 (and after the window), does not fail it."""
    early = pd.concat([PANEL, pd.DataFrame([(3, "ZZ", 2003, 5.0)], columns=KEY + ["year", "res_customers"])])
    g = group(early)
    assert g.extra["not_classifiable"]["3:BA"] == f"{cn.FOOTPRINT_UNAVAILABLE} (failed: {cn.TEST_ONE_STATE})"
    assert g.value["3:BA"]["footprint_tests"][cn.TEST_ONE_STATE]["years_with_a_unit_of_the_utility_in_another_state"] == {"2003": ["BA", "ZZ"]}
    assert "3:BA" not in g.member and g.value["3:BA"]["ratio_not_used_footprint_not_shown_comparable"] == pytest.approx(0.95)
    after = pd.concat([PANEL, pd.DataFrame([(3, "ZZ", 2019, 5.0)], columns=KEY + ["year", "res_customers"])])
    assert "3:BA" in group(after).member


@pytest.mark.parametrize("date,fails", [("2001-06-30", False),    # in the first year of the history: not after it
                                        ("2002-01-01", True), ("2012", True),   # inside, up to R inclusive
                                        ("2013-01-01", False)])  # after R
def test_a_merger_into_the_unit_fails_only_inside_the_history(date, fails):
    succ = succession([(77, "BA", "sum", 3, date)])
    g = group(succ=succ, has_pred={H3})
    assert ("3:BA" in g.extra["not_classifiable"]) is fails
    t = g.value["3:BA"]["footprint_tests"][cn.TEST_NO_SUCCESSION]
    assert t["passes"] is (not fails) and t["panel_flags_has_predecessors"] is True
    if fails:
        assert g.extra["not_classifiable"]["3:BA"] == f"{cn.FOOTPRINT_UNAVAILABLE} (failed: {cn.TEST_NO_SUCCESSION})"
        assert t["rows_inside_the_history"][0]["kind"] == "a predecessor summed into the host's unit"


def test_succession_through_a_chain_the_unit_as_predecessor_and_a_flag_with_no_row():
    chain = succession([(78, "BA", "sum", 79, "2005-05-02"), (79, "BA", "sum", 3, "2014-01-01")])   # 78 -> 79 in 2005 -> 3 in 2014
    t = group(succ=chain, has_pred={H3}).value["3:BA"]["footprint_tests"][cn.TEST_NO_SUCCESSION]
    assert not t["passes"] and [e["predecessor"] for e in t["rows_inside_the_history"]] == ["78:BA"]
    assert [e["predecessor"] for e in t["rows_outside_the_history"]] == ["79:BA"]
    sold = succession([(3, "BA", "not_linked", None, "2010-06-01")])          # part of the unit's territory went elsewhere
    t = group(succ=sold).value["3:BA"]["footprint_tests"][cn.TEST_NO_SUCCESSION]
    assert not t["passes"] and t["rows_inside_the_history"][0]["kind"] == "the host's unit is itself the predecessor"
    g = group(has_pred={H3})                                                     # flagged, and no row says when
    assert g.value["3:BA"]["footprint_tests"][cn.TEST_NO_SUCCESSION]["flagged_but_no_row_names_its_predecessors"]
    assert "3:BA" not in g.member


@pytest.mark.parametrize("row,fails", [
    ((3, "ZZ", "sum", 80, "2011-01-01"), True),         # the id's territory in another state left it inside the history
    ((81, "ZZ", "sum", 3, "2008"), True),               # another utility's territory in another state joined the id
    ((3, "ZZ", "not_linked", None, "2005-03"), True),   # the id's other-state territory went elsewhere
    ((3, "ZZ", "sum", 80, "2013-01-01"), False),        # after R (2012)
    ((3, "ZZ", "sum", 80, "2001-01-01"), False)])       # in 2001, the first year of the history: not after it
def test_a_succession_row_on_the_same_eia_id_in_another_state_fails_the_host_inside_the_history(row, fails):
    """The session's extension of 2026-11-19: the filing utility is the EIA id, not the panel unit."""
    g = group(succ=succession([row]))
    t = g.value["3:BA"]["footprint_tests"][cn.TEST_NO_SUCCESSION]
    assert ("3:BA" in g.member) is (not fails) and t["passes"] is (not fails)
    if fails:
        assert g.extra["not_classifiable"]["3:BA"] == f"{cn.FOOTPRINT_UNAVAILABLE} (failed: {cn.TEST_NO_SUCCESSION})"
        (hit,) = t["rows_inside_the_history"]
        assert hit["predecessor"] == f"{row[0]}:{row[1]}" and hit["effective_date"] == row[4]
        assert "another state" in hit["kind"] and "adopted by Joe on 2026-11-19, D-111" in hit["kind"]
    else:
        assert [e["predecessor"] for e in t["rows_outside_the_history"]] == [f"{row[0]}:{row[1]}"]
    assert "same_eia_id_in_another_state_inside_the_history_reported_not_applied" not in t


@pytest.mark.parametrize("to,passes", [(1099.0, True), (1100.0, False), (901.0, True), (900.0, False)])
def test_customer_continuity_at_exactly_ten_percent_up_or_down(to, passes):
    g = group(customers({2007: to}))
    t = g.value["3:BA"]["footprint_tests"][cn.TEST_CUSTOMERS]
    assert t["passes"] is passes and ("3:BA" in g.member) is passes
    if not passes:
        assert t["changes_of_10_percent_or_more"][0]["from_year"] == 2006 and t["changes_of_10_percent_or_more"][0]["to_year"] == 2007
        assert g.extra["not_classifiable"]["3:BA"] == f"{cn.FOOTPRINT_UNAVAILABLE} (failed: {cn.TEST_CUSTOMERS})"
    assert cn.CUSTOMER_CHANGE_LINE == 0.10


def test_customer_continuity_needs_every_year_and_a_count_it_can_measure_from():
    assert not group(customers({}, drop=[2004])).value["3:BA"]["footprint_tests"][cn.TEST_CUSTOMERS]["passes"]
    missing = group(customers({2004: np.nan, 2005: 1000.0}))
    assert missing.value["3:BA"]["footprint_tests"][cn.TEST_CUSTOMERS]["years_missing"] == [2004]
    zero = group(customers({2004: 0.0, 2005: 1000.0})).value["3:BA"]["footprint_tests"][cn.TEST_CUSTOMERS]
    assert not zero["passes"] and zero["zero_counts_no_change_measurable"] == [2004]
    # a jump after the reference year (2012) is outside the history and does not fail it
    assert "3:BA" in group(customers({2013: 5000.0})).member
    with pytest.raises(cn.ConditionInputError, match="no res_customers column"):
        cn.past_utilization_grouping(HOST_KEYS, cn.read_peaks(peak_source(PEAK_ROWS)), None, PANEL[KEY + ["year"]], succession=NO_SUCC)


def test_failing_tests_are_all_named_and_the_median_is_taken_among_hosts_with_a_ratio():
    g = group(customers({2007: 2000.0}), succession([(77, "BA", "sum", 3, "2008")]), has_pred={H3})
    assert g.value["3:BA"]["footprint_tests_failed"] == [cn.TEST_NO_SUCCESSION, cn.TEST_CUSTOMERS]
    assert g.extra["not_classifiable"]["3:BA"].endswith(f"(failed: {cn.TEST_NO_SUCCESSION}; {cn.TEST_CUSTOMERS})")
    # host 3 out: the median of 0.90 and 1.25 is 1.075, host 1 below and host 2 above
    assert g.extra["median"] == pytest.approx(1.075) and g.member == {"1:AA": False, "2:AC": True}
