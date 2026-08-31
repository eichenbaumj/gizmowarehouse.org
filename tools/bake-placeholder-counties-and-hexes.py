#!/usr/bin/env python3
"""Borrow NPE's cached geometry + synthesize realistic Medicaid placeholder values.

Produces:
  public/data/medicaid-counties.geojson    — 3,109 counties, ~3.5 MB
  public/data/medicaid-hex-5mi.geojson     — 74,872 hexes, ~40 MB
  public/data/medicaid-state-summary.json  — extended with all 41 expansion states

Apportionment math:
  - State totals: 11 named states have anchored values from medicaid-state-summary.json.
    For remaining 30 expansion states, synthesize values so total ≈ 18.5M (CBO).
    Working-age population is the apportionment key, with a small poverty-rate
    multiplier so high-poverty states get slightly more.
  - Within each state, counties are weighted by (county_pop × county_pov_pct).
    This produces realistic concentration: Cook County, Wayne County, LA County
    get dark cobalt; rural counties get pale fills.
  - 5-mile hexes inherit their parent county's subject_rate and burden_index.
    Count = hex_total_pop × working_age_share × subject_rate.

Non-expansion states get zero values for the expansion-pathway pool. A parallel
'uninsured_below_138pct' field carries the would-be-affected population for the
secondary overlay shown to those states.

This is a v0 PLACEHOLDER until the real pipeline (stage 07) runs end-to-end with
ACS B27003 + B18135 + state T-MSIS calibration. See METHODOLOGY.md.
"""
from __future__ import annotations

import json
import math
import os
import sys
import random
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
_npe_dir = os.environ.get("NPE_DIR")
if not _npe_dir:
    sys.exit("NPE_DIR not set — point it at the off-repo geometry cache (pipeline outputs with grid/places layers).")
NPE = Path(_npe_dir)
NPE_COUNTIES = NPE / "public/data/county_poverty.geojson"
NPE_HEX5 = NPE / "public/data/hex_5mi.geojson"
NPE_TRACT_CSV = NPE / "pipeline/output/acs_tract_data.csv"
NPE_PLACES = NPE / "pipeline/output/places_national.geojson"
STATE_SUMMARY_PATH = REPO / "public/data/medicaid-state-summary.json"
COUNTIES_OUT = REPO / "public/data/medicaid-counties.geojson"
HEXES_OUT = REPO / "public/data/medicaid-hex-5mi.geojson"

# Working-age (19-64) share of total population. Roughly stable nationally ~0.6.
WORKING_AGE_SHARE = 0.60

# 10 non-expansion state FIPS
NON_EXPANSION_FIPS = {"01", "12", "13", "20", "28", "45", "47", "48", "55", "56"}

# CBO national target (subject_count_strict)
NATIONAL_SUBJECT_TARGET = 18_500_000

# Loss exposure ratio (CBO: 5.2M loss out of 18.5M subject ≈ 28% admin churn)
NATIONAL_LOSS_RATE = 5_200_000 / 18_500_000

# State FIPS → 2-letter abbr (the 41 expansion + DC entities)
STATE_ABBR = {
    "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "21": "KY", "22": "LA", "23": "ME", "24": "MD", "25": "MA",
    "26": "MI", "27": "MN", "29": "MO", "30": "MT", "31": "NE", "32": "NV",
    "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "46": "SD",
    "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
}
# Non-expansion (zero subject_count via expansion pathway but show in map)
NON_EXP_ABBR = {
    "01": "AL", "12": "FL", "13": "GA", "20": "KS", "28": "MS",
    "45": "SC", "47": "TN", "48": "TX", "55": "WI", "56": "WY",
}
ALL_STATE_INFO = {**STATE_ABBR, **NON_EXP_ABBR}


def _load_county_names() -> pd.DataFrame:
    """Fetch cb_2024 US county shapefile + extract GEOID → NAMELSAD lookup.

    Cached locally at /tmp/cb_2024_us_county_500k for subsequent runs.
    """
    import io, tempfile, zipfile
    import requests
    cache = Path("/tmp/cb_2024_us_county_500k.csv")
    if cache.exists():
        return pd.read_csv(cache, dtype={"GEOID": str})

    url = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip"
    print(f"  fetching county names from {url}...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            zf.extractall(td)
        shp = next(Path(td).glob("*.shp"))
        gdf = gpd.read_file(shp)
    gdf["GEOID"] = gdf["GEOID"].astype(str).str.zfill(5)
    df = gdf[["GEOID", "NAME", "NAMELSAD"]].copy()
    df.to_csv(cache, index=False)
    print(f"  cached {len(df)} county names → {cache}")
    return df


def load_inputs():
    print(f"Loading {NPE_COUNTIES.name}...")
    counties = gpd.read_file(NPE_COUNTIES)
    counties["GEOID"] = counties["GEOID"].astype(str).str.zfill(5)
    counties["state_fips"] = counties["GEOID"].str[:2]
    print(f"  {len(counties)} counties")

    print("Loading county names (cb_2024 NAMELSAD)...")
    name_df = _load_county_names()
    counties = counties.merge(name_df, on="GEOID", how="left")
    counties["county_name"] = counties["NAMELSAD"].fillna(counties["GEOID"])
    counties["county_short"] = counties["NAME"].fillna(counties["GEOID"])
    counties = counties.drop(columns=["NAME", "NAMELSAD"], errors="ignore")
    n_named = (counties["county_name"] != counties["GEOID"]).sum()
    print(f"  named {n_named} of {len(counties)} counties")

    print(f"Loading {NPE_TRACT_CSV.name} for population data...")
    tracts = pd.read_csv(NPE_TRACT_CSV, dtype={"state": str, "county": str, "GEOID": str})
    tracts["GEOID"] = tracts["GEOID"].str.zfill(11)
    tracts["county_geoid"] = tracts["GEOID"].str[:5]
    county_pop = (
        tracts.groupby("county_geoid")["total_population"].sum().reset_index()
        .rename(columns={"county_geoid": "GEOID", "total_population": "total_pop"})
    )
    counties = counties.merge(county_pop, on="GEOID", how="left")
    counties["total_pop"] = counties["total_pop"].fillna(0)
    counties["working_age_pop"] = counties["total_pop"] * WORKING_AGE_SHARE
    print(f"  attached population to {(counties['total_pop'] > 0).sum()} counties")

    print(f"Loading {STATE_SUMMARY_PATH.name}...")
    with STATE_SUMMARY_PATH.open() as f:
        summary = json.load(f)
    return counties, summary


def compute_state_anchors(counties: gpd.GeoDataFrame, summary: dict) -> dict:
    """Build per-state subject_count target for all 41 expansion states + DC.

    Use anchored values from medicaid-state-summary.json where present; synthesize
    remaining states by apportioning the residual to fill CBO's ~18.5M total,
    weighted by working-age pop × poverty rate.
    """
    anchored = {row["state_fips"]: row for row in summary["states"]}
    state_anchors: dict[str, dict] = {}

    # Compute state-level working-age × poverty-weighted "burden mass".
    # AK and HI are CONUS-excluded by NPE's data → 0 mass; we'll patch their values
    # below with a population-based fallback so they don't render as empty.
    state_burden = {}
    for state_fips in STATE_ABBR.keys():
        mask = counties["state_fips"] == state_fips
        if mask.sum() == 0:
            state_burden[state_fips] = 0.0
            continue
        wa = counties.loc[mask, "working_age_pop"].sum()
        pov = counties.loc[mask, "pov_pct"].fillna(15).mean()
        state_burden[state_fips] = float(wa) * (float(pov) / 100.0)

    # Subtract anchored states from national target
    anchored_total = sum(
        anchored[f]["subject_count_strict"] for f in anchored if f in STATE_ABBR
    )
    residual = max(0, NATIONAL_SUBJECT_TARGET - anchored_total)
    residual_burden = sum(
        state_burden[f] for f in STATE_ABBR if f not in anchored or anchored[f]["subject_count_strict"] == 0
    )

    print(f"  anchored states sum to {anchored_total:,}; "
          f"residual {residual:,} distributed across remaining expansion states "
          f"(residual_burden mass = {residual_burden:,.0f})")

    rng = random.Random(42)  # deterministic
    for state_fips in STATE_ABBR.keys():
        anc = anchored.get(state_fips)
        if anc and anc["subject_count_strict"] > 0:
            subject = anc["subject_count_strict"]
            subject_perm = anc.get("subject_count_permissive", subject * 0.85)
            burden = anc.get("burden_index_centered", 0.0)
        else:
            share = state_burden[state_fips] / residual_burden if residual_burden > 0 else 0
            subject = residual * share
            subject_perm = subject * 0.85
            burden = rng.uniform(-12, 12)
        loss = subject * NATIONAL_LOSS_RATE
        state_anchors[state_fips] = {
            "subject_count_strict": subject,
            "subject_count_permissive": subject_perm,
            "loss_exposure_strict": loss,
            "burden_index_centered": burden,
        }

    # Non-expansion states: zero values for the expansion pathway
    for state_fips in NON_EXP_ABBR.keys():
        state_anchors[state_fips] = {
            "subject_count_strict": 0,
            "subject_count_permissive": 0,
            "loss_exposure_strict": 0,
            "burden_index_centered": 0,
        }

    return state_anchors


def apportion_to_counties(counties: gpd.GeoDataFrame, anchors: dict) -> gpd.GeoDataFrame:
    """Distribute each state's subject_count to its counties by (pop × pov_pct)."""
    df = counties.copy()
    df["pov_pct"] = df["pov_pct"].fillna(15).astype(float)
    df["county_burden_mass"] = df["working_age_pop"] * (df["pov_pct"] / 100.0)

    # Compute state burden mass for normalization
    state_mass = df.groupby("state_fips")["county_burden_mass"].sum().to_dict()
    df["state_mass"] = df["state_fips"].map(state_mass).fillna(1)
    df["county_share"] = df["county_burden_mass"] / df["state_mass"].replace(0, 1)

    # Apportion each metric
    rng = random.Random(42)
    for metric in ("subject_count_strict", "subject_count_permissive", "loss_exposure_strict"):
        df[metric] = df.apply(
            lambda r: anchors.get(r["state_fips"], {}).get(metric, 0) * r["county_share"],
            axis=1,
        )

    # Burden index: state avg + per-county noise (high-poverty counties have higher burden)
    state_burden_avg = {fips: a["burden_index_centered"] for fips, a in anchors.items()}
    df["burden_index_centered"] = df.apply(
        lambda r: state_burden_avg.get(r["state_fips"], 0)
        + (r["pov_pct"] - 15) * 0.5
        + rng.uniform(-3, 3),
        axis=1,
    )

    # Compute subject_rate as subject / working-age pop
    df["subject_rate"] = df.apply(
        lambda r: (r["subject_count_strict"] / r["working_age_pop"])
        if r["working_age_pop"] > 0 else 0,
        axis=1,
    )
    # Floor very small rates so the ramp doesn't render them as zero
    df["subject_rate"] = df["subject_rate"].clip(lower=0, upper=0.40)

    # Tag expansion flag
    df["expansion"] = ~df["state_fips"].isin(NON_EXPANSION_FIPS)
    df["state_abbr"] = df["state_fips"].map(ALL_STATE_INFO)

    # For non-expansion states, set 'uninsured_below_138pct' as a placeholder
    # (proxy = working_age_pop * 0.18) to be shown on the secondary overlay
    df["uninsured_below_138pct"] = df.apply(
        lambda r: r["working_age_pop"] * 0.18 if not r["expansion"] else 0,
        axis=1,
    )

    keep = [
        "GEOID", "state_fips", "state_abbr",
        "county_name", "county_short",
        "total_pop", "working_age_pop",
        "pov_pct", "expansion",
        "subject_count_strict", "subject_count_permissive",
        "loss_exposure_strict", "subject_rate", "burden_index_centered",
        "uninsured_below_138pct", "geometry",
    ]
    out = df[keep].copy()
    # Round numerics for compactness
    for c in ("total_pop", "working_age_pop", "subject_count_strict",
              "subject_count_permissive", "loss_exposure_strict",
              "uninsured_below_138pct"):
        out[c] = out[c].round().astype(int)
    out["pov_pct"] = out["pov_pct"].round(1)
    out["subject_rate"] = out["subject_rate"].round(4)
    out["burden_index_centered"] = out["burden_index_centered"].round(1)
    return out


def apportion_to_hexes(counties_out: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """For each 5-mile hex, assign its parent county via centroid spatial join."""
    print(f"Loading {NPE_HEX5.name}...")
    hex5 = gpd.read_file(NPE_HEX5)
    print(f"  {len(hex5):,} hexes")

    # Spatial join: hex centroid → county
    print("Spatial-joining hex centroids to counties...")
    centroids = hex5.copy()
    centroids["geometry"] = hex5.geometry.centroid
    joined = gpd.sjoin(
        centroids[["coarse_id", "total_pop", "total_pov_pct", "geometry"]],
        counties_out[["GEOID", "subject_rate", "burden_index_centered",
                      "expansion", "state_fips", "state_abbr",
                      "county_name", "county_short", "geometry"]],
        how="left", predicate="within",
    )
    joined["parent_county_name"] = joined["county_short"].fillna("")
    joined["parent_state_abbr"] = joined["state_abbr"].fillna("")

    # Nearest census place per hex centroid — gives popups a human name
    # like "near Bloomington, IL" instead of "in McLean County, IL."
    print("  joining nearest place to each hex centroid...")
    places = gpd.read_file(NPE_PLACES)[["NAME", "STUSPS", "geometry"]]
    places = places.rename(columns={"NAME": "nearest_place_name",
                                    "STUSPS": "nearest_place_state"})
    # Use sjoin_nearest for efficient nearest-place lookup on 74k hexes
    centroid_pts = gpd.GeoDataFrame(
        joined[["coarse_id"]].copy(),
        geometry=joined.geometry,
        crs=joined.crs,
    )
    nearest = gpd.sjoin_nearest(
        centroid_pts.to_crs(places.crs),
        places[["nearest_place_name", "nearest_place_state", "geometry"]],
        how="left",
        max_distance=None,
    )
    nearest = nearest.drop_duplicates(subset=["coarse_id"])
    joined = joined.merge(
        nearest[["coarse_id", "nearest_place_name", "nearest_place_state"]],
        on="coarse_id",
        how="left",
    )
    joined["nearest_place_name"] = joined["nearest_place_name"].fillna("")
    joined["nearest_place_state"] = joined["nearest_place_state"].fillna("")
    # Drop duplicates if a hex centroid is on a boundary
    joined = joined.drop_duplicates(subset=["coarse_id"])

    # Within-county hex apportionment weighted by (hex_pop × hex_pov_pct).
    # This is the "scale through precision" move: a 5-mile hex in a wealthy
    # suburb (low pov_pct) gets a lower share of the county's subject pool
    # than an equally-populous hex in a high-poverty neighborhood. Preserves
    # the county-level total — sum(hex_subject) across all hexes in a county
    # equals the county's total subject_count.
    joined["total_pop"] = joined["total_pop"].fillna(0)
    joined["total_pov_pct"] = joined["total_pov_pct"].fillna(0)
    joined["hex_weight"] = joined["total_pop"] * joined["total_pov_pct"].clip(lower=0.1)

    # Sum weights per county, then derive hex share = weight / sum_for_county.
    # We need each county's TOTAL subject_count to allocate across its hexes.
    county_totals = counties_out.set_index("GEOID")[
        ["subject_count_strict", "loss_exposure_strict"]
    ]
    sum_w = joined.groupby("GEOID")["hex_weight"].transform("sum").replace(0, 1.0)
    joined["share_of_county"] = joined["hex_weight"] / sum_w

    joined["subject_count_strict"] = (
        (joined["GEOID"].map(county_totals["subject_count_strict"]).fillna(0)
         * joined["share_of_county"]).fillna(0).round().astype(int)
    )
    joined["loss_exposure_strict"] = (
        (joined["GEOID"].map(county_totals["loss_exposure_strict"]).fillna(0)
         * joined["share_of_county"]).fillna(0).round().astype(int)
    )

    # Hex-level subject_rate = subject_count / hex_working_age_pop (recomputed
    # to reflect within-county variation, no longer just the county rate).
    hex_working_age = joined["total_pop"] * WORKING_AGE_SHARE
    joined["subject_rate"] = (
        joined["subject_count_strict"] / hex_working_age.replace(0, 1.0)
    ).clip(lower=0, upper=0.5).round(4)
    joined["burden_index_centered"] = joined["burden_index_centered"].fillna(0).round(1)
    joined["expansion"] = joined["expansion"].fillna(False).astype(bool)

    # Merge geometry back from hex5 (centroids in joined are points)
    hex5_lookup = hex5[["coarse_id", "geometry"]].set_index("coarse_id")
    joined = joined.set_index("coarse_id")
    joined["geometry"] = hex5_lookup["geometry"]
    joined = joined.reset_index()

    # Drop centroid-only columns, keep meaningful ones
    out = gpd.GeoDataFrame(
        joined[[
            "coarse_id", "GEOID", "state_fips", "state_abbr", "expansion",
            "parent_county_name", "parent_state_abbr",
            "nearest_place_name", "nearest_place_state",
            "total_pop", "subject_count_strict", "loss_exposure_strict",
            "subject_rate", "burden_index_centered", "geometry",
        ]].rename(columns={"GEOID": "county_geoid"}),
        geometry="geometry",
        crs=hex5.crs,
    )
    out["total_pop"] = out["total_pop"].fillna(0).round().astype(int)
    return out


def write_state_summary(counties_out: gpd.GeoDataFrame, hexes_out: gpd.GeoDataFrame, anchors: dict):
    """Rewrite medicaid-state-summary.json with all 51 states + concentration math."""
    # Sort top counties per state
    by_state = {}
    for state_fips, anchor in anchors.items():
        info = {
            "state_fips": state_fips,
            "state_abbr": ALL_STATE_INFO[state_fips],
            "state_name": STATE_NAMES.get(state_fips, ALL_STATE_INFO[state_fips]),
            "expansion": state_fips not in NON_EXPANSION_FIPS,
            "partial_expansion": state_fips == "13",
            "hardship_exception_status":
                "non_expansion" if state_fips in NON_EXPANSION_FIPS
                else "adopting" if state_fips not in NOT_ADOPTING_HARDSHIP
                else "not_adopting",
            "subject_count_strict": int(round(anchor["subject_count_strict"])),
            "subject_count_permissive": int(round(anchor["subject_count_permissive"])),
            "loss_exposure_strict": int(round(anchor["loss_exposure_strict"])),
            "burden_index_centered": round(anchor["burden_index_centered"], 1),
        }
        state_pop = counties_out.loc[
            counties_out["state_fips"] == state_fips, "working_age_pop"
        ].sum()
        info["subject_rate"] = (
            anchor["subject_count_strict"] / state_pop if state_pop > 0 else 0
        )
        info["subject_rate"] = round(info["subject_rate"], 4)
        # Top 5 counties
        sc = counties_out[counties_out["state_fips"] == state_fips]
        top = sc.sort_values("subject_count_strict", ascending=False).head(5)
        info["top_counties"] = [
            {"county_fips": r["GEOID"][2:], "GEOID": r["GEOID"],
             "subject_count_strict": int(r["subject_count_strict"])}
            for _, r in top.iterrows()
        ]
        by_state[state_fips] = info

    # Sort by subject_count desc for the headline
    states_sorted = sorted(by_state.values(), key=lambda s: s["subject_count_strict"], reverse=True)

    # Concentration math: share in top N counties (only expansion states)
    exp_counties = counties_out[counties_out["expansion"]].copy()
    exp_counties = exp_counties.sort_values("subject_count_strict", ascending=False)
    total_subject = exp_counties["subject_count_strict"].sum()
    share_in_top_n = {}
    for n in [5, 10, 25, 50, 100, 250, 500]:
        if len(exp_counties) >= n:
            share = exp_counties.head(n)["subject_count_strict"].sum() / total_subject
            share_in_top_n[str(n)] = round(share, 4)

    # Percentile cutoffs per (mode × primitive) — used by the frontend's
    # threshold slider to translate "Highlight top X%" into an absolute cutoff
    # value for the binary-reveal opacity expression. We compute over the
    # population of features that actually carry positive values (expansion
    # counties; hex cells inheriting expansion-state rate).
    def _pcts(series, props):
        s = series[series > 0]
        if len(s) == 0:
            return {p: 0 for p in props}
        return {p: float(s.quantile(p / 100)) for p in props}

    PCTS = [50, 67, 75, 80, 85, 90, 95, 97, 99]
    exp_hex = hexes_out[hexes_out["expansion"]].copy() if "expansion" in hexes_out.columns else hexes_out.copy()
    pct_cutoffs = {
        "subject_count": {
            "counties": _pcts(exp_counties["subject_count_strict"], PCTS),
            "hex5mi": _pcts(exp_hex["subject_count_strict"], PCTS),
        },
        "subject_rate": {
            "counties": _pcts(exp_counties["subject_rate"], PCTS),
            "hex5mi": _pcts(exp_hex["subject_rate"], PCTS),
        },
        "burden_index": {
            "counties": _pcts(exp_counties["burden_index_centered"], PCTS),
            "hex5mi": _pcts(exp_hex["burden_index_centered"], PCTS),
        },
        "loss_exposure": {
            "counties": _pcts(exp_counties["loss_exposure_strict"], PCTS),
            "hex5mi": _pcts(exp_hex["loss_exposure_strict"], PCTS),
        },
    }

    summary = {
        "version": "v0.3-placeholder-2026-05-22",
        "note": ("Placeholder data borrowing geometry from National Poverty Explorer. "
                 "State totals anchored to CBO national 18.5M (subject) + 5.2M (loss). "
                 "Within-state apportionment by (county_pop × poverty_rate). "
                 "Replace with real pipeline output (stage 07) before public release."),
        "vintage": {
            "acs": "5-Year 2024 (geometry from NPE)",
            "bls_laus": "Feb 2025 - Jan 2026 (placeholder)",
            "obbba_section": "71119 (§1902(xx))",
            "effective_date": "2026-12-31",
        },
        "national": {
            "subject_count_strict": int(round(total_subject)),
            "subject_count_permissive": int(round(total_subject * 0.85)),
            "loss_exposure_strict": int(round(total_subject * NATIONAL_LOSS_RATE)),
            "cbo_subject_target": NATIONAL_SUBJECT_TARGET,
            "cbo_loss_target_2034": 5_200_000,
            "urban_loss_2028_high_mitigation": 4_900_000,
            "urban_loss_2028_low_mitigation": 10_100_000,
        },
        "concentration": {
            "share_in_top_n_counties": share_in_top_n,
            "p90_county_subject_count": int(round(exp_counties["subject_count_strict"].quantile(0.90))),
            "p95_county_subject_count": int(round(exp_counties["subject_count_strict"].quantile(0.95))),
            "p99_county_subject_count": int(round(exp_counties["subject_count_strict"].quantile(0.99))),
        },
        "percentile_cutoffs": pct_cutoffs,
        "states": states_sorted,
    }
    STATE_SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
    print(f"-> {STATE_SUMMARY_PATH.relative_to(REPO)}")


# State name lookup
STATE_NAMES = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida", "13": "Georgia",
    "15": "Hawaii", "16": "Idaho", "17": "Illinois", "18": "Indiana",
    "19": "Iowa", "20": "Kansas", "21": "Kentucky", "22": "Louisiana",
    "23": "Maine", "24": "Maryland", "25": "Massachusetts", "26": "Michigan",
    "27": "Minnesota", "28": "Mississippi", "29": "Missouri", "30": "Montana",
    "31": "Nebraska", "32": "Nevada", "33": "New Hampshire", "34": "New Jersey",
    "35": "New Mexico", "36": "New York", "37": "North Carolina", "38": "North Dakota",
    "39": "Ohio", "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania",
    "44": "Rhode Island", "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah", "50": "Vermont",
    "51": "Virginia", "53": "Washington", "54": "West Virginia",
    "55": "Wisconsin", "56": "Wyoming",
}
NOT_ADOPTING_HARDSHIP = {"18", "19", "29", "40"}  # IN, IA, MO, OK


def main():
    counties_in, summary = load_inputs()
    anchors = compute_state_anchors(counties_in, summary)
    counties_out = apportion_to_counties(counties_in, anchors)
    counties_out.to_file(COUNTIES_OUT, driver="GeoJSON")
    size_mb = COUNTIES_OUT.stat().st_size / 1e6
    print(f"\n-> {COUNTIES_OUT.relative_to(REPO)} "
          f"({len(counties_out)} counties, {size_mb:.2f} MB)")

    hexes_out = apportion_to_hexes(counties_out)
    hexes_out.to_file(HEXES_OUT, driver="GeoJSON")
    size_mb = HEXES_OUT.stat().st_size / 1e6
    print(f"\n-> {HEXES_OUT.relative_to(REPO)} "
          f"({len(hexes_out)} hexes, {size_mb:.2f} MB)")

    write_state_summary(counties_out, hexes_out, anchors)

    print("\n--- Summary of placeholder data ---")
    print(f"National subject (sum of county estimates): "
          f"{counties_out['subject_count_strict'].sum():,}")
    print(f"Target (CBO):                                {NATIONAL_SUBJECT_TARGET:,}")
    print(f"Top 5 counties by subject_count:")
    top5 = counties_out.nlargest(5, "subject_count_strict")
    for _, r in top5.iterrows():
        print(f"  {r['state_abbr']} GEOID {r['GEOID']}: {r['subject_count_strict']:,}")


if __name__ == "__main__":
    main()
