"""A brute-force enumerator of references (docs/gate1/reference-repair-rule-2026-11-18.md, section 8.1).

Load and sales only; no price is read and nothing is written. Written from sections 1 to 6 of the rule file and
sections 1 to 4 of docs/gate1/exact-attribution-brief-2026-11-16.md, apart from the implementation: it never imports
pipeline/facilities/pass_c_exact.py, and it uses none of what the rule's section 6 forbids (the two ends of a question
or the corners to decide anything, monotonicity, merging, relevance, `_factor_range`, `factor_varies`, the evaluator's
old `reference()`, or `run_state`'s reference).

It decides a reference one way only. The reference-defining questions of a state, and every setting of each, are
listed here from the correction dicts in the words of the brief's section 2; every combination of their settings is
realised through `pass_c_expand.scratch_state` and `assignment.evaluate` with every other question at the reference
configuration (an assignment question on the utility the site is on; a date or capacity question with a convention at
that convention, which is what `scratch_state` gives a question it is not handed); and each utility's place and first
crossing as built are read here from the `as_built` matrix. A reference is defined if and only if one pair is seen at
every combination (rule R2).

The ends of each question are used for one thing only: `differs_inside_only`, which reports that the endpoint rule
(every combination of the questions' first and last settings) would have seen one pair where the full enumeration sees
more. It decides nothing.

Readings this file makes where the rule file does not settle the point (the agent's report lists them too):

* A crossing is a float year or None. With no positive base (zero or missing) a utility never crosses and any load
  puts it over the floor (the brief's section 3; `assignment.evaluate` reads it so).
* The utilities of a state are its panel units (`inp.units` in that state), every one of them, whether or not any
  question can reach it.
* A start interval that lies wholly at or before 1999 (the open-below start) is entered once at its latest year, and
  one that lies wholly after the last panel year once at 2026: both are "entered once" in the brief's words, and these
  are the years `_date_values` uses for them, so the lists can be compared item for item.
* `provisional_defines=False` (the place test's list, rule section 3) leaves a provisional date at its convention.
"""
from __future__ import annotations

import itertools
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

YEARS = list(asg.YEARS)
FLOOR = asg.CLEAN_BELOW
FIRST_PANEL_YEAR, LAST_PANEL_YEAR = YEARS[0], YEARS[-1]
RAMP_YEARS = 3                       # buildout.RAMP_YEARS: a start at or before 2001 - 3 + 1 is full load from 2001
OPEN_BELOW = FIRST_PANEL_YEAR - RAMP_YEARS + 1      # 1999
AFTER_PANEL = LAST_PANEL_YEAR + 1                   # 2026: no load in any panel year, and none in 2024
COMBINATION_LIMIT = 20000            # made-up states only: refuse rather than run for hours


# ---- listing the questions and their settings (brief section 2, in its words) ----------------------------------------

def _date_settings(c: dict) -> list:
    """Every start year from the early end to the late end, and "never" where it is possible.

    Open below (earliest null) starts at or before 1999; every start at or before 1999 is full load in every panel year
    and is entered once. Every start after the last panel year carries nothing in the panel or in 2024 and is entered
    once. An open-above interval (latest null) runs to after the panel.
    """
    lo = OPEN_BELOW if c.get("earliest") is None else int(c["earliest"])
    hi = AFTER_PANEL if c.get("latest") is None else int(c["latest"])
    if hi < OPEN_BELOW:                                  # wholly before the panel's open-below start: one setting
        years = [hi]
    elif lo > AFTER_PANEL:                               # wholly after the panel: one setting
        years = [AFTER_PANEL]
    else:
        years = list(range(max(lo, OPEN_BELOW), min(hi, AFTER_PANEL) + 1))
    return years + (["never"] if c.get("never_is_possible") else [])


def _capacity_settings(c: dict, inventory_year: float) -> list:
    """The two cases, or with rest_earliest every year from it to the inventory's year (the late case)."""
    if c.get("rest_earliest") is None:
        return [px.EARLY, px.LATE]
    return list(range(int(c["rest_earliest"]), int(inventory_year) + 1))


def admissible_reference_settings(inp, corrections: list[dict], st: str, provisional_defines: bool) -> dict:
    """The reference-defining questions of `st` and every setting of each (rule R1).

    {"questions": [{"fid", "question", "settings": [value, ...]}], "combinations": int}

    Defining: a date or capacity question with no convention; with `provisional_defines`, also a date whose
    convention is marked provisional. The lists are made here and checked against `_date_values` and `_capacity_values`.
    """
    corr = px.parse_corrections(corrections, inp)            # validates; refuses in words what cannot be applied
    questions = []
    for c in corrections:
        fid, kind = c.get("fid"), c.get("kind")
        if kind not in ("date", "capacity_split") or inp.fac.state[fid] != st:
            continue
        if kind == "date":
            defining = c.get("convention") is None or (provisional_defines and c.get("convention_is") == "provisional")
            if not defining:
                continue
            settings = _date_settings(c)
            theirs = px._date_values(corr[fid])
            q = "date"
        else:
            if c.get("convention") is not None:
                continue
            settings = _capacity_settings(c, inp.fac.energized_year[fid])
            theirs = px._capacity_values(corr[fid])
            q = "capacity"
        if settings != theirs:
            raise AssertionError(f"{fid} {q}: listed here as {settings}, by pass_c_expand as {theirs}")
        questions.append({"fid": fid, "question": q, "settings": settings})
    questions.sort(key=lambda x: (x["fid"], 0 if x["question"] == "date" else 1))
    return {"questions": questions, "combinations": math.prod(len(x["settings"]) for x in questions)}


# ---- place and first crossing as built, read here (brief section 3) ---------------------------------------------------

def _positive(b) -> bool:
    return b is not None and not (isinstance(b, float) and math.isnan(b)) and b > 0


def place_and_crossing(v, base_k, theta: float) -> tuple:
    """(place, first crossing) of one reading of one utility: GWh by panel year against its base-period sales."""
    v = np.asarray(v, dtype=float)
    crossing = None
    if _positive(base_k):
        for y, x in zip(YEARS, v):
            if x >= theta * base_k:
                crossing = float(y)
                break
    top = float(v.max())
    if top > 0:
        share = top / base_k if _positive(base_k) else math.inf
    else:
        share = 0.0
    if crossing is None:
        return ("comparison" if share < FLOOR else "neither"), None
    first, last = asg.COHORTS                          # the cohort years, 2011 to 2022
    return ("early" if crossing < first else "cohort" if crossing <= last else "late"), crossing


def _gap(v, base_k, theta: float) -> float:
    """The least relative distance of this reading from the 2% threshold (any year) and of its largest share from the
    floor; infinite where neither applies. Made-up cases keep it above one part in a million."""
    if not _positive(base_k):
        return math.inf
    v = np.asarray(v, dtype=float)
    t = theta * base_k
    g = float(np.min(np.abs(v - t)) / t)
    if v.max() > 0:
        g = min(g, abs(v.max() / base_k - FLOOR) / FLOOR)
    return g


# ---- realising every combination ---------------------------------------------------------------------------------------

def table(inp, corrections: list[dict], st: str, theta: float = 0.02, provisional_defines: bool = True,
          limit: int = COMBINATION_LIMIT) -> dict:
    """Every admissible reference setting realised. {"questions", "combinations", "units", "rows"}, a row being
    {"setting": tuple (one value per question, in the order of "questions"), "factor": float,
     "pairs": {unit: (place, crossing)}, "gap": {unit: float}}."""
    adm = admissible_reference_settings(inp, corrections, st, provisional_defines)
    if adm["combinations"] > limit:
        raise ValueError(f"{adm['combinations']} combinations of reference settings in {st}, more than {limit}: keep the "
                         f"made-up case smaller")
    corr = px.parse_corrections(corrections, inp)
    units = inp.units[inp.units.get_level_values("state") == st]
    base, regions = inp.base.reindex(units), inp.regions.reindex(units)
    keys = [(q["fid"], q["question"]) for q in adm["questions"]]
    rows = []
    for combo in itertools.product(*(q["settings"] for q in adm["questions"])):
        fac, fy, factor = px.scratch_state(inp, corr, st, dict(zip(keys, combo)))
        _, m, _ = asg.evaluate(fac, fy, units, base, regions, thresholds=(theta,))
        ab = m["as_built"]
        pairs, gap = {}, {}
        for k in units:
            v = ab.loc[k].reindex(YEARS).values.astype(float)
            b = base[k]
            b = float(b) if b is not None else math.nan
            pairs[k] = place_and_crossing(v, b, theta)
            gap[k] = _gap(v, b, theta)
        rows.append({"setting": combo, "factor": float(factor), "pairs": pairs, "gap": gap})
    return {**adm, "units": list(units), "rows": rows}


def _is_end(combo: tuple, questions: list) -> bool:
    return all(v == q["settings"][0] or v == q["settings"][-1] for v, q in zip(combo, questions))


def _sort_key(pair):
    place, crossing = pair
    return (place, -1.0 if crossing is None else crossing)


def from_table(t: dict) -> dict:
    """The references read off a realised table (rule R2), with `differs_inside_only` for reporting."""
    out = {}
    for k in t["units"]:
        seen = {r["pairs"][k] for r in t["rows"]}
        at_ends = {r["pairs"][k] for r in t["rows"] if _is_end(r["setting"], t["questions"])}
        defined = len(seen) == 1
        place, crossing = next(iter(seen)) if defined else (None, None)
        out[k] = {"defined": defined, "place": place, "crossing": crossing,
                  "seen": sorted(seen, key=_sort_key),
                  "differs_inside_only": bool(len(at_ends) == 1 and not defined)}
    return out


def references(inp, corrections: list[dict], st: str, theta: float = 0.02, provisional_defines: bool = True) -> dict:
    """{(utility_id_eia, state): {"defined", "place", "crossing", "seen", "differs_inside_only"}} for every panel
    utility of `st`, by realising every admissible reference setting."""
    return from_table(table(inp, corrections, st, theta, provisional_defines))
