#!/usr/bin/env python3
"""Build the data-center facility inventory and the utility-year load "dose".

Touches NO residential price data. Inputs are the three facility sources, the
service-territory polygons, and the quantity side of the EIA-861 panel.

What a row means
----------------
One facility (a permitted site, an OpenStreetMap object not matched to a
permitted site, or an Epoch AI site), with: where it is, which utility serves
it, the year it began drawing power, and how much it draws.

Load
----
Permitted sites: average load = KAPPA x permitted backup-generator capacity.
Operators size backup generation to carry the building, so generator capacity
is an upper bound on draw. Business Insider's own method brackets average draw
at 30% to 60% of generator capacity; we fix KAPPA = 0.5 before seeing any
outcome data and report 0.3 and 0.6 as sensitivities. We deliberately do NOT
tune KAPPA to make the inventory hit EPRI's state totals: doing that would
hide undercounting (inflating the sites we have to stand in for sites we are
missing). Instead the EPRI comparison is reported as a coverage gate.
Epoch sites: facility power from Epoch's own dated timeline, no scaling.

Dates
-----
energized_year = first permit year + PERMIT_LAG. A generator permit is issued
before the building runs, so the lag is positive; the validation sample
(docs/dating-validation.md) is what pins it down. Load then ramps linearly to
full over RAMP_YEARS, unless the site has a hand-verified phased history in
verified/buildout.csv, in which case each dated step ramps over RAMP_YEARS
(pipeline/facilities/buildout.py; docs/DECISIONS.md, D-28). Rows whose only permit is an "existing update" are
flagged left-censored: the site may be older than its first permit on file.

Utility
-------
Point-in-polygon against retail service territories. Polygons overlap, so we
take the smallest polygon containing the point (a city utility inside a large
investor-owned territory wins), keep every candidate, and flag ambiguity.

Step D (docs/gate1/step-d-inventory-design-2026-11-18.md and its addendum of Joe's rulings): the adopted
corrections reach the inventory through pipeline/facilities/corrections.py, at fixed points of main(): coordinate
corrections before the territory join (candidates become the union of old and new); the year-built relabel after the
operator-reported block; dates and capacity splits at their conventions before the state anchoring (a row with no
convention is LOAD UNKNOWN, carries no load and is listed with every utility it reaches); assign, reopen and candidates
corrections after the utility block. `--no-step-d` builds exactly as before step D, which is how the frozen inventory of
2026-11-14 is reproduced. The Census geocoder is not called in step D: a cache miss stops the run.

Run:  python3 -I pipeline/facilities/build_inventory.py [--corrections FILE] [--no-step-d]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import Point  # noqa: E402

from pipeline.electricity import panel  # noqa: E402
from pipeline.electricity import succession as succ  # noqa: E402
from pipeline.facilities import buildout, site_energy, sources  # noqa: E402
from pipeline.facilities import corrections as cx  # noqa: E402

RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"

KAPPA = 0.5            # average draw as a share of backup-generator capacity
KAPPA_SENS = (0.3, 0.6)
PERMIT_LAG = 1         # years from first generator permit to energization
RAMP_YEARS = 3         # linear ramp to full load
MATCH_M_OSM = 400      # an OSM object this close to a permitted site is the same site
MATCH_M_EPOCH = 2500   # Epoch campuses are large; match more loosely
BASE_YEARS = (2009, 2010, 2011)  # fixed denominator so a data center cannot move it
YEARS = list(range(2001, 2026))
EQUAL_AREA = 5070      # CONUS Albers, metres
SCALE_LO, SCALE_HI = 0.2, 3.0  # allowed range for the state anchoring factor
GEOCODE_OFFLINE = True  # step D: never call the geocoder; an address missing from the cache stops the run


def to_points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326).to_crs(EQUAL_AREA)


def geocode_epoch(sites: pd.DataFrame) -> pd.DataFrame:
    """Census Bureau geocoder for Epoch street addresses, cached on disk."""
    cache_path = RAW / "facilities" / "epoch" / "geocode_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    out = []
    for _, r in sites.iterrows():
        addr = str(r["Address"]) if pd.notna(r["Address"]) else ""
        if addr and addr not in cache and GEOCODE_OFFLINE:
            raise SystemExit(f"geocode cache has no entry for {addr!r}; the geocoder is not called in step D (GEOCODE_OFFLINE)")
        if addr and addr not in cache:
            q = urllib.parse.urlencode({"address": addr, "benchmark": "Public_AR_Current", "format": "json"})
            url = f"https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?{q}"
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    m = json.load(resp)["result"]["addressMatches"]
                cache[addr] = ({"lat": m[0]["coordinates"]["y"], "lon": m[0]["coordinates"]["x"],
                                "state": m[0]["addressComponents"]["state"]} if m else None)
            except Exception as e:  # leave unresolved; reported below, never guessed
                cache[addr] = None
                print("geocode failed:", addr, repr(e)[:80])
            time.sleep(0.2)
        g = cache.get(addr) or {}
        out.append({"lat": g.get("lat"), "lon": g.get("lon"), "state": g.get("state", "")})
    cache_path.write_text(json.dumps(cache, indent=1))
    return pd.concat([sites.reset_index(drop=True), pd.DataFrame(out)], axis=1)


def nearest_match(left: gpd.GeoDataFrame, right: gpd.GeoDataFrame, max_m: float, right_id: str) -> pd.Series:
    """For each row of `left`, the id of the nearest `right` row within max_m, else NaN."""
    j = gpd.sjoin_nearest(left[["geometry"]], right[[right_id, "geometry"]], max_distance=max_m, how="left")
    return j[~j.index.duplicated()][right_id].reindex(left.index)


def assign_utility(pts: gpd.GeoDataFrame) -> pd.DataFrame:
    terr = gpd.read_file(RAW / "territories" / "retail_service_territories.geojson")
    terr = terr[terr.ID.astype(str).str.fullmatch(r"\d+")].copy()
    terr["utility_id_eia"] = terr.ID.astype(int)
    terr["geometry"] = terr.geometry.buffer(0)  # repairs self-intersections left by simplification
    terr = terr.to_crs(EQUAL_AREA)
    terr["poly_km2"] = terr.geometry.area / 1e6
    j = gpd.sjoin(pts[["fid", "geometry"]], terr[["utility_id_eia", "NAME", "TYPE", "poly_km2", "geometry"]],
                  predicate="within", how="left")
    j = j.sort_values(["fid", "poly_km2"]).dropna(subset=["utility_id_eia"])
    cands = j.groupby("fid").utility_id_eia.agg(lambda x: [int(v) for v in x])
    return pd.DataFrame({"candidates": cands})


def pick_utilities(fac: pd.DataFrame, capacity_gwh: pd.Series, mapping: succ.Mapping | None = None) -> pd.DataFrame:
    """Choose one serving utility per facility from its overlapping candidates.

    Territory polygons carry the ids utilities had when the map was drawn. A
    candidate that has since been folded into another utility is read as its
    successor (pipeline/electricity/succession.py), which is the unit the panel
    carries.

    Start from the smallest polygon containing the point (a city utility inside
    a big investor-owned territory). Then apply one physical check: a utility
    cannot be serving a data center that uses more electricity than the utility
    sells. Capacity is the utility's largest annual retail sales in 2020-2025
    (quantities only, no prices). Facilities are placed largest first; if the
    smallest polygon cannot hold the load, the next larger candidate is tried.
    This is what moves the Mesa, Arizona campuses off the small city utility
    and onto Salt River Project. Every site of 50 MW or more is still verified
    by hand afterwards.
    """
    used: dict[tuple[int, str], float] = {}
    rows = []
    order = fac.assign(mwsort=fac.mw_full.fillna(0)).sort_values("mwsort", ascending=False)
    for f in order.itertuples():
        cands = f.candidates if isinstance(f.candidates, list) else []
        if mapping:
            cands = list(dict.fromkeys(succ.final_id(u, f.state, mapping) for u in cands))  # order kept, repeats dropped
        gwh = float(f.mwsort) * 8.76
        choice, how = None, "none"
        for k, u in enumerate(cands):
            cap = capacity_gwh.get((u, f.state), np.nan)
            if np.isnan(cap):
                continue  # not a reporting retail utility in this state
            if used.get((u, f.state), 0.0) + gwh <= cap:
                choice = u
                how = "unique" if len(cands) == 1 else ("smallest_polygon" if k == 0 else "next_larger_load_feasible")
                break
        if choice is None and cands:
            # Nothing fits (or no candidate reports sales): fall back to the largest
            # reporting candidate and flag it loudly.
            rep = [u for u in cands if not np.isnan(capacity_gwh.get((u, f.state), np.nan))]
            choice = (rep or cands)[-1]
            how = "fallback_largest_flagged"
        if choice is not None:
            used[(choice, f.state)] = used.get((choice, f.state), 0.0) + gwh
        rows.append((f.fid, choice, how, ";".join(str(c) for c in cands), len(cands)))
    return pd.DataFrame(rows, columns=["fid", "utility_id_eia", "utility_assign", "utility_candidates", "n_candidates"]).set_index("fid")


def apply_overrides(fac: pd.DataFrame, ov: pd.DataFrame) -> pd.DataFrame:
    """Lay hand-verified facts (overrides.csv, indexed by fid) over the permit-based guesses.

    A sourced start year replaces the permit-based one. A site a dated public page
    shows as still planned or under construction loses its start year, and with it
    any load in the panel years (docs/DECISIONS.md, D-15). A verified load replaces
    the generator-based estimate, except on Epoch rows, which keep their dated
    timeline. Rows flagged as not a data center are dropped. `verified_fields`
    records which facts on each row are verified.
    """
    fac["verified_fields"] = ""
    if len(ov):
        o = ov.reindex(fac.fid)
        if "drop_not_data_center" in o:
            fac = fac[~(o.drop_not_data_center.eq(True).values)].reset_index(drop=True)
            o = ov.reindex(fac.fid)
        yr = o.energized_year.values if "energized_year" in o else np.full(len(fac), np.nan)
        has_yr = ~pd.isna(yr)
        fac.loc[has_yr, "energized_year"] = yr[has_yr]
        fac.loc[has_yr, "date_basis"] = "verified_public_source"
        fac.loc[has_yr, "left_censored"] = False
        nyo = o.not_yet_operating.eq(True).values if "not_yet_operating" in o else np.zeros(len(fac), dtype=bool)
        fac.loc[nyo, "energized_year"] = np.nan
        fac.loc[nyo, "date_basis"] = "verified_not_yet_operating"
        fac.loc[nyo, "left_censored"] = False
        ld = o.load_mw_2025.values if "load_mw_2025" in o else np.full(len(fac), np.nan)
        has_ld = ~pd.isna(ld) & (fac.src != "epoch").values  # Epoch rows keep their dated timeline
        fac.loc[has_ld, "mw_full"] = ld[has_ld]
        fac.loc[has_ld, "mw_basis"] = "verified_public_figure"
        fac["verified_fields"] = (np.where(has_yr, "year;", "") + pd.Series(np.where(nyo, "status;", ""))
                                  + pd.Series(np.where(has_ld, "load;", "")))
        if "facility_type" in o:
            fac["facility_type"] = o.facility_type.values
    if "facility_type" not in fac:
        fac["facility_type"] = None
    return fac


def epoch_mw(epoch_path: dict, name: str, year: int) -> float:
    """An Epoch site's power in `year`: the most its dated timeline shows up to that year."""
    past = [v for (n, yy), v in epoch_path.items() if n == name and yy <= year]
    return float(max(past)) if past else 0.0


def epoch_gaps(fac: pd.DataFrame, epoch_path: dict, skip: set | None = None) -> dict[str, tuple[int, int, float]]:
    """Epoch rows whose sourced start year is before Epoch's first timeline entry: fid -> (start, first entry year, its MW).

    Epoch's timeline carries nothing for the years such a site was already running. Those years
    take a straight line from the sourced start to the first entry (buildout.gap_mw; D-44, T3).
    `skip` names rows whose operator reports their electricity, which governs instead (D-35).
    """
    first: dict[str, tuple[int, float]] = {}
    for (name, yy), v in sorted(epoch_path.items(), key=lambda kv: kv[0][1]):
        if v > 0 and name not in first:
            first[name] = (int(yy), float(v))
    out = {}
    e = fac[(fac.src == "epoch") & (fac.date_basis == "verified_public_source") & fac.energized_year.notna()]
    for fid, start in zip(e.fid, e.energized_year):
        name = fid.split(":", 1)[1]
        if fid in (skip or set()) or name not in first:
            continue
        if start < first[name][0]:
            out[fid] = (int(start), first[name][0], first[name][1])
    return out


def site_mw(src: str, fid: str, energized_year, mw_full, year: int, epoch_path: dict,
            phases: dict | None = None, energy: dict | None = None, gaps: dict | None = None) -> float:
    """Load a site carries in `year`. The one rule, used by the dose and by the state anchoring.

    A site whose operator reports its electricity year by year carries what the
    operator reports (pipeline/facilities/site_energy.py; D-35), on Epoch rows too.
    Epoch sites follow Epoch's dated timeline; one with a sourced start before its
    first entry (`gaps`, from epoch_gaps) carries a straight line up to that entry
    in the years between (D-44, T3). A site with a hand-verified phased
    history (pipeline/facilities/buildout.py) is built in its dated steps, each
    ramping over RAMP_YEARS. Every other site starts in its energized year and
    ramps linearly to its full load over RAMP_YEARS.
    """
    if energy and fid in energy:
        after = epoch_mw(epoch_path, fid.split(":", 1)[1], year) if src == "epoch" else None
        return site_energy.energy_mw(energy[fid], year, after)
    if src == "epoch":
        if gaps and fid in gaps and gaps[fid][0] <= year < gaps[fid][1]:
            return buildout.gap_mw(gaps[fid][2], gaps[fid][0], gaps[fid][1], year)
        return epoch_mw(epoch_path, fid.split(":", 1)[1], year)
    if pd.isna(mw_full):
        return 0.0
    if phases and fid in phases:
        return buildout.phased_mw(mw_full, phases[fid], year)
    if pd.isna(energized_year):
        return 0.0
    return buildout.ramp_mw(mw_full, energized_year, year, RAMP_YEARS)


def state_anchor(fac: pd.DataFrame, measured: pd.Series, epri_twh: pd.Series, epoch_path: dict,
                 year: int = 2024, phases: dict | None = None, energy: dict | None = None,
                 gaps: dict | None = None) -> pd.DataFrame:
    """Per state: EPRI's total, our permit-based and measured totals for `year`, and the scale factor.

    `measured` marks rows that are not scaled (Epoch sites and loads from a public
    figure). Their load in `year` is subtracted from EPRI's total before the
    permit-based rows are scaled to the remainder. An Epoch site counts for what
    its timeline shows in `year`, not for its present capacity on the generic ramp.
    """
    dated = fac[fac.energized_year.notna() & fac.mw_full.notna()]
    mw = [site_mw(s, f, ey, m, year, epoch_path, phases, energy, gaps)
          for s, f, ey, m in zip(dated.src, dated.fid, dated.energized_year, dated.mw_full)]
    twh = pd.Series(np.array(mw, dtype=float) * 8.76 / 1000.0, index=dated.index)
    is_measured = measured.reindex(dated.index)
    permit_twh = twh[~is_measured].groupby(dated.state[~is_measured]).sum()
    epoch_twh = twh[is_measured].groupby(dated.state[is_measured]).sum()
    t = pd.DataFrame({"epri_twh": epri_twh, "permit_twh": permit_twh, "epoch_twh": epoch_twh}).fillna(0.0)
    t["raw_factor"] = (t.epri_twh - t.epoch_twh).clip(lower=0) / t.permit_twh.replace(0, np.nan)
    t["factor"] = t.raw_factor.clip(SCALE_LO, SCALE_HI).fillna(1.0)
    t["flag"] = np.select(
        [t.epri_twh < 0.25, t.raw_factor.isna(), t.raw_factor > SCALE_HI, t.raw_factor < SCALE_LO],
        ["small_state", "no_dated_permits", "undercounted", "overcounted"], "ok")
    return t


def relocate(fac: gpd.GeoDataFrame, locations: dict, unresolved: dict) -> tuple[gpd.GeoDataFrame, dict]:
    """Coordinate corrections (Joe, R8): each listed row moves to its parcel centroid, labelled a coordinate convention;
    the rows whose location stays unresolved are labelled so. Returns the frame and each moved row's original point."""
    fac = fac.copy()
    fac["location_status"] = cx.LOCATION_AS_SOURCED
    old = {}
    for fid, r in locations.items():
        hit = fac.index[fac.fid == fid]
        if len(hit) != 1:
            raise SystemExit(f"step_d_locations.json names {fid}, which is in the inventory {len(hit)} times")
        i = hit[0]
        old[fid] = fac.at[i, "geometry"]
        lat, lon = float(r["centroid"]["lat"]), float(r["centroid"]["lon"])
        fac.loc[i, ["lat", "lon", "location_status"]] = [lat, lon, cx.LOCATION_CONVENTION]
        fac.loc[[i], "geometry"] = gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs=4326).to_crs(EQUAL_AREA).values
    for fid in unresolved:
        fac.loc[fac.fid == fid, "location_status"] = cx.LOCATION_UNRESOLVED_LABEL
    return fac, old


def candidates_after_relocation(fac: gpd.GeoDataFrame, old: dict, assign=None) -> pd.DataFrame:
    """Territory candidates at the (corrected) points; for a moved row, the union of the candidates at its new point and at
    its old one, the new point's first. A supplier is never removed because a centroid falls on one side of a line."""
    assign = assign or assign_utility
    new = assign(fac)
    if not old:
        return new
    olds = gpd.GeoDataFrame({"fid": list(old)}, geometry=list(old.values()), crs=fac.crs)
    before = assign(olds)
    for fid in old:
        n = new.candidates.get(fid, []) if fid in new.index else []
        o = before.candidates.get(fid, []) if fid in before.index else []
        new.loc[fid, "candidates"] = None
        new.at[fid, "candidates"] = cx.union_candidates(n, o)
    return new


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrections", default=str(cx.CORRECTIONS), help="the corrections file in force")
    ap.add_argument("--no-step-d", action="store_true", help="build as before step D (reproduces the 2026-11-14 inventory)")
    args = ap.parse_args(argv)
    step_d = not args.no_step_d
    corr = cx.load(args.corrections) if step_d else []
    locations = cx.load_locations() if step_d else {}
    bi = sources.load_bi()
    osm = sources.load_osm()
    ep_sites, ep_tl = sources.load_epoch()
    ep_us = geocode_epoch(ep_sites[ep_sites.Country == "United States"])

    # ---- permitted sites (backbone) -----------------------------------
    bi = bi.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    bi["fid"] = bi.src_id
    bi["left_censored"] = bi.permit_kind.str.lower().eq("existing update")
    bi["mw_full"] = KAPPA * bi.generator_kw / 1000.0
    bi["mw_basis"] = np.where(bi.generator_kw.notna(), "generator_capacity_x_kappa", "missing")
    bi["energized_year"] = bi.first_permit_year + PERMIT_LAG
    bi["date_basis"] = "first_generator_permit_plus_lag"
    g_bi = to_points(bi)

    # ---- OpenStreetMap: attach to permitted sites, keep the rest -------
    g_osm = to_points(osm)
    g_osm["bi_match"] = nearest_match(g_osm, g_bi, MATCH_M_OSM, "fid")
    osm_only = g_osm[g_osm.bi_match.isna()].copy()
    osm_only["fid"] = osm_only.src_id
    osm_only["mw_full"] = osm_only.osm_mw
    osm_only["mw_basis"] = np.where(osm_only.osm_mw.notna(), "osm_tag", "missing")
    osm_only["energized_year"] = osm_only.osm_start_year
    osm_only["date_basis"] = np.where(osm_only.osm_start_year.notna(), "osm_start_date_tag", "undated")
    osm_only["left_censored"] = False

    # ---- Epoch: authoritative for the sites it covers ------------------
    ov_path = ROOT / "pipeline" / "facilities" / "verified" / "overrides.csv"
    ov = pd.read_csv(ov_path).set_index("fid") if ov_path.exists() else pd.DataFrame()
    if len(ov) and "lat" in ov:
        hand = ov[ov.lat.notna()]
        key = "epoch:" + ep_us["Name"]
        need = ep_us.lat.isna() & key.isin(hand.index)
        ep_us.loc[need, "lat"] = key[need].map(hand.lat).values
        ep_us.loc[need, "lon"] = key[need].map(hand.lon).values
    ep_ok = ep_us.dropna(subset=["lat", "lon"]).copy()
    ep_ok["fid"] = "epoch:" + ep_ok["Name"]
    g_ep = to_points(ep_ok)
    g_ep["bi_match"] = nearest_match(g_ep, g_bi, MATCH_M_EPOCH, "fid")
    tl = ep_tl[ep_tl["Data center"].isin(ep_ok["Name"])].copy()
    tl["year"] = tl.Date.dt.year
    ep_year = tl.groupby(["Data center", "year"])["Power (MW)"].max().reset_index()
    first_on = ep_year[ep_year["Power (MW)"] > 0].groupby("Data center").year.min()
    g_ep["energized_year"] = g_ep["Name"].map(first_on)
    g_ep["mw_full"] = g_ep["Current power (MW)"]
    g_ep["operator"] = g_ep["Owner"].astype(str).str.replace(r"\s*#\w+", "", regex=True)

    # Permitted sites that are really an Epoch campus are dropped from the
    # generator-based rows so the campus is not counted twice.
    superseded = set(g_ep.bi_match.dropna())
    core = g_bi[~g_bi.fid.isin(superseded)]

    keep = ["fid", "src", "lat", "lon", "state", "operator", "energized_year", "date_basis",
            "mw_full", "mw_basis", "left_censored", "geometry"]
    g_ep = g_ep.assign(src="epoch", date_basis="epoch_timeline", mw_basis="epoch_timeline", left_censored=False)
    fac = pd.concat([core[keep + ["first_permit_year", "latest_permit_year", "generator_kw", "county_name"]],
                     osm_only[keep + ["name"]], g_ep[keep + ["Name"]]], ignore_index=True)
    fac = gpd.GeoDataFrame(fac, geometry="geometry", crs=EQUAL_AREA)

    # ---- sites found by the state sweeps that no source above carried ----
    ns_path = ROOT / "pipeline" / "facilities" / "verified" / "new_sites.csv"
    if ns_path.exists() and ns_path.stat().st_size > 5:
        ns = pd.read_csv(ns_path)
        has_xy = ns.lat.notna() & ns.lon.notna()
        geom = gpd.GeoSeries([None] * len(ns), crs=EQUAL_AREA)
        if has_xy.any():
            pts = gpd.GeoSeries(gpd.points_from_xy(ns.lon[has_xy], ns.lat[has_xy]), crs=4326).to_crs(EQUAL_AREA)
            geom.loc[has_xy[has_xy].index] = pts.values
        add = gpd.GeoDataFrame({
            "fid": ns.fid, "src": "state_search", "lat": ns.lat, "lon": ns.lon, "state_preset": ns.state,
            "operator": ns.operator, "name": ns.name, "energized_year": np.nan, "date_basis": "undated",
            "mw_full": np.nan, "mw_basis": "missing", "left_censored": False}, geometry=geom, crs=EQUAL_AREA)
        fac = pd.concat([fac, add], ignore_index=True)
        fac = gpd.GeoDataFrame(fac, geometry="geometry", crs=EQUAL_AREA)
    moved_points = {}
    if step_d:
        fac, moved_points = relocate(fac, locations, cx.LOCATION_UNRESOLVED)
    fac = fac.join(candidates_after_relocation(fac, moved_points), on="fid")

    # State from the point itself (sources disagree on formatting; the point does not).
    st_path = RAW / "territories" / "states.gpkg"
    if not st_path.exists():
        gpd.read_file("https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_20m.zip").to_file(st_path, driver="GPKG")
    states = gpd.read_file(st_path).to_crs(EQUAL_AREA)
    st = gpd.sjoin(fac[["fid", "geometry"]], states[["STUSPS", "geometry"]], how="left")
    fac["state"] = st.drop_duplicates("fid").set_index("fid").STUSPS.reindex(fac.fid).values
    if "state_preset" in fac:  # new sites without coordinates carry the state they were found in
        fac["state"] = fac.state.fillna(fac.state_preset)

    # ---- hand-verified facts override permit-based guesses ---------------
    fac = apply_overrides(fac, ov)
    # Cryptocurrency mines are large loads but they are not what the public claim is
    # about. They are kept, flagged, and counted separately (docs/DECISIONS.md, D-11).
    fac["is_crypto"] = fac.facility_type.eq("crypto")
    # Sites whose operator publishes their electricity year by year (D-35): the reported MWh are the load.
    # The site's size for reporting is its last reported year; a site that had only a permit-based
    # year, or none, takes the first year the operator reports electricity there.
    e_rows, e_sites = site_energy.load()
    energy = site_energy.paths(e_rows, e_sites, dict(zip(fac.fid, fac.generator_kw)))
    missing_rows = sorted(set(energy) - set(fac.fid))
    if missing_rows:
        raise SystemExit(f"site_energy_sites.csv names rows that are not in the inventory: {missing_rows}")
    has_energy = fac.fid.isin(energy)
    fac.loc[has_energy, "mw_full"] = [energy[f][max(energy[f])] for f in fac.fid[has_energy]]
    fac.loc[has_energy, "mw_basis"] = "operator_reported_energy"
    unsourced = has_energy & (fac.date_basis != "verified_public_source")
    fac.loc[unsourced, "energized_year"] = [float(site_energy.first_year(energy[f])) for f in fac.fid[unsourced]]
    fac.loc[unsourced, "date_basis"] = "operator_reported_energy"
    fac.loc[unsourced, "left_censored"] = False
    measured = (fac.src == "epoch") | fac.mw_basis.isin(["verified_public_figure", "operator_reported_energy"])
    year_built_ids = []
    if step_d:                                                   # Joe, R1: relabel only; years and loads unchanged
        f2, year_built_ids = cx.relabel_year_built(fac.set_index("fid"))
        fac = f2.reset_index()

    epoch_path = {(r["Data center"], int(r.year)): r["Power (MW)"] for _, r in ep_year.iterrows()}
    # Hand-verified build-out histories (D-28): dated steps for campuses built in phases.
    history = buildout.load()
    phases = buildout.phases_by_site(history)
    # Epoch rows already running before Epoch's first entry: a straight line up to that entry (D-44, T3).
    gaps = epoch_gaps(fac, epoch_path, skip=set(energy))
    fac["load_history"] = np.select(
        [has_energy, fac.fid.isin(gaps), fac.src == "epoch", fac.fid.isin(phases), fac.fid.isin(buildout.single_buildings(history))],
        ["operator_reported_energy", "epoch_timeline_after_an_assumed_line", "epoch_timeline", "verified_phases",
         "single_building_record"], "three_year_ramp")

    # ---- anchor state load levels to EPRI (see docs/DECISIONS.md, D-2) ----
    # Generator capacity is a noisy proxy for load: at KAPPA = 0.5 Virginia's
    # permits imply 2.5x EPRI's state total while several states are well under.
    # We keep the permits for WHERE and WHEN, and scale permit-based load within
    # each state so the 2024 state total matches EPRI. Epoch rows are measured
    # and are not scaled, and what they count for in 2024 is what Epoch's dated
    # timeline shows for 2024, the same quantity the dose uses (D-27). The
    # factor is clipped to [SCALE_LO, SCALE_HI]; states outside that band are
    # flagged as having an inadequate inventory.
    fac["mw_full_raw"] = fac.mw_full
    fac["state_scale"] = 1.0
    fac["state_coverage_flag"] = "no_epri_anchor"
    timing_report = {"applied": [], "load_unknown": []}
    if step_d:                                                   # dates and capacity at their conventions (Joe, R2, R4)
        f2, phases, timing_report = cx.apply_timing(fac.set_index("fid"), phases, corr)
        fac = f2.reset_index()
        fac["mw_full_raw"] = fac.mw_full
        measured = (fac.src == "epoch") | fac.mw_basis.isin(["verified_public_figure", "operator_reported_energy"])
    epri_path = RAW / "epri" / "epri_state_dashboard.json"
    scale_table = None
    if epri_path.exists():
        e = pd.DataFrame(json.loads(epri_path.read_text())["rows"])
        e24 = e[(e.scenario == "hist") & (e.year == 2024) & (e.state != "US")].set_index("state").annual_TWh
        # An Epoch row's assumed line before its first entry is not a measurement, so it is left out here: in the
        # anchoring the row counts for what Epoch's timeline shows, as it did before the line existed (D-45).
        t = state_anchor(fac, measured, e24, epoch_path, phases=phases, energy=energy)
        scale_table = t
        # The same table for each of EPRI's four historical years, before any scaling: what the treatment-history
        # bounds read (pipeline/facilities/treatment_bounds.py; D-44). Only 2024 sets the factor.
        hist_years = sorted(int(y) for y in e[e.scenario == "hist"].year.unique())
        by_year = []
        for hy in hist_years:
            tot = e[(e.scenario == "hist") & (e.year == hy) & (e.state != "US")].set_index("state").annual_TWh
            ty = state_anchor(fac, measured, tot, epoch_path, year=hy, phases=phases, energy=energy)
            by_year.append(ty[["epri_twh", "permit_twh", "epoch_twh"]].assign(year=hy).reset_index(names="state"))
        state_years = pd.concat(by_year, ignore_index=True).rename(
            columns={"permit_twh": "unscaled_estimates_twh", "epoch_twh": "measured_twh"})
        permit_rows = ~measured
        fac.loc[permit_rows, "state_scale"] = fac.loc[permit_rows, "state"].map(t.factor).fillna(1.0)
        fac["state_coverage_flag"] = fac.state.map(t.flag).fillna("no_epri_anchor")
        fac["mw_full"] = fac.mw_full_raw * fac.state_scale

    q = panel.load_quantities()
    capacity = (q[q.year >= 2020].groupby(["utility_id_eia", "state"]).total_retail_mwh.max() / 1000.0)
    mapping = succ.resolve(succ.load())
    fac = fac.join(pick_utilities(fac, capacity, mapping), on="fid")
    fac = fac.drop(columns="candidates")
    if len(ov) and "utility_status" in ov:
        o = ov.reindex(fac.fid)
        st = o.utility_status.values
        ver = st == "verified"
        fac.loc[ver, "utility_id_eia"] = o.utility_id_eia.values[ver]
        fac.loc[ver, "utility_assign"] = "verified_by_hand"
        off = pd.Series(st).isin(["ercot_wires_outside_panel", "behind_the_meter", "wholesale_direct"]).values
        fac.loc[off, "utility_id_eia"] = np.nan
        fac.loc[off, "utility_assign"] = st[off]
        fac["verified_fields"] = fac.verified_fields.fillna("") + np.where(ver | off, "utility;", "")
    # A hand-verified id may be one that has since been folded into a successor.
    fac["utility_id_eia"] = [succ.final_id(u, st, mapping) for u, st in zip(fac.utility_id_eia, fac.state)]
    assignment_report = {}
    if step_d:                                                   # assign, reopen, candidates (after the records)
        f2, assignment_report = cx.apply_assignment(fac.set_index("fid"), corr)
        fac = f2.reset_index()

    fac["in_dose"] = fac.energized_year.notna() & fac.mw_full.notna() & fac.utility_id_eia.notna()
    fac["verify_by_hand"] = fac.mw_full.fillna(0) >= 50

    # ---- facility-year load -------------------------------------------
    rows = []
    for f in fac[fac.in_dose].itertuples():
        for y in YEARS:
            mw = site_mw(f.src, f.fid, f.energized_year, f.mw_full, y, epoch_path, phases, energy, gaps)
            if mw > 0:
                rows.append((f.fid, int(f.utility_id_eia), f.state, y, mw, bool(f.is_crypto)))
    fy = pd.DataFrame(rows, columns=["fid", "utility_id_eia", "state", "year", "mw", "crypto"])

    # ---- utility x state x year dose ----------------------------------
    base = (q[q.year.isin(BASE_YEARS)].groupby(["utility_id_eia", "state"]).total_retail_mwh.mean() / 1000.0
            ).rename("base_retail_gwh")
    k = ["utility_id_eia", "state", "year"]
    dose = fy[~fy.crypto].groupby(k).agg(dc_mw=("mw", "sum"), n_facilities=("fid", "nunique")).reset_index()
    crypto = fy[fy.crypto].groupby(k).mw.sum().rename("crypto_mw").reset_index()
    dose = dose.merge(crypto, on=k, how="outer").fillna({"dc_mw": 0.0, "crypto_mw": 0.0, "n_facilities": 0})
    dose["dc_gwh"] = dose.dc_mw * 8.76
    dose = dose.join(base, on=["utility_id_eia", "state"])
    dose["dose"] = dose.dc_gwh / dose.base_retail_gwh                      # data centers only (primary)
    dose["dose_with_crypto"] = (dose.dc_mw + dose.crypto_mw) * 8.76 / dose.base_retail_gwh

    INTERIM.mkdir(parents=True, exist_ok=True)
    out = fac.drop(columns="geometry")
    out.to_parquet(INTERIM / "facilities.parquet", index=False)
    fy.to_parquet(INTERIM / "facility_year.parquet", index=False)
    dose.to_parquet(INTERIM / "utility_year_dose.parquet", index=False)
    # For the treatment-history bounds (pipeline/facilities/treatment_bounds.py; D-44): every state's anchoring row,
    # each state's total for EPRI's four historical years, and the Epoch rows carried on an assumed line.
    if scale_table is not None:
        scale_table.reset_index(names="state").to_parquet(INTERIM / "state_anchor.parquet", index=False)
        state_years.to_parquet(INTERIM / "state_load_by_year.parquet", index=False)
    pd.DataFrame([(f, a, b, c) for f, (a, b, c) in gaps.items()],
                 columns=["fid", "sourced_start", "first_entry_year", "first_entry_mw"]).to_parquet(INTERIM / "epoch_gaps.parquet", index=False)

    # ---- coverage gate against EPRI state totals (not a calibration) ---
    report = {
        "params": {"kappa": KAPPA, "permit_lag": PERMIT_LAG, "ramp_years": RAMP_YEARS},
        "facilities": {
            "total": int(len(fac)),
            "by_source": fac.src.value_counts().to_dict(),
            "in_dose": int(fac.in_dose.sum()),
            "undated": int(fac.energized_year.isna().sum()),
            "verified_not_yet_operating": int((fac.date_basis == "verified_not_yet_operating").sum()),
            "no_load_estimate": int(fac.mw_full.isna().sum()),
            "no_utility": int(fac.utility_id_eia.isna().sum()),
            "utility_assign": fac.utility_assign.value_counts().to_dict(),
            "state_coverage_flags_by_facility": fac.state_coverage_flag.value_counts().to_dict(),
            "left_censored": int(fac.left_censored.fillna(False).astype(bool).sum()),
            "load_history_of_sites_in_dose": fac[fac.in_dose].load_history.value_counts().to_dict(),
            "crypto_sites": int(fac.is_crypto.sum()),
            "crypto_mw_in_2025": round(float(fy[(fy.year == 2025) & fy.crypto].mw.sum()), 1),
            "verify_by_hand_50mw_plus": int(fac.verify_by_hand.sum()),
            "epoch_us_sites": int(len(ep_us)),
            "epoch_geocoded": int(len(ep_ok)),
            "epoch_superseding_permit_rows": len(superseded),
            "epoch_rows_on_an_assumed_line_before_their_first_entry": {
                f: {"sourced_start": a, "first_entry_year": b, "first_entry_mw": c} for f, (a, b, c) in sorted(gaps.items())},
        },
    }
    epri_path = RAW / "epri" / "epri_state_dashboard.json"
    if epri_path.exists():
        e = pd.DataFrame(json.loads(epri_path.read_text())["rows"])
        e = e[(e.scenario == "hist") & (e.year == 2024) & (e.state != "US")][["state", "annual_TWh"]]
        inv = (fy[fy.year == 2024].groupby("state").mw.sum() * 8.76 / 1000.0).rename("inventory_twh")
        c = e.set_index("state").join(inv).fillna({"inventory_twh": 0.0})
        both = c[(c.annual_TWh > 0.25)]
        report["epri_2024"] = {
            "national_inventory_twh": round(float(c.inventory_twh.sum()), 1),
            "national_epri_twh": round(float(c.annual_TWh.sum()), 1),
            "national_ratio": round(float(c.inventory_twh.sum() / c.annual_TWh.sum()), 3),
            "log_corr_states_ge_0.25twh": round(float(np.corrcoef(
                np.log(both.annual_TWh), np.log(both.inventory_twh.clip(lower=0.01)))[0, 1]), 3),
            "worst_covered_states": (c.assign(ratio=c.inventory_twh / c.annual_TWh)
                                     .sort_values("annual_TWh", ascending=False).head(15)
                                     .round(2).reset_index().to_dict("records")),
        }
    if scale_table is not None:
        report["state_anchor"] = scale_table[scale_table.epri_twh >= 0.25].round(3).reset_index(names="state").to_dict("records")
    if step_d:
        units = pd.MultiIndex.from_frame(q[["utility_id_eia", "state"]].drop_duplicates())
        f_idx = fac.set_index("fid")
        reach = cx.unknown_load_reach(f_idx, fy[~fy.crypto], scale_table if scale_table is not None else pd.DataFrame(),
                                      units, corr, measured.set_axis(fac.fid))
        fp = cx.fingerprint([args.corrections, cx.LOCATIONS, cx.GOV_YEARS, cx.WITHDRAWN, *cx.code_files()], step="build_inventory")
        (FROZEN / "unknown_load_sites_and_affected_utilities.json").write_text(
            json.dumps({**reach, "fingerprint": fp}, indent=2, default=str) + "\n")
        yb = cx.year_built_table(f_idx, year_built_ids, corr, PERMIT_LAG)
        yb.to_csv(FROZEN / "year_built_rows.csv", index=False)
        report["step_d"] = {
            "corrections_file": args.corrections, "fingerprint": fp,
            "locations_corrected": {f: cx.LOCATION_CONVENTION for f in moved_points},
            "locations_unresolved": cx.LOCATION_UNRESOLVED,
            "candidates_after_relocation": {f: f_idx.utility_candidates.get(f) for f in moved_points},
            "utility_after_relocation": {f: (None if pd.isna(f_idx.utility_id_eia.get(f)) else int(f_idx.utility_id_eia.get(f)))
                                         for f in moved_points},
            "timing": timing_report, "assignment": assignment_report,
            "first_fuel_years_set_aside": cx.first_fuel_report(f_idx, permit_lag=PERMIT_LAG),
            "year_built_rows": {"total": int(len(yb)), **yb["class"].value_counts().to_dict(),
                                "with_no_size": int((~yb.has_size).sum()),
                                "record_review": cx.YEAR_BUILT_REVIEW},
            "load_unknown_sites": reach["sites"], "utilities_affected_by_unknown_load": reach["every_affected_utility"],
            "date_basis": fac.date_basis.value_counts().to_dict()}
    (FROZEN / "inventory_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str))

    last = dose[dose.year == 2025]
    for theta in (0.02, 0.05, 0.10):
        ever = dose[dose.dose >= theta].groupby(["utility_id_eia", "state"]).year.min()
        print(f"theta {theta:.0%}: utilities ever crossing {len(ever)}; "
              f"first crossing 2011-2019: {int(ever.between(2011, 2019).sum())}; "
              f"2020+: {int((ever >= 2020).sum())}; before 2011: {int((ever < 2011).sum())}")
    print("utility-states with any data-center load in 2025:", len(last))
    return 0


if __name__ == "__main__":
    sys.exit(main())
