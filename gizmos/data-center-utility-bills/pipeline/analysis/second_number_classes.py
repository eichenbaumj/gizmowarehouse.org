#!/usr/bin/env python3
"""SUPERSEDED RECORD of what was proposed (D-104). Joe adopted the proposal with qualifications on 2026-11-19 (D-105):
each form classed at its own cap, the apparent-zero flag retained where settled takes precedence, classes 5 to 8 counted
as not settled for leverage, class 2 renamed "no endpoint exposure in modeled histories", and the common-dose exception
applied per capped form. The ADOPTED classification is pipeline/analysis/second_number.py, section 3a; the analysis
path calls nothing in this module. This module is kept as the record of the proposal, with its old class names, and
data/frozen/second_number_classification_proposal.json is kept unchanged as the record of its output: main() no longer
writes it, and summary() refuses to run (it reads the as-built classes from second_number_design.json, which now carries
the adopted ones, and calls run helpers of second_number.py whose signatures have since changed; the exact code that
wrote the record is this file at commit 76384e5).

The text below is the proposal as written.

A PROPOSAL for Joe, not adopted: an exhaustive classification of the second number's utilities by their dose ranges,
with explicit precedence, written beside rule 8.2 as built (PREANALYSIS.md, "The second number: per point of load",
rules 8.1 to 8.3; Joe's instruction of 2026-11-19, D-103: "Propose an exhaustive classification with explicit
precedence, distinguishing zero exposure change from no site in reach, and justify any sample exclusion from the
analysis rules").

Nothing here changes the plan, pipeline/analysis/second_number.py or data/frozen/second_number_design.json. The plan is
a DRAFT and not frozen. Load, sales, the usable flag and the access-list files only: nothing here reads, opens or prints
a price, a revenue or a bill.

The proposal (session 19's design). For each utility, from its feasible histories (rule 8.1, as second_number.py builds
them): a = the capped change as assigned (may be absent), lo and hi = the smallest and largest capped change over its
histories, reach = whether it carries any data center load (uncapped, above zero) in any year of either endpoint period
(2008 to 2010, 2023 to 2025) in any history. Tested in this order, first match wins:

  1 no_single_dose                          no dose as assigned (a site with no load history reaches it), unless its
                                            histories give one common dose
  2 no_site_in_reach                        reach is false
  3 settled_zero_change_with_load_in_reach  reach is true and lo == hi == 0
  4 settled                                 hi - lo < 2 points
  5 uncertain_positive_exposure             not settled, lo > 0
  6 apparent_zero                           not settled, a == 0, hi > 0
  7 positive_as_assigned_zero_in_some_case  not settled, a > 0, lo <= 0
  8 other_not_settled                       anything left

Output as written (2026-11-19): data/frozen/second_number_classification_proposal.json (quantity-only, provisional, a
proposal). Since D-105 nothing writes that file; it is the record.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import second_number as sn  # noqa: E402

PROPOSAL_RECORD = sn.FROZEN / "second_number_classification_proposal.json"     # the kept record; nothing writes it
SETTLED_BELOW = sn.SETTLED_BELOW                       # two points: the plan's convention (rule 8.2), not a new threshold

NO_SINGLE_DOSE = "no_single_dose"
NO_SITE_IN_REACH = "no_site_in_reach"
ZERO_CHANGE = "settled_zero_change_with_load_in_reach"
SETTLED = "settled"
UNCERTAIN = "uncertain_positive_exposure"
APPARENT_ZERO = "apparent_zero"
POSITIVE_ZERO_SOME = "positive_as_assigned_zero_in_some_case"
OTHER = "other_not_settled"
CLASSES = (NO_SINGLE_DOSE, NO_SITE_IN_REACH, ZERO_CHANGE, SETTLED, UNCERTAIN, APPARENT_ZERO, POSITIVE_ZERO_SOME, OTHER)
NOT_SETTLED = (UNCERTAIN, APPARENT_ZERO, POSITIVE_ZERO_SOME, OTHER)          # classes 5 to 8 (rule 8.3's leave-ten-out run)
SETTLED_ONLY_RUN = (NO_SITE_IN_REACH, ZERO_CHANGE, SETTLED)                  # classes 2 to 4

SUB_ZERO_ASSIGNED = "zero_as_assigned_positive_in_some_case"
SUB_POSITIVE_EVERY = "positive_in_every_case"
SUB_OTHER = "other"

PROPOSAL = "proposal"
APPARENT_ZERO_FIRST = "apparent_zero_before_settled"

DEFINITIONS = {
    NO_SINGLE_DOSE: "1. No dose as assigned (a site with no load history reaches it), unless its histories give one common "
                    "dose, in which case that dose is its dose as assigned and the tests below apply. Out of every run on "
                    "single doses and named.",
    NO_SITE_IN_REACH: "2. No data center load above zero in any year of 2008 to 2010 or 2023 to 2025 in any feasible history "
                      "(uncapped). Its change is zero because nothing reaches it. Still subject to missing sites (D-46 "
                      "ruling 6).",
    ZERO_CHANGE: "3. Load in reach (some history carries load in an endpoint period) and the capped change is zero in every "
                 "history. Zero exposure change, not zero exposure. Which kind is recorded per history: no load at either "
                 "endpoint in that history, at or above the cap in every endpoint year, or equal capped averages below the cap.",
    SETTLED: "4. Not classed above and the capped change differs by less than two points across its histories (hi - lo < 2; "
             "exactly 2 is not settled). Sub-labels, attributes and not classes: zero_as_assigned_positive_in_some_case "
             "(a == 0 and hi > 0; not a verified zero), positive_in_every_case (lo > 0), other.",
    UNCERTAIN: "5. Not settled and above zero in every history (lo > 0).",
    APPARENT_ZERO: "6. Not settled, zero as assigned and above zero in some history (a == 0, hi > 0). Not a verified zero.",
    POSITIVE_ZERO_SOME: "7. Not settled, above zero as assigned and zero or below in some history (a > 0, lo <= 0).",
    OTHER: "8. Anything left (for example zero or below as assigned with a negative change in some history and two points "
           "or more apart). Exists so the classification is exhaustive.",
}
PRECEDENCE = [NO_SINGLE_DOSE, NO_SITE_IN_REACH, ZERO_CHANGE, SETTLED, UNCERTAIN, APPARENT_ZERO, POSITIVE_ZERO_SOME, OTHER]
RUNS_IN_WORDS = {
    "as_assigned": "every class with a dose as assigned (2 to 8)",
    "settled_and_no_site_in_reach_only": "classes 2, 3 and 4, each at its dose as assigned",
    "ten_highest_leverage_not_settled_left_out": "classes 5 to 8 are not settled; the ten with the highest leverage in the "
                                                 "run as assigned at 25 points are left out",
    "class_1": "out of every run on single doses, and named",
}


# ================================================================================================================
# Pure functions
# ================================================================================================================

def range_of(changes) -> tuple[float, float]:
    """(lo, hi) of the within-history changes. Stops in words on an empty or non-finite range."""
    v = np.asarray(changes, dtype=float)
    if v.size == 0 or not np.isfinite(v).all():
        raise ValueError("a utility with a dose needs a finite change in every history; none is filled or dropped")
    return float(v.min()), float(v.max())


def reach_from_endpoints(endpoint_points) -> bool:
    """Whether any history carries data center load above zero in any endpoint year. endpoint_points: histories by the
    six endpoint years (2008 to 2010, 2023 to 2025), load share in points, UNCAPPED."""
    e = np.asarray(endpoint_points, dtype=float)
    if not np.isfinite(e).all():
        raise ValueError("endpoint load shares must be finite to say whether load is in reach")
    return bool((e > 0).any())


def zero_change_kind(endpoint_points, n_pre: int, cap) -> str:
    """For one history whose capped change is zero: why it is zero. endpoint_points: the six endpoint years, uncapped."""
    e = np.asarray(endpoint_points, dtype=float)
    if np.all(e == 0):
        return "no_load_at_either_endpoint"
    if cap is not None and np.all(e >= cap):
        return "at_or_above_the_cap_in_every_endpoint_year"
    unc = float(e[n_pre:].mean() - e[:n_pre].mean())
    return "equal_capped_averages_below_the_cap" + ("" if unc == 0 else "_uncapped_change_not_zero")


def classify(assigned, changes, reach: bool, common_dose=None, precedence: str = PROPOSAL) -> dict:
    """The proposal for one utility. assigned: the capped change as assigned, or None/NaN where there is none.
    changes: the capped change in every feasible history. reach: reach_from_endpoints over those histories.
    common_dose: for a utility with no dose as assigned, the change every history gives, where they all give one.
    precedence: PROPOSAL, or APPARENT_ZERO_FIRST (class 6 tested before class 4) to count what that order would move.
    Returns {"class", "sub_label", "a", "lo", "hi", "reach"}."""
    no_assigned = assigned is None or (isinstance(assigned, float) and np.isnan(assigned))
    if no_assigned:
        if common_dose is None:
            return {"class": NO_SINGLE_DOSE, "sub_label": None, "a": None, "lo": None, "hi": None, "reach": reach}
        assigned = float(common_dose)
    a = float(assigned)
    if not np.isfinite(a):
        raise ValueError("the dose as assigned must be finite")
    lo, hi = range_of(changes)
    if not (lo <= a <= hi):
        raise ValueError(f"the dose as assigned ({a}) lies outside the range of its histories [{lo}, {hi}]; the as-assigned "
                         "history is one of them")
    out = {"a": a, "lo": lo, "hi": hi, "reach": bool(reach), "sub_label": None}
    if not reach:
        if lo != 0 or hi != 0:
            raise ValueError("no load in reach but a change other than zero: the inputs are inconsistent")
        return {**out, "class": NO_SITE_IN_REACH}
    if lo == 0 and hi == 0:
        return {**out, "class": ZERO_CHANGE}
    settled = hi - lo < SETTLED_BELOW
    apparent = a == 0 and hi > 0
    if precedence == APPARENT_ZERO_FIRST and apparent and settled:
        return {**out, "class": APPARENT_ZERO}
    if precedence not in (PROPOSAL, APPARENT_ZERO_FIRST):
        raise ValueError(f"unknown precedence {precedence}")
    if settled:
        sub = SUB_ZERO_ASSIGNED if apparent else SUB_POSITIVE_EVERY if lo > 0 else SUB_OTHER
        return {**out, "class": SETTLED, "sub_label": sub}
    if lo > 0:
        return {**out, "class": UNCERTAIN}
    if apparent:
        return {**out, "class": APPARENT_ZERO}
    if a > 0 and lo <= 0:
        return {**out, "class": POSITIVE_ZERO_SOME}
    return {**out, "class": OTHER}


def rule_8_2_as_built(assigned, changes) -> str:
    """Rule 8.2 as built, in the order second_number.py tests it (no site in reach, apparent zero, settled, uncertain
    positive exposure; else in none of the four). Calls second_number.classify; nothing is copied."""
    if assigned is None or (isinstance(assigned, float) and np.isnan(assigned)):
        return sn.classify_without_assigned(changes)
    return sn.classify(float(assigned), changes)


def rule_8_2_text_matches(assigned: float, changes) -> set:
    """Which of the plan's four definitions the text applies to a range, with no order (rule 8.2 as written):
    settled (differs by less than two points), uncertain positive exposure (above zero in every case, not settled),
    apparent zero (zero as assigned, above zero in some case), no site in reach (zero in every case)."""
    lo, hi = range_of(changes)
    m = set()
    if hi - lo < SETTLED_BELOW:
        m.add(sn.SETTLED)
    if lo > 0 and not hi - lo < SETTLED_BELOW:
        m.add(sn.UNCERTAIN)
    if assigned == 0 and hi > 0:
        m.add(sn.APPARENT_ZERO)
    if lo == 0 and hi == 0:
        m.add(sn.NO_SITE)
    return m


PROPOSED_FOR_TEXT = {sn.SETTLED: SETTLED, sn.UNCERTAIN: UNCERTAIN, sn.APPARENT_ZERO: APPARENT_ZERO}


def as_settled_map(classes: dict, settled_like) -> dict:
    """Classes re-labelled for second_number's run helpers, which count as not settled anything that is not sn.SETTLED:
    every class in `settled_like` becomes sn.SETTLED and every other sn.UNCLASSIFIED (a label run_summary counts and
    treats as not settled; its class counts are then not read, only its leverage share)."""
    return {u: (sn.SETTLED if c in settled_like else sn.UNCLASSIFIED) for u, c in classes.items()}


# ================================================================================================================
# main: the quantity-only summary
# ================================================================================================================

def _name(names, uid):
    u, st = uid.split(":")
    return names.get((int(u), st))


def _listing(names, uids, extra=None) -> list:
    return [{"utility": u, "state": u.split(":")[1], "name": _name(names, u), **((extra or {}).get(u, {}))} for u in sorted(uids)]


class SupersededRecord(RuntimeError):
    pass


def summary() -> dict:
    """SUPERSEDED RECORD: the writer of the proposal's summary (D-104). It does not run any more; see the module docstring."""
    raise SupersededRecord("second_number_classes.summary is the superseded record of the proposal (D-104), adopted with "
                           "qualifications in D-105. Its output is kept unchanged at " + str(PROPOSAL_RECORD) + "; the "
                           "adopted classification and its summary are pipeline/analysis/second_number.py. Not rerun")
    from pipeline.analysis import usable_flag  # noqa: E402  (the record of the proposal's writer follows, unreachable)
    from pipeline.electricity import market_region, panel
    from pipeline.facilities import assignment as asg

    q = panel.load_quantities()
    usable = usable_flag.read().usable
    regions = market_region.by_unit_year(q)
    codes = sn.region_codes(regions)
    dose = pd.read_parquet(sn.INTERIM / "utility_year_dose.parquet")
    unknown = ps.load_unknown_load()
    affected = set(unknown.affected)
    hold = ps.price_hold()
    names = q.groupby(sn.KEY).utility_name.last()

    # ---- rule 8.1's six histories and the frame, by second_number's own functions, in design_summary's order
    fac, fy, _q, units, base, regions_fixed = asg.load_inputs()
    _t, m, _res = asg.evaluate(fac, fy, units, base, regions_fixed)
    pts, no_base = sn.case_points(m, base)
    cands, named_before = sn._sample_candidates(q, hold, affected)
    no_base_ids = {sn._uid(k) for k in no_base}
    frame0 = sn.build_frame(cands + sorted(affected), q, regions, usable, codes=codes)
    no_base_in_frame = [sn._uid(k) for k in frame0.keys if sn._uid(k) in no_base_ids]
    frame = sn.sub_frame(frame0, [i for i, k in enumerate(frame0.keys) if sn._uid(k) not in no_base_ids])
    assigned_keys = [k for k in frame.keys if k not in affected]
    idx = pd.MultiIndex.from_tuples(assigned_keys, names=sn.KEY)
    main_lab = sn.cap_label(sn.MAIN_CAP)
    ch = {sn.cap_label(c): sn.history_changes({h: p.reindex(idx) for h, p in pts.items()}, cap=c) for c in sn.CAPS}
    c25 = ch[main_lab]
    endpoint_years = list(sn.PRE) + list(sn.POST)

    # ---- as built, and the proposal, per utility with a dose as assigned
    as_built, prop, alt, kinds, reach = {}, {}, {}, {}, {}
    near_zero, class2_load_between = [], []
    for k in assigned_keys:
        uid = sn._uid(k)
        v = c25.loc[k].values
        a = float(c25.loc[k, sn.ASSIGNED])
        ends = np.vstack([pts[h].loc[k, endpoint_years].values for h in sn.HISTORIES])
        reach[uid] = reach_from_endpoints(ends)
        as_built[uid] = rule_8_2_as_built(a, v)
        prop[uid] = classify(a, v, reach[uid])
        alt[uid] = classify(a, v, reach[uid], precedence=APPARENT_ZERO_FIRST)["class"]
        if np.any((v != 0) & (np.abs(v) < 1e-9)):
            near_zero.append(uid)
        if prop[uid]["class"] == NO_SITE_IN_REACH and any(float(np.nanmax(pts[h].loc[k].values)) > 0 for h in sn.HISTORIES):
            class2_load_between.append(uid)
        if prop[uid]["class"] == ZERO_CHANGE:
            per_h = {h: zero_change_kind(ends[i], len(sn.PRE), sn.MAIN_CAP) for i, h in enumerate(sn.HISTORIES)}
            kinds[uid] = {"as_assigned": per_h[sn.ASSIGNED], "kinds_over_histories": sorted(set(per_h.values())),
                          "by_history": per_h,
                          "endpoint_load_share_points_as_assigned_uncapped": [round(float(x), 3) for x in ends[0]],
                          "largest_endpoint_load_share_points_any_history_uncapped": round(float(ends.max()), 3)}

    # ---- the utilities with no dose as assigned: their histories, as second_number builds them
    unk = {}
    sites = json.loads((sn.FROZEN / ps.UNKNOWN_LOAD_FILE).read_text()).get("sites", [])
    fids = [s["fid"] for s in sites]
    in_frame = {sn._uid(k) for k in frame.keys}
    try:
        S_by_state, inp = sn.oregon_state(fids)
        failed = None
    except Exception as e:                                       # reported, never papered over
        S_by_state, inp, failed = {}, None, f"{type(e).__name__}: {e}"
    for k in sorted(affected):
        uid = sn._uid(k)
        if uid not in in_frame:
            continue
        entry = {"name": names.get(k)}
        if failed or k[1] not in S_by_state:
            entry.update(range_established=False, why=failed or f"no enumeration for {k[1]}")
            as_built[uid] = sn.NO_RANGE
            prop[uid] = classify(None, [], True)
        else:
            r = sn.unknown_load_histories(S_by_state[k[1]], k, float(inp.base.get(k, np.nan)), fids)
            as_built[uid] = rule_8_2_as_built(None, r.changes.get(main_lab, [])) if r.established else sn.NO_RANGE
            if r.common_dose is not None:
                # Its reach would need the endpoint loads of every enumerated history, which unknown_load_histories does
                # not return; on the design as it stands no such utility has a common dose (second_number_design.json).
                raise RuntimeError(f"{uid} has a common dose over its histories; classing it under the proposal needs its "
                                   "endpoint loads per history, which this module does not compute. Stopping in words")
            prop[uid] = classify(None, r.changes.get(main_lab, []), True)
            entry.update(range_established=r.established, histories_evaluated=r.histories,
                         range_of_change_points={lab: [round(float(x.min()), 6), round(float(x.max()), 6)]
                                                 for lab, x in r.changes.items()},
                         common_dose_by_cap=sn.common_by_cap(r.changes), common_dose_at_every_cap=r.common_dose)
        entry.update(class_as_built=as_built[uid], proposed_class=prop[uid]["class"])
        unk[uid] = entry
        alt[uid] = prop[uid]["class"]

    # ---- reproduction of the as-built classes against the frozen file
    frozen = json.loads((sn.FROZEN / "second_number_design.json").read_text())
    fz = {r["utility"]: r["class"] for r in frozen["utilities"]}
    fz.update({u: r.get("class", sn.NO_RANGE) for u, r in frozen["utilities_with_no_assigned_dose"].items()})
    mism = sorted(u for u in as_built if fz.get(u) != as_built[u])
    reproduction = {"utilities_compared": len(as_built), "class_as_built_differs_from_second_number_design_json": mism,
                    "utilities_in_the_frozen_file_not_reproduced_here": sorted(set(fz) - set(as_built))}

    pc = {u: r["class"] for u, r in prop.items()}
    counts = {c: int(sum(v == c for v in pc.values())) for c in CLASSES}
    ab_labels = list(sn.CLASSES) + [sn.UNCLASSIFIED, sn.NO_RANGE]
    xtab = {c: {b: int(sum(1 for u in pc if pc[u] == c and as_built[u] == b)) for b in ab_labels} for c in CLASSES}
    sub_counts = {s: int(sum(1 for r in prop.values() if r["sub_label"] == s)) for s in (SUB_ZERO_ASSIGNED, SUB_POSITIVE_EVERY, SUB_OTHER)}

    def rng(u):
        r = prop[u]
        k = (int(u.split(":")[0]), u.split(":")[1])
        other = ({lab: [round(float(ch[lab].loc[k].min()), 6), round(float(ch[lab].loc[k].max()), 6)] for lab in ch if lab != main_lab}
                 if k in ch[main_lab].index else None)
        return {"assigned_change_points_capped_25": None if r["a"] is None else round(r["a"], 6),
                "range_points_capped_25": None if r["lo"] is None else [round(r["lo"], 6), round(r["hi"], 6)],
                "range_points_at_the_other_caps_for_information": other,
                "class_as_built": as_built[u]}

    named = {c: _listing(names, [u for u in pc if pc[u] == c], {u: rng(u) for u in pc}) for c in (NO_SINGLE_DOSE, ZERO_CHANGE, APPARENT_ZERO, POSITIVE_ZERO_SOME, OTHER)}
    for item in named[ZERO_CHANGE]:
        item["zero_change_kind"] = kinds[item["utility"]]
    named_sub = _listing(names, [u for u in prop if prop[u]["sub_label"] == SUB_ZERO_ASSIGNED], {u: rng(u) for u in pc})
    named_sub_other = _listing(names, [u for u in prop if prop[u]["sub_label"] == SUB_OTHER], {u: rng(u) for u in pc})
    moved_alt = [u for u in pc if alt[u] != pc[u]]

    # ---- the runs on single doses: who is in them and the share of leverage not settled
    dx = {lab: {sn._uid(k): float(ch[lab].loc[k, sn.ASSIGNED]) for k in assigned_keys} for lab in ch}
    a_sub = sn.sub_frame(frame, [i for i, k in enumerate(frame.keys) if k not in affected])
    lev25 = dict(zip(map(sn._uid, a_sub.keys), sn.leverage(np.array([dx[main_lab][sn._uid(k)] for k in a_sub.keys]), a_sub)))
    ids = [sn._uid(k) for k in assigned_keys]
    m_prop = as_settled_map(pc, SETTLED_ONLY_RUN)                     # classes 5 to 8 not settled
    m_prop_ab_convention = as_settled_map(pc, (SETTLED,))             # only class 4 settled, as second_number counts
    m_ab = {u: c for u, c in as_built.items()}
    ten_prop = sn.leave_out_ten(lev25, {u: m_prop[u] for u in ids})
    ten_ab = sn.leave_out_ten(lev25, {u: m_ab[u] for u in ids})
    members_prop = {"as_assigned": ids,
                    "settled_and_no_site_in_reach_only": [u for u in ids if pc[u] in SETTLED_ONLY_RUN],
                    "ten_highest_leverage_not_settled_left_out": [u for u in ids if u not in ten_prop]}
    members_ab = {"as_assigned": ids,
                  "settled_and_no_site_in_reach_only": [u for u in ids if m_ab[u] in (sn.SETTLED, sn.NO_SITE)],
                  "ten_highest_leverage_not_settled_left_out": [u for u in ids if u not in ten_ab]}

    def share(members, cmap):
        return sn.run_summary(members, frame, dx, cmap)["share_of_leverage_held_by_utilities_not_settled"]

    def by_class(members):
        want = set(members)
        sub = sn.sub_frame(frame, [i for i, k in enumerate(frame.keys) if sn._uid(k) in want])
        lev = sn.leverage(np.array([dx[main_lab][sn._uid(k)] for k in sub.keys]), sub)
        out = {}
        for k, l in zip(sub.keys, lev):
            out[pc[sn._uid(k)]] = out.get(pc[sn._uid(k)], 0.0) + float(l)
        return {c: round(out.get(c, 0.0), 6) for c in CLASSES if c != NO_SINGLE_DOSE}

    runs = {}
    for name in members_prop:
        mp, mb = members_prop[name], members_ab[name]
        runs[name] = {
            "proposal": {"utilities": len(mp), "not_settled_utilities_classes_5_to_8": int(sum(pc[u] in NOT_SETTLED for u in mp)),
                         "class_counts": {c: int(sum(pc[u] == c for u in mp)) for c in CLASSES},
                         "share_of_leverage_not_settled_classes_5_to_8": share(mp, m_prop),
                         "share_of_leverage_not_in_class_4_second_numbers_counting_convention": share(mp, m_prop_ab_convention),
                         "share_of_leverage_by_proposed_class_capped_25": by_class(mp)},
            "as_built_recomputed": {"utilities": len(mb), "not_settled_utilities_anything_not_settled": int(sum(m_ab[u] != sn.SETTLED for u in mb)),
                                    "share_of_leverage_not_settled": share(mb, m_ab)},
            "as_built_in_second_number_design_json": frozen["runs"][name]["share_of_leverage_held_by_utilities_not_settled"],
        }
    runs["ten_highest_leverage_not_settled_left_out"]["proposal"]["the_ten"] = _listing(names, ten_prop, {u: {"proposed_class": pc[u], "leverage_25": round(float(lev25[u]), 6)} for u in ten_prop})
    runs["ten_highest_leverage_not_settled_left_out"]["as_built_recomputed"]["the_ten"] = ten_ab
    runs["class_1_left_out_of_every_run_on_single_doses"] = _listing(names, [u for u in pc if pc[u] == NO_SINGLE_DOSE])

    sample = sample_findings(q, dose, frame, frame0, assigned_keys, affected, named_before, no_base_in_frame, pc, names, unknown)

    return {
        "what_this_is": ("A PROPOSAL for Joe, not adopted (his instruction of 2026-11-19, D-103). Quantity-only and PROVISIONAL: "
                         "the design as it stands on 2026-11-18; the plan is a DRAFT and not frozen. The as-built classes "
                         "(pipeline/analysis/second_number.py, data/frozen/second_number_design.json) are unchanged and remain "
                         "the record. No price, revenue or bill was read; usability is the quantities file's res_price_usable "
                         "flag. No estimate is here. The two alternatives of rule 8.3 remain undefined; no scenario is defined here."),
        "built_by": "pipeline/analysis/second_number_classes.py",
        "definitions": {"inputs": {"a": "the change in dose capped at 25 points as assigned (inventory as built)",
                                   "lo_hi": "smallest and largest change capped at 25 points over rule 8.1's six histories",
                                   "reach": "load share above zero, uncapped, in any year of 2008-2010 or 2023-2025 in any of "
                                            "the six histories (as assigned or in any case)",
                                   "zero": "exact equality, as second_number.classify tests it"},
                        "classes_in_order_first_match_wins": PRECEDENCE, "class_definitions": DEFINITIONS,
                        "runs": RUNS_IN_WORDS,
                        "caps": ("classes are computed at the 25-point cap only: second_number.py classes at 25 points only "
                                 "(its classify is called on the capped change), so no 50-point or uncapped classes are given")},
        "reproduction_of_the_as_built_classes": reproduction,
        "near_zero_changes_not_exactly_zero": {"utilities": near_zero,
                                               "what": "utilities with a capped change in some history whose absolute value is "
                                                       "above zero and under 1e-9 (a floating-point residue that exact equality "
                                                       "would not treat as zero)"},
        "counts_by_proposed_class_capped_25": counts,
        "no_site_in_reach_with_load_outside_the_endpoint_years": {
            "utilities": _listing(names, class2_load_between),
            "what": "class 2 utilities (no load in any endpoint year in any history) that carry load in some year 2011-2022 "
                    "in some history; reach is measured at the endpoints only, as the proposal defines it"},
        "class_4_sub_label_counts": sub_counts,
        "cross_tab_proposed_class_by_class_as_built": xtab,
        "named": {**named, "settled_sub_label_zero_as_assigned_positive_in_some_case": named_sub,
                  "settled_sub_label_other": named_sub_other},
        "utilities_with_no_dose_as_assigned": unk,
        "runs_on_single_doses": runs,
        "alternative_precedence_apparent_zero_before_settled": {
            "moves": len(moved_alt),
            "utilities": _listing(names, moved_alt, {u: {"proposal": pc[u], "alternative": alt[u], **rng(u)} for u in moved_alt})},
        "sample": sample,
    }


def sample_findings(q, dose, frame, frame0, assigned_keys, affected, named_before, no_base_in_frame, pc, names, unknown) -> dict:
    """(a) every exclusion of the second number's sample as built; (b) the units the simulation's stand-in construction
    left out, and why; crypto-mining load across the sample. Quantity and access-list files only."""
    uid = sn._uid
    why_counts = {}
    for x in frame0.left_out:
        w = x["why"].split(" (")[0] if x["why"].startswith("not usable") else x["why"]
        w = "not usable in some year of 2008-2010 or 2023-2025" if w.startswith("not usable") else w
        why_counts[w] = why_counts.get(w, 0) + 1
    panel_units = int(len(q[sn.KEY].drop_duplicates()))
    exclusions = [
        {"exclusion": "price hold (price_hold.csv)", "count": len(named_before) - sum(1 for w in named_before.values() if w.startswith("reached by")),
         "utilities": sorted(u for u, w in named_before.items() if not w.startswith("reached by")),
         "plan_sentence": "Comparison utilities, (5): \"not in price_hold.csv (Huntsville)\"; The former hosts: \"Huntsville is on "
                          "neither side.\"; As built: \"Huntsville is out under the price hold.\"",
         "note": "the plan's sentences put Huntsville on neither side of the design; none is written in the second number's "
                 "own section except the as-built paragraph (the agent's reading: 'neither side of any design' covers it)"},
        {"exclusion": "not usable in every year of 2008-2010 and 2023-2025 (res_price_usable)",
         "count": why_counts.get("not usable in some year of 2008-2010 or 2023-2025", 0),
         "plan_sentence": "\"Utilities need to be usable in all six years (`res_price_usable`, Missing data).\""},
        {"exclusion": "no market region in some year of the comparison",
         "count": why_counts.get("no market region in some year of the comparison", 0),
         "plan_sentence": "\"within the utility's market region before (2009), its region after (2024) and its size band\"",
         "note": "as built (second_number.build_frame, as the simulation's run_second_number) a region is required in all six "
                 "years, though only 2009 and 2024 enter the fixed effect; the plan writes no requirement for the other four "
                 "years. Tested after usability, it removes no unit on the design as it stands"},
        {"exclusion": "no residential customers in 2010 (size band undefined)",
         "count": why_counts.get("no residential customers in 2010 (size band undefined)", 0),
         "plan_sentence": "\"... and its size band\"; the bands are Size adjustment's (under 10,000; 10,000 to 99,999; 100,000 or more)",
         "note": "the year 2010 is the simulation's reading (second_number.SIZE_YEAR); the second number's section names no year"},
        {"exclusion": "load in some history and no positive 2009-2011 sales (no dose)", "count": len(no_base_in_frame),
         "utilities": no_base_in_frame,
         "plan_sentence": "Treatment: load share is \"a share of its 2009-2011 retail sales\"; with no sales there is no share"},
        {"exclusion": "no dose as assigned: a site with no load history reaches it (rule 8.3's runs on single doses only)",
         "count": sum(1 for k in frame.keys if k in affected),
         "utilities": sorted(uid(k) for k in frame.keys if k in affected),
         "plan_sentence": "Rule 8.3: \"a utility with no assigned dose is kept out of the settled-only run, and out of every run "
                          "on single doses, unless its histories actually give one common dose\"; Sites with no load history: "
                          "\"In the primary run on doses as assigned it has no assigned dose, so it is left out of that run and named.\""},
    ]
    held = [u for u, w in named_before.items() if not w.startswith("reached by")]
    adds_up = panel_units == len(held) + sum(why_counts.values()) + len(frame0.keys)
    sample_counts = {"panel_units": panel_units, "held": len(held), "left_out_by_the_frame": sum(why_counts.values()),
                     "units_in_the_frame_before_the_no_base_check": len(frame0.keys), "units_in_the_frame": len(frame.keys),
                     "with_a_dose_as_assigned": len(assigned_keys), "the_counts_add_up": adds_up}

    # ---- the simulation's stand-in construction, from quantities and the access-list files
    d = dose.assign(crypto_share=dose.crypto_mw * 8.76 / dose.base_retail_gwh)
    per = d.groupby(sn.KEY).agg(max_dose=("dose", "max"), max_crypto_share=("crypto_share", "max"),
                                max_crypto_mw=("crypto_mw", "max"), max_dose_with_crypto=("dose_with_crypto", "max"))
    sim = {}
    for theta in (0.02, 0.05):
        _tr, clean = ps.design(q, dose, theta, ps.history_settled(theta))
        listed, off = ps.restrict_to_access_list(clean)
        gated, _ = unknown.gate(listed, theta, "comparison")
        sim[theta] = {"clean": set(zip(clean.utility_id_eia.astype(int), clean.state)),
                      "listed": set(zip(listed.utility_id_eia.astype(int), listed.state)),
                      "gated": set(zip(gated.utility_id_eia.astype(int), gated.state))}
    s02 = sim[0.02]
    sim_sample = [k for k in assigned_keys if k in s02["gated"]]
    excl = pd.read_csv(sn.ROOT / "pipeline" / "analysis" / "simulation_access_excluded.csv", dtype={"utility_id_eia": int, "state": str})
    excl_reason = {(int(r.utility_id_eia), r.state): r.reason for r in excl.itertuples()}

    def sim_why(k):
        if k not in s02["clean"]:
            r = per.loc[k] if k in per.index else None
            parts = []
            if r is not None and pd.notna(r.max_dose) and r.max_dose >= ps.CLEAN_BELOW:
                parts.append("data center load share of 0.5% or more in some year (a host: represented by stand-ins, not itself in the sample)")
            if r is not None and pd.notna(r.max_crypto_share) and r.max_crypto_share >= ps.CRYPTO_LIMIT:
                parts.append("crypto-mining load of 2% or more of 2009-2011 sales in some year (power_simulation.design: CRYPTO_LIMIT)")
            return "not comparison-eligible in power_simulation.design at 2%: " + ("; ".join(parts) or "other (no base, or held)")
        if k not in s02["listed"]:
            return f"comparison-eligible but off the access list: {excl_reason.get(k, 'reason not found')}"
        if k not in s02["gated"]:
            return "load-unknown gate"
        return None

    zero_dose = [k for k in assigned_keys if not (k in per.index and per.loc[k, "max_dose"] > 0)]
    left_zero_all = [k for k in zero_dose if k not in set(sim_sample)]
    left_zero = [k for k in left_zero_all if k not in s02["clean"]]          # the ten of the plan's paragraph
    left_zero_list = [k for k in left_zero_all if k in s02["clean"]]         # comparison-eligible, left out by the access list
    left_all = [k for k in assigned_keys if k not in set(sim_sample)]
    why_all = {}
    for k in left_all:
        w = sim_why(k)
        why_all[w] = why_all.get(w, 0) + 1
    ten = []
    for k in left_zero:
        r = per.loc[k] if k in per.index else None
        ten.append({"utility": uid(k), "state": k[1], "name": names.get(k), "why_the_simulation_left_it_out": sim_why(k),
                    "on_the_access_list_universe": k in sim[0.02]["clean"] or k in sim[0.05]["clean"],
                    "in_simulation_access_excluded_csv": excl_reason.get(k),
                    "data_center_dose_max": None if r is None else float(r.max_dose),
                    "crypto_mw_max": None if r is None else float(r.max_crypto_mw),
                    "crypto_share_of_base_max": None if r is None else round(float(r.max_crypto_share), 6),
                    "dose_with_crypto_max": None if r is None else round(float(r.max_dose_with_crypto), 6),
                    "proposed_class": pc[uid(k)],
                    "excluded_by_a_rule_the_plan_writes_for_the_second_number": False})
    crypto_units = [k for k in frame.keys if k in per.index and pd.notna(per.loc[k, "max_crypto_share"]) and per.loc[k, "max_crypto_share"] >= ps.CRYPTO_LIMIT]
    return {
        "exclusions_as_built": exclusions, "counts": sample_counts,
        "simulation_long_difference_sample_from_quantities": {
            "how": ("power_simulation.main: design(q, dose, 0.02, history_settled(0.02)) -> restrict_to_access_list -> "
                    "unknown.gate(0.02) -> run_second_number: unknown.every, prices merged on those units, usable rows, "
                    "balanced over the six years, a region in each and customers in 2010. Reproduced here from quantities "
                    "and the access-list files without prices: the units of the second number's frame that pass design, the "
                    "list and the gate. Whether each has a price row in every usable year is not checked (no price file is "
                    "opened); the access list's N7 checked that each listed unit's outcome file exists"),
            "units": len(sim_sample),
            "units_of_the_second_number_sample_with_a_dose_as_assigned_not_in_it": len(left_all),
            "why_counts": why_all,
            "zero_dose_as_assigned_units_left_out": len(left_zero_all),
            "of_them_not_comparison_eligible_in_design": len(left_zero),
            "of_them_comparison_eligible_but_off_the_access_list": len(left_zero_list)},
        "the_units_with_no_data_center_dose_not_comparison_eligible_in_design": ten,
        "zero_dose_as_assigned_units_off_the_access_list": _listing(
            names, [uid(k) for k in left_zero_list],
            {uid(k): {"access_list_reason": excl_reason.get(k), "proposed_class": pc[uid(k)]} for k in left_zero_list}),
        "crypto_in_the_second_number_sample": {
            "units_in_the_frame_with_crypto_mining_load_2pct_or_more_of_base_in_any_year": len(crypto_units),
            "of_them_with_a_dose_as_assigned": sum(1 for k in crypto_units if k not in affected),
            "of_them_among_the_ten": sum(1 for k in crypto_units if k in set(left_zero)),
            "utilities": _listing(names, [uid(k) for k in crypto_units],
                                  {uid(k): {"crypto_share_of_base_max": round(float(per.loc[k, "max_crypto_share"]), 6),
                                            "data_center_dose_max": float(per.loc[k, "max_dose"]),
                                            "proposed_class": pc.get(uid(k))} for k in crypto_units}),
            "measure": "crypto_mw x 8.76 / base_retail_gwh, power_simulation.design's crypto_share, in utility_year_dose.parquet"},
    }


def main() -> int:
    """Writes nothing. The proposal's output is the kept record; the adopted classification is second_number.py's."""
    print(f"{PROPOSAL_RECORD.name} is kept unchanged as the record of what was proposed (D-104); nothing writes it. "
          "The adopted classification (D-105) is written by: python3 -I pipeline/analysis/second_number.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
