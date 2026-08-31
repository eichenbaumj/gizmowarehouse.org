"""Stage 08b — bring the 1-mile grid in line with the county model.

Stage 08 resamples tract metrics to the grid but (a) carries the OLD per-capita
`loss_exposure_strict` (a flat per-subject rate) and (b) has no `subject_rate`
denominator at all. Stages 07b/07c already unified the COUNTY layer on the
bottom-up loss model and a real ACS 19-64 `subject_rate`; this stage does the
same for the grid so the map is internally consistent at every zoom.

It operates on the 56 MB `grid_1mi_metrics.parquet` (NOT the 3.78 GB GeoJSON —
re-reading that would OOM), then regenerates `grid_1mi.geojson` by rebuilding
each cell's square from its stored centroid (geometry is a pure function of the
centroid, so no spatial join is needed). tippecanoe (stage 10) reads the GeoJSON.

What it sets per cell:
  - working_age_pop, total_pop : the tract's ACS 19-64 / total population threaded
    down to the cell (even split, same divisor stage 08 used for the counts).
  - subject_rate              : subject_count_strict / working_age_pop (the tract
    rate; the cells_in_tract divisor cancels). Matches the county legend.
  - loss_exposure_strict      : OVERWRITTEN with the bottom-up model — each state's
    total_loss_2034 (07b's loss-breakdown.json) apportioned across its cells by
    subject share, EXACTLY mirroring 07c's county apportionment.
  - expansion                 : real JSON bool from config.STATE_INFO (the map's
    gray non-expansion fill + popup read it; absent on the grid until now).
  - parent_county_name/_abbr  : popup sublabel ("1-mi cell · Wayne County, MI").

AK + HI are not in the grid (CONUS-only, like stage 08), so their bottom-up loss
(~1.20% of the 5.42M national) is absent here — grid/hex national loss reads
~5.36M while the county/headline national reads 5.42M. This matches the existing
grid subject-count behavior; see METHODOLOGY.

Idempotent: derives working_age/total/rate/loss from source each run (drops any
columns from a prior run first), so 08b -> 09 -> 09b -> 10 can be re-run without
touching 07/07b/07c.

Run after stage 08:  python 08b_patch_grid_metrics.py
"""
from __future__ import annotations

import json
import math
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent / "lib"))
import config  # type: ignore
from acs_pop import tract_population  # type: ignore

GRID_METRICS = config.OUTPUT_DIR / "grid_1mi_metrics.parquet"
GRID_GEOJSON = config.OUTPUT_DIR / "grid_1mi.geojson"
LOSS_BREAKDOWN = config.PUBLIC_DATA_DIR / "medicaid-loss-breakdown.json"
PUBLIC_COUNTIES = config.PUBLIC_DATA_DIR / "medicaid-counties.geojson"

CELL_SIZE_MI = 1.0  # matches stage 08

# Columns 08b derives — dropped before recompute so re-runs don't collide/double.
DERIVED_COLS = [
    "working_age_pop", "total_pop", "subject_rate", "expansion",
    "parent_county_name", "parent_state_abbr",
]

# Fields carried into the regenerated GeoJSON.
#   - tippecanoe (stage 10) keeps only its -y set (the metric fields + promoteId
#     cell_id).
#   - stage 12 (PDF briefs) reads this same GeoJSON and needs state_fips +
#     county_fips to find a county's cells for the "top cells" table, so they ride
#     along here (tiny, low-cardinality, dropped from the tile by -y exclusion).
# We deliberately do NOT carry a per-cell county-NAME string: at 2.2M cells it
# roughly doubled the PMTiles size (3,100 distinct names), and the grid popup
# degrades gracefully to "1-mi cell · — County" without it (its current live
# behavior). Real place labels are the deferred Tier-A bake, not this field.
GEOJSON_FIELDS = [
    "cell_id",
    "subject_count_strict", "subject_rate", "burden_index_centered",
    "loss_exposure_strict", "total_pop", "expansion",
    "state_fips", "county_fips",
]
# Round the tiled values to sensible precision. The grid GeoJSON is consumed
# ONLY by tippecanoe; full-precision 15-digit floats are high-entropy and roughly
# double the PMTiles size for no visible benefit. The parquet keeps full precision
# (stages 09/09b read it), so this rounding never touches the hex/cutoff math.
GEOJSON_ROUND = {
    "subject_count_strict": 2,
    "subject_rate": 4,
    "burden_index_centered": 1,
    "loss_exposure_strict": 2,
    "total_pop": 0,
}


def _check_inputs() -> bool:
    for p in (GRID_METRICS, LOSS_BREAKDOWN):
        if not p.exists():
            print(f"ERROR: {p} missing.", file=sys.stderr)
            return False
    return True


def _county_short_map() -> dict[str, str]:
    """GEOID(5) -> short county name (no 'County'/'Parish' suffix) for popups."""
    if not PUBLIC_COUNTIES.exists():
        return {}
    gj = json.loads(PUBLIC_COUNTIES.read_text())
    out = {}
    for f in gj.get("features", []):
        p = f.get("properties", {})
        gid = str(p.get("GEOID", "")).zfill(5)
        short = p.get("county_short") or p.get("county_name") or ""
        if gid:
            out[gid] = short
    return out


def main() -> None:
    if not _check_inputs():
        sys.exit(1)

    grid = pd.read_parquet(GRID_METRICS)
    n0 = len(grid)
    print(f"Loaded grid_1mi_metrics.parquet: {n0:,} cells")

    # Normalize join keys.
    grid["parent_tract_id"] = grid["parent_tract_id"].astype(str).str.zfill(11)
    grid["state_fips"] = grid["state_fips"].astype(str).str.zfill(2)
    grid["county_fips"] = grid["county_fips"].astype(str).str.zfill(3)
    grid["cells_in_tract"] = grid["cells_in_tract"].fillna(1).clip(lower=1).astype(int)

    # Drop any columns from a prior 08b run so the recompute is clean/idempotent.
    grid = grid.drop(columns=[c for c in DERIVED_COLS if c in grid.columns])

    # --- Working-age + total population, threaded from the tract (even split) ---
    # Rename the tract-pop GEOID to the grid's tract key so the merge is on one
    # column and the grid's own GEOID (also the tract id) is left untouched.
    tp = tract_population().rename(
        columns={"GEOID": "parent_tract_id", "working_age_pop": "_tract_wa", "total_pop": "_tract_total"}
    )
    grid = grid.merge(tp, on="parent_tract_id", how="left")

    miss = int(grid["_tract_wa"].isna().sum())
    if miss:
        print(f"  WARN: {miss:,} cells whose parent tract is absent from ACS B01001 -> pop 0")
    grid["_tract_wa"] = grid["_tract_wa"].fillna(0.0)
    grid["_tract_total"] = grid["_tract_total"].fillna(0.0)

    grid["working_age_pop"] = grid["_tract_wa"] / grid["cells_in_tract"]
    grid["total_pop"] = grid["_tract_total"] / grid["cells_in_tract"]

    # --- subject_rate = subject / working-age (cells_in_tract cancels => tract rate)
    wa = grid["working_age_pop"].to_numpy()
    subj = grid["subject_count_strict"].fillna(0.0).to_numpy()
    grid["subject_rate"] = np.where(wa > 0, subj / np.where(wa > 0, wa, 1.0), 0.0)

    # --- expansion (real bool) + popup labels ---------------------------------
    grid["expansion"] = grid["state_fips"].map(
        lambda f: bool(config.STATE_INFO.get(f, {}).get("expansion", False))
    )
    grid["parent_state_abbr"] = grid["state_fips"].map(
        lambda f: config.STATE_INFO.get(f, {}).get("abbr", "")
    )
    cmap = _county_short_map()
    grid["parent_county_name"] = (grid["state_fips"] + grid["county_fips"]).map(
        lambda g: cmap.get(g, "")
    )

    # --- Projected loss = bottom-up model apportioned to cells (07c pattern) ---
    lb = json.loads(LOSS_BREAKDOWN.read_text())
    state_loss = {f: float(v.get("total_loss_2034", 0.0)) for f, v in lb.get("states", {}).items()}
    national_loss = float(lb["_national"]["total_loss_2034"])
    state_subj = grid.groupby("state_fips")["subject_count_strict"].sum().to_dict()

    sf = grid["state_fips"].to_numpy()
    ss = np.array([state_subj.get(s, 0.0) for s in sf])
    sl = np.array([state_loss.get(s, 0.0) for s in sf])
    grid["loss_exposure_strict"] = np.where((ss > 0) & (sl > 0), subj / np.where(ss > 0, ss, 1.0) * sl, 0.0)

    # --- Persist the patched parquet ------------------------------------------
    assert len(grid) == n0, "row count changed during patch"
    grid.drop(columns=["_tract_wa", "_tract_total"]).to_parquet(GRID_METRICS, index=False)
    print(f"-> patched {GRID_METRICS.name}")

    _verify(grid, state_loss, national_loss)

    # --- Regenerate grid_1mi.geojson from centroids (no sjoin) -----------------
    _write_geojson(grid)


def _verify(grid: pd.DataFrame, state_loss: dict, national_loss: float) -> None:
    sr = grid["subject_rate"]
    print("\n--- verification ------------------------------------------------")
    print(f"subject_rate: min={sr.min():.3f} max={sr.max():.3f} mean={sr.mean():.3f} "
          f"nunique={sr.nunique():,}  (>1.0: {int((sr > 1.0).sum()):,})")
    print(f"working_age_pop > 0 cells: {int((grid['working_age_pop'] > 0).sum()):,} / {len(grid):,}")

    grid_loss = grid["loss_exposure_strict"].sum()
    conus_target = sum(v for f, v in state_loss.items() if f not in ("02", "15"))
    print(f"national grid loss = {grid_loss:,.0f}  (CONUS bottom-up target "
          f"{conus_target:,.0f}; national-with-AK/HI {national_loss:,.0f})")

    # Per-state reconciliation (CONUS expansion states should match exactly).
    by_state = grid.groupby("state_fips")["loss_exposure_strict"].sum()
    worst = 0.0
    for f, got in by_state.items():
        tgt = state_loss.get(f, 0.0)
        if tgt > 0:
            worst = max(worst, abs(got - tgt) / tgt)
    print(f"per-state loss vs bottom-up: max abs rel diff = {worst:.5f} (≈0 expected)")

    # LA county (06037) sanity: grid cell rate ~ county rate (~0.30).
    la = grid[(grid["state_fips"] == "06") & (grid["county_fips"] == "037")]
    if len(la):
        print(f"LA County 06037: {len(la):,} cells, mean subject_rate={la['subject_rate'].mean():.3f} "
              f"(county model ~0.30), loss sum={la['loss_exposure_strict'].sum():,.0f}")
    print("-----------------------------------------------------------------\n")


def _write_geojson(grid: pd.DataFrame) -> None:
    print(f"Regenerating {GRID_GEOJSON.name} from centroids ({len(grid):,} cells)...")
    t0 = time.time()
    lat_step = CELL_SIZE_MI / 69.0
    clat = grid["centroid_lat"].to_numpy()
    clon = grid["centroid_lon"].to_numpy()
    lon_step = CELL_SIZE_MI / (69.0 * np.cos(np.radians(clat)))
    lat0 = clat - lat_step / 2.0
    lon0 = clon - lon_step / 2.0
    geom = shapely.box(lon0, lat0, lon0 + lon_step, lat0 + lat_step)

    cols = [c for c in GEOJSON_FIELDS if c in grid.columns]
    out = grid[cols].copy()
    for c, nd in GEOJSON_ROUND.items():
        if c in out.columns:
            out[c] = out[c].round(nd)
            if nd == 0:
                out[c] = out[c].astype("int64")
    gdf = gpd.GeoDataFrame(out, geometry=geom, crs=config.WEB_CRS)
    if GRID_GEOJSON.exists():
        GRID_GEOJSON.unlink()
    gdf.to_file(GRID_GEOJSON, driver="GeoJSON")
    print(f"-> {GRID_GEOJSON.name}: {GRID_GEOJSON.stat().st_size / 1e9:.2f} GB "
          f"in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"Stage 08b done in {time.time() - t0:.0f}s")
