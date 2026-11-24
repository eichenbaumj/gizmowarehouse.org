#!/usr/bin/env python3
"""Write the assignment-evidence table for Joe (D-46, ruling 4): one section per host, its sites and its four cases.

Reads data/frozen/assignment_evidence.json and assignment_evidence_sites.csv. Load and sales only.

Run:  python3 -I pipeline/facilities/assignment_table.py docs/gate1/<name>.md "<title>"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "data" / "frozen"

PLACED = {"verified_by_hand": "verified by hand", "unique": "one territory, outside ERCOT (assumed)",
          "smallest_polygon": "map: smallest of several territories", "next_larger_load_feasible": "map: next larger territory",
          "fallback_largest_flagged": "map: fallback, nothing fit"}
YEAR = {"first_generator_permit_plus_lag": "first generator permit plus one", "verified_public_source": "a sourced page or record",
        "operator_reported_energy": "the operator's reported electricity", "epoch_timeline": "Epoch's timeline",
        "osm_start_date_tag": "an OpenStreetMap tag", "undated": "undated"}
SIZE = {"generator_capacity_x_kappa": "generator capacity x 0.5", "verified_public_figure": "a sourced public figure",
        "operator_reported_energy": "the operator's reported electricity", "epoch_timeline": "Epoch's timeline", "osm_tag": "an OpenStreetMap tag"}
HISTORY = {"three_year_ramp": "three-year ramp", "verified_phases": "building-record or verified steps", "single_building_record": "one building (county record)",
           "operator_reported_energy": "reported year by year", "epoch_timeline": "Epoch's timeline",
           "epoch_timeline_after_an_assumed_line": "Epoch's timeline after an assumed line"}


def label(h: dict) -> str:
    st = h["utility"].split(":")[1]
    return h["name"] if f"({st})" in h["name"] else f"{h['name']} ({st})"


def main(out: str, title: str) -> int:
    rep = json.loads((FROZEN / "assignment_evidence.json").read_text())
    hosts = [h for h in rep["thresholds"]["2%"]["hosts"] if h["in_the_headline_set_before_this_test"]]
    sites = pd.read_csv(FROZEN / "assignment_evidence_sites.csv")
    keep = sum(h["verdict"] == "keeps its place" for h in hosts)
    L = [f"# {title}", "",
         "Load and sales only; no price was read. Rule: D-46, ruling 4 as amended. A site's serving utility is resolved if it was "
         "verified by hand, or if the site lies in one territory only and is outside ERCOT (an assumption). Lower case: every unresolved "
         "site on the host is taken off. Upper case: every unresolved site that lists the host as a candidate territory is counted on it. "
         "Each is computed as built and with no anchoring, over every year from 2001. These are conservative envelopes: a site that could "
         "be on two utilities is counted on each in its own upper case, and the upper case is not checked against what the host's sales could carry.", "",
         f"**{keep} of {len(hosts)} hosts keep their place in all four cases** (the same group and a first crossing within one year). "
         "The 2% threshold. Hosts: the headline set under D-46's rulings 1 to 3 and the six Texas hosts.", "",
         "| Host | First crossing | Lower case (as built / no anchoring) | Upper case (as built / no anchoring) | Sites on it (unresolved) | Unresolved sites elsewhere that list it | Holds? |",
         "|---|---|---|---|---|---|---|"]
    for h in hosts:
        L.append(f"| {label(h)} | {h['first_crossing_as_built']} | {h['lower_as_built']} / {h['lower_no_anchoring']} | "
                 f"{h['upper_as_built']} / {h['upper_no_anchoring']} | {h['sites_on_it']} ({h['unresolved_on_it']}) | "
                 f"{h['unresolved_sites_elsewhere_that_list_it']} | {'yes' if h['verdict'] == 'keeps its place' else 'no'} |")
    L += ["", "## Host by host", "",
          "A site marked * is one of the largest sites in the crossing year, taken until they reach the threshold. That list is the order "
          "of verification, not a definition of what fixes the date. MW is the site's load in the host's crossing year as built; the share is of the 2% threshold.", ""]
    for h in hosts:
        s = sites[sites.host == h["utility"]].sort_values(["now_on", "mw_in_the_crossing_year"], ascending=[True, False],
                                                         key=lambda c: c.ne("this host") if c.name == "now_on" else c)
        L += [f"### {label(h)}, first crossing {h['first_crossing_as_built']}", "",
              f"Lower case {h['lower_as_built']} as built, {h['lower_no_anchoring']} with no anchoring. Upper case {h['upper_as_built']} as built, "
              f"{h['upper_no_anchoring']} with no anchoring. {'Keeps its place.' if h['verdict'] == 'keeps its place' else 'Does not hold: ' + h['verdict'] + '.'}", "",
              "| Site | Now on | Serving utility | MW in crossing year (share of threshold) | Start year rests on | Size rests on | Load history |", "|---|---|---|---|---|---|---|"]
        for r in s.itertuples():
            star = " *" if r.determining_site else ""
            scale = f", state factor {r.state_scale:g}" if r.size_rests_on == "generator_capacity_x_kappa" else ""
            flag = "; permit filed as an update to an existing source" if r.permit_filed_as_an_update_to_an_existing_source else ""
            L.append(f"| {r.site_label} (`{r.site}`){star} | {r.now_on} | {'resolved' if r.resolved else 'UNRESOLVED'}: {PLACED.get(r.how_placed, r.how_placed)} | "
                     f"{r.mw_in_the_crossing_year:g} ({r.share_of_threshold_in_the_crossing_year:.0%}) | {r.start_year}: {YEAR.get(r.year_rests_on, r.year_rests_on)}{flag} | "
                     f"{r.mw_now:g} MW now: {SIZE.get(r.size_rests_on, r.size_rests_on)}{scale} | {HISTORY.get(r.load_history, r.load_history)} |")
        L.append("")
    Path(ROOT / out).write_text("\n".join(L) + "\n")
    print("written", out, "| hosts", len(hosts), "| hold", keep, "| site rows", int(sites.host.isin([h["utility"] for h in hosts]).sum()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
