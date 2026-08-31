#!/usr/bin/env python3
"""Build a unified Medicaid-relevant POI set for cell landmark labeling.

Combines several sources into one normalized GeoJSON:
  - NCES public schools (local, from NPE cache) — strong community anchors
  - OSM hospitals + clinics + community health (per state via Overpass) —
    proxies for FQHCs / safety-net hospitals (a real HRSA/CMS pull would be
    better but Overpass is reliable and free)
  - OSM amenity=library, amenity=community_centre — caseworker-meeting venues
  - TIGER POINTLM (local cache at /tmp/tiger_pointlm_2024) — parks, gov't
    buildings, universities, religious institutions as last-resort anchors

Each POI is tagged with a rank 1-10 (lower is more preferred for cell labels).
Phase 3B's bake script picks the lowest-rank POI inside each cell.

Schema written to gizmos/medicaid-work-requirements/pipeline/raw/medicaid_pois.geojson:
    name            — display name
    category        — human-readable (FQHC/Hospital/School/Library/...)
    rank            — integer 1-10 (lower = preferred)
    source          — nces / osm_hospital / osm_clinic / osm_library / ...
    geometry        — Point (lon, lat)

Run:
    python3 tools/fetch-medicaid-pois.py
    python3 tools/fetch-medicaid-pois.py --skip-osm   # only NCES + TIGER
    python3 tools/fetch-medicaid-pois.py --states IL NY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

REPO = Path(__file__).resolve().parent.parent
_npe_dir = os.environ.get("NPE_DIR")
if not _npe_dir:
    sys.exit("NPE_DIR not set — point it at the off-repo geometry cache (pipeline outputs with grid/places layers).")
NCES_SCHOOLS = Path(_npe_dir) / "pipeline/output/nces_ccd_schools_2223.csv"
NCES_GEOCODE = Path(_npe_dir) / "pipeline/output/nces_edge_geocode_2223.csv"
TIGER_CACHE = Path("/tmp/tiger_pointlm_2024")
OUT_PATH = REPO / "gizmos/medicaid-work-requirements/pipeline/raw/medicaid_pois.geojson"
OSM_CACHE_DIR = REPO / "gizmos/medicaid-work-requirements/pipeline/raw/medicaid_pois"
OSM_CACHE_DIR.mkdir(parents=True, exist_ok=True)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

HEADERS = {
    "User-Agent": (
        "gizmo-warehouse/medicaid-work-requirements/1.0 "
        "(17A internal; contact joe@group17a.com)"
    ),
}

EXPANSION_STATES = [
    "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "HI", "IL", "IN",
    "IA", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SD", "UT", "VT", "VA", "WA", "WV",
]

# TIGER MTFCC → (category, rank) for codes we'll keep
TIGER_MTFCC = {
    "K1231": ("Hospital", 3),
    "K2543": ("School", 5),
    "K2540": ("University", 9),
    "K2195": ("Library", 6),
    "K2165": ("Government Building", 10),
    "K2190": ("Park", 8),
}


def load_nces_schools() -> gpd.GeoDataFrame:
    """NCES public schools with geocodes. Filter to open regular schools."""
    if not NCES_SCHOOLS.exists() or not NCES_GEOCODE.exists():
        print("  WARN: NCES cache missing — skipping schools", file=sys.stderr)
        return gpd.GeoDataFrame(columns=["name", "category", "rank", "source",
                                         "geometry"],
                                geometry="geometry", crs="EPSG:4326")

    print(f"  Reading {NCES_SCHOOLS.name}...", end="", flush=True)
    t0 = time.time()
    schools = pd.read_csv(NCES_SCHOOLS,
                          usecols=["NCESSCH", "SCH_NAME", "SY_STATUS",
                                   "SCH_TYPE_TEXT", "LEVEL"],
                          dtype={"NCESSCH": str},
                          low_memory=False)
    print(f" {len(schools):,} rows ({time.time() - t0:.1f}s)")

    print(f"  Reading {NCES_GEOCODE.name}...", end="", flush=True)
    t0 = time.time()
    geo = pd.read_csv(NCES_GEOCODE,
                      usecols=["NCESSCH", "LAT", "LON", "STATE"],
                      dtype={"NCESSCH": str},
                      low_memory=False)
    print(f" {len(geo):,} rows ({time.time() - t0:.1f}s)")

    # Filter: open + regular school + has geocode
    df = schools.merge(geo, on="NCESSCH", how="inner")
    df = df[df["SY_STATUS"] == 1]  # SY_STATUS=1 means Open
    df = df[df["SCH_TYPE_TEXT"] == "Regular School"]  # exclude vocational/special/etc.
    df = df.dropna(subset=["LAT", "LON"])

    # Rank by school level: high schools > middle > elementary (high schools
    # signal teen Medicaid eligibility and family clusters)
    level_rank = {"High": 5, "Middle": 5, "Elementary": 5, "Other": 5}
    df["rank"] = df["LEVEL"].map(level_rank).fillna(5).astype(int)

    out = gpd.GeoDataFrame({
        "name": df["SCH_NAME"].astype(str).str.strip(),
        "category": "Public School",
        "rank": df["rank"],
        "source": "nces",
        "geometry": [Point(lon, lat) for lon, lat in zip(df["LON"], df["LAT"])],
    }, geometry="geometry", crs="EPSG:4326")
    out = out[out["name"].notna() & (out["name"] != "")]
    print(f"  NCES schools (open regular K-12): {len(out):,}")
    return out


def load_tiger() -> gpd.GeoDataFrame:
    """TIGER POINTLM landmarks already cached. Filter to high-signal types."""
    if not TIGER_CACHE.exists():
        print("  WARN: TIGER cache missing — skipping TIGER", file=sys.stderr)
        return gpd.GeoDataFrame(columns=["name", "category", "rank", "source",
                                         "geometry"],
                                geometry="geometry", crs="EPSG:4326")

    parts = []
    for state_dir in sorted(TIGER_CACHE.iterdir()):
        if not state_dir.is_dir():
            continue
        shp = next(state_dir.glob("*pointlm.shp"), None)
        if not shp:
            continue
        try:
            g = gpd.read_file(shp)
        except Exception as e:
            print(f"    WARN: {shp.name}: {e}", file=sys.stderr)
            continue
        g = g[g["MTFCC"].isin(TIGER_MTFCC.keys())]
        g = g[g["FULLNAME"].notna() & (g["FULLNAME"].str.len() > 0)]
        if len(g) == 0:
            continue
        g["category"] = g["MTFCC"].map(lambda c: TIGER_MTFCC[c][0])
        g["rank"] = g["MTFCC"].map(lambda c: TIGER_MTFCC[c][1])
        g = g.rename(columns={"FULLNAME": "name"})
        g["source"] = "tiger_" + g["MTFCC"].str.lower()
        parts.append(g[["name", "category", "rank", "source", "geometry"]])

    if not parts:
        return gpd.GeoDataFrame(columns=["name", "category", "rank", "source",
                                         "geometry"],
                                geometry="geometry", crs="EPSG:4326")
    out = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True),
                           geometry="geometry", crs="EPSG:4326")
    print(f"  TIGER POINTLM (filtered): {len(out):,}")
    return out


def overpass_query(query: str, max_attempts: int = 4) -> dict:
    last_err = None
    for attempt in range(max_attempts):
        endpoint = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        try:
            r = requests.post(endpoint, data={"data": query},
                              headers=HEADERS, timeout=360)
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"      429 throttle; sleep {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            wait = 5 * (attempt + 1)
            print(f"      attempt {attempt+1}/{max_attempts} failed ({type(e).__name__}: {e}); waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {max_attempts}: {last_err}")


def fetch_osm_state(state_abbr: str, refetch: bool) -> list[dict]:
    """Fetch hospitals + clinics + libraries + community centers for one state."""
    cache = OSM_CACHE_DIR / f"{state_abbr}.geojson"
    if cache.exists() and not refetch:
        try:
            data = json.loads(cache.read_text())
            return data.get("features", [])
        except Exception:
            pass

    iso = f"US-{state_abbr}"
    query = f"""
[out:json][timeout:300];
area["ISO3166-2"="{iso}"]->.s;
(
  node["amenity"="hospital"]["name"](area.s);
  way["amenity"="hospital"]["name"](area.s);
  node["amenity"="clinic"]["name"](area.s);
  way["amenity"="clinic"]["name"](area.s);
  node["healthcare"~"^(hospital|clinic|community_health)$"]["name"](area.s);
  way["healthcare"~"^(hospital|clinic|community_health)$"]["name"](area.s);
  node["amenity"="library"]["name"](area.s);
  way["amenity"="library"]["name"](area.s);
  node["amenity"="community_centre"]["name"](area.s);
  way["amenity"="community_centre"]["name"](area.s);
);
out center;
""".strip()

    print(f"  [{state_abbr}] querying Overpass POIs...", flush=True)
    try:
        data = overpass_query(query)
    except Exception as e:
        print(f"    FAIL: {e}")
        return []

    features = []
    for el in data.get("elements", []):
        tags = el.get("tags", {}) or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        # Center for ways, lat/lon for nodes
        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center", {})
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue

        # Categorize
        amenity = tags.get("amenity")
        healthcare = tags.get("healthcare")
        if healthcare == "community_health" or tags.get("operator:type") == "fqhc":
            cat, rank, src = "Community Health Center", 1, "osm_community_health"
        elif amenity == "clinic" or healthcare == "clinic":
            cat, rank, src = "Clinic", 2, "osm_clinic"
        elif amenity == "hospital" or healthcare == "hospital":
            cat, rank, src = "Hospital", 3, "osm_hospital"
        elif amenity == "library":
            cat, rank, src = "Library", 6, "osm_library"
        elif amenity == "community_centre":
            cat, rank, src = "Community Center", 7, "osm_community_centre"
        else:
            continue

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"name": name, "category": cat, "rank": rank, "source": src},
        })

    cache.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    print(f"    {state_abbr}: {len(features):,} POIs")
    return features


def load_osm(states: list[str], refetch: bool) -> gpd.GeoDataFrame:
    rows = []
    for s in states:
        rows.extend(fetch_osm_state(s, refetch))
    if not rows:
        return gpd.GeoDataFrame(columns=["name", "category", "rank", "source",
                                         "geometry"],
                                geometry="geometry", crs="EPSG:4326")
    df = pd.DataFrame([f["properties"] | {"_lon": f["geometry"]["coordinates"][0],
                                          "_lat": f["geometry"]["coordinates"][1]}
                       for f in rows])
    out = gpd.GeoDataFrame(
        df.drop(columns=["_lon", "_lat"]),
        geometry=[Point(lon, lat) for lon, lat in zip(df["_lon"], df["_lat"])],
        crs="EPSG:4326",
    )
    print(f"  OSM POIs total: {len(out):,}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-osm", action="store_true",
                    help="Skip Overpass fetch — use only NCES + TIGER cache")
    ap.add_argument("--refetch", action="store_true",
                    help="Re-query Overpass even if state cache exists")
    ap.add_argument("--states", nargs="*", default=None,
                    help="Subset of state abbrs (default: all expansion states)")
    args = ap.parse_args()

    states = [s.upper() for s in args.states] if args.states else EXPANSION_STATES

    print("Loading NCES schools...")
    schools = load_nces_schools()

    print("\nLoading TIGER POINTLM...")
    tiger = load_tiger()

    osm = None
    if not args.skip_osm:
        print(f"\nFetching OSM POIs across {len(states)} state(s)...")
        osm = load_osm(states, args.refetch)

    parts = [schools, tiger]
    if osm is not None and len(osm) > 0:
        parts.append(osm)
    all_pois = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    print(f"\nTotal POIs: {len(all_pois):,}")
    print("\nBy category:")
    print(all_pois["category"].value_counts())
    print("\nBy source:")
    print(all_pois["source"].value_counts())

    print(f"\nWriting {OUT_PATH}...")
    all_pois.to_file(OUT_PATH, driver="GeoJSON")
    print(f"  {OUT_PATH.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
