#!/usr/bin/env python3
"""The timing run (PREANALYSIS.md, "Reported beside the headline every time": "As a timing run: Public Service of Colorado
and Ohio Power at their no-anchoring years at 2% (2015 and 2017 ...)"). Reads NO outcome: the outcome frame is an
argument of `estimate_timing_run`.

The specification is D-106 section 9, R7, which Joe adopted on 2026-11-19 (D-107):

    "The timing run. The headline set with Public Service of Colorado and Ohio Power added at their no-anchoring years,
    2015 and 2017, each matched at its own reference year under every existing rule, the seven's matches unchanged; a host
    that fails a rule is named; labelled a timing run on a design on which no validation was made. Under R3, Ohio Power's
    matches are chosen after the year-by-year ownership rule."

What is built
-------------
- The no-anchoring years are read from the frozen files, not from the plan: the labelled record
  `thresholds["2%"]["labelled_runs_beside_the_headline"]["timing_run_at_no_anchoring_years"]` of
  data/frozen/treatment_bounds.json, checked against the column `first_crossing_no_anchoring` of
  data/frozen/headline_set.csv at 2% (`no_anchoring_years`). If the two files disagree the run stops in words; where the
  files disagree with the plan's 2015 and 2017 the difference is reported and the files' years are used.
- The design is design.build_with_rules under the headline rules on the headline set's hosts with the two added at those
  years as their cohorts, and the headline set's comparison-eligible units (`build`). Each added host is matched at its
  own reference year (its cohort minus three) as every host is: the ten eligible units in its reference-year region
  nearest it in residential customers in that year. Every existing rule applies to it as built: the load-unknown gate,
  full-window usability, a region, fuel-mix group and degree days in every window year, the ownership exclusions on its
  pool (ownership.ineligible_for, whatever version of it the file holds at run time; Ohio Power's matches therefore follow
  the year-by-year rule once that repair is in the file), the support rule, and the listing of hosts with unresolved
  ownership.
- The seven's matches are checked against the headline design built from the same inputs without the two
  (`original_hosts_unchanged`): hosts, cohorts and every host's matched units in order, compared as JSON text. If they
  differ the run is not the timing run R7 defines; it is not estimated and the differences are given in words.
- For each added host, `added_hosts` gives its year, its reference year, whether it is in the design, and each rule's
  result; a host that fails a rule is named with the rule's own words and is not silently kept or dropped.
- The fit is outcome_analysis.estimate with validated_design=False, after the rank test made before any fit, and carries
  LABEL.

The agent's readings (not settled by R7 or the plan)
----------------------------------------------------
- The plan's "Public Service of Colorado" and "Ohio Power" are the frozen record's 15466:CO "Public Service Co of
  Colorado" and 14006:OH "Ohio Power Co"; the hosts are taken from the record, whose names are checked against
  PLAN_NAMES.
- "The seven's matches unchanged" is a condition of the run: if adding the two changed any of them, the run stops in
  words rather than reporting a design R7 does not describe.
- A host already in the headline set, or a unit in the comparison-eligible list, cannot be added; either stops in words.

What is here
------------
no_anchoring_years(record, headline_csv)   {host: year} from the two files, their agreement and any difference from
                                           the plan
build(treated, clean, added, q, regions, fuel, dd, *, ownership, usable, gas, ownership_of, unknown_load, theta)
                                           (the timing design, the record: the seven unchanged, each added host's rules)
estimate_timing_run(d, record, frame, column)
                                           the rank test before any fit, then the kernel, validated_design=False
main()                                     the quantity-side record on the headline set at 2%, written to
                                           data/frozen/timing_run_design.json (provisional). NOT to be run until the session
                                           says the ownership repair has been assessed.

Run:  python3 -I pipeline/analysis/timing_run.py
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
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
THRESHOLD = "2%"
OUT = ROOT / "data" / "frozen" / "timing_run_design.json"
TREATMENT_BOUNDS = ROOT / "data" / "frozen" / "treatment_bounds.json"
HEADLINE_CSV = ROOT / "data" / "frozen" / "headline_set.csv"
RECORD_PATH = ("thresholds", THRESHOLD, "labelled_runs_beside_the_headline", "timing_run_at_no_anchoring_years")
# What the plan says, kept to compare with the files and never used as the year (PREANALYSIS.md, "Reported beside the
# headline every time": "Public Service of Colorado and Ohio Power at their no-anchoring years at 2% (2015 and 2017").
PLAN_NAMES = {"Public Service Co of Colorado": 2015, "Ohio Power Co": 2017}

NOT_VALIDATED = oa.NOT_VALIDATED
LABEL = ("timing run: the headline set with Public Service of Colorado and Ohio Power added at their no-anchoring years; "
         + NOT_VALIDATED)


class TimingRunRefused(ValueError):
    """The timing run cannot be formed as R7 defines it. Raised in words; nothing is chosen in its place."""


def _label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def _norm(k) -> tuple:
    return (int(k[0]), str(k[1]))


def _key(label: str) -> tuple:
    u, s = label.split(":")
    return (int(u), s)


# ---- the years ----------------------------------------------------------------------------------------------------------

def no_anchoring_years(record: list, headline_csv: pd.DataFrame | None) -> dict:
    """The two hosts and their no-anchoring years from the labelled record of treatment_bounds.json (`record`, the list at
    RECORD_PATH), checked against headline_set.csv's `first_crossing_no_anchoring` at 2% when the frame is given.

    Returns {"years": {(id, state): year}, "names": {(id, state): name}, "as_built": {...}, "files_agree": bool,
    "differences_from_the_plan": [...]}. Stops in words (TimingRunRefused) if the record does not name exactly the two
    hosts PLAN_NAMES names, if a year is missing, or if the two files disagree."""
    if not isinstance(record, list) or not record:
        raise TimingRunRefused("the labelled record of the timing run is missing or empty in treatment_bounds.json")
    years, names, built = {}, {}, {}
    for r in record:
        k = _key(r["utility"])
        y = r.get("no_anchoring")
        if y is None:
            raise TimingRunRefused(f"the record gives no no-anchoring year for {r['utility']} ({r.get('name')})")
        years[k], names[k], built[k] = int(y), r.get("name"), r.get("as_built")
    if sorted(names.values()) != sorted(PLAN_NAMES):
        raise TimingRunRefused(f"the record names {sorted(map(str, names.values()))}; the plan's timing run is "
                               f"{sorted(PLAN_NAMES)}")
    agree, diffs = True, []
    if headline_csv is not None:
        h = headline_csv[headline_csv.threshold.astype(str) == THRESHOLD]
        for k, y in years.items():
            row = h[(h.utility_id_eia.astype(int) == k[0]) & (h.state.astype(str) == k[1])]
            if len(row) != 1:
                raise TimingRunRefused(f"headline_set.csv has {len(row)} rows for {_label(k)} at {THRESHOLD}; one is needed "
                                       "to check the record")
            y2 = int(row.first_crossing_no_anchoring.iloc[0])
            if y2 != y:
                agree = False
                diffs.append(f"{_label(k)}: treatment_bounds.json gives {y}, headline_set.csv gives {y2}")
        if not agree:
            raise TimingRunRefused("the two frozen files disagree on the no-anchoring years, and neither is chosen: "
                                   + "; ".join(diffs))
    plan = [f"{_label(k)} ({names[k]}): the files give {y}, the plan says {PLAN_NAMES[names[k]]}"
            for k, y in years.items() if PLAN_NAMES[names[k]] != y]
    return {"years": years, "names": names, "as_built": built, "files_agree": agree if headline_csv is not None else None,
            "differences_from_the_plan": plan}


# ---- the design -----------------------------------------------------------------------------------------------------------

def add_hosts(treated: pd.DataFrame, clean: pd.DataFrame, added: dict) -> pd.DataFrame:
    """`treated` with each added host at its year as its cohort. Stops in words if an added host is already a host or is
    in the comparison-eligible list."""
    have = {_norm(k) for k in zip(treated.utility_id_eia, treated.state)}
    comps = {_norm(k) for k in zip(clean.utility_id_eia, clean.state)}
    rows = []
    for k, y in added.items():
        k = _norm(k)
        if k in have:
            raise TimingRunRefused(f"{_label(k)} is already a host of the set; it cannot be added at another year")
        if k in comps:
            raise TimingRunRefused(f"{_label(k)} is in the comparison-eligible list; a host there would be both")
        rows.append({"utility_id_eia": k[0], "state": k[1], "cohort": int(y)})
    return pd.concat([treated[KEY + ["cohort"]], pd.DataFrame(rows, columns=KEY + ["cohort"])], ignore_index=True)


def _hosts_and_matches(d) -> list:
    return ([[_label(k), int(g), [_label(m) for m in mk]] for k, g, mk in zip(d.hosts.key, d.hosts.cohort, d.hosts.match_keys)]
            if len(d.hosts) else [])


def original_hosts_unchanged(base, timing, added: dict) -> dict:
    """Whether every host of `base` is in `timing` with the same cohort and the same matched units in the same order, and
    no host of `base` dropped differently, compared as JSON text. Returns {"unchanged", "differences"}."""
    new = {_label(_norm(k)) for k in added}
    a = _hosts_and_matches(base)
    b = [x for x in _hosts_and_matches(timing) if x[0] not in new]
    diffs = []
    if json.dumps(a) != json.dumps(b):
        da, db = {x[0]: x for x in a}, {x[0]: x for x in b}
        for h in sorted(set(da) | set(db)):
            if da.get(h) != db.get(h):
                diffs.append(f"{h}: headline design {da.get(h)}; timing run {db.get(h)}")
        if not diffs:
            diffs.append("the hosts are in a different order")
    drop_a = sorted(json.dumps(x, sort_keys=True, default=str) for x in base.dropped)
    drop_b = sorted(json.dumps(x, sort_keys=True, default=str) for x in timing.dropped
                    if str(x.get("utility")) not in new)
    if drop_a != drop_b:
        diffs.append("the hosts dropped by the rules differ apart from the added hosts")
    return {"unchanged": not diffs, "differences": diffs}


def _rule_results(d, k: tuple, cohort: int, names=None, matched_before_support: dict | None = None,
                  ownership=None) -> dict:
    """Each existing rule's result for one added host, from what design.build_with_rules recorded. Its matches and the
    ownership exclusions on its pool are read from the build before the support rule (`matched_before_support`), so a
    host the support rule moves out is still reported with them."""
    lab = _label(k)
    dropped = [x for x in d.dropped if str(x.get("utility")) == lab]
    why = [str(x["why"]) for x in dropped]
    unknown = [x for x in (getattr(d, "load_unknown_excluded", None) or []) if x.get("utility") == lab]
    row = next((r for r in d.hosts.itertuples() if _norm(r.key) == k), None) if len(d.hosts) else None
    st = getattr(d, "support_table", None)
    srow = None
    if st is not None and len(st):
        m = st[(st.utility_id_eia.astype(int) == k[0]) & (st.state.astype(str) == k[1])]
        srow = m.iloc[0].to_dict() if len(m) else None
    unresolved = [x for x in (getattr(d, "unresolved_ownership", None) or []) if x.get("utility") == lab]
    out = {"host": lab, "name": None if names is None else names.get(k), "no_anchoring_year": int(cohort),
           "reference_year": int(cohort) + ps.REF, "window": [int(cohort) - ps.PRE, int(cohort) + ps.POST],
           "in_the_design": row is not None, "named_as_failing": why,
           "rules": {
               "load_unknown_gate": "fails: " + unknown[0]["why"] if unknown else "passes",
               "full_window_usable": "fails: " + dsg.NOT_USABLE if dsg.NOT_USABLE in why else (
                   "not reached" if unknown else "passes"),
               "region_fuel_mix_and_degree_days_in_every_window_year":
                   "fails: " + next(w for w in why if w.startswith("no region")) if any(w.startswith("no region") for w in why)
                   else ("not reached" if unknown or dsg.NOT_USABLE in why else "passes"),
               "ownership_exclusions_on_its_pool": None,
               "support_rule": None,
               "unresolved_ownership": ("named as a host with unresolved ownership and kept under the headline rules: "
                                        + unresolved[0].get("reason", "") if unresolved else
                                        ("not listed" if getattr(d, "unresolved_ownership", None) is not None else
                                         "not tested (no ownership table)"))}}
    if srow is not None:
        out["rules"]["support_rule"] = {"pool_in_the_reference_year": int(srow["pool_in_the_reference_year"]),
                                        "matched_in_region_event_year_2": int(srow["matched_in_region_event_year_2"]),
                                        "matched_in_region_event_year_3": int(srow["matched_in_region_event_year_3"]),
                                        "keeps_its_place": bool(srow["keeps_its_place"]), "why_not": srow["why_not"] or None}
    else:
        out["rules"]["support_rule"] = "not reached"
    pre = (matched_before_support or {}).get(lab)
    if pre is not None:
        excl = [dict(x) for x in (pre["excluded_from_its_pool"] or [])]
        window = list(range(int(cohort) - ps.PRE, int(cohort) + ps.POST + 1))
        for x in excl:                       # rule 2.2, read year by year: the window years no row covers
            if x.get("why") == own_rules.NO_ROW and ownership is not None:
                u = _key(x["utility"])
                x["uncovered_window_years"] = [y for y in window if not len(own_rules._rows(ownership, u, [y]))]
                x["no_row_covers_any_window_year"] = len(x["uncovered_window_years"]) == len(window)
                x["name"] = None if names is None else names.get(u)
        out["rules"]["ownership_exclusions_on_its_pool"] = excl
        out["matches"] = [{"utility": _label(m), "name": None if names is None else names.get(_norm(m))}
                          for m in pre["match_keys"]]
        out["ownership_rule_code"] = "pipeline/analysis/ownership.py, ineligible_for, as in the file at run time"
    else:
        out["rules"]["ownership_exclusions_on_its_pool"] = "not reached"
        out["matches"] = None
    return out


def build(treated: pd.DataFrame, clean: pd.DataFrame, added: dict, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict,
          dd: pd.DataFrame, *, ownership, usable, gas, ownership_of, unknown_load, theta: float = 0.02,
          names=None) -> tuple:
    """(the timing design, its record). `treated` and `clean` are the headline set's hosts and comparison-eligible units
    (design.split); `added` maps each added host to its no-anchoring year. Both designs are design.build_with_rules under
    the headline rules on the same inputs."""
    kw = dict(ownership=ownership, usable=usable, gas=gas, ownership_of=ownership_of, unknown_load=unknown_load, theta=theta)
    base = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, ps.HEADLINE_RULES, **kw)
    t2 = add_hosts(treated, clean, added)
    d = dsg.build_with_rules(t2, clean, q, regions, fuel, dd, ps.HEADLINE_RULES, **kw)
    # The added hosts as matched before the support rule (so a host the rule moves out is still reported with its pool).
    pre = dsg.build_with_rules(t2, clean, q, regions, fuel, dd,
                               ps.Rules("timing_run_before_the_support_rule", support="reported_only"), **kw)
    new = {_label(_norm(k)) for k in added}
    before = ({_label(r.key): {"excluded_from_its_pool": getattr(r, "excluded_from_its_pool", []), "match_keys": list(r.match_keys)}
               for r in pre.hosts.itertuples() if _label(r.key) in new} if len(pre.hosts) else {})
    same = original_hosts_unchanged(base, d, added)
    record = {"label": LABEL, "original_hosts": [x[0] for x in _hosts_and_matches(base)],
              "original_hosts_unchanged": same["unchanged"], "original_hosts_differences": same["differences"],
              "added_hosts": [_rule_results(d, _norm(k), y, names, before, ownership) for k, y in added.items()],
              "hosts_in_the_timing_design": [x[0] for x in _hosts_and_matches(d)]}
    return d, record


def _fuel_control(d) -> str:
    rules = getattr(d, "rules", None)
    return rules.fuel_control if rules is not None else oa._fuel_control(d, None)


def estimate_timing_run(d, record: dict, frame: pd.DataFrame, column: str) -> dict:
    """The timing run on the caller's outcome: refused in words if the seven's matches changed; the rank test before any
    fit (influence.estimable, regressors only); then outcome_analysis.estimate, validated_design=False."""
    out = {"label": LABEL, "record": record, "rank_test_before_any_fit": None, "result": None, "estimated": False,
           "failure_in_words": None}
    if not record["original_hosts_unchanged"]:
        out["failure_in_words"] = ("not estimated: adding the two hosts changed the headline hosts' matches, so this is not "
                                   "the timing run R7 defines: " + "; ".join(record["original_hosts_differences"]))
        return out
    t = influence.estimable(d, _fuel_control(d))
    out["rank_test_before_any_fit"] = {"estimable": bool(t["estimable"]),
                                       "smallest_singular_value_ratio": float(t["smallest_singular_value_ratio"]),
                                       "hosts_with_no_matches": t["hosts_with_no_matches"],
                                       "hosts_with_zero_weight": t["hosts_with_zero_weight"]}
    if not t["estimable"]:
        out["failure_in_words"] = ("not estimated: the timing design fails the rank test made before any fit (smallest "
                                   f"singular value ratio {t['smallest_singular_value_ratio']:.3g})")
        return out
    k = oa.estimate(d, oa.outcome_vector(d, frame, column), validated_design=False)
    out["result"] = k
    out["estimated"] = bool(np.isfinite(k["headline"]["log_points"]))
    if not out["estimated"]:
        f = k.get("numerical_failure") or {}
        out["failure_in_words"] = f"the kernel computed no point estimate: {f.get('in_words', 'cause not recorded')}"
    return out


def main() -> int:
    """The timing design on the headline set at 2%, built from the same inputs design.main uses, with the two hosts at
    their no-anchoring years read from the frozen files; its quantity-side record. No price or outcome is read and nothing
    is fitted. Writes OUT."""
    from pipeline.analysis import usable_flag
    bounds = json.loads(TREATMENT_BOUNDS.read_text())
    rec = bounds
    for p in RECORD_PATH:
        rec = rec[p]
    years = no_anchoring_years(rec, pd.read_csv(HEADLINE_CSV))
    q, dose, regions, fuel, dd = dsg.load()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(ps.HEADLINE_RULES, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    names = q.groupby(KEY).utility_name.last()
    names = {(int(k[0]), k[1]): v for k, v in names.items()}
    treated, clean = dsg.split(0.02, ps.HEADLINE_SET, q, dose)
    d, record = build(treated, clean, years["years"], q, regions, fuel, dd, ownership=ownership, usable=usable, gas=gas,
                      ownership_of=ownership_of, unknown_load=unknown, theta=0.02, names=names)
    head = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, ps.HEADLINE_RULES, ownership=ownership, usable=usable,
                                gas=gas, ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
    head_sha = oa.design_hashes(head, usable, ps.HEADLINE_RULES.fuel_control)["design_inputs"]
    rank = None
    if record["original_hosts_unchanged"] and len(d.hosts):
        t = influence.estimable(d, ps.HEADLINE_RULES.fuel_control)
        rank = {"estimable": bool(t["estimable"]), "smallest_singular_value_ratio": float(t["smallest_singular_value_ratio"]),
                "hosts_with_no_matches": t["hosts_with_no_matches"], "hosts_with_zero_weight": t["hosts_with_zero_weight"]}
    fp = dsg.run_fingerprint(d, rules=ps.HEADLINE_RULES, usable=usable,
                             assumptions={"kind": "timing_run", "set": ps.HEADLINE_SET, "threshold": 0.02,
                                          "added": {_label(k): y for k, y in years["years"].items()}},
                             settings={}, seeds=None)
    doc = {"what_this_is": ("The timing run (Reported beside the headline; R7, adopted by Joe on 2026-11-19, D-107): the "
                            "headline set at 2% with Public Service of Colorado and Ohio Power added at their no-anchoring "
                            "years, each matched at its own reference year under every existing rule; whether the seven "
                            "headline hosts' matches are unchanged; each added host's rule results and matches; and the "
                            "rank test made before any fit on the regressors alone. Ohio Power's matches follow the "
                            "ownership code in the file when this was run. Quantities only: load, sales, customers, "
                            "ownership and the usable flag; no price, revenue, bill or outcome is read and nothing is "
                            "fitted. A timing run on a design on which no validation was made. PROVISIONAL: the design "
                            "stands as of 2026-11-18 and the plan is a DRAFT, not frozen."),
           "built_by": "pipeline/analysis/timing_run.py (main)",
           "years_source": {"record": "data/frozen/treatment_bounds.json, " + " / ".join(RECORD_PATH),
                            "checked_against": "data/frozen/headline_set.csv, first_crossing_no_anchoring at 2%",
                            "files_agree": years["files_agree"],
                            "differences_from_the_plan": years["differences_from_the_plan"]},
           "set": ps.HEADLINE_SET, "threshold": 0.02, "rules": ps.HEADLINE_RULES.label,
           "readings": ["the seven's matches unchanged is a condition of the run; if it fails the run is not estimated "
                        "(the agent's reading)"],
           **record, "rank_test_before_any_fit": rank,
           "design_inputs_sha256": fp["of"]["design_inputs"], "fingerprint": fp,
           "headline_design_inputs_sha256_same_inputs": head_sha}
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    for a in record["added_hosts"]:
        print(a["host"], a["name"], a["no_anchoring_year"], "in design:", a["in_the_design"], "| failing:", a["named_as_failing"])
        print("   matches:", [m["utility"] for m in (a["matches"] or [])])
        print("   ownership exclusions:", a["rules"]["ownership_exclusions_on_its_pool"])
    print("seven unchanged:", record["original_hosts_unchanged"], "| rank test:", rank)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
