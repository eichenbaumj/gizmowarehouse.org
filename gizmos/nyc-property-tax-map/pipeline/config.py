"""Shared paths, constants, and tax-rate table for the NYC property-tax pipeline.

The pipeline runs in numbered stages 01..07. Each stage reads from `output/`
(or `raw/`) and writes back to `output/`. Versioning info is stamped into
`output/data_version.json` at the end of stage 02 so the frontend can
display "data current as of <year>" with confidence.
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent
RAW_DIR = PIPELINE_DIR / "raw"
OUTPUT_DIR = PIPELINE_DIR / "output"
PUBLIC_DATA_DIR = PIPELINE_DIR.parent.parent.parent / "public" / "data"
PUBLIC_ASSETS_DIR = PIPELINE_DIR.parent.parent.parent / "public" / "assets"

for d in (RAW_DIR, OUTPUT_DIR, PUBLIC_DATA_DIR, PUBLIC_ASSETS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Source URLs
# ---------------------------------------------------------------------------
# PLUTO is published by NYC DCP. The Socrata mirror (64uk-42ks) ships
# attributes only — no geometry — so we go to DCP's ArcGIS FeatureServer for
# the polygons. See 01_fetch_pluto.py.
PLUTO_DATASET_ID = "64uk-42ks"  # Socrata mirror, attributes only — kept for cross-reference
PLUTO_METADATA_URL = f"https://data.cityofnewyork.us/api/views/{PLUTO_DATASET_ID}.json"
PLUTO_ARCGIS_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/"
    "ArcGIS/rest/services/MAPPLUTO/FeatureServer/0"
)
PLUTO_FIELDS = [
    "bbl",
    "borough",
    "block",
    "lot",
    "address",
    "zipcode",
    "cd",          # Community District (numeric, 3-digit)
    "bct2020",     # Borough + 2020 census tract
    "ownername",
    "bldgclass",   # Building class (e.g. A1, R4, O4) — finer than tax class
    "landuse",     # 1-11 land use code
    "lotarea",     # Land area, sqft
    "bldgarea",    # Gross building floor area, sqft
    "comarea",     # Commercial sqft within building
    "resarea",     # Residential sqft
    "officearea",
    "retailarea",
    "garagearea",
    "numbldgs",
    "numfloors",
    "unitsres",
    "unitstotal",
    "yearbuilt",
    "yearalter1",
    "lottype",
    "bsmtcode",
    "assessland",  # Final billable assessed land
    "assesstot",   # Final billable assessed total — billable AV
    "exempttot",
    "ext",
    "histdist",
    "landmark",
    "builtfar",
    "residfar",
    "commfar",
    "facilfar",
    "borocode",
    "xcoord",
    "ycoord",
    "latitude",
    "longitude",
    "geom",        # WKT MultiPolygon
]
PLUTO_CSV_URL = (
    f"https://data.cityofnewyork.us/resource/{PLUTO_DATASET_ID}.csv?"
    f"$select={','.join(PLUTO_FIELDS)}&$limit=10000000"
)

# PVAD: NYC DOF, on NYC Open Data (Socrata). The legacy dataset yjxr-fw8i
# is unmaintained (last update 2022, max year 2018/19). The current per-BBL
# valuation data lives at 8y4t-faws ("Property Valuation and Assessment Data
# Tax Classes 1,2,3,4"), updated March 2026 with the FY26 tentative roll.
#
# Field naming differs: 8y4t-faws uses scoped prefixes (py = prior year,
# ten = tentative, cbn = change-by-notice, fin = final, cur = current/billing).
# We use `cur*` for "what is currently being billed" and fall back to `fin*`
# if `cur*` is null.
#
#   curmkttot   = current market value (the FULLVAL equivalent, our denominator)
#   curacttot   = current actual assessed value
#   curactextot = current actual exempt total
#   curtrntot   = current transitional AV (Class 2L + 4)
#   curtxbtot   = current taxable BILLABLE AV (numerator after exemptions)
#   curtxbextot = current taxable BILLABLE exempt total
#   curtaxclass = current tax class
PVAD_DATASET_ID = "8y4t-faws"
PVAD_METADATA_URL = f"https://data.cityofnewyork.us/api/views/{PVAD_DATASET_ID}.json"
PVAD_FIELDS = [
    "parid",       # 10-char BBL + 3-char subident (' XXX' for non-easement)
    "boro",
    "block",
    "lot",
    "easement",
    "year",
    "owner",
    "bldg_class",
    # Current (billing) values — primary
    "curtaxclass",
    "curmktland",
    "curmkttot",       # DOF current market value — load-bearing
    "curactland",
    "curacttot",       # Actual AV
    "curactextot",     # Actual exempt
    "curtrnland",
    "curtrntot",       # Transitional AV
    "curtrnextot",
    "curtxbtot",       # Billable AV
    "curtxbextot",     # Billable exempt
    # Final FY (last finalized roll) — fallback if cur* missing
    "fintaxclass",
    "finmkttot",
    "finacttot",
    "finactextot",
    "fintrntot",
    "fintrnextot",
    "fintxbtot",
    "fintxbextot",
    # Tentative FY (most recent) — informational
    "tenmkttot",
    "tentaxclass",
    # Building/lot detail (PVAD-side) — useful when PLUTO doesn't match
    "gross_sqft",
    "residential_area_gross",
    "office_area_gross",
    "retail_area_gross",
    "factory_area_gross",
    "warehouse_area_gross",
    "garage_area",
    "land_area",
    "num_bldgs",
    "yrbuilt",
    "units",
    "coop_apts",
    "housenum_lo",
    "housenum_hi",
    "street_name",
    "zip_code",
    # Condo identifiers — used in stage 03 to aggregate unit-level rows up to
    # the condo lot polygon. condo_number is "{borocode}{condono:05d}", e.g.
    # "100944" = boro 1 + PLUTO CondoNo 944.
    "condo_number",
    "condo_sfx1",
]
PVAD_CSV_URL = (
    f"https://data.cityofnewyork.us/resource/{PVAD_DATASET_ID}.csv?"
    f"$select={','.join(PVAD_FIELDS)}&$limit=10000000"
)

# DOF Annual Tax Rates by tax class. Source: NYC Open Data dataset
# 7zb8-7bpk ("Property Tax Rates by Tax Class"), pulled 2026-04. Most recent
# row is FY24/25; the FY25/26 row had not yet been added to that dataset at
# verification time despite the City Council adopting the FY26 rates in late
# Oct 2025. Our PVAD data spans tax years 2023/24-2026/27 with the bulk in
# 2023/24-2024/25, so applying FY24/25 rates is the right call until the
# 25/26 row publishes.
#
# Reference: https://data.cityofnewyork.us/City-Government/Property-Tax-Rates-by-Tax-Class/7zb8-7bpk
TAX_RATES_DEFAULT = {
    "1": 0.20085,   # FY24/25
    "2": 0.12500,   # FY24/25 (was 0.12502 in FY23/24)
    "3": 0.11181,   # FY24/25 utility special franchises
    "4": 0.10762,   # FY24/25
}
TAX_RATES_FISCAL_YEAR = "FY24/25"

# ---------------------------------------------------------------------------
# Coordinate systems
# ---------------------------------------------------------------------------
# PLUTO ships in NY State Plane Long Island (EPSG:2263, US feet). We reproject
# to WGS84 (EPSG:4326) for web-mercator tiling.
PLUTO_CRS_NATIVE = "EPSG:2263"
WEB_CRS = "EPSG:4326"

# ---------------------------------------------------------------------------
# Output artifacts
# ---------------------------------------------------------------------------
PARCELS_GEOJSON = OUTPUT_DIR / "parcels.geojson"
PARCELS_PMTILES = OUTPUT_DIR / "parcels.pmtiles"
CD_AGGREGATES_GEOJSON = PUBLIC_DATA_DIR / "nyc-cd-aggregates.geojson"
NTA_AGGREGATES_GEOJSON = PUBLIC_DATA_DIR / "nyc-nta-aggregates.geojson"
DATA_VERSION_JSON = PUBLIC_DATA_DIR / "nyc-property-tax-version.json"


def stamp_version(payload: dict) -> None:
    """Persist a versioning record to the public data dir.

    Stage 02 calls this once it knows the PLUTO + PVAD edition years, so the
    frontend's "About" panel can render "Data current as of FY{year}" without
    having to scrape the file.
    """
    DATA_VERSION_JSON.write_text(json.dumps(payload, indent=2))


def load_version() -> dict | None:
    if DATA_VERSION_JSON.exists():
        return json.loads(DATA_VERSION_JSON.read_text())
    return None
