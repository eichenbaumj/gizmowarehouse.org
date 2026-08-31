#!/usr/bin/env python3
"""Fetch OpenStreetMap neighborhood + suburb polygons for each US state via
the Overpass API. Stores per-state GeoJSONs in
gizmos/medicaid-work-requirements/pipeline/raw/osm_neighborhoods/{state_abbr}.geojson.

We query for two complementary feature types:
  - relation[boundary=neighbourhood]            — neighborhood polygons (best)
  - relation[boundary=administrative][admin_level=10|11]  — Chicago/NYC-style sub-city districts
  - way[boundary=neighbourhood]                 — single-polygon neighborhoods
  - way[place=neighbourhood|suburb]             — closed-way neighborhoods

We deliberately SKIP nodes (place=neighbourhood as a node) because we need
polygons for the within-cell containment check; a node is a single point that
can't contain a 1-mile cell. Tier C (Census Place) handles cells outside any
OSM neighborhood polygon.

Output schema (per state):
    place_name    — OSM 'name' tag
    place_parent  — OSM 'is_in:city' tag if present, else null (resolved later)
    place_state   — state postal abbr
    place_source  — "osm_neighborhood" or "osm_admin10"
    geometry      — Polygon / MultiPolygon

We page through a state in one shot when possible, and skip empty states.
Overpass occasionally throttles; we retry with backoff. Already-fetched
states are skipped unless --refetch is passed.

Run:
    python3 tools/fetch-osm-neighborhoods.py
    python3 tools/fetch-osm-neighborhoods.py --only IL --refetch
    python3 tools/fetch-osm-neighborhoods.py --states IL NY CA WA OR DC

Approx wall time: ~1 hour for all 51 states sequentially (most are <30s, but
NY / IL / CA take 2-5 min each due to data volume).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import requests
from shapely.geometry import LineString, MultiPolygon, Polygon, shape
from shapely.ops import polygonize, unary_union

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "gizmos/medicaid-work-requirements/pipeline/raw/osm_neighborhoods"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Overpass mirrors — we'll cycle through them on failure
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

# 50 states + DC, expansion-state subset only (saves ~half the runtime; the
# grid has no cells in non-expansion states so labels there don't matter).
EXPANSION_STATES = [
    "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "HI", "IL", "IN",
    "IA", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SD", "UT", "VT", "VA", "WA", "WV",
]


def build_query(state_abbr: str) -> str:
    """Overpass QL for one state's neighborhood-equivalent polygons.

    Uses ISO3166-2 to scope. Multiple feature patterns are union-ed so we
    catch all the ways US cities tag their sub-city boundaries (Chicago
    uses admin_level=10 for community areas; NYC uses boundary=neighbourhood
    for some neighborhoods and admin_level=10 for others; smaller cities
    tend to use boundary=neighbourhood relations or place=suburb closed ways).
    """
    iso = f"US-{state_abbr}"
    return f"""
[out:json][timeout:300];
area["ISO3166-2"="{iso}"]->.s;
(
  relation["boundary"="neighbourhood"]["name"](area.s);
  relation["boundary"="administrative"]["admin_level"~"^(10|11)$"]["name"](area.s);
  way["boundary"="neighbourhood"]["name"](area.s);
  way["place"~"^(neighbourhood|suburb)$"]["name"](area.s);
);
out geom;
""".strip()


def osm_to_geojson(osm_json: dict, state_abbr: str) -> list[dict]:
    """Convert Overpass JSON to a list of GeoJSON Feature dicts.

    Handles three element types:
      - way with explicit 'geometry' (list of {lat,lon}) — closed polygon
      - relation with members[].geometry — multipolygon assembly
      - node — skipped (no polygon)
    """
    features = []
    for el in osm_json.get("elements", []):
        tags = el.get("tags", {}) or {}
        name = tags.get("name")
        if not name:
            continue

        # Categorize source
        if tags.get("boundary") == "administrative":
            source = "osm_admin10"
        else:
            source = "osm_neighborhood"

        # Build geometry
        shapely_geom = None
        if el["type"] == "way":
            coords = [(p["lon"], p["lat"]) for p in el.get("geometry") or []]
            if len(coords) >= 4 and coords[0] == coords[-1]:
                shapely_geom = Polygon(coords)
        elif el["type"] == "relation":
            # OSM multipolygon relations: outer members may be open ways that
            # need to be stitched together by shared endpoints to form a ring.
            # Use shapely.ops.polygonize on the union of all outer line
            # segments — it handles ring assembly cleanly. Inner ("inner"
            # role) ways become holes. We don't bother with hole semantics at
            # this resolution; over-coverage is fine for cell containment.
            outer_lines = []
            for m in el.get("members", []):
                if m.get("type") != "way" or m.get("role") != "outer":
                    continue
                coords = [(p["lon"], p["lat"]) for p in m.get("geometry") or []]
                if len(coords) >= 2:
                    outer_lines.append(LineString(coords))
            if outer_lines:
                merged = unary_union(outer_lines)
                polygons = list(polygonize(merged))
                if len(polygons) == 1:
                    shapely_geom = polygons[0]
                elif len(polygons) > 1:
                    shapely_geom = MultiPolygon(polygons)
        else:
            continue

        if shapely_geom is None or shapely_geom.is_empty:
            continue
        geom = shapely_geom.__geo_interface__

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "place_name": name.strip(),
                "place_parent": (tags.get("is_in:city") or "").strip() or None,
                "place_state": state_abbr,
                "place_source": source,
                "_admin_level": tags.get("admin_level"),
            },
        })
    return features


def overpass_query(query: str, max_attempts: int = 4) -> dict:
    """POST to Overpass with mirror cycling and exponential backoff."""
    last_err = None
    for attempt in range(max_attempts):
        endpoint = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        try:
            r = requests.post(
                endpoint,
                data={"data": query},
                headers=HEADERS,
                timeout=360,
            )
            if r.status_code == 429:
                # Throttled — wait extra
                wait = 30 * (attempt + 1)
                print(f"      429 throttle from {endpoint}; sleeping {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            wait = 5 * (attempt + 1)
            print(f"      attempt {attempt+1}/{max_attempts} failed "
                  f"({type(e).__name__}: {e}); waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {max_attempts} attempts: {last_err}")


def fetch_state(state_abbr: str, refetch: bool) -> dict:
    out_path = OUT_DIR / f"{state_abbr}.geojson"
    if out_path.exists() and not refetch:
        try:
            gdf = gpd.read_file(out_path)
            return {"state": state_abbr, "ok": True, "rows": len(gdf), "msg": "cached"}
        except Exception:
            pass  # fall through to refetch

    query = build_query(state_abbr)
    print(f"  [{state_abbr}] querying Overpass...", flush=True)
    t0 = time.time()
    try:
        data = overpass_query(query)
    except Exception as e:
        return {"state": state_abbr, "ok": False, "rows": 0, "msg": str(e)}

    features = osm_to_geojson(data, state_abbr)
    if not features:
        # Write an empty file so we don't re-query next time
        (out_path).write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        return {"state": state_abbr, "ok": True, "rows": 0, "msg": "no features"}

    fc = {"type": "FeatureCollection", "features": features}
    out_path.write_text(json.dumps(fc))
    dt = time.time() - t0
    return {"state": state_abbr, "ok": True, "rows": len(features),
            "msg": f"{dt:.0f}s"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--only", default=None, help="Single state abbr")
    ap.add_argument("--states", nargs="*", default=None,
                    help="Subset of state abbrs (default: all expansion states)")
    args = ap.parse_args()

    if args.only:
        states = [args.only.upper()]
    elif args.states:
        states = [s.upper() for s in args.states]
    else:
        states = EXPANSION_STATES

    print(f"Fetching OSM neighborhoods for {len(states)} state(s)...")
    results = []
    t_total = time.time()
    for s in states:
        results.append(fetch_state(s, args.refetch))

    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    total_rows = sum(r["rows"] for r in ok)
    print(f"\nFetched {len(ok)}/{len(results)} states, "
          f"{total_rows:,} neighborhood polygons total, "
          f"{time.time() - t_total:.0f}s elapsed")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  {r['state']:<3s} {r['msg'][:90]}")
    print("\nPer-state row counts:")
    for r in sorted(ok, key=lambda x: -x["rows"]):
        print(f"  {r['state']:<3s} {r['rows']:>5,}  ({r['msg']})")


if __name__ == "__main__":
    main()
