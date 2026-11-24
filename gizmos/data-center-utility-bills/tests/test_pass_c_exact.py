"""The exact attribution of the verification pass (docs/gate1/exact-attribution-brief-2026-11-16.md; D-65 item 4, D-66 section 4).

Load and sales only; no price is read. Every test works on a small made-up inventory built with `world()` and `mini()`
from tests/test_pass_c_expand.py, so none depends on the real one.

Three checks run on every result here, whatever the case:
  * every witness pair differs in exactly the named question, and its two outcomes differ; each side, realised through
    the scratch rebuild (`pass_c_expand.scratch_state`) and `assignment.evaluate`, gives the outcome reported, computed
    by this file's own code from the two matrices;
  * the kept set of every utility attributed exactly is a subset of the conservative joint check's kept set;
  * on the smaller cases, a brute force over EVERY configuration of every question in the state (no merging, no
    relevance, no ceiling), realised the same way, finds exactly the kept set.

The reference repair (docs/gate1/reference-repair-rule-2026-11-18.md, D-72 item 4): the brute force here decides a
reference by realising EVERY setting of every reference-defining question (rule R2), not the two ends, and the outcome
with a defined reference is rule R7's triple (place as built, place with no anchoring, accepted), or with
criterion="as_built" D-66 4.1's pair.
"""
import dataclasses
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_exact as pe  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import (GWH, anchoring_world, capacity_world, corners_world, date, interior_world,  # noqa: E402
                               mini, split, world)

YEARS = asg.YEARS
FLOOR = asg.CLEAN_BELOW
THETA = 0.02


# ---- this file's own realisation and outcome ----------------------------------------------------------------------

def _settings_of(inp, corr, st):
    """Every question of the state and its settings, as the conservative check lists them (via _sites)."""
    units = inp.units[inp.units.get_level_values("state") == st]
    sites, _, _ = px._sites(inp, corr, st, units)
    return {(s.fid, q): list(s.values[i]) for s in sites for i, q in enumerate(s.questions)}


def realise(inp, corr, st, config):
    """One configuration through scratch_state and assignment.evaluate. `config` maps (fid, question) to a value; a
    date or capacity question left out takes its convention, or its first setting where it has none; an assignment
    question left out stays as mapped."""
    corr = dict(corr)
    choice = {}
    for (fid, q), v in config.items():
        if q == "assignment":
            to = px.OFF if v in (None, "off_panel") else (int(v), st)
            c = corr.get(fid) or px.Correction(fid=fid, state=st, inventory_year=inp.fac.energized_year[fid])
            corr[fid] = dataclasses.replace(c, assign=to, reopen=None, narrow=None, widen=None)
        else:
            choice[(fid, q)] = v
    for fid, c in corr.items():
        if c.state != st:
            continue
        for q in c.questions():
            if (fid, q) not in choice and c.convention(q) is None:
                choice[(fid, q)] = (px._date_values(c) if q == "date" else px._capacity_values(c))[0]
    fac, fy, _ = px.scratch_state(inp, corr, st, choice)
    u = inp.units[inp.units.get_level_values("state") == st]
    _, m, _ = asg.evaluate(fac, fy, u, inp.base.reindex(u), inp.regions.reindex(u), thresholds=(THETA,))
    return m


def _cross(v, base):
    if not (pd.notna(base) and base > 0):
        return None
    return next((y for y, x in zip(YEARS, v) if x >= THETA * base), None)


def _under(v, base):
    top = max(v)
    if top <= 0:
        return True
    return bool(pd.notna(base) and base > 0 and top / base < FLOOR)


def _place(c, under):
    g = asg.group(c)
    return g if g != "never" else ("comparison" if under else "neither")


def outcome(m, k, base, ref, criterion="either_reading"):
    """The brief's section 3, written here independently: ref is None or (place, crossing year or None). With a defined
    reference, rule R7's triple (criterion "either_reading") or D-66 4.1's pair (criterion "as_built")."""
    ab, na = list(m["as_built"].loc[k].values), list(m["no_anchoring"].loc[k].values)
    cab, cna, uab, una = _cross(ab, base), _cross(na, base), _under(ab, base), _under(na, base)
    if ref is None:
        return {"crossing_as_built": "never" if cab is None else str(cab),
                "crossing_no_anchoring": "never" if cna is None else str(cna),
                "under_floor_as_built": uab, "under_floor_no_anchoring": una}
    p = _place(cab, uab)
    acc = p == ref[0]
    if acc and ref[0] == "cohort":
        acc = asg.same_place(ref[1], np.nan if cab is None else cab) and asg.same_place(ref[1], np.nan if cna is None else cna)
    elif acc and ref[0] == "early":
        acc = asg.group(cna) == "early"
    elif acc and ref[0] == "comparison":
        acc = una
    if criterion == "as_built":
        return {"place": p, "accepted": bool(acc)}
    return {"place": p, "place_no_anchoring": _place(cna, una), "accepted": bool(acc)}


def _ref_of(u):
    r = u["reference"]
    if not r["defined"]:
        return None
    return (r["place"], None if r["crossing"] == "never" else int(r["crossing"]))


def check(inp, corrections, st, res=None, realise_witnesses=True, ceiling=pe.CEILING, criterion="either_reading"):
    """The checks every result gets. Returns the result."""
    corr = px.parse_corrections(corrections, inp)
    res = res or pe.exact_attribution(inp, corr, st, ceiling=ceiling, criterion=criterion)
    criterion = res["criterion"]
    json.dumps(res)                                                                   # survives json.dumps
    jc = px.joint_check(inp, corr, st)
    for key, u in res["utilities"].items():
        cons = {(q["fid"], q["question"]) for q in jc["utilities"][key]["kept_questions"]}
        mine = {(q["fid"], q["question"]) for q in u["kept_questions"]}
        if u["method"] == "conservative":
            assert u["kept_questions"] == jc["utilities"][key]["kept_questions"], key   # unchanged
            assert not u["complete"]
            continue
        assert mine <= cons, (key, mine - cons)                                       # the conservative check drops nothing decisive
        assert u["complete"]
        assert u["joins"] == sorted({f for f, _ in mine})
        uid, s2 = key.split(":")
        k = (int(uid), s2)
        for q in u["kept_questions"]:
            w = q["witness"]
            name = f"{q['fid']} {q['question']}"
            assert set(w["a"]["settings"]) == set(w["b"]["settings"])
            assert [x for x in w["a"]["settings"] if w["a"]["settings"][x] != w["b"]["settings"][x]] == [name]
            assert w["a"]["outcome"] != w["b"]["outcome"]
            if realise_witnesses:
                for side in ("a", "b"):
                    cfg = {tuple(x.rsplit(" ", 1)): v for x, v in w[side]["settings"].items()}
                    got = outcome(realise(inp, corr, st, cfg), k, inp.base[k], _ref_of(u), criterion)
                    assert got == w[side]["outcome"], (key, name, side, got, w[side]["outcome"])
    return res


def brute_force(inp, corrections, st, criterion="either_reading"):
    """Every configuration of every question of the state, realised one at a time; the pivotal set per utility.

    The reference (rule R2): every setting of every reference-defining question, in every combination, everything else
    at its convention or as mapped; defined only if the place and crossing as built are the same in all of them."""
    corr = px.parse_corrections(corrections, inp)
    space = _settings_of(inp, corr, st)
    qs = list(space)
    u = inp.units[inp.units.get_level_values("state") == st]
    defining = [(f, q) for (f, q) in qs if q != "assignment"
                and (corr[f].convention(q) is None or (q == "date" and corr[f].date.get("convention_is") == "provisional"))]
    refs = {}
    for combo in itertools.product(*[space[q] for q in defining]):
        m = realise(inp, corr, st, dict(zip(defining, combo)))
        for k in u:
            ab = list(m["as_built"].loc[k].values)
            c = _cross(ab, inp.base[k])
            refs.setdefault(k, set()).add((_place(c, _under(ab, inp.base[k])), c))
    ref = {k: (next(iter(v)) if len(v) == 1 else None) for k, v in refs.items()}
    out = {}
    for combo in itertools.product(*[space[q] for q in qs]):
        m = realise(inp, corr, st, dict(zip(qs, combo)))
        for k in u:
            out.setdefault(k, {})[combo] = json.dumps(outcome(m, k, inp.base[k], ref[k], criterion), sort_keys=True)
    pivotal = {}
    for k in u:
        piv = set()
        for i, q in enumerate(qs):
            groups = {}
            for combo, o in out[k].items():
                groups.setdefault(combo[:i] + combo[i + 1:], set()).add(o)
            if any(len(g) > 1 for g in groups.values()):
                piv.add(q)
        pivotal[f"{k[0]}:{k[1]}"] = piv
    return pivotal, ref, int(np.prod([len(space[q]) for q in qs]))


def agrees_with_brute_force(inp, corrections, st, res):
    pivotal, ref, _ = brute_force(inp, corrections, st, res["criterion"])
    for key, u in res["utilities"].items():
        assert u["method"] == "exact", key
        assert {(q["fid"], q["question"]) for q in u["kept_questions"]} == pivotal[key], key
        k = (int(key.split(":")[0]), key.split(":")[1])
        assert _ref_of(u) == (None if ref[k] is None else (ref[k][0], ref[k][1])), key


def kept(res, uid, st):
    return {(q["fid"], q["question"]) for q in res["utilities"][f"{uid}:{st}"]["kept_questions"]}


def rel(res, uid, st):
    return {(q["fid"], q["question"]): q["settings"] for q in res["utilities"][f"{uid}:{st}"]["relevant_questions"]}


# ---- the cases of brief section 6 ----------------------------------------------------------------------------------

def four_world(base6=1e6):
    sites = [{"fid": f"a{i}", "st": "CC", "u": 5, "cands": "5;6", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}
             for i in range(1, 5)]
    return mini(sites, {(5, "CC"): 1.5 * GWH / 0.02, (6, "CC"): base6})


def test_two_of_four_equal_sites_are_all_kept_each_with_a_witness():
    inp = four_world()
    res = check(inp, [], "CC")
    five = res["utilities"]["5:CC"]
    assert five["method"] == "exact" and five["complete"] and five["configurations"] == 16    # on 5, or not: 2 x 2 x 2 x 2
    assert five["reference"]["defined"] and five["reference"]["place"] == "cohort" and five["reference"]["crossing"] == "2011"
    assert kept(res, 5, "CC") == {(f"a{i}", "assignment") for i in range(1, 5)}
    assert all("witness" in q for q in five["kept_questions"])
    assert five["joins"] == ["a1", "a2", "a3", "a4"]
    six = res["utilities"]["6:CC"]
    assert six["configurations"] == 16 and kept(res, 6, "CC") == set()                    # 4 MW is never 0.5% of utility 6
    agrees_with_brute_force(inp, [], "CC", res)


def cohort_world(earliest):
    # Utility 60's 2% threshold is 2.5 MW; x is 3 MW raw from its start, factor 1: it crosses two years after it starts.
    inp = mini([{"fid": "x", "st": "KK", "u": 60, "raw": 3.0, "year": 2015}], {(60, "KK"): 2.5 * GWH / 0.02})
    return inp, [date("x", earliest, 2015, 2015)]


def test_a_crossing_that_moves_by_one_cohort_year_is_not_kept_and_by_two_is():
    inp, c = cohort_world(2014)
    res = check(inp, c, "KK")
    u = res["utilities"]["60:KK"]
    assert u["reference"]["crossing"] == "2017" and rel(res, 60, "KK") == {("x", "date"): 2}
    assert kept(res, 60, "KK") == set()                                                    # 2016 against 2017: within one year
    assert px.joint_check(inp, px.parse_corrections(c, inp), "KK")["utilities"]["60:KK"]["kept_questions"]   # the conservative one keeps it
    agrees_with_brute_force(inp, c, "KK", res)
    inp, c = cohort_world(2013)
    res = check(inp, c, "KK")
    assert kept(res, 60, "KK") == {("x", "date")}                                          # 2015 against 2017: two years
    w = res["utilities"]["60:KK"]["kept_questions"][0]["witness"]
    assert {w["a"]["settings"]["x date"], w["b"]["settings"]["x date"]} == {2013, 2014}
    agrees_with_brute_force(inp, c, "KK", res)


def test_a_date_reaches_another_utility_only_through_the_factor():
    inp = anchoring_world()
    c = [date("q1", 2016, 2024, 2016)]
    res = check(inp, c, "DD")
    assert res["factor_can_move"]
    eight = res["utilities"]["8:DD"]
    assert eight["reference"]["defined"] and eight["reference"]["place"] == "neither"        # factor 0.5: s8 at 2 MW of 2.5
    assert kept(res, 8, "DD") == {("q1", "date")}
    w = eight["kept_questions"][0]["witness"]
    assert set(w["a"]["settings"]) == {"q1 date"}                                         # q1 is never on 8
    assert rel(res, 9, "DD") == {} and res["utilities"]["9:DD"]["configurations"] == 1      # measured only: the factor does not matter
    assert ("q1", "date") in kept(res, 7, "DD")
    agrees_with_brute_force(inp, c, "DD", res)


def test_a_comparison_utility_that_can_reach_the_floor_keeps_the_question_and_one_that_cannot_does_not():
    sites = [{"fid": "x", "st": "EE", "u": 10, "cands": "10;11;12", "assign": "smallest_polygon", "raw": 2.0, "year": 2010}]
    inp = mini(sites, {(10, "EE"): 1e3, (11, "EE"): 2 * GWH / 0.01, (12, "EE"): 1e6})    # x is 1% of 11, 0.002% of 12
    res = check(inp, [], "EE")
    eleven, twelve = res["utilities"]["11:EE"], res["utilities"]["12:EE"]
    assert eleven["reference"]["place"] == "comparison" and kept(res, 11, "EE") == {("x", "assignment")}
    assert twelve["reference"]["place"] == "comparison" and kept(res, 12, "EE") == set()
    assert rel(res, 12, "EE") == {("x", "assignment"): 2} and twelve["configurations"] == 2   # relevant, and not kept
    agrees_with_brute_force(inp, [], "EE", res)


def test_an_undefined_reference_keeps_its_question_and_names_it():
    inp = world()
    c = [date("p3", 2010, 2016, None)]                                                     # utility 3 crosses in 2012 or in 2018
    res = check(inp, c, "AA")
    three = res["utilities"]["3:AA"]
    r = three["reference"]
    assert not r["defined"] and r["place"] is None and r["crossing"] is None
    assert r["undefined_by"] == [{"fid": "p3", "question": "date"}] and r["why_undefined"]
    assert kept(res, 3, "AA") == {("p3", "date")}
    w = three["kept_questions"][0]["witness"]
    assert set(w["a"]["outcome"]) == {"crossing_as_built", "crossing_no_anchoring", "under_floor_as_built",
                                      "under_floor_no_anchoring"}
    one = res["utilities"]["1:AA"]                                                          # p3 does not reach 1: defined
    assert one["reference"]["defined"]
    agrees_with_brute_force(inp, c, "AA", res)


def test_reference_combinations_over_the_ceiling_leave_the_reference_undefined_without_the_search():
    # Rule R4 (D-72 item 4) replaced the limit of twelve questions: the reference is undefined without the search only
    # when the combinations of class representatives of the relevant reference-defining questions exceed the ceiling.
    inp = world()
    c = [date("p3", 2016, 2018, None)]
    assert check(inp, c, "AA")["utilities"]["3:AA"]["reference"]["defined"] is False      # 2018 or 2020: both cohort, two apart
    c = [date("p3", 2016, 2016, None)]                                                     # one setting: not relevant, defined
    r = check(inp, c, "AA")["utilities"]["3:AA"]["reference"]
    assert r["defined"] and r["searched"] and r["settings_enumerated"] == 1
    res = check(inp, [date("p3", 2016, 2017, None)], "AA", ceiling=1)
    u = res["utilities"]["3:AA"]
    r = u["reference"]
    assert u["method"] == "conservative" and u["configurations"] == 2
    assert not r["defined"] and r["searched"] is False and r["settings_enumerated"] == 2 and r["pair"] is None
    assert "not searched" in r["why_undefined"] and "over the ceiling of 1" in r["why_undefined"]
    assert r["undefined_by"] == [{"fid": "p3", "question": "date"}]
    assert not hasattr(pe, "REFERENCE_QUESTION_LIMIT")


def test_a_provisional_convention_makes_a_reference_that_turns_on_it_undefined():
    inp = world()
    plain = check(inp, [date("p3", 2010, 2016, 2016)], "AA")["utilities"]["3:AA"]
    assert plain["reference"]["defined"] and plain["reference"]["crossing"] == "2018"
    c = [dict(date("p3", 2010, 2016, 2016), convention_is="provisional")]
    res = check(inp, c, "AA")
    r = res["utilities"]["3:AA"]["reference"]
    assert not r["defined"] and r["undefined_by"] == [{"fid": "p3", "question": "date"}]
    assert kept(res, 3, "AA") == {("p3", "date")}
    assert res["utilities"]["1:AA"]["reference"]["defined"]                                 # not relevant to 1
    agrees_with_brute_force(inp, c, "AA", res)
    # A provisional question whose two ends give the same place and crossing as built leaves the reference defined.
    inp, c = cohort_world(2014)
    c = [dict(c[0], convention_is="provisional")]
    r = check(inp, c, "KK")["utilities"]["60:KK"]["reference"]
    assert not r["defined"]                                                                # 2016 and 2017: not identical
    inp = four_world()
    c = [dict(date("a1", 2008, 2009, 2009), convention_is="provisional")]                  # full by 2011 either way, 4 sites
    r = check(inp, c, "CC")["utilities"]["5:CC"]["reference"]
    assert r["defined"]


def test_a_count_over_the_ceiling_falls_back_to_the_conservative_result_unchanged():
    inp = four_world()
    res = check(inp, [], "CC", ceiling=10)
    jc = px.joint_check(inp, {}, "CC")
    for key in ("5:CC", "6:CC"):
        u = res["utilities"][key]
        assert u["method"] == "conservative" and u["configurations"] == 16 and not u["complete"]
        assert u["kept_questions"] == jc["utilities"][key]["kept_questions"]
        assert u["joins"] == jc["utilities"][key]["joins"] and "100,000" not in u["why_conservative"]
        assert "16" in u["why_conservative"] and "10" in u["why_conservative"]
    assert all("channel" in q and "witness" not in q for q in res["utilities"]["5:CC"]["kept_questions"])
    assert pe.exact_attribution(inp, {}, "CC", ceiling=16)["utilities"]["5:CC"]["method"] == "exact"   # at the ceiling: exact


def test_settings_are_merged_per_utility():
    sites = [{"fid": "y", "st": "LL", "u": 20, "cands": "20;21;22;23;24", "assign": "smallest_polygon", "raw": 2.0, "year": 2010}]
    inp = mini(sites, {(u, "LL"): 1e3 for u in range(20, 25)})
    res = check(inp, [], "LL")
    assert {"fid": "y", "question": "assignment", "settings": 6} in res["questions"]        # unmerged: five utilities and off
    for u in range(20, 25):
        assert rel(res, u, "LL") == {("y", "assignment"): 2} and res["utilities"][f"{u}:LL"]["configurations"] == 2
        assert kept(res, u, "LL") == {("y", "assignment")}                                   # 1.75%: neither, or comparison
    m = res["utilities"]["22:LL"]["relevant_questions"][0]["merged_settings"]
    assert sorted(map(sorted, ([str(v) for v in g] for g in m))) == [["20", "21", "23", "24", "off_panel"], ["22"]]
    agrees_with_brute_force(inp, [], "LL", res)


def test_every_witness_differs_in_exactly_its_question_on_a_state_with_everything():
    # World AA with p2's assignment, a factor-moving date on p3, and a capacity split dated by the date question.
    inp = world()
    c = [date("p3", 2013, 2024, 2016), split("p3", None, 0.5, rest_earliest=2014)]
    res = check(inp, c, "AA")
    assert res["factor_can_move"]
    n = sum(len(u["kept_questions"]) for u in res["utilities"].values())
    assert n >= 3
    agrees_with_brute_force(inp, c, "AA", res)


# ---- further cases: the brute force over the full product ----------------------------------------------------------

def test_brute_force_the_factor_moves_and_never():
    inp = world()
    c = [date("p3", 2016, 2024, 2016, never=True)]
    res = check(inp, c, "AA")
    agrees_with_brute_force(inp, c, "AA", res)


def test_brute_force_a_reopened_site_with_a_date():
    inp = world()
    c = [{"fid": "p1", "kind": "reopen", "candidates": [1, 3]}, date("p1", 2010, 2014, 2012)]
    res = check(inp, c, "AA")
    assert {"fid": "p1", "question": "assignment", "settings": 3} in res["questions"]
    agrees_with_brute_force(inp, c, "AA", res)


def test_brute_force_a_measured_site_whose_date_moves_the_factor():
    inp = world()
    c = [{"fid": "p3", "kind": "size", "mw_full": 2.0, "measured": True}, date("p3", 2020, 2024, 2020)]
    res = check(inp, c, "AA")
    agrees_with_brute_force(inp, c, "AA", res)


def test_brute_force_two_of_four_on_two_utilities():
    sites = [{"fid": f"a{i}", "st": "CC", "u": 5, "cands": "5;6", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}
             for i in range(1, 5)]
    inp = mini(sites, {(5, "CC"): 1.5 * GWH / 0.02, (6, "CC"): 1.5 * GWH / 0.02})
    res = check(inp, [], "CC")
    assert kept(res, 5, "CC") == kept(res, 6, "CC") == {(f"a{i}", "assignment") for i in range(1, 5)}
    assert res["utilities"]["5:CC"]["configurations"] == 16                                # on 5, or on 6 or off (merged for 5)
    agrees_with_brute_force(inp, [], "CC", res)


def test_the_factor_at_its_cap_closes_its_channel_and_reaching_the_cap_in_some_settings_opens_it():
    sites = [{"fid": "q", "st": "FF", "u": 40, "raw": 3.0, "year": 2016},
             {"fid": "s", "st": "FF", "u": 41, "raw": 3.0, "year": 2010}]
    base = {(40, "FF"): 1e3, (41, "FF"): 7.5 * GWH / 0.02}                                 # 41 crosses at 7.5 MW scaled
    c = [date("q", 2016, 2024, 2016)]
    held = mini(sites, base, {"FF": 1.0})                                                  # factor 3.0 in every setting
    res = check(held, c, "FF")
    assert not res["factor_can_move"] and rel(res, 41, "FF") == {}
    agrees_with_brute_force(held, c, "FF", res)
    some = mini(sites, base, {"FF": 14 * GWH / 1000})                                      # 2.33, 2.8, 3.0 (held)
    res = check(some, c, "FF")
    assert res["factor_can_move"] and ("q", "date") in rel(res, 41, "FF")
    assert kept(res, 41, "FF") == {("q", "date")}                                          # 3 x 2.33 = 7 MW under 7.5; 3 x 2.8 = 8.4 over
    agrees_with_brute_force(some, c, "FF", res)


def test_a_permit_total_that_can_be_zero():
    sites = [{"fid": "only", "st": "JJ", "u": 50, "raw": 2.0, "year": 2015},
             {"fid": "m", "st": "JJ", "u": 51, "raw": 3.0, "year": 2010, "basis": "verified_public_figure"}]
    inp = mini(sites, {(50, "JJ"): 1e3, (51, "JJ"): 1e3}, {"JJ": 1.0})
    c = [date("only", 2015, None, 2015, never=True)]
    res = check(inp, c, "JJ")
    assert kept(res, 50, "JJ") == {("only", "date")} and rel(res, 51, "JJ") == {}
    agrees_with_brute_force(inp, c, "JJ", res)


def test_a_utility_with_a_zero_base():
    sites = [{"fid": "z", "st": "MM", "u": 70, "cands": "70;71", "assign": "smallest_polygon", "raw": 1.0, "year": 2012}]
    inp = mini(sites, {(70, "MM"): 1e3, (71, "MM"): 0.0})
    res = check(inp, [], "MM")
    u = res["utilities"]["71:MM"]
    assert u["reference"]["place"] == "comparison" and kept(res, 71, "MM") == {("z", "assignment")}   # any load: over the floor
    agrees_with_brute_force(inp, [], "MM", res)


def test_a_measured_site_with_an_uncertain_divisor_sends_the_utility_to_the_conservative_rule():
    sites = [{"fid": "m", "st": "NN", "u": 80, "raw": 3.0, "year": 2010, "basis": "verified_public_figure"},
             {"fid": "p", "st": "NN", "u": 80, "cands": "80;81", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(80, "NN"): 1e3, (81, "NN"): 1e3})
    inp.fac.loc["m", "state_scale"] = 0.8                                                  # a measured row carrying a scale
    res = check(inp, [], "NN")
    u = res["utilities"]["80:NN"]
    assert u["method"] == "conservative" and "divisor" in u["why_conservative"] and "m" in u["why_conservative"]
    assert res["utilities"]["81:NN"]["method"] == "exact"


def test_a_utility_with_no_relevant_question_is_exact_and_complete_and_keeps_nothing():
    inp = world()
    res = check(inp, [], "BB")
    u = res["utilities"]["4:BB"]
    assert u["method"] == "exact" and u["complete"] and u["configurations"] == 1 and u["kept_questions"] == []
    assert u["relevant_questions"] == []


# ---- the driver ------------------------------------------------------------------------------------------------------

def test_the_hosts_are_read_from_the_headline_set():
    head = pd.DataFrame({"threshold": ["2%", "2%", "2%", "5%", "2%"], "utility_id_eia": [1, 2, 3, 4, 5],
                         "state": ["AA", "AA", "BB", "CC", "DD"], "in_headline_set": [True, False, False, True, False],
                         "why_not_in_the_headline_set": [None, "D-46, ruling 4: lower as built: x", "D-20 something",
                                                         None, "D-46, ruling 4: a; D-46, ruling 4: b"]})
    assert pe.hosts_from_headline(head) == [(1, "AA"), (2, "AA"), (5, "DD")]


OLD_CSV_COLUMNS = ["utility", "utility_name", "one_of_the_26_hosts", "method", "configurations", "complete",
                   "reference_defined", "reference_place", "reference_crossing", "site", "question", "site_state",
                   "site_is_on", "operator", "county", "mw_full", "already_on_the_target_list", "witness"]


def test_the_driver_writes_json_and_csv_and_a_summary(tmp_path):
    inp = world()
    corrections = [date("p3", 2010, 2016, None)]
    targets = tmp_path / "targets.csv"
    pd.DataFrame({"site": ["p3"]}).to_csv(targets, index=False)
    out = pe.run(corrections, inp, targets=targets, states=["AA", "BB"], hosts=[(1, "AA"), (3, "AA")], realise_witnesses=True)
    assert set(out["json"]["exact"]) == {"AA", "BB"} and out["json"]["hosts"][0]["utility"] == "1:AA"
    c = out["json"]["counts"]
    assert c["kept_not_in_the_conservative_set"] == 0 and c["witnesses_failing"] == 0
    assert c["witness_sides_realised"] == 2 * c["witnesses_checked"] > 0 and c["witness_sides_realised_differing"] == 0
    assert c["utilities"]["exact"] == 4 and c["utilities"]["conservative"] == 0
    rows = out["csv"]
    assert rows and list(rows[0]) == pe.CSV_COLUMNS
    p3 = [r for r in rows if r["site"] == "p3"]
    assert p3 and all(r["already_on_the_target_list"] for r in p3) and json.loads(p3[0]["witness"])["a"]["settings"]
    assert "counts" in out["summary"] and "1:AA" in out["summary"]
    # The reference repair: the new fields reach the JSON, the CSV (appended after the old columns) and the summary.
    assert pe.CSV_COLUMNS[:18] == OLD_CSV_COLUMNS
    assert pe.CSV_COLUMNS[18:22] == ["reference_settings_enumerated", "reference_searched", "reference_why_undefined", "criterion"]
    # D-90: one more column, last, for the place test's reference where the reference in the file is undefined.
    assert pe.CSV_COLUMNS[22:] == ["place_test_reference_note"]
    assert all(r["criterion"] == "either_reading" for r in rows)
    assert p3[0]["reference_searched"] is True and p3[0]["reference_settings_enumerated"] >= 1
    assert out["json"]["criterion"] == "either_reading" and out["json"]["exact"]["AA"]["criterion"] == "either_reading"
    assert "criterion: either_reading" in out["summary"] and "not searched" in out["summary"]
    assert "settings enumerated" in out["summary"]
    json.dumps(out["json"], default=str)
    with pytest.raises(ValueError, match="outside data/"):
        pe.main(["x.json", "--out", str(ROOT / "data" / "frozen" / "x.json")])


def test_a_comparison_reference_needs_the_no_anchoring_share_under_the_floor_too():
    # Factor 0.5. w (1 MW raw) on utility 92 is 0.4% of its sales as built and 0.8% with no anchoring: its place is still
    # "comparison", but it is not accepted against 92's comparison reference.
    sites = [{"fid": "big", "st": "PP", "u": 90, "raw": 10.0, "year": 2010},
             {"fid": "w", "st": "PP", "u": 91, "cands": "91;92", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(90, "PP"): 1e3, (91, "PP"): 1e3, (92, "PP"): GWH / 0.008}, {"PP": 0.5 * 11 * GWH / 1000})
    assert inp.frozen_factor("PP") == pytest.approx(0.5)
    res = check(inp, [], "PP")
    u = res["utilities"]["92:PP"]
    assert u["reference"]["place"] == "comparison" and kept(res, 92, "PP") == {("w", "assignment")}
    w = u["kept_questions"][0]["witness"]
    assert {w["a"]["outcome"]["place"], w["b"]["outcome"]["place"]} == {"comparison"}
    assert {w["a"]["outcome"]["accepted"], w["b"]["outcome"]["accepted"]} == {True, False}
    agrees_with_brute_force(inp, [], "PP", res)


def test_the_no_anchoring_crossing_is_measured_against_the_reference_crossing_as_built():
    # Factor 0.5: x (3 MW raw) on 61 crosses as built two years after its start (2017 at the convention) and with no
    # anchoring one year after it (2016). A start one year earlier puts the no-anchoring crossing at 2015, two years
    # before the reference's 2017: not accepted, so the question is kept, although each reading moved by one year only.
    sites = [{"fid": "x", "st": "QQ", "u": 61, "raw": 3.0, "year": 2015},
             {"fid": "big", "st": "QQ", "u": 62, "raw": 7.0, "year": 2005}]
    inp = mini(sites, {(61, "QQ"): 1.25 * GWH / 0.02, (62, "QQ"): 1e3}, {"QQ": 0.5 * 10 * GWH / 1000})
    c = [date("x", 2014, 2015, 2015)]
    res = check(inp, c, "QQ")
    u = res["utilities"]["61:QQ"]
    assert u["reference"]["crossing"] == "2017" and kept(res, 61, "QQ") == {("x", "date")}
    d = {w["detail"]["crossing_no_anchoring"] for w in u["kept_questions"][0]["witness"].values()}
    assert d == {"2015", "2016"}
    agrees_with_brute_force(inp, c, "QQ", res)


def test_the_vectorised_factor_is_pass_c_expands_and_snaps_to_the_frozen_one():
    inp = world()
    S = pe._State(inp, {}, "AA")
    P = np.array([0.0, 1e-9, 0.01, 0.05, 0.07008, 0.07008 * (1 + 1e-14), 0.2, 5.0])
    for M in (0.0, 0.01, 0.03504, 1.0):
        got = S.factor(np.full(P.shape, M), P)
        want = [px._factor(S.epri, M, p) for p in P]
        want = [S.frozen if abs(w - S.frozen) <= px.FACTOR_TOL * max(1.0, abs(S.frozen)) else w for w in want]
        assert list(got) == want
    assert S.factor(np.array([0.0]), np.array([0.07008 * (1 + 1e-14)]))[0] == 0.5                # within the tolerance: frozen


def test_an_early_reference_needs_the_no_anchoring_crossing_early_too():
    # Factor 2. x alone on 98 crosses as built in 2010 (early) and never with no anchoring; with y on 98 too, the
    # no-anchoring reading crosses in 2010. Same place either way; only the acceptance differs.
    sites = [{"fid": "x", "st": "RR", "u": 98, "raw": 1.0, "year": 2008},
             {"fid": "y", "st": "RR", "u": 99, "cands": "98;99", "assign": "smallest_polygon", "raw": 1.0, "year": 2008}]
    inp = mini(sites, {(98, "RR"): 1.5 * GWH / 0.02, (99, "RR"): 1e3}, {"RR": 4 * GWH / 1000})
    assert inp.frozen_factor("RR") == pytest.approx(2.0)
    res = check(inp, [], "RR")
    u = res["utilities"]["98:RR"]
    assert u["reference"]["place"] == "early" and kept(res, 98, "RR") == {("y", "assignment")}
    w = u["kept_questions"][0]["witness"]
    assert {w["a"]["outcome"]["place"], w["b"]["outcome"]["place"]} == {"early"}
    agrees_with_brute_force(inp, [], "RR", res)


def _every_config_loads_match(inp, corrections, st):
    """The vectorised loads, against the scratch rebuild's matrices, in every configuration of every question."""
    corr = px.parse_corrections(corrections, inp)
    S = pe._State(inp, corr, st)
    axes = [(qid, list(range(len(q.values)))) for qid, q in enumerate(S.qs)]
    n = 0
    for k in S.units:
        ab, na, shape = S.grid(k, axes)
        for i, at in enumerate(itertools.product(*[range(len(sel)) for _, sel in axes])):
            cfg = {(S.qs[q].fid, S.qs[q].name): S.qs[q].values[at[p]] for p, (q, _) in enumerate(axes)}
            m = realise(inp, corr, st, cfg)
            np.testing.assert_allclose(ab[i], m["as_built"].loc[k].values, rtol=1e-12, atol=1e-9)
            np.testing.assert_allclose(na[i], m["no_anchoring"].loc[k].values, rtol=1e-12, atol=1e-9)
            n += 1
    return n


def test_the_vectorised_loads_are_the_scratch_rebuilds_in_every_configuration():
    inp = world()
    assert _every_config_loads_match(inp, [date("p3", 2013, 2024, 2016), split("p3", None, 0.5, rest_earliest=2014)], "AA") == 3 * 108
    assert _every_config_loads_match(inp, [{"fid": "p1", "kind": "reopen", "candidates": [1, 3]}, date("p1", 2010, 2014, 2012),
                                           {"fid": "p3", "kind": "size", "mw_full": 2.0, "measured": True},
                                           date("p3", 2020, 2024, 2020, never=True)], "AA") > 0
    # An Epoch site carrying a scale of 0.8 (a fixed history; its divisor is one number): no anchoring divides by it.
    sites = [{"fid": "e", "st": "SS", "u": 95, "cands": "95;96", "assign": "smallest_polygon", "raw": 4.0, "year": 2012,
              "src": "epoch"},
             {"fid": "p", "st": "SS", "u": 95, "cands": "95;96", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(95, "SS"): 1e3, (96, "SS"): 1e3})
    inp.fac.loc["e", "state_scale"] = 0.8
    assert _every_config_loads_match(inp, [], "SS") == 2 * 9
    res = check(inp, [], "SS")
    assert res["utilities"]["95:SS"]["method"] == "exact"


def test_a_crypto_row_on_the_utility_reaches_it_through_the_factor_only():
    # c is a crypto row on utility 100: no load in the dose, but it counts in the 2024 anchoring (as build_inventory and
    # the scratch rebuild count it). Its date moves the factor from 2.33 to 2.8 or 3.0, and s (3 MW raw on 100) from
    # 7 MW to 8.4 or 9 against a 7.5 MW threshold. Its settings put the same (no) load on 100 and differ in the anchoring.
    sites = [{"fid": "c", "st": "TT", "u": 100, "raw": 3.0, "year": 2016},
             {"fid": "s", "st": "TT", "u": 100, "raw": 3.0, "year": 2010}]
    inp = mini(sites, {(100, "TT"): 7.5 * GWH / 0.02}, {"TT": 14 * GWH / 1000})
    inp.fac.loc["c", "is_crypto"] = True
    inp.fy = inp.fy[inp.fy.fid != "c"]
    c = [date("c", 2016, 2024, 2016)]
    res = check(inp, c, "TT")
    assert res["factor_can_move"] and kept(res, 100, "TT") == {("c", "date")}
    agrees_with_brute_force(inp, c, "TT", res)


def test_a_count_exactly_at_the_ceiling_is_evaluated_and_one_over_it_is_not():
    """Brief section 5: at or under the ceiling every configuration is evaluated. Added by the session at verification."""
    inp = world()
    corr = px.parse_corrections([date("p3", 2010, 2016, 2016)], inp)
    n = pe.exact_attribution(inp, corr, "AA")["utilities"]["3:AA"]["configurations"]
    assert n > 1
    at = pe.exact_attribution(inp, corr, "AA", ceiling=n)["utilities"]["3:AA"]
    assert at["method"] == "exact" and at["complete"] and at["configurations"] == n
    over = pe.exact_attribution(inp, corr, "AA", ceiling=n - 1)["utilities"]["3:AA"]
    assert over["method"] == "conservative" and not over["complete"] and over["configurations"] == n


# ---- the reference repair (docs/gate1/reference-repair-rule-2026-11-18.md; D-72 item 4) -----------------------------
# Rule R2: a reference is defined only if the place and crossing as built are the same at EVERY admissible reference
# setting (R3: one representative per class merged for the utility, relevant questions only); R4: undefined without the
# search over the ceiling; R6: the place test takes its reference from the same function; R7: the triple.

def _as_built_at(inp, corr, st, k, settings):
    """(place, crossing year or None) as built, from pass_c_exact.realise (the scratch rebuild), by this file's code."""
    m = pe.realise(inp, corr, st, settings)
    ab = list(m["as_built"].loc[k].values)
    c = _cross(ab, inp.base[k])
    return _place(c, _under(ab, inp.base[k])), c


def _pair_realises_differently(inp, corr, st, k, r):
    """The named pair of an undefined reference: differs in exactly its question, and realises to two different
    (place, crossing) as built, each the one the pair records."""
    pr = r["pair"]
    name = f"{pr['fid']} {pr['question']}"
    assert {"fid": pr["fid"], "question": pr["question"]} in r["undefined_by"]
    a, b = pr["a"]["settings"], pr["b"]["settings"]
    assert set(a) == set(b) and [x for x in a if a[x] != b[x]] == [name]
    assert name in r["why_undefined"] and f"at {a[name]}" in r["why_undefined"] and f"at {b[name]}" in r["why_undefined"]
    got = {side: _as_built_at(inp, corr, st, k, pr[side]["settings"]) for side in ("a", "b")}
    assert got["a"] != got["b"]
    for side in ("a", "b"):
        assert got[side] == (pr[side]["place"], None if pr[side]["crossing"] == "never" else int(pr[side]["crossing"])), side
    return pr


def test_an_interior_start_on_the_utility_leaves_the_reference_undefined_where_the_ends_agree():
    inp = interior_world()
    c = [date("x", 2005, 2025, None)]
    corr = px.parse_corrections(c, inp)
    k = (1, "ZA")
    assert _as_built_at(inp, corr, "ZA", k, {"x date": 2005}) == ("early", 2007)          # the first setting
    assert _as_built_at(inp, corr, "ZA", k, {"x date": 2025}) == ("early", 2007)          # the last setting
    assert _as_built_at(inp, corr, "ZA", k, {"x date": 2010}) == ("cohort", 2012)         # an interior one
    res = check(inp, c, "ZA")
    u = res["utilities"]["1:ZA"]
    r = u["reference"]
    assert not r["defined"] and r["place"] is None and r["crossing"] is None
    assert r["searched"] and r["settings_enumerated"] == 21 and r["undefined_by"] == [{"fid": "x", "question": "date"}]
    pr = _pair_realises_differently(inp, corr, "ZA", k, r)
    assert pr["a"]["settings"] == {"x date": 2005}                                         # the first setting against another
    assert u["method"] == "exact" and u["kept_questions"] and set(u["kept_questions"][0]["witness"]["a"]["outcome"]) == {
        "crossing_as_built", "crossing_no_anchoring", "under_floor_as_built", "under_floor_no_anchoring"}
    assert res["utilities"]["2:ZA"]["reference"]["defined"]                                # x is never on 2: not relevant
    agrees_with_brute_force(inp, c, "ZA", res)


def test_an_interior_start_leaves_the_reference_undefined_where_never_is_the_last_setting():
    inp = interior_world()
    c = [date("x", 2005, None, None, never=True)]
    corr = px.parse_corrections(c, inp)
    k = (1, "ZA")
    assert _as_built_at(inp, corr, "ZA", k, {"x date": "never"}) == ("early", 2007)
    assert _as_built_at(inp, corr, "ZA", k, {"x date": 2005}) == ("early", 2007)
    res = check(inp, c, "ZA")
    r = res["utilities"]["1:ZA"]["reference"]
    assert not r["defined"] and r["settings_enumerated"] == 22                             # 2026 and never: one class
    _pair_realises_differently(inp, corr, "ZA", k, r)
    rel_ = res["utilities"]["1:ZA"]["relevant_questions"][0]["merged_settings"]
    assert [2026, "never"] in rel_
    agrees_with_brute_force(inp, c, "ZA", res)


def test_never_alone_can_leave_the_reference_undefined():
    # ZG: y (1 MW raw from 2005) on utility 1 (threshold 1.5 MW); x (1 MW raw) on utility 2 starts in 2005 to 2010 or
    # never, with no convention, and reaches 1 through the factor only. Any start is full by 2024: permit total 2 MW,
    # factor 1, y at most 1.0 MW (1.3% of 1's sales: "neither"). Never: total 1 MW, factor 2, y 1.33 in 2006 and 2.0 in
    # 2007: early 2007. For utility 1 the six years are one class and "never" the other: only "never" separates them.
    sites = [{"fid": "y", "st": "ZG", "u": 1, "raw": 1.0, "year": 2005},
             {"fid": "x", "st": "ZG", "u": 2, "raw": 1.0, "year": 2005}]
    inp = mini(sites, {(1, "ZG"): 1.5 * GWH / 0.02, (2, "ZG"): 1e4}, {"ZG": 2.0 * GWH / 1000})
    c = [date("x", 2005, 2010, None, never=True)]
    corr = px.parse_corrections(c, inp)
    k = (1, "ZG")
    assert _as_built_at(inp, corr, "ZG", k, {"x date": 2010}) == ("neither", None)
    assert _as_built_at(inp, corr, "ZG", k, {"x date": "never"}) == ("early", 2007)
    res = check(inp, c, "ZG")
    u = res["utilities"]["1:ZG"]
    assert u["relevant_questions"][0]["merged_settings"] == [[2005, 2006, 2007, 2008, 2009, 2010], ["never"]]
    r = u["reference"]
    assert not r["defined"] and r["settings_enumerated"] == 2 and r["undefined_by"] == [{"fid": "x", "question": "date"}]
    pr = _pair_realises_differently(inp, corr, "ZG", k, r)
    assert {pr["a"]["settings"]["x date"], pr["b"]["settings"]["x date"]} == {2005, "never"}
    agrees_with_brute_force(inp, c, "ZG", res)
    assert _place_test_against_exact(inp, c, "ZG") >= 1


def test_a_provisional_convention_with_the_same_shape_leaves_the_exact_reference_undefined_and_the_place_tests_defined():
    inp = interior_world()
    c = [dict(date("x", 2005, 2025, 2005), convention_is="provisional")]
    corr = px.parse_corrections(c, inp)
    res = check(inp, c, "ZA")
    r = res["utilities"]["1:ZA"]["reference"]
    assert not r["defined"] and r["settings_enumerated"] == 21
    _pair_realises_differently(inp, corr, "ZA", (1, "ZA"), r)
    agrees_with_brute_force(inp, c, "ZA", res)
    one = next(u for u in px.expand(c, inputs=inp)["utilities"] if u["utility"] == "1:ZA")
    assert one["reference"]["place"] == "early" and one["reference"]["crossing"] == 2007     # the place test: at the convention
    # The same rule, called with the place test's list (no provisional question), gives that defined reference.
    S = pe._State(inp, corr, "ZA")
    x_date = [i for i, q in enumerate(S.qs) if (q.fid, q.name) == ("x", "date")]
    assert len(x_date) == 1 and S.defining("place_test") == [] and S.defining("exact") == x_date
    rec, _ = pe.reference_of(S, (1, "ZA"), float(inp.base[(1, "ZA")]), THETA, S.defining("place_test"))
    assert rec["defined"] and (rec["place"], rec["crossing"]) == ("early", "2007") and rec["settings_enumerated"] == 1


def test_a_reference_defined_at_every_setting_is_the_value_at_the_ends():
    # y (3 MW raw from 2001) on utility 1 (threshold 2.5 MW) crosses in 2003 whatever x (0.3 MW, start 2010 to 2025, no
    # convention) does: the factor runs from 3/3.3 = 0.91 to 1, so 2002 is at most 2.0 MW and 2003 at least 2.73.
    sites = [{"fid": "y", "st": "ZD", "u": 1, "raw": 3.0, "year": 2001},
             {"fid": "x", "st": "ZD", "u": 1, "raw": 0.3, "year": 2010}]
    inp = mini(sites, {(1, "ZD"): 2.5 * GWH / 0.02}, {"ZD": 3.0 * GWH / 1000})
    c = [date("x", 2010, 2025, None)]
    corr = px.parse_corrections(c, inp)
    res = check(inp, c, "ZD")
    r = res["utilities"]["1:ZD"]["reference"]
    assert res["factor_can_move"] and r["defined"] and r["searched"] and r["settings_enumerated"] == 16
    assert (r["place"], r["crossing"]) == ("early", "2003") and r["why_undefined"] is None and r["pair"] is None
    for end in (2010, 2025):
        assert _as_built_at(inp, corr, "ZD", (1, "ZD"), {"x date": end}) == ("early", 2003)
    agrees_with_brute_force(inp, c, "ZD", res)


def test_a_capacity_question_with_rest_earliest_whose_interior_arrival_moves_the_crossing():
    inp = capacity_world()
    c = [split("x", 2005, 0.5, rest_earliest=2005)]
    corr = px.parse_corrections(c, inp)
    k = (1, "ZC")
    assert _as_built_at(inp, corr, "ZC", k, {"x capacity": 2005}) == ("early", 2007)
    assert _as_built_at(inp, corr, "ZC", k, {"x capacity": 2025}) == ("early", 2007)
    assert _as_built_at(inp, corr, "ZC", k, {"x capacity": 2010}) == ("cohort", 2012)
    res = check(inp, c, "ZC")
    r = res["utilities"]["1:ZC"]["reference"]
    assert not r["defined"] and r["undefined_by"] == [{"fid": "x", "question": "capacity"}] and r["settings_enumerated"] == 21
    _pair_realises_differently(inp, corr, "ZC", k, r)
    agrees_with_brute_force(inp, c, "ZC", res)


def test_two_questions_whose_mixed_corner_moves_the_crossing():
    inp = corners_world()
    c = [date("x1", 2005, 2006, None), date("x2", 2024, 2025, None)]
    corr = px.parse_corrections(c, inp)
    k = (1, "ZB")
    assert _as_built_at(inp, corr, "ZB", k, {"x1 date": 2005, "x2 date": 2024}) == ("early", 2007)   # all early
    assert _as_built_at(inp, corr, "ZB", k, {"x1 date": 2006, "x2 date": 2025}) == ("early", 2007)   # all late
    assert _as_built_at(inp, corr, "ZB", k, {"x1 date": 2005, "x2 date": 2025}) == ("early", 2006)   # mixed
    res = check(inp, c, "ZB")
    r = res["utilities"]["1:ZB"]["reference"]
    assert not r["defined"] and r["settings_enumerated"] == 4
    assert {(q["fid"], q["question"]) for q in r["undefined_by"]} == {("x1", "date"), ("x2", "date")}
    _pair_realises_differently(inp, corr, "ZB", k, r)
    agrees_with_brute_force(inp, c, "ZB", res)


def test_a_reference_over_a_small_ceiling_is_undefined_without_the_search_and_says_so():
    inp = interior_world()
    corr = px.parse_corrections([date("x", 2005, 2025, None)], inp)
    over = pe.exact_attribution(inp, corr, "ZA", ceiling=20)["utilities"]["1:ZA"]
    r = over["reference"]
    assert over["method"] == "conservative" and over["configurations"] == 21
    assert not r["defined"] and r["searched"] is False and r["settings_enumerated"] == 21 and r["pair"] is None
    assert r["why_undefined"].startswith("not searched") and "21 combinations" in r["why_undefined"]
    assert "over the ceiling of 20" in r["why_undefined"] and "x date" in r["why_undefined"]
    assert r["undefined_by"] == [{"fid": "x", "question": "date"}]
    at = pe.exact_attribution(inp, corr, "ZA", ceiling=21)["utilities"]["1:ZA"]["reference"]
    assert at["searched"] and at["settings_enumerated"] == 21 and not at["defined"] and at["pair"]
    S = pe._State(inp, corr, "ZA")
    rec, codes = pe.reference_of(S, (1, "ZA"), float(inp.base[(1, "ZA")]), THETA, S.defining("exact"), ceiling=20)
    assert rec == r and codes is None


def test_more_than_twelve_reference_defining_questions_are_searched():
    # The old limit of twelve questions is gone (R4): thirteen small sites on utility 1, each with a start in 2010 or 2011
    # and no convention, give 2^13 = 8,192 combinations, under the ceiling. Utility 1 is a comparison utility throughout.
    sites = [{"fid": f"t{i:02d}", "st": "ZF", "u": 1, "raw": 0.1, "year": 2010} for i in range(13)]
    inp = mini(sites, {(1, "ZF"): 1e6})
    c = [date(f"t{i:02d}", 2010, 2011, None) for i in range(13)]
    res = pe.exact_attribution(inp, px.parse_corrections(c, inp), "ZF")
    u = res["utilities"]["1:ZF"]
    r = u["reference"]
    assert r["defined"] and r["searched"] and r["settings_enumerated"] == 2 ** 13 and r["place"] == "comparison"
    assert u["method"] == "exact" and u["complete"] and u["configurations"] == 2 ** 13 and u["kept_questions"] == []


def _place_test_against_exact(inp, corrections, st):
    """For every utility the place test touches: its reference (defined or not, place and crossing) is the exact
    attribution's, in a state with no provisional question, where the two lists of reference-defining questions agree."""
    corr = px.parse_corrections(corrections, inp)
    assert not any(c.date and c.date.get("convention_is") for c in corr.values())
    ex_ = pe.exact_attribution(inp, corr, st)
    n = 0
    for row in px.expand(corrections, inputs=inp)["utilities"]:
        if not row["utility"].endswith(f":{st}"):
            continue
        r = ex_["utilities"][row["utility"]]["reference"]
        rr = row["reference_rule"]
        assert (rr["settings_enumerated"], rr["searched"], rr["undefined_by"]) == (
            r["settings_enumerated"], r["searched"], r["undefined_by"]), row["utility"]
        if r["defined"]:
            assert isinstance(row["reference"], dict), row["utility"]
            assert (row["reference"]["place"], str(row["reference"]["crossing"])) == (r["place"], r["crossing"]), row["utility"]
        else:
            assert row["reference"] == f"none ({r['why_undefined']})", row["utility"]
        n += 1
    return n


def test_the_place_test_and_the_exact_attribution_agree_on_every_utility():
    n = 0
    n += _place_test_against_exact(interior_world(), [date("x", 2005, 2025, None)], "ZA")
    n += _place_test_against_exact(interior_world(), [date("x", 2005, None, None, never=True)], "ZA")
    n += _place_test_against_exact(capacity_world(), [split("x", 2005, 0.5, rest_earliest=2005)], "ZC")
    n += _place_test_against_exact(corners_world(), [date("x1", 2005, 2006, None), date("x2", 2024, 2025, None)], "ZB")
    n += _place_test_against_exact(world(), [date("p3", 2010, 2016, None)], "AA")
    n += _place_test_against_exact(world(), [date("p3", 2016, None, None, never=True),
                                             {"fid": "p1", "kind": "reopen", "candidates": [1, 3]}], "AA")
    n += _place_test_against_exact(anchoring_world(), [date("q1", 2016, 2024, None)], "DD")
    assert n >= 10


# ---- rule R7: the triple, and the narrower pair kept as a named alternative ----------------------------------------

def na_only_world():
    """ZE, factor 0.5 (assignments do not move it). Utility 3 (threshold 3 MW): P3 (2.8 MW raw from 2010) is 1.4 MW as
    built; Q3 (1.5 MW raw from 2005, unresolved between 3 and 6) adds 0.75: as built 3 never crosses and is over the
    floor either way ("neither", accepted). With no anchoring P3 alone is 2.8 MW (never, "neither"); with Q3 it is
    1.5 + 0.93 in 2010 and 1.5 + 1.87 = 3.37 in 2011: a cohort crossing. Only the no-anchoring place separates them."""
    sites = [{"fid": "P3", "st": "ZE", "u": 3, "raw": 2.8, "year": 2010},
             {"fid": "Q3", "st": "ZE", "u": 3, "cands": "3;6", "assign": "smallest_polygon", "raw": 1.5, "year": 2005}]
    return mini(sites, {(3, "ZE"): 3.0 * GWH / 0.02, (6, "ZE"): 1e6}, {"ZE": 0.5 * 4.3 * GWH / 1000})


def test_the_triple_keeps_a_question_that_only_the_no_anchoring_place_separates():
    inp = na_only_world()
    k = (3, "ZE")
    either = check(inp, [], "ZE")
    assert either["criterion"] == "either_reading"
    u = either["utilities"]["3:ZE"]
    assert u["reference"]["defined"] and u["reference"]["place"] == "neither"
    assert kept(either, 3, "ZE") == {("Q3", "assignment")}
    w = u["kept_questions"][0]["witness"]
    assert {w[s_]["outcome"]["place"] for s_ in "ab"} == {"neither"}
    assert {w[s_]["outcome"]["accepted"] for s_ in "ab"} == {True}
    assert {w[s_]["outcome"]["place_no_anchoring"] for s_ in "ab"} == {"cohort", "neither"}
    assert all(w[s_]["detail"]["place_no_anchoring"] == w[s_]["outcome"]["place_no_anchoring"] for s_ in "ab")
    agrees_with_brute_force(inp, [], "ZE", either)
    for s_ in "ab":                                                                        # the driver's realisation agrees
        m = pe.realise(inp, {}, "ZE", w[s_]["settings"])
        assert pe.realised_outcome(m, k, float(inp.base[k]), THETA, u["reference"]) == w[s_]["outcome"]
        assert pe.realised_outcome(m, k, float(inp.base[k]), THETA, u["reference"], criterion="as_built") == {
            "place": "neither", "accepted": True}
    narrow = check(inp, [], "ZE", criterion="as_built")
    assert narrow["criterion"] == "as_built" and kept(narrow, 3, "ZE") == set()
    agrees_with_brute_force(inp, [], "ZE", narrow)


def test_criterion_as_built_reproduces_the_narrower_outcome():
    """D-66 4.1's pair, kept as a named alternative: its outcomes carry place and accepted only, its kept sets are the
    pair's (checked against the brute force under the pair), and never larger than the triple's (section 5)."""
    cases = [(world(), [date("p3", 2016, 2024, 2016, never=True)], "AA"),
             (anchoring_world(), [date("q1", 2016, 2024, 2016)], "DD"),
             (na_only_world(), [], "ZE"),
             (interior_world(), [date("x", 2005, 2025, 2010)], "ZA")]
    for inp, c, st in cases:
        pair = check(inp, c, st, criterion="as_built")
        triple = check(inp, c, st)
        agrees_with_brute_force(inp, c, st, pair)
        agrees_with_brute_force(inp, c, st, triple)
        for key, u in pair["utilities"].items():
            mine = {(q["fid"], q["question"]) for q in u["kept_questions"]}
            assert mine <= {(q["fid"], q["question"]) for q in triple["utilities"][key]["kept_questions"]}, key
            assert u["reference"] == triple["utilities"][key]["reference"], key
            for q in u["kept_questions"]:
                for s_ in "ab":
                    o = q["witness"][s_]["outcome"]
                    assert set(o) in ({"place", "accepted"}, {"crossing_as_built", "crossing_no_anchoring",
                                                              "under_floor_as_built", "under_floor_no_anchoring"}), key
    with pytest.raises(ValueError, match="criterion"):
        pe.exact_attribution(world(), {}, "AA", criterion="both")


# ---- D-90 (Joe, 2026-11-18): the place test's reference is a conditional diagnostic and no more ---------------------

def diagnostic_world() -> px.Inputs:
    """ZK, invented: y (2 MW raw from 2005) and x (2 MW raw) on utility 1; EPRI 2 MW-equivalent; utility 1's 2% threshold
    is 1.9 MW. interior_world's arithmetic with the raw loads doubled, so that y alone crosses with no anchoring.

    As built, the 2024 permit total is 2 MW plus x's 2024 load: 4 MW for a start of x up to 2022 (factor 0.5), 2 MW for
    2025 (factor 1.0).
      x 2005: factor 0.5, y and x ramp together: 0.67, 1.33, 2.0 MW in 2005-2007           -> crosses in 2007 (early)
      x 2025: factor 1.0, y alone: 0.67, 1.33, 2.0 MW in 2005-2007                         -> crosses in 2007 (early)
      x 2010: factor 0.5, y alone is 1.0 MW until x comes: 1.33, 1.67, 2.0 in 2010-2012    -> crosses in 2012 (cohort)
    With no anchoring y alone is 0.67, 1.33, 2.0 MW in 2005-2007 and crosses in 2007 whatever x does (with x from 2005,
    2.67 MW in 2006): early at both ends. So the two ends agree in both readings and only an interior year differs.
    Every load is at least 0.1 MW from the threshold. Utility 2 carries nothing."""
    sites = [{"fid": "y", "st": "ZK", "u": 1, "raw": 2.0, "year": 2005},
             {"fid": "x", "st": "ZK", "u": 1, "raw": 2.0, "year": 2005}]
    return mini(sites, {(1, "ZK"): 1.9 * GWH / 0.02, (2, "ZK"): 1e3}, {"ZK": 2.0 * GWH / 1000})


def test_the_place_tests_reference_is_only_a_conditional_diagnostic_where_the_exact_reference_is_undefined(monkeypatch):
    """The place test's narrower reference cannot override an undefined exact reference or by itself justify eligibility
    or pruning (D-90). Invented inputs: diagnostic_world's x on utility 1, with a PROVISIONAL convention of 2005 in an
    interval of 2005 to 2025. A start of 2005 or of 2025 crosses in 2007 (early) and a start of 2010 in 2012 (cohort), so
    the exact reference of utility 1 is undefined. The place test does not read the provisional mark: it shows early 2007
    and, on the two ends it tries, says the utility keeps its place. That is the case the ruling is about: a reference and
    a "keeps its place" that look settled and are not. The output has to say which of the two governs."""
    inp = diagnostic_world()
    c = [dict(date("x", 2005, 2025, 2005), convention_is="provisional")]
    corr = px.parse_corrections(c, inp)
    assert _as_built_at(inp, corr, "ZK", (1, "ZK"), {"x date": 2005}) == ("early", 2007)
    assert _as_built_at(inp, corr, "ZK", (1, "ZK"), {"x date": 2025}) == ("early", 2007)
    assert _as_built_at(inp, corr, "ZK", (1, "ZK"), {"x date": 2010}) == ("cohort", 2012)
    ex = pe.exact_attribution(inp, px.parse_corrections(c, inp), "ZK")["utilities"]["1:ZK"]["reference"]
    assert not ex["defined"] and ex["searched"] and ex["undefined_by"] == [{"fid": "x", "question": "date"}]

    def one_of(res):
        return next(u for u in res["utilities"] if u["utility"] == "1:ZK")

    # ---- the place test's own row ----
    res = px.expand(c, inputs=inp)
    one = one_of(res)
    assert one["reference"] == {"place": "early", "crossing": 2007, "verdict": "keeps its place"} and one["keeps_its_place"]
    for phrase in ("conditional diagnostic", "only on the condition that every provisional convention is the site's start",
                   "cannot override an undefined exact reference", "by itself a ground for eligibility or for pruning"):
        assert phrase in px.REFERENCE_CONDITION, phrase
    assert res["place_test_reference"] == px.REFERENCE_CONDITION
    assert all(u["reference_is"] == "conditional diagnostic" for u in res["utilities"])        # the label, on every row
    assert one["exact_reference_defined"] is False and one["exact_reference_why_undefined"] == ex["why_undefined"]
    assert one["reference_shown_where_exact_is_undefined"] is True                                # the flag
    w = one["reference_warning"]                                                                  # and the words
    assert w.startswith("The exact attribution's reference for this utility is undefined (") and "x date" in w
    assert "do not override the undefined exact reference" in w and "D-90" in w
    assert "not a ground for eligibility or for pruning" in w
    table = px._table(res)
    assert px.REFERENCE_CONDITION in table and "[conditional diagnostic]" in table and f"NOTE  {w}" in table
    assert "keeps its place (diagnostic only): True" in table and "keeps its place: True" not in table

    # ---- the driver: JSON, CSV and printed summary ----
    out = pe.run(c, inp, states=["ZK"], hosts=[(1, "ZK")])
    assert out["json"]["place_test_reference"] == px.REFERENCE_CONDITION
    shown = out["json"]["counts"]["place_test_reference_shown_where_exact_is_undefined"]
    assert shown == [{"utility": "1:ZK", "name": "U1", "place_test_reference": "early 2007",
                      "place_test_keeps_its_place": True, "warning": w}]
    assert one_of(out["json"]["expansion"])["reference_shown_where_exact_is_undefined"] is True
    rows = [r for r in out["csv"] if r["utility"] == "1:ZK"]
    assert rows and list(rows[0]) == pe.CSV_COLUMNS and pe.CSV_COLUMNS[-1] == "place_test_reference_note"
    for r in rows:                                    # the file's own reference stays undefined; the place test's is words only
        assert r["reference_defined"] is False and r["reference_place"] == "" and r["reference_crossing"] == ""
        assert r["place_test_reference_note"] == w
    s = out["summary"]
    assert px.REFERENCE_CONDITION in s
    assert "the place test shows a reference where the reference here is undefined: 1." in s
    assert "1:ZK U1: the place test shows early 2007, keeps its place True; the reference here is undefined" in s
    assert "reference undefined (" in s                                                          # the host's own line is unchanged

    # ---- the other way a reference is undefined: not searched (over the ceiling), where the place test still has one ----
    out = pe.run(c, inp, states=["ZK"], hosts=[(1, "ZK")], ceiling=20)                             # 21 combinations
    shown = out["json"]["counts"]["place_test_reference_shown_where_exact_is_undefined"]
    assert [x["utility"] for x in shown] == ["1:ZK"] and "not searched" in shown[0]["warning"]
    assert "not searched" in one_of(out["json"]["expansion"])["exact_reference_why_undefined"]     # this run's reference governs
    monkeypatch.setattr(pe, "CEILING", 20)
    one = one_of(px.expand(c, inputs=inp))
    assert isinstance(one["reference"], dict) and one["reference_shown_where_exact_is_undefined"] is True
    assert "not searched" in one["reference_warning"]
    monkeypatch.undo()

    # ---- and the two cases that are not flagged ----
    # A convention that is not provisional: both references are defined and are the same; the label stays, no flag.
    c2 = [date("x", 2005, 2025, 2010)]
    one = one_of(px.expand(c2, inputs=inp))
    assert one["reference"]["place"] == "cohort" and one["reference"]["crossing"] == 2012
    assert one["reference_is"] == "conditional diagnostic" and one["exact_reference_defined"] is True
    assert one["exact_reference_why_undefined"] is None
    assert one["reference_shown_where_exact_is_undefined"] is False and one["reference_warning"] is None
    out = pe.run(c2, inp, states=["ZK"], hosts=[(1, "ZK")])
    assert out["json"]["counts"]["place_test_reference_shown_where_exact_is_undefined"] == []
    assert "the place test shows a reference where the reference here is undefined: 0" in out["summary"]
    assert all(r["place_test_reference_note"] == "" for r in out["csv"])
    # No convention at all: neither has a reference, so the place test shows none and there is nothing to flag.
    one = one_of(px.expand([date("x", 2005, 2025, None)], inputs=inp))
    assert isinstance(one["reference"], str) and one["exact_reference_defined"] is False
    assert one["reference_shown_where_exact_is_undefined"] is False and one["reference_warning"] is None
    assert not one["keeps_its_place"]
