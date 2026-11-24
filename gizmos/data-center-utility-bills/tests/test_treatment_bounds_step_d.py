"""Step D's verdicts folded into treatment_bounds' lists (treatment_bounds.step_d_reasons). Made-up rows."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.facilities import treatment_bounds as tb  # noqa: E402

UNITS = [(1, "AA"), (2, "AA"), (3, "AA"), (4, "AA"), (5, "AA")]


def row(u, keeps, mapped, ob=False, status="x"):
    return {"utility": u, "theta": 0.02, "keeps_its_place": keeps, "keeps_with_assignment_as_mapped": mapped,
            "fails_only_open_below": ob, "status": status}


def test_each_verdict_lands_in_its_list():
    rows = [row("1:AA", True, True), row("2:AA", False, False, ob=True), row("3:AA", None, None, status="unsettled: ref"),
            row("4:AA", False, True)]
    why, why4 = {}, {}
    lists = tb.step_d_reasons(rows, 0.02, UNITS, set(), why, why4)
    assert (1, "AA") not in why and (1, "AA") not in why4
    assert why[(2, "AA")][0].startswith("Step D (D-61 5.4)") and lists["step_d_open_below_only"] == ["2:AA"]
    assert why[(3, "AA")][0].startswith("Step D: unsettled") and lists["step_d_unsettled"] == ["3:AA"]
    assert (4, "AA") not in why and why4[(4, "AA")].startswith("D-46, ruling 4 (step D")
    assert lists["step_d_fails_only_jointly_with_its_unresolved_sites"] == ["4:AA"]


def test_an_unknown_load_utility_is_judged_by_the_enumeration_not_the_frame():
    why = {(1, "AA"): ["D-46: no anchoring puts the first crossing at 2014 against 2016"], (2, "AA"): ["T2: slower"]}
    why4 = {(1, "AA"): "D-46, ruling 4: upper as built"}
    rows = [row("1:AA", True, True), row("2:AA", True, True), row("3:AA", False, False)]
    lists = tb.step_d_reasons(rows, 0.02, UNITS, {"1:AA", "2:AA", "3:AA", "5:AA"}, why, why4)
    assert (1, "AA") not in why and (1, "AA") not in why4                 # the frame's verdicts are replaced
    assert why[(2, "AA")] == ["T2: slower"]                                # other histories still count
    assert "3:AA" in lists["unknown_load_unsettled"] and (3, "AA") in why
    assert "5:AA" in lists["unknown_load_unsettled"] and (5, "AA") in why # no enumeration row: never settled by the frame
    assert lists["unknown_load_decided_by_the_enumeration"] == ["1:AA", "2:AA"]


def test_an_unknown_load_utility_the_enumeration_cannot_settle_is_out():
    why, why4 = {}, {}
    tb.step_d_reasons([row("1:AA", None, None, status="unsettled: the reference is undefined")], 0.02, UNITS, {"1:AA"}, why, why4)
    assert (1, "AA") in why


def test_a_stress_difference_is_out_with_its_own_reason_and_list():
    r = row("1:AA", True, True)
    r["unresolved_by_stress"] = [{"site": "bi:1123-0", "label": "x", "reason": "unresolved: which building the row carries is not settled (D-96)"}]
    why, why4 = {}, {}
    lists = tb.step_d_reasons([r, row("2:AA", True, True)], 0.02, UNITS, set(), why, why4)
    assert why[(1, "AA")] == ["Step D: unresolved: which building the row carries is not settled (D-96) (bi:1123-0)"]
    assert lists["step_d_unresolved_by_a_stress_scenario"] == ["1:AA"]
    assert lists["step_d_does_not_keep_its_place_within_its_dates"] == [] and lists["step_d_open_below_only"] == []
    assert (2, "AA") not in why


def test_a_stress_difference_on_an_unknown_load_utility_is_not_wiped_by_the_enumeration():
    r = row("1:AA", True, True)
    r["unresolved_by_stress"] = [{"site": "s", "label": "x", "reason": "unresolved: y"}]
    why = {}
    tb.step_d_reasons([r], 0.02, UNITS, {"1:AA"}, why, {})
    assert (1, "AA") in why
