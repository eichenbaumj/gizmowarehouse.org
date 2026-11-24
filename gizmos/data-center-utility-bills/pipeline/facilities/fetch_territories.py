#!/usr/bin/env python3
"""Fetch Electric Retail Service Territories (HIFLD, built by ORNL for DOE CESER).

The HIFLD Open portal was retired in August 2025. This pulls a public ArcGIS
copy of the same layer. The polygons reflect roughly the 2022 EIA-861 vintage
and OVERLAP each other (a municipal utility sits inside the investor-owned
utility polygon that surrounds it), so a point can fall in several. Assignment
rules live in build_inventory.py; every facility of 50 MW or more is verified
by hand regardless.

Geometry is simplified to about 100 m on the server. That is fine for
assigning points to utilities and keeps the download small; the map build
fetches full resolution separately.

Run:  python3 -I pipeline/facilities/fetch_territories.py
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "territories" / "retail_service_territories.geojson"
LAYER = ("https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/"
         "Electric_Retail_Service_Territories_HIFLD/FeatureServer/0/query")
FIELDS = "OBJECTID,ID,NAME,STATE,TYPE,CNTRL_AREA,HOLDING_CO,RETAIL_MWH,CUSTOMERS,YEAR,SOURCEDATE"
PAGE = 250


def page(offset: int) -> dict:
    q = urllib.parse.urlencode({
        "where": "1=1", "outFields": FIELDS, "outSR": 4326, "f": "geojson",
        "orderByFields": "OBJECTID", "resultOffset": offset, "resultRecordCount": PAGE,
        "maxAllowableOffset": 0.001, "geometryPrecision": 4,
    })
    req = urllib.request.Request(f"{LAYER}?{q}", headers={"User-Agent": "research-data-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main() -> int:
    feats: list[dict] = []
    offset = 0
    while True:
        d = page(offset)
        got = d.get("features", [])
        feats.extend(got)
        print(f"offset {offset}: {len(got)} features (total {len(feats)})", flush=True)
        if len(got) < PAGE:
            break
        offset += PAGE
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print("wrote", OUT.relative_to(ROOT), f"{OUT.stat().st_size / 1e6:.1f} MB")
    return 0 if feats else 1


if __name__ == "__main__":
    sys.exit(main())
