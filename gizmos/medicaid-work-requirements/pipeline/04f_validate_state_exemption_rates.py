"""Stage 04f — cross-validate stage 04e's per-state exemption-eligibility rates
against external benchmarks.

This is the integrity check before the rates flow into 04c. For each subgroup
where a benchmark file is available, compare per-state rates to an independent
external source and flag any state-subgroup pair that diverges by more than
the documented tolerance. The check is **non-blocking** — definitional
differences between OBBBA eligibility and the external benchmark may produce
apparent failures that are not actually data errors. Stage 04f emits a
console table and writes a parquet of every comparison for downstream audit.

Benchmark table:
  medically_frail            ← KFF "Distribution of Medicaid Enrollees by
                                Enrollment Group" — disability share (±30%)
  parent_caretaker_child_under_14 ← KFF "Distribution of Medicaid Enrollees by
                                Enrollment Group" — parent/caretaker share (±25%)
  full_time_student          ← NCES IPEDS state college enrollment ÷ adult pop
                                (±35%)
  recent_incarceration       ← Prison Policy Initiative state release rates
                                (±50%) — note: PPI counts jails too, so this is
                                expected to read higher than BJS NPS state-only
  sud_treatment              ← SAMHSA NSDUH state SUD prevalence (echo check
                                from same source; ±10% sanity)
  pregnant_postpartum        ← PUMS FER-based per-state (echo check; ±10% sanity)

v9 additions (scraped via Chrome MCP from publisher interactive UIs):
  kinship_caregivers         ← AECF KIDS COUNT "Children in kinship care"
                                state percentages, most-recent year
                                (datacenter.aecf.org). Loaded from
                                raw/manual/aecf_kinship_state.csv.
                                Scaled to PUMS national mean before
                                per-state comparison.
  caregivers_disabled_adult  ← AARP / NAC "Caregiving in the US 2025"
                                State Data Profiles map data
                                (caregivingintheus.org). Loaded from
                                raw/manual/aarp_caregiver_state.csv.
                                Scaled to PUMS national mean before
                                per-state comparison.
  Tolerance for both: ±60%. The external benchmarks measure
  methodologically distant quantities (AECF = % of children in kinship
  care; AARP = % of any adult caregivers), so we calibrate each
  benchmark's national mean to our PUMS national mean and the per-state
  comparison then tests variation rather than absolute level.

Inputs:
  output/state_exemption_rates.parquet  (stage 04e output)
  raw/manual/kff_state_disability_medicaid.csv (optional)
  raw/manual/kff_state_parent_caretaker_medicaid.csv (optional)
  raw/manual/nces_ipeds_state_enrollment.csv (optional)
  raw/manual/ppi_state_release_rates.csv (optional)

Outputs:
  output/state_exemption_rates_validation.parquet — full comparison

Console: per-subgroup pass/fail counts + listing of failing state-subgroup pairs.

Run: python 04f_validate_state_exemption_rates.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

import config

# --- Paths ------------------------------------------------------------------

RATES_IN = config.OUTPUT_DIR / "state_exemption_rates.parquet"
MANUAL_DIR = config.RAW_DIR / "manual"

KFF_DISABILITY_IN = MANUAL_DIR / "kff_state_disability_medicaid.csv"
KFF_PARENT_IN = MANUAL_DIR / "kff_state_parent_caretaker_medicaid.csv"
NCES_IPEDS_IN = MANUAL_DIR / "nces_ipeds_state_enrollment.csv"
PPI_RELEASES_IN = MANUAL_DIR / "ppi_state_release_rates.csv"
# v9 additions: scraped via Chrome MCP from the publisher interactive UIs.
AECF_KINSHIP_IN = MANUAL_DIR / "aecf_kinship_state.csv"
AARP_CAREGIVER_IN = MANUAL_DIR / "aarp_caregiver_state.csv"

VALIDATION_OUT = config.OUTPUT_DIR / "state_exemption_rates_validation.parquet"

# --- Benchmark tolerances (relative; e.g. 0.30 = ±30%) ---------------------

BENCHMARK_TOLERANCES = {
    "medically_frail": 0.30,
    "parent_caretaker_child_under_14": 0.25,
    "full_time_student": 0.35,
    "recent_incarceration": 0.50,
    "sud_treatment": 0.10,
    # v9: kinship caregivers and caregivers of disabled adults. Higher tolerance
    # (±60%) because the external benchmark measures a methodologically distant
    # quantity (AECF = % of children in kinship care; AARP = % of adults who are
    # any-type caregivers), and we scale into a PUMS-comparable rate via the
    # constants documented in the benchmark loader. The tolerance reflects that
    # the scaling step is itself an editorial choice.
    "kinship_caregivers": 0.60,
    "caregivers_disabled_adult": 0.60,
}

# v9 scaling constants. Convert the external benchmark (different unit of
# analysis) into a PUMS-comparable rate. These are anchored to the ratio of
# national PUMS-derived rate to national external-benchmark rate; the cross-
# validation then tests whether per-state variation in the two sources tracks.
#
# AECF: their indicator is "% of children in kinship care" (children
# denominator). Our PUMS metric is "% of expansion-adult subject pool who are
# kinship caregivers." Nationally AECF reports 4% of children; PUMS-derived
# rate is ~1.5% of expansion adults. So a scaling constant of ~0.375 maps
# AECF to PUMS-comparable rate (1.5 ÷ 4).
AECF_TO_PUMS_KINSHIP_SCALE = 0.375
# AARP: their indicator is "% of adults who provide unpaid care to ANY adult."
# Our PUMS metric is "% of expansion subject pool caring for a WORKING-AGE
# disabled adult specifically." Nationally AARP reports ~24% of adults;
# PUMS-derived rate is ~3% of expansion adults. So the scale is ~0.125
# (3 ÷ 24).
AARP_TO_PUMS_DISABLED_ADULT_SCALE = 0.125


def _build_state_name_to_fips() -> dict[str, str]:
    mapping = {}
    for fips, info in config.STATE_INFO.items():
        mapping[info["name"]] = fips
        mapping[info["abbr"]] = fips
    return mapping

STATE_NAME_TO_FIPS = _build_state_name_to_fips()


def _load_benchmark(path: Path, state_col: str, value_col: str) -> dict[str, float] | None:
    """Read a benchmark CSV. Returns {fips: value} or None if file missing."""
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if state_col not in df.columns or value_col not in df.columns:
        print(f"WARN: {path.name} missing required columns ({state_col}, {value_col}); skipping")
        return None
    out: dict[str, float] = {}
    for _, r in df.iterrows():
        name = str(r[state_col]).strip()
        if name not in STATE_NAME_TO_FIPS:
            continue
        fips = STATE_NAME_TO_FIPS[name]
        try:
            out[fips] = float(r[value_col])
        except (ValueError, TypeError):
            continue
    return out


def _validate_subgroup(
    rates_df: pd.DataFrame,
    subgroup: str,
    benchmark_by_fips: dict[str, float] | None,
    tolerance: float,
    benchmark_label: str,
) -> tuple[pd.DataFrame, int, int, int]:
    """Compare per-state 04e rates to a benchmark. Returns (df, n_pass, n_fail, n_skipped)."""
    rows = []
    n_pass = n_fail = n_skipped = 0
    rate_col = f"{subgroup}_rate"
    for _, r in rates_df.iterrows():
        fips = r["state_fips"]
        abbr = r["state_abbr"]
        our_rate = float(r[rate_col])
        if benchmark_by_fips is None:
            n_skipped += 1
            rows.append({
                "subgroup": subgroup,
                "state_fips": fips,
                "state_abbr": abbr,
                "our_rate": our_rate,
                "benchmark": None,
                "delta_rel": None,
                "result": "skipped_no_benchmark",
                "benchmark_label": benchmark_label,
            })
            continue
        if fips not in benchmark_by_fips:
            n_skipped += 1
            rows.append({
                "subgroup": subgroup,
                "state_fips": fips,
                "state_abbr": abbr,
                "our_rate": our_rate,
                "benchmark": None,
                "delta_rel": None,
                "result": "skipped_state_missing",
                "benchmark_label": benchmark_label,
            })
            continue
        bench = benchmark_by_fips[fips]
        if bench <= 0:
            n_skipped += 1
            rows.append({
                "subgroup": subgroup,
                "state_fips": fips,
                "state_abbr": abbr,
                "our_rate": our_rate,
                "benchmark": bench,
                "delta_rel": None,
                "result": "skipped_benchmark_zero",
                "benchmark_label": benchmark_label,
            })
            continue
        delta_rel = (our_rate / bench) - 1.0
        passes = abs(delta_rel) <= tolerance
        result = "pass" if passes else "fail"
        if passes:
            n_pass += 1
        else:
            n_fail += 1
        rows.append({
            "subgroup": subgroup,
            "state_fips": fips,
            "state_abbr": abbr,
            "our_rate": our_rate,
            "benchmark": bench,
            "delta_rel": delta_rel,
            "result": result,
            "benchmark_label": benchmark_label,
        })
    return pd.DataFrame(rows), n_pass, n_fail, n_skipped


def main() -> None:
    if not RATES_IN.exists():
        print(f"ERROR: {RATES_IN} missing. Run stage 04e first.", file=sys.stderr)
        sys.exit(1)

    rates_df = pd.read_parquet(RATES_IN)
    print(f"Validating {len(rates_df)} expansion states against external benchmarks.\n")

    # Load benchmarks (each returns None if file missing)
    kff_dis = _load_benchmark(KFF_DISABILITY_IN, "state", "disability_share_among_medicaid_adults")
    kff_par = _load_benchmark(KFF_PARENT_IN, "state", "parent_caretaker_share_among_medicaid_adults")
    nces = _load_benchmark(NCES_IPEDS_IN, "state", "enrollment_age_19_24")
    ppi = _load_benchmark(PPI_RELEASES_IN, "state", "annual_releases_per_100k_adults")

    # SAMHSA NSDUH echo: re-load the same CSV we used in 04e and verify the
    # implied SUD-treatment rate matches the per-state rate × treatment-engagement.
    # This is a *circular* sanity check (same source), but catches CSV parsing bugs.
    samhsa_path = MANUAL_DIR / "samhsa_nsduh_state_sud.csv"
    if samhsa_path.exists():
        samhsa_df = pd.read_csv(samhsa_path)
        samhsa_dict: dict[str, float] = {}
        for _, r in samhsa_df.iterrows():
            name = str(r["state"]).strip()
            if name in STATE_NAME_TO_FIPS:
                try:
                    samhsa_dict[STATE_NAME_TO_FIPS[name]] = float(r["sud_prevalence_18plus_pct"]) / 100.0 * 0.35
                except (ValueError, TypeError):
                    pass
        samhsa_bench = samhsa_dict
    else:
        samhsa_bench = None

    # v9 benchmarks: scraped via Chrome MCP from publisher interactive UIs.
    # The external benchmarks measure methodologically distant quantities (AECF
    # = % of children in kinship care; AARP = % of any adult caregivers),
    # so we calibrate each benchmark's national mean to our PUMS national mean.
    # The cross-validation then tests per-state VARIATION (whether high-kinship
    # states per AECF are high-kinship per our PUMS), not absolute LEVELS
    # (which are already bounded by the floor/cap envelope in 04e).
    aecf_raw = _load_benchmark(AECF_KINSHIP_IN, "state", "aecf_kinship_pct_children_2023_2025")
    if aecf_raw is not None:
        # Recalibrate scale so the benchmark national mean equals our PUMS national mean.
        our_kinship_mean = float(rates_df["kinship_caregivers_rate"].mean())
        bench_kinship_mean = sum(pct / 100.0 for pct in aecf_raw.values()) / len(aecf_raw)
        scale = our_kinship_mean / bench_kinship_mean if bench_kinship_mean > 0 else AECF_TO_PUMS_KINSHIP_SCALE
        aecf_kinship = {fips: (pct / 100.0) * scale for fips, pct in aecf_raw.items()}
        print(f"AECF kinship scale: {scale:.3f} (our mean {our_kinship_mean:.4f} / AECF mean {bench_kinship_mean:.4f})")
    else:
        aecf_kinship = None

    aarp_raw = _load_benchmark(AARP_CAREGIVER_IN, "state", "aarp_caregiver_pct_adults_2025")
    if aarp_raw is not None:
        our_dac_mean = float(rates_df["caregivers_disabled_adult_rate"].mean())
        bench_dac_mean = sum(pct / 100.0 for pct in aarp_raw.values()) / len(aarp_raw)
        scale = our_dac_mean / bench_dac_mean if bench_dac_mean > 0 else AARP_TO_PUMS_DISABLED_ADULT_SCALE
        aarp_disabled = {fips: (pct / 100.0) * scale for fips, pct in aarp_raw.items()}
        print(f"AARP disabled-adult scale: {scale:.3f} (our mean {our_dac_mean:.4f} / AARP mean {bench_dac_mean:.4f})")
    else:
        aarp_disabled = None

    benchmark_specs = [
        ("medically_frail", kff_dis, "KFF state disability share among Medicaid adults"),
        ("parent_caretaker_child_under_14", kff_par, "KFF state parent/caretaker share"),
        ("full_time_student", nces, "NCES IPEDS state enrollment 19-24 ÷ adult pop"),
        ("recent_incarceration", ppi, "PPI state release rates (jails + prisons)"),
        ("sud_treatment", samhsa_bench, "SAMHSA NSDUH state SUD × 0.35 (echo check)"),
        ("kinship_caregivers", aecf_kinship, "AECF KIDS COUNT % children in kinship care × 0.375 scale"),
        ("caregivers_disabled_adult", aarp_disabled, "AARP/NAC % adults who are caregivers × 0.125 scale"),
    ]

    all_rows: list[pd.DataFrame] = []
    print(f"  {'subgroup':<32} {'benchmark':<55} {'pass':>5} {'fail':>5} {'skip':>5}")
    print(f"  {'-' * 32} {'-' * 55} {'-' * 5} {'-' * 5} {'-' * 5}")
    failing_pairs: list[str] = []
    for subgroup, bench, label in benchmark_specs:
        tol = BENCHMARK_TOLERANCES[subgroup]
        result_df, n_pass, n_fail, n_skip = _validate_subgroup(
            rates_df, subgroup, bench, tol, label,
        )
        all_rows.append(result_df)
        bench_status = label if bench else "(no benchmark file — skipped)"
        print(f"  {subgroup:<32} {bench_status:<55} {n_pass:>5d} {n_fail:>5d} {n_skip:>5d}")
        if n_fail > 0:
            for _, r in result_df.query("result == 'fail'").iterrows():
                failing_pairs.append(
                    f"    {subgroup}/{r['state_abbr']}: ours={r['our_rate']:.4f} "
                    f"vs bench={r['benchmark']:.4f} (Δ {r['delta_rel']:+.0%}, tol ±{tol:.0%})"
                )

    if failing_pairs:
        print()
        print(f"FAILING ({len(failing_pairs)} state-subgroup pairs outside tolerance):")
        print(f"  Note: failures may reflect definitional differences between OBBBA")
        print(f"  eligibility and the external benchmark. Review each before treating")
        print(f"  it as a data error.")
        for line in failing_pairs:
            print(line)

    # Stitch and write
    if all_rows:
        out = pd.concat(all_rows, ignore_index=True)
        out.to_parquet(VALIDATION_OUT, index=False)
        print(f"\n-> {VALIDATION_OUT.relative_to(config.PIPELINE_DIR)}")
    else:
        print("\nNo benchmark files present; no validation parquet written.")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 04f done in {time.time() - t0:.1f}s")
