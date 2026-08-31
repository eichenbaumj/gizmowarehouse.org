#!/usr/bin/env python3
"""Attach a Medicaid-relevant landmark inside each cell polygon (not nearest).

Phase 3 of the cell-label rebuild. Replaces the original TIGER-only nearest-
landmark logic with a rank-based within-cell join against the unified POI
set produced by tools/fetch-medicaid-pois.py.

POI rank (lower = higher preference; a state Medicaid director / caseworker
will recognize these as front-line service touchpoints):

    1. Community Health Center / FQHC      → "by"
    2. Clinic                              → "by"
    3. Hospital                            → "by"
    5. Public School (NCES K-12)           → "by"
    6. Library                             → "by"
    7. Community Center                    → "by"
    8. Park                                → "near"
    9. University / College                → "near"
   10. Government Building                 → "near"

Cells with no internal POI get an empty landmark_name. The popup falls back
to the place label alone in that case.

Reads:
    gizmos/medicaid-work-requirements/pipeline/raw/medicaid_pois.geojson
        (produced by fetch-medicaid-pois.py — NCES + OSM + TIGER POINTLM)

Writes back to:
    gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson
    with columns: landmark_name, landmark_type, landmark_category (rank 1-10)

Run:
    python3 tools/bake-medicaid-landmarks.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
GRID_PATH = REPO / "gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson"
POIS_PATH = REPO / "gizmos/medicaid-work-requirements/pipeline/raw/medicaid_pois.geojson"


def main() -> None:
    if not GRID_PATH.exists():
        print(f"ERROR: {GRID_PATH} missing", file=sys.stderr)
        sys.exit(1)
    if not POIS_PATH.exists():
        print(f"ERROR: {POIS_PATH} missing — run tools/fetch-medicaid-pois.py first",
              file=sys.stderr)
        sys.exit(1)

    print(f"Loading grid_1mi.geojson ({GRID_PATH.stat().st_size / 1e6:.0f} MB)...")
    t0 = time.time()
    grid = gpd.read_file(GRID_PATH)
    # Idempotency
    grid = grid.drop(columns=[c for c in ("landmark_name", "landmark_type",
                                          "landmark_category")
                              if c in grid.columns])
    print(f"  {len(grid):,} cells in {time.time() - t0:.1f}s")

    print(f"\nLoading {POIS_PATH.name} ({POIS_PATH.stat().st_size / 1e6:.0f} MB)...")
    t0 = time.time()
    pois = gpd.read_file(POIS_PATH)
    if pois.crs and pois.crs.to_string() != "EPSG:4326":
        pois = pois.to_crs("EPSG:4326")
    if grid.crs and grid.crs.to_string() != "EPSG:4326":
        grid_join = grid.to_crs("EPSG:4326")
    else:
        grid_join = grid
    print(f"  {len(pois):,} POIs in {time.time() - t0:.1f}s")
    print(f"  category distribution:")
    print(pois["category"].value_counts().to_string())

    print(f"\nJoining POIs contained within each cell polygon...")
    t0 = time.time()
    cell_polys = grid_join[["cell_id", "geometry"]].copy()
    joined = gpd.sjoin(
        cell_polys,
        pois[["name", "category", "rank", "source", "geometry"]],
        how="left",
        predicate="contains",
    )
    # Each cell may have multiple POIs inside; pick the lowest rank
    joined["rank"] = joined["rank"].fillna(99).astype(int)
    joined = (
        joined
        .sort_values(["cell_id", "rank"])
        .drop_duplicates(subset=["cell_id"], keep="first")
    )
    matched = int(joined["name"].notna().sum())
    print(f"  joined in {time.time() - t0:.1f}s; "
          f"{matched:,} cells matched a POI inside their polygon "
          f"({100 * matched / len(grid):.1f}%)")

    # Merge back
    grid = grid.merge(
        joined[["cell_id", "name", "category", "rank"]].rename(columns={
            "name": "landmark_name",
            "category": "landmark_type",
            "rank": "landmark_category",
        }),
        on="cell_id",
        how="left",
    )
    grid["landmark_name"] = grid["landmark_name"].fillna("")
    grid["landmark_type"] = grid["landmark_type"].fillna("")
    grid["landmark_category"] = grid["landmark_category"].fillna(99).astype(int)

    # Summary by category
    print(f"\nLandmark category distribution ({matched:,} matched cells):")
    print(grid[grid["landmark_name"] != ""]["landmark_type"].value_counts().to_string())

    print(f"\nWriting back to {GRID_PATH}...")
    t0 = time.time()
    grid.to_file(GRID_PATH, driver="GeoJSON")
    print(f"  wrote {GRID_PATH.stat().st_size / 1e6:.1f} MB in {time.time() - t0:.1f}s")

    # Sample diagnostic
    print("\nSample cells with landmarks (top categories):")
    for cat in ["Community Health Center", "Hospital", "Public School", "Library"]:
        sub = grid[grid["landmark_type"] == cat].head(3)
        if len(sub) == 0:
            continue
        print(f"\n  {cat}:")
        for _, r in sub.iterrows():
            print(f"    {r.get('parent_county_name', '')}, {r.get('parent_state_abbr', '')}: {r['landmark_name']}")


if __name__ == "__main__":
    main()
