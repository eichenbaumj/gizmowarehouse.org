"""Stage 04c — build per-state exemption-documentation-failure breakdown.

These are the people who are CATEGORICALLY EXEMPT under OBBBA §1902(xx) but
who will lose Medicaid coverage anyway because their exemption can't be
verified in time, every month, through whatever paperwork their state's
eligibility system demands.

This is half of the "social safety net with holes" story. The other half —
work-hours documentation failures — comes from stage 04b.

Subgroups (6):
  medically_frail_no_match    — disability/chronic condition not in state Medicaid
                                claims data or BH MCO enrollment
  caregivers_no_match         — parent/caretaker of child ≤13 whose status isn't
                                in child welfare / vital records data
  sud_not_flagged             — SUD treatment not flagged in claims data
  recent_incarc_data_gap      — recently released but corrections records
                                aren't talking to the eligibility system
  students_no_match           — full-time student status not auto-verified
                                against state registrar / FAFSA data
  pregnancy_lag               — pregnancy / postpartum lagged in claims data

Methodology:
  exemption_eligible_count = state_expansion_pool × national_exemption_rate
  failure_rate = base_rate × ex_parte_attenuation
    where base_rate per subgroup is anchored to Sommers Arkansas 2018 evidence
    and ex_parte_attenuation depends on the relevant state flag(s) being true.
  doc_failure_count = exemption_eligible × failure_rate

Sources for the parameters:
  - Sommers et al. (2019) NEJM, Arkansas 1115 work-req evaluation
  - KFF "An Early Look at Policy Decisions" (May 2026)
  - KFF survey of state medically-frail verification approaches
  - SAMHSA NSDUH 2023 state-level SUD prevalence
  - BJS NPS state-level recent-release rates
  - Urban Institute HIPSM 2028 high vs low mitigation parameter ranges

Output:
  output/state_exemption_doc_failures.parquet — columns:
      state_fips, state_abbr, state_name, expansion_pool, ex_parte_score,
      and per-subgroup columns:
        {subgroup}_eligible          — N exemption-eligible enrollees
        {subgroup}_doc_fail_rate     — rate
        {subgroup}_doc_failures      — N who will lose coverage despite eligibility
      total_exemption_doc_failures   — sum across subgroups

Pre-rake totals. Stage 07 will rake the national total to ~50% of CBO loss
(roughly 2.3-2.5M nationally).

Run: python 04c_build_exemption_breakdown.py
"""

from __future__ import annotations

import json
import sys
import time

import pandas as pd

import config

STATE_SUMMARY_IN = config.PUBLIC_DATA_DIR / "medicaid-state-summary.json"
EX_PARTE_IN = config.OUTPUT_DIR / "state_ex_parte_scored.parquet"
STATE_EXEMPTION_RATES_IN = config.OUTPUT_DIR / "state_exemption_rates.parquet"
EXEMPTION_OUT = config.OUTPUT_DIR / "state_exemption_doc_failures.parquet"

# Subject pool / expansion pool ratio. CBO scores 18.5M subject from
# ~21M total expansion enrollment (KFF), so subject ≈ 88% of expansion. We use
# the inverse to back out expansion_pool from the per-state subject_count_strict
# when the pipeline hasn't surfaced expansion_pool directly.
SUBJECT_TO_EXPANSION_RATIO = 0.88

# Six exemption-doc-failure subgroups. Each maps to:
#   - the national prior share of the expansion pool (from config or local)
#   - which ex-parte flag(s) drive auto-match success
#   - the base failure rate when the flag is FALSE (anchored to Sommers 2019)
#   - the attenuation when the flag is TRUE (reflects partial-but-imperfect match)
#
# The base failure rate reflects: of all enrollees who *should* qualify for this
# exemption, what fraction will be terminated for failure to verify in a state
# with no auto-match infrastructure (Arkansas-grade baseline). The attenuation
# factor is multiplied in when the state's flag is TRUE.
SUBGROUPS = {
    "medically_frail_no_match": {
        "label": "Medically frail without auto-match",
        # v2: per-state eligibility rate from stage 04e (PUMS DIS × specific
        # functional-impairment flags, Medicaid+income filtered). v1's national
        # prior is retained as the fallback when 04e produces a NaN for a state.
        "rate_key_04e": "medically_frail",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["medically_frail"],
        "drivers": ["medicaid_claims_match", "behavioral_health_mco_match"],
        # v4: raised from 0.45 → 0.65 to reflect that medical-frailty
        # documentation is structurally the hardest exemption to prove.
        # Even Sommers 2019's Arkansas 45% was a floor for disability-eligible
        # adults; OBBBA's "complex medical or behavioral-health condition"
        # standard is narrower than "has a disability," and requires recurring
        # provider letters that don't propagate cleanly from claims data.
        "base_failure_rate": 0.65,
        # v4: weakened from 0.50 → 0.65 (each TRUE flag now only reduces
        # residual by 35% instead of 50%). Even claims-match states miss the
        # OBBBA functional-impairment specifics; BH MCO data covers SMI/SUD
        # but not somatic chronic conditions.
        "attenuation_per_driver": 0.65,
        # v4: raised from 0.08 → 0.15. The recurring nature of provider
        # letters resists automation even in CalSAWS-grade states.
        "min_floor": 0.15,
        "narrative": (
            "Medical frailty is the OBBBA exemption with the highest documentation "
            "friction. Even in states with Medicaid claims data flowing into the "
            "eligibility system, the exemption requires evidence of meeting CMS "
            "criteria for 'complex medical or behavioral-health condition' — a "
            "narrower standard than 'has a disability.' That typically requires a "
            "recurring provider letter: a clinic appointment (often weeks out), "
            "provider workload, and the patient remembering to bring the form back. "
            "Behavioral-health MCO data covers the SMI/SUD subset but not somatic "
            "chronic conditions. Sommers 2019 measured ~45% loss among "
            "disability-eligible Arkansas enrollees in a state with zero auto-match; "
            "we hold close to that for high-churn states and floor at 15% even for "
            "high-integration states because the recurring nature of provider "
            "letters resists automation."
        ),
    },
    "caregivers_no_match": {
        "label": "Parent caregivers of children ≤13 without auto-match",
        # Per-state rate from 04e (PUMS household linkage SERIALNO × RELSHIPP for parents).
        "rate_key_04e": "parent_caretaker_child_under_14",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["parent_caretaker_child_under_14"],
        "drivers": ["child_welfare_records_match"],
        # v4: lowered from 0.30 → 0.16. Birth certificates, school enrollment,
        # and tax-dependent records are easy one-time productions; 30% was too
        # high for an exemption with such straightforward documentation.
        # v5: When the parent is also a Medicaid enrollee, the state has the
        # child's case linked to the household — the exemption should auto-apply
        # without the parent doing anything. The remaining failures concentrate
        # in blended/separated families, mixed-status households, and homeschool
        # arrangements.
        "base_failure_rate": 0.16,
        "attenuation_per_driver": 0.25,
        "min_floor": 0.04,
        "narrative": (
            "Birth parents and legal caretakers of children 13 or under who "
            "qualify for the categorical exemption but lose coverage anyway. "
            "When the parent is also a Medicaid enrollee, the child's case in "
            "the state's eligibility system already carries the household "
            "linkage — the parent's exemption should auto-apply without anyone "
            "filling out a form. The failures concentrate in three patterns: "
            "address mismatches common in blended and separated families, "
            "mixed-status households where parents avoid government data "
            "systems, and children too young for school records (under 5, "
            "homeschooled). Non-traditional kinship arrangements are tracked "
            "in a separate subgroup; this row is parents only."
        ),
    },
    "kinship_caregivers_other": {
        "label": "Kinship caregivers (non-parent) of children ≤13",
        # v5: split out from caregivers_no_match. v6: 04e now computes per-state
        # rates from PUMS RELSHIPP-based household-structure inference.
        "rate_key_04e": "kinship_caregivers",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["kinship_caregivers"],
        "drivers": ["child_welfare_records_match"],
        # Higher base failure rate than parent caregivers because the child's
        # Medicaid case typically doesn't link the kinship caregiver — birth
        # certificate, school enrollment, and tax-dependent records all point
        # to the biological parents. Documentation requires guardianship orders
        # or sworn affidavits, neither of which auto-flow into state systems.
        "base_failure_rate": 0.55,
        "attenuation_per_driver": 0.50,
        "min_floor": 0.18,
        "narrative": (
            "Grandparents, aunts and uncles, older siblings, and other "
            "non-parent kinship caregivers who function as the primary "
            "caretaker for a child 13 or under. Per Annie E. Casey 2023 KIDS "
            "COUNT, roughly 7% of US children in low-income families live in "
            "non-parent kinship arrangements, but their relationship is rarely "
            "captured in the data sources state eligibility systems consult. "
            "Birth certificates, school enrollment records, and tax-dependent "
            "filings all point to the biological parent. The kinship caregiver "
            "must produce a guardianship order or a sworn affidavit through the "
            "portal, often without the family-court paperwork to back it up. "
            "This has been a quiet but sizable issue in the HR1 implementation "
            "dialogue and one we expect to surface in early-implementer states."
        ),
    },
    "caregivers_disabled_adult": {
        "label": "Caregivers of a disabled adult",
        # v5: introduced as uniform prior. v6: 04e now computes per-state
        # rates via PUMS SERIALNO household linkage to a working-age disabled
        # adult, with primary-caregiver heuristic (spouse > householder > eldest).
        "rate_key_04e": "caregivers_disabled_adult",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["caregivers_disabled_adult"],
        # No good admin flag exists — caregiving status for an adult is not in
        # any state data feed. Vital records and child welfare data don't apply.
        # The closest hook is SSI/SSDI for the care recipient + household
        # linkage, which is rarely operationalized.
        "drivers": [],
        # Very high base failure rate because no admin data flow exists. This
        # is essentially a manual-only exemption pathway.
        "base_failure_rate": 0.70,
        "attenuation_per_driver": 1.0,  # no drivers, attenuation is moot
        "min_floor": 0.30,
        "narrative": (
            "Adults caring for a disabled family member: an elderly parent, an "
            "adult child with a developmental disability, a spouse with a "
            "chronic illness. AARP/NAC 2020 estimates that roughly 1 in 6 US "
            "adults provides unpaid care to an adult; for low-income working-"
            "age adults the share is somewhat lower, and the subset where the "
            "care recipient has a documented disability that qualifies the "
            "caregiver for an OBBBA exemption is around 3-4%. There is no good "
            "administrative data flow for the relationship. SSI/SSDI records on "
            "the care "
            "recipient plus household linkage exist in theory but are rarely "
            "operationalized at the state level. The exemption requires a "
            "physician letter for the care recipient's condition plus proof of "
            "the caregiving relationship, both manual. Expect high failure "
            "rates everywhere until states build dedicated workflows."
        ),
    },
    "sud_not_flagged": {
        "label": "SUD treatment not flagged in claims data",
        # v2: per-state rate from 04e (SAMHSA NSDUH 2023-2024 state SUD prevalence
        # × national 35% treatment-engagement multiplier).
        "rate_key_04e": "sud_treatment",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["sud_treatment"],
        "drivers": ["behavioral_health_mco_match", "medicaid_claims_match"],
        # v4: 0.55 → 0.50. Modest reduction for proportional rebalance.
        "base_failure_rate": 0.50,
        "attenuation_per_driver": 0.45,
        "min_floor": 0.10,
        "narrative": (
            "Adults in substance-use treatment whose engagement isn't visible to "
            "the eligibility system. Behavioral-health MCO data covers medication-"
            "assisted treatment (MAT) and structured outpatient enrollment, but "
            "informal recovery — 12-step participation, peer support, intensive "
            "outpatient not billed through the MCO — is invisible to the state's "
            "data. The floor stays at 10% because some forms of "
            "recovery-supportive activity will never appear in claims data, even "
            "in states with mature behavioral-health integration."
        ),
    },
    "recent_incarc_data_gap": {
        "label": "Recent incarceration (data-match gap)",
        # v2: per-state rate from 04e (BJS NPS state releases calibrated so the
        # national-weighted-mean honors the 0.008 prior; NPS gives relative
        # variation, prior gives the level since NPS excludes jails).
        "rate_key_04e": "recent_incarceration",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["recent_incarceration"],
        "drivers": ["corrections_records_match"],
        # v4: 0.60 → 0.55. Modest reduction.
        "base_failure_rate": 0.55,
        "attenuation_per_driver": 0.40,
        "min_floor": 0.12,
        "narrative": (
            "Adults recently released from incarceration who qualify for the "
            "post-release exemption. State DOC data-share agreements with the "
            "Medicaid eligibility system are uncommon and, where they exist, "
            "typically cover state corrections only, not county jails (which "
            "account for roughly 60% of corrections churn) or federal "
            "facilities. Returning citizens released from jails, federal "
            "prisons, or out-of-state facilities have to self-report, often "
            "without a stable address for portal mail. Expect this number to "
            "run high for states that lack the data-sharing agreement, and we "
            "may revise it upward as state implementation reports land."
        ),
    },
    "students_no_match": {
        "label": "Full-time students not auto-verified",
        # v2: per-state rate from 04e (PUMS SCH ∈ {2,3} × SCHG ≥ 15).
        "rate_key_04e": "full_time_student",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["full_time_student"],
        # Student verification is harder than usual because there's no central
        # federal data feed. We use snap_tanf_compliance_match as a weak proxy
        # for general data-sharing maturity and self_attestation_accepted as the
        # only realistic alternative.
        "drivers": ["self_attestation_accepted", "snap_tanf_compliance_match"],
        # v4: 0.50 → 0.40. Modest reduction.
        "base_failure_rate": 0.40,
        "attenuation_per_driver": 0.35,
        "min_floor": 0.08,
        "narrative": (
            "Full-time students at qualifying institutions. The National "
            "Student Clearinghouse runs a broadly-available API that covers "
            "roughly 97% of US degree-granting institutions; states that have "
            "stood up the NSC integration can ex-parte-verify student status "
            "for most enrollees automatically. Failures concentrate in states "
            "that haven't integrated NSC (which is most of them — FAFSA data "
            "is sealed by federal privacy rules, so NSC is the practical "
            "alternative). In those states the student must produce a "
            "registrar letter every renewal cycle; self-attestation is the "
            "backstop where the portal accepts it."
        ),
    },
    "pregnancy_lag": {
        "label": "Pregnancy / postpartum data lag",
        # v4: pregnancy is no longer treated like other exemptions. OBBBA
        # §1902(xx)(4)(D)(ii) permits self-attestation; the failure rate
        # should approach zero. The residual reflects only edge cases.
        "rate_key_04e": "pregnant_postpartum",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["pregnant_postpartum"],
        "drivers": ["medicaid_claims_match"],
        # v4: 0.25 → 0.03. Dramatic reduction because self-attestation is
        # the statutory default.
        "base_failure_rate": 0.03,
        "attenuation_per_driver": 0.50,
        # v4: 0.05 → 0.01. Lets the median state run near zero.
        "min_floor": 0.01,
        "narrative": (
            "OBBBA §1902(xx)(4)(D)(ii) permits self-attestation for pregnancy, so "
            "the failure rate should approach zero. The surviving residual reflects "
            "five edge cases: (a) unknown pregnancies, since roughly 5 to 10% of "
            "women aren't aware until weeks 8 to 12 and can't attest to something "
            "they don't know; (b) postpartum data lag, since the 60-day postpartum "
            "window starts at delivery while state claims data typically lags 15 to "
            "45 days, so women fall off coverage mid-window even though they remain "
            "biologically eligible; (c) pregnancy-loss cases, since miscarriage and "
            "stillbirth carry forward postpartum eligibility (per CMS SHO 2022 "
            "guidance) but state systems don't cleanly capture fetal-demise events; "
            "(d) crisis non-engagement among DV survivors and women with immigration "
            "concerns who qualify but never claim it; and (e) state-level operational "
            "failures where some states may de facto require an attached provider "
            "letter despite the statutory self-attestation language, particularly "
            "during 2027 implementation chaos. Base rate 0.03 with floor 0.01 lets "
            "the median state run near zero while leaving headroom for a few "
            "low-integration states with operational gaps."
        ),
    },
    # v7 NEW (Esty review follow-up): "compliant via volunteer or job-training
    # hours" subgroup. Lives in 04c for code reuse (same per-state-rate
    # machinery) but is routed to the COMPLIANT-DOC bucket in 07b, not the
    # exemption-doc bucket. Sarah Esty: "compliant" is a legal category
    # (work/school/volunteering); exempt is medical/caregiving/etc.
    "volunteering_job_training": {
        "label": "Volunteering / job training (compliant, but can't prove it)",
        "rate_key_04e": "volunteering_job_training",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["volunteering_job_training"],
        # The only relevant admin pathway is DOL/WIOA workforce-development records;
        # volunteer hours are not centrally tracked. High failure rate.
        "drivers": ["workforce_dev_records_match", "self_attestation_accepted"],
        "base_failure_rate": 0.60,
        "attenuation_per_driver": 0.55,
        "min_floor": 0.20,
        "narrative": (
            "Adults meeting the 80-hour OBBBA requirement through volunteer hours "
            "at a qualifying nonprofit or through enrollment in a DOL/WIOA-funded "
            "job-training program. CPS Volunteering Supplement + DOL WIOA "
            "participant data suggest roughly 1.5% of low-income working-age "
            "adults participate at this intensity. There is no centralized data "
            "feed for volunteer hours, and only a handful of states have "
            "WIOA-to-Medicaid data sharing in place. The failure rate is high "
            "everywhere; most of this group has to self-attest and supply a "
            "coordinator letter through the portal, which catches the same "
            "operational friction that other manual-documentation subgroups hit."
        ),
    },
    # v8 NEW (Esty review 2): AI/AN tribal members, pulled out of the v7 bundle
    # as their own line. American Indians and Alaska Natives are exempt under
    # OBBBA, and — unlike the rest of the bundle — they ARE observable in PUMS
    # (RACAIAN), so 04e derives a per-state eligibility rate. The verification
    # pathway is tribal/IHS enrollment data, which few state eligibility systems
    # consume; self-attestation is the practical backstop. Sarah Esty: "We
    # should be able to pull AI/AN."
    "ai_an_exempt": {
        "label": "American Indian / Alaska Native (tribal exemption)",
        "rate_key_04e": "ai_an_exempt",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["ai_an_exempt"],
        "drivers": ["self_attestation_accepted"],
        "base_failure_rate": 0.45,
        "attenuation_per_driver": 0.50,
        "min_floor": 0.12,
        "narrative": (
            "American Indians and Alaska Natives are categorically exempt from "
            "the OBBBA work requirement. Unlike the other small categorical "
            "groups, they're identifiable in the Census (the ACS PUMS RACAIAN "
            "recode), so this subgroup is sized per state from microdata rather "
            "than a flat national prior — it runs higher in states with large "
            "tribal populations (AK, NM, OK, MT, the Dakotas, AZ). The exemption "
            "should auto-apply where the state consumes IHS or tribal-enrollment "
            "data, but few eligibility systems do; absent that, the enrollee must "
            "self-attest or document tribal membership through the portal. States "
            "with a clear self-attestation policy fare much better here."
        ),
    },
    # v7 NEW (Esty review follow-up); v8 trimmed: bundled small categorical-
    # exemption populations that remain unobservable in PUMS — former foster
    # youth aged out under 26, AYA cancer survivors, and the SNAP/TANF work-req
    # compliant subset that doesn't auto-flow into Medicaid. (AI/AN was split
    # into its own line above in v8.) They sum to ~1.4% of expansion adults.
    "other_categorical_exempt": {
        "label": "Other categorical exemptions (foster youth, AYA cancer, SNAP/TANF)",
        "rate_key_04e": "other_categorical_exempt",
        "national_eligible_rate": config.NATIONAL_EXEMPTION_RATES["other_categorical_exempt"],
        # Two main admin pathways: SNAP/TANF data share (covers the
        # work-req-compliant subset) and child welfare records (covers foster
        # youth). AYA cancer survivor has no clean state-level admin pathway.
        "drivers": ["snap_tanf_compliance_match", "child_welfare_records_match"],
        "base_failure_rate": 0.50,
        "attenuation_per_driver": 0.60,
        "min_floor": 0.15,
        "narrative": (
            "A bundle of small but distinct categorical-exemption populations "
            "that aren't observable in the Census: former foster youth who aged "
            "out under 26 (~0.4% of expansion adults per AFCARS and Annie E. "
            "Casey), AYA cancer survivors (~0.1% per NCI SEER), and the share of "
            "SNAP/TANF work-requirement compliant adults whose status isn't "
            "auto-flowed into the Medicaid eligibility system (~0.9%). (AI/AN "
            "tribal members, also exempt, are now shown as their own line.) "
            "State variation depends mostly on whether the state has "
            "SNAP/TANF-to-Medicaid data sharing wired up and whether the "
            "child-welfare integration covers aged-out former foster youth."
        ),
    },
}


def _check_inputs() -> bool:
    ok = True
    if not STATE_SUMMARY_IN.exists():
        print(f"ERROR: {STATE_SUMMARY_IN} missing. Run stages 01-07 (or use prior outputs).", file=sys.stderr)
        ok = False
    if not EX_PARTE_IN.exists():
        print(f"ERROR: {EX_PARTE_IN} missing. Run stage 04d first.", file=sys.stderr)
        ok = False
    if not STATE_EXEMPTION_RATES_IN.exists():
        print(f"WARN: {STATE_EXEMPTION_RATES_IN} missing. Run stage 04e to enable "
              f"state-derived eligibility rates. Falling back to NATIONAL_EXEMPTION_RATES "
              f"for all states/subgroups.", file=sys.stderr)
        # Not a hard error — 04c remains runnable against the v1 fallback (national priors).
    return ok


def state_failure_rate(subgroup_meta: dict, state_row: pd.Series) -> float:
    """Compute the doc-failure rate for one subgroup in one state.

    base_rate × prod_over_drivers(attenuation if flag else 1.0), with min floor.
    """
    rate = subgroup_meta["base_failure_rate"]
    for driver in subgroup_meta["drivers"]:
        col = f"flag_{driver}"
        if state_row.get(col, False):
            rate *= subgroup_meta["attenuation_per_driver"]
    # Additional attenuation for high-integration-bonus states (CalSAWS-grade)
    if state_row.get("integration_bonus", 0) >= 15:
        rate *= 0.80
    return max(rate, subgroup_meta["min_floor"])


def blend_waiver_to_national_avg(df: pd.DataFrame) -> pd.DataFrame:
    """Re-rate subject-via-waiver states (WI/GA) at the expansion-pool-weighted
    national AVERAGE per-subgroup exemption-doc-failure rate, instead of the
    unattenuated base rate they'd otherwise get for lacking an ex parte row. See
    the matching helper in stage 04b for the rationale. Eligible counts (which
    carry the childless-only parent zeroing) are preserved; only the failure RATE
    is replaced, then failures and the row total are recomputed."""
    waiver = {f for f, w in config.WAIVER_SUBJECT.items() if w.get("control_total", 0) > 0}
    is_w = df["state_fips"].isin(waiver)
    if not is_w.any():
        return df
    exp = df[~is_w]
    for key in SUBGROUPS:
        rate_col, elig_col, fail_col = f"{key}_doc_fail_rate", f"{key}_eligible", f"{key}_doc_failures"
        if rate_col not in df.columns or elig_col not in df.columns:
            continue
        w = exp["expansion_pool"].to_numpy(dtype=float)
        r = exp[rate_col].to_numpy(dtype=float)
        natl = float((r * w).sum() / w.sum()) if w.sum() > 0 else float(r.mean())
        df.loc[is_w, rate_col] = natl
        df.loc[is_w, fail_col] = df.loc[is_w, elig_col] * natl
    fail_cols = [f"{k}_doc_failures" for k in SUBGROUPS if f"{k}_doc_failures" in df.columns]
    df.loc[is_w, "total_exemption_doc_failures_pre_rake"] = df.loc[is_w, fail_cols].sum(axis=1)
    return df


def main() -> None:
    if not _check_inputs():
        sys.exit(1)

    summary = json.loads(STATE_SUMMARY_IN.read_text())
    ex_parte = pd.read_parquet(EX_PARTE_IN).set_index("state_fips")

    # v2: per-state eligibility rates from stage 04e (PUMS + SAMHSA + BJS).
    # Falls through to NATIONAL_EXEMPTION_RATES per row if 04e output is absent
    # or if a specific state-subgroup rate is NaN.
    if STATE_EXEMPTION_RATES_IN.exists():
        state_rates = pd.read_parquet(STATE_EXEMPTION_RATES_IN).set_index("state_fips")
        print(f"Loaded per-state eligibility rates from 04e ({len(state_rates)} states).")
    else:
        state_rates = None
        print("No 04e output found — using NATIONAL_EXEMPTION_RATES uniformly (v1 behavior).")

    rows = []
    fallback_log: dict[str, list[str]] = {k: [] for k in SUBGROUPS}

    for s in summary["states"]:
        fips = s["state_fips"]
        # Expansion states + subject-via-1115-waiver states (WI/GA, which carry an
        # admin-anchored pool from stage 04). True non-expansion states and TN
        # have pool 0 and fall out below. Waiver states have no 04e per-state
        # rate, so they use NATIONAL_EXEMPTION_RATES via the per-cell fallback.
        if not s["expansion"] and not s.get("subject_via_waiver"):
            continue
        # expansion_pool from explicit field if present (real pipeline run),
        # otherwise back-derived from subject_count_strict (placeholder/v0 run).
        if "expansion_pool" in s and s["expansion_pool"] > 0:
            pool = float(s["expansion_pool"])
        else:
            pool = float(s["subject_count_strict"]) / SUBJECT_TO_EXPANSION_RATIO
        if pool <= 0:
            continue
        ex_row = ex_parte.loc[fips] if fips in ex_parte.index else None
        state_rate_row = state_rates.loc[fips] if (state_rates is not None and fips in state_rates.index) else None
        row = {
            "state_fips": fips,
            "state_abbr": s["state_abbr"],
            "state_name": s["state_name"],
            "expansion_pool": pool,
            "ex_parte_score": int(ex_row["score"]) if ex_row is not None and pd.notna(ex_row.get("score")) else None,
            "ex_parte_band": (ex_row["churn_band"] if ex_row is not None else None),
        }

        total_failures = 0.0
        for key, meta in SUBGROUPS.items():
            # Per-state eligibility rate from 04e, with per-cell fallback to the
            # national prior if the 04e file is absent or the rate is NaN.
            rate_key = meta["rate_key_04e"]
            rate_col = f"{rate_key}_rate"
            source_col = f"{rate_key}_source"
            national_prior = meta["national_eligible_rate"]
            if state_rate_row is not None and rate_col in state_rate_row and pd.notna(state_rate_row[rate_col]):
                eligible_rate = float(state_rate_row[rate_col])
                rate_source = str(state_rate_row.get(source_col, "unknown"))
            else:
                eligible_rate = national_prior
                rate_source = "national_fallback"
                fallback_log[key].append(s["state_abbr"])

            # Childless-only waiver populations (WI) have no parent/caretaker-of-a-
            # child exemption — zero it so we don't model phantom parent
            # documentation failures for a population with no minor children.
            if rate_key == "parent_caretaker_child_under_14" and config.waiver_meta(fips).get("childless_only"):
                eligible_rate = 0.0
                rate_source = "childless_waiver_na"

            eligible = pool * eligible_rate
            failure_rate = state_failure_rate(meta, ex_row) if ex_row is not None else meta["base_failure_rate"]
            failures = eligible * failure_rate
            row[f"{key}_eligible"] = eligible
            row[f"{key}_eligible_rate"] = eligible_rate
            row[f"{key}_rate_source"] = rate_source
            row[f"{key}_doc_fail_rate"] = failure_rate
            row[f"{key}_doc_failures"] = failures
            total_failures += failures

        row["total_exemption_doc_failures_pre_rake"] = total_failures
        rows.append(row)

    # Log fallbacks (one line per subgroup-set, only if non-empty)
    for k, fallbacks in fallback_log.items():
        if fallbacks:
            print(f"  national_fallback for {k}: {', '.join(sorted(set(fallbacks)))}", file=sys.stderr)

    df = pd.DataFrame(rows)
    df = blend_waiver_to_national_avg(df)
    df = df.sort_values("total_exemption_doc_failures_pre_rake", ascending=False)
    df.to_parquet(EXEMPTION_OUT, index=False)

    nat_total = df["total_exemption_doc_failures_pre_rake"].sum()
    target_low = 0.45 * config.CROSS_VALIDATION_TARGETS["cbo_national_loss_2034"]
    target_high = 0.55 * config.CROSS_VALIDATION_TARGETS["cbo_national_loss_2034"]

    print(f"Built exemption-doc-failure breakdown for {len(df)} expansion states + DC.")
    print(f"Pre-rake national total: {nat_total:>11,.0f}")
    print(f"  target band (45-55% of CBO 5.2M loss): {target_low:,.0f} – {target_high:,.0f}")
    print(f"  pre-rake / target_midpoint ratio: {nat_total / ((target_low + target_high) / 2):.2f}")
    print()
    print("Subgroup national totals (pre-rake):")
    for key, meta in SUBGROUPS.items():
        col = f"{key}_doc_failures"
        total = df[col].sum()
        print(f"  {meta['label']:<55}  {total:>11,.0f}")

    print()
    print("Top 5 states by exemption-doc-failure exposure:")
    for _, r in df.head(5).iterrows():
        print(f"  {r['state_abbr']}  {int(r['total_exemption_doc_failures_pre_rake']):>10,d}  "
              f"(ex parte score {int(r['ex_parte_score']) if pd.notna(r['ex_parte_score']) else '—':<3})")

    print(f"\n-> {EXEMPTION_OUT.relative_to(config.PIPELINE_DIR)}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 04c done in {time.time() - t0:.1f}s")
