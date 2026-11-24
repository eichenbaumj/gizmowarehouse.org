#!/usr/bin/env python3
"""Load histories: how fast a site reached its present size, and which utilities that decides.

The inventory gives every site that is not on Epoch's timeline its full
present-day load within three years of opening. A campus that opened in 2010
and grew through 2024 is therefore counted at its 2024 size in 2012
(docs/DECISIONS.md, D-26). This module does three things about that, from load
and sales quantities only. No price data.

1. A slow-build alternative for every such site. The site still starts in its
   energized year, and reaches full load in the year after its latest generator
   permit instead of in its third year. Permits are added as halls are fitted
   out, so the latest permit is a rough upper bound on when the build-out ended;
   it can also be a renewal, so the truth lies between the two paths.
2. The list of utilities for which the choice matters: the first year the load
   share reaches 2% or 5% falls on the other side of 2011 or 2022 (an early
   host, a cohort utility or a late host changes group), or a cohort utility's
   first crossing moves by two years or more.
3. Hand-verified histories, read from verified/buildout.csv, for the sites on
   those utilities. Two kinds:
     single_building  a government record shows one building at the permit's
                      address, with one year built. There is no campus to phase,
                      and the three-year ramp stands.
     phases           dated steps, each a cumulative share of the site's present
                      size, each with a source the session model opened (D-15).
                      Every step ramps over three years like a new site.
   The inventory build reads the same table, so a verified history changes the
   dose, not just this report.

After the verified histories are applied, each utility is recomputed twice: with
every still-unverified site on the three-year ramp, and with every one of them
on the slow path. A utility is settled when the two agree.

4. Utility-level histories (verified/utility_history.csv, D-34): a utility's own
   count of its data center load, read against the same threshold. Where one
   brackets the first crossing, the utility is settled by it whatever the sites'
   paths say, and its first crossing is the one the utility's figures give.
   Site loads and the dose are not changed.

Output: data/frozen/buildout_sensitivity.json
Run:  python3 -I pipeline/facilities/buildout.py --write-county   (after match_county_gis.py; then rebuild the inventory)
      python3 -I pipeline/facilities/buildout.py                  (after build_inventory.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import utility_history as uh  # noqa: E402

VERIFIED_DIR = ROOT / "pipeline" / "facilities" / "verified"
# buildout.csv         histories verified by hand, each source opened by the session model (D-15)
# buildout_county.csv  single buildings matched by rule to a county's building layer (write_county_rows)
VERIFIED = (VERIFIED_DIR / "buildout.csv", VERIFIED_DIR / "buildout_county.csv")
COUNTY_MATCHES = ROOT / "pipeline" / "facilities" / "leads" / "county_gis_matches.csv"
COUNTY_MIN_YEAR = 2005
COUNTY_BUILT = {"Completed", "Existing or Permitted"}
COLUMNS = ["fid", "kind", "year", "cumulative_share", "source_url", "source_quote", "confidence", "checked_on", "note"]
KINDS = {"single_building", "phases"}
BLOCKED_DOMAINS = {"baxtel.com", "datacentermap.com", "datacenters.com", "cleanview.co", "datacenterhawk.com"}
RAMP_YEARS = 3
PERMIT_LAG = 1
COHORTS = (2011, 2022)
THRESHOLDS = (0.02, 0.05)
MOVE_TOLERANCE = 2
KEY = ["utility_id_eia", "state"]


# ---- the verified table -------------------------------------------------------

def load(paths: tuple[Path, ...] | None = None) -> pd.DataFrame:
    """Both verified tables as one. A site with a hand-verified history is not also read from the county rows."""
    parts = []
    for path in (paths or VERIFIED):
        if path.exists():
            parts.append(pd.read_csv(path, dtype={"fid": str, "kind": str, "source_url": str, "source_quote": str,
                                                  "confidence": str, "checked_on": str, "note": str}))
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    if len(parts) == 2:
        parts[1] = parts[1][~parts[1].fid.isin(parts[0].fid)]
    return validate(pd.concat(parts, ignore_index=True)[COLUMNS])


def write_county_rows() -> int:
    """Single buildings, by rule, from the two Virginia county layers (match_county_gis.py).

    A permit row is one building when the county lists exactly one data center
    building at the permit's street address, finished, with a year built of 2005
    or later (the same cuts D-15 set for taking a county year as a start year).
    One building has no campus to phase, so its later generator permits are
    additions or renewals inside that building and the three-year ramp stands.
    This is a government record matched by address, medium confidence; it is not
    a measurement of how fast the building filled.
    """
    from datetime import date
    from pipeline.facilities.match_county_gis import record_url
    m = pd.read_csv(COUNTY_MATCHES)
    rows = []
    for fid, g in m.groupby("fid"):
        if len(g) != 1:
            continue                      # several buildings at the address: a campus, left for hand verification
        r = g.iloc[0]
        if r.status not in COUNTY_BUILT or not (COUNTY_MIN_YEAR <= (r.year_built if pd.notna(r.year_built) else 0) <= date.today().year):
            continue
        quote = (f"{r.county_address} | {r.building_name} | {r.status} | Year Built {int(r.year_built)} | occupancy {r.occupancy_date}"
                 if r.county == "Prince William" else
                 f"{r.county_address} | COM_DATA_CENTER | {r.status} | Demographic Year Built {int(r.year_built)}")
        rows.append({"fid": fid, "kind": "single_building", "year": None, "cumulative_share": None,
                     "source_url": record_url(r.county, r.county_address), "source_quote": quote, "confidence": "medium",
                     "checked_on": str(r.layer_as_of),
                     "note": f"{r.county} County lists one data center building at the permit's street address "
                             f"({r.permit_address}). checked_on is the date of the county's layer."})
    pd.DataFrame(rows, columns=COLUMNS).to_csv(VERIFIED[1], index=False)
    return len(rows)


def validate(t: pd.DataFrame) -> pd.DataFrame:
    """Refuse a table the build should not read. Every row needs a source that was opened."""
    missing = [c for c in COLUMNS if c not in t.columns]
    if missing:
        raise ValueError(f"buildout table is missing columns: {missing}")
    if not set(t.kind.dropna()) <= KINDS or t.kind.isna().any():
        raise ValueError("unknown kind in buildout table")
    dom = t.source_url.map(lambda u: urlparse(u).netloc.replace("www.", "") if isinstance(u, str) else "")
    if (dom == "").any() or dom.isin(BLOCKED_DOMAINS).any() or not t.confidence.isin(["high", "medium"]).all():
        raise ValueError("every buildout row needs a source that is not a directory site, at high or medium confidence")
    if t.source_quote.isna().any() or t.checked_on.isna().any():
        raise ValueError("every buildout row needs a quote from the source and the date it was opened")
    for fid, g in t.groupby("fid"):
        if g.kind.nunique() != 1:
            raise ValueError(f"{fid}: one site, one kind of history")
        if g.kind.iloc[0] == "single_building":
            if len(g) != 1:
                raise ValueError(f"{fid}: a single building has one row")
            continue
        g = g.sort_values("year")
        if g.year.isna().any() or g.cumulative_share.isna().any() or g.year.duplicated().any():
            raise ValueError(f"{fid}: every phase needs its own year and a cumulative share")
        s = g.cumulative_share.values
        if len(g) < 2 or (np.diff(s) <= 0).any() or s[0] <= 0 or abs(s[-1] - 1.0) > 1e-9:
            raise ValueError(f"{fid}: phases need two or more steps whose shares rise to 1.0")
    return t


def phases_by_site(t: pd.DataFrame) -> dict[str, list[tuple[int, float]]]:
    """fid -> [(year, cumulative share)], for the sites with a verified phased history."""
    p = t[t.kind == "phases"].sort_values(["fid", "year"])
    return {fid: [(int(y), float(s)) for y, s in zip(g.year, g.cumulative_share)] for fid, g in p.groupby("fid")}


def single_buildings(t: pd.DataFrame) -> set[str]:
    return set(t[t.kind == "single_building"].fid)


# ---- load paths -----------------------------------------------------------------

def ramp_mw(mw_full: float, start: float, year: int, ramp_years: int = RAMP_YEARS) -> float:
    """Linear ramp from the start year to full load over `ramp_years`."""
    age = year - start
    return 0.0 if age < 0 else float(mw_full) * min(1.0, (age + 1) / ramp_years)


def phased_mw(mw_full: float, phases: list[tuple[int, float]], year: int) -> float:
    """Load in `year` when the site was built in dated steps. Each step ramps like a new site."""
    mw, prev = 0.0, 0.0
    for y, share in phases:
        mw += ramp_mw(mw_full * (share - prev), y, year)
        prev = share
    return mw


def gap_mw(first_mw: float, start: float, first_year: float, year: int) -> float:
    """A measured site already running before its first measured year: a straight line from the start to that year's level.

    An assumption, not a measurement (D-44, T3). Zero before the start; the caller uses the measured series from `first_year` on.
    """
    if year < start or year >= first_year:
        return 0.0
    return float(first_mw) * (year - start + 1) / (first_year - start + 1)


def slow_end_year(energized_year: float, latest_permit_year) -> float:
    """The year a site reaches full load on the slow path."""
    end = energized_year + RAMP_YEARS - 1
    if pd.notna(latest_permit_year):
        end = max(end, latest_permit_year + PERMIT_LAG)
    return end


def slow_mw(mw_full: float, energized_year: float, latest_permit_year, year: int) -> float:
    """Slow-build alternative: start in the energized year, full load the year after the latest permit."""
    end = slow_end_year(energized_year, latest_permit_year)
    return ramp_mw(mw_full, energized_year, year, int(end - energized_year + 1))


# ---- which utilities it matters for ------------------------------------------------

def group(first_year) -> str:
    if pd.isna(first_year):
        return "never"
    return "early" if first_year < COHORTS[0] else ("cohort" if first_year <= COHORTS[1] else "late")


def material(a, b) -> bool:
    """Does moving a first crossing from a to b change the design? (group change, or a cohort year by two or more)"""
    if group(a) != group(b):
        return True
    return group(a) == "cohort" and abs(a - b) >= MOVE_TOLERANCE


def first_crossings(fy: pd.DataFrame, base: pd.Series, theta: float) -> pd.Series:
    g = fy.groupby(KEY + ["year"]).mw.sum().reset_index()
    g["dose"] = g.mw * 8.76 / g.set_index(KEY).index.map(base)
    return g[g.dose >= theta].groupby(KEY).year.min()


def paths(fac: pd.DataFrame, fy: pd.DataFrame, years: list[int], which: dict[str, str]) -> pd.DataFrame:
    """Facility-year load with each non-Epoch site on the path `which` names for it.

    `which[fid]` is "ramp" or "slow"; a site not named keeps the load the inventory
    gave it (Epoch timelines and verified phase histories).
    """
    keep = fy[~fy.fid.isin(which)][["fid"] + KEY + ["year", "mw"]]
    rows = []
    for f in fac[fac.fid.isin(which)].itertuples():
        for y in years:
            mw = (slow_mw(f.mw_full, f.energized_year, f.latest_permit_year, y) if which[f.fid] == "slow"
                  else ramp_mw(f.mw_full, f.energized_year, y))
            if mw > 0:
                rows.append((f.fid, int(f.utility_id_eia), f.state, y, mw))
    return pd.concat([keep, pd.DataFrame(rows, columns=keep.columns)], ignore_index=True)


def counts(first: pd.Series) -> dict:
    g = first.map(group).value_counts()
    return {k: int(g.get(k, 0)) for k in ("early", "cohort", "late")}


def apply_utility_histories(first: pd.Series, settled: dict) -> tuple[pd.Series, list]:
    """First crossings with the utilities a utility-level history settles moved to what it says (D-34).

    `settled` is utility_history.settled(): {(utility, state): {"group", "first_crossing"}}. A cohort utility
    takes the history's year. An early host keeps the inventory's year if that is before the cohorts and
    otherwise is put at the year before they begin. A utility the history puts outside the cohorts loses any
    crossing inside them. Returns the new series and the keys now known only as "outside the cohorts".
    """
    out, outside = first.copy(), []
    for k, v in settled.items():
        if v["group"] == "cohort":
            out[k] = v["first_crossing"]
        elif v["group"] == "early":
            if k not in out.index or out[k] >= COHORTS[0]:
                out[k] = COHORTS[0] - 1
        else:
            out = out.drop(k, errors="ignore")
            outside.append(k)
    return out, outside


def reconcile(history: dict, ramp: pd.DataFrame, slow: pd.DataFrame) -> None:
    """Put the inventory's load beside every utility figure, on the ramp and on the slow path (in place)."""
    tot = lambda f: f.groupby(KEY + ["year"]).mw.sum() * 8.76  # noqa: E731
    r, s = tot(ramp), tot(slow)
    for key, entry in history.items():
        u, st = key.split(":")
        for fig in entry.get("figures", []):
            k = (int(u), st, fig["year"])
            fig["inventory_gwh_three_year_ramp"] = round(float(r.get(k, 0.0)), 1)
            fig["inventory_gwh_slow_path"] = round(float(s.get(k, 0.0)), 1)


def main() -> int:
    if "--write-county" in sys.argv:
        print("single buildings written from county records:", write_county_rows())
        return 0
    fac = pd.read_parquet(ROOT / "data" / "interim" / "facilities.parquet")
    fy = pd.read_parquet(ROOT / "data" / "interim" / "facility_year.parquet")
    dose = pd.read_parquet(ROOT / "data" / "interim" / "utility_year_dose.parquet")
    q = pd.read_parquet(ROOT / "data" / "interim" / "panel_quantities.parquet")
    names = q.groupby(KEY).utility_name.last()
    base = dose.drop_duplicates(KEY).set_index(KEY).base_retail_gwh
    years = list(range(int(fy.year.min()), int(fy.year.max()) + 1))
    t = load()
    phased, single = set(phases_by_site(t)), single_buildings(t)

    # Epoch's sites and the sites whose operator reports their electricity year by year (D-35) have measured histories.
    sites = fac[fac.in_dose & ~fac.is_crypto & (fac.src != "epoch") & (fac.load_history != "operator_reported_energy")].copy()
    fy = fy[~fy.crypto]
    sites["slow_end"] = [slow_end_year(e, lp) for e, lp in zip(sites.energized_year, sites.latest_permit_year)]
    sites["could_be_phased"] = sites.slow_end > sites.energized_year + RAMP_YEARS - 1
    open_sites = sites[sites.could_be_phased & ~sites.fid.isin(phased | single)]
    everything = sites[sites.could_be_phased]

    report = {
        "what_this_is": "First year each utility's data center load reaches the threshold, with sites not on Epoch's "
                        "timeline on the three-year ramp, on the slow path (full load the year after the latest "
                        "generator permit), and after hand-verified histories are applied.",
        "sites_with_electricity_reported_by_the_operator": int((fac.in_dose & (fac.load_history == "operator_reported_energy")).sum()),
        "sites_not_on_epochs_timeline": int(len(sites)),
        "of_which_the_slow_path_differs": int(len(everything)),
        "their_mw": round(float(everything.mw_full.sum()), 1),
        "verified": {"single_building_by_government_record": int(everything.fid.isin(single).sum()),
                     "phased_history_from_opened_sources": int(everything.fid.isin(phased).sum()),
                     "mw_verified": round(float(everything[everything.fid.isin(phased | single)].mw_full.sum()), 1),
                     "still_unverified": int(len(open_sites)),
                     "mw_still_unverified": round(float(open_sites.mw_full.sum()), 1)},
        "definition_of_material": f"the utility changes group (early host before {COHORTS[0]}, cohort {COHORTS[0]} to "
                                  f"{COHORTS[1]}, late host, never), or a cohort utility's first crossing moves by "
                                  f"{MOVE_TOLERANCE} years or more",
        "thresholds": {},
    }
    # Before any verified history: every phaseable site on the ramp, then every one on the slow path.
    all_ramp = paths(fac, fy, years, dict.fromkeys(everything.fid, "ramp"))
    all_slow = paths(fac, fy, years, dict.fromkeys(everything.fid, "slow"))
    # After: verified histories as the inventory carries them; the rest on the ramp, then on the slow path.
    rest_ramp = fy[["fid"] + KEY + ["year", "mw"]]
    rest_slow = paths(fac, fy, years, dict.fromkeys(open_sites.fid, "slow"))
    # Utility-level histories (D-34): the utility's own count of its data center load, read against the same base.
    sales = q.set_index(KEY + ["year"]).total_retail_mwh / 1000.0
    all_base = base.combine_first(q[q.year.isin((2009, 2010, 2011))].groupby(KEY).total_retail_mwh.mean() / 1000.0)
    history = uh.read(uh.load(), all_base, sales, THRESHOLDS)
    reconcile(history, rest_ramp, rest_slow)
    report["utility_level_histories"] = history
    worklist = []
    for theta in THRESHOLDS:
        a, b = first_crossings(all_ramp, base, theta), first_crossings(all_slow, base, theta)
        c, d = first_crossings(rest_ramp, base, theta), first_crossings(rest_slow, base, theta)
        x = pd.concat([a.rename("ramp"), b.rename("slow"), c.rename("now"), d.rename("now_slow")], axis=1)
        before = x[[material(r, s) for r, s in zip(x.ramp, x.slow)]]
        after = x[[material(r, s) for r, s in zip(x.now, x.now_slow)]]
        by_history = uh.settled(history, theta)
        settled_rows = [{"utility": f"{u}:{st}", "name": names.get((u, st)), "group": v["group"],
                         "first_crossing": v["first_crossing"],
                         "inventory_three_year_ramp": None if (u, st) not in x.index or pd.isna(x.ramp[(u, st)]) else int(x.ramp[(u, st)]),
                         "inventory_slow_path": None if (u, st) not in x.index or pd.isna(x.slow[(u, st)]) else int(x.slow[(u, st)]),
                         "was_unsettled_on_site_histories": (u, st) in after.index}
                        for (u, st), v in sorted(by_history.items())]
        after = after[[k not in by_history for k in after.index]]
        final, outside = apply_utility_histories(c.dropna(), by_history)
        fmt = lambda v: None if pd.isna(v) else int(v)  # noqa: E731
        rows = lambda f: [{"utility": f"{int(u)}:{st}", "name": names.get((u, st)), "three_year_ramp": fmt(r.ramp),  # noqa: E731
                           "slow_path": fmt(r.slow), "after_verification": fmt(r.now),
                           "after_verification_rest_slow": fmt(r.now_slow)} for (u, st), r in f.iterrows()]
        report["thresholds"][f"{theta:.0%}"] = {
            "three_year_ramp_everywhere": counts(a),
            "slow_path_everywhere": counts(b),
            "after_verified_histories": counts(c),
            "after_verified_histories_rest_on_the_slow_path": counts(d),
            "utilities_the_choice_was_material_for": len(before),
            "of_which_settled_by_verified_histories": len(before) - len(before.index.intersection(after.index)),
            "utilities_still_unsettled": rows(after),
            "settled_by_utility_level_history": settled_rows,
            "after_verified_and_utility_level_histories": {**counts(final), "outside_the_cohorts_on_the_utilitys_own_figures": len(outside)},
            "utilities_the_choice_was_material_for_list": rows(before),
        }
        for (u, st) in after.index:
            s = open_sites[(open_sites.utility_id_eia == u) & (open_sites.state == st)]
            worklist += [(fid, theta) for fid in s.fid]
    report["unverified_sites_on_unsettled_utilities"] = len({w[0] for w in worklist})
    (ROOT / "data" / "frozen" / "buildout_sensitivity.json").write_text(json.dumps(report, indent=2) + "\n")
    slim = {k: v for k, v in report.items() if k != "thresholds"}
    slim["thresholds"] = {k: {a: b for a, b in v.items() if not a.endswith("_list")} for k, v in report["thresholds"].items()}
    print(json.dumps(slim, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
