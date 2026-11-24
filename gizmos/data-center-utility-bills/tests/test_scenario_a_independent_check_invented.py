"""Tests of the independent check of sensitivity scenario A (tests/scenario_a_independent_check.py) on invented inputs.

Invented inputs only: no file under data/ is read. Each test plants the answer R2's words give and checks the checker
returns it; placements are compared exactly and loads to 1e-9 GWh. Each clause of R2's rule has its own test. The last
tests show the checks can fail, by breaking the checker's input or a function inside the test process (monkeypatch),
never by editing the code.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scenario_a_independent_check as ck  # noqa: E402

TOL = 1e-9
PANEL = {(5, "AA"), (6, "AA"), (7, "AA"), (8, "AA"), (9, "BB")}


def sites(rows):
    """rows: (fid, state, on, candidates, GWh). frame_order is the row order given."""
    f = pd.DataFrame(rows, columns=["fid", "state", "utility_id_eia", "candidates", "load_gwh"])
    f["candidates"] = [ck.parse_candidates(c) for c in f.candidates]
    f["frame_order"] = range(len(f))
    return f


def to(records):
    return {r["fid"]: r["to"] for r in records}


def why(records):
    return {r["fid"]: r["why"] for r in records}


# ---- R2's clauses, one test each -----------------------------------------------------------------------------------

def test_stored_order_is_kept():
    """Everything fits; the site goes to the first other candidate in stored order, not the largest or smallest id."""
    r = ck.place(sites([("s", "AA", 6, "8;5;7", 1.0)]), {}, {(5, "AA"): 100.0, (7, "AA"): 100.0, (8, "AA"): 100.0}, PANEL)
    assert to(r) == {"s": 8}


def test_panel_units_only_and_off_the_panel_never_chosen():
    """3 is not a panel unit (and has a capacity entry, to show the panel filter, not the sales filter, drops it)."""
    cap = {(3, "AA"): 1e6, (7, "AA"): 100.0}
    r = ck.place(sites([("s", "AA", 6, "3;7", 1.0)]), {}, cap, PANEL)
    assert to(r) == {"s": 7}
    r = ck.place(sites([("s", "AA", 6, "3", 1.0)]), {}, cap, PANEL)
    assert to(r) == {"s": 6} and why(r) == {"s": "no_other_panel_candidate"}
    # a candidate that is a panel unit in another state only is not a panel unit in the site's state
    r = ck.place(sites([("s", "AA", 6, "9", 1.0)]), {}, {(9, "BB"): 1e6}, PANEL)
    assert to(r) == {"s": 6} and why(r) == {"s": "no_other_panel_candidate"}


def test_the_current_utility_goes_to_the_end_and_is_never_a_move():
    r = ck.place(sites([("s", "AA", 6, "6;5", 1.0)]), {}, {(5, "AA"): 100.0, (6, "AA"): 100.0}, PANEL)
    assert to(r) == {"s": 5}
    r = ck.place(sites([("s", "AA", 6, "6", 1.0)]), {}, {(6, "AA"): 100.0}, PANEL)
    assert to(r) == {"s": 6} and r[0]["moved"] is False


def test_descending_size_with_ties_by_site_id():
    """Room on 7 for one 10 GWh site. The 20 GWh site goes first and does not fit (20 > 15), then of the two 10 GWh
    sites the lower site id takes 7. Given in the order z, b, a to show the input order is not used."""
    s = sites([("z", "AA", 6, "7", 10.0), ("b", "AA", 6, "7", 20.0), ("a", "AA", 6, "7", 10.0)])
    r = ck.place(s, {}, {(7, "AA"): 15.0}, PANEL)
    assert [x["fid"] for x in r] == ["b", "a", "z"]
    assert to(r) == {"b": 6, "a": 7, "z": 6}


def test_ties_by_frame_order_is_a_separate_switch():
    s = sites([("z", "AA", 6, "7", 10.0), ("a", "AA", 6, "7", 10.0)])
    r = ck.place(s, {}, {(7, "AA"): 15.0}, PANEL, dataclasses.replace(ck.MODULE_READING, tie="frame"))
    assert to(r) == {"z": 7, "a": 6}


def test_first_candidate_that_holds_the_full_load_on_top_of_what_it_carries():
    """7 carries 95 of 100: 10 more does not fit; 5 carries 40 of 50: 10 more fits exactly (<=, as pick_utilities)."""
    r = ck.place(sites([("s", "AA", 6, "7;5", 10.0)]), {(7, "AA"): 95.0, (5, "AA"): 40.0},
                 {(7, "AA"): 100.0, (5, "AA"): 50.0}, PANEL)
    assert to(r) == {"s": 5}
    r = ck.place(sites([("s", "AA", 6, "7;5", 10.0)]), {(7, "AA"): 95.0, (5, "AA"): 40.0},
                 {(7, "AA"): 100.0, (5, "AA"): 50.0}, PANEL, dataclasses.replace(ck.MODULE_READING, strict=True))
    assert to(r) == {"s": 6}                                           # strict <: 50 is not < 50


def test_capacity_is_the_largest_annual_retail_sales_2020_to_2025():
    """MWh over 1000; years before 2020 are ignored however large; a missing year is skipped; all missing is no row."""
    rows = pd.DataFrame({"utility_id_eia": [7, 7, 7, 7, 5, 5], "state": ["AA"] * 6,
                         "year": [2019, 2020, 2023, 2025, 2021, 2022],
                         "total_retail_mwh": [9e9, 120_000.0, 150_000.0, None, None, None]})
    cap = ck.capacity_from_sales(rows)
    assert abs(cap[(7, "AA")] - 150.0) < TOL
    assert (5, "AA") not in cap


def test_a_candidate_with_no_sales_row_is_skipped():
    r = ck.place(sites([("s", "AA", 6, "7;5", 10.0)]), {}, {(5, "AA"): 100.0}, PANEL)
    assert to(r) == {"s": 5}


def test_stays_if_no_other_candidate_fits():
    r = ck.place(sites([("s", "AA", 6, "7;5", 10.0)]), {(7, "AA"): 95.0}, {(7, "AA"): 100.0, (5, "AA"): 5.0}, PANEL)
    assert to(r) == {"s": 6} and why(r) == {"s": "no_other_candidate_fits"}


def test_moves_update_what_each_unit_carries():
    """Under the module's earlier reading, a site that moves is added to its new unit (the second site no longer fits
    on 7) and taken off its old one (the third site then fits on 6)."""
    E = ck.EARLIER_MODULE_READING
    s = sites([("a", "AA", 6, "7", 30.0), ("b", "AA", 8, "7", 20.0), ("c", "AA", 5, "6", 10.0)])
    carried = {(6, "AA"): 30.0, (8, "AA"): 20.0, (5, "AA"): 10.0}
    cap = {(7, "AA"): 40.0, (6, "AA"): 35.0}
    r = ck.place(s, carried, cap, PANEL, E)
    assert to(r) == {"a": 7, "b": 8, "c": 6}
    r = ck.place(s, carried, cap, PANEL, dataclasses.replace(E, update=False))
    assert to(r) == {"a": 7, "b": 7, "c": 5}                          # never updated: b fits on 7, c not on 6


def test_under_the_module_rule_each_placed_site_counts_where_it_lands():
    """The module's rule (lift first): the start leaves the placed sites out. a (30) lands on 7 (cap 40); b (20) does
    not fit on 7 and stays on 8, counted there; c (10) finds 6 empty (a was lifted off it) and moves."""
    s = sites([("a", "AA", 6, "7", 30.0), ("b", "AA", 8, "7", 20.0), ("c", "AA", 5, "6", 10.0)])
    r = ck.place(s, {}, {(7, "AA"): 40.0, (6, "AA"): 35.0}, PANEL)
    assert ck.MODULE_READING.carried == "resolved_only"
    assert to(r) == {"a": 7, "b": 8, "c": 6} and why(r)["b"] == "no_other_candidate_fits"


# ---- the readings of "what that candidate already carries" ------------------------------------------------------

def invented_inventory():
    """Two unresolved sites on 6 (x 30, y 20) and one resolved site on 7 (r 10); a crypto mine on 7 and a site out of
    the dose on 5. mw_full is GWh/8.76 so loads are round numbers."""
    k = 1 / ck.GWH_PER_MW_YEAR
    return pd.DataFrame({
        "fid": ["x", "y", "r", "m", "n"], "state": ["AA"] * 5, "utility_id_eia": [6, 6, 7, 7, 5],
        "utility_assign": ["smallest_polygon", "fallback_largest_flagged", "verified_by_hand", "unique", "unique"],
        "utility_candidates": ["7;6", "7;5;6", "7", "7", "5"], "in_dose": [True, True, True, True, False],
        "is_crypto": [False, False, False, True, False],
        "mw_full": [30 * k, 20 * k, 10 * k, 5 * k, 3 * k], "mw_full_raw": [15 * k, 10 * k, 5 * k, 5 * k, 3 * k]})


def test_selection_is_unresolved_in_dose_with_a_state_and_not_crypto():
    fac = invented_inventory()
    s = ck.select_sites(fac, set())
    assert sorted(s.fid) == ["x", "y"]
    assert abs(s.set_index("fid").load_gwh["x"] - 30.0) < TOL
    assert abs(ck.select_sites(fac, set(), "unscaled").set_index("fid").load_gwh["x"] - 15.0) < TOL


def test_one_territory_in_texas_with_an_ercot_candidate_is_unresolved():
    assert ck.is_resolved("unique", "TX", "4", {(4, "TX")}) is False
    assert ck.is_resolved("unique", "TX", "4", set()) is True
    assert ck.is_resolved("unique", "OK", "4", {(4, "OK")}) is True
    assert ck.is_resolved("verified_by_hand", "TX", "4", {(4, "TX")}) is True
    assert ck.is_resolved("next_larger_load_feasible", "AA", "4", set()) is False


def test_ercot_region_is_the_latest_known_code_else_the_states_most_common():
    rows = pd.DataFrame({"utility_id_eia": [1, 1, 2, 3, 4], "state": ["TX"] * 4 + ["OK"],
                         "year": [2014, 2020, 2020, 2020, 2020],
                         "balancing_authority": ["ERCO", "SWPP", "ERCO", None, "ZZZZ"]})
    table = {"ERCO": "ERCOT", "SWPP": "SPP"}
    e = ck.ercot_units(rows, table)
    # 1 last reported SWPP; 2 ERCO; 3 has no code and takes TX's most common (a tie of one each; value_counts order),
    # so only 1 and 2 are pinned here; 4's code is unknown and OK has no known code, so 4 has no region.
    assert (2, "TX") in e and (1, "TX") not in e and (4, "OK") not in e


def test_carried_readings_on_an_invented_inventory():
    fac = invented_inventory()
    R = ck.EARLIER_MODULE_READING
    placed = {"x", "y"}
    assert ck.carried_at_start(fac, placed, R) == pytest.approx({(6, "AA"): 50.0, (7, "AA"): 15.0, (5, "AA"): 3.0})
    assert ck.carried_at_start(fac, placed, dataclasses.replace(R, carried="in_dose")) == \
        pytest.approx({(6, "AA"): 50.0, (7, "AA"): 15.0})
    assert ck.carried_at_start(fac, placed, dataclasses.replace(R, carried="not_crypto")) == \
        pytest.approx({(6, "AA"): 50.0, (7, "AA"): 10.0, (5, "AA"): 3.0})
    assert ck.carried_at_start(fac, placed, dataclasses.replace(R, carried="resolved_only")) == \
        pytest.approx({(7, "AA"): 15.0, (5, "AA"): 3.0})
    assert ck.carried_at_start(fac, placed, dataclasses.replace(R, carried="nothing")) == {}


def test_the_reading_of_carried_load_decides_a_packed_unit():
    """The case found on the real inputs, invented: unit 5 is packed near its capacity by an unresolved site (p, 9 of
    15) that will itself move later. The larger site L (12) is placed first. Under the module's reading 5 already
    carries p's 9, so L does not fit and stays; with the placed sites' own load not counted at the start, 5 is empty
    for L and L moves there; p, placed next, moves to its other candidate under both readings."""
    s = sites([("L", "AA", 6, "5;6", 12.0), ("p", "AA", 5, "5;7", 9.0)])
    carried_all = {(6, "AA"): 12.0, (5, "AA"): 9.0}
    cap = {(5, "AA"): 15.0, (7, "AA"): 100.0}
    a = ck.place(s, carried_all, cap, PANEL, ck.EARLIER_MODULE_READING)
    assert to(a) == {"L": 6, "p": 7} and why(a)["L"] == "no_other_candidate_fits"
    b = ck.place(s, {}, cap, PANEL, dataclasses.replace(ck.MODULE_READING, carried="resolved_only"))
    assert to(b) == {"L": 5, "p": 7}
    assert ck.summarize(a, s)["sites_moved"] == 1 and ck.summarize(b, s)["sites_moved"] == 2
    assert ck.count_units(a, s) == {(5, "AA"), (7, "AA")}
    assert ck.count_units(b, s) == {(5, "AA"), (6, "AA"), (7, "AA")}


# ---- the counts -----------------------------------------------------------------------------------------------------

def test_unit_counts():
    """a: 6 -> 7 (10); b: 7 -> 6 (10), so 6 and 7 each gain and lose 10 and their placed load does not change; c: 8 ->
    5 in AA; d stays on 9 in BB. Utility 5 also counted once over two states in the id count."""
    s = sites([("a", "AA", 6, "7", 10.0), ("b", "AA", 7, "6", 10.0), ("c", "AA", 8, "5", 4.0)])
    recs = [{"fid": "a", "state": "AA", "from": 6, "to": 7, "moved": True, "why": "moved"},
            {"fid": "b", "state": "AA", "from": 7, "to": 6, "moved": True, "why": "moved"},
            {"fid": "c", "state": "AA", "from": 8, "to": 5, "moved": True, "why": "moved"},
            {"fid": "d", "state": "BB", "from": 5, "to": 5, "moved": False, "why": "no_other_candidate_fits"}]
    s = pd.concat([s, sites([("d", "BB", 5, "5", 1.0)])], ignore_index=True)
    assert ck.count_units(recs, s) == {(6, "AA"), (7, "AA"), (8, "AA"), (5, "AA")}
    assert ck.count_units(recs, s, "units_whose_placed_load_differs") == {(8, "AA"), (5, "AA")}
    assert ck.count_units(recs, s, "utility_ids_gaining_or_losing_a_site") == {5, 6, 7, 8}
    assert len(ck.count_units(recs, s, "units_gaining_or_losing_including_stayers_current_unit")) == 5


def test_a_site_listed_twice_is_refused():
    with pytest.raises(ValueError, match="twice"):
        ck.place(sites([("s", "AA", 6, "7", 1.0), ("s", "AA", 6, "7", 1.0)]), {}, {(7, "AA"): 9.0}, PANEL)


def test_a_dose_or_price_column_is_refused_but_the_in_dose_flag_is_not():
    s = sites([("s", "AA", 6, "7", 1.0)]).assign(res_price=1.0)
    with pytest.raises(ValueError, match="no dose, price or estimate"):
        ck.place(s, {}, {(7, "AA"): 9.0}, PANEL)
    ck.refuse(invented_inventory(), "the inventory")


# ---- the checks can fail (breaks made in the test process, not in the code) --------------------------------------

def test_breaking_the_order_is_caught(monkeypatch):
    """Make the sort ascending inside this test process: the tie and size test then fails."""
    real = pd.DataFrame.sort_values

    def ascending(self, by, ascending=True, **kw):
        return real(self, by, ascending=True, **kw)
    monkeypatch.setattr(pd.DataFrame, "sort_values", ascending)
    with pytest.raises(AssertionError):
        test_descending_size_with_ties_by_site_id()


def test_breaking_the_capacity_input_is_caught(monkeypatch):
    """Make capacity_from_sales read every year (the pre-2020 year included): the capacity test fails."""
    monkeypatch.setattr(ck, "SALES_FROM_YEAR", 2000)
    with pytest.raises(AssertionError):
        test_capacity_is_the_largest_annual_retail_sales_2020_to_2025()


def test_breaking_the_panel_filter_is_caught(monkeypatch):
    """Hand place a panel set that also holds the off-panel unit 3: the off-panel test fails."""
    monkeypatch.setattr(sys.modules[__name__], "PANEL", PANEL | {(3, "AA")})
    with pytest.raises(AssertionError):
        test_panel_units_only_and_off_the_panel_never_chosen()
