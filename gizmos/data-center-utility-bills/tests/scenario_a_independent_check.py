"""An independent check of sensitivity scenario A, runner-up placement (Joe, D-107, adopting R2 of D-106).

Written for session 22's reconciliation of the count on file (R2: "380 of the 460 move and 121 units carry different
load") with the count the module built in session 21 gives (379 sites move; 120 units gain or lose a site). Written from
the WORDS of R2 and from `build_inventory.pick_utilities`, apart from `pipeline/analysis/second_number_scenarios.py`,
which this file never imports. It calls no function from `pipeline/`: the inventory, the sales and the market region of
each unit are read here from the quantity files and computed here, so that no code is shared with the module under
test or with the assignment code it calls. The one thing taken from `pipeline/` is a table of data (see below).

Quantity side only. It reads `data/interim/facilities.parquet` (site, state, assignment, candidates, full load) and
`data/interim/panel_quantities.parquet` by the four columns utility_id_eia, state, year, total_retail_mwh and
balancing_authority. It reads no dose, no price, no revenue, no bill and no estimate, and it writes nothing unless a
path is given to main.

R2's rule, word for word: "the site's stored candidate list in stored order (smallest territory polygon first), kept to
panel units, with the utility it is on now moved to the end; sites taken in descending size, ties by site id; each site
takes the first candidate that can hold its full load on top of what that candidate already carries, capacity being
the unit's largest annual retail sales in 2020 to 2025 as `pick_utilities` computes it; a candidate with no sales row is
skipped; if no other candidate fits, the site stays where it is; off the panel is never chosen."

Where a clause reads two ways, each reading is a named switch (Reading). MODULE_READING is the module's rule since
2026-11-19, Joe's rule adopted that day (D-111): "lift the 460 unresolved sites first, keeping all other load counted,
then place them in the adopted descending-size order" (`carried="resolved_only"`: the 460 are left out of the start and
each counts where it lands, a staying site from its own turn). EARLIER_MODULE_READING is the module's reading before
that date (interpretation N-2): every site placed on a unit in the inventory as assigned, the 460 included, updated as
sites move; it is kept as a named variant. Every other setting is a variant to count, not a proposal.

Readings this file makes that R2 does not state (the agent's readings):
* "Size" and "full load" are the inventory's `mw_full` (scaled by the state's factor where the row is permit-based)
  times 8.76, in GWh, the quantity pick_utilities compares with sales.
* The 460 are the sites with a state, in the dose (`in_dose`), not crypto, whose assignment is unresolved under ruling 4
  as amended: an assignment of verified_by_hand, ercot_wires_outside_panel, behind_the_meter or wholesale_direct is
  resolved; "unique" (one territory) is resolved unless the site is in Texas and one of its candidates is a Texas
  panel unit in the ERCOT region; every other assignment is unresolved. A unit's region is the one it most recently
  reports (balancing authority mapped to region), else its state's most common region; only ERCOT matters here, so the
  map is reduced to the ERCOT balancing authority codes (ERCO).
* A panel unit is a (utility, state) pair that has a row in panel_quantities.parquet.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"

VERIFIED_ASSIGNMENTS = ("verified_by_hand", "ercot_wires_outside_panel", "behind_the_meter", "wholesale_direct")
ONE_TERRITORY = "unique"
ERCOT_REGION = "ERCOT"
TEXAS = "TX"
GWH_PER_MW_YEAR = 8.76
SALES_FROM_YEAR = 2020
REFUSED = ("dose", "price", "revenue", "bill", "estimate", "outcome", "slope", "points", "share")


# ================================================================================================================
# The readings
# ================================================================================================================

@dataclasses.dataclass(frozen=True)
class Reading:
    """One reading of each clause that can be read two ways. The defaults are the module's earlier reading (N-2,
    EARLIER_MODULE_READING); the module's rule since 2026-11-19 is MODULE_READING (carried="resolved_only").

    carried         what a candidate "already carries" at the start:
                      "all_assigned"     every site of the inventory on it at its full load (the module's earlier
                                         reading)
                      "in_dose"          only the sites in the dose
                      "not_crypto"       every site but the crypto mines
                      "resolved_only"    every site except the sites being placed (the 460's own load is not
                                         counted on the unit they are on; each is added where it ends): the
                                         module's rule since 2026-11-19 (D-111)
                      "nothing"          nothing (pick_utilities' start); each placed site is added where it ends
    update          True: a site that moves is added to its new unit (and taken off its old one if subtract_source);
                    False: every test is against the start, never updated
    subtract_source True: a moved site's load leaves the unit it was on
    load            "scaled" (mw_full) or "unscaled" (mw_full_raw), for both the size order and the capacity test
    strict          False: carried + load <= capacity fits (pick_utilities); True: <
    tie             "fid" (ascending site id) or "frame" (the inventory's row order, a stable sort)
    """
    carried: str = "all_assigned"
    update: bool = True
    subtract_source: bool = True
    load: str = "scaled"
    strict: bool = False
    tie: str = "fid"

    def __post_init__(self):
        if self.carried not in ("all_assigned", "in_dose", "not_crypto", "resolved_only", "nothing"):
            raise ValueError(f"unknown carried reading {self.carried!r}")
        if self.load not in ("scaled", "unscaled"):
            raise ValueError(f"unknown load reading {self.load!r}")
        if self.tie not in ("fid", "frame"):
            raise ValueError(f"unknown tie reading {self.tie!r}")


EARLIER_MODULE_READING = Reading()                      # the module's reading until 2026-11-19 (N-2)
MODULE_READING = Reading(carried="resolved_only")       # Joe's rule, adopted 2026-11-19 (D-111): lift the 460 first


# ================================================================================================================
# Pure functions
# ================================================================================================================

FLAGS_ALLOWED = ("in_dose",)   # a boolean flag (the site is load-carrying), not a dose


def refuse(frame: pd.DataFrame, what: str) -> None:
    bad = [c for c in frame.columns if c not in FLAGS_ALLOWED and any(r in str(c).lower() for r in REFUSED)]
    if bad:
        raise ValueError(f"{what} carries {bad}; this check takes no dose, price or estimate")


def parse_candidates(value) -> list[int]:
    """The stored candidate list ('a;b;c', or a list) in stored order, repeats dropped, first occurrence kept."""
    if isinstance(value, (list, tuple, np.ndarray)):
        raw = [int(x) for x in value]
    elif isinstance(value, str):
        raw = [int(x) for x in value.split(";") if x.strip() and x.strip().lower() != "nan"]
    else:
        raw = []
    out = []
    for x in raw:
        if x not in out:
            out.append(x)
    return out


def ercot_units(regions_rows: pd.DataFrame, region_of_ba: dict) -> set:
    """(utility, state) units whose region is ERCOT. A unit's region is the region of the balancing authority it reports
    in its latest year with a code the map knows; a unit with no known code in any year takes the most common region
    among its state's units that have one. regions_rows: utility_id_eia, state, year, balancing_authority.
    region_of_ba: the code-to-region table (data, passed in)."""
    r = regions_rows.copy()
    units = r[["utility_id_eia", "state"]].drop_duplicates()
    r["region"] = r.balancing_authority.map(region_of_ba)
    known = r.dropna(subset=["region"])
    last = known.sort_values("year", kind="mergesort").groupby(["utility_id_eia", "state"]).region.last()
    u = units.join(last.rename("region"), on=["utility_id_eia", "state"])
    common = u.dropna(subset=["region"]).groupby("state").region.agg(lambda x: x.value_counts().index[0])
    u["region"] = u.region.fillna(u.state.map(common))
    return {(int(a), str(b)) for a, b, g in zip(u.utility_id_eia, u.state, u.region) if g == ERCOT_REGION}


def is_resolved(assign, state, candidates, ercot: set) -> bool:
    """Ruling 4 as amended, from its words: verified or off-panel statuses are resolved; one territory is resolved
    unless a Texas site has an ERCOT panel unit among its candidates; anything else is unresolved."""
    if assign in VERIFIED_ASSIGNMENTS:
        return True
    if assign == ONE_TERRITORY:
        return not (state == TEXAS and any((c, state) in ercot for c in parse_candidates(candidates)))
    return False


def select_sites(fac: pd.DataFrame, ercot: set, load: str = "scaled") -> pd.DataFrame:
    """R2's 460: load-carrying (in the dose), with a state, not a crypto mine, serving utility unresolved. One row per
    site: fid, state, utility_id_eia, candidates (list), load_gwh, frame_order."""
    refuse(fac, "the inventory")
    col = "mw_full" if load == "scaled" else "mw_full_raw"
    res = np.array([is_resolved(a, s, c, ercot) for a, s, c in
                    zip(fac.utility_assign, fac.state, fac.utility_candidates)], dtype=bool)
    keep = (~res) & fac.in_dose.fillna(False).astype(bool).values & fac.state.notna().values & \
        ~fac.is_crypto.fillna(False).astype(bool).values
    f = fac[keep]
    return pd.DataFrame({"fid": f.fid.astype(str).values, "state": f.state.astype(str).values,
                         "utility_id_eia": f.utility_id_eia.astype(int).values,
                         "candidates": [parse_candidates(c) for c in f.utility_candidates],
                         "load_gwh": f[col].astype(float).values * GWH_PER_MW_YEAR,
                         "frame_order": np.flatnonzero(keep)})


def capacity_from_sales(sales_rows: pd.DataFrame) -> dict:
    """{(utility, state): GWh}: the largest annual total retail sales in 2020 and later, as pick_utilities computes it
    (MWh over 1000; a unit whose sales in those years are all missing has no capacity)."""
    s = sales_rows[sales_rows.year >= SALES_FROM_YEAR]
    out = {}
    for (u, st), g in s.groupby(["utility_id_eia", "state"]):
        v = g.total_retail_mwh.dropna()
        if len(v):
            out[(int(u), str(st))] = float(v.max()) / 1000.0
    return out


def carried_at_start(fac: pd.DataFrame, placed_fids: set, reading: Reading) -> dict:
    """{(utility, state): GWh} what every unit carries before any site is placed, under `reading.carried`."""
    if reading.carried == "nothing":
        return {}
    col = "mw_full" if reading.load == "scaled" else "mw_full_raw"
    f = fac[fac.utility_id_eia.notna() & fac.state.notna()]
    if reading.carried == "in_dose":
        f = f[f.in_dose.fillna(False).astype(bool)]
    elif reading.carried == "not_crypto":
        f = f[~f.is_crypto.fillna(False).astype(bool)]
    elif reading.carried == "resolved_only":
        f = f[~f.fid.astype(str).isin(placed_fids)]
    out: dict = {}
    for u, st, mw in zip(f.utility_id_eia, f.state, f[col]):
        k = (int(u), str(st))
        out[k] = out.get(k, 0.0) + (0.0 if pd.isna(mw) else float(mw) * GWH_PER_MW_YEAR)
    return out


def place(sites: pd.DataFrame, carried: dict, capacity: dict, panel_units: set, reading: Reading = MODULE_READING) -> list:
    """R2's runner-up placement, written from its words. Returns one record per site: fid, state, from, to, moved,
    why ("moved" | "no_other_panel_candidate" | "no_other_candidate_fits"), others (the candidates tried, in order).

    The start state is `carried` (not changed in place). With reading.carried in ("resolved_only", "nothing") the sites
    being placed are not in the start, so each is added where it ends, moved or not."""
    refuse(sites, "the sites")
    if sites.fid.duplicated().any():
        raise ValueError("a site appears twice")
    start = dict(carried)
    now_load = dict(start)
    add_where_it_ends = reading.carried in ("resolved_only", "nothing")
    key = ["load_gwh", "fid"] if reading.tie == "fid" else ["load_gwh", "frame_order"]
    order = sites.sort_values(key, ascending=[False, True], kind="mergesort")
    out = []
    for r in order.itertuples(index=False):
        st, here, g = r.state, int(r.utility_id_eia), float(r.load_gwh)
        panel = [c for c in parse_candidates(r.candidates) if (c, st) in panel_units]
        others = [c for c in panel if c != here]          # the unit it is on goes to the end and is never a move
        dest = None
        for c in others:
            if (c, st) not in capacity:
                continue                                  # no sales row: skipped
            have = (now_load if reading.update else start).get((c, st), 0.0)
            fits = have + g < capacity[(c, st)] if reading.strict else have + g <= capacity[(c, st)]
            if fits:
                dest = c
                break
        if dest is None:
            why = "no_other_panel_candidate" if not others else "no_other_candidate_fits"
            if add_where_it_ends:
                now_load[(here, st)] = now_load.get((here, st), 0.0) + g
            out.append({"fid": r.fid, "state": st, "from": here, "to": here, "moved": False, "why": why,
                        "others": others})
            continue
        now_load[(dest, st)] = now_load.get((dest, st), 0.0) + g
        if reading.subtract_source and not add_where_it_ends:
            now_load[(here, st)] = now_load.get((here, st), 0.0) - g
        out.append({"fid": r.fid, "state": st, "from": here, "to": dest, "moved": True, "why": "moved",
                    "others": others})
    return out


COUNTS = ("units_gaining_or_losing_a_site", "units_whose_placed_load_differs", "utility_ids_gaining_or_losing_a_site",
          "units_gaining_a_site", "units_losing_a_site", "units_gaining_or_losing_including_stayers_current_unit")


def count_units(records: list, sites: pd.DataFrame, how: str = "units_gaining_or_losing_a_site", tol: float = 1e-9) -> set:
    """The units a placement changes, counted one of several plain ways (none of them a rule):
    units_gaining_or_losing_a_site   (utility, state) units that are the from or the to of a moved site
    units_whose_placed_load_differs  units whose summed full load of placed sites changes by more than tol GWh
    utility_ids_gaining_or_losing_a_site  the same as the first, a utility counted once over its states
    units_gaining_a_site / units_losing_a_site   one side only
    units_gaining_or_losing_including_stayers_current_unit  the first, plus the unit of every site that stays"""
    moved = [r for r in records if r["moved"]]
    if how == "units_gaining_or_losing_a_site":
        return {(r["from"], r["state"]) for r in moved} | {(r["to"], r["state"]) for r in moved}
    if how == "utility_ids_gaining_or_losing_a_site":
        return {r["from"] for r in moved} | {r["to"] for r in moved}
    if how == "units_gaining_a_site":
        return {(r["to"], r["state"]) for r in moved}
    if how == "units_losing_a_site":
        return {(r["from"], r["state"]) for r in moved}
    if how == "units_gaining_or_losing_including_stayers_current_unit":
        return count_units(records, sites) | {(r["from"], r["state"]) for r in records if not r["moved"]}
    if how == "units_whose_placed_load_differs":
        g = dict(zip(sites.fid, sites.load_gwh))
        net: dict = {}
        for r in moved:
            net[(r["from"], r["state"])] = net.get((r["from"], r["state"]), 0.0) - g[r["fid"]]
            net[(r["to"], r["state"])] = net.get((r["to"], r["state"]), 0.0) + g[r["fid"]]
        return {k for k, v in net.items() if abs(v) > tol}
    raise ValueError(f"unknown count {how!r}")


def summarize(records: list, sites: pd.DataFrame) -> dict:
    out = {"sites": len(records), "sites_moved": sum(r["moved"] for r in records),
           "stay_no_other_panel_candidate": sum(r["why"] == "no_other_panel_candidate" for r in records),
           "stay_no_other_candidate_fits": sum(r["why"] == "no_other_candidate_fits" for r in records)}
    for how in COUNTS:
        out[how] = len(count_units(records, sites, how))
    return out


# ================================================================================================================
# Inputs (quantity side) and main
# ================================================================================================================

FAC_COLUMNS = ["fid", "state", "utility_id_eia", "utility_assign", "utility_candidates", "in_dose", "is_crypto",
               "mw_full", "mw_full_raw"]


def read_inputs(interim: Path = INTERIM):
    fac = pd.read_parquet(interim / "facilities.parquet", columns=FAC_COLUMNS)
    q = pd.read_parquet(interim / "panel_quantities.parquet",
                        columns=["utility_id_eia", "state", "year", "total_retail_mwh", "balancing_authority"])
    panel_units = {(int(u), str(s)) for u, s in q[["utility_id_eia", "state"]].drop_duplicates().itertuples(index=False)}
    return fac, q, panel_units


def region_table() -> dict:
    """The balancing-authority-to-region table, read as data from pipeline/electricity/market_region.py."""
    sys.path.insert(0, str(ROOT))
    from pipeline.electricity.market_region import REGION_OF_BA
    return dict(REGION_OF_BA)


def run(fac, q, panel_units, reading: Reading = MODULE_READING, region_of_ba: dict | None = None):
    ercot = ercot_units(q[["utility_id_eia", "state", "year", "balancing_authority"]],
                        region_table() if region_of_ba is None else region_of_ba)
    sites = select_sites(fac, ercot, reading.load)
    cap = capacity_from_sales(q[["utility_id_eia", "state", "year", "total_retail_mwh"]])
    carried = carried_at_start(fac, set(sites.fid), reading)
    records = place(sites, carried, cap, panel_units, reading)
    return sites, records


def main(out_path: Path | None = None) -> dict:
    fac, q, panel_units = read_inputs()
    sites, records = run(fac, q, panel_units, MODULE_READING)
    s = summarize(records, sites)
    moves = [{"fid": r["fid"], "state": r["state"], "from": r["from"], "to": r["to"]} for r in records if r["moved"]]
    stays = [{"fid": r["fid"], "state": r["state"], "on": r["from"], "why": r["why"]} for r in records if not r["moved"]]
    units = sorted(f"{u}:{st}" for u, st in count_units(records, sites))
    print(json.dumps(s, indent=1))
    result = {"summary": s, "moves": moves, "stays": stays, "units_gaining_or_losing_a_site": units}
    if out_path is not None:
        Path(out_path).write_text(json.dumps(result, indent=1) + "\n")
    return result


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
