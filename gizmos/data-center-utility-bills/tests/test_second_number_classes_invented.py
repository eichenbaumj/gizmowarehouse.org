"""The proposed exhaustive classification of the second number's utilities (pipeline/analysis/second_number_classes.py),
kept as the SUPERSEDED RECORD of what was proposed (D-104); Joe adopted it with qualifications (D-105), and the adopted
classification is tested in tests/test_second_number_adopted_invented.py. Invented doses only: no file under data/ is read and no price exists here."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import second_number as sn  # noqa: E402
from pipeline.analysis import second_number_classes as sc  # noqa: E402

N_PRE = 3
CAP = 25.0


# ---- every class, on invented doses -----------------------------------------------------------------------------------

@pytest.mark.parametrize("assigned, changes, reach, common, expected, sub", [
    (None, [3.0, 5.0], True, None, sc.NO_SINGLE_DOSE, None),                    # 1: no dose as assigned
    (None, [], True, None, sc.NO_SINGLE_DOSE, None),                            # 1: no range at all
    (0.0, [0.0, 0.0, 0.0], False, None, sc.NO_SITE_IN_REACH, None),             # 2
    (0.0, [0.0, 0.0, 0.0], True, None, sc.ZERO_CHANGE, None),                   # 3
    (1.0, [1.0, 0.5, 1.2], True, None, sc.SETTLED, sc.SUB_POSITIVE_EVERY),      # 4
    (0.0, [0.0, 0.0, 1.5], True, None, sc.SETTLED, sc.SUB_ZERO_ASSIGNED),       # 4, not a verified zero
    (1.0, [1.0, 0.0, 1.0], True, None, sc.SETTLED, sc.SUB_OTHER),               # 4, positive as assigned, zero in a case
    (5.0, [5.0, 1.0, 9.0], True, None, sc.UNCERTAIN, None),                     # 5
    (0.0, [0.0, 0.0, 6.0], True, None, sc.APPARENT_ZERO, None),                 # 6
    (8.0, [8.0, 0.0, 8.0], True, None, sc.POSITIVE_ZERO_SOME, None),            # 7
    (8.0, [8.0, -3.0, 8.0], True, None, sc.POSITIVE_ZERO_SOME, None),           # 7, negative in a case with a > 0
    (0.0, [0.0, -3.0, 0.0], True, None, sc.OTHER, None),                        # 8
    (-1.0, [-1.0, -4.0, 2.0], True, None, sc.OTHER, None),                      # 8
    (None, [4.0, 4.0], True, 4.0, sc.SETTLED, sc.SUB_POSITIVE_EVERY),           # 1 does not apply: one common dose
])
def test_every_class(assigned, changes, reach, common, expected, sub):
    r = sc.classify(assigned, changes, reach, common_dose=common)
    assert r["class"] == expected
    assert r["sub_label"] == sub


# ---- boundaries --------------------------------------------------------------------------------------------------------

def test_exactly_two_points_is_not_settled_and_just_under_is():
    assert sc.classify(3.0, [3.0, 1.0, 3.0], True)["class"] == sc.UNCERTAIN          # hi - lo == 2
    assert sc.classify(3.0, [3.0, 1.0 + 1e-9, 3.0], True)["class"] == sc.SETTLED
    assert sc.classify(2.0, [2.0, 0.0], True)["class"] == sc.POSITIVE_ZERO_SOME       # lo exactly 0, range 2
    assert sc.classify(2.5, [2.5, 0.5, 2.5], True)["class"] == sc.UNCERTAIN           # lo above 0, range exactly 2
    assert sc.classify(2.0, [2.0, 1e-12, 2.0], True)["class"] == sc.SETTLED           # lo just above 0, range just under 2


def test_exactly_zero():
    assert sc.classify(0.0, [0.0, 0.0], True)["class"] == sc.ZERO_CHANGE
    assert sc.classify(1e-12, [1e-12, 0.0], True)["class"] == sc.SETTLED              # not exactly zero: not class 3
    assert sc.classify(0.0, [0.0, 3.0], True)["class"] == sc.APPARENT_ZERO
    assert sc.classify(1e-12, [1e-12, 0.0, 3.0], True)["class"] == sc.POSITIVE_ZERO_SOME


def test_above_the_cap_at_both_ends_is_zero_change_with_load_in_reach():
    # One history at 30 then 40 points (above the 25-point cap at both ends), one with the site taken off (no load).
    ends = np.array([[30.0, 30.0, 30.0, 40.0, 40.0, 40.0], [0.0] * 6])
    capped = sn.change(ends, N_PRE, CAP)
    uncapped = sn.change(ends, N_PRE, None)
    assert np.all(capped == 0) and uncapped[0] == pytest.approx(10.0)
    reach = sc.reach_from_endpoints(ends)
    assert reach
    assert sc.classify(float(capped[0]), capped, reach)["class"] == sc.ZERO_CHANGE
    assert sc.zero_change_kind(ends[0], N_PRE, CAP) == "at_or_above_the_cap_in_every_endpoint_year"
    assert sc.zero_change_kind(ends[1], N_PRE, CAP) == "no_load_at_either_endpoint"
    assert sc.zero_change_kind([5.0] * 6, N_PRE, CAP) == "equal_capped_averages_below_the_cap"
    assert sc.zero_change_kind([4.0, 5.0, 6.0, 6.0, 5.0, 4.0], N_PRE, CAP) == "equal_capped_averages_below_the_cap"
    assert sc.zero_change_kind([20.0, 25.0, 25.0, 25.0, 25.0, 30.0], N_PRE, CAP) == \
        "equal_capped_averages_below_the_cap_uncapped_change_not_zero"
    # exactly at the cap in every endpoint year counts as at or above it
    assert sc.zero_change_kind([25.0] * 6, N_PRE, CAP) == "at_or_above_the_cap_in_every_endpoint_year"


def test_reach_is_any_uncapped_load_at_an_endpoint_in_any_history():
    assert not sc.reach_from_endpoints(np.zeros((6, 6)))
    e = np.zeros((6, 6))
    e[5, 4] = 0.001                                   # one history, one year after
    assert sc.reach_from_endpoints(e)
    with pytest.raises(ValueError):
        sc.reach_from_endpoints([[np.nan, 0, 0, 0, 0, 0]])


# ---- precedence -------------------------------------------------------------------------------------------------------

def test_precedence():
    # class 1 before everything, even with nothing in reach
    assert sc.classify(None, [0.0, 0.0], False)["class"] == sc.NO_SINGLE_DOSE
    # class 3 before settled: a zero change everywhere is never just "settled"
    assert sc.classify(0.0, [0.0, 0.0], True)["class"] == sc.ZERO_CHANGE
    # settled before apparent zero under the proposal; the alternative order puts it in apparent zero
    assert sc.classify(0.0, [0.0, 1.0], True)["class"] == sc.SETTLED
    assert sc.classify(0.0, [0.0, 1.0], True, precedence=sc.APPARENT_ZERO_FIRST)["class"] == sc.APPARENT_ZERO
    # the alternative order moves nothing else
    for a, v in [(5.0, [5.0, 6.0]), (0.0, [0.0, 0.0]), (0.0, [0.0, 7.0]), (8.0, [8.0, 0.0])]:
        assert sc.classify(a, v, True)["class"] == sc.classify(a, v, True, precedence=sc.APPARENT_ZERO_FIRST)["class"]
    # uncertain before apparent zero cannot conflict (a == 0 means lo <= 0); class 7 after 6 cannot either (a > 0 vs a == 0)
    with pytest.raises(ValueError):
        sc.classify(1.0, [1.0], True, precedence="no such order")


def test_inconsistent_or_missing_inputs_stop_in_words():
    with pytest.raises(ValueError):
        sc.classify(0.0, [0.0, 2.0], False)                   # nothing in reach but a change
    with pytest.raises(ValueError):
        sc.classify(5.0, [1.0, 2.0], True)                    # the as-assigned history must be one of them
    with pytest.raises(ValueError):
        sc.classify(1.0, [1.0, np.nan], True)
    with pytest.raises(ValueError):
        sc.classify(1.0, [], True)


# ---- exhaustive and exclusive on a random invented population ---------------------------------------------------------

def _random_population(n=20000, seed=11):
    rng = np.random.default_rng(seed)
    out = []
    grid = np.array([-3.0, -2.0, -1.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.99, 2.0, 3.0, 25.0])
    for _ in range(n):
        h = int(rng.integers(1, 7))
        v = rng.choice(grid, h) if rng.random() < 0.6 else np.round(rng.normal(0, 4, h), int(rng.integers(0, 3)))
        a = float(v[int(rng.integers(0, h))])
        reach = True if np.any(v != 0) else bool(rng.random() < 0.5)
        out.append((a, v, reach))
    return out


def _predicates(a, v, reach):
    """Each class's full definition written out on its own, with "not classed above" made explicit."""
    lo, hi = float(np.min(v)), float(np.max(v))
    c2 = not reach
    c3 = reach and lo == 0 and hi == 0
    settled = hi - lo < 2
    c4 = not (c2 or c3) and settled
    rest = not (c2 or c3 or c4)
    c5 = rest and lo > 0
    c6 = rest and not c5 and a == 0 and hi > 0
    c7 = rest and not (c5 or c6) and a > 0 and lo <= 0
    c8 = rest and not (c5 or c6 or c7)
    return {sc.NO_SITE_IN_REACH: c2, sc.ZERO_CHANGE: c3, sc.SETTLED: c4, sc.UNCERTAIN: c5, sc.APPARENT_ZERO: c6,
            sc.POSITIVE_ZERO_SOME: c7, sc.OTHER: c8}


def test_exhaustive_and_exclusive_on_a_random_population():
    seen = set()
    for a, v, reach in _random_population():
        r = sc.classify(a, v, reach)
        p = _predicates(a, v, reach)
        assert sum(p.values()) == 1, (a, v, reach, p)
        assert p[r["class"]], (a, v, reach, r)
        assert r["class"] in sc.CLASSES
        seen.add(r["class"])
    assert seen == set(sc.CLASSES) - {sc.NO_SINGLE_DOSE}                    # every class with a dose is reached
    assert sc.classify(None, [1.0], True)["class"] == sc.NO_SINGLE_DOSE


def test_agrees_with_rule_8_2_wherever_the_text_gives_exactly_one_class():
    n_unique = 0
    for a, v, reach in _random_population():
        m = sc.rule_8_2_text_matches(a, v)
        if len(m) != 1:
            continue
        (only,) = m
        n_unique += 1
        assert sc.rule_8_2_as_built(a, v) == only                            # the as-built order agrees there too
        assert sc.classify(a, v, reach)["class"] == sc.PROPOSED_FOR_TEXT[only], (a, v, reach, only)
    assert n_unique > 1000


def test_where_the_text_gives_two_classes_or_none():
    # zero in every case: the text gives both "no site in reach" and "settled" (a range of 0 is under two points)
    assert sc.rule_8_2_text_matches(0.0, [0.0, 0.0]) == {sn.NO_SITE, sn.SETTLED}
    # zero as assigned and above zero in a case within two points: "settled" and "apparent zero"
    assert sc.rule_8_2_text_matches(0.0, [0.0, 1.0]) == {sn.SETTLED, sn.APPARENT_ZERO}
    # positive as assigned, zero in a case, two points or more apart: none of the four (as built: unclassified)
    assert sc.rule_8_2_text_matches(5.0, [5.0, 0.0]) == set()
    assert sc.rule_8_2_as_built(5.0, [5.0, 0.0]) == sn.UNCLASSIFIED
    assert sc.classify(5.0, [5.0, 0.0], True)["class"] == sc.POSITIVE_ZERO_SOME
    # the as-built order on the two-class cases
    assert sc.rule_8_2_as_built(0.0, [0.0, 0.0]) == sn.NO_SITE
    assert sc.rule_8_2_as_built(0.0, [0.0, 1.0]) == sn.APPARENT_ZERO


# ---- the proposal on doses built by second_number's own functions ------------------------------------------------------

def test_classes_from_second_numbers_within_history_changes():
    """Six histories of load share in points for four invented utilities, through sn.history_changes at the 25-point cap."""
    years = list(sn.PRE) + list(sn.POST)
    idx = pd.MultiIndex.from_tuples([(1, "AA"), (2, "AA"), (3, "AA"), (4, "AA")], names=sn.KEY)
    def h(rows):
        return pd.DataFrame(rows, index=idx, columns=years, dtype=float)
    base = [[0] * 6,                                  # 1: nothing anywhere
            [30, 30, 30, 40, 40, 40],                 # 2: above the cap at both ends
            [0, 0, 0, 0, 0, 0],                       # 3: zero as assigned
            [0, 0, 0, 8, 8, 8]]                       # 4: eight points after
    off = [[0] * 6, [0] * 6, [0] * 6, [0] * 6]        # every unresolved site taken off
    up = [[0] * 6, [30, 30, 30, 40, 40, 40], [0, 0, 0, 1, 1, 1], [0, 0, 0, 8, 8, 8]]
    pts = {"as_assigned_as_built": h(base), "as_assigned_no_anchoring": h(base), "lower_as_built": h(off),
           "lower_no_anchoring": h(off), "upper_as_built": h(up), "upper_no_anchoring": h(up)}
    ch = sn.history_changes(pts, cap=CAP)
    got = {}
    for k in idx:
        ends = np.vstack([pts[name].loc[k, years].values for name in sn.HISTORIES])
        got[k[0]] = sc.classify(float(ch.loc[k, sn.ASSIGNED]), ch.loc[k].values, sc.reach_from_endpoints(ends))["class"]
    assert got == {1: sc.NO_SITE_IN_REACH, 2: sc.ZERO_CHANGE, 3: sc.SETTLED, 4: sc.POSITIVE_ZERO_SOME}
    # as built, utility 2 is "no site in reach" and utility 4 is in none of the four
    assert sc.rule_8_2_as_built(float(ch.loc[idx[1], sn.ASSIGNED]), ch.loc[idx[1]].values) == sn.NO_SITE
    assert sc.rule_8_2_as_built(float(ch.loc[idx[3], sn.ASSIGNED]), ch.loc[idx[3]].values) == sn.UNCLASSIFIED


# The proposal's leverage-share test ran through second_number.run_summary's as-built signature, which the adopted
# classification replaced (D-105); the adopted shares, classes 5 to 8 and class 2 on separate lines, are tested by hand in
# tests/test_second_number_adopted_invented.py.
