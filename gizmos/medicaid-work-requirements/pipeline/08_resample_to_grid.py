"""Stage 08 — resample tract metrics onto the NPE 1-mile HEX grid, dasymetric by population.

We render the 1-mile layer on the National Poverty Explorer's 1-mile hexagon
mesh (`grid_for_tiling.geojson`, ~1.7M non-overlapping hex cells that share
vertices and tile cleanly to ~105 MB) rather than a synthetic square lattice.
For each cell we:

  1. Find the census tract containing the cell's centroid.
  2. Apportion that tract's COUNT values (subject counts, working-age + total
     population, expansion pool) to the cell by a **population-dasymetric**
     within-tract weight: each cell gets the tract count times its share of the
     tract's population, where the population surface is NPE's per-cell
     `total_pop`. Σ(share) == 1 within every tract, so cells reconcile to the
     tract control exactly (and to the county control, via stage 07c).
  3. Assign the tract's RATE values directly (subject_rate, burden index, and
     the burden components) — uniform within a tract; the dasymetric share
     cancels out of subject_rate = subject / working-age.
  4. Re-apportion projected coverage loss from the BOTTOM-UP per-state model
     (medicaid-loss-breakdown.json, the same total stage 07c uses for counties)
     across the state's cells by subject share — never the tract's old
     loss_exposure column.

Place + landmark labels are added afterward by tools/bake-medicaid-place-labels.py
and tools/bake-medicaid-landmarks.py (run between stage 08 and stage 09). This
stage emits the identity columns those bakes and the popup need:
parent_county_name / parent_state_abbr (Tier-D fallback + popup sublabel),
nearest_place_name / nearest_place_state (legacy popup fallback), and
county_geoid (lib/render_maps.py + lib/state_brief_context.py filter on it).

AK + HI render at the state level only (the NPE mesh is CONUS-only), so grid/hex
projected loss sums to the CONUS share (~5.36M) of the 5.42M national total. See
METHODOLOGY.md §4.5.

Output:
  output/grid_1mi.geojson         — 1-mile hex cells with all metrics + identity
  output/grid_1mi_metrics.parquet — tabular (no geometry) for stages 09/09b

Run:  python 08_resample_to_grid.py
Fast iteration:  MWR_SAMPLE_STATE=PA python 08_resample_to_grid.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import config  # type: ignore
from acs_pop import tract_population  # type: ignore

# --- NPE geometry source (off-repo cache; same NPE_DIR as the bake scripts) --
_npe_dir = os.environ.get("NPE_DIR")
if not _npe_dir:
    sys.exit("NPE_DIR not set — point it at the off-repo geometry cache (pipeline outputs with grid/places layers).")
NPE = Path(_npe_dir)
NPE_GRID = NPE / "pipeline/output/grid_for_tiling.geojson"
NPE_PLACES = NPE / "pipeline/output/places_national.geojson"

TRACT_GEOJSON_IN = config.RAW_DIR / "cb_2024_tracts_all.geojson"
TRACT_FULL_IN = config.OUTPUT_DIR / "tract_full.parquet"
LOSS_BREAKDOWN = config.PUBLIC_DATA_DIR / "medicaid-loss-breakdown.json"
PUBLIC_COUNTIES = config.PUBLIC_DATA_DIR / "medicaid-counties.geojson"

GRID_GEOJSON_OUT = config.OUTPUT_DIR / "grid_1mi.geojson"
GRID_METRICS_OUT = config.OUTPUT_DIR / "grid_1mi_metrics.parquet"

# Drop cells only for states with NO modeled subject pool: non-expansion states
# that are not subject-via-waiver. WI/GA (sized waiver slice) survive; TN (listed
# but control_total 0, not in SUBJECT_STATE_FIPS) is dropped.
DROP_FIPS = set(config.NON_EXPANSION_STATE_FIPS) - set(config.SUBJECT_STATE_FIPS)
ABBR_TO_FIPS = {info["abbr"]: f for f, info in config.STATE_INFO.items()}

# Tract count columns apportioned by population share. Each is divided by the
# tract control via `share` (Σ share == 1 per tract). Optional ones are carried
# only when present in tract_full.parquet.
COUNT_COLS = [
    "subject_count_strict",
    "subject_count_permissive",
    "expansion_pool_estimate",
]
# Tract rate / index columns assigned uniformly within the tract (the share
# cancels). subject_rate is computed from subject/working-age below.
RATE_COLS = [
    "burden_index_centered",
    "verification_difficulty",
    "labor_volatility",
    "access_gap",
]

# Fields written into grid_1mi.geojson. The two label bakes append place_* and
# landmark_*; tippecanoe (stage 10) keeps its -y subset. The non-tiled identity
# columns (county_geoid, nearest_place_*, state_fips, county_fips) ride along for
# the PDF/render path (lib/render_maps.py reads county_geoid with no fallback).
GEOJSON_FIELDS = [
    "cell_id",
    "subject_count_strict", "subject_rate", "burden_index_centered",
    "loss_exposure_strict", "total_pop", "expansion", "subject_via_waiver",
    "state_fips", "county_fips", "county_geoid",
    "parent_county_name", "parent_state_abbr",
    "nearest_place_name", "nearest_place_state",
]
GEOJSON_ROUND = {
    "subject_count_strict": 2,
    "subject_rate": 4,
    "burden_index_centered": 1,
    "loss_exposure_strict": 2,
    "total_pop": 0,
}


def _check_inputs() -> bool:
    for p in (NPE_GRID, TRACT_GEOJSON_IN, TRACT_FULL_IN, LOSS_BREAKDOWN):
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


def _load_tracts(sample_fips: str | None) -> gpd.GeoDataFrame:
    print(f"Loading tracts from {TRACT_GEOJSON_IN.name}...")
    t = pyogrio.read_dataframe(
        TRACT_GEOJSON_IN, columns=["GEOID", "STATEFP"], use_arrow=True
    )
    t["GEOID"] = t["GEOID"].astype(str).str.zfill(11)
    t["STATEFP"] = t["STATEFP"].astype(str).str.zfill(2)
    if sample_fips:
        t = t[t["STATEFP"] == sample_fips].reset_index(drop=True)
        print(f"  sample state {sample_fips}: {len(t):,} tracts")
    else:
        t = t[~t["STATEFP"].isin(["02", "15"])].reset_index(drop=True)
        print(f"  CONUS tracts: {len(t):,}")
    return t


def _load_npe_grid(bbox: tuple | None) -> gpd.GeoDataFrame:
    print(f"Loading NPE grid {NPE_GRID.name} ({NPE_GRID.stat().st_size/1e6:.0f} MB)...")
    t0 = time.time()
    g = pyogrio.read_dataframe(
        NPE_GRID, columns=["cell_id", "total_pop"], use_arrow=True, bbox=bbox
    )
    g["cell_id"] = g["cell_id"].astype(str)
    print(f"  {len(g):,} hex cells in {time.time()-t0:.1f}s")
    return g


def _tract_frame() -> pd.DataFrame:
    """Tract-level metric frame: counts + burden from tract_full, population from
    ACS B01001 (lib/acs_pop), and the within-tract subject_rate."""
    cols = ["GEOID", "state_fips", "county_fips"] + COUNT_COLS + RATE_COLS
    tf = pd.read_parquet(TRACT_FULL_IN)
    keep = [c for c in cols if c in tf.columns]
    missing = [c for c in COUNT_COLS + RATE_COLS if c not in tf.columns]
    if missing:
        print(f"  note: tract_full.parquet lacks {missing} — skipped")
    tf = tf[keep].copy()
    tf["GEOID"] = tf["GEOID"].astype(str).str.zfill(11)
    tf["state_fips"] = tf["state_fips"].astype(str).str.zfill(2)
    tf["county_fips"] = tf["county_fips"].astype(str).str.zfill(3)

    tp = tract_population()  # GEOID(11), total_pop, working_age_pop
    tp["GEOID"] = tp["GEOID"].astype(str).str.zfill(11)
    tdf = tf.merge(tp[["GEOID", "total_pop", "working_age_pop"]], on="GEOID", how="left")
    tdf[["total_pop", "working_age_pop"]] = tdf[["total_pop", "working_age_pop"]].fillna(0.0)
    wa = tdf["working_age_pop"].to_numpy()
    subj = tdf["subject_count_strict"].fillna(0.0).to_numpy()
    tdf["tract_subject_rate"] = np.where(wa > 0, subj / np.where(wa > 0, wa, 1.0), 0.0)
    return tdf


def main() -> None:
    if not _check_inputs():
        sys.exit(1)
    warnings.filterwarnings("ignore", message=".*Geometry is in a geographic CRS.*")

    sample = os.environ.get("MWR_SAMPLE_STATE", "").strip().upper()
    sample_fips = ABBR_TO_FIPS.get(sample) if sample else None
    if sample and not sample_fips:
        print(f"ERROR: unknown sample state {sample!r}", file=sys.stderr)
        sys.exit(1)

    # 1. Tracts (drives the NPE-grid bbox in sample mode for a fast smoke test).
    tracts = _load_tracts(sample_fips)
    npe_bbox = tuple(tracts.total_bounds) if sample_fips else None

    # 2. NPE hex grid → centroids + a cell_id→polygon lookup; drop bulk geometry.
    g_npe = _load_npe_grid(npe_bbox)
    polys = g_npe.set_index("cell_id").geometry.copy()  # restitch source for the write
    cen = g_npe.geometry.centroid
    cells = pd.DataFrame({
        "cell_id": g_npe["cell_id"].to_numpy(),
        "npe_total_pop": g_npe["total_pop"].astype("float64").to_numpy(),
        "centroid_lon": cen.x.to_numpy(),
        "centroid_lat": cen.y.to_numpy(),
    })
    del g_npe, cen

    # 3. Centroid → tract (within); drop cells off the tract mesh.
    cen_gdf = gpd.GeoDataFrame(
        cells[["cell_id"]],
        geometry=gpd.points_from_xy(cells["centroid_lon"], cells["centroid_lat"]),
        crs=config.WEB_CRS,
    )
    sj = gpd.sjoin(cen_gdf, tracts[["GEOID", "geometry"]], how="left", predicate="within")
    sj = sj.drop_duplicates(subset=["cell_id"])
    cells = cells.merge(
        sj[["cell_id", "GEOID"]].rename(columns={"GEOID": "parent_tract_id"}),
        on="cell_id", how="left",
    )
    del cen_gdf, sj, tracts
    n_no_tract = int(cells["parent_tract_id"].isna().sum())
    cells = cells[cells["parent_tract_id"].notna()].copy()
    print(f"  cells with a parent tract: {len(cells):,}  (dropped {n_no_tract:,} off-mesh)")

    # 4. Join tract metrics; population-dasymetric within-tract share.
    tdf = _tract_frame()
    cells = cells.merge(tdf, left_on="parent_tract_id", right_on="GEOID", how="left")
    cells = cells[cells["GEOID"].notna()].copy()  # tract present in the model

    cells["w"] = cells["npe_total_pop"].clip(lower=0.0).fillna(0.0)
    denom = cells.groupby("parent_tract_id")["w"].transform("sum")
    ncell = cells.groupby("parent_tract_id")["cell_id"].transform("size")
    share = np.where(denom.to_numpy() > 0, cells["w"].to_numpy() / np.where(denom.to_numpy() > 0, denom.to_numpy(), 1.0), 1.0 / ncell.to_numpy())
    cells["share"] = share

    # 5a. Apportion counts (tract count × share); 5b. assign rates (uniform).
    for c in COUNT_COLS:
        if c in cells.columns:
            cells[c] = cells[c].fillna(0.0) * cells["share"]
    for pop_c in ("working_age_pop", "total_pop"):
        cells[pop_c] = cells[pop_c].fillna(0.0) * cells["share"]
    cells["subject_rate"] = cells["tract_subject_rate"].fillna(0.0)
    for c in RATE_COLS:
        if c in cells.columns:
            cells[c] = cells[c].fillna(0.0)

    # 6. Identity columns.
    cells["state_fips"] = cells["state_fips"].astype(str).str.zfill(2)
    cells["county_fips"] = cells["county_fips"].astype(str).str.zfill(3)
    cells["county_geoid"] = cells["state_fips"] + cells["county_fips"]
    cells["expansion"] = cells["state_fips"].map(
        lambda f: bool(config.STATE_INFO.get(f, {}).get("expansion", False))
    )
    # Subject via a sized 1115-waiver slice (WI/GA) so the map renders these grid
    # cells as in-scope (metric color) rather than gray non-expansion fill.
    cells["subject_via_waiver"] = cells["state_fips"].map(
        lambda f: bool(config.waiver_meta(f).get("control_total", 0) > 0)
    )
    cells["parent_state_abbr"] = cells["state_fips"].map(
        lambda f: config.STATE_INFO.get(f, {}).get("abbr", "")
    )
    cmap = _county_short_map()
    cells["parent_county_name"] = cells["county_geoid"].map(lambda g: cmap.get(g, "")).fillna("")

    # Drop cells for states with no modeled subject pool before the loss
    # apportionment. Subject-via-waiver states (WI/GA) are retained.
    before = len(cells)
    cells = cells[~cells["state_fips"].isin(DROP_FIPS)].copy()
    print(f"  dropped {before - len(cells):,} non-subject cells; {len(cells):,} remain")

    # 7. Bottom-up per-state loss apportioned by subject share (07c/08b pattern).
    lb = json.loads(LOSS_BREAKDOWN.read_text())
    state_loss = {f: float(v.get("total_loss_2034", 0.0)) for f, v in lb.get("states", {}).items()}
    national_loss = float(lb["_national"]["total_loss_2034"])
    state_subj = cells.groupby("state_fips")["subject_count_strict"].sum().to_dict()
    sf = cells["state_fips"].to_numpy()
    subj = cells["subject_count_strict"].to_numpy()
    ss = np.array([state_subj.get(s, 0.0) for s in sf])
    sl = np.array([state_loss.get(s, 0.0) for s in sf])
    cells["loss_exposure_strict"] = np.where((ss > 0) & (sl > 0), subj / np.where(ss > 0, ss, 1.0) * sl, 0.0)

    # 8. Nearest NPE place (legacy popup fallback).
    print("Joining nearest NPE place...")
    t0 = time.time()
    places = pyogrio.read_dataframe(NPE_PLACES, columns=["NAME", "STUSPS"], use_arrow=True).rename(
        columns={"NAME": "nearest_place_name", "STUSPS": "nearest_place_state"}
    )
    cell_pts = gpd.GeoDataFrame(
        cells[["cell_id"]],
        geometry=gpd.points_from_xy(cells["centroid_lon"], cells["centroid_lat"]),
        crs=config.WEB_CRS,
    )
    near = gpd.sjoin_nearest(cell_pts.to_crs(places.crs), places, how="left").drop_duplicates("cell_id")
    cells = cells.merge(
        near[["cell_id", "nearest_place_name", "nearest_place_state"]], on="cell_id", how="left"
    )
    for c in ("nearest_place_name", "nearest_place_state"):
        cells[c] = cells[c].fillna("")
    del cell_pts, near, places
    print(f"  attached nearest place in {time.time()-t0:.1f}s")

    # 9. Drop zero-subject cells (after loss so the per-state denominator was complete).
    before = len(cells)
    cells = cells[cells["subject_count_strict"] > 0].copy()
    print(f"  dropped {before - len(cells):,} zero-subject cells; {len(cells):,} remain")

    _verify(cells, state_loss, national_loss)

    # 10. Write the lean metrics parquet (full precision, no geometry).
    cells = cells.drop(columns=["w", "GEOID", "tract_subject_rate", "npe_total_pop"], errors="ignore")
    cells.to_parquet(GRID_METRICS_OUT, index=False)
    print(f"-> {GRID_METRICS_OUT.name}: {len(cells):,} cells")

    # 11. Write grid_1mi.geojson — restitch the NPE hex polygons by cell_id.
    _write_geojson(cells, polys)


def _verify(cells: pd.DataFrame, state_loss: dict, national_loss: float) -> None:
    sr = cells["subject_rate"]
    print("\n--- verification ------------------------------------------------")
    print(f"surviving cells: {len(cells):,}")
    print(f"subject_rate: min={sr.min():.3f} max={sr.max():.3f} mean={sr.mean():.3f} "
          f"nunique={sr.nunique():,}  (>0.70: {int((sr > 0.70).sum()):,})")
    subj_total = cells["subject_count_strict"].sum()
    print(f"grid subject_count_strict sum = {subj_total:,.0f}  "
          f"(vs CBO 18.5M; ~1-2% low expected — tracts with no NPE cell go unallocated)")

    grid_loss = cells["loss_exposure_strict"].sum()
    conus_target = sum(v for f, v in state_loss.items() if f not in ("02", "15"))
    print(f"grid loss = {grid_loss:,.0f}  (CONUS bottom-up target {conus_target:,.0f}; "
          f"national-with-AK/HI {national_loss:,.0f})")
    by_state = cells.groupby("state_fips")["loss_exposure_strict"].sum()
    worst = 0.0
    for f, got in by_state.items():
        tgt = state_loss.get(f, 0.0)
        if tgt > 0:
            worst = max(worst, abs(got - tgt) / tgt)
    print(f"per-state loss vs bottom-up: max abs rel diff = {worst:.6f} (≈0 expected)")

    la = cells[(cells["state_fips"] == "06") & (cells["county_fips"] == "037")]
    if len(la):
        print(f"LA County 06037: {len(la):,} cells, mean subject_rate={la['subject_rate'].mean():.3f} "
              f"(county model ~0.30)")
    print("-----------------------------------------------------------------\n")


def _write_geojson(cells: pd.DataFrame, polys: gpd.GeoSeries) -> None:
    print(f"Writing {GRID_GEOJSON_OUT.name} ({len(cells):,} hex cells)...")
    t0 = time.time()
    cols = [c for c in GEOJSON_FIELDS if c in cells.columns]
    out = cells[cols].copy()
    for c, nd in GEOJSON_ROUND.items():
        if c in out.columns:
            out[c] = out[c].round(nd)
            if nd == 0:
                out[c] = out[c].astype("int64")
    geom = polys.reindex(out["cell_id"].to_numpy()).to_numpy()
    gdf = gpd.GeoDataFrame(out, geometry=geom, crs=config.WEB_CRS)
    n_missing = int(pd.isna(gdf.geometry).sum())
    if n_missing:
        print(f"  WARN: {n_missing:,} cells missing geometry after restitch — dropping")
        gdf = gdf[gdf.geometry.notna()].copy()
    if GRID_GEOJSON_OUT.exists():
        GRID_GEOJSON_OUT.unlink()
    # COORDINATE_PRECISION=6 (~0.1 m) trims the intermediate GeoJSON; tippecanoe
    # re-quantizes per zoom so this doesn't change the tile, just the disk/IO.
    pyogrio.write_dataframe(gdf, GRID_GEOJSON_OUT, driver="GeoJSON", COORDINATE_PRECISION=6)
    print(f"-> {GRID_GEOJSON_OUT.name}: {GRID_GEOJSON_OUT.stat().st_size/1e6:.1f} MB "
          f"in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 08 done in {time.time()-t0:.0f}s")
