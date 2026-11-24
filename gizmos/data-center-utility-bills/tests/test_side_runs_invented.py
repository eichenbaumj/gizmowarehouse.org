"""The design side of the runs that do not change the inventory (pipeline/analysis/side_runs.py). Invented data only.

Each run's hosts and windows are checked by hand; each wrapper reproduces the headline design exactly when its change is
switched off. No file under data/ is read.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, ownership  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import side_runs as sr  # noqa: E402
from test_matching_rules import table  # noqa: E402

KEY = ps.KEY
YEARS = list(range(2001, 2026))
FUEL = {"AA": 0, "BB": 1, "CC": 0}
GAS = {"AA": 0.2, "BB": 0.5, "CC": 0.3}
COOP, IOU = "cooperative", "investor_owned"
NONE = ps.UnknownLoad.none("invented data in a test")


def world(hosts, comps, *, region=None, size=None, missing=(), own_rows=None, unknown=NONE, seed=5):
    """Invented quantities and an Inputs under the headline rules.

    hosts  [(id, state, customers, ownership class, cohort)]
    comps  [(id, state, customers, ownership class)]
    region(key, year) -> region (default "West"); size(key, year, customers) -> customers in that year (default fixed);
    missing: (id, state, year) not usable; own_rows: ownership table rows (test_matching_rules.table form).
    """
    units = [(u, st, c, o) for u, st, c, o, _ in hosts] + list(comps)
    region = region or (lambda key, year: "West")
    size = size or (lambda key, year, c: c)
    q = pd.DataFrame([(u, st, y, o, float(size((u, st), y, c)), 1.0, True, f"U{u}{st}") for u, st, c, o in units for y in YEARS],
                     columns=KEY + ["year", "ownership", "res_customers", "res_mwh", "meets_size_floor", "utility_name"])
    regions = pd.DataFrame([(u, st, y, region((u, st), y)) for u, st, _, _ in units for y in YEARS], columns=KEY + ["year", "region"])
    rng = np.random.default_rng(seed)
    dd = pd.DataFrame([(st, y, 5.0 + rng.normal(0, 0.3), 1.0 + rng.normal(0, 0.3)) for st in FUEL for y in YEARS],
                      columns=["state", "year", "hdd", "cdd"]).set_index(["state", "year"])
    usable = {(u, st, y) for u, st, _, _ in units for y in YEARS} - set(missing)
    treated = pd.DataFrame({"utility_id_eia": [h[0] for h in hosts], "state": [h[1] for h in hosts], "cohort": [h[4] for h in hosts]})
    clean = pd.DataFrame([(u, st) for u, st, *_ in comps], columns=KEY)
    t = table(own_rows or [])
    inp = sr.Inputs(q, None, regions, FUEL, dd, ownership=t, usable=usable, gas=GAS, unknown_load=unknown)
    return inp, treated, clean


def ladder(first, n, state="AA", own=COOP, start=10_050, step=100):
    return [(first + i, state, start + step * i, own) for i in range(n)]


def mk(d, key):
    """The match keys of host `key` in Design d."""
    return sr.matches_of(d)[key]


# ---- E1 --------------------------------------------------------------------------------------------------------------

def test_e1_cuts_cohorts_2011_and_2012_and_shifts_every_window_six_years():
    hosts = [(1, "AA", 10_000, COOP, 2011), (2, "AA", 10_000, COOP, 2012), (3, "AA", 10_000, COOP, 2015), (4, "AA", 10_000, COOP, 2020)]
    inp, treated, clean = world(hosts, ladder(10, 14))
    d = sr.e1(inp, treated, clean, 0.02)
    assert sr.host_keys(d) == [(3, "AA"), (4, "AA")]
    assert dict(zip(map(tuple, d.hosts.key), d.hosts.cohort)) == {(3, "AA"): 2009, (4, "AA"): 2014}
    assert d.real_cohort == {(3, "AA"): 2015, (4, "AA"): 2020}
    assert d.windows_in_calendar_years == {2009: (2003, 2012), 2014: (2008, 2017)}      # g-12 to g-3
    assert [(x["utility"], x["why"]) for x in d.left_out] == [("1:AA", sr.E1_LEFT_OUT), ("2:AA", sr.E1_LEFT_OUT)]
    assert {x["utility"] for x in d.dropped} >= {"1:AA", "2:AA"}
    dose = pd.DataFrame({"utility_id_eia": [3, 3, 3], "state": "AA", "year": [2002, 2010, 2014], "dose": [0.5, 0.004, 0.03]})
    rep = {r["host"]: r for r in sr.e1_report(d, dose, 0.02)}
    assert rep["3:AA"]["window"] == [2003, 2012] and rep["3:AA"]["reference_year"] == 2006
    assert rep["3:AA"]["fake_headline_years"] == [2011, 2012] and rep["3:AA"]["fake_early_years"] == [2003, 2004, 2005]
    assert rep["3:AA"]["largest_load_share_in_the_fake_window"] == pytest.approx(0.004, abs=1e-12)   # 2002 and 2014 are outside
    assert rep["4:AA"]["largest_load_share_in_the_fake_window"] == 0.0


def test_e1_matches_on_size_in_the_fake_reference_year_g_minus_9():
    # comparison 90 is the host's size up to 2007 and five times larger after: nearest at g-9 = 2006, not at g-3 = 2012
    size = lambda key, year, c: (10_000 if year <= 2007 else 50_000) if key == (90, "AA") else c  # noqa: E731
    inp, treated, clean = world([(3, "AA", 10_000, COOP, 2015)], [(90, "AA", 10_000, COOP)] + ladder(10, 12), size=size)
    head = inp.build(treated, clean, 0.02)
    d = sr.e1(inp, treated, clean, 0.02)
    assert (90, "AA") not in mk(head, (3, "AA"))
    assert mk(d, (3, "AA"))[0] == (90, "AA")


def test_e1_same_parent_rule_reads_the_fake_window_only():
    """A parent shared only after g-3 does not exclude in E1; one shared inside g-12 to g-3 does."""
    rows = [{"utility_id_eia": 3, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
            {"utility_id_eia": 20, "state": "AA", "ultimate_parent": "Q", "from_year": 2001, "to_year": 2012},
            {"utility_id_eia": 20, "state": "AA", "ultimate_parent": "P", "from_year": 2013, "to_year": 2025},   # after g-3 = 2012
            {"utility_id_eia": 21, "state": "AA", "ultimate_parent": "P", "from_year": 2012, "to_year": 2012}]   # inside, at g-3
    comps = [(20, "AA", 10_010, COOP), (21, "AA", 10_020, COOP)] + ladder(30, 12)
    inp, treated, clean = world([(3, "AA", 10_000, COOP, 2015)], comps, own_rows=rows)
    head = inp.build(treated, clean, 0.02)
    d = sr.e1(inp, treated, clean, 0.02)
    assert (20, "AA") not in mk(head, (3, "AA")) and (21, "AA") not in mk(head, (3, "AA"))   # window 2009-2018 meets both
    assert mk(d, (3, "AA"))[0] == (20, "AA")
    assert (21, "AA") not in mk(d, (3, "AA"))
    why = {x["utility"]: x["why"] for x in d.hosts.excluded_from_its_pool.iloc[0]}
    assert why == {"21:AA": ownership.SAME_PARENT}


def test_e1_usability_is_read_over_the_fake_window():
    # comparison 10 lacks 2005 (inside g-12..g-3 for g = 2015, outside the real window); the host lacks 2018 (outside the fake)
    inp, treated, clean = world([(3, "AA", 10_000, COOP, 2015)], ladder(10, 13), missing=[(10, "AA", 2005), (3, "AA", 2018)])
    head = inp.build(treated, clean, 0.02)
    d = sr.e1(inp, treated, clean, 0.02)
    assert sr.host_keys(head) == [] and head.dropped[-1]["why"] == design.NOT_USABLE
    assert sr.host_keys(d) == [(3, "AA")] and (10, "AA") not in mk(d, (3, "AA"))


def test_e1_with_no_shift_is_the_headline_design():
    hosts = [(1, "AA", 10_000, COOP, 2011), (3, "AA", 12_000, COOP, 2015), (4, "BB", 11_000, COOP, 2020)]
    inp, treated, clean = world(hosts, ladder(10, 14) + ladder(40, 12, state="BB", start=11_000))
    assert sr.same_design(sr.e1(inp, treated, clean, 0.02, shift=0, cohorts=ps.COHORTS), inp.build(treated, clean, 0.02))


# ---- E3 --------------------------------------------------------------------------------------------------------------

def e3_world():
    hosts = [(1, "AA", 10_000, COOP, 2013), (2, "AA", 20_000, COOP, 2017), (3, "AA", 10_000, COOP, 2018), (4, "BB", 11_000, COOP, 2021)]
    comps = ladder(10, 14) + ladder(40, 14, start=20_050) + ladder(70, 12, state="BB", start=11_050)
    return world(hosts, comps, missing=[(10, "AA", 2022), (41, "AA", 2015)])


def test_e3_names_cohorts_2018_to_2022_and_equals_the_restriction_to_2011_to_2017():
    inp, treated, clean = e3_world()
    d = sr.e3(inp, treated, clean, 0.02)
    assert sr.host_keys(d) == [(1, "AA"), (2, "AA")]
    assert [(x["utility"], x["cohort"], x["why"]) for x in d.left_out] == [("3:AA", 2018, sr.E3_LEFT_OUT), ("4:BB", 2021, sr.E3_LEFT_OUT)]
    r = sr.e3_restricted(inp, treated, clean, 0.02)
    assert sr.same_design(d, r)
    assert sr.e3_equals_cohort_restriction(inp, treated, clean, 0.02)
    # comparison 10 lacks only 2022, so it stays the 2013 host's nearest; 41 lacks 2015 and is not the 2017 host's
    assert mk(d, (1, "AA"))[0] == (10, "AA") and (41, "AA") not in mk(d, (2, "AA"))
    head = inp.build(treated, clean, 0.02)
    assert mk(head, (1, "AA")) == mk(d, (1, "AA")) and mk(head, (2, "AA")) == mk(d, (2, "AA"))


def test_e3_with_no_years_removed_is_the_headline_design():
    inp, treated, clean = e3_world()
    assert sr.same_design(sr.e3(inp, treated, clean, 0.02, years=()), inp.build(treated, clean, 0.02))


def test_e3_with_every_host_after_2017_leaves_an_empty_design_not_an_error():
    inp, treated, clean = world([(3, "AA", 10_000, COOP, 2019)], ladder(10, 12))
    d = sr.e3(inp, treated, clean, 0.02)
    assert sr.host_keys(d) == [] and [x["utility"] for x in d.left_out] == ["3:AA"]


# ---- G-b, E5, E6 ----------------------------------------------------------------------------------------------------

def gb_world():
    # host 1 (BB): its ten nearest are six AA units then four BB; host 2 (BB, larger): three AA then BB; host 3 in AA
    comps = ([(10 + i, "AA", 10_010 + 10 * i, COOP) for i in range(6)] + [(20 + i, "BB", 10_100 + 10 * i, COOP) for i in range(8)]
             + [(30 + i, "AA", 30_010 + 10 * i, COOP) for i in range(3)] + [(40 + i, "BB", 30_100 + 10 * i, COOP) for i in range(9)])
    hosts = [(1, "BB", 10_000, COOP, 2015), (2, "BB", 30_000, COOP, 2015), (3, "AA", 30_000, COOP, 2016)]
    return world(hosts, comps)


def test_e5_removes_without_rematching_and_names_a_host_left_under_five():
    inp, treated, clean = gb_world()
    head = inp.build(treated, clean, 0.02)
    assert [k[1] for k in mk(head, (1, "BB"))].count("AA") == 6
    d = sr.e5(head, {"AA"})
    assert sr.host_keys(d) == [(2, "BB")]
    assert mk(d, (2, "BB")) == [k for k in mk(head, (2, "BB")) if k[1] != "AA"]           # same order, nothing new
    assert len(mk(d, (2, "BB"))) == 7
    assert d.gb["hosts_removed"] == [{"utility": "3:AA", "cohort": 2016, "why": sr.E5_HOST_DROPPED}]
    assert d.gb["hosts_excluded_under_g_b"] == [{"utility": "1:BB", "cohort": 2015, "why": sr.GB_FEWER, "surviving": 4}]
    assert {x["utility"] for x in d.dropped} >= {"1:BB", "3:AA"}
    assert sr.same_design(sr.e5(head, set()), head)


def test_remove_units_names_a_host_left_with_none_as_not_estimable():
    inp, treated, clean = gb_world()
    head = inp.build(treated, clean, 0.02)
    d = sr.remove_units(head, {}, set(mk(head, (1, "BB"))))
    out = {x["utility"]: x for x in d.gb["hosts_excluded_under_g_b"]}
    assert out["1:BB"]["why"] == sr.GB_NONE and out["1:BB"]["surviving"] == 0
    assert (1, "BB") not in sr.host_keys(d)


def test_remove_units_takes_the_hosts_it_removes_off_the_unresolved_ownership_list():
    """Session 19: the returned design's unresolved-ownership list names only hosts of that design. E5 on AA removes
    host 3 by name and excludes host 1 under G-b; an entry for each leaves the list, host 2's stays, and an entry for a
    host an earlier rule already moved out (in_this_run "excluded") is kept. The list here is invented."""
    inp, treated, clean = gb_world()
    head = inp.build(treated, clean, 0.02)
    head.unresolved_ownership = [{"utility": u, "cohort": g, "in_this_run": run} for u, g, run in
                                 (("1:BB", 2015, "kept"), ("2:BB", 2015, "kept"), ("3:AA", 2016, "kept"), ("9:ZZ", 2015, "excluded"))]
    d = sr.e5(head, {"AA"})
    assert [x["utility"] for x in d.unresolved_ownership] == ["2:BB", "9:ZZ"]
    assert d.gb["unresolved_ownership_hosts_removed_by_this_run"] == ["1:BB", "3:AA"]
    assert [x["utility"] for x in head.unresolved_ownership] == ["1:BB", "2:BB", "3:AA", "9:ZZ"]     # the base is unchanged


NAN = float("nan")
E5_BLOCK = [{"state": "AA", "epri_twh": 5, "permit_twh": 1, "epoch_twh": 0, "raw_factor": 4.0, "factor": 3.0, "flag": "undercounted"},
            {"state": "BB", "epri_twh": 5, "permit_twh": 1, "epoch_twh": 0, "raw_factor": 2.0, "factor": 2.0, "flag": "ok"},
            {"state": "CC", "epri_twh": 5, "permit_twh": 1, "epoch_twh": 0, "raw_factor": 1.99, "factor": 1.99, "flag": "ok"},
            {"state": "DD", "epri_twh": 5, "permit_twh": 0, "epoch_twh": 0, "raw_factor": NAN, "factor": 1.0, "flag": "no_dated_permits"},
            {"state": "NE", "epri_twh": 5, "permit_twh": 1, "epoch_twh": 9, "raw_factor": 0.0, "factor": 0.2, "flag": "overcounted"}]
E5_SMALL = [  # left out of the block (EPRI total under 0.25 TWh); `small_state` hides how each factor arose
    {"state": "FF", "epri_twh": 0.1, "permit_twh": 0.01, "epoch_twh": 0, "raw_factor": 7.0, "factor": 3.0, "flag": "small_state"},   # computed, capped
    {"state": "GG", "epri_twh": 0.1, "permit_twh": 0.0, "epoch_twh": 0, "raw_factor": NAN, "factor": 1.0, "flag": "small_state"},    # the fallback
    {"state": "HH", "epri_twh": 0.02, "permit_twh": 0.5, "epoch_twh": 0, "raw_factor": 0.04, "factor": 0.2, "flag": "small_state"},  # lower limit
    {"state": "II", "epri_twh": 0.1, "permit_twh": 0.1, "epoch_twh": 0, "raw_factor": 1.0, "factor": 1.0, "flag": "small_state"}]    # computed 1.0


def test_e5_states_come_from_the_factor_rule_over_the_full_table_not_the_block(tmp_path):
    every = pd.DataFrame(E5_BLOCK + E5_SMALL)
    out = sr.e5_states(E5_BLOCK, every, lo=0.2, hi=3.0)
    # a computed factor at the cap in a small state is dropped; the fallback is flagged, not dropped
    assert [r["state"] for r in out["dropped"]] == ["AA", "BB", "FF"]
    assert [r["state"] for r in out["flagged_not_dropped"]] == ["DD", "GG"]
    ff = next(r for r in out["dropped"] if r["state"] == "FF")
    assert ff["factor_is"] == sr.COMPUTED and ff["clipped_to"] == 3.0 and ff["flag"] == "small_state" and not ff["in_report_block"]
    gg = next(r for r in out["flagged_not_dropped"] if r["state"] == "GG")
    assert gg["factor_is"] == sr.FALLBACK and gg["factor"] == 1.0 and "fallback" in gg["why"]
    # a computed 1.0 (II) is not the fallback and is on neither list
    assert "II" not in {r["state"] for k in ("dropped", "flagged_not_dropped") for r in out[k]}
    # the lower limit: reported, not decided; the plan's named states marked, another added by the table named as such
    low = {r["state"]: r for r in out["at_the_lower_limit"]}
    assert sorted(low) == ["HH", "NE"] and low["NE"]["named_in_the_plan"] and not low["HH"]["named_in_the_plan"]
    assert low["HH"]["status"].startswith("added by the full table, not decided")
    assert [(r["state"], r["cap"]) for r in out["capped"]] == [("AA", 3.0), ("FF", 3.0), ("HH", 0.2), ("NE", 0.2)]
    # the block-versus-table difference: the block alone gives the lists before the ruling
    assert out["from_the_report_block_alone"]["dropped"] == ["AA", "BB"]
    assert out["from_the_report_block_alone"]["flagged_not_dropped"] == ["DD"]
    assert [(r["state"], r["factor_is"], r["factor_2_or_more"]) for r in out["computed_but_not_in_the_report_block"]] == [
        ("FF", "computed", True), ("GG", "fallback", False), ("HH", "computed", False), ("II", "computed", False)]


def test_e5_states_stop_in_words_on_an_inconsistent_table(tmp_path):
    every = pd.DataFrame(E5_BLOCK + E5_SMALL)
    with pytest.raises(ValueError, match="pass it as all_states"):
        sr.e5_states(E5_BLOCK)
    bad = every.copy()
    bad.loc[bad.state == "BB", "factor"] = 2.5                       # the block says 2.0
    with pytest.raises(ValueError, match="BB: the report's block has factor"):
        sr.e5_states(E5_BLOCK, bad, lo=0.2, hi=3.0)
    blk = [dict(r) for r in E5_BLOCK]
    blk[1]["factor"] = 2.5
    bad2 = pd.DataFrame(blk + E5_SMALL)
    with pytest.raises(ValueError, match="not the raw factor"):     # 2.5 is not 2.0 clipped: not what state_anchor gives
        sr.e5_states(blk, bad2, lo=0.2, hi=3.0)
    fb = pd.DataFrame(E5_BLOCK + [{**E5_SMALL[1], "factor": 0.7}])
    with pytest.raises(ValueError, match="not the fallback 1.0"):
        sr.e5_states(E5_BLOCK, fb, lo=0.2, hi=3.0)
    with pytest.raises(ValueError, match="the full table lacks"):
        sr.e5_states(E5_BLOCK, pd.DataFrame(E5_BLOCK[1:] + E5_SMALL), lo=0.2, hi=3.0)
    path = tmp_path / "inventory_report.json"
    path.write_text(json.dumps({"state_anchor": [{k: v for k, v in E5_BLOCK[0].items() if k != "raw_factor"}]}))
    with pytest.raises(ValueError, match="lacks"):
        sr.read_state_anchor_block(path)
    path.write_text(json.dumps({"state_anchor": E5_BLOCK[:1]}))
    assert sr.read_state_anchor_block(path)[0]["state"] == "AA"


def test_factor_applied_reads_the_scale_on_permit_based_rows_only():
    fac = pd.DataFrame([("FF", "permit", "permit_based", 3.0, True), ("FF", "epoch", "epoch", 1.0, True),
                        ("FF", "permit", "verified_public_figure", 1.0, True), ("GG", "permit", "permit_based", 1.0, False),
                        ("II", "permit", "permit_based", 0.9, True)],
                       columns=["state", "src", "mw_basis", "state_scale", "in_dose"])
    rows = [{"state": "FF", "factor": 3.0, "factor_is": "computed"}, {"state": "GG", "factor": 1.0, "factor_is": "fallback"},
            {"state": "II", "factor": 1.0, "factor_is": "computed"}, {"state": "ZZ", "factor": 1.0, "factor_is": "fallback"}]
    out = {r["state"]: r for r in sr.factor_applied(fac, rows)}
    assert out["FF"]["state_scale_on_permit_based_rows"] == [3.0] and out["FF"]["state_scale_on_measured_rows"] == [1.0]
    assert out["FF"]["factor_applied_to_permit_based_rows"] is True and out["FF"]["permit_based_rows"] == 1
    assert out["GG"]["factor_applied_to_permit_based_rows"] is True and out["GG"]["permit_based_rows_in_the_dose"] == 0
    assert out["II"]["factor_applied_to_permit_based_rows"] is False                  # 0.9 on the row, 1.0 in the table
    assert out["ZZ"]["factor_applied_to_permit_based_rows"] is None                   # no permit-based row at all


def test_e6_lists_region_changers_and_removes_them_without_rematching():
    moves = {(10, "AA"), (11, "AA"), (12, "AA"), (13, "AA"), (14, "AA"), (15, "AA")}
    region = lambda key, year: ("East" if year < 2004 else "West") if key in moves else "West"  # noqa: E731
    hosts = [(1, "AA", 10_000, COOP, 2015), (2, "AA", 30_000, COOP, 2015)]
    comps = ladder(10, 12) + ladder(40, 12, start=30_050)
    inp, treated, clean = world(hosts, comps, region=region)
    q = inp.q[~((inp.q.utility_id_eia == 40) & (inp.q.year == 2003))]                     # 40 is absent from the panel in 2003
    head = inp.build(treated, clean, 0.02)
    matched = {m for v in sr.matches_of(head).values() for m in v}
    ch = sr.region_changers(inp.regions, matched, q)
    assert ch["coded"] == sorted(moves)
    assert ch["absent_in_some_year"] == [(40, "AA")]
    assert ch["coded_or_absent_in_some_year"] == sorted(moves | {(40, "AA")})
    d = sr.e6(head, set(ch["coded"]))
    assert sr.host_keys(d) == [(2, "AA")]                                                  # host 1 keeps 4 of 10
    assert d.gb["hosts_excluded_under_g_b"][0]["utility"] == "1:AA" and d.gb["hosts_excluded_under_g_b"][0]["surviving"] == 4
    assert mk(d, (2, "AA")) == mk(head, (2, "AA"))
    assert sr.same_design(sr.e6(head, set()), head)


# ---- the longer horizon ---------------------------------------------------------------------------------------------

def test_build_windows_span_at_ten_years_is_build_windows():
    hosts = [(1, "AA", 10_000, COOP, 2015), (2, "BB", 11_000, COOP, 2019)]
    inp, treated, clean = world(hosts, ladder(10, 12) + ladder(40, 12, state="BB"), missing=[(12, "AA", 2011)])
    d = inp.build(treated, clean, 0.02)
    everyone = pd.DataFrame(list(d.unit_code), columns=KEY)
    template = sr._template(inp.usable, everyone)
    a = ps.build_windows([2015, 2019], template, inp.q, inp.regions, FUEL, inp.dd, d.unit_code, d.state_code)
    b = sr.build_windows_span([2015, 2019], template, inp.q, inp.regions, FUEL, inp.dd, d.unit_code, d.state_code, ps.PRE, ps.POST)
    for g in a:
        assert a[g].keys == b[g].keys
        for attr in ("y", "region_t", "fuel", "hdd", "cdd", "size", "unit", "state"):
            np.testing.assert_array_equal(getattr(a[g], attr), getattr(b[g], attr))
        assert list(a[g].region) == list(b[g].region)
    c = sr.build_windows_span([2015], template, inp.q, inp.regions, FUEL, inp.dd, d.unit_code, d.state_code, 6, 6)
    assert c[2015].y.shape[1] == 13 and (12, "AA") not in c[2015].keys


def long_world():
    rows = [{"utility_id_eia": 1, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
            {"utility_id_eia": 11, "state": "AA", "ultimate_parent": "Q", "from_year": 2001, "to_year": 2019},
            {"utility_id_eia": 11, "state": "AA", "ultimate_parent": "P", "from_year": 2020, "to_year": 2025}]   # g+5 for g = 2015
    hosts = [(1, "AA", 10_000, COOP, 2015), (2, "AA", 30_000, COOP, 2021)]
    comps = ladder(10, 13) + ladder(40, 12, start=30_050)
    return world(hosts, comps, missing=[(10, "AA", 2020)], own_rows=rows)                 # 10 lacks g+5


def test_longer_horizon_rematches_among_units_eligible_for_thirteen_years():
    inp, treated, clean = long_world()
    head = inp.build(treated, clean, 0.02)
    lh = sr.long_horizon(inp, treated, clean, 0.02)
    d = lh.design
    assert sr.host_keys(d) == [(1, "AA")]
    assert [(x["utility"], x["why"]) for x in d.dropped if x["utility"] == "2:AA"] == [("2:AA", sr.LONG_NOT_IN_COHORTS)]
    assert mk(head, (1, "AA"))[:2] == [(10, "AA"), (11, "AA")]
    got = mk(d, (1, "AA"))
    assert (10, "AA") not in got and (11, "AA") not in got                                  # missing g+5; shared parent in g+5
    assert got == [(12 + i, "AA") for i in range(10)]                                       # the next nearest enter
    assert lh.report["ownership_exclusions_added_by_the_years_g_plus_4_to_g_plus_6"]["1:AA"][0]["utility"] == "11:AA"
    g, tr, comp = lh.blocks13[0]
    w = lh.windows13[g]
    assert w.y.shape[1] == 13 and w.keys[tr[0]] == (1, "AA") and [w.keys[i] for i in comp] == got
    w10 = d.windows[g]
    h = d.hosts.iloc[0]
    assert w10.keys[h.row] == (1, "AA") and [w10.keys[i] for i in h.matches] == got


def test_longer_horizon_at_three_years_after_is_the_headline_design():
    inp, treated, clean = long_world()
    lh = sr.long_horizon(inp, treated, clean, 0.02, post=ps.POST, cohorts=ps.COHORTS)
    assert sr.same_design(lh.design, inp.build(treated, clean, 0.02))


def test_a_host_missing_year_g_plus_5_leaves_the_longer_horizon():
    inp, treated, clean = world([(1, "AA", 10_000, COOP, 2015)], ladder(10, 12), missing=[(1, "AA", 2020)])
    lh = sr.long_horizon(inp, treated, clean, 0.02)
    assert sr.host_keys(lh.design) == [] and lh.design.dropped[0]["why"] == sr.LONG_NOT_USABLE
    assert sr.host_keys(inp.build(treated, clean, 0.02)) == [(1, "AA")]


# ---- thresholds ------------------------------------------------------------------------------------------------------

def dose_frame(paths: dict) -> pd.DataFrame:
    """paths {(id, state): {year: share}}; base sales 1,000 GWh; no crypto."""
    rows = [(u, st, y, v, 0.0, 1000.0) for (u, st), p in paths.items() for y, v in p.items()]
    return pd.DataFrame(rows, columns=KEY + ["year", "dose", "crypto_mw", "base_retail_gwh"])


def test_the_one_percent_hosts_are_every_cohort_utility_at_one_percent():
    step = lambda at1, at2: {y: (0.025 if at2 is not None and y >= at2 else 0.012 if y >= at1 else 0.0) for y in YEARS}  # noqa: E731
    paths = {(1, "AA"): step(2011, 2013),     # 1% in 2011, 2% in 2013
             (2, "AA"): step(2016, None),     # 1% in 2016, never 2%
             (3, "AA"): step(2006, 2008),     # early at both thresholds
             (4, "AA"): step(2022, 2024),     # 1% in 2022; 2% in 2024, a late host at 2%
             (5, "AA"): {y: 0.004 for y in YEARS}}  # never 0.5%: a comparison
    units = [(k[0], k[1], 10_000, COOP) for k in paths]
    inp, _, _ = world([], units)
    tr1, cl1 = sr.every_cohort_at(0.01, inp.q, dose_frame(paths), history={}, hold=set())
    tr2, _ = sr.every_cohort_at(0.02, inp.q, dose_frame(paths), history={}, hold=set())
    assert sorted(zip(tr1.utility_id_eia, tr1.cohort)) == [(1, 2011), (2, 2016), (4, 2022)]
    assert sorted(zip(tr2.utility_id_eia, tr2.cohort)) == [(1, 2013)]
    assert sorted(cl1.utility_id_eia) == [5]
    a, b = sr.every_cohort_at(0.02, inp.q, dose_frame(paths), history={}, hold=set()), ps.design(inp.q, dose_frame(paths), 0.02, {}, hold=set())
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])


def test_a_load_unknown_unit_with_no_verdict_at_one_percent_is_excluded_on_both_sides():
    hosts = [(1, "AA", 10_000, COOP, 2015), (2, "AA", 12_000, COOP, 2016)]
    unknown = ps.UnknownLoad(frozenset({(2, "AA"), (10, "AA")}), {"2%": frozenset({(2, "AA"), (10, "AA")})}, "invented")
    inp, treated, clean = world(hosts, ladder(10, 14), unknown=unknown)
    at2, at1 = inp.build(treated, clean, 0.02), inp.build(treated, clean, 0.01)
    assert sr.host_keys(at2) == [(1, "AA"), (2, "AA")] and (10, "AA") in mk(at2, (1, "AA"))
    assert sr.host_keys(at1) == [(1, "AA")] and (10, "AA") not in mk(at1, (1, "AA"))
    assert {x["utility"] for x in at1.load_unknown_excluded} == {"2:AA", "10:AA"}


def test_without_rappahannock_sets_it_aside_by_name_and_keeps_the_rest():
    t = pd.DataFrame({"utility_id_eia": [40228, 6958], "state": ["VA", "TX"], "cohort": [2011, 2019]})
    kept, left = sr.without_rappahannock(t)
    assert list(kept.utility_id_eia) == [6958]
    assert left == [{"utility": "40228:VA", "cohort": 2011, "why": sr.RAPPAHANNOCK_ASIDE}]


def test_history_at_with_no_utility_level_figures_settles_nothing():
    inp, _, _ = world([], ladder(10, 2))
    assert sr.history_at(0.01, inp.q, dose_frame({}), table=pd.DataFrame()) == {}


# ---- own state -------------------------------------------------------------------------------------------------------

def test_own_state_matches_only_in_the_hosts_state_and_reports_its_support():
    hosts = [(1, "AA", 10_000, COOP, 2015), (2, "BB", 10_000, COOP, 2017)]
    comps = ([(10 + i, "BB", 10_001 + i, COOP) for i in range(6)] + ladder(20, 12, start=10_500)
             + ladder(50, 12, state="BB", start=10_500))
    inp, treated, clean = world(hosts, comps)
    head = inp.build(treated, clean, 0.02)
    assert any(k[1] == "BB" for k in mk(head, (1, "AA")))
    d = sr.own_state(inp, treated, clean, 0.02)
    assert all(k[1] == "AA" for k in mk(d, (1, "AA"))) and all(k[1] == "BB" for k in mk(d, (2, "BB")))
    assert mk(d, (1, "AA")) == [(20 + i, "AA") for i in range(10)]
    for h in d.hosts.itertuples():                                                          # rows index base's windows by key
        w = d.windows[h.cohort]
        assert w.keys[h.row] == h.key and [w.keys[i] for i in h.matches] == [tuple(m) for m in h.match_keys]
    pools = {(int(r.utility_id_eia), r.state): int(r.pool_in_the_reference_year) for r in d.support_table.itertuples()}
    assert pools == {(1, "AA"): 12, (2, "BB"): 18}


def test_own_state_is_the_headline_design_when_every_comparison_is_in_the_hosts_state():
    hosts = [(1, "AA", 10_000, COOP, 2015), (2, "AA", 11_000, COOP, 2017)]
    inp, treated, clean = world(hosts, ladder(10, 14))
    assert sr.same_design(sr.own_state(inp, treated, clean, 0.02), inp.build(treated, clean, 0.02))


def test_own_state_drops_a_host_whose_state_pool_is_under_ten_by_the_support_rule():
    hosts = [(1, "AA", 10_000, COOP, 2015)]
    inp, treated, clean = world(hosts, ladder(10, 9) + ladder(30, 12, state="BB"))
    d = sr.own_state(inp, treated, clean, 0.02)
    assert sr.host_keys(d) == [] and design.SUPPORT_RULE in d.dropped[-1]["why"]
    assert sr.host_keys(inp.build(treated, clean, 0.02)) == [(1, "AA")]
