"""The exhaustive evaluator (tests/exhaustive_evaluator.py) against answers worked out by hand, and the cases of
tests/test_pass_c_exact_against_evaluator.py checked to exercise what each claims to.

Load and sales only; no price is read. Everything is made up with mini() and world() from tests/test_pass_c_expand.py.

Arithmetic used throughout: a site of R MW starting in year s carries R/3 in s, 2R/3 in s+1 and R from s+2
(buildout.ramp_mw, three ramp years); a utility's GWh in a year is 8.76 x MW; T(m) is the base whose 2% threshold is
m MW of load all year (T(m) = m x 8.76 / 0.02). mini() gives each state the factor 1 unless its EPRI total is set.

Brought up to date under docs/gate1/reference-repair-rule-2026-11-18.md, section 8.3 (agent B, 2026-11-18): the
evaluator's reference now comes from tests/reference_enumerator.py at every setting of every reference-defining
question, and its outcome with a defined reference is rule R7's triple (place as built, place with no anchoring,
accepted) by default, the old pair under criterion="as_built". Every changed expectation keeps its old value under
"as_built" or is rewritten to the triple with the no-anchoring place worked out beside it; the limit of twelve
questions is now a refusal above 4096 combinations. No pivotal set or reference expected here changed. The last
section pins the cases added for the rule's section 8.5 and the one case on file whose pivotal set the triple widens.
"""
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import GWH, _realize, date, mini  # noqa: E402

import exhaustive_evaluator as ex  # noqa: E402
import test_pass_c_exact_against_evaluator as cmp  # noqa: E402

T = cmp.T
CAN_PARSE_CANDIDATES = "candidates" in px.KINDS      # the candidates kind is in pass_c_expand from D-66 step 1 on


def evaluator(name):
    inp, corrections, st = cmp.CASES[name]()
    return ex.Evaluator(inp, corrections, st)


@pytest.fixture(scope="module")
def solved():
    """Every comparison case: its evaluator (with every configuration realised and cached) and its pivotal sets."""
    out = {}
    for name in cmp.CASES:
        ev = evaluator(name)
        out[name] = (ev, ev.pivotal())
    return out


# ---- the outcome function -------------------------------------------------------------------------------------------

def test_the_readings_of_a_utility_with_no_positive_base():
    v = np.zeros(len(asg.YEARS))
    v[-1] = 1.0
    for base in (0.0, float("nan")):
        r = ex.reading(v, base, 0.02)
        assert r["crossing"] is None and r["share"] == math.inf and r["place"] == "neither"   # any load: over the floor
        r = ex.reading(np.zeros(len(asg.YEARS)), base, 0.02)
        assert r["crossing"] is None and r["share"] == 0.0 and r["place"] == "comparison"      # no load: share 0
    r = ex.reading(v, 219.0, 0.02)                                     # 2% of 219 is 4.38 GWh; 1 GWh is 1/219 = 0.457%
    assert r["crossing"] is None and r["place"] == "comparison" and r["share"] == pytest.approx(1 / 219)
    r = ex.reading(v, 150.0, 0.02)                                     # 2% is 3 GWh; 1 GWh is 0.667%: over the floor
    assert r["crossing"] is None and r["place"] == "neither"
    r = ex.reading(v * 4, 150.0, 0.02)                                 # 4 GWh in 2025 alone: a late crossing
    assert r["crossing"] == 2025.0 and r["place"] == "late"


def test_the_outcome_with_a_defined_and_an_undefined_reference():
    base = 1000.0                                                                             # 2%: 20 GWh; floor: 5 GWh
    y = asg.YEARS
    def path(first):                                                                          # 30 GWh from `first` on
        return np.array([30.0 if yr >= first else 0.0 for yr in y])
    cohort = {"defined": True, "place": "cohort", "crossing": 2015.0}
    assert ex.outcome(path(2016), path(2014), base, cohort, 0.02, "as_built") == ("defined", "cohort", True)     # 1 year each way
    assert ex.outcome(path(2016), path(2013), base, cohort, 0.02, "as_built") == ("defined", "cohort", False)    # no anchoring 2 early
    assert ex.outcome(path(2017), path(2015), base, cohort, 0.02, "as_built") == ("defined", "cohort", False)
    assert ex.outcome(path(2009), path(2009), base, cohort, 0.02, "as_built") == ("defined", "early", False)
    early = {"defined": True, "place": "early", "crossing": 2005.0}
    assert ex.outcome(path(2008), path(2010), base, early, 0.02, "as_built") == ("defined", "early", True)
    assert ex.outcome(path(2008), path(2011), base, early, 0.02, "as_built") == ("defined", "early", False)
    comp = {"defined": True, "place": "comparison", "crossing": None}
    small = np.full(len(y), 4.0)                                                              # 0.4%
    assert ex.outcome(small, small, base, comp, 0.02, "as_built") == ("defined", "comparison", True)
    assert ex.outcome(small, small * 2, base, comp, 0.02, "as_built") == ("defined", "comparison", False)  # 0.8% with no anchoring
    neither = {"defined": True, "place": "neither", "crossing": None}
    assert ex.outcome(small * 2, small * 4, base, neither, 0.02, "as_built") == ("defined", "neither", True)
    assert ex.outcome(path(2024), path(2024), base, neither, 0.02, "as_built") == ("defined", "late", False)
    undef = {"defined": False, "place": None, "crossing": None}
    assert ex.outcome(path(2016), path(2014), base, undef, 0.02) == ("undefined", 2016.0, 2014.0, False, False)
    assert ex.outcome(small, small * 2, base, undef, 0.02) == ("undefined", None, None, True, False)
    # Rule R7 (reference-repair-rule-2026-11-18.md; changed under its section 8.3): the default criterion,
    # "either_reading", gives the triple (place as built, place with no anchoring, accepted). The no-anchoring place is
    # the place of the same reading: the group of its crossing, or comparison / neither by its largest share.
    assert ex.outcome(path(2016), path(2014), base, cohort, 0.02) == ("defined", "cohort", "cohort", True)
    assert ex.outcome(path(2016), path(2013), base, cohort, 0.02) == ("defined", "cohort", "cohort", False)
    assert ex.outcome(path(2017), path(2015), base, cohort, 0.02) == ("defined", "cohort", "cohort", False)
    assert ex.outcome(path(2009), path(2009), base, cohort, 0.02) == ("defined", "early", "early", False)
    assert ex.outcome(path(2008), path(2010), base, early, 0.02) == ("defined", "early", "early", True)
    assert ex.outcome(path(2008), path(2011), base, early, 0.02) == ("defined", "early", "cohort", False)
    assert ex.outcome(small, small, base, comp, 0.02) == ("defined", "comparison", "comparison", True)
    assert ex.outcome(small, small * 2, base, comp, 0.02) == ("defined", "comparison", "neither", False)
    # 0.8% and 1.6% (16 GWh, under the 20 GWh threshold): neither in both readings.
    assert ex.outcome(small * 2, small * 4, base, neither, 0.02) == ("defined", "neither", "neither", True)
    assert ex.outcome(path(2024), path(2024), base, neither, 0.02) == ("defined", "late", "late", False)
    # The no-anchoring place alone separates two outcomes under a "neither" reference: the pair cannot see it.
    a, b = ex.outcome(small * 2, path(2009), base, neither, 0.02), ex.outcome(small * 2, path(2014), base, neither, 0.02)
    assert a == ("defined", "neither", "early", True) and b == ("defined", "neither", "cohort", True)
    assert ex.outcome(small * 2, path(2009), base, neither, 0.02, "as_built") == \
        ex.outcome(small * 2, path(2014), base, neither, 0.02, "as_built") == ("defined", "neither", True)
    assert ex.outcome(path(2016), path(2014), base, undef, 0.02, "as_built") == \
        ex.outcome(path(2016), path(2014), base, undef, 0.02)                         # undefined: the same four values
    with pytest.raises(ValueError, match="criterion"):
        ex.outcome(small, small, base, comp, 0.02, "either")


# ---- hand-worked cases ----------------------------------------------------------------------------------------------

def test_two_of_four_equal_sites_by_hand():
    # Four 1 MW sites from 2010 on utility 5, unresolved between 5 and 6; both thresholds 1.5 MW; factor 1.
    # n sites on a utility carry n/3, 2n/3, n MW in 2010, 2011, 2012 on.
    #   n=4: 1.33, 2.67 -> crosses 2011 (the reference for 5: every site on 5 as mapped; cohort 2011)
    #   n=3: 1.00, 2.00 -> 2011; n=2: 0.67, 1.33, 2.00 -> 2012 (within a year of 2011: accepted)
    #   n=1: at most 1 MW < 1.5 -> never; share 8.76 / T(1.5) = 1/1.5 x 2% = 1.33% >= 0.5% -> neither
    #   n=0: comparison
    # So utility 5's outcome is (cohort, accepted) for n >= 2 and something else for n <= 1: moving one site between
    # n=2 and n=1 changes it, for every site. Utility 6's reference is comparison (no site on it as mapped): n=0 gives
    # (comparison, accepted), n=1 (neither, not accepted): every site is pivotal for 6 too. 3^4 = 81 configurations.
    res = ex.pivotal_questions(*cmp.case_two_of_four())
    every = {(f"a{i}", "assignment") for i in range(1, 5)}
    assert res["configurations"] == 81
    assert res["reference"][(5, "CC")] == {"defined": True, "place": "cohort", "crossing": 2011.0}
    assert res["reference"][(6, "CC")] == {"defined": True, "place": "comparison", "crossing": None}
    assert res["pivotal"] == {(5, "CC"): every, (6, "CC"): every}


def one_site(interval, convention, provisional=False):
    # d: 3 MW on utility 1 (one territory, resolved), threshold 2.5 MW, factor 1. From a start s it carries 1, 2, 3 MW
    # in s, s+1, s+2: it crosses in s+2. Every start here is before 2023, so its 2024 load is full and the factor stays 1.
    inp = mini([{"fid": "d", "st": "AA", "u": 1, "raw": 3.0, "year": 2014}], {(1, "AA"): T(2.5)})
    c = date("d", interval[0], interval[1], convention)
    if provisional:
        c["convention_is"] = "provisional"
    return inp, [c], "AA"


def test_a_date_that_moves_a_cohort_crossing_by_more_than_one_year_is_pivotal():
    # Starts 2012 to 2016, convention 2014: crossings 2014 to 2018, reference cohort 2016.
    #   start 2012 -> 2014: two years from 2016 -> (cohort, not accepted); start 2013 -> 2015 -> (cohort, accepted).
    # The two differ only in d's date: pivotal. No anchoring reads the same (factor 1).
    res = ex.pivotal_questions(*one_site((2012, 2016), 2014))
    assert res["configurations"] == 5
    assert res["reference"][(1, "AA")] == {"defined": True, "place": "cohort", "crossing": 2016.0}
    assert res["pivotal"][(1, "AA")] == {("d", "date")}
    ev = ex.Evaluator(*one_site((2012, 2016), 2014))
    got = {s: ev.outcomes(ev.normalise({("d", "date"): s}))[(1, "AA")] for s in range(2012, 2017)}
    # Factor 1: the no-anchoring place is the as-built place (cohort) at every start (the triple, rule R7).
    assert got == {2012: ("defined", "cohort", "cohort", False), 2013: ("defined", "cohort", "cohort", True),
                   2014: ("defined", "cohort", "cohort", True), 2015: ("defined", "cohort", "cohort", True),
                   2016: ("defined", "cohort", "cohort", False)}


def test_a_date_that_moves_a_cohort_crossing_by_exactly_one_year_is_not_pivotal_under_a_defined_reference():
    # Starts 2014 or 2015, convention 2014: crossings 2016 and 2017, reference cohort 2016; both within a year of it,
    # as built and with no anchoring: (cohort, accepted) either way. Not pivotal.
    res = ex.pivotal_questions(*one_site((2014, 2015), 2014))
    assert res["configurations"] == 2
    assert res["reference"][(1, "AA")] == {"defined": True, "place": "cohort", "crossing": 2016.0}
    assert res["pivotal"][(1, "AA")] == set()


def test_with_no_convention_the_same_one_year_move_leaves_the_reference_undefined_and_is_pivotal():
    # No convention: the date is reference-defining. Its ends (2014, 2015) give crossings 2016 and 2017: not identical,
    # so the reference is undefined. The outcome is then the four values (2016, 2016, False, False) against
    # (2017, 2017, False, False): different, so the date is pivotal.
    res = ex.pivotal_questions(*one_site((2014, 2015), None))
    assert res["reference"][(1, "AA")] == {"defined": False, "place": None, "crossing": None}
    assert res["pivotal"][(1, "AA")] == {("d", "date")}


def test_a_provisional_convention_is_replaced_by_its_ends():
    # Convention 2014, provisional: the reference is found at the ends 2012 and 2016 (crossings 2014 and 2018), not at
    # the convention: undefined. The same interval with the convention not provisional has a reference (cohort 2016).
    res = ex.pivotal_questions(*one_site((2012, 2016), 2014, provisional=True))
    assert res["reference"][(1, "AA")]["defined"] is False and res["pivotal"][(1, "AA")] == {("d", "date")}
    res = ex.pivotal_questions(*one_site((2012, 2016), 2014))
    assert res["reference"][(1, "AA")]["defined"] is True


def floor_world():
    # Factor 0.5 (EPRI half of the 8 MW permit total). x: 2 MW raw from 2010, unresolved among 10, 11, 12; y: 6 MW raw
    # from 2010 on 10.
    sites = [{"fid": "x", "st": "II", "u": 10, "cands": "10;11;12", "assign": "smallest_polygon", "raw": 2.0, "year": 2010},
             {"fid": "y", "st": "II", "u": 10, "raw": 6.0, "year": 2010}]
    return mini(sites, {(10, "II"): 1e3, (11, "II"): GWH / 0.004, (12, "II"): 2 * GWH / 0.004},
                {"II": 0.5 * 8.0 * GWH / 1000}), [], "II"


def test_a_comparison_utility_at_the_floor_by_hand():
    # Utility 11 (base 2190 GWh): x on it is 1 MW scaled = 8.76 GWh = 0.4% as built (under 0.5%: comparison as built)
    # but 2 MW = 17.52 GWh = 0.8% with no anchoring: not accepted against its comparison reference (x on 10 as mapped,
    # nothing on 11). Off 11 it is (comparison, accepted). Pivotal.
    # Utility 12 (base 4380 GWh): 0.2% as built, 0.4% with no anchoring: accepted either way. Not pivotal.
    # Utility 10 (base 1000, 2% = 20 GWh = 2.28 MW): with x, as built 1.33, 2.67 MW in 2010, 2011 -> 2011 (the reference);
    # with no anchoring 2.67 MW in 2010 -> 2010, early: not accepted. Without x: as built y alone 1, 2, 3 -> 2012, and
    # with no anchoring 2, 4 -> 2011, both within a year of 2011: accepted. Pivotal. Four configurations.
    res = ex.pivotal_questions(*floor_world())
    assert res["configurations"] == 4
    assert res["reference"][(10, "II")] == {"defined": True, "place": "cohort", "crossing": 2011.0}
    assert res["reference"][(11, "II")] == {"defined": True, "place": "comparison", "crossing": None}
    assert res["pivotal"] == {(10, "II"): {("x", "assignment")}, (11, "II"): {("x", "assignment")}, (12, "II"): set()}
    ev = ex.Evaluator(*floor_world())
    on11 = ex.configuration_outcome(*floor_world(), {"x assignment": 11}, evaluator=ev)
    assert on11["outcomes"][(11, "II")] == ("defined", "comparison", "neither", False)          # 0.8%: neither, no anchoring
    assert on11["as_built"].loc[(11, "II")].max() / (GWH / 0.004) == pytest.approx(0.004)
    assert on11["no_anchoring"].loc[(11, "II")].max() / (GWH / 0.004) == pytest.approx(0.008)
    off = ex.configuration_outcome(*floor_world(), {"x assignment": "off_panel"}, evaluator=ev)
    assert off["outcomes"][(10, "II")] == ("defined", "cohort", "cohort", True)              # no anchoring 2011
    assert off["outcomes"][(11, "II")] == ("defined", "comparison", "comparison", True)
    assert ev.outcomes(ev.reference_configuration())[(10, "II")] == ("defined", "cohort", "early", False)   # 2010


def test_more_reference_settings_than_the_combination_limit_is_refused():
    # Thirteen two-setting questions: 2^13 = 8192 combinations, over the evaluator's limit of 4096 (the limit of twelve
    # questions is replaced by a refusal above a number of combinations; rule section 8.3).
    sites = [{"fid": f"d{i}", "st": "AA", "u": 1, "raw": 1.0, "year": 2014} for i in range(13)]
    inp = mini(sites, {(1, "AA"): T(2.5)})
    assert ex.REFERENCE_COMBINATION_LIMIT == 4096
    with pytest.raises(ValueError, match="8192 combinations .* more than 4096"):
        ex.Evaluator(inp, [date(f"d{i}", 2014, 2015, None) for i in range(13)], "AA").reference()


# ---- the evaluator's own listing and realisation against the module's --------------------------------------------

def parseable(name):
    return CAN_PARSE_CANDIDATES or not any(c.get("kind") == "candidates" for c in cmp.CASES[name]()[1])


@pytest.mark.parametrize("name", list(cmp.CASES))
def test_the_questions_listed_here_are_the_joint_checks(name):
    """Listed by this file's own code, they are the questions the brief describes: the conservative check's, unmerged."""
    inp, corrections, st = cmp.CASES[name]()
    ev = ex.Evaluator(inp, corrections, st)
    if not parseable(name):
        pytest.skip("this checkout's pass_c_expand has no candidates kind")
    jc = px.joint_check(inp, px.parse_corrections(corrections, inp), st)
    assert [(q["fid"], q["question"], q["settings"]) for q in jc["questions"]] == \
        [(q.fid, q.question, len(q.settings)) for q in ev.questions]


@pytest.mark.parametrize("name", ["two_of_four", "reopen", "date_and_capacity", "factor_cap_some", "permit_zero_some",
                                  "world_reopen"])
def test_the_realisation_is_the_brute_force_tests(name):
    """This file's realisation gives the matrices tests/test_pass_c_expand.py's _realize gives, configuration by configuration."""
    inp, corrections, st = cmp.CASES[name]()
    ev = ex.Evaluator(inp, corrections, st)
    corr = px.parse_corrections(corrections, inp)
    for cfg in ev.configurations():
        mine = ev.realise(cfg)
        theirs = _realize(inp, corr, st, cfg)
        for r in ("as_built", "no_anchoring"):
            assert np.array_equal(mine[r].values, theirs[r].values), (name, cfg, r)


@pytest.mark.parametrize("name", list(cmp.CASES))
def test_every_pivotal_question_is_one_the_joint_check_keeps(name, solved):
    """The joint check over-includes by design (D-63 rule 7): a pivotal question changes an outcome, which changes some
    threshold status, so the joint check must keep it. A check on both, not a definition of either."""
    if not parseable(name):
        pytest.skip("this checkout's pass_c_expand has no candidates kind")
    inp, corrections, st = cmp.CASES[name]()
    jc = px.joint_check(inp, px.parse_corrections(corrections, inp), st)
    ev, piv = solved[name]
    for k in ev.units:
        kept = {(q["fid"], q["question"]) for q in jc["utilities"][f"{k[0]}:{k[1]}"]["kept_questions"]}
        assert piv[k] <= kept, (name, k, piv[k] - kept)


# ---- each comparison case exercises what it claims ----------------------------------------------------------------

def factors(ev):
    """The state's factor in every configuration of the full product."""
    return {tuple(cfg[q.key] for q in ev.questions): ev.realise(cfg)["factor"] for cfg in ev.configurations()}


def ends_agree_everywhere(ev, key, k):
    """For every setting of the other questions, the question's first and last settings give utility k one outcome."""
    q = ev.by_key[key]
    others = [o for o in ev.questions if o.key != key]
    for combo in itertools.product(*(o.settings for o in others)):
        cfg = dict(zip((o.key for o in others), combo))
        a = ev.outcomes({**cfg, key: q.settings[0]})[k]
        b = ev.outcomes({**cfg, key: q.settings[-1]})[k]
        if a != b:
            return False
    return True


def test_case_interior_year_pivot(solved):
    ev, piv = solved["interior"]
    assert ("d", "date") in piv[(1, "AA")]
    assert ends_agree_everywhere(ev, ("d", "date"), (1, "AA"))                 # 2010 and 2016 both miss 2015 by 3 years
    o = {s: ev.outcomes(ev.normalise({("d", "date"): s}))[(1, "AA")] for s in (2010, 2013, 2016)}
    assert o[2010] == o[2016] == ("defined", "cohort", "cohort", False) and o[2013] == ("defined", "cohort", "cohort", True)
    assert piv[(2, "AA")] == {("e", "assignment")}


def test_case_factor_at_the_cap_in_every_setting(solved):
    ev, piv = solved["factor_cap_everywhere"]
    assert set(factors(ev).values()) == {px.SCALE_HI}
    assert "never" not in ev.by_key[("p", "date")].settings and 2025 in ev.by_key[("p", "date")].settings
    assert piv[(1, "BB")] == {("p", "date")} and piv[(2, "BB")] == set()   # one number: no question reaches 2 through it


def test_case_factor_at_the_floor_in_every_setting(solved):
    ev, piv = solved["factor_floor_everywhere"]
    assert set(factors(ev).values()) == {px.SCALE_LO}
    assert piv[(1, "DD")] == {("p", "date")} and piv[(2, "DD")] == set()
    # "never" is a setting and a pivot: never gives utility 1 no load (comparison), the convention 2021 0.8 MW scaled,
    # 0.53% of its base (neither).
    o = {s: ev.outcomes(ev.normalise({("p", "date"): s}))[(1, "DD")] for s in (2021, "never")}
    # With no anchoring the convention's 4 MW raw crosses utility 1's 3 MW threshold in 2023 (4/3, 8/3, 4): late.
    assert o[2021] == ("defined", "neither", "late", True) and o["never"] == ("defined", "comparison", "comparison", False)


def test_case_factor_reaching_the_cap_in_some_settings_only(solved):
    ev, piv = solved["factor_cap_some"]
    f = factors(ev)
    by_start = {combo[0]: v for combo, v in f.items()}
    assert by_start[2020] == pytest.approx(2.0) and by_start[2023] == pytest.approx(14 / (2 + 1 + 4 * 2 / 3))
    assert all(by_start[s] == px.SCALE_HI for s in (2024, 2025, "never"))
    # p is only ever on utility 1; its date reaches 2 and 3 through the factor alone (a start of 2023 or later).
    assert ev.by_key[("p", "date")].settings[-1] == "never"
    assert ("p", "date") in piv[(2, "EE")] and ("p", "date") in piv[(3, "EE")]
    for cfg in ev.configurations():
        m = ev.realise(cfg)
        assert m["factor"] in (pytest.approx(2.0), pytest.approx(14 / (2 + 1 + 4 * 2 / 3)), px.SCALE_HI)
    # The pivot for 2 is between starts on either side of 2023 (2022 vs 2024), with w held off utility 2.
    a = ev.outcomes(ev.normalise({("p", "date"): 2022, ("w", "assignment"): "off_panel"}))[(2, "EE")]
    b = ev.outcomes(ev.normalise({("p", "date"): 2024, ("w", "assignment"): "off_panel"}))[(2, "EE")]
    assert a != b


def test_case_permit_total_zero_in_some_settings(solved):
    ev, piv = solved["permit_zero_some"]
    by_start = {}
    for combo, v in factors(ev).items():
        by_start.setdefault(combo[0], set()).add(v)
    assert all(by_start[s] == {1.0} for s in (2025, 2026, "never"))               # permit total zero: the factor is 1
    # Otherwise (EPRI less the measured 1 MW) / p's 2024 load: 1 / 2 MW, 1 / (2 x 2/3), 1 / (2 x 1/3).
    for s, want in ((2020, 0.5), (2022, 0.5), (2023, 0.75), (2024, 1.5)):
        assert len(by_start[s]) == 1 and next(iter(by_start[s])) == pytest.approx(want), s
    assert ("p", "date") in piv[(2, "GG")] and ("p", "date") in piv[(4, "GG")]   # r's utilities, through the factor only
    assert piv[(3, "GG")] == set()                                                # a measured site's utility: not scaled


def test_case_permit_total_zero_in_every_setting_and_no_base(solved):
    ev, piv = solved["permit_zero_every_and_no_base"]
    assert set(factors(ev).values()) == {1.0}
    assert ev.inp.base[(3, "HH")] == 0.0 and math.isnan(ev.inp.base[(4, "HH")])
    for k in ((3, "HH"), (4, "HH")):
        assert piv[k] == {("p", "assignment"), ("p", "date")}
        for cfg in ev.configurations():
            assert ev.outcomes(cfg)[k][1] in ("neither", "comparison")              # never crosses with no positive base


def test_case_reopened_assignment(solved):
    ev, piv = solved["reopen"]
    assert ev.by_key[("v", "assignment")].settings == [1, 2, None]                  # stays on 1, among its candidates
    assert ev.by_key[("v2", "assignment")].settings == [3, 2, None]                 # entered on its first candidate
    assert ("v", "assignment") in piv[(1, "AA")] and ("v2", "assignment") not in piv[(1, "AA")]   # v2 is never on 1
    assert piv[(3, "AA")] == {("v2", "assignment")}


def test_case_date_and_capacity_split_with_rest_earliest_on_one_site(solved):
    ev, piv = solved["date_and_capacity"]
    assert ev.by_key[("s", "capacity")].settings == [2013, 2014, 2015, 2016]
    assert piv[(1, "AA")] == {("s", "assignment"), ("s", "date"), ("s", "capacity")}


def test_case_comparison_floor(solved):
    ev, piv = solved["comparison_floor"]
    assert ev.reference()[(11, "II")]["place"] == "comparison" and piv[(11, "II")] == {("x", "assignment")}
    assert ev.reference()[(12, "II")]["place"] == "comparison" and piv[(12, "II")] == set()
    seen = {ev.outcomes(cfg)[(11, "II")] for cfg in ev.configurations()}
    assert seen == {("defined", "comparison", "comparison", True),
                    ("defined", "comparison", "neither", False)}       # at the floor: only no anchoring fails


def test_case_undefined_reference(solved):
    ev, piv = solved["undefined"]
    assert ev.by_key[("d", "date")].defining and ev.by_key[("f", "date")].defining
    assert ev.reference()[(1, "JJ")]["defined"] is False
    assert ev.reference()[(2, "JJ")] == {"defined": True, "place": "early", "crossing": 2001.0}
    assert piv[(1, "JJ")] == {("d", "date"), ("g", "assignment")} and piv[(2, "JJ")] == set()


def test_case_provisional_reference(solved):
    ev, piv = solved["provisional"]
    assert ev.reference()[(1, "KK")]["defined"] is False                             # convention 2014, provisional
    assert ev.reference()[(2, "KK")]["defined"] is True
    assert ev.reference()[(3, "KK")] == {"defined": True, "place": "cohort", "crossing": 2016.0}
    assert not ev.by_key[("h", "date")].defining and piv[(3, "KK")] == set()


def test_case_assignment_with_several_candidates(solved):
    ev, piv = solved["several_candidates"]
    assert ev.by_key[("s", "assignment")].settings == [20, 21, 22, 23, 24, None]
    assert (23, "LL") not in set(ev.units)                                          # a candidate that is not a panel unit
    assert piv[(24, "LL")] == {("s", "assignment")} and ev.inp.base[(24, "LL")] == 0.0
    assert piv[(22, "LL")] == set() and ("s", "assignment") in piv[(21, "LL")]


def test_case_candidates_correction(solved):
    ev, piv = solved["candidates_kind"]
    assert ev.by_key[("c", "assignment")].settings == [30, 31, None]
    inp, _, st = cmp.case_candidates_kind()
    assert ex.Evaluator(inp, [], st).questions == []                                # resolved without the correction
    assert piv[(31, "MM")] == {("c", "assignment")}


def test_case_mixed(solved):
    ev, piv = solved["mixed"]
    assert len(set(factors(ev).values())) > 1
    assert ev.reference()[(3, "NN")]["defined"] is False
    assert {("s", "date"), ("s", "capacity"), ("p", "date")} <= piv[(3, "NN")]


def test_every_case_is_small_and_no_load_sits_at_a_threshold(solved):
    """At most a few thousand configurations; no load within one part in a million of 2% or of the 0.5% floor."""
    sizes = {}
    for name, (ev, _) in solved.items():
        n = ev.n_configurations()
        sizes[name] = n
        assert n <= 3000, name
        for cfg in ev.configurations():
            m = ev.realise(cfg)
            for k in ev.units:
                b = ev.base[k]
                if not (b > 0):
                    continue
                for reading in ("as_built", "no_anchoring"):
                    v = m[reading].loc[k].values.astype(float)
                    t = 0.02 * b
                    assert np.min(np.abs(v - t)) > 1e-6 * t, (name, k, reading, cfg)
                    if v.max() > 0:
                        assert abs(v.max() / b - ex.FLOOR) > 1e-6 * ex.FLOOR, (name, k, reading, cfg)
    assert sum(sizes.values()) < 5000


def test_every_case_has_no_divisor_range():
    """Brief section 2: a site with a no-anchoring divisor range would send its utility to the conservative result."""
    for name, build in cmp.CASES.items():
        if not parseable(name):
            continue
        inp, corrections, st = build()
        units = inp.units[inp.units.get_level_values("state") == st]
        sites, _, _ = px._sites(inp, px.parse_corrections(corrections, inp), st, units)
        assert all(s.na_div[0] == s.na_div[1] for s in sites), name


def test_the_witness_interface():
    """Settings keyed "<fid> <question>" with off_panel, years and never; an absent question is held at the reference."""
    ev = evaluator("permit_zero_some")
    cfg = ev.normalise({"p date": "never", "r assignment": "off_panel"})
    assert cfg == {("p", "date"): "never", ("r", "assignment"): None}
    assert ev.normalise({"p date": 2024}) == {("p", "date"): 2024, ("r", "assignment"): 2}
    with pytest.raises(ValueError):
        ev.normalise({"p date": 2030})
    with pytest.raises(KeyError):
        ev.normalise({"m date": 2020})


# ---- the one-year tolerance and the undefined outcome's no-anchoring components (added on review) -------------------

def differing_pairs(ev, key, k):
    """Every pair of configurations that differ only in `key` and give utility k different outcomes."""
    q = ev.by_key[key]
    others = [o for o in ev.questions if o.key != key]
    out = []
    for combo in itertools.product(*(o.settings for o in others)):
        base = dict(zip((o.key for o in others), combo))
        for a, b in itertools.combinations(q.settings, 2):
            ca, cb = {**base, key: a}, {**base, key: b}
            oa, ob = ev.outcomes(ca)[k], ev.outcomes(cb)[k]
            if oa != ob:
                out.append((ca, cb, oa, ob))
    return out


def crossings(ev, cfg, k):
    ab, na = ev.row(ev.realise(cfg), k)
    return ex.reading(ab, ev.base[k], ev.theta)["crossing"], ex.reading(na, ev.base[k], ev.theta)["crossing"]


def test_case_a_crossing_exactly_two_years_from_a_defined_reference_as_built(solved):
    ev, piv = solved["two_years_as_built"]
    k = (1, "PA")
    assert ev.reference()[k] == {"defined": True, "place": "cohort", "crossing": 2016.0}
    assert piv[k] == {("d", "date")}
    pairs = differing_pairs(ev, ("d", "date"), k)
    assert pairs
    for ca, cb, oa, ob in pairs:
        (a_ab, a_na), (b_ab, b_na) = crossings(ev, ca, k), crossings(ev, cb, k)
        assert a_ab == a_na and b_ab == b_na                                          # factor 1: the readings agree
        assert sorted([abs(a_ab - 2016), abs(b_ab - 2016)]) in ([0, 2], [1, 2])     # within a year against exactly two
        assert {oa, ob} == {("defined", "cohort", "cohort", True), ("defined", "cohort", "cohort", False)}
    # e moves utility 2's crossing by exactly one year inside the band (2015, 2016 against 2016): not pivotal.
    k2 = (2, "PA")
    assert ev.reference()[k2] == {"defined": True, "place": "cohort", "crossing": 2016.0}
    assert piv[k2] == set()
    seen = {crossings(ev, ev.normalise({("e", "date"): s}), k2)[0] for s in (2013, 2014)}
    assert seen == {2015.0, 2016.0}


def test_case_a_no_anchoring_crossing_exactly_two_years_from_a_defined_reference(solved):
    ev, piv = solved["two_years_no_anchoring"]
    k = (1, "PC")
    assert ev.reference()[k] == {"defined": True, "place": "cohort", "crossing": 2012.0}
    assert all(f == pytest.approx(2.0) for f in factors(ev).values())
    assert piv[k] == {("Q", "date")}
    c12, c13 = (crossings(ev, ev.normalise({("Q", "date"): s}), k) for s in (2012, 2013))
    assert c12 == (2012.0, 2013.0) and c13 == (2012.0, 2014.0)                       # as built unchanged; no anchoring 1 vs 2
    assert ev.outcomes(ev.normalise({("Q", "date"): 2012}))[k] == ("defined", "cohort", "cohort", True)
    assert ev.outcomes(ev.normalise({("Q", "date"): 2013}))[k] == ("defined", "cohort", "cohort", False)


def test_case_an_undefined_reference_and_a_question_that_moves_only_the_no_anchoring_crossing(solved):
    ev, piv = solved["undefined_no_anchoring_crossing"]
    k = (1, "PD")
    assert ev.reference()[k]["defined"] is False and ev.by_key[("U", "date")].defining
    assert not ev.by_key[("Q", "date")].defining
    assert ("Q", "date") in piv[k]
    pairs = differing_pairs(ev, ("Q", "date"), k)
    assert pairs
    for _, _, oa, ob in pairs:                    # ("undefined", as built, no anchoring, floor as built, floor no anchoring)
        assert [i for i in range(5) if oa[i] != ob[i]] == [2], (oa, ob)


def test_case_an_undefined_reference_and_a_question_that_moves_only_the_no_anchoring_floor_flag(solved):
    ev, piv = solved["undefined_no_anchoring_floor"]
    k = (1, "PE")
    assert ev.reference()[k]["defined"] is False and ev.by_key[("U", "date")].defining
    assert set(factors(ev).values()) == {px.SCALE_LO}
    assert ("Q", "date") in piv[k]
    pairs = differing_pairs(ev, ("Q", "date"), k)
    assert pairs
    for _, _, oa, ob in pairs:
        assert [i for i in range(5) if oa[i] != ob[i]] == [4], (oa, ob)
        assert oa[1] is None and oa[2] is None                                        # no crossing in either reading


# ---- every acceptance branch pinned by a case where it is the only difference (second review) ----------------------

def components(ev, cfg, k):
    """What the outcome is made of: the as-built place, both crossings and both under-the-floor flags."""
    ab, na = ev.row(ev.realise(cfg), k)
    a, n = ex.reading(ab, ev.base[k], ev.theta), ex.reading(na, ev.base[k], ev.theta)
    return {"place_ab": a["place"], "crossing_ab": a["crossing"], "crossing_na": n["crossing"],
            "under_ab": a["share"] < ex.FLOOR, "under_na": n["share"] < ex.FLOOR}


def only_difference(ev, ca, cb, k):
    x, y = components(ev, ca, k), components(ev, cb, k)
    return {c for c in x if x[c] != y[c]}, x, y


def test_case_the_as_built_tolerance_alone_with_a_factor_other_than_one(solved):
    ev, piv = solved["as_built_tolerance_alone"]
    k = (1, "QA")
    assert all(f == pytest.approx(0.5) for f in factors(ev).values())
    assert ev.reference()[k] == {"defined": True, "place": "cohort", "crossing": 2015.0}
    assert piv[k] == {("P", "date")}
    pairs = differing_pairs(ev, ("P", "date"), k)
    assert len(pairs) == 2                                                          # 2014 and 2015 each against 2016
    for ca, cb, _, _ in pairs:
        diff, x, y = only_difference(ev, ca, cb, k)
        assert diff == {"crossing_ab"}
        assert x["place_ab"] == y["place_ab"] == "cohort" and x["crossing_na"] == y["crossing_na"] == 2014.0
        assert sorted(abs(c["crossing_ab"] - 2015) for c in (x, y)) in ([0, 2], [1, 2])


def test_case_an_early_reference_and_the_no_anchoring_crossing_leaving_the_early_years(solved):
    ev, piv = solved["early_reference"]
    k = (1, "QB")
    assert all(f == pytest.approx(2.0) for f in factors(ev).values())
    assert ev.reference()[k] == {"defined": True, "place": "early", "crossing": 2007.0}
    assert piv[k] == {("Q1", "date")}
    pairs = differing_pairs(ev, ("Q1", "date"), k)
    assert pairs
    for ca, cb, oa, ob in pairs:
        diff, x, y = only_difference(ev, ca, cb, k)
        assert diff == {"crossing_na"} and x["place_ab"] == y["place_ab"] == "early"
        assert sorted(asg.group(c["crossing_na"]) for c in (x, y)) == ["cohort", "early"]
        assert {oa, ob} == {("defined", "early", "early", True), ("defined", "early", "cohort", False)}
    # The mirror: Q2 moves utility 2's no-anchoring crossing among early years (2008, 2009, 2010) and is not kept.
    k2 = (2, "QB")
    assert ev.reference()[k2] == {"defined": True, "place": "early", "crossing": 2007.0} and piv[k2] == set()
    seen = {components(ev, ev.normalise({("Q2", "date"): s}), k2)["crossing_na"] for s in (2007, 2008, 2009)}
    assert seen == {2008.0, 2009.0, 2010.0}


def test_case_comparison_reference_only_the_no_anchoring_share_crosses_the_floor(solved):
    ev, piv = solved["comparison_floor"]
    k = (11, "II")
    pairs = differing_pairs(ev, ("x", "assignment"), k)
    assert pairs
    for ca, cb, _, _ in pairs:
        diff, x, y = only_difference(ev, ca, cb, k)
        assert diff == {"under_na"} and x["place_ab"] == y["place_ab"] == "comparison"
    assert differing_pairs(ev, ("x", "date"), k) == [] and piv[k] == {("x", "assignment")}


def test_case_late_and_neither_references_ignore_the_no_anchoring_reading(solved):
    ev, piv = solved["late_and_neither_references"]
    assert ev.reference()[(3, "QC")] == {"defined": True, "place": "neither", "crossing": None}
    assert ev.reference()[(4, "QC")] == {"defined": True, "place": "late", "crossing": 2023.0}
    assert piv[(3, "QC")] == set() and piv[(4, "QC")] == set()
    for key, k, want in ((("Q3", "assignment"), (3, "QC"), {2011.0, 2012.0}),
                         (("Q4", "assignment"), (4, "QC"), {2021.0, 2022.0})):
        on = ev.normalise({key: k[0]})
        off = ev.normalise({key: "off_panel"})
        diff, x, y = only_difference(ev, on, off, k)
        assert diff == {"crossing_na"} and {x["crossing_na"], y["crossing_na"]} == want   # it moves; nothing else does
        assert x["place_ab"] == y["place_ab"] == ev.reference()[k]["place"]


@pytest.mark.parametrize("name,where", [("cohort_no_anchoring_to_early", ("QD", "early")),
                                        ("cohort_no_anchoring_to_none", ("QE", "never"))])
def test_case_cohort_reference_and_the_no_anchoring_crossing_leaving_the_cohort_years(solved, name, where):
    st, group = where
    ev, piv = solved[name]
    k = (1, st)
    assert ev.reference()[k] == {"defined": True, "place": "cohort", "crossing": 2012.0}
    assert piv[k] == {("Q", "assignment")}
    pairs = differing_pairs(ev, ("Q", "assignment"), k)
    assert pairs
    for ca, cb, _, _ in pairs:
        diff, x, y = only_difference(ev, ca, cb, k)
        assert diff == {"crossing_na"} and x["crossing_ab"] == y["crossing_ab"] == 2012.0
        assert sorted(asg.group(c["crossing_na"]) for c in (x, y)) == sorted(["cohort", group])


# ---- the reference repair (rule section 8.3 and 8.5): enumerated references and the triple -------------------------

REF_UNDEFINED_INSIDE = {"ref_own_site": [(1, "RA")], "ref_own_site_never": [(1, "RA")],
                        "ref_own_site_provisional": [(1, "RA")], "ref_factor_only": [(2, "RE")],
                        "ref_capacity_rest_earliest": [(1, "RF")], "ref_two_questions": [(1, "RG")]}


@pytest.mark.parametrize("name", sorted(REF_UNDEFINED_INSIDE))
def test_the_evaluators_reference_is_undefined_where_only_an_interior_setting_disagrees(name, solved):
    """The cases of tests/test_reference_enumerator.py (worked by hand there): at every combination of the defining
    questions' first and last settings the utility has one place and crossing, so the old reference() (the ends) called
    it defined; some interior setting gives another, so it is undefined now, and the question that moves it is pivotal."""
    ev, piv = solved[name]
    defining = [q for q in ev.questions if q.defining]
    assert defining
    for k in REF_UNDEFINED_INSIDE[name]:
        at_ends = set()
        for combo in itertools.product(*(q.ends for q in defining)):
            cfg = ev.normalise({q.key: v for q, v in zip(defining, combo)})
            c = components(ev, cfg, k)
            at_ends.add((c["place_ab"], c["crossing_ab"]))
        assert len(at_ends) == 1, (name, k, at_ends)
        assert ev.reference()[k] == {"defined": False, "place": None, "crossing": None}
        assert {q.key for q in defining} <= piv[k]


def test_the_held_factor_case_keeps_its_reference_and_drops_its_question(solved):
    # tests/test_reference_enumerator.py, case 4: the factor is 3.0 in every setting; as built utility 1 is cohort 2011
    # and utility 2 cohort 2012 at every start of d. With no anchoring: utility 1 carries r raw (0.67, 1.33, 2) plus d
    # raw (at most 1 MW): at most 3 MW < 3.5, never a crossing, 3 MW over the 0.875 MW floor: neither; so a cohort
    # reference is not accepted, (cohort, neither, False) at every start (d never: 2 MW, still neither). Utility 2:
    # q raw at most 1 MW < 2.5: neither with no anchoring, (cohort, neither, False) throughout. d is kept for neither.
    ev, piv = solved["ref_held_factor"]
    assert ev.reference()[(1, "RD")] == {"defined": True, "place": "cohort", "crossing": 2011.0}
    assert ev.reference()[(2, "RD")] == {"defined": True, "place": "cohort", "crossing": 2012.0}
    for s in (2021, 2024, "never"):
        o = ev.outcomes(ev.normalise({"d date": s}))
        assert o[(1, "RD")] == o[(2, "RD")] == ("defined", "cohort", "neither", False), s
    assert piv[(1, "RD")] == set() and piv[(2, "RD")] == set()


def test_a_question_only_the_no_anchoring_place_separates_is_kept_under_either_reading_only():
    # cmp.case_na_place_only: utility 1's reference is "neither" (P and Q as mapped: at most 2.9 MW as built). Q on 1:
    # no anchoring 1.33 + 1.8 = 3.13 >= 3 in 2010 (early); Q off 1: 1.33, 2.67, 4 -> 2012 (cohort). As built neither
    # either way, and a "neither" reference accepts anything with that place: the pair is (neither, True) both times.
    inp, corrections, st = cmp.case_na_place_only()
    k = (1, "QF")
    wide = ex.pivotal_questions(inp, corrections, st)
    narrow = ex.pivotal_questions(inp, corrections, st, criterion="as_built")
    assert wide["reference"][k] == narrow["reference"][k] == {"defined": True, "place": "neither", "crossing": None}
    assert wide["pivotal"][k] == {("Q", "assignment")} and narrow["pivotal"][k] == set()
    assert wide["pivotal"][(2, "QF")] == narrow["pivotal"][(2, "QF")] == set()    # 0.9 MW of a 1e6 GWh base
    ev = ex.Evaluator(inp, corrections, st)
    assert ev.outcomes(ev.normalise({"Q assignment": 1}))[k] == ("defined", "neither", "early", True)
    assert ev.outcomes(ev.normalise({"Q assignment": "off_panel"}))[k] == ("defined", "neither", "cohort", True)


def test_the_triple_widens_world_reopens_pivotal_set_for_utility_3():
    # world(), state AA, factor 0.5. Utility 3 (threshold 0.8 MW) carries p3 (2 MW raw from 2016) and, when the
    # reopened p1 is put on it, p1 (4 MW raw, start 2010 to 2014). With p1 on 3, as built p1 is 0.67, 1.33 from its start:
    # crossing start + 1, cohort for every start, more than a year from the reference's 2018: (cohort, not accepted)
    # for every start. With no anchoring p1 is 1.33 in its first year: crossing the start itself, early for 2010 and
    # cohort for 2011 to 2014. So p1's date changes the triple (early against cohort) and not the pair: kept for utility 3
    # under "either_reading" only. This is what rule section 5 allows: the widened criterion keeps at least as much.
    inp, corrections, st = cmp.case_world_reopen()
    wide = ex.pivotal_questions(inp, corrections, st)
    narrow = ex.pivotal_questions(inp, corrections, st, criterion="as_built")
    k = (3, "AA")
    assert wide["reference"][k] == {"defined": True, "place": "cohort", "crossing": 2018.0}
    assert narrow["pivotal"][k] == {("p1", "assignment")}
    assert wide["pivotal"][k] == {("p1", "assignment"), ("p1", "date")}
    ev = ex.Evaluator(inp, corrections, st)
    on3 = {s: ev.outcomes(ev.normalise({"p1 assignment": 3, "p1 date": s}))[k] for s in (2010, 2011)}
    assert on3 == {2010: ("defined", "cohort", "early", False), 2011: ("defined", "cohort", "cohort", False)}
    for name in cmp.CASES:                                     # and nowhere does the triple keep less than the pair
        if name in ("mixed",):
            continue                                           # 648 configurations twice; covered by the comparison file
        inp, corrections, st = cmp.CASES[name]()
        w = ex.pivotal_questions(inp, corrections, st)["pivotal"]
        n = ex.pivotal_questions(inp, corrections, st, criterion="as_built")["pivotal"]
        assert all(n[u] <= w[u] for u in n), name
