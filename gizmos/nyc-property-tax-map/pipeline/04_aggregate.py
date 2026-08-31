#!/usr/bin/env python3
"""Stage 04 — citywide stats + per-parcel etr_vs_median enrichment + NTA
aggregates for the low-zoom map layer + (opt-in) BBL → properties manifest.

Inputs:
    --in <path>   parcels_with_tax.geojson from stage 03 (default: output/...)

Outputs:
    output/<basename>_enriched.geojson         parcels + etr_vs_median
    output/citywide_stats.json                 medians + percentiles for legend
    public/data/nyc-property-tax-stats.json    ditto, deployed
    public/data/nyc-nta-aggregates.geojson     NTA polygons + per-NTA medians
                                               (frontend's z=9–13 layer)
    public/data/parcels-manifest.json          BBL -> trimmed props + centroid
                                               (opt-in via --manifest; only for
                                                samples — citywide is too big)

NTA boundaries come from NYC Open Data dataset 9nt8-h7nd (262 NTAs, 2020).
The endpoint is /api/geospatial/<id>?method=export&format=geojson — NOT the
/resource/<id>.geojson form (that one returns 404).
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import pandas as pd
import requests

import config

NTA_GEOJSON_URL = (
    "https://data.cityofnewyork.us/api/geospatial/9nt8-h7nd"
    "?method=export&format=geojson"
)
NTA_BOUNDARIES_CACHE = config.RAW_DIR / "nta_boundaries_2020.geojson"


def centroid(geom: dict | None) -> list[float] | None:
    """Crude representative point: mean of all coordinates in a (Multi)Polygon.
    Good enough for a flyTo target; we don't need geometric correctness."""
    if not geom:
        return None
    coords: list[list[float]] = []

    def walk(g):
        if isinstance(g, list):
            if g and isinstance(g[0], (int, float)):
                coords.append(g)
            else:
                for c in g:
                    walk(c)

    walk(geom.get("coordinates", []))
    if not coords:
        return None
    return [statistics.mean(c[0] for c in coords), statistics.mean(c[1] for c in coords)]


# Properties carried into the manifest. Trimmed to keep the manifest small —
# everything else stays in the GeoJSON / PMTiles for the map render.
MANIFEST_FIELDS = [
    "bbl",
    "address",
    "borough",
    "bldg_class",
    "tax_class",
    "year_built",
    "units_total",
    "units_res",
    "bldg_area",
    "lot_area",
    "market_value",
    "billable_av",
    "tax_bill",
    "etr",
    "tax_per_sqft",
    "etr_vs_median",
    "data_quality",
    "aggregation",
    "units_aggregated",
]


def fetch_nta_boundaries() -> dict:
    """Fetch + cache NYC NTA 2020 boundary polygons. ~262 features, ~3 MB."""
    if NTA_BOUNDARIES_CACHE.exists():
        return json.loads(NTA_BOUNDARIES_CACHE.read_text())
    print(f"Fetching NTA 2020 boundaries: {NTA_GEOJSON_URL}")
    r = requests.get(NTA_GEOJSON_URL, timeout=120)
    r.raise_for_status()
    NTA_BOUNDARIES_CACHE.write_text(r.text)
    return r.json()


def build_nta_aggregates(parcels_features: list[dict], nta_geo: dict) -> dict:
    """Spatial-join parcel centroids to NTA polygons; compute per-NTA medians.

    Returns a FeatureCollection of NTA polygons enriched with median ETR,
    median $/sqft, median market value, median exempt_fraction, parcel
    count, and % abated.
    """
    # Need geopandas + shapely for the spatial join. Imported lazily so
    # earlier stages don't load it.
    import geopandas as gpd
    from shapely.geometry import Point, shape

    # Build a parcel point GeoDataFrame from centroids of the polygon geom.
    parcel_rows = []
    for f in parcels_features:
        c = centroid(f.get("geometry"))
        if not c:
            continue
        p = f["properties"]
        parcel_rows.append({
            "lon": c[0], "lat": c[1],
            "etr": p.get("etr"),
            "tax_per_sqft": p.get("tax_per_sqft"),
            "market_value": p.get("market_value"),
            "tax_bill": p.get("tax_bill"),
            "exempt_fraction": p.get("exempt_fraction"),
        })
    pdf = pd.DataFrame(parcel_rows)
    parcel_gdf = gpd.GeoDataFrame(
        pdf,
        geometry=gpd.points_from_xy(pdf["lon"], pdf["lat"]),
        crs="EPSG:4326",
    )

    # Build NTA GeoDataFrame.
    nta_features = nta_geo.get("features", [])
    nta_records = []
    for nf in nta_features:
        props = nf.get("properties", {})
        nta_records.append({
            "nta2020": props.get("nta2020"),
            "ntaname": props.get("ntaname"),
            "boroname": props.get("boroname"),
            "geometry": shape(nf["geometry"]),
        })
    nta_gdf = gpd.GeoDataFrame(nta_records, crs="EPSG:4326")

    # Spatial join: each parcel point gets the NTA it falls in.
    print(f"Spatial-joining {len(parcel_gdf):,} parcels to {len(nta_gdf)} NTAs...")
    joined = gpd.sjoin(parcel_gdf, nta_gdf, predicate="within", how="left")
    print(f"  joined; {joined['nta2020'].notna().sum():,} parcels matched an NTA")

    # Aggregate.
    agg = (
        joined.groupby("nta2020")
        .agg(
            n_parcels=("etr", "size"),
            n_with_etr=("etr", lambda s: int(s.notna().sum())),
            median_etr=("etr", "median"),
            median_tax_per_sqft=("tax_per_sqft", "median"),
            median_market_value=("market_value", "median"),
            median_tax_bill=("tax_bill", "median"),
            median_exempt_fraction=("exempt_fraction", "median"),
            pct_abated=(
                "exempt_fraction",
                lambda s: float((s.notna() & (s > 0.05)).mean()),
            ),
        )
        .reset_index()
    )
    agg_by_nta = agg.set_index("nta2020").to_dict(orient="index")

    # Build the output FeatureCollection.
    out_features = []
    for nf in nta_features:
        nta = nf["properties"].get("nta2020")
        a = agg_by_nta.get(nta, {})
        merged_props = {
            "nta2020": nta,
            "ntaname": nf["properties"].get("ntaname"),
            "boroname": nf["properties"].get("boroname"),
            "n_parcels": int(a.get("n_parcels", 0)),
            "n_with_etr": int(a.get("n_with_etr", 0)),
            "median_etr": (
                round(float(a["median_etr"]), 5)
                if a.get("median_etr") is not None and pd.notna(a["median_etr"])
                else None
            ),
            "median_tax_per_sqft": (
                round(float(a["median_tax_per_sqft"]), 2)
                if a.get("median_tax_per_sqft") is not None and pd.notna(a["median_tax_per_sqft"])
                else None
            ),
            "median_market_value": (
                round(float(a["median_market_value"]), 2)
                if a.get("median_market_value") is not None and pd.notna(a["median_market_value"])
                else None
            ),
            "median_tax_bill": (
                round(float(a["median_tax_bill"]), 2)
                if a.get("median_tax_bill") is not None and pd.notna(a["median_tax_bill"])
                else None
            ),
            "median_exempt_fraction": (
                round(float(a["median_exempt_fraction"]), 4)
                if a.get("median_exempt_fraction") is not None and pd.notna(a["median_exempt_fraction"])
                else None
            ),
            "pct_abated": (
                round(float(a["pct_abated"]), 4)
                if a.get("pct_abated") is not None and pd.notna(a["pct_abated"])
                else None
            ),
        }
        out_features.append({
            "type": "Feature",
            "geometry": nf["geometry"],
            "properties": merged_props,
        })
    return {"type": "FeatureCollection", "features": out_features}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--in",
        dest="inp",
        default=str(config.OUTPUT_DIR / "parcels_with_tax.geojson"),
    )
    ap.add_argument("--out", dest="out", default=None)
    ap.add_argument("--manifest", dest="manifest", default=None)
    args = ap.parse_args()

    inp = Path(args.inp)
    out = Path(args.out) if args.out else inp.parent / (inp.stem + "_enriched.geojson")
    # Manifest is OPT-IN. For citywide (~860k parcels) the manifest is ~330 MB
    # which is too big to ship in /public/. Use it for borough/zip samples only.
    manifest_path = Path(args.manifest) if args.manifest else None

    print(f"Loading {inp}")
    fc = json.loads(inp.read_text())
    rows = [f["properties"] for f in fc["features"]]
    df = pd.DataFrame(rows)
    n = len(df)
    print(f"  {n:,} parcels")

    # Citywide + per-class statistics on parcels with valid ETR.
    valid = df[df["etr"].notna() & (df["etr"] > 0)]
    print(f"  {len(valid):,} with valid ETR")

    stats: dict = {
        "n_parcels_total": int(n),
        "n_with_etr": int(len(valid)),
        "tax_year": getattr(config, "TAX_RATES_FISCAL_YEAR", None),
        "etr_overall": {
            "median": float(valid["etr"].median()),
            "p10": float(valid["etr"].quantile(0.10)),
            "p25": float(valid["etr"].quantile(0.25)),
            "p75": float(valid["etr"].quantile(0.75)),
            "p90": float(valid["etr"].quantile(0.90)),
        },
        "etr_by_class": {},
        "tax_per_sqft_overall": {
            "median": float(df.loc[df["tax_per_sqft"] > 0, "tax_per_sqft"].median())
            if (df["tax_per_sqft"] > 0).any() else None,
            "p90": float(df.loc[df["tax_per_sqft"] > 0, "tax_per_sqft"].quantile(0.9))
            if (df["tax_per_sqft"] > 0).any() else None,
        },
        "tax_bill_overall": {
            "median": float(df.loc[df["tax_bill"] > 0, "tax_bill"].median())
            if (df["tax_bill"] > 0).any() else None,
            "p90": float(df.loc[df["tax_bill"] > 0, "tax_bill"].quantile(0.9))
            if (df["tax_bill"] > 0).any() else None,
        },
    }
    for cls in valid["tax_class"].dropna().unique():
        sub = valid[valid["tax_class"] == cls]
        stats["etr_by_class"][str(cls)] = {
            "n": int(len(sub)),
            "median": float(sub["etr"].median()),
            "p10": float(sub["etr"].quantile(0.10)),
            "p90": float(sub["etr"].quantile(0.90)),
        }
    stats_path = config.OUTPUT_DIR / "citywide_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2))
    # Also publish to the deployed public data dir so the map can read it.
    (config.PUBLIC_DATA_DIR / "nyc-property-tax-stats.json").write_text(
        json.dumps(stats, indent=2)
    )
    print(f"  Citywide median ETR: {stats['etr_overall']['median']*100:.2f}%")
    print(f"  Wrote {stats_path}")

    # etr_vs_median enrichment + manifest build.
    citywide_med = stats["etr_overall"]["median"]
    new_features = []
    manifest: dict = {}
    for feat, props in zip(fc["features"], rows):
        etr = props.get("etr")
        props["etr_vs_median"] = (
            round(etr / citywide_med - 1.0, 4)
            if (etr and citywide_med)
            else None
        )
        new_features.append({
            "type": "Feature",
            "geometry": feat.get("geometry"),
            "properties": props,
        })
        # Manifest entry.
        bbl = props.get("bbl")
        if bbl:
            entry = {k: props.get(k) for k in MANIFEST_FIELDS}
            c = centroid(feat.get("geometry"))
            if c:
                entry["_lon"] = round(c[0], 6)
                entry["_lat"] = round(c[1], 6)
            manifest[str(bbl)] = entry

    # Scrub pandas NaN out of properties — JSON disallows NaN literals and
    # tippecanoe rejects the file. (Pandas Float NaN sneaks in via PVAD's
    # `owner` column for parcels where DOF has no owner string.)
    import math

    def scrub(v):
        if isinstance(v, float) and math.isnan(v):
            return None
        return v

    for feat in new_features:
        feat["properties"] = {k: scrub(v) for k, v in feat["properties"].items()}

    out.write_text(json.dumps({"type": "FeatureCollection", "features": new_features}))
    print(f"  Wrote {out}")

    # NTA aggregates for the low-zoom layer.
    try:
        nta_geo = fetch_nta_boundaries()
        nta_fc = build_nta_aggregates(new_features, nta_geo)
        nta_out = config.PUBLIC_DATA_DIR / "nyc-nta-aggregates.geojson"
        nta_out.write_text(json.dumps(nta_fc))
        print(
            f"  Wrote {nta_out} "
            f"({len(nta_fc['features'])} NTAs, "
            f"{nta_out.stat().st_size/(1<<20):.1f} MB)"
        )
    except Exception as e:
        print(f"NTA aggregate step failed: {e}; continuing without NTA layer.")

    if manifest_path is not None:
        for bbl, entry in manifest.items():
            manifest[bbl] = {k: scrub(v) for k, v in entry.items()}
        manifest_path.write_text(json.dumps(manifest))
        print(f"  Wrote {manifest_path} ({len(manifest):,} BBLs, "
              f"{manifest_path.stat().st_size/(1<<20):.1f} MB)")


if __name__ == "__main__":
    main()
