"""The dependency adapter (docs/gate1/dependency-adapter-brief-2026-11-18.md; D-72 item 3; D-83).

Invented data only. Every inventory here is made up with `mini()` from tests/test_pass_c_expand.py and every mask is
made up in the test. Nothing under data/ is opened, and no availability mask on disk is read, listed or hashed.

These are the session's own tests of the adapter it wrote. The independent check (a brute-force evaluator and toy
cases worked by hand from the brief alone, by an agent that never saw the adapter) is in tests/adapter_evaluator.py,
tests/test_adapter_evaluator.py, tests/test_adapter_toy_cases.py and tests/test_adapter_against_evaluator.py.
"""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline.analysis import availability as avail  # noqa: E402
from pipeline.analysis import availability_adapter as adapter  # noqa: E402
from pipeline.facilities import pass_c_exact  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import GWH, anchoring_world, date, mini, split, world  # noqa: E402

PANEL = range(2001, 2026)
IDENT = {"run": "r" * 32, "audit_attempt": "a" * 32, "definition": "made-up.1", "mask_sha256": "0" * 64}
BIG = 1e6                                   # a base no made-up load here comes near: 2% of it is 20,000 GWh


def mask_of(units, missing=(), absent=()):
    """Every unit usable in every panel year, except `missing` (unit, state, year) rows flagged not usable and
    `absent` rows left out of the mask altogether."""
    missing, absent = set(missing), set(absent)
    rows = [(u, s, y, (u, s, y) not in missing) for u, s in units for y in PANEL if (u, s, y) not in absent]
    return pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "usable"])


def all_years(unit):
    return [(unit[0], unit[1], y) for y in PANEL]


def zz():
    """State ZZ. Utilities 10 to 13 are far too large for any load here to matter to them; 14 is a host.

      x: 2 MW, unresolved between 10 and 11 (an assignment question: on 10, on 11, off the panel).
      d: 1 MW on 12, start between 2008 and 2012: full load in 2024 whichever year, so the anchoring does not move.
      e: 1 MW on 13, start between 2021 and 2025: its 2024 load is full, full, two thirds, one third or nothing.
      h: 5 MW on 14 from 2012, and 14's base makes 2.5 MW its 2% threshold: it crosses.
      y: 1 MW, unresolved between 14 and 11.
    """
    sites = [{"fid": "x", "st": "ZZ", "u": 10, "cands": "10;11", "assign": "smallest_polygon", "raw": 2.0, "year": 2010},
             {"fid": "d", "st": "ZZ", "u": 12, "raw": 1.0, "year": 2010},
             {"fid": "e", "st": "ZZ", "u": 13, "raw": 1.0, "year": 2021},
             {"fid": "h", "st": "ZZ", "u": 14, "raw": 5.0, "year": 2012},
             {"fid": "y", "st": "ZZ", "u": 14, "cands": "14;11", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}]
    bases = {(10, "ZZ"): BIG, (11, "ZZ"): BIG, (12, "ZZ"): BIG, (13, "ZZ"): BIG, (14, "ZZ"): 2.5 * GWH / 0.02}
    return mini(sites, bases)


ZZ_CORRECTIONS = [date("d", 2008, 2012, 2010), date("e", 2021, 2025, 2021)]
ZZ_UNITS = [(u, "ZZ") for u in (10, 11, 12, 13, 14)]
ZZ_POOL = [(u, "ZZ") for u in (10, 11, 12, 13)]


def zz_table(corrections=ZZ_CORRECTIONS):
    inp = zz()
    return adapter.dependency_table(inp, px.parse_corrections(corrections, inp), ["ZZ"])


def by_id(table, st="ZZ"):
    return {q["question_id"]: q for q in table["states"][st]["questions"]}


def run(mask, pool=ZZ_POOL, hosts=(), table=None, covered=("ZZ",), corrections=ZZ_CORRECTIONS, windows=None):
    table = zz_table() if table is None else table
    return adapter.screen(mask, IDENT, pool, hosts, table, covered, corrections, windows)


# ---- the table: direct reach and anchoring, from loads and contributions alone -------------------------------------

def test_the_table_lists_every_question_with_what_it_reaches_and_whether_it_moves_the_anchoring():
    t = zz_table()
    assert t["refused"] == {}
    q = by_id(t)
    assert set(q) == {"x assignment", "d date", "e date", "y assignment"}
    assert q["x assignment"]["utilities"] == ["10:ZZ", "11:ZZ"] and q["x assignment"]["moves_anchoring"] is False
    assert q["x assignment"]["settings"] == [10, 11, "off_panel"]
    assert q["d date"]["utilities"] == ["12:ZZ"] and q["d date"]["moves_anchoring"] is False
    assert q["d date"]["settings"] == [2008, 2009, 2010, 2011, 2012]
    assert q["e date"]["utilities"] == ["13:ZZ"] and q["e date"]["moves_anchoring"] is True
    assert q["y assignment"]["utilities"] == ["11:ZZ", "14:ZZ"] and q["y assignment"]["moves_anchoring"] is False
    assert t["states"]["ZZ"]["possible_hosts"] == ["14:ZZ"]
    assert t["states"]["ZZ"]["units"] == ["10:ZZ", "11:ZZ", "12:ZZ", "13:ZZ", "14:ZZ"]
    json.dumps(t)


def test_a_question_moves_the_anchoring_even_where_the_factor_cannot_move():
    """Direct anchoring dependencies (D-72 item 3): read from the contributions, not from the factor or a classification.

    EPRI is set so high that the factor sits at its cap of 3.0 in every setting. The conservative joint check then
    closes the factor channel, rightly for its purpose: no question reaches anyone through a factor that is one number.
    The adapter still says the date question moves the anchoring, because its 2024 contribution differs, and retains it.
    """
    sites = [{"fid": "e", "st": "CP", "u": 30, "raw": 1.0, "year": 2021},
             {"fid": "o", "st": "CP", "u": 31, "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(30, "CP"): BIG, (31, "CP"): BIG}, epri={"CP": 100.0})
    corrections = [date("e", 2021, 2025, 2021)]
    corr = px.parse_corrections(corrections, inp)
    jc = px.joint_check(inp, corr, "CP")
    assert jc["factor_range"]["low"] == jc["factor_range"]["high"] == px.SCALE_HI
    assert jc["utilities"]["31:CP"]["can_affect"] == []                 # nothing reaches 31, through load or factor
    t = adapter.dependency_table(inp, corr, ["CP"])
    assert by_id(t, "CP")["e date"]["moves_anchoring"] is True
    units = [(30, "CP"), (31, "CP")]
    r = adapter.screen(mask_of(units, all_years((30, "CP")) + all_years((31, "CP"))), IDENT, units, [], t, ["CP"], corrections)
    assert r["narrowed"] == ["30:CP", "31:CP"]                           # both fail every window
    assert r["deferrable"] == [] and r["retained"] == {"e date": adapter.MOVES}


def test_a_contribution_that_is_not_a_number_is_unknown_and_unknown_is_retained(monkeypatch):
    inp = zz()
    corr = px.parse_corrections(ZZ_CORRECTIONS, inp)
    real = px._sites

    def broken(*a, **k):
        sites, no_load, removed = real(*a, **k)
        for s in sites:
            if s.fid == "d":
                s.a = s.a.astype(float)
                s.a[0] = np.nan
        return sites, no_load, removed

    monkeypatch.setattr(px, "_sites", broken)
    t = adapter.dependency_table(inp, corr, ["ZZ"])
    assert by_id(t)["d date"]["moves_anchoring"] is None
    r = run(mask_of(ZZ_UNITS, all_years((12, "ZZ"))), table=t)
    assert "12:ZZ" in r["narrowed"] and r["retained"]["d date"] == adapter.UNKNOWN and "d date" not in r["deferrable"]


def test_a_dependency_that_shows_only_under_another_questions_setting_is_found(monkeypatch):
    """A site with two questions, built by hand so that each effect shows only when the OTHER question is away from its
    first setting. The site is on 10, on 11 or off the panel, and starts in 2010 or 2011.

      load: on 10 the start year changes nothing; on 11 it doubles the load. So the date question reaches 11 and not
            10, and that shows only in the rows where the assignment is 11 (the second group of three).
      2024 contribution: 1 everywhere except off the panel with the later start, where it is 2. So the date question
            moves the anchoring, and that shows only in the third group; and the assignment question moves it too,
            which shows only among the rows with the later start.
    """
    inp = zz()
    ones = np.ones(len(px.YEARS))
    hand = px._Site(fid="t", kind="permit", questions=["assignment", "date"], values=[[10, 11, None], [2010, 2011]],
                    idx=np.array([[0, 0], [0, 1], [1, 0], [1, 1], [2, 0], [2, 1]]),
                    unit=[(10, "ZZ"), (10, "ZZ"), (11, "ZZ"), (11, "ZZ"), None, None],
                    load=np.vstack([ones, ones, ones, 2 * ones, ones, 2 * ones]), a=np.array([1.0, 1.0, 1.0, 1.0, 1.0, 2.0]))
    monkeypatch.setattr(px, "_sites", lambda *a, **k: ([hand], [], 0.0))
    q = {x["question_id"]: x for x in adapter.state_dependencies(inp, {}, "ZZ")["questions"]}
    assert q["t date"]["utilities"] == ["11:ZZ"] and q["t date"]["moves_anchoring"] is True
    assert q["t assignment"]["utilities"] == ["10:ZZ", "11:ZZ"] and q["t assignment"]["moves_anchoring"] is True
    # The same site with the off-panel contribution level: neither question moves the anchoring.
    hand.a = np.ones(6)
    q = {x["question_id"]: x for x in adapter.state_dependencies(inp, {}, "ZZ")["questions"]}
    assert q["t date"]["moves_anchoring"] is False and q["t assignment"]["moves_anchoring"] is False


def test_a_date_on_an_unresolved_site_reaches_every_utility_the_site_can_be_on():
    sites = [{"fid": "z", "st": "ZY", "u": 10, "cands": "10;11", "assign": "smallest_polygon", "raw": 2.0, "year": 2010},
             {"fid": "o", "st": "ZY", "u": 12, "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(10, "ZY"): BIG, (11, "ZY"): BIG, (12, "ZY"): BIG})
    corrections = [date("z", 2008, 2012, 2010)]
    t = adapter.dependency_table(inp, px.parse_corrections(corrections, inp), ["ZY"])
    q = by_id(t, "ZY")
    assert q["z date"]["utilities"] == ["10:ZY", "11:ZY"] and q["z date"]["moves_anchoring"] is False
    assert q["z assignment"]["utilities"] == ["10:ZY", "11:ZY"]
    units = [(10, "ZY"), (11, "ZY"), (12, "ZY")]
    r = adapter.screen(mask_of(units, all_years((10, "ZY"))), IDENT, units, [], t, ["ZY"], corrections)
    assert r["deferrable"] == [] and "11:ZY (passes " in r["retained"]["z date"]       # 11 is on the site's list and passes
    r = adapter.screen(mask_of(units, all_years((10, "ZY")) + all_years((11, "ZY"))), IDENT, units, [], t, ["ZY"], corrections)
    assert r["deferrable"] == ["z assignment", "z date"]


def test_the_receiving_end_retains_a_null_anchoring_flag():
    """D-72 item 3: null or unknown means retain. Before 2026-11-18 a None was read as "does not move"."""
    narrowed = {(3, "AA")}
    for unknown in (None, "no", 0, 1, np.nan):
        r = avail.retirable_questions([{"question_id": "q", "utilities": [(3, "AA")], "moves_anchoring": unknown}], narrowed)
        assert r["retirable"] == [] and "q" in r["kept"], unknown
    r = avail.retirable_questions([{"question_id": "q", "utilities": [(3, "AA")]}], narrowed)
    assert r["retirable"] == []
    r = avail.retirable_questions([{"question_id": "q", "utilities": [(3, "AA")], "moves_anchoring": False}], narrowed)
    assert r["retirable"] == ["q"]


# ---- the screen: shared questions, all relevant questions, the pool, the hosts -------------------------------------

def test_a_question_is_deferred_only_when_every_utility_it_reaches_is_narrowed():
    fail = lambda *us: [r for u in us for r in all_years((u, "ZZ"))]  # noqa: E731
    r = run(mask_of(ZZ_UNITS, fail(10, 12, 13)))
    assert r["narrowed"] == ["10:ZZ", "12:ZZ", "13:ZZ"]
    assert r["deferrable"] == ["d date"]
    assert r["retained"]["x assignment"].startswith(adapter.NOT_NARROWED + "11:ZZ (passes ")     # shared with 11
    assert r["retained"]["e date"] == adapter.MOVES                                               # though 13 is narrowed
    assert "14:ZZ (a possible host)" in r["retained"]["y assignment"] and "11:ZZ (passes " in r["retained"]["y assignment"]
    # With 11 narrowed too, the shared question x goes; y still reaches 14.
    r = run(mask_of(ZZ_UNITS, fail(10, 11, 12, 13)))
    assert r["deferrable"] == ["d date", "x assignment"]
    assert r["retained"]["y assignment"] == adapter.NOT_NARROWED + "14:ZZ (a possible host)"
    json.dumps(r)


def test_a_question_that_changes_no_ones_place_is_still_retained_for_a_utility_that_passes_a_window():
    """All relevant questions, not only kept ones. x is 2 MW against utilities of a million GWh: the exact attribution
    keeps it for no one, and it is relevant to both. With 11 usable it is retained."""
    inp = zz()
    corr = px.parse_corrections(ZZ_CORRECTIONS, inp)
    ex = pass_c_exact.exact_attribution(inp, corr, "ZZ")
    for key in ("10:ZZ", "11:ZZ"):
        u = ex["utilities"][key]
        assert {"fid": "x", "question": "assignment"} not in [{"fid": q["fid"], "question": q["question"]} for q in u["kept_questions"]]
        assert "x" in [q["fid"] for q in u["relevant_questions"]]
    r = run(mask_of(ZZ_UNITS, all_years((10, "ZZ"))))
    assert "x assignment" in r["retained"] and "x assignment" not in r["deferrable"]


def test_a_unit_outside_the_pool_is_never_narrowed_whatever_its_flags():
    r = run(mask_of(ZZ_UNITS, all_years((12, "ZZ"))), pool=[(10, "ZZ"), (11, "ZZ"), (13, "ZZ")])
    assert "12:ZZ" not in r["narrowed"]
    assert r["retained"]["d date"] == adapter.NOT_NARROWED + "12:ZZ (not in the pool)"


def test_a_listed_host_and_a_possible_host_are_never_narrowed_and_their_questions_never_deferred():
    everything_fails = [r for u in ZZ_UNITS for r in all_years(u)]
    r = run(mask_of(ZZ_UNITS, everything_fails), pool=ZZ_UNITS, hosts=[(10, "ZZ")])
    assert r["protected"] == {"10:ZZ": "a listed host", "14:ZZ": "a possible host"}
    assert r["narrowed"] == ["11:ZZ", "12:ZZ", "13:ZZ"]
    assert r["retained"]["x assignment"] == adapter.NOT_NARROWED + "10:ZZ (a listed host)"
    assert r["retained"]["y assignment"] == adapter.NOT_NARROWED + "14:ZZ (a possible host)"
    assert r["deferrable"] == ["d date"]


def test_no_flag_of_any_unit_changes_who_is_protected_or_frees_a_question_that_reaches_a_protected_unit():
    """Availability must not change host verification effort (D-72 item 3; D-83). Over many made-up masks."""
    t = zz_table()
    rng = np.random.default_rng(20261118)
    seen = set()
    for i in range(60):
        flags = rng.random((len(ZZ_UNITS), len(PANEL))) < rng.choice([0.0, 0.2, 0.8, 1.0])
        missing = [(u, s, y) for (u, s), row in zip(ZZ_UNITS, flags) for y, bad in zip(PANEL, row) if bad]
        absent = missing[:: 3] if i % 2 else []
        r = run(mask_of(ZZ_UNITS, missing, absent), pool=ZZ_UNITS, hosts=[(10, "ZZ")], table=t)
        assert r["protected"] == {"10:ZZ": "a listed host", "14:ZZ": "a possible host"}
        assert "10:ZZ" not in r["narrowed"] and "14:ZZ" not in r["narrowed"]
        assert "x assignment" in r["retained"] and "y assignment" in r["retained"] and "e date" in r["retained"]
        seen.add(tuple(r["deferrable"]))
    assert seen == {(), ("d date",)}                                      # only d ever moves, and only with 12's flags


# ---- windows and missing years --------------------------------------------------------------------------------------

def narrowed_and_why(missing=(), absent=()):
    r = run(mask_of(ZZ_UNITS, missing, absent))
    return "12:ZZ" in r["narrowed"], r["not_narrowed"].get("12:ZZ", "")


def test_windows_and_missing_years():
    k = (12, "ZZ")
    every = [f"cohort_{g}" for g in range(2011, 2023)] + ["second_estimate_long_difference", "second_estimate_panel"]
    assert narrowed_and_why() == (False, "passes " + ", ".join(every))
    # 2012 sits in the ten years g-6..g+3 of cohorts 2011 to 2018 and in the panel form; cohorts 2019 to 2022 start
    # in 2013 or later, and the long difference does not use 2012.
    assert narrowed_and_why([(*k, 2012)]) == (False, "passes cohort_2019, cohort_2020, cohort_2021, cohort_2022, "
                                                     "second_estimate_long_difference")
    # 2005 kills cohort 2011 (2005-2014) and the panel form; 2016 kills cohorts 2013 to 2022; 2025 kills the long
    # difference. Cohort 2012's window, 2006 to 2015, is the one left.
    gone = [(*k, 2005), (*k, 2016), (*k, 2025)]
    assert narrowed_and_why(gone) == (False, "passes cohort_2012")
    # The same years left out of the mask altogether count the same as flagged not usable.
    assert narrowed_and_why(absent=gone) == (False, "passes cohort_2012")
    # One more year inside 2006 to 2015 and nothing is left: narrowed.
    assert narrowed_and_why(gone + [(*k, 2010)]) == (True, "")
    assert narrowed_and_why(absent=gone + [(*k, 2010)]) == (True, "")
    # A unit absent from the mask altogether passes no window.
    assert narrowed_and_why(absent=all_years(k)) == (True, "")
    # Usable only in the long difference's six years: not narrowed.
    only_long = [(*k, y) for y in PANEL if y not in (2008, 2009, 2010, 2023, 2024, 2025)]
    assert narrowed_and_why(only_long) == (False, "passes second_estimate_long_difference")


def test_a_mask_that_is_malformed_or_unidentified_is_refused():
    m = mask_of(ZZ_UNITS)
    t = zz_table()
    with pytest.raises(ValueError, match="two rows"):
        adapter.screen(pd.concat([m, m.iloc[:1]]), IDENT, ZZ_POOL, [], t, ["ZZ"], ZZ_CORRECTIONS)
    bad = m.astype({"usable": object})
    bad.loc[3, "usable"] = None
    with pytest.raises(ValueError, match="missing value"):
        adapter.screen(bad, IDENT, ZZ_POOL, [], t, ["ZZ"], ZZ_CORRECTIONS)
    with pytest.raises(ValueError, match="no column"):
        adapter.screen(m.drop(columns="usable"), IDENT, ZZ_POOL, [], t, ["ZZ"], ZZ_CORRECTIONS)
    for field in adapter.MASK_IDENTITY_FIELDS:
        with pytest.raises(ValueError, match="not identified"):
            adapter.screen(m, {**IDENT, field: ""}, ZZ_POOL, [], t, ["ZZ"], ZZ_CORRECTIONS)


# ---- coverage --------------------------------------------------------------------------------------------------------

def test_nothing_is_deferred_and_no_one_is_narrowed_outside_the_named_coverage():
    everything_fails = [r for u in ZZ_UNITS for r in all_years(u)]
    r = run(mask_of(ZZ_UNITS, everything_fails), covered=())
    assert r["deferrable"] == [] and r["narrowed"] == []
    assert set(r["retained"].values()) == {adapter.OUTSIDE} and len(r["retained"]) == 4
    assert all("outside the attribution's coverage" in v for v in r["not_narrowed"].values())
    # Naming a state the table does not hold covers nothing either.
    r = run(mask_of(ZZ_UNITS, everything_fails), covered=("QQ",))
    assert r["deferrable"] == [] and r["narrowed"] == []


def test_a_state_whose_table_is_refused_is_not_covered():
    # An unresolved row with a size, a start year and candidates but on no utility: the pass's own code refuses it.
    sites = [{"fid": "bad", "st": "RR", "u": None, "cands": "20;21", "assign": "smallest_polygon", "raw": 1.0, "year": 2010},
             {"fid": "k", "st": "RR", "u": 20, "cands": "20;21", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}]
    inp = mini(sites, {(20, "RR"): BIG, (21, "RR"): BIG})
    t = adapter.dependency_table(inp, {}, ["RR"])
    assert t["states"] == {} and "RR" in t["refused"] and "on no utility" in t["refused"]["RR"]
    units = [(20, "RR"), (21, "RR")]
    r = adapter.screen(mask_of(units, all_years(units[0]) + all_years(units[1])), IDENT, units, [], t, ["RR"], [])
    assert r["deferrable"] == [] and r["narrowed"] == [] and r["refused_states"] == t["refused"]


# ---- reopening -------------------------------------------------------------------------------------------------------

def test_any_change_to_what_a_screen_rests_on_voids_it_and_names_what_changed():
    t = zz_table()
    m = mask_of(ZZ_UNITS, all_years((12, "ZZ")))
    record = run(m, table=t)
    assert record["deferrable"] == ["d date"]
    args = dict(mask=m, mask_identity=IDENT, pool=ZZ_POOL, hosts=[], table=t, covered_states=["ZZ"],
                corrections=ZZ_CORRECTIONS, windows=None)

    def reasons(**change):
        return adapter.reopen_reasons(record, **{**args, **change})

    assert reasons() == []
    assert reasons(pool=list(reversed(ZZ_POOL))) == []                                  # the same pool in another order
    assert reasons(mask=m.sample(frac=1, random_state=7).reset_index(drop=True)) == []  # the same rows in another order
    # corrections: one more, or one changed
    assert reasons(corrections=ZZ_CORRECTIONS + [{"fid": "h", "kind": "assign", "to": [14, "ZZ"]}]) == ["corrections"]
    assert reasons(corrections=[date("d", 2008, 2013, 2010), ZZ_CORRECTIONS[1]]) == ["corrections"]
    # candidates: a site's list of settings changes
    t2 = copy.deepcopy(t)
    by_id(t2)["x assignment"]["settings"].insert(2, 12)
    assert reasons(table=t2) == ["candidates"]
    # dependencies: a question reaches one more utility, or its anchoring flag changes, or a unit becomes a possible host
    t3 = copy.deepcopy(t)
    by_id(t3)["d date"]["utilities"].append("13:ZZ")
    assert reasons(table=t3) == ["dependencies"]
    t4 = copy.deepcopy(t)
    by_id(t4)["d date"]["moves_anchoring"] = True
    assert reasons(table=t4) == ["dependencies"]
    t5 = copy.deepcopy(t)
    t5["states"]["ZZ"]["possible_hosts"].append("12:ZZ")
    assert reasons(table=t5) == ["dependencies"]
    # the real thing: a new correction rebuilds the table, and both the corrections and the candidates differ
    changed = [date("d", 2008, 2013, 2010), ZZ_CORRECTIONS[1]]
    assert reasons(corrections=changed, table=zz_table(changed)) == ["corrections", "candidates"]
    # mask identity: one flag, or what the caller says identifies the mask
    m2 = m.copy()
    m2.loc[(m2.utility_id_eia == 11) & (m2.year == 2015), "usable"] = False
    assert reasons(mask=m2) == ["mask_identity"]
    for field in adapter.MASK_IDENTITY_FIELDS:
        assert reasons(mask_identity={**IDENT, field: "other"}) == ["mask_identity"]
    # eligibility rules: a window, the pool, the listed hosts, the covered states
    w = avail.permitted_windows()
    w["cohort_2011"] = tuple(range(2004, 2015))
    assert reasons(windows=w) == ["eligibility_rules"]
    assert reasons(pool=ZZ_POOL[:-1]) == ["eligibility_rules"]
    assert reasons(hosts=[(10, "ZZ")]) == ["eligibility_rules"]
    assert reasons(covered_states=["ZZ", "QQ"]) == ["eligibility_rules"]
    assert reasons(covered_states=[]) == ["candidates", "dependencies", "eligibility_rules"]
    # a record with no fingerprints stands for nothing
    assert adapter.reopen_reasons({}, **args) == list(adapter.FINGERPRINTS)


def test_the_host_threshold_is_part_of_the_eligibility_rules():
    """The agent's independent read found that the brief's interface gave the threshold no way into a fingerprint.
    Each state's table carries the threshold it was built at, and the eligibility-rules fingerprint hashes it."""
    inp = zz()
    corr = px.parse_corrections(ZZ_CORRECTIONS, inp)
    m = mask_of(ZZ_UNITS)
    t = adapter.dependency_table(inp, corr, ["ZZ"])
    record = run(m, table=t)
    # A threshold of one part in a million (1 GWh of a base of a million): every utility that can carry a site becomes
    # a possible host, and the rule has changed.
    lower = adapter.dependency_table(inp, corr, ["ZZ"], theta=1e-6)
    assert lower["states"]["ZZ"]["theta"] == 1e-6 and lower["states"]["ZZ"]["possible_hosts"] == t["states"]["ZZ"]["units"]
    assert adapter.reopen_reasons(record, m, IDENT, ZZ_POOL, [], lower, ["ZZ"], ZZ_CORRECTIONS) == ["dependencies", "eligibility_rules"]
    # The threshold alone, with the same table otherwise.
    same = copy.deepcopy(t)
    same["states"]["ZZ"]["theta"] = 0.03
    assert adapter.reopen_reasons(record, m, IDENT, ZZ_POOL, [], same, ["ZZ"], ZZ_CORRECTIONS) == ["eligibility_rules"]


def test_the_rule_version_is_part_of_the_eligibility_rules(monkeypatch):
    t = zz_table()
    m = mask_of(ZZ_UNITS)
    record = run(m, table=t)
    monkeypatch.setattr(adapter, "RULE_VERSION", "later")
    assert adapter.reopen_reasons(record, m, IDENT, ZZ_POOL, [], t, ["ZZ"], ZZ_CORRECTIONS) == ["eligibility_rules"]


# ---- what the adapter does not depend on ----------------------------------------------------------------------------

def test_the_table_is_the_same_whatever_convention_a_question_carries():
    """No reference is used (brief, section 5): a convention, another convention, a provisional one or none at all
    give the same table. So the reference repair of D-72 item 4 is not one of the adapter's dependencies."""
    base = zz_table([date("d", 2008, 2012, 2010), date("e", 2021, 2025, 2021)])
    for d_conv, e_conv, provisional in ((2008, 2025, False), (2012, 2023, False), (None, None, False), (2010, 2021, True)):
        d, e = date("d", 2008, 2012, d_conv), date("e", 2021, 2025, e_conv)
        if provisional:
            d["convention_is"] = e["convention_is"] = "provisional"
        assert zz_table([d, e]) == base, (d_conv, e_conv, provisional)


def test_the_screen_never_reads_the_exact_attribution(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the adapter called the exact attribution")
    monkeypatch.setattr(pass_c_exact, "exact_attribution", boom)
    monkeypatch.setattr(pass_c_exact, "_exact", boom)
    assert run(mask_of(ZZ_UNITS, all_years((12, "ZZ"))))["deferrable"] == ["d date"]


# ---- agreement with the pass's own two checks, on made-up states ---------------------------------------------------

def worlds():
    two_of_four = ([{"fid": f"a{i}", "st": "CC", "u": 5, "cands": "5;6", "assign": "smallest_polygon", "raw": 1.0, "year": 2010}
                    for i in range(1, 5)] + [{"fid": "r6", "st": "CC", "u": 6, "raw": 1.0, "year": 2010}])
    floor = [{"fid": "x", "st": "EE", "u": 10, "cands": "10;11;12", "assign": "smallest_polygon", "raw": 2.0, "year": 2010}]
    yield "ZZ", zz(), ZZ_CORRECTIONS
    yield "DD", anchoring_world(), [date("q1", 2016, 2024, 2016)]
    yield "DD", anchoring_world(), [date("q1", 2016, 2026, 2016, never=True)]
    yield "CC", mini(two_of_four, {(5, "CC"): 1.5 * GWH / 0.02, (6, "CC"): 1e6}), []
    yield "EE", mini(floor, {(10, "EE"): 1e3, (11, "EE"): 2 * GWH / 0.01, (12, "EE"): 1e6}), []
    yield "AA", world(), [{"fid": "p1", "kind": "reopen", "candidates": [1, 2]}, split("p3", 2012, 0.5, rest_earliest=2014)]


def test_the_table_agrees_with_the_exact_attributions_relevance_and_the_joint_checks_reach():
    """Three pieces of code, written apart, on the same made-up states. For every utility:
    what the adapter says reaches it directly is within what each of the pass's checks calls relevant or able to affect
    it, and everything they list beyond that is a question the adapter says moves the anchoring."""
    n = 0
    for st, inp, corrections in worlds():
        corr = px.parse_corrections(corrections, inp)
        dep = adapter.state_dependencies(inp, corr, st)
        jc = px.joint_check(inp, corr, st)
        ex = pass_c_exact.exact_attribution(inp, corr, st)
        reach = {q["question_id"]: set(q["utilities"]) for q in dep["questions"]}
        moving = {q["question_id"] for q in dep["questions"] if q["moves_anchoring"]}
        assert all(isinstance(q["moves_anchoring"], bool) for q in dep["questions"])
        assert set(reach) == {f"{q['fid']} {q['question']}" for q in jc["questions"]}          # the same question universe
        assert {q["question_id"]: len(q["settings"]) for q in dep["questions"]} == \
               {f"{q['fid']} {q['question']}": q["settings"] for q in jc["questions"]}
        for key in dep["units"]:
            direct = {qid for qid, us in reach.items() if key in us}
            relevant = {f"{q['fid']} {q['question']}" for q in ex["utilities"][key]["relevant_questions"]}
            can = {f"{q['fid']} {q['question']}" for q in jc["utilities"][key]["can_affect"]}
            assert direct <= relevant <= direct | moving, (st, key)
            assert direct <= can <= direct | moving, (st, key)
            n += 1
    assert n == 19                                    # every utility of the six made-up states: 5 + 3 + 3 + 2 + 3 + 3


def test_every_utility_the_pass_can_find_a_crossing_for_is_a_possible_host():
    for st, inp, corrections in worlds():
        corr = px.parse_corrections(corrections, inp)
        dep = adapter.state_dependencies(inp, corr, st)
        ex = pass_c_exact.exact_attribution(inp, corr, st)
        for key, u in ex["utilities"].items():
            crossings = {u["reference"]["crossing"]} | {w[side]["detail"][c] for q in u["kept_questions"] if "witness" in q
                                                         for w in [q["witness"]] for side in ("a", "b")
                                                         for c in ("crossing_as_built", "crossing_no_anchoring")}
            if crossings - {None, "never"}:
                assert key in dep["possible_hosts"], (st, key, crossings)
