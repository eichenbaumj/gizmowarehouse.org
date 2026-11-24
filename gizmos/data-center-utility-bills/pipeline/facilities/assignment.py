#!/usr/bin/env python3
"""Assignment evidence: does a utility keep its place whichever way its unresolved sites fall?

Touches NO price data. The rule is D-46's ruling 4 as amended in its two addenda
(docs/DECISIONS.md), written before anything here was run.

A site's serving utility is RESOLVED if it was verified by hand (a page the
session model opened names who delivers to it, or shows the site is behind the
meter, served at wholesale or on an ERCOT wires company), or if the site lies
in one territory only and is outside ERCOT. The second is an assumption: that
the territory map is right there and the site is not served at wholesale or
behind the meter. Every other map-placed site is UNRESOLVED: one placed among
more than one candidate territory, and any map-placed Texas site with a
candidate territory in the ERCOT region.

For every utility, every panel year from 2001 is recomputed two ways:

  lower case   every unresolved site now on the utility is taken off
  upper case   every unresolved site that lists the utility among its candidate
               territories is counted on it, once, including sites the inventory
               now puts on another utility

each as built (reading B) and with no anchoring (reading A). A utility keeps
its place only if its group and, for a cohort utility, its first crossing
within one year are the same on all four as on the inventory as built. A
comparison utility has to stay under 0.5% throughout in its upper case, as
built and with no anchoring. The date used in any estimate stays the
inventory's.

These are conservative envelopes. Each utility's two cases are its own
extremes: a site that is a candidate for two utilities is counted on each in
its own upper case, which cannot both be true, and the upper case is not
checked against what the utility's sales could carry.

The sites that determine a crossing (the largest in the crossing year, taken
until they reach the threshold) are a worklist: the order in which sites are
verified first. They are not a definition of what fixes the date.

`evaluate()` is what treatment_bounds.py calls to decide who is in. Run as a
script this writes the table of hosts and sites:
  data/frozen/assignment_evidence.json
  data/frozen/assignment_evidence_sites.csv

Run:  python3 -I pipeline/facilities/assignment.py     (after build_inventory.py; treatment_bounds.py reads the same rule)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"

KEY = ["utility_id_eia", "state"]
YEARS = list(range(2001, 2026))
COHORTS = (2011, 2022)
MOVE_TOLERANCE = 2
CLEAN_BELOW = 0.005
ERCOT_STATE, ERCOT_REGION = "TX", "ERCOT"
VERIFIED = ("verified_by_hand", "ercot_wires_outside_panel", "behind_the_meter", "wholesale_direct")
ONE_TERRITORY = "unique"
CASES = ("lower_as_built", "lower_no_anchoring", "upper_as_built", "upper_no_anchoring")


def group(first_year) -> str:
    if first_year is None or pd.isna(first_year):
        return "never"
    return "early" if first_year < COHORTS[0] else ("cohort" if first_year <= COHORTS[1] else "late")


def same_place(a, b) -> bool:
    if group(a) != group(b):
        return False
    return group(a) != "cohort" or abs(a - b) < MOVE_TOLERANCE


def candidates(s) -> list[int]:
    return [int(x) for x in str(s).split(";") if x and x != "nan"] if isinstance(s, str) else []


def resolved(fac: pd.DataFrame, ercot_units: set) -> pd.Series:
    """True where a site's serving utility is resolved under ruling 4 as amended. Indexed like `fac`.

    `ercot_units` is the set of (utility, state) panel units in the ERCOT region: a map-placed Texas site
    with any of them among its candidates is unresolved even if it lies in one territory.
    """
    out = []
    for assign, state, cands in zip(fac.utility_assign, fac.state, fac.utility_candidates):
        if assign in VERIFIED:
            out.append(True)
        elif assign == ONE_TERRITORY:
            in_ercot = state == ERCOT_STATE and any((c, state) in ercot_units for c in candidates(cands))
            out.append(not in_ercot)
        else:
            out.append(False)
    return pd.Series(out, index=fac.index)


def matrices(fy: pd.DataFrame, fac: pd.DataFrame, units: pd.MultiIndex, is_resolved: pd.Series) -> dict[str, pd.DataFrame]:
    """Utility-by-year GWh as built, with no anchoring, and in the four cases.

    fy            facility-year rows (fid, utility, state, year, mw), data centers only
    fac           the inventory, indexed by fid, with state_scale and utility_candidates
    is_resolved   by fid
    """
    scale = fac.state_scale.reindex(fy.fid).fillna(1.0).values
    rows = fy.assign(mw_a=fy.mw.values / scale, unresolved=~is_resolved.reindex(fy.fid).fillna(False).values)

    def mat(frame: pd.DataFrame, col: str) -> pd.DataFrame:
        if not len(frame):
            return pd.DataFrame(0.0, index=units, columns=YEARS)
        g = (frame.groupby(KEY + ["year"])[col].sum() * 8.76).unstack("year")
        return g.reindex(index=units, columns=YEARS).fillna(0.0)

    # Every unresolved site, put on each of its other candidates (the site's own state; a candidate that is not
    # a panel unit there cannot be carrying it).
    unit_set = set(units)
    extra = []
    loose = rows[rows.unresolved]
    cand_of = fac.utility_candidates.reindex(loose.fid.unique())
    for fid, grp in loose.groupby("fid"):
        now, state = int(grp.utility_id_eia.iloc[0]), grp.state.iloc[0]
        for c in dict.fromkeys(candidates(cand_of.get(fid))):
            if c != now and (c, state) in unit_set:
                extra.append(grp.assign(utility_id_eia=c))
    extra = pd.concat(extra, ignore_index=True) if extra else rows.iloc[:0]
    b, a = mat(rows, "mw"), mat(rows, "mw_a")
    return {"as_built": b, "no_anchoring": a,
            "lower_as_built": mat(rows[~rows.unresolved], "mw"), "lower_no_anchoring": mat(rows[~rows.unresolved], "mw_a"),
            "upper_as_built": b + mat(extra, "mw"), "upper_no_anchoring": a + mat(extra, "mw_a")}


def first_crossing(gwh: pd.DataFrame, base: pd.Series, theta: float) -> pd.Series:
    hit = gwh.ge(theta * base.reindex(gwh.index), axis=0) & base.reindex(gwh.index).gt(0).values[:, None]
    years = np.array(gwh.columns, dtype=float)
    return pd.Series(np.where(hit.values.any(axis=1), years[hit.values.argmax(axis=1)], np.nan), index=gwh.index)


def max_share(gwh: pd.DataFrame, base: pd.Series) -> pd.Series:
    top = gwh.max(axis=1)
    return (top / base.reindex(gwh.index)).where(top > 0, 0.0)


def fmt(y):
    return "never" if y is None or pd.isna(y) else int(y)


def verdict(place: str, yb, years: dict, shares: dict) -> str:
    """Ruling 4's verdict for one utility at one threshold.

    place   its place on the inventory as built: cohort, early, late, comparison, neither
    yb      its first crossing as built
    years   first crossing in each of the four cases
    shares  largest load share in any year in the two upper cases
    """
    if place == "cohort":
        for name in CASES:
            if not same_place(yb, years[name]):
                return f"{name.replace('_', ' ')}: first crossing {fmt(years[name])} against {fmt(yb)}"
        return "keeps its place"
    if place == "early":
        for name in CASES:
            if group(years[name]) != "early":
                return f"{name.replace('_', ' ')}: first crossing {fmt(years[name])}, not before {COHORTS[0]}"
        return "keeps its place"
    if place == "comparison":
        for name in ("upper_as_built", "upper_no_anchoring"):
            if not shares[name] < CLEAN_BELOW:
                return f"{name.replace('_', ' ')}: load share {shares[name]:.1%}"
        return "keeps its place"
    return "not tested"


def determining_sites(fy: pd.DataFrame, key: tuple, year: int, need_gwh: float) -> list[str]:
    """The utility's sites, largest first in `year`, taken until their combined load reaches the threshold. A worklist."""
    mine = fy[(fy.utility_id_eia == key[0]) & (fy.state == key[1]) & (fy.year == year)].sort_values("mw", ascending=False)
    out, total = [], 0.0
    for fid, mw in zip(mine.fid, mine.mw):
        out.append(fid)
        total += mw * 8.76
        if total >= need_gwh:
            break
    return out


def only_ruling_4(reasons) -> bool:
    """True if nothing but ruling 4 keeps a cohort utility out of the headline set (or nothing does)."""
    parts = [x.strip() for x in str(reasons).split(";")] if isinstance(reasons, str) and reasons else []
    return all(x.startswith("D-46, ruling 4") for x in parts)


def load_inputs(frame_dir=None):
    """The inventory frame (facilities, site-years, dose) from `frame_dir` (default data/interim, the live inventory),
    and the sales side from data/interim always. Only pass_c_expand.load_frozen passes another folder: the frozen
    inventory of 2026-11-14 when the live one is a step D rebuild. Everything else reads the live inventory."""
    from pipeline.electricity import market_region
    frame = INTERIM if frame_dir is None else frame_dir
    fac = pd.read_parquet(frame / "facilities.parquet").set_index("fid")
    fy = pd.read_parquet(frame / "facility_year.parquet")
    fy = fy[~fy.crypto][["fid"] + KEY + ["year", "mw"]]
    q = pd.read_parquet(INTERIM / "panel_quantities.parquet")
    dose = pd.read_parquet(frame / "utility_year_dose.parquet")
    units = pd.MultiIndex.from_frame(q[KEY].drop_duplicates().sort_values(KEY))
    base = (q[q.year.isin((2009, 2010, 2011))].groupby(KEY).total_retail_mwh.mean() / 1000.0)
    base = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh.combine_first(base).reindex(units)
    regions = market_region.fixed(q).reindex(units)
    return fac, fy, q, units, base, regions


def evaluate(fac: pd.DataFrame, fy: pd.DataFrame, units: pd.MultiIndex, base: pd.Series, regions: pd.Series,
             thresholds=(0.02, 0.05)) -> tuple[pd.DataFrame, dict, pd.Series]:
    """(one row per utility with the four cases at each threshold, the six matrices, which sites are resolved)."""
    ercot = {k for k in units if regions.get(k) == ERCOT_REGION}
    is_resolved = resolved(fac, ercot)
    m = matrices(fy, fac, units, is_resolved)
    t = pd.DataFrame(index=units)
    for name in ("upper_as_built", "upper_no_anchoring", "as_built"):
        t[f"max_share_{name}"] = max_share(m[name], base)
    on = fy.drop_duplicates("fid").assign(unres=lambda d: ~is_resolved.reindex(d.fid).fillna(False).values)
    t["sites_on_it"] = on.groupby(KEY).size().reindex(units).fillna(0).astype(int)
    t["unresolved_sites_on_it"] = on[on.unres].groupby(KEY).size().reindex(units).fillna(0).astype(int)
    for theta in thresholds:
        th = f"{theta:.0%}"
        t[f"as_built_{th}"] = first_crossing(m["as_built"], base, theta)
        for name in CASES:
            t[f"{name}_{th}"] = first_crossing(m[name], base, theta)
    return t, m, is_resolved


def site_label(r) -> str:
    who = r.operator if isinstance(r.operator, str) and r.operator else ""
    what = next((x for x in (r.get("name"), r.get("Name")) if isinstance(x, str) and x), "")
    where = f"{r.county_name} County" if isinstance(r.get("county_name"), str) and r.get("county_name") else ""
    return ", ".join(x for x in (who, what if what != who else "", where, r.state) if x)


def main() -> int:
    from pipeline.analysis import power_simulation as ps
    fac, fy, q, units, base, regions = load_inputs()
    names = q.groupby(KEY).utility_name.last()
    t, m, is_resolved = evaluate(fac, fy, units, base, regions)
    key_of = lambda k: f"{int(k[0])}:{k[1]}"  # noqa: E731
    counts = fac.assign(res=is_resolved).groupby("utility_assign").res.agg(["size", "sum"])
    report = {
        "what_this_is": "D-46, ruling 4 as amended: every utility's history recomputed with its unresolved sites taken off (lower case) "
                        "and with every unresolved site that lists it as a candidate territory counted on it (upper case), as built and "
                        "with no anchoring. Load and sales only.",
        "resolved_means": "verified by hand, or in one territory only and outside ERCOT (the second is an assumption: that the "
                          "territory map is right there and the site is not served at wholesale or behind the meter)",
        "envelopes": "Each utility's two cases are its own extremes. A site that is a candidate for two utilities is counted on each in "
                     "its own upper case, which cannot both be true, and the upper case is not checked against what the utility's "
                     "sales could carry.",
        "sites": {"all": int(len(fac)), "resolved": int(is_resolved.sum()), "unresolved": int((~is_resolved).sum()),
                  "by_how_placed": {k: {"sites": int(r["size"]), "resolved": int(r["sum"])} for k, r in counts.iterrows()},
                  "carrying_load": int(fac.in_dose.sum()), "carrying_load_and_unresolved": int((fac.in_dose & ~is_resolved).sum())},
        "thresholds": {},
    }
    site_rows = []
    for theta in (0.02, 0.05):
        th = f"{theta:.0%}"
        lists = json.loads((FROZEN / "treatment_bounds.json").read_text())["thresholds"][th]
        hosts = [(int(x["utility"].split(":")[0]), x["utility"].split(":")[1])
                 for x in lists["sets"]["every_cohort_utility"]["left"] + lists["sets"]["every_cohort_utility"]["unsettled_on_assignment_list"]]
        head = pd.read_csv(FROZEN / "headline_set.csv")
        head = head[head.threshold == th].set_index(KEY)
        out = []
        for k in sorted(hosts, key=lambda k: (k[1], k[0])):
            yb = t.at[k, f"as_built_{th}"]
            years = {name: t.at[k, f"{name}_{th}"] for name in CASES}
            v = verdict("cohort", yb, years, {})
            det = determining_sites(fy, k, int(yb), theta * base[k])
            mine = fy[(fy.utility_id_eia == k[0]) & (fy.state == k[1])]
            at_y = mine[mine.year == int(yb)].set_index("fid").mw
            own = list(mine.drop_duplicates("fid").fid)
            others = [f for f in fac.index[~is_resolved & fac.in_dose]
                      if k[0] in candidates(fac.utility_candidates[f]) and fac.state[f] == k[1] and f not in own]
            row = {"utility": key_of(k), "name": names.get(k), "region": regions.get(k), "first_crossing_as_built": fmt(yb),
                   **{name: fmt(years[name]) for name in CASES}, "verdict": v,
                   "in_the_headline_set_before_this_test": only_ruling_4(head.at[k, "why_not_in_the_headline_set"]),
                   "sites_on_it": len(own), "unresolved_on_it": int(sum(not is_resolved[f] for f in own)),
                   "unresolved_sites_elsewhere_that_list_it": len(others),
                   "determining_sites": det, "determining_sites_unresolved": [f for f in det if not is_resolved[f]]}
            out.append(row)
            if theta == 0.02:
                for f in own + others:
                    r = fac.loc[f]
                    y_mw = fy[(fy.fid == f) & (fy.year == int(yb))].mw.sum()
                    site_rows.append({
                        "host": key_of(k), "host_name": names.get(k), "host_first_crossing": fmt(yb), "site": f, "site_label": site_label(r),
                        "now_on": "this host" if f in own else f"{names.get((int(r.utility_id_eia), r.state))} ({int(r.utility_id_eia)})",
                        "how_placed": r.utility_assign, "resolved": bool(is_resolved[f]), "candidate_territories": r.utility_candidates,
                        "determining_site": f in det,
                        "mw_in_the_crossing_year": round(float(at_y.get(f, y_mw)), 2), "mw_now": round(float(r.mw_full), 2),
                        "share_of_threshold_in_the_crossing_year": round(float(at_y.get(f, y_mw)) * 8.76 / (theta * base[k]), 3),
                        "start_year": fmt(r.energized_year), "year_rests_on": r.date_basis, "size_rests_on": r.mw_basis,
                        "load_history": r.load_history, "state_scale": round(float(r.state_scale), 3),
                        "permit_filed_as_an_update_to_an_existing_source": bool(r.left_censored) if pd.notna(r.left_censored) else False
                        })
        report["thresholds"][th] = {
            "cohort_utilities_tested": len(out), "keep_their_place": int(sum(r["verdict"] == "keeps its place" for r in out)),
            "hosts": out}
    (FROZEN / "assignment_evidence.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    pd.DataFrame(site_rows).to_csv(FROZEN / "assignment_evidence_sites.csv", index=False)
    for th, r in report["thresholds"].items():
        print(th, "cohort utilities tested:", r["cohort_utilities_tested"], "| keep their place:", r["keep_their_place"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
