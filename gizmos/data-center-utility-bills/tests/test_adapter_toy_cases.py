"""Toy cases for the dependency adapter, worked by hand (docs/gate1/dependency-adapter-brief-2026-11-18.md, section 7.3).

Written to the interface of the brief's section 6 by an author who has not seen the adapter. Every expectation is
worked out by hand from sections 1 and 4 of the brief, with the working in the comments; none was taken from running
any code. This file cannot run in the checkout it was written in, because the adapter is not there.

Invented data only. Every state is made up with `mini()` from tests/test_pass_c_expand.py; every mask is a small
DataFrame made up here (columns utility_id_eia, state, year, usable), never a file.

Arithmetic used throughout: a site starting in year Y carries a third of its full load in Y, two thirds in Y + 1 and
full load from Y + 2 (buildout.ramp_mw); 1 MW for a year is 8.76 GWh; a site counts its 2024 MW times 8.76 / 1000 TWh in
its state's anchoring; the host threshold is 2% of base-period sales (base 1,000,000 GWh: 20,000 GWh, far above any
load in these states unless a smaller base is named).

The permitted windows (brief 4.6): cohort g, for g from 2011 to 2022, is the ten years g-6 to g+3; the second
estimate's long difference is 2008, 2009, 2010, 2023, 2024, 2025; its panel form is 2005 to 2025.

Readings made where the brief does not settle a point (the report lists them):
* `pool` and `hosts` are passed as sets of (utility_id_eia, state) tuples, the form availability.py takes units in.
  Units the adapter returns are compared after normalising "<utility_id_eia>:<state>" strings and tuples alike.
* The five fingerprint names of brief 4.8 are compared after lower-casing and reading "_" and "-" as spaces:
  corrections, candidates, dependencies, mask identity, eligibility rules.
* A retained question's reason is checked by words it must contain: "coverage" or "covered" (outside coverage);
  "unknown" (anchoring unknown); "anchoring" (moves the state's anchoring); "no utility" (reaches none); and for a
  utility that is not narrowed, the utility as "<utility_id_eia>:<state>" and, where the brief names why, "host",
  "possible host" or "pool".
* Where one change can also change a fingerprint that rests on it (a listed host is also a protected unit; the covered
  states also decide which questions and tables are fingerprinted), the test requires the named fingerprint and allows
  only those others.
* A record that has been through json.dumps and json.loads is still a record reopen_reasons accepts.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import availability  # noqa: E402
from pipeline.analysis import availability_adapter as adapter  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import mini  # noqa: E402

YEARS = list(range(2001, 2026))
BIG = 1e6                                         # a base under which nothing here comes near either threshold
# The four field names are the adapter's (MASK_IDENTITY_FIELDS). The brief did not fix them and this file first used
# run_id, definition_version and mask_file_hash; the session renamed them on 2026-11-18. No value or expectation changed.
IDENTITY = {"run": "run-1", "audit_attempt": "attempt-1", "definition": "def-1", "mask_sha256": "hash-1"}
FINGERPRINTS = {"corrections", "candidates", "dependencies", "mask identity", "eligibility rules"}


# ---- helpers ----------------------------------------------------------------------------------------------------------

def unit(x) -> tuple:
    if isinstance(x, str):
        u, s = x.split(":")
        return (int(u), s)
    return (int(x[0]), str(x[1]))


def units(xs) -> set:
    return {unit(x) for x in xs}


def fp_name(x: str) -> str:
    return " ".join(str(x).lower().replace("_", " ").replace("-", " ").split())


def names(xs) -> set:
    return {fp_name(x) for x in xs}


def mask_of(spec: dict) -> pd.DataFrame:
    """{unit: {year: usable}}; a year left out of a unit's dict has no row."""
    rows = [(u, s, y, bool(f)) for (u, s), years in spec.items() for y, f in years.items()]
    return pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "usable"])


def every_year(flag: bool, except_years=(), drop=()) -> dict:
    return {y: (not flag if y in except_years else flag) for y in YEARS if y not in drop}


def date(fid, earliest, latest, convention, never=False):
    return {"fid": fid, "kind": "date", "earliest": earliest, "latest": latest, "never_is_possible": never,
            "convention": convention}


def table_for(inp, corrections, states):
    return adapter.dependency_table(inp, px.parse_corrections(corrections, inp), states)


def run_screen(mask, pool, hosts, table, covered, corrections, identity=IDENTITY, windows=None):
    rec = adapter.screen(mask, identity, pool, hosts, table, covered, corrections, windows=windows)
    json.dumps(rec)                                                     # everything returned survives json.dumps
    return rec


def question(table, st, qid):
    return next(q for q in table["states"][st]["questions"] if q["question_id"] == qid)


def deferrable(rec) -> set:
    return set(rec["deferrable"])


def reason(rec, qid) -> str:
    return str(rec["retained"][qid]).lower()


# ---- the made-up states -----------------------------------------------------------------------------------------------

def shared_state(base2=BIG, cands="1;2"):
    # SA. x is unresolved: on utility 1 by the map, candidate 2; 1 MW raw from 2010. Factor 1.
    # Its assignment question has settings 1, 2, off the panel. On 1 its load is 2.92, 5.84, then 8.76 GWh from 2012;
    # on 2 the same; off the panel none. It reaches 1 and 2 (brief 4.1).
    # Its 2024 contribution is 1 MW = 0.00876 TWh in all three settings (a site off the panel stays in the anchoring):
    # it does not move anchoring (brief 4.2).
    # With base 1,000,000 GWh neither utility is a possible host (8.76 against 20,000 GWh).
    #
    # DB. q is resolved on utility 1: 2 MW raw, inventory year 2012, date question 2010 to 2014. s on utility 2: 5 MW
    # raw from 2005. q at any start from 2010 to 2014 is at 2 MW by 2016, so its 2024 contribution is 0.01752 TWh in
    # every setting: does not move anchoring. Starting in 2010 rather than 2011 puts 2/3 MW on utility 1 in 2010: it
    # reaches 1 only.
    sites = [{"fid": "x", "st": "SA", "u": 1, "cands": cands, "assign": "smallest_polygon", "raw": 1.0, "year": 2010},
             {"fid": "q", "st": "DB", "u": 1, "raw": 2.0, "year": 2012},
             {"fid": "s", "st": "DB", "u": 2, "raw": 5.0, "year": 2005}]
    bases = {(1, "SA"): BIG, (2, "SA"): base2, (1, "DB"): BIG, (2, "DB"): BIG}
    return mini(sites, bases)


SHARED_CORRECTIONS = [date("q", 2010, 2014, 2012)]
SHARED_UNITS = {(1, "SA"), (2, "SA"), (1, "DB"), (2, "DB")}


def all_false(us) -> pd.DataFrame:
    return mask_of({u: every_year(False) for u in us})


# ---- 4.1, 4.2 and 4.5 on the made-up states ----------------------------------------------------------------------------

def test_state_dependencies_by_hand():
    inp = shared_state()
    corr = px.parse_corrections(SHARED_CORRECTIONS, inp)
    sa = adapter.state_dependencies(inp, corr, "SA")
    json.dumps(sa)
    assert sa["state"] == "SA"
    assert units(sa["units"]) == {(1, "SA"), (2, "SA")}
    qs = {q["question_id"]: q for q in sa["questions"]}
    assert set(qs) == {"x assignment"}                                     # r has none: one site, one question
    assert qs["x assignment"]["fid"] == "x" and qs["x assignment"]["question"] == "assignment"
    assert qs["x assignment"]["settings"] == [1, 2, "off_panel"]
    assert qs["x assignment"]["utilities"] == ["1:SA", "2:SA"]
    assert qs["x assignment"]["moves_anchoring"] is False
    assert sa["possible_hosts"] == []
    db = adapter.state_dependencies(inp, corr, "DB")
    qd = {q["question_id"]: q for q in db["questions"]}
    assert set(qd) == {"q date"}                                           # q is resolved: no assignment question
    assert qd["q date"]["settings"] == [2010, 2011, 2012, 2013, 2014]
    assert qd["q date"]["utilities"] == ["1:DB"]
    assert qd["q date"]["moves_anchoring"] is False
    assert db["possible_hosts"] == []


def test_a_date_with_never_moves_anchoring_and_lists_never():
    # NV. n on utility 1: 2 MW raw, inventory year 2015; date 2015 to 2016 or never. Settings 2015, 2016, never.
    # 2024 contribution: 0.01752 TWh from 2015 or 2016, nothing if never: moves anchoring. Reaches 1 only (t on 2 is
    # resolved and its own load never changes; with no anchoring it is 8.76 GWh whatever the factor).
    inp = mini([{"fid": "n", "st": "NV", "u": 1, "raw": 2.0, "year": 2015},
                {"fid": "t", "st": "NV", "u": 2, "raw": 1.0, "year": 2005}], {(1, "NV"): BIG, (2, "NV"): BIG})
    dep = adapter.state_dependencies(inp, px.parse_corrections([date("n", 2015, 2016, 2015, never=True)], inp), "NV")
    q = {x["question_id"]: x for x in dep["questions"]}["n date"]
    assert q["settings"] == [2015, 2016, "never"]
    assert q["utilities"] == ["1:NV"] and q["moves_anchoring"] is True


# ---- window eligibility and missing years (brief 4.6) ------------------------------------------------------------------

def window_state():
    # WA. Units 1 to 9, every base 1,000,000 GWh. One site: x7 unresolved on utility 7 with candidate 6, 1 MW from 2010.
    # Its assignment question reaches 6 and 7; 8.76 GWh at most, so no possible host anywhere.
    sites = [{"fid": "x7", "st": "WA", "u": 7, "cands": "7;6", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}]
    return mini(sites, {(k, "WA"): BIG for k in range(1, 10)})


def window_mask(drop_2015_everywhere=False):
    d = (2015,) if drop_2015_everywhere else ()
    spec = {
        # 1: usable every year. Passes all fourteen windows.
        (1, "WA"): every_year(True, drop=d),
        # 2: not usable in 2015 only. 2015 lies in cohort g's window when 2012 <= g <= 2021, so those ten cohorts fail
        # and so does the panel form. Cohort 2011 (2005 to 2014), cohort 2022 (2016 to 2025) and the long difference
        # (2008 to 2010, 2023 to 2025) do not hold 2015: they pass. Not narrowed. (No year lies in every cohort window:
        # cohort 2011 ends in 2014 and cohort 2022 starts in 2016. This is the nearest reading of the brief's bullet:
        # one missing year, outside the long difference, that cohort windows hold.)
        (2, "WA"): every_year(True, except_years=(2015,), drop=d),
        # 3: not usable in 2009 and 2020. 2009 is in cohort g's window when g <= 2015 (cohorts 2011 to 2015 fail);
        # 2020 when g >= 2017 (cohorts 2017 to 2022 fail). Cohort 2016 is 2010 to 2019 and passes. The long difference
        # holds 2009 and the panel form holds both: both fail. Exactly one window survives: cohort 2016.
        (3, "WA"): every_year(True, except_years=(2009, 2020), drop=d),
        # 4: as 3, but the mask has no row at all for 2015. A missing year is not usable, so cohort 2016 (which holds
        # 2015) fails too. No window passes: narrowed.
        (4, "WA"): every_year(True, except_years=(2009, 2020), drop=(2015,)),
        # 5: absent from the mask. Passes no window: narrowed.
        # 6: not usable in any year. Narrowed.
        (6, "WA"): every_year(False, drop=d),
        # 7: not usable in any year, but not in the pool. Never narrowed.
        (7, "WA"): every_year(False, drop=d),
        # 8: not usable in any year, in the pool, but a listed host. Protected: never narrowed.
        (8, "WA"): every_year(False, drop=d),
        # 9: not usable in 2010, 2015 and 2020 only. Cohort 2011 holds 2010; cohorts 2012 to 2021 hold 2015; cohort
        # 2022 (2016 to 2025) holds 2020; the long difference holds 2010; the panel form holds all three. Narrowed.
        (9, "WA"): every_year(True, except_years=(2010, 2015, 2020), drop=d),
    }
    return mask_of(spec)


WINDOW_POOL = {(k, "WA") for k in (1, 2, 3, 4, 5, 6, 8, 9)}
WINDOW_HOSTS = {(8, "WA")}


def test_window_eligibility_and_missing_years():
    inp = window_state()
    table = table_for(inp, [], ["WA"])
    rec = run_screen(window_mask(), WINDOW_POOL, WINDOW_HOSTS, table, ["WA"], [])
    assert units(rec["narrowed"]) == {(4, "WA"), (5, "WA"), (6, "WA"), (9, "WA")}
    protected = {unit(k): str(v).lower() for k, v in rec["protected"].items()}
    assert (8, "WA") in protected and "host" in protected[(8, "WA")]
    nn = {unit(k): str(v) for k, v in rec["not_narrowed"].items()}
    # 3 passes exactly one window, cohort 2016; 2 passes cohort 2011, cohort 2022 and the long difference.
    assert "cohort_2016" in nn[(3, "WA")]
    assert not any(f"cohort_{g}" in nn[(3, "WA")] for g in range(2011, 2023) if g != 2016)
    for w in ("cohort_2011", "cohort_2022", "long_difference"):
        assert w in nn[(2, "WA")]
    assert not any(f"cohort_{g}" in nn[(2, "WA")] for g in range(2012, 2022))
    # x7 reaches 6 (narrowed) and 7 (not in the pool): retained, naming 7 and why.
    r = reason(rec, "x7 assignment")
    assert "7:wa" in r and "pool" in r and "x7 assignment" not in deferrable(rec)


def test_a_year_absent_from_the_mask_altogether():
    # The same units with every 2015 row taken out of the mask. 1 now lacks 2015 but still passes cohort 2011,
    # cohort 2022 and the long difference: not narrowed. 2 is as before. 3 lacks 2009 and 2020 (not usable) and 2015
    # (absent), so cohort 2016 fails too: narrowed. 4, 5, 6 and 9 as before.
    inp = window_state()
    table = table_for(inp, [], ["WA"])
    rec = run_screen(window_mask(drop_2015_everywhere=True), WINDOW_POOL, WINDOW_HOSTS, table, ["WA"], [])
    assert units(rec["narrowed"]) == {(3, "WA"), (4, "WA"), (5, "WA"), (6, "WA"), (9, "WA")}


def test_the_screen_uses_the_permitted_windows_by_default():
    # The windows the brief states, written out by hand, are the module's.
    expected = {f"cohort_{g}": tuple(range(g - 6, g + 4)) for g in range(2011, 2023)}
    expected["second_estimate_long_difference"] = (2008, 2009, 2010, 2023, 2024, 2025)
    expected["second_estimate_panel"] = tuple(range(2005, 2026))
    assert {k: tuple(v) for k, v in availability.permitted_windows().items()} == expected


# ---- all relevant questions, not only kept ones -------------------------------------------------------------------------

def test_a_question_that_cannot_change_a_comparison_utilitys_place_is_still_retained():
    # RA. x unresolved on 1, candidate 2, 1 MW from 2010: at most 8.76 GWh. Utility 2's base is 10,000,000 GWh, so its
    # floor is 50,000 GWh: x can never change its place (it stays far under the floor in every setting). An exact
    # attribution would keep no question for 2. The adapter still has x reach 2 (brief 4.1: own load, nothing about
    # place), and 2 passes every window, so x is retained, naming 2.
    inp = mini([{"fid": "x", "st": "RA", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.0,
                 "year": 2010}], {(1, "RA"): BIG, (2, "RA"): 1e7})
    table = table_for(inp, [], ["RA"])
    assert question(table, "RA", "x assignment")["utilities"] == ["1:RA", "2:RA"]
    mask = mask_of({(1, "RA"): every_year(False), (2, "RA"): every_year(True)})
    rec = run_screen(mask, {(1, "RA"), (2, "RA")}, set(), table, ["RA"], [])
    assert units(rec["narrowed"]) == {(1, "RA")}
    assert "x assignment" not in deferrable(rec)
    assert "2:ra" in reason(rec, "x assignment")


# ---- direct anchoring dependencies ------------------------------------------------------------------------------------

def anchoring_state(st, epri):
    # q on utility 1 (its only site): 2 MW raw, inventory year 2022. s on utility 2: 5 MW raw from 2005.
    # Both bases 1,000,000 GWh. Both utilities narrowed in the test.
    sites = [{"fid": "q", "st": st, "u": 1, "raw": 2.0, "year": 2022},
             {"fid": "s", "st": st, "u": 2, "raw": 5.0, "year": 2005}]
    return mini(sites, {(1, st): BIG, (2, st): BIG}, epri)


@pytest.mark.parametrize("st,epri", [("DA", {"DA": 0.0}), ("DC", None)])
def test_a_date_on_a_narrowed_utilitys_only_site_that_moves_the_2024_contribution_is_retained(st, epri):
    # q's date question runs 2021 to 2024. Its 2024 MW by start: 2021 full 2; 2022 full 2; 2023 two thirds (4/3);
    # 2024 a third (2/3). Contributions 0.01752, 0.01752, 0.01168, 0.00584 TWh: it moves anchoring (brief 4.2).
    # DA: EPRI is 0, so the factor is max(0 - 0, 0) / permit = 0, held up at 0.2; the permit total is at least s's
    # 0.0438 TWh, never zero, so the factor is 0.2 in every setting: it cannot move. q is still retained.
    # DC: EPRI defaults to the frozen total (7 MW = 0.06132 TWh), so the factor is 1 with q at 2021 or 2022, and
    # 0.06132 / 0.05548 (about 1.105) or 0.06132 / 0.04964 (about 1.235) with q at 2023 or 2024. Retained too.
    inp = anchoring_state(st, epri)
    corrections = [date("q", 2021, 2024, 2022)]
    table = table_for(inp, corrections, [st])
    q = question(table, st, "q date")
    assert q["settings"] == [2021, 2022, 2023, 2024]
    assert q["utilities"] == [f"1:{st}"] and q["moves_anchoring"] is True
    rec = run_screen(all_false({(1, st), (2, st)}), {(1, st), (2, st)}, set(), table, [st], corrections)
    assert units(rec["narrowed"]) == {(1, st), (2, st)}
    assert "q date" not in deferrable(rec)
    r = reason(rec, "q date")
    assert "anchoring" in r and "unknown" not in r


def test_the_same_date_wholly_before_2024_may_be_deferred():
    # DB-like: q's date runs 2010 to 2014 instead; every start is at full load by 2016, so its 2024 contribution is
    # 0.01752 TWh in every setting: moves_anchoring False. It reaches 1 only, which is narrowed: may be deferred.
    inp = anchoring_state("DE", {"DE": 0.0})
    corrections = [date("q", 2010, 2014, 2012)]
    table = table_for(inp, corrections, ["DE"])
    assert question(table, "DE", "q date")["moves_anchoring"] is False
    rec = run_screen(all_false({(1, "DE"), (2, "DE")}), {(1, "DE"), (2, "DE")}, set(), table, ["DE"], corrections)
    assert deferrable(rec) == {"q date"}


# ---- shared questions --------------------------------------------------------------------------------------------------

def test_a_shared_assignment_question_is_retained_unless_both_candidates_are_narrowed():
    inp = shared_state()
    table = table_for(inp, SHARED_CORRECTIONS, ["SA", "DB"])
    # 1:SA fails every window, 2:SA is usable every year: x reaches 2, which is not narrowed. Retained, naming 2.
    mask = mask_of({(1, "SA"): every_year(False), (2, "SA"): every_year(True),
                    (1, "DB"): every_year(False), (2, "DB"): every_year(False)})
    rec = run_screen(mask, SHARED_UNITS, set(), table, ["SA", "DB"], SHARED_CORRECTIONS)
    assert units(rec["narrowed"]) == {(1, "SA"), (1, "DB"), (2, "DB")}
    assert "x assignment" not in deferrable(rec)
    assert "2:sa" in reason(rec, "x assignment")
    # Both narrowed: every utility x reaches is narrowed and it does not move anchoring. May be deferred.
    rec = run_screen(all_false(SHARED_UNITS), SHARED_UNITS, set(), table, ["SA", "DB"], SHARED_CORRECTIONS)
    assert deferrable(rec) == {"x assignment", "q date"}


# ---- unknown and uncovered ----------------------------------------------------------------------------------------------

def test_a_question_in_a_state_that_is_not_covered_is_retained():
    # The same table, but only DB is covered. Everything fails every window and is in the pool. x is in SA, outside
    # coverage: retained whatever the mask says. q in DB may be deferred as before.
    inp = shared_state()
    table = table_for(inp, SHARED_CORRECTIONS, ["SA", "DB"])
    rec = run_screen(all_false(SHARED_UNITS), SHARED_UNITS, set(), table, ["DB"], SHARED_CORRECTIONS)
    assert "x assignment" not in deferrable(rec)
    r = reason(rec, "x assignment")
    assert "coverage" in r or "covered" in r
    assert "q date" in deferrable(rec)


def test_a_state_whose_table_is_refused_is_not_covered():
    # RF. w is unresolved (candidates 1 and 2), with a size and a year, but on no utility: the pass refuses such a
    # state in words (pass_c_expand's joint check has no as-mapped reading for it). rd is resolved on 1 with a date
    # question 2008 to 2012 that never reaches 2024. RF's table is refused and recorded; nothing in RF is deferred
    # even with RF named as covered and every unit failing every window. SA beside it is handled as usual.
    inp = mini([{"fid": "w", "st": "RF", "u": None, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.0,
                 "year": 2010},
                {"fid": "rd", "st": "RF", "u": 1, "raw": 1.0, "year": 2010},
                {"fid": "x", "st": "SA", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.0,
                 "year": 2010}],
               {(1, "RF"): BIG, (2, "RF"): BIG, (1, "SA"): BIG, (2, "SA"): BIG})
    corrections = [date("rd", 2008, 2012, 2010)]
    table = table_for(inp, corrections, ["RF", "SA"])
    json.dumps(table)
    assert "RF" in table["refused"] and str(table["refused"]["RF"]).strip()
    assert "RF" not in table["states"] and "SA" in table["states"]
    us = {(1, "RF"), (2, "RF"), (1, "SA"), (2, "SA")}
    rec = run_screen(all_false(us), us, set(), table, ["RF", "SA"], corrections)
    assert not any(q.split(" ")[0] in ("w", "rd") for q in deferrable(rec))
    assert deferrable(rec) == {"x assignment"}


def hand_table(moves):
    # A table written by hand, in the shape of brief section 6: one state, one question reaching 1:NA.
    return {"states": {"NA": {"state": "NA",
                              "questions": [{"question_id": "k date", "fid": "k", "question": "date",
                                             "settings": [2010, 2011], "utilities": ["1:NA"],
                                             "moves_anchoring": moves}],
                              "possible_hosts": [], "units": ["1:NA"]}},
            "refused": {}}


def test_moves_anchoring_unknown_means_retain():
    # Unknown (None) means retain (D-72 item 3; brief 4.2 and 4.7). With False the same question may be deferred.
    mask = all_false({(1, "NA")})
    rec = run_screen(mask, {(1, "NA")}, set(), hand_table(None), ["NA"], [])
    assert "k date" not in deferrable(rec) and "unknown" in reason(rec, "k date")
    rec = run_screen(mask, {(1, "NA")}, set(), hand_table(False), ["NA"], [])
    assert deferrable(rec) == {"k date"}


def test_retirable_questions_treats_none_as_retain():
    # The receiving end must keep a question whose moves_anchoring is None (brief section 6: corrected with the adapter).
    q = [{"question_id": "k date", "utilities": [(1, "NA")], "moves_anchoring": None}]
    out = availability.retirable_questions(q, {(1, "NA")})
    assert out["retirable"] == [] and "k date" in out["kept"]
    q = [{"question_id": "k date", "utilities": [(1, "NA")], "moves_anchoring": False}]
    assert availability.retirable_questions(q, {(1, "NA")})["retirable"] == ["k date"]


# ---- hosts -------------------------------------------------------------------------------------------------------------

def test_a_question_reaching_a_listed_host_that_fails_every_window_is_retained():
    # HA. x unresolved on 1, candidate 2, 1 MW from 2010; both bases 1,000,000 GWh. 1 is a listed host and fails every
    # window; 2 fails every window too. 1 is protected, never narrowed; 2 is narrowed. x reaches 1: retained, naming 1.
    inp = mini([{"fid": "x", "st": "HA", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.0,
                 "year": 2010}], {(1, "HA"): BIG, (2, "HA"): BIG})
    table = table_for(inp, [], ["HA"])
    us = {(1, "HA"), (2, "HA")}
    rec = run_screen(all_false(us), us, {(1, "HA")}, table, ["HA"], [])
    assert units(rec["narrowed"]) == {(2, "HA")}
    assert (1, "HA") in units(rec["protected"])
    r = reason(rec, "x assignment")
    assert "1:ha" in r and "host" in r


def possible_host_state():
    # HB. x unresolved on 3, candidate 4; 5 MW raw from 2008. Factor 1. On 3 it carries 5 x 8.76 = 43.8 GWh from 2010.
    # Utility 3's base is 100 GWh, so its host threshold is 2 GWh: the upper bound on its load reaches it (by far), and
    # 3 is a possible host. Utility 4's base is 1,000,000 GWh (threshold 20,000 GWh): not a possible host.
    return mini([{"fid": "x", "st": "HB", "u": 3, "cands": "3;4", "assign": "smallest_polygon", "raw": 5.0,
                  "year": 2008}], {(3, "HB"): 100.0, (4, "HB"): BIG})


def test_a_question_reaching_a_possible_host_that_fails_every_window_is_retained():
    inp = possible_host_state()
    table = table_for(inp, [], ["HB"])
    assert table["states"]["HB"]["possible_hosts"] == ["3:HB"]
    us = {(3, "HB"), (4, "HB")}
    rec = run_screen(all_false(us), us, set(), table, ["HB"], [])
    assert units(rec["narrowed"]) == {(4, "HB")}
    assert (3, "HB") in units(rec["protected"])
    r = reason(rec, "x assignment")
    assert "3:hb" in r and "possible host" in r


@pytest.mark.parametrize("state,protected_unit,other,hosts", [
    ("HA", (1, "HA"), (2, "HA"), {(1, "HA")}),
    ("HB", (3, "HB"), (4, "HB"), set()),
])
def test_a_protected_units_flags_change_nothing_about_its_questions(state, protected_unit, other, hosts):
    # For a fixed table, the protected unit's flags run through every pattern below while the other unit fails every
    # window. Protection does not consult flags (brief 4.5), so the protected set, the deferrable list and the reason
    # for x are the same every time: x is retained, naming the protected unit.
    if state == "HA":
        inp = mini([{"fid": "x", "st": "HA", "u": 1, "cands": "1;2", "assign": "smallest_polygon", "raw": 1.0,
                     "year": 2010}], {(1, "HA"): BIG, (2, "HA"): BIG})
    else:
        inp = possible_host_state()
    table = table_for(inp, [], [state])
    rng = np.random.default_rng(7)
    patterns = [every_year(True), every_year(False), every_year(True, except_years=(2015,)),
                every_year(True, drop=(2024,)), None]                       # None: the unit is absent from the mask
    patterns += [{y: bool(rng.random() < 0.7) for y in YEARS} for _ in range(4)]
    seen = set()
    for p in patterns:
        spec = {other: every_year(False)}
        if p is not None:
            spec[protected_unit] = p
        rec = run_screen(mask_of(spec), {protected_unit, other}, hosts, table, [state], [])
        seen.add((tuple(sorted(units(rec["protected"]))), tuple(sorted(rec["deferrable"])),
                  str(rec["retained"].get("x assignment"))))
    assert len(seen) == 1
    (prot, dfr, why), = seen
    assert protected_unit in prot and dfr == () and why != "None"


# ---- reopening (brief 4.8) ---------------------------------------------------------------------------------------------

def reopen_baseline():
    inp = shared_state()
    table = table_for(inp, SHARED_CORRECTIONS, ["SA", "DB"])
    mask = all_false(SHARED_UNITS)
    rec = run_screen(mask, SHARED_UNITS, set(), table, ["SA", "DB"], SHARED_CORRECTIONS)
    assert names(rec["fingerprints"]) == FINGERPRINTS
    assert deferrable(rec) == {"x assignment", "q date"}
    return inp, table, mask, rec


def reasons(rec, mask, table, *, identity=IDENTITY, pool=SHARED_UNITS, hosts=frozenset(), covered=("SA", "DB"),
            corrections=SHARED_CORRECTIONS, windows=None):
    out = adapter.reopen_reasons(rec, mask, identity, set(pool), set(hosts), table, list(covered), corrections,
                                 windows=windows)
    return names(out)


def test_no_change_names_nothing_and_a_stored_record_still_works():
    inp, table, mask, rec = reopen_baseline()
    assert reasons(rec, mask, table) == set()
    stored = json.loads(json.dumps(rec))
    assert reasons(stored, mask, table) == set()


def test_reopening_after_a_change_to_the_corrections():
    # A correction that changes no question, setting, dependency or protected unit: s, already resolved on 2:DB, is
    # assigned there by hand. Only the corrections fingerprint differs.
    inp, table, mask, rec = reopen_baseline()
    corrections = SHARED_CORRECTIONS + [{"fid": "s", "kind": "assign", "to": [2, "DB"]}]
    table2 = table_for(inp, corrections, ["SA", "DB"])
    assert reasons(rec, mask, table2, corrections=corrections) == {"corrections"}


def test_reopening_after_a_change_to_a_candidate_list():
    # x's candidates in the inventory become 1;2;9, where 9 is not a panel unit in SA. Its settings become 1, 2, 9,
    # off the panel; the utilities it reaches stay 1 and 2. The candidates fingerprint differs; the dependencies one
    # may too, if it carries the settings. Nothing else.
    _, _, mask, rec = reopen_baseline()
    inp2 = shared_state(cands="1;2;9")
    table2 = table_for(inp2, SHARED_CORRECTIONS, ["SA", "DB"])
    assert question(table2, "SA", "x assignment")["settings"] == [1, 2, 9, "off_panel"]
    got = reasons(rec, mask, table2)
    assert "candidates" in got and got <= {"candidates", "dependencies"}


def test_reopening_after_a_change_to_a_dependency():
    # 2:SA's base drops to 400 GWh: its threshold is 8 GWh and x on it carries 8.76 GWh from 2012, so 2:SA becomes a
    # possible host. Questions and settings are unchanged; the protected units in the dependency table change.
    _, _, mask, rec = reopen_baseline()
    inp2 = shared_state(base2=400.0)
    table2 = table_for(inp2, SHARED_CORRECTIONS, ["SA", "DB"])
    assert table2["states"]["SA"]["possible_hosts"] == ["2:SA"]
    assert reasons(rec, mask, table2) == {"dependencies"}


def test_reopening_after_a_change_to_the_masks_rows():
    # One flag flipped (1:SA, 2010, now usable). 1:SA still fails every window, so nothing about the narrowing moves,
    # but the rows differ: the mask identity fingerprint differs.
    _, table, mask, rec = reopen_baseline()
    mask2 = mask.copy()
    hit = (mask2.utility_id_eia == 1) & (mask2.state == "SA") & (mask2.year == 2010)
    mask2.loc[hit, "usable"] = True
    assert reasons(rec, mask2, table) == {"mask identity"}


def test_reopening_after_a_change_to_the_masks_stated_identity():
    _, table, mask, rec = reopen_baseline()
    assert reasons(rec, mask, table, identity={**IDENTITY, "run": "run-2"}) == {"mask identity"}


def test_reopening_after_a_change_to_a_window():
    _, table, mask, rec = reopen_baseline()
    windows = {k: tuple(v) for k, v in availability.permitted_windows().items()}
    windows["cohort_2016"] = tuple(range(2010, 2019))
    assert reasons(rec, mask, table, windows=windows) == {"eligibility rules"}


def test_reopening_after_a_change_to_the_pool():
    _, table, mask, rec = reopen_baseline()
    assert reasons(rec, mask, table, pool=SHARED_UNITS - {(2, "DB")}) == {"eligibility rules"}


def test_reopening_after_a_change_to_the_listed_hosts():
    _, table, mask, rec = reopen_baseline()
    got = reasons(rec, mask, table, hosts={(2, "DB")})
    assert "eligibility rules" in got and got <= {"eligibility rules", "dependencies"}


def test_reopening_after_a_change_to_the_covered_states():
    _, table, mask, rec = reopen_baseline()
    got = reasons(rec, mask, table, covered=("SA",))
    assert "eligibility rules" in got and got <= {"eligibility rules", "candidates", "dependencies"}
