#!/usr/bin/env python3
"""Future hosts: the criterion, the side run "Future hosts as a second comparison group", and E2's sample and design.

Load and sales only. Nothing here reads a price, revenue or bill, opens data/blind or data/interim/availability, or
writes under data/interim. The design side only: this module builds design.Design objects and quantity-only reports;
it fits nothing.

The criterion (PREANALYSIS.md, Other runs, "Future hosts as a second comparison group"; Joe, D-99)
-------------------------------------------------------------------------------------------------
A utility that first crosses the threshold in 2023 or later is a comparison utility for cohort g only if, in every
admissible history the sets test, its own load share is under 0.5% in every year through g+3 and its first crossing is
g+7 or later; and it meets every other comparison rule. `admitted` is the criterion for one unit and one cohort over a
supplied collection of histories, and is true only if it holds in every one.

Adopted by Joe on 2026-11-19 (D-111), where the plan does not say: a history in which the unit does not cross in the
panel (2001 to 2025) meets "first crossing g+7 or later" only where g+7 is 2026 or earlier, since all such a history
shows is that the crossing, if any, is 2026 or later. For g of 2020 or later it is not shown, and the history fails.

Which histories exist for a late host (`late_host_histories`)
------------------------------------------------------------
"Every admissible history the sets test" is the place test's enumeration (pipeline/facilities/timing.py; the plan's
headline-set rule 3): every combination, one setting per site, of each unresolved assignment (as mapped, each
candidate, off the panel, which contains D-46 ruling 4's three cases for the unit), each date question at every year of
its interval (open below where it is, "never" where allowed), each capacity question, crossed with the generic screen
(0, 3 and 5 years earlier), each state's factor recomputed in every configuration, each read as built and with no
anchoring. timing.run evaluates EVERY unit of a state, late hosts included, but writes only a place verdict and a range
of crossings, not the year-by-year shares the criterion needs. The shares come from the same objects the place test
builds: timing.StateRun's cases and pass_c_exact._State.grid over the unit's relevant questions at one representative
of each class of settings merged for the unit. Merged settings put the same load on the unit in every year (and count
the same in the anchoring where the factor matters to it), so the representatives give every distinct share series the
enumeration contains (pass_c_exact's rule R3).

A screen case whose count is over the 100,000 ceiling is not enumerated by the place test; it goes to the envelope,
which gives bounds on statuses and no share series. Those histories are NOT approximated here: the unit's coverage is
incomplete, it is named, and it is "not shown admissible in every admissible history", so it is admitted for no cohort
and is not in E2.

Also added, adopted by Joe on 2026-11-19 (D-111): the slow path of headline-set rule 2 (D-28; buildout.py: every still-unverified
site with a later latest permit on the slow build-out, the factor held as built) is tested by the sets through rule 2
and is not among the place test's cases (PREANALYSIS.md, E4(a)). It is added as one more history per unit. It never
puts more load on a unit than the three-year ramp in any year, so it can only remove an admission, and the report says
whether it removed any.

Outside the admissible histories by the plan's own definition, and so not counted as gaps: the ten-year screen case and
the permit-error reach (labelled stress tests), stress scenarios (never admissible), the later-start shifts, the state's
unassigned remainder, and rows with no size (no load in any history).

The side run (Joe's ruling of 2026-11-19, verbatim)
---------------------------------------------------
"Add eligible future hosts to each cohort's side-run comparison pool and match under the existing rules. Report how
many enter the matches and any sample changes. This does not change the headline pool."

The hosts are the headline set's. For cohort g the pool is the headline design's eligible pool plus the future hosts
admitted for g that meet every other comparison rule (not set aside, no crypto load of 2% or more, a sales base, not in
price_hold.csv, the load-unknown rule; region, ownership rules 2.1 to 2.3, the usable full window and the customer floor
are applied by the matching itself). design.build_with_rules takes one comparison frame for every cohort, so the pool
cannot differ by cohort inside one call. `side_run_design` therefore calls build_with_rules once per cohort (that
cohort's hosts, that cohort's pool) and once more on every host with the union of the pools only for its windows, unit
codes and state codes; each cohort's matches are mapped into the union windows by key, and `is_comp` is set per cohort.
Window rows are sorted by key and each unit's membership in a window depends only on its own data, so the per-cohort
pool is the same units in the same order in the union window, and the nearest-in-size ties break the same way. With no
future host admitted it returns exactly the headline design (tests/test_future_hosts_invented.py). design.py is not
edited.

E2 (PREANALYSIS.md, Other outcomes and robustness, E2 and G-a)
---------------------------------------------------------------
Units: late hosts at 2% with group "late host" in every admissible history (both readings, every enumerated history and
the slow path), complete coverage, not set aside, not reached by a site with no load history unless the enumeration
decided it, not in price_hold.csv. Fake date f: the latest year in 2011 to 2022 for which the criterion holds for the
unit itself in every admissible history; none, and the unit is left out and named. Window f-6 to f+3, reference f-3.
Design: each unit a pseudo-host of cohort f, matched at f-3 under G-a in the MAIN comparison pool (the headline
design's eligible pool: other late hosts are not in it, and the unit is not a comparison in its own sub-experiment),
with the support rule and usability over the new window, through design.build_with_rules.

E2 and a pseudo-host with no ownership row (Joe's ruling of 2026-11-19, verbatim)
-------------------------------------------------------------------------------
"I accept excluding Entergy Mississippi from E2 with the reason disclosed, unless existing permitted evidence resolves
the relevant affiliation. This does not change headline-host eligibility."

The existing permitted evidence (pipeline/analysis/ownership.csv and pipeline/analysis/leads/) was checked on
2026-11-19: ownership.csv has no row for Entergy Mississippi (12685) and no lead file has a lead row for it, so the
affiliation is not resolved under the table's standard (a row with a source). Implemented as a general rule of E2's
unit selection, which is the session's reading of the ruling: an investor-owned pseudo-host (the panel's ownership
class) for which some year of its fake window f-6 to f+3 has no ownership row covering it is left out of E2, named, with
the reason disclosed (E2_NO_OWNERSHIP_ROW). That "no row covering its fake window" means "some year of the window has
no covering row" is the agent's reading within the session's rule; a row assumed at both ends is a row and does not
trigger it. The ruling names one unit, so main() stops if the rule would remove any other (E2_RULING_NAMES). The rule is
applied only to E2's units: the headline set, the headline design and the side run are not touched by it.

Run:  python3 -I pipeline/analysis/future_hosts.py      writes data/frozen/future_host_runs.json (provisional)
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
OUT = FROZEN / "future_host_runs.json"
KEY = ps.KEY

THETA = 0.02
PANEL_YEARS = tuple(range(2001, 2026))          # the inventory's years (assignment.YEARS)
LATE = (2023, 2025)                             # a late host's first crossing
FAKE_YEARS = (2011, 2022)                       # E2's fake dates are looked for in these years
QUIET_THROUGH = ps.POST                         # under 0.5% through g+3
CROSSING_AT_LEAST = 7                           # first crossing at g+7 or later

READINGS = ("as_built", "no_anchoring")
PLACE_TEST_CLASSES = ("assignment", "timing", "capacity")   # timing._kind's names for the question kinds
NOT_ADMISSIBLE_BY_DEFINITION = [
    "the ten-year screen case (a labelled stress test, D-54 ruling 1)",
    "the permit-error reach (reported under its own name, D-61 section 6)",
    "stress scenarios (never an admissible history, D-96 item 3)",
    "the later-start shifts (chosen stress sizes, reported beside the result)",
    "the state's unassigned remainder (a stated limit, not a history, D-46 ruling 6)",
    "rows with no size (they carry no load in any history)",
]
SLOW_PATH = "slow_path_of_headline_set_rule_2"

E2_RULING_2026_11_19 = ("I accept excluding Entergy Mississippi from E2 with the reason disclosed, unless existing permitted "
                        "evidence resolves the relevant affiliation. This does not change headline-host eligibility.")
E2_RULING_NAMES = {(12685, "MS")}               # the one unit the ruling names; main() stops if the rule removes another
E2_NO_OWNERSHIP_ROW = ("left out of E2 (Joe, 2026-11-19): an investor-owned pseudo-host with no ownership row covering "
                       "{years} of its fake window, so no shared parent with its investor-owned matches can be shown or "
                       "ruled out (rule 2.3); the ownership table was sourced for cohort hosts and eligible comparisons, not "
                       "for late hosts standing as hosts. The general rule (any investor-owned pseudo-host with a year of "
                       "its fake window that no ownership row covers) is the session's reading of the ruling")
E2_EVIDENCE_CHECKED = ("pipeline/analysis/ownership.csv: no row for utility_id_eia 12685 (rows exist for Entergy Arkansas, "
                       "Entergy Louisiana and Entergy New Orleans, each listed at 2025-12-31 with earlier years assumed). "
                       "pipeline/analysis/leads/: no lead row names 12685 or Entergy Mississippi in any lead file; the name "
                       "appears only inside the captured page text of two fetch records in ownership_opened_2026-11-18.csv "
                       "(fetch 125, entergy.com's customer menu; fetch 272, Entergy Corporation's Exhibit 21 as of "
                       "2025-12-31, whose searched fragments were Entergy Arkansas, Entergy Louisiana and Entergy New "
                       "Orleans). Neither is a row with a source, and the Exhibit 21 text speaks to 2025-12-31, outside "
                       "the window 2012 to 2021. Not resolved; no row was added and no lookup was made (checked 2026-11-19)")


# ---- the criterion --------------------------------------------------------------------------------------------------

def _frame(histories, years=None) -> pd.DataFrame:
    """Histories as a frame, one row per history and one column per year, from a frame, a 2-D array with `years`, or an
    iterable of year -> share mappings (dicts or Series)."""
    if isinstance(histories, pd.DataFrame):
        f = histories.copy()
    elif isinstance(histories, np.ndarray):
        if years is None:
            raise ValueError("an array of histories needs its years")
        f = pd.DataFrame(np.atleast_2d(histories), columns=list(years))
    else:
        f = pd.DataFrame([dict(h) for h in histories])
    f.columns = [int(c) for c in f.columns]
    return f


def first_crossings(histories, theta: float = THETA, years=None) -> np.ndarray:
    """Each history's first year at or above theta, NaN where it never gets there in the panel."""
    f = _frame(histories, years)
    need = [y for y in PANEL_YEARS if y not in f.columns]
    if need:
        raise ValueError(f"a history lacks panel years {need[:5]}{'...' if len(need) > 5 else ''}: its first crossing "
                         "cannot be told, and nothing is filled in")
    v = f[list(PANEL_YEARS)].to_numpy(float)
    if np.isnan(v).any():
        raise ValueError("a history has a missing share in a panel year; nothing is filled in")
    hit = v >= theta
    return np.where(hit.any(axis=1), np.array(PANEL_YEARS)[hit.argmax(axis=1)], np.nan)


def _passes(f: pd.DataFrame, cohort: int, theta: float) -> np.ndarray:
    g = int(cohort)
    c = first_crossings(f, theta)                       # checks every panel year is present and none is missing
    through = [y for y in PANEL_YEARS if y <= g + QUIET_THROUGH]
    quiet = (f[through].to_numpy(float) < ps.CLEAN_BELOW).all(axis=1)
    # No crossing in the panel shows only that the crossing, if any, is after the last panel year (adopted by Joe on
    # 2026-11-19, D-111).
    late_enough = np.where(np.isnan(c), g + CROSSING_AT_LEAST <= PANEL_YEARS[-1] + 1, c >= g + CROSSING_AT_LEAST)
    return quiet & late_enough


def admitted(histories, cohort: int, theta: float = THETA, years=None) -> bool:
    """The future-host criterion for one unit and cohort g: in EVERY supplied history (year -> load share), the share is
    under 0.5% in every year through g+3 and the first crossing of theta is g+7 or later. No history: not shown, False."""
    f = _frame(histories, years)
    if f.empty:
        return False
    return bool(_passes(f, cohort, theta).all())


def admitted_cohorts(histories, theta: float = THETA, cohorts=ps.COHORTS, years=None) -> list[int]:
    f = _frame(histories, years)
    return [g for g in range(cohorts[0], cohorts[1] + 1) if not f.empty and bool(_passes(f, g, theta).all())]


def fake_date(histories, theta: float = THETA, years=None) -> int | None:
    """E2's f: the latest year in 2011 to 2022 for which the criterion holds in every history; None if there is none."""
    ok = admitted_cohorts(histories, theta, FAKE_YEARS, years)
    return max(ok) if ok else None


def late_in_every_history(histories, theta: float = THETA, years=None) -> bool:
    """Group "late host" (first crossing 2023 to 2025) in every history. No history: not shown, False."""
    f = _frame(histories, years)
    if f.empty:
        return False
    c = first_crossings(f, theta)
    return bool(((c >= LATE[0]) & (c <= LATE[1])).all())


# ---- the histories the existing machinery supplies -------------------------------------------------------------------

def enumeration_inputs():
    """timing.load_rebuilt's inputs, read from the quantity files only (nothing written).

    One difference, stated: timing.load_rebuilt also reads data/interim/epoch_gaps.parquet, which is not among the files
    this pass may read, to set the 2024 anchoring contribution of fixed-history rows in an Epoch gap. That value
    (Inputs.frozen_2024_mw) is read by pass_c_expand only for a fixed-history row with a not_a_site correction. This
    refuses if the corrections in force carry any not_a_site entry, so the value cannot reach a history; main() then
    checks that every late host's place test reproduces the frozen one exactly."""
    from pipeline.facilities import assignment as asg
    from pipeline.facilities import buildout
    from pipeline.facilities import corrections as cx
    from pipeline.facilities import pass_c_expand as px
    from pipeline.facilities import timing
    corrections = cx.load()
    nas = [c["fid"] for c in corrections if c.get("kind") == "not_a_site"]
    if nas:
        raise RuntimeError(f"not_a_site corrections in force ({nas[:5]}): their 2024 anchoring needs epoch_gaps.parquet, "
                           "which this pass may not read; stopping rather than approximating")
    fac, fy, q, units, base, regions = asg.load_inputs()
    fac = timing.patch_unknown(fac)
    fy_all = pd.read_parquet(INTERIM / "facility_year.parquet")
    anchor = pd.read_parquet(INTERIM / "state_anchor.parquet").set_index("state")
    phases = buildout.phases_by_site(buildout.load())
    names = q.groupby(asg.KEY).utility_name.last()
    fixed = fac.index[(fac.src == "epoch") | (fac.load_history == "operator_reported_energy")]
    y24 = fy_all[fy_all.year == px.ANCHOR_YEAR].groupby("fid").mw.sum()
    frozen_2024 = {fid: float(y24.get(fid, 0.0)) for fid in fixed if bool(fac.in_dose[fid])}
    inp = px.Inputs.build(fac, fy, units, base, regions, names, anchor, phases, frozen_2024, fy_all)
    return inp, corrections


def late_hosts_on_the_frame(dose: pd.DataFrame, theta: float = THETA) -> dict:
    """{(utility, state): first crossing} for units whose first crossing on the inventory as built (the dose frame) is
    2023 to 2025."""
    first = dose[dose.dose >= theta].groupby(KEY).year.min()
    return {(int(u), st): int(y) for (u, st), y in first.items() if LATE[0] <= y <= LATE[1]}


def histories_from_state_run(sr, k: tuple, theta: float = THETA, ceiling: int | None = None) -> dict:
    """Every admissible share history of unit k that the place test's objects supply, with what they cover.

    sr: a timing.StateRun of k's state (its screen cases built). Returns {"histories": DataFrame (rows: distinct
    histories, columns: panel years), "coverage": {...}, "complete": bool, "why_incomplete": [...]}."""
    from pipeline.facilities import pass_c_exact as pe
    from pipeline.facilities import timing
    ceiling = timing.CEILING if ceiling is None else ceiling
    base_k = float(sr.inp.base.get(k, np.nan))
    rec, _ = sr.reference(k, theta)
    cov = {"reference": {"defined": rec["defined"], "place": rec["place"], "crossing": rec["crossing"]},
           "screen_cases": [], "question_kinds_relevant": [], "readings": list(READINGS),
           "ceiling_per_screen_case": ceiling}
    why, rows, kinds = [], [], set()
    base_ok = bool(np.isfinite(base_k) and base_k > 0)
    if not base_ok:
        why.append("no positive 2009-2011 sales base, so no share can be computed")
    for c in sr.cases:
        S = c["S"]
        if k not in S.units:
            why.append(f"not among the units of the state's place test (screen case {c['shift']})")
            continue
        fm, rel = S.relevance(k)
        n = int(math.prod(len(cl) for _, cl in rel))
        kinds |= {timing._kind(S.qs[qid]) for qid, _ in rel}
        case = {"screen_shift": c["shift"], "configurations": n, "factor_recomputed_in_each": bool(fm),
                "relevant_questions": [f"{S.qs[qid].fid} {S.qs[qid].name}" for qid, _ in rel], "enumerated": n <= ceiling}
        cov["screen_cases"].append(case)
        if n > ceiling:
            why.append(f"screen case {c['shift']}: {n} configurations, over the ceiling of {ceiling}; the place test "
                       "takes this case to the envelope, which gives no share series, so its histories are not enumerated")
            continue
        if not base_ok:
            continue
        axes = [(qid, [g[0] for g in cl]) for qid, cl in rel]
        ab, na, _ = S.grid(k, axes)
        for reading, v in (("as_built", ab), ("no_anchoring", na)):
            s = v / base_k
            # The crossing read from the shares must be the one the place test reads from the loads (pe._readings).
            c_pe, _, _ = pe._readings(v, base_k, theta)
            c_me = first_crossings(s, theta, PANEL_YEARS)
            mine = np.where(np.isnan(c_me), pe.NEVER, np.nan_to_num(c_me, nan=0) - PANEL_YEARS[0]).astype(int)
            if not (mine == c_pe).all():
                raise RuntimeError(f"{k}: a crossing read from shares differs from the place test's at the threshold "
                                   "boundary; stopping rather than choosing one")
            rows.append(s)
    cov["question_kinds_relevant"] = sorted(kinds)
    hist = pd.DataFrame(np.unique(np.vstack(rows), axis=0) if rows else np.zeros((0, len(PANEL_YEARS))),
                        columns=list(PANEL_YEARS))
    cov["distinct_histories_enumerated"] = int(len(hist))
    cov["classes"] = {
        "assignment (as mapped, each candidate, off the panel; contains D-46 ruling 4's three cases)":
            _class_status("assignment", kinds, cov["screen_cases"]),
        "date cases (every year of each interval, open below, never)": _class_status("timing", kinds, cov["screen_cases"]),
        "capacity cases": _class_status("capacity", kinds, cov["screen_cases"]),
        "generic screen (0, 3 and 5 years earlier)": {str(x["screen_shift"]): ("enumerated" if x["enumerated"] else "not enumerated: over the ceiling")
                                                       for x in cov["screen_cases"]},
        "anchoring (each state's factor recomputed in every configuration)": "within each enumerated case",
        "readings (as built; with no anchoring)": "both, within each enumerated case",
    }
    return {"histories": hist, "coverage": cov, "complete": not why, "why_incomplete": why}


def _class_status(kind: str, kinds: set, cases: list) -> str:
    if kind not in kinds:
        return "no question of this kind is relevant to the unit (nothing to enumerate)"
    if all(x["enumerated"] for x in cases):
        return "enumerated in every screen case"
    return "not enumerated in screen case(s) " + ", ".join(str(x["screen_shift"]) for x in cases if not x["enumerated"])


def slow_path_histories(fac: pd.DataFrame, fy: pd.DataFrame, base: pd.Series, units) -> dict:
    """{unit: share series} with every still-unverified phaseable site on the slow path, every other row as the frame
    has it and the factor held as built: buildout.main's `rest_slow`, from its own functions. `fac` and `fy` are the
    frame's facilities (not patched) and site-years with crypto removed."""
    from pipeline.facilities import buildout
    t = buildout.load()
    phased, single = set(buildout.phases_by_site(t)), buildout.single_buildings(t)
    f = fac.reset_index() if "fid" not in fac.columns else fac
    sites = f[f.in_dose & ~f.is_crypto & (f.src != "epoch") & (f.load_history != "operator_reported_energy")].copy()
    sites["slow_end"] = [buildout.slow_end_year(e, lp) for e, lp in zip(sites.energized_year, sites.latest_permit_year)]
    could = sites.slow_end > sites.energized_year + buildout.RAMP_YEARS - 1
    open_sites = sites[could & ~sites.fid.isin(phased | single)]
    years = list(range(int(fy.year.min()), int(fy.year.max()) + 1))
    slow = buildout.paths(f, fy, years, dict.fromkeys(open_sites.fid, "slow"))
    gwh = (slow.groupby(KEY + ["year"]).mw.sum() * 8.76).reset_index()
    out = {}
    for k in units:
        b = float(base.get(k, np.nan))
        if not (np.isfinite(b) and b > 0):
            out[k] = None                     # no positive sales base: no share exists to compare (named by the caller)
            continue
        s = gwh[(gwh.utility_id_eia == k[0]) & (gwh.state == k[1])].set_index("year").mw
        out[k] = (s.reindex(list(PANEL_YEARS)).fillna(0.0) / b).rename(None)
    return out


# ---- the side run: one pool per cohort, matched under the existing rules -------------------------------------------

def _keys(frame: pd.DataFrame) -> list:
    return [(int(u), st) for u, st in zip(frame.utility_id_eia, frame.state)]


def _with(clean: pd.DataFrame, extra) -> pd.DataFrame:
    have = set(_keys(clean))
    add = [k for k in extra if k not in have]
    return pd.concat([clean[KEY], pd.DataFrame(add, columns=KEY)], ignore_index=True) if add else clean[KEY].reset_index(drop=True)


def _category(why: str) -> int:
    if why == ps.LOAD_UNKNOWN:
        return 0
    if why == dsg.NOT_USABLE or why.startswith("no region") or why.startswith("no residential sales"):
        return 1
    if why.startswith(dsg.SUPPORT_RULE):
        return 2
    if why.startswith(own_rules.UNRESOLVED_EXCLUDED):
        return 3
    raise ValueError(f"a dropped host's reason this module does not know how to order: {why!r}")


def side_run_design(treated: pd.DataFrame, clean: pd.DataFrame, admitted_by_cohort: dict, q, regions, fuel, dd,
                    rules: ps.Rules = ps.HEADLINE_RULES, **kw) -> dsg.Design:
    """The headline hosts matched under build_with_rules, each cohort's pool the headline pool plus the future hosts
    admitted for that cohort ({cohort: [(utility, state)]}). Keywords go to build_with_rules (ownership, usable, gas,
    ownership_of, unknown_load, theta, k). With nobody admitted the result is the headline design."""
    order = {(int(u), st, int(g)): i for i, (u, st, g) in enumerate(zip(treated.utility_id_eia, treated.state, treated.cohort))}
    cohorts = sorted(int(g) for g in treated.cohort.unique())
    pools = {g: _with(clean, admitted_by_cohort.get(g, [])) for g in cohorts}
    union_clean = _with(clean, [k for g in cohorts for k in admitted_by_cohort.get(g, [])])
    union = dsg.build_with_rules(treated, union_clean, q, regions, fuel, dd, rules, **kw)
    unknown, theta = kw.get("unknown_load"), kw.get("theta", 0.02)
    hosts, dropped, tables, unresolved, out_hosts, out_comps = [], [], [], [], [], []
    is_comp = {}
    for g in cohorts:
        d = dsg.build_with_rules(treated[treated.cohort == g], pools[g], q, regions, fuel, dd, rules, **kw)
        w = union.windows.get(g)
        gated = set(_keys(unknown.gate(pools[g], theta, "comparison")[0])) if unknown is not None else set(_keys(pools[g]))
        if w is not None:
            is_comp[g] = np.array([key in gated for key in w.keys])
        for h in d.hosts.to_dict("records"):
            row = w.keys.index(tuple(h["key"]))
            m = [w.keys.index(tuple(x)) for x in h["match_keys"]]
            hosts.append({**h, "row": row, "matches": m})
        dropped += d.dropped
        if d.support_table is not None:
            tables.append(d.support_table)
        unresolved += list(d.unresolved_ownership or [])
        out_hosts += [x for x in d.load_unknown_excluded if x["role"] == "host"]
        out_comps += [x for x in d.load_unknown_excluded if x["role"] == "comparison"]
    cols = list(union.hosts.columns)
    hf = pd.DataFrame(hosts, columns=cols) if hosts else union.hosts.iloc[0:0].copy()
    if len(hf):
        hf = hf.iloc[np.argsort([order[(int(k[0]), k[1], int(c))] for k, c in zip(hf.key, hf.cohort)], kind="stable")].reset_index(drop=True)

    def rank(x):
        u, st = x["utility"].split(":")
        g = x.get("cohort")
        pos = min((i for (uu, ss, gg), i in order.items() if (uu, ss) == (int(u), st) and (g is None or gg == int(g))), default=len(order))
        return (_category(x["why"]), pos)
    dropped = sorted(dropped, key=rank)
    out = dsg.Design(hf, union.windows, {**union.is_comp, **is_comp}, dropped, union.region_names, union.unit_code,
                     union.state_code, union.gas)
    if tables:
        t = pd.concat(tables, ignore_index=True)
        t = t.iloc[np.argsort([order[(int(u), st, int(g))] for u, st, g in zip(t.utility_id_eia, t.state, t.cohort)], kind="stable")]
        out.support_table = t.reset_index(drop=True)
    else:
        out.support_table = union.support_table
    if union.unresolved_ownership is None:
        out.unresolved_ownership = None
    else:
        out.unresolved_ownership = sorted(unresolved, key=lambda v: order[(*dsg._key_of(v["utility"]), int(v["cohort"]))])
    comp_order = {k: i for i, k in enumerate(_keys(union_clean))}
    seen, comps = set(), []
    for x in sorted(out_comps, key=lambda x: comp_order[dsg._key_of(x["utility"])]):
        if x["utility"] not in seen:
            seen.add(x["utility"])
            comps.append(x)
    host_rank = {(u, st): i for (u, st, _), i in sorted(order.items(), key=lambda kv: -kv[1])}
    out.load_unknown_excluded = sorted(out_hosts, key=lambda x: host_rank[dsg._key_of(x["utility"])]) + comps
    out.rules, out.unknown_load_source = union.rules, union.unknown_load_source
    out.pools_by_cohort = {g: _keys(pools[g]) for g in cohorts}
    return out


def same_design(a: dsg.Design, b: dsg.Design) -> list[str]:
    """Where two designs differ (empty: the same hosts, matches, order, pools, windows, drops and tables)."""
    diffs = []
    ha, hb = a.hosts.to_dict("records"), b.hosts.to_dict("records")
    if list(a.hosts.columns) != list(b.hosts.columns):
        diffs.append("host columns")
    if [_norm(x) for x in ha] != [_norm(x) for x in hb]:
        diffs.append("hosts, matches or their order")
    if a.dropped != b.dropped:
        diffs.append("dropped hosts or their order")
    if sorted(a.windows) != sorted(b.windows) or any(a.windows[g].keys != b.windows[g].keys for g in a.windows):
        diffs.append("windows")
    if sorted(a.is_comp) != sorted(b.is_comp) or any(not np.array_equal(a.is_comp[g], b.is_comp[g]) for g in a.is_comp):
        diffs.append("comparison flags by cohort")
    ta, tb = getattr(a, "support_table", None), getattr(b, "support_table", None)
    if (ta is None) != (tb is None) or (ta is not None and not ta.reset_index(drop=True).equals(tb.reset_index(drop=True))):
        diffs.append("support table")
    if getattr(a, "unresolved_ownership", None) != getattr(b, "unresolved_ownership", None):
        diffs.append("hosts with unresolved ownership")
    if getattr(a, "load_unknown_excluded", None) != getattr(b, "load_unknown_excluded", None):
        diffs.append("load-unknown exclusions")
    if a.unit_code != b.unit_code or a.state_code != b.state_code:
        diffs.append("unit or state codes")
    return diffs


def _norm(x):
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_norm(v) for v in x]
    if isinstance(x, np.generic):
        return x.item()
    return x


def compare_to_headline(side: dsg.Design, head: dsg.Design, future: set, names=None) -> dict:
    """The ruling's report: per host, how many of its matches are future hosts and which matches changed; hosts gained
    or lost (support rule or anything else); totals."""
    nm = (lambda k: None if names is None else names.get(k))
    hk = {(tuple(k), int(g)): [tuple(m) for m in mk] for k, g, mk in zip(head.hosts.key, head.hosts.cohort, head.hosts.match_keys)}
    sk = {(tuple(k), int(g)): [tuple(m) for m in mk] for k, g, mk in zip(side.hosts.key, side.hosts.cohort, side.hosts.match_keys)}
    hp = {(tuple(k), int(g)): int(p) for k, g, p in zip(head.hosts.key, head.hosts.cohort, head.hosts.pool_in_the_reference_year)}
    sp = {(tuple(k), int(g)): int(p) for k, g, p in zip(side.hosts.key, side.hosts.cohort, side.hosts.pool_in_the_reference_year)}
    per_host = []
    for (k, g) in sorted(set(hk) | set(sk), key=lambda x: (x[1], x[0])):
        a, b = hk.get((k, g)), sk.get((k, g))
        entry = {"utility": f"{k[0]}:{k[1]}", "name": nm(k), "cohort": g,
                 "in_the_headline_design": a is not None, "in_the_side_run": b is not None,
                 "pool_in_the_reference_year_headline": hp.get((k, g)), "pool_in_the_reference_year_side_run": sp.get((k, g))}
        if b is not None:
            entry["future_hosts_among_its_matches"] = [f"{m[0]}:{m[1]}" for m in b if m in future]
            entry["n_future_hosts_among_its_matches"] = len(entry["future_hosts_among_its_matches"])
        if a is not None and b is not None:
            entry["matches_entered"] = [f"{m[0]}:{m[1]}" for m in b if m not in a]
            entry["matches_left"] = [f"{m[0]}:{m[1]}" for m in a if m not in b]
        per_host.append(entry)
    why = lambda d, k, g: [x["why"] for x in d.dropped if x["utility"] == f"{k[0]}:{k[1]}" and x.get("cohort") in (g, None)]  # noqa: E731
    gained = [{"utility": f"{k[0]}:{k[1]}", "cohort": g, "why_out_of_the_headline_design": why(head, k, g)} for k, g in set(sk) - set(hk)]
    lost = [{"utility": f"{k[0]}:{k[1]}", "cohort": g, "why_out_of_the_side_run": why(side, k, g)} for k, g in set(hk) - set(sk)]
    return {"per_host": per_host, "hosts_gained": sorted(gained, key=lambda x: x["utility"]),
            "hosts_lost": sorted(lost, key=lambda x: x["utility"]),
            "totals": {"hosts_in_the_headline_design": len(hk), "hosts_in_the_side_run": len(sk),
                       "hosts_with_a_future_host_among_their_matches": sum(1 for x in per_host if x.get("n_future_hosts_among_its_matches")),
                       "future_host_matches": sum(x.get("n_future_hosts_among_its_matches", 0) for x in per_host),
                       "distinct_future_hosts_matched": len({m for x in per_host for m in x.get("future_hosts_among_its_matches", [])}),
                       "matches_changed": sum(len(x.get("matches_entered", [])) for x in per_host)}}


# ---- other comparison rules a future host must meet ------------------------------------------------------------------

def other_rule_failures(k: tuple, dose: pd.DataFrame, aside: set, hold: set) -> list[str]:
    """The comparison rules that do not depend on the cohort and are not applied by the matching itself (region,
    ownership, the usable full window and the customer floor are): not set aside, no crypto load of 2% or more, a sales
    base, not held. The load-unknown rule is applied by build_with_rules' gate and reported from it."""
    d = dose[(dose.utility_id_eia == k[0]) & (dose.state == k[1])]
    out = []
    if k in aside:
        out.append("set aside (power_simulation.set_aside at 2%: D-20, D-28 or a treatment_bounds list)")
    crypto = (d.crypto_mw * 8.76 / d.base_retail_gwh).max() if len(d) else 0.0
    if pd.notna(crypto) and crypto >= ps.CRYPTO_LIMIT:
        out.append(f"crypto-mining load of 2% or more (largest {crypto:.1%})")
    if len(d) and not d.base_retail_gwh.notna().any():
        out.append("no 2009-2011 sales base")
    if k in hold:
        out.append("in price_hold.csv")
    return out


# ---- E2 ---------------------------------------------------------------------------------------------------------------

def e2_uncovered_years(key: tuple, f: int, ownership: pd.DataFrame, ownership_of: dict) -> list[int]:
    """The years of the fake window f-6 to f+3 that no ownership row covers, for an investor-owned unit; [] for a public
    or cooperative unit (rule 2.2: its own owner) or one every year of whose window a row covers. A unit with no ownership
    class raises (ownership._ownership), as the matching does."""
    key = (int(key[0]), key[1])
    if own_rules._ownership(ownership_of, key) != own_rules.INVESTOR_OWNED:
        return []
    return [y for y in own_rules.window_years(f) if not len(own_rules._rows(ownership, key, [y]))]


def investor_owned_with_an_uncovered_window_year(admitted_by_cohort: dict, ownership: pd.DataFrame, ownership_of: dict) -> dict:
    """{unit: [cohorts]}: each admitted future host that is investor-owned with no ownership row in SOME year of the cohort's
    window g-6 to g+3, the condition ownership.ineligible_for's rule 2.2 bar applies year by year since Joe's ruling of
    2026-11-19 (D-107). The per-year test is e2_uncovered_years, the same per-year row test the bar uses. Report only."""
    out: dict = {}
    for g, ks in admitted_by_cohort.items():
        for k in ks:
            k = (int(k[0]), k[1])
            if ownership_of.get(k) == own_rules.INVESTOR_OWNED and e2_uncovered_years(k, int(g), ownership, ownership_of):
                out.setdefault(k, []).append(int(g))
    return out


def e2_units(units: dict, aside: set, hold: set, unknown: "ps.UnknownLoad", theta: float = THETA, *,
             ownership: pd.DataFrame | None = None, ownership_of: dict | None = None) -> tuple[pd.DataFrame, list]:
    """(the E2 pseudo-hosts with cohort f, the late hosts left out and why). `units`: {key: history record} as
    `late_host_histories` returns, each with "histories", "complete", "why_incomplete", "slow_path".

    With `ownership` (the ownership table) and `ownership_of` (the panel's classes), a unit that meets every other E2 rule
    and has a fake date is left out if it is investor-owned and some year of its fake window has no covering ownership row
    (Joe's ruling of 2026-11-19 on Entergy Mississippi; the general rule is the session's reading). Its entry in the
    left-out list carries the reason, the uncovered years and `"ownership_rule_of_2026_11_19": True`. Without the table the
    rule is not applied (the behaviour before the ruling)."""
    if ownership is not None and ownership_of is None:
        raise ValueError("the ownership rule for E2 needs ownership_of (the panel's ownership classes) with the table")
    rows, left = [], []
    for k, r in sorted(units.items()):
        why = []
        if not r["complete"]:
            why.append("not shown admissible in every admissible history: " + "; ".join(r["why_incomplete"]))
        allh = _all_histories(r)
        if r["complete"] and not late_in_every_history(allh, theta):
            why.append("not a late host in every admissible history")
        if k in aside:
            why.append("set aside")
        if not unknown.settled(k, theta):
            why.append("reached by a site with no load history and not decided by the enumeration")
        if k in hold:
            why.append("in price_hold.csv")
        f = fake_date(allh, theta) if r["complete"] else None
        if not why and f is None:
            why.append("no year in 2011 to 2022 meets the criterion in every admissible history")
        uncovered = []
        if not why and ownership is not None:
            uncovered = e2_uncovered_years(k, int(f), ownership, ownership_of)
            if uncovered:
                span = (f"every year ({uncovered[0]} to {uncovered[-1]})" if uncovered == own_rules.window_years(int(f))
                        else "the years " + ", ".join(str(y) for y in uncovered))
                why.append(E2_NO_OWNERSHIP_ROW.format(years=span))
        if why:
            entry = {"utility": f"{k[0]}:{k[1]}", "why": why}
            if uncovered:
                entry.update(ownership_rule_of_2026_11_19=True, fake_date_f=int(f),
                             fake_window=[int(f) - ps.PRE, int(f) + ps.POST], years_with_no_ownership_row=uncovered)
            left.append(entry)
        else:
            rows.append({"utility_id_eia": k[0], "state": k[1], "cohort": int(f)})
    return pd.DataFrame(rows, columns=KEY + ["cohort"]), left


def e2_ruling_scope(left: list, names=E2_RULING_NAMES) -> list:
    """The left-out entries the ownership rule made. Raises if the rule removed any unit the ruling of 2026-11-19 does
    not name: the ruling names one unit, so the rule is not applied to another without Joe's word."""
    by_rule = [x for x in left if x.get("ownership_rule_of_2026_11_19")]
    beyond = sorted(x["utility"] for x in by_rule if dsg._key_of(x["utility"]) not in names)
    if beyond:
        raise SystemExit(f"E2's ownership rule would also remove {beyond}; the ruling of 2026-11-19 names one unit "
                         "(Entergy Mississippi), so the rule is not applied to the others and this stops for Joe")
    return by_rule


def _all_histories(r: dict) -> pd.DataFrame:
    h = r["histories"]
    if r.get("slow_path") is not None:
        h = pd.concat([h, pd.DataFrame([r["slow_path"].to_numpy(float)], columns=list(PANEL_YEARS))], ignore_index=True)
    return h


def e2_design(e2: pd.DataFrame, main_clean: pd.DataFrame, late: set, q, regions, fuel, dd,
              rules: ps.Rules = ps.HEADLINE_RULES, **kw) -> dsg.Design:
    """Each E2 unit a pseudo-host of cohort f, matched at f-3 under G-a in the main comparison pool. Other late hosts are
    not in the pool (the main rule keeps every unit under 0.5% throughout, which this asserts), nor is the unit itself."""
    pool = main_clean[KEY].reset_index(drop=True)
    inside = set(_keys(pool)) & (set(late) | set(_keys(e2)))
    if inside:
        raise ValueError(f"late hosts in the main comparison pool: {sorted(inside)}; the main rule should keep them out")
    return dsg.build_with_rules(e2[KEY + ["cohort"]], pool, q, regions, fuel, dd, rules, **kw)


def design_summary(d: dsg.Design, names=None) -> dict:
    nm = (lambda k: None if names is None else names.get(k))
    return {"hosts": [{"utility": f"{k[0]}:{k[1]}", "name": nm(tuple(k)), "cohort": int(g), "region": r,
                       "pool_in_the_reference_year": int(p), "matches": [f"{m[0]}:{m[1]}" for m in mk]}
                      for k, g, r, p, mk in zip(d.hosts.key, d.hosts.cohort, d.hosts.region, d.hosts.pool_in_the_reference_year, d.hosts.match_keys)],
            "dropped": d.dropped,
            "support_rule_by_host": [] if getattr(d, "support_table", None) is None else d.support_table.to_dict("records"),
            "load_unknown_excluded": getattr(d, "load_unknown_excluded", []),
            "hosts_with_unresolved_ownership": getattr(d, "unresolved_ownership", None)}


# ---- main ---------------------------------------------------------------------------------------------------------------

def late_host_histories(theta: float = THETA) -> tuple[dict, dict]:
    """Every late host at theta on the frame, its histories from the place test's objects and the slow path, and its
    coverage. Also checks that each one's place test reproduces the frozen data/frozen/timing_place_test.json row."""
    from pipeline.facilities import assignment as asg
    from pipeline.facilities import timing
    inp, corrections = enumeration_inputs()
    entries = timing.timing_entries(corrections)
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    late = late_hosts_on_the_frame(dose, theta)
    frozen = {(r["utility"], r["theta"]): r for r in json.loads((FROZEN / "timing_place_test.json").read_text())["utilities"]}
    fac_raw = pd.read_parquet(INTERIM / "facilities.parquet")
    fy = pd.read_parquet(INTERIM / "facility_year.parquet")
    fy = fy[~fy.crypto][["fid"] + asg.KEY + ["year", "mw"]]
    base_frame = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh
    slow = slow_path_histories(fac_raw, fy, base_frame, list(late))
    out, check = {}, {"compared_fields": ["keeps_its_place", "configurations_by_screen_shift", "range", "status", "method"],
                      "units": [], "all_reproduce": True}
    for st in sorted({s for _, s in late}):
        sr = timing.StateRun(inp, entries, st)
        for k in sorted(x for x in late if x[1] == st):
            r = histories_from_state_run(sr, k, theta)
            ev = sr.evaluate(k, theta)
            fr = frozen.get((f"{k[0]}:{k[1]}", theta))
            same = fr is not None and all(ev[f] == fr[f] for f in check["compared_fields"])
            check["units"].append({"utility": f"{k[0]}:{k[1]}", "reproduces": same})
            check["all_reproduce"] &= same
            r["slow_path"] = slow[k]
            r["frame_first_crossing"] = late[k]
            r["frame_base_equals_enumeration_base"] = bool(np.isclose(base_frame[k], float(inp.base[k]), rtol=0, atol=1e-9))
            r["place_test"] = {"keeps_its_place": ev["keeps_its_place"], "status": ev["status"], "method": ev["method"]}
            out[k] = r
    return out, check


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    from pipeline.analysis import usable_flag
    rules = ps.HEADLINE_RULES
    units, check = late_host_histories(THETA)
    if not check["all_reproduce"]:
        raise SystemExit("a late host's place test does not reproduce the frozen timing_place_test.json; stopping")
    q, dose, regions, fuel, dd = dsg.load()
    names = q.groupby(KEY).utility_name.last()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    aside, hold = ps.set_aside(THETA), ps.price_hold()
    kw = dict(ownership=ownership, usable=usable, gas=gas, ownership_of=ownership_of, unknown_load=unknown, theta=THETA)
    treated, clean = dsg.split(THETA, ps.HEADLINE_SET, q, dose)
    head = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, rules, **kw)

    # The headline design as it stands, against the frozen record of it (design_support.json, headline_set).
    rec = json.loads((FROZEN / "design_support.json").read_text())["sets"][ps.HEADLINE_SET]["hosts"]
    frozen_matches = {x["utility"]: [m["utility"] for m in x["matched_utilities"]] for x in rec}
    built_matches = {f"{k[0]}:{k[1]}": [f"{m[0]}:{m[1]}" for m in mk] for k, mk in zip(head.hosts.key, head.hosts.match_keys)}
    unchanged_against_frozen = frozen_matches == built_matches
    empty = side_run_design(treated, clean, {}, q, regions, fuel, dd, rules, **kw)
    wrapper_diffs = same_design(empty, head)

    per_unit, admitted_by_cohort, criterion_only = {}, {}, {}
    slow_removed = []
    for k, r in sorted(units.items()):
        fails = other_rule_failures(k, dose, aside, hold)
        cohorts = admitted_cohorts(_all_histories(r), THETA) if r["complete"] else []
        without_slow = admitted_cohorts(r["histories"], THETA) if r["complete"] else []
        if without_slow != cohorts:
            slow_removed.append({"utility": f"{k[0]}:{k[1]}", "cohorts_without": without_slow, "cohorts_with": cohorts})
        allh = _all_histories(r)
        c = first_crossings(allh, THETA) if len(allh) else np.array([])
        per_unit[f"{k[0]}:{k[1]}"] = {
            "name": names.get(k), "first_crossing_on_the_frame": r["frame_first_crossing"],
            "place_test_reference": r["coverage"]["reference"], "place_test_verdict": r["place_test"],
            "coverage_complete": r["complete"], "why_incomplete": r["why_incomplete"],
            "coverage": r["coverage"],
            "slow_path_history_added": True,
            "first_crossing_across_its_histories": None if not len(c) else
                {"earliest": None if np.isnan(c).all() else int(np.nanmin(c)), "latest": "never" if np.isnan(c).any() else int(np.nanmax(c))},
            "late_host_in_every_admissible_history": late_in_every_history(allh, THETA) if r["complete"] else None,
            "criterion_holds_for_cohorts": cohorts if r["complete"] else "not shown: coverage incomplete",
            "other_comparison_rules_failed": fails,
        }
        for g in cohorts:
            criterion_only.setdefault(g, []).append(f"{k[0]}:{k[1]}")
            if not fails:
                admitted_by_cohort.setdefault(g, []).append(k)

    side = side_run_design(treated, clean, admitted_by_cohort, q, regions, fuel, dd, rules, **kw)
    future = {k for ks in admitted_by_cohort.values() for k in ks}
    report = compare_to_headline(side, head, future, names)
    headline_cohorts = sorted(int(g) for g in treated.cohort.unique())
    pool_added = {}
    for g in headline_cohorts:
        gated = set(_keys(unknown.gate(pd.DataFrame(admitted_by_cohort.get(g, []), columns=KEY), THETA, "comparison")[0]))
        w = side.windows.get(g)
        in_window = [f"{k[0]}:{k[1]}" for k in admitted_by_cohort.get(g, []) if w is not None and k in w.keys]
        pool_added[str(g)] = {"admitted_and_meeting_the_other_rules": [f"{k[0]}:{k[1]}" for k in admitted_by_cohort.get(g, [])],
                              "after_the_load_unknown_gate": sorted(f"{k[0]}:{k[1]}" for k in gated),
                              "with_a_usable_full_window_in_the_cohorts_window": in_window}

    e2, e2_left = e2_units(units, aside, hold, unknown, THETA, ownership=ownership, ownership_of=ownership_of)
    by_rule = e2_ruling_scope(e2_left)
    main_clean = clean
    e2d = e2_design(e2, main_clean, set(units), q, regions, fuel, dd, rules, **kw) if len(e2) else None
    # For the record: E2 as it stood before the ruling (no ownership rule), to show what the exclusion changes.
    e2_before, _ = e2_units(units, aside, hold, unknown, THETA)
    e2d_before = e2_design(e2_before, main_clean, set(units), q, regions, fuel, dd, rules, **kw) if len(e2_before) else None
    kept_before = {} if e2d_before is None else {f"{k[0]}:{k[1]}": [f"{m[0]}:{m[1]}" for m in mk]
                                                 for k, mk in zip(e2d_before.hosts.key, e2d_before.hosts.match_keys)}
    kept_after = {} if e2d is None else {f"{k[0]}:{k[1]}": [f"{m[0]}:{m[1]}" for m in mk]
                                         for k, mk in zip(e2d.hosts.key, e2d.hosts.match_keys)}
    removed_labels = {x["utility"] for x in by_rule}
    e2_ruling = {
        "ruling": E2_RULING_2026_11_19,
        "existing_permitted_evidence_checked": E2_EVIDENCE_CHECKED,
        "rule_as_implemented": ("any investor-owned pseudo-host (the panel's ownership class) with a year of its fake window "
                                "f-6 to f+3 that no row of ownership.csv covers is left out of E2 and named; the session's "
                                "reading of the ruling, applied as a rule of E2's unit selection only"),
        "units_the_rule_removes": [{**x, "name": names.get(dsg._key_of(x["utility"])),
                                    "matches_before_the_ruling": kept_before.get(x["utility"])} for x in by_rule],
        "units_before_the_ruling": sorted(kept_before),
        "units_after_the_ruling": sorted(kept_after),
        "other_units_matches_unchanged": all(kept_before[u] == kept_after.get(u) for u in kept_before if u not in removed_labels),
        "headline_host_eligibility": ("unchanged: the rule is applied to E2's units only; the headline design is built "
                                      "by design.split and build_with_rules with no input from it (see "
                                      "side_run.headline_pool_unchanged)"),
    }

    # Report only (Joe's ruling speaks to E2, so nothing in the side run is changed): where each admitted future host that
    # is investor-owned with no ownership row in some year of a headline cohort's window stands in each headline host's
    # pool, and whether rule 2.2's bar (ownership.ineligible_for, NO_ROW, read year by year since D-107) is applied to it.
    io_no_row = investor_owned_with_an_uncovered_window_year(admitted_by_cohort, ownership, ownership_of)
    side_bar = []
    for k, gs in sorted(io_no_row.items()):
        rows_ = []
        for h in side.hosts.to_dict("records"):
            g = int(h["cohort"])
            if g not in gs:
                continue
            w = side.windows[g]
            j = w.keys.index(k) if k in w.keys else None
            excl = [x["why"] for x in h.get("excluded_from_its_pool", []) if x["utility"] == f"{k[0]}:{k[1]}"]
            rows_.append({"host": f"{h['key'][0]}:{h['key'][1]}", "host_name": names.get(tuple(h["key"])), "cohort": g,
                          "host_ownership_class": ownership_of.get(tuple(h["key"])),
                          "host_region": w.region[h["row"]],
                          "unit_region_in_the_reference_year": None if j is None else w.region[j],
                          "in_the_hosts_in_region_pool": bool(j is not None and side.is_comp[g][j] and w.region[j] == w.region[h["row"]]),
                          "barred_from_its_pool_by": excl, "among_its_matches": k in [tuple(m) for m in h["match_keys"]]})
        side_bar.append({"utility": f"{k[0]}:{k[1]}", "name": names.get(k), "ownership_class": ownership_of.get(k),
                         "admitted_for_cohorts": sorted(gs), "headline_hosts_of_those_cohorts": rows_})

    doc = {
        "what_this_is": ("Provisional, quantity-only: the future-host criterion applied to the late hosts at 2%, the side run "
                         "'Future hosts as a second comparison group' under Joe's ruling of 2026-11-19, and E2's units, fake "
                         "dates and design. The design stands as of 2026-11-18 and the plan is not frozen. Load, sales, "
                         "customers, regions, ownership and the usable flag only; no price, revenue or bill is read."),
        "ruling_of_2026_11_19": ("Add eligible future hosts to each cohort's side-run comparison pool and match under the "
                                 "existing rules. Report how many enter the matches and any sample changes. This does not "
                                 "change the headline pool."),
        "criterion": {"quiet_through": "g+3, share under 0.5% in every year from 2001", "first_crossing_at_least": "g+7",
                      "threshold": THETA, "every_history": True,
                      "agent_reading_no_crossing_in_the_panel": ("a history with no crossing through 2025 meets 'g+7 or "
                                                                 "later' only where g+7 is 2026 or earlier")},
        "histories": {
            "source": ("timing.StateRun's screen cases and pass_c_exact._State.grid over each unit's relevant questions, one "
                       "representative per class of settings merged for the unit; both readings; plus the slow path of "
                       "headline-set rule 2 (adopted by Joe on 2026-11-19, D-111)"),
            "inputs_note": ("timing.load_rebuilt reads data/interim/epoch_gaps.parquet, which this pass may not read; it "
                            "sets a value read only for fixed-history rows with a not_a_site correction, and none is in "
                            "force. Every late host's place test reproduces the frozen one (place_test_reproduction)."),
            "outside_the_admissible_histories_by_the_plans_definition": NOT_ADMISSIBLE_BY_DEFINITION,
            "slow_path_changed_an_admission": slow_removed,
        },
        "place_test_reproduction": check,
        "late_hosts_at_2pct": per_unit,
        "late_hosts_not_shown_admissible_in_every_admissible_history": [
            {"utility": u, "name": v["name"], "why": v["why_incomplete"]} for u, v in per_unit.items() if not v["coverage_complete"]],
        "criterion_holds_by_cohort_before_the_other_rules": {str(g): v for g, v in sorted(criterion_only.items())},
        "admitted_by_cohort_meeting_the_other_rules": {str(g): [f"{k[0]}:{k[1]}" for k in v] for g, v in sorted(admitted_by_cohort.items())},
        "side_run": {
            "hosts": "the headline set's",
            "headline_cohorts": headline_cohorts,
            "future_hosts_added_to_each_headline_cohorts_pool": pool_added,
            "headline_pool_unchanged": {
                "headline_design_against_design_support_json": unchanged_against_frozen,
                "wrapper_with_nobody_admitted_equals_the_headline_design": not wrapper_diffs, "differences": wrapper_diffs,
                "headline_pool": "built by design.build_with_rules from design.split; this module never passes its additions to it"},
            "against_the_headline_design": report,
            "investor_owned_future_hosts_with_no_ownership_row_and_rule_2_2": {
                "what_this_is": ("report only, nothing changed (Joe's ruling of 2026-11-19 speaks to E2 alone): each admitted "
                                 "future host that is investor-owned with no ownership row in some year of a headline cohort's "
                                 "window (rule 2.2 read year by year, Joe, 2026-11-19, D-107), and "
                                 "for each headline host of that cohort whether the unit is in its in-region pool and whether "
                                 "rule 2.2's bar (ownership.ineligible_for, NO_ROW) removes it there. The bar is applied by "
                                 "build_with_rules inside side_run_design to every host's in-region pool; it bites only on an "
                                 "investor-owned host, and only on units in the host's region in the reference year."),
                "units": side_bar},
            "design": design_summary(side, names),
        },
        "E2": {
            "units": [{"utility": f"{int(u)}:{st}", "name": names.get((int(u), st)), "fake_date_f": int(f),
                       "window": [int(f) - ps.PRE, int(f) + ps.POST], "reference_year": int(f) + ps.REF,
                       "first_crossing_on_the_frame": units[(int(u), st)]["frame_first_crossing"]}
                      for u, st, f in zip(e2.utility_id_eia, e2.state, e2.cohort)],
            "left_out": [{**x, "name": names.get(dsg._key_of(x["utility"]))} for x in e2_left],
            "pseudo_hosts_with_no_ownership_row_ruling_of_2026_11_19": e2_ruling,
            "pool": "the headline design's eligible comparison pool (design.split, headline set); no late host is in it",
            "design": None if e2d is None else design_summary(e2d, names),
        },
        "inputs": {p: _hash(ROOT / p) for p in ("data/interim/facilities.parquet", "data/interim/facility_year.parquet",
                                               "data/interim/state_anchor.parquet", "data/interim/utility_year_dose.parquet",
                                               "data/frozen/timing_place_test.json", "data/frozen/treatment_bounds.json",
                                               "data/frozen/design_support.json", "pipeline/analysis/future_hosts.py",
                                               "pipeline/analysis/design.py", "pipeline/facilities/timing.py",
                                               "pipeline/facilities/pass_c_exact.py", "pipeline/facilities/pass_c_expand.py")},
    }
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps({"late_hosts": len(per_unit),
                      "not_shown_admissible": [x["utility"] for x in doc["late_hosts_not_shown_admissible_in_every_admissible_history"]],
                      "admitted_by_cohort": doc["admitted_by_cohort_meeting_the_other_rules"],
                      "side_run_totals": report["totals"], "e2_units": doc["E2"]["units"],
                      "headline_unchanged": doc["side_run"]["headline_pool_unchanged"]}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
