"""The capacity exceedance check for sensitivity scenario A (Joe, D-111; job 1 of the session 23 handover, stage 1).

Joe's words (D-111): before finalizing the lift-first rule, "check whether returning a site to its original utility
when no alternative fits creates a final capacity exceedance because other sites have occupied that space. Distinguish
pre-existing exceedances from newly introduced ones." And his clarification: "defer the item if lifting first either
introduces a capacity exceedance or increases a pre-existing exceedance."

This file sits beside `tests/scenario_a_independent_check.py` and builds on its placement (`place`) and its readings
(`Reading`). Like that checker it imports nothing from `pipeline/analysis/second_number_scenarios.py` and calls no
function in `pipeline/`. It reads the same quantity-side inputs as that checker and nothing else: nine columns of
`data/interim/facilities.parquet` and five of `data/interim/panel_quantities.parquet`, plus the balancing-authority
table read as data from `pipeline/electricity/market_region.py`. It reads no dose, price, revenue, bill or estimate.

The accounting, per panel unit (utility, state) that carries any of the 460 before or after:
* capacity: the unit's largest annual total retail sales in 2020 and later (the panel ends in 2025), MWh over 1000,
  as `build_inventory.py` computes it before calling `pick_utilities` (`capacity = (q[q.year >= 2020]...max() / 1000.0)`);
  the checker's `capacity_from_sales` computes the same.
* load as assigned: every site of the inventory on the unit (utility and state not missing), at scaled full load
  (`mw_full` times 8.76, GWh), the 460 included where they sit now. This is the checker's `carried_at_start` under the
  module's earlier reading `all_assigned` (ck.EARLIER_MODULE_READING).
* final load: every site that is not one of the 460, where the inventory has it, plus each of the 460 where the
  placement ends it (moved to its destination, or returned to the unit it is on).
* exceeds: load strictly greater than capacity. `pick_utilities` and the checker treat `carried + load <= capacity` as
  fitting, so a load equal to capacity is within it. No tolerance is used anywhere in the classification.

Every load is summed with `math.fsum` over per-site loads, so a unit carrying the same sites before and after has
exactly the same load before and after; a difference smaller than 1e-6 GWh is reported raw and flagged, never classed
away.

The three classes of a unit whose final load exceeds its capacity (from the handover, section 5, job 1):
* pre_existing: over capacity as assigned, and final load no larger than load as assigned;
* newly_introduced: within capacity as assigned, over it at the end;
* pre_existing_made_larger: over capacity as assigned, and final load larger than load as assigned.
The second and the third defer the item. A unit with no recorded capacity measure (no sales on file in 2020 to 2025,
the years the placement rule measures capacity from, so the rule has no measure for it) cannot be classed and is
reported as such, in the class `no_recorded_capacity_measure`.
"""
from __future__ import annotations

import dataclasses
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scenario_a_independent_check as ck  # noqa: E402

# The module was brought to the lift-first rule after this check (2026-11-19, D-111): ck.MODULE_READING is now
# LIFT_FIRST, and the comparison is with the module's earlier reading.
LIFT_FIRST = dataclasses.replace(ck.EARLIER_MODULE_READING, carried="resolved_only")
EARLIER = ck.EARLIER_MODULE_READING
NOISE_GWH = 1e-6        # a reporting flag only: never used to class a unit
OUT_CSV = ck.FROZEN / "scenario_a_exceedance_check.csv"

CLASSES = ("pre_existing", "newly_introduced", "pre_existing_made_larger")
DEFERRING = ("newly_introduced", "pre_existing_made_larger")


def site_table(fac: pd.DataFrame, load: str = "scaled") -> pd.DataFrame:
    """Every site of the inventory on a unit: fid, unit (utility, state), gwh. The same sites and loads the checker's
    carried_at_start counts under `all_assigned` (a missing full load counts 0)."""
    ck.refuse(fac, "the inventory")
    col = "mw_full" if load == "scaled" else "mw_full_raw"
    f = fac[fac.utility_id_eia.notna() & fac.state.notna()]
    return pd.DataFrame({"fid": f.fid.astype(str).values,
                         "unit": [(int(u), str(s)) for u, s in zip(f.utility_id_eia, f.state)],
                         "gwh": [0.0 if pd.isna(m) else float(m) * ck.GWH_PER_MW_YEAR for m in f[col]]})


def classify(assigned: float, final: float, capacity: float) -> str:
    """Exact comparisons, as the placement rule makes them (a load equal to capacity fits)."""
    if capacity is None or (isinstance(capacity, float) and math.isnan(capacity)):
        return "no_recorded_capacity_measure"
    if not final > capacity:
        return "over_as_assigned_within_at_end" if assigned > capacity else "within"
    if not assigned > capacity:
        return "newly_introduced"
    if final > assigned:
        return "pre_existing_made_larger"
    return "pre_existing"


def account(all_sites: pd.DataFrame, sites: pd.DataFrame, records: list, capacity: dict,
            units: set | None = None) -> pd.DataFrame:
    """One row per unit that carries any of the placed sites before or after (or per unit in `units` if given).

    all_sites: site_table (every site of the inventory on a unit). sites: the 460 (fid, state, utility_id_eia,
    load_gwh). records: the placement (ck.place). capacity: {(utility, state): GWh}."""
    ck.refuse(sites, "the sites")
    placed = set(sites.fid)
    if set(r["fid"] for r in records) != placed:
        raise ValueError("the placement and the sites differ")
    g460 = dict(zip(sites.fid, sites.load_gwh))
    end = {r["fid"]: (r["to"], r["state"]) for r in records}
    start = {r["fid"]: (r["from"], r["state"]) for r in records}
    resident: dict = {}
    assigned: dict = {}
    for fid, unit, gwh in zip(all_sites.fid, all_sites.unit, all_sites.gwh):
        assigned.setdefault(unit, []).append(gwh)
        if fid not in placed:
            resident.setdefault(unit, []).append(gwh)
    # a placed site's own load in the site table must be the load it is placed with
    tab = dict(zip(all_sites.fid, all_sites.gwh))
    unit_of = dict(zip(all_sites.fid, all_sites.unit))
    for fid in placed:
        if fid not in tab or tab[fid] != g460[fid]:
            raise ValueError(f"site {fid} is not in the inventory at the load it is placed with")
        if unit_of[fid] != start[fid]:
            raise ValueError(f"site {fid} is not on the unit the placement starts it from")
    if units is None:
        units = set(start.values()) | set(end.values())
    rows = []
    for unit in sorted(units, key=lambda k: (k[1], k[0])):
        res = resident.get(unit, [])
        returned = [(r["fid"], g460[r["fid"]], r["why"]) for r in records if not r["moved"] and end[r["fid"]] == unit]
        arriving = [(r["fid"], g460[r["fid"]], r["from"]) for r in records if r["moved"] and end[r["fid"]] == unit]
        leaving = [(r["fid"], g460[r["fid"]], r["to"]) for r in records if r["moved"] and start[r["fid"]] == unit]
        a = math.fsum(assigned.get(unit, []))
        fin = math.fsum(res + [x[1] for x in returned] + [x[1] for x in arriving])
        cap = capacity.get(unit, float("nan"))
        cls = classify(a, fin, cap)
        rows.append({
            "utility_id_eia": unit[0], "state": unit[1], "capacity_gwh": cap,
            "resident_sites": len(res), "resident_load_gwh": math.fsum(res),
            "placed_sites_on_it_as_assigned": sum(1 for f in placed if start[f] == unit),
            "load_as_assigned_gwh": a, "final_load_gwh": fin, "difference_gwh": fin - a,
            "over_as_assigned": bool(a > cap), "over_at_end": bool(fin > cap),
            "excess_at_end_gwh": (fin - cap) if fin > cap else 0.0,
            "excess_share_of_capacity": ((fin - cap) / cap) if fin > cap and cap > 0 else 0.0,
            "class": cls,
            "near_noise": bool((not math.isnan(cap)) and (abs(fin - cap) < NOISE_GWH or abs(a - cap) < NOISE_GWH
                               or (0 < abs(fin - a) < NOISE_GWH))),
            "returned": ";".join(f"{f}={g:.6f}({w})" for f, g, w in returned),
            "arriving": ";".join(f"{f}={g:.6f}(from {o})" for f, g, o in arriving),
            "leaving": ";".join(f"{f}={g:.6f}(to {d})" for f, g, d in leaving),
            "n_returned": len(returned), "n_arriving": len(arriving), "n_leaving": len(leaving)})
    return pd.DataFrame(rows)


def arrival_slack(all_sites: pd.DataFrame, sites: pd.DataFrame, records: list, capacity: dict,
                  reading: dataclasses.dataclass) -> list:
    """For every moved site: its destination's capacity less (what that unit carried when the site was tested, by
    fsum, plus the site), recomputed in processing order apart from `place`. Non-negative means the test passed by
    this recount too. Used to confirm the placement's running sums agree with fsum (a reporting check only)."""
    placed = set(sites.fid)
    g460 = dict(zip(sites.fid, sites.load_gwh))
    if reading.carried == "resolved_only":
        on = {}
        for fid, unit, gwh in zip(all_sites.fid, all_sites.unit, all_sites.gwh):
            if fid not in placed:
                on.setdefault(unit, []).append((fid, gwh))
    elif reading.carried == "all_assigned":
        on = {}
        for fid, unit, gwh in zip(all_sites.fid, all_sites.unit, all_sites.gwh):
            on.setdefault(unit, []).append((fid, gwh))
    else:
        raise ValueError("slack is recounted for the two readings compared here only")
    out = []
    for r in records:                                      # records are in processing order
        u_from, u_to = (r["from"], r["state"]), (r["to"], r["state"])
        if r["moved"]:
            have = math.fsum(g for _, g in on.get(u_to, []))
            out.append({"fid": r["fid"], "to": u_to, "slack_gwh": capacity[u_to] - (have + g460[r["fid"]])})
            on.setdefault(u_to, []).append((r["fid"], g460[r["fid"]]))
            if reading.carried == "all_assigned":
                on[u_from] = [x for x in on[u_from] if x[0] != r["fid"]]
        elif reading.carried == "resolved_only":
            on.setdefault(u_from, []).append((r["fid"], g460[r["fid"]]))
    return out


def inventory_over_capacity(fac: pd.DataFrame, capacity: dict, panel_units: set) -> pd.DataFrame:
    """Every panel unit whose load as assigned (all sites) exceeds its capacity, with the counts of its sites by
    `utility_assign` (how the build placed each), to show why it can be over."""
    s = site_table(fac)
    assign = dict(zip(fac.fid.astype(str), fac.utility_assign.astype(str)))
    rows = []
    for unit, g in s.groupby("unit"):
        if unit not in panel_units:
            continue
        cap = capacity.get(unit, float("nan"))
        a = math.fsum(g.gwh)
        if not math.isnan(cap) and a > cap:
            how = g.fid.map(assign).value_counts().to_dict()
            rows.append({"utility_id_eia": unit[0], "state": unit[1], "capacity_gwh": cap, "load_as_assigned_gwh": a,
                         "excess_gwh": a - cap, "sites": len(g),
                         "sites_by_assignment": ";".join(f"{k}:{v}" for k, v in sorted(how.items()))})
    return pd.DataFrame(rows)


def run_both(fac, q, panel_units, region_of_ba=None):
    """Both placements on the same inputs, and the accounting for each over the union of the units either touches."""
    out = {}
    for name, reading in (("lift_first", LIFT_FIRST), ("earlier_module_reading", EARLIER)):
        sites, records = ck.run(fac, q, panel_units, reading, region_of_ba)
        out[name] = (sites, records)
    cap = ck.capacity_from_sales(q[["utility_id_eia", "state", "year", "total_retail_mwh"]])
    all_sites = site_table(fac)

    def touched(records):
        return {(r["from"], r["state"]) for r in records} | {(r["to"], r["state"]) for r in records}
    u_lift, u_mod = touched(out["lift_first"][1]), touched(out["earlier_module_reading"][1])
    union = u_lift | u_mod
    tables = {}
    for name, (sites, records) in out.items():
        t = account(all_sites, sites, records, cap, union)
        t.insert(0, "reading", name)
        t["carries_one_under_lift_first"] = [(u, s) in u_lift for u, s in zip(t.utility_id_eia, t.state)]
        t["carries_one_under_earlier_module_reading_only"] = [((u, s) in u_mod) and ((u, s) not in u_lift)
                                              for u, s in zip(t.utility_id_eia, t.state)]
        tables[name] = t
    return out, tables, cap, all_sites


def main(write: bool = False) -> dict:
    fac, q, panel_units = ck.read_inputs()
    out, tables, cap, all_sites = run_both(fac, q, panel_units)
    summary = {}
    for name, (sites, records) in out.items():
        reading = LIFT_FIRST if name == "lift_first" else EARLIER
        s = ck.summarize(records, sites)
        t = tables[name]
        slack = arrival_slack(all_sites, sites, records, cap, reading)
        summary[name] = {
            "sites_moved": s["sites_moved"], "units_gaining_or_losing_a_site": s["units_gaining_or_losing_a_site"],
            "stay_no_other_candidate_fits": s["stay_no_other_candidate_fits"],
            "stay_no_other_panel_candidate": s["stay_no_other_panel_candidate"],
            "units_in_table": len(t),
            "class_counts": t["class"].value_counts().to_dict(),
            "near_noise_units": t[t.near_noise][["utility_id_eia", "state"]].values.tolist(),
            "min_arrival_slack_gwh": min((x["slack_gwh"] for x in slack), default=None),
            "arrivals_failing_fsum_recount": [x for x in slack if x["slack_gwh"] < 0],
            "total_assigned_equals_total_final": math.fsum(t.load_as_assigned_gwh) - math.fsum(t.final_load_gwh)}
    over = inventory_over_capacity(fac, cap, panel_units)
    summary["inventory_units_over_capacity_as_assigned"] = len(over)
    print(json.dumps(summary, indent=1, default=str))
    if write:
        both = pd.concat([tables["lift_first"], tables["earlier_module_reading"]], ignore_index=True)
        both.to_csv(OUT_CSV, index=False, float_format="%.9f")
    return {"summary": summary, "tables": tables, "over": over, "placements": out}


if __name__ == "__main__":
    main(write="--write" in sys.argv[1:])
