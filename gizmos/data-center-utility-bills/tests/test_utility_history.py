"""Utility-level histories of data center load: how one figure is read, and what a history settles (D-34)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.facilities import buildout as bo  # noqa: E402
from pipeline.facilities import utility_history as uh  # noqa: E402


def table(rows):
    base = {"utility_id_eia": 1, "state": "ZZ", "value_error": np.nan, "bound": "exact", "unit": "GWh", "mw_kind": np.nan,
            "load_factor": np.nan, "coverage": "utility", "source_url": "https://example.org/irp.pdf",
            "source_type": "resource plan", "source_quote": "data center sales were", "read_from_chart": False,
            "confidence": "high", "checked_on": "2026-11-12", "note": ""}
    return pd.DataFrame([{**base, **r} for r in rows])[uh.COLUMNS]


def row(**kw):
    return next(table([{"year": 2015, "value": 100.0, **kw}]).itertuples())


def test_energy_is_used_as_given_and_average_mw_runs_all_year():
    assert uh.bounds_gwh(row(value=500.0)) == (500.0, 500.0)
    assert uh.bounds_gwh(row(unit="MW", mw_kind="average", value=100.0)) == pytest.approx((876.0, 876.0))


def test_a_share_of_sales_needs_that_years_sales():
    assert uh.bounds_gwh(row(unit="share_of_sales", value=0.21), sales_gwh=80_000.0) == pytest.approx((16_800.0, 16_800.0))
    assert uh.bounds_gwh(row(unit="share_of_sales", value=0.21), sales_gwh=None) == (0.0, np.inf)


def test_demand_in_mw_is_read_both_ways():
    lo, hi = uh.bounds_gwh(row(unit="MW", mw_kind="demand", value=100.0))
    assert lo == pytest.approx(100 * 0.6 * 8.76) and hi == pytest.approx(100 * 8.76)
    # the document's own load factor replaces the band
    assert uh.bounds_gwh(row(unit="MW", mw_kind="demand", value=100.0, load_factor=0.9)) == pytest.approx((788.4, 788.4))


def test_capacity_is_not_load_and_can_only_show_a_utility_below():
    lo, hi = uh.bounds_gwh(row(unit="MW", mw_kind="connected", value=100.0))
    assert lo == 0.0 and hi == pytest.approx(876.0)
    assert uh.verdict(lo, hi, 900.0) == "below" and uh.verdict(lo, hi, 500.0) == "undecided"


def test_a_larger_area_can_only_show_below_and_a_part_only_at_or_above():
    lo, hi = uh.bounds_gwh(row(value=500.0, coverage="larger_area"))
    assert (lo, hi) == (0.0, 500.0) and uh.verdict(lo, hi, 400.0) == "undecided" and uh.verdict(lo, hi, 600.0) == "below"
    lo, hi = uh.bounds_gwh(row(value=500.0, coverage="part"))
    assert lo == 500.0 and hi == np.inf and uh.verdict(lo, hi, 400.0) == "at_or_above" and uh.verdict(lo, hi, 600.0) == "undecided"


def test_a_floor_has_no_upper_bound_and_a_chart_read_carries_its_error():
    lo, hi = uh.bounds_gwh(row(unit="MW", mw_kind="demand", value=100.0, bound="at_least"))
    assert lo == pytest.approx(525.6) and hi == np.inf
    lo, hi = uh.bounds_gwh(row(unit="MW", mw_kind="demand", value=190.0, value_error=10.0))
    assert lo == pytest.approx(180 * 0.6 * 8.76) and hi == pytest.approx(200 * 8.76)


def test_consecutive_years_give_the_crossing():
    s = uh.settle({2014: "below", 2015: "at_or_above", 2016: "at_or_above"})
    assert s["settled"] and s["group"] == "cohort" and s["first_crossing"] == 2015


def test_two_candidate_years_take_the_later_and_three_settle_nothing():
    s = uh.settle({2013: "below", 2014: "undecided", 2015: "at_or_above"})
    assert s["settled"] and s["first_crossing"] == 2015
    s = uh.settle({2012: "below", 2015: "at_or_above"})
    assert not s["settled"] and "2 years or more" in s["why"]


def test_candidates_that_span_two_groups_settle_nothing():
    assert not uh.settle({2009: "below", 2011: "at_or_above"})["settled"]          # early or cohort
    assert not uh.settle({2015: "below", 2023: "at_or_above"})["settled"]          # cohort or late


def test_an_early_host_needs_no_year_and_no_below():
    s = uh.settle({2008: "at_or_above"})
    assert s["settled"] and s["group"] == "early" and s["first_crossing"] is None


def test_at_or_above_with_nothing_below_before_it_settles_nothing():
    s = uh.settle({2013: "at_or_above", 2014: "at_or_above"})
    assert not s["settled"] and s["first_at_or_above"] == 2013


def test_below_through_the_last_cohort_year_puts_a_utility_outside_the_cohorts():
    s = uh.settle({2015: "below", 2022: "below", 2024: "undecided"})
    assert s["settled"] and s["group"] == "outside_cohorts"
    assert not uh.settle({2015: "below", 2021: "below"})["settled"]                # 2022 is still open
    s = uh.settle({2022: "below", 2023: "at_or_above"})
    assert s["settled"] and s["group"] == "outside_cohorts" and s["first_crossing"] is None


def test_a_below_year_after_the_first_year_at_or_above_does_not_reopen_the_bracket():
    s = uh.settle({2014: "below", 2015: "at_or_above", 2016: "below"})
    assert s["settled"] and s["first_crossing"] == 2015


def test_read_judges_each_threshold_separately_and_disagreeing_figures_decide_nothing():
    t = table([{"year": 2014, "value": 150.0}, {"year": 2015, "value": 250.0},
               {"year": 2016, "value": 300.0}, {"year": 2016, "value": 900.0}])
    base = pd.Series({(1, "ZZ"): 10_000.0})
    r = uh.read(t, base, pd.Series(dtype=float))["1:ZZ"]["thresholds"]
    assert r["2%"]["settled"] and r["2%"]["first_crossing"] == 2015               # 200 GWh: 150 below, 250 above
    assert r["5%"]["verdicts"] == {"2014": "below", "2015": "below", "2016": "undecided"}
    assert not r["5%"]["settled"]
    assert uh.settled({"1:ZZ": {"thresholds": r}}, 0.02) == {(1, "ZZ"): {"group": "cohort", "first_crossing": 2015}}


@pytest.mark.parametrize("change", [
    {"source_url": "https://www.datacentermap.com/x"},
    {"source_url": np.nan},
    {"source_quote": np.nan},
    {"checked_on": np.nan},
    {"confidence": "low"},
    {"unit": "MW"},                                           # MW with no kind
    {"unit": "MW", "mw_kind": "demand", "load_factor": 1.4},
    {"read_from_chart": True},                                # chart read with no reading error
    {"read_from_chart": True, "value_error": 10.0},           # chart read at high confidence
    {"coverage": "zone"},
])
def test_the_table_refuses_rows_the_rule_does_not_allow(change):
    with pytest.raises(ValueError):
        uh.validate(table([{"year": 2015, "value": 100.0, **change}]))


def test_the_committed_table_is_valid_and_every_row_was_opened():
    t = uh.load()
    assert t.checked_on.notna().all() and t.source_quote.str.len().gt(20).all()


def test_first_crossings_take_the_utilitys_year_and_leave_the_others_alone():
    first = pd.Series({(1, "AA"): 2013, (2, "BB"): 2016, (3, "CC"): 2012, (4, "DD"): 2018})
    out, outside = bo.apply_utility_histories(first, {(1, "AA"): {"group": "cohort", "first_crossing": 2019},
                                                       (2, "BB"): {"group": "outside_cohorts", "first_crossing": None},
                                                       (3, "CC"): {"group": "early", "first_crossing": None}})
    assert out[(1, "AA")] == 2019 and out[(4, "DD")] == 2018 and out[(3, "CC")] == 2010
    assert (2, "BB") not in out.index and outside == [(2, "BB")]


def test_the_design_uses_the_utilitys_year_for_the_cohort_and_drops_a_utility_put_outside():
    years = range(2005, 2026)
    q = pd.DataFrame([(u, "ZZ", y) for u in (1, 2, 3, 4) for y in years], columns=["utility_id_eia", "state", "year"])
    rows = []
    for u, start in ((1, 2013), (2, 2016), (3, 2014)):
        rows += [(u, "ZZ", y, 0.03 if y >= start else 0.0, 0.0, 100.0) for y in years]
    dose = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "dose", "crypto_mw", "base_retail_gwh"])
    plain, _ = ps.design(q, dose, 0.02)
    assert dict(zip(plain.utility_id_eia, plain.cohort)) == {1: 2013, 2: 2016, 3: 2014}
    hist = {(1, "ZZ"): {"group": "cohort", "first_crossing": 2019}, (2, "ZZ"): {"group": "outside_cohorts", "first_crossing": None},
            (3, "ZZ"): {"group": "early", "first_crossing": None}}
    treated, clean = ps.design(q, dose, 0.02, hist)
    assert dict(zip(treated.utility_id_eia, treated.cohort)) == {1: 2019}
    assert set(clean.utility_id_eia) == {4}                    # comparison eligibility still rests on the inventory


def test_a_utility_settled_by_its_own_history_leaves_the_set_aside(tmp_path):
    import json
    (tmp_path / "dating_sensitivity.json").write_text(json.dumps(
        {"thresholds": {"2%": {"dependent_utilities": ["1:ZZ", "5:ZZ"]}}}))
    (tmp_path / "buildout_sensitivity.json").write_text(json.dumps(
        {"thresholds": {"2%": {"utilities_still_unsettled": [{"utility": "6:ZZ"}],
                               "settled_by_utility_level_history": [{"utility": "1:ZZ", "group": "cohort", "first_crossing": 2019}]}}}))
    assert set(ps.dates_and_histories_reasons(0.02, tmp_path)) == {(5, "ZZ"), (6, "ZZ")}
    (tmp_path / "treatment_bounds.json").write_text(json.dumps({"thresholds": {"2%": {"lists": {"does_not_keep_its_place": []}}}}))
    assert ps.set_aside(0.02, tmp_path) == {(5, "ZZ"), (6, "ZZ")}
    assert ps.history_settled(0.02, tmp_path)[(1, "ZZ")]["first_crossing"] == 2019


# ---- a site's electricity as its operator reports it (D-35) ----------------------------------

from pipeline.facilities import build_inventory as bi  # noqa: E402
from pipeline.facilities import site_energy as se  # noqa: E402


def energy_tables(rows, sites):
    base = {"operator": "Meta", "year_type": "calendar", "printed_unit": "MWh", "document": "data index", "page": 6,
            "source_url": "https://sustainability.atmeta.com/x.pdf", "source_quote": "Site [...] 2021: 1", "confidence": "high",
            "checked_on": "2026-11-12", "note": ""}
    e = pd.DataFrame([{**base, "printed_value": str(r["mwh"]), **r} for r in rows])[se.ENERGY_COLUMNS]
    s = pd.DataFrame([{"site_as_the_operator_names_it": "Site", "match_basis": "operator and place", **x} for x in sites])[se.SITE_COLUMNS]
    return se.validate(e, s)


def test_reported_electricity_becomes_average_load_and_holds_after_the_last_year():
    e, s = energy_tables([{"campus": "a", "year": 2020, "mwh": 0}, {"campus": "a", "year": 2021, "mwh": 87_600},
                          {"campus": "a", "year": 2023, "mwh": 175_200}], [{"campus": "a", "fid": "bi:1-0"}])
    path = se.paths(e, s)["bi:1-0"]
    assert se.first_year(path) == 2021
    assert [se.energy_mw(path, y) for y in (2019, 2020, 2021, 2022, 2023, 2025)] == pytest.approx([0, 0, 10, 10, 20, 20])
    # past the end of the series another measured source counts only if it is higher
    assert se.energy_mw(path, 2025, after=15.0) == pytest.approx(20.0)
    assert se.energy_mw(path, 2025, after=99.0) == pytest.approx(99.0)
    assert se.energy_mw(path, 2023, after=99.0) == pytest.approx(20.0)


def test_a_campus_on_two_rows_is_split_by_generator_capacity_and_needs_both_capacities():
    e, s = energy_tables([{"campus": "a", "year": 2021, "mwh": 87_600}],
                         [{"campus": "a", "fid": "bi:1-0"}, {"campus": "a", "fid": "bi:2-0"}])
    p = se.paths(e, s, {"bi:1-0": 3000.0, "bi:2-0": 1000.0})
    assert p["bi:1-0"][2021] == pytest.approx(7.5) and p["bi:2-0"][2021] == pytest.approx(2.5)
    with pytest.raises(ValueError):
        se.paths(e, s, {"bi:1-0": 3000.0})


@pytest.mark.parametrize("change", [{"source_url": "https://www.datacenterdynamics.com/x"}, {"mwh": -1},
                                    {"source_quote": np.nan}, {"checked_on": np.nan}, {"confidence": "low"}])
def test_the_site_energy_table_refuses_what_the_rule_does_not_allow(change):
    with pytest.raises(ValueError):
        energy_tables([{"campus": "a", "year": 2021, "mwh": 10, **change}], [{"campus": "a", "fid": "bi:1-0"}])


def test_a_site_with_reported_electricity_follows_it_in_the_one_load_rule():
    energy = {"bi:1-0": {2021: 10.0, 2022: 30.0}, "epoch:X": {2021: 10.0, 2022: 30.0}}
    timeline = {("X", 2024): 80.0}
    assert bi.site_mw("bi", "bi:1-0", 2015, 500.0, 2020, {}, None, energy) == 0.0          # not the ramp from its permit year
    assert bi.site_mw("bi", "bi:1-0", 2015, 500.0, 2022, {}, None, energy) == pytest.approx(30.0)
    assert bi.site_mw("bi", "bi:1-0", 2015, 500.0, 2025, {}, None, energy) == pytest.approx(30.0)
    assert bi.site_mw("epoch", "epoch:X", 2021, 80.0, 2022, timeline, None, energy) == pytest.approx(30.0)
    assert bi.site_mw("epoch", "epoch:X", 2021, 80.0, 2025, timeline, None, energy) == pytest.approx(80.0)
    assert bi.site_mw("bi", "bi:2-0", 2015, 90.0, 2015, {}, None, energy) == pytest.approx(30.0)   # every other site still ramps


def test_the_committed_site_energy_tables_are_valid_and_cover_what_the_decision_log_says():
    e, s = se.load()
    assert set(e.operator) == {"Meta", "Apple"} and e.checked_on.notna().all()
    assert len(s) == 21 and s.fid.is_unique
    meta = e[e.campus == "meta_prineville"].set_index("year").mwh
    assert meta[2014] == 262_000 and meta[2024] == 1_728_291
    assert e[(e.campus == "apple_maiden") & (e.year == 2025)].mwh.iloc[0] == 470_000
