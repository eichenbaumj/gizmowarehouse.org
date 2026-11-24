#!/usr/bin/env python3
"""Write job V's results for Joe: what the assignment check (D-46 ruling 4, D-48) did to each host, and support.

Compares the hosts as they stood before ruling 4 was applied to anyone (data/frozen/headline_set_before_ruling_4.csv,
the list frozen at job R1) with the lists as they stand now. Load and sales only.

Run:  python3 -I pipeline/facilities/assignment_results.py docs/gate1/<name>.md      (after treatment_bounds.py, assignment.py, design.py)
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "data" / "frozen"
VER = ROOT / "pipeline" / "facilities" / "verified"
KEY = ["utility_id_eia", "state"]


# Why each host that left the cohorts left, in a line. The verifications themselves are in verified/batch_v_*.json.
NO_LONGER = {
    (9094, "AL"): "Meta says its campus is served directly by TVA, with a small Huntsville Utilities contract for auxiliary power; its 866 GWh never showed in the city's sales",
    (2144, "MA"): "its one site is Digital Realty's building in Needham, which Eversource lists as its own town; the map had put it on Braintree",
    (13679, "MA"): "its one site is Congruity360 in Fall River, a National Grid customer; the map had put it on North Attleborough",
    (11272, "MT"): "both of its sites are Crusoe generator stations on oil-well pads: state air permits say the engines burn pad gas to power the site",
    (12199, "MT"): "all four of its sites are Crusoe generator stations on oil-well pads: state air permits say the engines burn pad gas to generate the site's electricity",
}


def main(out: str) -> int:
    before = pd.read_csv(FROZEN / "headline_set_before_ruling_4.csv")
    before = before[before.threshold == "2%"]
    before = before[before.in_headline_set | before.why_not_in_the_headline_set.fillna("").str.contains("ruling 3")]
    now = pd.read_csv(FROZEN / "headline_set.csv")
    now = now[now.threshold == "2%"].set_index(KEY)
    ev = {h["utility"]: h for h in json.loads((FROZEN / "assignment_evidence.json").read_text())["thresholds"]["2%"]["hosts"]}
    bounds = json.loads((FROZEN / "treatment_bounds.json").read_text())["thresholds"]["2%"]
    sup = json.loads((FROZEN / "design_support.json").read_text())["sets"]["headline_set"]
    sites = pd.read_csv(FROZEN / "assignment_evidence_sites.csv")
    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet").set_index("fid")
    verified = [r for f in sorted(glob.glob(str(VER / "batch_v_*.json"))) for r in json.loads(Path(f).read_text())]

    rows, n_in, n_unsettled, n_gone = [], 0, 0, 0
    for r in before.itertuples():
        k = (r.utility_id_eia, r.state)
        if k not in now.index:
            n_gone += 1
            rows.append((r.name, r.first_crossing, "No longer a host on the inventory",
                         NO_LONGER.get(k, "its site or sites were verified onto another utility, onto no utility, or as served at wholesale (see the verifications below)")))
        elif bool(now.at[k, "in_headline_set"]):
            n_in += 1
            e = ev[f"{k[0]}:{k[1]}"]
            rows.append((r.name, r.first_crossing, "In", f"holds in all four cases; {e['sites_on_it']} sites on it, {e['unresolved_on_it']} unresolved"))
        else:
            n_unsettled += 1
            e = ev.get(f"{k[0]}:{k[1]}", {})
            why = str(now.at[k, "why_not_in_the_headline_set"]).replace("D-46, ruling 4: ", "")
            rows.append((r.name, r.first_crossing, "Unsettled on assignment", f"{why}; {e.get('unresolved_on_it', '?')} of its {e.get('sites_on_it', '?')} sites unresolved, "
                         f"{e.get('unresolved_sites_elsewhere_that_list_it', 0)} unresolved sites elsewhere list it"))
    h = bounds["sets"]["headline_set"]
    c = bounds["comparison_utilities"]
    L = ["# Job V: who is in after the assignment check (2026-11-14)", "",
         "Load and sales only; no price was read, no tariff collected, the plan is not frozen. Rules: D-46 ruling 4 as amended, and D-48 (what counts as a page that names the delivering utility), "
         "which was written and committed before any page was opened or applied.", "",
         f"**The headline set is {h['after']} hosts.** Of the 31 hosts that went into this check (the 25 of D-46 and the six Texas hosts): **{n_in} are in, {n_unsettled} are unsettled on assignment, "
         f"and {n_gone} are no longer hosts on the inventory at all.** No count is a target; this is below the 20 at which job U waits for Joe.", "",
         "What 'unsettled' means here: the host's first crossing rests on sites the map placed among several territories, and no page that can be cited names who delivers to them. "
         "It does not mean the host is wrong. Most of the unsettled hosts are small municipal systems and cooperatives with one or two sites; for the five Texas cooperatives every lookup "
         "pointed, on directory listings only, to a wires company outside the panel.", "",
         "## The 31 hosts", "", "| Host | First crossing | Now | Why |", "|---|---|---|---|"]
    order = {"In": 0, "Unsettled on assignment": 1, "No longer a host on the inventory": 2}
    for name, y, status, why in sorted(rows, key=lambda x: (order[x[2]], x[0])):
        L.append(f"| {name} | {y} | {status} | {why} |")
    L += ["", "## Support for the hosts that are in", "",
          "Two counts for each host (D-46, second addendum). Pool: eligible comparison utilities in the host's sub-experiment that are in its market region that year. "
          "Matched: of its ten matched comparison utilities (matched once, on the reference year), how many are in its region that year. The second describes the regression. "
          "The full table for every window year is `data/frozen/design_support.csv`.", "",
          "| Host | First crossing | Region | Pool: reference year | Pool: event year 2 | Pool: event year 3 | Matched: reference year | Matched: event year 2 | Matched: event year 3 |", "|---|---|---|---|---|---|---|---|---|"]
    for x in sorted(sup["hosts"], key=lambda x: x["name"]):
        p_, m_ = x["pool"], x["matched"]
        L.append(f"| {x['name']} | {x['cohort']} | {x['region_in_the_reference_year']} | {p_['reference_year']} | {p_['event_year_2']} | {p_['event_year_3']} | "
                 f"{m_['reference_year']} of {x['matched_set_size']} | {m_['event_year_2']} | {m_['event_year_3']} |")
    thin = sup["hosts_with_fewer_than_ten_eligible_in_their_region_in_the_reference_year"]
    thin2 = sup["hosts_with_fewer_than_ten_matched_in_their_region_in_event_year_2_or_3"]
    L += ["", f"Hosts with fewer than ten eligible in their region in the reference year: {', '.join(thin) if thin else 'none'}. "
          f"Hosts with fewer than ten of their matched set in their region in event year 2 or 3: {', '.join(thin2) if thin2 else 'none'}. "
          f"Hosts dropped for lacking residential sales in a window year: {len(sup['hosts_dropped'])}.", "",
          "## Comparison utilities", "",
          f"{c['keep_their_place']:,} of {c['under_0.5pct_as_built_and_not_set_aside']:,} keep their place ({c['above_the_customer_floor_keep_their_place']:,} of "
          f"{c['above_the_customer_floor_before']:,} above the customer floor). {len(c['do_not'])} fail between the built and unanchored inventories; "
          f"{c['fail_the_upper_case_of_ruling_4']} more ({c['fail_the_upper_case_above_the_customer_floor']} above the floor) fail the upper case, where every unresolved site that lists them "
          f"as a candidate territory is counted on them. Above the floor by region, those that fail the upper case: "
          + ", ".join(f"{k} {v}" for k, v in c["fail_the_upper_case_by_region_above_the_floor"].items()) + ".", "",
          "## What was verified", "",
          "Every page below was opened by the session model with a plain client and the words around the quote read. Evidence kinds are D-48's.", "",
          "| Site | Delivering utility | Kind of evidence | The period the page speaks to | Source |", "|---|---|---|---|---|"]
    for v in verified:
        util = v["serving_utility"] if v["service_arrangement"] == "retail" else f"{v['serving_utility']} ({v['service_arrangement'].replace('_', ' ')})"
        L.append(f"| {v['site_name']} (`{v['fid']}`) | {util} | {v['utility_evidence_kind']} | {v['utility_evidence_period']} | {v['utility_source_url']} |")
    kinds = pd.Series([v["utility_evidence_kind"] for v in verified]).value_counts()
    L += ["", f"{len(verified)} sites: " + ", ".join(f"{n} by {k}" for k, n in kinds.items()) + ". "
          f"On the inventory now {int((fac.utility_assign == 'verified_by_hand').sum())} sites are verified on a panel utility and "
          f"{int(fac.utility_assign.isin(['behind_the_meter', 'wholesale_direct', 'ercot_wires_outside_panel']).sum())} are verified off the panel.", "",
          "Findings that could not be applied, each with the reason, are in `pipeline/facilities/leads/serving_utility_leads.csv`. Three are one step short and a person could close them: "
          "Bentonville (the article that ties Walmart's site to the city utility is readable only in its first sentence without a subscription), the two State Farm-area sites in Olathe "
          "(the local map says Evergy; the city's own pages refuse a plain client), and Elk River (the utility's own packet describes two existing data centers and names neither).", ""]
    Path(ROOT / out).write_text("\n".join(L) + "\n")
    print("written", out, "| in", n_in, "| unsettled", n_unsettled, "| no longer hosts", n_gone)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
