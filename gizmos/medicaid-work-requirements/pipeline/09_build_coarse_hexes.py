"""Stage 09 — aggregate the 1-mile grid into 5-mile hexes for low-zoom rendering.

The 5-mile layer is a **complete, non-overlapping pointy-top hex tiling** sized to
match the deployed look (~3.8 mi across, the NPE hex size). We assign each 1-mile
cell to the hex that contains its centroid and aggregate: counts SUM, the
per-capita subject_rate is a ratio-of-sums (Σ subject ÷ Σ working-age), burden is
subject-weighted, and the popup labels carry the most-common value among the
hex's cells. Because the tiling has no gaps, every cell lands in exactly one hex,
so the 5-mile total equals the 1-mile total — one loss story at every zoom.

(We tile our own hex grid rather than reuse NPE's public/data/hex_5mi.geojson:
that mesh covers only ~63% of populated area, so a within-join onto it drops ~45%
of the subjects. A clean generated tiling is gap-free, non-overlapping, and
reconciles to the grid exactly.)

A 20-mile flat-top layer is still emitted for tippecanoe's coarse_hex.pmtiles
(stage 10) + R2 (stage 13), but the SPA does not load it — build-only artifact.

Reads:
  output/grid_1mi_metrics.parquet   (stage 08 + label merge — NOT the GeoJSON)

Output:
  output/hex_5mi.geojson
  output/hex_20mi.geojson

Run: python 09_build_coarse_hexes.py
"""

from __future__ import annotations

import math
import sys
import time
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import Polygon

import config

GRID_IN = config.OUTPUT_DIR / "grid_1mi_metrics.parquet"
HEX_5MI_OUT = config.OUTPUT_DIR / "hex_5mi.geojson"
HEX_20MI_OUT = config.OUTPUT_DIR / "hex_20mi.geojson"

# CONUS bbox (matches stage 08's NPE mesh).
CONUS_SOUTH, CONUS_NORTH = 24.4, 49.5
CONUS_WEST, CONUS_EAST = -125.0, -66.8

# Hex circumradius (center→vertex), miles. 2.2 ≈ NPE's 5-mi hex (3.8 mi across).
HEX5_RADIUS_MI = 2.2
HEX20_RADIUS_MI = 8.8  # build-only 20-mi layer (not read by the SPA)

# Counts: summed across the cells in a hex.
SUM_COLS = [
    "subject_count_strict", "subject_count_permissive",
    "loss_exposure_strict", "expansion_pool_estimate",
    "working_age_pop", "total_pop",
]
# Rates / indices: subject-weighted mean (fallback expansion-pool weight).
WEIGHTED_COLS = [
    "burden_index_centered", "verification_difficulty",
    "labor_volatility", "access_gap",
]
# Popup labels: most-common value among the hex's cells.
LABEL_COLS = ["parent_county_name", "nearest_place_name", "place_name"]


def pointy_top_hexagon(clon: float, clat: float, radius_mi: float) -> Polygon:
    """Pointy-top hexagon (vertex at the top) in lat/lon space."""
    r_lat = radius_mi / 69.0
    r_lon = radius_mi / (69.0 * math.cos(math.radians(clat)))
    pts = []
    for ang in (30, 90, 150, 210, 270, 330):
        rad = math.radians(ang)
        pts.append((clon + r_lon * math.cos(rad), clat + r_lat * math.sin(rad)))
    return Polygon(pts)


def generate_hex_mesh(radius_mi: float, prefix: str) -> gpd.GeoDataFrame:
    """Complete non-overlapping pointy-top hex tiling over CONUS (odd-r offset)."""
    row_step_lat = 1.5 * radius_mi / 69.0          # row-to-row spacing (vertical)
    rows, row, lat = [], 0, CONUS_SOUTH
    while lat < CONUS_NORTH:
        col_step_lon = math.sqrt(3) * radius_mi / (69.0 * math.cos(math.radians(lat)))
        lon = CONUS_WEST + (0.0 if row % 2 == 0 else col_step_lon / 2)
        while lon < CONUS_EAST:
            rows.append({"coarse_id": f"{prefix}_{row}_{len(rows)}",
                         "geometry": pointy_top_hexagon(lon, lat, radius_mi)})
            lon += col_step_lon
        lat += row_step_lat
        row += 1
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=config.WEB_CRS)


def _most_common(joined: pd.DataFrame, col: str) -> pd.Series:
    """Vectorized per-hex mode of a string label column (ignores blanks)."""
    sub = joined[joined[col].astype(str) != ""]
    if len(sub) == 0:
        return pd.Series(dtype=object)
    counts = sub.groupby(["coarse_id", col]).size().rename("n").reset_index()
    counts = counts.sort_values("n").drop_duplicates("coarse_id", keep="last")
    return counts.set_index("coarse_id")[col]


def _bin_cells(grid_pts: gpd.GeoDataFrame, hexes: gpd.GeoDataFrame) -> pd.DataFrame:
    """Assign every cell to exactly one hex. `within` for the bulk; the few cells
    that land in the sub-0.1mi slivers between hex rows (an artifact of the
    per-latitude lon scaling) are caught by nearest-hex, so coverage is complete
    and Σ hex == Σ grid exactly."""
    cols = ["coarse_id", "geometry"]
    inside = gpd.sjoin(grid_pts, hexes[cols], how="inner", predicate="within").drop_duplicates("cell_id")
    missed = grid_pts[~grid_pts["cell_id"].isin(inside["cell_id"])]
    if len(missed):
        near = gpd.sjoin_nearest(missed, hexes[cols], how="inner").drop_duplicates("cell_id")
        inside = pd.concat([inside, near], ignore_index=True)
    return inside


def aggregate_to_hexes(grid_pts: gpd.GeoDataFrame, hexes: gpd.GeoDataFrame, label: str):
    joined = _bin_cells(grid_pts, hexes)
    n_out = len(grid_pts) - len(joined)
    g = joined.groupby("coarse_id")

    sums = g[[c for c in SUM_COLS if c in joined.columns]].sum()

    # Subject-weighted means (fallback to expansion-pool weight where Σsubject==0).
    w = joined["subject_count_strict"].fillna(0.0)
    if "expansion_pool_estimate" in joined.columns:
        w = w.where(w > 0, joined["expansion_pool_estimate"].fillna(0.0))
    tmp = pd.DataFrame({"coarse_id": joined["coarse_id"].to_numpy(), "_w": w.to_numpy()})
    wcols = [c for c in WEIGHTED_COLS if c in joined.columns]
    for c in wcols:
        tmp[f"_wx_{c}"] = joined[c].fillna(0.0).to_numpy() * w.to_numpy()
    wagg = tmp.groupby("coarse_id").sum()
    weighted = pd.DataFrame(index=wagg.index)
    for c in wcols:
        weighted[c] = np.where(wagg["_w"] > 0, wagg[f"_wx_{c}"] / wagg["_w"].replace(0, np.nan), 0.0)

    agg = sums.join(weighted, how="left")
    for c in [c for c in LABEL_COLS if c in joined.columns]:
        agg[c] = _most_common(joined, c)
    agg["n_cells"] = g.size()
    wa = agg.get("working_age_pop", pd.Series(0.0, index=agg.index)).to_numpy()
    subj = agg.get("subject_count_strict", pd.Series(0.0, index=agg.index)).to_numpy()
    agg["subject_rate"] = np.where(wa > 0, subj / np.where(wa > 0, wa, 1.0), 0.0)
    agg = agg.reset_index()
    print(f"  {label}: {len(agg):,} non-empty hexes, {len(joined):,} cells binned "
          f"({n_out:,} outside CONUS mesh)")
    return agg


# Columns kept in the served hex GeoJSON. The SPA reads the 4 mode fields + the
# popup body (total_pop, working_age_pop) + the labels; 09b reads the 4 modes.
# Everything else (permissive, the burden sub-components, expansion_pool, n_cells,
# nearest_place_name) is dropped to keep the browser download lean.
HEX_OUTPUT_COLS = [
    "coarse_id", "subject_count_strict", "subject_rate", "burden_index_centered",
    "loss_exposure_strict", "total_pop", "working_age_pop",
    "parent_county_name", "place_name",
]


def _restitch_and_write(agg: pd.DataFrame, hexes: gpd.GeoDataFrame, out_path) -> gpd.GeoDataFrame:
    hp = hexes.set_index("coarse_id").geometry
    geom = hp.reindex(agg["coarse_id"].to_numpy()).to_numpy()
    gdf = gpd.GeoDataFrame(agg, geometry=geom, crs=config.WEB_CRS)
    gdf = gdf[gdf.geometry.notna()].copy()
    for c in [c for c in LABEL_COLS if c in gdf.columns]:
        gdf[c] = gdf[c].fillna("")
    rnd = {"subject_count_strict": 2, "subject_rate": 4, "burden_index_centered": 1,
           "loss_exposure_strict": 2, "total_pop": 0, "working_age_pop": 0}
    for c, nd in rnd.items():
        if c in gdf.columns:
            gdf[c] = gdf[c].round(nd)
            if nd == 0:
                gdf[c] = gdf[c].astype("int64")
    keep = [c for c in HEX_OUTPUT_COLS if c in gdf.columns] + ["geometry"]
    gdf = gdf[keep]
    if out_path.exists():
        out_path.unlink()
    # COORDINATE_PRECISION=4 (~11 m, sub-pixel at the z4-9 the 5-mi hex renders)
    # — this GeoJSON is fetched whole by the browser, so coordinate entropy is size.
    pyogrio.write_dataframe(gdf, out_path, driver="GeoJSON", COORDINATE_PRECISION=4)
    print(f"  -> {out_path.name}: {len(gdf):,} hexes, {out_path.stat().st_size/1e6:.1f} MB")
    return gdf


def main() -> None:
    if not GRID_IN.exists():
        print(f"ERROR: {GRID_IN} missing. Run stage 08 + label bakes + merge first.", file=sys.stderr)
        sys.exit(1)
    warnings.filterwarnings("ignore", message=".*Geometry is in a geographic CRS.*")

    print(f"Loading {GRID_IN.name}...")
    grid = pd.read_parquet(GRID_IN)
    print(f"  {len(grid):,} cells")
    grid_pts = gpd.GeoDataFrame(
        grid, geometry=gpd.points_from_xy(grid["centroid_lon"], grid["centroid_lat"]), crs=config.WEB_CRS
    )

    print("\nBuilding 5-mile hexes (complete pointy-top tiling)...")
    hex5_mesh = generate_hex_mesh(HEX5_RADIUS_MI, "h5")
    print(f"  candidate hexes: {len(hex5_mesh):,}")
    agg5 = aggregate_to_hexes(grid_pts, hex5_mesh, "5mi")
    hex5 = _restitch_and_write(agg5, hex5_mesh, HEX_5MI_OUT)

    g_subj = float(grid["subject_count_strict"].sum())
    h_subj = float(agg5["subject_count_strict"].sum())
    rel = abs(h_subj - g_subj) / g_subj if g_subj else 0.0
    print(f"  reconcile subject: grid {g_subj:,.0f} vs 5-mi hex {h_subj:,.0f} (rel {rel:.5f})")
    for c in [c for c in LABEL_COLS if c in hex5.columns]:
        print(f"  label fill ({c}): {(hex5[c].astype(str) != '').mean():.1%}")

    print("\nBuilding 20-mile flat-top hexes (build-only artifact for stage 10/13)...")
    hex20_mesh = generate_hex_mesh(HEX20_RADIUS_MI, "h20")
    agg20 = aggregate_to_hexes(grid_pts, hex20_mesh, "20mi")
    _restitch_and_write(agg20, hex20_mesh, HEX_20MI_OUT)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 09 done in {time.time()-t0:.0f}s")
