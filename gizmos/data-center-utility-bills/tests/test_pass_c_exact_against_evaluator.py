"""The exact attribution against the exhaustive evaluator (docs/gate1/exact-attribution-brief-2026-11-16.md, section 7).

Load and sales only; no price is read. Every case is a made-up state built with world() or mini() from
tests/test_pass_c_expand.py, small enough for the full product of every setting of every question.

Written to the interface of the brief's section 6 without sight of the implementation:
    from pipeline.facilities import pass_c_exact
    pass_c_exact.exact_attribution(inp, px.parse_corrections(corrections, inp), st)
It was written in a checkout that does not have pipeline/facilities/pass_c_exact.py, so the comparison tests here could
not be run there; the cases themselves (what each exercises) are checked against the evaluator alone in
tests/test_exhaustive_evaluator.py. The implementation is imported inside each test, so a missing or broken module
fails loudly rather than skipping.

For each case and every utility of its state: the method is "exact" and complete is true; the kept set
{(fid, question)} equals the evaluator's pivotal set; the references agree (defined or not; where defined, the place
and the crossing); and every witness pair, realised through the evaluator's own realisation (questions absent from a
witness held at the reference configuration), differs in exactly the named question and gives two different outcomes
by the evaluator's outcome function.

Added under docs/gate1/reference-repair-rule-2026-11-18.md, section 8.5 (agent B, 2026-11-18; written in a checkout
without pipeline/facilities/pass_c_exact.py at any version, and not run there): every case of the rule's section 8.2
(tests/test_reference_enumerator.py's HAND_CASES, named "ref_..." here) and one case the outcome's no-anchoring place
alone separates ("na_place_only"). The comparison runs under both criteria of rule R7, passed as
`exact_attribution(..., criterion=...)` and to the evaluator: "either_reading" (the default) and "as_built". The
evaluator's references now come from tests/reference_enumerator.py (every admissible reference setting), so the
references compared are rule R2's, not the ends'. Existing cases and assertions are unchanged.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import GWH, date, mini, split, world  # noqa: E402,F401

import exhaustive_evaluator as ex  # noqa: E402
from test_reference_enumerator import HAND_CASES  # noqa: E402


def T(mw: float) -> float:
    """The base-period sales (GWh) whose 2% threshold is `mw` MW of load all year."""
    return mw * GWH / 0.02


def prov(c: dict) -> dict:
    return {**c, "convention_is": "provisional"}


# ---- the cases ------------------------------------------------------------------------------------------------------
# Each builder returns (inputs, corrections, state). Loads and thresholds are chosen so that no load sits within one
# part in a million of a threshold (test_exhaustive_evaluator checks that over every configuration).

def case_two_of_four():
    # Four 1 MW unresolved sites on utility 5, each also a candidate of 6; both utilities' threshold is 1.5 MW.
    sites = [{"fid": f"a{i}", "st": "CC", "u": 5, "cands": "5;6", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}
             for i in range(1, 5)]
    return mini(sites, {(5, "CC"): T(1.5), (6, "CC"): T(1.5)}), [], "CC"


def case_interior():
    # d's date decides utility 1's cohort crossing (start + 2): only the interior starts 2012-2014 land within a year of
    # the reference's 2015; the two ends (2010, 2016) both miss it. e (0.3 MW, unresolved 1;2) is 1% of utility 2.
    sites = [{"fid": "d", "st": "AA", "u": 1, "raw": 3.0, "year": 2013},
             {"fid": "e", "st": "AA", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 0.3, "year": 2005}]
    return mini(sites, {(1, "AA"): T(2.5), (2, "AA"): 0.3 * GWH / 0.01}), [date("d", 2010, 2016, 2013)], "AA"


def case_factor_cap_everywhere():
    # EPRI far above the permit total: the factor is at the cap (3) in every setting of p's date (which reaches 2025).
    sites = [{"fid": "p", "st": "BB", "u": 1, "raw": 4.0, "year": 2020},
             {"fid": "q", "st": "BB", "u": 2, "raw": 2.0, "year": 2010}]
    return mini(sites, {(1, "BB"): T(7.0), (2, "BB"): T(5.0)}, {"BB": 1.0}), [date("p", 2020, 2025, 2020)], "BB"


def case_factor_floor_everywhere():
    # EPRI far below the permit total: the factor is at the floor (0.2) in every setting of p's date (and "never").
    sites = [{"fid": "p", "st": "DD", "u": 1, "raw": 4.0, "year": 2021},
             {"fid": "q", "st": "DD", "u": 2, "raw": 2.0, "year": 2010}]
    return (mini(sites, {(1, "DD"): T(3.0), (2, "DD"): T(0.35)}, {"DD": 0.001}),
            [date("p", 2021, 2024, 2021, never=True)], "DD")


def case_factor_cap_some():
    # The factor is 14 MW-equivalent over the permit total: 2.0 with p full in 2024 (7 MW), 2.47 with p started in 2023,
    # and at the cap (3) with p started in 2024 or later, or never. p reaches utilities 2 and 3 only through the factor.
    sites = [{"fid": "p", "st": "EE", "u": 1, "raw": 4.0, "year": 2020},
             {"fid": "q", "st": "EE", "u": 2, "raw": 2.0, "year": 2010},
             {"fid": "w", "st": "EE", "u": 2, "cands": "2;3", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(1, "EE"): T(7.0), (2, "EE"): T(5.5), (3, "EE"): T(2.75)}, {"EE": 2.0 * 7.0 * GWH / 1000})
    return inp, [date("p", 2020, 2025, 2020, never=True)], "EE"


def case_permit_zero_some():
    # p is the only permit-based site with load in 2024: started in 2025 or 2026, or never, the permit total is zero and
    # the factor is 1; otherwise (EPRI less the measured m) / p's 2024 load: 0.5, 0.75 (2023), 1.5 (2024). r (start 2025,
    # no 2024 load) carries 1 MW raw in 2025, scaled; utility 2's threshold is 1.2 MW.
    sites = [{"fid": "p", "st": "GG", "u": 1, "raw": 2.0, "year": 2020},
             {"fid": "m", "st": "GG", "u": 3, "raw": 1.0, "year": 2010, "basis": "verified_public_figure"},
             {"fid": "r", "st": "GG", "u": 2, "cands": "2;4", "assign": "smallest_polygon", "raw": 3.0, "year": 2025}]
    inp = mini(sites, {(1, "GG"): T(0.9), (2, "GG"): T(1.2), (3, "GG"): 1e3, (4, "GG"): T(1.2)}, {"GG": 2.0 * GWH / 1000})
    return inp, [date("p", 2020, 2026, 2020, never=True)], "GG"


def case_permit_zero_every_and_no_base():
    # The only permit-based site starts in 2025 at the earliest: the permit total is zero in every setting and the
    # factor is 1. It is unresolved between utility 3 (base zero) and utility 4 (no base).
    sites = [{"fid": "p", "st": "HH", "u": 3, "cands": "3;4", "assign": "smallest_polygon", "raw": 2.0, "year": 2025},
             {"fid": "m", "st": "HH", "u": 5, "raw": 1.0, "year": 2010, "basis": "verified_public_figure"}]
    inp = mini(sites, {(3, "HH"): 0.0, (4, "HH"): float("nan"), (5, "HH"): 1e3})
    return inp, [date("p", 2025, 2026, 2025, never=True)], "HH"


def case_reopen():
    # v and v2 were verified on utility 1; the pass reopens both. v stays on 1 (among its candidates) and has a date;
    # v2's candidates are 3 and 2, so it is entered on 3 and can never be on 1.
    sites = [{"fid": "v", "st": "AA", "u": 1, "assign": "verified_by_hand", "raw": 3.0, "year": 2012},
             {"fid": "v2", "st": "AA", "u": 1, "assign": "verified_by_hand", "raw": 2.0, "year": 2010},
             {"fid": "k", "st": "AA", "u": 2, "raw": 1.0, "year": 2010}]
    corrections = [{"fid": "v", "kind": "reopen", "candidates": [2, 1]}, date("v", 2010, 2014, 2012),
                   {"fid": "v2", "kind": "reopen", "candidates": [3, 2]}]
    return mini(sites, {(1, "AA"): T(2.5), (2, "AA"): T(3.5), (3, "AA"): T(1.5)}), corrections, "AA"


def case_date_and_capacity():
    # One site with an assignment question, a date question and a capacity split with rest_earliest: half the row
    # with the first phase (2011-2013), the rest in any year from max(first phase, 2013) to the inventory's 2016.
    sites = [{"fid": "s", "st": "AA", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 4.0, "year": 2016}]
    corrections = [date("s", 2011, 2013, 2012), split("s", None, 0.5, rest_earliest=2013, convention="late")]
    return mini(sites, {(1, "AA"): T(2.5), (2, "AA"): T(3.5)}), corrections, "AA"


def case_comparison_floor():
    # Factor 0.5. x (2 MW raw) on utility 11 is 0.4% as built and 0.8% with no anchoring: a comparison place as built that
    # fails the no-anchoring floor. On utility 12 it is far under 0.5% either way.
    sites = [{"fid": "x", "st": "II", "u": 10, "cands": "10;11;12", "assign": "smallest_polygon", "raw": 2.0, "year": 2010},
             {"fid": "y", "st": "II", "u": 10, "raw": 6.0, "year": 2010}]
    inp = mini(sites, {(10, "II"): 1e3, (11, "II"): 1.0 * GWH / 0.004, (12, "II"): 1e6}, {"II": 0.5 * 8.0 * GWH / 1000})
    return inp, [date("x", 2008, 2012, 2010)], "II"


def case_undefined():
    # d has no convention and its ends move utility 1's crossing: utility 1 has no reference. f has no convention either,
    # but every start from 1999 to 2001 gives utility 2 the same early crossing (2001): its reference is defined.
    sites = [{"fid": "d", "st": "JJ", "u": 1, "raw": 3.0, "year": 2014},
             {"fid": "f", "st": "JJ", "u": 2, "raw": 30.0, "year": 2000},
             {"fid": "g", "st": "JJ", "u": 1, "cands": "1;3", "assign": "smallest_polygon", "raw": 0.7, "year": 2005}]
    inp = mini(sites, {(1, "JJ"): T(2.5), (2, "JJ"): T(1.0), (3, "JJ"): 1e3})
    return inp, [date("d", 2012, 2016, None), date("f", 1995, 2001, None)], "JJ"


def case_provisional():
    # d's convention (2014) is provisional: its ends (2012, 2016) give utility 1 different crossings, so no reference.
    # f's is provisional too, but its ends give utility 2 the same crossing. h's convention is not provisional.
    sites = [{"fid": "d", "st": "KK", "u": 1, "raw": 3.0, "year": 2014},
             {"fid": "f", "st": "KK", "u": 2, "raw": 30.0, "year": 2000},
             {"fid": "h", "st": "KK", "u": 3, "raw": 3.0, "year": 2014}]
    inp = mini(sites, {(1, "KK"): T(2.5), (2, "KK"): T(1.0), (3, "KK"): T(2.5)})
    return inp, [prov(date("d", 2012, 2016, 2014)), prov(date("f", 1995, 2001, 2000)), date("h", 2013, 2015, 2014)], "KK"


def case_several_candidates():
    # s lists five candidates: 23 is not a panel unit, 22 is too large for s to matter, 24 has a zero base.
    sites = [{"fid": "s", "st": "LL", "u": 20, "cands": "20;21;22;23;24", "assign": "smallest_polygon", "raw": 2.0,
              "year": 2010},
             {"fid": "t", "st": "LL", "u": 21, "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(20, "LL"): 1e3, (21, "LL"): T(2.5), (22, "LL"): 1e6, (24, "LL"): 0.0})
    return inp, [date("s", 2009, 2011, 2010)], "LL"


def case_candidates_kind():
    # c was alone in utility 30's territory (resolved); a candidates correction adds utility 31, so it is unresolved.
    sites = [{"fid": "c", "st": "MM", "u": 30, "raw": 2.0, "year": 2010},
             {"fid": "o", "st": "MM", "u": 30, "raw": 0.5, "year": 2012}]
    inp = mini(sites, {(30, "MM"): T(1.5), (31, "MM"): 1e3})
    return inp, [{"fid": "c", "kind": "candidates", "candidates": [30, 31]}], "MM"


def case_mixed():
    # Several channels together: p's date reaches 2025 and "never" and moves the factor; a and b are unresolved; s has
    # a provisional date and a capacity split with rest_earliest.
    sites = [{"fid": "p", "st": "NN", "u": 1, "raw": 4.0, "year": 2022},
             {"fid": "a", "st": "NN", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.5, "year": 2012},
             {"fid": "b", "st": "NN", "u": 2, "cands": "2;3", "assign": "smallest_polygon", "raw": 1.0, "year": 2014},
             {"fid": "s", "st": "NN", "u": 3, "raw": 2.0, "year": 2018}]
    inp = mini(sites, {(1, "NN"): T(4.5), (2, "NN"): T(1.3), (3, "NN"): T(2.2)}, {"NN": 1.2 * 8.5 * GWH / 1000})
    corrections = [date("p", 2021, 2025, 2022, never=True), prov(date("s", 2015, 2018, 2016)),
                   split("s", None, 0.5, rest_earliest=2016, convention="early")]
    return inp, corrections, "NN"


def case_world_reopen():
    # world()'s state AA: p1 reopened onto 1 or 3, with a date; p2 unresolved between 1 and 2.
    inp = world()
    return inp, [{"fid": "p1", "kind": "reopen", "candidates": [1, 3]}, date("p1", 2010, 2014, 2012)], "AA"


def case_two_years_as_built():
    # The one-year tolerance, as built. Factor 1. d (3 MW on utility 1, threshold 2.5 MW) crosses at start + 2: starts
    # 2012-2014 give 2014-2016 against the reference's 2016, so 2012 is exactly two years off (not accepted) and 2013 one
    # (accepted): d is pivotal for 1 by that alone. e (3 MW on utility 2, same threshold) starts 2013 or 2014: crossings
    # 2015 and 2016, both within a year of 2016: a one-year move inside the band, not pivotal.
    sites = [{"fid": "d", "st": "PA", "u": 1, "raw": 3.0, "year": 2014},
             {"fid": "e", "st": "PA", "u": 2, "raw": 3.0, "year": 2014}]
    return (mini(sites, {(1, "PA"): T(2.5), (2, "PA"): T(2.5)}),
            [date("d", 2012, 2014, 2014), date("e", 2013, 2014, 2014)], "PA")


def case_two_years_no_anchoring():
    # The one-year tolerance, with no anchoring only. Factor 2 in every setting (every start is before 2023). Utility 1,
    # threshold 3 MW: P (2 MW raw from 2010) scaled is 1.33, 2.67, 4 in 2010-2012, so as built it crosses in 2012
    # whatever Q does (Q starts in 2012 at the earliest). With no anchoring P is 2 MW from 2012 and Q (1.8 MW raw) adds
    # 0.6, 1.2: Q from 2012 gives 2.6 in 2012 and 3.2 in 2013 -> 2013 (one year from 2012, accepted); Q from 2013 gives
    # 2014 (exactly two years, not accepted).
    sites = [{"fid": "P", "st": "PC", "u": 1, "raw": 2.0, "year": 2010},
             {"fid": "Q", "st": "PC", "u": 1, "raw": 1.8, "year": 2012}]
    return (mini(sites, {(1, "PC"): T(3.0)}, {"PC": 2.0 * 3.8 * GWH / 1000}),
            [date("Q", 2012, 2013, 2012)], "PC")


def case_undefined_no_anchoring_crossing():
    # An undefined reference and a question that moves only the no-anchoring crossing. Factor 2 throughout; utility 1,
    # threshold 3 MW. U (0.75 MW raw, no convention, starts 2005-2012): as built it crosses in 2011 for a start up to
    # 2011 (2.67 + 1.5 or + 0.5 at 2011) and 2012 for a start in 2012: the ends differ, the reference is undefined.
    # Q (1.8 MW raw, starts 2012 or 2013) never moves the as-built crossing (it is 2011 or 2012 before Q has load that
    # matters), never moves a floor flag (always over 0.5%), and with U full by 2012 moves the no-anchoring crossing
    # from 2012 (2 + 0.75 + 0.6 = 3.35) to 2013 (2.75 in 2012).
    sites = [{"fid": "P", "st": "PD", "u": 1, "raw": 2.0, "year": 2010},
             {"fid": "Q", "st": "PD", "u": 1, "raw": 1.8, "year": 2012},
             {"fid": "U", "st": "PD", "u": 1, "raw": 0.75, "year": 2008}]
    return (mini(sites, {(1, "PD"): T(3.0)}, {"PD": 2.0 * (2.0 + 1.8 + 0.75) * GWH / 1000}),
            [date("Q", 2012, 2013, 2012), date("U", 2005, 2012, None)], "PD")


def case_undefined_no_anchoring_floor():
    # An undefined reference and a question that moves only the no-anchoring floor flag. The factor is at the floor (0.2)
    # in every setting (R keeps the permit total positive). Utility 1: floor 1 MW (base 1752 GWh), 2% 4 MW. U is a
    # measured 1.6 MW (unscaled) with no convention, starts 2015-2026: from 2015 it is over the floor as built
    # (neither); from 2026 it carries nothing: the ends give different places, the reference is undefined. Q (2.25 MW
    # raw, scaled 0.45) never takes the as-built reading over the floor on its own and never makes a crossing (U + Q is
    # 3.85 MW at most); with U at 2026, Q full (2.25 MW) is over the floor with no anchoring and Q from 2025 (0.75 MW)
    # is under it.
    sites = [{"fid": "U", "st": "PE", "u": 1, "raw": 1.6, "year": 2015, "basis": "verified_public_figure"},
             {"fid": "Q", "st": "PE", "u": 1, "raw": 2.25, "year": 2020},
             {"fid": "R", "st": "PE", "u": 2, "raw": 5.0, "year": 2010}]
    return (mini(sites, {(1, "PE"): GWH / 0.005, (2, "PE"): 1e6}, {"PE": 0.001}),
            [date("U", 2015, 2026, None), date("Q", 2020, 2025, 2020)], "PE")


def case_as_built_tolerance_alone():
    # Factor 0.5 (constant: every start is before 2023). Utility 1, threshold 3 MW. Z (4 MW raw from 2012) carries the
    # no-anchoring crossing: 1.33, 2.67, 4 -> 2014, and P (starting 2014 at the earliest) cannot bring it earlier. As
    # built Z is 2 MW from 2014 and P (4 MW raw, 0.67, 1.33, 2 scaled) crosses with it in its second year: starts
    # 2014, 2015, 2016 give 2015, 2016, 2017 against the reference's 2015 (P at 2014). The no-anchoring 2014 is within a
    # year of 2015 throughout; only the as-built crossing of the start 2016 is two years off.
    sites = [{"fid": "Z", "st": "QA", "u": 1, "raw": 4.0, "year": 2012},
             {"fid": "P", "st": "QA", "u": 1, "raw": 4.0, "year": 2014}]
    return (mini(sites, {(1, "QA"): T(3.0)}, {"QA": 0.5 * 8.0 * GWH / 1000}),
            [date("P", 2014, 2016, 2014)], "QA")


def case_early_reference():
    # Factor 2 (constant). Thresholds 3 MW. Utility 1: P1 (2 MW raw from 2005) is 4 MW as built from 2007 and crosses in
    # 2007 (2.67 in 2006): an early reference that no start of Q1 (2008 at the earliest) can move. With no anchoring P1
    # is 2 MW and Q1 (1.8 MW raw: 0.6, 1.2) crosses with it in its second year: starts 2008, 2009, 2010 give 2009, 2010,
    # 2011, so only the start 2010 takes the no-anchoring crossing out of the early years. Utility 2 is the mirror: Q2's
    # starts 2007-2009 give no-anchoring crossings 2008-2010, all early, and change nothing.
    sites = [{"fid": "P1", "st": "QB", "u": 1, "raw": 2.0, "year": 2005},
             {"fid": "Q1", "st": "QB", "u": 1, "raw": 1.8, "year": 2008},
             {"fid": "P2", "st": "QB", "u": 2, "raw": 2.0, "year": 2005},
             {"fid": "Q2", "st": "QB", "u": 2, "raw": 1.8, "year": 2007}]
    return (mini(sites, {(1, "QB"): T(3.0), (2, "QB"): T(3.0)}, {"QB": 2.0 * 7.6 * GWH / 1000}),
            [date("Q1", 2008, 2010, 2008), date("Q2", 2007, 2009, 2007)], "QB")


def case_late_and_neither_references():
    # Factor 0.5 (constant; assignments do not move it). Utility 3 (threshold 3 MW): P3 (4 MW raw from 2010) is 2 MW as
    # built, with Q3 (1.5 MW raw from 2005, unresolved 3;6) 2.75: never a crossing, always over the floor: "neither".
    # With no anchoring Q3 moves the crossing from 2012 (P3 alone) to 2011. Utility 4 (threshold 1.8 MW): P4 (4 MW raw
    # from 2021) crosses as built in 2023 (1.33 in 2022, or 1.73 with Q4): "late". With no anchoring Q4 (0.8 MW raw from
    # 2015, unresolved 4;6) moves the crossing from 2022 to 2021. Neither question may be kept for 3 or 4.
    sites = [{"fid": "P3", "st": "QC", "u": 3, "raw": 4.0, "year": 2010},
             {"fid": "Q3", "st": "QC", "u": 3, "cands": "3;6", "assign": "smallest_polygon", "raw": 1.5, "year": 2005},
             {"fid": "P4", "st": "QC", "u": 4, "raw": 4.0, "year": 2021},
             {"fid": "Q4", "st": "QC", "u": 4, "cands": "4;6", "assign": "smallest_polygon", "raw": 0.8, "year": 2015}]
    return (mini(sites, {(3, "QC"): T(3.0), (4, "QC"): T(1.8), (6, "QC"): 1e6}, {"QC": 0.5 * 10.3 * GWH / 1000}),
            [], "QC")


def case_cohort_no_anchoring_to_early():
    # Factor 0.5. Utility 1, threshold 2.5 MW. P (6 MW raw from 2010) as built is 1, 2, 3 MW: crosses 2012, and Q (0.9 MW
    # raw from 2005, scaled 0.45, unresolved 1;2) leaves that alone (2.45 in 2011). With no anchoring P is 2, 4 in 2010,
    # 2011: 2011 alone, 2010 with Q (2.9): Q on 1 takes the no-anchoring crossing out of the cohort years into the early.
    sites = [{"fid": "P", "st": "QD", "u": 1, "raw": 6.0, "year": 2010},
             {"fid": "Q", "st": "QD", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 0.9, "year": 2005}]
    return mini(sites, {(1, "QD"): T(2.5), (2, "QD"): 1e6}, {"QD": 0.5 * 6.9 * GWH / 1000}), [], "QD"


def case_cohort_no_anchoring_to_none():
    # Factor 2. Utility 1, threshold 3 MW. P (2 MW raw from 2010) as built crosses 2012 (4 MW); Q (1.8 MW raw from 2012,
    # unresolved 1;2) adds nothing before. With no anchoring P alone (2 MW) never crosses; with Q it does in 2013.
    sites = [{"fid": "P", "st": "QE", "u": 1, "raw": 2.0, "year": 2010},
             {"fid": "Q", "st": "QE", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.8, "year": 2012}]
    return mini(sites, {(1, "QE"): T(3.0), (2, "QE"): 1e6}, {"QE": 2.0 * 3.8 * GWH / 1000}), [], "QE"


CASES = {
    "two_of_four": case_two_of_four,
    "interior": case_interior,
    "factor_cap_everywhere": case_factor_cap_everywhere,
    "factor_floor_everywhere": case_factor_floor_everywhere,
    "factor_cap_some": case_factor_cap_some,
    "permit_zero_some": case_permit_zero_some,
    "permit_zero_every_and_no_base": case_permit_zero_every_and_no_base,
    "reopen": case_reopen,
    "date_and_capacity": case_date_and_capacity,
    "comparison_floor": case_comparison_floor,
    "undefined": case_undefined,
    "provisional": case_provisional,
    "several_candidates": case_several_candidates,
    "candidates_kind": case_candidates_kind,
    "mixed": case_mixed,
    "world_reopen": case_world_reopen,
    "two_years_as_built": case_two_years_as_built,
    "two_years_no_anchoring": case_two_years_no_anchoring,
    "undefined_no_anchoring_crossing": case_undefined_no_anchoring_crossing,
    "undefined_no_anchoring_floor": case_undefined_no_anchoring_floor,
    "as_built_tolerance_alone": case_as_built_tolerance_alone,
    "early_reference": case_early_reference,
    "late_and_neither_references": case_late_and_neither_references,
    "cohort_no_anchoring_to_early": case_cohort_no_anchoring_to_early,
    "cohort_no_anchoring_to_none": case_cohort_no_anchoring_to_none,
}


def case_na_place_only():
    # Factor 0.5 (P = 4 + 1.8 = 5.8 MW, every start before 2023). Utility 1, threshold 3 MW, floor 0.75 MW. P (4 MW raw
    # from 2010) as built is 0.67, 1.33, 2 MW and Q (1.8 MW raw from 2005, unresolved 1;2) adds 0.9: at most 2.9 MW, never
    # a crossing, over the floor: "neither" with Q on 1 or off it. With no anchoring P is 1.33, 2.67, 4: 2012 without Q
    # (cohort); with Q 1.33 + 1.8 = 3.13 in 2010 (early). Under a "neither" reference the pair (place as built, accepted)
    # is (neither, True) either way; the triple's no-anchoring place (early against cohort) keeps Q's assignment.
    sites = [{"fid": "P", "st": "QF", "u": 1, "raw": 4.0, "year": 2010},
             {"fid": "Q", "st": "QF", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.8, "year": 2005}]
    return mini(sites, {(1, "QF"): T(3.0), (2, "QF"): 1e6}, {"QF": 0.5 * 5.8 * GWH / 1000}), [], "QF"


CASES.update({f"ref_{name}": build for name, build in HAND_CASES.items()})
CASES["na_place_only"] = case_na_place_only
CRITERIA = ("either_reading", "as_built")


# ---- the comparison --------------------------------------------------------------------------------------------------

def _impl():
    from pipeline.facilities import pass_c_exact  # imported here: a missing implementation fails, it does not skip
    return pass_c_exact


def _ukey(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def _crossing_str(c) -> str:
    return "never" if c is None else str(int(c))


@pytest.mark.parametrize("criterion", CRITERIA)
@pytest.mark.parametrize("name", list(CASES))
def test_the_exact_attribution_matches_the_full_product(name, criterion):
    pce = _impl()
    inp, corrections, st = CASES[name]()
    ev = ex.Evaluator(inp, corrections, st, criterion=criterion)
    piv = ev.pivotal()
    ref = ev.reference()
    res = pce.exact_attribution(inp, px.parse_corrections(corrections, inp), st, criterion=criterion)
    assert res["state"] == st
    # The questions as the conservative check lists them, unmerged: the same questions and setting counts as listed here.
    assert {(q["fid"], q["question"]): q["settings"] for q in res["questions"]} == \
        {q.key: len(q.settings) for q in ev.questions}, name
    assert set(res["utilities"]) == {_ukey(k) for k in ev.units}, name
    for k in ev.units:
        u = res["utilities"][_ukey(k)]
        tag = (name, _ukey(k))
        assert u["method"] == "exact" and u["why_conservative"] is None, tag
        assert u["complete"] is True, tag
        assert 1 <= u["configurations"] <= ev.n_configurations(), tag
        # The reference.
        r, mine = u["reference"], ref[k]
        assert r["defined"] == mine["defined"], (tag, r, mine)
        if mine["defined"]:
            assert r["place"] == mine["place"] and r["crossing"] == _crossing_str(mine["crossing"]), (tag, r, mine)
            assert r["why_undefined"] is None
        else:
            assert r["why_undefined"], tag
            defining = {q.key for q in ev.questions if q.defining}
            assert r["undefined_by"] and {(x["fid"], x["question"]) for x in r["undefined_by"]} <= defining, (tag, r)
        # The kept set against the pivotal set.
        kept = {(q["fid"], q["question"]) for q in u["kept_questions"]}
        assert kept == piv[k], (tag, sorted(kept), sorted(piv[k]))
        assert kept <= {(q["fid"], q["question"]) for q in u["relevant_questions"]}, tag
        assert sorted(u["joins"]) == sorted({f for f, _ in kept}), tag
        # Every witness, realised here.
        for q in u["kept_questions"]:
            w = q["witness"]
            name_q = f"{q['fid']} {q['question']}"
            assert name_q in w["a"]["settings"] and name_q in w["b"]["settings"], (tag, q)
            ca, cb = ev.normalise(w["a"]["settings"]), ev.normalise(w["b"]["settings"])
            differ = {key for key in ca if ca[key] != cb[key]}
            assert differ == {(q["fid"], q["question"])}, (tag, q, differ)
            oa, ob = ev.outcomes(ca)[k], ev.outcomes(cb)[k]
            assert oa != ob, (tag, q, oa, ob)
    # The whole result survives json.
    import json
    json.dumps(res)


def test_over_a_small_ceiling_a_utility_takes_the_conservative_result_unchanged():
    pce = _impl()
    inp, corrections, st = case_factor_cap_some()
    corr = px.parse_corrections(corrections, inp)
    res = pce.exact_attribution(inp, corr, st, ceiling=2)
    jc = px.joint_check(inp, corr, st)
    n_cons = 0
    for key, u in res["utilities"].items():
        if u["configurations"] > 2:
            n_cons += 1
            assert u["method"] == "conservative" and u["complete"] is False and u["why_conservative"], key
            got = sorted((q["fid"], q["question"], q["channel"]) for q in u["kept_questions"])
            want = sorted((q["fid"], q["question"], q["channel"]) for q in jc["utilities"][key]["kept_questions"])
            assert got == want, key
            assert all("witness" not in q for q in u["kept_questions"]), key
        else:
            assert u["method"] == "exact" and u["complete"] is True, key
    assert n_cons >= 2


def test_every_case_is_attributed_exactly_and_no_site_has_a_divisor_range():
    """Section 2's exclusion (a no-anchoring divisor range whose ends differ) is not met by any case here."""
    for name, build in CASES.items():
        inp, corrections, st = build()
        corr = px.parse_corrections(corrections, inp)
        units = inp.units[inp.units.get_level_values("state") == st]
        sites, _, _ = px._sites(inp, corr, st, units)
        assert all(s.na_div[0] == s.na_div[1] for s in sites), name
        assert np.isfinite(ex.Evaluator(inp, corrections, st).n_configurations())
