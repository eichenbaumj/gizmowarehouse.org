"""Stage 07b — combine 04b + 04c + 04d into the loss-breakdown JSON (v5).

We keep the existing stage 07 (which builds state_summary.json from tract-
level outputs) untouched, and add stage 07b that combines the three new
breakdown stages into a separate `medicaid-loss-breakdown.json`. This gives
the new section its own data file without entangling with stage 07's
unrelated tract-level work.

Inputs:
  output/state_workdoc_failures.parquet         (stage 04b)
  output/state_exemption_doc_failures.parquet   (stage 04c)
  output/state_ex_parte_scored.parquet          (stage 04d)
  public/data/medicaid-state-summary.json       (stage 07 output)
  pipeline/state_ex_parte_capability.json        (for historical_experience)

Output:
  public/data/medicaid-loss-breakdown.json     — consumed by MedicaidLossSankey

v5 (Esty review) — methodology change:
  Per-(state, subgroup) loss is computed bottom-up in 04b and 04c:
      loss = subject_pool × eligibility_rate × failure_rate
  where failure_rate decomposes implicitly into (1 - p_ex_parte_to_subgroup)
  × (1 - p_documentation_success). 07b sums those per-state totals to a
  national bottom-up estimate and compares against the published range:
      CBO 5.2M (June 2025 OBBBA score)
      Urban Institute HIPSM 7.5M (midpoint)
      CBPP up to 10M (state-implementation-lag scenario)
  If the bottom-up total lands inside [4.5M, 11M], no calibration is applied
  and the Sankey shows the raw bottom-up output. If it lands outside, a single
  global multiplier is applied uniformly to land at the CBO+Urban midpoint of
  6.4M. Per-state and per-subgroup PROPORTIONS are preserved either way —
  only the absolute scale moves.

  The v4 45/45/10 rake-to-CBO was dropped per Esty review (the rake distorted
  the within-bucket proportions to match an editorial split; the bottom-up
  proportions are now the result rather than the input).

Run: python 07b_build_loss_breakdown.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time

import pandas as pd

import config

WORKDOC_IN = config.OUTPUT_DIR / "state_workdoc_failures.parquet"
EXEMPTION_IN = config.OUTPUT_DIR / "state_exemption_doc_failures.parquet"
EX_PARTE_IN = config.OUTPUT_DIR / "state_ex_parte_scored.parquet"
EX_PARTE_JSON_IN = config.PIPELINE_DIR / "state_ex_parte_capability.json"
STATE_SUMMARY_IN = config.PUBLIC_DATA_DIR / "medicaid-state-summary.json"
BREAKDOWN_OUT = config.PUBLIC_DATA_DIR / "medicaid-loss-breakdown.json"
LOCAL_OUT = config.OUTPUT_DIR / "medicaid-loss-breakdown.json"


def _load_historical_experience_map() -> dict:
    """Read historical_experience nested dict from state_ex_parte_capability.json
    by FIPS so 07b can pass it through to the front-end JSON.
    """
    if not EX_PARTE_JSON_IN.exists():
        return {}
    payload = json.loads(EX_PARTE_JSON_IN.read_text())
    out: dict = {}
    for fips, entry in payload.get("states", {}).items():
        hx = entry.get("historical_experience")
        if hx:
            out[fips] = hx
    return out


def _import_stage_module(filename: str, modname: str):
    """Load a stage module whose filename starts with a digit (not a valid
    Python identifier) so we can read its SUBGROUPS dict for narratives.
    """
    spec = importlib.util.spec_from_file_location(modname, config.PIPELINE_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


# Pull the SUBGROUPS dicts (label + narrative) from 04b / 04c so subgroup
# metadata lives in one place per stage and propagates into the front-end JSON.
_stage_04b = _import_stage_module("04b_fetch_pums_workdoc_breakdown.py", "stage_04b")
_stage_04c = _import_stage_module("04c_build_exemption_breakdown.py", "stage_04c")
WORKDOC_NARRATIVES = {k: v.get("narrative", "") for k, v in _stage_04b.SYNTHETIC_SUBGROUPS.items()}
EXEMPTION_NARRATIVES = {k: v.get("narrative", "") for k, v in _stage_04c.SUBGROUPS.items()}
# Some compliant-bucket subgroups (students, volunteering/job-training) are
# displayed in the work-doc band but sourced from 04c, so their narrative lives
# in EXEMPTION_NARRATIVES. Merge both so a subgroup resolves its narrative from
# whichever stage defines it, regardless of which band renders it.
ALL_NARRATIVES = {**EXEMPTION_NARRATIVES, **WORKDOC_NARRATIVES}

# National targets. These are calibration anchors only; state-level numbers
# are scaled to honor these national totals via iterative proportional fitting.
TARGET_TOTAL_LOSS = 5_200_000          # CBO 5.2M by 2034
TARGET_NONCOMPLIANT_SHARE = 0.10       # ~10% (Sommers Arkansas residual + KFF subject-pool math)
TARGET_WORKDOC_SHARE = 0.45            # ~45%
TARGET_EXEMPTION_SHARE = 0.45          # ~45%

# Pre-rake non-compliant rate as share of state subject pool.
# 3% × 18.5M subject ≈ 555k, close to the 520k target.
NONCOMPLIANT_PRE_RAKE_RATE = 0.030

# Subgroup label ordering for the JSON output.
# v7 restructure (Esty review follow-up): Sarah flagged that legally, "compliant"
# = work / school / volunteering and "exempt" = medical / caregiving / pregnancy.
# v6 had students in the exemption bucket; v7 moves them to the compliant bucket
# where they belong, alongside new volunteering/job-training subgroup. The
# "workdoc" variable name is preserved to minimize churn but represents the
# wider "compliant-doc" bucket.
WORKDOC_SUBGROUPS = [
    # Sourced from stage 04b (work-classified PUMS records)
    ("gig_courier", "Gig / courier (DoorDash, Uber, Lyft, Instacart)"),
    ("cash_construction", "Cash-paid construction & trades"),
    ("multi_part_time", "Multiple part-time jobs (aggregation failure)"),
    ("seasonal_ag_hosp", "Seasonal: agriculture, hospitality, food service"),
    ("self_employed_other", "Self-employed (other)"),
    ("variable_shifts", "Variable shifts / on-call work"),
    # v7 moved from EXEMPTION_SUBGROUPS — sourced from stage 04c
    ("students_no_match", "Full-time students not auto-verified"),
    # v7 NEW — sourced from stage 04c
    ("volunteering_job_training", "Volunteering / job training"),
]

EXEMPTION_SUBGROUPS = [
    ("medically_frail_no_match", "Medically frail without auto-match"),
    ("caregivers_no_match", "Parent caregivers of children ≤13 without auto-match"),
    ("kinship_caregivers_other", "Kinship caregivers (non-parent) of children ≤13"),     # v5 NEW
    ("caregivers_disabled_adult", "Caregivers of a disabled adult"),                      # v5 NEW
    ("sud_not_flagged", "SUD treatment not flagged in claims data"),
    ("recent_incarc_data_gap", "Recent incarceration (data-match gap)"),
    ("pregnancy_lag", "Pregnancy / postpartum data lag"),
    ("ai_an_exempt", "American Indian / Alaska Native (tribal exemption)"),               # v8 NEW
    # v7 NEW — sourced from stage 04c
    ("other_categorical_exempt", "Other categorical exemptions (foster, AYA cancer, SNAP/TANF)"),
]

# v7: each subgroup key maps to which stage's output parquet it lives in.
# Most are still in their original source; the new compliant-side additions
# (students, volunteering) live in 04c.
SUBGROUP_SOURCE: dict[str, str] = {
    # 04b work-doc subgroups
    "gig_courier": "workdoc",
    "cash_construction": "workdoc",
    "multi_part_time": "workdoc",
    "seasonal_ag_hosp": "workdoc",
    "self_employed_other": "workdoc",
    "variable_shifts": "workdoc",
    # 04c exemption subgroups (legal category: exempt)
    "medically_frail_no_match": "exemption",
    "caregivers_no_match": "exemption",
    "kinship_caregivers_other": "exemption",
    "caregivers_disabled_adult": "exemption",
    "sud_not_flagged": "exemption",
    "recent_incarc_data_gap": "exemption",
    "pregnancy_lag": "exemption",
    "ai_an_exempt": "exemption",                 # v8 NEW — data source = 04c parquet
    # 04c subgroups that legally belong on the compliant side
    "students_no_match": "exemption",            # data source = 04c parquet
    "volunteering_job_training": "exemption",    # data source = 04c parquet
    "other_categorical_exempt": "exemption",     # data source = 04c parquet
}


def _load_prior_state_exemption_totals(prior_path) -> dict[str, float]:
    """Load post-rake exemption-doc-failure totals per state from prior
    medicaid-loss-breakdown.json (if present). Returns {fips: total}.

    Used by the v2 drift report to flag states whose pre-rake exemption total
    has shifted >25% from v1's post-rake total — a signal that 04e's per-state
    rates introduced a state-level number worth reviewing before publish.
    """
    if not prior_path.exists():
        return {}
    try:
        prior = json.loads(prior_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    states = prior.get("states", {})
    if not isinstance(states, dict):
        return {}
    out: dict[str, float] = {}
    for fips, s in states.items():
        try:
            out[fips] = float(s["exemption_doc_failures"]["total"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _check_inputs() -> bool:
    for p in (WORKDOC_IN, EXEMPTION_IN, EX_PARTE_IN, STATE_SUMMARY_IN):
        if not p.exists():
            print(f"ERROR: {p} missing.", file=sys.stderr)
            return False
    return True


def main() -> None:
    if not _check_inputs():
        sys.exit(1)

    workdoc = pd.read_parquet(WORKDOC_IN).set_index("state_fips")
    exemption = pd.read_parquet(EXEMPTION_IN).set_index("state_fips")
    ex_parte = pd.read_parquet(EX_PARTE_IN).set_index("state_fips")
    historical_map = _load_historical_experience_map()
    summary = json.loads(STATE_SUMMARY_IN.read_text())

    # ---- Compute pre-rake state-level totals ----
    state_rows: list[dict] = []
    for s in summary["states"]:
        fips = s["state_fips"]
        # Expansion states + subject-via-1115-waiver states (WI/GA). True
        # non-expansion states and TN have subject 0 and fall out below.
        if not s["expansion"] and not s.get("subject_via_waiver"):
            continue
        subject = float(s["subject_count_strict"])
        if subject <= 0:
            continue
        # Georgia's Pathways enrollees are ALREADY work-conditional under the
        # state's 1115 waiver, so OBBBA adds no NET-NEW procedural loss. Carry the
        # subject count but zero every loss subgroup → total_loss_2034 == 0.
        already_work_conditional = bool(
            config.waiver_meta(fips).get("already_work_conditional")
        )

        wd = workdoc.loc[fips] if fips in workdoc.index else None
        ex = exemption.loc[fips] if fips in exemption.index else None
        xp = ex_parte.loc[fips] if fips in ex_parte.index else None

        # v7: read each subgroup's count from its source-stage parquet.
        # SUBGROUP_SOURCE maps the subgroup key to "workdoc" (04b) or
        # "exemption" (04c). The new compliant-side additions (students,
        # volunteering, other_categorical_exempt) all live in 04c's output.
        def _subgroup_count(key: str) -> float:
            src = SUBGROUP_SOURCE.get(key)
            row = wd if src == "workdoc" else ex
            if row is None:
                return 0.0
            col = f"{key}_doc_failures"
            try:
                return float(row[col])
            except (KeyError, TypeError, ValueError):
                return 0.0

        # v7: apply CYCLE_COMPOUNDING_FACTOR to documentation-failure subgroup
        # counts (compliant-doc and exemption-doc buckets) to scale single-cycle
        # snapshots to cumulative 2034 figures. NOT applied to noncompliant_pre
        # (already a steady-state count, not a per-cycle flow).
        workdoc_subs_pre = {
            key: _subgroup_count(key) * config.CYCLE_COMPOUNDING_FACTOR
            for key, _ in WORKDOC_SUBGROUPS
        }
        exemption_subs_pre = {
            key: _subgroup_count(key) * config.CYCLE_COMPOUNDING_FACTOR
            for key, _ in EXEMPTION_SUBGROUPS
        }
        # Bucket totals computed from the subgroup-level numbers — the
        # legacy `total_*_pre_rake` columns no longer match the new bucket
        # structure (students moved from exemption to compliant).
        workdoc_total_pre = sum(workdoc_subs_pre.values())
        exemption_total_pre = sum(exemption_subs_pre.values())
        noncompliant_pre = subject * NONCOMPLIANT_PRE_RAKE_RATE

        if already_work_conditional:
            # Population already faces a state work requirement → no new OBBBA loss.
            workdoc_subs_pre = {key: 0.0 for key, _ in WORKDOC_SUBGROUPS}
            exemption_subs_pre = {key: 0.0 for key, _ in EXEMPTION_SUBGROUPS}
            workdoc_total_pre = exemption_total_pre = noncompliant_pre = 0.0

        # Extract v4 two-factor scores + sub-components from the ex_parte parquet.
        def _opt_int(v):
            try:
                return int(v) if v is not None and pd.notna(v) else None
            except (TypeError, ValueError):
                return None

        if xp is not None:
            historical_score = _opt_int(xp.get("historical_churn"))
            scores = {
                "composite": _opt_int(xp.get("composite")),
                "observed_ex_parte": _opt_int(xp.get("observed_ex_parte")),   # v8
                "core_capability": _opt_int(xp.get("core_capability")),
                "data_sources": _opt_int(xp.get("data_sources")),
                "historical_churn": historical_score,
            }
            core_components = None
            source_components = None
            if scores["composite"] is not None:
                core_components = {
                    "system_integration": _opt_int(xp.get("core_system_integration")),
                    "account_matching": _opt_int(xp.get("core_account_matching")),
                    "deduplication": _opt_int(xp.get("core_deduplication")),
                    "operational_sla": _opt_int(xp.get("core_operational_sla")),
                    "self_attestation_policy": _opt_int(xp.get("core_self_attestation_policy")),
                    "identity_proofing": _opt_int(xp.get("core_identity_proofing")),
                }
                source_components = {
                    "wage_data": _opt_int(xp.get("source_wage_data")),
                    "frailty_data": _opt_int(xp.get("source_frailty_data")),
                    "other_data": _opt_int(xp.get("source_other_data")),
                }
            # Historical churn band (v5).
            if historical_score is None:
                historical_band = None
            elif historical_score >= 70:
                historical_band = "low"
            elif historical_score >= 45:
                historical_band = "mid"
            else:
                historical_band = "high"
            bands = {
                "composite": xp.get("band_composite") if pd.notna(xp.get("band_composite", None)) else None,
                "observed_ex_parte": xp.get("band_observed_ex_parte") if pd.notna(xp.get("band_observed_ex_parte", None)) else None,
                "core_capability": xp.get("band_core_capability") if pd.notna(xp.get("band_core_capability", None)) else None,
                "data_sources": xp.get("band_data_sources") if pd.notna(xp.get("band_data_sources", None)) else None,
                "historical_churn": historical_band,
            }
        else:
            scores = {"composite": None, "observed_ex_parte": None, "core_capability": None, "data_sources": None, "historical_churn": None}
            core_components = None
            source_components = None
            bands = {"composite": None, "observed_ex_parte": None, "core_capability": None, "data_sources": None, "historical_churn": None}

        historical_experience = historical_map.get(fips)

        state_rows.append({
            "fips": fips,
            "abbr": s["state_abbr"],
            "name": s["state_name"],
            "subject_count": subject,
            "ex_parte_score": scores["composite"],          # back-compat alias = composite
            "ex_parte_band": bands["composite"],            # back-compat alias = band_composite
            "scores": scores,
            "core_components": core_components,
            "source_components": source_components,
            "bands": bands,
            "historical_experience": historical_experience,
            "system_vendor": xp.get("system_vendor", "") if xp is not None else "",
            "workdoc_total_pre": workdoc_total_pre,
            "exemption_total_pre": exemption_total_pre,
            "noncompliant_pre": noncompliant_pre,
            "workdoc_subs_pre": workdoc_subs_pre,
            "exemption_subs_pre": exemption_subs_pre,
        })

    # ---- v2 drift report: pre-rake vs prior published breakdown ----
    # If a prior medicaid-loss-breakdown.json exists, compare per-state pre-rake
    # exemption totals against v1's post-rake totals to surface any pathological
    # shifts. This is the alarm bell when 04e introduces a state-level number
    # that diverges meaningfully from v1; state Medicaid directors care.
    prior_state_totals = _load_prior_state_exemption_totals(BREAKDOWN_OUT)
    if prior_state_totals:
        drift_warnings: list[tuple[str, float, float, float]] = []
        for r in state_rows:
            prior_total = prior_state_totals.get(r["fips"])
            if prior_total is None or prior_total <= 0:
                continue
            delta = (r["exemption_total_pre"] / prior_total) - 1.0
            # 25% threshold per plan §B.5.
            if abs(delta) > 0.25:
                drift_warnings.append((r["abbr"], prior_total, r["exemption_total_pre"], delta))
        if drift_warnings:
            print(f"WARN: {len(drift_warnings)} state(s) exemption pre-rake shifted >25% vs v1:")
            for abbr, prior, new, delta in sorted(drift_warnings, key=lambda x: -abs(x[3])):
                print(f"  {abbr}: v1 post-rake {prior:>9,.0f} -> v2 pre-rake {new:>9,.0f}  ({delta:+.0%})")
            print()

    # ---- v5: bottom-up totals (no rake) ----
    nat_workdoc_pre = sum(r["workdoc_total_pre"] for r in state_rows)
    nat_exemption_pre = sum(r["exemption_total_pre"] for r in state_rows)
    nat_noncompliant_pre = sum(r["noncompliant_pre"] for r in state_rows)
    bottom_up_total = nat_workdoc_pre + nat_exemption_pre + nat_noncompliant_pre

    if prior_state_totals:
        prior_exemption_national = sum(prior_state_totals.values())
        nat_delta = (nat_exemption_pre / prior_exemption_national) - 1.0 if prior_exemption_national > 0 else 0
        print(f"v4 exemption-doc post-rake -> v5 exemption-doc bottom-up: "
              f"{prior_exemption_national:>11,.0f} -> {nat_exemption_pre:>11,.0f}  ({nat_delta:+.0%})")
        print(f"  (no rake applied in v5; per-state distribution preserves the bottom-up math)")
        print()

    # Reference points loaded from config: CBO 5.2M baseline, Urban 7.5M, CBPP 10M.
    ref = config.LOSS_BREAKDOWN_REFERENCE
    range_low = ref["acceptable_range_low"]
    range_high = ref["acceptable_range_high"]
    calibration_target = ref["calibration_target"]

    if range_low <= bottom_up_total <= range_high:
        calibration_multiplier = 1.0
        calibration_note = (
            f"Bottom-up total ({bottom_up_total:,.0f}) lands inside the published "
            f"range [{range_low:,.0f}–{range_high:,.0f}] (CBO 5.2M to CBPP 10M). "
            f"No calibration applied; the Sankey is the raw bottom-up output."
        )
    else:
        calibration_multiplier = calibration_target / bottom_up_total if bottom_up_total > 0 else 1.0
        calibration_note = (
            f"Bottom-up total ({bottom_up_total:,.0f}) falls outside the published "
            f"range [{range_low:,.0f}–{range_high:,.0f}]. Applying uniform "
            f"calibration multiplier ×{calibration_multiplier:.3f} to land at the "
            f"CBO+Urban midpoint of {calibration_target:,.0f}. Per-state and "
            f"per-subgroup proportions are preserved; only the absolute scale moves."
        )

    print(f"v5 BOTTOM-UP national totals (pre-calibration):")
    print(f"  work-doc failures:      {nat_workdoc_pre:>11,.0f}")
    print(f"  exemption-doc failures: {nat_exemption_pre:>11,.0f}")
    print(f"  genuinely noncompliant: {nat_noncompliant_pre:>11,.0f}")
    print(f"  TOTAL:                  {bottom_up_total:>11,.0f}  "
          f"(CBO 5.2M / Urban 7.5M / CBPP up to 10M)")
    print()
    print(calibration_note)
    print()

    # ---- Build per-state final breakdown ----
    state_outputs: dict[str, dict] = {}
    nat_workdoc_subs: dict[str, float] = {k: 0.0 for k, _ in WORKDOC_SUBGROUPS}
    nat_exemption_subs: dict[str, float] = {k: 0.0 for k, _ in EXEMPTION_SUBGROUPS}

    for r in state_rows:
        # v5: scale each state's bottom-up numbers by the (possibly 1.0) calibration multiplier.
        wd_total = r["workdoc_total_pre"] * calibration_multiplier
        ex_total = r["exemption_total_pre"] * calibration_multiplier
        nc_total = r["noncompliant_pre"] * calibration_multiplier
        wd_subs = {k: v * calibration_multiplier for k, v in r["workdoc_subs_pre"].items()}
        ex_subs = {k: v * calibration_multiplier for k, v in r["exemption_subs_pre"].items()}

        for k, v in wd_subs.items():
            nat_workdoc_subs[k] += v
        for k, v in ex_subs.items():
            nat_exemption_subs[k] += v

        total_loss = wd_total + ex_total + nc_total
        eligible_but_lose = wd_total + ex_total

        state_entry = {
            "abbr": r["abbr"],
            "name": r["name"],
            "ex_parte_score": r["ex_parte_score"],            # back-compat alias = composite
            "ex_parte_band": r["ex_parte_band"],              # back-compat alias = band_composite
            "scores": r["scores"],                            # v5: composite + core + sources + historical
            "core_components": r["core_components"],
            "source_components": r["source_components"],
            "bands": r["bands"],
            "system_vendor": r["system_vendor"],
            "subject_count": int(round(r["subject_count"])),
            "total_loss_2034": int(round(total_loss)),
            "eligible_but_lose": int(round(eligible_but_lose)),
            "genuinely_noncompliant": int(round(nc_total)),
            "work_hours_doc_failures": {
                "total": int(round(wd_total)),
                "subgroups": {
                    key: {
                        "label": label,
                        "count": int(round(wd_subs[key])),
                        "narrative": ALL_NARRATIVES.get(key, ""),
                    }
                    for key, label in WORKDOC_SUBGROUPS
                },
            },
            "exemption_doc_failures": {
                "total": int(round(ex_total)),
                "subgroups": {
                    key: {
                        "label": label,
                        "count": int(round(ex_subs[key])),
                        "narrative": ALL_NARRATIVES.get(key, ""),
                    }
                    for key, label in EXEMPTION_SUBGROUPS
                },
            },
        }
        if r["historical_experience"]:
            state_entry["historical_experience"] = r["historical_experience"]
        wv = config.waiver_meta(r["fips"])
        if wv:
            state_entry["subject_via_waiver"] = bool(wv.get("control_total", 0) > 0)
            state_entry["already_work_conditional"] = bool(wv.get("already_work_conditional"))
            state_entry["loss_quantified"] = bool(wv.get("loss_quantified", True))
            state_entry["waiver_note"] = wv.get("label")
        state_outputs[r["fips"]] = state_entry

    # ---- v5 drift report: top movers in v4-rake → v5-bottom-up exemption totals ----
    if prior_state_totals:
        movers: list[tuple[str, float, float, float]] = []
        for fips, out in state_outputs.items():
            prior = prior_state_totals.get(fips)
            if prior is None:
                continue
            new = float(out["exemption_doc_failures"]["total"])
            abs_change = new - prior
            movers.append((out["abbr"], prior, new, abs_change))
        if movers:
            movers.sort(key=lambda x: -abs(x[3]))
            print("Top 5 states by absolute change in exemption-doc total (v4 → v5):")
            for abbr, prior, new, abs_change in movers[:5]:
                rel = (new / prior - 1.0) if prior > 0 else 0
                print(f"  {abbr}: {prior:>9,.0f} -> {new:>9,.0f}  ({abs_change:+,.0f}, {rel:+.0%})")
            print()

    # ---- National rollup ----
    nat_workdoc_total = sum(s["work_hours_doc_failures"]["total"] for s in state_outputs.values())
    nat_exemption_total = sum(s["exemption_doc_failures"]["total"] for s in state_outputs.values())
    nat_noncompliant_total = sum(s["genuinely_noncompliant"] for s in state_outputs.values())
    nat_total_loss = nat_workdoc_total + nat_exemption_total + nat_noncompliant_total

    nat_obj = {
        "abbr": "US",
        "name": "United States",
        "ex_parte_score": None,
        "ex_parte_band": None,
        "scores": {"composite": None, "observed_ex_parte": None, "core_capability": None, "data_sources": None, "historical_churn": None},
        "core_components": None,
        "source_components": None,
        "bands": {"composite": None, "observed_ex_parte": None, "core_capability": None, "data_sources": None, "historical_churn": None},
        "system_vendor": "",
        "subject_count": int(sum(r["subject_count"] for r in state_rows)),
        "total_loss_2034": nat_total_loss,
        "eligible_but_lose": nat_workdoc_total + nat_exemption_total,
        "genuinely_noncompliant": nat_noncompliant_total,
        "work_hours_doc_failures": {
            "total": nat_workdoc_total,
            "subgroups": {
                key: {
                    "label": label,
                    "count": int(round(nat_workdoc_subs[key])),
                    "narrative": ALL_NARRATIVES.get(key, ""),
                }
                for key, label in WORKDOC_SUBGROUPS
            },
        },
        "exemption_doc_failures": {
            "total": nat_exemption_total,
            "subgroups": {
                key: {
                    "label": label,
                    "count": int(round(nat_exemption_subs[key])),
                    "narrative": ALL_NARRATIVES.get(key, ""),
                }
                for key, label in EXEMPTION_SUBGROUPS
            },
        },
    }

    # ---- Ex parte capability table (separate from per-state breakdown) ----
    ex_parte_table = []
    for fips, info in config.STATE_INFO.items():
        xp = ex_parte.loc[fips] if fips in ex_parte.index else None
        if xp is None:
            continue
        composite = _opt_int(xp.get("composite"))
        observed_score = _opt_int(xp.get("observed_ex_parte"))   # v8
        core_score = _opt_int(xp.get("core_capability"))
        sources_score = _opt_int(xp.get("data_sources"))
        historical_score = _opt_int(xp.get("historical_churn"))
        observed_rate_raw = xp.get("observed_ex_parte_rate")
        try:
            observed_rate_raw = float(observed_rate_raw) if observed_rate_raw is not None and pd.notna(observed_rate_raw) else None
        except (TypeError, ValueError):
            observed_rate_raw = None
        if composite is not None:
            core_components = {
                "system_integration": _opt_int(xp.get("core_system_integration")),
                "account_matching": _opt_int(xp.get("core_account_matching")),
                "deduplication": _opt_int(xp.get("core_deduplication")),
                "operational_sla": _opt_int(xp.get("core_operational_sla")),
                "self_attestation_policy": _opt_int(xp.get("core_self_attestation_policy")),
                "identity_proofing": _opt_int(xp.get("core_identity_proofing")),
            }
            source_components = {
                "wage_data": _opt_int(xp.get("source_wage_data")),
                "frailty_data": _opt_int(xp.get("source_frailty_data")),
                "other_data": _opt_int(xp.get("source_other_data")),
            }
        else:
            core_components = None
            source_components = None
        if historical_score is None:
            historical_band = None
        elif historical_score >= 70:
            historical_band = "low"
        elif historical_score >= 45:
            historical_band = "mid"
        else:
            historical_band = "high"
        ex_parte_table_entry = {
            "fips": fips,
            "abbr": info["abbr"],
            "name": info["name"],
            # Back-compat: top-level score / band = composite values.
            "score": composite,
            "band": xp.get("band_composite") if pd.notna(xp.get("band_composite", None)) else None,
            # v8: observed-rate-led scoring (observed dominant; core = context).
            "scores": {
                "composite": composite,
                "observed_ex_parte": observed_score,
                "core_capability": core_score,
                "data_sources": sources_score,
                "historical_churn": historical_score,
            },
            "observed_ex_parte_rate": observed_rate_raw,
            "core_components": core_components,
            "source_components": source_components,
            "bands": {
                "composite": xp.get("band_composite") if pd.notna(xp.get("band_composite", None)) else None,
                "observed_ex_parte": xp.get("band_observed_ex_parte") if pd.notna(xp.get("band_observed_ex_parte", None)) else None,
                "core_capability": xp.get("band_core_capability") if pd.notna(xp.get("band_core_capability", None)) else None,
                "data_sources": xp.get("band_data_sources") if pd.notna(xp.get("band_data_sources", None)) else None,
                "historical_churn": historical_band,
            },
            "system_vendor": xp.get("system_vendor", ""),
            "notes": xp.get("notes", ""),
            "expansion": info["expansion"],
            "subject_via_waiver": bool(config.waiver_meta(fips).get("control_total", 0) > 0),
            "waiver_listed": bool(config.waiver_meta(fips)),
            "loss_quantified": bool(config.waiver_meta(fips).get("loss_quantified", True)),
            "already_work_conditional": bool(config.waiver_meta(fips).get("already_work_conditional", False)),
            "flags": {
                "medicaid_claims_match": bool(xp.get("flag_medicaid_claims_match", False)),
                "behavioral_health_mco_match": bool(xp.get("flag_behavioral_health_mco_match", False)),
                "ui_wage_match": bool(xp.get("flag_ui_wage_match", False)),
                "snap_tanf_compliance_match": bool(xp.get("flag_snap_tanf_compliance_match", False)),
                "corrections_records_match": bool(xp.get("flag_corrections_records_match", False)),
                "child_welfare_records_match": bool(xp.get("flag_child_welfare_records_match", False)),
                "vital_records_match": bool(xp.get("flag_vital_records_match", False)),            # v4 NEW
                "workforce_dev_records_match": bool(xp.get("flag_workforce_dev_records_match", False)),  # v4 NEW
                "self_attestation_accepted": bool(xp.get("flag_self_attestation_accepted", False)),
            },
        }
        hx = historical_map.get(fips)
        if hx:
            ex_parte_table_entry["historical_experience"] = hx
        ex_parte_table.append(ex_parte_table_entry)
    # Sort by expansion-then-composite-desc, with non-expansion at bottom alphabetical
    ex_parte_table.sort(key=lambda r: (
        0 if r["expansion"] else 1,
        -(r["score"] or 0),
        r["abbr"],
    ))

    payload = {
        "version": "v8.0-2026-05-30",
        "vintage": {
            "acs_pums": "5-Year 2020-2024 (full-PUMS mode; cache schema v6 — Section 1931 + non-citizen subject-pool refinement, AI/AN + combination-of-activities counts)",
            "kff_survey": "May 2026 implementation survey",
            "cbo": "June 2025 OBBBA scoring",
            "ex_parte_scoring": "v8 observed-rate-led (observed ex parte 50% + data sources 35% + historical 15%); core capability shown as context only. Observed rate = CMS eligibility-processing data 2023-03 to 2026-02. Source weights within data-sources score 50/30/20",
            "subject_pool_refinement": "v8 (Esty review 2): Section 1931 parents (below state 1931 % FPL limit) removed as non-expansion/not-subject; recent non-citizens (CIT=5 within 5-year bar) removed; both fix composition while the national level stays raked to CBO 18.5M",
            "exemption_subgroup_params": "v7: medical frailty prior 0.25→0.28; students moved to compliant bucket; v8: AI/AN split into its own PUMS-derived (RACAIAN) line out of the other-categorical bundle",
            "compounding": "v7: CYCLE_COMPOUNDING_FACTOR=1.15 applied to documentation-failure buckets to scale single-cycle bottom-up to cumulative 2034 figure (14 six-month renewal cycles)",
            "historical_experience": "Sourced scores for AR (Sommers 2019 NEJM), NH (Philbrick v. Azar 2019), GA Pathways (KFF tracking 2023-25), KY (Stewart v. Azar 2018); neutral 50 prior elsewhere",
        },
        "national_targets": {
            "total_loss_2034": TARGET_TOTAL_LOSS,                 # legacy field
            "noncompliant_share": TARGET_NONCOMPLIANT_SHARE,      # legacy field
            "workdoc_share": TARGET_WORKDOC_SHARE,                # legacy field
            "exemption_share": TARGET_EXEMPTION_SHARE,            # legacy field
            # v5: bottom-up methodology fields.
            "v5_methodology": "bottom_up_no_rake",
            "v5_bottom_up_total": int(round(bottom_up_total)),
            "v5_calibration_multiplier": round(calibration_multiplier, 4),
            "v5_calibration_applied": calibration_multiplier != 1.0,
            "v5_cbo_baseline": ref["cbo_baseline_2034"],
            "v5_urban_midpoint": ref["urban_midpoint_2034"],
            "v5_cbpp_upper": ref["cbpp_upper_2034"],
        },
        "_national": nat_obj,
        "states": state_outputs,
        "ex_parte_table": ex_parte_table,
    }

    BREAKDOWN_OUT.write_text(json.dumps(payload, indent=2))
    LOCAL_OUT.write_text(json.dumps(payload, indent=2))

    print("Post-rake national totals:")
    print(f"  work-doc:      {nat_workdoc_total:>11,d}  ({nat_workdoc_total/nat_total_loss:.1%} of total)")
    print(f"  exemption-doc: {nat_exemption_total:>11,d}  ({nat_exemption_total/nat_total_loss:.1%} of total)")
    print(f"  non-compliant: {nat_noncompliant_total:>11,d}  ({nat_noncompliant_total/nat_total_loss:.1%} of total)")
    print(f"  total:         {nat_total_loss:>11,d}  (target {TARGET_TOTAL_LOSS:,})")
    print()
    print("Top 8 states by total projected loss:")
    top = sorted(state_outputs.values(), key=lambda s: -s["total_loss_2034"])[:8]
    for s in top:
        print(f"  {s['abbr']}  total {s['total_loss_2034']:>10,d}  "
              f"(workdoc {s['work_hours_doc_failures']['total']:>8,d}  "
              f"exemption {s['exemption_doc_failures']['total']:>8,d}  "
              f"non-compliant {s['genuinely_noncompliant']:>7,d})  "
              f"ex parte band: {s['ex_parte_band']}")

    print()
    print(f"-> {BREAKDOWN_OUT.relative_to(config.REPO_ROOT)}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 07b done in {time.time() - t0:.1f}s")
