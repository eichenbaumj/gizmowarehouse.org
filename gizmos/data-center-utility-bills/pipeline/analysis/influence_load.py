#!/usr/bin/env python3
"""The five-highest-load deletion of "Reported checks", Influence: the estimate with the five hosts of the highest data
center load dropped. Reads NO outcome: the outcome frame is an argument of `estimate_without_the_five`.

Joe's ruling of 2026-11-19 (D-105), his words: "For the five-highest-load deletion, use absolute data-center load in
event year 3, not load share."

What is built, as the session's brief for session 20 states it
--------------------------------------------------------------
- The load is the data center load in GWh (`dc_gwh` in data/interim/utility_year_dose.parquet), read for each host in
  ITS OWN event year 3: its first-crossing year (its cohort) plus 3. The frame is passed in; no function here opens it.
- The five hosts with the largest load are dropped together with their sub-experiments: each host's own stack, its rows
  and its matches' rows in that stack. Every remaining host keeps its matches untouched; nothing is rematched.
- Ties are stated and not broken silently. The whole ranking is reported with each host's load and the gap between
  adjacent ranks. An exact tie that straddles the line between rank 5 and rank 6 is not resolved: the run does not
  estimate and says so, naming the tied hosts. No tolerance for a "near tie" is set; the gaps are reported and nothing is
  decided from them.
- A host with no load value in its event year 3 (no row, or a value that is not finite) is a failure in words, never a
  silent zero.
- With five or fewer hosts in the estimate nothing remains: not estimable, in words.
- The deleted design goes through run_outcomes.carry_design_attributes (prefreeze_summaries.carry_design_attributes) so it
  keeps the rules it was built under; the dropped hosts are added to its `dropped` list with the reason. The rank test
  (influence.estimable, on the regressors after the fixed effects are removed, no outcome) is made before any fit; a
  design that fails it is not fitted. The fit is outcome_analysis.estimate with validated_design=False, so the result
  carries the plan's words for a design on which no validation was made.
The other three influence deletions (a market region, a state, Virginia) are not settled and are not built here.

The agent's readings (not stated by Joe's words or the plan)
------------------------------------------------------------
- "The hosts in the estimate" are the design's hosts that are stacked, those with at least one matched comparison
  utility (outcome_analysis.stackable). A host with no match carries nothing in the estimate; it is named, it is not
  ranked, and it stays in the deleted design as it was (the kernel names it again).
- Ties elsewhere in the ranking (both tied hosts dropped, or both kept) change no one's place in the deletion; they are
  listed and the run proceeds. Hosts with exactly equal load are listed in the ranking in the order of their labels, for
  display only.
- "An exact tie" is equality of the two floating-point values as read from the frame.

What is here
------------
ranking(d, load, names=None)          the ranking of the hosts in the estimate by load in their own event year 3, the
                                      gaps, the ties, the five to drop and the hosts kept, or a failure in words
drop_the_five(d, load, names=None)    (the deleted design or None, the ranking record)
estimate_without_the_five(d, load, frame, column, names=None)
                                      the rank test before any fit, then outcome_analysis.estimate on the deleted design
                                      for the caller's outcome column, validated_design=False
main()                                the ranking on the headline design at 2% as it stands, quantities only, written to
                                      data/frozen/influence_five_highest_load.json (provisional)

Run:  python3 -I pipeline/analysis/influence_load.py
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
HOW_MANY = 5                        # the plan's "five highest-load utilities"
EVENT_YEAR = 3                      # Joe, D-105: load in event year 3
LOAD_COLUMN = "dc_gwh"              # data/interim/utility_year_dose.parquet: data center load in GWh
OUT = ROOT / "data" / "frozen" / "influence_five_highest_load.json"

WHY_DROPPED = (f"dropped by the influence check: one of the {HOW_MANY} hosts with the highest data center load (GWh) in "
               f"its own event year {EVENT_YEAR} (Joe, 2026-11-19, D-105)")
TIE_AT_THE_LINE = "exact tie at the line between rank {k} and rank {k1}"


class LoadFrameRefused(ValueError):
    """The load frame cannot be read as one value per unit-year. Raised in words; nothing is filled."""


def _label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def _load_lookup(load: pd.DataFrame) -> dict:
    need = KEY + ["year", LOAD_COLUMN]
    miss = [c for c in need if c not in load.columns]
    if miss:
        raise LoadFrameRefused(f"the load frame has no column {miss} (it is utility_year_dose: utility_id_eia, state, year, "
                               f"{LOAD_COLUMN})")
    f = load[need]
    keys = list(zip(f.utility_id_eia.astype(int), f.state.astype(str), f.year.astype(int)))
    if len(set(keys)) != len(keys):
        seen, dup = set(), None
        for k in keys:
            if k in seen:
                dup = k
                break
            seen.add(k)
        raise LoadFrameRefused(f"the load frame repeats a unit-year, for example {dup[0]}:{dup[1]} in {dup[2]}; stopping")
    return dict(zip(keys, f[LOAD_COLUMN].to_numpy(dtype=float)))


def ranking(d, load: pd.DataFrame, names=None) -> dict:
    """The hosts in the estimate ranked by data center load (GWh) in their own event year 3, largest first.

    Returns a record:
      hosts_in_the_estimate            how many hosts are ranked (stacked hosts: at least one match)
      hosts_with_no_matches_not_ranked named
      ranking                          [{rank, host, name, cohort, event_year_3_calendar_year, dc_gwh,
                                         gap_to_the_next_rank_gwh (None for the last)}]
      exact_ties                       [{hosts, dc_gwh, ranks}] every group of hosts with exactly equal load
      tie_at_the_line                  None, or the tied group that straddles rank HOW_MANY and HOW_MANY + 1
      gap_at_the_line_gwh              load at rank HOW_MANY less load at rank HOW_MANY + 1 (None if not computed)
      to_drop, kept                    host labels (None when the run cannot proceed)
      failure_in_words                 None, or why the deletion cannot be formed (missing load, five or fewer hosts, the
                                       tie at the line)
    """
    lookup = _load_lookup(load)
    nm = (lambda k: None) if names is None else (lambda k: names.get(k))
    hosts = list(d.hosts.itertuples()) if len(d.hosts) else []
    stacked = [h for h in hosts if len(h.matches) > 0]
    no_match = [_label(h.key) for h in hosts if len(h.matches) == 0]
    out = {"load_column": LOAD_COLUMN, "event_year": EVENT_YEAR, "how_many_dropped": HOW_MANY,
           "hosts_in_the_estimate": len(stacked), "hosts_with_no_matches_not_ranked": no_match,
           "ranking": None, "exact_ties": None, "tie_at_the_line": None, "gap_at_the_line_gwh": None,
           "to_drop": None, "kept": None, "failure_in_words": None}
    recs, missing = [], []
    for h in stacked:
        k = (int(h.key[0]), str(h.key[1]))
        year = int(h.cohort) + EVENT_YEAR
        v = lookup.get((k[0], k[1], year))
        if v is None or not np.isfinite(v):
            missing.append(f"{_label(k)} ({nm(k) or 'no name'}), cohort {int(h.cohort)}: "
                           f"{'no row' if v is None else 'a value that is not finite'} for {year}")
            continue
        recs.append({"host": _label(k), "name": nm(k), "cohort": int(h.cohort), "event_year_3_calendar_year": year,
                     "dc_gwh": float(v)})
    if missing:
        out["failure_in_words"] = ("not estimable: a host in the estimate has no data center load in its event year 3, and "
                                   "a missing load is not read as zero: " + "; ".join(missing))
        return out
    recs.sort(key=lambda r: (-r["dc_gwh"], r["host"]))
    for i, r in enumerate(recs):
        r["rank"] = i + 1
        r["gap_to_the_next_rank_gwh"] = (r["dc_gwh"] - recs[i + 1]["dc_gwh"]) if i + 1 < len(recs) else None
    out["ranking"] = [{k: r[k] for k in ("rank", "host", "name", "cohort", "event_year_3_calendar_year", "dc_gwh",
                                         "gap_to_the_next_rank_gwh")} for r in recs]
    groups: dict = {}
    for r in recs:
        groups.setdefault(r["dc_gwh"], []).append(r)
    out["exact_ties"] = [{"hosts": [r["host"] for r in g], "dc_gwh": v, "ranks": [r["rank"] for r in g]}
                         for v, g in groups.items() if len(g) > 1]
    if len(recs) <= HOW_MANY:
        out["failure_in_words"] = (f"not estimable: {len(recs)} hosts are in the estimate, so dropping the {HOW_MANY} with "
                                   "the highest load leaves no host")
        return out
    out["gap_at_the_line_gwh"] = recs[HOW_MANY - 1]["dc_gwh"] - recs[HOW_MANY]["dc_gwh"]
    line = recs[HOW_MANY - 1]["dc_gwh"]
    if line == recs[HOW_MANY]["dc_gwh"]:
        tied = groups[line]
        out["tie_at_the_line"] = {"hosts": [r["host"] for r in tied], "names": [r["name"] for r in tied], "dc_gwh": line,
                                  "ranks": [r["rank"] for r in tied]}
        out["failure_in_words"] = (f"not estimated: {TIE_AT_THE_LINE.format(k=HOW_MANY, k1=HOW_MANY + 1)}. "
                                   + ", ".join(f"{r['host']} ({r['name'] or 'no name'})" for r in tied)
                                   + f" each carry exactly {line!r} GWh in their event year 3, and which of them is among "
                                   f"the {HOW_MANY} dropped is not decided by the code")
        return out
    out["to_drop"] = [r["host"] for r in recs[:HOW_MANY]]
    out["kept"] = [r["host"] for r in recs[HOW_MANY:]]
    return out


def drop_the_five(d, load: pd.DataFrame, names=None) -> tuple:
    """(the design without the five hosts of the highest load and their sub-experiments, the ranking record), or (None,
    the record) when ranking() gives a failure. The deleted design keeps the rules and lists `d` was built under
    (carry_design_attributes; its support table is None, since it described the design before the deletion) and names
    each dropped host in `dropped` with WHY_DROPPED. Every other host, its matches and their order are as in `d`."""
    r = ranking(d, load, names)
    if r["failure_in_words"]:
        return None, r
    gone = set(r["to_drop"])
    keep = np.array([_label(k) not in gone for k in d.hosts.key])
    e = pf.carry_design_attributes(d, influence._without(d, keep))
    e.dropped = list(e.dropped) + [{"utility": h.get("host"), "cohort": h.get("cohort"), "why": WHY_DROPPED}
                                   for h in r["ranking"] if h["host"] in gone]
    return e, r


def _fuel_control(d) -> str:
    rules = getattr(d, "rules", None)
    return rules.fuel_control if rules is not None else oa._fuel_control(d, None)


def estimate_without_the_five(d, load: pd.DataFrame, frame: pd.DataFrame, column: str, names=None) -> dict:
    """The deletion on the caller's outcome. The ranking first; then the rank test on the deleted design before any fit
    (influence.estimable, regressors only); then outcome_analysis.estimate on the deleted design, the outcome aligned by
    outcome_analysis.outcome_vector on THAT design, validated_design=False. Returns {"estimated", "ranking",
    "rank_test_before_any_fit", "result" (the kernel's, or None), "failure_in_words"}. Nothing is fitted when the
    ranking fails or the rank test fails; each says why in words."""
    e, r = drop_the_five(d, load, names)
    out = {"ranking": r, "rank_test_before_any_fit": None, "result": None, "estimated": False,
           "failure_in_words": r["failure_in_words"]}
    if e is None:
        return out
    fc = _fuel_control(e)
    test = influence.estimable(e, fc)
    out["rank_test_before_any_fit"] = {k: v for k, v in test.items()}
    if not test["estimable"]:
        out["failure_in_words"] = ("not estimated: the design without the five fails the rank test made before any fit "
                                   f"(smallest singular value ratio {test['smallest_singular_value_ratio']:.3g}; hosts with no "
                                   f"matches {test['hosts_with_no_matches']})")
        return out
    k = oa.estimate(e, oa.outcome_vector(e, frame, column), validated_design=False)
    out["result"] = k
    out["estimated"] = bool(np.isfinite(k["headline"]["log_points"]))
    if not out["estimated"]:
        f = k.get("numerical_failure") or {}
        out["failure_in_words"] = f"the kernel computed no point estimate: {f.get('in_words', 'cause not recorded')}"
    return out


# ---- main: the ranking on the design as it stands, quantities only ----------------------------------------------------

def main() -> int:
    """The headline set at 2% under the headline rules, built as design.main and design_weights.main build it; the ranking
    from utility_year_dose (dc_gwh); the rank test of the design without the five, regressors only. No price or outcome is
    read and nothing is fitted."""
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
    e, r = drop_the_five(d, dose, names)
    rank_test = None
    if e is not None:
        t = influence.estimable(e, rules.fuel_control)
        rank_test = {"estimable": bool(t["estimable"]), "smallest_singular_value_ratio": t["smallest_singular_value_ratio"],
                     "hosts_with_no_matches": t["hosts_with_no_matches"], "hosts_with_zero_weight": t["hosts_with_zero_weight"]}
    fp = dsg.run_fingerprint(d, rules=rules, usable=usable,
                             assumptions={"kind": "influence_five_highest_load", "set": ps.HEADLINE_SET, "threshold": 0.02},
                             settings={"how_many": HOW_MANY, "event_year": EVENT_YEAR, "load_column": LOAD_COLUMN}, seeds=None)
    doc = {"what_this_is": ("The ranking behind the five-highest-load deletion (Reported checks, Influence) on the headline "
                            "set at 2% under the headline rules: each host's data center load in GWh in its own event year 3 "
                            "(first-crossing year plus 3), largest first, with the gap between adjacent ranks, the five to "
                            "drop and the hosts kept, and the rank test of the design without the five, made on the "
                            "regressors alone. Joe's ruling of 2026-11-19 (D-105): absolute data-center load in event year 3, "
                            "not load share. Quantities only: no price, revenue, bill or outcome is read and nothing is "
                            "fitted. PROVISIONAL: the design stands as of 2026-11-18 and the plan is a DRAFT, not frozen."),
           "built_by": "pipeline/analysis/influence_load.py (main)",
           "load_source": f"data/interim/utility_year_dose.parquet, field {LOAD_COLUMN}",
           "set": ps.HEADLINE_SET, "threshold": 0.02, "rules": rules.label,
           "readings": ["the hosts in the estimate are the stacked hosts (at least one matched comparison utility); the "
                        "agent's reading",
                        "no tolerance is set for a near tie; only an exact tie at the line between rank 5 and rank 6 stops "
                        "the run, and the gaps are reported"],
           "ranking": r, "rank_test_of_the_design_without_the_five": rank_test,
           "design_inputs_sha256": fp["of"]["design_inputs"], "fingerprint": fp}
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    for x in r["ranking"] or []:
        gap = x["gap_to_the_next_rank_gwh"]
        print(f"{x['rank']}  {x['host']:<9} {str(x['name']):<36} cohort {x['cohort']}  {x['dc_gwh']:.6f} GWh  "
              f"gap {'' if gap is None else f'{gap:.6f}'}")
    print("to drop:", r["to_drop"], "| kept:", r["kept"], "| failure:", r["failure_in_words"],
          "| rank test without the five:", None if rank_test is None else rank_test["estimable"])
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
