#!/usr/bin/env python3
"""Trace the PLUTO ↔ PVAD condo join for one or more BBLs.

Use when a parcel renders blank ("no_pvad_match") on the deployed map and
you want to know exactly where the join is failing — source-data gap,
pipeline logic, or stale local cache.

Pulls fresh PLUTO (ArcGIS) + PVAD (Socrata) for each BBL, reproduces the
join logic from 03_compute_tax_bill in isolation, and prints a verdict.

Usage:
    python diagnose_join.py                                  # defaults to 240 Centre + 20 Henry
    python diagnose_join.py 1004727501 3002117501            # explicit BBLs
    python diagnose_join.py 1004727501 --pvad-limit 200      # raise unit-row cap
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import quote

import importlib.util
from pathlib import Path

import pandas as pd
import requests

# The pipeline module's filename starts with a digit (03_...), which isn't a
# legal Python identifier, so import via importlib to reuse the live join
# logic and keep the diagnostic in sync with the pipeline.
_MOD_PATH = Path(__file__).resolve().parent / "03_compute_tax_bill.py"
_spec = importlib.util.spec_from_file_location("stage03", _MOD_PATH)
stage03 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(stage03)

DEFAULT_BBLS = ["1004727501", "3002117501"]

ARCGIS_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/"
    "ArcGIS/rest/services/MAPPLUTO/FeatureServer/0/query"
)
PVAD_URL = "https://data.cityofnewyork.us/resource/8y4t-faws.json"

PLUTO_FIELDS = [
    "BBL", "Borough", "Block", "Lot", "Address", "BldgClass",
    "OwnerName", "BldgArea", "UnitsTotal", "YearBuilt",
    "CondoNo", "BoroCode",
]


def fetch_pluto_row(bbl: str) -> dict | None:
    r = requests.get(
        ARCGIS_URL,
        params={
            "where": f"bbl = {bbl}",
            "outFields": ",".join(PLUTO_FIELDS),
            "returnGeometry": "false",
            "f": "json",
        },
        timeout=30,
    )
    r.raise_for_status()
    feats = r.json().get("features", [])
    if not feats:
        return None
    # ArcGIS JSON wraps under .attributes; downstream wants .properties.
    return {"properties": feats[0]["attributes"]}


def fetch_pvad_by_condo(condo_number: str, limit: int = 200) -> list[dict]:
    where = f"condo_number='{condo_number}'"
    r = requests.get(
        PVAD_URL,
        params={
            "$select": (
                "parid,year,bldg_class,curtaxclass,curmkttot,curacttot,"
                "curactextot,curtxbtot,curtxbextot,condo_number,units"
            ),
            "$where": where,
            "$order": "parid,year",
            "$limit": str(limit),
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_pvad_by_parid(parid: str, limit: int = 20) -> list[dict]:
    r = requests.get(
        PVAD_URL,
        params={
            "$select": (
                "parid,year,bldg_class,curtaxclass,curmkttot,curacttot,"
                "curactextot,curtxbtot,curtxbextot,condo_number,units"
            ),
            "$where": f"parid like '{parid}%'",
            "$order": "year",
            "$limit": str(limit),
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def diagnose(bbl: str, pvad_limit: int) -> dict:
    """Run the trace for one BBL. Returns a dict with the verdict + details."""
    print(f"\n{'─' * 72}\nDiagnosing BBL {bbl}\n{'─' * 72}")
    out: dict = {"bbl": bbl, "verdict": None, "reason": ""}

    # 1. Fetch PLUTO row.
    pluto_row = fetch_pluto_row(bbl)
    if not pluto_row:
        out["verdict"] = "FAIL"
        out["reason"] = "PLUTO has no feature with this BBL."
        print(out["reason"])
        return out
    p = pluto_row["properties"]
    print(
        f"PLUTO: {p.get('Address')} · {p.get('BldgClass')} · "
        f"Lot={p.get('Lot')} · CondoNo={p.get('CondoNo')} · "
        f"BoroCode={p.get('BoroCode')} · BldgArea={p.get('BldgArea')}"
    )
    out["pluto"] = p

    # 2. Build the lookup from this one PLUTO feature.
    lookup = stage03.build_condo_lot_lookup([pluto_row])
    print(f"build_condo_lot_lookup → {lookup or '{}'}")
    out["lookup"] = lookup

    condono = p.get("CondoNo")
    borocode = p.get("BoroCode")
    if not condono or not borocode:
        out["verdict"] = "FAIL"
        out["reason"] = (
            "PLUTO row has no CondoNo or BoroCode — the join requires "
            "both. This polygon will never aggregate."
        )
        print(out["reason"])
        return out
    expected_key = (int(borocode), int(condono))
    if expected_key not in lookup:
        out["verdict"] = "FAIL"
        out["reason"] = (
            f"Lookup did not include {expected_key}. Check Lot / BldgArea / "
            f"BoroCode handling in build_condo_lot_lookup."
        )
        print(out["reason"])
        return out

    # 3. Pull PVAD unit rows by condo_number.
    condo_number_str = f"{int(borocode)}{int(condono):05d}"
    pvad_rows = fetch_pvad_by_condo(condo_number_str, limit=pvad_limit)
    print(f"PVAD by condo_number='{condo_number_str}': {len(pvad_rows)} rows")
    if not pvad_rows:
        out["verdict"] = "FAIL"
        out["reason"] = (
            f"PVAD has zero rows with condo_number='{condo_number_str}'. "
            "This is a public-data gap; the parcel cannot be joined until "
            "DOF backfills."
        )
        print(out["reason"])
        return out

    # 4. Build a DataFrame and run the live aggregation logic.
    df = pd.DataFrame(pvad_rows)
    # Coerce numerics like the pipeline does, then filter to curmkttot > 0
    # like stage 03 does on each raw PVAD file.
    for col in ("curmkttot", "curacttot", "curtxbtot", "curtxbextot"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["curmkttot"].notna() & (df["curmkttot"] > 0)].copy()
    df["bbl_norm"] = df["parid"].apply(stage03.normalize_bbl)
    print(
        f"  after curmkttot>0 filter: {len(df)} rows; "
        f"unique (parid, year) pairs: "
        f"{df.groupby(['parid','year']).ngroups if len(df) else 0}"
    )

    # Stage 03 hands the aggregator an unfiltered-by-year DataFrame today.
    rates = stage03.config.TAX_RATES_DEFAULT
    aggregated = stage03.aggregate_condo_units(df, lookup, rates)
    matching = aggregated[aggregated["bbl_norm"] == bbl]
    if matching.empty:
        out["verdict"] = "FAIL"
        out["reason"] = (
            "aggregate_condo_units returned no row keyed at the lot BBL. "
            "Inspect expanded_rows in stage 03."
        )
        print(out["reason"])
        return out

    row = matching.iloc[0]
    mv_current = float(row.get("_pre_aggregated_mv") or row.get("curmkttot") or 0)
    bill = float(row.get("_pre_aggregated_bill") or 0)
    units_agg = int(row.get("units_aggregated") or 0)

    # 5. Sanity-check the magnitude. Sum FY26-only curmkttot from the source
    # data to compare against the aggregator output. If the pipeline aggregate
    # is more than ~2× the FY26 reference, the year-filter bug is live.
    fy26 = df[df["year"].astype(str) == "2026"]
    fy26_dedup = (
        fy26.sort_values("curmkttot", ascending=False)
        .drop_duplicates("parid", keep="first")
    )
    fy26_mv = float(fy26_dedup["curmkttot"].sum())

    inflation = mv_current / fy26_mv if fy26_mv > 0 else float("inf")
    print(
        f"Aggregate MV: ${mv_current:>15,.0f}  ({units_agg} units rolled up)\n"
        f"FY26 baseline: ${fy26_mv:>14,.0f}  "
        f"({len(fy26_dedup)} unique parids in 2026)\n"
        f"Inflation:    {inflation:>6.2f}×  "
        f"({'OK' if 0.9 <= inflation <= 1.1 else 'BUG — aggregator sums across years/dups'})"
    )
    if 0.9 <= inflation <= 1.1:
        out["verdict"] = "JOIN_OK"
        out["reason"] = (
            f"Lot {bbl} aggregates to ${mv_current:,.0f} matching the FY26 "
            f"sum across {units_agg} unit BBLs. If the deployed tile still "
            f"flags no_pvad_match, the deployed build used stale raw inputs "
            f"(re-run build.sh after rm raw/)."
        )
    else:
        out["verdict"] = "JOIN_INFLATED"
        out["reason"] = (
            f"Lot {bbl} aggregates to ${mv_current:,.0f} but FY26 sum is "
            f"only ${fy26_mv:,.0f} ({inflation:.1f}× inflation). Year-filter "
            f"+ dedup fix in Step 2a will resolve."
        )
    print(out["reason"])
    out["mv_current"] = mv_current
    out["mv_fy26"] = fy26_mv
    out["units_aggregated"] = units_agg
    out["inflation"] = inflation
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bbls", nargs="*", default=DEFAULT_BBLS, help="10-digit BBLs")
    ap.add_argument("--pvad-limit", type=int, default=200,
                    help="Max PVAD rows per BBL (raise for huge condos).")
    args = ap.parse_args()

    results = [diagnose(bbl, args.pvad_limit) for bbl in args.bbls]

    print(f"\n{'═' * 72}\nSUMMARY\n{'═' * 72}")
    for r in results:
        print(f"  {r['bbl']}  {r['verdict']:<14}  {r['reason'][:80]}")

    # Exit non-zero if any join failed, so this can gate CI later.
    bad = [r for r in results if r["verdict"] != "JOIN_OK"]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
