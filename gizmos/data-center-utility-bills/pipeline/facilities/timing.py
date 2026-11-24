#!/usr/bin/env python3
"""Step D's place test on the rebuilt inventory (docs/gate1/step-d-inventory-design-2026-11-18.md, section 2 and the
addendum recording Joe's rulings of 2026-11-18). Load and sales only: nothing here reads a price, opens data/blind or
touches the availability files.

What it decides, per utility and threshold
------------------------------------------
The REFERENCE is the utility's group and first crossing on the corrected inventory as built: every correction in force
applied, every convention year in place, each state's factor recomputed (D-61 5.4, addendum point 6). It is
pass_c_exact.reference_of with the exact attribution's list of reference-defining questions, so a reference that turns
on a provisional convention (Joe, R1) or on a row whose start is unresolved and whose load is unknown (Joe, R2) is
UNDEFINED, and the utility is unsettled, never kept.

A utility KEEPS ITS PLACE if, in every admissible history, its place as built is the reference's and (cohort) both first
crossings, as built and with no anchoring, are within one year of the reference's, (early) the crossing with no
anchoring is early too, (comparison) the largest share with no anchoring is under 0.5% (pass_c_exact._outcomes, its
"accepted" flag). The admissible histories are every combination, one setting per site (consistent settings and their
dependencies), of:
  * each unresolved assignment: each candidate, the utility it is on, off the panel (ruling 4, as the exact attribution
    enumerates it);
  * each date question at every year of its interval, open below where it is (full load from 2001), "never" where the
    interval allows it;
  * each capacity question;
  * the generic screen, CROSSED with all of the above (Joe, R10): every still permit-dated row of 20 MW or more that has
    no interval and no known phases is started 0, 3 or 5 years earlier, one shift for all of them in the state, and
    the state's factor is recomputed in every configuration.
The state's factor is recomputed in every configuration (pass_c_exact._State.grid).

The CEILING: 100,000 configurations PER PREDEFINED SCREEN CASE, the same for every utility (Joe, Stop 3, 2026-11-18,
amending R6). Within each screen case (shift 0, 3 or 5) the count is the utility's full dependency component across
every factor configuration, joint settings and dependencies preserved: the product of its relevant questions' merged
classes in that case. Cases are not subdivided further. A case at or under the ceiling is enumerated completely; a case
over it goes to the conservative envelope (pass_c_expand.joint_check's bounds), which either settles that case or leaves
it unsettled. A utility keeps its place only if it does in EVERY case; a case that fails, exactly or by the envelope,
means it does not; otherwise a case the envelope cannot settle leaves it UNSETTLED, described by what is actually
uncertain (assignment, timing, capacity, anchoring, comparison eligibility). Exact conclusions are used in either
direction. Until 2026-11-18 the rule was the ceiling against the three cases' counts SUMMED (R6 as first applied, D-96's
wording), with every case going to the envelope when the sum was over it; Joe amended it at Stop 3 with its design
consequences known (Arizona Public Service and Sacramento among them). The summed rule survives only as
`rule=SUMMED_SUPERSEDED`, read by nothing but the record of what the amendment changed (`--compare-ceiling-per-screen-
case`, data/frozen/timing_ceiling_per_screen_case_comparison.json). The exact attribution's own ceiling per dependency
component (pass_c_exact) is unchanged.

A STRESS SCENARIO (Joe, R4) is a date entry's `stress` field, {"start": null | year, "label": "...", "reason": optional}:
start null is the whole row at full load from 2001. It is evaluated every other question at the reference. It never
defines a reference and is never an admissible history. But eligibility stays unresolved where the distinction matters
(Joe, R4: "Preserve unresolved eligibility where the distinction matters"; D-96): a utility whose outcome under the
stress is not accepted against its reference is marked `unresolved_by_stress`, with its own reason (by default
STRESS_REASON), and does not keep its place; treatment_bounds carries it in a list of its own. A utility whose outcome
is the same with and without the stress is unaffected.

THE FIVE OREGON ROWS (corrections.FIRST_FUEL_NOT_A_START; Joe, Stop 3, 2026-11-18): first generator fuel bounds nothing,
and each row is dated by its own date entry in the corrections file in force, like any other dated row, so it leaves the
generic screen: bi:820-0 not before 2018 (a new-source construction permit on file), the other four open below; every
late end is the permit-based year, a labelled convention and a tested end. Nothing in this module special-cases them.
Until 2026-11-18 they sat in the generic screen as plain permit-dated rows (the session's application of D-96 (1),
overruled at Stop 3).

THE LOOSER OREGON READING (`--compare-oregon-looser-reading`; `compare_oregon_looser_reading`): a labelled comparison
that decides nothing and that treatment_bounds never reads. It shows each Oregon utility's verdict as in force beside
its verdict if bi:822-0 and bi:823-0 were also bounded not before 2018 (the reading in which the recorder's note "new
source" counts as the permit's kind).

OPEN BELOW ONLY: a utility whose every failing configuration has some open-below date at its open-below setting is
listed apart, with the generic screen's result and the permit-error reach (D-58 rule 1.6 (b): the lower end is the
latest year less the 95th percentile of measured permit lateness for the row's size class, recomputed from the rebuilt
dating_report.json) beside it, and is described as unsettled on timing under a bounding assumption, not as misdated.

Output: data/frozen/timing_place_test.json and data/frozen/timing_place_test_by_utility.csv, each with a fingerprint.
Run:  python3 -I pipeline/facilities/timing.py [--corrections FILE] [--ceiling 100000]     (after build_inventory.py)
      python3 -I pipeline/facilities/timing.py --compare-ceiling-per-screen-case     (the amendment's record)
      python3 -I pipeline/facilities/timing.py --compare-oregon-looser-reading       (labelled; decides nothing)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import buildout  # noqa: E402
from pipeline.facilities import corrections as cx  # noqa: E402
from pipeline.facilities import pass_c_exact as pe  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"
SNAPSHOT = INTERIM / "snapshot-2026-11-14"
CEILING = pe.CEILING
CEILING_RULE = "per_screen_case"                  # in force since Joe's amendment at Stop 3, 2026-11-18
SUMMED_SUPERSEDED = "summed_until_2026_11_18"     # the superseded rule; read only by the amendment's record
CEILING_RULES = (CEILING_RULE, SUMMED_SUPERSEDED)
# The looser reading of two Oregon rows (labelled comparison only): the recorder's note "new source" taken as the
# permit's kind, so each is bounded not before its permit's year.
OREGON_LOOSER_READING = {"bi:822-0": 2018, "bi:823-0": 2018}
SCREEN = (0, 3, 5)
SCREEN_MIN_MW = 20.0
THRESHOLDS = (0.02, 0.05)
PLACES = pe.PLACES
STRESS_REASON = "unresolved: which building the row carries is not settled (D-96)"
SIZE_CLASSES = (("under_20", 0.0, 20.0), ("20_to_50", 20.0, 50.0), ("50_plus", 50.0, math.inf))


# ---- inputs ---------------------------------------------------------------------------------------------------------

def patch_unknown(fac: pd.DataFrame) -> pd.DataFrame:
    """The frame carries no year for a LOAD UNKNOWN row; the enumeration needs its inventory year (a capacity split's late
    case) and rebuilds every admissible history of it from its correction. The patch is on a copy and never written."""
    fac = fac.copy()
    if "load_unknown" in fac:
        unk = fac.load_unknown.fillna(False).astype(bool)
        fac.loc[unk, "energized_year"] = fac.loc[unk, "date_inventory_year"].astype(float)
    return fac


def load_rebuilt() -> px.Inputs:
    """pass_c_expand.load_frozen's inputs, read from the rebuilt data/interim, with the unknown-load rows patched."""
    fac, fy, q, units, base, regions = asg.load_inputs()
    fac = patch_unknown(fac)
    fy_all = pd.read_parquet(INTERIM / "facility_year.parquet")
    anchor = pd.read_parquet(INTERIM / "state_anchor.parquet").set_index("state")
    gaps = pd.read_parquet(INTERIM / "epoch_gaps.parquet").set_index("fid")
    phases = buildout.phases_by_site(buildout.load())
    names = q.groupby(asg.KEY).utility_name.last()
    fixed = fac.index[(fac.src == "epoch") | (fac.load_history == "operator_reported_energy")]
    y24 = fy_all[fy_all.year == px.ANCHOR_YEAR].groupby("fid").mw.sum()
    frozen_2024 = {}
    for fid in fixed:
        if fid in gaps.index and gaps.sourced_start[fid] <= px.ANCHOR_YEAR < gaps.first_entry_year[fid]:
            frozen_2024[fid] = 0.0
        elif bool(fac.in_dose[fid]):
            frozen_2024[fid] = float(y24.get(fid, 0.0))
    return px.Inputs.build(fac, fy, units, base, regions, names, anchor, phases, frozen_2024, fy_all)


def timing_entries(corrections: list[dict]) -> list[dict]:
    """The corrections in force that carry a history question (dates, capacity, size, phases, not_a_site)."""
    _, t = cx.split(corrections)
    return cx.stripped(t)


def screen_rows(inp: px.Inputs, st: str, exclude: set) -> list[str]:
    """Still permit-dated rows of 20 MW or more in the state, with no interval, no known phases, no fixed history."""
    f = inp.fac[inp.fac.state == st]
    keep = ((f.date_basis == cx.PERMIT_LABEL) & f.in_dose.astype(bool) & ~f.is_crypto.astype(bool)
            & (f.mw_full >= SCREEN_MIN_MW) & f.energized_year.notna())
    return [fid for fid in f.index[keep] if fid not in exclude and fid not in inp.phases and not bool(inp.fixed[fid])]


def fixed_date(fid: str, year: int) -> dict:
    return {"fid": fid, "kind": "date", "earliest": int(year), "latest": int(year), "never_is_possible": False,
            "convention": int(year), "ends": "tested"}


def screen_entries(inp: px.Inputs, st: str, shift: int, exclude: set) -> list[dict]:
    if not shift:
        return []
    return [fixed_date(fid, int(inp.fac.energized_year[fid]) - shift) for fid in screen_rows(inp, st, exclude)]


# ---- one state ------------------------------------------------------------------------------------------------------

def _below(S: pe._State, rel: list, shape: tuple, open_below: dict, floor: int) -> np.ndarray:
    """Per configuration: True where some open-below date question sits in a class all of whose years are earlier than
    min(floor, the question's convention). Those are the configurations a sourced lower end at `floor` would rule out."""
    n = int(np.prod(shape)) if shape else 1
    out = np.zeros(n, dtype=bool)
    if not rel:
        return out
    grids = np.indices(shape).reshape(len(shape), -1)
    for p, (qid, cl) in enumerate(rel):
        q = S.qs[qid]
        if q.name != "date" or q.fid not in open_below:
            continue
        lim = min(floor, open_below[q.fid]) if open_below[q.fid] is not None else floor
        early = np.array([all(q.values[j] != "never" and int(q.values[j]) < lim for j in g) for g in cl], dtype=bool)
        out |= early[grids[p]]
    return out


def _kind(q) -> str:
    return {"assignment": "assignment", "date": "timing", "capacity": "capacity"}[q.name]


def _setting(S: pe._State, axes: list, shape: tuple, i: int) -> dict:
    at = np.unravel_index(i, shape) if axes else ()
    return {f"{S.qs[qid].fid} {S.qs[qid].name}": pe._value(S.qs[qid].values[sel[at[p]]]) for p, (qid, sel) in enumerate(axes)}


class StateRun:
    """Every screen case of one state, built once and evaluated per utility."""

    def __init__(self, inp: px.Inputs, entries: list[dict], st: str, screen=SCREEN, refs: dict | None = None):
        self.inp, self.st = inp, st
        mine = [c for c in entries if inp.fac.state.get(c["fid"]) == st]
        self.base_entries = mine
        exclude = {c["fid"] for c in mine}
        self.cases = []
        for sh in screen:
            ent = mine + screen_entries(inp, st, sh, exclude)
            corr = px.parse_corrections(ent, inp)
            self.cases.append({"shift": sh, "corr": corr, "S": pe._State(inp, corr, st), "jc": None})
        self.refs = refs or {}
        self.ends = {c["fid"]: c.get("ends", "tested") for c in mine if c["kind"] == "date"}
        # fid -> its convention (None if it has none): the date questions whose interval is open below
        self.open_below = {c["fid"]: c.get("convention") if isinstance(c.get("convention"), int) else None
                           for c in mine if c["kind"] == "date" and c.get("earliest") is None}

    def reference(self, k, theta: float):
        if (k, theta) in self.refs:
            return self.refs[(k, theta)]
        S0 = self.cases[0]["S"]
        base_k = float(self.inp.base.get(k, np.nan))
        rec, ref = pe.reference_of(S0, k, base_k, theta, S0.defining("exact"), CEILING)
        self.refs[(k, theta)] = (rec, ref)
        return rec, ref

    def joint(self, i: int, theta: float) -> dict:
        key = ("jc", theta)
        c = self.cases[i]
        if c.get(key) is None:
            c[key] = px.joint_check(self.inp, c["corr"], self.st, theta)
        return c[key]

    def evaluate(self, k: tuple, theta: float, ceiling: int = CEILING, rule: str = CEILING_RULE) -> dict:
        """The place test for utility k. The rule in force (CEILING_RULE, Joe at Stop 3, 2026-11-18): each screen case is
        enumerated completely where its own count is at or under the ceiling, and only a case over it goes to the
        envelope. SUMMED_SUPERSEDED is the rule until 2026-11-18, kept only for the amendment's record: the cases' counts
        summed against the ceiling and, over it, every case to the envelope."""
        if rule not in CEILING_RULES:
            raise ValueError(f"unknown ceiling rule {rule!r}; in force: {CEILING_RULE!r}")
        per_case = rule == CEILING_RULE
        base_k = float(self.inp.base.get(k, np.nan))
        rec, ref = self.reference(k, theta)
        out = {"utility": f"{k[0]}:{k[1]}", "name": self.inp.names.get(k), "theta": theta,
               "reference": {"defined": rec["defined"], "place": rec["place"], "crossing": rec["crossing"],
                             "why_undefined": rec["why_undefined"],
                             "undefined_by": rec["undefined_by"]},
               "keeps_its_place": None, "status": "", "method": None, "configurations": 0, "uncertain_in": [],
               "failure": None, "fails_only_open_below": False, "by_screen_shift": {}, "range": None, "range_kind": None,
               "keeps_with_assignment_as_mapped": None, "unresolved_by_stress": [], "ceiling_rule": rule}
        rels = []
        for c in self.cases:
            fm, rel = c["S"].relevance(k)
            rels.append((fm, rel))
        ns = [int(math.prod(len(cl) for _, cl in rel)) for _, rel in rels]
        n = sum(ns)
        out["configurations"] = int(n)
        out["configurations_by_screen_shift"] = {str(c["shift"]): m for c, m in zip(self.cases, ns)}
        env = [m > ceiling for m in ns] if per_case else [n > ceiling] * len(ns)
        kinds = set()
        for (fm, rel), c in zip(rels, self.cases):
            kinds |= {_kind(c["S"].qs[qid]) for qid, _ in rel}
            if fm:
                kinds.add("anchoring")
        timing_q = [(c["S"].qs[qid]) for (fm, rel), c in zip(rels, self.cases) for qid, _ in rel
                    if c["S"].qs[qid].name in ("date", "capacity")]
        out["range_kind"] = ("inventory dates only" if not timing_q else
                             "admissible" if all(q.name == "date" and self.ends.get(q.fid) == "evidence" for q in timing_q)
                             else "tested")
        if ref is None:
            out.update(status="unsettled: the reference is undefined (" + str(rec["why_undefined"]) + ")",
                       uncertain_in=sorted(kinds | {_kind_of(x) for x in rec["undefined_by"]}))
            return out
        if PLACES[ref[0]] == "comparison":
            kinds.add("comparison eligibility")
        if all(env):
            return self._envelope(k, theta, ref, out, kinds, ceiling, per_case)
        out["method"] = "exact" if not any(env) else "exact where a case is under the ceiling, envelope where it is over"
        lo, hi, places, fails = None, None, set(), []
        as_mapped_ok = True
        evaluated = []
        env_unsettled, env_uncertain = [], set()
        for i, ((fm, rel), c) in enumerate(zip(rels, self.cases)):
            if env[i]:
                ok, unc = self._envelope_case(i, k, theta, ref, base_k)
                out["by_screen_shift"][str(c["shift"])] = ok
                if ok is None:
                    env_unsettled.append(c["shift"])
                    env_uncertain |= unc
                    as_mapped_ok = False if as_mapped_ok is False else None
                elif not ok:
                    fails.append({"screen_shift": c["shift"], "settings": "over the ceiling in this case; the envelope settles it"})
                    as_mapped_ok = None if as_mapped_ok is not False else False
                continue
            S = c["S"]
            axes = [(qid, [g[0] for g in cl]) for qid, cl in rel]
            ab, na, shape = S.grid(k, axes)
            _, parts = pe._outcomes(ab, na, base_k, theta, ref)
            acc = parts["acc"]
            c_ab = parts["c_ab"]
            dated = c_ab[c_ab != pe.NEVER]
            if len(dated):
                lo = min(lo, int(dated.min())) if lo is not None else int(dated.min())
                hi = max(hi, int(dated.max())) if hi is not None else int(dated.max())
            if (c_ab == pe.NEVER).any():
                hi = pe.NEVER
            places |= {PLACES[int(p)] for p in np.unique(parts["p_ab"])}
            ok = bool(acc.all())
            out["by_screen_shift"][str(c["shift"])] = ok
            evaluated.append((S, rel, shape, acc))
            mapped = np.ones(acc.shape, dtype=bool)                     # every unresolved site where the inventory has it
            if rel:
                grids = np.indices(shape).reshape(len(shape), -1)
                for p, (qid, cl) in enumerate(rel):
                    if S.qs[qid].name == "assignment":
                        mapped &= grids[p] == next(i for i, g in enumerate(cl) if S.qs[qid].default in g)
            if as_mapped_ok is not False:
                as_mapped_ok = as_mapped_ok if bool(acc[mapped].all()) else False
            if not ok:
                i = int(np.flatnonzero(~acc)[0])
                fails.append({"screen_shift": c["shift"], "settings": _setting(S, axes, shape, i),
                              "place_as_built": PLACES[int(parts["p_ab"][i])], "crossing_as_built": pe._year(int(parts["c_ab"][i])),
                              "crossing_no_anchoring": pe._year(int(parts["c_na"][i])),
                              "largest_share_no_anchoring": pe._share(float(parts["s_na"][i]))})
        out["range"] = {"earliest_crossing": None if lo is None else pe._year(lo),
                        "latest_crossing": None if hi is None else pe._year(hi), "places": sorted(places)}
        out["uncertain_in"] = sorted(kinds)
        out["keeps_with_assignment_as_mapped"] = as_mapped_ok
        if env_unsettled and not fails:
            out.update(keeps_its_place=None, uncertain_in=sorted(env_uncertain or kinds),
                       status=(f"unsettled: screen case(s) {env_unsettled} over the ceiling of {ceiling} on their own, and "
                               f"the envelope cannot settle them; uncertain in " + ", ".join(sorted(env_uncertain or kinds))))
            return out
        if not fails:
            out.update(keeps_its_place=True, status="keeps its place within the modeled histories")
            return out
        # Open below only (D-59 item 1; Joe at 1528): it would keep its place if its open-below questions had a sourced
        # lower end; the latest such end tried is each question's own convention, then earlier years.
        def passes(floor):
            return all(bool(acc[~_below(S, rel, shape, self.open_below, floor)].all()) for S, rel, shape, acc in evaluated)
        top = max([v for v in self.open_below.values() if v is not None] or [px.YEARS[-1]])
        ob_only = bool(self.open_below) and not any(env) and passes(top + 1)
        lower = None
        if ob_only:
            for floor in range(top, px.OPEN_BELOW_START - 1, -1):
                if not passes(floor):
                    break
                lower = floor
        out.update(keeps_its_place=False, failure=fails[0], fails_only_open_below=ob_only,
                   lower_end_that_would_let_it_stay=lower,
                   status=("does not keep its place only under the open-below bounding assumption: unsettled on timing "
                           "under a bounding assumption, not misdated" if ob_only else "does not keep its place"))
        return out

    def _envelope_case(self, i: int, k, theta, ref, base_k) -> tuple:
        """One screen case by the envelope: (True | False | None for unsettled, what is uncertain)."""
        key = f"{k[0]}:{k[1]}"
        c = self.cases[i]
        u = self.joint(i, theta)["utilities"].get(key, {"n_unsettled": 0, "kept_questions": [], "unsettled": []})
        if u["n_unsettled"]:
            uncertain = set()
            for q in u["kept_questions"]:
                uncertain.add({"assignment": "assignment", "date": "timing", "capacity": "capacity"}[q["question"]])
                if q["channel"] in ("factor", "both"):
                    uncertain.add("anchoring")
            if any(cell[2] == asg.CLEAN_BELOW for cell in u["unsettled"]):
                uncertain.add("comparison eligibility")
            return None, uncertain
        ab, na, _ = c["S"].grid(k, [])
        _, parts = pe._outcomes(ab, na, base_k, theta, ref)
        return bool(parts["acc"].all()), set()

    def _envelope(self, k, theta, ref, out, kinds, ceiling: int = CEILING, per_case: bool = True) -> dict:
        out["method"] = "envelope"
        over = (f"every screen case over the ceiling of {ceiling} on its own "
                f"({', '.join(f'{s}: {n}' for s, n in out['configurations_by_screen_shift'].items())})" if per_case
                else f"{out['configurations']} configurations, over the ceiling of {ceiling}")
        base_k = float(self.inp.base.get(k, np.nan))
        all_settled, refused = True, False
        uncertain = set()
        for i, c in enumerate(self.cases):
            ok, unc = self._envelope_case(i, k, theta, ref, base_k)
            out["by_screen_shift"][str(c["shift"])] = ok
            if ok is None:
                all_settled = False
                uncertain |= unc
            else:
                refused |= not ok
        out["keeps_with_assignment_as_mapped"] = (True if (all_settled and not refused) else None)
        if refused:
            out.update(keeps_its_place=False, status="does not keep its place (over the ceiling; the envelope settles it)",
                       uncertain_in=sorted(kinds))
        elif all_settled:
            out.update(keeps_its_place=True, status="keeps its place (over the ceiling; the envelope settles every status)",
                       uncertain_in=sorted(kinds))
        else:
            out.update(keeps_its_place=None, uncertain_in=sorted(uncertain or kinds),
                       status=(f"unsettled: {over}, and the envelope cannot settle it; uncertain in "
                               + ", ".join(sorted(uncertain or kinds))))
        return out


def _kind_of(x: dict) -> str:
    return {"assignment": "assignment", "date": "timing", "capacity": "capacity"}.get(x.get("question"), "timing")


# ---- stress scenarios (Joe, R4) ---------------------------------------------------------------------------------------

def stress_entries(corrections: list[dict]) -> list[dict]:
    out = []
    for c in corrections:
        s = c.get("stress")
        if not s:
            continue
        if not s.get("label"):
            raise ValueError(f"{c['fid']}: a stress scenario needs a label")
        start = px.OPEN_BELOW_START if s.get("start") is None else int(s["start"])
        out.append({"fid": c["fid"], "label": s["label"], "start": start, "reason": s.get("reason") or STRESS_REASON,
                    "entry": fixed_date(c["fid"], start), "replaces": {k: v for k, v in c.items() if k != "stress"}})
    return out


def run_stress(inp: px.Inputs, entries: list[dict], stress: dict, theta: float, refs: dict) -> list[dict]:
    """A stress scenario: the row at its stress start, every other question at its reference setting. Reported; it
    decides nothing."""
    st = inp.fac.state[stress["fid"]]
    ent = [c for c in entries if c["fid"] != stress["fid"] or c["kind"] != "date"] + [stress["entry"]]
    run = StateRun(inp, ent, st, screen=(0,))
    S = run.cases[0]["S"]
    r = inp.fac.loc[stress["fid"]]
    us = {(int(u), st) for u in asg.candidates(r.utility_candidates)} | ({(int(r.utility_id_eia), st)} if pd.notna(r.utility_id_eia) else set())
    fm_any = run.cases[0]["S"].factor_can_move
    ks = sorted(set(S.units) if fm_any else us & set(S.units))
    out = []
    for k in ks:
        rec, ref = refs.get((k, theta), (None, None))
        base_k = float(inp.base.get(k, np.nan))
        ab, na, _ = S.grid(k, [])
        _, parts = pe._outcomes(ab, na, base_k, theta, ref) if ref is not None else pe._outcomes(ab, na, base_k, theta, None)
        out.append({"utility": f"{k[0]}:{k[1]}", "theta": theta, "site": stress["fid"], "label": stress["label"],
                    "is_admissible": False,
                    "place_as_built": PLACES[int(parts["p_ab"][0])], "crossing_as_built": pe._year(int(parts["c_ab"][0])),
                    "accepted_against_the_reference": (None if ref is None else bool(parts["acc"][0]))})
    return out


# ---- the permit-error reach (D-58 rule 1.6 (b)), beside the open-below-only list ---------------------------------------

def permit_error_reach(dating_report: dict) -> dict:
    """The 95th percentile of measured permit lateness by size class, from dating_report.json. numpy's "nearest" method
    (an observed value) is the one that reproduces D-58 rule 1.6's figures (10, 16 and 10 years) on the frozen report."""
    errs = dating_report["permit_dating_error"]["errors_in_years_by_generator_based_size_mw"]
    return {name: int(np.percentile(np.array(errs[name], dtype=float), 95, method="nearest")) for name, _, _ in SIZE_CLASSES}


def reach_entries(inp: px.Inputs, entries: list[dict], reach: dict) -> list[dict]:
    """Every open-below date entry with its lower end at its late end less the reach for its size class."""
    out = []
    for c in entries:
        if c["kind"] == "date" and c.get("earliest") is None and c.get("latest") is not None:
            mw = float(inp.fac.mw_full.get(c["fid"], np.nan)) if pd.notna(inp.fac.mw_full.get(c["fid"], np.nan)) else 0.0
            cls = next(n for n, lo, hi in SIZE_CLASSES if lo <= mw < hi)
            c = {**c, "earliest": int(c["latest"]) - reach[cls]}
            if c.get("convention") is not None and c["convention"] < c["earliest"]:
                c["convention"] = c["earliest"]
        out.append(c)
    return out


# ---- the run --------------------------------------------------------------------------------------------------------

def run(inp: px.Inputs, corrections: list[dict], thetas=THRESHOLDS, states=None, ceiling: int = CEILING,
        screen=SCREEN, reach: dict | None = None) -> dict:
    entries = timing_entries(corrections)
    stresses = stress_entries(corrections)
    states = sorted(states or set(inp.units.get_level_values("state")))
    rows, stress_rows, reach_rows = [], [], []
    for st in states:
        sr = StateRun(inp, entries, st, screen=screen)
        units = sr.cases[0]["S"].units
        for theta in thetas:
            res = [sr.evaluate(k, theta, ceiling) for k in units]
            rows += res
            ob = [r for r in res if r["fails_only_open_below"]]
            if ob and reach:
                rr = StateRun(inp, reach_entries(inp, entries, reach), st, screen=screen, refs=dict(sr.refs))
                for r in ob:
                    k = (int(r["utility"].split(":")[0]), st)
                    x = rr.evaluate(k, theta, ceiling)
                    reach_rows.append({"utility": r["utility"], "theta": theta, "keeps_its_place_under_the_permit_error_reach":
                                       x["keeps_its_place"], "status": x["status"],
                                       "by_screen_shift_under_the_open_below_case": r["by_screen_shift"]})
            by_u = {r["utility"]: r for r in res}
            for s in [s for s in stresses if inp.fac.state.get(s["fid"]) == st]:
                got = run_stress(inp, entries, s, theta, sr.refs)
                stress_rows += got
                for x in got:
                    if x["accepted_against_the_reference"] is False and x["utility"] in by_u:
                        r = by_u[x["utility"]]
                        r["unresolved_by_stress"].append({"site": s["fid"], "label": s["label"], "reason": s["reason"],
                                                          "place_under_the_stress": x["place_as_built"],
                                                          "crossing_under_the_stress": x["crossing_as_built"]})
    return {"utilities": rows, "stress_scenarios": stress_rows, "open_below_only_with_the_permit_error_reach": reach_rows}


def _verdict(r: dict) -> dict:
    return {"keeps_its_place": r["keeps_its_place"], "keeps_with_assignment_as_mapped": r["keeps_with_assignment_as_mapped"],
            "method": r["method"], "status": r["status"], "configurations_by_screen_shift": r.get("configurations_by_screen_shift"),
            "by_screen_shift": r["by_screen_shift"], "failure": r["failure"], "fails_only_open_below": r["fails_only_open_below"],
            "lower_end_that_would_let_it_stay": r.get("lower_end_that_would_let_it_stay"), "range": r["range"],
            "reference": r["reference"]}


def compare_oregon_looser_reading(inp: px.Inputs, corrections: list[dict], thetas=THRESHOLDS, ceiling: int = CEILING,
                                  looser: dict | None = None) -> dict:
    """The labelled comparison (decides nothing; never read by treatment_bounds): each Oregon utility's verdict in force,
    beside its verdict if bi:822-0 and bi:823-0 were also bounded not before 2018 (OREGON_LOOSER_READING: the recorder's
    note "new source" counted as the permit's kind). Everything else is as in force. Refuses unless each of the two
    has a date entry that is open below in force."""
    looser = dict(OREGON_LOOSER_READING if looser is None else looser)
    alt, used = [], []
    seen = set()
    for c in corrections:
        if c.get("kind") == "date" and c["fid"] in looser:
            if c.get("earliest") is not None:
                raise ValueError(f"{c['fid']}: in force it is not open below (earliest {c['earliest']}); there is nothing to loosen")
            e = {**c, "earliest": int(looser[c["fid"]]),
                 "why": (f"labelled comparison only (decides nothing): not before {looser[c['fid']]}, the recorder's note "
                         f"'new source' counted as the permit's kind; in force the row is open below")}
            alt.append(e)
            used.append(e)
            seen.add(c["fid"])
        else:
            alt.append(c)
    missing = sorted(set(looser) - seen)
    if missing:
        raise ValueError(f"no date entry in the corrections for {missing}: the comparison loosens an entry in force, never invents one")
    in_force = run(inp, corrections, thetas=thetas, states=["OR"], ceiling=ceiling)
    other = run(inp, alt, thetas=thetas, states=["OR"], ceiling=ceiling)
    key = lambda r: (r["utility"], r["theta"])  # noqa: E731
    b = {key(r): r for r in other["utilities"]}
    rows, differs = [], []
    for r in in_force["utilities"]:
        x = b[key(r)]
        row = {"utility": r["utility"], "name": r["name"], "theta": r["theta"],
               "in_force": _verdict(r), "looser_reading": _verdict(x)}
        rows.append(row)
        if (r["keeps_its_place"], r["keeps_with_assignment_as_mapped"]) != (x["keeps_its_place"], x["keeps_with_assignment_as_mapped"]):
            differs.append(f"{r['utility']} at {r['theta']:.0%}")
    return {"what_this_is": ("A labelled comparison that decides nothing and is never read by treatment_bounds or anything "
                             "downstream. In force (Joe, Stop 3, 2026-11-18), bi:822-0 and bi:823-0 are open below because "
                             "the record does not establish their permits' kind ('new source' is the recorder's note, not "
                             "DEQ's wording). Here they are instead bounded not before 2018, with everything else as in force."),
            "entries_used_for_the_comparison": used,
            "utilities_whose_verdict_differs": differs,
            "every_oregon_utility": rows}


def compare_ceiling_per_screen_case(inp: px.Inputs, corrections: list[dict], thetas=THRESHOLDS, states=None,
                                    ceiling: int = CEILING, screen=SCREEN) -> dict:
    """The record of what the ceiling amendment changed (decides nothing; never read by treatment_bounds): every utility
    whose verdict under the rule in force (the ceiling per screen case, Joe at Stop 3, 2026-11-18) differs from its
    verdict under the superseded rule (the cases' counts summed against the ceiling).

    Which utilities are compared is decided from the superseded rule's own row (`evaluate`'s `method`), never from a
    separate count: every utility whose summed-rule place test went to the envelope is evaluated under the rule in force,
    and the run stops if the two lists ever disagree. A utility enumerated exactly under the summed rule cannot change
    (each case is then under the ceiling too), and one with an undefined reference has no place test to redo (the
    reference search does not count the screen cases)."""
    entries = timing_entries(corrections)
    states = sorted(states or set(inp.units.get_level_values("state")))
    rows, envelope_summed, evaluated = [], [], []
    for st in states:
        sr = StateRun(inp, entries, st, screen=screen)
        for k in sr.cases[0]["S"].units:
            for theta in thetas:
                a = sr.evaluate(k, theta, ceiling, rule=SUMMED_SUPERSEDED)
                if a["method"] != "envelope":
                    continue
                envelope_summed.append((a["utility"], theta))
                b = sr.evaluate(k, theta, ceiling, rule=CEILING_RULE)
                evaluated.append((a["utility"], theta))
                same = (a["keeps_its_place"] == b["keeps_its_place"]
                        and a["keeps_with_assignment_as_mapped"] == b["keeps_with_assignment_as_mapped"])
                if same:
                    continue
                rows.append({"utility": a["utility"], "name": a["name"], "theta": theta,
                             "configurations_by_screen_shift": a["configurations_by_screen_shift"],
                             "configurations_summed": a["configurations"],
                             "summed_rule_until_2026_11_18": {"keeps_its_place": a["keeps_its_place"], "method": a["method"],
                                                              "status": a["status"]},
                             "in_force_per_screen_case": {"keeps_its_place": b["keeps_its_place"], "method": b["method"],
                                                          "status": b["status"], "failure": b["failure"],
                                                          "by_screen_shift": b["by_screen_shift"]}})
    if sorted(envelope_summed) != sorted(evaluated):
        raise RuntimeError("the record skipped a utility whose summed-rule place test went to the envelope")
    return {"what_this_is": ("The record of what the ceiling amendment changed; it decides nothing and is never read by "
                             "treatment_bounds. Until 2026-11-18 the configurations of the three screen cases were summed "
                             "against the 100,000 ceiling, and over it every case went to the envelope. Joe amended the rule "
                             "at Stop 3 (2026-11-18), with these consequences known: the ceiling applies to each predefined "
                             "screen case's enumeration separately, a case at or under it is enumerated completely, and only "
                             "a case over it goes to the envelope. Each row is a utility whose verdict differs between the "
                             "two rules."),
            "ceiling": ceiling, "screen_shifts": list(screen), "rule_in_force": CEILING_RULE,
            "superseded_rule": SUMMED_SUPERSEDED,
            "utilities_over_the_ceiling_when_summed_evaluated": len(evaluated),
            "summed_rule_envelope_utilities_evaluated_under_the_rule_in_force": [f"{u} at {t:.0%}" for u, t in sorted(evaluated)],
            "utilities_whose_verdict_differs": rows}


def original_places(snapshot: Path, thetas=THRESHOLDS) -> dict:
    """Each utility's place and first crossing as built on the frozen inventory of 2026-11-14 (the snapshot)."""
    fac = pd.read_parquet(snapshot / "facilities.parquet").set_index("fid")
    fy = pd.read_parquet(snapshot / "facility_year.parquet")
    fy = fy[~fy.crypto][["fid"] + asg.KEY + ["year", "mw"]]
    _, _, q, units, base, regions = asg.load_inputs()
    t, _, _ = asg.evaluate(fac, fy, units, base, regions, thresholds=thetas)
    out = {}
    for theta in thetas:
        th = f"{theta:.0%}"
        for k in units:
            out[(f"{k[0]}:{k[1]}", theta)] = {"place": px.place(t.at[k, f"as_built_{th}"], t.at[k, "max_share_as_built"]),
                                             "crossing": asg.fmt(t.at[k, f"as_built_{th}"])}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrections", default=str(cx.CORRECTIONS))
    ap.add_argument("--ceiling", type=int, default=CEILING)
    ap.add_argument("--states", default=None)
    ap.add_argument("--compare-ceiling-per-screen-case", action="store_true",
                    help="write the record of what the ceiling amendment changed (decides nothing)")
    ap.add_argument("--compare-oregon-looser-reading", action="store_true",
                    help="write the labelled comparison of the looser reading of bi:822-0 and bi:823-0 (decides nothing)")
    args = ap.parse_args(argv)
    if args.compare_ceiling_per_screen_case:
        doc = compare_ceiling_per_screen_case(load_rebuilt(), cx.load(args.corrections),
                                              states=args.states.split(",") if args.states else None, ceiling=args.ceiling)
        doc["fingerprint"] = cx.fingerprint([args.corrections, *cx.code_files(), INTERIM / "facilities.parquet",
                                             INTERIM / "facility_year.parquet", INTERIM / "state_anchor.parquet"],
                                            thresholds=list(THRESHOLDS), screen_shifts=list(SCREEN), ceiling=args.ceiling,
                                            ceiling_rule=CEILING_RULE, compared_with=SUMMED_SUPERSEDED)
        (FROZEN / "timing_ceiling_per_screen_case_comparison.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
        print(json.dumps(doc["utilities_whose_verdict_differs"], indent=1, default=str)[:4000])
        return 0
    if args.compare_oregon_looser_reading:
        corrections = cx.load(args.corrections)
        doc = compare_oregon_looser_reading(load_rebuilt(), corrections, ceiling=args.ceiling)
        doc["fingerprint"] = cx.fingerprint([args.corrections, *cx.code_files(), INTERIM / "facilities.parquet",
                                             INTERIM / "facility_year.parquet", INTERIM / "state_anchor.parquet"],
                                            thresholds=list(THRESHOLDS), screen_shifts=list(SCREEN), ceiling=args.ceiling,
                                            ceiling_rule=CEILING_RULE, looser_reading=OREGON_LOOSER_READING)
        (FROZEN / "timing_oregon_looser_reading_comparison.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
        print(json.dumps({"utilities_whose_verdict_differs": doc["utilities_whose_verdict_differs"],
                          "every_oregon_utility": [{"utility": r["utility"], "theta": r["theta"],
                                                    "in_force": r["in_force"]["status"], "looser": r["looser_reading"]["status"]}
                                                   for r in doc["every_oregon_utility"]]}, indent=1, default=str)[:4000])
        return 0
    if not SNAPSHOT.exists():
        raise SystemExit(f"{SNAPSHOT} is missing: the original crossings of 2026-11-14 are read from it (addendum point 6)")
    corrections = cx.load(args.corrections)
    inp = load_rebuilt()
    reach = permit_error_reach(json.loads((FROZEN / "dating_report.json").read_text()))
    res = run(inp, corrections, states=args.states.split(",") if args.states else None, ceiling=args.ceiling, reach=reach)
    orig = original_places(SNAPSHOT)
    up = FROZEN / "unknown_load_sites_and_affected_utilities.json"
    unknown = set(json.loads(up.read_text())["every_affected_utility"]) if up.exists() else set()
    for r in res["utilities"]:
        r["original_2026_11_14"] = orig.get((r["utility"], r["theta"]))
        r["a_load_unknown_site_reaches_it"] = r["utility"] in unknown
    res["unknown_load_affected_utilities"] = sorted(unknown)
    res["utilities_unresolved_by_a_stress_scenario"] = sorted({(r["utility"], r["theta"]) for r in res["utilities"]
                                                               if r["unresolved_by_stress"]})
    fp = cx.fingerprint([args.corrections, cx.LOCATIONS, *cx.code_files(), FROZEN / "dating_report.json",
                         INTERIM / "facilities.parquet", INTERIM / "facility_year.parquet", INTERIM / "state_anchor.parquet"],
                        thresholds=list(THRESHOLDS), screen_shifts=list(SCREEN), screen_min_mw=SCREEN_MIN_MW,
                        ceiling=args.ceiling, ceiling_rule=CEILING_RULE, permit_error_reach=reach)
    doc = {"what_this_is": __doc__.split("\n\n")[0], "fingerprint": fp, **res}
    (FROZEN / "timing_place_test.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
    flat = pd.DataFrame([{**{k: v for k, v in r.items() if k not in ("reference", "failure", "by_screen_shift", "range",
                                                                      "original_2026_11_14", "unresolved_by_stress")},
                          "unresolved_by_stress": json.dumps(r["unresolved_by_stress"]),
                          "reference_place": r["reference"]["place"], "reference_crossing": r["reference"]["crossing"],
                          "original_place": (r.get("original_2026_11_14") or {}).get("place"),
                          "original_crossing": (r.get("original_2026_11_14") or {}).get("crossing"),
                          "range": json.dumps(r["range"]), "uncertain_in": ";".join(r["uncertain_in"])}
                         for r in res["utilities"]])
    flat.to_csv(FROZEN / "timing_place_test_by_utility.csv", index=False)
    summ = flat.groupby(["theta", flat.keeps_its_place.astype(str)]).size()
    print(summ.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
