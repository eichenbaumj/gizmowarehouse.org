"""Treatment and assignment rules for the reconciliation rows (pipeline/analysis/reconciliation_treatment.py), on
invented inputs only. Nothing here reads data/.

An invented map where the three assignment rules disagree; first years under "above 5 MW" counted by site and by
county-year, by hand; the 2% dose rule at its edge; cumulative MW by hand, with a multi-state utility's total entered in
each of its states; and no builder opens a file.
"""
from __future__ import annotations

import builtins
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import reconciliation_treatment as rt  # noqa: E402

KEY = rt.KEY
# The retail-first priority with wholesale-only sites unassigned: row U's rule under D-107, no row's rule since D-109.
# Kept so that the mechanics of the priority stay tested.
RETAIL_FIRST = {"priority": "retail_first", "wholesale_only_sites": "unassigned"}

# Invented map, state AA. Panel units: 1 (an investor-owned utility, large), 2 (a co-op inside it), 3 and 4 (two
# municipal utilities with polygons of identical area), 7 (a utility in AA and BB). Reported id 5 is utility 1's
# predecessor; 9 is a wholesale-only territory with no panel unit.
UNITS = pd.DataFrame({"utility_id_eia": [1, 2, 3, 4, 7, 7], "state": ["AA", "AA", "AA", "AA", "AA", "BB"]})
REPORTED = pd.DataFrame({"utility_id_reported": [1, 2, 3, 4, 5, 7, 7], "state": ["AA", "AA", "AA", "AA", "AA", "AA", "BB"],
                         "utility_id_eia": [1, 2, 3, 4, 1, 7, 7]})


def sites() -> pd.DataFrame:
    return pd.DataFrame({
        "fid": ["s1", "s2", "s3", "s4", "s5", "s6"],
        "state": ["AA", "AA", "AA", "AA", "AA", "AA"],
        "energized_year": [2012.0, 2011.0, 2011.0, 2013.0, np.nan, 2016.0],
        "mw_full": [6.0, 4.0, 3.0, 50.0, 20.0, 5.0],
        "mw_full_raw": [4.5, 4.0, 3.0, 50.0, 20.0, 8.0],
        "is_crypto": [False, False, False, True, False, False],
        "utility_id_eia": [1.0, 1.0, 2.0, 1.0, 7.0, np.nan],
        "utility_assign": ["verified_by_hand", "unique", "smallest_polygon", "unique", "unique", "none"],
    })


SITE_COUNTY = pd.DataFrame({"fid": ["s1", "s2", "s3", "s4", "s5", "s6"], "county": ["C1", "C1", "C1", "C1", "C2", None]})
TERRITORY = pd.DataFrame({
    "utility_id_reported": [5, 2, 1, 7, 9, 3],
    "state": ["AA"] * 6,
    "county": ["C1", "C1", "C2", "C2", "C2", "C1"],
    "year": [2010, 2010, 2010, 2010, 2010, 2015],
})
INCIDENCE = pd.DataFrame({
    "fid": ["s1", "s1", "s1", "s2", "s3", "s3", "s5"],
    "utility_id_reported": [1, 2, 9, 9, 3, 4, 7],
    "area": [1000.0, 50.0, 10.0, 10.0, 20.0, 20.0, 300.0],
    "type_class": ["retail", "retail", "wholesale_only", "wholesale_only", "retail", "retail", "retail"],
})


def units_of(a: rt.Assignment, fid: str) -> set:
    t = a.table[a.table.fid == fid]
    return set(zip(t.utility_id_eia, t.state))


def test_the_three_rules_disagree_on_one_map():
    s = sites()
    ver = rt.assign_verified(s)
    ct = rt.assign_county_touch(s, SITE_COUNTY, TERRITORY, REPORTED, territory_vintage=2010)
    poly = rt.assign_polygon_smallest(s, INCIDENCE, REPORTED, priority="retail_first",
                                      wholesale_only_sites="smallest_wholesale_only")
    # s1: verified on the investor-owned utility; every utility touching C1 in 2010 (5 -> 1, and 2); the smallest
    # RETAIL polygon is the co-op's (the wholesale-only polygon 9 is smaller but comes after retail ones).
    assert units_of(ver, "s1") == {(1, "AA")}
    assert units_of(ct, "s1") == {(1, "AA"), (2, "AA")}
    assert units_of(poly, "s1") == {(2, "AA")}
    # s2 lies only in the wholesale-only polygon 9, which is no panel unit: unassigned under the polygon rule, listed
    assert units_of(poly, "s2") == set()
    assert "not a panel unit" in poly.unassigned.set_index("fid").reason["s2"]
    # s3 sits in two polygons of identical area: no tie rule, so unassigned with both ids listed
    assert "tie in area between polygons [3, 4]" in poly.unassigned.set_index("fid").reason["s3"]
    # the crypto mine is in no rule
    for a in (ver, ct, poly):
        assert "s4" not in set(a.table.fid)
        assert "not a data center" in a.unassigned.set_index("fid").reason["s4"]
    # s5 in C2: 1 and 7 are panel units, 9 is not; s6 has no county and no verified utility
    assert units_of(ct, "s5") == {(1, "AA"), (7, "AA")}
    assert "no county" in ct.unassigned.set_index("fid").reason["s6"]
    assert "no utility" in ver.unassigned.set_index("fid").reason["s6"]
    cmp = rt.compare_assignments(ver, poly).set_index("fid")
    assert not cmp.loc["s1", "agree"] and cmp.loc["s5", "agree"]


def test_a_site_inside_only_wholesale_only_polygons_is_an_explicit_choice():
    # the paper: "prioritizing retail providers over wholesale-only territories" (p. 5, Sec. 2.1); what happens when no
    # retail polygon contains the site is not stated, so it has no default
    s = sites()
    with pytest.raises(TypeError):
        rt.assign_polygon_smallest(s, INCIDENCE, REPORTED)
    with pytest.raises(TypeError):
        rt.assign_polygon_smallest(s, INCIDENCE, REPORTED, priority="retail_first")
    with pytest.raises(ValueError):
        rt.assign_polygon_smallest(s, INCIDENCE, REPORTED, priority="retail_first", wholesale_only_sites="largest")
    inc = pd.concat([INCIDENCE, pd.DataFrame({"fid": ["s2"], "utility_id_reported": [5], "area": [400.0],
                                              "type_class": ["wholesale_only"]})], ignore_index=True)
    # s2 lies in wholesale-only polygons 9 (10 km2, no panel unit) and 5 (400 km2, utility 1's predecessor)
    small = rt.assign_polygon_smallest(s, inc, REPORTED, priority="retail_first",
                                       wholesale_only_sites="smallest_wholesale_only")
    assert units_of(small, "s2") == set() and "not a panel unit" in small.unassigned.set_index("fid").reason["s2"]
    none = rt.assign_polygon_smallest(s, inc, REPORTED, **RETAIL_FIRST)
    assert units_of(none, "s2") == set()
    assert none.unassigned.set_index("fid").reason["s2"] == "only wholesale-only polygons contain the site"
    # a retail polygon present always wins, whatever the choice: s1 goes to the co-op either way
    assert units_of(small, "s1") == units_of(none, "s1") == {(2, "AA")}
    # s6 is in no polygon: listed, never placed
    assert "no territory polygon contains the site" in none.unassigned.set_index("fid").reason["s6"]
    inc2 = inc[inc.utility_id_reported != 9]
    only5 = rt.assign_polygon_smallest(s, inc2, REPORTED, priority="retail_first",
                                       wholesale_only_sites="smallest_wholesale_only")
    assert units_of(only5, "s2") == {(1, "AA")}


def test_each_rows_polygon_rule_and_its_name():
    """Since D-109 rows U and C apply one rule: the smallest of every containing polygon, the type not read, named
    "polygon_smallest_any_type" (row C's from Scalera S1.1 p. 25; row U's our labelled approximation). The retail-first
    priority stays available under its own name and is no row's rule. An old table with is_retail and no type_class is
    refused in words under the retail-first priority."""
    s = sites()
    u = rt.assign_polygon_smallest(s, INCIDENCE, REPORTED, **rt.ROW_U_POLYGON)
    c = rt.assign_polygon_smallest(s, INCIDENCE.drop(columns="type_class"), REPORTED, **rt.ROW_C_POLYGON)
    rf = rt.assign_polygon_smallest(s, INCIDENCE, REPORTED, **RETAIL_FIRST)
    assert (u.rule, c.rule, rf.rule) == ("polygon_smallest_any_type", "polygon_smallest_any_type",
                                         "polygon_smallest_retail_first")
    assert rt.ROW_U_POLYGON == rt.ROW_C_POLYGON == {"priority": "none", "wholesale_only_sites": None}
    # s1: with no priority the smallest polygon is 9 (10 km2), which is no panel unit, so both rows leave s1 unassigned
    # and listed; the retail-first priority would have given the co-op (2, 50 km2)
    assert units_of(u, "s1") == units_of(c, "s1") == set() and units_of(rf, "s1") == {(2, "AA")}
    assert "not a panel unit" in u.unassigned.set_index("fid").reason["s1"]
    assert rf.unassigned.set_index("fid").reason["s2"] == "only wholesale-only polygons contain the site"
    assert len(u.depends_on_ambiguous) == len(c.depends_on_ambiguous) == 0
    old = INCIDENCE.drop(columns="type_class").assign(is_retail=True)
    with pytest.raises(ValueError, match="no type_class"):
        rt.assign_polygon_smallest(s, old, REPORTED, **RETAIL_FIRST)
    with pytest.raises(ValueError, match="plays no part"):
        rt.assign_polygon_smallest(s, INCIDENCE, REPORTED, priority="none", wholesale_only_sites="unassigned")
    with pytest.raises(ValueError, match="type_class must be one of"):
        rt.assign_polygon_smallest(s, INCIDENCE.assign(type_class="retail_maybe"), REPORTED, **RETAIL_FIRST)


AMB_SITES = pd.DataFrame({"fid": ["a", "b", "c", "d", "e"], "state": ["AA"] * 5, "energized_year": [2016.0] * 5,
                          "mw_full": [10.0] * 5, "is_crypto": [False] * 5, "utility_id_eia": [1.0] * 5})
AMB_INCIDENCE = pd.DataFrame({
    "fid":                 ["a",       "a",         "b",      "b",         "c",         "d",         "d",      "e"],
    "utility_id_reported": [1,         2,           2,        1,           7,           5,           1,        3],
    "area":                [1000.0,    50.0,        50.0,     1000.0,      300.0,       400.0,       1000.0,   20.0],
    "type_class":          ["retail",  "ambiguous", "retail", "ambiguous", "ambiguous", "ambiguous", "retail", "retail"],
})


def test_an_ambiguous_polygon_never_decides_a_site_by_a_guess():
    """a: retail 1 (1000) and ambiguous 2 (50): classed retail, 2 wins; classed wholesale-only, 1 wins. Listed, not
    assigned. b: retail 2 (50) and ambiguous 1 (1000): 2 either way, assigned. c: ambiguous 7 alone: 7 or no unit,
    listed. d: ambiguous 5 (400, utility 1's predecessor) and retail 1 (1000): utility 1 either way, assigned (the
    comparison is on the panel unit, not the polygon id). e: no ambiguity. Under row C's rule the type is not read and
    no site depends on it."""
    u = rt.assign_polygon_smallest(AMB_SITES, AMB_INCIDENCE, REPORTED, **RETAIL_FIRST)
    assert units_of(u, "b") == {(2, "AA")} and units_of(u, "d") == {(1, "AA")} and units_of(u, "e") == {(3, "AA")}
    assert units_of(u, "a") == set() and units_of(u, "c") == set()
    dep = u.depends_on_ambiguous.set_index("fid")
    assert sorted(dep.index) == ["a", "c"]
    assert dep.possible_units["a"] == ["1:AA", "2:AA"] and dep.possible_units["c"] == ["7:AA", "none"]
    assert dep.ambiguous_polygons["a"] == [2]
    why = u.unassigned.set_index("fid").reason
    assert "depends on how the ambiguous polygon(s) [2] are classed" in why["a"] and "not assigned by a guess" in why["c"]
    assert any("2 sites are not assigned" in n for n in u.notes)
    # the treatment built on it carries the dependent sites to the step
    sy = pd.DataFrame({"fid": list("abcde"), "year": [2016] * 5, "mw": [10.0] * 5})
    tr = rt.cumulative_mw(u, UNITS, range(2015, 2018), "site_year_load", site_year=sy)
    assert tr.depends_on_ambiguous == ["a", "c"] and any("2 sites are not assigned" in n for n in tr.notes)
    c = rt.assign_polygon_smallest(AMB_SITES, AMB_INCIDENCE, REPORTED, **rt.ROW_C_POLYGON)
    assert len(c.depends_on_ambiguous) == 0
    assert units_of(c, "a") == {(2, "AA")} and units_of(c, "c") == {(7, "AA")}


def test_territory_vintage_is_an_explicit_choice():
    s = sites()
    with pytest.raises(TypeError):
        rt.assign_county_touch(s, SITE_COUNTY, TERRITORY, REPORTED)      # no default
    with pytest.raises(ValueError):
        rt.assign_county_touch(s, SITE_COUNTY, TERRITORY, REPORTED, territory_vintage="latest")
    union = rt.assign_county_touch(s, SITE_COUNTY, TERRITORY, REPORTED, territory_vintage="union_of_all_years")
    assert units_of(union, "s1") == {(1, "AA"), (2, "AA"), (3, "AA")}   # 3 lists C1 in 2015 only
    terr = pd.concat([TERRITORY, pd.DataFrame({"utility_id_reported": [2], "state": ["AA"], "county": ["C1"], "year": [2012]})])
    entry = rt.assign_county_touch(s, SITE_COUNTY, terr, REPORTED, territory_vintage="year_of_entry")
    # s1 starts in 2012, when only the co-op lists C1; s2 and s3 start in 2011, a year the table does not have
    assert units_of(entry, "s1") == {(2, "AA")}
    assert set(entry.unassigned.fid) >= {"s2", "s3", "s5"}


def test_first_year_above_5mw_by_site_and_by_county_year_by_hand():
    s = sites()
    ver = rt.assign_verified(s)
    by_site = rt.first_year_above_size(s, ver, UNITS, size_column="mw_full", counting="site").table.set_index(KEY)
    # utility 1: s1 6 MW in 2012 is the first site above 5; s2 (4 MW, 2011) is not; s4 is crypto
    assert by_site.first_year[(1, "AA")] == 2012
    assert np.isnan(by_site.first_year[(2, "AA")])          # s3 is 3 MW
    assert np.isnan(by_site.first_year[(7, "AA")])          # s5 has no start year: listed, never treats
    raw = rt.first_year_above_size(s, ver, UNITS, size_column="mw_full_raw", counting="site").table.set_index(KEY)
    assert np.isnan(raw.first_year[(1, "AA")])              # s1 is 4.5 MW before anchoring
    cy = rt.first_year_above_size(s, ver, UNITS, size_column="mw_full", counting="county_year_new_capacity",
                                  site_county=SITE_COUNTY).table.set_index(KEY)
    assert cy.first_year[(1, "AA")] == 2012                 # its own sites in C1: 2011 has 4 MW, 2012 has 6
    ct = rt.assign_county_touch(s, SITE_COUNTY, TERRITORY, REPORTED, territory_vintage=2010)
    cyc = rt.first_year_above_size(s, ct, UNITS, size_column="mw_full", counting="county_year_new_capacity",
                                   site_county=SITE_COUNTY).table.set_index(KEY)
    # every utility touching C1 carries all of C1's sites: 2011 has 4 + 3 = 7 MW, above 5
    assert cyc.first_year[(1, "AA")] == 2011 and cyc.first_year[(2, "AA")] == 2011
    sitec = rt.first_year_above_size(s, ct, UNITS, size_column="mw_full", counting="site").table.set_index(KEY)
    assert sitec.first_year[(2, "AA")] == 2012              # by site, the co-op is treated by s1 in 2012
    excl = rt.first_year_above_size(s, ver, UNITS, size_column="mw_full", counting="site").excluded_sites
    assert "no start year" in excl.set_index("fid").reason["s5"]


def test_exactly_5_mw_is_not_above():
    s = sites()
    s.loc[s.fid == "s1", "mw_full"] = 5.0
    ver = rt.assign_verified(s)
    t = rt.first_year_above_size(s, ver, UNITS, size_column="mw_full", counting="site").table.set_index(KEY)
    assert np.isnan(t.first_year[(1, "AA")])


def test_size_and_counting_have_no_defaults():
    s, ver = sites(), rt.assign_verified(sites())
    with pytest.raises(TypeError):
        rt.first_year_above_size(s, ver, UNITS)
    with pytest.raises(ValueError):
        rt.first_year_above_size(s, ver, UNITS, size_column="mw", counting="site")
    with pytest.raises(ValueError):
        rt.first_year_above_size(s, ver, UNITS, size_column="mw_full", counting="county_year_new_capacity")


def test_first_year_at_the_2pct_dose_at_its_edge():
    dose = pd.DataFrame({"utility_id_eia": [1, 1, 1, 2, 2, 3], "state": ["AA"] * 6,
                         "year": [2013, 2014, 2015, 2014, 2015, 2015], "dose": [0.0199, 0.02, 0.5, 0.019999, np.nan, np.nan]})
    t = rt.first_year_at_dose(dose, UNITS, 0.02)
    f = t.table.set_index(KEY).first_year
    assert f[(1, "AA")] == 2014 and np.isnan(f[(2, "AA")]) and np.isnan(f[(3, "AA")])
    assert any("no non-missing dose" in n for n in t.notes)


def test_cumulative_mw_by_hand_and_the_multi_state_rule():
    s = sites()
    s.loc[s.fid == "s5", "energized_year"] = 2015.0
    ver = rt.assign_verified(s)
    years = range(2010, 2018)
    site_year = pd.DataFrame({"fid": ["s1", "s1", "s2", "s5", "s5", "s4"], "year": [2012, 2013, 2013, 2015, 2016, 2013],
                              "mw": [2.0, 6.0, 4.0, 10.0, 20.0, 50.0], "crypto": [False, False, False, False, False, True]})
    t = rt.cumulative_mw(ver, UNITS, years, "site_year_load", site_year=site_year).table.set_index(KEY + ["year"]).mw
    assert t[(1, "AA", 2012)] == 2.0 and t[(1, "AA", 2013)] == 10.0 and t[(1, "AA", 2014)] == 0.0
    # utility 7's AA site counts in AA AND in BB, the same total in each
    assert t[(7, "AA", 2016)] == 20.0 and t[(7, "BB", 2016)] == 20.0 and t[(7, "BB", 2015)] == 10.0
    assert t[(2, "AA", 2013)] == 0.0 and t[(3, "AA", 2017)] == 0.0       # crypto row never counted
    full = rt.cumulative_mw(ver, UNITS, years, "full_size_from_energized_year", sites=s).table.set_index(KEY + ["year"]).mw
    assert full[(1, "AA", 2011)] == 4.0 and full[(1, "AA", 2012)] == 10.0 and full[(1, "AA", 2017)] == 10.0
    assert full[(2, "AA", 2011)] == 3.0 and full[(7, "BB", 2015)] == 20.0 and full[(7, "BB", 2014)] == 0.0
    assert len(full) == len(UNITS) * len(years)
    with pytest.raises(TypeError):
        rt.cumulative_mw(ver, UNITS, years)                                # how operating is dated: no default
    ct = rt.assign_county_touch(s, SITE_COUNTY, TERRITORY, REPORTED, territory_vintage=2010)
    with pytest.raises(ValueError):
        rt.cumulative_mw(ct, UNITS, years, "site_year_load", site_year=site_year)   # several units per site


def test_no_builder_opens_a_file(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a builder tried to read a file")
    for mod, name in ((builtins, "open"), (pd, "read_parquet"), (pd, "read_csv"), (np, "load")):
        monkeypatch.setattr(mod, name, refuse)
    s = sites()
    ver = rt.assign_verified(s)
    rt.assign_county_touch(s, SITE_COUNTY, TERRITORY, REPORTED, territory_vintage=2010)
    rt.assign_polygon_smallest(s, INCIDENCE, REPORTED, **rt.ROW_U_POLYGON)
    rt.assign_polygon_smallest(s, INCIDENCE, REPORTED, **rt.ROW_C_POLYGON)
    rt.first_year_above_size(s, ver, UNITS, size_column="mw_full", counting="site")
    rt.cumulative_mw(ver, UNITS, range(2010, 2012), "full_size_from_energized_year", sites=s)


def test_an_exact_area_tie_is_listed_under_row_cs_rule_too():
    """A site in two polygons of identical smallest area (as osm:way/571010571 is on the real layer) is not placed by
    either rule: listed with both ids, whatever larger polygons also contain it."""
    sites_ = AMB_SITES.iloc[:1].assign(fid="t")
    inc = pd.DataFrame({"fid": ["t"] * 4, "utility_id_reported": [3, 4, 2, 1], "area": [94.4, 94.4, 3280.0, 12904.0],
                        "type_class": ["ambiguous"] * 4})
    c = rt.assign_polygon_smallest(sites_, inc, REPORTED, **rt.ROW_C_POLYGON)
    assert units_of(c, "t") == set() and "tie in area between polygons [3, 4]" in c.unassigned.set_index("fid").reason["t"]
    u = rt.assign_polygon_smallest(sites_, inc, REPORTED, **rt.ROW_U_POLYGON)
    assert units_of(u, "t") == set() and "tie in area between polygons [3, 4]" in u.unassigned.set_index("fid").reason["t"]
    assert len(u.depends_on_ambiguous) == 0
    rf = rt.assign_polygon_smallest(sites_, inc, REPORTED, **RETAIL_FIRST)
    assert units_of(rf, "t") == set() and list(rf.depends_on_ambiguous.fid) == ["t"]


# ---------------------------------------------------------------------------------------------------------------------
# Row U's U0 under Joe's ruling of 2026-11-19 (D-109): the smallest containing polygon over every polygon, the type not
# read; the list of the sites associated with four entity types; the coincidence with row C's rule.
# ---------------------------------------------------------------------------------------------------------------------
# Invented typed incidence, state AA. Polygon ids map to panel units through REPORTED (9 is no panel unit).
#   f1: inside FEDERAL polygon 2 (5 km2) and INVESTOR OWNED 1 (1000): assigned to 2, a FEDERAL polygon -> listed
#   f2: inside WHOLESALE POWER MARKETER 9 (900) and COOPERATIVE 3 (40): assigned to 3; lies in a WPM polygon only
#   f3: inside STATE 4 (30) and STATE 7 (30): an exact tie, not broken, listed apart
#   f4: inside MUNICIPAL MKTG AUTHORITY 9 (8) alone: assigned to polygon 9, which is no panel unit -> listed, not mapped
#   f5: inside INVESTOR OWNED 1 (1000) only
#   f6: a crypto mine inside FEDERAL 2: never listed
TYPED_SITES = pd.DataFrame({"fid": ["f1", "f2", "f3", "f4", "f5", "f6", "f7"], "state": ["AA"] * 7,
                            "energized_year": [2016.0] * 7, "mw_full": [10.0] * 7,
                            "is_crypto": [False, False, False, False, False, True, False],
                            "utility_id_eia": [1.0] * 7})
TYPED = pd.DataFrame({
    "fid":                 ["f1",      "f1",             "f2",                       "f2",          "f3",    "f3",
                            "f4",                       "f5",             "f6"],
    "utility_id_reported": [2,         1,                9,                          3,             4,       7,
                            9,                          1,                2],
    "area":                [5.0,       1000.0,           900.0,                      40.0,          30.0,    30.0,
                            8.0,                        1000.0,           5.0],
    "TYPE":                ["FEDERAL", "INVESTOR OWNED", "WHOLESALE POWER MARKETER", "COOPERATIVE", "STATE", "STATE",
                            "MUNICIPAL MKTG AUTHORITY", "INVESTOR OWNED", "FEDERAL"],
    # type_class is carried to show that row U's rule does not read it: every class is a different nonsense
    "type_class":          ["wholesale_only", "retail", "retail", "wholesale_only", "ambiguous", "retail",
                            "retail", "ambiguous", "retail"],
})


def test_row_u_rule_ignores_the_class():
    """The same assignment whatever type_class says, and with type_class removed altogether."""
    a = rt.assign_polygon_smallest(TYPED_SITES, TYPED, REPORTED, **rt.ROW_U_POLYGON)
    flipped = TYPED.assign(type_class=TYPED.type_class.map({"retail": "wholesale_only", "wholesale_only": "retail",
                                                            "ambiguous": "retail"}))
    b = rt.assign_polygon_smallest(TYPED_SITES, flipped, REPORTED, **rt.ROW_U_POLYGON)
    c = rt.assign_polygon_smallest(TYPED_SITES, TYPED.drop(columns=["type_class", "TYPE"]), REPORTED, **rt.ROW_U_POLYGON)
    for x in (b, c):
        assert x.table.equals(a.table) and x.unassigned.equals(a.unassigned)
    assert units_of(a, "f1") == {(2, "AA")} and units_of(a, "f2") == {(3, "AA")}   # smallest polygon wins, any type
    assert len(a.depends_on_ambiguous) == 0


def test_the_entity_type_list_assigned_and_lying_in_any():
    a = rt.assign_polygon_smallest(TYPED_SITES, TYPED, REPORTED, **rt.ROW_U_POLYGON)
    lst = rt.entity_type_list(TYPED_SITES, TYPED, a)
    bt = lst["by_type"]
    assert lst["types"] == ["FEDERAL", "STATE", "MUNICIPAL MKTG AUTHORITY", "WHOLESALE POWER MARKETER"]
    # a site in a small polygon of a listed type is assigned to it and is on the list (the crypto mine f6 is not)
    assert bt["FEDERAL"] == {"assigned_fids": ["f1"], "assigned_count": 1, "lying_in_any_count": 1,
                             "assigned_and_mapped_to_a_panel_unit": 1}
    # a site in a LARGE polygon of a listed type and a SMALLER polygon of another type goes to the smaller one and is
    # counted only in "lying in any"
    assert bt["WHOLESALE POWER MARKETER"]["assigned_fids"] == [] and bt["WHOLESALE POWER MARKETER"]["lying_in_any_count"] == 1
    # the exact tie is listed apart and not broken: no assigned polygon, so not on the STATE list, but lying in it
    assert bt["STATE"]["assigned_fids"] == [] and bt["STATE"]["lying_in_any_count"] == 1
    assert lst["ties_not_broken"] == {"f3": {"tied_polygon_ids": [4, 7], "types_of_the_tied_polygons": ["STATE"]}}
    assert "tie in area between polygons [4, 7]" in a.unassigned.set_index("fid").reason["f3"]
    # assigned to a listed type's polygon whose utility is no panel unit: listed, not mapped
    assert bt["MUNICIPAL MKTG AUTHORITY"]["assigned_fids"] == ["f4"]
    assert bt["MUNICIPAL MKTG AUTHORITY"]["assigned_and_mapped_to_a_panel_unit"] == 0
    assert lst["listed_sites_any_type"] == 2 and lst["listed_sites_mapped_to_a_panel_unit"] == 1
    assert "not a verified wholesale classification" in lst["label"] and "decides no assignment" in lst["label"]
    # the list decides no assignment: the assignment is the same with the list computed or not, and with the TYPE
    # values all renamed
    renamed = rt.entity_type_list(TYPED_SITES, TYPED.assign(TYPE="NOT AVAILABLE"), a)
    assert all(d["assigned_count"] == 0 and d["lying_in_any_count"] == 0 for d in renamed["by_type"].values())
    with pytest.raises(ValueError, match="TYPE"):
        rt.entity_type_list(TYPED_SITES, TYPED.drop(columns="TYPE"))


def test_the_labels_carry_the_rulings_words():
    lab = rt.ROW_U_POLYGON_LABEL
    assert "priority to retail providers over wholesale-only territories" in lab
    assert "TYPE field does not establish which polygons are retail, so that priority is not applied" in lab
    assert "exact reproduction of the paper's assignment is unavailable" in lab
    assert "ours" in lab and "not the paper's assignment" in lab and "D-109" in lab
    assert "the tie is not broken" in lab and "not independent validation" in lab
    assert "not independent validation" in rt.ROW_U_C_COINCIDENCE and "same rule" in rt.ROW_U_C_COINCIDENCE
    assert "No assigned site is not proof of no facility" in rt.MISSING_COVERAGE_QUALIFICATION
    assert "never evidence of no treatment" in rt.MISSING_COVERAGE_QUALIFICATION


def test_u0_and_c0_assign_identically_site_by_site_and_a_difference_is_found():
    """The two rows' assignments are identical by construction; identical_site_by_site counts it and can find a
    difference (an assignment under the retail-first priority differs on f1)."""
    u = rt.assign_polygon_smallest(TYPED_SITES, TYPED, REPORTED, **rt.ROW_U_POLYGON)
    c = rt.assign_polygon_smallest(TYPED_SITES, TYPED.drop(columns="type_class"), REPORTED, **rt.ROW_C_POLYGON)
    dc = TYPED_SITES.fid[~TYPED_SITES.is_crypto]
    ident = rt.identical_site_by_site(u, c, dc)
    assert ident == {"sites_compared": 6, "identical": 6, "differ": [], "placed_on_the_same_unit": 3,
                     "left_unplaced_for_the_same_reason": 3}
    other = TYPED.copy()
    other.loc[(other.fid == "f1") & (other.utility_id_reported == 2), "area"] = 5000.0   # f1 now goes to 1
    v = rt.assign_polygon_smallest(TYPED_SITES, other, REPORTED, **rt.ROW_U_POLYGON)
    assert rt.identical_site_by_site(u, v, dc)["differ"] == ["f1"]
