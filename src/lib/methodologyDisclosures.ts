// Methodology disclosures: the click-to-reveal explanation that lives behind
// every "ⓘ" icon in the Medicaid work-requirements gizmo. Each entry walks the
// curious reader through the synthetic chain (census → boundaries → enrollment
// → subjects → employment) so hidden assumptions don't undermine trust.
//
// The disclosures are never open by default. The page must read cleanly
// without them. Tone: short, specific, defensible. Full chain stays in
// METHODOLOGY.md.

export interface Disclosure {
  /** Short title, sentence-case, no period. */
  title: string;
  /**
   * Ordered breadcrumb of the data-derivation chain. Each step is one short
   * phrase the reader can scan in a second. Render as a vertical list with
   * arrow connectors.
   */
  chain: string[];
  /**
   * What this disclosure is *honest* about: explicit assumptions, caveats,
   * known divergences. 1-3 short lines.
   */
  caveats: string[];
  /**
   * The anchor (slug under METHODOLOGY.md) for "See full methodology" link.
   * Falls back to "" → top of doc.
   */
  fullMethodologyAnchor?: string;
  /**
   * Which methodology page this disclosure links to. Defaults to the Medicaid
   * methodology doc (METHODOLOGY_DOC_URL). Other gizmos that reuse this popover
   * (e.g. the public-private compensation piece) set their own page here.
   */
  docUrl?: string;
}

// Public, in-site methodology page (rendered from METHODOLOGY.md). Previously
// this pointed at the GitHub blob URL, which 404s for everyone because the repo
// is private (Sarah Esty flagged the dead links). The dedicated route below
// serves the full methodology on gizmowarehouse.org, with section anchors that
// match the `<a id="...">` tags embedded in METHODOLOGY.md.
const METHOD_DOC = "/gizmo/medicaid-work-requirements/methodology";

export const METHODOLOGY_DOC_URL = METHOD_DOC;

// Public-private compensation gizmo: its disclosures link to its own appendix.
const COMPGAP_METHOD_DOC = "/gizmo/public-private-compensation-comparison/methodology";

export const DISCLOSURES: Record<string, Disclosure> = {
  // ---- Map render modes ---------------------------------------------------
  "map.subject_count": {
    title: "How we estimate subject enrollees per place",
    chain: [
      "ACS 5-Year 2024 (B27003 Medicaid coverage × B18135 disability × B17024 income) for tract-level distribution",
      "CMS T-MSIS administrative enrollment files for state-level count (calibrated to projected Jan 2027 expansion-adult population)",
      "Cell value = state count × (cell working-age pop × poverty rate) ÷ sum of that quantity across the state",
      "OBBBA §1902(xx) exemptions (parent of child ≤13, medically frail, pregnant, SNAP-compliant) deducted via ACS cross-tabs where available, state-level rates otherwise",
    ],
    caveats: [
      "State totals anchor to CBO's 18.5M national control; within-state apportionment is modeled from population × poverty (a shape × level estimate), not microdata head counts.",
      "Margin of error is inherited from the parent tract; hex/grid resolution is a display choice, not a measurement choice.",
    ],
    fullMethodologyAnchor: "#section-3-subject-count",
  },

  "map.subject_rate": {
    title: "How we compute the % subject rate",
    chain: [
      "Subject count (above) as numerator",
      "ACS B01001 working-age population (19–64) as denominator",
      "Rate = subject count ÷ working-age population, clipped to [0, 0.5]",
    ],
    caveats: [
      "The rate is structural. Places where Medicaid expansion supports a large share of working-age adults score high regardless of population size.",
      "Non-expansion states render as 0 here; their working-age uninsured population shows on the secondary overlay.",
    ],
    fullMethodologyAnchor: "#section-3-subject-rate",
  },

  "map.burden_index": {
    title: "How we compute compliance burden",
    chain: [
      "0.4 × verification difficulty (limited-English households, low broadband, distance to DSS office)",
      "0.3 × labor volatility (employment concentration in seasonal / gig / construction / hospitality)",
      "0.3 × access gap (postal-route reliability, prior procedural-disenrollment rate from SNAP)",
      "Centered on the national median so the diverging palette reads symmetrically",
    ],
    caveats: [
      "This is an editorial composite. Weights were chosen to mirror predictors from the Arkansas 2018 and Georgia Pathways 2023 Section 1115 evaluations.",
      "Not from CMS or HHS. Treat as 'where to focus,' not 'who will fail.'",
    ],
    fullMethodologyAnchor: "#section-5-burden-index",
  },

  "map.loss_exposure": {
    title: "How we project coverage loss",
    chain: [
      "Each (state, subgroup): subject pool × eligibility rate × failure rate, summed bottom-up — not a flat churn rate",
      "Documentation-failure buckets scaled ×1.15 for cross-cycle compounding (14 six-month renewals by 2034)",
      "Each state's bottom-up total apportioned to its counties and cells by subject share",
    ],
    caveats: [
      "Lands at ~5.42M nationally, just above CBO's 5.2M baseline and inside Urban's 4.9–10.1M combined range. No calibration applied (the total is in range).",
      "Loss is the *operational* number directors should plan around. Not a forecast of need, but of paperwork failure.",
    ],
    fullMethodologyAnchor: "#section-6-loss-exposure",
  },

  // ---- Spatial chain ------------------------------------------------------
  "map.county_apportionment": {
    title: "How county estimates were apportioned from state totals",
    chain: [
      "State subject total → from CMS T-MSIS calibrated to CBO's national 18.5M",
      "County weight = working-age pop × poverty rate",
      "County share of state = county weight ÷ Σ county weights in same state",
      "County estimate = state total × county share",
    ],
    caveats: [
      "Apportionment, not measurement. Counties with similar pop and poverty get similar estimates by construction.",
      "When real T-MSIS county breakouts are available (some states release them; most don't), we'll replace this within-state model with administrative data.",
    ],
    fullMethodologyAnchor: "#section-4-county-apportionment",
  },

  "map.hex_within_county": {
    title: "How 5-mile hex estimates were derived from the parent county",
    chain: [
      "County subject total (above)",
      "Hex weight = cell total population × max(poverty rate, 0.1)",
      "Hex share of county = hex weight ÷ Σ hex weights in same county",
      "Hex estimate = county total × hex share",
    ],
    caveats: [
      "Preserves the county total: Σ hex values within a county equals the county estimate.",
      "Within-county precision comes from population and poverty distribution, not from microdata. Wealthy suburbs render lower, dense high-poverty cells render higher.",
    ],
    fullMethodologyAnchor: "#section-7-hex-within-county",
  },

  "map.grid_within_county": {
    title: "How 1-mile cell estimates were derived from the parent county",
    chain: [
      "Same within-county weighting as the 5-mile hex layer, applied to ~1.7M 1-mile cells (NPE grid)",
      "Cell weight = cell total population × max(poverty rate, 0.1)",
      "Cell estimate = county total × (cell weight ÷ Σ cell weights in same county)",
      "Nearest census place attached via spatial nearest-neighbor join for popup names",
    ],
    caveats: [
      "Sum of cell values in a county equals the county total. Precision is redistributed within the county, not added.",
      "Coverage is contiguous 48 states + DC; Alaska / Hawaii / non-expansion states are intentionally absent at this layer.",
    ],
    fullMethodologyAnchor: "#section-8-grid-within-county",
  },

  // ---- Demographic profile (heaviest disclosure) --------------------------
  demographic_profile: {
    title: "How we built the subject pool composition",
    chain: [
      "ACS PUMS 5-Year 2020-2024 microdata, pulled per state via Census API + bulk-download cache",
      "Filtered to Medicaid-covered low-income adults: AGEP 19-64, HINS4=1, POVPIP ≤ 138 (138% FPL), PWGTP > 0",
      "Remove parents covered through the non-expansion Section 1931 pathway (POVPIP below the state's 1931 limit, so not subject to the requirement at all) and recent non-citizens inside the federal 5-year bar (CIT, YOEP)",
      "Age bands and weekly-hours-to-monthly-hours buckets (WKHP × 4) computed directly, weighted by person weight (PWGTP)",
      "'Of the not-working' panel: priority-assigned exemption status using DIS (disability), SERIALNO+AGEP household join (caretaker), SEX+FER (postpartum), SCH (full-time student); residual = 'not in any qualifying activity'",
    ],
    caveats: [
      "Shares are real per-state microdata estimates, not national priors applied uniformly. Each panel reflects that state's refined Medicaid expansion-subject composition.",
      "The Section 1931 carve-out is the largest single adjustment. In high-1931-limit states (e.g. California, where ~75% of low-income parents are covered outside expansion) it sharply lowers the parent share; in low-limit states (Arkansas ~16%) it barely moves it. This is the dominant reason a state's true subject pool differs from a raw 0-138% FPL tabulation.",
      "Two honest limits remain after these screens: POVPIP is the Census family poverty ratio, not adjusted to Medicaid MAGI (a few-point error), and we cannot perfectly isolate everyone enrolled through a non-expansion eligibility category (disabled/aged) beyond what the medically-frail exemption and the 1931/citizenship screens remove. We use Census family-based POVPIP + household linkage, not a single blunt health-insurance-unit measure.",
      "Subject totals per state remain calibrated estimates from state_summary.json (raked to CBO 18.5M nationally), not raw PUMS counts. Per KFF/CBPP posture, read per-state demographic splits as distributional, not microdata-grade.",
    ],
    fullMethodologyAnchor: "#section-9-demographic-profile",
  },

  // ---- Hero stats ---------------------------------------------------------
  "hero_stat.subject": {
    title: "Where the 18.5 million number comes from",
    chain: [
      "Section 71119 of OBBBA establishes the work-requirement framework at §1902(xx)",
      "CBO's projection of 18.5M subject to monthly verification matches our state-totals sum",
      "Subject-count differences between CBO and KFF (16.8–20.1M range) trace to definitions of 'exempted at point-of-verification' vs 'reportable each month'",
    ],
    caveats: [
      "Reasonable estimates range ~17–20M depending on exemption interpretation.",
      "Our headline matches CBO's central figure for comparability.",
    ],
    fullMethodologyAnchor: "#section-2-subject-pool",
  },

  "hero_stat.loss": {
    title: "Where the 5.4 million number comes from",
    chain: [
      "Our bottom-up model: per-(state, subgroup) subject pool × eligibility rate × failure rate, summed to ~5.42M (shown as 5.4M)",
      "Just above CBO's 5.2M benchmark (coverage loss by 2034 from the work requirement alone)",
      "Inside Urban's combined work-req + six-month-redetermination range of 4.9–10.1M (2028, high vs low mitigation)",
    ],
    caveats: [
      "Mostly *not* failure to work. Failure to prove work each month under whatever verification system the state stands up.",
      "Loss compounds across renewal cycles; the bottom-up total applies a ×1.15 cross-cycle factor (14 six-month renewals by 2034).",
    ],
    fullMethodologyAnchor: "#section-2-loss-projection",
  },

  // ---- Loss breakdown sankey ---------------------------------------------
  loss_breakdown: {
    title: "How we sized each subgroup in the 5.4M loss",
    chain: [
      "Bottom-up, not raked: for each (state, subgroup), loss = subject_pool × eligibility_rate × failure_rate. Documentation-failure buckets are scaled by a ×1.15 cross-cycle compounding factor (14 six-month renewal cycles by 2034), then summed to a national total.",
      "The national total lands at ~5.42M, just above CBO's 5.2M baseline, and the compliant / exempt / non-compliant split (~38% / ~51% / ~10%) emerges from the math, not from an editorial target. A uniform calibration multiplier is applied only if the total falls outside [4.5M, 11M] (it doesn't, so none is applied).",
      "Compliant-doc subgroups: per-state ACS PUMS 5-Year 2020-2024 classification (multi-PT, variable shifts, self-employed, seasonal, cash construction, gig/courier), plus students and volunteering/job-training.",
      "Exemption-doc subgroups: per-state ACS PUMS (medically frail, parent caregivers ≤13, kinship caregivers, caregivers of a disabled adult, pregnancy via FER, and AI/AN via the RACAIAN race recode), SAMHSA NSDUH state SUD prevalence, BJS NPS state releases, and bundled priors for the remaining small categorical exemptions (foster youth, AYA cancer, SNAP/TANF).",
      "Per-(state, subgroup) failure rates attenuate with each ex parte capability flag the state has set; the ex parte composite itself now leads with each state's observed 2023-2026 ex parte renewal rate.",
    ],
    caveats: [
      "The compliant/exempt/non-compliant split is a bottom-up result, not an editorial input. The ~10% genuine non-compliance is consistent with Sommers et al. (2019), whose Arkansas evaluation found ~95% of disenrollments were among people working enough hours or exemption-eligible.",
      "Per-state subgroup eligibility rates are clipped to a national-prior envelope to bound PUMS small-sample noise. The envelope is widened for AI/AN (a direct Census measure with genuine ~40× state variation, since Alaska's expansion pool is ~42% AI/AN) and the floor is lowered for parents (the Section 1931 carve-out legitimately drives expansion-parent rates near zero in high-1931 states).",
      "Pregnancy/postpartum uses PUMS FER (gave birth in the past 12 months) per state; it is the smallest exemption subgroup, so its impact is bounded.",
      "Subgroup-by-state failure-rate parameters reflect KFF's April 2026 stated implementation intent plus observed unwinding ex parte rates, not yet-observable work-requirement operational performance.",
      "We deliberately do NOT publish per-state estimated administrative-churn rates. The ex parte score is a relative ranking signal, not a coverage-loss forecast.",
    ],
    fullMethodologyAnchor: "#section-3-4-loss-breakdown-estimation",
  },

  // ---- State PDF brief ----------------------------------------------------
  state_brief: {
    title: "What's in the state brief and how it was generated",
    chain: [
      "Subject + loss estimates from this map's county/hex/grid layers",
      "Top 10 affected counties by subject count + by burden index",
      "State-specific exemption summary (parents of young children, SNAP-compliant, etc.)",
      "Operational checklist for state Medicaid agencies (December 31 timeline)",
    ],
    caveats: [
      "Auto-generated from pipeline stage 12. Numbers reflect the same shape × level model as the map: state totals raked to CMS T-MSIS and CBO's 18.5M, within-state composition from ACS PUMS.",
      "If the brief disagrees with KFF or Urban by >15%, the methodology document calls out which assumption drives the gap.",
    ],
    fullMethodologyAnchor: "#section-12-state-briefs",
  },

  // =========================================================================
  // Public-private compensation gizmo. docUrl points at its own appendix.
  // =========================================================================
  "compgap.shape": {
    title: "Where the headcounts come from",
    chain: [
      "ACS PUMS 1-year (2023): employed residents aged 25-64 in wage/salary jobs, split federal / state / local by class of worker, weighted by person weight",
      "Federal includes active-duty military; the local 'education' figure is the SOC 25 occupation group",
      "Same basis as the Sankey and the wage charts, so the counts line up across the piece",
    ],
    caveats: [
      "These differ from the familiar BLS payroll figures (~23M government jobs, ~15% of U.S. employment). BLS counts jobs of all ages, civilian only; ACS counts employed people 25-64 and includes the military. ACS runs above BLS for federal — self-report overstates federal employment by roughly 1M — and below for local, which omits the part-time and under-25 jobs BLS counts.",
      "The NCES count of K-12 classroom teachers specifically is 3.25M; the broader education group here (~4.1M local, ~5.5M across all levels) adds public-college faculty, special-ed, librarians, and teaching assistants.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#data-sources",
  },

  "compgap.workforce": {
    title: "How the workforce-mix chart is built",
    chain: [
      "ACS PUMS 1-year microdata (2023): employed residents aged 25 to 64 in wage/salary jobs, weighted by person weight",
      "Occupations grouped on a finer SOC→workgroup crosswalk than the wage domains, so the 'Other' slice all but disappears and active-duty military gets its own flow",
      "Employment summed by government level (federal / state / local) × workgroup; the small service tail is rolled into one 'Other roles' node for legibility",
    ],
    caveats: [
      "These ACS counts differ from the BLS CES headcounts in the stat strip on purpose: CES counts payroll JOBS of all ages, civilian only; ACS counts PEOPLE 25-64 by occupation and includes the military. The chart is about the occupation mix, not the totals.",
      "The teacher numbers reconcile once you match definitions. The stat strip's 3.25M is NCES K-12 classroom teachers; the Sankey's 'Teachers & instructors' (~5.5M) is the full SOC 25 occupation group (K-12 plus public-college faculty, special-ed, librarians, and teaching assistants) across federal, state, and local. Restrict the ACS to local K-12 classroom teachers and it lands around 3.2M, in line with NCES.",
      "The military slice is all uniformed personnel aged 25-64 (~0.85M), not just military-specific occupation codes, so service members in medical, legal, admin, or trade roles count as military rather than scattering into those buckets. The full active-duty force is about 1.3M counting all ages (DoD); the force skews young, so the 25-64 count is smaller. It sits only on the federal side; the BLS federal figure is civilian-only.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#data-sources",
  },

  "compgap.macro_divergence": {
    title: "How the compensation-growth lines are built",
    chain: [
      "BLS Employment Cost Index (ECI): private vs state-&-local total compensation and wages, fixed-bundle index (controls for job mix), 2001-present",
      "Each nominal ECI index deflated by CPI-U and rebased to 2005 = 100, so the lines show REAL compensation growth",
      "Federal line: BEA NIPA compensation per full-time-equivalent (federal civilian), the series ECI lacks, deflated the same way",
    ],
    caveats: [
      "ECI is composition-controlled and economy-wide, so it shows the AVERAGE job — it cannot reveal the top of the distribution, which is the point of the domain section.",
      "ECI starts 2001 on a consistent NAICS basis; the federal BEA series is average comp per FTE (mix can drift), so the federal line is not strictly comparable to the fixed-weight ECI lines.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#data-sources",
  },

  "compgap.macro_topdist": {
    title: "How the wage charts are built",
    chain: [
      "ACS PUMS 1-year microdata (Census API), full-time workers aged 25 to 64",
      "Weighted median annual wage in constant 2026 dollars (deflated by CPI-U to the latest month)",
      "Private p50/p90/p95 trace the private wage ladder; the government median is shown alongside",
      "The 'exclude teachers' toggle drops the education-instruction occupations (SOC 25) from the government line",
      "The 'knowledge economy' toggle on the ladder restricts both sides to the knowledge-economy domains (software, legal, finance, engineering, management), where the private top has pulled away hardest",
    ],
    caveats: [
      "Census top-codes very high wages, so the 90th and 95th percentiles understate how far the true top has pulled away. The top-1% wage series come from tax records (SSA / Kopczuk-Saez-Song, EPI) and are economy-wide, not splittable public vs private.",
      "In cash, the government median tracks or sits above the private median. The gap concentrates in the knowledge-economy domains and at the top of each field, shown in the domain explorer.",
      "Weighted percentiles use linear interpolation (the standard method). ACS still reports wages in rounded amounts, so a median can sit on a common round-number salary; read small median differences as approximate.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#data-sources",
  },

  "compgap.domain_gap": {
    title: "How the public-vs-private wage gap is measured",
    chain: [
      "ACS PUMS, class-of-worker splits federal / state / local government from private (NOT NAICS industry, which misclassifies government workers)",
      "Occupations rolled into domains via a versioned SOC→domain crosswalk (software, legal, finance, engineering, management, healthcare, education, …)",
      "Within each domain and government level: weighted real hourly wage percentiles (p50/p75/p90), full-time, age 25 to 64",
      "Median gap = government median over private-for-profit median, minus 1",
      "Top-of-field gap = 90th-percentile government over 90th-percentile private, where the elite private firms pay",
    ],
    caveats: [
      "Raw gaps reflect who works where (public workers are older and more educated), so we also report a composition-adjusted gap. See the adjusted-gap note.",
      "Adjustment controls for education, age, hours, and geography, but NOT for the mix of jobs within a domain. Protective service is the clearest case: the public side is sworn police and firefighters, the private side is mostly security guards, so the large adjusted 'premium' is largely different jobs. The selected-domain note under the chart breaks out that mix (ACS, stage 07).",
      "The top-of-field (90th-percentile) gap is a floor: Census top-codes the highest earners, so the true elite private firms pay even more than shown.",
      "Wages only. The benefits and pension value, where public compensation is relatively richer, is handled in the total-comp note.",
      "Federal, state, and local are kept separate because they have opposite signs; a single 'public sector' average cancels them out.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#how-the-gap-is-estimated",
  },

  "compgap.adjusted_gap": {
    title: "What 'composition-adjusted' means here",
    chain: [
      "Weighted Mincer regression: log(real hourly wage) on education, an age (experience) quadratic, hours, sex, race, and state",
      "The coefficient on each government-level indicator (vs private for-profit) is the adjusted gap, converted to a percent",
      "Reported with a sensitivity RANGE across three specifications (full / drop education / drop geography)",
    ],
    caveats: [
      "The specification choice is exactly the EPI (penalty) vs Biggs-Richwine (premium) dispute — dropping the education control moves the number materially, which is why we show the spread, not a single point.",
      "Standard errors are heteroskedasticity-robust (HC1). Design-based replicate-weight SEs are a documented future refinement.",
      "This is descriptive, not causal — it does not identify the effect of public employment on a given worker.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#how-the-gap-is-estimated",
  },

  "compgap.compression": {
    title: "How the compression curve is built",
    chain: [
      "Within each education bucket (ACS PUMS, full-time, age 25-64), the composition-adjusted government-vs-private wage gap, computed separately for federal, state, and local",
      "Same weighted Mincer specification as the adjusted-gap note — education, age quadratic, hours, sex, race, state — read off the government-level indicator",
      "Plotted across education levels so the floor-to-ceiling slope is visible; zero = the comparable private-sector wage",
    ],
    caveats: [
      "These are WAGES. The external anchor in the caption — CBO (2024), Comparing the Compensation of Federal and Private-Sector Employees in 2022 — is TOTAL COMPENSATION (wages + benefits) and is federal-only; both trace the same downward slope. The low-end federal premium is largely a benefits story, and on wages alone federal pay runs modestly below private overall.",
      "Federal stays positive furthest up the ladder; state and local cross into a penalty early, so the bottom-end public premium does not generalize cleanly across all of government. State/local levels are also more contested in the literature than federal.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#how-the-gap-is-estimated",
  },

  "compgap.education_gradient": {
    title: "Why the public advantage flips at the top",
    chain: [
      "Within each education bucket, the composition-adjusted government-vs-private wage gap (ACS PUMS)",
      "The gap is positive at lower education and turns negative at the bachelor's-and-above tail",
      "Anchored to CBO 2024 total-compensation estimates: federal +5% overall, but −4% at master's and −22% at doctorate/professional",
    ],
    caveats: [
      "Our PUMS figures are WAGES; the CBO gradient is TOTAL COMPENSATION (wages + benefits). Both show the same reversal at the high-education tail.",
      "CBO, Comparing the Compensation of Federal and Private-Sector Employees, 2022 (April 2024).",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#how-the-gap-is-estimated",
  },

  "compgap.locality": {
    title: "How a city or state government is compared to private pay",
    chain: [
      "Cities: the government's own payroll file (NYC, Chicago, SF, Seattle, LA) — full-time salaried base pay, in 2026 dollars",
      "Free-text civil-service titles mapped to occupation domains via an ordered keyword classifier (titles are not coded to SOC)",
      "Private comparator for a city = the private sector in that city's METRO (central county/counties), median and 90th percentile, from ACS PUMS in those PUMAs",
      "States: government and private medians both come from ACS PUMS for that state",
    ],
    caveats: [
      "Title→occupation mapping is the largest source of error in the city view; treat domain assignments in payroll files as approximate, and the all-occupations view as rough (it mixes very different jobs).",
      "City pay is full-time salaried base pay; the metro-private comparator is full-time/full-year ACS PUMS. Payroll files also have coverage gaps (e.g. NYC withholds some NYPD/DA detail).",
      "ACS top-codes the highest earners, so the top-of-field (90th-percentile) private figure — and therefore the gap — is a floor.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#data-sources",
  },

  "compgap.total_comp": {
    title: "Wages vs total compensation",
    chain: [
      "The charts here are WAGES (ACS PUMS, BLS ECI wages series)",
      "Public compensation carries a relatively larger benefits + pension load",
      "BLS ECEC: state & local total compensation ≈ $65.68/hr vs private $46.15/hr; benefits are 38.3% of comp vs 29.9%",
    ],
    caveats: [
      "A wages-only comparison overstates the public lag at lower education and understates it at the top — the CBO total-compensation gradient still goes negative for advanced degrees.",
      "Pension value depends on contested discount-rate assumptions, which drive much of the disagreement between studies.",
    ],
    docUrl: COMPGAP_METHOD_DOC,
    fullMethodologyAnchor: "#known-limitations",
  },
};

export type DisclosureId = keyof typeof DISCLOSURES;

export function getDisclosure(id: string): Disclosure | undefined {
  return DISCLOSURES[id];
}
