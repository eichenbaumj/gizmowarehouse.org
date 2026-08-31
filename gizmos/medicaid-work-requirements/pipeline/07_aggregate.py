"""Stage 07 — roll tract-level estimates up to counties + states.

We join stage 05 (subject pool) and stage 06 (burden index) into a single
tract-level frame, then compute county and state aggregates. The state
aggregates feed the home-page headline stats and the per-state PDF briefs.

Output:
  output/tract_full.parquet    — tract-level merged frame (input to stage 08)
  output/county_summary.parquet — per-county totals + burden weighted avg
  output/state_summary.json    — JSON for the frontend headline stats
  public/data/medicaid-state-summary.json — same JSON, shipped with the SPA

Run: python 07_aggregate.py
"""

from __future__ import annotations

import json
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd

import config
from lib import acs_pop  # type: ignore

SUBJECT_IN = config.OUTPUT_DIR / "tract_subject.parquet"
BURDEN_IN = config.OUTPUT_DIR / "tract_burden.parquet"
COUNTIES_GEOJSON_IN = config.RAW_DIR / "cb_2024_counties.geojson"

TRACT_OUT = config.OUTPUT_DIR / "tract_full.parquet"
COUNTY_OUT = config.OUTPUT_DIR / "county_summary.parquet"
COUNTY_GEOJSON_OUT = config.OUTPUT_DIR / "counties_with_metrics.geojson"
STATE_JSON_OUT = config.OUTPUT_DIR / "state_summary.json"
PUBLIC_STATE_JSON = config.PUBLIC_DATA_DIR / "medicaid-state-summary.json"


def _check_inputs() -> bool:
    if not SUBJECT_IN.exists():
        print(f"ERROR: {SUBJECT_IN} missing. Run stage 05 first.", file=sys.stderr)
        return False
    if not BURDEN_IN.exists():
        print(f"ERROR: {BURDEN_IN} missing. Run stage 06 first.", file=sys.stderr)
        return False
    return True


def _weighted_avg(values: pd.Series, weights: pd.Series) -> float:
    w = weights.fillna(0).values
    v = values.fillna(0).values
    return float(np.average(v, weights=w)) if w.sum() > 0 else 0.0


def main() -> None:
    if not _check_inputs():
        sys.exit(1)

    subject = pd.read_parquet(SUBJECT_IN)
    burden = pd.read_parquet(BURDEN_IN)
    full = subject.merge(burden, on="GEOID", how="left")
    full.to_parquet(TRACT_OUT, index=False)
    print(f"Tract-level merged: {len(full):,} rows -> {TRACT_OUT.name}")

    # County aggregates
    grp_county = full.groupby(["state_fips", "county_fips"], as_index=False)
    county = grp_county.agg(
        expansion_pool=("expansion_pool_estimate", "sum"),
        expansion_pool_moe=("expansion_pool_moe", lambda s: float(np.sqrt((s.fillna(0) ** 2).sum()))),
        subject_count_strict=("subject_count_strict", "sum"),
        subject_count_permissive=("subject_count_permissive", "sum"),
        loss_exposure_strict=("loss_exposure_strict", "sum"),
        loss_exposure_permissive=("loss_exposure_permissive", "sum"),
        n_tracts=("GEOID", "count"),
    )
    # Burden index weighted by expansion pool
    burden_by_county = []
    for (sf, cf), grp in full.groupby(["state_fips", "county_fips"]):
        burden_by_county.append({
            "state_fips": sf,
            "county_fips": cf,
            "burden_index_centered": _weighted_avg(
                grp["burden_index_centered"], grp["expansion_pool_estimate"]
            ),
            "verification_difficulty": _weighted_avg(
                grp["verification_difficulty"], grp["expansion_pool_estimate"]
            ),
            "labor_volatility": _weighted_avg(
                grp["labor_volatility"], grp["expansion_pool_estimate"]
            ),
            "access_gap": _weighted_avg(grp["access_gap"], grp["expansion_pool_estimate"]),
        })
    burden_county_df = pd.DataFrame(burden_by_county)
    county = county.merge(burden_county_df, on=["state_fips", "county_fips"])
    county["GEOID"] = county["state_fips"] + county["county_fips"]
    # Attach real ACS population (B01001) so subject_rate is the share of
    # working-age (19-64) adults — what the map's "% of working-age adults"
    # legend describes. (Previously this divided by expansion_pool, which made
    # subject_rate a near-constant ≈ subject/pool ≈ 0.94 in every county.)
    pop = acs_pop.county_population()
    county = county.merge(pop, on="GEOID", how="left")
    county["total_pop"] = county["total_pop"].fillna(0.0)
    county["working_age_pop"] = county["working_age_pop"].fillna(0.0)
    county["subject_rate"] = np.where(
        county["working_age_pop"] > 0,
        county["subject_count_strict"] / county["working_age_pop"],
        0.0,
    )
    county.to_parquet(COUNTY_OUT, index=False)
    print(f"County aggregates: {len(county):,} rows -> {COUNTY_OUT.name}")

    # Write the county polygons + metrics GeoJSON for tippecanoe consumption.
    if COUNTIES_GEOJSON_IN.exists():
        counties_gdf = gpd.read_file(COUNTIES_GEOJSON_IN)
        counties_gdf["GEOID"] = counties_gdf["GEOID"].astype(str)
        joined = counties_gdf.merge(county, on="GEOID", how="left")
        joined.to_file(COUNTY_GEOJSON_OUT, driver="GeoJSON")
        print(f"County GeoJSON + metrics: {len(joined):,} rows -> {COUNTY_GEOJSON_OUT.name}")
    else:
        print(f"WARN: {COUNTIES_GEOJSON_IN} missing — skipping counties_with_metrics.geojson")

    # State aggregates + JSON for the frontend
    # Working-age (19-64) population per state, for the state-level subject_rate.
    state_wa = county.groupby("state_fips")["working_age_pop"].sum().to_dict()
    state_rows = []
    for sf, grp in full.groupby("state_fips"):
        info = config.STATE_INFO[sf]
        pool = float(grp["expansion_pool_estimate"].sum())
        subject_strict = float(grp["subject_count_strict"].sum())
        subject_perm = float(grp["subject_count_permissive"].sum())
        loss = float(grp["loss_exposure_strict"].sum())
        burden = _weighted_avg(grp["burden_index_centered"], grp["expansion_pool_estimate"])
        # Identify top-3 counties by subject_count_strict
        top_counties = (
            county[county["state_fips"] == sf]
            .sort_values("subject_count_strict", ascending=False)
            .head(3)
        )
        wv = config.waiver_meta(sf)
        state_rows.append({
            "state_fips": sf,
            "state_abbr": info["abbr"],
            "state_name": info["name"],
            "expansion": info["expansion"],
            "partial_expansion": bool(info.get("partial_expansion")),
            # Subject via a sized 1115-waiver slice (WI, GA) — shaded as in-scope.
            "subject_via_waiver": bool(wv.get("control_total", 0) > 0),
            # Named on CMS's June-2026 subject list at all (WI, GA, TN).
            "waiver_listed": bool(wv),
            # False for TN (listed but not publicly quantified); True elsewhere.
            "loss_quantified": bool(wv.get("loss_quantified", True)),
            # GA Pathways enrollees are already work-conditional → no net-new loss.
            "already_work_conditional": bool(wv.get("already_work_conditional", False)),
            "waiver_note": wv.get("label"),
            "hardship_exception_status": info["hardship_exception_status"],
            "early_implementer": info.get("early_implementer"),
            "expansion_pool": pool,
            "subject_count_strict": subject_strict,
            "subject_count_permissive": subject_perm,
            "loss_exposure_strict": loss,
            "burden_index_centered": burden,
            "subject_rate": (subject_strict / state_wa[sf]) if state_wa.get(sf, 0) > 0 else 0.0,
            "top_counties": [
                {
                    "county_fips": r.county_fips,
                    "GEOID": r.GEOID,
                    "subject_count_strict": float(r.subject_count_strict),
                }
                for _, r in top_counties.iterrows()
            ],
        })

    # Sort by subject count desc for the headline
    state_rows.sort(key=lambda r: r["subject_count_strict"], reverse=True)

    # National total
    national_strict = sum(r["subject_count_strict"] for r in state_rows)
    national_perm = sum(r["subject_count_permissive"] for r in state_rows)
    national_loss = sum(r["loss_exposure_strict"] for r in state_rows)

    summary = {
        "version": "v2-2026-06-03",
        "vintage": {
            "acs": f"5-Year {config.ACS_VINTAGE}",
            "bls_laus": config.BLS_LAUS_VINTAGE,
            "obbba_section": "71119 (§1902(xx))",
            "effective_date": "2026-12-31",
        },
        "national": {
            "subject_count_strict": national_strict,
            "subject_count_permissive": national_perm,
            "loss_exposure_strict": national_loss,
            "cbo_subject_target": config.CROSS_VALIDATION_TARGETS["cbo_national_subject_2027"],
            "cbo_loss_target_2034": config.CROSS_VALIDATION_TARGETS["cbo_national_loss_2034"],
            "urban_loss_2028_high_mitigation": config.CROSS_VALIDATION_TARGETS["urban_national_loss_2028_high_mitigation"],
            "urban_loss_2028_low_mitigation": config.CROSS_VALIDATION_TARGETS["urban_national_loss_2028_low_mitigation"],
        },
        "states": state_rows,
    }

    STATE_JSON_OUT.write_text(json.dumps(summary, indent=2, default=str))
    PUBLIC_STATE_JSON.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nNational subject (strict): {national_strict:,.0f}")
    print(f"National loss exposure:     {national_loss:,.0f}")
    print(f"\n-> {STATE_JSON_OUT.relative_to(config.PIPELINE_DIR)}")
    print(f"-> {PUBLIC_STATE_JSON.relative_to(config.REPO_ROOT)} (shipped with SPA)")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 07 done in {time.time() - t0:.1f}s")
