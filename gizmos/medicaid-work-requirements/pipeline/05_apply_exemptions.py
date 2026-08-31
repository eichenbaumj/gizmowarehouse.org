"""Stage 05 — apply OBBBA categorical exemptions to derive the subject pool.

Starting from stage 04's expansion-adult Medicaid pool, we subtract:
  - Medically frail (disability + SUD + serious medical conditions)
  - Pregnant / postpartum
  - Parent / caretaker of child age 13 or younger
  - Full-time student
  - Recent incarceration
  - SNAP/TANF work compliance

Each exemption category has a different data quality. See METHODOLOGY.md §3.

For each tract we produce a *central estimate* (strict-enforcement assumption)
and a *low-band estimate* (permissive: hardship exceptions adopted, short-term
hardships catch 2% of enrollees).

Output:
  output/tract_subject.parquet — GEOID, expansion_pool, exemptions by category,
    subject_central, subject_low_band, MOEs

Run: python 05_apply_exemptions.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import config

POOL_IN = config.OUTPUT_DIR / "tract_expansion_pool.parquet"
ACS_TRACT_IN = config.RAW_DIR / "acs_tract.parquet"
HARDSHIP_IN = config.RAW_DIR / "manual" / "kff_hardship_county_eligibility.csv"
SAMHSA_IN = config.RAW_DIR / "manual" / "samhsa_nsduh_sud_state.csv"

TRACT_OUT = config.OUTPUT_DIR / "tract_subject.parquet"


def _check_inputs() -> bool:
    if not POOL_IN.exists():
        print(f"ERROR: {POOL_IN} missing. Run stage 04 first.", file=sys.stderr)
        return False
    if not ACS_TRACT_IN.exists():
        print(f"ERROR: {ACS_TRACT_IN} missing. Run stage 01 first.", file=sys.stderr)
        return False
    return True


def estimate_disability_share(acs: pd.DataFrame) -> pd.Series:
    """Estimate tract-level share of expansion adults with a disability.

    B18135 universe is civilian noninstitutionalized; we use the 19-64 with-public-
    coverage subtotals where available. If those exact columns aren't pulled, we
    fall back to a uniform national rate from NATIONAL_EXEMPTION_RATES.

    Returns a Series indexed by GEOID with the disability share (0-1).
    """
    # B18135 cells: _004E (under 19 with public coverage with disability), and
    # subsequent age bins. The full table has 53 columns. The relevant 19-64
    # subset is approximately columns 011, 022, 033 across age × coverage × disability.
    # For v1 we apply a uniform national rate; v2 will derive from the actual
    # B18135 cells once we've fully validated column meanings.
    national_rate = config.NATIONAL_EXEMPTION_RATES["medically_frail"]
    return pd.Series(national_rate, index=acs.index, name="disability_share")


def estimate_parent_share(acs: pd.DataFrame) -> pd.Series:
    """Estimate share of expansion adults caring for a child age 13 or younger."""
    return pd.Series(
        config.NATIONAL_EXEMPTION_RATES["parent_caretaker_child_under_14"],
        index=acs.index,
        name="parent_share",
    )


def estimate_pregnant_share(acs: pd.DataFrame) -> pd.Series:
    """Pregnant + postpartum share — state-level rate apportioned uniformly within state."""
    return pd.Series(
        config.NATIONAL_EXEMPTION_RATES["pregnant_postpartum"],
        index=acs.index,
        name="pregnant_share",
    )


def estimate_student_share(acs: pd.DataFrame) -> pd.Series:
    return pd.Series(
        config.NATIONAL_EXEMPTION_RATES["full_time_student"],
        index=acs.index,
        name="student_share",
    )


def estimate_incarceration_share(acs: pd.DataFrame) -> pd.Series:
    return pd.Series(
        config.NATIONAL_EXEMPTION_RATES["recent_incarceration"],
        index=acs.index,
        name="incarceration_share",
    )


def estimate_snap_compliance_share(acs: pd.DataFrame) -> pd.Series:
    return pd.Series(
        config.NATIONAL_EXEMPTION_RATES["snap_tanf_work_compliant"],
        index=acs.index,
        name="snap_share",
    )


def load_hardship_county_flags() -> pd.DataFrame:
    """Load KFF's list of counties qualifying for high-unemployment hardship exception."""
    if not HARDSHIP_IN.exists():
        print(f"WARN: {HARDSHIP_IN} missing — high-unemployment exception not applied", file=sys.stderr)
        return pd.DataFrame(columns=["state_fips", "county_fips", "qualifies"])
    df = pd.read_csv(HARDSHIP_IN, dtype={"state_fips": str, "county_fips": str})
    return df[df["qualifies"].astype(bool)].copy()


def main() -> None:
    if not _check_inputs():
        sys.exit(1)

    pool = pd.read_parquet(POOL_IN)
    acs = pd.read_parquet(ACS_TRACT_IN)

    print(f"Pool: {len(pool):,} tracts; national total {pool['expansion_pool_estimate'].sum():,.0f}")

    # Align ACS to pool's order
    acs = acs.set_index("GEOID").reindex(pool["GEOID"]).reset_index()

    # Estimate exemption shares per tract
    disability_share = estimate_disability_share(acs)
    parent_share = estimate_parent_share(acs)
    pregnant_share = estimate_pregnant_share(acs)
    student_share = estimate_student_share(acs)
    incarceration_share = estimate_incarceration_share(acs)
    snap_share = estimate_snap_compliance_share(acs)

    # Childless-only waiver populations (e.g. WI BadgerCare childless adults) have
    # no parent/caretaker-of-a-child exemption by definition. Zero that one share
    # for those states so we don't remove parents who aren't in the pool.
    childless_fips = {
        f for f, w in config.WAIVER_SUBJECT.items() if w.get("childless_only")
    }
    if childless_fips:
        parent_arr = parent_share.to_numpy(copy=True)
        childless_mask = pool["state_fips"].isin(childless_fips).to_numpy()
        parent_arr[childless_mask] = 0.0
        parent_share = pd.Series(parent_arr, index=parent_share.index, name="parent_share")

    # Exemption shares are NOT independent (a person can be both pregnant and
    # disabled, for example). To avoid double-counting, we compute an effective
    # combined exemption share assuming partial independence. The conservative
    # approach for a first-pass approximation: treat shares as independent and
    # compute non-exempt = product(1 - share_i), then exempt = 1 - non-exempt.
    # This understates total exemption modestly; we'll refine in v2 with PUMS.
    shares = {
        "medically_frail": disability_share.values,
        "parent_caretaker_under_14": parent_share.values,
        "pregnant_postpartum": pregnant_share.values,
        "full_time_student": student_share.values,
        "recent_incarceration": incarceration_share.values,
        "snap_tanf_work_compliant": snap_share.values,
    }
    non_exempt = np.ones(len(pool))
    for arr in shares.values():
        non_exempt = non_exempt * (1.0 - arr)
    exempt_share = 1.0 - non_exempt

    # ---- CBO subject-target rake (v3 calibration) -------------------------
    # PUMS-derived per-state exemption rates measure statutory eligibility
    # (who *could* claim an exemption under §1902(xx)). CBO's published 18.5M
    # subject reflects who they assume *will* be in the verification cohort
    # after the HHS interim final rule (CMS-2454-IFC, published 2026-06-01)
    # narrows operational eligibility and after enrollee uptake of exemption
    # claiming. The two
    # numbers diverge because PUMS captures statutory eligibility broadly.
    # We rake the per-tract subject share by a uniform national multiplier so
    # the national headline matches CBO's empirical control total while
    # preserving each state's PUMS-derived relative exemption profile. This
    # mirrors what stage 07b does for the loss-breakdown national rake.
    # The CBO 18.5M control total is the ACA-EXPANSION subject population. Compute
    # and apply the rake on expansion tracts ONLY; subject-via-1115-waiver states
    # (WI/GA) carry an admin-anchored pool from stage 04 and are ADDED ON TOP of
    # 18.5M (rake factor 1.0), not folded into it. National subject headline
    # becomes 18.5M + the waiver admin slice (~206K).
    is_exp = pool["state_fips"].isin(set(config.EXPANSION_STATE_FIPS)).values
    pre_rake_subject_national = float(
        (pool["expansion_pool_estimate"].values[is_exp] * non_exempt[is_exp]).sum()
    )
    cbo_subject_target = float(config.CROSS_VALIDATION_TARGETS["cbo_national_subject_2027"])
    if pre_rake_subject_national > 0:
        subject_rake_factor = cbo_subject_target / pre_rake_subject_national
    else:
        subject_rake_factor = 1.0
    print(
        f"  CBO subject rake (expansion only): pre-rake {pre_rake_subject_national:>14,.0f} "
        f"-> target {cbo_subject_target:>14,.0f}  (rake factor {subject_rake_factor:.3f})"
    )
    # Scale (1 - exempt_share) by the rake factor on expansion tracts; waiver
    # tracts use factor 1.0 (admin level). Clip to [0, 1] so we never produce a
    # subject share above the expansion-pool denominator.
    per_tract_rake = np.where(is_exp, subject_rake_factor, 1.0)
    raked_subject_share = np.clip(non_exempt * per_tract_rake, 0.0, 1.0)
    effective_exempt_share = 1.0 - raked_subject_share

    # Apply (raked) exemptions to compute subject pool (strict band)
    subject_strict = pool["expansion_pool_estimate"].values * raked_subject_share
    subject_strict_moe = pool["expansion_pool_moe"].values * raked_subject_share

    # Permissive band: also exempt enrollees in high-unemployment counties that
    # adopt the exception, plus 2% short-term hardship across all enrollees.
    hardship_flags = load_hardship_county_flags()
    hardship_county_geoids = set(
        (hardship_flags["state_fips"] + hardship_flags["county_fips"]).tolist()
    ) if not hardship_flags.empty else set()

    pool_geo_5 = pool["state_fips"].astype(str) + pool["county_fips"].astype(str)
    adopting_states = set(config.ADOPTING_HARDSHIP_FIPS)
    in_adopting_state = pool["state_fips"].astype(str).isin(adopting_states).values
    in_hardship_county = pool_geo_5.isin(hardship_county_geoids).values
    permissive_geo_exempt = in_adopting_state & in_hardship_county

    permissive_factor = np.where(
        permissive_geo_exempt,
        0.0,  # county is fully exempt for adopting states
        raked_subject_share * (1.0 - config.PERMISSIVE_BAND["short_term_hardship_rate"]),
    )
    subject_permissive = pool["expansion_pool_estimate"].values * permissive_factor
    subject_permissive_moe = pool["expansion_pool_moe"].values * permissive_factor

    # Per-category exemption counts (for analyst CSV)
    pool_n = pool["expansion_pool_estimate"].values
    out = pd.DataFrame({
        "GEOID": pool["GEOID"].values,
        "state_fips": pool["state_fips"].values,
        "county_fips": pool["county_fips"].values,
        "tract": pool["tract"].values,
        "expansion_pool_estimate": pool_n,
        "expansion_pool_moe": pool["expansion_pool_moe"].values,
        "exempt_share_combined": effective_exempt_share,
        "exempt_share_pre_rake": exempt_share,
        "subject_rake_factor": subject_rake_factor,
        "n_exempt_medically_frail": pool_n * disability_share.values,
        "n_exempt_parent_under_14": pool_n * parent_share.values,
        "n_exempt_pregnant_postpartum": pool_n * pregnant_share.values,
        "n_exempt_full_time_student": pool_n * student_share.values,
        "n_exempt_recent_incarceration": pool_n * incarceration_share.values,
        "n_exempt_snap_tanf_compliant": pool_n * snap_share.values,
        "subject_count_strict": subject_strict,
        "subject_count_strict_moe": subject_strict_moe,
        "subject_count_permissive": subject_permissive,
        "subject_count_permissive_moe": subject_permissive_moe,
        "permissive_geo_exempt": permissive_geo_exempt,
        "calibration_source": pool["calibration_source"].values,
        "data_quality_flag": pool["data_quality_flag"].values,
    })

    # Compute loss exposure (CBO admin-churn assumption)
    out["loss_exposure_strict"] = out["subject_count_strict"] * config.LOSS_EXPOSURE_CHURN_RATE
    out["loss_exposure_permissive"] = out["subject_count_permissive"] * config.LOSS_EXPOSURE_CHURN_RATE

    # CBO loss-target rake. With raked subject = 18.5M and config churn = 0.30,
    # the implied loss is 5.55M — but CBO's published score is 5.2M (implied
    # churn ~28.1%). Apply a small additional uniform rake so the loss headline
    # matches CBO. The same logic that raked subject; loss is also a CBO
    # control total worth honoring. Per-tract relative ranking is preserved.
    # As with the subject rake, the CBO 5.2M loss control total is the expansion
    # population's. Rake on expansion tracts only; waiver tracts (factor 1.0) add
    # their churn-proxy loss on top. (This stage's churn-proxy loss is superseded
    # by stage 07b's bottom-up loss for the shipped headline; the rake keeps the
    # intermediate parquet's national figure aligned with CBO.)
    is_exp_out = out["state_fips"].isin(set(config.EXPANSION_STATE_FIPS)).values
    pre_rake_loss_national = float(out["loss_exposure_strict"].values[is_exp_out].sum())
    cbo_loss_target = float(config.CROSS_VALIDATION_TARGETS["cbo_national_loss_2034"])
    if pre_rake_loss_national > 0:
        loss_rake_factor = cbo_loss_target / pre_rake_loss_national
    else:
        loss_rake_factor = 1.0
    print(
        f"  CBO loss rake (expansion only): pre-rake {pre_rake_loss_national:>14,.0f} "
        f"-> target {cbo_loss_target:>14,.0f}  (rake factor {loss_rake_factor:.3f})"
    )
    per_tract_loss_rake = np.where(is_exp_out, loss_rake_factor, 1.0)
    out["loss_exposure_strict"] = out["loss_exposure_strict"] * per_tract_loss_rake
    out["loss_exposure_permissive"] = out["loss_exposure_permissive"] * per_tract_loss_rake

    nat_strict = out["subject_count_strict"].sum()
    nat_perm = out["subject_count_permissive"].sum()
    nat_loss = out["loss_exposure_strict"].sum()

    cbo_subject = config.CROSS_VALIDATION_TARGETS["cbo_national_subject_2027"]
    cbo_loss = config.CROSS_VALIDATION_TARGETS["cbo_national_loss_2034"]
    print()
    print(f"National subject (strict):    {nat_strict:>12,.0f}  (CBO target {cbo_subject:>10,}; ratio {nat_strict/cbo_subject:.2f})")
    print(f"National subject (permissive):{nat_perm:>12,.0f}")
    print(f"National loss exposure:       {nat_loss:>12,.0f}  (CBO target {cbo_loss:>10,}; ratio {nat_loss/cbo_loss:.2f})")
    print()

    out.to_parquet(TRACT_OUT, index=False)
    print(f"-> {TRACT_OUT.relative_to(config.PIPELINE_DIR)}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 05 done in {time.time() - t0:.1f}s")
