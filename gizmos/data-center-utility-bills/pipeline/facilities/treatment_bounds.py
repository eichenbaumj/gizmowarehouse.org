#!/usr/bin/env python3
"""Treatment-history bounds: how far each utility's place in the design rests on things the inventory does not know.

Touches NO price data. Inputs are the built inventory, the quantity side of the
EIA-861 panel, and the state totals the anchoring uses. The rules are in
docs/DECISIONS.md, D-44, written before this was run.

T1. States where the inventory falls short of the state total. Three readings:

  A  no anchoring: measured site-years as they are, every other site at its
     unscaled estimate. Right only if the inventory is complete.
  B  the cap as now: the built inventory (the proportional-allocation assumption).
  C  the remainder left unassigned: reading A, plus a state remainder for 2024
     that no site is raised to absorb. Each utility, alone, gets a lowest
     exposure (none of it) and a highest feasible exposure (as much as its own
     non-residential sales allow), and from those an earliest and a latest
     possible first crossing.

  D-44 let a utility keep its place only if all three agreed. Joe ruled on what
  that found (D-46): a utility keeps its place if readings A and B agree, in
  every state, the ones whose estimates are scaled down included
  (`keeps_its_place`). Reading C is still computed and is reported beside
  every estimate as what the inventory cannot rule out
  (`with_the_remainder_unassigned`); it no longer decides who is in.

  A utility also has to keep its place whichever way its unresolved sites fall
  (ruling 4 as amended; pipeline/facilities/assignment.py): its whole history
  recomputed with every unresolved site on it taken off and with every
  unresolved site that lists it as a candidate territory counted on it, as
  built and with no anchoring. The Texas hosts ruling 3 held face that rule
  like every other host.

T2. The six building-record histories filled over five years a step instead of three.
T3. Epoch rows already running before Epoch's first entry: nothing, the working line, the first entry's level.
T4. A measured site against its utility's own non-residential sales.
T5. Operator-reported sites in the unobserved years before their first figure.

Step D (docs/gate1/step-d-inventory-design-2026-11-18.md and Joe's rulings in its addendum): on a rebuilt inventory
(facilities.parquet carries `date_rule`), timing.py's place test is read in (`step_d_reasons`). A utility whose place
changes within its dated intervals or the crossed three- and five-year screen, with every unresolved site where the
inventory has it, does not keep its place; one the enumeration cannot settle (an undefined reference, the envelope over
the ceiling) is unsettled and is out too; one that fails only jointly with its unresolved sites joins ruling 4's list. One whose outcome differs under a stress scenario
(R4) is out with its own reason and in a list of its own.
A utility a LOAD UNKNOWN site reaches (directly or through its state's factor) is judged by the enumeration, never by
the frame: its frame-based D-46 and ruling 4 verdicts are replaced by timing.py's where timing.py keeps it.

Writes data/frozen/treatment_bounds.json, data/frozen/treatment_bounds_by_utility.csv and
data/frozen/headline_set.csv (every cohort utility, which sets it is in, and why not).
power_simulation.set_aside() reads the lists in treatment_bounds.json.

Run:  python3 -I pipeline/facilities/treatment_bounds.py     (after build_inventory.py, dating_sensitivity.py, buildout.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import assignment, buildout, site_energy  # noqa: E402

INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"

KEY = ["utility_id_eia", "state"]
YEARS = list(range(2001, 2026))
THRESHOLDS = (0.02, 0.05)
COHORTS = (2011, 2022)
MOVE_TOLERANCE = 2          # D-28's: a cohort crossing that moves by this many years or more has changed place
CLEAN_BELOW = 0.005         # comparison utilities: load share under 0.5% in every panel year
CRYPTO_LIMIT = 0.02
REMAINDER_YEAR = 2024       # the year the state total is read for
SLOW_OCCUPANCY = 5          # years a building-record step takes to fill in the slower alternative (the inventory uses 3)
BUILDING_RECORD_SITES = {   # settled between the two modeled paths, not verified load histories (D-41)
    "bi:677-0": "Google, Lenoir, North Carolina",
    "bi:941-0": "eBay, South Jordan, Utah",
    "bi:943-0": "Aligned, West Jordan, Utah",
    "bi:795-0": "Amazon, Hilliard, Ohio",
    "bi:12-0": "CyrusOne, Chandler, Arizona",
    "bi:31-0": "Iron Mountain, Phoenix, Arizona",
}
NOT_YET_ONLINE = "not yet online"   # how the operator's table marks an observed zero (T5)
HELD_STATE = "TX"                   # D-46, ruling 3: the state whose hosts were held; reported apart


# ---- small pieces -----------------------------------------------------------------

def group(first_year) -> str:
    if first_year is None or pd.isna(first_year):
        return "never"
    return "early" if first_year < COHORTS[0] else ("cohort" if first_year <= COHORTS[1] else "late")


def same_place(a, b) -> bool:
    """D-28's tolerance: the same group, and for a cohort utility a first crossing within one year."""
    if group(a) != group(b):
        return False
    return group(a) != "cohort" or abs(a - b) < MOVE_TOLERANCE


def matrix(fy: pd.DataFrame, units: pd.MultiIndex) -> pd.DataFrame:
    """Utility-by-year GWh of data center load from facility-year rows (MW)."""
    g = (fy.groupby(KEY + ["year"]).mw.sum() * 8.76).unstack("year")
    return g.reindex(index=units, columns=YEARS).fillna(0.0)


def first_crossing(gwh: pd.DataFrame, base: pd.Series, theta: float) -> pd.Series:
    """First year each utility's load reaches theta of its base; NaN where it never does or has no base."""
    hit = gwh.ge(theta * base.reindex(gwh.index), axis=0) & base.reindex(gwh.index).gt(0).values[:, None]
    years = np.array(gwh.columns, dtype=float)
    first = np.where(hit.values.any(axis=1), years[hit.values.argmax(axis=1)], np.nan)
    return pd.Series(first, index=gwh.index)


def max_share(gwh: pd.DataFrame, base: pd.Series) -> pd.Series:
    """Largest load share in any panel year. Zero where there is no load; NaN where there is load and no base to divide by."""
    top = gwh.max(axis=1)
    return (top / base.reindex(gwh.index)).where(top > 0, 0.0)


# ---- T1 ---------------------------------------------------------------------------

def state_remainders(anchor: pd.DataFrame) -> pd.DataFrame:
    """Per state: the total, measured load, unscaled estimates, and what is left over (never negative)."""
    t = anchor.set_index("state")[["epri_twh", "epoch_twh", "permit_twh", "raw_factor", "factor", "flag"]].rename(
        columns={"epoch_twh": "measured_twh", "permit_twh": "unscaled_estimates_twh"})
    t["remainder_twh"] = (t.epri_twh - t.measured_twh - t.unscaled_estimates_twh).clip(lower=0.0)
    t["kind"] = np.select(
        [t.remainder_twh > 0, (t.measured_twh >= t.epri_twh) & (t.measured_twh > 0)],
        ["falls_short", "measured_load_at_or_above_the_total"], "estimates_scaled_down")
    t["at_the_cap"] = t.raw_factor > t.factor
    return t


def ceiling(a_gwh: pd.DataFrame, nonres_gwh: pd.DataFrame, remainder_gwh: pd.Series) -> pd.DataFrame:
    """Reading C's highest feasible exposure: reading A plus the most hidden load the utility could be carrying.

    Through the remainder year hidden load is at most the smaller of the state's remainder and the utility's
    non-residential sales less reading A's load. After it, the remainder may have grown by as much as the
    utility's own non-residential sales did. Where the utility reports no sales for a year the remainder
    alone bounds it. `remainder_gwh` is per utility (its state's).
    """
    r = remainder_gwh.reindex(a_gwh.index).fillna(0.0)
    room = (nonres_gwh.reindex(index=a_gwh.index, columns=a_gwh.columns) - a_gwh).clip(lower=0.0)
    cap = pd.DataFrame(np.repeat(r.values[:, None], a_gwh.shape[1], axis=1), index=a_gwh.index, columns=a_gwh.columns)
    for y in [c for c in a_gwh.columns if c > REMAINDER_YEAR]:
        growth = (nonres_gwh[y] - nonres_gwh[REMAINDER_YEAR]).reindex(a_gwh.index).clip(lower=0.0).fillna(0.0)
        cap[y] = r + growth
    hidden = cap.where(room.isna(), np.minimum(cap, room))
    hidden = hidden.mul(r.gt(0).astype(float), axis=0)
    return a_gwh + hidden


def largest_rise(nonres_gwh: pd.DataFrame) -> pd.Series:
    """The largest rise in non-residential sales between any earlier and any later panel year (zero if it never rose)."""
    v = nonres_gwh.values.astype(float)
    best = np.zeros(len(v))
    low = np.full(len(v), np.inf)
    for j in range(v.shape[1]):
        col = v[:, j]
        ok = ~np.isnan(col)
        best = np.where(ok & np.isfinite(low), np.maximum(best, col - low), best)
        low = np.where(ok, np.minimum(low, col), low)
    return pd.Series(best, index=nonres_gwh.index)


def keeps_its_place(row: dict, theta_key: str) -> tuple[str, str]:
    """(place under reading B, verdict) for one utility at one threshold, under D-46's rulings 1 and 2.

    The test is readings A and B and D-28's tolerance, in every state: the same group and, for a cohort
    utility, a first crossing within one year; a comparison utility under 0.5% throughout on both.
    Verdict is "keeps its place" or the reason it does not. Reading C does not enter.
    """
    yb, ya = row[f"b_{theta_key}"], row[f"a_{theta_key}"]
    place = group(yb)
    if row.get(f"settled_by_its_own_count_{theta_key}"):
        return row[f"settled_by_its_own_count_{theta_key}"], "keeps its place (judged on the utility's own count, D-34)"
    if place == "cohort":
        if not same_place(yb, ya):
            return place, f"no anchoring puts the first crossing at {fmt(ya)} against {fmt(yb)}"
        return place, "keeps its place"
    if place == "early":
        if group(ya) != "early":
            return place, f"no anchoring puts the first crossing at {fmt(ya)}, not before {COHORTS[0]}"
        return place, "keeps its place"
    if place == "late":
        return place, "not tested (a late host is in no estimate)"
    if row["clean_b"]:
        if not row["max_share_a"] < CLEAN_BELOW:
            return "comparison", f"no anchoring puts its load share at {row['max_share_a']:.1%}"
        return "comparison", "keeps its place"
    return "neither", "not tested (neither a host nor under 0.5% throughout)"


def with_the_remainder_unassigned(row: dict, theta_key: str) -> str:
    """D-44's reading C for one utility, in words. Reported beside every estimate; it decides nothing (D-46, ruling 1).

    "holds" if the utility's place would be the same whatever share of its state's remainder it carried, else
    what the remainder could do to it. Empty for a utility the test does not reach.
    """
    yb, early, late = row[f"b_{theta_key}"], row[f"c_earliest_{theta_key}"], row[f"c_latest_{theta_key}"]
    place = group(yb)
    if not row["state_remainder_gwh"] > 0:
        return "the state has no remainder" if place in ("cohort", "early") or row["clean_b"] else ""
    if place == "cohort":
        if not same_place(yb, early):
            return f"the first crossing could be as early as {fmt(early)} against {fmt(yb)}"
        if not same_place(yb, late):
            return f"the first crossing could be as late as {fmt(late)} against {fmt(yb)}"
        return "holds"
    if place == "early":
        return "holds" if group(late) == "early" else f"the first crossing could be as late as {fmt(late)}"
    if place == "never" and row["clean_b"]:
        return "holds" if row["max_share_c"] < CLEAN_BELOW else "the state's remainder could put it at 0.5% or more"
    return ""


def fmt(y):
    return "never" if y is None or pd.isna(y) else int(y)


# ---- T2, T3, T5: one history changed at a time --------------------------------------

def swap(fy: pd.DataFrame, where: pd.DataFrame, paths: dict[str, dict[int, float]]) -> pd.DataFrame:
    """Facility-year rows with the named sites' loads replaced by `paths[fid][year]` (MW)."""
    keep = fy[~fy.fid.isin(paths)][["fid"] + KEY + ["year", "mw"]]
    rows = [(fid, where.utility_id_eia[fid], where.state[fid], y, mw)
            for fid, p in paths.items() if fid in where.index for y, mw in p.items() if mw > 0]
    return pd.concat([keep, pd.DataFrame(rows, columns=keep.columns)], ignore_index=True)


def phased_mw(mw_full: float, phases: list[tuple[int, float]], year: int, ramp_years: int) -> float:
    mw, prev = 0.0, 0.0
    for y, share in phases:
        mw += buildout.ramp_mw(mw_full * (share - prev), y, year, ramp_years)
        prev = share
    return mw


def compare(units: pd.MultiIndex, base: pd.Series, built: pd.DataFrame, alts: dict[str, pd.DataFrame], affected: set,
            names: pd.Series) -> list[dict]:
    """For each affected utility: first crossing as built and under each alternative, at both thresholds, and whether its place holds."""
    out = []
    mats = {k: matrix(v, units) for k, v in alts.items()}
    for k in sorted(affected):
        row = {"utility": f"{int(k[0])}:{k[1]}", "name": names.get(k), "place_holds_by_threshold": {}}
        clean_b = bool(max_share(built.loc[[k]], base).iloc[0] < CLEAN_BELOW)
        clean_alt = all(bool(max_share(m.loc[[k]], base).iloc[0] < CLEAN_BELOW) for m in mats.values())
        row["under_0.5pct_throughout_as_built"], row["under_0.5pct_throughout_under_every_alternative"] = bool(clean_b), bool(clean_alt)
        for theta in THRESHOLDS:
            t = f"{theta:.0%}"
            yb = first_crossing(built.loc[[k]], base, theta).iloc[0]
            row[f"as_built_{t}"] = fmt(yb)
            holds = clean_b == clean_alt
            for name, m in mats.items():
                ya = first_crossing(m.loc[[k]], base, theta).iloc[0]
                row[f"{name}_{t}"] = fmt(ya)
                holds = holds and same_place(yb, ya)
            row["place_holds_by_threshold"][t] = bool(holds)
        out.append(row)
    return out


# ---- step D ---------------------------------------------------------------------------------------------

def step_d_reasons(timing_rows: list[dict], theta: float, units, unknown_affected: set, why: dict, why4: dict) -> dict:
    """Fold timing.py's verdicts into `why` (does not keep its place) and `why4` (ruling 4), in place. Returns the lists
    step D adds to the report. `units` are (utility, state) tuples; timing rows are keyed "utility:state"."""
    key_of = lambda k: f"{int(k[0])}:{k[1]}"  # noqa: E731
    rows = {r["utility"]: r for r in timing_rows if abs(float(r["theta"]) - theta) < 1e-12}
    lists = {"step_d_does_not_keep_its_place_within_its_dates": [], "step_d_unsettled": [],
             "step_d_open_below_only": [], "step_d_fails_only_jointly_with_its_unresolved_sites": [],
             "unknown_load_decided_by_the_enumeration": [], "unknown_load_unsettled": [],
             "step_d_unresolved_by_a_stress_scenario": []}
    for k in units:
        u = key_of(k)
        r = rows.get(u)
        affected = u in unknown_affected
        if r is None:
            if affected:
                why.setdefault(k, []).append("Joe, R2: a site whose load is unknown reaches it and the enumeration has no row for it")
                lists["unknown_load_unsettled"].append(u)
            continue
        # A stress scenario never defines a reference and is never admissible, but a utility whose outcome differs under
        # it is not settled (Joe, R4: "Preserve unresolved eligibility where the distinction matters"; D-96).
        for x in r.get("unresolved_by_stress") or []:
            why.setdefault(k, []).append("Step D: " + x["reason"] + f" ({x['site']})")
            lists["step_d_unresolved_by_a_stress_scenario"].append(u)
        if affected and r["keeps_its_place"] is True:
            # The frame lacks the unknown site; its frame-based verdicts are not admissible readings (Joe, R2).
            why[k] = [x for x in why.get(k, []) if not x.startswith("D-46: ")]
            if not why[k]:
                why.pop(k)
            if str(why4.get(k, "")).startswith("D-46, ruling 4"):
                why4.pop(k)
            lists["unknown_load_decided_by_the_enumeration"].append(u)
            continue
        if r["keeps_its_place"] is None:
            why.setdefault(k, []).append("Step D: unsettled: " + r["status"])
            lists["step_d_unsettled"].append(u)
            if affected:
                lists["unknown_load_unsettled"].append(u)
        elif r["keeps_with_assignment_as_mapped"] is False:
            why.setdefault(k, []).append("Step D (D-61 5.4): " + r["status"] + " within its dated intervals or the crossed screen")
            lists["step_d_does_not_keep_its_place_within_its_dates"].append(u)
            if r.get("fails_only_open_below"):
                lists["step_d_open_below_only"].append(u)
        elif r["keeps_its_place"] is False:
            why4.setdefault(k, "D-46, ruling 4 (step D, joint with its dated intervals): its place changes when its "
                               "unresolved sites move")
            lists["step_d_fails_only_jointly_with_its_unresolved_sites"].append(u)
        if affected and r["keeps_its_place"] is False:
            lists["unknown_load_unsettled"].append(u)
    return {k: sorted(set(v)) for k, v in lists.items()}


# ---- the run ------------------------------------------------------------------------

def main() -> int:
    from pipeline.analysis import power_simulation as ps
    from pipeline.electricity import market_region

    fac = pd.read_parquet(INTERIM / "facilities.parquet")
    fy_all = pd.read_parquet(INTERIM / "facility_year.parquet")
    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet")
    q = pd.read_parquet(INTERIM / "panel_quantities.parquet")
    anchor = pd.read_parquet(INTERIM / "state_anchor.parquet")
    state_years = pd.read_parquet(INTERIM / "state_load_by_year.parquet")
    gaps = pd.read_parquet(INTERIM / "epoch_gaps.parquet")

    fy = fy_all[~fy_all.crypto][["fid"] + KEY + ["year", "mw"]]
    step_d = "date_rule" in fac.columns
    timing_doc, unknown_affected = None, set()
    if step_d:                                       # a rebuilt inventory: timing.py's verdicts are required
        tp, up = FROZEN / "timing_place_test.json", FROZEN / "unknown_load_sites_and_affected_utilities.json"
        if not tp.exists() or not up.exists():
            raise SystemExit(f"step D inventory: run timing.py first ({tp.name} and {up.name} are both required)")
        timing_doc = json.loads(tp.read_text())
        unknown_affected = set(json.loads(up.read_text())["every_affected_utility"])
    units = pd.MultiIndex.from_frame(q[KEY].drop_duplicates().sort_values(KEY))
    names = q.groupby(KEY).utility_name.last()
    base = (q[q.year.isin((2009, 2010, 2011))].groupby(KEY).total_retail_mwh.mean() / 1000.0)
    base = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh.combine_first(base).reindex(units)
    nonres = (q.assign(v=q.nonres_mwh.fillna(q.total_retail_mwh) / 1000.0)
              .pivot_table(index=KEY, columns="year", values="v").reindex(index=units, columns=YEARS))
    regions = market_region.fixed(q).reindex(units)
    scale = fac.set_index("fid").state_scale
    where = fy.drop_duplicates("fid").set_index("fid")[KEY]

    # ---- T1: the three readings ----
    states = state_remainders(anchor)
    b = matrix(fy, units)
    a = matrix(fy.assign(mw=fy.mw / fy.fid.map(scale).fillna(1.0)), units)
    rem_gwh = pd.Series(units.get_level_values("state").map(states.remainder_twh).values * 1000.0, index=units).fillna(0.0)
    c = ceiling(a, nonres, rem_gwh)

    crypto = dose.assign(s=dose.crypto_mw * 8.76 / dose.base_retail_gwh).groupby(KEY).s.max().reindex(units).fillna(0.0)
    table = pd.DataFrame({"name": names.reindex(units), "region": regions, "base_gwh": base.round(1),
                          "state_kind": units.get_level_values("state").map(states.kind).values,
                          "state_at_the_cap": units.get_level_values("state").map(states.at_the_cap).values,
                          "state_remainder_gwh": rem_gwh.round(1)}, index=units)
    table["state_kind"] = table.state_kind.fillna("no_state_total")
    table["max_share_b"] = max_share(b, base)
    table["max_share_a"] = max_share(a, base)
    table["max_share_c"] = max_share(c, base)
    table["no_base"] = ~(base > 0)
    table["clean_b"] = (table.max_share_b.fillna(0) < CLEAN_BELOW) & (crypto < CRYPTO_LIMIT) & ~((b.max(axis=1) > 0) & table.no_base)
    rise = largest_rise(nonres)
    table["most_hidden_load_that_could_have_arrived_in_the_panel_share"] = (np.minimum(rise, rem_gwh) / base).where(rem_gwh > 0, 0.0)
    for theta in THRESHOLDS:
        t = f"{theta:.0%}"
        table[f"b_{t}"] = first_crossing(b, base, theta)
        table[f"a_{t}"] = first_crossing(a, base, theta)
        table[f"c_earliest_{t}"] = first_crossing(c, base, theta)
        table[f"c_latest_{t}"] = table[f"a_{t}"]
        own = ps.history_settled(theta)
        table[f"settled_by_its_own_count_{t}"] = [own[k]["group"] if k in own else None for k in units]
    # A utility with no 2009-2011 sales to divide by cannot be shown to be clean where there is a remainder.
    table.loc[table.no_base & (rem_gwh > 0), "max_share_c"] = np.inf

    for theta in THRESHOLDS:
        t = f"{theta:.0%}"
        res = [keeps_its_place(r, t) for r in table.to_dict("records")]
        table[f"place_{t}"] = [x[0] for x in res]
        table[f"t1_{t}"] = [x[1] for x in res]
        table[f"remainder_unassigned_{t}"] = [with_the_remainder_unassigned(r, t) for r in table.to_dict("records")]

    # The side readings: growth in sales, and EPRI's four historical years.
    sy = state_years.assign(rem=(state_years.epri_twh - state_years.measured_twh - state_years.unscaled_estimates_twh).clip(lower=0.0))
    smallest = sy.groupby("state").rem.min() * 1000.0
    rem4 = pd.Series(units.get_level_values("state").map(smallest).values, index=units).fillna(0.0)
    c4 = ceiling(a, nonres, np.minimum(rem4, rem_gwh))
    # Years from 2021 on take that year's own remainder where EPRI gives one.
    for y in sorted(sy.year.unique()):
        ry = pd.Series(units.get_level_values("state").map(sy[sy.year == y].set_index("state").rem * 1000.0).values, index=units).fillna(0.0)
        room = (nonres[y] - a[y]).clip(lower=0.0)
        c4[y] = a[y] + np.where(room.isna(), ry, np.minimum(ry, room))
    table["max_share_c_four_years"] = max_share(c4, base)
    for theta in THRESHOLDS:
        table[f"c_earliest_four_years_{theta:.0%}"] = first_crossing(c4, base, theta)

    # How many sites the smallest-territory rule would place differently at unscaled sizes (reported, not applied).
    from pipeline.facilities import build_inventory as bi
    cap = (q[q.year >= 2020].groupby(KEY).total_retail_mwh.max() / 1000.0)
    every = fac.copy()
    every["candidates"] = [[int(x) for x in str(s).split(";") if x and x != "nan"] for s in every.utility_candidates.fillna("")]
    by_map = every.set_index("fid").utility_assign.isin(["unique", "smallest_polygon", "next_larger_load_feasible", "fallback_largest_flagged"])
    as_scaled = bi.pick_utilities(every, cap).utility_id_eia.reindex(every.fid).fillna(-1)
    unscaled = bi.pick_utilities(every.assign(mw_full=every.mw_full_raw), cap).utility_id_eia.reindex(every.fid).fillna(-1)
    moved_sites = (as_scaled != unscaled) & by_map.reindex(every.fid).values & every.set_index("fid").in_dose
    rerun_differs = int(((as_scaled != every.set_index("fid").utility_id_eia.fillna(-1)) & by_map.reindex(every.fid).values).sum())
    st_of = every.set_index("fid").state
    moved_utilities = {(int(u), st_of[f]) for f, u in as_scaled[moved_sites].items() if u >= 0}
    moved_utilities |= {(int(u), st_of[f]) for f, u in unscaled[moved_sites].items() if u >= 0}
    table["a_site_would_move_at_unscaled_sizes"] = [k in moved_utilities for k in units]

    # ---- T2: the six building-record histories at five years a step ----
    f_idx = fac.set_index("fid")
    phases = buildout.phases_by_site(buildout.load())
    slow = {fid: {y: phased_mw(f_idx.mw_full[fid], phases[fid], y, SLOW_OCCUPANCY) for y in YEARS}
            for fid in BUILDING_RECORD_SITES if fid in phases and fid in where.index}
    t2_units = {tuple(where.loc[f]) for f in slow}
    t2 = compare(units, base, b, {"five_years_a_step": swap(fy, where, slow)}, t2_units, names)
    for r in t2:
        r["sites"] = [BUILDING_RECORD_SITES[f] for f in slow if tuple(where.loc[f]) == (int(r["utility"].split(":")[0]), r["utility"].split(":")[1])]

    # ---- T3: Epoch rows already running before Epoch's first entry ----
    g = gaps[gaps.fid.isin(where.index)]
    cur = {fid: fy[fy.fid == fid].set_index("year").mw.to_dict() for fid in g.fid}
    low = {r.fid: {y: (0.0 if r.sourced_start <= y < r.first_entry_year else cur[r.fid].get(y, 0.0)) for y in YEARS} for r in g.itertuples()}
    high = {r.fid: {y: (buildout.ramp_mw(r.first_entry_mw, r.sourced_start, y) if r.sourced_start <= y < r.first_entry_year
                        else cur[r.fid].get(y, 0.0)) for y in YEARS} for r in g.itertuples()}
    t3_units = {tuple(where.loc[f]) for f in g.fid}
    t3 = compare(units, base, b, {"nothing_before_the_first_entry": swap(fy, where, low),
                                  "first_entry_level_from_the_start": swap(fy, where, high)}, t3_units, names)
    t3_sites = [{"site": r.fid, "utility": f"{int(where.utility_id_eia[r.fid])}:{where.state[r.fid]}", "sourced_start": int(r.sourced_start),
                 "first_entry_year": int(r.first_entry_year), "first_entry_mw": round(float(r.first_entry_mw), 1)} for r in g.itertuples()]
    t3_off_panel = [{"site": r.fid, "sourced_start": int(r.sourced_start), "first_entry_year": int(r.first_entry_year)}
                    for r in gaps[~gaps.fid.isin(where.index)].itertuples()]

    # ---- T5 and T4: operator-reported sites ----
    e_rows, e_sites = site_energy.load()
    energy = site_energy.paths(e_rows, e_sites, dict(zip(fac.fid, fac.generator_kw)))
    said_zero = {(r.campus, int(r.year)) for r in e_rows.itertuples() if str(r.printed_value).strip().lower() == NOT_YET_ONLINE}
    campus_of = dict(zip(e_sites.fid, e_sites.campus))
    t5_sites, bracket, disagree = [], {}, []
    for fid, path in energy.items():
        if fid not in where.index:
            continue
        first = site_energy.first_year(path)
        start = f_idx.energized_year[fid]
        if pd.isna(start) or start >= first:
            continue
        unobserved = [y for y in range(int(start), first) if (campus_of[fid], y) not in said_zero]
        zeros = [y for y in range(int(start), first) if (campus_of[fid], y) in said_zero]
        if zeros:
            disagree.append({"site": fid, "campus": campus_of[fid], "sourced_start": int(start), "operator_says_not_yet_online": zeros})
        if unobserved:
            cur_path = fy[fy.fid == fid].set_index("year").mw.to_dict()
            bracket[fid] = {y: (path[first] if y in unobserved else cur_path.get(y, 0.0)) for y in YEARS}
            t5_sites.append({"site": fid, "campus": campus_of[fid], "utility": f"{int(where.utility_id_eia[fid])}:{where.state[fid]}",
                             "sourced_start": int(start), "first_reported_year": int(first), "unobserved_years": unobserved,
                             "first_reported_mw": round(float(path[first]), 1)})
    t5_units = {tuple(where.loc[f]) for f in bracket}
    t5 = compare(units, base, b, {"first_reported_figure_from_the_sourced_start": swap(fy, where, bracket)}, t5_units, names)

    t4 = []
    for fid, path in energy.items():
        if fid not in where.index:
            continue
        k = tuple(where.loc[fid])
        if k not in nonres.index:
            continue
        nr = nonres.loc[k]
        yrs = [y for y in sorted(path) if y in nr.index and pd.notna(nr[y]) and path[y] > 0]
        if not yrs:
            continue
        gwh = {y: path[y] * 8.76 for y in yrs}
        over = [y for y in yrs if gwh[y] > nr[y]]
        y0, y1 = yrs[0], yrs[-1]
        prior = nr.get(y0 - 1) if (y0 - 1) in nr.index and pd.notna(nr.get(y0 - 1)) else nr[y0]
        site_rise, sales_rise = gwh[y1], float(nr[y1] - prior)
        if over or site_rise > sales_rise:
            t4.append({"site": fid, "campus": campus_of[fid], "utility": f"{int(k[0])}:{k[1]}", "name": names.get(k),
                       "how_the_site_was_placed": f_idx.utility_assign[fid],
                       "years_the_site_exceeds_the_utilitys_nonresidential_sales": over,
                       "site_gwh_in_last_reported_year": round(site_rise, 1), "last_reported_year": int(y1),
                       "utilitys_rise_in_nonresidential_gwh_since_the_year_before_the_first_report": round(sales_rise, 1)})

    # ---- who is left (D-46) ----
    fails_other: dict[tuple, list[str]] = {}
    for label, rows in (("T2: its place changes if the building-record steps fill over five years", t2),
                        ("T3: its place depends on what an Epoch site carried before Epoch's first entry", t3),
                        ("T5: its place depends on a reported site's unobserved first years", t5)):
        for r in rows:
            k = (int(r["utility"].split(":")[0]), r["utility"].split(":")[1])
            for theta in THRESHOLDS:
                if not r["place_holds_by_threshold"][f"{theta:.0%}"]:
                    fails_other.setdefault((k, f"{theta:.0%}"), []).append(label)
    unverified_assignment = sorted({(x["utility"], x["site"]) for x in t4 if x["how_the_site_was_placed"] != "verified_by_hand"})
    for u, _ in unverified_assignment:
        k = (int(u.split(":")[0]), u.split(":")[1])
        for theta in THRESHOLDS:
            fails_other.setdefault((k, f"{theta:.0%}"), []).append("T4: a measured site is on it by the map alone and its sales do not show the site")

    report = {
        "what_this_is": "How far each utility's place in the design rests on what the inventory does not know. Rules in "
                        "docs/DECISIONS.md: D-44 (written before the first run) as Joe ruled on what it found (D-46). Load and sales only.",
        "the_test": "D-46, rulings 1 and 2: a utility keeps its place if the inventory as built (reading B) and with no anchoring "
                    "(reading A) agree, in every state. Reading C, the state's remainder left unassigned, is reported and decides nothing. "
                    "Ruling 4 as amended: it also has to keep its place with every unresolved site on it taken off and with every "
                    "unresolved site that lists it as a candidate counted on it; those two cases are each utility's own extremes "
                    "and cannot all hold together.",
        "tolerance": f"the same group (early before {COHORTS[0]}, cohort {COHORTS[0]} to {COHORTS[1]}, late, never) and, for a cohort "
                     f"utility, a first crossing within {MOVE_TOLERANCE - 1} year of the built inventory's",
        "assumption_reading_c_needs": "hidden load does not shrink: load on a system in an earlier year is still there in 2024",
        "states": {},
        "thresholds": {},
        "sites_the_smallest_territory_rule_would_place_differently_at_unscaled_sizes": int(moved_sites.sum()),
        "map_placed_sites_where_rerunning_the_rule_here_does_not_give_the_built_utility": rerun_differs,
        "T2_building_record_histories_at_five_years_a_step": t2,
        "T3_epoch_rows_before_their_first_entry": {"sites": t3_sites, "sites_with_no_panel_utility": t3_off_panel, "utilities": t3},
        "T4_measured_sites_against_their_utilitys_sales": t4,
        "T5_reported_sites_with_unobserved_first_years": {"sites": t5_sites, "utilities": t5,
                                                          "sourced_start_against_an_operators_not_yet_online": disagree},
    }
    st = states.copy()
    st["utilities_in_panel"] = pd.Series(units.get_level_values("state")).value_counts().reindex(st.index).fillna(0).astype(int)
    for s, r in st.sort_values("remainder_twh", ascending=False).iterrows():
        report["states"][s] = {"kind": r.kind, "at_the_cap": bool(r.at_the_cap), "state_total_twh": round(float(r.epri_twh), 3),
                               "measured_twh": round(float(r.measured_twh), 3), "unscaled_estimates_twh": round(float(r.unscaled_estimates_twh), 3),
                               "remainder_twh": round(float(r.remainder_twh), 3),
                               "raw_factor": None if pd.isna(r.raw_factor) else round(float(r.raw_factor), 3), "factor_used": round(float(r.factor), 3)}

    key_of = lambda k: f"{int(k[0])}:{k[1]}"  # noqa: E731
    ownership = q.groupby(KEY).ownership.last()
    floor = set(map(tuple, q[q.meets_size_floor][KEY].drop_duplicates().values))
    by_region = lambda ks: (pd.Series([regions.get(k) for k in ks], dtype=object).fillna("no region on file")  # noqa: E731
                            .value_counts().sort_index().to_dict())
    holds_c = lambda k, t: table.at[k, f"remainder_unassigned_{t}"] in ("holds", "the state has no remainder")  # noqa: E731
    membership = []
    cases, _, _ = assignment.evaluate(fac.set_index("fid"), fy, units, base, regions, THRESHOLDS)
    for theta in THRESHOLDS:
        t = f"{theta:.0%}"
        treated, clean = ps.design(q, dose, theta, ps.history_settled(theta))
        cohort_keys = list(zip(treated.utility_id_eia.astype(int), treated.state))
        clean_keys = set(zip(clean.utility_id_eia.astype(int), clean.state))
        dates = ps.dates_and_histories_reasons(theta)                      # D-20 and D-28, by utility
        aside = {k for k, why_k in dates.items() if any(not x.startswith(ps.TEN_YEAR_REASON) for x in why_k)}
        aside10 = set(dates)
        why = {}
        for k in units:
            reasons = []
            v = table.at[k, f"t1_{t}"]
            if not v.startswith("keeps its place") and not v.startswith("not tested"):
                reasons.append("D-46: " + v)
            reasons += fails_other.get((k, t), [])
            if reasons:
                why[k] = reasons
        # Ruling 4 as amended: the lower and upper cases, on hosts, early hosts and comparison utilities alike.
        # A utility judged on its own count of its load (D-34) does not rest on where sites were placed.
        why4 = {}
        for k in units:
            place = table.at[k, f"place_{t}"]
            if place not in ("cohort", "early", "comparison") or table.at[k, f"settled_by_its_own_count_{t}"]:
                continue
            v4 = assignment.verdict(place, table.at[k, f"b_{t}"], {c: cases.at[k, f"{c}_{t}"] for c in assignment.CASES},
                                    {c: cases.at[k, f"max_share_{c}"] for c in ("upper_as_built", "upper_no_anchoring")})
            if v4 != "keeps its place":
                why4[k] = "D-46, ruling 4: " + v4
        if step_d:
            sd = step_d_reasons(timing_doc["utilities"], theta, units, unknown_affected, why, why4)
        held = sorted(k for k in cohort_keys if k in why4 and k not in why)
        sets = {"headline_set": [k for k in cohort_keys if k not in aside],
                "set_with_the_ten_year_case": [k for k in cohort_keys if k not in aside10],
                "every_cohort_utility": cohort_keys}
        out_sets = {}
        for name, ks in sets.items():
            keep = [k for k in ks if k not in why]
            left = [k for k in keep if k not in held]
            srt = lambda xs: sorted(xs, key=lambda k: (k[1], k[0]))  # noqa: E731
            out_sets[name] = {
                "before": len(ks), "keep_their_place_between_the_built_and_unanchored_inventories": len(keep),
                "unsettled_on_assignment": len(keep) - len(left), "after": len(left),
                "after_by_ownership": ownership.reindex(pd.MultiIndex.from_tuples(left, names=KEY)).value_counts().to_dict() if left else {},
                "after_by_region": by_region(left), "after_states": len({k[1] for k in left}),
                "of_those_left_how_many_hold_with_the_remainder_unassigned": int(sum(holds_c(k, t) for k in left)),
                "left": [{"utility": key_of(k), "name": names.get(k), "first_crossing": fmt(table.at[k, f"b_{t}"]),
                          "no_anchoring": fmt(table.at[k, f"a_{t}"]), "with_the_remainder_unassigned": table.at[k, f"remainder_unassigned_{t}"]}
                         for k in srt(left)],
                "unsettled_on_assignment_list": [
                    {"utility": key_of(k), "name": names.get(k), "first_crossing": fmt(table.at[k, f"b_{t}"]), "why": why4[k],
                     **{c: fmt(cases.at[k, f"{c}_{t}"]) for c in assignment.CASES},
                     "unresolved_sites_on_it": int(cases.at[k, "unresolved_sites_on_it"])} for k in srt(keep) if k in held],
                "lost": [{"utility": key_of(k), "name": names.get(k), "first_crossing": fmt(table.at[k, f"b_{t}"]),
                          "state_kind": table.at[k, "state_kind"], "why": why[k],
                          "no_anchoring": fmt(table.at[k, f"a_{t}"]), "earliest_possible": fmt(table.at[k, f"c_earliest_{t}"]),
                          "latest_possible": fmt(table.at[k, f"c_latest_{t}"])} for k in srt(ks) if k in why]}
        early = [k for k in units if table.at[k, f"place_{t}"] == "early"]
        comp_pool = [k for k in units if k in clean_keys and k not in aside]
        comp_ab = [k for k in comp_pool if k not in why]                  # rulings 1 and 2
        comp_left = [k for k in comp_ab if k not in why4]                 # and ruling 4's upper case
        comp_fail = [k for k in comp_pool if k in why]
        comp_fail4 = [k for k in comp_ab if k in why4]
        arrive = table["most_hidden_load_that_could_have_arrived_in_the_panel_share"] + table.max_share_a.fillna(0)
        # Ruling 2's labelled timing run: hosts in states whose estimates are scaled down, at their no-anchoring years.
        timing = [{"utility": key_of(k), "name": names.get(k), "as_built": fmt(table.at[k, f"b_{t}"]), "no_anchoring": fmt(table.at[k, f"a_{t}"]),
                   "place_in_the_timing_run": {"cohort": "a host at its no-anchoring year", "early": "an early host, on neither side"}.get(
                       group(table.at[k, f"a_{t}"]), "not a cohort host")}
                  for k in srt(sets["headline_set"]) if k in why and table.at[k, "state_kind"] == "estimates_scaled_down"
                  and any(x.startswith("D-46: no anchoring") for x in why[k])]
        report["thresholds"][t] = {
            "sets": out_sets,
            "labelled_runs_beside_the_headline": {
                "timing_run_at_no_anchoring_years": timing,
                "headline_set_with_every_host_unsettled_on_assignment_in": [key_of(k) for k in sets["headline_set"] if k not in why]},
            "early_hosts": {"before": len(early), "keep_their_place": int(sum(k not in why for k in early)),
                            "of_which_also_hold_in_the_lower_and_upper_cases": int(sum(k not in why and k not in why4 for k in early)),
                            "in_states_whose_estimates_are_scaled_down": int(sum(table.at[k, "state_kind"] == "estimates_scaled_down" for k in early)),
                            "of_which_keep_their_place": int(sum(table.at[k, "state_kind"] == "estimates_scaled_down" and k not in why for k in early)),
                            "do_not": [{"utility": key_of(k), "name": names.get(k), "why": why[k]} for k in early if k in why]},
            "comparison_utilities": {
                "under_0.5pct_as_built_and_not_set_aside": len(comp_pool),
                "keep_their_place_between_the_built_and_unanchored_inventories": len(comp_ab),
                "keep_their_place": len(comp_left),
                "by_region_before": by_region(comp_pool), "by_region_keep_their_place": by_region(comp_left),
                "above_the_customer_floor_before": int(sum(k in floor for k in comp_pool)),
                "above_the_customer_floor_between_the_built_and_unanchored_inventories": int(sum(k in floor for k in comp_ab)),
                "above_the_customer_floor_keep_their_place": int(sum(k in floor for k in comp_left)),
                "by_region_above_the_floor_before": by_region([k for k in comp_pool if k in floor]),
                "by_region_above_the_floor_keep_their_place": by_region([k for k in comp_left if k in floor]),
                "do_not": [{"utility": key_of(k), "name": names.get(k), "state_kind": table.at[k, "state_kind"], "why": why[k]} for k in comp_fail],
                "fail_the_upper_case_of_ruling_4": len(comp_fail4),
                "fail_the_upper_case_above_the_customer_floor": int(sum(k in floor for k in comp_fail4)),
                "fail_the_upper_case_by_region_above_the_floor": by_region([k for k in comp_fail4 if k in floor]),
                "fail_the_upper_case_list": [{"utility": key_of(k), "name": names.get(k), "why": why4[k]} for k in comp_fail4],
                "in_texas_keep_their_place": int(sum(k[1] == HELD_STATE for k in comp_left)),
                "in_texas_above_the_floor_by_region": by_region([k for k in comp_left if k in floor and k[1] == HELD_STATE]),
                "reported_not_a_filter_with_the_remainder_unassigned": {
                    "of_those_that_keep_their_place_how_many_would_hold": int(sum(holds_c(k, t) for k in comp_left)),
                    "above_the_customer_floor": int(sum(holds_c(k, t) and k in floor for k in comp_left)),
                    "by_region_above_the_floor": by_region([k for k in comp_left if k in floor and holds_c(k, t)]),
                    "of_those_that_would_not_how_many_could_not_have_gained_0.5pct_inside_the_panel":
                        int(sum((not holds_c(k, t)) and arrive[k] < CLEAN_BELOW for k in comp_left)),
                    "would_hold_with_the_remainder_read_for_each_of_2021_to_2024":
                        int(sum(table.at[k, "max_share_c_four_years"] < CLEAN_BELOW for k in comp_left)),
                },
            },
            "by_state_kind": {kind: {"cohort_utilities": int(sum(table.at[k, "state_kind"] == kind for k in cohort_keys)),
                                     "of_which_keep_their_place": int(sum(table.at[k, "state_kind"] == kind and k not in why for k in cohort_keys)),
                                     "comparison_utilities": int(sum(table.at[k, "state_kind"] == kind for k in comp_pool)),
                                     "comparison_utilities_that_keep_their_place": int(sum(table.at[k, "state_kind"] == kind for k in comp_left))}
                              for kind in ("falls_short", "measured_load_at_or_above_the_total", "estimates_scaled_down", "no_state_total")},
            # What power_simulation.set_aside() reads: on both sides, everyone here is out of the headline set.
            "lists": {"does_not_keep_its_place": sorted(key_of(k) for k in why),
                      "unsettled_on_assignment_under_ruling_4": sorted(key_of(k) for k in why4),
                      **(sd if step_d else {})},
        }
        table[f"lost_{t}"] = ["; ".join(why[k]) if k in why else "" for k in units]
        table[f"ruling_4_{t}"] = [why4.get(k, "") for k in units]
        for c in assignment.CASES:
            table[f"{c}_{t}"] = cases[f"{c}_{t}"]
        for k in sorted(cohort_keys, key=lambda k: (k[1], k[0])):
            ten_only = [x for x in dates.get(k, []) if x.startswith(ps.TEN_YEAR_REASON)]
            reasons = ([x for x in dates.get(k, []) if x not in ten_only] + why.get(k, [])
                       + ([why4[k]] if k in why4 else []))
            in_head = k in sets["headline_set"] and k not in why and k not in why4
            in_ten = k in sets["set_with_the_ten_year_case"] and k not in why and k not in why4
            membership.append({"threshold": t, "utility_id_eia": k[0], "state": k[1], "name": names.get(k), "ownership": ownership.get(k),
                               "region": regions.get(k), "first_crossing": fmt(table.at[k, f"b_{t}"]), "first_crossing_no_anchoring": fmt(table.at[k, f"a_{t}"]),
                               "in_headline_set": in_head, "in_set_with_the_ten_year_case": in_ten, "in_every_cohort_utility_run": True,
                               "keeps_its_place_in_the_every_cohort_utility_test": k not in why and k not in why4,
                               "why_not_in_the_headline_set": "; ".join(reasons),
                               "why_not_in_the_set_with_the_ten_year_case": "; ".join(reasons + ten_only)})

    out = table.reset_index()
    for col in [c for c in out.columns if c.startswith(("b_", "a_", "c_earliest", "c_latest", "lower_", "upper_"))]:
        out[col] = out[col].astype("Int64")
    for col in ("max_share_a", "max_share_b", "max_share_c", "max_share_c_four_years", "most_hidden_load_that_could_have_arrived_in_the_panel_share"):
        out[col] = out[col].replace(np.inf, np.nan).round(5)
    keep = out[(out.max_share_b.fillna(0) > 0) | (out.max_share_a.fillna(0) > 0) | (out.state_remainder_gwh > 0)]
    keep.to_csv(FROZEN / "treatment_bounds_by_utility.csv", index=False)
    pd.DataFrame(membership).to_csv(FROZEN / "headline_set.csv", index=False)
    if step_d:
        from pipeline.facilities import corrections as cx
        report["step_d"] = {"timing_fingerprint": timing_doc.get("fingerprint"),
                            "stress_scenarios_reported_not_deciding": timing_doc.get("stress_scenarios", []),
                            "open_below_only_with_the_permit_error_reach": timing_doc.get("open_below_only_with_the_permit_error_reach", []),
                            "unknown_load_affected_utilities": sorted(unknown_affected)}
        report["fingerprint"] = cx.fingerprint([*cx.code_files(), FROZEN / "timing_place_test.json",
                                                FROZEN / "unknown_load_sites_and_affected_utilities.json",
                                                INTERIM / "facilities.parquet", INTERIM / "facility_year.parquet"],
                                               thresholds=list(THRESHOLDS))
    (FROZEN / "treatment_bounds.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    slim = {t: {"sets": {n: {k: v[k] for k in ("before", "keep_their_place_between_the_built_and_unanchored_inventories", "unsettled_on_assignment", "after")}
                         for n, v in r["sets"].items()},
                "early_hosts": {k: v for k, v in r["early_hosts"].items() if k != "do_not"},
                "comparison_utilities": {k: v for k, v in r["comparison_utilities"].items() if "by_region" not in k and not k.endswith("_list") and k != "do_not"},
                "by_state_kind": r["by_state_kind"]}
            for t, r in report["thresholds"].items()}
    print(json.dumps(slim, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
