"""Per-state CSV writer for the PDF brief's downloadable data."""
from __future__ import annotations

import csv
from pathlib import Path

import geopandas as gpd

import config  # type: ignore

REPO = config.REPO_ROOT
COUNTIES_PATH = REPO / "public/data/medicaid-counties.geojson"
CSV_OUT_DIR = REPO / "public/assets/medicaid-data"
CSV_OUT_DIR.mkdir(parents=True, exist_ok=True)

_counties_cache: gpd.GeoDataFrame | None = None


def _counties() -> gpd.GeoDataFrame:
    global _counties_cache
    if _counties_cache is None:
        _counties_cache = gpd.read_file(COUNTIES_PATH)
    return _counties_cache


def write_state_csv(state_fips: str, state_abbr: str) -> Path:
    """Write a single state's full county breakdown to CSV. Returns path."""
    df = _counties()
    df = df[df["state_fips"] == state_fips].copy()
    df = df.sort_values("county_name")
    out = CSV_OUT_DIR / f"medicaid_counties_{state_abbr}.csv"
    cols = [
        "GEOID", "county_name", "total_pop", "working_age_pop", "pov_pct",
        "subject_count_strict", "subject_count_permissive",
        "loss_exposure_strict", "subject_rate", "burden_index_centered",
    ]
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "county_fips", "county_name", "total_pop", "working_age_pop", "pov_pct",
            "subject_count_strict", "subject_count_permissive",
            "loss_exposure_strict", "subject_rate", "burden_index_centered",
        ])
        for _, r in df.iterrows():
            w.writerow([
                r["GEOID"],
                r["county_name"],
                int(r["total_pop"] or 0),
                int(r["working_age_pop"] or 0),
                round(float(r["pov_pct"] or 0), 2),
                int(r["subject_count_strict"] or 0),
                int(r["subject_count_permissive"] or 0),
                int(r["loss_exposure_strict"] or 0),
                round(float(r["subject_rate"] or 0), 4),
                round(float(r["burden_index_centered"] or 0), 2),
            ])
    return out
