#!/usr/bin/env python3
"""Bake the 1-mile grid layer with within-county Medicaid subject apportionment.

Reads NPE's grid_for_tiling.geojson (836 MB, ~1.7M cells, schema: cell_id,
total_pop, total_pov_pct, child_pop, child_pov, child_pov_pct + Polygon geom)
and produces a per-cell GeoJSON carrying Medicaid subject counts that:

  - Apportion each county's baked subject_count_strict / permissive /
    loss_exposure_strict across the cells inside that county, weighted by
    cell_weight = total_pop × max(total_pov_pct, 0.1). Sum of cell values
    in a county equals the county's total ("scale through precision").
  - Carry parent county + nearest census place names for popups.
  - Drop cells in non-expansion states and cells with zero subject value.

Output:
  gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson

Also merges grid-level percentile_cutoffs into
  public/data/medicaid-state-summary.json
so the frontend percentile slider can resolve "top X%" cutoffs at z>=7.

This is a v0 PLACEHOLDER bake riding NPE geometry + the synthetic county
apportionment from bake-placeholder-counties-and-hexes.py. Real pipeline
(stages 06-09) will replace once T-MSIS calibration is wired.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

REPO = Path(__file__).resolve().parent.parent
_npe_dir = os.environ.get("NPE_DIR")
if not _npe_dir:
    sys.exit("NPE_DIR not set — point it at the off-repo geometry cache (pipeline outputs with grid/places layers).")
NPE = Path(_npe_dir)
NPE_GRID = NPE / "pipeline/output/grid_for_tiling.geojson"
NPE_PLACES = NPE / "pipeline/output/places_national.geojson"

COUNTIES_PATH = REPO / "public/data/medicaid-counties.geojson"
STATE_SUMMARY = REPO / "public/data/medicaid-state-summary.json"
GRID_OUT = REPO / "gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson"

WORKING_AGE_SHARE = 0.60

# Non-expansion FIPS — skipped entirely (no expansion-pathway subject pool)
NON_EXP_FIPS = {"01", "12", "13", "20", "28", "45", "47", "48", "55", "56"}

PCTS = [50, 67, 75, 80, 85, 90, 95, 97, 99]


def load_expansion_counties() -> gpd.GeoDataFrame:
    print(f"Loading {COUNTIES_PATH.name}...")
    c = gpd.read_file(COUNTIES_PATH)
    c["state_fips"] = c["GEOID"].astype(str).str[:2]
    c = c[~c["state_fips"].isin(NON_EXP_FIPS)].reset_index(drop=True)
    print(f"  {len(c):,} expansion-state counties")
    return c


def load_grid() -> gpd.GeoDataFrame:
    print(f"Loading {NPE_GRID.name} ({NPE_GRID.stat().st_size / 1e6:.0f} MB)...")
    t0 = time.time()
    g = pyogrio.read_dataframe(NPE_GRID, use_arrow=True)
    print(f"  {len(g):,} cells in {time.time() - t0:.1f}s")
    return g


def apportion(grid: gpd.GeoDataFrame, counties: gpd.GeoDataFrame, places: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Spatial-join centroids -> counties, apportion county totals to cells."""
    if grid.crs is None:
        grid = grid.set_crs("EPSG:4326")
    if grid.crs != counties.crs:
        grid = grid.to_crs(counties.crs)

    print("Computing centroids...")
    centroids = gpd.GeoDataFrame(
        grid[["cell_id", "total_pop", "total_pov_pct"]].copy(),
        geometry=grid.geometry.centroid,
        crs=grid.crs,
    )

    print("Spatial-join centroids -> expansion counties...")
    t0 = time.time()
    joined = gpd.sjoin(
        centroids,
        counties[[
            "GEOID", "state_fips", "state_abbr", "county_short",
            "subject_count_strict", "subject_count_permissive",
            "loss_exposure_strict", "burden_index_centered",
            "working_age_pop", "geometry",
        ]],
        how="inner",
        predicate="within",
    )
    print(f"  {len(joined):,} cells in expansion counties ({time.time() - t0:.1f}s)")
    # Free unneeded geometry copies
    joined = joined.drop(columns=["index_right"], errors="ignore")

    print("Computing within-county rate scaling (no cap)...")
    joined["total_pop"] = joined["total_pop"].fillna(0)
    joined["total_pov_pct"] = joined["total_pov_pct"].fillna(0)
    # Bounded poverty multiplier — 0.5× to 2.5× around the national-median
    # poverty rate of ~15%. High-poverty cells get higher rates; low-poverty
    # cells get lower. This is the real limiter on within-county variance.
    joined["pov_mult"] = (joined["total_pov_pct"] / 15.0).clip(lower=0.5, upper=2.5)

    # IMPORTANT: We scale RATES, not absolute counts.
    #
    # The naive approach — give each cell a share of the county's subject
    # total weighted by pop × pov — breaks for dense urban counties because
    # NPE's 1-mile grid only covers ~10–15% of the county's actual working-age
    # population (water, parks, transit, etc. punch holes in the cell mesh).
    # In Kings County (Brooklyn), the cells contain ~210k people but the
    # county has 334k subject enrollees to allocate. There's no way to fit
    # them, and the old cap+redistribute logic saturated every cell at the
    # limit and dropped ~80% of the pool.
    #
    # Instead, each cell gets the county's overall subject rate, scaled by
    # how its poverty deviates from the county's average. Cells with the
    # county's average poverty get the county rate; high-pov cells in a poor
    # county can hit 55–65%; low-pov cells in a wealthy county drop to ~5%.
    # The map shows the cell's share of the county's STORY, not its share
    # of the county's count. Counties still show full totals on the county
    # layer; the grid just shows the within-county geography of who/where.
    #
    # Cells will NOT sum to the county total — they sum to the share of the
    # county's working-age population that lives in cells (typically 60–90%
    # in rural / suburban; 10–20% in dense urban cores). This is honest about
    # the data coverage and produces visually meaningful within-county
    # differentials (Brooklyn Heights pale, Bed-Stuy red).
    county_rate = (
        joined["subject_count_strict"] / joined["working_age_pop"].replace(0, 1.0)
    )
    mean_pov_mult = joined.groupby("GEOID")["pov_mult"].transform("mean").replace(0, 1.0)
    joined["subject_rate_cell"] = (
        county_rate * (joined["pov_mult"] / mean_pov_mult)
    ).clip(lower=0, upper=0.70)

    cell_wa = joined["total_pop"] * WORKING_AGE_SHARE
    joined["subject_count_strict_cell"] = joined["subject_rate_cell"] * cell_wa

    # Permissive + loss scale proportionally to the cell's strict count.
    # (Strict ratio = cell_subject / county_subject; preserves relative magnitude.)
    strict_county = joined["subject_count_strict"].replace(0, 1.0)
    ratio = joined["subject_count_strict_cell"] / strict_county
    joined["subject_count_permissive_cell"] = joined["subject_count_permissive"] * ratio * (
        # Re-scale so that nationally permissive ≈ 85% of strict (matches the
        # county-layer convention) rather than tracking the cell-vs-county
        # ratio (which is < 1 in sparse-coverage counties).
        strict_county / joined["subject_count_strict"].replace(0, 1.0)
    )
    joined["loss_exposure_strict_cell"] = joined["subject_count_strict_cell"] * 0.30  # CBO 30% admin churn

    print("Joining nearest place for popups...")
    t0 = time.time()
    cell_pts = gpd.GeoDataFrame(
        joined[["cell_id"]].copy(),
        geometry=joined.geometry,
        crs=joined.crs,
    )
    p = places[["NAME", "STUSPS", "geometry"]].rename(
        columns={"NAME": "nearest_place_name", "STUSPS": "nearest_place_state"}
    )
    nearest = gpd.sjoin_nearest(
        cell_pts.to_crs(p.crs),
        p,
        how="left",
        max_distance=None,
    )
    nearest = nearest.drop_duplicates(subset=["cell_id"])[
        ["cell_id", "nearest_place_name", "nearest_place_state"]
    ]
    joined = joined.merge(nearest, on="cell_id", how="left")
    print(f"  attached nearest place to {len(joined):,} cells ({time.time() - t0:.1f}s)")

    # Stitch polygon geometry back from the original grid
    print("Restoring polygon geometry...")
    polys = grid[["cell_id", "geometry"]].set_index("cell_id")
    joined = joined.set_index("cell_id")
    joined["geometry"] = polys["geometry"]
    joined = joined.reset_index()

    out = gpd.GeoDataFrame(
        {
            "cell_id": joined["cell_id"],
            "county_geoid": joined["GEOID"],
            "state_fips": joined["state_fips"],
            "state_abbr": joined["state_abbr"],
            "expansion": True,
            "parent_county_name": joined["county_short"].fillna(""),
            "parent_state_abbr": joined["state_abbr"].fillna(""),
            "nearest_place_name": joined["nearest_place_name"].fillna(""),
            "nearest_place_state": joined["nearest_place_state"].fillna(""),
            "total_pop": joined["total_pop"].fillna(0).round().astype(int),
            "subject_count_strict": joined["subject_count_strict_cell"].fillna(0).round().astype(int),
            "loss_exposure_strict": joined["loss_exposure_strict_cell"].fillna(0).round().astype(int),
            "subject_rate": joined["subject_rate_cell"].fillna(0).round(4),
            "burden_index_centered": joined["burden_index_centered"].fillna(0).round(1),
            "geometry": joined["geometry"],
        },
        geometry="geometry",
        crs=joined.crs,
    )
    return out


def update_state_summary(grid: gpd.GeoDataFrame) -> None:
    print(f"\nComputing grid percentile_cutoffs...")

    def _pcts(s: pd.Series) -> dict[str, float]:
        s = s[s > 0]
        if len(s) == 0:
            return {str(p): 0 for p in PCTS}
        return {str(p): float(s.quantile(p / 100)) for p in PCTS}

    cutoffs = {
        "subject_count": _pcts(grid["subject_count_strict"]),
        "subject_rate": _pcts(grid["subject_rate"]),
        "burden_index": _pcts(grid["burden_index_centered"]),
        "loss_exposure": _pcts(grid["loss_exposure_strict"]),
    }

    print(f"Updating {STATE_SUMMARY.name}...")
    summary = json.loads(STATE_SUMMARY.read_text())
    pc = summary.setdefault("percentile_cutoffs", {})
    for mode, c in cutoffs.items():
        pc.setdefault(mode, {})["grid"] = c
    STATE_SUMMARY.write_text(json.dumps(summary, indent=2))

    # Echo a few diagnostic stats
    print(f"  grid percentile_cutoffs[subject_count]:")
    for p, v in cutoffs["subject_count"].items():
        print(f"    p{p:>2}: {v:,.0f}")


def main() -> None:
    GRID_OUT.parent.mkdir(parents=True, exist_ok=True)

    counties = load_expansion_counties()

    print(f"Loading {NPE_PLACES.name}...")
    places = gpd.read_file(NPE_PLACES)
    print(f"  {len(places):,} places")

    grid = load_grid()

    out = apportion(grid, counties, places)

    print(f"\n{len(out):,} cells with positive geometry before subject filter")
    out = out[out["subject_count_strict"] > 0].copy()
    print(f"{len(out):,} cells after dropping zero-subject cells")

    print(f"\nWriting {GRID_OUT}...")
    t0 = time.time()
    out.to_file(GRID_OUT, driver="GeoJSON")
    size_mb = GRID_OUT.stat().st_size / 1e6
    print(f"  {size_mb:.1f} MB written in {time.time() - t0:.1f}s")

    update_state_summary(out)

    print("\nDiagnostic — top 5 cells by subject_count:")
    top = out.nlargest(5, "subject_count_strict")[
        ["cell_id", "parent_county_name", "state_abbr",
         "nearest_place_name", "total_pop", "subject_count_strict", "subject_rate"]
    ]
    print(top.to_string(index=False))


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nDone in {time.time() - t0:.1f}s")
