"""pipeline/analysis/future_hosts.py on invented inputs only: the future-host criterion, the histories it reads, the side
run's per-cohort pool, and E2's fake dates and pool. No file under data/ is read: the price hold, the ownership table
and the load-unknown input are passed in (an empty hold, a header-only or invented table, UnknownLoad.none)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import stepd_world as W  # noqa: E402
from pipeline.analysis import design, ownership  # noqa: E402
from pipeline.analysis import future_hosts as fh  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.facilities import timing as tm  # noqa: E402
from test_matching_rules import COOP, FUEL, IOU, YEARS, keys_of, ladder, table, world  # noqa: E402

YRS = list(fh.PANEL_YEARS)
GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}
NONE = ps.UnknownLoad.none("invented data: no load-unknown site")


def series(crossing=None, level=0.03, quiet=0.0, extra=None):
    """A share history: `quiet` every year, `level` from `crossing` on; `extra` {year: share} overrides."""
    s = {y: (level if crossing is not None and y >= crossing else quiet) for y in YRS}
    s.update(extra or {})
    return s


def header_only(tmp_path):
    path = tmp_path / "ownership.csv"
    path.write_text(",".join(ownership.COLUMNS) + "\n")
    return ownership.load(path)


def all_usable(units):
    return {(u, st, y) for u, st, *_ in units for y in YEARS}


def kw(t, usable):
    return dict(ownership=t, usable=usable, gas=GAS, unknown_load=NONE, theta=0.02)


# ---- the criterion at its boundaries -------------------------------------------------------------------------------

def test_a_share_of_exactly_half_a_percent_in_year_g_plus_3_fails_and_just_under_passes():
    g = 2015
    assert not fh.admitted([series(2025, extra={g + 3: 0.005})], g)
    assert fh.admitted([series(2025, extra={g + 3: 0.00499})], g)
    assert fh.admitted([series(2025, extra={g + 4: 0.005})], g)          # g+4 is after the quiet years


def test_a_crossing_at_g_plus_6_fails_and_at_g_plus_7_passes():
    assert not fh.admitted([series(2021)], 2015)
    assert fh.admitted([series(2022)], 2015)
    assert fh.admitted([series(2025, level=0.02)], 2018)                 # exactly the threshold is a crossing
    assert not fh.admitted([series(2024, level=0.02)], 2018)


def test_one_history_that_fails_is_enough_and_no_history_shows_nothing():
    ok, bad = series(2025), series(2025, extra={2012: 0.006})
    assert fh.admitted([ok, ok], 2015) and not fh.admitted([ok, bad, ok], 2015)
    assert not fh.admitted([], 2015)
    assert fh.admitted(pd.DataFrame([ok]), 2015) and fh.admitted(np.array([[ok[y] for y in YRS]]), 2015, years=YRS)


def test_a_unit_crossing_in_2023_is_admitted_for_cohorts_2011_to_2016_only():
    assert fh.admitted_cohorts([series(2023)]) == list(range(2011, 2017))
    assert fh.admitted_cohorts([series(2023), series(2024)]) == list(range(2011, 2017))   # the earliest history binds
    assert fh.admitted_cohorts([series(2025)]) == list(range(2011, 2019))


def test_a_history_with_no_crossing_in_the_panel_shows_g_plus_7_only_up_to_2026():
    """The agent's reading: no crossing through 2025 shows only a crossing in 2026 or later."""
    assert fh.admitted_cohorts([series(None)]) == list(range(2011, 2020))


def test_a_missing_year_stops_rather_than_being_filled():
    s = series(2025)
    del s[2008]
    with pytest.raises(ValueError, match="lacks panel years"):
        fh.admitted([s], 2015)


# ---- E2's fake date -----------------------------------------------------------------------------------------------

def test_e2_fake_date_is_the_latest_year_meeting_the_criterion_in_every_history():
    assert fh.fake_date([series(2025)]) == 2018
    assert fh.fake_date([series(2024)]) == 2017
    assert fh.fake_date([series(2025), series(2023)]) == 2016
    # creeping load: 0.6% from 2016 on, so f+3 must be 2015 at most
    assert fh.fake_date([series(2025, extra={y: 0.006 for y in range(2016, 2025)})]) == 2012
    # from 2014 on: f+3 would have to be 2013 at most, so f is 2010, outside 2011 to 2022: no fake date
    assert fh.fake_date([series(2025, extra={y: 0.006 for y in range(2014, 2025)})]) is None


def test_e2_a_unit_with_no_fake_date_is_left_out_and_named():
    h = pd.DataFrame([series(2025, extra={y: 0.006 for y in range(2011, 2025)})])
    assert fh.fake_date(h) is None
    units = {(7, "AA"): {"histories": h, "complete": True, "why_incomplete": [], "slow_path": None}}
    e2, left = fh.e2_units(units, aside=set(), hold=set(), unknown=NONE)
    assert e2.empty and left == [{"utility": "7:AA", "why": ["no year in 2011 to 2022 meets the criterion in every admissible history"]}]


def test_e2_units_need_late_in_every_history_complete_coverage_and_the_other_rules():
    good = pd.DataFrame([series(2025), series(2024)])
    early = pd.DataFrame([series(2025), series(2021)])                 # one history crosses inside the cohorts
    units = {(1, "AA"): {"histories": good, "complete": True, "why_incomplete": [], "slow_path": None},
             (2, "AA"): {"histories": early, "complete": True, "why_incomplete": [], "slow_path": None},
             (3, "AA"): {"histories": good.iloc[0:0], "complete": False, "why_incomplete": ["screen case 0: over the ceiling"], "slow_path": None},
             (4, "AA"): {"histories": good, "complete": True, "why_incomplete": [], "slow_path": None},
             (5, "AA"): {"histories": good, "complete": True, "why_incomplete": [], "slow_path": None}}
    e2, left = fh.e2_units(units, aside={(4, "AA")}, hold={(5, "AA")}, unknown=NONE)
    assert e2.to_dict("records") == [{"utility_id_eia": 1, "state": "AA", "cohort": 2017}]
    why = {x["utility"]: x["why"] for x in left}
    assert why["2:AA"] == ["not a late host in every admissible history"]
    assert why["3:AA"][0].startswith("not shown admissible in every admissible history")
    assert why["4:AA"] == ["set aside"] and why["5:AA"] == ["in price_hold.csv"]


def test_the_slow_path_history_is_counted_with_the_others():
    r = {"histories": pd.DataFrame([series(2025)]), "complete": True, "why_incomplete": [],
         "slow_path": pd.Series(series(2025, extra={2010: 0.01}))}
    assert fh.fake_date(r["histories"]) == 2018 and fh.fake_date(fh._all_histories(r)) is None


# ---- the histories the place test's objects supply ---------------------------------------------------------------------

def test_histories_cover_every_date_case_and_both_readings_and_admit_from_them():
    inp = W.make([{"fid": "a", "state": "AA", "mw": 20, "year": 2023, "utility": 1}], {(1, "AA"): 10.0, (2, "AA"): 1000.0})
    sr = tm.StateRun(inp, [W.date("a", 2022, 2024, 2023, ends="evidence")], "AA", screen=(0,))
    r = fh.histories_from_state_run(sr, (1, "AA"))
    assert r["complete"] and r["why_incomplete"] == []
    # with no anchoring, one history per start year; as built, the state's factor is recomputed in each, so the start
    # years also move the factor and give histories of their own
    assert set(int(c) for c in fh.first_crossings(r["histories"])) == {2023, 2024, 2025}
    assert len(r["histories"]) == 5 and r["coverage"]["screen_cases"][0]["factor_recomputed_in_each"]
    assert r["coverage"]["question_kinds_relevant"] == ["timing"] and r["coverage"]["readings"] == ["as_built", "no_anchoring"]
    assert fh.admitted_cohorts(r["histories"]) == list(range(2011, 2017))   # the 2023 history binds
    assert fh.late_in_every_history(r["histories"])


def test_a_screen_case_over_the_ceiling_is_not_approximated_and_the_unit_is_not_admitted():
    inp = W.make([{"fid": "a", "state": "AA", "mw": 20, "year": 2023, "utility": 1}], {(1, "AA"): 10.0, (2, "AA"): 1000.0})
    sr = tm.StateRun(inp, [W.date("a", 2022, 2024, 2023, ends="evidence")], "AA", screen=(0,))
    r = fh.histories_from_state_run(sr, (1, "AA"), ceiling=2)
    assert not r["complete"] and "over the ceiling of 2" in r["why_incomplete"][0]
    assert r["histories"].empty and not fh.admitted(r["histories"], 2011)
    e2, left = fh.e2_units({(1, "AA"): {**r, "slow_path": None}}, set(), set(), NONE)
    assert e2.empty and left[0]["why"][0].startswith("not shown admissible")


def test_an_unresolved_assignment_puts_the_unit_on_and_off_its_sites():
    sites = [{"fid": "a", "state": "AA", "mw": 20, "year": 2023, "utility": 1, "assign": "smallest_polygon", "candidates": "1;2"}]
    inp = W.make(sites, {(1, "AA"): 10.0, (2, "AA"): 1000.0})
    sr = tm.StateRun(inp, [], "AA", screen=(0,))
    r = fh.histories_from_state_run(sr, (1, "AA"))
    c = fh.first_crossings(r["histories"])
    assert np.isnan(c).any() and 2024 in c                             # on it, and off it (on the other candidate or off the panel)
    assert not fh.late_in_every_history(r["histories"])                 # so not a late host in every history


# ---- the side run: the pool differs by cohort, matching under the existing rules --------------------------------------

def side_world(future, region=None, extra_hosts=()):
    host = (1, "AA", 10_000, COOP)
    comps = ladder(10, 12)
    treated, clean, q, regions, dd = world([host, *extra_hosts], comps + [future], region=region)
    clean = clean[clean.utility_id_eia != future[0]].reset_index(drop=True)      # the headline pool has no future host
    return treated, clean, q, regions, dd, [host, *extra_hosts] + comps + [future]


def test_with_nobody_admitted_the_side_run_is_exactly_the_headline_design(tmp_path):
    hosts = [(1, "AA", 10_000, COOP), (2, "AA", 20_000, IOU), (3, "BB", 30_000, COOP), (4, "AA", 15_000, COOP)]
    comps = ladder(10, 14) + ladder(40, 9, state="BB", start=30_050) + [(60, "AA", 20_010, IOU), (61, "AA", 20_020, IOU)]
    region = lambda key, year: "East" if key[1] == "BB" else "West"  # noqa: E731
    treated, clean, q, regions, dd = world(hosts, comps, region=region)
    treated["cohort"] = [2015, 2017, 2015, 2017]
    usable = all_usable(hosts + comps) - {(4, "AA", 2012), (11, "AA", 2016)}
    t = table([{"utility_id_eia": 2, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
               {"utility_id_eia": 60, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}])
    head = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw(t, usable))
    assert len(head.hosts) == 2 and any(design.SUPPORT_RULE in x["why"] for x in head.dropped)    # the world exercises the drops
    assert any(x["why"] == design.NOT_USABLE for x in head.dropped)
    for admitted in ({}, {2013: [(10, "AA")]}):                        # a cohort with no host changes nothing either
        side = fh.side_run_design(treated, clean, admitted, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw(t, usable))
        assert fh.same_design(side, head) == []
        assert list(side.hosts.key) == list(head.hosts.key) and [list(m) for m in side.hosts.matches] == [list(m) for m in head.hosts.matches]
        assert side.dropped == head.dropped


def test_an_admitted_future_host_closest_in_size_enters_and_displaces_the_tenth(tmp_path):
    future = (99, "AA", 10_010, COOP)
    treated, clean, q, regions, dd, units = side_world(future)
    args = (q, regions, FUEL, dd, ps.HEADLINE_RULES)
    head = design.build_with_rules(treated, clean, *args, **kw(header_only(tmp_path), all_usable(units)))
    side = fh.side_run_design(treated, clean, {2015: [(99, "AA")]}, *args, **kw(header_only(tmp_path), all_usable(units)))
    assert keys_of(head) == [(10 + i, "AA") for i in range(10)]
    assert keys_of(side) == [(99, "AA")] + [(10 + i, "AA") for i in range(9)]
    assert side.hosts.pool_in_the_reference_year.iloc[0] == head.hosts.pool_in_the_reference_year.iloc[0] + 1
    rep = fh.compare_to_headline(side, head, {(99, "AA")})
    h = rep["per_host"][0]
    assert h["matches_entered"] == ["99:AA"] and h["matches_left"] == ["19:AA"] and h["n_future_hosts_among_its_matches"] == 1
    assert rep["totals"]["future_host_matches"] == 1 and rep["hosts_gained"] == [] and rep["hosts_lost"] == []
    # the design the estimator takes: the host row and its matches index the window it sits in
    w = side.windows[2015]
    (g, tr, comp), = side.blocks()
    assert w.keys[int(tr[0])] == (1, "AA") and [w.keys[int(m)] for m in comp] == keys_of(side)


def test_the_pool_differs_by_cohort(tmp_path):
    future = (99, "AA", 10_010, COOP)
    treated, clean, q, regions, dd, units = side_world(future, extra_hosts=[(2, "AA", 10_000, COOP)])
    treated["cohort"] = [2015, 2019]
    side = fh.side_run_design(treated, clean, {2015: [(99, "AA")]}, q, regions, FUEL, dd, ps.HEADLINE_RULES,
                              **kw(header_only(tmp_path), all_usable(units)))
    by = {tuple(k): [tuple(m) for m in mk] for k, mk in zip(side.hosts.key, side.hosts.match_keys)}
    assert (99, "AA") in by[(1, "AA")] and (99, "AA") not in by[(2, "AA")]
    w19 = side.windows[2019]
    assert not side.is_comp[2019][w19.keys.index((99, "AA"))] and side.is_comp[2015][side.windows[2015].keys.index((99, "AA"))]


@pytest.mark.parametrize("why", ["same_parent", "no_usable_window", "other_region"])
def test_an_admitted_future_host_that_fails_another_rule_does_not_enter(tmp_path, why):
    host, future = (1, "AA", 10_000, IOU), (99, "AA", 10_010, IOU)
    comps = ladder(10, 12, own=IOU)
    region = (lambda key, year: "East" if key == (99, "AA") else "West") if why == "other_region" else None
    treated, clean, q, regions, dd = world([host], comps + [future], region=region)
    clean = clean[clean.utility_id_eia != 99].reset_index(drop=True)
    rows = [{"utility_id_eia": u, "state": "AA", "ultimate_parent": f"Own{u}", "from_year": 2001, "to_year": 2025} for u, *_ in comps]
    rows += [{"utility_id_eia": 1, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},
             {"utility_id_eia": 99, "state": "AA", "ultimate_parent": "P" if why == "same_parent" else "Q", "from_year": 2001, "to_year": 2025}]
    usable = all_usable([host, future] + comps) - ({(99, "AA", 2011)} if why == "no_usable_window" else set())
    side = fh.side_run_design(treated, clean, {2015: [(99, "AA")]}, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw(table(rows), usable))
    assert (99, "AA") not in keys_of(side) and keys_of(side) == [(10 + i, "AA") for i in range(10)]
    if why == "same_parent":
        assert {"utility": "99:AA", "why": ownership.SAME_PARENT} in side.hosts.excluded_from_its_pool.iloc[0]


# ---- E2's pool ------------------------------------------------------------------------------------------------------

def test_e2_is_matched_in_the_main_pool_without_other_late_hosts(tmp_path):
    late1, late2 = (1, "AA", 10_000, COOP), (2, "AA", 10_010, COOP)
    comps = ladder(10, 12)
    _, clean, q, regions, dd = world([late1, late2], comps)
    e2 = pd.DataFrame([{"utility_id_eia": 1, "state": "AA", "cohort": 2016}])
    usable = all_usable([late1, late2] + comps)
    d = fh.e2_design(e2, clean, {(1, "AA"), (2, "AA")}, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw(header_only(tmp_path), usable))
    assert list(d.hosts.key) == [(1, "AA")] and int(d.hosts.cohort.iloc[0]) == 2016
    assert (2, "AA") not in keys_of(d) and keys_of(d) == [(10 + i, "AA") for i in range(10)]
    leaky = pd.concat([clean, pd.DataFrame([{"utility_id_eia": 2, "state": "AA"}])], ignore_index=True)
    with pytest.raises(ValueError, match="late hosts in the main comparison pool"):
        fh.e2_design(e2, leaky, {(1, "AA"), (2, "AA")}, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw(header_only(tmp_path), usable))


def test_e2_window_needs_usable_years_f_minus_6_to_f_plus_3(tmp_path):
    late1 = (1, "AA", 10_000, COOP)
    comps = ladder(10, 12)
    _, clean, q, regions, dd = world([late1], comps)
    e2 = pd.DataFrame([{"utility_id_eia": 1, "state": "AA", "cohort": 2016}])
    usable = all_usable([late1] + comps) - {(1, "AA", 2010)}            # f-6 = 2010
    d = fh.e2_design(e2, clean, {(1, "AA")}, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw(header_only(tmp_path), usable))
    assert d.hosts.empty and d.dropped == [{"utility": "1:AA", "cohort": 2016, "why": design.NOT_USABLE}]


# ---- this does not change the headline pool ------------------------------------------------------------------------------

def test_importing_the_module_leaves_the_headline_design_and_its_modules_unchanged():
    """Built before and after importing future_hosts, in a fresh interpreter: the same design, and no attribute of
    design or power_simulation added, removed or rebound by the import."""
    code = r"""
import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)
from pipeline.analysis import design, power_simulation as ps
from test_matching_rules import COOP, FUEL, YEARS, ladder, world
def build():
    hosts = [(1, "AA", 10_000, COOP)]; comps = ladder(10, 14)
    treated, clean, q, regions, dd = world(hosts, comps)
    usable = {(u, st, y) for u, st, *_ in hosts + comps for y in YEARS}
    d = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.replace(ps.HEADLINE_RULES, label="x", ownership="off"),
                                usable=usable, gas={"AA": 0.1}, unknown_load=ps.UnknownLoad.none("invented"))
    return [(tuple(k), list(m)) for k, m in zip(d.hosts.key, d.hosts.match_keys)], d.dropped
snap = {m.__name__: {k: id(v) for k, v in vars(m).items()} for m in (design, ps)}
before = build()
from pipeline.analysis import future_hosts
after = build()
assert before == after, (before, after)
for m in (design, ps):
    assert {k: id(v) for k, v in vars(m).items()} == snap[m.__name__], m.__name__
print("ok")
""" % (str(ROOT), str(Path(__file__).resolve().parent))
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().endswith("ok")


# ---- E2 and a pseudo-host with no ownership row (Joe's ruling of 2026-11-19) --------------------------------------------

def e2_records(*keys):
    """E2 records whose single history crosses in 2025, so f = 2018 and the fake window is 2012 to 2021."""
    return {k: {"histories": pd.DataFrame([series(2025)]), "complete": True, "why_incomplete": [], "slow_path": None} for k in keys}


OWN_E2 = {(1, "AA"): IOU, (2, "AA"): IOU, (3, "AA"): COOP, (4, "AA"): IOU, (5, "AA"): IOU}


def test_e2_uncovered_years_reads_every_year_of_the_fake_window():
    t = table([{"utility_id_eia": 2, "ultimate_parent": "P", "from_year": 2001, "to_year": 2025},       # covers 2012 to 2021
               {"utility_id_eia": 4, "ultimate_parent": "Q", "from_year": 2015, "to_year": 2025}])      # covers part of it
    assert fh.e2_uncovered_years((1, "AA"), 2018, t, OWN_E2) == list(range(2012, 2022))       # investor-owned, no row
    assert fh.e2_uncovered_years((2, "AA"), 2018, t, OWN_E2) == []
    assert fh.e2_uncovered_years((3, "AA"), 2018, t, OWN_E2) == []                          # a cooperative is its own owner
    assert fh.e2_uncovered_years((4, "AA"), 2018, t, OWN_E2) == [2012, 2013, 2014]
    with pytest.raises(ValueError, match="no ownership class"):
        fh.e2_uncovered_years((9, "AA"), 2018, t, OWN_E2)


def test_e2_an_investor_owned_pseudo_host_with_no_covering_row_is_left_out_and_named_with_the_reason():
    t = table([{"utility_id_eia": 2, "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}])
    units = e2_records((1, "AA"), (2, "AA"), (3, "AA"))
    e2, left = fh.e2_units(units, set(), set(), NONE, ownership=t, ownership_of=OWN_E2)
    assert e2.to_dict("records") == [{"utility_id_eia": 2, "state": "AA", "cohort": 2018},
                                     {"utility_id_eia": 3, "state": "AA", "cohort": 2018}]
    (x,) = left
    assert x["utility"] == "1:AA" and x["ownership_rule_of_2026_11_19"] is True
    assert x["years_with_no_ownership_row"] == list(range(2012, 2022)) and x["fake_window"] == [2012, 2021]
    assert x["why"] == [fh.E2_NO_OWNERSHIP_ROW.format(years="every year (2012 to 2021)")]
    assert "no shared parent" in x["why"][0] and "session's reading" in x["why"][0]
    # without the table the rule is not applied (as before the ruling); a table without the classes stops
    e2_old, left_old = fh.e2_units(units, set(), set(), NONE)
    assert len(e2_old) == 3 and left_old == []
    with pytest.raises(ValueError, match="needs ownership_of"):
        fh.e2_units(units, set(), set(), NONE, ownership=t)


def test_e2_the_rule_is_general_and_the_ruling_scope_guard_stops_on_a_unit_it_does_not_name():
    """The rule names no unit: every investor-owned pseudo-host with an uncovered year leaves, a partly covered one
    included. The guard in main lets through only the unit the ruling names."""
    t = table([{"utility_id_eia": 4, "ultimate_parent": "Q", "from_year": 2015, "to_year": 2025}])
    e2, left = fh.e2_units(e2_records((1, "AA"), (4, "AA"), (5, "AA")), set(), set(), NONE, ownership=t, ownership_of=OWN_E2)
    assert e2.empty and [x["utility"] for x in left] == ["1:AA", "4:AA", "5:AA"]
    assert left[1]["why"] == [fh.E2_NO_OWNERSHIP_ROW.format(years="the years 2012, 2013, 2014")]
    assert [x["utility"] for x in fh.e2_ruling_scope(left, names={(1, "AA"), (4, "AA"), (5, "AA")})] == ["1:AA", "4:AA", "5:AA"]
    with pytest.raises(SystemExit, match=r"also remove \['4:AA', '5:AA'\]"):
        fh.e2_ruling_scope(left, names={(1, "AA")})
    assert fh.E2_RULING_NAMES == {(12685, "MS")}
    # a unit left out for another reason is not counted as the rule's
    _, left2 = fh.e2_units(e2_records((1, "AA")), {(1, "AA")}, set(), NONE, ownership=t, ownership_of=OWN_E2)
    assert left2 == [{"utility": "1:AA", "why": ["set aside"]}] and fh.e2_ruling_scope(left2, names=set()) == []


def test_e2_rule_leaves_the_headline_design_identical(tmp_path):
    """The headline design built before and after E2's units are selected under the rule is the same design; the rule
    reads no frame the headline design is built from and changes none."""
    hosts = [(1, "AA", 10_000, IOU), (2, "AA", 20_000, COOP)]
    comps = ladder(10, 14, own=IOU) + [(60, "AA", 20_010, COOP), (61, "AA", 20_020, IOU)]
    treated, clean, q, regions, dd = world(hosts, comps)
    t = table([{"utility_id_eia": u, "ultimate_parent": f"Own{u}", "from_year": 2001, "to_year": 2025} for u, *_ in comps]
              + [{"utility_id_eia": 2, "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}])      # host 1 has no row
    usable = all_usable(hosts + comps)
    frames = [f.copy() for f in (treated, clean, q, regions)]
    head = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw(t, usable))
    own_of = ps.ownership_classes(q)
    e2, left = fh.e2_units(e2_records((1, "AA"), (60, "AA")), set(), set(), NONE, ownership=t, ownership_of=own_of)
    assert [x["utility"] for x in left] == ["1:AA"] and list(e2.utility_id_eia) == [60]
    again = design.build_with_rules(treated, clean, q, regions, FUEL, dd, ps.HEADLINE_RULES, **kw(t, usable))
    assert fh.same_design(again, head) == []
    assert all(a.equals(b) for a, b in zip(frames, (treated, clean, q, regions)))
    assert (1, "AA") in [tuple(k) for k in head.hosts.key]          # the host the E2 rule would leave out stays a headline host


# ---- the report-only block on investor-owned future hosts and rule 2.2 (Joe, 2026-11-19, D-107) ---------------------------

def test_the_report_selects_a_future_host_with_no_row_in_some_window_year_as_the_bar_does():
    # cohort 2015, window 2009-2018. 70: rows 2010-2025 (2009 uncovered); 71: no row at all; 72: covered every year;
    # 73: cooperative with no row. Rule 2.2 read year by year bars 70 and 71 for an investor-owned host; the report must
    # select exactly those, and must not fall back to "no row in any window year" (which would select 71 only).
    t = table([{"utility_id_eia": 70, "state": "AA", "ultimate_parent": "Z", "from_year": 2010, "to_year": 2025},
               {"utility_id_eia": 72, "state": "AA", "ultimate_parent": "Y", "from_year": 2001, "to_year": 2025},
               {"utility_id_eia": 1, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}])
    own = {(1, "AA"): IOU, (70, "AA"): IOU, (71, "AA"): IOU, (72, "AA"): IOU, (73, "AA"): COOP}
    admitted = {2015: [(70, "AA"), (71, "AA"), (72, "AA"), (73, "AA")], 2016: [(72, "AA")]}
    got = fh.investor_owned_with_an_uncovered_window_year(admitted, t, own)
    assert got == {(70, "AA"): [2015], (71, "AA"): [2015]}
    barred = ownership.ineligible_for(t, (1, "AA"), ownership.window_years(2015), admitted[2015], own)
    assert set(got) == {k for k, why in barred.items() if why == ownership.NO_ROW}      # the same per-year test as the bar


def test_the_reports_description_says_some_year_and_year_by_year():
    src = (ROOT / "pipeline" / "analysis" / "future_hosts.py").read_text()
    assert "no ownership row in some year of a headline cohort's" in src and "read year by year" in src
