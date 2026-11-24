"""Rule 2.2 read year by year (Joe, 2026-11-19, D-107, adopting R3 of D-106): an investor-owned candidate with no ownership
row in SOME year of an investor-owned host's window is not eligible for that host, before matching, so the next eligible
unit enters. Before the repair, ownership.ineligible_for barred such a unit only when no row covered ANY window year.

Invented inputs only: the worlds and tables are built here or by tests/test_matching_rules.py's helpers. Nothing under
data/ is read. No estimator is fitted, so no numerical tolerance applies; every assertion is exact.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import design, ownership  # noqa: E402
from test_matching_rules import COOP, FUEL, IOU, PUBLIC, keys_of, ladder, table, world  # noqa: E402

COHORT = 2015
WINDOW = ownership.window_years(COHORT)                 # 2009 to 2018, g-6 to g+3
HOST = (1, "AA")
CAND = (40, "AA")


def rows_for(uid, spans, state="AA", parent="Z"):
    """One ownership row per (from_year, to_year) span for unit `uid`, each with its own parent unless `parent` is given."""
    return [{"utility_id_eia": uid, "state": state, "ultimate_parent": parent, "from_year": a, "to_year": b} for a, b in spans]


def host_row(parent="P"):
    return rows_for(1, [(2001, 2025)], parent=parent)


def classes(host=IOU, cand=IOU):
    return {HOST: host, CAND: cand}


# ---- the bar, on ownership.ineligible_for ---------------------------------------------------------------------------------

@pytest.mark.parametrize("spans,uncovered", [
    ([(2010, 2025)], [2009]),                           # the first window year uncovered
    ([(2001, 2017)], [2018]),                           # the last window year uncovered
    ([(2001, 2011), (2013, 2025)], [2012]),             # a gap inside the window
    ([(2016, 2025)], [2009, 2010, 2011, 2012, 2013, 2014, 2015]),   # most of the window, as Versant's 2011-2019 against NSTAR
])
def test_a_unit_covered_for_part_of_the_window_is_barred_for_an_investor_owned_host(spans, uncovered):
    t = table(host_row() + rows_for(40, spans))
    assert [y for y in WINDOW if not len(ownership._rows(t, CAND, [y]))] == uncovered      # the world is as described
    assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes()) == {CAND: ownership.NO_ROW}


def test_a_unit_with_no_row_in_any_window_year_is_still_barred():
    t = table(host_row() + rows_for(40, [(2020, 2025)]))
    assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes()) == {CAND: ownership.NO_ROW}
    t = table(host_row())
    assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes()) == {CAND: ownership.NO_ROW}


@pytest.mark.parametrize("spans,state", [
    ([(2001, 2025)], "AA"),                             # one row over the whole window
    ([(2009, 2018)], "AA"),                             # exactly the window, both ends inclusive
    ([(2001, 2012), (2013, 2025)], "AA"),               # two consecutive rows
    ([(2001, 2012), (2012, 2025)], "AA"),               # two rows overlapping in the closing year (rule 2.1)
    ([(2001, 2025)], ""),                               # a blank state covers every state of the id
])
def test_a_unit_covered_in_every_window_year_is_not_barred(spans, state):
    t = table(host_row() + rows_for(40, spans, state=state))
    assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes()) == {}


def test_a_row_for_the_same_id_in_another_state_does_not_cover_the_candidate():
    t = table(host_row() + rows_for(40, [(2001, 2025)], state="BB"))
    assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes()) == {CAND: ownership.NO_ROW}


@pytest.mark.parametrize("host_class", [PUBLIC, COOP])
def test_a_public_or_cooperative_host_is_unaffected(host_class):
    for spans in ([(2010, 2025)], [(2020, 2025)], []):
        t = table(host_row() + rows_for(40, spans))
        assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes(host=host_class)) == {}


@pytest.mark.parametrize("cand_class", [PUBLIC, COOP])
def test_a_public_or_cooperative_candidate_is_unaffected(cand_class):
    for spans in ([(2010, 2025)], [(2020, 2025)], []):
        t = table(host_row() + rows_for(40, spans))
        assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes(cand=cand_class)) == {}


def test_affiliates_included_still_skips_the_bar():
    t = table(host_row() + rows_for(40, [(2010, 2025)]))
    assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes(), affiliates_included=True) == {}
    own_id = (1, "BB")                                   # but the host's own utility is never readmitted
    assert ownership.ineligible_for(t, HOST, WINDOW, [own_id], {**classes(), own_id: IOU}, affiliates_included=True) == \
        {own_id: ownership.OWN_UTILITY}


def test_the_own_utility_reason_still_takes_precedence():
    own_id = (1, "BB")                                   # the host's EIA id in another state, rows for part of the window only
    t = table(host_row() + rows_for(1, [(2010, 2025)], state="BB", parent="Q"))
    assert ownership.ineligible_for(t, HOST, WINDOW, [own_id], {**classes(), own_id: IOU}) == {own_id: ownership.OWN_UTILITY}


def test_the_same_parent_reason_still_takes_precedence():
    # shares the host's parent P in 2012 and has no row in 2009: same parent is the reason given, as before
    t = table(host_row() + rows_for(40, [(2010, 2011)], parent="Q") + rows_for(40, [(2012, 2012)], parent="P")
              + rows_for(40, [(2013, 2025)], parent="Q"))
    assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes()) == {CAND: ownership.SAME_PARENT}


def test_the_window_is_the_one_passed_and_years_outside_it_do_not_count():
    t = table(host_row() + rows_for(40, [(2009, 2018)]))
    assert ownership.ineligible_for(t, HOST, WINDOW, [CAND], classes()) == {}
    assert ownership.ineligible_for(t, HOST, ownership.window_years(2016), [CAND], classes()) == {CAND: ownership.NO_ROW}


def test_the_reason_says_the_bar_is_read_year_by_year():
    assert "a year" in ownership.NO_ROW and "window" in ownership.NO_ROW
    assert "rule 2.2" in ownership.NO_ROW


# ---- through the design builder: the next eligible unit enters, and the support rule is tested again -----------------

def test_the_next_eligible_unit_enters_a_match_when_a_partly_covered_unit_is_barred():
    host = (1, "AA", 10_000, IOU)
    partial = (40, "AA", 10_010, IOU)                    # the nearest in size; rows 2010-2025 only, so 2009 is unknown
    full = (41, "AA", 10_020, IOU)                       # covered every year
    comps = [partial, full] + ladder(60, 12, own=COOP)
    treated, clean, q, regions, dd = world([host], comps)
    t = table(host_row() + rows_for(40, [(2010, 2025)]) + rows_for(41, [(2001, 2025)], parent="R"))
    d = design.build(treated, clean, q, regions, FUEL, dd, ownership=t)
    got = keys_of(d)
    assert (40, "AA") not in got
    assert got == [(41, "AA")] + [(60 + i, "AA") for i in range(9)]       # the eleventh in size, 69:AA, is now tenth
    assert d.hosts.excluded_from_its_pool.iloc[0] == [{"utility": "40:AA", "why": ownership.NO_ROW}]
    assert d.hosts.pool_in_the_reference_year.iloc[0] == 13


def test_a_cooperative_host_keeps_the_partly_covered_unit_in_the_same_world():
    host = (1, "AA", 10_000, COOP)
    comps = [(40, "AA", 10_010, IOU), (41, "AA", 10_020, IOU)] + ladder(60, 12, own=COOP)
    treated, clean, q, regions, dd = world([host], comps)
    t = table(host_row() + rows_for(40, [(2010, 2025)]) + rows_for(41, [(2001, 2025)], parent="R"))
    d = design.build(treated, clean, q, regions, FUEL, dd, ownership=t)
    assert keys_of(d)[0] == (40, "AA") and d.hosts.excluded_from_its_pool.iloc[0] == []


def test_the_support_rule_is_tested_on_the_pool_after_the_bar():
    # ten eligible before the bar, nine after: the host no longer keeps its place
    host = (1, "AA", 10_000, IOU)
    comps = [(40, "AA", 10_010, IOU)] + ladder(60, 9, own=COOP)
    treated, clean, q, regions, dd = world([host], comps)
    t = table(host_row() + rows_for(40, [(2010, 2025)]))
    d = design.build(treated, clean, q, regions, FUEL, dd, ownership=t)
    r = design.support_rule(d).iloc[0]
    assert r.pool_in_the_reference_year == 9 and not r.keeps_its_place
    covered = table(host_row() + rows_for(40, [(2001, 2025)]))
    r2 = design.support_rule(design.build(treated, clean, q, regions, FUEL, dd, ownership=covered)).iloc[0]
    assert r2.pool_in_the_reference_year == 10 and r2.keeps_its_place
