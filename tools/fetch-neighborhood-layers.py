#!/usr/bin/env python3
"""Fetch Tier-A curated neighborhood-boundary layers per the manifest at
gizmos/medicaid-work-requirements/pipeline/raw/neighborhood_layers/manifest.json.

For each city in the manifest, downloads the source GeoJSON and writes a
normalized version to {slug}.geojson with a stable schema:

    place_name    — neighborhood name (from manifest's name_field)
    place_parent  — display label for the parent city (from manifest's `city`)
    place_state   — 2-letter state postal abbreviation (from manifest's `state`)
    place_source  — slug identifying which source layer this is from
    geometry      — Polygon / MultiPolygon

Robust to source failures: a city that 404s, 5xx's, or returns invalid GeoJSON
is logged and skipped, not fatal. The downstream bake script picks up whatever
slugs exist locally and lets OSM Tier B / Census Place Tier C handle the rest.

Already-fetched layers are skipped unless --refetch is passed. Use --only to
target a single slug (handy when iterating on schema quirks).

Run:
    python3 tools/fetch-neighborhood-layers.py
    python3 tools/fetch-neighborhood-layers.py --only chicago_community_areas --refetch
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests

REPO = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO / "gizmos/medicaid-work-requirements/pipeline/raw/neighborhood_layers/manifest.json"
OUT_DIR = MANIFEST_PATH.parent

HEADERS = {
    "User-Agent": (
        "gizmo-warehouse/medicaid-work-requirements "
        "(17A internal; contact joe@group17a.com)"
    ),
}


def fetch_one(slug: str, entry: dict, out_path: Path, refetch: bool) -> dict:
    """Download one source layer and normalize its schema. Returns a status dict."""
    status = {"slug": slug, "ok": False, "rows": 0, "msg": ""}
    if out_path.exists() and not refetch:
        try:
            gdf = gpd.read_file(out_path)
            status["ok"] = True
            status["rows"] = len(gdf)
            status["msg"] = "cached"
            return status
        except Exception as e:
            status["msg"] = f"cached but unreadable ({e}); refetching"

    url = entry["source_url"]
    print(f"  [{slug}] GET {url[:90]}...", end=" ", flush=True)
    try:
        r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
        r.raise_for_status()
    except Exception as e:
        status["msg"] = f"HTTP error: {e}"
        print(f"FAIL ({e})")
        return status

    # Save raw response first so we can re-parse without re-fetching
    raw_path = out_path.with_suffix(".raw.geojson")
    raw_path.write_bytes(r.content)

    try:
        gdf = gpd.read_file(raw_path)
    except Exception as e:
        status["msg"] = f"parse error: {e}"
        print(f"FAIL (parse: {e})")
        return status

    name_field = entry["name_field"]
    if name_field not in gdf.columns:
        # Try a few common alternates before giving up
        alternates = ["NAME", "Name", "name", "neighborhood", "Neighborhood",
                      "nhood", "NHOOD", "S_HOOD", "BDNAME", "community",
                      "CSA2010", "NBHD_NAME", "NBH_NAMES", "hood"]
        found = next((c for c in alternates if c in gdf.columns), None)
        if found:
            print(f"NOTE: name_field '{name_field}' missing; using '{found}'")
            name_field = found
        else:
            status["msg"] = (
                f"name_field '{name_field}' missing — available: {list(gdf.columns)[:8]}"
            )
            print(f"FAIL ({status['msg']})")
            return status

    # Reproject to EPSG:4326 for consistency
    if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    norm = gpd.GeoDataFrame({
        "place_name": gdf[name_field].astype(str).str.strip(),
        "place_parent": entry["city"],
        "place_state": entry["state"],
        "place_source": slug,
        "geometry": gdf.geometry,
    }, geometry="geometry", crs="EPSG:4326")
    # Drop empty/NaN names
    norm = norm[norm["place_name"].notna() & (norm["place_name"] != "")
                & (norm["place_name"].str.lower() != "nan")]

    norm.to_file(out_path, driver="GeoJSON")
    raw_path.unlink(missing_ok=True)
    status["ok"] = True
    status["rows"] = len(norm)
    status["msg"] = "ok"
    print(f"OK ({len(norm):,} features)")
    return status


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true",
                    help="Force re-download even if cached")
    ap.add_argument("--only", default=None,
                    help="Slug to fetch (skip the rest)")
    args = ap.parse_args()

    if not MANIFEST_PATH.exists():
        print(f"ERROR: {MANIFEST_PATH} missing", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(MANIFEST_PATH.read_text())["layers"]
    slugs = [args.only] if args.only else list(manifest.keys())
    if args.only and args.only not in manifest:
        print(f"ERROR: --only {args.only!r} not in manifest", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching {len(slugs)} neighborhood layer(s)...")
    results = []
    t0 = time.time()
    for slug in slugs:
        entry = manifest[slug]
        out_path = OUT_DIR / f"{slug}.geojson"
        results.append(fetch_one(slug, entry, out_path, args.refetch))

    # Summary
    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    total_features = sum(r["rows"] for r in ok)
    print(f"\nFetched {len(ok)}/{len(results)} layers, "
          f"{total_features:,} features total, "
          f"{time.time() - t0:.1f}s elapsed")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  {r['slug']:<30s} {r['msg']}")
    if ok:
        print("\nSuccessful layers:")
        for r in ok:
            print(f"  {r['slug']:<30s} {r['rows']:>6,} features  ({r['msg']})")


if __name__ == "__main__":
    main()
