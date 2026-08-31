"""Stage 04e — per-state exemption-eligibility rate computation.

Computes per-state eligibility rates for the six exemption subgroups consumed
by stage 04c. v1 of the pipeline applied a single national prior per subgroup
uniformly across all states; v2 derives state-specific rates from authoritative
data where it exists.

Subgroup → primary source:
  medically_frail            → ACS PUMS 2020-2024 (DIS × specific-impairment flags)
  parent_caretaker_child_under_14  → ACS PUMS 2020-2024 (household with own child ≤13)
  full_time_student          → ACS PUMS 2020-2024 (SCH ∈ {2,3} AND SCHG ≥ 15)
  sud_treatment              → SAMHSA NSDUH 2023-2024 SAE × 0.35 treatment engagement
  recent_incarceration       → BJS NPS 2023, calibrated to national 0.008 prior
  pregnant_postpartum        → national prior (no state-level public data in v2)

Floor / cap policy:
  For all subgroups except pregnancy, each state's rate is clipped to
  national_prior × [0.5, 2.0]. PUMS 5-year samples can be noisy in small states;
  BJS NPS rates pre-calibration can swing wildly. The 0.5-2.0 envelope preserves
  the meaningful real variation (most subgroups span 0.7-1.5× nationally) while
  clipping pathological tails. Every clipped state is logged.

Small-sample fallback:
  PUMS-derived rates require subject_pool_weighted ≥ 5000. States below that
  threshold (typically WY, VT, AK, ND, SD) get the national fallback for that
  subgroup, logged explicitly.

Outputs:
  output/state_exemption_rates.parquet — one row per expansion state, columns:
    state_fips, state_abbr, subject_pool_weighted
    For each subgroup k:
      {k}_rate              — the per-state eligibility rate to be applied in 04c
      {k}_source            — one of: pums, samhsa_nsduh, bjs_nps, national_fallback
      {k}_clipped           — bool: True if floor/cap clip was applied
      {k}_raw_rate          — pre-clip rate (for diagnostics)
    vintage_pums, vintage_samhsa, vintage_bjs  — provenance strings

Cross-validation:
  Stage 04f runs after 04e and validates these rates against external benchmarks
  (KFF state-level Medicaid disability/parent shares, NCES IPEDS state enrollment,
  PPI state release rates). 04f emits a console pass/fail table.

METHODOLOGY.md §3.5 documents every parameter, every source, every clip.

Run: python 04e_compute_state_exemption_rates.py
     python 04e_compute_state_exemption_rates.py --allow-missing-manual
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

import config

# --- Paths ------------------------------------------------------------------

STATE_SUMMARY_IN = config.PUBLIC_DATA_DIR / "medicaid-state-summary.json"
PUMS_CACHE_DIR = config.OUTPUT_DIR / "pums_state_cache"
MANUAL_DIR = config.RAW_DIR / "manual"
SAMHSA_SUD_IN = MANUAL_DIR / "samhsa_nsduh_state_sud.csv"
BJS_RELEASES_IN = MANUAL_DIR / "bjs_nps_state_releases.csv"

STATE_EXEMPTION_RATES_OUT = config.OUTPUT_DIR / "state_exemption_rates.parquet"

# --- Constants --------------------------------------------------------------

# Subject pool / expansion pool ratio. Mirror of 04c's SUBJECT_TO_EXPANSION_RATIO.
SUBJECT_TO_EXPANSION_RATIO = 0.88

# Floor/cap envelope as a multiplier of the national prior. The default ±2×
# envelope assumes modest state variation around a stable national rate — right
# for proxy-derived subgroups whose tails are mostly small-sample noise.
FLOOR_MULTIPLIER = 0.5
CAP_MULTIPLIER = 2.0

# v8 (Esty review 2): per-subgroup envelope overrides for subgroups where the
# default ±2× is wrong:
#   - ai_an_exempt: RACAIAN is a DIRECT Census measure with genuine ~40× state
#     variation (AK expansion pool ≈ 42% AI/AN; NM/MT/OK/Dakotas also very high).
#     Clipping to 2× the 1% national prior would erase the real concentration
#     that is exactly the state heterogeneity Sarah asked us to surface. Use a
#     wide envelope (0.1×–50×) so the per-state PUMS share stands.
#   - parent_caretaker_child_under_14: the Section 1931 carve-out legitimately
#     drives the expansion-parent rate near zero in high-1931-limit states
#     (MA, CT, MN, MD, etc.). A 0.5× floor would re-inflate exactly the parents
#     we just correctly removed, so drop the floor to 0.1×.
SUBGROUP_CLIP_OVERRIDES: dict[str, tuple[float, float]] = {
    "ai_an_exempt": (0.1, 50.0),
    "parent_caretaker_child_under_14": (0.1, CAP_MULTIPLIER),
}

# PUMS small-sample threshold (weighted subject pool). Below this, PUMS-derived
# rates are replaced by the national fallback.
PUMS_MIN_SUBJECT_POOL_WEIGHTED = 5000

# SAMHSA NSDUH SAE measures past-year SUD prevalence. Of those, ~35% are in
# treatment qualifying for medically-frail under §1902(xx). National anchor
# from SAMHSA's National Tracking Indicators. Document in METHODOLOGY §3.5.
SUD_TREATMENT_ENGAGEMENT_NATIONAL = 0.35

# Subgroup keys. Must match config.NATIONAL_EXEMPTION_RATES keys for fallback.
SUBGROUPS = [
    "medically_frail",
    "parent_caretaker_child_under_14",
    "full_time_student",
    "sud_treatment",
    "recent_incarceration",
    "pregnant_postpartum",
    # v4 (Esty review): per-state rates for the v5-introduced exemption subgroups,
    # replacing the uniform national priors.
    "kinship_caregivers",
    "caregivers_disabled_adult",
    # v8 (Esty review 2): AI/AN exemption, now PUMS-derived per state (RACAIAN).
    "ai_an_exempt",
]

# --- State-name → FIPS mapping (for SAMHSA/BJS files that key on state name) ---

def _build_state_name_to_fips() -> dict[str, str]:
    mapping = {}
    for fips, info in config.STATE_INFO.items():
        mapping[info["name"]] = fips
        # Accept abbreviation too (defensive)
        mapping[info["abbr"]] = fips
    return mapping

STATE_NAME_TO_FIPS = _build_state_name_to_fips()


# --- Input loaders ----------------------------------------------------------

def _check_inputs(allow_missing_manual: bool) -> bool:
    ok = True
    if not STATE_SUMMARY_IN.exists():
        print(f"ERROR: {STATE_SUMMARY_IN} missing. Run stage 07 first.", file=sys.stderr)
        ok = False
    if not PUMS_CACHE_DIR.exists() or not any(PUMS_CACHE_DIR.glob("*_classified.parquet")):
        print(f"ERROR: {PUMS_CACHE_DIR} missing or empty. "
              f"Run `python 04b_fetch_pums_workdoc_breakdown.py --pums-mode full` first.",
              file=sys.stderr)
        ok = False
    for path, label in [(SAMHSA_SUD_IN, "SAMHSA NSDUH SUD"), (BJS_RELEASES_IN, "BJS NPS releases")]:
        if not path.exists():
            msg = f"{'WARN' if allow_missing_manual else 'ERROR'}: {path} missing ({label})."
            print(msg, file=sys.stderr)
            if not allow_missing_manual:
                print(f"  See {MANUAL_DIR / 'README.md'} for the source URL. "
                      f"Pass --allow-missing-manual to fall back to national priors.",
                      file=sys.stderr)
                ok = False
    return ok


def _load_state_pums_v2(state_abbr: str) -> dict | None:
    """Load v2 PUMS cache for a state. Returns None if missing or schema too old."""
    path = PUMS_CACHE_DIR / f"{state_abbr.lower()}_classified.parquet"
    if not path.exists():
        return None
    row = pd.read_parquet(path).iloc[0].to_dict()
    schema_v = int(row.get("cache_schema_version", 1))
    if schema_v < 2:
        return None
    return row


def _load_samhsa_sud() -> dict[str, float]:
    """Returns {state_fips: sud_prevalence_pct}. Excludes census regions / Total U.S."""
    if not SAMHSA_SUD_IN.exists():
        return {}
    df = pd.read_csv(SAMHSA_SUD_IN)
    out: dict[str, float] = {}
    for _, r in df.iterrows():
        state_name = str(r["state"]).strip()
        if state_name not in STATE_NAME_TO_FIPS:
            continue  # skip Total U.S., census regions, etc.
        fips = STATE_NAME_TO_FIPS[state_name]
        try:
            out[fips] = float(r["sud_prevalence_18plus_pct"]) / 100.0
        except (ValueError, TypeError):
            continue
    return out


def _load_bjs_releases() -> dict[str, int]:
    """Returns {state_fips: releases_2023}."""
    if not BJS_RELEASES_IN.exists():
        return {}
    df = pd.read_csv(BJS_RELEASES_IN)
    out: dict[str, int] = {}
    for _, r in df.iterrows():
        state_name = str(r["state"]).strip()
        if state_name not in STATE_NAME_TO_FIPS:
            continue
        fips = STATE_NAME_TO_FIPS[state_name]
        try:
            out[fips] = int(r["releases_2023"])
        except (ValueError, TypeError):
            continue
    return out


# --- Per-subgroup rate computation ------------------------------------------

def _clip_rate(
    rate: float,
    national_prior: float,
    floor_mult: float = FLOOR_MULTIPLIER,
    cap_mult: float = CAP_MULTIPLIER,
) -> tuple[float, bool]:
    """Apply national_prior × [floor_mult, cap_mult] envelope.

    Returns (clipped_rate, was_clipped).
    """
    floor = national_prior * floor_mult
    cap = national_prior * cap_mult
    if rate < floor:
        return floor, True
    if rate > cap:
        return cap, True
    return rate, False


def _pums_rate(
    pums_row: dict | None,
    count_col: str,
    national_prior: float,
    floor_mult: float = FLOOR_MULTIPLIER,
    cap_mult: float = CAP_MULTIPLIER,
) -> tuple[float, str, bool, float]:
    """Compute a PUMS-derived rate for one subgroup.

    Returns (clipped_rate, source, was_clipped, raw_rate).
    """
    if pums_row is None:
        return national_prior, "national_fallback", False, national_prior
    subject_pool = float(pums_row.get("subject_pool_weighted") or 0)
    if subject_pool < PUMS_MIN_SUBJECT_POOL_WEIGHTED:
        return national_prior, "national_fallback", False, national_prior
    count = float(pums_row.get(count_col) or 0)
    raw = count / subject_pool if subject_pool > 0 else 0.0
    clipped, was_clipped = _clip_rate(raw, national_prior, floor_mult, cap_mult)
    return clipped, "pums", was_clipped, raw


def _sud_rate(
    state_fips: str,
    sud_by_fips: dict[str, float],
    national_prior: float,
) -> tuple[float, str, bool, float]:
    """SAMHSA NSDUH state SUD prevalence × national treatment-engagement rate."""
    if state_fips not in sud_by_fips:
        return national_prior, "national_fallback", False, national_prior
    state_sud_prev = sud_by_fips[state_fips]
    raw = state_sud_prev * SUD_TREATMENT_ENGAGEMENT_NATIONAL
    clipped, was_clipped = _clip_rate(raw, national_prior)
    return clipped, "samhsa_nsduh", was_clipped, raw


def _incarceration_rates_all_states(
    expansion_states: list[dict],
    bjs_releases: dict[str, int],
    national_prior: float,
) -> dict[str, tuple[float, str, bool, float]]:
    """Compute calibrated per-state recent-incarceration rates for all states.

    Calibration: state_share = BJS_releases[s] / sum(BJS_releases). Each state's
    eligibility count is target_total × state_share, where target_total honors
    the national prior. State rate = eligibility_count / state_expansion_pool.

    This preserves relative state variation (states with proportionally more
    state-prison releases get higher rates) while honoring the national level
    (NPS excludes jails, which the 0.008 prior includes via Sommers Arkansas).

    Returns {fips: (clipped_rate, source, was_clipped, raw_rate)}.
    """
    if not bjs_releases:
        return {s["state_fips"]: (national_prior, "national_fallback", False, national_prior)
                for s in expansion_states}

    # Total expansion pool across all expansion states (denominator for target_total).
    total_expansion = sum(
        (float(s.get("expansion_pool") or 0) or float(s["subject_count_strict"]) / SUBJECT_TO_EXPANSION_RATIO)
        for s in expansion_states
    )
    target_total = total_expansion * national_prior

    # BJS national total across only the expansion states that have BJS data.
    # Non-expansion states (TX, FL, GA, etc.) are excluded — they're not part
    # of the subject pool. DC has no BJS data (federal BoP); DC gets fallback.
    bjs_states_in_expansion = {s["state_fips"]: bjs_releases[s["state_fips"]]
                                for s in expansion_states
                                if s["state_fips"] in bjs_releases}
    bjs_national_in_expansion = sum(bjs_states_in_expansion.values())

    if bjs_national_in_expansion == 0:
        return {s["state_fips"]: (national_prior, "national_fallback", False, national_prior)
                for s in expansion_states}

    out: dict[str, tuple[float, str, bool, float]] = {}
    for s in expansion_states:
        fips = s["state_fips"]
        expansion_pool = float(s.get("expansion_pool") or 0) or float(s["subject_count_strict"]) / SUBJECT_TO_EXPANSION_RATIO
        if fips not in bjs_states_in_expansion or expansion_pool <= 0:
            out[fips] = (national_prior, "national_fallback", False, national_prior)
            continue
        state_share = bjs_states_in_expansion[fips] / bjs_national_in_expansion
        state_eligible = target_total * state_share
        raw = state_eligible / expansion_pool
        clipped, was_clipped = _clip_rate(raw, national_prior)
        out[fips] = (clipped, "bjs_nps", was_clipped, raw)
    return out


# --- Main -------------------------------------------------------------------

def main(allow_missing_manual: bool = False) -> None:
    if not _check_inputs(allow_missing_manual):
        sys.exit(1)

    summary = json.loads(STATE_SUMMARY_IN.read_text())
    # Per-state rates are computed for every OBBBA-SUBJECT state: the ACA
    # expansion states PLUS the sized 1115-waiver states (WI/GA), which now use
    # their OWN ACS PUMS instead of national priors — matching every other
    # state's method. (TN has no subject pool, so subject_via_waiver is False and
    # it's excluded.) The ~1% WI/GA add to the incarceration/BJS national
    # denominators is immaterial and conceptually correct: they ARE subject pool.
    subject_states = [s for s in summary["states"] if s["expansion"] or s.get("subject_via_waiver")]

    sud_by_fips = _load_samhsa_sud()
    bjs_releases = _load_bjs_releases()

    print(f"Inputs:")
    print(f"  PUMS v2 cache         : {PUMS_CACHE_DIR.relative_to(config.PIPELINE_DIR)}")
    print(f"  SAMHSA SUD (rows)     : {len(sud_by_fips)} / {len(subject_states)} subject states")
    print(f"  BJS releases (rows)   : {len(bjs_releases)} / {len(subject_states)} subject states")
    print(f"  Floor/cap multipliers : ×{FLOOR_MULTIPLIER:.1f} / ×{CAP_MULTIPLIER:.1f}")
    print(f"  PUMS small-N floor    : subject_pool_weighted ≥ {PUMS_MIN_SUBJECT_POOL_WEIGHTED:,}")
    print()

    # Pre-compute incarceration rates (needs cross-state calibration)
    incarc_rates = _incarceration_rates_all_states(
        subject_states, bjs_releases,
        config.NATIONAL_EXEMPTION_RATES["recent_incarceration"],
    )

    # Build per-state rows
    rows = []
    fallback_log: dict[str, list[str]] = {k: [] for k in SUBGROUPS}
    clip_log: dict[str, list[str]] = {k: [] for k in SUBGROUPS}

    pums_vintage = None  # filled from first PUMS row we see

    for s in subject_states:
        fips = s["state_fips"]
        abbr = s["state_abbr"]
        pums_row = _load_state_pums_v2(abbr)
        subject_pool_weighted = float(pums_row["subject_pool_weighted"]) if pums_row else 0.0

        row = {
            "state_fips": fips,
            "state_abbr": abbr,
            "state_name": s["state_name"],
            "subject_pool_weighted": subject_pool_weighted,
        }

        # PUMS-derived (medically frail, caregiver, student, kinship, disabled-adult caregiver, pregnancy)
        for subgroup, count_col in [
            ("medically_frail", "medically_frail_count_weighted"),
            ("parent_caretaker_child_under_14", "caregiver_under14_count_weighted"),
            ("full_time_student", "fulltime_student_count_weighted"),
            # v4 additions (Esty review):
            ("kinship_caregivers", "kinship_caregiver_count_weighted"),
            ("caregivers_disabled_adult", "caregivers_disabled_adult_count_weighted"),
            ("pregnant_postpartum", "pregnant_postpartum_count_weighted"),
            # v8 addition (Esty review 2): AI/AN exemption from PUMS RACAIAN.
            ("ai_an_exempt", "ai_an_count_weighted"),
        ]:
            national_prior = config.NATIONAL_EXEMPTION_RATES[subgroup]
            floor_mult, cap_mult = SUBGROUP_CLIP_OVERRIDES.get(subgroup, (FLOOR_MULTIPLIER, CAP_MULTIPLIER))
            rate, source, was_clipped, raw = _pums_rate(pums_row, count_col, national_prior, floor_mult, cap_mult)
            row[f"{subgroup}_rate"] = rate
            row[f"{subgroup}_source"] = source
            row[f"{subgroup}_clipped"] = was_clipped
            row[f"{subgroup}_raw_rate"] = raw
            if source == "national_fallback":
                fallback_log[subgroup].append(abbr)
            if was_clipped:
                clip_log[subgroup].append(f"{abbr}({raw:.3f}→{rate:.3f})")

        # SAMHSA NSDUH (SUD treatment)
        national_prior = config.NATIONAL_EXEMPTION_RATES["sud_treatment"]
        rate, source, was_clipped, raw = _sud_rate(fips, sud_by_fips, national_prior)
        row["sud_treatment_rate"] = rate
        row["sud_treatment_source"] = source
        row["sud_treatment_clipped"] = was_clipped
        row["sud_treatment_raw_rate"] = raw
        if source == "national_fallback":
            fallback_log["sud_treatment"].append(abbr)
        if was_clipped:
            clip_log["sud_treatment"].append(f"{abbr}({raw:.4f}→{rate:.4f})")

        # BJS NPS (recent incarceration)
        rate, source, was_clipped, raw = incarc_rates[fips]
        row["recent_incarceration_rate"] = rate
        row["recent_incarceration_source"] = source
        row["recent_incarceration_clipped"] = was_clipped
        row["recent_incarceration_raw_rate"] = raw
        if source == "national_fallback":
            fallback_log["recent_incarceration"].append(abbr)
        if was_clipped:
            clip_log["recent_incarceration"].append(f"{abbr}({raw:.4f}→{rate:.4f})")

        # Vintage provenance — set once, on first non-empty PUMS row
        if pums_vintage is None and pums_row is not None:
            pums_vintage = f"ACS PUMS 5-Year {config.ACS_VINTAGE} (cache schema v{int(pums_row.get('cache_schema_version', 1))})"

        rows.append(row)

    df = pd.DataFrame(rows)

    # Provenance columns (uniform across rows)
    df["vintage_pums"] = pums_vintage or "ACS PUMS unavailable"
    df["vintage_samhsa"] = "SAMHSA NSDUH SAE 2023-2024 (released Oct 2024)" if sud_by_fips else "not available"
    df["vintage_bjs"] = "BJS NPS Prisoners 2023 (released Sep 2025)" if bjs_releases else "not available"

    # ---- Console summary --------------------------------------------------
    print(f"Per-subgroup state-rate summary (n={len(df)} subject states):")
    print(f"  {'subgroup':<30} {'national':>9}  {'mean':>8}  {'min':>8}  {'max':>8}  "
          f"{'pums/samhsa/bjs/fallback':>26}  {'clipped':>7}")
    print(f"  {'-' * 30} {'-' * 9}  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 26}  {'-' * 7}")
    total_w = df["subject_pool_weighted"].sum()
    for subgroup in SUBGROUPS:
        national_prior = config.NATIONAL_EXEMPTION_RATES[subgroup]
        col = f"{subgroup}_rate"
        source_col = f"{subgroup}_source"
        if total_w > 0:
            wmean = (df[col] * df["subject_pool_weighted"]).sum() / total_w
        else:
            wmean = df[col].mean()
        sources = df[source_col].value_counts()
        sources_str = "/".join(str(sources.get(s, 0)) for s in
                                ["pums", "samhsa_nsduh", "bjs_nps", "national_fallback"])
        n_clipped = int(df[f"{subgroup}_clipped"].sum())
        print(f"  {subgroup:<30} {national_prior:>9.4f}  {wmean:>8.4f}  "
              f"{df[col].min():>8.4f}  {df[col].max():>8.4f}  "
              f"{sources_str:>26}  {n_clipped:>7d}")

    # Fallback / clip details
    has_log = any(fallback_log[k] for k in SUBGROUPS) or any(clip_log[k] for k in SUBGROUPS)
    if has_log:
        print()
        for k in SUBGROUPS:
            if fallback_log[k]:
                print(f"  {k} — national_fallback for: {', '.join(sorted(fallback_log[k]))}")
            if clip_log[k]:
                print(f"  {k} — clipped: {', '.join(clip_log[k])}")

    # ---- Write output -----------------------------------------------------
    STATE_EXEMPTION_RATES_OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(STATE_EXEMPTION_RATES_OUT, index=False)
    print(f"\n-> {STATE_EXEMPTION_RATES_OUT.relative_to(config.PIPELINE_DIR)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-missing-manual", action="store_true",
                    help="Fall back to national priors for SUD/incarceration when "
                         "manual CSVs (raw/manual/) are absent. Use only for "
                         "developer iteration; production builds should have all "
                         "manual files in place per raw/manual/README.md.")
    args = ap.parse_args()
    t0 = time.time()
    main(allow_missing_manual=args.allow_missing_manual)
    print(f"\nStage 04e done in {time.time() - t0:.1f}s")
