"""The adapter's brute-force evaluator (tests/adapter_evaluator.py) checked against answers worked out by hand.

docs/gate1/dependency-adapter-brief-2026-11-18.md, section 7.2. Invented data only: every state is made up here with
`mini()` from tests/test_pass_c_expand.py, and every expectation below is worked by hand in the comments beside it, not
taken from running code.

Arithmetic used throughout:
  * A site that starts in year Y ramps over three years (buildout.ramp_mw): a third of its full load in Y, two thirds
    in Y + 1, full from Y + 2. Nothing before Y.
  * One MW for a year is 8.76 GWh; in the 2024 anchoring a site counts its 2024 MW times 8.76 / 1000 TWh.
  * The state factor is (EPRI less the measured total) over the permit total, held between 0.2 and 3.0, and 1 when
    the permit total is zero. `mini()` sets EPRI to the state's own frozen total unless given, so its factor is 1.
  * The host threshold is 2% of base-period sales; the comparison floor is 0.5%.
  * As built, a permit-based site's load is its raw load times the factor; with no anchoring it is its raw load.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter_evaluator as ev  # noqa: E402
from test_pass_c_expand import mini  # noqa: E402

GWH = 8.76
YEARS = list(range(2001, 2026))


def date(fid, earliest, latest, convention, never=False):
    return {"fid": fid, "kind": "date", "earliest": earliest, "latest": latest, "never_is_possible": never,
            "convention": convention}


def series(start, full_gwh):
    """A three-year ramp from `start` to `full_gwh` GWh, by panel year, worked out from the rule above."""
    out = []
    for y in YEARS:
        age = y - start
        out.append(0.0 if age < 0 else full_gwh * min(1.0, (age + 1) / 3))
    return out


def same(a, b):
    return all(x == pytest.approx(y, abs=1e-9) for x, y in zip(a, b)) and len(a) == len(b)


# ---- case 1: an assignment question between two utilities ----------------------------------------------------------

def state_assignment():
    # AA. x is unresolved: on utility 1 by the map, utility 2 another candidate; 2 MW raw from 2010.
    #     r is resolved on utility 3: 1 MW raw from 2005.
    # Bases: 1 and 3 at 1000 GWh (threshold 20 GWh, floor 5 GWh); 2 at 500 GWh (threshold 10 GWh, floor 2.5 GWh).
    # The factor is 1 (EPRI defaults to the state's own total).
    sites = [{"fid": "x", "st": "AA", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 2.0, "year": 2010},
             {"fid": "r", "st": "AA", "u": 3, "raw": 1.0, "year": 2005}]
    return mini(sites, {(1, "AA"): 1000.0, (2, "AA"): 500.0, (3, "AA"): 1000.0})


def test_an_assignment_question_reaches_both_utilities_and_does_not_move_anchoring():
    res = ev.brute_force(state_assignment(), [], "AA")
    # One question, x's assignment, with settings: the utility it is on (1), each candidate (2), off the panel (None).
    assert res["questions"] == [("x", "assignment")]
    assert res["settings"][("x", "assignment")] == [1, 2, None]
    assert res["configurations"] == 3
    # x's load: 2/3 MW in 2010 (5.84 GWh), 4/3 MW in 2011 (11.68 GWh), 2 MW from 2012 (17.52 GWh).
    x = series(2010, 2 * GWH)
    assert x[YEARS.index(2010)] == pytest.approx(5.84) and x[YEARS.index(2011)] == pytest.approx(11.68)
    # r's load: 2.92 GWh in 2005, 5.84 in 2006, 8.76 from 2007, on utility 3 in every configuration.
    r = series(2005, GWH)
    zero = [0.0] * len(YEARS)
    for setting, on1, on2 in ((1, x, zero), (2, zero, x), (None, zero, zero)):
        loads = res["loads"][(setting,)]
        for reading in ("as_built", "no_anchoring"):                     # factor 1: both readings are equal
            assert same(loads[(1, "AA")][reading], on1)
            assert same(loads[(2, "AA")][reading], on2)
            assert same(loads[(3, "AA")][reading], r)
    # Reaches 1 and 2 (x's own load moves between them), never 3.
    assert res["reaches"][("x", "assignment")] == {(1, "AA"), (2, "AA")}
    # The 2024 contributions: x 2 MW = 0.01752 TWh wherever it is (a site off the panel stays in the anchoring),
    # r 1 MW = 0.00876 TWh. Permit total 0.02628 TWh, measured 0, in all three configurations: does not move.
    assert res["moves_anchoring"][("x", "assignment")] is False
    for key in res["anchoring"]:
        assert res["anchoring"][key] == (pytest.approx(0.0, abs=1e-15), pytest.approx(0.02628, abs=1e-12))
    # Host threshold: utility 2 needs 10 GWh, and x on it carries 11.68 in 2011 and 17.52 later: it can cross.
    # Utility 1 needs 20 GWh and x gives at most 17.52; utility 3 needs 20 and r gives 8.76. Neither can.
    assert res["can_cross"] == {(2, "AA")}
    assert res["near_ties"] == []


def test_violations_name_a_utility_that_is_not_narrowed():
    res = ev.brute_force(state_assignment(), [], "AA")
    # Deferring x's assignment with only utility 1 narrowed breaches (a): utility 2's load differs (0 or x's load).
    v = ev.violations(res, {("x", "assignment")}, {(1, "AA")})
    assert v and {b["unit"] for b in v if b["breach"] == "load"} == {(2, "AA")}
    assert not any(b["breach"] == "anchoring" for b in v)
    # With 1 and 2 narrowed nothing else moves (3 is untouched, the totals are fixed): no breach.
    assert ev.violations(res, {"x assignment"}, {"1:AA", "2:AA"}) == []
    # A question the state does not have is reported, since nothing here can show it is harmless.
    assert ev.violations(res, {("nope", "date")}, set())[0]["breach"].startswith("not a question")


# ---- case 2: a date question wholly before the anchoring year's ramp -------------------------------------------------

def state_early_date():
    # BB. d is resolved on utility 4: 3 MW raw, inventory year 2012; its date question runs 2010 to 2014.
    #     y is unresolved on utility 5 with candidate 6: 1 MW raw from 2005.
    # Frozen permit total in 2024: d 3 MW (full by 2014) + y 1 MW = 4 MW = 0.03504 TWh. EPRI is set to half of that,
    # 0.01752 TWh, so the factor is 0.01752 / 0.03504 = 0.5.
    # Bases: 4 at 2000 GWh (threshold 40, floor 10); 5 and 6 at 1000 GWh (threshold 20, floor 5).
    sites = [{"fid": "d", "st": "BB", "u": 4, "raw": 3.0, "year": 2012},
             {"fid": "y", "st": "BB", "u": 5, "cands": "5;6", "assign": "smallest_polygon", "raw": 1.0, "year": 2005}]
    epri = {"BB": 0.5 * 4 * GWH / 1000}
    return mini(sites, {(4, "BB"): 2000.0, (5, "BB"): 1000.0, (6, "BB"): 1000.0}, epri)


def test_a_date_question_before_the_anchoring_ramp_reaches_its_utility_and_does_not_move_anchoring():
    inp = state_early_date()
    res = ev.brute_force(inp, [date("d", 2010, 2014, 2012)], "BB")
    # d's date: each start year 2010 to 2014 (no "never"); y's assignment: 5, 6, off. 5 x 3 = 15 configurations.
    assert res["questions"] == [("d", "date"), ("y", "assignment")]
    assert res["settings"][("d", "date")] == [2010, 2011, 2012, 2013, 2014]
    assert res["configurations"] == 15
    # Any start from 2010 to 2014 is at full load (3 MW) by 2016, so d counts 3 x 8.76 / 1000 = 0.02628 TWh in 2024
    # in every setting: does not move anchoring. The factor stays 0.5 in every configuration.
    assert res["moves_anchoring"][("d", "date")] is False
    assert res["moves_anchoring"][("y", "assignment")] is False
    assert all(f == pytest.approx(0.5) for f in res["factor"].values())
    for key in res["anchoring"]:
        assert res["anchoring"][key][1] == pytest.approx(0.03504, abs=1e-12)
    # Starting in 2010 rather than 2011 puts 1 MW (8.76 GWh) on utility 4 in 2010 with no anchoring: it reaches 4.
    assert res["reaches"][("d", "date")] == {(4, "BB")}
    assert res["reaches"][("y", "assignment")] == {(5, "BB"), (6, "BB")}
    # d from 2012 with y on 5: utility 4 carries 8.76, 17.52, then 26.28 GWh with no anchoring, half that as built.
    loads = res["loads"][(2012, 5)]
    assert same(loads[(4, "BB")]["no_anchoring"], series(2012, 3 * GWH))
    assert same(loads[(4, "BB")]["as_built"], series(2012, 1.5 * GWH))
    # Nobody can cross: 4 gets at most 26.28 against 40; 5 or 6 get at most 8.76 against 20.
    assert res["can_cross"] == set()
    assert res["near_ties"] == []
    # Deferring d's date with utility 4 narrowed: nothing else moves. With nothing narrowed: utility 4 moves.
    assert ev.violations(res, {("d", "date")}, {(4, "BB")}) == []
    assert {b["unit"] for b in ev.violations(res, {("d", "date")}, set())} == {(4, "BB")}


# ---- case 3: a date question that changes the 2024 contribution while the factor cannot move -------------------------

def state_held_factor():
    # CC. q on utility 7: 6 MW raw, inventory year 2022, date question 2021 to 2025.
    #     s on utility 8: 5 MW raw from 2005.
    # EPRI is 0. The factor is max(0 - 0, 0) / permit = 0, held up to the band's floor, 0.2. The permit total is never
    # zero (s alone is 5 MW = 0.0438 TWh), so the factor is 0.2 in every setting.
    # Bases: 7 at 1000 GWh (threshold 20, floor 5); 8 at 10000 GWh (threshold 200, floor 50).
    sites = [{"fid": "q", "st": "CC", "u": 7, "raw": 6.0, "year": 2022},
             {"fid": "s", "st": "CC", "u": 8, "raw": 5.0, "year": 2005}]
    return mini(sites, {(7, "CC"): 1000.0, (8, "CC"): 10000.0}, {"CC": 0.0})


def test_a_date_question_moves_anchoring_even_where_the_factor_is_held_at_one_value():
    res = ev.brute_force(state_held_factor(), [date("q", 2021, 2025, 2022)], "CC")
    assert res["questions"] == [("q", "date")]
    assert res["settings"][("q", "date")] == [2021, 2022, 2023, 2024, 2025]
    # q's 2024 MW by start: 2021 (age 3) 6; 2022 (age 2) 6; 2023 (age 1) 4; 2024 (age 0) 2; 2025 nothing.
    # Contributions: 0.05256, 0.05256, 0.03504, 0.01752, 0 TWh. Permit totals add s's 0.0438.
    expected = {2021: 0.09636, 2022: 0.09636, 2023: 0.07884, 2024: 0.06132, 2025: 0.0438}
    for (start,), (meas, perm) in res["anchoring"].items():
        assert meas == pytest.approx(0.0, abs=1e-15) and perm == pytest.approx(expected[start], abs=1e-12)
        assert res["contributions"][(start,)]["q"] == pytest.approx(expected[start] - 0.0438, abs=1e-12)
    # The factor is 0.2 in every configuration, so no other utility's load changes...
    assert all(f == pytest.approx(0.2) for f in res["factor"].values())
    s_as_built = series(2005, 5 * 0.2 * GWH)                            # 8.76 GWh from 2007
    for key in res["loads"]:
        assert same(res["loads"][key][(8, "CC")]["as_built"], s_as_built)
        assert same(res["loads"][key][(8, "CC")]["no_anchoring"], series(2005, 5 * GWH))
    # ...and the question still moves anchoring (brief 4.2: read from the contributions and nothing else).
    assert res["moves_anchoring"][("q", "date")] is True
    assert res["reaches"][("q", "date")] == {(7, "CC")}
    # Utility 7 with no anchoring: q at full load is 52.56 GWh against 20; it can cross. Utility 8: 43.8 against 200.
    assert res["can_cross"] == {(7, "CC")}
    assert res["near_ties"] == []
    # Deferring q with both utilities narrowed breaches (b) only: the permit total differs, no utility load does.
    v = ev.violations(res, {("q", "date")}, {(7, "CC"), (8, "CC")})
    assert v and {b["breach"] for b in v} == {"anchoring"}


# ---- case 4: a date question with "never" -----------------------------------------------------------------------------

def state_never():
    # DD. n on utility 9: 2 MW raw, inventory year 2015; date question 2015 to 2016, or never.
    #     t on utility 10: 1 MW raw from 2005.
    # Frozen permit total: 3 MW = 0.02628 TWh; EPRI defaults to that, so the factor is 1.
    # Bases: 9 at 1000 GWh (threshold 20, floor 5); 10 at 2000 GWh (threshold 40, floor 10).
    sites = [{"fid": "n", "st": "DD", "u": 9, "raw": 2.0, "year": 2015},
             {"fid": "t", "st": "DD", "u": 10, "raw": 1.0, "year": 2005}]
    return mini(sites, {(9, "DD"): 1000.0, (10, "DD"): 2000.0})


def test_a_date_question_with_never():
    res = ev.brute_force(state_never(), [date("n", 2015, 2016, 2015, never=True)], "DD")
    assert res["settings"][("n", "date")] == [2015, 2016, "never"]
    assert res["configurations"] == 3
    # 2024 contribution: 2 MW (0.01752 TWh) from 2015 or 2016, nothing if never. Moves anchoring.
    assert res["moves_anchoring"][("n", "date")] is True
    assert res["anchoring"][(2015,)][1] == pytest.approx(0.02628, abs=1e-12)
    assert res["anchoring"][(2016,)][1] == pytest.approx(0.02628, abs=1e-12)
    assert res["anchoring"][("never",)][1] == pytest.approx(0.00876, abs=1e-12)
    # Factor: 0.02628 / 0.02628 = 1 with n; 0.02628 / 0.00876 = 3 with never (the band's top, 3.0).
    assert res["factor"][(2015,)] == pytest.approx(1.0) and res["factor"][("never",)] == pytest.approx(3.0)
    # So utility 10's as-built load is t's 8.76 GWh, or 26.28 GWh when n never starts, but its no-anchoring load is
    # 8.76 GWh either way: n does not reach utility 10. It reaches 9 (17.52 GWh or nothing).
    assert res["loads"][(2015,)][(10, "DD")]["as_built"][-1] == pytest.approx(8.76)
    assert res["loads"][("never",)][(10, "DD")]["as_built"][-1] == pytest.approx(26.28)
    assert res["loads"][("never",)][(10, "DD")]["no_anchoring"][-1] == pytest.approx(8.76)
    assert res["reaches"][("n", "date")] == {(9, "DD")}
    # Nobody crosses: 9 at most 17.52 against 20; 10 at most 26.28 against 40.
    assert res["can_cross"] == set()
    assert res["near_ties"] == []
    # Deferring n with 9 narrowed breaches (a) on 10's as-built load and (b) on the permit total.
    v = ev.violations(res, {("n", "date")}, {(9, "DD")})
    assert {(b["breach"], b.get("unit"), b.get("reading")) for b in v} == {("load", (10, "DD"), "as_built"),
                                                                          ("anchoring", None, None)}


# ---- case 5: the measured side, with a fixed (Epoch) history in the state -------------------------------------------

def state_measured():
    # EE. m on utility 11: a measured figure (verified_public_figure), 3 MW, inventory year 2022; date 2022 to 2024.
    #     e on utility 12: an Epoch timeline, 4 MW from 2015 (fixed: not rebuilt).
    #     p on utility 12: permit-based, 2 MW raw from 2010.
    # Frozen totals: measured m 3 MW + e 4 MW = 7 MW = 0.06132 TWh; permit p 2 MW = 0.01752 TWh. EPRI defaults to
    # 0.07884, so the factor is (0.07884 - 0.06132) / 0.01752 = 1.
    # Bases: 11 at 1000 GWh (threshold 20, floor 5); 12 at 10000 GWh (threshold 200, floor 50).
    sites = [{"fid": "m", "st": "EE", "u": 11, "raw": 3.0, "year": 2022, "basis": "verified_public_figure"},
             {"fid": "e", "st": "EE", "u": 12, "raw": 4.0, "year": 2015, "src": "epoch"},
             {"fid": "p", "st": "EE", "u": 12, "raw": 2.0, "year": 2010}]
    return mini(sites, {(11, "EE"): 1000.0, (12, "EE"): 10000.0})


def test_a_measured_date_moves_the_measured_side_and_the_fixed_part_is_carried():
    res = ev.brute_force(state_measured(), [date("m", 2022, 2024, 2022)], "EE")
    assert res["questions"] == [("m", "date")]
    # m's 2024 MW: 3 from 2022, 2 from 2023, 1 from 2024. Measured totals add e's fixed 4 MW (0.03504 TWh):
    # 0.06132, 0.05256, 0.0438 TWh. The permit side is p's 0.01752 throughout.
    expected = {2022: 0.06132, 2023: 0.05256, 2024: 0.0438}
    for (start,), (meas, perm) in res["anchoring"].items():
        assert meas == pytest.approx(expected[start], abs=1e-12) and perm == pytest.approx(0.01752, abs=1e-12)
    # Factor: (0.07884 - measured) / 0.01752 = 1.0, 1.5, 2.0.
    assert [res["factor"][(y,)] for y in (2022, 2023, 2024)] == [pytest.approx(1.0), pytest.approx(1.5), pytest.approx(2.0)]
    assert res["moves_anchoring"][("m", "date")] is True
    # m reaches 11 only. Utility 12's no-anchoring load (e 4 MW + p 2 MW raw) does not change; as built, p is scaled.
    assert res["reaches"][("m", "date")] == {(11, "EE")}
    assert res["loads"][(2024,)][(12, "EE")]["as_built"][-1] == pytest.approx((4 + 2 * 2.0) * GWH)
    assert res["loads"][(2022,)][(12, "EE")]["no_anchoring"][-1] == pytest.approx(6 * GWH)
    # m at full load is 26.28 GWh against 11's threshold of 20: 11 can cross. 12 at most 70.08 against 200.
    assert res["can_cross"] == {(11, "EE")}
    assert res["near_ties"] == []


# ---- case 6: a capacity question, and a refusal ------------------------------------------------------------------------

def test_a_capacity_question_before_the_anchoring_year():
    # FF. c on utility 13: 3 MW raw, inventory year 2016; a capacity split with its first phase (half) in 2014 and no
    # convention. Settings: early (the whole row ramps from 2014) and late (half from 2014, the rest from 2016).
    # Base 13 at 1000 GWh (threshold 20, floor 5). Factor 1.
    inp = mini([{"fid": "c", "st": "FF", "u": 13, "raw": 3.0, "year": 2016}], {(13, "FF"): 1000.0})
    split = {"fid": "c", "kind": "capacity_split", "first_phase_year": 2014, "first_share": 0.5, "convention": None}
    res = ev.brute_force(inp, [split], "FF")
    assert res["settings"][("c", "capacity")] == ["early", "late"]
    # Early, 2014: a third of 3 MW = 1 MW (8.76 GWh). Late, 2014: a third of 1.5 MW = 0.5 MW (4.38 GWh): reaches 13.
    assert res["loads"][("early",)][(13, "FF")]["no_anchoring"][YEARS.index(2014)] == pytest.approx(8.76)
    assert res["loads"][("late",)][(13, "FF")]["no_anchoring"][YEARS.index(2014)] == pytest.approx(4.38)
    assert res["reaches"][("c", "capacity")] == {(13, "FF")}
    # Both cases are at 3 MW by 2018, so 2024 counts 0.02628 TWh either way: does not move anchoring.
    assert res["moves_anchoring"][("c", "capacity")] is False
    # 3 MW is 26.28 GWh against 20: 13 can cross.
    assert res["can_cross"] == {(13, "FF")}
    assert res["near_ties"] == []


def test_an_unresolved_site_with_load_and_no_utility_is_refused():
    # GG. w is unresolved (candidates 1 and 2) with a size and a year but on no utility: the pass refuses such a row.
    inp = mini([{"fid": "w", "st": "GG", "u": None, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.0,
                 "year": 2010}], {(1, "GG"): 1000.0, (2, "GG"): 1000.0})
    with pytest.raises(ValueError, match="on no utility"):
        ev.brute_force(inp, [], "GG")


# ---- the windows of brief 4.6 ------------------------------------------------------------------------------------------

def test_the_windows_written_from_the_brief_are_the_modules():
    from pipeline.analysis import availability
    assert ev.brief_windows() == {k: tuple(v) for k, v in availability.permitted_windows().items()}


def test_windows_passed_by_hand():
    import pandas as pd
    rows = []
    for y in range(2001, 2026):
        rows.append((1, "WA", y, True))                                  # usable every year: all 14 windows
        rows.append((3, "WA", y, y not in (2009, 2020)))                 # see below
    mask = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "usable"])
    assert len(ev.windows_passed(mask, (1, "WA"))) == 14
    # Unit 3 fails 2009 and 2020. Cohort g's window is g-6 to g+3. It holds 2009 when g <= 2015 (cohorts 2011 to
    # 2015 fail) and 2020 when g >= 2017 (cohorts 2017 to 2022 fail). Cohort 2016 is 2010 to 2019: passes. The long
    # difference holds 2009 and the panel form holds both: both fail. Exactly one window survives.
    assert ev.windows_passed(mask, (3, "WA")) == ["cohort_2016"]
    # A unit absent from the mask passes nothing.
    assert ev.windows_passed(mask, (9, "WA")) == []
