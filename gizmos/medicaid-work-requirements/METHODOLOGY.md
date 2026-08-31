# Methodology: Medicaid Work Requirements Map

Last updated: 2026-06-04. Next refresh planned after CCF/KFF pre-review (2026-07) and to re-reflect the HHS interim final rule (CMS-2454-IFC), [issued 2026-06-01](https://www.cms.gov/newsroom/fact-sheets/medicaid-community-engagement-requirement-certain-individuals-interim-final-rule-comment-period-cms) (Federal Register 2026-06-03).

This document is the load-bearing trust document for the [Medicaid Work Requirements gizmo](https://gizmowarehouse.org/gizmo/medicaid-work-requirements). It explains every methodological choice we made, every data source, every assumption, and (most importantly) every limitation. If anything in the gizmo surprises you, the answer is here. If the answer isn't here, that's a bug; please email and we'll fix it.

**What changed (2026-06-03).** CMS issued the interim final rule (CMS-2454-IFC) on June 1, 2026 (published in the Federal Register June 3, 2026) ([CMS fact sheet](https://www.cms.gov/newsroom/fact-sheets/medicaid-community-engagement-requirement-certain-individuals-interim-final-rule-comment-period-cms)). It ties the medical-frailty exemption to a health condition that impairs the ability to meet the 80-hour requirement and bars states from categorically exempting people by diagnosis (see §3.5), and it permits time-limited self-declaration of work or exemption status through 2027. The figures in this document do not yet re-reflect the rule; we are assessing its impact and will update this document and the gizmo in the coming weeks, as we have time to interpret and model the new rule.

**What changed in the prior data revision (2026-06-02).** The ex parte capability score drops the IRS wage-match flag (whose annual lag makes it too stale for monthly verification) and does not replace it with a scored income component: credit-rating-agency data is universal through the federal Data Services Hub (so it doesn't differentiate states), and reliable per-state data on consent-based verification adoption isn't yet available. Supplemental income-verification tools are flagged as an important factor for future analysis rather than scored; see §3.5 and 17A's CBV Buying Guide. This revision also completed the §10 Sources list to enumerate every dataset the pipeline integrates (it had been abbreviated); the analysis and all figures are unchanged. The prior revision (2026-05-30) rebuilt the score to lead with each state's *observed* ex parte renewal rate from CMS unwinding data (2023–2026) rather than a vendor-tier proxy (§3.5); removed Section 1931 parent-pathway enrollees from the subject pool, because the work requirement does not reach them (§3.1, §3.7); pulled American Indian / Alaska Native enrollees out as their own per-state, PUMS-derived exemption line; and added §3.7 documenting the subject-pool definition head-on, including a recent-non-citizen screen and the limits of using ACS poverty ratio rather than MAGI.

<a id="section-1-what-were-estimating"></a>
<a id="section-2-subject-pool"></a>
<a id="section-2-loss-projection"></a>
<a id="section-3-subject-count"></a>
<a id="section-3-subject-rate"></a>

## 1. What we're estimating

We estimate, for each county and 1-mile grid cell in the United States, the number of adults aged 19-64 enrolled through ACA Medicaid expansion (eligibility category VIII) who will be subject to verification of 80 hours per month of qualifying activity under **Section 71119 of the One Big Beautiful Bill Act**, which adds **§1902(xx)** to the Medicaid Act. We also estimate the *verification burden*: a composite index of factors that predict whether eligible enrollees will lose coverage through administrative churn rather than for failing to meet the underlying work requirement.

We do *not* estimate:
- Coverage losses from OBBBA's six-month redetermination provision (Urban Institute estimates this separately and we recommend their March 2026 paper for that figure)
- SNAP work-requirement expansions in the same bill
- Other OBBBA Medicaid provisions (retroactive coverage reduction, provider taxes, etc.)

The work-requirement provision **cannot be waived under Section 1115**. State discretion is limited to two levers: the **short-term hardship exception** (case-by-case) and the **high-unemployment hardship exception** (geographic, state must request).

### 1.1 Who is subject: expansion states plus three Section 1115 waiver states

§1902(xx) applies to the ACA expansion-adult group **and** to "certain enrollees in 1115 waiver programs" who fit a comparable description. Per KFF's tracker and CMS's June 2026 subject-state list, the requirement covers **44 states including DC**: all 40 expansion states + DC, plus three **non-expansion** states whose 1115 demonstrations cover an expansion-like adult slice. We did not adopt the binary "expansion vs. not" frame for these three; we model each on its own terms:

- **Wisconsin** — BadgerCare Plus covers childless adults to 100% FPL under an 1115 waiver (~198,000 non-disabled childless adults, Jan 2025). This population is **not currently work-conditional**, so OBBBA imposes a genuinely new requirement and a real coverage-loss exposure. We size the subject pool from administrative enrollment (not the full state ACS Medicaid-adult pool), distribute it across tracts by the ACS B27003 Medicaid-adult shape, and run it through the same exemption and documentation-failure model used for expansion states. Wisconsin's exemption *prevalence* rates are derived from its own ACS PUMS in stage 04e — the same method every expansion state uses (its medical-frailty rate comes out near 18%, vs. the 28% national prior). Only the documentation-*failure* rates fall back to the national average, because no work-requirement-specific verification-feed (ex parte) data exists for this waiver population yet. Two honest caveats remain: the published enrollment already excludes disability-pathway enrollees, so the PUMS frailty rate is measured on a broader Medicaid-adult sample than the childless waiver slice (a mild over-estimate), and we zero the parent/caretaker exemption because the population is childless by definition. Wisconsin's figure is a model projection, not a precise count.
- **Georgia** — Pathways to Coverage (~8,000 enrolled) **already conditions coverage on an 80-hour work requirement**. OBBBA therefore adds no net-new procedural loss for current enrollees; Pathways runs through 2026-12-31, after which the state must comply with the federal framework. We carry Georgia's subject count but model **zero net-new loss**.
- **Tennessee** — a closer look shows TennCare III has *no* ACA expansion group, so OBBBA reaches it only via prong (II): adults who get minimum-essential coverage through an 1115 expenditure authority and aren't otherwise state-plan eligible. In TennCare that is the "MEC Additions" group — parents/caretaker relatives covered to 100% FPL (eligibility group EG16 ≈ 17,758 in the Jan–Mar 2025 quarterly report; the state projected ~8,100 when it added the group in 2024). But OBBBA exempts parents/caretakers of a dependent child under 14 (§1902(xx)(9)), so almost the entire EG16 group is exempt and the genuinely-subject slice (caretakers of teens 14–17) is negligible. KFF and Georgetown CCF both read OBBBA as effectively not applying in Tennessee. We therefore flag Tennessee as in-scope (it is not labeled "not affected") but model **no coverage-loss estimate**, rather than fabricate one. Note that CMS has not itself published a definitive count of the TennCare population it deems subject; the three-non-expansion-state list is KFF's characterization, and CMS's December 2025 bulletin says it "continues to evaluate which existing section 1115 demonstration populations meet the definition."

Five **expansion** states (Hawaii, Massachusetts, New York, Oregon, Utah) also have 1115 waiver populations the requirement reaches. They are already counted via expansion, so the only residual is a small undercount of their waiver-only enrollees, which we do not separately quantify. The national subject pool is therefore CBO's 18.5M (expansion) **plus** the sized waiver slice (~206,000), not folded into the 18.5M rake.

## 2. Statutory authority and effective date

| Item | Citation | Notes |
|---|---|---|
| OBBBA section | § 71119 | Adds new § 1902(xx) to the Social Security Act / Medicaid Act |
| Effective date | December 31, 2026 | Work reporting requirements take effect; biannual redeterminations also begin |
| HHS interim final rule | Issued June 1, 2026; Federal Register June 3, 2026 (CMS-2454-IFC) | Interim final rule with comment period: effective immediately, public comment open |
| State enrollee-notification deadline | September 30, 2026 | At least 3 months before first compliance look-back |
| Hardship extension authority | Through December 31, 2028 | Secretary may exempt states demonstrating "good faith" compliance efforts |
| Retroactive coverage reduction | January 1, 2027 | Falls from 90 days to 1 month for expansion enrollees (separate OBBBA provision) |

**The HHS interim final rule (CMS-2454-IFC) issued June 1, 2026 (Federal Register June 3)** ([CMS fact sheet](https://www.cms.gov/newsroom/fact-sheets/medicaid-community-engagement-requirement-certain-individuals-interim-final-rule-comment-period-cms)). It sets the 80-hour community-engagement standard, narrows the medical-frailty exemption (tying it to a condition that impairs the ability to meet the requirement, and barring categorical exemption by diagnosis — see §3.5), and allows time-limited self-declaration of work or exemption status through 2027. Some operational details, including how the high-unemployment hardship exception will be applied, will become clearer as states implement. The figures here do not yet re-reflect the rule; we are assessing its impact and will update this document and the gizmo in the coming weeks, as we have time to interpret and model the new rule.

<a id="section-3-1-the-exemption-stack"></a>

## 3. The exemption stack

OBBBA defines several categorical exemptions. Each one matters because subtracting them from the raw enrollment count gives our subject-to-requirement headline.

**Before the exemptions: the Section 1931 parent carve-out.** A person is only subject to the work requirement if they're in the ACA-expansion eligibility category (VIII). Parents and caretaker relatives below their state's mandatory **Section 1931** parent/caretaker income limit are covered through *that* pathway, not expansion — so the requirement doesn't reach them at all, and we remove them from the subject pool before anything else. In an expansion state, a low-income parent is enrolled under 1931 if their income is below the state's 1931 limit and under expansion between that limit and 138% FPL. The 1931 limit varies enormously — from 12% FPL in Arkansas to 138% in Connecticut, Massachusetts, and Minnesota (California 109%, Maryland 123%, Rhode Island 116%) — so the share of low-income parents who are even subject runs from ~85% in Arkansas down to ~25% in California. Georgetown CCF's April 2026 analysis clarifies that under OBBBA all parents of a child under 14 are exempt regardless of pathway, so the binding case is parents of teens (14–17) in high-1931-limit states. We source the per-state 1931 income limits (% FPL) from Georgetown CCF's table (built from KFF's 2026 parent-eligibility tracker) and apply them in `pipeline/lib/pums_refine.py`. This is the single largest reason a state's true subject pool differs from a raw "everyone 0–138% FPL" tabulation; see §3.7.

### 3.1 Federal mandatory exemptions

| Exemption | OBBBA definition | Our data source | Estimability |
|---|---|---|---|
| Parent / caretaker of a child age 13 or younger | Includes legal guardians and primary caretakers | ACS B23008 + B11003 + B09001, downscaled via PUMS for the "child ≤13" cut | **Moderate**; ACS gives us "with own children 6-17" and "under 6", so we interpolate via B09001 (single-year-of-age child population) within each tract |
| Medically frail | Blind, disabled, physical / intellectual / developmental disability, substance use disorder, "disabling" mental disorder, serious or complex medical conditions | ACS B18135 (disability × insurance × age) for the disability core; state-level SAMHSA NSDUH prevalence for SUD; literature-based imputation for "serious or complex" | **Moderate for disability, low for the broader categories**; see § 3.3 |
| Pregnant or postpartum | All pregnant women + extended postpartum window | State T-MSIS pregnancy enrollment, apportioned to tracts by women 19-44 from ACS B01001 | **Low (state-level only)**; pregnancy isn't observed at tract level |
| Recent incarceration | Defined in HHS guidance (pending) | We will apply state-level returning-citizen rates from BJS NPS data; tract apportionment by adult male population 18-49 | **Low (state-level only)** |
| Compliance with SNAP / TANF work requirements | Already verified for another federal benefit | USDA FNS state SNAP work-req rolls × overlap rate with Medicaid expansion | **Low (state-level only)**; overlap rate from KFF research on dual-benefit caseloads |

### 3.2 State-discretion exemptions

| Exemption | Mechanism | Our treatment |
|---|---|---|
| Short-term hardship | State approves case-by-case for "extenuating circumstances" | We assume this catches ~2% of enrollees in the permissive band; 0% in the strict band |
| High-unemployment hardship | State requests; Secretary approves; counties with 12-month average unemployment ≥8% OR ≥1.5× national average qualify | We use BLS LAUS February 2025-January 2026 data (the vintage KFF used). State adoption flags reflect KFF's April 2026 implementation survey |

**The high-unemployment exception is the dominant geographic lever.** Per KFF's April 2026 analysis based on the most recent BLS data:

- 133 counties in 22 states meet the threshold
- ~1.4M expansion enrollees (~7.5%) live in qualifying counties
- 5 states (CA, NY, MI, NJ, OR) account for ~90% of affected enrollees
- 16 states + DC have zero qualifying counties
- 27 states plan to adopt, 12 undecided, **4 explicit non-adopters: IN, IA, MO, OK**
- The Secretary will set operational parameters (exception duration, application process) in the interim final rule

In our gizmo, the "permissive band" assumes all adopting states get hardship exceptions approved generously, and the strict band assumes none do. Real outcomes will fall in between.

### 3.3 What public data cannot estimate

Several exemption categories have no observable tract-level signal:

| Category | Why public data fails | Our caveat |
|---|---|---|
| "Serious or complex medical conditions" portion of medically frail | Determined by managed care plans on a case-by-case basis; not in ACS, CPS, or BRFSS at tract level | We treat this as a known **floor** on uncertainty. Likely causes a 3-8% overcount of the subject pool nationally |
| Substance use disorder (recovery status) | NSDUH state-level only; tract apportionment is speculative | State-level rate applied uniformly within state. Documented as low-confidence |
| Mental illness severity reaching "disabling" threshold | No public source bridges ACS disability question with OBBBA's disabling-mental-disorder definition | Same caveat as SUD |

**We are upfront about this.** A reviewer who knows Medicaid will check for these caveats, and the rest of our work will be trusted more if we lead with them.

<a id="section-3-4-loss-breakdown-estimation"></a>

### 3.4 Loss-breakdown estimation: who actually loses coverage and why

This section explains how the "Where the projected losses come from" Sankey sizes each subgroup. It is the most rigorously cited part of the gizmo because the implicit claim (that 80–90% of the projected loss is people who *are* eligible) is the load-bearing piece.

#### Bottom-up methodology (no rake-to-CBO target)

CBO projects 5.2M coverage loss by 2034 from the work-requirement provision alone. The Urban Institute's HIPSM model projects 3–7M from the work requirement alone (and 4.9–10.1M once OBBBA's six-month redeterminations are included); CBPP estimates 9.7–14.4M are at risk if state implementation is poor. Our Sankey is built bottom-up rather than raked to any of these targets: for each (state, subgroup) cell, `loss = subject_pool × eligibility_rate × failure_rate`, summed across all cells. Documentation-failure subgroup totals are then multiplied by a cross-cycle compounding factor (×1.15, see below) to translate single-renewal-cycle snapshots into a cumulative 2034 figure.

The bottom-up national total currently lands at ~5.42M, just above CBO's 5.2M baseline (well inside the [4.5M, 11M] no-calibration band). The within-bucket proportions and the compliant-doc / exemption-doc / genuinely-non-compliant split (currently ~38% / ~51% / ~10%) emerge from the math rather than from an editorial split. A calibration check compares the bottom-up total against the published range; if the total falls outside [4.5M, 11M] (bracketing CBO 5.2M to CBPP 10M), a single uniform multiplier scales the result to the CBO + Urban midpoint of 6.4M while preserving per-state and per-subgroup PROPORTIONS. Whether the calibration multiplier is currently applied is disclosed in the `national_targets` field of `public/data/medicaid-loss-breakdown.json`.

#### The cross-cycle compounding factor

OBBBA has 6-month renewal cycles. By 2034 there are 14 cycles. Single-cycle bottom-up math undercounts cumulative loss because people who lose coverage and re-enroll may fail a later cycle. The compounding factor of ×1.15 reflects 14 cycles × ~30% per-cycle procedural denial × ~70% re-enrollment fraction × geometric decay (each re-enrolled cohort is smaller than the previous). The factor is applied only to documentation-failure subgroups (compliant-doc + exemption-doc); the genuinely-non-compliant population is unaffected because it's a steady-state count, not a per-cycle flow. The constant lives in `pipeline/config.py:CYCLE_COMPOUNDING_FACTOR`.

#### Compliant-but-can't-prove-it failures (eight subgroups)

Under OBBBA, "compliant" means meeting the requirement through work, school, or volunteering; "exempt" means medical/caregiving/pregnancy. Students and volunteer/job-training subjects therefore live in the compliant bucket, not the exempt bucket. Sized by ACS PUMS-derivable shares of the state subject pool; stage 04b's `--pums-mode full` path produces the per-state classification, with national synthetic priors as a fallback. The eight subgroups (six work-side from PUMS occupation/industry/hours classifiers, plus students and volunteering/job-training from the exemption-stage 04c outputs routed to the compliant bucket):

| Subgroup | Share of subject pool | Source |
|---|---|---|
| Gig / courier (DoorDash, Uber, Lyft, Instacart) | 5% | Pew "State of Gig Work" Dec 2021, restricted to Medicaid-eligible income bands. Primary-income gig workers are ~3-5% of low-income working-age adults. (SHED 2022 does not isolate gig work, so it is not used for this share.) |
| Cash-paid construction & trades | 6% | Modeled prior from BLS QCEW 2024 (NAICS 23 employment) + ACS C24010 + IRS SOI 1099-NEC 2023. Construction employs a large share of low-income men; we assume roughly 40% are paid in cash or by 1099 and so can't be matched to wage records. |
| Multiple part-time jobs (aggregation failure) | 12% | Modeled prior (not a direct BLS headline). BLS Multiple Jobholders 2024 reports ~5% of all employed; CPS data put low-income multiple-jobholding somewhat higher (~6-8%). The 12% prior reflects the broader segment whose hours are split across employers and so fail single-paystub verification. |
| Seasonal: agriculture, hospitality, food service | 8% | ACS C24010 + BLS CES seasonal adjustment. ~16% of low-income working-age adults work in NAICS 11+72; ~50% of those have <40 weeks worked annually. |
| Self-employed (other) | 5% | ACS class-of-worker codes 2024, residual after removing gig/courier and cash-construction subsets. |
| Variable shifts / on-call | 6% | Federal Reserve SHED 2022 + Schneider & Harknett 2024 ("Shift Project"). ~25% of low-wage retail/food/healthcare workers have variable schedules; ~half dip below 80 hrs in some month per year. |

Per-state failure rate per subgroup = base_failure_rate × ∏(attenuation if the relevant state ex parte flag is true). The base failure rates are anchored to Arkansas 2018 admin churn (75-85% for 1099/gig, 50-55% for variable-hour W-2, 45-55% for multi-job). Attenuation factors per driver flag are 0.45-0.65 (each true flag halves residual failure rate, roughly). High-integration-bonus states (CalSAWS-grade) get an additional 0.80 multiplier. Floor: 10-25% per subgroup (some enrollees fail even with perfect data matching).

Driver flag mapping by subgroup is documented in `pipeline/04b_fetch_pums_workdoc_breakdown.py` and summarized below:

| Subgroup | Driver flags |
|---|---|
| Gig / courier | UI wage match, self-attestation |
| Cash-paid construction | Self-attestation |
| Multiple part-time jobs | UI wage match |
| Seasonal ag/hospitality | UI wage match, self-attestation |
| Self-employed (other) | Self-attestation |
| Variable shifts | UI wage match, self-attestation |

#### Exempt-but-can't-prove-it failures (nine subgroups)

Sized by `(state expansion pool × per-state eligibility rate × per-state failure rate × cross-cycle compounding factor)`. The eligibility rate is derived from authoritative state-level data per subgroup, with the national priors in `config.NATIONAL_EXEMPTION_RATES` retained as floor/cap anchors and as per-cell fallbacks when state-level data is unavailable. See §3.5 below for the full derivation.

| Subgroup | Eligibility-rate source | Driver flag(s) | Base failure |
|---|---|---|---|
| Medically frail without auto-match | ACS PUMS 2020-2024 (DIS × specific-functional-impairment flags, Medicaid+income filtered) | Medicaid claims match, BH MCO match | 65% (see §3.5 for rationale) |
| Parent caregivers of children ≤13 without auto-match | ACS PUMS 2020-2024 (SERIALNO household link to own-child AGEP ≤ 13) | Child welfare records match | 16% (see §3.5) |
| Kinship caregivers (non-parent) of children ≤13 | ACS PUMS 2020-2024 (SERIALNO + RELSHIPP household-inference for grandparent/other-relative-headed households with child ≤13) | Child welfare records match | 55% |
| Caregivers of a working-age disabled adult | ACS PUMS 2020-2024 (SERIALNO household link to working-age adult with DIS=1 AND ≥2 specific functional flags; spouse-then-householder-then-eldest primary-caregiver heuristic) | (none — no clean admin pathway) | 70% |
| SUD treatment not flagged in claims | SAMHSA NSDUH 2023-2024 state SUD prevalence × 0.35 national treatment-engagement | BH MCO match, Medicaid claims match | 50% |
| Recent incarceration (data-match gap) | BJS NPS 2023 state releases, calibrated so the national-weighted-mean honors the 0.008 prior (NPS gives relative variation; prior gives the level since NPS excludes jails) | Corrections records match | 55% |
| Pregnancy / postpartum data lag | ACS PUMS 2020-2024 (FER=1 AND SEX=2: woman gave birth in the past 12 months) | Medicaid claims match | 3% (self-attestation per §1902(xx)(4)(D)(ii); see §3.5) |
| American Indian / Alaska Native | ACS PUMS 2020-2024 (RACAIAN recode: AI/AN alone or in combination), per-state | IHS / tribal-enrollment data match | 45% (tribal/IHS data rarely flows into state eligibility systems) |
| Other categorical exemptions (bundled) | National prior 0.014 (combined: former foster youth aged out under 26 ~0.4%, AYA cancer survivors ~0.1%, SNAP/TANF work-req compliant subset whose status doesn't auto-flow ~0.9%) | SNAP/TANF compliance match, child welfare records match | 50% |

**Bottom-up distribution within the exemption-doc bucket** (national, ~2.78M post-compounding): medically frail ~37%, caregivers of disabled adults ~25%, parent caregivers ~12%, AI/AN ~10%, kinship caregivers ~6%, SUD ~6%, other categorical ~2%, recent incarceration ~2%, pregnancy <1%. The shape reflects four substantive points: (i) medical frailty is the hardest exemption to document because verification requires a recurring provider letter that claims data can't fully substitute for, (ii) caregivers of disabled adults are essentially unmodeled by state eligibility systems because no clean admin pathway exists for the relationship, (iii) parent caregiver documentation is mostly one-time and the child's Medicaid case usually carries the household linkage anyway, and (iv) pregnancy approaches zero because OBBBA permits self-attestation. Parameters live in `pipeline/04c_build_exemption_breakdown.py`.

Floor/cap policy: per-state rates are clipped to `national_prior × [0.5, 2.0]`. PUMS small-sample fallback: states with `subject_pool_weighted < 5000` get the national fallback for PUMS-derived subgroups (typically only WY in practice). Every clip and fallback is logged in stage 04e's console output and serialized to the `*_clipped` and `*_source` columns of `output/state_exemption_rates.parquet`.

These subgroups can overlap (a person who is both medically frail and a caregiver). For the chart, we show each subgroup separately. The chart's purpose is to name failure modes, not produce a microdata-grade headcount. The multi-category overlap upset plot above the Sankey shows the per-record PUMS joint distribution across four headline categories (working ≥80hrs, parent caregiver, medically frail, full-time student).

<a id="section-3-5-per-state-exemption-eligibility-rate-derivation"></a>

### 3.5 Per-state exemption-eligibility rate derivation

This section documents the state-derived eligibility rates for each of the nine exemption subgroups. It is the section a state Medicaid director will read closely; every parameter is sourced and every state-level deviation has a paper trail in `output/state_exemption_rates.parquet`.

The general pattern: `state_rate = clip(raw_state_rate, national_prior × 0.5, national_prior × 2.0)`. The 0.5–2.0 envelope is editorial; it preserves meaningful real variation (most subgroups span roughly 0.7×–1.5× nationally per PUMS) while clipping pathological tails from small-state sample noise or definitional drift in administrative data.

#### Medically frail
- **Source:** ACS PUMS 2020-2024, classified per state.
- **Numerator:** `PWGTP` sum where `DIS == 1` AND at least **two** of `DDRS / DPHY / DOUT / DREM == 1` (self-care, ambulatory, independent-living, and cognitive difficulty). A looser criterion ("any one of six functional flags" including DEYE/DEAR) over-classifies milder impairments (uncorrected vision/hearing) as OBBBA "medically frail." §1902(xx)(2)(B) covers blind / disabled / SUD / disabling-mental / serious-or-complex; requiring ≥2 of the four severe functional flags brings PUMS measurement closer to that statutory threshold. The June 1, 2026 interim final rule ([CMS-2454-IFC](https://www.cms.gov/newsroom/fact-sheets/medicaid-community-engagement-requirement-certain-individuals-interim-final-rule-comment-period-cms)) ties medical frailty to a condition that impairs the ability to meet the requirement and bars categorical condition-based exemptions; against that work-ability test this functional-difficulty proxy likely overstates some physical impairment while understating mental-health and substance-use conditions ACS cannot see, and we will refine it as states operationalize the rule.
- **Denominator:** `subject_pool_weighted`, the PWGTP sum across `(AGEP 19-64) × (HINS4=1) × (POVPIP 0-138) × (PWGTP>0)`.
- **Fallback chain:** PUMS → national 0.28.
- **Caveat:** OBBBA's "serious or complex medical conditions" sub-clause is not observable in ACS, so we capture the functional-impairment portion only. Future work may add a state Medicaid claims match if T-MSIS becomes publicly accessible at that grain.

#### Parent / caretaker of child ≤13
- **Source:** ACS PUMS 2020-2024, household linkage via `SERIALNO` + `RELSHIPP`.
- **Numerator:** Subject-pool persons with `RELSHIPP ∈ {20, 21, 22, 23, 24}` (reference person or spouse/partner) whose household `SERIALNO` contains a person with `AGEP ≤ 13` and `RELSHIPP ∈ {25, 26, 27, 35}` (own/step/adopted/foster child of reference person).
- **Denominator:** `subject_pool_weighted`.
- **Fallback chain:** PUMS → national 0.20.
- **Caveat:** Slight undercount of grandparent / aunt / uncle caretakers. Those relationships are coded as `RELSHIPP 33` (other relative), and ACS doesn't crisply separate primary caretakers from non-caretaker household members. The undercount is bounded; future work may use the ACS B23008 + B09001 fallback to triangulate.

#### Full-time student
- **Source:** ACS PUMS 2020-2024.
- **Numerator:** Subject-pool persons with `SCH ∈ {2, 3}` (currently enrolled in public or private school) AND `SCHG ≥ 15` (undergraduate or graduate).
- **Denominator:** `subject_pool_weighted`.
- **Fallback chain:** PUMS → national 0.04.
- **Caveat:** PUMS doesn't have an explicit FT/PT flag for college enrollees. The §1902(xx) "full-time student" requirement is operationalized by enrollment intent; we accept any current college enrollment in the numerator and let the per-state failure-rate logic in 04c apply ex-parte attenuation.

#### SUD treatment
- **Source:** SAMHSA NSDUH 2023-2024 State Small Area Estimates, Table 24.
- **Numerator (state-level rate):** `sud_prevalence_18plus_pct × 0.35`. The 0.35 multiplier reflects the national share of past-year SUD adults in any form of treatment qualifying for medically-frail under §1902(xx) (SAMHSA Tracking Indicator).
- **Denominator:** Subject pool (rate applied directly; no per-state denominator computation since the SAMHSA rate is already a prevalence).
- **Fallback chain:** SAMHSA state SUD → national 0.042.
- **Caveat:** SAMHSA's state-level estimates are Bayesian small-area estimates combining 2022-2023 data; the 18+ universe is broader than the Medicaid 19-64 subject pool. The state-level SUD prevalence likely *underestimates* the Medicaid-enrollee prevalence (low-income adults have higher SUD prevalence), so the rate is conservative. Future work may scale by the published Medicaid-vs-all-adults SUD differential.
- **State variation observed:** Past-year SUD among adults 18+ ranges roughly 14% (Texas, Mississippi) to 25% (DC, Vermont, Oregon). After 0.35× treatment-engagement and floor/cap clip, eligibility rates range ~4.7%–8.4% across states.

#### Recent incarceration
- **Source:** BJS National Prisoner Statistics, *Prisoners in 2023 — Statistical Tables* (NCJ 310197), Table 9.
- **Calibration:** `state_share = BJS_releases[state] ÷ sum(BJS_releases across expansion states)`. Each state's eligible count is `target_total × state_share`, where `target_total = 0.008 × sum(expansion_pool)`. State rate = `state_eligible_count ÷ state_expansion_pool`. This preserves relative state variation (high-churn corrections systems get proportionally higher rates) while honoring the national prior level. The 0.008 prior includes jail releases, which BJS NPS excludes; hence the calibration step.
- **Fallback chain:** BJS → national 0.008. DC always falls back (federal Bureau of Prisons administers DC adult corrections since 2001; no state-prison data).
- **Caveat:** NPS counts only state-prison releases, not county jail, federal Bureau of Prisons, or ICE detention. The §1902(xx) "recent incarceration" exemption presumably covers all three. We trust the BJS *ranking* of states more than the BJS *absolute counts*, which is why we calibrate the level to the prior.
- **State variation observed:** Calibrated rates range ~0.27%–2.2% (NY, MA at the low end; KY, SD, DE at the high end; 5 states clipped to the floor/cap envelope).

#### Pregnancy / postpartum
- **Source:** ACS PUMS 2020-2024, `FER == 1 AND SEX == 2` (woman gave birth in the past 12 months).
- **Numerator:** `PWGTP` sum across women aged 19-64 in the post-filter sample where `FER == 1`.
- **Denominator:** `subject_pool_weighted`.
- **Why FER and not point-in-time pregnancy:** FER captures a 12-month accumulation rather than a point-in-time snapshot. Over the 6-month OBBBA renewal cycle, every woman who gives birth in a given year passes through the postpartum exemption window. The 12-month measure is more relevant to the cumulative renewal-cycle exposure than a point-in-time pregnancy rate. The national prior was set to 0.03 (3.0%) to align with FER's typical population rate; floor/cap envelope at [0.5×, 2.0×] = [1.5%, 6.0%].
- **Fallback chain:** PUMS → national 0.03.
- **Caveat:** The PUMS small-sample fallback (`subject_pool_weighted < 5000`) typically only fires for WY in practice. CDC WONDER natality data may eventually offer a more granular Medicaid-mother subset if T-MSIS becomes publicly accessible.

#### Kinship caregivers (non-parent caregivers of children ≤13)
- **Source:** ACS PUMS 2020-2024, household-structure inference via `SERIALNO + RELSHIPP`.
- **Numerator:** Subject-pool persons with `RELSHIPP ∈ {20, 21, 22, 23, 24}` (reference person / spouse) whose household contains a child ≤13 with `RELSHIPP ∈ {30, 36, 37}` (grandchild / other relative / non-relative) AND whose household contains no person with `RELSHIPP ∈ RELSHIPP_OWN_CHILD` (i.e., the householder is not also a parent of a young child).
- **Denominator:** `subject_pool_weighted`.
- **Fallback chain:** PUMS → national 0.015 (Annie E. Casey 2023 KIDS COUNT: ~3% of US children in non-parent kinship arrangements; ~7% in low-income families; translates to ~1.5% of expansion subject pool as kinship caregivers).
- **Caveat:** This captures formal household co-residence of a kinship caregiver with the child. Informal kinship arrangements (caregiver and child not living together, or kinship status not picked up by the survey's RELSHIPP coding) are missed. Cross-validation against AECF KIDS COUNT state-level kinship-care rates is deferred pending manual CSV sourcing (datacenter.aecf.org is UI-only; no download API).

#### Caregivers of a working-age disabled adult
- **Source:** ACS PUMS 2020-2024, household-structure inference + primary-caregiver heuristic.
- **Numerator:** For each household containing a working-age disabled adult (`AGEP 19-64 AND DIS == 1 AND ≥2 specific functional flags`), identify candidate caregivers (other adults in the same household, in the subject pool). Apply primary-caregiver heuristic: prefer spouse (RELSHIPP=21), then householder (RELSHIPP=20, excluding the disabled adult themselves), then the eldest other adult by AGEP. At most one caregiver per disabled-adult household.
- **Denominator:** `subject_pool_weighted`.
- **Fallback chain:** PUMS → national 0.03 (AARP / NAC 2020 "Caregiving in the US": ~16% of US adults provide unpaid care to an adult; ~10% among low-income working-age adults; ~3–4% with a care recipient whose disability would qualify the caregiver under OBBBA).
- **Caveat:** "Primary caregiver" is an inference from co-residence and household role, not a direct survey question. The heuristic avoids over-counting in multi-adult households but may under-count when the actual primary caregiver isn't the spouse/householder/eldest. Cross-validation against AARP / NAC state caregiver profiles is deferred pending manual CSV sourcing (caregivingintheus.org publishes per-state PDF reports, no downloadable tables).

#### American Indian / Alaska Native
- **Source:** ACS PUMS 2020-2024, `RACAIAN` recode (= 1 for any respondent reporting American Indian / Alaska Native alone or in combination), within the refined subject pool.
- **Numerator:** `PWGTP` sum where `RACAIAN == 1`. **Denominator:** `subject_pool_weighted`.
- **Why its own line:** AI/AN are categorically exempt under OBBBA, and — unlike foster youth, AYA cancer survivors, or the SNAP/TANF residual — they are directly observable in the Census. Bundling them into a flat 2% prior erased real, large state variation. Per-state rates run from a rounding error in most states to ~42% of the expansion subject pool in Alaska, with New Mexico (~20%), Oklahoma (~17%), Montana (~21%), and the Dakotas (~21–33%) also high.
- **Floor/cap envelope:** AI/AN gets a deliberately wide envelope (national prior × [0.1, 50], vs the default × [0.5, 2.0]). The default ±2× envelope is designed to clip small-sample noise around a stable national rate; for a direct measure with genuine ~40× state variation, the default cap would destroy exactly the heterogeneity that matters. Documented in `04e_compute_state_exemption_rates.py::SUBGROUP_CLIP_OVERRIDES`.
- **Caveat:** The exemption pathway is tribal/IHS enrollment data, which few state eligibility systems consume; absent that, the enrollee must self-attest or document tribal membership. Base failure rate 45%, attenuated by self-attestation policy.

#### Other categorical exemptions (bundled)
- **Source:** National prior ~1.4% applied uniformly across states (reduced from 2.0% after AI/AN was pulled out into its own line above).
- **Composition:** former foster youth aged out under 26 (~0.4% per AFCARS / Annie E. Casey), AYA cancer survivors (~0.1% per NCI SEER), SNAP/TANF work-requirement compliant subset whose status doesn't auto-flow into the Medicaid eligibility system (~0.9%).
- **Why uniform:** None of the three is consistently observable per state in public data. The SNAP/TANF compliant share could in principle be per-state but is folded into the uniform prior pending further research.
- **Caveat:** Bundled subgroup with heterogeneous documentation pathways; the base failure rate (50%) is a weighted average across the three sub-components. State variation in failure rate is driven by the `snap_tanf_compliance_match` and `child_welfare_records_match` flags.

#### Failure-rate parameters by subgroup

The *within-bucket* distribution of exemption-doc failures is set by three per-subgroup parameters in `pipeline/04c_build_exemption_breakdown.py`: `base_failure_rate` (failure rate in a state with no auto-match infrastructure), `attenuation_per_driver` (multiplicative reduction per relevant ex parte flag that's TRUE), and `min_floor` (failure-rate floor even in high-integration states). Documentation-failure bucket totals are then scaled by the cross-cycle compounding factor (×1.15) and summed bottom-up; no rake-to-CBO is applied.

| Subgroup | base | attenuation | floor | Why |
|---|---|---|---|---|
| Medically frail | 0.65 | 0.65 | 0.15 | Even in claims-match states, OBBBA's "complex medical or behavioral-health condition" standard is narrower than "has a disability." Verification typically requires a recurring provider letter (clinic appointment, provider workload, patient remembering to return docs) that resists automation. Sommers 2019 measured ~45% loss among disability-eligible Arkansas enrollees with zero auto-match; we hold close to that for high-churn states and floor at 15% even for high-integration states. |
| Parent caregivers of children ≤13 | 0.16 | 0.25 | 0.04 | Birth certificates, school enrollment, and tax-dependent records are easy one-time productions. When the parent is also a Medicaid enrollee, the child's case in the state system already carries the household linkage — the exemption should auto-apply. The surviving share concentrates in blended/separated families, mixed-status families, and children too young for school records (under 5, homeschooled). |
| Kinship caregivers ≤13 | 0.55 | 0.50 | 0.18 | Higher failure rate than parent caregivers because the child's Medicaid case typically doesn't link the kinship caregiver — birth certificates, school enrollment, and tax-dependent records all point to the biological parents. Documentation requires guardianship orders or sworn affidavits, neither of which auto-flow into state systems. |
| Caregivers of disabled adult | 0.70 | (no drivers) | 0.30 | No good admin pathway exists for the caregiver-of-adult relationship. The exemption requires a physician letter for the recipient's condition plus proof of the caregiving relationship, both manual. Expect high failure rates everywhere until states build dedicated workflows. |
| SUD treatment | 0.50 | 0.45 | 0.10 | BH MCO data covers MAT and structured outpatient; informal recovery (12-step, peer support, IOP not billed through MCO) is invisible to the eligibility system. |
| Recent incarceration | 0.55 | 0.40 | 0.12 | Even with state DOC data-share, the agreement typically covers state corrections only, not county jails (~60% of corrections churn) or federal facilities. Floor reflects cross-jurisdictional limits. |
| Students | 0.40 | 0.35 | 0.08 | The National Student Clearinghouse API is broadly available; failures concentrate in states that haven't integrated NSC. Self-attestation is the backstop where the portal accepts it. |
| Pregnancy | 0.03 | 0.50 | 0.01 | OBBBA §1902(xx)(4)(D)(ii) permits self-attestation, so failure rate approaches zero. The surviving share reflects unknown pregnancies (women not yet aware), postpartum data lag (claims data lags 15–45 days vs the 60-day biological window), pregnancy-loss cases (CMS SHO 2022 carries forward postpartum eligibility but state systems don't cleanly capture fetal-demise events), crisis non-engagement, and operational failures during 2027 implementation. |
| Other categorical (bundled) | 0.50 | 0.60 | 0.15 | Heterogeneous group with mixed admin pathways (SNAP/TANF data share, child welfare for foster youth, no clean pathway for AI/AN or AYA cancer survivor). 50% base reflects the weighted average across the four sub-components. |

The narrative strings emitted into `medicaid-loss-breakdown.json` (and surfaced as click-tooltips on the Sankey subgroup bars) are the single source of truth for the operational story behind each subgroup. They're maintained in `pipeline/04c_build_exemption_breakdown.py::SUBGROUPS[...].narrative` and `pipeline/04b_fetch_pums_workdoc_breakdown.py::SYNTHETIC_SUBGROUPS[...].narrative`; stage 07b reads them via dynamic import and writes them into the JSON.

#### How the per-state rates flow into 04c

Stage 04e writes `output/state_exemption_rates.parquet` with one row per subject state (the expansion states plus the sized 1115-waiver states WI and GA, which use their own ACS PUMS the same way) and per-subgroup columns: `{subgroup}_rate`, `{subgroup}_source`, `{subgroup}_clipped`, `{subgroup}_raw_rate`. Stage 04c reads this file, joins per-state, and uses `state_rates.loc[fips, f"{rate_key}_rate"]` rather than the national prior. The per-state rate is multiplied by the state expansion pool, then by the per-state failure rate (driver-flag attenuation).

Stage 07b loads any prior `medicaid-loss-breakdown.json` and prints (a) per-state warnings for any pre-rake exemption shift > 25%, and (b) the top-5 absolute movers in post-rake totals after the rake completes. These are the integrity checks before the new numbers reach the front-end.

#### Stage 05 subject-pool rake to CBO control total

After the union exemption deduction in stage 05, one rake aligns the national subject pool to CBO's published control total while preserving each state's PUMS-derived relative exemption profile:

- **Subject rake**: scales per-tract `(1 - exempt_share)` by `cbo_national_subject_target / pre_rake_subject_national` so the national subject pool matches CBO's 18.5M exactly. The factor is logged at stage 05 startup; it is ~1.807× because PUMS-derived statutory eligibility is broader than CBO's narrower implied-operational definition.

The rake is a uniform proportional scaling factor, so per-state ranking is preserved. The factor is exposed in `medicaid-state-summary.json` provenance for transparency. Rationale: PUMS captures *statutory eligibility* under §1902(xx); CBO's 18.5M reflects *operational reality* after the yet-unwritten HHS interim final rule narrows eligibility and after enrollee uptake behavior. The rake honors CBO's headline subject count while letting PUMS drive within-state demographics.

The loss numerator (CBO's 5.2M) is **not** raked. Earlier versions applied a uniform loss rake to scale per-tract `loss_exposure` to CBO's 5.2M, with the implied per-cycle churn rate falling out as a consequence. The current bottom-up Sankey computes per-(state, subgroup) loss directly and the national total lands just above CBO's 5.2M (~5.42M at present) without a rake. The loss-breakdown JSON's `national_targets.v5_calibration_applied` field discloses whether the calibration multiplier (used only when the bottom-up total falls outside [4.5M, 11M]) is currently in effect.

<a id="ex-parte-verification-capability-score"></a>

#### Ex parte verification capability score

A 0–100 composite per state, leading with each state's *observed* ex parte renewal rate rather than a vendor-tier proxy. The front-end cartogram lets users toggle between Composite / Observed ex parte / Data sources.

**Score — Observed ex parte (0–100), the dominant factor.** The share of completed Medicaid/CHIP renewals a state actually conducted on an ex parte (automatic) basis, from CMS State Medicaid & CHIP Eligibility Processing Data (data.medicaid.gov, volume-weighted across reporting periods 2023-03 through 2026-02), × 100. This is a *realized* measure of whether a state can clear an enrollee without making them act — far better evidence than the vendor tier of its eligibility system. It validates against published benchmarks (North Carolina ~99%, Rhode Island/Arizona ~90%+, Pennsylvania/Texas <20%, national ~66.6%). The one caveat: it measures auto-renewal for *income/eligibility*, which is necessary but not sufficient for *work-requirement* verification (that additionally needs the hours and exemption feeds in Score B). Sourced data lives in `pipeline/state_current_ex_parte.json`.

**Score B — Data Sources (0–100), quality-weighted** carries the work-requirement-specific feeds that income-renewal ex parte didn't test (see the table below). It's the secondary factor.

**Score (context only) — Core Capability (0–100)** captures the eligibility-system plumbing (vendor tier). It is computed as context but **no longer feeds the composite** — the observed ex parte rate now measures realized capability directly, superseding the proxy. Sub-components:

| Sub-component | Range | Source |
|---|---|---|
| System integration | 0–25 | `system_vendor` lookup. Tier 1 (CalSAWS, HIX-IES, ProviderOne, NYSoH/WMS, METS, CBMS, IES, ONE, COMPASS, VHC, MA EE, OBIE) = 25; Tier 2 (kynect, Bridges, NCFAST, NJ FamilyCare, KOLEA, DCAS, VaCMS) = 20; Tier 3 (mid-tier integrated) = 15; Tier 4 (limited) = 10; Tier 5 (legacy/minimal: ICES, FAMIS, ARIES, Soonercare IMS) = 5. |
| Account matching | 0–20 | Same vendor tier table — proxy for ability to consistently match the same person across data sources. |
| Deduplication | 0–15 | Same vendor tier table — proxy for master-person-index maturity. |
| Operational SLA | 0–15 | `round(integration_bonus × 0.75)`, capped at 15. Proxy: states with documented CMS Innovator-pathway grants and modern integration have measured 5-day operational capacity. |
| Self-attestation policy | 0–15 | `self_attestation_accepted ? 15 : 0`. Self-attestation is a state policy lever rather than a data source, so it contributes to core capability. |
| Identity proofing | 0–10 | Same vendor tier table — proxy for federated identity / modern auth. |

**Score B — Data Sources (0–100), quality-weighted.** Three buckets:

| Bucket | Weight | Sub-flags |
|---|---|---|
| Wage data | 30 pts | `ui_wage_match` (30). Income-verification tools are not scored — see below. |
| Medical frailty data | 30 pts | `medicaid_claims_match` (20) + `behavioral_health_mco_match` (10) |
| Other auto-match feeds | 20 pts | `snap_tanf_compliance_match` (5) + `vital_records_match` (4) + `workforce_dev_records_match` (4) + `corrections_records_match` (4) + `child_welfare_records_match` (3) |

The quality weighting reflects the relative loss-prevention impact: UI wage match drives the work-hours verification load (which carries ~38% of the projected loss), Medicaid claims + BH MCO data drives medical frailty auto-application (~19% of loss), and the rest of the auto-match feeds plug specific exemption pathways. The wage bucket is the single `ui_wage_match` flag (30 points); income-verification tools are not scored (see below), so Score B tops out at 80 in practice.

**Income-verification tools are not scored.** Two real verification avenues sit outside the score. Credit-rating-agency income data (Equifax's The Work Number) is available to every state through the federal Data Services Hub, so it doesn't differentiate. Consent-based income verification (SteadyIQ, Truv, Argyle, Digital Public Works, the CMS "Emmy" tooling) is the only mechanism that reaches gig, 1099, and self-employment income, but reliable per-state adoption data isn't available; it's a forward-looking, sparsely-documented landscape (the OBBBA work requirement starts January 1, 2027, and most consent-based verification is planned, not operational). A better version of this analysis would compare states on these supplemental income tools directly, and specifically on use of consent-based verification; for CBV design, see 17A's [CBV Buying Guide](https://group17a.substack.com/p/introducing-our-consent-based-verification). Landscape sources: KFF "An Early Look at Policy Decisions" (2026), SHVS/Manatt "Verifying Compliance and Exemptions" (Nov 2025), and CBPP's vendor-landscape work.

**Two of the auto-match feeds require state-level research that isn't fully complete yet:**
- `vital_records_match` — state vital-records department integration with the eligibility system. Drives pregnancy exemption auto-application via birth-registry feeds and supports caregiver-of-minor verification independently of child-welfare records. Evidence base: state public-health department modernization filings, CSTE registry, CDC WONDER documentation. We populate this only for states with documented evidence (CA, WA, MA, CO, MD, NY, MN, OR); other states default to FALSE pending further research.
- `workforce_dev_records_match` — state DOL / WIOA training database integration. Drives qualifying-activity auto-verification for adults in approved workforce-development programs (OBBBA §1902(xx)(2)(C)). Evidence base: publicly-filed WIOA state plans, NASWA workforce-data interoperability reports. Populated TRUE for CA, WA, MA, CO, MN; others default to FALSE pending further research.

This is honest under-coverage rather than synthetic differentiation, and we'll populate additional states as state-level research is completed.

**Score C — Historical Churn (0–100).** Reflects what actually happened in states with prior Section 1115 work-requirement experience. Sourced for four states; neutral 50 prior elsewhere.

| State | Score | Source / context |
|---|---|---|
| Arkansas (AR) | 61 | 2018 Section 1115 demonstration. 18,164 dropped — about 30% of the ~60,700 subject (ages 30-49, Dec 2018), roughly 18% of the ~100,000 targeted. Sommers et al. 2019, NEJM. The only state where work-requirement disenrollments happened at scale before federal courts halted further implementation. |
| New Hampshire (NH) | 70 | Granite Advantage 2019. Reached one month of active enforcement before federal court halt. ~17K of 25K subject enrollees were reportedly heading for non-compliance disenrollment when stopped. Score uses a generous 30% projected denial rate (Philbrick v. Azar, D.D.C. 2019). |
| Georgia (GA) | 20 | Pathways to Coverage 2023–present. ~5,500 enrolled of 100,000+ projected eligible in first 18 months. KFF tracking + HHS OIG audit findings. Non-expansion state, so this score is documented for context but does not feed an OBBBA composite. |
| Kentucky (KY) | 50 | 2018 proposal halted by federal court before implementation (Stewart v. Azar, D.D.C. 2018). No operational data; neutral prior. |
| All other states | 50 | Neutral prior (no prior Section 1115 experience). |

Sourced data lives in `pipeline/state_historical_experience.json`.

**Composite:**

```
composite = round(0.50 × observed_ex_parte + 0.35 × data_sources + 0.15 × historical_churn)
```

50/35/15 weighting, leading with the realized observed rate. Weights live in `config.EX_PARTE_WEIGHTS`; scoring in `pipeline/04d_compile_state_ex_parte.py`.

Verifying *income* automatically and verifying *work hours and exemptions* automatically are different jobs; the composite rewards states that have demonstrated the first (the observed ex parte rate) and wired the feeds for the second (Score B).

**Bands (driven by composite, but each view has its own band breakdown shown in the cartogram tooltip):**
- composite ≥ 70 → "low churn" (admin churn likely substantially mitigated)
- composite 45–69 → "mid"
- composite < 45 → "high churn" (Arkansas-grade)

See `pipeline/state_ex_parte_capability.json` for per-state flags + notes, vendor → tier mapping in `pipeline/04d_compile_state_ex_parte.py:VENDOR_TIER`, and the full scoring code in the same file.

Sources for the inputs:
- KFF, "An Early Look at Policy Decisions as States Get Ready to Implement Work Requirements" (April 2026) for data-source flag values
- State eligibility-system vendor public filings for vendor tier classification
- CMS T-MSIS Technical Assessment summary 2025-Q4 for system-maturity check
- State public-health department modernization filings (CSTE registry, CDC WONDER) for `vital_records_match`
- WIOA state plans + NASWA workforce-data interoperability reports for `workforce_dev_records_match`

**We deliberately do not publish per-state estimated administrative-churn rates.** The scores are relative ranking signals. The gap between "the state plans to use UI wage data" and "UI wage data flows into the eligibility decision in time for the 5-day reporting window" is large and not yet observable. Treat each score qualitatively: a state at 75+ composite should produce substantially less admin churn than a state at 30, with the gap closing as HHS guidance lands and as early-implementer states (NE, MT, AR, IA) generate empirical data through 2027.

#### Multi-category overlap upset plot (per-record PUMS joint counts)

Above the Sankey, an upset plot shows how subjects distribute across four headline qualifying-activity categories: working ≥80hrs/month, parent caregiver of child ≤13, medically frail, full-time student. Stage 04b's PUMS classifier writes a 16-cell weighted joint distribution per state (`overlap_cell_*_count_weighted` columns; cache schema v5). Stage 04h reads those cells directly, scales each state's per-cell counts so the state total matches its CBO-anchored `subject_count_strict` (preserving the PUMS-derived proportions), and sums to national.

The headline insight: at the national level, ~38% of subjects are in zero of the four headline categories, ~44% are in exactly one, ~16% are in two, and ~1% are in three or more. People in the single-bucket band are the most exposed to verification failure because they lack a backstop category. The zero-bucket band includes both the genuinely non-compliant residual and subjects whose only categorical exemption is one we don't track in this view (SUD treatment, recent incarceration, pregnancy, former foster youth, AI/AN tribal membership) — those latter cases appear in the appropriate exempt subgroup of the Sankey.

Earlier versions of this view used a marginal-independence simulation with pairwise correlation adjustments; the per-record PUMS approach replaced that approximation once stage 04b's classifier was extended to write the joint-cell columns. The per-record method tends to show *more* zero-bucket subjects and *fewer* multi-bucket overlaps than independence-with-adjustment predicted.

#### Open methodology gaps

The methodology is published with known gaps that future iterations will close as upstream data lands:

1. Empirical churn data from early-implementer states (Nebraska, May 2026; Montana, July 2026; Arkansas, July 2026; Iowa, December 2026) will refine the per-subgroup failure-rate floors. Earliest data lands Q3 2026.
2. Cross-validation of the kinship-caregivers and caregivers-of-disabled-adult subgroups against AECF KIDS COUNT (state-level kinship-care percentages) and AARP/NAC State Data Profiles (state-level adult-caregiver prevalence) is wired into stage 04f. Each external benchmark is calibrated to our PUMS national mean before per-state comparison (testing variation, not absolute level), with a ±60% tolerance reflecting the methodological distance between the published metric and our subject-pool-conditioned rate. Most recent run: 38/41 pass for kinship; 40/41 pass for caregivers of disabled adult. The few failures (MO, IA, NE for kinship; PA for disabled-adult caregivers) plausibly reflect either small-state PUMS noise or genuine definitional drift.
3. The BJS NPS calibration excludes county jails (~60% of corrections churn) and federal facilities; Prison Policy Initiative jail-release estimates would relax that scope caveat.
4. A documented CMS Innovator-pathway grant ledger would let the core-capability score read integration maturity directly rather than via the vendor tier lookup.
5. The other-categorical-exempt bundled subgroup (former foster youth, AYA cancer survivor, SNAP/TANF compliant residual) uses a uniform ~1.4% national prior; American Indian / Alaska Native enrollees are now pulled out into their own per-state PUMS-derived line. Per-state derivations of the remaining bundle would require: AFCARS foster-aged-out counts joined to Medicaid, NCI SEER AYA cancer prevalence × state Medicaid enrollment, and state SNAP/TANF roll cross-walks. All sourceable but not currently wired.

<a id="section-3-6-what-this-gizmo-is-not"></a>

### 3.6 What this gizmo is not

**This gizmo is a visualization of where the procedural-disenrollment wave will concentrate. It is not an operational outreach plan, and it should not be read as a county-level prioritization for January 2027 field campaigns.**

The dense red counties on the main map and the high-burden-index regions in the burden-index view show where the OBBBA work requirement will cost the most expansion enrollees their Medicaid. Read them as situational awareness, as the answer to "where will the wave hit hardest, and at what scale." Do not read them as the answer to "where should I send a 2027 field campaign."

The variables that actually move a county's loss exposure are upstream of the rule. There are four of them:

1. **Ex parte data plumbing.** The three-factor capability score above measures how many of an enrollee's hours and exemptions can be auto-verified against administrative data the state already holds (UI wage, Medicaid claims, BH MCO, SNAP/TANF compliance, corrections, child welfare, vital records, workforce development), the maturity of the eligibility system that consumes that data, and the state's prior Section 1115 work-requirement experience where it exists. Each new data-source flag set TRUE removes a class of enrollees from the procedural-disenrollment exposure pool. The work happens in 2026, in vendor configuration meetings and cross-agency data-share agreements.
2. **Cross-program data work.** SNAP/TANF compliance lists are categorically exempt under §1902(xx)(2)(F). Pulling them into the eligibility system before the rule activates means those enrollees never enter the verification queue.
3. **Vendor configuration.** The vendor-tier portion of the core-capability score reflects whether the eligibility system can act on data once it arrives: account matching, deduplication, 5-day operational SLA. A state can plug in every data source on the planet and still produce Arkansas-grade churn if the system can't match the same person across them in time.
4. **Enrollee comms.** Most procedural disenrollments aren't people who failed to produce documentation; they're people who never saw the verification letter. Postal address validation, MCO-channel outreach, SMS/email reminder schedules, and provider-side notifications all happen before December 31 and reach far more enrollees than any post-activation door-knocking campaign.

Once an enrollee in Cook County or the Arkansas–Louisiana Delta is receiving a termination letter, field outreach is a recovery effort rather than a prevention one. The activities that prevent terminations have already happened or already failed to happen.

The state PDF brief's operational checklist is ordered to reflect this principle: ex parte and data-sharing items first, comms-plan items next, geographic-targeting items last. Read it in that order.

<a id="section-3-7-subject-pool-definition-and-its-limits"></a>

### 3.7 Subject-pool definition, and how it differs from a raw ACS tabulation

The hardest methodological question for any ACS-based work-requirement analysis is: *who is actually in the subject pool?* A naive approach tabulates everyone aged 19–64 with income 0–138% FPL in expansion states. That population is far from the population subject to the requirement, and tabulations built on it don't have a clear interpretation. (Reviewers at CBPP and KFF make exactly this point, and decline to publish detailed demographic tabulations from ACS for it.) Here is precisely how our approach differs — and where it shares the same limits.

**Our structural defense: we anchor to administrative control totals.** State subject totals are raked to CMS T-MSIS expansion-adult enrollment, and the national total to CBO's 18.5M. Our *levels* are anchored to authoritative sources, not to a raw ACS count; ACS supplies only the within-state geographic distribution and the composition (which subgroups, in what proportion). The well-documented 15–25% ACS Medicaid undercount (Boudreaux et al. 2015) is therefore not in our levels.

**Where we refine the composition:**
- **Eligibility category.** A raw tabulation includes people eligible/enrolled through non-expansion pathways (disabled, aged, parent/caretaker). We remove the largest and most identifiable — Section 1931 parents (§3.1) — and the medically-frail exemption absorbs much of the disability-pathway overlap. PUMS carries no eligibility-category field, so we cannot perfectly isolate category VIII; the rake to T-MSIS expansion enrollment corrects the *level*, and we flag the residual composition effect rather than hide it.
- **Immigration status.** A raw tabulation includes immigration-ineligible people. We conservatively remove non-citizens (`CIT == 5`) who entered within the federal 5-year-bar window (`YOEP`) — the slice most likely undocumented, inside the bar, or in state-funded/emergency coverage the federal requirement doesn't reach. Long-resident LPRs, refugees, and citizens are kept. A floor, not a precise eligibility screen.
- **Health-insurance unit.** We use the Census family-based poverty ratio (`POVPIP`) plus direct household linkage (`SERIALNO` + `RELSHIPP`), not a single blunt health-insurance-unit measure stretched across Medicaid, employer, and marketplace eligibility at once. Program-specific units would be better still, but the single-blunt-HIU pitfall is avoided.

**Where the same limits remain, stated plainly:**
- **MAGI.** `POVPIP` is the Census poverty ratio, not adjusted to Medicaid's Modified Adjusted Gross Income definition (different disregards and add-backs). This introduces a few-point error at the 138% boundary; we accept it rather than impute MAGI, which PUMS can't support without assumptions that would manufacture false precision.
- **Other coverage.** `HINS4 == 1` records presence of Medicaid, not exclusivity; the rake to T-MSIS enrollment corrects the level.

**Bottom line, and our publishing posture.** These refinements make the analysis materially better-defined than a raw 0–138% FPL tabulation, and the rake anchors every headline — but the limits above are real. So, consistent with KFF's and CBPP's own posture, we present *per-state demographic splits as distributional estimates, not microdata-grade head counts*, and we lead the gizmo with the operational story (what share a state can clear ex parte, and how) rather than with detailed demographic claims the ACS can't fully support.

<a id="section-4-county-apportionment"></a>
<a id="section-7-hex-within-county"></a>
<a id="section-8-grid-within-county"></a>
<a id="section-9-demographic-profile"></a>

## 4. Data architecture

### 4.1 Tract-level *shape* from ACS

The tract-level distribution of expansion-adult Medicaid enrollment comes from ACS 5-Year 2024 (covers 2020-2024). The relevant tables:

| Table | Use |
|---|---|
| **B27003** | Medicaid coverage by sex × age (the spine) |
| **B18135** | Age × disability × insurance (disability exemption) |
| **B17024** | Age × ratio of income to poverty (138% FPL filter, interpolated between the 125% and 150% bands; introduces ±2-3 pp error per tract) |
| **B23008, B11003, B09001** | Households with children + age of own children (parent-of-child-≤13 exemption) |
| **B14004** | School enrollment (full-time student exemption) |
| **B16002 / B16004, B28002** | Language at home, internet access (burden-index inputs) |
| **B01001** | Population by sex × age (denominator) |
| **B03002** | Hispanic origin × race (burden-index input) |

Geographic boundaries (state, county, and tract) come from the Census Bureau's 2024 TIGER/Line cartographic boundary files (the cb_2024 500k series); the 1-mile grid (§ 4.5) is cut against those tract polygons.

**Critical caveat: ACS undercounts Medicaid enrollment by 15-25%.** This is the well-documented "Medicaid undercount" (Boudreaux, Call, Turner, Fried & O'Hara 2015 in Health Services Research; updated by Boudreaux, Noon, Fried & Pascale 2019). We do not trust ACS levels at any geography. We use ACS only for the within-state geographic *distribution*.

**PUMS classification cache consumed by 04e and 04h.** Stages 04e (per-state exemption-eligibility rates) and 04h (multi-category overlap upset plot) both read from the per-state PUMS classification cache `output/pums_state_cache/<abbr>_classified.parquet`. The cache is produced by stage 04b's `--pums-mode full` path and carries:

- `subject_pool_weighted` (denominator: PWGTP sum across the post-filter sample)
- `medically_frail_count_weighted` (DIS=1 AND ≥2 specific functional-impairment flags)
- `caregiver_under14_count_weighted` (parent caregivers; household contains own-child ≤13)
- `kinship_caregiver_count_weighted` (non-parent kinship-led households)
- `caregivers_disabled_adult_count_weighted` (primary caregivers of working-age disabled adults)
- `fulltime_student_count_weighted` (SCH ∈ {2,3} AND SCHG ≥ 15)
- `pregnant_postpartum_count_weighted` (FER=1, women aged 19-64)
- `overlap_cell_*_count_weighted` (16 columns; per-record joint distribution across W/P/M/S for the upset plot)

Schema versioned by `cache_schema_version` (current: 5); older caches auto-rebuild on next 04b run.

### 4.2 State-level *level* from administrative data

The total expansion-adult Medicaid enrollment subject to the work requirement comes from administrative data, calibrated to a January 2027 expected level:

| Source | Use |
|---|---|
| **CMS T-MSIS state monthly enrollment** | State-level expansion-adult enrollment, latest quarterly extract |
| **KFF State Health Facts** | Expansion-state adoption status, validation benchmark |
| **ACS PUMS 2020-2024** | State-level share of expansion enrollment by eligibility category, demographic |
| **CBO 2025 OBBBA scoring** | National control total: 18.5M subject, 5.2M coverage loss |

### 4.3 The shape × level rake

We apply iterative proportional fitting:

1. Compute tract-level expansion-adult Medicaid shares from ACS (sums to 1 within each state).
2. Multiply by state-level T-MSIS-calibrated expansion-adult count.
3. Apply categorical exemption deductions (§ 3.1) tract-by-tract for moderate-confidence exemptions and uniformly within state for low-confidence ones.
4. Apply state-policy adjustments (§ 3.2); these only matter for the strict-vs-permissive band.

This is the standard small-area-estimation move; SAIPE (Small Area Income and Poverty Estimates) and SAHIE (Small Area Health Insurance Estimates) use the same logic.

### 4.4 Margin-of-error propagation

We propagate ACS margins of error through every transformation per the Census Bureau's ACS Handbook for Data Users:

- Sum: √(sum of squared MOEs)
- Ratio: standard ratio MOE formula
- Product (rate × population): Taylor-series approximation

We publish MOE and coefficient of variation columns in the analyst CSV. Tracts with CV >0.4 render with diagonal hatching in the map; tracts with CV >1.0 are hidden by default behind a "show low-confidence cells" toggle.

### 4.5 Tract-to-grid resampling: the honest version

We render the map at three primitives: states, counties, and a 1-mile hex grid. The 1-mile grid is the prettiest, the most visually intuitive, and **the easiest to mislead with**. Here's the truth about it:

- The grid is rendered on the National Poverty Explorer's 1-mile hexagon mesh (and the 5-mile layer on a complete, non-overlapping pointy-top hex tiling at the same scale). Each cell takes its parent census tract's *rates* directly (subject_rate, burden index) and a **population-weighted share** of the tract's *counts* (subject count, working-age and total population): a cell's share of a count is its share of the tract's population, so the apportionment is dasymetric — the denser parts of a tract carry more of its enrollees — not a flat even split. Within a tract the shares sum to one, so the cells reconcile to the tract control exactly.
- The per-capita rate (`subject_rate`) is the cell's subject count over its working-age (19-64) population, both threaded from the tract — so the cell rate equals the tract rate, on the same ACS B01001 denominator the county layer uses (§ 4.1). The 5-mile hex rate is a true ratio-of-sums (Σ subjects ÷ Σ working-age over the cells in the hex), not an average of cell rates.
- **The 1-mile grid is a geographic *sample* of cells, not a complete census of them.** The mesh resolves about one cell per square mile, so it cannot represent a census tract smaller than that — and dense-city tracts routinely are (a Manhattan or central-Brooklyn tract can be a tenth of a square mile, with no cell centroid landing inside it). Tracts with no cell go unrepresented: nationally the grid carries about **78% of the CONUS subject pool**, and the missing ~22% is concentrated in the dense urban cores of New York, California, New Jersey, and Massachusetts. **So read the count and loss layers as within-county *geography*, not as totals** — a 1-mile cell tells you *where*, not *how many* in aggregate. The county choropleth and the headline carry the authoritative counts; in dense metros the grid deliberately does not sum to them.
- Projected coverage loss on the grid and hex is each state's bottom-up total (the per-(state, subgroup) model, § 3.4) apportioned across the state's *represented* cells by subject share — the same apportionment the county layer uses (§ 6). Because it is re-normalized per state, each state's grid loss still sums to its bottom-up total even where cell coverage is partial, so the map tells one loss story at every zoom.
- The grid and hex cover the lower 48 only. Alaska and Hawaii render at the state level, not in the grid/hex layers, so grid/hex projected loss sums to ~5.36M — the CONUS share of the 5.42M national total (AK + HI ≈ 65k, ~1.2%). The county choropleth and the headline include AK + HI and read 5.42M.
- The grid does not add information. The underlying ACS measurement is at the tract level. Going to 1-mile cells redistributes that measurement; it does not refine it.
- **The MOE on each grid cell is its parent tract's MOE.** It is *not* the tract MOE divided by √(cells in tract). That would be a statistical mistake; slicing an estimate doesn't increase its precision.

A persistent footer below the map says exactly this. Cells whose parent-tract CV exceeds the thresholds above are visually muted or hidden. Tracts themselves are downloadable as a CSV with full MOE columns; they're the unit where we have *operational* confidence.

<a id="section-5-burden-index"></a>
<a id="section-6-loss-exposure"></a>

## 5. The burden index

The "compliance burden" mode is the most editorial part of this gizmo. It is a composite score, normalized to a national 0-100 distribution, designed to predict where verification will fail not because enrollees aren't doing the work but because the paperwork will defeat them.

### 5.1 Components and weights

| Sub-score | Weight | Inputs | Rationale |
|---|---|---|---|
| Verification difficulty | 0.4 | Share of households with limited English proficiency (ACS B16002/B16004); share without home internet (B28002); share with less than HS education (B15003) | Predicted by prior Section 1115 work-requirement implementations to drive procedural disenrollment |
| Labor volatility | 0.3 | Share of working-age workers in NAICS 23 (construction), 56 (admin/waste), 71-72 (arts, food service), 11 (agriculture), and self-employment (ACS C24010) | Workers in seasonal, gig, and high-turnover sectors are more likely to fail an 80-hour monthly threshold even when working full-time annually |
| Access gap | 0.3 | Share without broadband (FCC Form 477 census-block data); average drive time to nearest county-DSS office (computed from OpenStreetMap routing + DSS coordinates from state directories) | Consistent with the documentation barriers identified in Arkansas's 2018 work-requirement evaluation (Sommers et al. 2019 in NEJM) |

Weights are published here and replicable from the inputs. The composite is centered on the national median; the diverging color ramp goes cool (below median) to warm (above).

### 5.2 What the burden index is and is not

- It **is** a forecast of where churn will look like an administrative failure rather than a policy outcome.
- It **is not** a forecast of total coverage loss. That's the "projected coverage loss" mode, which shows the bottom-up per-(state, subgroup) model apportioned to counties (~5.42M nationally, just above CBO's 5.2M baseline).
- It **is** editorial. The component weights are defensible but not derivable from data.

If you think the weights are wrong, the methodology is open-source and the input CSVs are downloadable. We incorporate sourced critiques in subsequent refreshes.

## 6. Cross-validation benchmarks

We rake to multiple external benchmarks before publishing:

| Benchmark | Source | Tolerance | What it validates |
|---|---|---|---|
| **CBO national subject count** | CBO scoring of OBBBA (18.5M subject/year) | ±5% | National total |
| **CBO national coverage loss** | CBO scoring (5.2M by 2034 from work req alone) | ±10% in loss_exposure mode | National loss |
| **Urban HIPSM 2028 state estimates** | Urban Institute March 2026 (4.9-10.1M national, CA 1.0-1.2M, NY 743-846k) | ±15% per state | State-level distribution |
| **CBPP state and CD estimates** | CBPP July 2025 (9.7-14.4M at risk; broader OBBBA scope, not work-req-only; adjust accordingly) | ±20% per state for the work-req-only subset | State-level cross-check |
| **SAHIE county Medicaid counts** | Census SAHIE 2022 | ±20% per county | Within-state geographic distribution |
| **Loss-breakdown national totals** | CBO 5.2M anchor; bottom-up sum converges with CBO organically (no rake) | ±15% national (calibration only if bottom-up falls outside [4.5M, 11M]); ±20% per-state vs Urban HIPSM ranges | Bottom-up national converges with CBO; state-level distribution preserves bottom-up math; per-state cross-checked against Urban |
| **Ex parte capability score floor/ceiling** | KFF April 2026 implementation survey (43 states, including DC) | All 10 flag values must trace to survey response or documented vendor filing | Per-state ex parte score |
| **Per-state medically-frail rate** | KFF "Distribution of Medicaid Enrollees by Enrollment Group", state disability share | ±30% per state | stage 04f benchmark check |
| **Per-state parent/caretaker rate** | KFF "Distribution of Medicaid Enrollees by Enrollment Group", state parent/caretaker share | ±25% per state | stage 04f benchmark check |
| **Per-state full-time-student rate** | NCES IPEDS state college enrollment ÷ adult population 19-24 | ±35% per state | stage 04f benchmark check |
| **Per-state recent-incarceration rate** | Prison Policy Initiative state release rates (jails + prisons) | ±50% per state (definitional drift; PPI counts jails, BJS NPS does not) | stage 04f benchmark check |
| **Per-state SUD treatment rate** | SAMHSA NSDUH state SUD prevalence (echo check from same source as 04e) | ±10% per state | stage 04f sanity check |
| **Per-state pregnancy rate** | ACS PUMS FER echo check (same source as 04e); CDC WONDER natality data as a future external benchmark | ±10% per state | stage 04f sanity check |
| **Per-state kinship-caregivers rate** | AECF KIDS COUNT "Children in kinship care" state percentages, scaled to PUMS national mean | ±60% per state (variation check, not level) | stage 04f benchmark check (38/41 pass currently) |
| **Per-state caregivers-of-disabled-adult rate** | AARP / NAC "Caregiving in the US 2025" State Data Profiles, scaled to PUMS national mean | ±60% per state (variation check, not level) | stage 04f benchmark check (40/41 pass currently) |

If any state diverges by more than its tolerance, we investigate and document. Stage 04f writes `output/state_exemption_rates_validation.parquet` with every comparison. The investigation log lives in `gizmos/medicaid-work-requirements/pipeline/cross_validation/`.

<a id="section-12-state-briefs"></a>
<a id="section-7-vintage-and-refresh-schedule"></a>

## 7. Vintage and refresh schedule

| Component | Current vintage | Refresh trigger |
|---|---|---|
| ACS tables | 5-Year 2020-2024 | New 5-year release (Dec 2026 for 2021-2025 vintage) |
| ACS PUMS microdata | 5-Year 2020-2024 | Same as ACS tables; rebuild `pums_state_cache/` after refresh |
| T-MSIS | Latest available state quarterly extract | New quarterly release |
| BLS LAUS | Feb 2025 - Jan 2026 12-month average | Monthly |
| KFF state adoption survey | KFF April 2026 publication | KFF refresh |
| SAMHSA NSDUH state estimates | 2023-2024 SAE (released Oct 2024) | Annual (~Oct release) |
| BJS National Prisoner Statistics | 2023 (released Sep 2025) | Annual (~Dec release for prior calendar year) |
| HHS interim final rule | Issued June 1, 2026; Federal Register June 3 (CMS-2454-IFC) | Interpreting and modeling; folded in over the coming weeks |
| Bill text and CBO scoring | OBBBA Section 71119 as enacted July 2025 | Statutory amendment (none expected before 2027) |

We commit to refreshing the gizmo within 30 days of:
- Each new ACS 5-Year release
- Each KFF state-adoption survey update

The June 1, 2026 interim final rule (CMS-2454-IFC) is a one-off change we will fold in over the coming weeks, as we have time to interpret and model it.

After January 1, 2027, we will add a tenth render mode tracking actual disenrollment data as states report it.

## 8. Disclosure-avoidance and small-population suppression

We suppress any tract or grid cell where the estimated subject count is below N=50 in the count modes. This is consistent with the Census Bureau's Disclosure Avoidance System guidance for tract-level estimates. The exact suppression rule is published in `pipeline/config.py` under `MIN_DISPLAY_N`.

## 9. Things we got wrong

This section will be populated post-launch with errors found by pre-reviewers, state directors, journalists, and our own QC. We'd rather be visibly correctable than secretly wrong.

## 10. Sources

All publicly accessible. Ordered by role (projections and control totals; Census demographic, microdata, and geography; CMS administrative and program data; state policy; labor and employment; health, behavioral, and corrections; caregiving and youth; burden-index, land-use, and access; methodology and legal references):

1. CBO, "Supplemental Cost Estimate, Public Law 119-21 — Medicaid Provisions" (Oct 2025). https://www.cbo.gov/publication/61837
2. Urban Institute, "Projected Reductions in Medicaid Expansion Enrollment Under OBBBA's Work Requirements and Six-Month Redeterminations." March 2026. urban.org/research.
3. Urban Institute, "State-by-State Estimates of Medicaid Expansion Coverage Losses under a Federal Work Requirement" (HIPSM, 2025). https://www.urban.org/research/publication/state-state-estimates-medicaid-expansion-coverage-losses-under-federal-work
4. Center on Budget and Policy Priorities (CBPP), "Medicaid Work Requirements Will Harm Low-Paid Workers." https://www.cbpp.org/research/health/medicaid-work-requirements-will-harm-low-paid-workers
5. U.S. Census Bureau. American Community Survey 5-Year 2020-2024 detailed tables. Tables consumed: B27003 (Medicaid coverage by sex × age), B18135 (age × disability × insurance), B17024 (income-to-poverty ratio), B23008 / B11003 / B09001 (households with own children by age), B14004 (school enrollment), B16002 / B16004 (language at home) and B28002 (internet access), B01001 (population by sex × age), B03002 (Hispanic origin × race), C24010 (occupation by sex). Supplies the within-state geographic distribution (the "shape," § 4.1). census.gov/programs-surveys/acs.
6. U.S. Census Bureau. American Community Survey Public Use Microdata Sample (PUMS), 5-Year 2020-2024. Variables consumed: PWGTP, AGEP, SEX, HINS4, POVPIP, SERIALNO, RELSHIPP, DIS, DDRS, DPHY, DOUT, DREM, SCH, SCHG, FER, plus the work-doc classifiers INDP, OCCP, COW, WKHP, WKWN. (DEYE/DEAR are pulled but do not feed the medically-frail criterion.) census.gov/programs-surveys/acs.
7. U.S. Census Bureau. Small Area Health Insurance Estimates (SAHIE), 2022. County-level Medicaid coverage, used as a within-state geographic-distribution cross-validation benchmark (§ 6). census.gov/programs-surveys/sahie.html.
8. U.S. Census Bureau. TIGER/Line cartographic boundary files, 2024 (cb_2024 500k state, county, and tract series). Geographies for county and tract aggregation and the 1-mile grid (§ 4). census.gov/geographies/mapping-files.html.
9. CMS. Transformed Medicaid Statistical Information System (T-MSIS) state enrollment, latest quarterly extract. State-level expansion-adult enrollment, the level anchor the ACS shape is raked to (§ 4.2). medicaid.gov.
10. CMS. State Medicaid & CHIP Eligibility Processing Data (data.medicaid.gov), reporting periods 2023-03 through 2026-02. Observed ex parte (automatic) renewal share per state, the dominant input to the ex parte capability score (§ 3.5).
11. KFF, "A Closer Look at the Work Requirement Provisions in the 2025 Federal Budget Reconciliation Law" (Jul 2025). https://www.kff.org/medicaid/a-closer-look-at-the-work-requirement-provisions-in-the-2025-federal-budget-reconciliation-law/
12. KFF, "A Look at the High Unemployment Hardship Exception to Medicaid Work Requirements Based on Unemployment Data from February 2025 to January 2026." kff.org/medicaid.
13. KFF, "An Early Look at Policy Decisions as States Get Ready to Implement Work Requirements" (April 2026). https://www.kff.org/medicaid/an-early-look-at-policy-decisions-as-states-get-ready-to-implement-work-requirements/
14. Georgetown CCF, "States Pursuing Medicaid Work Requirement Waivers Must Make Changes." July 2025. ccf.georgetown.edu.
15. BLS. Local Area Unemployment Statistics (LAUS), February 2025 – January 2026 12-month average. County unemployment for the high-unemployment hardship exception (§ 3.2). bls.gov/lau.
16. BLS. Quarterly Census of Employment and Wages (QCEW), 2024. Construction and trades employment shares for the cash-paid-trades work-documentation subgroup (§ 3.4). bls.gov/cew.
17. BLS Multiple Jobholders, 2024, with the Current Population Survey ASEC, 2024. Multiple-jobholder rates among low-income workers for the aggregation-failure subgroup, and the share already working (§ 3.4). bls.gov; census.gov/programs-surveys/cps.
18. Pew Research Center, "The State of Gig Work in 2021" (Dec 2021). Primary-income gig and courier prevalence for the gig subgroup (§ 3.4). pewresearch.org.
19. Federal Reserve, Survey of Household Economics and Decisionmaking (SHED), 2022, with Schneider & Harknett, "The Shift Project," 2024. Variable and on-call schedule prevalence for the variable-shifts subgroup (§ 3.4). federalreserve.gov/consumerscommunities/shed.htm.
20. IRS Statistics of Income (SOI), Form 1099-NEC, 2023. Cash and 1099 arrangement share within construction and trades (§ 3.4). irs.gov/statistics.
21. SAMHSA, Center for Behavioral Health Statistics and Quality. National Surveys on Drug Use and Health, 2023-2024 State Small Area Estimates, Table 24 (Substance Use Disorder in the Past Year by State). Released Oct 2024. samhsa.gov/data.
22. Bureau of Justice Statistics. *Prisoners in 2023 — Statistical Tables* (NCJ 310197), Table 9 (Releases of sentenced prisoners by jurisdiction). Authors Derek Mueller & Rich Kluckow. Released Sep 2025. bjs.ojp.gov.
23. Prison Policy Initiative. State jail and prison release rates. Recent-incarceration cross-validation benchmark, broader than BJS NPS because it includes jail churn (§ 6). prisonpolicy.org.
24. Annie E. Casey Foundation, KIDS COUNT Data Center, "Children in kinship care" state-level percentages. datacenter.aecf.org/data/tables/10455-children-in-kinship-care
25. AARP / National Alliance for Caregiving, "Caregiving in the United States 2020" + State Data Profiles. https://www.caregivingintheus.org/reports/state-data-profiles/
26. FCC. Form 477 census-block broadband data. Household broadband access for the burden-index access-gap component (§ 5). fcc.gov/form477.
27. OpenStreetMap road network with state DSS office directories. Drive-time to the nearest county DSS office for the burden-index access-gap component (§ 5). openstreetmap.org.
28. USGS / MRLC. National Land Cover Database (NLCD), 2021 developed-land layer. The 1-mile grid resampling (§ 4.5) apportions each tract's counts by **population** share (dasymetric, using the National Poverty Explorer's 1-mile population surface); NLCD developed-land was evaluated as an alternative weighting surface but not adopted. mrlc.gov.
29. NCES. Integrated Postsecondary Education Data System (IPEDS), state college enrollment. Full-time-student-rate cross-validation benchmark (§ 6). nces.ed.gov/ipeds.
30. USDA Food and Nutrition Service (FNS). SNAP work-requirement participation data. SNAP/TANF-compliant exemption overlap with Medicaid expansion (§ 3.1). fns.usda.gov.
31. Census Bureau, ACS Handbook for Data Users.
32. Boudreaux, Call, Turner, Fried & O'Hara (2015). "Measurement Error in Public Health Insurance Reporting in the American Community Survey: Evidence from Record Linkage." *Health Services Research*, 50(6):1973-1995.
33. Sommers, Goldman, Blendon, Orav & Epstein (2019). "Medicaid Work Requirements — Results from the First Year in Arkansas." New England Journal of Medicine 381:1073-1082. https://www.nejm.org/doi/full/10.1056/NEJMsr1901772
34. Philbrick v. Azar (D.D.C. 2019), New Hampshire Section 1115 work-requirement halt. Stewart v. Azar (D.D.C. 2018), Kentucky Section 1115 work-requirement vacatur. — referenced in `pipeline/state_historical_experience.json` for the historical-churn factor of the ex parte composite.

## 11. Contact

Questions, corrections, requests for the underlying data: joe@group17a.com.

## 12. Acknowledgments

Thank you to Sarah Esty for her generous feedback, expertise, and guidance on the methodology.
