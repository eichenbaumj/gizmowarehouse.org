#!/usr/bin/env python3
"""Bake tiered place labels onto every 1-mi cell in grid_1mi.geojson.

The previous implementation used `gpd.sjoin_nearest` against Census Places
with no max-distance bound, which collapsed entire Chicago / NYC / LA cells
into "Near Chicago" / "Near New York" — coarse enough that a state-level
Medicaid scanner couldn't recognize what part of the city they were looking
at.

This bake replaces that with a four-tier lookup, each tier using *within*
semantics (centroid contained inside the source polygon, no nearest fallback):

    Tier A (curated) — NYC NTAs (special-cased from public/data/) plus any
        Tier A layer downloaded by tools/fetch-neighborhood-layers.py
    Tier B (OSM) — per-state polygons baked by tools/fetch-osm-neighborhoods.py
    Tier C (Census Place) — Census-designated places, but ONLY when the cell
        centroid is contained (no `sjoin_nearest` magic that grabs a town
        from 5 miles away)
    Tier D (county-only) — fallback when nothing contains the centroid

The cell's pre-existing `nearest_place_name` / `nearest_place_state` columns
are KEPT for back-compat (the frontend still falls back to them if it can't
find the new fields), but the canonical fields going forward are:

    place_name    — the most specific name found (neighborhood preferred)
    place_parent  — the city / borough this neighborhood belongs to (blank
                    when place_name is itself the city, i.e. Tier C)
    place_state   — 2-letter postal abbr
    place_source  — slug indicating which tier won (debugging + analytics)

Run:
    python3 tools/bake-medicaid-place-labels.py
    python3 tools/bake-medicaid-place-labels.py --skip-osm   # if OSM fetch isn't done yet
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

REPO = Path(__file__).resolve().parent.parent
GRID_PATH = REPO / "gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson"
NYC_NTA_URL = "https://data.gizmowarehouse.org/nyc-property-tax/nta-aggregates.geojson"
NYC_NTA_PATH = REPO / "tools/.cache/nyc-nta-aggregates.geojson"  # downloaded on demand (R2 canonical)
TIER_A_DIR = REPO / "gizmos/medicaid-work-requirements/pipeline/raw/neighborhood_layers"
OSM_DIR = REPO / "gizmos/medicaid-work-requirements/pipeline/raw/osm_neighborhoods"
_npe_dir = os.environ.get("NPE_DIR")
if not _npe_dir:
    sys.exit("NPE_DIR not set — point it at the off-repo geometry cache (pipeline outputs with grid/places layers).")
PLACES_PATH = Path(_npe_dir) / "pipeline/output/places_national.geojson"


def load_nyc_ntas() -> gpd.GeoDataFrame:
    """NYC NTAs — fetched from R2 into tools/.cache/. Schema: ntaname + boroname."""
    if not NYC_NTA_PATH.exists():
        import urllib.request
        NYC_NTA_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"  downloading NYC NTAs from {NYC_NTA_URL} ...")
        try:
            urllib.request.urlretrieve(NYC_NTA_URL, NYC_NTA_PATH)
        except Exception as e:  # noqa: BLE001
            print(f"  WARN: NTA download failed ({e}) — NYC will fall back to OSM/Census",
                  file=sys.stderr)
    if not NYC_NTA_PATH.exists():
        print(f"  WARN: {NYC_NTA_PATH} missing — NYC will fall back to OSM/Census",
              file=sys.stderr)
        return gpd.GeoDataFrame(columns=["place_name", "place_parent", "place_state",
                                         "place_source", "geometry"],
                                geometry="geometry", crs="EPSG:4326")
    g = gpd.read_file(NYC_NTA_PATH)
    if g.crs and g.crs.to_string() != "EPSG:4326":
        g = g.to_crs("EPSG:4326")
    out = gpd.GeoDataFrame({
        "place_name": g["ntaname"].astype(str).str.strip(),
        "place_parent": g["boroname"].astype(str).str.strip(),
        "place_state": "NY",
        "place_source": "nyc_nta",
        "geometry": g.geometry,
    }, geometry="geometry", crs="EPSG:4326")
    return out[out["place_name"].notna() & (out["place_name"] != "")]


def load_curated_tier_a() -> gpd.GeoDataFrame:
    """Pick up any per-city Tier A layers fetched by fetch-neighborhood-layers.py.

    Each per-city file already has the normalized 4-column schema, so we just
    concatenate.
    """
    parts = []
    for path in sorted(TIER_A_DIR.glob("*.geojson")):
        if path.name == "manifest.json":
            continue
        try:
            g = gpd.read_file(path)
        except Exception as e:
            print(f"  WARN: failed to read {path.name}: {e}", file=sys.stderr)
            continue
        if g.crs and g.crs.to_string() != "EPSG:4326":
            g = g.to_crs("EPSG:4326")
        # Normalize column presence
        for c in ("place_name", "place_parent", "place_state", "place_source"):
            if c not in g.columns:
                g[c] = "" if c != "place_source" else path.stem
        parts.append(g[["place_name", "place_parent", "place_state",
                        "place_source", "geometry"]])
        print(f"    {path.stem}: {len(g):,} features")
    if not parts:
        return gpd.GeoDataFrame(columns=["place_name", "place_parent", "place_state",
                                         "place_source", "geometry"],
                                geometry="geometry", crs="EPSG:4326")
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True),
                            geometry="geometry", crs="EPSG:4326")


def load_osm() -> gpd.GeoDataFrame:
    """Concatenate per-state OSM neighborhood GeoJSONs into one layer."""
    parts = []
    for path in sorted(OSM_DIR.glob("*.geojson")):
        try:
            g = gpd.read_file(path)
        except Exception as e:
            print(f"  WARN: failed to read {path.name}: {e}", file=sys.stderr)
            continue
        if len(g) == 0:
            continue
        if g.crs and g.crs.to_string() != "EPSG:4326":
            g = g.to_crs("EPSG:4326")
        # Drop columns we don't carry forward
        keep = [c for c in ("place_name", "place_parent", "place_state",
                            "place_source", "geometry") if c in g.columns]
        parts.append(g[keep])
    if not parts:
        return gpd.GeoDataFrame(columns=["place_name", "place_parent", "place_state",
                                         "place_source", "geometry"],
                                geometry="geometry", crs="EPSG:4326")
    osm = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True),
                           geometry="geometry", crs="EPSG:4326")
    # Filter to only valid geometries that are actually polygons
    osm = osm[osm.geometry.notna() & ~osm.geometry.is_empty]
    osm = osm[osm.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    return osm


def load_census_places() -> gpd.GeoDataFrame:
    """Census Places from NPE cache. Used as Tier C."""
    if not PLACES_PATH.exists():
        print(f"  ERROR: {PLACES_PATH} missing — Tier C cannot be populated.",
              file=sys.stderr)
        sys.exit(1)
    g = gpd.read_file(PLACES_PATH)
    if g.crs and g.crs.to_string() != "EPSG:4326":
        g = g.to_crs("EPSG:4326")
    # Schema: NAME, STUSPS (state abbr)
    out = gpd.GeoDataFrame({
        "place_name": g["NAME"].astype(str).str.strip(),
        "place_parent": "",   # The place IS the city; no narrower parent
        "place_state": g["STUSPS"].astype(str).str.strip(),
        "place_source": "census_place",
        "geometry": g.geometry,
    }, geometry="geometry", crs="EPSG:4326")
    return out[out["place_name"].notna() & (out["place_name"] != "")]


def tier_join(centroids: gpd.GeoDataFrame, layer: gpd.GeoDataFrame,
              already_labeled: set, tier_label: str) -> tuple[pd.DataFrame, int]:
    """Spatial-join only the unlabeled centroids against this tier's polygons.

    Returns the rows that newly matched, and the count.
    """
    if len(layer) == 0:
        return pd.DataFrame(), 0
    todo = centroids[~centroids["cell_id"].isin(already_labeled)]
    if len(todo) == 0:
        return pd.DataFrame(), 0
    print(f"  Tier {tier_label}: {len(layer):,} polygons × {len(todo):,} unlabeled cells...",
          end="", flush=True)
    t0 = time.time()
    joined = gpd.sjoin(
        todo, layer[["place_name", "place_parent", "place_state",
                     "place_source", "geometry"]],
        how="inner",
        predicate="within",
    )
    # If a centroid falls in multiple polygons (e.g. nested admin levels),
    # keep the first — input layers should be roughly disjoint within a tier.
    joined = joined.drop_duplicates(subset=["cell_id"], keep="first")
    print(f" matched {len(joined):,} ({time.time() - t0:.1f}s)")
    return joined[["cell_id", "place_name", "place_parent", "place_state",
                   "place_source"]], len(joined)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-osm", action="store_true",
                    help="Skip Tier B (OSM) — useful when OSM fetch is incomplete")
    args = ap.parse_args()

    if not GRID_PATH.exists():
        print(f"ERROR: {GRID_PATH} missing", file=sys.stderr)
        sys.exit(1)

    print(f"Loading grid_1mi.geojson ({GRID_PATH.stat().st_size/1e6:.0f} MB)...")
    t0 = time.time()
    grid = gpd.read_file(GRID_PATH)
    # Idempotency
    grid = grid.drop(columns=[c for c in ("place_name", "place_parent",
                                          "place_state", "place_source")
                              if c in grid.columns])
    print(f"  {len(grid):,} cells in {time.time() - t0:.1f}s")

    # Build a centroid GeoDataFrame for the spatial joins (using centroid
    # rather than full polygon means tier membership is unambiguous: a cell
    # belongs to exactly one neighborhood at each tier).
    centroids = gpd.GeoDataFrame(
        grid[["cell_id"]].copy(),
        geometry=grid.geometry.centroid,
        crs=grid.crs,
    )

    # ----- Tier A: curated neighborhood layers --------------------------------
    print("\nLoading Tier A: curated neighborhood layers...")
    nyc = load_nyc_ntas()
    print(f"  NYC NTAs: {len(nyc):,} features")
    curated = load_curated_tier_a()
    tier_a = gpd.GeoDataFrame(pd.concat([nyc, curated], ignore_index=True),
                              geometry="geometry", crs="EPSG:4326")
    tier_a = tier_a[tier_a.geometry.notna() & ~tier_a.geometry.is_empty]
    print(f"  Tier A total: {len(tier_a):,} polygons")

    labeled_frames = []
    labeled_ids: set = set()

    matched_a, _ = tier_join(centroids, tier_a, labeled_ids, "A (curated)")
    if len(matched_a):
        labeled_frames.append(matched_a)
        labeled_ids.update(matched_a["cell_id"])

    # ----- Tier B: OSM neighborhood polygons ----------------------------------
    if not args.skip_osm:
        print("\nLoading Tier B: OSM per-state neighborhood polygons...")
        osm = load_osm()
        print(f"  OSM total: {len(osm):,} polygons")
        matched_b, _ = tier_join(centroids, osm, labeled_ids, "B (OSM)")
        if len(matched_b):
            labeled_frames.append(matched_b)
            labeled_ids.update(matched_b["cell_id"])

    # ----- Tier C: Census Place (within only, not nearest) --------------------
    print("\nLoading Tier C: Census Places...")
    places = load_census_places()
    print(f"  Census Places: {len(places):,} features")
    matched_c, _ = tier_join(centroids, places, labeled_ids, "C (Census Place)")
    if len(matched_c):
        labeled_frames.append(matched_c)
        labeled_ids.update(matched_c["cell_id"])

    # ----- Tier D: county fallback --------------------------------------------
    unlabeled = centroids[~centroids["cell_id"].isin(labeled_ids)]
    print(f"\nTier D: {len(unlabeled):,} cells without any place match — "
          f"falling back to county")
    if len(unlabeled) > 0:
        tier_d = grid[grid["cell_id"].isin(unlabeled["cell_id"])][
            ["cell_id", "parent_county_name", "parent_state_abbr"]
        ].copy()
        tier_d_rows = pd.DataFrame({
            "cell_id": tier_d["cell_id"],
            "place_name": "Rural " + tier_d["parent_county_name"].fillna("Unincorporated") + " County",
            "place_parent": "",
            "place_state": tier_d["parent_state_abbr"].fillna(""),
            "place_source": "county_only",
        })
        labeled_frames.append(tier_d_rows)

    # ----- Combine and merge back into grid -----------------------------------
    all_labels = pd.concat(labeled_frames, ignore_index=True)
    # Sanity: every cell should be labeled exactly once now
    if all_labels["cell_id"].duplicated().any():
        n_dup = int(all_labels["cell_id"].duplicated().sum())
        print(f"  WARN: {n_dup} duplicate cell_ids across tiers — keeping first")
        all_labels = all_labels.drop_duplicates(subset=["cell_id"], keep="first")

    grid = grid.merge(all_labels, on="cell_id", how="left")
    for c in ("place_name", "place_parent", "place_state", "place_source"):
        grid[c] = grid[c].fillna("")

    # ----- Supplement Tier A/B with parent city from Census Place -------------
    # OSM neighborhood/admin polygons rarely carry an is_in:city tag, so
    # place_parent comes back empty even when we know the neighborhood is
    # inside a named Census Place (Rogers Park → Chicago, Hyde Park → Chicago).
    # For cells whose neighborhood is set but place_parent is empty, look up
    # the containing Census Place and copy its name into place_parent. The
    # final label reads "Rogers Park · Chicago, IL" instead of "Rogers Park, IL".
    needs_parent_mask = (
        (grid["place_name"] != "")
        & (grid["place_parent"] == "")
        & grid["place_source"].isin(["osm_admin10", "osm_neighborhood",
                                     "dc_neighborhood_clusters"])
    )
    n_need = int(needs_parent_mask.sum())
    if n_need:
        print(f"\nSupplementing place_parent for {n_need:,} Tier A/B cells "
              f"via Census Place lookup...")
        t0 = time.time()
        need_centroids = gpd.GeoDataFrame(
            grid.loc[needs_parent_mask, ["cell_id"]].copy(),
            geometry=grid.loc[needs_parent_mask].geometry.centroid,
            crs=grid.crs,
        )
        # Reuse places loaded earlier
        parent_join = gpd.sjoin(
            need_centroids,
            places[["place_name", "geometry"]].rename(
                columns={"place_name": "_parent_city"}
            ),
            how="left",
            predicate="within",
        ).drop_duplicates(subset=["cell_id"], keep="first")
        parent_map = dict(zip(parent_join["cell_id"], parent_join["_parent_city"].fillna("")))
        grid.loc[needs_parent_mask, "place_parent"] = grid.loc[needs_parent_mask, "cell_id"].map(parent_map).fillna("")
        n_filled = int((grid.loc[needs_parent_mask, "place_parent"] != "").sum())
        print(f"  filled {n_filled:,} place_parent fields ({time.time() - t0:.1f}s)")

    # Summary
    src_counts = grid["place_source"].value_counts()
    print(f"\nPlace-source breakdown:")
    for s, n in src_counts.items():
        pct = 100 * n / len(grid)
        print(f"  {s:<30s} {n:>10,}  ({pct:>5.1f}%)")

    # Weighted by subject_count
    if "subject_count_strict" in grid.columns:
        wsum = grid.groupby("place_source")["subject_count_strict"].sum()
        total = float(grid["subject_count_strict"].sum())
        print(f"\nPlace-source weighted by subject_count_strict ({total:,.0f}):")
        for s, n in wsum.sort_values(ascending=False).items():
            pct = 100 * n / total if total else 0
            print(f"  {s:<30s} {n:>12,.0f}  ({pct:>5.1f}%)")

    print(f"\nWriting back to {GRID_PATH}...")
    t0 = time.time()
    grid.to_file(GRID_PATH, driver="GeoJSON")
    print(f"  wrote {GRID_PATH.stat().st_size/1e6:.1f} MB in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
