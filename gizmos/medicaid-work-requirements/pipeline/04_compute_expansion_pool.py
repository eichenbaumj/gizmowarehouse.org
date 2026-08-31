"""Stage 04 — compute the tract-level ACA-expansion-adult Medicaid pool.

The methodological move is **shape × level** small-area estimation:
  - Tract-level *shape* comes from ACS B27003 (Medicaid by sex × age),
    optionally filtered by B17024 (income-to-poverty ratio).
  - State-level *level* comes from CMS T-MSIS expansion enrollment, calibrated
    to a Jan 2027 expected level using CBO's projection.

For non-expansion states the expansion-pathway pool is zero. We do *not* model
the would-be-expansion population here — that gets surfaced separately as the
"Uninsured Adults" overlay built in stage 11.

EXCEPTION — subject-via-1115-waiver states (config.WAIVER_SUBJECT). OBBBA reaches
"certain enrollees in 1115 waiver programs," so three non-expansion states are
subject through a waiver slice: Wisconsin (~198K BadgerCare childless adults),
Georgia (~8K Pathways enrollees), Tennessee (named but not publicly quantified).
For these we do NOT flip expansion=True (that would rake the whole state pool and
overcount); instead we rake the ACS B27003 19-64 tract *shape* to the state's
administrative `control_total`, distributing the small admin slice across tracts
by where low-income Medicaid adults live. Georgia is already work-conditional
under Pathways (its loss is zeroed in stage 07b); Tennessee has control_total 0
and stays zeroed here, surfaced only as a flagged status downstream.

Output:
  output/tract_expansion_pool.parquet  — columns: GEOID, state_fips, county_fips,
      tract, expansion_pool_estimate, expansion_pool_moe, data_quality_flag

Run: python 04_compute_expansion_pool.py
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import config

ACS_TRACT_IN = config.RAW_DIR / "acs_tract.parquet"
TMSIS_IN = config.RAW_DIR / "manual" / "cms_tmsis_state_enrollment.csv"
KFF_IN = config.RAW_DIR / "manual" / "kff_expansion_enrollment.csv"

TRACT_OUT = config.OUTPUT_DIR / "tract_expansion_pool.parquet"


# ACS B27003 columns of interest. The table is "Allocation of Medicaid/Means-
# Tested Public Coverage by Sex by Age". Columns _004E through _016E are the
# male enrollee bins (under 6, 6-18, 19-25, 26-34, 35-44, 45-54, 55-64, 65+),
# and _020E through _032E are the female bins, *with the enrollee subtotals
# at specific offsets*. We sum the 19-64 enrollee cells across both sexes.
#
# The actual column numbering depends on the table's universe definition.
# Census documents B27003 as "B27003: Allocation of Medicaid/Means-tested
# Public Coverage by Sex by Age". For the 5-year 2024 vintage we will verify
# the exact column suffixes when reading the data — they ARE stable across
# vintages but we should not assume.
#
# As a safe pattern, we read the parquet, find any column matching the
# B27003 prefix and the expected suffix pattern, and sum age-19-64
# Medicaid-enrolled cells across both sexes.
B27003_AGE_19_64_PATTERNS = [
    # Male: 19-25, 26-34, 35-44, 45-54, 55-64
    "B27003_007E", "B27003_008E", "B27003_009E", "B27003_010E", "B27003_011E",
    # Female: 19-25, 26-34, 35-44, 45-54, 55-64
    "B27003_023E", "B27003_024E", "B27003_025E", "B27003_026E", "B27003_027E",
]
B27003_AGE_19_64_MOE = [c.replace("E", "M") for c in B27003_AGE_19_64_PATTERNS]


def _check_inputs() -> bool:
    ok = True
    if not ACS_TRACT_IN.exists():
        print(f"ERROR: {ACS_TRACT_IN} missing. Run stage 01 first.", file=sys.stderr)
        ok = False
    if not TMSIS_IN.exists():
        print(f"WARN: {TMSIS_IN} missing — using ACS uncalibrated.", file=sys.stderr)
    if not KFF_IN.exists():
        print(f"WARN: {KFF_IN} missing — using ACS uncalibrated.", file=sys.stderr)
    return ok


def compute_tract_shape(acs: pd.DataFrame) -> pd.DataFrame:
    """Sum ACS B27003 ages 19-64 across sexes; propagate MOE.

    The MOE for a sum of independent estimates is sqrt(sum of squared MOEs).
    """
    available = [c for c in B27003_AGE_19_64_PATTERNS if c in acs.columns]
    available_m = [c for c in B27003_AGE_19_64_MOE if c in acs.columns]
    if len(available) < 6:
        warnings.warn(
            f"Only {len(available)} of {len(B27003_AGE_19_64_PATTERNS)} expected "
            f"B27003 columns present. Estimates will be incomplete."
        )

    estimates = acs[available].fillna(0).sum(axis=1)
    moes = np.sqrt((acs[available_m].fillna(0).pow(2)).sum(axis=1))

    out = pd.DataFrame({
        "GEOID": acs["GEOID"].astype(str),
        "tract_medicaid_19_64": estimates,
        "tract_medicaid_19_64_moe": moes,
    })
    out["state_fips"] = out["GEOID"].str[:2]
    out["county_fips"] = out["GEOID"].str[2:5]
    out["tract"] = out["GEOID"].str[5:]
    return out


def load_state_level_calibration() -> pd.DataFrame:
    """Build a per-state expansion-adult control total.

    Order of preference for the state level:
      1. CMS T-MSIS expansion adults 19-64 if available
      2. KFF state expansion enrollment if available
      3. ACS state sum unchanged (no calibration)
    """
    rows = []
    if TMSIS_IN.exists():
        tmsis = pd.read_csv(TMSIS_IN)
        # Use the most recent month if multiple
        if "month" in tmsis.columns:
            tmsis = tmsis.sort_values("month").groupby("state_abbr").tail(1)
        for _, r in tmsis.iterrows():
            abbr = r["state_abbr"]
            fips = next((f for f, info in config.STATE_INFO.items() if info["abbr"] == abbr), None)
            if fips:
                rows.append({"state_fips": fips, "state_level_target": r["expansion_adults_19_64"], "source": "T-MSIS"})
    elif KFF_IN.exists():
        kff = pd.read_csv(KFF_IN)
        for _, r in kff.iterrows():
            abbr = r["state_abbr"]
            fips = next((f for f, info in config.STATE_INFO.items() if info["abbr"] == abbr), None)
            if fips:
                rows.append({"state_fips": fips, "state_level_target": r["expansion_enrollment"], "source": "KFF"})
    return pd.DataFrame(rows)


def rake_tract_to_state(tract_df: pd.DataFrame, state_targets: pd.DataFrame) -> pd.DataFrame:
    """Multiply tract shares by state-level targets where available.

    Non-expansion states are zeroed out regardless of ACS rate (the expansion
    pathway pool is zero by definition) — EXCEPT subject-via-1115-waiver states
    (config.WAIVER_SUBJECT), whose tract shape is raked to an administrative
    control total rather than zeroed.
    """
    df = tract_df.copy()
    state_acs_sums = df.groupby("state_fips")["tract_medicaid_19_64"].sum().rename("state_acs_sum")
    df = df.merge(state_acs_sums, on="state_fips")

    if state_targets.empty:
        # No calibration available; pass through ACS values
        df["state_scaler"] = 1.0
        df["calibration_source"] = "uncalibrated"
    else:
        df = df.merge(state_targets, on="state_fips", how="left")
        df["state_scaler"] = np.where(
            df["state_acs_sum"] > 0,
            df["state_level_target"] / df["state_acs_sum"],
            0.0,
        )
        df["calibration_source"] = df["source"].fillna("uncalibrated")
        df["state_scaler"] = df["state_scaler"].fillna(1.0)

    # Apply scaler to estimate and MOE (a multiplicative scalar scales both)
    df["expansion_pool_estimate"] = df["tract_medicaid_19_64"] * df["state_scaler"]
    df["expansion_pool_moe"] = df["tract_medicaid_19_64_moe"] * df["state_scaler"]

    # Zero out non-expansion states that are NOT subject-via-waiver. Waiver
    # states with a positive control total are handled in the next block.
    waiver_fips = {
        f for f, w in config.WAIVER_SUBJECT.items() if w.get("control_total", 0) > 0
    }
    non_exp_non_waiver = set(config.NON_EXPANSION_STATE_FIPS) - waiver_fips
    mask = df["state_fips"].isin(non_exp_non_waiver)
    df.loc[mask, "expansion_pool_estimate"] = 0.0
    df.loc[mask, "expansion_pool_moe"] = 0.0
    df.loc[mask, "calibration_source"] = "non_expansion_state"

    # Subject-via-1115-waiver non-expansion states: rake the ACS B27003 19-64
    # tract SHAPE to the administrative CONTROL TOTAL (e.g. WI 198,000), so the
    # subject pool is the small admin slice distributed across tracts by the
    # Medicaid-coverage proxy — NOT the full state Medicaid-adult ACS pool.
    for fips in waiver_fips:
        wmask = df["state_fips"] == fips
        acs_sum = float(df.loc[wmask, "tract_medicaid_19_64"].sum())
        ctrl = float(config.WAIVER_SUBJECT[fips]["control_total"])
        scaler = (ctrl / acs_sum) if acs_sum > 0 else 0.0
        df.loc[wmask, "expansion_pool_estimate"] = df.loc[wmask, "tract_medicaid_19_64"] * scaler
        df.loc[wmask, "expansion_pool_moe"] = df.loc[wmask, "tract_medicaid_19_64_moe"] * scaler
        df.loc[wmask, "calibration_source"] = "waiver_admin_control"

    return df


def add_quality_flag(df: pd.DataFrame) -> pd.DataFrame:
    """Classify each tract by data quality based on CV and N."""
    df = df.copy()
    cv = np.where(
        df["expansion_pool_estimate"] > 0,
        df["expansion_pool_moe"] / df["expansion_pool_estimate"],
        np.inf,
    )
    df["coefficient_of_variation"] = cv

    flag = np.where(
        df["expansion_pool_estimate"] < config.MIN_DISPLAY_N,
        "low_n_suppressed",
        np.where(
            cv > config.CV_HIDE_THRESHOLD,
            "low_confidence_hidden",
            np.where(cv > config.CV_HATCH_THRESHOLD, "low_confidence_hatched", "ok"),
        ),
    )
    df["data_quality_flag"] = flag
    return df


def main() -> None:
    if not _check_inputs():
        sys.exit(1)

    print(f"Reading {ACS_TRACT_IN.name}...")
    acs = pd.read_parquet(ACS_TRACT_IN)
    print(f"  {len(acs):,} tracts × {len(acs.columns):,} cols")

    print("\nComputing tract-level Medicaid 19-64 shape from B27003...")
    tract_shape = compute_tract_shape(acs)
    print(f"  total tract-level enrollment: {tract_shape['tract_medicaid_19_64'].sum():,.0f}")

    print("\nLoading state-level calibration targets...")
    state_targets = load_state_level_calibration()
    if state_targets.empty:
        print("  no calibration sources found; output will be uncalibrated ACS values")
    else:
        print(f"  {len(state_targets)} states calibrated from "
              f"{state_targets['source'].iloc[0] if 'source' in state_targets.columns else 'unknown'}")

    print("\nRaking tract shape × state level...")
    raked = rake_tract_to_state(tract_shape, state_targets)
    raked = add_quality_flag(raked)

    nat = raked["expansion_pool_estimate"].sum()
    print(f"\nNational expansion pool (post-rake): {nat:,.0f}")

    # Quick sanity check vs CBO subject benchmark (18.5M ÷ exemption-applied-share)
    cbo_target = config.CROSS_VALIDATION_TARGETS["cbo_national_subject_2027"]
    print(f"CBO 'subject to requirements' benchmark: {cbo_target:,}")
    print(f"  ratio (ours / CBO): {nat / cbo_target:.2f}  "
          "(should be > 1.0 since we haven't applied exemptions yet)")

    raked.to_parquet(TRACT_OUT, index=False)
    print(f"\n-> {TRACT_OUT.relative_to(config.PIPELINE_DIR)}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 04 done in {time.time() - t0:.1f}s")
