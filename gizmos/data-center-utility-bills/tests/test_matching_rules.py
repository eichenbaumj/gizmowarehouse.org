"""The matching rules, opt-in in design.build: own utility (D-54, ruling 2), common ownership (D-58, rules 2.2 and 2.3),
full-window usability (D-58, rule 6.3), and the support rule (D-54, ruling 2). Synthetic data only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import design, ownership  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
FUEL = {"AA": 0, "AB": 0, "BB": 1, "BC": 1}
COHORT = 2015
WINDOW = list(range(COHORT - ps.PRE, COHORT + ps.POST + 1))          # 2009 to 2018
IOU, COOP, PUBLIC = "investor_owned", "cooperative", "public"


def world(hosts, comps, region=None, cohort=COHORT, seed=3):
    """Made-up quantities. hosts and comps are lists of (id, state, residential customers, ownership class).

    region(key, year) gives a unit's market region in a year; the default puts everyone in "West".
    """
    units = list(hosts) + list(comps)
    region = region or (lambda key, year: "West")
    q = pd.DataFrame([(u, st, y, own, size, 1.0, True) for u, st, size, own in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor"])
    regions = pd.DataFrame([(u, st, y, region((u, st), y)) for u, st, _, _ in units for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(seed)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in FUEL for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    treated = pd.DataFrame({"utility_id_eia": [u for u, *_ in hosts], "state": [st for _, st, *_ in hosts], "cohort": [cohort] * len(hosts)})
    clean = pd.DataFrame([(u, st) for u, st, *_ in comps], columns=KEY)
    return treated, clean, q, regions, dd


def ladder(first_id, n, state="AA", own=COOP, start=10_050, step=100):
    """n comparison utilities ever further from a host of 10,000 customers, in id order."""
    return [(first_id + i, state, start + step * i, own) for i in range(n)]


def table(rows):
    cols = ownership.COLUMNS
    base = {"name": "x", "how_it_changed": "", "source_url": "https://example.org/filing", "source_kind": "sec_filing",
            "quote": "a quoted line", "date_opened": "2026-11-15"}
    t = pd.DataFrame([{**base, "state": "", **r} for r in rows], columns=cols)
    return t.astype({"utility_id_eia": int, "from_year": int, "to_year": int})


def keys_of(d, i=0):
    return [tuple(k) for k in d.hosts.match_keys.iloc[i]]


def expected_nearest(host_size, comps, k=ps.MATCH_K):
    sizes = np.log(np.array([c[2] for c in comps], dtype=float))
    order = np.argsort(np.abs(sizes - np.log(host_size)), kind="stable")[:k]
    return [(comps[i][0], comps[i][1]) for i in order]


# ---- defaults ------------------------------------------------------------------------------------

def test_build_with_no_new_arguments_matches_the_ten_nearest_and_adds_no_column():
    comps = ladder(10, 14)[::-1] + [(1, "BB", 10_000, COOP)]       # own utility in another state is the nearest of all
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, COOP)], comps)
    d = design.build(treated, clean, q, regions, FUEL, dd)
    assert keys_of(d) == expected_nearest(10_000, comps)
    assert keys_of(d)[0] == (1, "BB")                                 # today's behaviour: nothing is excluded
    assert list(d.hosts.columns) == ["key", "cohort", "row", "state", "region", "matches", "match_keys", "pool_in_the_reference_year"]
    assert d.hosts.pool_in_the_reference_year.iloc[0] == 15


# ---- own utility (D-54, ruling 2) ----------------------------------------------------------------

@pytest.mark.parametrize("how", ["flag", "empty_table"])
def test_a_unit_of_the_hosts_own_utility_is_never_matched_and_the_next_nearest_enters(how):
    comps = [(1, "BB", 10_000, COOP)] + ladder(10, 12)
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, COOP)], comps)
    kw = {"no_own_utility": True} if how == "flag" else {"ownership": ownership.load()}
    d = design.build(treated, clean, q, regions, FUEL, dd, **kw)
    got = keys_of(d)
    assert (1, "BB") not in got and len(got) == 10
    assert got == [(10 + i, "AA") for i in range(10)]
    assert d.hosts.excluded_from_its_pool.iloc[0] == [{"utility": "1:BB", "why": ownership.OWN_UTILITY}]
    assert d.hosts.pool_in_the_reference_year.iloc[0] == 12           # the eligible pool, after the exclusion


# ---- common ownership with spells (D-58, rule 2.3) -----------------------------------------------

def spells_world():
    host = (1, "AA", 10_000, IOU)
    comps = [(1, "BB", 10_000, IOU),                                  # the host's own utility in another state
             (20, "AA", 10_010, IOU),                                 # shares the host's parent in 2018 only
             (21, "AA", 10_020, IOU)] + ladder(30, 12, own=IOU)       # shared it until 2008, the year before the window
    rows = [{"utility_id_eia": 1, "state": "", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
            {"utility_id_eia": 20, "state": "AA", "ultimate_parent": "Q", "from_year": 2001, "to_year": 2017},
            {"utility_id_eia": 20, "state": "AA", "ultimate_parent": "P", "from_year": 2018, "to_year": 2018},
            {"utility_id_eia": 20, "state": "AA", "ultimate_parent": "Q", "from_year": 2019, "to_year": 2025},
            {"utility_id_eia": 21, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2008},
            {"utility_id_eia": 21, "state": "AA", "ultimate_parent": "R", "from_year": 2009, "to_year": 2025}]
    rows += [{"utility_id_eia": 30 + i, "state": "", "ultimate_parent": f"Own{30 + i}", "from_year": 2001, "to_year": 2025} for i in range(12)]
    return world([host], comps), table(rows)


def test_same_parent_in_one_window_year_is_excluded_and_a_spell_that_ended_before_the_window_is_not():
    (treated, clean, q, regions, dd), t = spells_world()
    assert ownership.affiliated(t, (1, "AA"), (20, "AA"), WINDOW)
    assert not ownership.affiliated(t, (1, "AA"), (21, "AA"), WINDOW)
    assert ownership.affiliated(t, (1, "AA"), (21, "AA"), [2008])
    assert ownership.affiliated(t, (1, "AA"), (1, "BB"), [])          # the same EIA id, in every year, table or no table
    d = design.build(treated, clean, q, regions, FUEL, dd, ownership=t)
    got = keys_of(d)
    assert (20, "AA") not in got and (1, "BB") not in got
    assert got[0] == (21, "AA") and len(got) == 10
    why = {e["utility"]: e["why"] for e in d.hosts.excluded_from_its_pool.iloc[0]}
    assert why == {"1:BB": ownership.OWN_UTILITY, "20:AA": ownership.SAME_PARENT}


def test_affiliates_included_readmits_the_same_parent_affiliate_but_never_the_own_utility():
    (treated, clean, q, regions, dd), t = spells_world()
    d = design.build(treated, clean, q, regions, FUEL, dd, ownership=t, affiliates_included=True)
    got = keys_of(d)
    assert got[:2] == [(20, "AA"), (21, "AA")] and (1, "BB") not in got
    assert d.hosts.excluded_from_its_pool.iloc[0] == [{"utility": "1:BB", "why": ownership.OWN_UTILITY}]


def test_a_blank_state_row_covers_every_state_of_that_id_and_spells_are_inclusive():
    t = table([{"utility_id_eia": 50, "state": "", "ultimate_parent": "P", "from_year": 2010, "to_year": 2012},
               {"utility_id_eia": 50, "state": "BB", "ultimate_parent": "S", "from_year": 2012, "to_year": 2020}])
    assert ownership.parents(t, (50, "ZZ"), [2010]) == {"P"}
    assert ownership.parents(t, (50, "BB"), [2012]) == {"P", "S"}      # the closing year: both count (rule 2.1)
    assert ownership.parents(t, (50, "BB"), [2009]) == set()
    assert ownership.company_of(t, (50, "BB"), [2012]) == "P / S"
    assert ownership.company_of(t, (50, "BB"), [2005]) == "50:BB"


# ---- fail closed (D-58, rule 2.2) ----------------------------------------------------------------

def test_an_investor_owned_candidate_with_no_row_is_not_eligible_for_an_investor_owned_host():
    host = (1, "AA", 10_000, IOU)
    comps = [(40, "AA", 10_010, IOU), (41, "AA", 10_020, PUBLIC)] + ladder(60, 12, own=COOP)
    treated, clean, q, regions, dd = world([host], comps)
    t = table([{"utility_id_eia": 1, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}])
    d = design.build(treated, clean, q, regions, FUEL, dd, ownership=t)
    got = keys_of(d)
    assert (40, "AA") not in got and got[0] == (41, "AA")            # a public unit with no row is its own owner
    assert d.hosts.excluded_from_its_pool.iloc[0] == [{"utility": "40:AA", "why": ownership.NO_ROW}]
    own = {(1, "AA"): IOU, (40, "AA"): IOU, (41, "AA"): PUBLIC}
    # a row that covers no year of the window does not count
    late = pd.concat([t, table([{"utility_id_eia": 40, "state": "AA", "ultimate_parent": "Z", "from_year": 2020, "to_year": 2025}])])
    assert ownership.ineligible_for(late, (1, "AA"), WINDOW, [(40, "AA")], own) == {(40, "AA"): ownership.NO_ROW}
    covered = pd.concat([t, table([{"utility_id_eia": 40, "state": "AA", "ultimate_parent": "Z", "from_year": 2001, "to_year": 2025}])])
    assert ownership.ineligible_for(covered, (1, "AA"), WINDOW, [(40, "AA")], own) == {}
    assert ownership.ineligible_for(t, (1, "AA"), WINDOW, [(40, "AA")], own, affiliates_included=True) == {}


def test_the_fail_closed_rule_does_not_apply_to_a_cooperative_host():
    t = ownership.load()
    own = {(2, "AA"): COOP, (40, "AA"): IOU}
    assert ownership.ineligible_for(t, (2, "AA"), WINDOW, [(40, "AA")], own) == {}
    host = (2, "AA", 10_000, COOP)
    treated, clean, q, regions, dd = world([host], [(40, "AA", 10_010, IOU)] + ladder(60, 12))
    d = design.build(treated, clean, q, regions, FUEL, dd, ownership=t)
    assert keys_of(d)[0] == (40, "AA") and d.hosts.excluded_from_its_pool.iloc[0] == []


def test_an_unknown_ownership_class_fails_loudly_when_the_rule_needs_it():
    with pytest.raises(ValueError, match="no ownership class"):
        ownership.ineligible_for(ownership.load(), (1, "AA"), WINDOW, [(40, "AA")], {(1, "AA"): IOU})


# ---- the table's source standard (D-58, rule 2.2) -------------------------------------------------

def test_the_shipped_table_loads_with_its_columns():
    t = ownership.load()
    assert list(t.columns) == ownership.COLUMNS + list(ownership.BASIS)      # the basis columns are kept (Stop 3)


@pytest.mark.parametrize("blank", ["source_url", "quote", "ultimate_parent", "date_opened", "from_year", "to_year"])
def test_load_refuses_a_row_without_its_source_or_quote(tmp_path, blank):
    good = {"utility_id_eia": "7", "state": "AA", "name": "x", "ultimate_parent": "P", "from_year": "2001", "to_year": "2025",
            "how_it_changed": "", "source_url": "https://example.org", "source_kind": "sec_filing", "quote": "q", "date_opened": "2026-11-15"}
    bad = {**good, "utility_id_eia": "8", blank: ""}
    path = tmp_path / "ownership.csv"
    pd.DataFrame([good, bad])[ownership.COLUMNS].to_csv(path, index=False)
    with pytest.raises(ValueError, match=rf"row 3 .*utility_id_eia 8.* has no {blank}"):
        ownership.load(path)


def test_load_refuses_a_spell_that_ends_before_it_starts(tmp_path):
    row = {"utility_id_eia": "7", "state": "", "name": "x", "ultimate_parent": "P", "from_year": "2010", "to_year": "2009",
           "how_it_changed": "", "source_url": "https://example.org", "source_kind": "sec_filing", "quote": "q", "date_opened": "2026-11-15"}
    path = tmp_path / "ownership.csv"
    pd.DataFrame([row])[ownership.COLUMNS].to_csv(path, index=False)
    with pytest.raises(ValueError, match="row 2 .*every state.*from_year 2010 after to_year 2009"):
        ownership.load(path)


# ---- full-window usability (D-58, rule 6.3) --------------------------------------------------------

def all_usable(units):
    return {(u, st, y) for u, st, *_ in units for y in YEARS}


def test_usable_drops_a_comparison_missing_one_window_year_and_the_next_enters():
    hosts = [(1, "AA", 10_000, COOP), (2, "AA", 10_000, COOP)]
    comps = ladder(10, 12)
    treated, clean, q, regions, dd = world(hosts, comps)
    usable = all_usable(hosts + comps) - {(10, "AA", 2012), (2, "AA", 2010), (11, "AA", 2003)}   # 2003 is outside the window
    d = design.build(treated, clean, q, regions, FUEL, dd, usable=usable)
    assert list(d.hosts.key) == [(1, "AA")]
    assert keys_of(d) == [(11 + i, "AA") for i in range(10)]
    assert d.dropped == [{"utility": "2:AA", "cohort": COHORT, "why": design.NOT_USABLE}]
    assert "rule 6.3" in design.NOT_USABLE


def test_usable_none_is_todays_design_and_the_sales_mask_as_usable_reproduces_it():
    hosts = [(1, "AA", 10_000, COOP), (2, "BB", 12_000, COOP)]
    comps = ladder(10, 8) + ladder(30, 8, state="BB", start=11_000)
    treated, clean, q, regions, dd = world(hosts, comps)
    q.loc[(q.utility_id_eia == 12) & (q.year == 2011), "res_mwh"] = 0.0         # no residential sales in one window year
    a = design.build(treated, clean, q, regions, FUEL, dd)
    b = design.build(treated, clean, q, regions, FUEL, dd, usable=None)
    pd.testing.assert_frame_equal(a.hosts, b.hosts)
    assert a.dropped == b.dropped and all(a.windows[g].keys == b.windows[g].keys for g in a.windows)
    assert (12, "AA") not in keys_of(a)
    mask = {(int(u), s, int(y)) for u, s, y in q[q.meets_size_floor & (q.res_mwh > 0)][KEY + ["year"]].itertuples(index=False)}
    c = design.build(treated, clean, q, regions, FUEL, dd, usable=mask)
    pd.testing.assert_frame_equal(a.hosts, c.hosts)


# ---- the support rule (D-54, ruling 2) -------------------------------------------------------------

def test_a_host_with_nine_eligible_in_its_region_does_not_keep_its_place():
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, COOP)], ladder(10, 9))
    d = design.build(treated, clean, q, regions, FUEL, dd)
    r = design.support_rule(d).iloc[0]
    assert r.pool_in_the_reference_year == 9 and not r.keeps_its_place
    assert "9 eligible in its region in the reference year" in r.why_not


def test_seven_of_ten_in_region_in_event_year_3_does_not_keep_its_place():
    movers = {(10, "AA"), (11, "AA"), (12, "AA")}
    region = lambda key, year: "East" if key in movers and year == COHORT + 3 else "West"  # noqa: E731
    hosts = [(1, "AA", 10_000, COOP), (2, "AA", 20_000, COOP)]
    comps = ladder(10, 12) + ladder(40, 12, start=20_050)
    treated, clean, q, regions, dd = world(hosts, comps, region=region)
    d = design.build(treated, clean, q, regions, FUEL, dd)
    r = design.support_rule(d).set_index(["utility_id_eia", "state"])
    one, two = r.loc[(1, "AA")], r.loc[(2, "AA")]
    assert one.pool_in_the_reference_year >= 10
    assert (one.matched_in_region_event_year_2, one.matched_in_region_event_year_3) == (10, 7)
    assert not one.keeps_its_place and "7 of its 10 matched in its region in event year 3" in one.why_not
    assert two.keeps_its_place and two.why_not == ""


def test_the_support_rule_reads_the_pool_after_exclusions():
    comps = [(1, "BB", 10_000, COOP)] + ladder(10, 9)
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, COOP)], comps)
    assert design.support_rule(design.build(treated, clean, q, regions, FUEL, dd)).keeps_its_place.iloc[0]
    r = design.support_rule(design.build(treated, clean, q, regions, FUEL, dd, no_own_utility=True)).iloc[0]
    assert r.pool_in_the_reference_year == 9 and not r.keeps_its_place


# ---- build_blocks in the simulation ----------------------------------------------------------------

def test_build_blocks_leaves_out_excluded_rows_before_taking_the_nearest():
    hosts = [(1, "AA", 10_000, COOP)]
    comps = ladder(10, 12)
    treated, clean, q, regions, dd = world(hosts, comps)
    d = design.build(treated, clean, q, regions, FUEL, dd)
    w = d.windows[COHORT]
    j = w.keys.index((1, "AA"))
    picks, n = [(COHORT, j, 0)], len(d.unit_code)
    plain, _ = ps.build_blocks(d.windows, picks, "nearest_in_size", n)
    same, _ = ps.build_blocks(d.windows, picks, "nearest_in_size", n, excluded=None)
    assert [list(b[2]) for b in plain] == [list(b[2]) for b in same]
    nearest = w.keys.index((10, "AA"))
    assert nearest in plain[0][2]
    out, lost = ps.build_blocks(d.windows, picks, "nearest_in_size", n, excluded=lambda g, row: {nearest} if row == j else set())
    got = [w.keys[r] for r in out[0][2]]
    assert lost == 0 and (10, "AA") not in got and len(got) == ps.MATCH_K and (20, "AA") in got
