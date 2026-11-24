"""Step D's place test (pipeline/facilities/timing.py) on made-up inventories. No real data, except the last test,
which reads the frozen dating_report.json (load and sales only) and skips if it is absent."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]

import stepd_world as W  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from pipeline.facilities import timing as tm  # noqa: E402

T = 0.02


def one(inp, entries, k=(1, "AA"), screen=(0,), ceiling=tm.CEILING):
    return tm.StateRun(inp, entries, k[1], screen=screen).evaluate(k, T, ceiling)


def site(fid, mw, year, utility=1, state="AA", **kw):
    return {"fid": fid, "state": state, "mw": mw, "year": year, "utility": utility, **kw}


BASE = {(1, "AA"): 10.0, (2, "AA"): 1000.0}


def test_a_narrow_evidence_interval_keeps_its_place_and_is_admissible():
    inp = W.make([site("a", 20, 2015)], BASE)
    r = one(inp, [W.date("a", 2014, 2015, 2015, ends="evidence")])
    assert r["reference"]["crossing"] == "2016" and r["keeps_its_place"] is True
    assert r["method"] == "exact" and r["range_kind"] == "admissible"
    assert r["range"]["earliest_crossing"] == "2015" and r["range"]["latest_crossing"] == "2016"


def test_a_wide_interval_fails_and_names_the_setting():
    inp = W.make([site("a", 20, 2015)], BASE)
    r = one(inp, [W.date("a", 2011, 2015, 2015)])
    assert r["keeps_its_place"] is False and not r["fails_only_open_below"]
    assert r["failure"]["settings"]["a date"] in (2011, 2012, 2013)
    assert r["range_kind"] == "tested"


def test_failing_only_below_the_convention_of_an_open_interval_is_listed_with_the_lower_end():
    inp = W.make([site("a", 20, 2012)], BASE)
    r = one(inp, [W.date("a", None, 2012, 2012)])
    assert r["keeps_its_place"] is False and r["fails_only_open_below"] is True
    assert r["lower_end_that_would_let_it_stay"] == 2011
    assert "not misdated" in r["status"]


def test_a_provisional_convention_that_moves_the_crossing_leaves_the_reference_undefined():
    inp = W.make([site("a", 20, 2015)], BASE)
    r = one(inp, [W.date("a", 2011, 2015, 2015, convention_is="provisional")])
    assert r["reference"]["defined"] is False and r["keeps_its_place"] is None
    assert r["status"].startswith("unsettled")


def test_a_provisional_convention_that_moves_nothing_still_has_a_reference():
    inp = W.make([site("a", 20, 2015)], {(1, "AA"): 1000.0})
    r = one(inp, [W.date("a", 2014, 2015, 2015, convention_is="provisional")])
    assert r["reference"]["defined"] is True and r["reference"]["place"] == "comparison" and r["keeps_its_place"] is True


def test_an_unknown_start_is_never_read_as_no_load():
    """A row with no convention (load unknown): the frame carries no load for it, but the place test enumerates its
    histories; where they disagree the utility is unsettled, never kept on the frame's zero."""
    inp = W.make([site("a", 20, None, load_unknown=True, date_inventory_year=2015)], BASE)
    inp2 = W.make([site("a", 20, 2015)], BASE)                 # the same row with its inventory year, as patch_unknown does
    r = one(inp2, [W.date("a", 2011, 2019, None)])
    assert r["reference"]["defined"] is False and r["keeps_its_place"] is None
    # On the frame, the utility looks like a comparison utility with no load: that reading is what R2 forbids.
    fr = px.place(np.nan, 0.0)
    assert fr == "comparison"
    pf = tm.patch_unknown(inp.fac.assign(date_inventory_year=inp.fac.date_inventory_year.astype(float)))
    assert pf.energized_year["a"] == 2015


def test_the_factor_is_recomputed_in_every_configuration():
    """A start of 2023 or later moves the state's 2024 permit total and so the factor on every other permit-based site:
    utility 1 carries no question at all, yet its crossing moves with the other utility's date (D-58 rule 1.7)."""
    sites = [site("x", 9.0, 2010), site("y", 30.0, 2020, utility=2)]
    epri = {"AA": (9.0 + 30.0) * 8.76 / 1000}                        # factor 1 with y full in 2024
    inp = W.make(sites, {(1, "AA"): 10.0, (2, "AA"): 1000.0}, epri=epri)
    run = tm.StateRun(inp, [W.date("y", 2020, 2024, 2020)], "AA", screen=(0,))
    r = run.evaluate((1, "AA"), T)
    assert r["reference"]["crossing"] == "never"
    assert "anchoring" in r["uncertain_in"]
    assert r["keeps_its_place"] is False                              # with y late, the factor rises and x crosses 10 MW


def test_corners_suffice_with_no_anchoring_earlier_is_more_load():
    for start in range(1995, 2025):
        for y in range(2001, 2026):
            assert buildout.ramp_mw(10, start, y) >= buildout.ramp_mw(10, start + 1, y)


def test_the_generic_screen_is_crossed_and_reported_by_shift():
    sites = [site("a", 20, 2015), site("g", 25, 2016, utility=2)]
    inp = W.make(sites, {(1, "AA"): 10.0, (2, "AA"): 20.0})
    r = tm.StateRun(inp, [W.date("a", 2014, 2015, 2015)], "AA", screen=(0, 3, 5)).evaluate((2, "AA"), T)
    assert r["by_screen_shift"]["0"] is True and r["by_screen_shift"]["5"] is False
    assert r["keeps_its_place"] is False
    # an interval site never enters the screen; a small one is not in it either
    assert tm.screen_rows(inp, "AA", exclude={"a"}) == ["g"]


def test_over_the_ceiling_a_utility_the_envelope_cannot_settle_is_never_kept():
    inp = W.make([site("a", 20, 2015)], BASE)
    r = one(inp, [W.date("a", 2011, 2015, 2015)], ceiling=1)
    assert r["method"] == "envelope" and r["keeps_its_place"] is None
    assert "timing" in r["uncertain_in"]


# ---- the ceiling per predefined screen case (Joe, Stop 3, 2026-11-18) --------------------------------------------------

def test_the_ceiling_in_force_is_counted_per_screen_case_not_summed():
    """Each case's own count (2) is under a ceiling of 5, the three summed (6) are over it. In force since Stop 3 the
    count is per case, so every case is enumerated exactly. Reverting to the summed count sends it to the envelope,
    which cannot settle it, and this test fails."""
    inp = W.make([site("a", 20, 2015)], BASE)
    run = tm.StateRun(inp, [W.date("a", 2014, 2015, 2015, ends="evidence")], "AA", screen=(0, 3, 5))
    r = run.evaluate((1, "AA"), T, ceiling=5)
    assert r["configurations_by_screen_shift"] == {"0": 2, "3": 2, "5": 2} and r["configurations"] == 6
    assert r["method"] == "exact" and r["keeps_its_place"] is True
    assert r["ceiling_rule"] == tm.CEILING_RULE == "per_screen_case"


def test_the_summed_rule_survives_only_as_the_labelled_superseded_reading():
    inp = W.make([site("a", 20, 2015)], BASE)
    run = tm.StateRun(inp, [W.date("a", 2014, 2015, 2015, ends="evidence")], "AA", screen=(0, 3, 5))
    old = run.evaluate((1, "AA"), T, ceiling=5, rule=tm.SUMMED_SUPERSEDED)
    assert old["method"] == "envelope" and old["keeps_its_place"] is None and old["ceiling_rule"] == tm.SUMMED_SUPERSEDED
    with pytest.raises(ValueError):
        run.evaluate((1, "AA"), T, ceiling=5, rule="something else")
    import inspect
    assert "per_case" not in inspect.signature(tm.StateRun.evaluate).parameters


def test_every_case_over_the_ceiling_on_its_own_goes_to_the_envelope():
    inp = W.make([site("a", 20, 2015)], BASE)
    r = tm.StateRun(inp, [W.date("a", 2014, 2015, 2015, ends="evidence")], "AA", screen=(0, 3, 5)).evaluate((1, "AA"), T, ceiling=1)
    assert r["method"] == "envelope" and r["keeps_its_place"] is None


def test_mixed_cases_stay_unsettled_where_the_envelope_cannot_settle_the_case_over_the_ceiling():
    """Cases 0 and 3 enumerated, case 5 over the ceiling on its own (its count is made 3 here) and unsettled by the
    envelope: the verdict is unsettled, never 'keeps its place' by omission of the case."""
    inp = W.make([site("a", 20, 2015)], BASE)
    run = tm.StateRun(inp, [W.date("a", 2014, 2015, 2015, ends="evidence")], "AA", screen=(0, 3, 5))
    S5 = run.cases[2]["S"]
    real = S5.relevance

    def wider(k):
        fm, rel = real(k)
        return fm, [(qid, cl + [cl[0]]) for qid, cl in rel]          # a count of 3 for this case only
    S5.relevance = wider
    r = run.evaluate((1, "AA"), T, ceiling=2)
    assert r["configurations_by_screen_shift"] == {"0": 2, "3": 2, "5": 3}
    assert r["by_screen_shift"]["0"] is True and r["by_screen_shift"]["3"] is True and r["by_screen_shift"]["5"] is None
    assert r["keeps_its_place"] is None and r["status"].startswith("unsettled: screen case(s) [5]")


def test_a_failure_in_any_enumerated_case_is_final_even_where_another_case_is_unsettled():
    """Eligibility requires the criterion in every required case: a case enumerated exactly that fails decides 'does not
    keep its place', whatever the envelope says of a case over the ceiling."""
    inp = W.make([site("a", 20, 2015)], BASE)
    run = tm.StateRun(inp, [W.date("a", 2011, 2015, 2015)], "AA", screen=(0, 3, 5))
    S5 = run.cases[2]["S"]
    real = S5.relevance
    S5.relevance = lambda k: (real(k)[0], [(q, cl + cl) for q, cl in real(k)[1]])     # case 5 alone over the ceiling
    n0 = run.evaluate((1, "AA"), T)["configurations_by_screen_shift"]["0"]
    r = run.evaluate((1, "AA"), T, ceiling=n0)
    assert r["by_screen_shift"]["0"] is False and r["keeps_its_place"] is False


def test_over_the_ceiling_a_settled_utility_is_kept():
    inp = W.make([site("a", 20, 2015)], {(1, "AA"): 1000.0})
    r = one(inp, [W.date("a", 2011, 2015, 2015)], ceiling=1)
    assert r["method"] == "envelope" and r["keeps_its_place"] is True


def test_a_stress_never_defines_the_reference_but_a_different_place_under_it_stays_unresolved():
    """R4 and D-96: the stress is not admissible and sets no reference; but where the utility's outcome under it differs,
    its eligibility is unresolved, with its own reason, and it does not keep its place."""
    inp = W.make([site("a", 20, 2014)], BASE)
    entries = [W.date("a", 2014, 2014, 2014, stress={"start": None, "label": "whole row from 2001 (Joe, R4)"})]
    res = tm.run(inp, entries, thetas=(T,), states=["AA"], screen=(0,))
    u1 = next(r for r in res["utilities"] if r["utility"] == "1:AA")
    assert u1["reference"]["crossing"] == "2015"                       # the reference is the admissible one
    assert u1["keeps_its_place"] is True                                # the admissible verdict alone
    assert [x["reason"] for x in u1["unresolved_by_stress"]] == [tm.STRESS_REASON]
    assert u1["unresolved_by_stress"][0]["crossing_under_the_stress"] == "2001"
    s = [x for x in res["stress_scenarios"] if x["utility"] == "1:AA"]
    assert s and s[0]["is_admissible"] is False and s[0]["accepted_against_the_reference"] is False


def test_a_stress_that_leaves_the_place_unchanged_changes_nothing():
    inp = W.make([site("a", 20, 2014)], {(1, "AA"): 1000.0})
    plain = tm.run(inp, [W.date("a", 2014, 2014, 2014)], thetas=(T,), states=["AA"], screen=(0,))
    stressed = tm.run(inp, [W.date("a", 2014, 2014, 2014, stress={"start": None, "label": "x"})], thetas=(T,), states=["AA"],
                      screen=(0,))
    a = next(r for r in plain["utilities"] if r["utility"] == "1:AA")
    b = next(r for r in stressed["utilities"] if r["utility"] == "1:AA")
    assert b["unresolved_by_stress"] == [] and a == b


# ---- the five Oregon rows (Joe, Stop 3, 2026-11-18: the evidence-based dating) ---------------------------------------

OREGON = {"bi:819-0": 2021, "bi:820-0": 2018, "bi:822-0": 2018, "bi:823-0": 2018, "bi:846-0": 2021}   # first permit years


def oregon_world(base=60.0):
    from pipeline.facilities import corrections as cx
    sites = [site(f, 50, fp + 1, utility=7, state="OR", first_permit_year=fp) for f, fp in OREGON.items()]
    entries = [c for c in cx.load() if c["fid"] in OREGON and c["kind"] == "date"]
    return W.make(sites, {(7, "OR"): base}), entries


def test_the_five_oregon_rows_are_dated_by_the_corrections_file_and_never_in_the_ordinary_screen():
    """The corrections file in force governs the five: each is a date entry, so none is in the three- and five-year
    screen. Taking one entry out of the file (or putting the rows back into the screen) fails this test."""
    inp, entries = oregon_world()
    assert sorted(c["fid"] for c in entries) == sorted(OREGON)
    run = tm.StateRun(inp, entries, "OR", screen=(0, 3, 5))
    exclude = {c["fid"] for c in run.base_entries}
    assert tm.screen_rows(inp, "OR", exclude) == []
    assert tm.screen_entries(inp, "OR", 3, exclude) == [] and tm.screen_entries(inp, "OR", 5, exclude) == []
    assert sorted(run.open_below) == ["bi:819-0", "bi:822-0", "bi:823-0", "bi:846-0"]
    assert {f: run.open_below[f] for f in run.open_below} == {"bi:819-0": 2022, "bi:822-0": 2019, "bi:823-0": 2019,
                                                              "bi:846-0": 2022}


def test_the_looser_oregon_reading_bounds_two_rows_not_before_2018_and_decides_nothing():
    inp, entries = oregon_world()
    doc = tm.compare_oregon_looser_reading(inp, entries, thetas=(T,))
    used = {e["fid"]: e for e in doc["entries_used_for_the_comparison"]}
    assert sorted(used) == ["bi:822-0", "bi:823-0"]
    assert all(e["earliest"] == 2018 and e["latest"] == 2019 == e["convention"] and e["ends"] == "tested" for e in used.values())
    assert "decides nothing" in doc["what_this_is"]
    assert {r["utility"] for r in doc["every_oregon_utility"]} == {"7:OR"}
    # in force the two are open below; the comparison never edits the entries it was given
    assert all(c["earliest"] is None for c in entries if c["fid"] in used)


def test_the_looser_oregon_reading_refuses_when_the_entries_it_loosens_are_not_open_below():
    inp, entries = oregon_world()
    bad = [c if c["fid"] != "bi:822-0" else {**c, "earliest": 2018} for c in entries]
    with pytest.raises(ValueError, match="open below"):
        tm.compare_oregon_looser_reading(inp, bad, thetas=(T,))
    with pytest.raises(ValueError, match="no date entry"):
        tm.compare_oregon_looser_reading(inp, [c for c in entries if c["fid"] != "bi:823-0"], thetas=(T,))


def test_on_the_rebuilt_inventory_the_five_oregon_rows_carry_their_intervals():
    """Real data (load only): after the rebuild the five rows are interval rows at their permit-based year and outside
    the ordinary screen. Skips before a step D rebuild."""
    import pandas as pd
    p = ROOT / "data" / "interim" / "facilities.parquet"
    if not p.exists():
        pytest.skip("no rebuilt inventory")
    f = pd.read_parquet(p).set_index("fid")
    if "date_rule" not in f:
        pytest.skip("not a step D inventory")
    from pipeline.facilities import corrections as cx
    rows = f.loc[sorted(OREGON)]
    assert (rows.date_rule == "interval").all()
    assert (rows.date_basis != cx.PERMIT_LABEL).all()
    assert list(rows.energized_year.astype(int)) == [OREGON[x] + 1 for x in sorted(OREGON)]
    assert rows.date_earliest.isna().tolist() == [True, False, True, True, True]          # 819, 820, 822, 823, 846
    assert int(rows.date_earliest["bi:820-0"]) == 2018


def test_a_stress_needs_a_label():
    with pytest.raises(ValueError):
        tm.stress_entries([W.date("a", 2014, 2014, 2014, stress={"start": None})])


def test_the_permit_error_reach_sets_a_lower_end_on_open_intervals_only():
    inp = W.make([site("a", 25, 2015), site("b", 5, 2015)], BASE)
    out = tm.reach_entries(inp, [W.date("a", None, 2015, 2015), W.date("b", None, 2015, 2015), W.date("c", 2010, 2015, 2015)],
                           {"under_20": 10, "20_to_50": 16, "50_plus": 10})
    assert out[0]["earliest"] == 1999 and out[1]["earliest"] == 2005 and out[2]["earliest"] == 2010


def test_the_permit_error_reach_reproduces_the_ledgers_figures():
    p = ROOT / "data" / "frozen" / "dating_report.json"
    if not p.exists():
        pytest.skip("data/frozen/dating_report.json is absent")
    assert tm.permit_error_reach(json.loads(p.read_text())) == {"under_20": 10, "20_to_50": 16, "50_plus": 10}


def test_the_verdict_with_assignment_as_mapped_is_kept_apart_from_the_joint_one():
    """An unresolved site that can sit on utility 1: the joint verdict fails on assignment while the dates alone hold."""
    sites = [site("a", 20, 2015), site("u", 30, 2005, utility=2, assign="smallest_polygon", candidates="2;1")]
    inp = W.make(sites, BASE)
    r = one(inp, [W.date("a", 2014, 2015, 2015)])
    assert r["keeps_its_place"] is False and r["keeps_with_assignment_as_mapped"] is True
    assert "assignment" in r["uncertain_in"]


# ---- the record of what the ceiling amendment changed (decides nothing) ------------------------------------------------

def test_the_amendment_record_compares_the_superseded_summed_rule_with_the_rule_in_force():
    inp = W.make([site("a", 20, 2015)], BASE)
    entries = [W.date("a", 2014, 2015, 2015, ends="evidence")]
    doc = tm.compare_ceiling_per_screen_case(inp, entries, thetas=(T,), states=["AA"], ceiling=5, screen=(0, 3, 5))
    row = next(r for r in doc["utilities_whose_verdict_differs"] if r["utility"] == "1:AA")
    assert row["configurations_summed"] == 6
    assert row["summed_rule_until_2026_11_18"]["keeps_its_place"] is None
    assert row["summed_rule_until_2026_11_18"]["method"] == "envelope"
    assert row["in_force_per_screen_case"]["keeps_its_place"] is True
    assert row["in_force_per_screen_case"]["method"] == "exact"
    assert "decides nothing" in doc["what_this_is"] and "amended" in doc["what_this_is"]


def test_the_amendment_record_is_empty_where_the_summed_count_was_under_the_ceiling():
    inp = W.make([site("a", 20, 2015)], BASE)
    entries = [W.date("a", 2014, 2015, 2015, ends="evidence")]
    doc = tm.compare_ceiling_per_screen_case(inp, entries, thetas=(T,), states=["AA"], screen=(0, 3, 5))
    assert doc["utilities_whose_verdict_differs"] == [] and doc["utilities_over_the_ceiling_when_summed_evaluated"] == 0


def test_the_amendment_record_decides_from_the_summed_rules_own_row_not_from_a_separate_count(monkeypatch):
    """Whatever any separate formula would count, a utility whose summed-rule row went to the envelope is evaluated
    under the rule in force. Here the summed-rule row is forced to the envelope for a utility whose real count is 2 per
    case (6 summed, under the real ceiling): a count-based pre-filter would skip it; the record does not."""
    inp = W.make([site("a", 20, 2015)], BASE)
    entries = [W.date("a", 2014, 2015, 2015, ends="evidence")]
    real = tm.StateRun.evaluate

    def fake(self, k, theta, ceiling=tm.CEILING, rule=tm.CEILING_RULE):
        r = real(self, k, theta, ceiling, rule)
        if rule == tm.SUMMED_SUPERSEDED and k == (1, "AA"):
            r = {**r, "method": "envelope", "keeps_its_place": None, "status": "unsettled: forced for the test"}
        return r
    monkeypatch.setattr(tm.StateRun, "evaluate", fake)
    doc = tm.compare_ceiling_per_screen_case(inp, entries, thetas=(T,), states=["AA"], screen=(0, 3, 5))
    assert doc["summed_rule_envelope_utilities_evaluated_under_the_rule_in_force"] == ["1:AA at 2%"]
    row = next(r for r in doc["utilities_whose_verdict_differs"] if r["utility"] == "1:AA")
    assert row["configurations_summed"] == 6 and row["in_force_per_screen_case"]["keeps_its_place"] is True


def test_every_summed_rule_envelope_utility_is_in_the_amendment_record():
    """Two utilities, one enumerated under the summed rule and one over the ceiling when summed (ceiling 5)."""
    sites = [site("a", 20, 2015), site("b", 20, 2015, utility=2)]
    inp = W.make(sites, {(1, "AA"): 10.0, (2, "AA"): 1000.0})
    entries = [W.date("a", 2014, 2015, 2015, ends="evidence")]
    old = {}
    for k in ((1, "AA"), (2, "AA")):
        old[k] = tm.StateRun(inp, entries, "AA", screen=(0, 3, 5)).evaluate(k, T, ceiling=5, rule=tm.SUMMED_SUPERSEDED)["method"]
    doc = tm.compare_ceiling_per_screen_case(inp, entries, thetas=(T,), states=["AA"], ceiling=5, screen=(0, 3, 5))
    want = sorted(f"{k[0]}:{k[1]} at 2%" for k, m in old.items() if m == "envelope")
    assert want and doc["summed_rule_envelope_utilities_evaluated_under_the_rule_in_force"] == want


def test_run_uses_the_rule_in_force():
    """timing.run, which treatment_bounds reads through timing_place_test.json, counts per screen case."""
    inp = W.make([site("a", 20, 2015)], BASE)
    res = tm.run(inp, [W.date("a", 2014, 2015, 2015, ends="evidence")], thetas=(T,), states=["AA"], ceiling=5)
    u = next(r for r in res["utilities"] if r["utility"] == "1:AA")
    assert u["method"] == "exact" and u["keeps_its_place"] is True and u["ceiling_rule"] == "per_screen_case"
