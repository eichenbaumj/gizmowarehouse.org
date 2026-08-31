#!/usr/bin/env python3
"""Stage 01 — fetch MapPLUTO with polygon geometry from NYC DCP's ArcGIS service.

The Socrata mirror of PLUTO (64uk-42ks) does NOT include geometry, so we go
to the source: DCP publishes MapPLUTO as an ArcGIS FeatureServer at
https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/ArcGIS/rest/services/MAPPLUTO/FeatureServer/0

We query it paginated (2000 records / page) and request server-side
reprojection to WGS84. Output is a single GeoJSON file in `output/`.

Usage:
    python 01_fetch_pluto.py                  # full citywide (~860k features, ~30-60 min)
    python 01_fetch_pluto.py --sample-zip 11201   # one zipcode (fast)
    python 01_fetch_pluto.py --sample-boro BK     # one borough (Manhattan/Bronx/etc.)
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import requests
from tqdm import tqdm

import config

ARCGIS_BASE = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/"
    "ArcGIS/rest/services/MAPPLUTO/FeatureServer/0"
)
PAGE_SIZE = 2000

BORO_NAMES = {"MN": "MN", "BX": "BX", "BK": "BK", "QN": "QN", "SI": "SI"}

# ArcGIS field names are TitleCase. We pull a working subset; downstream
# stages tolerate missing fields. Adding a column? Update both this list
# and the consumer in 03_compute_tax_bill.py / 05_export_geojson.py.
OUT_FIELDS = [
    "BBL", "Borough", "Block", "Lot", "CD", "BCT2020",
    "Address", "ZipCode", "OwnerName",
    "BldgClass", "LandUse",
    "LotArea", "BldgArea", "ComArea", "ResArea", "OfficeArea",
    "RetailArea", "GarageArea", "NumBldgs", "NumFloors",
    "UnitsRes", "UnitsTotal", "YearBuilt",
    "AssessLand", "AssessTot", "ExemptTot",
    "BoroCode", "Latitude", "Longitude",
    "BuiltFAR", "ResidFAR", "CommFAR", "FacilFAR",
    "HistDist", "Landmark",
    "CondoNo",
]


def build_where(args) -> str:
    if args.sample_zip:
        return f"ZipCode = '{args.sample_zip}'"
    if args.sample_boro:
        b = args.sample_boro.upper()
        if b not in BORO_NAMES:
            raise SystemExit(f"--sample-boro must be one of {list(BORO_NAMES)}")
        return f"Borough = '{BORO_NAMES[b]}'"
    return "1=1"


def query_count(where: str) -> int:
    r = requests.get(
        ARCGIS_BASE + "/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("count", 0)


def query_page(where: str, offset: int) -> dict:
    """Fetch one page of features as GeoJSON in WGS84."""
    params = {
        "where": where,
        "outFields": ",".join(OUT_FIELDS),
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "orderByFields": "BBL ASC",
    }
    # Brief retry — ArcGIS occasionally returns 5xx under load.
    for attempt in range(3):
        try:
            r = requests.get(ARCGIS_BASE + "/query", params=params, timeout=120)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-zip", help="restrict to one 5-digit zipcode")
    ap.add_argument("--sample-boro", help="restrict to one borough (MN/BX/BK/QN/SI)")
    ap.add_argument("--out", default=None, help="output filename override")
    args = ap.parse_args()

    where = build_where(args)
    sample_tag = args.sample_zip or args.sample_boro or None
    out_name = args.out or (f"pluto.{sample_tag}.geojson" if sample_tag else "pluto.geojson")
    out = config.RAW_DIR / out_name

    total = query_count(where)
    print(f"PLUTO -> {out}")
    print(f"Filter: {where}")
    print(f"Features: {total:,}")
    if total == 0:
        raise SystemExit("Filter returned zero features.")

    features: list[dict] = []
    n_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    for offset in tqdm(range(0, total, PAGE_SIZE), total=n_pages, desc="pluto", disable=not sys.stderr.isatty()):
        page = query_page(where, offset)
        feats = page.get("features", [])
        if not feats:
            break
        features.extend(feats)

    fc = {"type": "FeatureCollection", "features": features}
    out.write_text(json.dumps(fc))

    # Stamp meta for stage 02.
    meta = {
        "source": "NYC DCP MapPLUTO ArcGIS FeatureServer",
        "url": ARCGIS_BASE,
        "filter": where,
        "feature_count": len(features),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (config.RAW_DIR / "pluto.meta.json").write_text(json.dumps(meta, indent=2))

    size_mb = out.stat().st_size / (1 << 20)
    with_geom = sum(1 for f in features if f.get("geometry"))
    print(f"Wrote {out} ({size_mb:.1f} MB, {len(features):,} features, {with_geom:,} with geometry)")


if __name__ == "__main__":
    main()
