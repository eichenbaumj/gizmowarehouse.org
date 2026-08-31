"""Stage 02 — fetch Census cartographic boundary geometries.

We pull cb_2024 simplified shapefiles for:
  - states (cb_2024_us_state_500k)
  - counties (cb_2024_us_county_500k)
  - tracts, per-state (cb_2024_{fips}_tract_500k)

500k is the most simplified ("1:500,000") version — appropriate for web display.
Full TIGER/Line tract polygons triple the bundle size with no visible benefit.

Output:
  raw/cb_2024_states.geojson      ~ 1 MB
  raw/cb_2024_counties.geojson    ~ 35 MB
  raw/cb_2024_tracts_{fips}.geojson  (one per state)
  raw/cb_2024_tracts_all.geojson  ~ 130 MB (concatenated for downstream stages)

Resumable: if a file already exists, skip the download.

Run: python 02_fetch_geometry.py
"""

from __future__ import annotations

import io
import os
import sys
import time
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from tqdm import tqdm

import config


def _which_states() -> list[str]:
    sample = os.environ.get("MWR_SAMPLE_STATE", "").strip().upper()
    if not sample:
        return config.ALL_STATE_FIPS
    if len(sample) == 2 and sample.isalpha():
        match = [f for f, info in config.STATE_INFO.items() if info["abbr"] == sample]
        if not match:
            print(f"ERROR: unknown state abbreviation {sample!r}", file=sys.stderr)
            sys.exit(1)
        return match
    if sample in config.STATE_INFO:
        return [sample]
    print(f"ERROR: unknown state FIPS {sample!r}", file=sys.stderr)
    sys.exit(1)


def download_zip(url: str, label: str, max_retries: int = 4) -> bytes:
    """Download a zip with retry + exponential backoff for transient network errors.

    Census TIGER URLs occasionally drop mid-stream (ChunkedEncodingError /
    IncompleteRead). Retry up to max_retries times with exponential backoff so
    one transient failure doesn't kill an otherwise multi-hour pipeline run.
    """
    import time as _time
    last_exc = None
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"    retry {attempt}/{max_retries} after {2 ** (attempt - 1)}s backoff")
            _time.sleep(2 ** (attempt - 1))
        print(f"  downloading {label}: {url}")
        try:
            resp = requests.get(url, timeout=300)
            resp.raise_for_status()
            return resp.content
        except (requests.RequestException, requests.exceptions.ChunkedEncodingError) as e:
            last_exc = e
            print(f"    network error: {type(e).__name__}: {e}")
            continue
    raise RuntimeError(f"download failed after {max_retries} attempts: {url}") from last_exc


def read_shp_from_zip(zip_bytes: bytes) -> gpd.GeoDataFrame:
    """Extract the .shp + sidecars to a temp dir and read."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Find the .shp inside
        shp_names = [n for n in zf.namelist() if n.endswith(".shp")]
        if not shp_names:
            raise RuntimeError("No .shp found in archive")
        shp_name = shp_names[0]
        # Extract everything to a temp dir
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            zf.extractall(td)
            return gpd.read_file(Path(td) / shp_name)


def fetch_states() -> Path:
    out = config.RAW_DIR / "cb_2024_states.geojson"
    if out.exists():
        print(f"  cache hit: {out.name}")
        return out
    zip_bytes = download_zip(config.TIGER_STATE_URL, "states")
    gdf = read_shp_from_zip(zip_bytes)
    # Filter to our state list (excludes PR, GU, AS, VI, MP)
    gdf = gdf[gdf["STATEFP"].isin(config.ALL_STATE_FIPS)].copy()
    gdf = gdf.to_crs(config.WEB_CRS)
    # Tag expansion status for use in the states layer
    gdf["expansion"] = gdf["STATEFP"].map(
        lambda f: config.STATE_INFO[f]["expansion"]
    )
    gdf["partial_expansion"] = gdf["STATEFP"].map(
        lambda f: bool(config.STATE_INFO[f].get("partial_expansion"))
    )
    # Subject-via-1115-waiver tags so the map can style WI/GA (sized slice) and TN
    # (listed but not quantified) distinctly from truly-unaffected states.
    gdf["subject_via_waiver"] = gdf["STATEFP"].map(
        lambda f: bool(config.waiver_meta(f).get("control_total", 0) > 0)
    )
    gdf["waiver_listed"] = gdf["STATEFP"].map(
        lambda f: bool(config.waiver_meta(f))
    )
    gdf["loss_quantified"] = gdf["STATEFP"].map(
        lambda f: bool(config.waiver_meta(f).get("loss_quantified", True))
    )
    gdf["waiver_note"] = gdf["STATEFP"].map(
        lambda f: config.waiver_meta(f).get("label") or ""
    )
    gdf.to_file(out, driver="GeoJSON")
    print(f"  -> {out.name}: {len(gdf):,} states")
    return out


def fetch_counties() -> Path:
    out = config.RAW_DIR / "cb_2024_counties.geojson"
    if out.exists():
        print(f"  cache hit: {out.name}")
        return out
    zip_bytes = download_zip(config.TIGER_COUNTY_URL, "counties")
    gdf = read_shp_from_zip(zip_bytes)
    gdf = gdf[gdf["STATEFP"].isin(config.ALL_STATE_FIPS)].copy()
    gdf = gdf.to_crs(config.WEB_CRS)
    gdf.to_file(out, driver="GeoJSON")
    print(f"  -> {out.name}: {len(gdf):,} counties")
    return out


def fetch_tracts_for_state(state_fips: str) -> Path:
    out = config.RAW_DIR / f"cb_2024_tracts_{state_fips}.geojson"
    if out.exists():
        return out
    url = config.TIGER_TRACT_URL_FMT.format(state_fips=state_fips)
    zip_bytes = download_zip(url, f"tracts state {state_fips}")
    gdf = read_shp_from_zip(zip_bytes)
    gdf = gdf.to_crs(config.WEB_CRS)
    gdf.to_file(out, driver="GeoJSON")
    return out


def main() -> None:
    states_path = fetch_states()
    counties_path = fetch_counties()

    state_fips_list = _which_states()
    print(f"\nFetching tracts for {len(state_fips_list)} state(s)...")
    tract_paths = []
    for fips in tqdm(state_fips_list, desc="states"):
        tract_paths.append(fetch_tracts_for_state(fips))

    # Concatenate all per-state tract files into one national tracts GeoJSON
    all_tracts_out = config.RAW_DIR / "cb_2024_tracts_all.geojson"
    if not all_tracts_out.exists() or len(state_fips_list) < len(config.ALL_STATE_FIPS):
        print("\nConcatenating per-state tract files...")
        frames = [gpd.read_file(p) for p in tract_paths]
        combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
        combined.to_file(all_tracts_out, driver="GeoJSON")
        print(f"  -> {all_tracts_out.name}: {len(combined):,} tracts")

    print(f"\nGeometry artifacts in {config.RAW_DIR}/")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 02 done in {time.time() - t0:.1f}s")
