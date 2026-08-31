"""Shared PUMS subject-pool refinements (v8 — Sarah Esty review 2).

Both stage 04b (the workdoc/exemption classifier) and
tools/bake-medicaid-subject-profile.py independently read ACS PUMS person
records and build the expansion-adult Medicaid subject pool. To keep the two in
sync, the two corrections introduced in the Esty-review-2 pass live here:

  1. Section 1931 parent carve-out — parents/caretaker relatives whose income is
     below their state's mandatory Section 1931 parent/caretaker limit are
     covered OUTSIDE the ACA-expansion category, so the OBBBA work requirement
     does not apply to them. Remove them from the subject pool.

  2. Recent non-citizen screen — non-citizens (CIT == 5) who entered the U.S.
     within the federal 5-year-bar window are conservatively excluded as not
     federally expansion-eligible (likely undocumented, inside the 5-year bar,
     or in state-funded / emergency coverage that the federal requirement
     doesn't reach). Long-resident LPRs, refugees, and citizens are kept.

Both corrections fix the within-pool COMPOSITION; the national level stays
anchored by the downstream rake to CBO 18.5M. See METHODOLOGY §3.1 and §3.7.

Every function is defensive about missing columns: if a needed column is absent,
it returns an all-False mask so the caller silently keeps everyone (and the
provenance count is 0), matching pre-v8 behavior.
"""
from __future__ import annotations

import pandas as pd

import config  # type: ignore

# RELSHIPP codes for a parent / caretaker relative (reference person + spouse/
# partner). Mirrors 04b's RELSHIPP_CARETAKER.
RELSHIPP_CARETAKER = {20, 21, 22, 23, 24}
# RELSHIPP codes for "own child of the reference person" (bio/adopted/step/foster).
RELSHIPP_OWN_CHILD = {25, 26, 27, 35}
# Section 1931 covers caretaker relatives of a dependent child, conventionally
# under 18 (or 18 if a full-time student). We use < 19 (AGEP ≤ 18).
SECTION_1931_DEPENDENT_CHILD_MAX_AGE = 18


def households_with_own_child_under_19(full_df: pd.DataFrame) -> set[str]:
    """SERIALNOs of households containing the reference person's own child ≤18.

    Computed on the FULL pre-filter PUMS frame (children are rarely the enrolled
    subject, so they must be seen before the adult subject-pool filter).
    """
    if "SERIALNO" not in full_df.columns or "RELSHIPP" not in full_df.columns \
            or "AGEP" not in full_df.columns:
        return set()
    relshipp = pd.to_numeric(full_df["RELSHIPP"], errors="coerce")
    agep = pd.to_numeric(full_df["AGEP"], errors="coerce")
    mask = (agep <= SECTION_1931_DEPENDENT_CHILD_MAX_AGE) & relshipp.isin(RELSHIPP_OWN_CHILD)
    return set(full_df.loc[mask, "SERIALNO"].astype(str).unique())


def section_1931_parent_mask(
    adults_df: pd.DataFrame,
    child_under_19_households: set[str],
    state_fips: str,
) -> pd.Series:
    """Boolean mask (aligned to adults_df) of Section-1931 parents to EXCLUDE.

    A record is a 1931 parent if it is a caretaker relative (RELSHIPP 20-24),
    shares a household with the reference person's own child ≤18, and has
    POVPIP below the state's Section 1931 limit (% FPL).
    """
    false = pd.Series(False, index=adults_df.index)
    threshold = config.SECTION_1931_PARENT_THRESHOLD_PCT_FPL.get(state_fips)
    if threshold is None or not child_under_19_households:
        return false
    if "RELSHIPP" not in adults_df.columns or "SERIALNO" not in adults_df.columns \
            or "POVPIP" not in adults_df.columns:
        return false
    relshipp = pd.to_numeric(adults_df["RELSHIPP"], errors="coerce")
    povpip = pd.to_numeric(adults_df["POVPIP"], errors="coerce")
    serial = adults_df["SERIALNO"].astype(str)
    return (
        relshipp.isin(RELSHIPP_CARETAKER)
        & serial.isin(child_under_19_households)
        & povpip.notna()
        & (povpip < threshold)
    )


def recent_noncitizen_mask(adults_df: pd.DataFrame) -> pd.Series:
    """Boolean mask of non-citizens who entered within the 5-year-bar window.

    CIT == 5 ("not a U.S. citizen") AND (survey_year - YOEP) < bar years.
    """
    false = pd.Series(False, index=adults_df.index)
    if "CIT" not in adults_df.columns or "YOEP" not in adults_df.columns:
        return false
    cit = pd.to_numeric(adults_df["CIT"], errors="coerce")
    yoep = pd.to_numeric(adults_df["YOEP"], errors="coerce")
    years_in_us = config.PUMS_SURVEY_END_YEAR - yoep
    return (
        (cit == config.PUMS_CITIZEN_NONCITIZEN_CODE)
        & yoep.notna()
        & (years_in_us < config.RECENT_IMMIGRANT_YEARS_BAR)
    )


def refine_subject_pool(
    adults_df: pd.DataFrame,
    full_df: pd.DataFrame | None,
    state_fips: str,
    weight_col: str = "PWGTP",
    child_under_19_households: set[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Apply both v8 refinements to an already-subject-filtered adult frame.

    Parameters
    ----------
    adults_df : the subject-pool frame (Medicaid, 19-64, POVPIP 0-138, PWGTP>0).
    full_df   : the full pre-filter PUMS frame (needed for child-household
                detection); ignored if child_under_19_households is supplied.
    state_fips: 2-digit FIPS for the Section 1931 threshold lookup.
    child_under_19_households : optional precomputed set (callers that already
                computed household-child sets pass it to avoid recomputation).

    Returns (refined_adults_df, provenance) where provenance carries weighted
    counts for logging + the on-page "share of parents covered outside
    expansion" summary stat.
    """
    if child_under_19_households is not None:
        child_hh = child_under_19_households
    else:
        child_hh = households_with_own_child_under_19(full_df) if full_df is not None else set()
    s1931 = section_1931_parent_mask(adults_df, child_hh, state_fips)
    noncit = recent_noncitizen_mask(adults_df)

    w = pd.to_numeric(adults_df[weight_col], errors="coerce").fillna(0.0)
    pool_before = float(w.sum())
    # All caretaker-relative parents of an own child ≤18 (the denominator for
    # the "share of parents covered outside expansion" stat).
    if {"RELSHIPP", "SERIALNO"}.issubset(adults_df.columns) and child_hh:
        relshipp = pd.to_numeric(adults_df["RELSHIPP"], errors="coerce")
        serial = adults_df["SERIALNO"].astype(str)
        all_parents_mask = relshipp.isin(RELSHIPP_CARETAKER) & serial.isin(child_hh)
        parents_total_w = float(w[all_parents_mask].sum())
    else:
        parents_total_w = 0.0

    exclude = s1931 | noncit
    refined = adults_df.loc[~exclude].copy()

    s1931_w = float(w[s1931].sum())
    noncit_w = float(w[noncit].sum())
    provenance = {
        "pool_before_refinement_weighted": pool_before,
        "pool_after_refinement_weighted": float(pool_before - w[exclude].sum()),
        "section_1931_parent_excluded_weighted": s1931_w,
        "recent_noncitizen_excluded_weighted": noncit_w,
        "parents_of_own_child_total_weighted": parents_total_w,
        # Share of in-pool parents who turn out to be covered outside expansion
        # (below the Section 1931 limit) — the headline summary stat for the caveat.
        "share_parents_covered_outside_expansion": (
            s1931_w / parents_total_w if parents_total_w > 0 else 0.0
        ),
    }
    return refined, provenance
