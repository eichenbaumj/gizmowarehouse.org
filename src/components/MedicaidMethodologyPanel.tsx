// MedicaidMethodologyPanel: in-page expandable methodology disclosure.
//
// State Medicaid directors are the primary audience: they will look at the
// per-state numbers and want to know what's behind them before deciding whether
// to trust them. The default presentation is "closed" so the page reads clean
// without it. Each section opens to reveal sources, parameters, and caveats
// inline, not in a popover and not on GitHub.
//
// The full METHODOLOGY.md document remains linked at the bottom for LLM users
// and for anyone who wants the deepest dive. Per-section anchor links jump
// directly to the corresponding METHODOLOGY.md section on GitHub.
//
// Built with semantic <details>/<summary> for native keyboard accessibility
// (Tab to focus, Enter/Space to toggle). No new dependency.

import React from "react";
import { METHODOLOGY_DOC_URL } from "@/lib/methodologyDisclosures";

const COBALT = "#1F1FD6";

interface Source {
  label: string;
  href?: string;
}

interface Parameter {
  label: string;
  value: string;
}

interface Section {
  /** Stable anchor / key */
  id: string;
  /** Section title (no period) */
  title: string;
  /** 2-4 sentence plain-English summary, shown when section is closed too */
  summary: string;
  /** Detailed prose body, rendered when the section is open. */
  body?: string;
  /** Authoritative sources with optional URL */
  sources: Source[];
  /** Key numeric parameters with brief description */
  parameters: Parameter[];
  /** Known limitations / honest caveats */
  caveats: string[];
  /** Anchor under METHODOLOGY.md, e.g. "#section-3-4-loss-breakdown-estimation" */
  methodologyAnchor: string;
}

const SECTIONS: Section[] = [
  {
    id: "overview",
    title: "Overview: what this estimate is and how it lines up with CBO, Urban, and KFF",
    summary:
      "Shape × level small-area estimation, the same statistical pattern Census Bureau's SAIPE and SAHIE programs use. ACS 5-Year 2024 supplies the within-state geographic distribution; CMS T-MSIS supplies the state-level count, calibrated to projected January 2027 expansion enrollment. Categorical exemptions are deducted using authoritative per-state data per subgroup, not uniform national priors.",
    body:
      "Our national subject count (~18.5 million) matches CBO. Our national bottom-up projected coverage loss (~5.42 million) lands just above CBO's 5.2 million baseline and inside Urban Institute's combined-policy range (4.9M to 10.1M). Where our state-level estimates diverge from KFF or Urban by more than 15%, we document why and how.",
    sources: [
      { label: "CBO 2025 OBBBA scoring (national control totals)", href: "https://www.cbo.gov/publication/61837" },
      { label: "Urban Institute HIPSM, Projected Reductions in Medicaid Expansion Enrollment Under OBBBA's Work Requirements and Six-Month Redeterminations (Mar 2026): 3-7M work-req-only, 4.9-10.1M combined", href: "https://www.urban.org/research/publication/projected-reductions-medicaid-expansion-enrollment-under-obbbas-work" },
      { label: "Urban Institute HIPSM, State-by-State Estimates of Medicaid Expansion Coverage Losses under a Federal Work Requirement (2025): CA 1.0-1.2M, NY 743-846k", href: "https://www.urban.org/research/publication/state-state-estimates-medicaid-expansion-coverage-losses-under-federal-work" },
      { label: "KFF State Health Facts: Medicaid expansion enrollment + adoption status", href: "https://www.kff.org/statedata/" },
      { label: "CMS T-MSIS state monthly enrollment files" },
      { label: "ACS 5-Year 2020-2024 + PUMS microdata (Census Bureau)", href: "https://www.census.gov/programs-surveys/acs" },
      { label: "SAMHSA NSDUH 2023-2024 State SAE", href: "https://www.samhsa.gov/data" },
      { label: "BJS NPS Prisoners in 2023", href: "https://bjs.ojp.gov" },
    ],
    parameters: [
      { label: "National subject pool (target)", value: "18,500,000 (CBO by 2027)" },
      { label: "National coverage loss (CBO benchmark)", value: "5,200,000 (CBO 2034); our bottom-up ≈ 5,424,480" },
      { label: "Urban HIPSM 2028 national range", value: "4,900,000 – 10,100,000 (high–low mitigation)" },
      { label: "State-level tolerance vs KFF/Urban", value: "15% per state before we document divergence" },
      { label: "Loss-breakdown split", value: "~38% work-doc / ~51% exemption-doc / ~10% genuinely non-compliant (emerges from the bottom-up math, no rake)" },
    ],
    caveats: [
      "ACS undercounts Medicaid enrollment by 15-25% (Boudreaux et al. 2015). We use ACS only for within-state geographic distribution, never for levels.",
      "We deliberately do NOT publish per-state estimated administrative-churn rates. The ex parte capability score is a relative ranking signal, not a coverage-loss forecast.",
    ],
    methodologyAnchor: "#section-1-what-were-estimating",
  },

  {
    id: "subject-count",
    title: "Who's subject to the requirement, and where they live",
    summary:
      "Roughly 18.5 million adults will need to verify work or an exemption at application and on every renewal cycle. We estimate per-place subject counts with a shape × level rake: ACS 5-Year 2024 supplies the within-state geographic distribution, T-MSIS supplies the state-level total calibrated to projected January 2027 expansion enrollment.",
    body: "ACS undercounts Medicaid enrollment by 15-25% (the well-documented Boudreaux et al. 2015 undercount), so we never trust ACS levels, only its distributional shape. State totals come from CMS T-MSIS state monthly enrollment with KFF state-facts cross-validation. The CBO national control total (18.5M subject by 2027) anchors the rake for the 40 expansion states and DC. Three non-expansion states are also subject through Section 1115 waivers (CMS June 2026 list): Wisconsin (~198,000 BadgerCare childless adults) and Georgia (~8,000 Pathways enrollees) are sized from administrative enrollment and added on top of the CBO control total rather than folded into it; Tennessee is reached only through TennCare's 1115 parent/caretaker group (EG16 ≈ 17,700 to 100% FPL), which OBBBA almost entirely exempts (parents of a child under 14), so it is flagged without a modeled count. Georgia's Pathways population is already work-conditional, so it carries no net-new modeled loss.",
    sources: [
      { label: "ACS 5-Year 2024 (Census Bureau)", href: "https://www.census.gov/programs-surveys/acs" },
      { label: "ACS B27003: Medicaid coverage by sex × age" },
      { label: "ACS B17024: age × ratio of income to poverty (138% FPL filter)" },
      { label: "ACS B01001: population by sex × age (denominator)" },
      { label: "CMS T-MSIS state monthly enrollment files" },
      { label: "KFF State Health Facts (cross-validation)", href: "https://www.kff.org/statedata/" },
      { label: "CBO 2025 OBBBA scoring (national control total)", href: "https://www.cbo.gov/publication/61837" },
      { label: "Boudreaux et al. (2015), Health Services Research (Medicaid undercount)" },
    ],
    parameters: [
      { label: "Income filter", value: "≤ 138% FPL (interpolated between 125% and 150% bands; ±2-3 pp error per tract)" },
      { label: "Age filter", value: "19-64 (expansion-adult pathway)" },
      { label: "ACS vintage", value: "5-Year 2020-2024" },
      { label: "Calibration target", value: "Projected Jan 2027 expansion-adult enrollment per state" },
    ],
    caveats: [
      "ACS undercounts Medicaid by 15-25%; we use ACS only for within-state geographic distribution, never for levels.",
      "Tract MOE is inherited by hex/grid cells. Slicing a tract into smaller display cells does not increase its statistical precision.",
      "Waiver states (WI, GA) are sized from administrative enrollment and distributed by the ACS Medicaid-adult shape. Their exemption-prevalence rates are derived from their own ACS PUMS, the same as every other state (WI medical frailty ~18%, vs. the 28% national prior); only the documentation-failure rates fall back to the national average, since no work-requirement-specific verification data exists for these populations yet. Their figures are projections, not microdata-grade counts, and for WI the PUMS frailty rate is measured on a broader Medicaid-adult sample than the childless waiver slice (a mild over-estimate); the parent exemption is zeroed since the population is childless.",
    ],
    methodologyAnchor: "#section-1-what-were-estimating",
  },

  {
    id: "exemptions",
    title: "Per-state exemption-eligibility rates (nine subgroups, all per-state)",
    summary:
      "Nine federal exemption subgroups under §1902(xx). The per-state eligibility rates are derived from authoritative data: ACS PUMS for the ACS-observable categories (medically frail, parent caregivers, kinship caregivers, caregivers of disabled adults, pregnancy, and American Indian / Alaska Native via RACAIAN), SAMHSA NSDUH for SUD, BJS NPS for recent incarceration, and a national prior for the small bundled 'other categorical' group (foster youth, AYA cancer survivor, SNAP/TANF compliant residual).",
    body: "Stage 04e produces state-derived rates everywhere a defensible state data source exists. Every rate is sourced and clipped to national_prior × [0.5, 2.0] to bound PUMS small-sample noise and definitional drift in administrative data. Stage 04f cross-validates against KFF/NCES/PPI benchmarks plus AECF KIDS COUNT (state-level kinship-care rates) and AARP/NAC State Data Profiles (state-level adult-caregiver prevalence). Each external benchmark is calibrated to our PUMS national mean before per-state comparison; the validation tests whether per-state variation tracks, not absolute level. Most-recent pass rates: 38/41 for kinship; 40/41 for caregivers of disabled adult.",
    sources: [
      { label: "ACS PUMS 5-Year 2020-2024 (Census Bureau)", href: "https://www.census.gov/programs-surveys/acs/microdata.html" },
      { label: "SAMHSA NSDUH 2023-2024 State SAE, Table 24 (past-year SUD prevalence)", href: "https://www.samhsa.gov/data" },
      { label: "BJS National Prisoner Statistics, Prisoners in 2023 (Table 9)", href: "https://bjs.ojp.gov/library/publications/prisoners-2023-statistical-tables" },
      { label: "KFF / Georgetown CCF, 'An Early Look at Policy Decisions as States Get Ready to Implement Work Requirements' (Apr 2026)", href: "https://www.kff.org/medicaid/an-early-look-at-policy-decisions-as-states-get-ready-to-implement-work-requirements/" },
      { label: "AECF KIDS COUNT Data Center, 'Children in kinship care' (deferred benchmark; UI-only)", href: "https://datacenter.aecf.org/data/tables/10455-children-in-kinship-care" },
      { label: "AARP / NAC 'Caregiving in the United States' State Data Profiles (deferred benchmark; per-state PDFs)", href: "https://www.caregivingintheus.org/reports/state-data-profiles/" },
    ],
    parameters: [
      { label: "Medically frail", value: "PUMS DIS=1 AND ≥2 of DDRS/DPHY/DOUT/DREM=1, Medicaid+income filtered. National prior 0.28 (MMIS midpoint)" },
      { label: "Parent caregiver of child ≤13", value: "PUMS household linkage via SERIALNO; subject has RELSHIPP ∈ {20-24} with own-child AGEP ≤ 13" },
      { label: "Kinship caregivers (non-parent)", value: "PUMS household-inference: subject is householder/spouse in a household with kinship-coded child AGEP ≤ 13 and no own-child of householder" },
      { label: "Caregivers of disabled adult", value: "PUMS household linkage to working-age adult with DIS=1 AND ≥2 functional flags; primary-caregiver heuristic (spouse > householder > eldest)" },
      { label: "Full-time student", value: "PUMS SCH ∈ {2,3} AND SCHG ≥ 15" },
      { label: "SUD treatment", value: "SAMHSA state SUD prevalence × 0.35 national treatment-engagement" },
      { label: "Recent incarceration", value: "BJS state-prison releases calibrated to national 0.008 prior (NPS gives relative variation; prior gives level)" },
      { label: "Pregnant / postpartum", value: "PUMS FER=1 AND SEX=2 (woman gave birth in past 12 months). National prior 0.03 to align with FER's 12-month accumulation" },
      { label: "Other categorical (bundled)", value: "Uniform 0.014 national prior: foster youth + AYA cancer + SNAP/TANF compliant residual (AI/AN is a separate per-state PUMS-derived line, prior 0.010)" },
      { label: "Floor / cap", value: "national_prior × [0.5, 2.0]" },
      { label: "PUMS small-sample fallback", value: "Subject pool weighted < 5,000 → national prior" },
    ],
    caveats: [
      "ACS captures the functional-impairment portion of medically frail but not OBBBA's 'serious or complex medical conditions' sub-clause; capture is a structural floor.",
      "Kinship caregivers and caregivers of disabled adults rely on PUMS household-inference (relational categories aren't asked directly). Informal arrangements where the caregiver isn't co-resident are missed.",
      "BJS NPS counts state-prison releases only, not jails, federal Bureau of Prisons, or ICE detention. The 0.008 prior implicitly includes jails; we calibrate NPS to honor the level while preserving relative state variation.",
      "Pregnancy uses PUMS FER (gave birth in past 12 months) rather than point-in-time pregnancy because the 12-month measure better matches the 6-month renewal cycle's exposure window. State variation in pregnancy is small; bounded impact on the loss-breakdown Sankey.",
      "External cross-validation for kinship caregivers (AECF KIDS COUNT) and caregivers of disabled adults (AARP/NAC) is deferred because those publishers don't expose state-level CSVs through a public API.",
    ],
    methodologyAnchor: "#section-3-5-per-state-exemption-eligibility-rate-derivation",
  },

  {
    id: "loss-projection",
    title: "Bottom-up loss model",
    summary:
      "CBO projects 5.2M Medicaid coverage losses by 2034 from the work-requirement provision alone. Urban Institute's HIPSM model projects 3–7M from the work requirement alone; CBPP estimates 9.7–14.4M at risk if state implementation lags substantially. Our model is bottom-up per-(state, subgroup): subject pool × eligibility rate × failure rate, summed and scaled by a cross-cycle compounding factor to translate single-renewal-cycle snapshots into a cumulative 2034 figure. The within-bucket proportions and the compliant/exempt/non-compliant split emerge from the math rather than from an editorial target.",
    body: "Bottom-up methodology: for each (state, subgroup) cell, loss = subject_pool × eligibility_rate × failure_rate. failure_rate decomposes implicitly into (1 - p_ex_parte_to_subgroup) × (1 - p_documentation_success), where each component is calibrated per Sommers 2019 (Arkansas base rates) attenuated by the relevant state ex parte capability flags. Documentation-failure subgroup totals are then multiplied by a cross-cycle compounding factor (×1.15) reflecting the 14 six-month renewal cycles between January 2027 and the CBO 2034 horizon; the genuinely non-compliant population is unaffected (it's a steady-state count, not a per-cycle flow). The sum across all (state, subgroup) cells is the bottom-up national total. If it lands inside [4.5M, 11M], bracketing CBO 5.2M to CBPP 10M, no calibration is applied. If outside, a single uniform multiplier brings it to the CBO + Urban midpoint of 6.4M while preserving per-state and per-subgroup PROPORTIONS. Whether a calibration multiplier is currently applied is disclosed in the medicaid-loss-breakdown.json national_targets field.",
    sources: [
      { label: "CBO 2025 OBBBA scoring (5.2M coverage loss; 4.8M newly uninsured; 18.5M subject)", href: "https://www.cbo.gov/publication/61837" },
      { label: "Urban Institute HIPSM, Projected Reductions in Medicaid Expansion Enrollment Under OBBBA's Work Requirements and Six-Month Redeterminations (Mar 2026)", href: "https://www.urban.org/research/publication/projected-reductions-medicaid-expansion-enrollment-under-obbbas-work" },
      { label: "Center on Budget and Policy Priorities, Medicaid Work Requirements Will Harm Low-Paid Workers (CBPP, 2025)", href: "https://www.cbpp.org/research/health/medicaid-work-requirements-will-harm-low-paid-workers" },
      { label: "Sommers, Goldman, Blendon, Orav & Epstein (2019), NEJM (Arkansas Section 1115 evaluation — ~18,000 lost coverage, roughly 30% of those subject)" },
      { label: "KFF, 'A Closer Look at the Work Requirement Provisions in the 2025 Federal Budget Reconciliation Law' (Jul 2025)", href: "https://www.kff.org/medicaid/a-closer-look-at-the-work-requirement-provisions-in-the-2025-federal-budget-reconciliation-law/" },
    ],
    parameters: [
      { label: "CBO baseline (2034)", value: "5,200,000" },
      { label: "Urban HIPSM midpoint (combined work-req + six-month redetermination, 2028)", value: "7,500,000" },
      { label: "CBPP upper bound (state lag)", value: "10,000,000" },
      { label: "Cross-cycle compounding factor", value: "×1.15 (applied to documentation-failure buckets)" },
      { label: "Calibration acceptable range", value: "[4,500,000 - 11,000,000]" },
      { label: "Calibration target (if outside range)", value: "6,400,000 (CBO+Urban midpoint)" },
      { label: "Within-bucket split", value: "Emerges from bottom-up math (no rake)" },
    ],
    caveats: [
      "The bottom-up subgroup eligibility rates and failure rates are editorial parameters anchored to Sommers 2019 (Arkansas Section 1115 evaluation). We expect to refine per state as 2027 implementation data lands.",
      "The calibration multiplier (when applied) is uniform across all states and subgroups. It preserves the geographic and category-level shape of the bottom-up math but does not refine individual cell estimates.",
      "Loss compounds across renewal cycles. CBO's ~30% per-cycle churn assumption is a starting point; Arkansas 2018 saw about 30% of its subject pool lose coverage under active state effort.",
    ],
    methodologyAnchor: "#section-3-4-loss-breakdown-estimation",
  },

  {
    id: "work-doc",
    title: "Compliant-but-can't-prove-it failures (eight subgroups)",
    summary:
      "Roughly 2.1M people (~38% of total projected loss) meet the OBBBA requirement through work, school, or volunteering, but can't document it through the state portal. The data flips the popular narrative. This is mostly ordinary work that produces the wrong paperwork, not the gig economy. Subgroups, largest first: multiple part-time jobs (aggregation failure), variable-shift retail/food/healthcare, self-employed, full-time students, volunteering / job training, seasonal agriculture/hospitality, cash-paid construction, and gig/courier. Per-state composition comes from ACS PUMS 5-Year 2020-2024 with bundled priors for the small volunteer/job-training subgroup that PUMS doesn't directly classify.",
    body: "Each subgroup is classified per PUMS record by INDP (industry), OCCP (occupation), COW (class of worker), WKHP (usual hours), and WKWN (weeks worked). The classifier is documented in pipeline/04b_fetch_pums_workdoc_breakdown.py. Per-state failure rates are anchored to Arkansas 2018 administrative-churn rates (75-85% for 1099/gig with no auto-match; 50-55% for variable-hour W-2; 45-55% for multi-job) and attenuated by each state's ex parte capability flags.",
    sources: [
      { label: "ACS PUMS 5-Year 2020-2024 (Census Bureau)" },
      { label: "Pew Research, 'The State of Gig Work in 2021'", href: "https://www.pewresearch.org/" },
      { label: "BLS QCEW 2024 (construction employment)" },
      { label: "BLS Multiple Jobholders 2024 (aggregation failure)" },
      { label: "Federal Reserve SHED 2022 (variable shifts)" },
      { label: "Schneider & Harknett, The Shift Project (variable shifts)" },
      { label: "Sommers et al. (2019), NEJM (Arkansas admin-churn base rates)" },
    ],
    parameters: [
      { label: "Base failure rate (1099/gig, no auto-match)", value: "75-85%" },
      { label: "Base failure rate (variable-hour W-2)", value: "50-55%" },
      { label: "Base failure rate (multi-job)", value: "45-55%" },
      { label: "Per-flag attenuation", value: "0.45-0.65 (each TRUE ex parte flag multiplies residual rate)" },
      { label: "Integration bonus attenuation", value: "Additional 0.80× when integration_bonus ≥ 15" },
      { label: "Floor", value: "10-25% per subgroup (some failure persists even with perfect data)" },
    ],
    caveats: [
      "The 80-hour monthly threshold creates a coverage cliff in slow months even when annual hours are stable. Multi-job aggregators and variable-shift workers fail repeatedly across the year.",
      "Cash-paid construction trades are particularly hard to verify. Even consent-based bank-account aggregation catches only deposited earnings, not pure under-the-table cash.",
    ],
    methodologyAnchor: "#compliant-but-cant-prove-it-failures-eight-subgroups",
  },

  {
    id: "exemption-doc",
    title: "Exemption documentation failures (nine subgroups, all per-state)",
    summary:
      "Roughly 2.8M people (~51% of total projected loss) are categorically exempt under §1902(xx) but unable to document the exemption through their state's portal. The taxonomy covers nine subgroups: medically frail, parent caregivers of children ≤13, non-parent kinship caregivers, caregivers of working-age disabled adults, SUD treatment, recent incarceration, pregnancy/postpartum, American Indian / Alaska Native, and a bundled 'other categorical' (former foster youth, AYA cancer survivor, SNAP/TANF work-req compliant). All nine exemption rates vary per state, derived from ACS PUMS via household-structure inference for the relational subgroups (kinship, disabled-adult caregivers, parent caregivers) and direct PUMS flags for the rest (DIS+functional impairment, FER, RACAIAN). Per-state failure rates are parameterized by the state's ten ex parte capability flags.",
    body: "Each of the nine exemption subgroups has a primary auto-match data source (e.g., Medicaid claims for medically frail; child-welfare records for caregivers; corrections records for recent incarceration; IHS / tribal-enrollment data for AI/AN; SNAP/TANF + child-welfare records for the bundled 'other categorical' group). The failure-rate logic mirrors the compliant-doc bucket: base failure rate anchored to Arkansas 2018 (≈65% for medically frail without auto-match), attenuated by each flag the state has TRUE.",
    sources: [
      { label: "Sommers et al. (2019), NEJM (Arkansas exemption-verification failure base rates)" },
      { label: "KFF survey of state medically-frail verification approaches (Apr 2026, 43 states incl. DC)" },
      { label: "SAMHSA NSDUH 2023-2024 (SUD treatment)" },
      { label: "BJS NPS Prisoners in 2023 (recent incarceration)" },
      { label: "ACS PUMS 2020-2024 (medically frail, caregivers, students)" },
    ],
    parameters: [
      { label: "Base failure rate (medically frail, no auto-match)", value: "65% (Sommers Arkansas anchor)" },
      { label: "Base failure rate (recent incarceration, no DOC share)", value: "55%" },
      { label: "Base failure rate (SUD, no claims flag)", value: "50%" },
      { label: "Base failure rate (parent caregivers, no child-welfare match)", value: "16% (kinship caregivers 55%; caregivers of a disabled adult 70%)" },
      { label: "Base failure rate (full-time student)", value: "40%" },
      { label: "Base failure rate (pregnancy)", value: "3% (lowest — OBBBA §1902(xx)(4)(D)(ii) permits self-attestation)" },
      { label: "Per-flag attenuation", value: "0.25-0.65 (each TRUE ex parte flag multiplies residual rate)" },
      { label: "Per-subgroup floor", value: "1-30% (residual failure even with perfect data matching)" },
    ],
    caveats: [
      "Subgroups can overlap (a person can be both medically frail and a caregiver). We render each separately; the multi-category overlap visualization above the Sankey shows the per-record PUMS joint distribution across four headline categories. The Sankey names failure modes, not microdata-grade headcounts.",
      "Per-state failure-rate parameters reflect KFF's April 2026 stated implementation intent, not yet-observable operational performance. The gap between 'state plans to use UI wage data' and 'UI wage data flows into the eligibility decision by the December 2026 deadline' is large.",
    ],
    methodologyAnchor: "#exempt-but-cant-prove-it-failures-nine-subgroups",
  },

  {
    id: "ex-parte",
    title: "Ex parte verification capability: the state-level 0-100 score",
    summary:
      "A 0-100 composite per state. It leads with the state's observed ex parte renewal rate during the 2023-2026 unwinding (CMS eligibility-processing data, weighted 50%), then adds the breadth of work-requirement verification data sources (35%) and any documented prior Section 1115 work-requirement churn (15%). The data-source feeds scored: Medicaid claims, behavioral-health MCO, UI wage records, SNAP/TANF compliance, corrections, child welfare, and vital/workforce records. Income-verification tools (credit-agency data, consent-based verification) are a real factor but are not scored; see the methodology. A legacy vendor-tier capability score is computed as context but no longer feeds the composite.",
    body: "The high-capability band (composite ≥ 70, where admin churn is likely substantially mitigated) now spans most expansion states, led by North Carolina, Washington, Arizona, Rhode Island, Nevada, and California. The 45-69 mid band holds the lower-observed-rate states, including West Virginia, Iowa, Oklahoma, and the Dakotas. Pennsylvania is the lone state in the < 45 'high churn' band, held there by a 16% observed ex parte rate, the national floor. State data-source flags are sourced from the KFF / Georgetown CCF April 2026 implementation survey (43 states, including DC), SHVS/Manatt's tracking of consent-based-verification deployments, and state-vendor public filings.",
    sources: [
      { label: "KFF / Georgetown CCF, 'An Early Look at Policy Decisions as States Get Ready to Implement Work Requirements' (Apr 2026)", href: "https://www.kff.org/medicaid/an-early-look-at-policy-decisions-as-states-get-ready-to-implement-work-requirements/" },
      { label: "State eligibility-system vendor public filings (CalSAWS, Cúram, in-house)" },
      { label: "CMS T-MSIS Technical Assessment Summary 2025-Q4" },
    ],
    parameters: [
      { label: "Composite weights", value: "0.50 × observed ex parte rate + 0.35 × data sources + 0.15 × historical churn" },
      { label: "Observed ex parte rate", value: "CMS eligibility-processing data, 2023–2026 unwinding (50% of the score)" },
      { label: "Data-source points (80 max)", value: "UI wage 30 · Medicaid claims 20 · behavioral-health MCO 10 · SNAP/TANF 5 · vital records 4 · workforce 4 · corrections 4 · child welfare 3" },
      { label: "Historical churn", value: "Prior Section 1115 work-requirement experience; neutral 50 prior otherwise (15% of the score)" },
      { label: "Band thresholds", value: "≥70 high, 45-69 mid, <45 low" },
    ],
    caveats: [
      "We deliberately do NOT publish per-state estimated administrative-churn rates. The score is a relative ranking signal, not a coverage-loss forecast.",
      "The gap between 'state plans to use X data source' and 'X data source operationally integrated in time for the 5-day reporting window' is large, and not yet observable. Early-implementer states (NE, MT, AR, IA) will generate empirical churn data through 2027.",
    ],
    methodologyAnchor: "#ex-parte-verification-capability-score",
  },

  {
    id: "burden-index",
    title: "Compliance burden index: the editorial composite",
    summary:
      "The most editorial part of the gizmo. A 0-100 composite predicting where verification will fail not because enrollees aren't doing the work but because the paperwork will defeat them. Components: verification difficulty (40%), labor volatility (30%), access gap (30%). Centered on the national median; diverging palette.",
    body: "Component weights are defensible from prior Section 1115 evaluations (Arkansas 2018, Georgia Pathways 2023-) but not derivable from data. The burden index is a 'where to focus' signal for state Medicaid agencies. Counties scoring high are not necessarily where enrollees are less likely to be working; they're where the work is harder to verify.",
    sources: [
      { label: "ACS B16002 / B16004 (language at home)" },
      { label: "ACS B28002 (internet access)" },
      { label: "ACS B15003 (educational attainment)" },
      { label: "ACS C24010 (occupation × industry, labor volatility)" },
      { label: "FCC Form 477 (broadband by census block)" },
      { label: "OpenStreetMap + state DSS office directories (drive time to DSS)" },
      { label: "Arkansas 2018 Section 1115 evaluation (Sommers et al. 2019)" },
      { label: "Georgia Pathways implementation reporting 2023-" },
    ],
    parameters: [
      { label: "Verification difficulty weight", value: "0.4 (LEP × no-broadband × low-ed)" },
      { label: "Labor volatility weight", value: "0.3 (NAICS 23 + 56 + 71-72 + 11 + self-employment share)" },
      { label: "Access gap weight", value: "0.3 (no broadband + drive time to DSS)" },
      { label: "Centering", value: "National median (diverging palette reads symmetrically)" },
    ],
    caveats: [
      "Editorial composite. Weights are defensible but not derivable from data.",
      "Not a coverage-loss forecast. Use the 'loss exposure' mode for that.",
      "Burden ≠ ineligibility. A high-burden county doesn't mean residents are less likely to be working; it means verification will fail more often.",
    ],
    methodologyAnchor: "#5-the-burden-index",
  },

  {
    id: "data-sources",
    title: "Data sources and refresh schedule",
    summary:
      "Every input source, vintage, and refresh trigger. We refresh within 30 days of each new ACS 5-Year release and each KFF state-adoption survey update; the June 1, 2026 interim final rule (CMS-2454-IFC) we will fold in over the coming weeks, as we have time to interpret and model it. After January 1, 2027, a tenth render mode will track actual disenrollment data as states report it.",
    sources: [
      { label: "ACS 5-Year 2024 tables (Census Bureau, Dec 2025 release)", href: "https://www.census.gov/programs-surveys/acs" },
      { label: "ACS PUMS 5-Year 2020-2024 (Census Bureau)", href: "https://www.census.gov/programs-surveys/acs/microdata.html" },
      { label: "CMS T-MSIS state monthly enrollment (latest quarterly extract)" },
      { label: "BLS LAUS (Feb 2025 to Jan 2026 12-month average)" },
      { label: "KFF / Georgetown CCF state adoption survey (Apr 2026)" },
      { label: "SAMHSA NSDUH 2023-2024 State SAE (released Oct 2024)", href: "https://www.samhsa.gov/data" },
      { label: "BJS NPS Prisoners in 2023 (released Sep 2025)", href: "https://bjs.ojp.gov" },
      { label: "CBO scoring of OBBBA Section 71119 (July 2025)" },
      { label: "Urban Institute HIPSM March 2026" },
      { label: "CBPP state and CD estimates (July 2025)" },
      { label: "Census SAHIE 2022 (county-level Medicaid cross-validation)" },
      { label: "FCC Form 477 (broadband by census block)" },
      { label: "OpenStreetMap (routing for drive-time-to-DSS computations)" },
    ],
    parameters: [
      { label: "Pipeline orchestrator", value: "pipeline/build.sh (stages 01 through 13)" },
      { label: "Per-state ACS PUMS cache", value: "output/pums_state_cache/<abbr>_classified.parquet (schema versioned)" },
      { label: "Per-state exemption rates", value: "output/state_exemption_rates.parquet (stage 04e)" },
      { label: "Loss-breakdown JSON consumed by sankey", value: "public/data/medicaid-loss-breakdown.json (stage 07b)" },
      { label: "Refresh commitment", value: "Within 30 days of ACS or KFF updates; IFR folded in over the coming weeks as modeled" },
    ],
    caveats: [
      "ACS undercounts Medicaid by 15-25%. We never trust ACS levels.",
      "BJS NPS counts state-prison releases only, not jails or federal facilities. We calibrate to a national prior to compensate.",
      "Pregnancy uses a uniform national prior; no public state-level T-MSIS pregnancy-pathway enrollment data is available yet.",
    ],
    methodologyAnchor: "#section-7-vintage-and-refresh-schedule",
  },
];

const SubText = ({ children }: { children: React.ReactNode }) => (
  <div className="mb-1 mt-3 font-sans text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">
    {children}
  </div>
);

const SourcesList = ({ sources }: { sources: Source[] }) => (
  <ul className="list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-slate-700">
    {sources.map((s, i) => (
      <li key={i}>
        {s.href ? (
          <a href={s.href} target="_blank" rel="noreferrer" className="text-cobalt hover:underline">
            {s.label}
          </a>
        ) : (
          s.label
        )}
      </li>
    ))}
  </ul>
);

const ParametersList = ({ parameters }: { parameters: Parameter[] }) => (
  <dl className="grid grid-cols-1 gap-y-1.5 text-[13px] leading-relaxed text-slate-700 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] sm:gap-x-4">
    {parameters.map((p, i) => (
      <React.Fragment key={i}>
        <dt className="font-sans font-semibold text-slate-600">{p.label}</dt>
        <dd className="break-words font-mono text-[12.5px] text-slate-800">{p.value}</dd>
      </React.Fragment>
    ))}
  </dl>
);

const Caveats = ({ caveats }: { caveats: string[] }) => (
  <div className="mt-1 rounded-md bg-amber-50 px-4 py-3 text-[13px] leading-relaxed text-amber-900">
    <div className="mb-1 font-sans text-[10px] font-semibold uppercase tracking-[0.08em] text-amber-700">
      Caveats
    </div>
    <ul className="list-disc space-y-1 pl-5">
      {caveats.map((c, i) => (
        <li key={i}>{c}</li>
      ))}
    </ul>
  </div>
);

export default function MedicaidMethodologyPanel() {
  return (
    <div className="mt-2">
      <p className="mb-4 text-sm leading-relaxed text-slate-600">
        Detailed methodology, sources, and parameters for each part of the
        gizmo. Thank you to Sarah Esty for her generous feedback, expertise,
        and guidance on the methodology. Sections are closed by default; open the ones you want.
        State Medicaid directors evaluating these numbers for their own
        operational planning will want most of this; everyone else can
        read the headline and trust that the work is documented here.
      </p>

      <div className="divide-y divide-slate-200 overflow-hidden rounded-lg border border-slate-200 bg-white">
        {SECTIONS.map((section) => (
          <details key={section.id} className="group">
            <summary
              className="flex cursor-pointer list-none items-start justify-between gap-3 px-4 py-3 transition hover:bg-slate-50"
              aria-label={`Toggle: ${section.title}`}
            >
              <div className="flex-1">
                <div
                  className="font-serif text-[16px] font-semibold leading-snug"
                  style={{ color: COBALT }}
                >
                  {section.title}
                </div>
                <p className="mt-1 text-[13px] leading-relaxed text-slate-600 group-open:hidden">
                  {section.summary}
                </p>
              </div>
              <span
                aria-hidden
                className="mt-1 inline-flex h-5 w-5 flex-none items-center justify-center rounded-full bg-slate-100 text-[12px] font-bold text-slate-600 transition group-open:rotate-45 group-open:bg-cobalt/10 group-open:text-cobalt"
              >
                +
              </span>
            </summary>

            <div className="space-y-3 border-t border-slate-100 bg-slate-50/50 px-4 py-4 text-[13.5px] leading-relaxed text-charcoal">
              <p className="text-slate-700">{section.summary}</p>
              {section.body && <p className="text-slate-700">{section.body}</p>}

              <SubText>Sources</SubText>
              <SourcesList sources={section.sources} />

              <SubText>Parameters</SubText>
              <ParametersList parameters={section.parameters} />

              {section.caveats.length > 0 && (
                <>
                  <SubText>Caveats</SubText>
                  <Caveats caveats={section.caveats} />
                </>
              )}

              <div className="pt-1">
                <a
                  href={`${METHODOLOGY_DOC_URL}${section.methodologyAnchor}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-sans text-[11px] font-semibold uppercase tracking-[0.06em] text-cobalt transition hover:text-cobalt/80"
                  style={{ color: COBALT }}
                >
                  Read this section in METHODOLOGY.md
                  <span aria-hidden>↗</span>
                </a>
              </div>
            </div>
          </details>
        ))}
      </div>

      <p className="mt-4 text-[13px] leading-relaxed text-slate-600">
        Full methodology document with every parameter, every limitation, every
        source, including the things we got wrong and the things we'll refine
        in the next iteration:&nbsp;
        <a
          href={METHODOLOGY_DOC_URL}
          target="_blank"
          rel="noreferrer"
          className="font-semibold text-cobalt hover:underline"
        >
          Read the full methodology ↗
        </a>
      </p>
    </div>
  );
}
