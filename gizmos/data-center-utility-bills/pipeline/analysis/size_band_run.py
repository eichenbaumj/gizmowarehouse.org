#!/usr/bin/env python3
"""The size-band form as a side run (PREANALYSIS.md, "Size adjustment": "The size-band form is reported as a side run").
Reads NO outcome: the outcome frame is an argument of `estimate_size_band`.

The specification is D-106 section 9, R7, which Joe adopted on 2026-11-19 (D-107):

    "The size-band form as a side run. Cells of reference-year region by size band; utility effects and cell-by-year
    effects; the gas-share and degree-day controls; comparison utilities every unit eligible under the main design's
    rules, ownership and full-window usability included; the support rule's first limb as written, with each host's count
    of comparison utilities in its cell reported and a host with none not estimable and named."

The size bands are the plan's (Size adjustment: under 10,000 residential customers; 10,000 to 99,999; 100,000 or more),
by residential customers in the cohort's reference year: power_simulation.SIZE_BANDS and power_simulation.size_band, the
same function the simulation used, applied by power_simulation.Stack to each unit's customers in the reference year.

What is the kernel's and what is this module's
-----------------------------------------------
Nothing here estimates. The regressors, fixed effects, clusters and procedure are outcome_analysis.estimate's, unchanged
(inference_check.fixed_parts and power_simulation.assemble): event-time columns on host rows, the two degree-day controls,
the gas-share-by-calendar-year columns; utility effects; block-by-region-by-year effects; clusters by state. What is this
module's is the comparison set and nothing else:
  - eligibility is design.build_with_rules' under the headline rules (the ownership table with rules 2.2 and 2.3, the
    host's own utility out, full-window usability from the usable flag applied before matching, the load-unknown gate,
    the price hold through the comparison-eligible list), called with k equal to the number of units so that no
    nearest-ten cut is made, and with the support rule reported only, so that its second limb (eight of ten matches in
    region in event years 2 and 3), which belongs to the ten-nearest form, moves no one;
  - each host's comparison utilities are then every unit of that eligible pool in the host's reference-year region whose
    size band in the reference year is the host's (`cell_comparisons`);
  - the support rule's first limb is applied as written: a host with fewer than ten eligible comparison utilities in its
    region in its reference year (design.THIN; the pool design.build counts after the exclusions) leaves this run's
    estimate and is named in `dropped` (FIRST_LIMB).
Each host's comparisons sit in its own block, so the kernel's block-by-region-by-year effects are, within each host's
sub-experiment, effects for the host's cell by year: every unit in the block shares the host's reference-year region and
size band. The region in that effect is read year by year as the main design reads it (D-37); the band is fixed at the
reference year, as the plan measures size. Both are adopted by Joe on 2026-11-19 (D-111).

The form and its scope, adopted by Joe on 2026-11-19 (D-111)
------------------------------------------------------------
His words: "Size-band form: adopt the tested per-host form for the headline set at 2%. Applications to sets with shared
cohort-and-cell hosts are outside this freeze. Do not build an extension for them."
- One sub-experiment per host, its cell's eligible units its comparisons, rather than the simulation's form
  (power_simulation.build_blocks, form "size_band"), which pools every host of a cohort and cell into one block. The
  reason: ownership eligibility (rules 2.2 and 2.3) is decided for each host, and a pooled block cannot keep a unit for
  one host and leave it out for another. Adopted by Joe on 2026-11-19 (D-111), for the headline set at 2%.
- The equivalence was tested and not inferred (docs/gate1/size-band-equivalence-2026-11-19.md;
  tests/test_size_band_equivalence_invented.py; D-110). The pooled form it was tested against is blocks of cohort by
  cell with each host's ownership exclusions kept, adopted by Joe on 2026-11-19 (D-111) as what the comparison takes the
  intended pooled form to be. On the headline set at 2% the two are the same design by the test: the same 890 stacked
  rows over 722 utility-years with the same multiplicities, the same fixed effects and controls, 26 of 26 regressors at
  full rank, and the implied weight on every stacked row equal to within 1.1e-14. Where two hosts share a cohort and a
  cell the two forms differ: the per-host form stacks each shared comparison unit once for each host and gives the hosts
  that share a cell more weight against the other hosts.
- Applying this side run to a set in which two hosts share a cohort and a cell is outside this freeze by Joe's ruling,
  and no extension is built for it: no pooled form, no per-cell form across cohorts, no companion-set version. `build`
  refuses such a set in words before it returns a design, so nothing is stacked (`refuse_outside_the_adopted_scope`).
  Two hosts share a cohort and a cell when, after the first limb, they have the same cohort, the same reference-year
  region and the same size band in the reference year: the grouping `quantity_summary` uses for
  "hosts_sharing_a_cohort_and_a_cell", and the cell of tests/size_band_pooled_form.cell_of (cohort, the region and the
  band of the host's row in its cohort's window).
- "As written" for the first limb, in a side run: a host that fails it leaves this run's estimate and is named, as the
  support rule moves such a host out of the headline set. The limb itself is unchanged. Adopted by Joe on 2026-11-19
  (D-111).

The agent's reading (not settled by R7 or the plan)
---------------------------------------------------
- A host with no comparison utility in its cell stays in the design with no matches, named as not estimable; the kernel
  names it again and does not stack it.

What is here
------------
SIZE_BAND_RULES                     the headline rules with the support rule reported only (see above)
build(treated, clean, q, regions, fuel, dd, *, ownership, usable, gas, ownership_of, unknown_load, theta)
                                    the size-band design: every host's cell comparisons, the first limb applied; refuses
                                    in words a set in which two hosts share a cohort and a cell (OutsideTheAdoptedScope)
hosts_sharing_a_cohort_and_a_cell(d)
                                    the groups of two or more hosts with one cohort, region and band (quantity_summary's)
refuse_outside_the_adopted_scope(d) raises OutsideTheAdoptedScope, naming the hosts, if any group exists
_per_host_design(...)               the per-host construction without the scope refusal, kept so that the equivalence
                                    test's invented worlds with shared cells (tests/test_size_band_equivalence_invented.py,
                                    through tests/test_size_band_run_invented.world) stay the record of the tested
                                    comparison; no pipeline module calls it (tested). It is not the side run.
cell_comparisons(d)                 per host: region, band, customers, pool in region, comparison utilities in its cell
estimate_size_band(d, frame, column)
                                    the rank test before any fit, then outcome_analysis.estimate, validated_design=False
quantity_summary(d, names=None)     hosts by cell, counts, hosts not estimable, the rank test (no outcome)
main()                              the quantity-side summary on the headline set at 2%, written to
                                    data/frozen/size_band_design.json (provisional). NOT to be run until the session says
                                    the ownership repair has been assessed.

Run:  python3 -I pipeline/analysis/size_band_run.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

KEY = ps.KEY
SIZE_BANDS = ps.SIZE_BANDS                       # (10_000, 100_000): the plan's bands, as the simulation used them
BAND_NAMES = ("under 10,000", "10,000 to 99,999", "100,000 or more")
FIRST_LIMB = dsg.THIN                            # at least ten eligible in the host's region in its reference year
SIZE_BAND_RULES = replace(ps.HEADLINE_RULES, label="side_run_size_band_form", support="reported_only")
OUT = ROOT / "data" / "frozen" / "size_band_design.json"

NOT_VALIDATED = oa.NOT_VALIDATED
LABEL = ("side run: the size-band form (cells of reference-year region by size band), in the tested per-host form adopted "
         "by Joe on 2026-11-19 (D-111) for the headline set at 2%; a set in which hosts share a cohort and a cell is "
         "outside this freeze; " + NOT_VALIDATED)
FIRST_LIMB_WHY = ("fails the support rule's first limb: {n} eligible comparison utilities in its region in its reference "
                  "year, fewer than ten; left out of the size-band side run and named (R7, adopted by Joe, D-107)")
NO_CELL = "no comparison utility in its cell (region by size band in its reference year): not estimable"
OUTSIDE_THE_ADOPTED_SCOPE = (
    "the size-band side run is not built for this set: {groups}. Its form is the tested per-host form, adopted by Joe on "
    "2026-11-19 (D-111) for the headline set at 2%. Applying it to a set in which hosts share a cohort and a cell is "
    "outside this freeze by that ruling, and no extension is built for it. No design is returned and nothing is stacked.")


class OutsideTheAdoptedScope(RuntimeError):
    """The refusal of a set in which two hosts share a cohort and a cell. `shared` holds the groups, as
    hosts_sharing_a_cohort_and_a_cell returns them."""

    def __init__(self, shared: list):
        self.shared = shared
        super().__init__(OUTSIDE_THE_ADOPTED_SCOPE.format(groups="; ".join(
            f"hosts {' and '.join(g['hosts'])} share cohort {g['cohort']} and the cell {g['region']} by {g['size_band']}"
            for g in shared)))

if SIZE_BANDS != (10_000, 100_000):              # the plan's three bands; refuse anything else in words
    raise RuntimeError(f"power_simulation.SIZE_BANDS is {SIZE_BANDS}; the plan's bands are under 10,000, 10,000 to 99,999 "
                       "and 100,000 or more")


def _label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def _name(names, label: str):
    if not names:
        return None
    u, s = label.split(":")
    v = names.get((int(u), s)) if hasattr(names, "get") else None
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)


def band_name(b: int) -> str:
    return BAND_NAMES[int(b)]


def build(treated: pd.DataFrame, clean: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict,
          dd: pd.DataFrame, *, ownership, usable, gas, ownership_of, unknown_load, theta: float) -> dsg.Design:
    """The size-band design (see the module docstring). Every host keeps every eligible unit of its cell, in the order
    design.build sorts its pool (nearest in size first, which changes nothing in the fit). The returned Design carries
    SIZE_BAND_RULES, the first-limb drops in `dropped`, `cells` (cell_comparisons), and `support_table` None (the support
    table of the ten-nearest form does not describe it). A set in which two hosts share a cohort and a cell is refused
    in words (OutsideTheAdoptedScope, naming the hosts) before any design is returned, so no caller of build reaches a
    stacked design for it: outside this freeze by Joe's ruling of 2026-11-19 (D-111), and no extension is built."""
    d = _per_host_design(treated, clean, q, regions, fuel, dd, ownership=ownership, usable=usable, gas=gas,
                         ownership_of=ownership_of, unknown_load=unknown_load, theta=theta)
    refuse_outside_the_adopted_scope(d)
    return d


def hosts_sharing_a_cohort_and_a_cell(d) -> list:
    """Every group of two or more hosts of `d` (after the first limb) with the same cohort, reference-year region and
    size band in the reference year, read by cell_comparisons and grouped exactly as quantity_summary groups them for
    "hosts_sharing_a_cohort_and_a_cell". Returns [{"cohort", "region", "size_band", "hosts"}]."""
    share: dict = {}
    for c in cell_comparisons(d):
        share.setdefault((c["cohort"], c["region"], c["size_band"]), []).append(c["host"])
    return [{"cohort": k[0], "region": k[1], "size_band": k[2], "hosts": v} for k, v in share.items() if len(v) > 1]


def refuse_outside_the_adopted_scope(d) -> None:
    """The guard on the adopted scope (Joe, 2026-11-19, D-111): raises OutsideTheAdoptedScope, naming the hosts, if two
    hosts of `d` share a cohort and a cell. It is a refusal and not an extension: it builds nothing and switches to no
    other form."""
    shared = hosts_sharing_a_cohort_and_a_cell(d)
    if shared:
        raise OutsideTheAdoptedScope(shared)


def _per_host_design(treated: pd.DataFrame, clean: pd.DataFrame, q: pd.DataFrame, regions: pd.DataFrame, fuel: dict,
                     dd: pd.DataFrame, *, ownership, usable, gas, ownership_of, unknown_load, theta: float) -> dsg.Design:
    """The per-host construction that `build` returns, without the scope refusal. Kept only so that the equivalence
    test's invented worlds in which hosts share a cell remain the record of the tested comparison
    (tests/test_size_band_equivalence_invented.py). No pipeline module calls it, and it is not the side run."""
    k_all = int(len(pd.concat([treated[KEY], clean[KEY]]).drop_duplicates())) + 1
    d0 = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, SIZE_BAND_RULES, ownership=ownership, usable=usable,
                              gas=gas, ownership_of=ownership_of, unknown_load=unknown_load, k=k_all, theta=theta)
    if not len(d0.hosts):
        d0.support_table, d0.cells = None, []
        return d0
    matches, match_keys, in_cell, band = [], [], [], []
    for h in d0.hosts.itertuples():
        w = d0.windows[h.cohort]
        b = int(w.band[h.row])
        kept = [(int(m), mk) for m, mk in zip(h.matches, h.match_keys) if int(w.band[int(m)]) == b]
        matches.append([m for m, _ in kept])
        match_keys.append([mk for _, mk in kept])
        in_cell.append(len(kept))
        band.append(b)
    hosts = d0.hosts.copy()
    hosts["matches"] = pd.Series(matches, index=hosts.index, dtype=object)
    hosts["match_keys"] = pd.Series(match_keys, index=hosts.index, dtype=object)
    hosts["size_band"] = band
    hosts["comparison_utilities_in_its_cell"] = in_cell
    fails = hosts.pool_in_the_reference_year.astype(int) < FIRST_LIMB
    dropped = list(d0.dropped) + [{"utility": _label(r.key), "cohort": int(r.cohort),
                                   "why": FIRST_LIMB_WHY.format(n=int(r.pool_in_the_reference_year))}
                                  for r in hosts[fails].itertuples()]
    d = dsg.Design(hosts[~fails].reset_index(drop=True), d0.windows, d0.is_comp, dropped, dict(d0.region_names),
                   dict(d0.unit_code), dict(d0.state_code), d0.gas)
    for attr in ("rules", "load_unknown_excluded", "unknown_load_source", "names"):
        if hasattr(d0, attr):
            setattr(d, attr, getattr(d0, attr))
    gone = {_label(r.key) for r in hosts[fails].itertuples()}
    d.unresolved_ownership = ([x for x in d0.unresolved_ownership if x.get("utility") not in gone]
                              if d0.unresolved_ownership is not None else None)
    d.support_table = None
    d.first_limb_failures = sorted(gone)
    d.cells = cell_comparisons(d, q)
    return d


def cell_comparisons(d, q: pd.DataFrame | None = None, names=None) -> list:
    """Per host: its reference-year region and size band, its residential customers in the reference year (from q when
    given), the eligible pool in its region in the reference year (the first limb's count), and its comparison utilities
    in its cell, counted and listed."""
    cust = None
    if q is not None:
        cust = {(int(u), str(s), int(y)): float(c) for u, s, y, c in zip(q.utility_id_eia, q.state, q.year, q.res_customers)}
    out = []
    for h in d.hosts.itertuples():
        g = int(h.cohort)
        w = d.windows[g]
        b = int(w.band[h.row])
        k = (int(h.key[0]), str(h.key[1]))
        out.append({"host": _label(k), "name": _name(names, _label(k)), "cohort": g, "reference_year": g + ps.REF,
                    "region": str(h.region), "size_band": band_name(b),
                    "residential_customers_in_the_reference_year": None if cust is None else cust.get((k[0], k[1], g + ps.REF)),
                    "eligible_in_its_region_in_the_reference_year": int(h.pool_in_the_reference_year),
                    "comparison_utilities_in_its_cell": int(len(h.matches)),
                    "comparisons": [_label(m) for m in h.match_keys]})
    return out


def _fuel_control(d) -> str:
    rules = getattr(d, "rules", None)
    return rules.fuel_control if rules is not None else oa._fuel_control(d, None)


def estimate_size_band(d, frame: pd.DataFrame, column: str) -> dict:
    """The side run on the caller's outcome: the rank test before any fit (influence.estimable, regressors only), then
    outcome_analysis.estimate on `d` for `column` of `frame`, validated_design=False. Returns {"label",
    "hosts_with_no_comparison_in_its_cell_not_estimable", "first_limb_failures", "rank_test_before_any_fit", "result",
    "estimated", "failure_in_words"}."""
    none = [_label(k) for k, m in zip(d.hosts.key, d.hosts.matches) if len(m) == 0] if len(d.hosts) else []
    out = {"label": LABEL, "hosts_with_no_comparison_in_its_cell_not_estimable": [{"host": h, "why": NO_CELL} for h in none],
           "first_limb_failures": list(getattr(d, "first_limb_failures", []) or []),
           "rank_test_before_any_fit": None, "result": None, "estimated": False, "failure_in_words": None}
    if not len(d.hosts):
        out["failure_in_words"] = "not estimable: no host is in the size-band design"
        return out
    t = influence.estimable(d, _fuel_control(d))
    out["rank_test_before_any_fit"] = {"estimable": bool(t["estimable"]),
                                       "smallest_singular_value_ratio": float(t["smallest_singular_value_ratio"]),
                                       "hosts_with_no_matches": t["hosts_with_no_matches"],
                                       "hosts_with_zero_weight": t["hosts_with_zero_weight"]}
    if not t["estimable"]:
        out["failure_in_words"] = ("not estimated: the size-band design fails the rank test made before any fit (smallest "
                                   f"singular value ratio {t['smallest_singular_value_ratio']:.3g})")
        return out
    k = oa.estimate(d, oa.outcome_vector(d, frame, column), validated_design=False)
    out["result"] = k
    out["estimated"] = bool(np.isfinite(k["headline"]["log_points"]))
    if not out["estimated"]:
        f = k.get("numerical_failure") or {}
        out["failure_in_words"] = f"the kernel computed no point estimate: {f.get('in_words', 'cause not recorded')}"
    return out


def quantity_summary(d, q: pd.DataFrame | None = None, names=None) -> dict:
    """Hosts by cell, each host's count of comparison utilities in its cell, hosts not estimable, the first-limb
    failures, any two hosts sharing a cohort and a cell, and the rank test made before any fit. No outcome. It takes a
    built design and refuses nothing itself: a design from `build` has no hosts sharing a cohort and a cell, so for it
    the list is empty; the list is non-empty only on a design from _per_host_design (the equivalence test's worlds)."""
    cells = cell_comparisons(d, q, names)
    by_cell: dict = {}
    for c in cells:
        by_cell.setdefault(f"{c['region']} | {c['size_band']}", []).append(c["host"])
    share: dict = {}
    for c in cells:
        share.setdefault((c["cohort"], c["region"], c["size_band"]), []).append(c["host"])
    rank = None
    if len(d.hosts):
        t = influence.estimable(d, _fuel_control(d))
        rank = {"estimable": bool(t["estimable"]), "smallest_singular_value_ratio": float(t["smallest_singular_value_ratio"]),
                "hosts_with_zero_weight": t["hosts_with_zero_weight"]}
    return {"label": LABEL, "hosts": cells, "hosts_by_cell": by_cell,
            "hosts_with_no_comparison_in_its_cell_not_estimable": [{"host": c["host"], "name": c["name"], "why": NO_CELL}
                                                                    for c in cells if c["comparison_utilities_in_its_cell"] == 0],
            "first_limb_failures": [x for x in d.dropped if str(x.get("why", "")).startswith("fails the support rule's first limb")],
            "hosts_sharing_a_cohort_and_a_cell": [{"cohort": k[0], "region": k[1], "size_band": k[2], "hosts": v}
                                                  for k, v in share.items() if len(v) > 1],
            "rank_test_before_any_fit": rank}


def main() -> int:
    """The size-band design on the headline set at 2%, built from the same inputs design.main uses; its quantity-side
    summary. No price or outcome is read and nothing is fitted. Writes OUT."""
    from pipeline.analysis import usable_flag
    q, dose, regions, fuel, dd = dsg.load()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(ps.HEADLINE_RULES, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    names = q.groupby(KEY).utility_name.last()
    names = {(int(k[0]), k[1]): v for k, v in names.items()}
    treated, clean = dsg.split(0.02, ps.HEADLINE_SET, q, dose)
    d = build(treated, clean, q, regions, fuel, dd, ownership=ownership, usable=usable, gas=gas, ownership_of=ownership_of,
              unknown_load=unknown, theta=0.02)
    head = dsg.build_with_rules(treated, clean, q, regions, fuel, dd, ps.HEADLINE_RULES, ownership=ownership, usable=usable,
                                gas=gas, ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
    head_sha = oa.design_hashes(head, usable, ps.HEADLINE_RULES.fuel_control)["design_inputs"]
    s = quantity_summary(d, q, names)
    fp = dsg.run_fingerprint(d, rules=SIZE_BAND_RULES, usable=usable,
                             assumptions={"kind": "size_band_side_run", "set": ps.HEADLINE_SET, "threshold": 0.02},
                             settings={"size_bands": list(SIZE_BANDS), "first_limb": FIRST_LIMB}, seeds=None)
    doc = {"what_this_is": ("The size-band form as a side run (Size adjustment; R7, adopted by Joe on 2026-11-19, D-107) on "
                            "the headline set at 2%: each host's cell of reference-year region by size band, its count of "
                            "comparison utilities in the cell (every unit eligible under the main design's rules, ownership "
                            "and full-window usability included), the support rule's first limb, the hosts not estimable, "
                            "and the rank test made before any fit on the regressors alone. Quantities only: load, sales, "
                            "customers, ownership and the usable flag; no price, revenue, bill or outcome is read and "
                            "nothing is fitted. The per-host form is the side run's form, adopted by Joe on 2026-11-19 "
                            "(D-111) for the headline set at 2%, where it was tested to be the same design as the form "
                            "pooled by cohort and cell with each host's ownership exclusions kept (D-110); applying it to "
                            "a set in which hosts share a cohort and a cell is outside this freeze, build refuses such a "
                            "set in words, and no extension is built. A side run on a design on which no validation was "
                            "made. PROVISIONAL: the "
                            "design stands as of 2026-11-18 under the ownership code in the file when this was run, and the "
                            "plan is a DRAFT, not frozen."),
           "built_by": "pipeline/analysis/size_band_run.py (main)",
           "set": ps.HEADLINE_SET, "threshold": 0.02, "rules": SIZE_BAND_RULES.label,
           "size_bands": list(BAND_NAMES),
           "readings": ["one sub-experiment per host with its cell's eligible units, not the simulation's pooled cohort-by-"
                        "cell blocks, because ownership eligibility is decided for each host (adopted by Joe on "
                        "2026-11-19, D-111, for the headline set at 2%; a set in which hosts share a cohort and a cell "
                        "is outside this freeze)",
                        "a host failing the first limb leaves this run's estimate and is named, 'as written' in a side "
                        "run (adopted by Joe on 2026-11-19, D-111)"],
           "hosts_dropped_before_the_cells": [x for x in d.dropped],
           **s, "design_inputs_sha256": fp["of"]["design_inputs"], "fingerprint": fp,
           "headline_design_inputs_sha256_same_inputs": head_sha}
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    for c in s["hosts"]:
        print(f"{c['host']:<9} {str(c['name']):<36} {c['region']:<10} {c['size_band']:<17} pool "
              f"{c['eligible_in_its_region_in_the_reference_year']:>4}  in cell {c['comparison_utilities_in_its_cell']:>4}")
    print("rank test:", s["rank_test_before_any_fit"], "| sharing a cohort and cell:", s["hosts_sharing_a_cohort_and_a_cell"])
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
