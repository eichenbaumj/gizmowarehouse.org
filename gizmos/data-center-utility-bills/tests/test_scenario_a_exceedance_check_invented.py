"""Tests of the capacity exceedance check for scenario A (tests/scenario_a_exceedance_check.py) on invented inputs.

Invented inputs only: no file under data/ is read. Each world plants one case of Joe's question (D-111): a returned site
whose unit was filled by arrivals (newly introduced), a unit over capacity before and unchanged (pre-existing), one
over before and further over (made larger), and a world with none. Classes are compared exactly; loads to 1e-9 GWh.
The last tests show the checks can fail, by breaks made in the test process (monkeypatch or a changed input), never by
editing the code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scenario_a_independent_check as ck  # noqa: E402
import scenario_a_exceedance_check as ex   # noqa: E402

TOL = 1e-9
PANEL = {(5, "AA"), (6, "AA"), (7, "AA"), (8, "AA"), (9, "AA")}


def world(resident, placed, cap, reading=None):
    """resident: (fid, unit id, GWh) sites not among those placed, all in state AA. placed: (fid, on, candidates, GWh).
    Returns the accounting table indexed by utility id, and the placement records."""
    reading = ex.LIFT_FIRST if reading is None else reading
    all_sites = pd.DataFrame({"fid": [r[0] for r in resident] + [p[0] for p in placed],
                              "unit": [(r[1], "AA") for r in resident] + [(p[1], "AA") for p in placed],
                              "gwh": [float(r[2]) for r in resident] + [float(p[3]) for p in placed]})
    sites = pd.DataFrame({"fid": [p[0] for p in placed], "state": "AA", "utility_id_eia": [p[1] for p in placed],
                          "candidates": [ck.parse_candidates(p[2]) for p in placed],
                          "load_gwh": [float(p[3]) for p in placed]})
    sites["frame_order"] = range(len(sites))
    fids = set(sites.fid)
    carried = {}
    for fid, unit, g in zip(all_sites.fid, all_sites.unit, all_sites.gwh):
        if reading.carried == "all_assigned" or fid not in fids:
            carried[unit] = carried.get(unit, 0.0) + g
    capacity = {(u, "AA"): float(c) for u, c in cap.items()}
    records = ck.place(sites, carried, capacity, PANEL, reading)
    t = ex.account(all_sites, sites, records, capacity)
    return t.set_index("utility_id_eia"), records


# ---- the classes, exact comparisons ---------------------------------------------------------------------------------

def test_classify_is_exact_with_equality_within():
    assert ex.classify(10.0, 10.0, 10.0) == "within"                  # equal to capacity fits, as pick_utilities
    assert ex.classify(9.0, 10.0 + 1e-12, 10.0) == "newly_introduced"  # no tolerance: a raw excess is an excess
    assert ex.classify(12.0, 12.0, 10.0) == "pre_existing"            # over before, no larger after
    assert ex.classify(12.0, 11.0, 10.0) == "pre_existing"
    assert ex.classify(12.0, 12.0 + 1e-12, 10.0) == "pre_existing_made_larger"
    assert ex.classify(12.0, 9.0, 10.0) == "over_as_assigned_within_at_end"
    assert ex.classify(1.0, 99.0, float("nan")) == "no_recorded_capacity_measure"


# ---- the four invented worlds ---------------------------------------------------------------------------------------

def test_newly_introduced_a_returned_site_whose_unit_was_filled_by_arrivals(reading=None):
    """Unit 5 (capacity 15) carries the unresolved site L (12) as assigned: within. Lifted first, 5 is empty when the
    larger site A (14, on 6) is placed, so A arrives on 5. L's one other candidate, 7 (capacity 10), cannot hold it, so
    L is returned to 5 with no capacity test: final 26, over by 11. A newly introduced exceedance on 5."""
    t, recs = world(resident=[], placed=[("A", 6, "5;6", 14.0), ("L", 5, "7;5", 12.0)],
                    cap={5: 15.0, 6: 100.0, 7: 10.0}, reading=reading)
    u = t.loc[5]
    assert abs(u.load_as_assigned_gwh - 12.0) < TOL and abs(u.final_load_gwh - 26.0) < TOL
    assert u["class"] == "newly_introduced"
    assert abs(u.excess_at_end_gwh - 11.0) < TOL and abs(u.excess_share_of_capacity - 11.0 / 15.0) < TOL
    assert u.returned.startswith("L=12.000000(no_other_candidate_fits)") and u.arriving.startswith("A=14.000000")
    assert (t["class"].isin(ex.DEFERRING)).sum() == 1


def test_the_same_world_under_the_modules_earlier_reading_has_no_exceedance():
    """Under the module's earlier reading 5 already carries L's 12 when A is tested (12 + 14 > 15), so A stays on 6."""
    t, recs = world(resident=[], placed=[("A", 6, "5;6", 14.0), ("L", 5, "7;5", 12.0)],
                    cap={5: 15.0, 6: 100.0, 7: 10.0}, reading=ex.EARLIER)
    assert set(t["class"]) == {"within"}
    assert {r["fid"]: r["to"] for r in recs} == {"A": 6, "L": 5}


def test_pre_existing_over_before_and_unchanged_or_smaller(resident_load=15.0):
    """Unit 8 (capacity 10) carries a resolved site r (15) and the unresolved q (3): over as assigned (18). q has no
    other candidate that fits and is returned: final 18, equal to as assigned, so pre-existing. Unit 9 (capacity 10)
    carries resolved s (14) and unresolved w (2), which leaves for 7: final 14, smaller, still pre-existing."""
    t, _ = world(resident=[("r", 8, resident_load), ("s", 9, 14.0)],
                 placed=[("q", 8, "5;8", 3.0), ("w", 9, "7;9", 2.0)], cap={5: 1.0, 7: 50.0, 8: 10.0, 9: 10.0})
    assert t.loc[8, "class"] == "pre_existing" and abs(t.loc[8, "difference_gwh"]) < TOL
    assert abs(t.loc[8, "excess_at_end_gwh"] - 8.0) < TOL
    assert t.loc[9, "class"] == "pre_existing" and abs(t.loc[9, "difference_gwh"] + 2.0) < TOL
    assert t.loc[9, "leaving"].startswith("w=2.000000(to 7)")
    assert not t["class"].isin(ex.DEFERRING).any()


def test_pre_existing_and_made_larger():
    """Unit 5 (capacity 10) carries resolved r (4) and unresolved a (5) and b (5): 14 as assigned, over. Lifted first
    it carries 4, so the larger site c (6, on 6) arrives (4 + 6 = 10 fits). a and b then find nothing else that fits
    (7 has capacity 1) and are returned: final 20, over by 10 and larger than 14. Made larger, and it defers."""
    t, _ = world(resident=[("r", 5, 4.0)], placed=[("c", 6, "5;6", 6.0), ("a", 5, "7;5", 5.0), ("b", 5, "7;5", 5.0)],
                 cap={5: 10.0, 6: 100.0, 7: 1.0})
    u = t.loc[5]
    assert u["class"] == "pre_existing_made_larger"
    assert abs(u.load_as_assigned_gwh - 14.0) < TOL and abs(u.final_load_gwh - 20.0) < TOL
    assert abs(u.excess_at_end_gwh - 10.0) < TOL and u.n_returned == 2 and u.n_arriving == 1


def test_a_world_with_none():
    """Every unresolved site moves to or stays on a unit with room; nothing is over before or after."""
    t, _ = world(resident=[("r", 5, 4.0)], placed=[("a", 6, "5;6", 3.0), ("b", 7, "5;7", 2.0), ("c", 8, "8", 1.0)],
                 cap={5: 10.0, 6: 10.0, 7: 10.0, 8: 10.0})
    assert set(t["class"]) == {"within"}
    assert abs(t.loc[5, "final_load_gwh"] - 9.0) < TOL and t.loc[8, "returned"].endswith("(no_other_panel_candidate)")


def test_a_unit_with_no_recorded_capacity_measure_is_reported_not_classed():
    t, _ = world(resident=[], placed=[("a", 6, "7;6", 30.0)], cap={7: 10.0})
    assert t.loc[6, "class"] == "no_recorded_capacity_measure"


def test_loads_of_the_same_sites_are_identical_before_and_after():
    """fsum over the same sites in another order gives the same float, so an unchanged unit shows a difference of
    exactly zero (the real inputs have loads like 0.1 + 0.2 that a running sum would not add back exactly)."""
    t, _ = world(resident=[("r1", 8, 0.1), ("r2", 8, 0.2), ("r3", 8, 0.3)], placed=[("q", 8, "8", 0.7)],
                 cap={8: 0.5})
    assert t.loc[8, "difference_gwh"] == 0.0 and t.loc[8, "class"] == "pre_existing"


def test_site_table_counts_what_carried_at_start_counts():
    """The accounting's load as assigned equals the checker's start load under the module's earlier reading."""
    k = 1 / ck.GWH_PER_MW_YEAR
    fac = pd.DataFrame({"fid": ["x", "y", "r", "n"], "state": ["AA", "AA", "AA", None],
                        "utility_id_eia": [6, 6, 7, 7], "utility_assign": ["smallest_polygon"] * 4,
                        "utility_candidates": ["7;6"] * 4, "in_dose": [True] * 4, "is_crypto": [False] * 4,
                        "mw_full": [30 * k, None, 10 * k, 5 * k], "mw_full_raw": [1.0] * 4})
    s = ex.site_table(fac)
    sums = {}
    for u, g in zip(s.unit, s.gwh):
        sums[u] = sums.get(u, 0.0) + g
    assert sums == pytest.approx(ck.carried_at_start(fac, set(), ck.EARLIER_MODULE_READING))


def test_a_placement_that_does_not_match_the_sites_is_refused():
    all_sites = pd.DataFrame({"fid": ["a"], "unit": [(6, "AA")], "gwh": [1.0]})
    sites = pd.DataFrame({"fid": ["a"], "state": ["AA"], "utility_id_eia": [6], "load_gwh": [1.0]})
    with pytest.raises(ValueError, match="differ"):
        ex.account(all_sites, sites, [], {})
    bad = [{"fid": "a", "state": "AA", "from": 7, "to": 7, "moved": False, "why": "no_other_panel_candidate"}]
    with pytest.raises(ValueError, match="starts it from"):
        ex.account(all_sites, sites, bad, {})


# ---- the checks can fail (breaks made in the test process, not in the code) --------------------------------------

def test_breaking_the_reading_hides_the_newly_introduced_case():
    """Run the newly introduced world under the module's earlier reading: the planted exceedance is not there, so it fails."""
    with pytest.raises((AssertionError, KeyError)):
        test_newly_introduced_a_returned_site_whose_unit_was_filled_by_arrivals(reading=ex.EARLIER)


def test_breaking_the_classifier_is_caught(monkeypatch):
    """Replace classify inside this process with one that never says made larger: the made-larger test fails."""
    real = ex.classify

    def blunt(a, f, c):
        out = real(a, f, c)
        return "pre_existing" if out == "pre_existing_made_larger" else out
    monkeypatch.setattr(ex, "classify", blunt)
    with pytest.raises(AssertionError):
        test_pre_existing_and_made_larger()


def test_lift_first_is_the_modules_rule_now():
    assert ex.LIFT_FIRST == ck.MODULE_READING and ex.EARLIER == ck.EARLIER_MODULE_READING != ck.MODULE_READING


def test_breaking_the_resident_load_is_caught():
    """Give the resident site a load that leaves unit 8 within capacity: the pre-existing test fails."""
    with pytest.raises(AssertionError):
        test_pre_existing_over_before_and_unchanged_or_smaller(resident_load=1.0)


def test_breaking_the_sum_is_caught(monkeypatch):
    """Replace math.fsum inside the module with a sum that drops the last term: the loads come out wrong."""
    monkeypatch.setattr(ex.math, "fsum", lambda xs: sum(list(xs)[:-1]))
    with pytest.raises(AssertionError):
        test_a_world_with_none()
