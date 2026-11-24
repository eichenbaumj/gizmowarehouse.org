"""The dependency adapter against the brute-force evaluator (docs/gate1/dependency-adapter-brief-2026-11-18.md, 7.4).

Written to the interface of the brief's section 6 by an author who has not seen the adapter; it cannot run where it
was written. Invented data only: made-up states built with `world()` and `mini()` from tests/test_pass_c_expand.py,
each small enough for the full product (at most a couple of hundred configurations), and made-up masks (all usable,
none usable, and seeded random ones), each a small DataFrame made up here.

For each state and mask:
  * the adapter's questions are exactly the evaluator's (brief 4.3: all relevant questions), with the same settings;
  * the adapter's `utilities` for each question contain the evaluator's `reaches`;
  * `moves_anchoring` agrees exactly;
  * every unit the evaluator finds can cross the host threshold is among the adapter's possible hosts;
  * the narrowed set is exactly brief 4.6, worked out here from the mask with this file's own windows;
  * the deferrable set is exactly brief 4.7 applied to the adapter's own table and narrowed set, and is a subset of
    what 4.7 gives on the evaluator's `reaches`;
  * `violations(...)` is empty: the guarantee of brief section 2 holds on the full product;
  * no question that reaches a listed host, a possible host or a unit that can cross is ever deferrable.

Readings: `pool` and `hosts` are passed as sets of (utility_id_eia, state) tuples; units the adapter returns are
normalised from "<utility_id_eia>:<state>" or tuples. An assignment question's off-panel setting is None in the
evaluator and "off_panel" in the adapter.
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

import adapter_evaluator as ev  # noqa: E402
from pipeline.analysis import availability_adapter as adapter  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import mini, world  # noqa: E402

YEARS = list(range(2001, 2026))
# The four field names are the adapter's (MASK_IDENTITY_FIELDS). The brief did not fix them and this file first used
# run_id, definition_version and mask_file_hash; the session renamed them on 2026-11-18. No value or expectation changed.
IDENTITY = {"run": "run-1", "audit_attempt": "attempt-1", "definition": "def-1", "mask_sha256": "hash-1"}
# world()'s own sizes put utility 3's as-built load exactly on its threshold in one setting; these sizes keep every
# load well away from every threshold (checked: the evaluator's near_ties is empty for each state below).
WORLD_RAW = {"p1": 4.2, "p2": 2.3, "p3": 2.1}
GWH = 8.76


def date(fid, earliest, latest, convention, never=False):
    return {"fid": fid, "kind": "date", "earliest": earliest, "latest": latest, "never_is_possible": never,
            "convention": convention}


def split(fid, first, share, rest_earliest=None, convention=None):
    c = {"fid": fid, "kind": "capacity_split", "first_phase_year": first, "first_share": share, "convention": convention}
    if rest_earliest is not None:
        c["rest_earliest"] = rest_earliest
    return c


def big_world():
    # world() with utilities 1 and 2 given bases of 100,000 GWh, so neither can come near the host threshold (2,000
    # GWh) and questions that reach only them can be deferred when both are narrowed. Utility 3 keeps its small base.
    inp = world(WORLD_RAW)
    inp.base.loc[(1, "AA")] = 1e5
    inp.base.loc[(2, "AA")] = 1e5
    return inp


def held_factor_state():
    # HF: EPRI 0, so the factor is 0.2 in every configuration (the permit total is never zero: e8 alone is 2 MW).
    # a: unresolved on 5 (candidate 6), 2 MW from 2010. b: unresolved on 6 (candidates 7 and 99, 99 not a panel unit),
    # 1.5 MW from 2012. m: a measured figure on 7, 3 MW, inventory year 2021, date 2021 to 2024 (moves the measured
    # side). e: an Epoch timeline on 5, 4 MW from 2015. d: resolved on 8, 2 MW, inventory year 2015, date 2013 to 2016
    # (before 2024's ramp). h: resolved on 9, 10 MW from 2005, base 300 GWh (a possible host). e8: 2 MW on 8 from 2006.
    sites = [{"fid": "a", "st": "HF", "u": 5, "cands": "5;6", "assign": "smallest_polygon", "raw": 2.0, "year": 2010},
             {"fid": "b", "st": "HF", "u": 6, "cands": "6;7;99", "assign": "smallest_polygon", "raw": 1.5, "year": 2012},
             {"fid": "m", "st": "HF", "u": 7, "raw": 3.0, "year": 2021, "basis": "verified_public_figure"},
             {"fid": "e", "st": "HF", "u": 5, "raw": 4.0, "year": 2015, "src": "epoch"},
             {"fid": "d", "st": "HF", "u": 8, "raw": 2.0, "year": 2015},
             {"fid": "h", "st": "HF", "u": 9, "raw": 10.0, "year": 2005},
             {"fid": "e8", "st": "HF", "u": 8, "raw": 2.0, "year": 2006}]
    bases = {(5, "HF"): 3000.0, (6, "HF"): 700.0, (7, "HF"): 1300.0, (8, "HF"): 5e4, (9, "HF"): 300.0, (10, "HF"): 1e6}
    inp = mini(sites, bases, {"HF": 0.0})
    return inp, [date("m", 2021, 2024, 2021), date("d", 2013, 2016, 2015)], "HF"


def moving_factor_state():
    # MF: the factor moves inside the band. p: resolved on 10, 4 MW from 2010. q: unresolved on 10 (candidate 11), 2 MW,
    # inventory year 2018, date 2020 to 2024 or never. w: resolved on 11, 1 MW from 2008, given an added candidate 12
    # (a candidates correction: unresolved from then on). n: unresolved on 12 (candidates 10 and 11), 1 MW from 2009,
    # narrowed to 12 and 10. EPRI is 0.6 times the frozen permit total (8 MW), so the frozen factor is 0.6.
    sites = [{"fid": "p", "st": "MF", "u": 10, "raw": 4.0, "year": 2010},
             {"fid": "q", "st": "MF", "u": 10, "cands": "10;11", "assign": "smallest_polygon", "raw": 2.0, "year": 2018},
             {"fid": "w", "st": "MF", "u": 11, "raw": 1.0, "year": 2008},
             {"fid": "n", "st": "MF", "u": 12, "cands": "12;10;11", "assign": "smallest_polygon", "raw": 1.0,
              "year": 2009}]
    bases = {(10, "MF"): 2300.0, (11, "MF"): 1e5, (12, "MF"): 1e5}
    inp = mini(sites, bases, {"MF": 0.6 * 8 * GWH / 1000})
    corrections = [date("q", 2020, 2024, 2020, never=True),
                   {"fid": "w", "kind": "candidates", "candidates": [11, 12]},
                   {"fid": "n", "kind": "narrow", "candidates": [12, 10]}]
    return inp, corrections, "MF"


STATES = {
    "world, a date with never that moves the factor": lambda: (
        world(WORLD_RAW), [date("p3", 2016, 2024, 2016, never=True)], "AA"),
    "world, a reopened site with a date": lambda: (
        world(WORLD_RAW), [{"fid": "p1", "kind": "reopen", "candidates": [1, 3]}, date("p1", 2010, 2014, 2012)], "AA"),
    "world, a capacity split dated by a date question": lambda: (
        world(WORLD_RAW), [date("p3", 2011, 2013, 2012), split("p3", None, 0.5, rest_earliest=2013)], "AA"),
    "world, a measured size with a date": lambda: (
        world(WORLD_RAW), [{"fid": "p3", "kind": "size", "mw_full": 2.0, "measured": True},
                           date("p3", 2020, 2024, 2020)], "AA"),
    "world, the state with no questions": lambda: (world(WORLD_RAW), [], "BB"),
    "world with large bases, a date with never": lambda: (
        big_world(), [date("p3", 2016, 2024, 2016, never=True)], "AA"),
    "world with large bases, a reopened site with a date": lambda: (
        big_world(), [{"fid": "p1", "kind": "reopen", "candidates": [1, 2]}, date("p1", 2010, 2014, 2012)], "AA"),
    "mini, the factor held at the band's floor": held_factor_state,
    "mini, the factor moving inside the band": moving_factor_state,
}

_CACHE: dict = {}


def built(name):
    if name not in _CACHE:
        inp, corrections, st = STATES[name]()
        result = ev.brute_force(inp, corrections, st)
        assert result["configurations"] <= 400, (name, result["configurations"])
        assert result["near_ties"] == [], name
        table = adapter.dependency_table(inp, px.parse_corrections(corrections, inp), [st])
        json.dumps(table)
        assert st in table["states"] and st not in table["refused"], (name, table["refused"])
        _CACHE[name] = (inp, corrections, st, result, table)
    return _CACHE[name]


def unit(x) -> tuple:
    if isinstance(x, str):
        u, s = x.split(":")
        return (int(u), s)
    return (int(x[0]), str(x[1]))


def qid(key) -> str:
    return f"{key[0]} {key[1]}"


def setting(v):
    return "off_panel" if v is None else v


# ---- masks ----------------------------------------------------------------------------------------------------------

def masks(units, st):
    """(label, mask, pool, hosts): all usable, none usable, and seeded random ones."""
    out = []
    full = [(u, s, y, True) for u, s in units for y in YEARS]
    out.append(("all usable", pd.DataFrame(full, columns=["utility_id_eia", "state", "year", "usable"]),
                set(units), set()))
    none = [(u, s, y, False) for u, s in units for y in YEARS]
    out.append(("none usable", pd.DataFrame(none, columns=["utility_id_eia", "state", "year", "usable"]),
                set(units), set()))
    for seed in range(6):
        rng = np.random.default_rng(1000 + seed)
        rows = []
        for u, s in units:
            kind = rng.integers(0, 6)
            if kind == 0:
                ys = {y: True for y in YEARS}
            elif kind == 1:
                ys = {y: False for y in YEARS}
            elif kind == 2:
                ys = {y: bool(rng.random() < 0.85) for y in YEARS}
            elif kind == 3:
                continue                                                     # absent from the mask
            elif kind == 4:
                gone = set(rng.choice(YEARS, size=3, replace=False).tolist())
                ys = {y: True for y in YEARS if y not in gone}               # three years with no row
            else:
                bad = int(rng.choice(YEARS))
                ys = {y: y != bad for y in YEARS}                            # one year not usable
            rows += [(u, s, y, f) for y, f in ys.items()]
        mask = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "usable"])
        pool = set(units) if seed % 2 == 0 else {k for k in units if rng.random() < 0.6}
        hosts = set() if seed % 3 else {units[int(rng.integers(0, len(units)))]}
        out.append((f"seed {seed}", mask, pool, hosts))
    return out


CASES = [(name, i) for name in STATES for i in range(8)]


# ---- the table against the evaluator --------------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(STATES))
def test_the_table_agrees_with_the_evaluator(name):
    inp, corrections, st, result, table = built(name)
    dep = table["states"][st]
    qs = {q["question_id"]: q for q in dep["questions"]}
    # Every question the evaluator lists, and no other (brief 4.3), with the same settings.
    assert set(qs) == {qid(k) for k in result["questions"]}
    for k in result["questions"]:
        q = qs[qid(k)]
        assert q["fid"] == k[0] and q["question"] == k[1]
        assert list(q["settings"]) == [setting(v) for v in result["settings"][k]], k
        # 4.1: contains the evaluator's reaches.
        assert {unit(u) for u in q["utilities"]} >= result["reaches"][k], k
        assert list(q["utilities"]) == sorted(q["utilities"])
        # 4.2: agrees exactly.
        assert q["moves_anchoring"] is result["moves_anchoring"][k], (k, q["moves_anchoring"], result["moves_anchoring"][k])
    # 4.5: every unit that can cross the host threshold is a possible host.
    assert result["can_cross"] <= {unit(u) for u in dep["possible_hosts"]}
    assert {unit(u) for u in dep["units"]} == set(result["units"])


# ---- the screen against the evaluator -------------------------------------------------------------------------------

@pytest.mark.parametrize("name,i", CASES)
def test_the_screen_keeps_the_guarantee(name, i):
    inp, corrections, st, result, table = built(name)
    dep = table["states"][st]
    label, mask, pool, hosts = masks(result["units"], st)[i]
    rec = adapter.screen(mask, IDENTITY, pool, hosts, table, [st], corrections)
    json.dumps(rec)
    narrowed = {unit(u) for u in rec["narrowed"]}
    possible = {unit(u) for u in dep["possible_hosts"]}
    protected = hosts | possible

    # Brief 4.6, worked out here: in the pool, not protected, and passing no permitted window on the mask.
    expected = {k for k in pool if k not in protected and not ev.windows_passed(mask, k)}
    assert narrowed == expected, (label, narrowed, expected)
    assert not (narrowed & result["can_cross"]), label

    # Brief 4.7 on the adapter's own table and narrowed set: exactly the deferrable list.
    deferrable = set(rec["deferrable"])
    by_table = {q["question_id"] for q in dep["questions"]
                if q["moves_anchoring"] is False and q["utilities"]
                and {unit(u) for u in q["utilities"]} <= narrowed}
    assert deferrable == by_table, label
    # And within what 4.7 gives on the evaluator's own reaches.
    by_evaluator = {qid(k) for k in result["questions"]
                    if result["moves_anchoring"][k] is False and result["reaches"][k]
                    and result["reaches"][k] <= narrowed}
    assert deferrable <= by_evaluator, label
    # Every question is accounted for once.
    assert deferrable.isdisjoint(rec["retained"]) and deferrable | set(rec["retained"]) == {qid(k) for k in result["questions"]}

    # The guarantee of brief section 2, on the full product.
    assert ev.violations(result, deferrable, narrowed) == [], label

    # No question that reaches a protected unit, or a unit that can cross, is deferrable, whatever the mask.
    for k in result["questions"]:
        if result["reaches"][k] & (protected | result["can_cross"]):
            assert qid(k) not in deferrable, (label, k)
