#!/usr/bin/env python3
"""One-off: fetch cb_2024 US states geometry, simplify, merge in placeholder
Medicaid summary data, and write to public/data/medicaid-states.geojson.

This unblocks the frontend prototype before the full pipeline produces real
data. Once stage 07 of the pipeline runs end-to-end, that file will replace
this one.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import requests

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "public" / "data" / "medicaid-states.geojson"
SUMMARY_IN = REPO / "public" / "data" / "medicaid-state-summary.json"
URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip"

# Standard inset shift for AK / HI to fit them under the lower-48
INSET_TRANSFORMS = {
    "02": {"scale": 0.35, "translate_x": 38, "translate_y": -34},  # AK
    "15": {"scale": 1.0, "translate_x": 51, "translate_y": 5},      # HI
}


def shift_geometry(geom, dx: float, dy: float, scale: float):
    from shapely.affinity import translate, scale as scale_geom
    if scale != 1.0:
        geom = scale_geom(geom, xfact=scale, yfact=scale, origin="center")
    return translate(geom, xoff=dx, yoff=dy)


def main():
    print(f"Fetching {URL}...")
    resp = requests.get(URL, timeout=120)
    resp.raise_for_status()
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(td)
        shp = next(Path(td).glob("*.shp"))
        gdf = gpd.read_file(shp).to_crs("EPSG:4326")

    # Drop territories
    gdf = gdf[gdf["STATEFP"].isin([str(s).zfill(2) for s in [
        1,2,4,5,6,8,9,10,11,12,13,15,16,17,18,19,20,21,22,23,24,25,26,27,28,
        29,30,31,32,33,34,35,36,37,38,39,40,41,42,44,45,46,47,48,49,50,51,53,
        54,55,56
    ]])].copy()

    # Apply inset for AK + HI so they fit under the lower-48 on a flat map
    for fips, t in INSET_TRANSFORMS.items():
        mask = gdf["STATEFP"] == fips
        if mask.any():
            gdf.loc[mask, "geometry"] = gdf.loc[mask, "geometry"].apply(
                lambda g: shift_geometry(g, t["translate_x"], t["translate_y"], t["scale"])
            )

    # Simplify aggressively for web
    gdf["geometry"] = gdf["geometry"].simplify(0.02, preserve_topology=True)

    # Merge in placeholder summary data
    summary = json.loads(SUMMARY_IN.read_text())
    by_fips = {row["state_fips"]: row for row in summary["states"]}
    expansion_map = {
        # 41 expansion states + DC (everything except the 10 non-expansion)
        f: f not in {"01","12","13","20","28","45","47","48","55","56"}
        for f in gdf["STATEFP"].tolist()
    }

    def attach(fips: str):
        row = by_fips.get(fips, {})
        return {
            "subject_count_strict": float(row.get("subject_count_strict", 0)),
            "subject_count_permissive": float(row.get("subject_count_permissive", 0)),
            "loss_exposure_strict": float(row.get("loss_exposure_strict", 0)),
            "burden_index_centered": float(row.get("burden_index_centered", 0)),
            "subject_rate": float(row.get("subject_rate", 0)),
            "expansion": expansion_map.get(fips, True),
            "partial_expansion": bool(row.get("partial_expansion", False)),
            # Subject-via-1115-waiver tags (WI/GA sized, TN listed-not-quantified)
            # so the map's gray vs. amber hatch and the metric fill can distinguish
            # the three non-expansion scope pathways. Sourced from stage 07's summary.
            "subject_via_waiver": bool(row.get("subject_via_waiver", False)),
            "waiver_listed": bool(row.get("waiver_listed", False)),
            "loss_quantified": bool(row.get("loss_quantified", True)),
            "already_work_conditional": bool(row.get("already_work_conditional", False)),
            "waiver_note": row.get("waiver_note") or "",
            "hardship_exception_status": row.get("hardship_exception_status", "undecided"),
        }

    for col in ["subject_count_strict", "subject_count_permissive", "loss_exposure_strict",
                "burden_index_centered", "subject_rate", "expansion",
                "partial_expansion", "subject_via_waiver", "waiver_listed",
                "loss_quantified", "already_work_conditional", "waiver_note",
                "hardship_exception_status"]:
        gdf[col] = gdf["STATEFP"].map(lambda f: attach(f)[col])

    # Keep only what the frontend needs
    keep = ["STATEFP", "STUSPS", "NAME", "subject_count_strict",
            "subject_count_permissive", "loss_exposure_strict",
            "burden_index_centered", "subject_rate", "expansion",
            "partial_expansion", "subject_via_waiver", "waiver_listed",
            "loss_quantified", "already_work_conditional", "waiver_note",
            "hardship_exception_status", "geometry"]
    gdf = gdf[keep].copy()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT, driver="GeoJSON")
    size_kb = OUT.stat().st_size / 1024
    print(f"-> {OUT.relative_to(REPO)} ({len(gdf)} states, {size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
