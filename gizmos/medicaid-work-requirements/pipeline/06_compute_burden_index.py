"""Stage 06 — compute the composite verification-burden index per tract.

The burden index is the editorial layer of the analysis. It predicts where
verification will fail not because enrollees aren't doing the work but because
the paperwork will defeat them. See METHODOLOGY.md §5 for the rationale.

Three sub-scores, each 0-1 normalized at national level:
  - verification_difficulty: limited English + no internet + low education
  - labor_volatility: share in seasonal/gig/construction/hospitality
  - access_gap: broadband + DSS office drive time (drive time stubbed in v1)

Final burden_index = weighted sum × 100, centered on national median.

Output:
  output/tract_burden.parquet — GEOID, burden_index, sub-scores, components

Run: python 06_compute_burden_index.py
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

import config

ACS_IN = config.RAW_DIR / "acs_tract.parquet"
SUBJECT_IN = config.OUTPUT_DIR / "tract_subject.parquet"

OUT = config.OUTPUT_DIR / "tract_burden.parquet"


def _check_inputs() -> bool:
    if not ACS_IN.exists():
        print(f"ERROR: {ACS_IN} missing. Run stage 01 first.", file=sys.stderr)
        return False
    if not SUBJECT_IN.exists():
        print(f"ERROR: {SUBJECT_IN} missing. Run stage 05 first.", file=sys.stderr)
        return False
    return True


def _safe_ratio(num: pd.Series, denom: pd.Series) -> pd.Series:
    return np.where(denom > 0, num / denom, 0.0)


def compute_verification_difficulty(acs: pd.DataFrame) -> pd.Series:
    """Limited English + no internet + low literacy proxy.

    Inputs (best-effort with available columns):
      - B16002 / B16004: language at home (limited English households)
      - B28002: internet subscription type (no internet = no broadband + no cell)
      - B15003: educational attainment 25+ (less than 9th grade as low-literacy proxy)
    """
    # Limited English share: B16002 _004E is "Spanish: limited English speaking"
    # plus other-language limited English equivalents. For v1 we use a conservative
    # estimate based on B16002_001E (total households) vs the limited-English subtotals.
    limited_eng = pd.Series(0.0, index=acs.index)
    if "B16002_004E" in acs.columns and "B16002_001E" in acs.columns:
        limited_eng = _safe_ratio(
            acs["B16002_004E"].fillna(0)
            + acs.get("B16002_007E", pd.Series(0.0, index=acs.index)).fillna(0)
            + acs.get("B16002_010E", pd.Series(0.0, index=acs.index)).fillna(0)
            + acs.get("B16002_013E", pd.Series(0.0, index=acs.index)).fillna(0),
            acs["B16002_001E"].fillna(0),
        )
    elif "B16002_002E" in acs.columns and "B16002_001E" in acs.columns:
        # Coarser fallback: any non-English-speaking household share
        non_eng = acs["B16002_001E"].fillna(0) - acs["B16002_002E"].fillna(0)
        limited_eng = _safe_ratio(non_eng, acs["B16002_001E"].fillna(0))
    limited_eng = pd.Series(limited_eng, index=acs.index, name="limited_eng_share").clip(0, 1)

    # No-internet share: B28002 _013E is "No internet access" / total B28002_001E
    no_internet = pd.Series(0.0, index=acs.index)
    if "B28002_013E" in acs.columns and "B28002_001E" in acs.columns:
        no_internet = _safe_ratio(acs["B28002_013E"].fillna(0), acs["B28002_001E"].fillna(0))
    no_internet = pd.Series(no_internet, index=acs.index, name="no_internet_share").clip(0, 1)

    # Less-than-HS share: B15003 sums of categories under high school
    # B15003 columns _002E through _016E are <HS; _001E is universe
    less_hs = pd.Series(0.0, index=acs.index)
    if "B15003_001E" in acs.columns:
        less_hs_cols = [c for c in [f"B15003_{n:03d}E" for n in range(2, 17)] if c in acs.columns]
        if less_hs_cols:
            less_hs_sum = acs[less_hs_cols].fillna(0).sum(axis=1)
            less_hs = _safe_ratio(less_hs_sum, acs["B15003_001E"].fillna(0))
    less_hs = pd.Series(less_hs, index=acs.index, name="less_hs_share").clip(0, 1)

    # Equal-weighted average of three sub-inputs
    score = (limited_eng + no_internet + less_hs) / 3.0
    return score.rename("verification_difficulty")


def compute_labor_volatility(acs: pd.DataFrame) -> pd.Series:
    """Share of workers in volatile sectors.

    C24010 has occupation by sex. For an MVP we sum 'service occupations',
    'natural resources/construction/maintenance', and 'production/transportation'
    — the broad categories most associated with seasonal and gig work.

    C24010 columns are paired by sex:
      Total: _001E
      Service occupations: _019E (male) + _055E (female)
      Natural resources, construction, maintenance: _030E (male) + _066E (female)
      Production, transportation, material moving: _034E (male) + _070E (female)
    """
    if "C24010_001E" not in acs.columns:
        return pd.Series(0.0, index=acs.index, name="labor_volatility")

    universe = acs["C24010_001E"].fillna(0)
    volatile_cols = [
        "C24010_019E", "C24010_055E",  # service
        "C24010_030E", "C24010_066E",  # natural resources / construction / maintenance
        "C24010_034E", "C24010_070E",  # production / transportation
    ]
    present = [c for c in volatile_cols if c in acs.columns]
    volatile_sum = acs[present].fillna(0).sum(axis=1) if present else pd.Series(0.0, index=acs.index)
    return pd.Series(_safe_ratio(volatile_sum, universe), index=acs.index, name="labor_volatility").clip(0, 1)


def compute_access_gap(acs: pd.DataFrame) -> pd.Series:
    """Broadband + drive-time-to-DSS proxy.

    For v1 we use only no-internet share as the access proxy. Drive-time to
    nearest DSS office requires a stage-08-side join to OSM routing — we'll
    add that in v2. Documented in METHODOLOGY §5.
    """
    if "B28002_013E" in acs.columns and "B28002_001E" in acs.columns:
        no_internet = _safe_ratio(acs["B28002_013E"].fillna(0), acs["B28002_001E"].fillna(0))
        return pd.Series(no_internet, index=acs.index, name="access_gap").clip(0, 1)
    return pd.Series(0.0, index=acs.index, name="access_gap")


def main() -> None:
    if not _check_inputs():
        sys.exit(1)

    acs = pd.read_parquet(ACS_IN)
    subject = pd.read_parquet(SUBJECT_IN)

    # Align ACS to subject's GEOID order
    acs_aligned = acs.set_index("GEOID").reindex(subject["GEOID"]).reset_index()

    print("Computing burden sub-scores...")
    vd = compute_verification_difficulty(acs_aligned)
    lv = compute_labor_volatility(acs_aligned)
    ag = compute_access_gap(acs_aligned)

    weighted = (
        config.BURDEN_INDEX_WEIGHTS["verification_difficulty"] * vd
        + config.BURDEN_INDEX_WEIGHTS["labor_volatility"] * lv
        + config.BURDEN_INDEX_WEIGHTS["access_gap"] * ag
    )

    # Scale 0-100 and center on national median (weighted by expansion pool)
    score_0_100 = weighted * 100.0
    pool = subject["expansion_pool_estimate"].fillna(0).values
    if pool.sum() > 0:
        national_median = np.average(
            score_0_100,
            weights=np.where(pool > 0, pool, 1e-9),
        )
    else:
        national_median = score_0_100.median()
    score_centered = score_0_100 - national_median

    out = pd.DataFrame({
        "GEOID": subject["GEOID"].values,
        "verification_difficulty": vd.values,
        "labor_volatility": lv.values,
        "access_gap": ag.values,
        "burden_index_raw_0_100": score_0_100.values,
        "burden_index_centered": score_centered.values,
    })
    out["national_median_burden"] = national_median
    out.to_parquet(OUT, index=False)

    print(f"  national_median_burden = {national_median:.1f}")
    print(f"  burden_index range: {score_centered.min():.1f} to {score_centered.max():.1f}")
    print(f"\n-> {OUT.relative_to(config.PIPELINE_DIR)}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 06 done in {time.time() - t0:.1f}s")
