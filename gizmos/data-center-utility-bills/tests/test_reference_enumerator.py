"""The reference enumerator (tests/reference_enumerator.py) against answers worked out by hand
(docs/gate1/reference-repair-rule-2026-11-18.md, section 8.2).

Load and sales only; no price is read. Everything is made up with mini() from tests/test_pass_c_expand.py. Nothing
here imports pipeline/facilities/pass_c_exact.py.

Arithmetic used throughout (as in tests/test_exhaustive_evaluator.py):
* A site of R MW raw starting in year s carries R/3 in s, 2R/3 in s+1 and R from s+2 (buildout.ramp_mw, three ramp
  years). In 2024 it counts R if s <= 2022, 2R/3 if s = 2023, R/3 if s = 2024 and 0 if s >= 2025 or never.
* A permit-based site's load as built is its raw load times the state's factor. With no measured load the factor is
  E / P, where E is the state's EPRI total and P its permit-based 2024 total, held to the band 0.2 to 3.0
  (pass_c_expand._factor: SCALE_LO, SCALE_HI); a factor within 1e-12 of the frozen one is the frozen one
  (FACTOR_TOL in scratch_state). Below, E and P are written in MW-years (E MW of 2024 load = E x 8.76 / 1000 TWh).
* A utility's GWh in a year is 8.76 x MW. T(m) is the base whose 2% threshold is m MW all year; the 0.5% floor is then
  m / 4 MW. A crossing is the first year whose load reaches the threshold; "cohort" is 2011 to 2022.
* With one site at a time, a "setting" is a start year (or "never") of a reference-defining question; the reference
  configuration holds every other question at its convention and every site on the utility it is on.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import GWH, date, mini, split  # noqa: E402

import reference_enumerator as en  # noqa: E402


def T(mw: float) -> float:
    """The base-period sales (GWh) whose 2% threshold is `mw` MW of load all year."""
    return mw * GWH / 0.02


def E(mw: float) -> float:
    """An EPRI total (TWh) equal to `mw` MW of load in 2024."""
    return mw * GWH / 1000


def prov(c: dict) -> dict:
    return {**c, "convention_is": "provisional"}


# ---- the cases (each builder returns (inputs, corrections, state); also used by tests/test_reference_against_enumerator.py
# and tests/test_pass_c_exact_against_evaluator.py) ----------------------------------------------------------------------

def _own_site_world():
    # Utility 1 (threshold 3.5 MW, floor 0.875 MW) carries r (3 MW raw from 2010) and d (3 MW raw). E = 6. The
    # inventory dates d 2015, so P = 6 and the frozen factor is 1.
    sites = [{"fid": "r", "st": "RA", "u": 1, "raw": 3.0, "year": 2010},
             {"fid": "d", "st": "RA", "u": 1, "raw": 3.0, "year": 2015}]
    return mini(sites, {(1, "RA"): T(3.5)}, {"RA": E(6.0)})


def case_own_site():
    # d's start has no convention: any year from 2010 to 2025.
    return _own_site_world(), [date("d", 2010, 2025, None)], "RA"


def case_own_site_never():
    # d's start has no convention: any year from 2010, open above, or never (settings 2010 ... 2026, "never").
    return _own_site_world(), [date("d", 2010, None, None, never=True)], "RA"


def case_own_site_provisional():
    # d's convention is 2015, marked provisional (a year built from a government record).
    return _own_site_world(), [prov(date("d", 2010, 2025, 2015))], "RA"


def case_held_factor():
    # E = 100 against P of 3 or 4 MW: the raw factor is 25 to 33, so the factor is held at the cap, 3.0, in every setting.
    # Utility 1 (threshold 3.5 MW) carries r (2 MW raw from 2010) and d (1 MW raw, start 2021 or later, or never, no
    # convention); utility 2 (threshold 2.5 MW) carries q (1 MW raw from 2010).
    sites = [{"fid": "r", "st": "RD", "u": 1, "raw": 2.0, "year": 2010},
             {"fid": "d", "st": "RD", "u": 1, "raw": 1.0, "year": 2021},
             {"fid": "q", "st": "RD", "u": 2, "raw": 1.0, "year": 2010}]
    return (mini(sites, {(1, "RD"): T(3.5), (2, "RD"): T(2.5)}, {"RD": E(100.0)}),
            [date("d", 2021, None, None, never=True)], "RD")


def case_factor_only():
    # r (3 MW raw from 2010) is on utility 1; d (3 MW raw, start 2022 to 2025, no convention) is on utility 2 and never
    # on 1. E = 6. Both thresholds 3.3 MW (floor 0.825 MW).
    sites = [{"fid": "r", "st": "RE", "u": 1, "raw": 3.0, "year": 2010},
             {"fid": "d", "st": "RE", "u": 2, "raw": 3.0, "year": 2022}]
    return mini(sites, {(1, "RE"): T(3.3), (2, "RE"): T(3.3)}, {"RE": E(6.0)}), [date("d", 2022, 2025, None)], "RE"


def case_capacity_rest_earliest():
    # Utility 1 (threshold 4.75 MW) carries r (3 MW raw from 2010) and c (3 MW raw, inventory year 2025). c's capacity
    # split: half with a first phase in 2010, the rest arriving in any year from rest_earliest 2012 to 2025; no
    # convention. E = 6. (The inventory's 2025 gives P = 3 and a frozen factor of 2, which no setting reproduces.)
    sites = [{"fid": "r", "st": "RF", "u": 1, "raw": 3.0, "year": 2010},
             {"fid": "c", "st": "RF", "u": 1, "raw": 3.0, "year": 2025}]
    return (mini(sites, {(1, "RF"): T(4.75)}, {"RF": E(6.0)}),
            [split("c", 2010, 0.5, rest_earliest=2012)], "RF")


def case_two_questions():
    # Utility 1 (threshold 4.5 MW) carries r (6 MW raw from 2010), a and b (2 MW raw each, starts 2010 to 2025, no
    # convention). E = 10; the inventory dates a and b 2015, so the frozen factor is 10 / 10 = 1.
    sites = [{"fid": "r", "st": "RG", "u": 1, "raw": 6.0, "year": 2010},
             {"fid": "a", "st": "RG", "u": 1, "raw": 2.0, "year": 2015},
             {"fid": "b", "st": "RG", "u": 1, "raw": 2.0, "year": 2015}]
    return (mini(sites, {(1, "RG"): T(4.5)}, {"RG": E(10.0)}),
            [date("a", 2010, 2025, None), date("b", 2010, 2025, None)], "RG")


HAND_CASES = {
    "own_site": case_own_site,
    "own_site_never": case_own_site_never,
    "own_site_provisional": case_own_site_provisional,
    "held_factor": case_held_factor,
    "factor_only": case_factor_only,
    "capacity_rest_earliest": case_capacity_rest_earliest,
    "two_questions": case_two_questions,
}


def solve(build, provisional_defines=True):
    inp, corrections, st = build()
    t = en.table(inp, corrections, st, provisional_defines=provisional_defines)
    return t, en.from_table(t)


def at(t, setting, k):
    """(factor, (place, crossing)) of utility k at one setting (a tuple, one value per question)."""
    row = next(r for r in t["rows"] if r["setting"] == setting)
    return row["factor"], row["pairs"][k]


# ---- 1. a site on the utility, no convention, the factor moving with its start ------------------------------------------

def test_own_site_no_convention_ends_agree_and_an_interior_year_does_not():
    # d's 2024 count c and the factor f = 6 / (3 + c):
    #   start <= 2022: c = 3, f = 6/6 = 1.0;  2023: c = 2, f = 6/5 = 1.2;  2024: c = 1, f = 6/4 = 1.5;  2025: c = 0, f = 2.0
    # Utility 1 as built, MW = f x (r + d); r is 1, 2, 3 in 2010, 2011, 2012 on; threshold 3.5:
    #   start 2010 (first): 2010 1x(1+1) = 2; 2011 1x(2+2) = 4 >= 3.5            -> cohort 2011
    #   start 2011:         2011 1x(2+1) = 3; 2012 1x(3+2) = 5                    -> 2012
    #   start s, 2012-2022: year s-1 1x3 = 3; year s 1x(3+1) = 4                  -> s
    #   start 2023:         2011 1.2x2 = 2.4; 2012 1.2x3 = 3.6 (d nothing yet)    -> 2012
    #   start 2024:         2011 1.5x2 = 3.0; 2012 1.5x3 = 4.5                    -> 2012
    #   start 2025 (last):  2010 2x1 = 2;     2011 2x2 = 4                        -> cohort 2011
    # The first and last settings agree (cohort 2011); every interior year gives another crossing (2012 to 2022).
    t, ref = solve(case_own_site)
    k = (1, "RA")
    assert t["questions"] == [{"fid": "d", "question": "date", "settings": list(range(2010, 2026))}]
    assert t["combinations"] == 16
    assert at(t, (2010,), k) == (pytest.approx(1.0), ("cohort", 2011.0))
    assert at(t, (2011,), k) == (pytest.approx(1.0), ("cohort", 2012.0))
    assert at(t, (2017,), k) == (pytest.approx(1.0), ("cohort", 2017.0))
    assert at(t, (2023,), k) == (pytest.approx(1.2), ("cohort", 2012.0))
    assert at(t, (2024,), k) == (pytest.approx(1.5), ("cohort", 2012.0))
    assert at(t, (2025,), k) == (pytest.approx(2.0), ("cohort", 2011.0))
    assert ref[k]["defined"] is False and ref[k]["place"] is None and ref[k]["crossing"] is None
    assert ref[k]["seen"] == [("cohort", float(y)) for y in range(2011, 2023)]
    assert ref[k]["differs_inside_only"] is True


# ---- 2. the same shape with "never" as the last setting -----------------------------------------------------------------

def test_own_site_with_never_last_ends_agree_and_an_interior_year_does_not():
    # Open above with never: the settings are 2010 ... 2026 (a start after the panel, entered once) and "never".
    # 2026 and never: c = 0, f = 2.0, d carries nothing in the panel: 2010 2x1 = 2; 2011 2x2 = 4 -> cohort 2011, as 2025.
    # The first (2010) and the last (never) agree; the interior is as in the first case.
    t, ref = solve(case_own_site_never)
    k = (1, "RA")
    assert t["questions"][0]["settings"] == list(range(2010, 2027)) + ["never"]
    assert at(t, (2010,), k) == (pytest.approx(1.0), ("cohort", 2011.0))
    assert at(t, (2014,), k) == (pytest.approx(1.0), ("cohort", 2014.0))
    assert at(t, (2026,), k) == (pytest.approx(2.0), ("cohort", 2011.0))
    assert at(t, ("never",), k) == (pytest.approx(2.0), ("cohort", 2011.0))
    assert ref[k]["defined"] is False and ref[k]["differs_inside_only"] is True
    assert ref[k]["seen"] == [("cohort", float(y)) for y in range(2011, 2023)]


# ---- 3. the same shape with a provisional convention -------------------------------------------------------------------

def test_own_site_provisional_convention_is_defining_for_the_exact_attribution_only():
    # Convention 2015, provisional. For the exact attribution (provisional_defines True) the date is reference-defining:
    # the same sixteen settings and the same answer as the first case, undefined, the ends agreeing.
    t, ref = solve(case_own_site_provisional, provisional_defines=True)
    k = (1, "RA")
    assert [q["settings"] for q in t["questions"]] == [list(range(2010, 2026))]
    assert ref[k]["defined"] is False and ref[k]["differs_inside_only"] is True
    # For the place test (provisional_defines False) the date sits at its convention, 2015: no question to enumerate,
    # one combination: f = 1.0; 2014 1x3 = 3; 2015 1x(3+1) = 4 -> cohort 2015. Defined.
    t, ref = solve(case_own_site_provisional, provisional_defines=False)
    assert t["questions"] == [] and t["combinations"] == 1
    assert at(t, (), k) == (pytest.approx(1.0), ("cohort", 2015.0))
    assert ref[k] == {"defined": True, "place": "cohort", "crossing": 2015.0, "seen": [("cohort", 2015.0)],
                      "differs_inside_only": False}


# ---- 4. a factor held at one value in every setting ----------------------------------------------------------------------

def test_a_factor_held_at_the_cap_in_every_setting_and_every_setting_agrees():
    # P is r 2 + q 1 + d's 2024 count (1, 2/3, 1/3 or 0): 3 to 4 MW, so E / P is 25 to 33: held at 3.0 everywhere.
    # Utility 1: r scaled 3x(2/3, 4/3, 2) = 2, 4, 6 MW in 2010, 2011, 2012 on: 2011 crosses 3.5 whatever d does (d
    # starts in 2021 at the earliest): cohort 2011 in every setting. Utility 2: q scaled 1, 2, 3: 3 >= 2.5 first in
    # 2012: cohort 2012 in every setting. The factor being one number, d's start reaches neither through it, and for
    # utility 1 d's own load comes after the crossing: every setting agrees, not only the ends. Defined.
    t, ref = solve(case_held_factor)
    assert t["questions"][0]["settings"] == [2021, 2022, 2023, 2024, 2025, 2026, "never"]
    assert {r["factor"] for r in t["rows"]} == {px.SCALE_HI}
    for s in (2021, 2023, 2024, "never"):
        assert at(t, (s,), (1, "RD"))[1] == ("cohort", 2011.0)
        assert at(t, (s,), (2, "RD"))[1] == ("cohort", 2012.0)
    assert ref[(1, "RD")] == {"defined": True, "place": "cohort", "crossing": 2011.0, "seen": [("cohort", 2011.0)],
                              "differs_inside_only": False}
    assert ref[(2, "RD")]["defined"] is True and ref[(2, "RD")]["crossing"] == 2012.0


# ---- 5. a site on another utility, reaching this one only through the factor ----------------------------------------------

def test_a_site_on_another_utility_reaches_this_one_only_through_the_factor():
    # f = 6 / (3 + c): start 2022 1.0; 2023 1.2; 2024 1.5; 2025 2.0.
    # Utility 1 carries r alone: f x (1, 2, 3); threshold 3.3:
    #   2022: 1, 2, 3 -> never; largest share 3/3.3 x 2% = 1.8% >= 0.5%                      -> neither
    #   2023: 1.2, 2.4, 3.6 -> 2012;  2024: 1.5, 3.0, 4.5 -> 2012;  2025: 2, 4 -> 2011
    # d is never on utility 1; its start moves utility 1 through the factor alone, and the ends already differ:
    # undefined, and not an interior-only difference.
    # Utility 2 carries d alone: f x d in 2022 to 2025:
    #   2022: 1, 2, 3, 3 -> never (neither);  2023: -, 1.2, 2.4, 3.6 -> 2025 (late)
    #   2024: 1.5, 3.0 -> never (neither);    2025: 2.0 -> never (neither)
    # Its ends agree (neither) and the interior 2023 does not: undefined, interior only.
    t, ref = solve(case_factor_only)
    assert [r["factor"] for r in t["rows"]] == [pytest.approx(x) for x in (1.0, 1.2, 1.5, 2.0)]
    assert [at(t, (s,), (1, "RE"))[1] for s in (2022, 2023, 2024, 2025)] == \
        [("neither", None), ("cohort", 2012.0), ("cohort", 2012.0), ("cohort", 2011.0)]
    assert [at(t, (s,), (2, "RE"))[1] for s in (2022, 2023, 2024, 2025)] == \
        [("neither", None), ("late", 2025.0), ("neither", None), ("neither", None)]
    inp, _, _ = case_factor_only()
    assert set(inp.fy[inp.fy.utility_id_eia == 1].fid) == {"r"}                      # d is not on utility 1
    assert ref[(1, "RE")]["defined"] is False and ref[(1, "RE")]["differs_inside_only"] is False
    assert ref[(1, "RE")]["seen"] == [("cohort", 2011.0), ("cohort", 2012.0), ("neither", None)]
    assert ref[(2, "RE")]["defined"] is False and ref[(2, "RE")]["differs_inside_only"] is True


# ---- 6. a capacity question with rest_earliest -----------------------------------------------------------------------------

def test_a_capacity_split_with_rest_earliest_ends_agree_and_an_interior_year_does_not():
    # c: first phase 1.5 MW from 2010 (0.5, 1.0, 1.5 in 2010, 2011, 2012 on); the rest, 1.5 MW, from year v (0.5, 1.0,
    # 1.5). Settings v = 2012 ... 2025 (rest_earliest to the inventory's 2025). c's 2024 count: 3 for v <= 2022, 2.5
    # (2023), 2.0 (2024), 1.5 (2025); P = 3 + that; f = 6 / P: 1.0, 1.0909 (6/5.5), 1.2 (6/5), 1.3333 (6/4.5).
    # Utility 1, f x (r + c); before the rest arrives r + first phase is 1.5, 3.0, 4.5 in 2010, 2011, 2012 on;
    # threshold 4.75:
    #   v = 2012 (first): 2011 3.0; 2012 1x(4.5+0.5) = 5.0                       -> cohort 2012
    #   v = 2013 ... 2022: year v-1 4.5; year v 4.5+0.5 = 5.0                    -> v
    #   v = 2023: 2011 1.0909x3.0 = 3.27; 2012 1.0909x4.5 = 4.91                  -> 2012
    #   v = 2024: 2011 3.6; 2012 5.4                                               -> 2012
    #   v = 2025 (last): 2011 4.0; 2012 6.0                                        -> cohort 2012
    t, ref = solve(case_capacity_rest_earliest)
    k = (1, "RF")
    assert t["questions"] == [{"fid": "c", "question": "capacity", "settings": list(range(2012, 2026))}]
    assert at(t, (2012,), k) == (pytest.approx(1.0), ("cohort", 2012.0))
    assert at(t, (2016,), k) == (pytest.approx(1.0), ("cohort", 2016.0))
    assert at(t, (2023,), k) == (pytest.approx(6 / 5.5), ("cohort", 2012.0))
    assert at(t, (2024,), k) == (pytest.approx(1.2), ("cohort", 2012.0))
    assert at(t, (2025,), k) == (pytest.approx(6 / 4.5), ("cohort", 2012.0))
    assert ref[k]["defined"] is False and ref[k]["differs_inside_only"] is True
    assert ref[k]["seen"] == [("cohort", float(y)) for y in range(2012, 2023)]


# ---- 7. two reference-defining questions, the disagreement interior to both ---------------------------------------------

def test_two_questions_undefined_only_at_combinations_interior_to_both():
    # a and b each count c = 2 in 2024 for a start up to 2022, 4/3 (2023), 2/3 (2024), 0 (2025). f = 10 / (6 + ca + cb).
    # Utility 1 = f x (r + a + b); r is 2, 4, 6 in 2010, 2011, 2012 on; a start in 2010 adds 2/3, 4/3 in 2010, 2011,
    # in 2011 adds 2/3 in 2011. Threshold 4.5.
    #   Either start at the last setting, 2025 (c = 0, no load before 2025), the other anywhere: f >= 10 / (6 + 2) =
    #     1.25, so 2011 is at least 1.25 x 4 = 5.0; 2010 is at most 10/3 = 3.33 (the other at 2025: 10/6 x 2; or at
    #     2010: 1.25 x (2 + 2/3)). 2011.
    #   Either at the first setting, 2010, the other anywhere: f >= 10 / 10 = 1.0, 2011 at least 1 x (4 + 4/3) = 5.33,
    #     2010 at most 3.33 again (the other at 2025: 1.25 x (2 + 2/3)). 2011.
    #   So every combination with either question at an end, the four corners among them, is cohort 2011: the corners
    #   alone would call the reference defined.
    #   Both interior, both at 2012 to 2022: f = 1.0; 2011 1 x 4 = 4 < 4.5; 2012 1 x (6 + 2/3 + 2/3) = 7.33 -> 2012.
    #   Both interior, a at 2022 and b at 2023: f = 10 / (6 + 2 + 4/3) = 1.0714; 2011 4.29 < 4.5; 2012 6.43 -> 2012.
    #   Both interior, both at 2023: f = 10 / 8.67 = 1.1538; 2011 4.62 -> 2011 (an interior combination that agrees).
    #   Both interior, both at 2011: f = 1.0; 2011 4 + 2/3 + 2/3 = 5.33 -> 2011.
    t, ref = solve(case_two_questions)
    k = (1, "RG")
    assert [q["settings"] for q in t["questions"]] == [list(range(2010, 2026))] * 2
    assert t["combinations"] == 256
    for corner in ((2010, 2010), (2010, 2025), (2025, 2010), (2025, 2025)):
        assert at(t, corner, k)[1] == ("cohort", 2011.0)
    assert at(t, (2010, 2010), k)[0] == pytest.approx(1.0) and at(t, (2025, 2025), k)[0] == pytest.approx(10 / 6)
    assert at(t, (2012, 2012), k) == (pytest.approx(1.0), ("cohort", 2012.0))
    assert at(t, (2022, 2023), k) == (pytest.approx(10 / (8 + 4 / 3)), ("cohort", 2012.0))
    assert at(t, (2023, 2023), k) == (pytest.approx(10 / (6 + 8 / 3)), ("cohort", 2011.0))
    assert at(t, (2011, 2011), k) == (pytest.approx(1.0), ("cohort", 2011.0))
    ends = {2010, 2025}
    for r in t["rows"]:
        if r["setting"][0] in ends or r["setting"][1] in ends:
            assert r["pairs"][k] == ("cohort", 2011.0), r["setting"]           # agreement wherever either is at an end
    differing = [r["setting"] for r in t["rows"] if r["pairs"][k] != ("cohort", 2011.0)]
    assert differing and all(a not in ends and b not in ends for a, b in differing)
    assert ref[k]["defined"] is False and ref[k]["differs_inside_only"] is True
    assert ref[k]["seen"] == [("cohort", 2011.0), ("cohort", 2012.0)]


# ---- the listing, against pass_c_expand's, and the guards -------------------------------------------------------------

@pytest.mark.parametrize("interval,never,want", [
    ((2010, 2025), False, list(range(2010, 2026))),
    ((None, 2003), False, [1999, 2000, 2001, 2002, 2003]),         # open below: every start at or before 1999 is 1999
    ((1990, 2001), False, [1999, 2000, 2001]),
    ((1990, 1995), False, [1995]),                                 # wholly before the open-below start: entered once
    ((2020, None), True, [2020, 2021, 2022, 2023, 2024, 2025, 2026, "never"]),
    ((2024, 2030), True, [2024, 2025, 2026, "never"]),             # starts after the panel: entered once, as 2026
    ((2027, 2030), False, [2026]),
    ((2016, 2016), True, [2016, "never"]),
])
def test_the_date_settings_listed_here_are_pass_c_expands(interval, never, want):
    inp = _own_site_world()
    c = date("d", interval[0], interval[1], None, never=never)
    adm = en.admissible_reference_settings(inp, [c], "RA", provisional_defines=True)   # asserts equality with _date_values
    assert adm["questions"] == [{"fid": "d", "question": "date", "settings": want}]
    assert want == px._date_values(px.parse_corrections([c], inp)["d"])


def test_the_capacity_settings_listed_here_are_pass_c_expands():
    inp, corrections, st = case_capacity_rest_earliest()
    assert en.admissible_reference_settings(inp, corrections, st, True)["questions"][0]["settings"] == list(range(2012, 2026))
    two = [split("c", 2010, 0.5)]                                  # no rest_earliest: its two cases
    assert en.admissible_reference_settings(inp, two, st, True)["questions"][0]["settings"] == [px.EARLY, px.LATE]
    # A capacity split with a convention is not reference-defining; neither is a date with a convention not provisional.
    assert en.admissible_reference_settings(inp, [split("c", 2010, 0.5, convention="late")], st, True)["questions"] == []
    inp, _, st = case_own_site()
    assert en.admissible_reference_settings(inp, [date("d", 2010, 2025, 2015)], st, True)["questions"] == []


def test_a_question_in_another_state_is_not_listed():
    inp, corrections, st = case_own_site()
    assert en.admissible_reference_settings(inp, corrections, "ZZ", True) == {"questions": [], "combinations": 1}


def test_over_the_limit_the_enumerator_refuses():
    inp, corrections, st = case_two_questions()
    with pytest.raises(ValueError, match="more than 100"):
        en.table(inp, corrections, st, limit=100)


def test_no_load_sits_near_a_threshold_in_any_hand_case():
    """Every realised setting of every case: no load within one part in a million of 2% or of the 0.5% floor."""
    for name, build in HAND_CASES.items():
        for flag in (True, False):
            t, _ = solve(build, flag)
            for r in t["rows"]:
                assert min(r["gap"].values()) > 1e-6, (name, flag, r["setting"])


def test_a_defined_reference_is_the_pair_at_the_reference_configuration():
    """Where nothing is reference-defining the one combination is the reference configuration itself, realised with no
    choice: scratch_state puts each question at its convention."""
    inp, _, st = case_own_site()
    t = en.table(inp, [date("d", 2010, 2025, 2019)], st)
    assert t["combinations"] == 1 and t["rows"][0]["pairs"][(1, "RA")] == ("cohort", 2019.0)   # 2018 3; 2019 4
    fac, fy, factor = px.scratch_state(inp, px.parse_corrections([date("d", 2010, 2025, 2019)], inp), st, {})
    assert factor == pytest.approx(1.0) and fy[fy.fid == "d"].year.min() == 2019
