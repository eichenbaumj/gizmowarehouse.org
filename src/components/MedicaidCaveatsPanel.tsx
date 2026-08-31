// MedicaidCaveatsPanel: top-level uncertainty disclosure.
//
// State Medicaid directors need to see the load-bearing caveats before they
// dig into accordion methodology. This panel surfaces 5 high-severity flags
// in a single non-collapsible amber-tinted callout, always visible. Each item
// is a headline + 2-3 sentence body + anchor link into the methodology
// accordion for the full derivation.
//
// Placement on the gizmo page: between the "Find your state" section and the
// "Methodology" accordion. The order is intentional: directors finish the
// per-state download, see the caveats panel, then can dive into methodology
// if they want more.

import { METHODOLOGY_DOC_URL } from "@/lib/methodologyDisclosures";

const COBALT = "#1F1FD6";

interface Caveat {
  /** Stable anchor for in-page links */
  id: string;
  /** Bold one-line headline. Max ~14 words. */
  headline: string;
  /** 2-3 sentence explanation. Plain language; no jargon if avoidable. */
  body: string;
  /** Anchor under METHODOLOGY.md (full text on GitHub) */
  methodologyAnchor: string;
  /** Optional external source (e.g. a regulation), rendered next to "See methodology". */
  sourceLink?: { label: string; url: string };
}

const CAVEATS: Caveat[] = [
  {
    id: "bottom-up-calibration",
    headline:
      "The Sankey is bottom-up and converges with the CBO's 5.2M.",
    body:
      "Each state's loss is computed per-(subgroup) as subject pool × eligibility rate × failure rate, then summed and scaled by a cross-cycle compounding factor (×1.15) to translate single-renewal-cycle snapshots into a cumulative 2034 figure. The within-bucket proportions and the compliant/exempt/non-compliant split emerge from the math, not from an editorial target. The bottom-up national total currently lands at 5.42M, just above CBO's 5.2M baseline. A fallback calibration multiplier is wired in for honesty (would scale to the CBO + Urban midpoint of 6.4M if the bottom-up total ever fell outside [4.5M, 11M]), but it currently evaluates to 1.0, so no calibration is applied. Whether a multiplier is in effect is always disclosed in the loss-breakdown JSON's national_targets field.",
    methodologyAnchor: "#section-3-4-loss-breakdown-estimation",
  },
  {
    id: "waiver-subject-states",
    headline:
      "Three non-expansion states are subject through Section 1115 waivers: Wisconsin and Georgia are modeled, Tennessee is flagged.",
    body:
      "OBBBA's work requirement reaches the ACA expansion-adult group plus, per CMS's June 2026 list, certain Section 1115 waiver enrollees in three non-expansion states. Wisconsin's BadgerCare Plus childless-adult waiver (~198,000 enrolled, ≤100% FPL) is not currently work-conditional, so it carries a genuine new loss; we size its subject pool from administrative enrollment and run it through the same exemption and documentation-failure model as expansion states. Wisconsin's exemption rates are derived from its own ACS PUMS, the same method every other state uses (e.g. medical frailty ~18% rather than the 28% national prior); only the documentation-failure rates fall back to the national average, since no work-requirement-specific verification-feed data exists for this waiver population yet. Two honest caveats remain: the published enrollment already excludes disability-pathway enrollees, so the PUMS frailty rate is measured on a broader sample than the childless waiver slice, and we zero the parent exemption because the population is childless by definition. Treat Wisconsin's figure as a projection, not a precise count. Georgia's Pathways enrollees (~8,000) already face an 80-hour work requirement, so OBBBA adds no net-new procedural loss; Georgia appears as subject with zero modeled new loss. Tennessee is reached only through TennCare's 1115 'MEC Additions' group — parents/caretaker relatives covered to 100% FPL (eligibility group EG16 ≈ 17,758 in the Jan–Mar 2025 quarterly report). Because OBBBA exempts parents of a child under 14, almost the entire group is exempt and the genuinely-subject slice is negligible, so Tennessee is flagged as in-scope but modeled with no loss (KFF and Georgetown CCF read OBBBA as effectively not applying there). Five expansion states (Hawaii, Massachusetts, New York, Oregon, Utah) also have waiver populations the requirement reaches; they are already counted as expansion states, leaving a small residual undercount of their waiver-only enrollees that we do not separately quantify.",
    methodologyAnchor: "#section-3-4-loss-breakdown-estimation",
  },
  {
    id: "hhs-rule-published",
    headline:
      "HHS interim final rule issued June 1, 2026; it narrows the medical-frailty exemption.",
    body:
      "CMS issued the interim final rule (CMS-2454-IFC) on June 1, 2026. It ties the medical-frailty exemption to a health condition that impairs the ability to meet the 80-hour requirement, and bars states from categorically exempting people by diagnosis — a narrower test than a condition count. Our medically-frail proxy is built from ACS PUMS functional-difficulty flags: a disability indicator (DIS) plus two or more of self-care (DDRS), ambulatory (DPHY), independent-living (DOUT), and cognitive (DREM) difficulty. Against the rule's work-ability test that proxy likely overstates some physical disabilities while understating intellectual, mental-health, and substance-use conditions that ACS doesn't register as a functional difficulty. We expect this to modestly affect projections and will refine the proxy as states operationalize the rule.",
    methodologyAnchor: "#section-3-5-per-state-exemption-eligibility-rate-derivation",
    sourceLink: {
      label: "Read the IFR (CMS)",
      url: "https://www.cms.gov/newsroom/fact-sheets/medicaid-community-engagement-requirement-certain-individuals-interim-final-rule-comment-period-cms",
    },
  },
  {
    id: "medical-frailty-mmis-hedge",
    headline:
      "Medical frailty rates are derived from ACS PUMS and likely undercount what state MMIS data shows.",
    body:
      "PUMS-derived medical-frailty rates run roughly 15-25% of the expansion adult population in most states. State Medicaid directors are reporting that MMIS claims data show 25-30% of expansion adults meeting medical-frailty criteria once chronic conditions are surfaced through diagnostic codes. We anchor the national prior near the 27.5% midpoint of that reported range (we use 28%) and apply per-state attenuation through the ex parte capability flags. Even with this adjustment, the medically-frail-without-auto-match count likely understates the group; we expect to refine per state as 2027 implementation data lands.",
    methodologyAnchor: "#section-3-5-per-state-exemption-eligibility-rate-derivation",
  },
  {
    id: "all-exemptions-per-state",
    headline:
      "Eight of the nine exemption-eligibility rates are derived per state (ACS PUMS, SAMHSA, or BJS); cross-validated against external benchmarks.",
    body:
      "The PUMS classifier identifies (a) non-parent kinship-led households via RELSHIPP code combinations, (b) primary caregivers of working-age disabled adults via household linkage and a spouse-then-householder-then-eldest heuristic, (c) pregnant/postpartum subjects via PUMS FER (gave-birth-in-past-12-months), and (d) American Indian / Alaska Native subjects via the RACAIAN recode, in addition to medical frailty, parent caretaking, and student status. The PUMS-derived rates are bounded by a floor/cap envelope of [0.5×, 2.0×] of the national prior. The smallest, bundled subgroup (former foster youth, AYA cancer survivor, SNAP/TANF compliant) uses a research-anchored national prior with state attenuation through the SNAP/TANF and child-welfare data flags. The base failure rates and per-data-source-flag attenuation multipliers remain uniform across states; the operative per-(state, subgroup) failure rate varies via the state's data-source flag profile. Stage 04f cross-validates the PUMS-derived rates against external benchmarks (KFF disability + parent shares, NCES IPEDS enrollment, PPI release rates, SAMHSA NSDUH SUD, AECF KIDS COUNT for kinship, AARP/NAC State Data Profiles for caregivers of disabled adults). Current pass rates above 90% for the kinship and disabled-adult-caregiver benchmarks.",
    methodologyAnchor: "#section-3-5-per-state-exemption-eligibility-rate-derivation",
  },
  {
    id: "overlap-per-record",
    headline:
      "The multi-category overlap view uses per-record PUMS joint counts, scaled to CBO-anchored subject totals.",
    body:
      "The upset plot above the Sankey is built from per-record ACS PUMS classifications: each subject in the post-filter sample (Medicaid, age 19-64, POVPIP ≤138) is sorted into exactly one of 16 cells across four boolean flags (working ≥80hrs/month, parent caregiver of child ≤13, medically frail, full-time student). Per-state cell counts are then scaled so each state's total matches its CBO-anchored subject count, preserving the PUMS-derived proportions while keeping totals consistent with the rest of the page. The four categories cover the largest qualifying-activity buckets but not all of them; subjects whose only qualifying status is SUD treatment, recent incarceration, pregnancy, former foster youth, or AI/AN tribal membership appear in the zero-bucket band here and in the appropriate exempt subgroup of the Sankey.",
    methodologyAnchor: "#section-3-5-per-state-exemption-eligibility-rate-derivation",
  },
  {
    id: "ex-parte-ranking",
    headline:
      "The ex parte capability scores are relative ranking signals, not coverage-loss forecasts.",
    body:
      "The 0-100 composite leads with each state's OBSERVED ex parte renewal rate (the share of Medicaid renewals it actually auto-completed during the 2023-2026 unwinding, from CMS eligibility-processing data), weighted 50%. Data sources (the work-requirement-specific feeds) carry 35%, and documented prior Section 1115 work-requirement churn 15%. One caveat on the observed rate: it measures realized auto-renewal for income/eligibility, which is necessary but not sufficient for work-requirement verification (that also needs hours and exemption feeds). Treat the composite as a relative ranking, not a predicted churn rate. States at 75+ should see substantially less procedural disenrollment than states at 30; exact rates will emerge from 2027 pilot data.",
    methodologyAnchor: "#ex-parte-verification-capability-score",
  },
  {
    id: "subject-pool-definition",
    headline:
      "Our subject-pool counts are anchored to administrative totals; the demographic composition is ACS-derived and should be read as distributional.",
    body:
      "State totals are raked to CMS T-MSIS expansion enrollment and the national subject pool to CBO's 18.5M, so the levels are anchored to authoritative sources, not a raw \"everyone 0-138% FPL\" tabulation. The within-pool composition comes from ACS PUMS, and we make three refinements that distinguish this from a naive ACS analysis: we remove parents covered through the non-expansion Section 1931 pathway (who aren't subject at all), we screen out recent non-citizens inside the federal 5-year bar, and we use Census family-based poverty ratios plus household linkage rather than a single blunt health-insurance-unit measure. Two honest limits remain: ACS poverty ratio (POVPIP) is not adjusted to Medicaid MAGI (a few-point error), and we cannot perfectly identify everyone enrolled through a non-expansion eligibility category. Per KFF's and CBPP's own posture, we therefore present per-state demographic splits as distributional estimates, not microdata-grade head counts.",
    methodologyAnchor: "#section-3-7-subject-pool-definition-and-its-limits",
  },
  {
    id: "acs-undercount",
    headline:
      "ACS undercounts Medicaid enrollment by 15-25%.",
    body:
      "This is the well-documented Medicaid undercount (Boudreaux et al. 2015, Health Services Research). We use ACS exclusively for within-state geographic distribution, never for absolute levels. State totals come from CMS T-MSIS administrative data raked to CBO control totals. County and tract estimates are apportioned from the state total, not derived from ACS levels directly.",
    methodologyAnchor: "#section-1-what-were-estimating",
  },
  {
    id: "map-is-visualization",
    headline:
      "The map is a visualization of where impact will concentrate, not an operational outreach plan.",
    body:
      "Read the dense red counties as 'this is where the procedural-disenrollment wave will be largest,' not as 'this is where to send a 2027 field campaign.' The variables that move a county's loss exposure are upstream of the rule: ex parte data plumbing, vendor configuration, cross-program data hookups, and the enrollee comms plan that ships in Q4 2026. Once an enrollee in one of these counties is receiving a termination letter, field outreach is a recovery effort rather than a way to prevent the loss.",
    methodologyAnchor: "#section-3-6-what-this-gizmo-is-not",
  },
];

export default function MedicaidCaveatsPanel() {
  return (
    <div className="mt-4 mb-2">
      <div className="rounded-lg border-l-4 border-amber-400 bg-amber-50/70 px-6 py-5">
        <div className="mb-3 flex items-baseline gap-3">
          <span
            aria-hidden
            className="font-sans text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-700"
          >
            Caveats & uncertainty flags
          </span>
          <span className="font-sans text-[12px] text-slate-600">
            Read these before drawing operational conclusions.
          </span>
        </div>

        <ol className="space-y-4 text-[14px] leading-relaxed text-charcoal">
          {CAVEATS.map((c, i) => (
            <li key={c.id} className="flex gap-3">
              <span
                aria-hidden
                className="mt-[2px] inline-flex h-6 w-6 flex-none items-center justify-center rounded-full bg-white font-serif text-[13px] font-semibold ring-1 ring-amber-300"
                style={{ color: COBALT }}
              >
                {i + 1}
              </span>
              <div className="flex-1">
                <div
                  className="font-serif text-[15px] font-semibold leading-snug"
                  style={{ color: COBALT }}
                >
                  {c.headline}
                </div>
                <p className="mt-1 text-slate-700">{c.body}</p>
                <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <a
                    href={`${METHODOLOGY_DOC_URL}${c.methodologyAnchor}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-sans text-[11px] font-semibold uppercase tracking-[0.06em] text-cobalt transition hover:text-cobalt/80"
                    style={{ color: COBALT }}
                  >
                    See methodology
                    <span aria-hidden>↗</span>
                  </a>
                  {c.sourceLink && (
                    <a
                      href={c.sourceLink.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 font-sans text-[11px] font-semibold uppercase tracking-[0.06em] text-cobalt transition hover:text-cobalt/80"
                      style={{ color: COBALT }}
                    >
                      {c.sourceLink.label}
                      <span aria-hidden>↗</span>
                    </a>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
