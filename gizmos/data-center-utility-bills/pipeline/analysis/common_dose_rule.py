#!/usr/bin/env python3
"""Joe's common-dose rule for a utility a site with no load history reaches (2026-11-19), applied as written.

Pre-freeze implementation on a DRAFT pre-analysis plan that is not frozen. Load and sales only: nothing here reads,
opens or prints a price, a revenue or a bill. Figures computed from the quantity files are provisional on the design as
it stands.

The rule, in Joe's words (2026-11-19), unchanged:

    Apply the common-dose exception consistently to Umatilla. If complete admissible histories establish one common
    change in capped dose, apply that exception for the capped form. Otherwise retain exclusion and state what remains
    unestablished. Do not decide this merely by following the current code. Keep analysis eligibility separate from
    simulation-access eligibility.

and his clarification:

    For Umatilla, assess completeness or establish the common capped change by a justified argument within the adopted
    computational limits. Do not raise the ceiling or launch exhaustive enumeration merely to establish eligibility. If
    it remains unestablished, retain exclusion and explain the precise gap.

What is here
------------
apply_rule            the rule itself, on a utility's within-history changes per cap label, with an explicit statement
                      of completeness and/or a bounds result. Established only for a capped form, only where the
                      histories are complete or the bounds argument holds, and only where every history gives exactly
                      the same change (no tolerance, no midpoint, no narrow range). Never for the uncapped form.
admissible_settings   each admissible setting of a date or capacity question, derived from its correction entry in the
                      plan's own words, independently of the enumeration's code.
coverage_check        what an enumeration varies against what is admissible: the load-unknown sites' questions, ruling
                      4's cases, the two readings, and every question relevant to the utility that it holds at the
                      reference configuration. It reports two scopes apart and never merges them.
load_extremes         per year, the least and greatest load a utility can carry over a stated set of settings, from
                      per-site extremes (the load is additive over sites, and each site's settings are its own), with
                      the state's factor bounded by its clip limits and, apart, by the monotone bound.
bounds_argument       the argument that needs no enumeration: each before year zero in every history and each after
                      year at or above the cap in every history, from those extremes, or the step that fails.
witness_changes       the change in a few named single configurations (one setting per question), for showing that a
                      wider set of histories is not common. Never an enumeration.
oregon_detail         everything above for Portland General and Umatilla from the quantity files, for one scope.
oregon_verdicts       {utility: {cap label: {"established", "dose", "why"}}}, for one scope, named explicitly. Both
                      scopes are computed so that both verdicts stay on record as what was found.
established_as_ruled  the mapping the analysis applies: the ruled scope's verdicts (RULED_SCOPE), with the other scope's
                      verdict recorded beside each.

The two scopes, and Joe's ruling between them (D-107, 2026-11-19)
-----------------------------------------------------------------
His words: "Keep Umatilla excluded from the common-dose exception: the wider admissible histories contain a
counterexample. Do not narrow those histories to obtain settled status." The exception is therefore judged on the place
test's wider set (RULED_SCOPE), and that is the only scope the analysis path applies. Rule 8.1's own histories are still
evaluated and recorded: under them Umatilla's capped change is common (25.0 and 50.0 points), and that verdict is kept as
what was found, not applied. His clarification adds that "settled" is conditional on rule 8.1's modeled histories with
dates held at their conventions (second_number.SETTLED_IS_CONDITIONAL).

"rule_8_1_text"         the histories rule 8.1 and "Sites with no load history" define in their own words: every
                        admissible history of each site with no load history (each year of its interval, no operation
                        where the interval allows it, each capacity case), crossed with D-46 ruling 4's three cases, as
                        built and with no anchoring, the state's factor recomputed in each. Every other question stays
                        where the inventory as built has it, as it does for every other utility under rule 8.1.
"place_test_wider_set"  every open question of every site that reaches the utility, as the place test
                        (pipeline/facilities/timing.py) enumerates it: also the other sites' date, capacity and
                        assignment questions, and the generic screen's shifts of 3 and 5 years.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

UNCAPPED = "uncapped"
SCOPES = ("rule_8_1_text", "place_test_wider_set")
# Joe's ruling, 2026-11-19 (D-107): the common-dose exception is judged on the wider admissible histories, which contain
# a counterexample for Umatilla, and those histories are not narrowed to obtain settled status. The analysis path
# applies this scope and no other (established_as_ruled); the other scope's verdicts are computed and kept on record.
RULED_SCOPE = "place_test_wider_set"
RULING = ("Joe ruled on 2026-11-19 (D-107) that the common-dose exception is judged on the wider admissible histories "
          "(the place test's wider set), which contain a counterexample for Umatilla, and that those histories are not "
          "narrowed to obtain settled status; Umatilla stays excluded")
PRE_YEARS = (2008, 2009, 2010)                 # rule 8.1's before period (PREANALYSIS.md, the second number)
POST_YEARS = (2023, 2024, 2025)                # its after period
GWH_PER_MW = 8.76
# A lower bound within this relative distance of the cap is not taken to put the year at the cap: the bound is computed
# in a different order of floating-point operations from the enumeration, so a year that close is not decided here.
CAP_MARGIN_REL = 1e-9


def cap_value(label: str) -> float | None:
    """The cap a label names (second_number.cap_label's labels): None for the uncapped form."""
    if label == UNCAPPED:
        return None
    if label.startswith("capped_at_") and label.endswith("_points"):
        return float(label[len("capped_at_"):-len("_points")])
    raise ValueError(f"not a cap label: {label!r}")


# ================================================================================================================
# 1. The rule
# ================================================================================================================

@dataclass(frozen=True)
class Completeness:
    """An explicit statement of whether the histories evaluated are the complete admissible histories of a scope."""
    complete: bool
    basis: str
    gaps: tuple = ()


@dataclass(frozen=True)
class YearStep:
    year: int
    period: str                    # "before" or "after"
    lowest_points: float           # the least load share in this year over every history the bound covers
    highest_points: float          # the greatest
    value: float | None            # the capped load share every history gives this year, or None if the bound leaves it open
    why: str


@dataclass(frozen=True)
class BoundsResult:
    """The argument with no enumeration, for one cap: each year's capped load share is the same in every history
    (zero, because the greatest load is zero; or the cap, because the least load is at or above it)."""
    label: str
    holds: bool
    dose: float | None
    steps: tuple
    failed: tuple                  # words naming each step that fails, with the year and by how much
    basis: str


def _verdict(established: bool, dose, why: str) -> dict:
    return {"established": bool(established), "dose": (None if dose is None else float(dose)), "why": why}


def apply_rule(changes: dict, *, completeness: Completeness | None, bounds: dict | None) -> dict:
    """Joe's rule for one utility. `changes`: {cap label: array of within-history changes in the histories evaluated
    (the enumeration's, with any witness histories added)}. `completeness`: whether those histories are the complete
    admissible histories of the scope in hand, or None for no statement. `bounds`: {cap label: BoundsResult} or None.
    Both keywords are required so that leaving one out is a visible choice.

    Per cap label: established only where the form is capped, every history evaluated gives exactly the same change,
    and either the histories are complete or the bounds argument holds (and agrees with the histories evaluated).
    Never for the uncapped form. A narrow range is not a common change; no tolerance and no midpoint are used."""
    bounds = bounds or {}
    out = {}
    for label in list(dict.fromkeys(list(changes) + list(bounds))):
        v = np.asarray(changes.get(label, []), dtype=float).ravel()
        shown = (f"the {v.size} histories evaluated give {v.min():.6g} to {v.max():.6g} points" if v.size and np.isfinite(v).all()
                 else "no history evaluated" if not v.size else "a history evaluated gives a non-finite change")
        if cap_value(label) is None:
            out[label] = _verdict(False, None, "uncapped form: the exception is applied to a capped form only (Joe, "
                                               "2026-11-19); " + shown)
            continue
        if v.size and not np.isfinite(v).all():
            out[label] = _verdict(False, None, "not established: " + shown)
            continue
        if v.size and not np.all(v == v[0]):
            out[label] = _verdict(False, None, "not established, and not common: " + shown + ". Histories that already "
                                               "differ cannot be made common by any wider set of histories")
            continue
        b = bounds.get(label)
        if completeness is not None and completeness.complete and v.size:
            out[label] = _verdict(True, v[0], f"established: every one of the {v.size} histories gives exactly "
                                              f"{v[0]:.6g} points, and they are complete ({completeness.basis})")
            continue
        if b is not None and b.holds:
            if v.size and v[0] != b.dose:
                out[label] = _verdict(False, None, f"not established: the bounds argument gives {b.dose} and the histories "
                                                   f"evaluated give {v[0]}; the two disagree and nothing is chosen")
                continue
            out[label] = _verdict(True, b.dose, f"established by the bounds argument ({b.basis}): every admissible history "
                                                f"gives exactly {b.dose:.6g} points"
                                                + (f"; the {v.size} histories evaluated agree" if v.size else ""))
            continue
        gaps = []
        if completeness is None:
            gaps.append("no statement of completeness")
        elif not completeness.complete:
            gaps.append("the histories evaluated are not shown complete: " + "; ".join(completeness.gaps or (completeness.basis,)))
        if b is None:
            gaps.append("no bounds argument")
        elif not b.holds:
            gaps.append("the bounds argument fails: " + "; ".join(b.failed))
        if not v.size:
            gaps.append("no history evaluated")
        out[label] = _verdict(False, None, "not established (" + shown + "): " + " | ".join(gaps))
    return out


# ================================================================================================================
# 2. What is admissible, and what an enumeration covers
# ================================================================================================================

def admissible_settings(entry: dict, *, first_year: int, last_year: int, ramp_years: int,
                        inventory_year: int | None = None) -> list:
    """Each admissible setting of one question, from its correction entry, in the plan's words, written apart from the
    enumeration's code so the two can be compared.

    A date entry ({"kind": "date", "earliest", "latest", "never_is_possible"}): each start year of its interval, and
    "never" where the interval allows no operation. An open lower end ("earliest": None) reaches back without limit and
    an open upper end ("latest": None) forward without limit; the years are then represented by the distinct histories
    they give. Under the linear ramp (buildout.ramp_mw: a start in year s gives (age + 1) / ramp_years of full load at
    age = year - s), every start at or before first_year - ramp_years + 1 gives full load in every panel year and in the
    2024 anchoring, so they are one history, entered at that year; every start after last_year gives no load in any panel
    year or in the 2024 anchoring, so they are one history, entered at last_year + 1.
    A capacity_split entry ({"kind": "capacity_split", "rest_earliest", ...}): each year from rest_earliest to the
    inventory year, or the two cases "early" and "late" where there is no rest_earliest."""
    if entry.get("kind") == "capacity_split":
        re_ = entry.get("rest_earliest")
        if re_ is None:
            return ["early", "late"]
        if inventory_year is None:
            raise ValueError(f"{entry.get('fid')}: a capacity question with rest_earliest needs the inventory year")
        return list(range(int(re_), int(inventory_year) + 1))
    if entry.get("kind") != "date":
        raise ValueError(f"not a date or capacity entry: {entry.get('kind')!r}")
    lo_all, hi_all = first_year - ramp_years + 1, last_year + 1
    lo = lo_all if entry.get("earliest") is None else max(int(entry["earliest"]), lo_all)
    hi = hi_all if entry.get("latest") is None else min(int(entry["latest"]), hi_all)
    years = list(range(min(lo, hi), hi + 1))
    return years + (["never"] if entry.get("never_is_possible") else [])


def rule4_cases(qs, k_id: int) -> dict:
    """D-46 ruling 4's three cases for utility k_id, written apart from second_number.rule4_case_settings: as assigned
    (every assignment question at the inventory's setting), lower (every unresolved site now on k taken off the panel),
    upper (every unresolved site that lists k among its other candidates counted on k). {case: {question id: setting}}."""
    out = {"as_assigned": {}, "lower": {}, "upper": {}}
    for qid, q in enumerate(qs):
        if q.name != "assignment":
            continue
        if q.values[0] == k_id:
            out["lower"][qid] = q.values.index(None)
        elif k_id in q.values:
            out["upper"][qid] = q.values.index(k_id)
    return out


def coverage_check(qs, *, k_id: int, unknown_fids: list, varied_qids: list, case_settings: dict, relevant: list,
                   admissible: dict, histories: int, readings: int = 2, wider_set_gaps: list = ()) -> dict:
    """What an enumeration of a utility's dose histories covers, against what is admissible, in two scopes kept apart.

    qs             the state's questions (pass_c_exact._State.qs: fid, name, values, default)
    varied_qids    the questions the enumeration varies over every setting
    case_settings  {case: {qid: setting}} the enumeration applies (its ruling 4 cases)
    relevant       [(question id, merged classes)] for every question whose setting can change the utility's load in
                   some year or its state's factor (pass_c_exact._State.relevance, the place test's set); two settings
                   in one class give the utility the same load in every year and the same anchoring
    wider_set_gaps further parts of the place test's set the enumeration does not evaluate (the generic screen's
                   shifts), named by the caller; they count against the wider scope only
    admissible     {(fid, question name): [settings]} from admissible_settings, for the load-unknown sites' questions
    histories      how many within-history changes the enumeration returned (as built and no anchoring stacked)
    Returns per-question coverage, the questions held at the reference with their admissible settings, and for each
    scope whether the enumeration is complete and what is missing."""
    rows, missing = [], []
    for (fid, name), need in sorted(admissible.items(), key=lambda x: (x[0][0], x[0][1])):
        qid = next((i for i, q in enumerate(qs) if q.fid == fid and q.name == name), None)
        have = list(qs[qid].values) if qid is not None else []
        lacks = [x for x in need if x not in have]
        extra = [x for x in have if x not in need]
        varied = qid is not None and qid in varied_qids
        rows.append({"site": fid, "question": name, "admissible": need, "enumerated": have if varied else [],
                     "varied_over_every_setting": varied, "admissible_settings_missing": lacks, "settings_not_admissible": extra})
        if not varied:
            missing.append(f"{fid} {name}: not varied by the enumeration")
        elif lacks or extra:
            missing.append(f"{fid} {name}: missing {lacks}, not admissible {extra}")
    expect = rule4_cases(qs, k_id)
    cases_ok = {c: case_settings.get(c) == expect[c] for c in expect}
    for c, ok in cases_ok.items():
        if not ok:
            missing.append(f"ruling 4's case {c!r}: the enumeration applies {case_settings.get(c)}, the case is {expect[c]}")
    n_expect = readings * len(expect) * math.prod(len(qs[q].values) for q in varied_qids)
    if histories != n_expect:
        missing.append(f"{histories} histories returned, {n_expect} expected from {readings} readings x {len(expect)} cases "
                       f"x every setting of the varied questions")
    in_case = {q for c in case_settings.values() for q in c}
    held = []
    for qid, classes in relevant:
        if qid in varied_qids:
            continue
        q = qs[qid]
        used = {q.default} | {c[qid] for c in case_settings.values() if qid in c}
        uncovered = [[_plain(q.values[j]) for j in cl] for cl in classes if not (set(cl) & used)]
        held.append({"question_id": int(qid), "site": q.fid, "question": q.name,
                     "reference_setting": _plain(q.values[q.default]),
                     "admissible_settings": [_plain(x) for x in q.values],
                     "settings_the_enumeration_uses": [_plain(q.values[j]) for j in sorted(used)],
                     "classes_for_this_utility": len(classes),
                     "classes_not_reached": uncovered,
                     "note": ("varied only through ruling 4's cases" if qid in in_case else "held at the reference")})
    scope_i = not missing
    scope_ii_gaps = [f"{h['site']} {h['question']}: {h['note']} at {h['settings_the_enumeration_uses']}; "
                     f"{len(h['classes_not_reached'])} of its {h['classes_for_this_utility']} classes of admissible "
                     f"settings not reached" for h in held if h["classes_not_reached"]] + list(wider_set_gaps)
    return {"questions_of_sites_with_no_load_history": rows, "ruling_4_cases_as_applied": cases_ok,
            "histories_returned": int(histories), "histories_expected": int(n_expect),
            "relevant_questions_not_varied": held,
            "scope": {"rule_8_1_text": {"complete": scope_i, "gaps": missing},
                      "place_test_wider_set": {"complete": scope_i and not held, "gaps": missing + scope_ii_gaps}}}


def completeness_for(cov: dict, scope: str, basis_extra: str = "") -> Completeness:
    _check_scope(scope)
    s = cov["scope"][scope]
    basis = (f"scope {scope}: every admissible setting of every question of the sites with no load history, ruling 4's three "
             f"cases and both readings, {cov['histories_returned']} histories" + (f"; {basis_extra}" if basis_extra else ""))
    return Completeness(bool(s["complete"]), basis if s["complete"] else f"scope {scope}: not complete", tuple(s["gaps"]))


def _plain(v):
    if v is None:
        return "off_panel"
    if isinstance(v, (int, np.integer)):
        return int(v)
    return str(v)


def _check_scope(scope: str) -> str:
    if scope not in SCOPES:
        raise ValueError(f"the scope is one of {SCOPES}, not {scope!r}, and is named explicitly: both are computed for the "
                         f"record, and the analysis applies {RULED_SCOPE!r} only (Joe, D-107, 2026-11-19)")
    return scope


# ================================================================================================================
# 3. The bounds argument (no enumeration)
# ================================================================================================================

def allowed_rows(S, *, free_qids, fixed_options: dict) -> dict:
    """Per site index, the rows of its settings a scope admits: a free question at any setting, a question in
    fixed_options at one of the settings listed, every other question at the reference configuration's setting."""
    free = set(free_qids)
    out = {}
    for si, s in enumerate(S.sites):
        keep = np.ones(len(s.unit), dtype=bool)
        for qi, qid in enumerate(S.site_qids[si]):
            if qid in free:
                continue
            ok = set(fixed_options.get(qid, set())) | {S.qs[qid].default}
            keep &= np.isin(s.idx[:, qi], sorted(ok))
        out[si] = np.flatnonzero(keep)
    return out


def load_extremes(S, k: tuple, base_k: float, rows: dict, *, scale_lo: float, scale_hi: float, factor_tol: float,
                  years: list, factor_fn=None) -> dict:
    """The least and greatest load share (points of base_k) utility k can carry in each year of `years`, over every
    combination of the admitted rows of every site, in both readings, with the state's factor bounded two ways.

    The load on k is additive over sites (pass_c_exact._State.grid: measured MW as carried plus the factor times the
    permit-based raw MW, each summed over sites; with no anchoring, measured MW over its divisor plus raw MW), and each
    site's setting is its own, so the least (greatest) sum is the sum of each site's least (greatest). The factor is the
    one quantity shared across sites. It is bounded (a) by its clip limits [scale_lo, scale_hi], with 1 added where the
    permit total can be zero, which needs no property of the factor at all; and (b) by its value at the greatest totals
    and at the least (it falls as either total rises, before and after the clip), widened by factor_tol for the snap to
    the frozen factor. Bound (a) is the one the argument uses first."""
    yi = [list(_years()).index(y) for y in years]
    n = len(years)
    R_lo, R_hi, Mm_lo, Mm_hi, Mna_lo, Mna_hi = (np.zeros(n) for _ in range(6))
    P_lo = P_hi = 0.0
    M_lo = M_hi = float(S.m0)
    for si, s in enumerate(S.sites):
        r = rows[si]
        if not len(r):
            raise ValueError(f"{s.fid}: no admitted setting")
        on = np.array([s.unit[j] == k for j in r], dtype=bool)
        L = s.load[r][:, yi] * on[:, None]
        if s.kind == "permit":
            R_lo += L.min(axis=0)
            R_hi += L.max(axis=0)
            P_lo += float(s.a[r].min())
            P_hi += float(s.a[r].max())
        else:
            Mm_lo += L.min(axis=0)
            Mm_hi += L.max(axis=0)
            Mna_lo += (L / float(s.na_div[0])).min(axis=0)
            Mna_hi += (L / float(s.na_div[0])).max(axis=0)
            M_lo += float(s.a[r].min())
            M_hi += float(s.a[r].max())
    clip = (min(scale_lo, 1.0) if P_lo <= 0 else scale_lo, max(scale_hi, 1.0) if P_lo <= 0 else scale_hi)
    mono = None
    if factor_fn is not None:
        f_lo = float(factor_fn(np.array([M_hi]), np.array([P_hi]))[0])
        f_hi = float(factor_fn(np.array([M_lo]), np.array([P_lo]))[0])
        tol = factor_tol * max(1.0, abs(float(getattr(S, "frozen", 1.0))))
        mono = (f_lo - tol, f_hi + tol)
        if P_lo <= 0:
            mono = (min(mono[0], 1.0), max(mono[1], 1.0))
    pts = 100.0 * GWH_PER_MW / float(base_k)

    def band(F):
        lo = np.minimum(pts * (Mm_lo + F[0] * R_lo), pts * (Mna_lo + R_lo))
        hi = np.maximum(pts * (Mm_hi + F[1] * R_hi), pts * (Mna_hi + R_hi))
        return lo, hi
    out = {"years": list(years), "factor_clip": clip, "factor_monotone": mono,
           "permit_twh_2024_anchoring": (P_lo, P_hi), "measured_twh_2024_anchoring": (M_lo, M_hi),
           "raw_permit_mw_on_k": (R_lo.tolist(), R_hi.tolist()), "measured_mw_on_k": (Mm_lo.tolist(), Mm_hi.tolist())}
    out["clip"] = tuple(x.tolist() for x in band(clip))
    if mono is not None:
        out["monotone"] = tuple(x.tolist() for x in band(mono))
    return out


def bounds_from_extremes(lowest: dict, highest: dict, *, label: str, pre_years=PRE_YEARS, post_years=POST_YEARS,
                         basis: str = "") -> BoundsResult:
    """The argument for one cap from each year's least and greatest load share over every history ({year: points}).
    A year is decided if its greatest load is zero (capped value zero in every history) or its least is at or above the
    cap (capped value the cap in every history, the cap being applied in each year before averaging, as
    second_number.change applies it). If every year of both periods is decided, every history gives the same change,
    the after mean less the before mean of the decided values. Otherwise the result names each undecided year."""
    cap = cap_value(label)
    if cap is None:
        return BoundsResult(label, False, None, (), ("the uncapped form has no cap to bound against",), basis)
    steps, failed = [], []
    for period, yrs in (("before", pre_years), ("after", post_years)):
        for y in yrs:
            lo, hi = float(lowest[y]), float(highest[y])
            if hi <= 0.0:
                steps.append(YearStep(y, period, lo, hi, 0.0, "greatest load zero: capped share zero in every history"))
            elif lo >= cap * (1.0 + CAP_MARGIN_REL):
                steps.append(YearStep(y, period, lo, hi, cap, f"least load {lo:.6g} points, at or above the cap of {cap:g}"))
            else:
                why = (f"{period} year {y}: the load share runs from {lo:.6g} to {hi:.6g} points over the histories bounded, "
                       f"so it is not zero in every history (greatest {hi:.6g} above zero) and not at or above the cap of "
                       f"{cap:g} in every history (least {lo:.6g}, {cap - lo:.6g} short)")
                steps.append(YearStep(y, period, lo, hi, None, why))
                failed.append(why)
    if failed:
        return BoundsResult(label, False, None, tuple(steps), tuple(failed), basis)
    pre = np.array([s.value for s in steps if s.period == "before"], dtype=float)
    post = np.array([s.value for s in steps if s.period == "after"], dtype=float)
    return BoundsResult(label, True, float(post.mean() - pre.mean()), tuple(steps), (), basis)


def bounds_argument(ext: dict, *, label: str, pre_years=PRE_YEARS, post_years=POST_YEARS) -> BoundsResult:
    """bounds_from_extremes on load_extremes' result: with the factor's clip limits first, and with the monotone bound
    only where the clip limits leave a year undecided. The basis says which was used."""
    def at(kind):
        lo, hi = ext[kind]
        yrs = ext["years"]
        return dict(zip(yrs, lo)), dict(zip(yrs, hi))
    lo, hi = at("clip")
    r = bounds_from_extremes(lo, hi, label=label, pre_years=pre_years, post_years=post_years,
                             basis=f"factor bounded by its clip limits {ext['factor_clip']}")
    if r.holds or "monotone" not in ext:
        return r
    lo, hi = at("monotone")
    r2 = bounds_from_extremes(lo, hi, label=label, pre_years=pre_years, post_years=post_years,
                              basis=f"factor bounded at the greatest and least anchoring totals {ext['factor_monotone']}")
    return r2 if r2.holds else BoundsResult(label, False, None, r2.steps, r2.failed,
                                            r.basis + "; and " + r2.basis)


# ================================================================================================================
# 4. Witness histories (single configurations, never an enumeration)
# ================================================================================================================

def witness_changes(S, k: tuple, base_k: float, settings: list, *, caps, change_fn, cap_label_fn,
                    pre_years=PRE_YEARS, post_years=POST_YEARS) -> tuple[dict, list]:
    """The change in each of a few named configurations: settings is a list of {question id: setting index}, every
    other question at the reference. Each is one configuration through S.grid (as built and with no anchoring, the
    factor recomputed). Returns ({cap label: changes}, [described settings])."""
    yrs = list(pre_years) + list(post_years)
    cols = [list(_years()).index(y) for y in yrs]
    rows, described = [], []
    for st in settings:
        axes = sorted((qid, [int(v)]) for qid, v in st.items())
        ab, na, _ = S.grid(k, axes)
        rows += [ab[0], na[0]]
        described.append({f"{S.qs[q].fid} {S.qs[q].name}": _plain(S.qs[q].values[v]) for q, v in st.items()})
    if not rows:
        return {cap_label_fn(c): np.zeros(0) for c in caps}, described
    pts = np.vstack(rows)[:, cols] / float(base_k) * 100.0
    return {cap_label_fn(c): change_fn(pts, len(pre_years), c) for c in caps}, described


def _years():
    from pipeline.facilities import pass_c_expand as px
    return px.YEARS


# ================================================================================================================
# 5. The two Oregon utilities, from the quantity files
# ================================================================================================================

def _oregon_inputs():
    """The state enumeration exactly as second_number builds it (oregon_state, screen shift 0), the corrections in
    force for its sites, and the load-unknown sites' file. Load and sales only."""
    from pipeline.analysis import second_number as sn
    from pipeline.facilities import corrections as cx
    from pipeline.facilities import timing as tm
    unk = json.loads((ROOT / "data" / "frozen" / "unknown_load_sites_and_affected_utilities.json").read_text())
    fids = [s["fid"] for s in unk["sites"]]
    S_by_state, inp = sn.oregon_state(fids)
    entries = tm.timing_entries(cx.load(cx.CORRECTIONS))
    return sn, tm, unk, fids, S_by_state, inp, entries


def oregon_detail(scope: str) -> dict:
    """Everything the finding rests on, for Portland General and Umatilla, in one scope. The scope is required."""
    _check_scope(scope)
    from pipeline.facilities import pass_c_expand as px
    sn, tm, unk, fids, S_by_state, inp, entries = _oregon_inputs()
    first, last = px.YEARS[0], px.YEARS[-1]
    out = {"scope": scope, "sites_with_no_load_history": fids, "utilities": {}}
    for uid in unk["every_affected_utility"]:
        u, st = uid.split(":")
        k = (int(u), st)
        S = S_by_state[st]
        base_k = float(inp.base.get(k, np.nan))
        r = sn.unknown_load_histories(S, k, base_k, fids)
        varied = [qid for qid, q in enumerate(S.qs) if q.fid in fids and q.name in ("date", "capacity")]
        cases = rule4_cases(S.qs, k[0])
        adm = {}
        for e in entries:
            if e["fid"] in fids and e["kind"] in ("date", "capacity_split"):
                name = "date" if e["kind"] == "date" else "capacity"
                adm[(e["fid"], name)] = admissible_settings(
                    e, first_year=first, last_year=last, ramp_years=px.RAMP_YEARS,
                    inventory_year=(int(inp.fac.date_inventory_year[e["fid"]]) if e["kind"] == "capacity_split" else None))
        fm, rel = S.relevance(k)
        screen = [f for f in tm.screen_rows(inp, st, {e["fid"] for e in entries if inp.fac.state.get(e["fid"]) == st})
                  if int(inp.fac.utility_id_eia[f]) == k[0]]
        cov = coverage_check(S.qs, k_id=k[0], unknown_fids=fids, varied_qids=varied, case_settings=cases,
                             relevant=rel, admissible=adm, histories=r.histories,
                             wider_set_gaps=([f"the generic screen's shifts of 3 and 5 years (rows {', '.join(screen)} on "
                                              f"this utility) are held at shift 0"] if screen else []))
        # the scope's admitted settings, for the bounds
        if scope == "rule_8_1_text":
            opts = {}
            for c in cases.values():
                for q, v in c.items():
                    opts.setdefault(q, set()).add(v)
            rows = allowed_rows(S, free_qids=varied, fixed_options=opts)
        else:
            rows = allowed_rows(S, free_qids=range(len(S.qs)), fixed_options={})
        yrs = list(PRE_YEARS) + list(POST_YEARS)
        ext = load_extremes(S, k, base_k, rows, scale_lo=px.SCALE_LO, scale_hi=px.SCALE_HI, factor_tol=px.FACTOR_TOL,
                            years=yrs, factor_fn=S.factor)
        changes = {lab: np.asarray(v) for lab, v in r.changes.items()}
        witnesses, described = {}, []
        if scope == "place_test_wider_set":
            # one configuration per held date question at its earliest admissible setting, every other question at the
            # reference: a handful of single configurations, never an enumeration
            held_dates = [h["question_id"] for h in cov["relevant_questions_not_varied"] if h["question"] == "date"]
            settings = [{q: 0} for q in held_dates]
            witnesses, described = witness_changes(S, k, base_k, settings, caps=sn.CAPS, change_fn=sn.change,
                                                   cap_label_fn=sn.cap_label)
            changes = {lab: np.concatenate([changes[lab], witnesses.get(lab, np.zeros(0))]) for lab in changes}
        bnds = {lab: bounds_argument(ext, label=lab) for lab in r.changes if lab != UNCAPPED}
        comp = completeness_for(cov, scope)
        verdict = apply_rule(changes, completeness=comp, bounds=bnds)
        out["utilities"][uid] = {
            "name": str(inp.names.get(k)), "base_gwh_2009_2011": base_k,
            "enumeration": {"histories": r.histories,
                            "range_by_cap": {lab: [float(np.min(v)), float(np.max(v))] for lab, v in r.changes.items()},
                            "every_history_equal_by_cap": {lab: bool(len(v) and np.all(np.asarray(v) == np.asarray(v)[0]))
                                                           for lab, v in r.changes.items()}},
            "coverage": cov, "factor_matters": bool(fm),
            "place_test_configurations_screen_shift_0": int(math.prod(len(c) for _, c in rel)),
            "load_extremes": ext,
            "bounds": {lab: {"holds": b.holds, "dose": b.dose, "basis": b.basis, "failed": list(b.failed),
                             "steps": [s.__dict__ for s in b.steps]} for lab, b in bnds.items()},
            "witnesses": {"settings": described,
                          "changes_by_cap": {lab: [float(x) for x in v] for lab, v in witnesses.items()}},
            "generic_screen_rows_on_it": screen,
            "verdict": verdict}
    return out


def oregon_verdicts(scope: str) -> dict:
    """{utility id: {cap label: {"established", "dose", "why"}}} for Portland General and Umatilla, read from the
    quantity files, in the scope named. The scope is a required argument with no default so that each call says which
    verdicts it computes: both are computed and kept on record, and the verdict for Umatilla differs between the two.
    The analysis applies RULED_SCOPE's only (Joe, D-107, 2026-11-19; established_as_ruled)."""
    return {uid: d["verdict"] for uid, d in oregon_detail(_check_scope(scope))["utilities"].items()}


SCOPE_WORDS = {"rule_8_1_text": "rule 8.1's own histories", "place_test_wider_set": "the place test's wider set"}


def _check_both(verdicts_by_scope: dict) -> dict:
    missing = [s for s in SCOPES if s not in verdicts_by_scope]
    if missing:
        raise ValueError(f"the verdicts of every scope are needed ({SCOPES}) so that both stay on record; missing: {missing}")
    extra = [s for s in verdicts_by_scope if s not in SCOPES]
    if extra:
        raise ValueError(f"unknown scopes {extra}; the scopes are {SCOPES}")
    uids = {s: set(verdicts_by_scope[s]) for s in SCOPES}
    if len({frozenset(v) for v in uids.values()}) != 1:
        raise ValueError(f"the scopes give verdicts for different utilities: {uids}")
    for uid in uids[SCOPES[0]]:
        labs = {s: set(verdicts_by_scope[s][uid]) for s in SCOPES}
        if len({frozenset(v) for v in labs.values()}) != 1:
            raise ValueError(f"{uid}: the scopes give verdicts for different forms: {labs}")
    return uids


def established_as_ruled(verdicts_by_scope: dict) -> dict:
    """The common-dose mapping the analysis applies: {uid: {cap label: {"established", "dose", "why"}}}, the verdicts of
    RULED_SCOPE (Joe, D-107, 2026-11-19: the exception is judged on the wider admissible histories, which contain a
    counterexample; they are not narrowed to obtain settled status). `verdicts_by_scope` carries every scope of SCOPES,
    so that the other scope's verdict is recorded beside each one; a missing scope stops in words. Only RULED_SCOPE's
    `established` and `dose` are applied. Where the other scope would establish a form the ruled scope does not, the why
    says so, as what was found and not as an open choice."""
    uids = _check_both(verdicts_by_scope)
    other = [s for s in SCOPES if s != RULED_SCOPE][0]
    out = {}
    for uid in sorted(uids[RULED_SCOPE]):
        out[uid] = {}
        for lab in sorted(verdicts_by_scope[RULED_SCOPE][uid]):
            r, o = verdicts_by_scope[RULED_SCOPE][uid][lab], verdicts_by_scope[other][uid][lab]
            if bool(r["established"]) and r.get("dose") is None:
                raise ValueError(f"{uid} at {lab}: the ruled scope establishes a change with no dose")
            beside = (f"recorded beside it, not applied, under {SCOPE_WORDS[other]}: "
                      + (f"established at {float(o['dose'])} ({o['why']})" if bool(o["established"]) else
                         f"not established ({o['why']})"))
            out[uid][lab] = _verdict(bool(r["established"]), r.get("dose") if bool(r["established"]) else None,
                                     f"{RULING}. Under {SCOPE_WORDS[RULED_SCOPE]}: {r['why']}; {beside}")
    return out


def established_under_every_scope(verdicts_by_scope: dict) -> dict:
    """SUPERSEDED RECORD (applied from D-106 until Joe's ruling of 2026-11-19, D-107; nothing in the analysis path calls
    it since, and established_as_ruled replaces it). {uid: {cap label: {"established", "dose", "why"}}}, established only
    where every scope of SCOPES establishes the same form at exactly the same dose. `verdicts_by_scope`: {scope:
    oregon_verdicts(scope)} for ALL of SCOPES; a missing scope, or a utility or form one scope has and another lacks,
    stops in words. Where the scopes disagree the why carries each scope's own reason and says which scope Joe ruled
    governs."""
    missing = [s for s in SCOPES if s not in verdicts_by_scope]
    if missing:
        raise ValueError(f"the verdicts of every scope are needed ({SCOPES}); missing: {missing}. A form is established "
                         "here only where every scope establishes it, so no scope can be left out")
    extra = [s for s in verdicts_by_scope if s not in SCOPES]
    if extra:
        raise ValueError(f"unknown scopes {extra}; the scopes are {SCOPES}")
    uids = {s: set(verdicts_by_scope[s]) for s in SCOPES}
    if len({frozenset(v) for v in uids.values()}) != 1:
        raise ValueError(f"the scopes give verdicts for different utilities: {uids}")
    out = {}
    for uid in sorted(uids[SCOPES[0]]):
        labs = {s: set(verdicts_by_scope[s][uid]) for s in SCOPES}
        if len({frozenset(v) for v in labs.values()}) != 1:
            raise ValueError(f"{uid}: the scopes give verdicts for different forms: {labs}")
        out[uid] = {}
        for lab in sorted(labs[SCOPES[0]]):
            v = {s: verdicts_by_scope[s][uid][lab] for s in SCOPES}
            est = {s: bool(v[s]["established"]) for s in SCOPES}
            doses = {s: (None if v[s]["dose"] is None else float(v[s]["dose"])) for s in SCOPES}
            each = "; ".join(f"under {SCOPE_WORDS[s]}: {v[s]['why']}" for s in SCOPES)
            if all(est.values()) and len(set(doses.values())) == 1:
                d = doses[SCOPES[0]]
                out[uid][lab] = _verdict(True, d, f"established at {d} under every scope ({each})")
            elif not any(est.values()):
                out[uid][lab] = _verdict(False, None, f"not established under any scope ({each})")
            else:
                parts = []
                for s in SCOPES:
                    parts.append(f"established at {doses[s]} under {SCOPE_WORDS[s]} ({v[s]['why']})" if est[s] else
                                 f"not established under {SCOPE_WORDS[s]} ({v[s]['why']})")
                ruled = (f"{SCOPE_WORDS[RULED_SCOPE]} establishes it, and under the ruling it is established_as_ruled "
                         "that applies it" if est[RULED_SCOPE] else
                         f"{SCOPE_WORDS[RULED_SCOPE]} does not establish it, so the exclusion is retained")
                out[uid][lab] = _verdict(False, None, "; ".join(parts) + f". {RULING}; here {ruled}")
    return out


def main() -> int:
    """Prints both scopes' verdicts and the mapping applied under Joe's ruling (D-107). Writes nothing."""
    by_scope = {}
    for scope in SCOPES:
        by_scope[scope] = oregon_verdicts(scope)
        print(scope)
        print(json.dumps(by_scope[scope], indent=1))
    print("applied, " + RULED_SCOPE)
    print(json.dumps(established_as_ruled(by_scope), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
