"""Stage 07c — build the shipped county GeoJSON for the web map + PDF briefs.

`public/data/medicaid-counties.geojson` is what the live county choropleth
renders (config `countiesGeoJsonUrl`) and what `lib/write_csv.py` +
`lib/state_brief_context.py` read for the downloadable per-state CSVs and the
PDF briefs. It was originally SEEDED by
`tools/bake-placeholder-counties-and-hexes.py`, which apportioned each state's
subject total to its counties by a (working-age x poverty) heuristic and used a
flat working-age share — i.e. placeholder county numbers that were never
replaced by the real tract-level model in `county_summary.parquet`. That's why
the map showed e.g. Wayne County, MI at ~181k subjects when the real model says
~107k.

This stage overwrites the model + population columns with the real per-county
values from stage 07 (`county_summary.parquet`, which now carries an ACS-based
`subject_rate` and `working_age_pop`), while preserving the scaffold's stable
geometry and display fields (county_name, county_short, pov_pct). The result is
that the map, the CSVs, and the briefs all reflect the real model.

Run after stage 07:  python 07c_build_public_counties.py
"""
from __future__ import annotations

import json
import sys
import time

import geopandas as gpd
import pandas as pd

import config

PUBLIC_GEOJSON = config.PUBLIC_DATA_DIR / "medicaid-counties.geojson"
COUNTY_SUMMARY = config.OUTPUT_DIR / "county_summary.parquet"
LOSS_BREAKDOWN = config.PUBLIC_DATA_DIR / "medicaid-loss-breakdown.json"
STATE_SUMMARY = config.PUBLIC_DATA_DIR / "medicaid-state-summary.json"

# Columns refreshed from the real county model (everything else in the scaffold
# — geometry, county_name, county_short, pov_pct — is geographic/ACS-stable and
# kept as-is).
MODEL_COLS = [
    "subject_count_strict",
    "subject_count_permissive",
    "loss_exposure_strict",
    "burden_index_centered",
    "subject_rate",
    "total_pop",
    "working_age_pop",
]


def main() -> None:
    if not PUBLIC_GEOJSON.exists():
        print(f"ERROR: {PUBLIC_GEOJSON} missing (scaffold).", file=sys.stderr)
        sys.exit(1)
    if not COUNTY_SUMMARY.exists():
        print(f"ERROR: {COUNTY_SUMMARY} missing. Run stage 07 first.", file=sys.stderr)
        sys.exit(1)

    scaffold = gpd.read_file(PUBLIC_GEOJSON)
    scaffold["GEOID"] = scaffold["GEOID"].astype(str).str.zfill(5)

    cs = pd.read_parquet(COUNTY_SUMMARY)
    cs["GEOID"] = cs["GEOID"].astype(str).str.zfill(5)
    cs = cs[["GEOID"] + MODEL_COLS]

    # Drop the stale model columns from the scaffold, keep geometry + display
    # fields, merge in the real model.
    base = scaffold.drop(columns=[c for c in MODEL_COLS if c in scaffold.columns])
    out = base.merge(cs, on="GEOID", how="left")

    # State identity from config (robust to scaffold drift).
    out["state_fips"] = out["GEOID"].str[:2]
    out["state_abbr"] = out["state_fips"].map(
        lambda f: config.STATE_INFO.get(f, {}).get("abbr", "")
    )
    out["expansion"] = out["state_fips"].map(
        lambda f: bool(config.STATE_INFO.get(f, {}).get("expansion", False))
    )
    # Subject via a sized 1115-waiver slice (WI, GA): in-scope but not expansion.
    out["subject_via_waiver"] = out["state_fips"].map(
        lambda f: bool(config.waiver_meta(f).get("control_total", 0) > 0)
    )
    # Named on CMS's June-2026 subject list at all (WI, GA, TN) + whether the
    # affected population is quantifiable (False for TN). Drives the map's
    # distinct "subject, not quantified" treatment for Tennessee.
    out["waiver_listed"] = out["state_fips"].map(
        lambda f: bool(config.waiver_meta(f))
    )
    out["loss_quantified"] = out["state_fips"].map(
        lambda f: bool(config.waiver_meta(f).get("loss_quantified", True))
    )

    # Counties absent from the model (none expected for CONUS) -> 0, not NaN.
    for c in MODEL_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    # --- Projected coverage loss = the bottom-up model, apportioned to counties.
    # The map's "Projected coverage loss" layer renders loss_exposure_strict. We
    # overwrite it with each state's bottom-up total_loss (stage 07b's
    # loss-breakdown.json) apportioned across its counties by subject share, so
    # the map, the Sankey, the briefs, and the headline all show ONE loss number
    # per place (national ~5.42M, not the CBO-uniform 5.2M proxy). CBO's 5.2M
    # stays the cited external benchmark in the copy.
    lb = json.loads(LOSS_BREAKDOWN.read_text())
    state_loss = {f: float(v.get("total_loss_2034", 0.0)) for f, v in lb.get("states", {}).items()}
    state_subj = out.groupby("state_fips")["subject_count_strict"].sum().to_dict()

    def _apportion(r):
        sl = state_loss.get(r["state_fips"], 0.0)
        ss = state_subj.get(r["state_fips"], 0.0)
        return (r["subject_count_strict"] / ss * sl) if ss > 0 and sl > 0 else 0.0

    out["loss_exposure_strict"] = out.apply(_apportion, axis=1)

    # Non-expansion overlay proxy (the would-be-affected working-age uninsured if
    # the state had expanded). Suppressed for expansion states AND for
    # subject-via-waiver states (WI/GA), which now carry real subject numbers and
    # shouldn't double up with the uninsured proxy.
    out["uninsured_below_138pct"] = (out["working_age_pop"] * 0.18).where(
        ~(out["expansion"] | out["subject_via_waiver"]), 0.0
    )

    for c in (
        "total_pop",
        "working_age_pop",
        "subject_count_strict",
        "subject_count_permissive",
        "loss_exposure_strict",
        "uninsured_below_138pct",
    ):
        out[c] = out[c].round().astype(int)
    out["subject_rate"] = out["subject_rate"].round(4)
    out["burden_index_centered"] = out["burden_index_centered"].round(1)
    if "pov_pct" in out.columns:
        out["pov_pct"] = pd.to_numeric(out["pov_pct"], errors="coerce").round(1)

    out.to_file(PUBLIC_GEOJSON, driver="GeoJSON")

    # Patch the shipped state-summary so the map's national + per-state loss
    # headline reads the same bottom-up totals (national 5.42M, not 5.2M).
    summ = json.loads(STATE_SUMMARY.read_text())
    summ["national"]["loss_exposure_strict"] = float(lb["_national"]["total_loss_2034"])
    for s in summ.get("states", []):
        s["loss_exposure_strict"] = state_loss.get(s.get("state_fips"), 0.0)
    STATE_SUMMARY.write_text(json.dumps(summ, indent=2))
    print(f"-> patched {STATE_SUMMARY.name}: national loss = {summ['national']['loss_exposure_strict']:,.0f}")

    # Propagate the same bottom-up loss into county_summary.parquet so the
    # stage-11 analyst CSVs carry the same per-county loss as the map + briefs.
    cs_full = pd.read_parquet(COUNTY_SUMMARY)
    cs_full["GEOID"] = cs_full["GEOID"].astype(str).str.zfill(5)
    cs_full["_sf"] = cs_full["GEOID"].str[:2]
    cs_subj = cs_full.groupby("_sf")["subject_count_strict"].sum().to_dict()

    def _ap2(r):
        sl = state_loss.get(r["_sf"], 0.0)
        ss = cs_subj.get(r["_sf"], 0.0)
        return (r["subject_count_strict"] / ss * sl) if ss > 0 and sl > 0 else 0.0

    cs_full["loss_exposure_strict"] = cs_full.apply(_ap2, axis=1)
    cs_full = cs_full.drop(columns=["_sf"])
    cs_full.to_parquet(COUNTY_SUMMARY, index=False)
    print(f"-> patched {COUNTY_SUMMARY.name}: national loss = {cs_full['loss_exposure_strict'].sum():,.0f}")

    # ---- verification print -------------------------------------------------
    print(f"-> {PUBLIC_GEOJSON.relative_to(config.REPO_ROOT)}: {len(out):,} counties")
    print(f"   national subject_count_strict = {int(out['subject_count_strict'].sum()):,}")
    sr = out["subject_rate"]
    print(
        f"   subject_rate: min={sr.min():.3f} max={sr.max():.3f} "
        f"mean={sr.mean():.3f} nunique={sr.nunique()}"
    )
    top = out.nlargest(5, "subject_rate")[["GEOID", "county_name", "subject_rate"]]
    print("   highest subject_rate counties:")
    for _, r in top.iterrows():
        print(f"     {r['county_name']} ({r['GEOID']}): {r['subject_rate']:.3f}")
    for gid, lbl in [("06037", "LA"), ("26163", "Wayne"), ("42101", "Philadelphia")]:
        r = out[out["GEOID"] == gid]
        if len(r):
            rr = r.iloc[0]
            print(
                f"   {lbl} {gid}: subject={int(rr['subject_count_strict']):,} "
                f"rate={rr['subject_rate']:.3f} wa={int(rr['working_age_pop']):,}"
            )


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"Stage 07c done in {time.time() - t0:.1f}s")
