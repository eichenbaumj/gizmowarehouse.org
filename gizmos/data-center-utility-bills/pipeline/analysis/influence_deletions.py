#!/usr/bin/env python3
"""Three influence deletions of "Reported checks", Influence: each market region left out, each state left out, and
Virginia left out, on the headline set. Reads NO outcome: the outcome frame is an argument of `estimate_deletion` and
`run_deletions`.

The specification is D-106 section 9, R7, which Joe adopted on 2026-11-19 (D-107). Its words for these runs:

    "Influence by deletion of a market region, a state and Virginia, on the headline set. A region left out: every host
    whose reference-year region it is leaves with its matches. A state left out: its hosts leave, and its comparison
    utilities leave every remaining host's matches, with no rematching. After a deletion, rule 7's treatment: a host left
    with fewer than five matches is named as inadequately supported and stays; a host with none or with no weight is not
    estimable and named; the rank test comes before any fit. Virginia is that state deletion and is reported though it
    removes nothing, and the write-up says no host and no matched unit of the headline design is in Virginia and does not
    present an unchanged estimate as a check passed."

And the plan's Influence bullet: "Reported as the range of estimates across deletions and the deletion that moves it
most. Dropping observations changes precision, so a deletion that makes the range span zero is reported, not treated as
a reversal."

What is built
-------------
- A region left out (`delete_region`): every host whose reference-year region (the `region` field design.build writes
  for each host, its region in the cohort's reference year) is that region leaves the design with its own stack. The
  other hosts keep their matches untouched and in order.
- A state left out (`delete_state`): every host whose unit is in that state leaves with its own stack, and every copy of
  every comparison unit in that state leaves every remaining host's matches (influence.leave_out). Nothing is rematched.
- Virginia (`delete_state(d, "VA")`, run by `run_deletions` always, whether or not Virginia is present): its record
  says, from the design and not by assumption, whether any host or matched comparison utility is in Virginia. Where
  none is, the label says the deletion removes nothing and that its estimate, which is the design's own, is not
  presented as a check passed (VIRGINIA_REMOVES_NOTHING).
- After every deletion, rule 7's treatment (`after_deletion`): hosts left with one to four matches are named as
  inadequately supported and STAY; hosts left with none, and hosts with zero headline weight, are named as not
  estimable (influence.estimable, from the regressors alone); the rank test is made before any fit, and a design that
  fails it is not fitted.
- Every deleted design keeps the rules it was built under (prefreeze_summaries.carry_design_attributes); the hosts that
  leave are added to its `dropped` list with the reason and leave its unresolved-ownership list (as side_runs.remove_units
  does). It is estimated with outcome_analysis.estimate and validated_design=False, so its result carries the plan's
  words for a design on which no validation was made (outcome_analysis.NOT_VALIDATED).
- `summarise` gives the range of estimates across the deletions, the deletion that moves the estimate most from the full
  design's, and the deletions whose 90% range includes zero where the full design's does not, reported and not treated
  as a reversal.

Adopted by Joe on 2026-11-19 (D-111), the definitions of R7's terms (not settled by R7 or the plan before then)
--------------------------------------------------------------------------------------------------------------
- "One run per region and one per state present in the design": a region is present when it is the reference-year
  region of a host in the design (a region deletion removes only hosts, so a region with no host would remove nothing);
  a state is present when a host or a matched comparison utility of the design is in it. Virginia is run in addition,
  whether present or not.
- A unit is a utility in one state, so a state deletion removes units in that state; the same utility's units in other
  states stay.
- The range across deletions and the deletion that moves it most are taken over the deletions that remove something
  and computed a point estimate. A deletion that removes nothing (Virginia, where nothing is in it) is reported beside
  them and is not in the range, since its estimate is the full design's estimate and not a deletion's.
- "Moves it most" is the largest absolute difference in log points between a deletion's estimate and the full design's.
  An exact tie for the largest (equal floating-point values) is not broken: every tied deletion is named and none is
  picked. No tolerance for a near tie is set.

The agent's readings (not settled by R7 or the plan)
----------------------------------------------------
- If Virginia is present its per-state run and the Virginia run are the same deletion and the Virginia run is listed
  once, as Virginia.
- A deletion that leaves no host in the design is not estimable and says so in words.
- The full design's estimate is the caller's to claim validation for: `run_deletions` passes `full_design_validation`
  straight to outcome_analysis.estimate (False, or a ValidationClaim the kernel checks). Every deletion is False.

What is here
------------
regions_present(d), states_present(d)   the deletions to run
delete_region(d, region), delete_state(d, state)
                                        (the deleted design, what left)
after_deletion(e, fuel_control, names)  rule 7's treatment on a deleted design, regressors only
estimate_deletion(d, kind, value, frame, column, names=None)
                                        the deletion, the rank test before any fit, then the kernel
run_deletions(d, frame, column, *, full_design_validation, names=None)
                                        every region and state present, and Virginia, with `summarise`
quantity_summary(d, names=None)         every deletion's quantity-side record (no outcome)
main()                                  the quantity-side summary on the headline design at 2%, written to
                                        data/frozen/influence_deletions_design.json (provisional). NOT to be run until the
                                        session says the ownership repair has been assessed.

Run:  python3 -I pipeline/analysis/influence_deletions.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import prefreeze_summaries as pf  # noqa: E402

KEY = ps.KEY
INADEQUATE = influence.INADEQUATE           # rule 7: a host left with fewer than five matches has inadequate support
VIRGINIA = "VA"
REGION, STATE = "region", "state"
OUT = ROOT / "data" / "frozen" / "influence_deletions_design.json"

NOT_VALIDATED = oa.NOT_VALIDATED            # "under the procedure validated on the headline set; no validation was made on this design"
WHY_REGION = "left out by the influence check: its reference-year market region {r} is left out (R7, adopted by Joe, D-107)"
WHY_STATE = "left out by the influence check: its state {s} is left out (R7, adopted by Joe, D-107)"
INADEQUATE_WORDS = "fewer than five matches left: inadequately supported, and stays in the estimate (rule 7)"
NONE_WORDS = "no match left: not estimable (rule 7)"
ZERO_WORDS = "zero headline weight: not estimable (rule 7)"
VIRGINIA_REMOVES_NOTHING = ("Virginia left out removes nothing: no host and no matched comparison utility of this design "
                            "is in Virginia (checked on the design). Its estimate is the design's own estimate and is not "
                            "presented as a check passed.")
VIRGINIA_REMOVES = ("Virginia left out removes {h} host(s) and {m} matched comparison utility(ies) of this design (checked "
                    "on the design).")
SPANS_ZERO = "the 90% range includes zero where the full design's does not: reported, not treated as a reversal"


def _label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def _norm(k) -> tuple:
    return (int(k[0]), str(k[1]))


def _name(names, label: str):
    if not names:
        return None
    u, s = label.split(":")
    v = names.get((int(u), s)) if hasattr(names, "get") else None
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)


def run_label(kind: str, value: str) -> str:
    """The label every deletion's result carries: which deletion, and the plan's words for a design on which no
    validation was made."""
    return f"influence deletion: {kind} {value} left out; {NOT_VALIDATED}"


# ---- what is present ------------------------------------------------------------------------------------------------

def regions_present(d) -> list:
    """The reference-year market regions of the design's hosts, sorted ("present" as Joe adopted it, 2026-11-19, D-111)."""
    if not len(d.hosts):
        return []
    return sorted({str(r) for r in d.hosts.region})


def states_present(d) -> list:
    """The states of the design's hosts and of their matched comparison utilities, sorted."""
    if not len(d.hosts):
        return []
    out = {str(k[1]) for k in d.hosts.key}
    for mk in d.hosts.match_keys:
        out |= {str(m[1]) for m in mk}
    return sorted(out)


# ---- the deletions --------------------------------------------------------------------------------------------------

def _drop_hosts(d, gone: dict):
    """`d` without the hosts in `gone` ({host label: why}), each named in `dropped`, and out of the unresolved-ownership
    list; every other host and its matches as in `d`. The rules and lists `d` carries are kept."""
    keep = np.array([_label(k) not in gone for k in d.hosts.key], dtype=bool) if len(d.hosts) else np.zeros(0, bool)
    e = pf.carry_design_attributes(d, influence._without(d, keep)) if len(d.hosts) else pf.carry_design_attributes(
        d, dsg.Design(d.hosts.copy(), d.windows, d.is_comp, list(d.dropped), dict(d.region_names), dict(d.unit_code),
                      dict(d.state_code), d.gas))
    e.dropped = list(d.dropped) + [{"utility": _label(k), "cohort": int(g), "why": gone[_label(k)]}
                                   for k, g in zip(d.hosts.key, d.hosts.cohort) if _label(k) in gone] if len(d.hosts) else list(d.dropped)
    if getattr(e, "unresolved_ownership", None):
        e.unresolved_ownership = [x for x in e.unresolved_ownership if x.get("utility") not in gone]
    return e


def delete_region(d, region: str) -> tuple:
    """(the design without every host whose reference-year region is `region`, what left). Nothing is rematched and no
    comparison utility is removed from a remaining host's matches."""
    gone = {_label(k): WHY_REGION.format(r=region) for k, r in zip(d.hosts.key, d.hosts.region) if str(r) == str(region)} \
        if len(d.hosts) else {}
    e = _drop_hosts(d, gone)
    left = {"kind": REGION, "value": str(region), "hosts_leaving": sorted(gone),
            "matched_units_leaving_with_those_hosts": sorted({_label(m) for k, mk in zip(d.hosts.key, d.hosts.match_keys)
                                                              if _label(k) in gone for m in mk}) if len(d.hosts) else [],
            "matched_units_leaving_remaining_hosts": []}
    left["removes_nothing"] = not gone
    return e, left


def delete_state(d, state: str) -> tuple:
    """(the design without the hosts in `state` and without every copy of every comparison unit in `state` in every
    remaining host's matches, what left). Nothing is rematched; each remaining host keeps its other matches in order."""
    state = str(state)
    gone = {_label(k): WHY_STATE.format(s=state) for k in d.hosts.key if str(k[1]) == state} if len(d.hosts) else {}
    e1 = _drop_hosts(d, gone)
    units = {_norm(m) for mk in e1.hosts.match_keys for m in mk if str(m[1]) == state} if len(e1.hosts) else set()
    e = pf.carry_design_attributes(e1, influence.leave_out(e1, units)) if units else e1
    e.dropped = list(e1.dropped)
    all_units_in_state = {_label(m) for mk in d.hosts.match_keys for m in mk if str(m[1]) == state} if len(d.hosts) else set()
    left = {"kind": STATE, "value": state, "hosts_leaving": sorted(gone),
            "matched_units_leaving_with_those_hosts": sorted({_label(m) for k, mk in zip(d.hosts.key, d.hosts.match_keys)
                                                              if _label(k) in gone for m in mk}) if len(d.hosts) else [],
            "matched_units_leaving_remaining_hosts": sorted(_label(u) for u in units),
            "matched_units_in_the_state": sorted(all_units_in_state)}
    left["removes_nothing"] = not gone and not all_units_in_state
    return e, left


def after_deletion(e, fuel_control: str, names=None, before=None) -> dict:
    """Rule 7's treatment on the deleted design, from the regressors alone (no outcome): matches left per host, hosts
    with one to four (named, inadequately supported, kept), hosts with none and hosts with zero weight (named, not
    estimable), and the rank test made before any fit (influence.estimable). `before` ({host label: matches}) adds each
    host's count before the deletion."""
    left = {_label(h.key): len(h.matches) for h in e.hosts.itertuples()} if len(e.hosts) else {}
    out = {"hosts_remaining": len(left),
           "matches_left_by_host": [{"host": h, "name": _name(names, h), "matches_left": n,
                                     **({"matches_before": before.get(h)} if before is not None else {})}
                                    for h, n in left.items()],
           "hosts_with_fewer_than_five_matches_inadequately_supported_kept":
               [{"host": h, "name": _name(names, h), "matches_left": n, "why": INADEQUATE_WORDS}
                for h, n in left.items() if 0 < n < INADEQUATE]}
    if not left:
        out.update(hosts_with_no_matches_not_estimable=[], hosts_with_zero_weight_not_estimable=[],
                   rank_test_before_any_fit={"estimable": False, "why": "no host remains in the design"})
        return out
    r = influence.estimable(e, fuel_control)
    out["hosts_with_no_matches_not_estimable"] = [{"host": h, "name": _name(names, h), "why": NONE_WORDS}
                                                  for h in r["hosts_with_no_matches"]]
    out["hosts_with_zero_weight_not_estimable"] = [{"host": h, "name": _name(names, h), "why": ZERO_WORDS}
                                                   for h in r["hosts_with_zero_weight"]]
    out["zero_weight_checked"] = ("influence.zero_weight_hosts, through influence.estimable" if r["estimable"] else
                                  "not computed: the design fails the rank test, so no weight is computed")
    out["rank_test_before_any_fit"] = {"estimable": bool(r["estimable"]),
                                       "smallest_singular_value_ratio": float(r["smallest_singular_value_ratio"])}
    return out


def _fuel_control(d) -> str:
    rules = getattr(d, "rules", None)
    return rules.fuel_control if rules is not None else oa._fuel_control(d, None)


def _delete(d, kind: str, value: str) -> tuple:
    if kind == REGION:
        return delete_region(d, value)
    if kind == STATE:
        return delete_state(d, value)
    raise ValueError(f"unknown deletion kind {kind!r}; {REGION!r} or {STATE!r}")


def _virginia_line(left: dict) -> str:
    if left["removes_nothing"]:
        return VIRGINIA_REMOVES_NOTHING
    return VIRGINIA_REMOVES.format(h=len(left["hosts_leaving"]), m=len(left["matched_units_in_the_state"]))


def estimate_deletion(d, kind: str, value: str, frame: pd.DataFrame, column: str, names=None) -> dict:
    """One deletion on the caller's outcome: the deletion; rule 7's treatment and the rank test before any fit; then
    outcome_analysis.estimate on the deleted design for `column` of `frame`, aligned on THAT design, validated_design=False.
    Returns {"kind", "value", "label", "what_left", "after_deletion", "result" (the kernel's or None), "estimated",
    "failure_in_words"} and, for Virginia, "virginia". Nothing is fitted when no host remains or the rank test fails."""
    e, left = _delete(d, kind, value)
    before = {_label(h.key): len(h.matches) for h in d.hosts.itertuples()} if len(d.hosts) else {}
    a = after_deletion(e, _fuel_control(d), names, before)
    out = {"kind": kind, "value": str(value), "label": run_label(kind, value), "what_left": left, "after_deletion": a,
           "result": None, "estimated": False, "failure_in_words": None}
    if kind == STATE and str(value) == VIRGINIA:
        out["virginia"] = _virginia_line(left)
    if not a["hosts_remaining"]:
        out["failure_in_words"] = f"not estimable: no host remains once {kind} {value} is left out"
        return out
    if not a["rank_test_before_any_fit"]["estimable"]:
        out["failure_in_words"] = ("not estimated: the deleted design fails the rank test made before any fit (smallest "
                                   f"singular value ratio {a['rank_test_before_any_fit']['smallest_singular_value_ratio']:.3g})")
        return out
    k = oa.estimate(e, oa.outcome_vector(e, frame, column), validated_design=False)
    out["result"] = k
    out["estimated"] = bool(np.isfinite(k["headline"]["log_points"]))
    if not out["estimated"]:
        f = k.get("numerical_failure") or {}
        out["failure_in_words"] = f"the kernel computed no point estimate: {f.get('in_words', 'cause not recorded')}"
    return out


def deletion_list(d) -> list:
    """[(kind, value)] in order: every region present, every state present except Virginia, then Virginia."""
    return ([(REGION, r) for r in regions_present(d)] + [(STATE, s) for s in states_present(d) if s != VIRGINIA]
            + [(STATE, VIRGINIA)])


def _range_includes_zero(k: dict) -> bool | None:
    r = (k or {}).get("headline", {}).get("range_90_log_points") if k else None
    if not r:
        return None
    return bool(r[0] <= 0.0 <= r[1])


def summarise(full: dict, deletions: list) -> dict:
    """The range of estimates across the deletions, the deletion that moves the estimate most, and the ranges that span
    zero, from the kernel results. `full` is the full design's kernel result; `deletions` are estimate_deletion records.
    See the module docstring for which deletions enter the range (adopted by Joe on 2026-11-19, D-111)."""
    f = (full or {}).get("headline", {}).get("log_points", float("nan"))
    tag = lambda x: f"{x['kind']} {x['value']}"  # noqa: E731
    in_range = [x for x in deletions if x["estimated"] and not x["what_left"]["removes_nothing"]]
    out = {"full_design_estimate_log_points": f, "full_design_range_includes_zero": _range_includes_zero(full),
           "deletions_run": len(deletions),
           "deletions_in_the_range": [tag(x) for x in in_range],
           "deletions_not_estimated": [{"deletion": tag(x), "failure_in_words": x["failure_in_words"]}
                                       for x in deletions if not x["estimated"]],
           "deletions_that_remove_nothing_reported_beside_the_range": [tag(x) for x in deletions
                                                                       if x["what_left"]["removes_nothing"]],
           "range_of_estimates_log_points": None, "moves_it_most": None, "exact_tie_for_moves_it_most": None,
           "ranges_that_span_zero_where_the_full_designs_does_not": []}
    if in_range:
        v = [x["result"]["headline"]["log_points"] for x in in_range]
        out["range_of_estimates_log_points"] = [float(min(v)), float(max(v))]
        out["range_of_estimates_percent"] = [oa._pct(float(min(v))), oa._pct(float(max(v)))]
        if np.isfinite(f):
            moves = [abs(x - f) for x in v]
            top = max(moves)
            tied = [tag(x) for x, m in zip(in_range, moves) if m == top]
            if len(tied) > 1:
                out["exact_tie_for_moves_it_most"] = {"deletions": tied, "moves_by_log_points": top,
                                                      "words": "an exact tie for the largest move; none is picked"}
            else:
                i = moves.index(top)
                out["moves_it_most"] = {"deletion": tied[0], "estimate_log_points": float(v[i]),
                                        "moves_by_log_points": float(v[i] - f)}
        else:
            out["moves_it_most_not_computed"] = "the full design's estimate did not compute, so no move is measured"
    full_zero = out["full_design_range_includes_zero"]
    for x in deletions:
        z = _range_includes_zero(x["result"])
        if z and full_zero is False:
            out["ranges_that_span_zero_where_the_full_designs_does_not"].append({"deletion": tag(x), "words": SPANS_ZERO})
    return out


def run_deletions(d, frame: pd.DataFrame, column: str, *, full_design_validation, names=None) -> dict:
    """Every region and state present, and Virginia, on the caller's outcome, with the summary. The full design's estimate
    is computed beside them with `full_design_validation` (False, or a ValidationClaim the kernel checks; no default).
    Every deletion is estimated with validated_design=False and labelled so."""
    full = oa.estimate(d, oa.outcome_vector(d, frame, column), validated_design=full_design_validation)
    runs = [estimate_deletion(d, kind, value, frame, column, names) for kind, value in deletion_list(d)]
    va = next(x for x in runs if x["kind"] == STATE and x["value"] == VIRGINIA)
    return {"what_this_is": ("Influence by deletion of each market region, each state and Virginia (R7, adopted by Joe on "
                             "2026-11-19, D-107). Each deleted design: " + NOT_VALIDATED + "."),
            "full_design": full, "deletions": runs, "summary": summarise(full, runs), "virginia": va["virginia"],
            "estimated": any(x["estimated"] for x in runs)}


# ---- quantity side ----------------------------------------------------------------------------------------------------

def quantity_summary(d, names=None) -> dict:
    """Every deletion's record from the design alone (no outcome): hosts leaving, matched units leaving, hosts under five
    matches, hosts not estimable and whether the rank test passes; and Virginia's line."""
    fc = _fuel_control(d)
    before = {_label(h.key): len(h.matches) for h in d.hosts.itertuples()} if len(d.hosts) else {}
    rows = []
    for kind, value in deletion_list(d):
        e, left = _delete(d, kind, value)
        a = after_deletion(e, fc, names, before)
        row = {"kind": kind, "value": value, "label": run_label(kind, value),
               "hosts_leaving": [{"host": h, "name": _name(names, h)} for h in left["hosts_leaving"]],
               "matched_units_leaving_with_those_hosts": left["matched_units_leaving_with_those_hosts"],
               "matched_units_leaving_remaining_hosts": left["matched_units_leaving_remaining_hosts"],
               "removes_nothing": left["removes_nothing"],
               "hosts_remaining": a["hosts_remaining"],
               "hosts_with_fewer_than_five_matches_inadequately_supported_kept":
                   a["hosts_with_fewer_than_five_matches_inadequately_supported_kept"],
               "hosts_with_no_matches_not_estimable": a["hosts_with_no_matches_not_estimable"],
               "hosts_with_zero_weight_not_estimable": a["hosts_with_zero_weight_not_estimable"],
               "rank_test_before_any_fit": a["rank_test_before_any_fit"]}
        if kind == STATE and value == VIRGINIA:
            row["virginia"] = _virginia_line(left)
        rows.append(row)
    va = next(r for r in rows if r["kind"] == STATE and r["value"] == VIRGINIA)
    return {"hosts_in_the_design": [{"host": h, "name": _name(names, h), "matches": n} for h, n in before.items()],
            "regions_present": regions_present(d), "states_present": states_present(d), "deletions": rows,
            "virginia": va["virginia"]}


def main() -> int:
    """The headline set at 2% under the headline rules, built as design.main and influence_load.main build it; every
    deletion's quantity-side record. No price or outcome is read and nothing is fitted. Writes OUT."""
    from pipeline.analysis import usable_flag
    rules = ps.HEADLINE_RULES
    q, dose, regions, fuel, dd = dsg.load()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    names = q.groupby(KEY).utility_name.last()
    names = {(int(k[0]), k[1]): v for k, v in names.items()}
    treated, clean = dsg.split(0.02, ps.HEADLINE_SET, q, dose)
    d = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                             ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
    s = quantity_summary(d, names)
    fp = dsg.run_fingerprint(d, rules=rules, usable=usable,
                             assumptions={"kind": "influence_deletions", "set": ps.HEADLINE_SET, "threshold": 0.02},
                             settings={"inadequate": INADEQUATE, "virginia": VIRGINIA}, seeds=None)
    doc = {"what_this_is": ("The three influence deletions of Reported checks, Influence (each market region, each state, "
                            "Virginia; R7, adopted by Joe on 2026-11-19, D-107) on the headline set at 2% under the headline "
                            "rules, from the design alone: for each deletion the hosts leaving, the matched comparison "
                            "utilities leaving, the hosts left with fewer than five matches (kept, inadequately supported), "
                            "the hosts not estimable, and the rank test made before any fit on the regressors alone. "
                            "Quantities only: load, sales, customers, ownership and the usable flag; no price, revenue, "
                            "bill or outcome is read and nothing is fitted. Each deleted design is one on which no "
                            "validation was made. PROVISIONAL: the design stands as of 2026-11-18 under the ownership code "
                            "in the file when this was run, and the plan is a DRAFT, not frozen."),
           "built_by": "pipeline/analysis/influence_deletions.py (main)",
           "set": ps.HEADLINE_SET, "threshold": 0.02, "rules": rules.label,
           "readings": ["a region is present when it is the reference-year region of a host; a state is present when a "
                        "host or a matched comparison utility is in it; Virginia is run in addition (adopted by Joe on 2026-11-19, "
                        "D-111)",
                        "a unit is a utility in one state, so a state deletion removes units in that state (adopted by Joe "
                        "on 2026-11-19, D-111)"],
           **s, "design_inputs_sha256": fp["of"]["design_inputs"], "fingerprint": fp}
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    for r in s["deletions"]:
        print(f"{r['kind']:<6} {r['value']:<12} hosts leaving {len(r['hosts_leaving'])}  units leaving remaining hosts "
              f"{len(r['matched_units_leaving_remaining_hosts'])}  under five "
              f"{len(r['hosts_with_fewer_than_five_matches_inadequately_supported_kept'])}  rank test "
              f"{r['rank_test_before_any_fit'].get('estimable')}")
    print(s["virginia"])
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
