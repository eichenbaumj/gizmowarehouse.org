// MedicaidSubjectProfile — three "bouncy" rollups landing the 1/3-1/3-1/3 story
// of the 18.5M subject pool: already working enough, categorically exempt by
// reason (disabled or caretakers — "find them at the hospital and the school"),
// and the residual mix (part-time, students, postpartum, no qualifying activity).
//
// Adapts to a selected state via a local dropdown OR the medicaid-select-state
// custom event (dispatched by MedicaidFindYourState and MedicaidWorkRequirementsMap).
// Staggered IntersectionObserver fade-in on scroll into view.
//
// Heavy synthetic disclosure: KFF + Urban Institute state-level shares applied
// to subject counts. State variation (where modeled) is small. Numbers are
// distributional estimates, not microdata. See "How these numbers were derived"
// pill for the ACS PUMS derivation chain.

import { useEffect, useRef, useState } from "react";
import MethodologyInfo from "@/components/MethodologyInfo";
import InfoTip from "@/components/InfoTip";
import { useReadMode } from "@/lib/readMode";

interface ProfileEntry {
  state_fips: string;
  state_abbr: string;
  state_name: string;
  subject_total: number;
  age_band: Record<string, number>;
  has_kids_under_14: Record<string, number>;
  work_hours_per_wk: Record<string, number>;
  not_working_breakdown?: Record<string, number>;
  // v8: share of in-pool parents covered outside expansion (Section 1931) and
  // therefore not subject to the work requirement at all.
  share_parents_covered_outside_expansion?: number;
}

type Profile = Record<string, ProfileEntry>;

interface RollupNumbers {
  total: number;
  // Card 1 — Already meeting the requirement
  compliantCount: number;
  workingHoursCount: number;        // 80+ hrs/month (verifiable via pay stubs)
  incomeGateCount: number;          // part-time but meeting $580/month in high-min-wage states
  studentCount: number;             // full-time student → qualifying activity via school
  // Card 2 — Categorically exempt
  exemptByReasonCount: number;
  disabledCount: number;
  caretakerCount: number;
  postpartumCount: number;
  // Card 3 — Residual (not visible in any tracked path)
  residualCount: number;
  partTimeBelowGateCount: number;   // PT workers NOT in high-min-wage states
  noActivityCount: number;          // 0 hrs and not in any surveyed exemption
}

// Share of national part-time (1-79 hr) Medicaid subjects who plausibly meet
// the alternative $580/month income gate. Estimate:
//   ~30% of US Medicaid enrollees live in states with min wage ≥ $14.50/hr
//   (CA, NY, WA, MA, NJ, MD, CT, IL, DE, NV, DC carry that share).
//   Of those PT workers, roughly 60% earn at or above the gate at their hours
//   (the rest work too few hours to clear $580 even at the higher rate).
// So ~0.30 × 0.60 ≈ 0.18 of national PT count.
// This is a national prior; per-state min wage variation would refine it. v6.
const INCOME_GATE_PT_SHARE = 0.18;

// Sarah Esty v8 review: the "not visible in any tracked path" residual is the
// bucket that decides the outcome, and it splits two ways. We size the
// "anticipated to drop" segment as a share of the no-observed-activity group —
// the population the policy nominally targets. CBO assumes most of them move
// into compliance; the Arkansas (2018) and Georgia Pathways (2023) experience
// suggests many won't and will simply drop. The remainder of the no-activity
// group, plus the part-time-under-gate workers, are almost certainly compliant
// or exempt but have no data trail (caregivers of a disabled adult, SUD
// recovery, kinship caregivers, recent incarceration, AI/AN) — their coverage
// is downstream of state comms, submission platform, and timely review. The
// 0.55 share is editorial, landing the drop segment a little under half of the
// residual, consistent with Esty's read; flagged as such on the card.
const ANTICIPATED_DROP_SHARE_OF_NOACTIVITY = 0.55;

function computeRollupNumbers(entry: ProfileEntry): RollupNumbers {
  const total = entry.subject_total;
  const work = entry.work_hours_per_wk;
  const nw = entry.not_working_breakdown ?? {};

  const workingHoursCount = Math.round((work["80_plus"] ?? 0) * total);
  const notWorkingCount = Math.round((work["0"] ?? 0) * total);
  const partTimeShare = (work["1-19"] ?? 0) + (work["20-79"] ?? 0);
  const partTimeTotal = Math.round(partTimeShare * total);

  // Sarah Esty v5 review: in higher-min-wage states the bar is $580/month
  // income rather than 80 hours. Part-time workers in those states meeting
  // the income gate are compliant, not residual.
  const incomeGateCount = Math.round(partTimeTotal * INCOME_GATE_PT_SHARE);
  const partTimeBelowGateCount = partTimeTotal - incomeGateCount;

  const disabledCount = Math.round((nw.disabled ?? 0) * notWorkingCount);
  const caretakerCount = Math.round((nw.caretaker ?? 0) * notWorkingCount);
  const postpartumCount = Math.round((nw.postpartum ?? 0) * notWorkingCount);
  const studentCount = Math.round((nw.student ?? 0) * notWorkingCount);
  const noActivityCount = Math.round((nw.other ?? 0) * notWorkingCount);

  // Card 1: meeting the requirement = 80+hrs working + PT meeting income gate + students
  // (students meet via "in school" qualifying activity, not via the exemption pathway)
  const compliantCount = workingHoursCount + incomeGateCount + studentCount;

  // Card 2: categorically exempt = disabled + parent caretaker + postpartum
  // (Smaller categorical groups — SUD, recent incarceration, kinship, disabled-adult
  // caregivers, AI/AN, foster youth, AYA cancer survivor — aren't separately surveyed
  // at the subject-pool level; they show up in the loss-breakdown.)
  const exemptByReasonCount = disabledCount + caretakerCount + postpartumCount;

  // Card 3: residual = PT below gate + no-activity. Includes the genuine
  // non-compliant residual (~0.55M nationally) plus people in categorical exemptions
  // not separately surveyed in this profile (the rest).
  const residualCount = partTimeBelowGateCount + noActivityCount;

  return {
    total,
    compliantCount,
    workingHoursCount,
    incomeGateCount,
    studentCount,
    exemptByReasonCount,
    disabledCount,
    caretakerCount,
    postpartumCount,
    residualCount,
    partTimeBelowGateCount,
    noActivityCount,
  };
}

function formatBigN(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 10_000) return Math.round(n / 1000).toLocaleString() + "K";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return n.toLocaleString();
}

function ratioOf(n: number, total: number): string {
  if (total <= 0 || n <= 0) return "—";
  // Display as percentage of the subject pool so the three cards sum cleanly
  // to ~100%. Earlier "≈ 1 in X" formulation made the cards look like they
  // didn't fully partition the pool (1/3 + 1/3 + 1/4 = 11/12, not 1).
  const pct = (n / total) * 100;
  return `${pct.toFixed(0)}% of the subject pool`;
}

interface RollupCardProps {
  eyebrow: string;
  bigN: number;
  ratio: string;
  headline: string;
  bodyMain: string;
  active: boolean;
  staggerMs: number;
  /** BLUF: hide the body paragraph and offer it behind an ⓘ tooltip instead. */
  compact?: boolean;
  /** Where the compact tooltip popover hangs (avoid clipping at the edges). */
  tipAlign?: "left" | "right" | "center";
}

function RollupCard({
  eyebrow,
  bigN,
  ratio,
  headline,
  bodyMain,
  active,
  staggerMs,
  compact = false,
  tipAlign = "left",
}: RollupCardProps) {
  return (
    <div
      className={
        "rounded-xl border border-slate-200 bg-white p-6 shadow-sm" +
        (compact ? "" : " transition-transform duration-500 ease-out")
      }
      // The reveal transform creates a stacking context, which would trap an
      // open InfoTip popover behind the neighbouring card. Compact (BLUF) cards
      // skip the reveal so the z-50 popover can paint above its siblings.
      style={
        compact
          ? undefined
          : {
              transform: active ? "translateY(0)" : "translateY(14px)",
              transitionDelay: active ? `${staggerMs}ms` : "0ms",
            }
      }
    >
      <div className="font-sans text-[11px] font-bold uppercase tracking-[0.16em] text-carolina">
        {eyebrow}
      </div>
      <div
        className="mt-3 font-serif font-black leading-none tabular-nums text-cobalt"
        style={{ fontSize: "clamp(2.4rem, 4vw, 3.4rem)" }}
      >
        {formatBigN(bigN)}
      </div>
      <div className="mt-1 font-sans text-[13px] font-bold text-carolina">
        {ratio}
      </div>
      <div className="mt-4 flex items-start gap-1.5 font-serif text-[1.05rem] font-semibold leading-tight text-charcoal">
        <span>{headline}</span>
        {compact && (
          <InfoTip align={tipAlign} label={`Detail: ${headline}`}>
            {bodyMain}
          </InfoTip>
        )}
      </div>
      {!compact && (
        <p className="mt-2 text-[0.92rem] leading-snug text-slate-700">
          {bodyMain}
        </p>
      )}
    </div>
  );
}

export default function MedicaidSubjectProfile() {
  const bluf = useReadMode() === "bluf";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [stateFips, setStateFips] = useState<string>("_national");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(false);

  // Fetch profile data
  useEffect(() => {
    fetch("/data/medicaid-subject-profile.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((j: Profile) => setProfile(j))
      .catch(() => setProfile(null));
  }, []);

  // Sync to map / find-your-state state-select event
  useEffect(() => {
    const onSelect = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail && typeof detail.fips === "string" && detail.fips) {
        setStateFips(detail.fips);
      }
    };
    window.addEventListener("medicaid-select-state", onSelect);
    return () => window.removeEventListener("medicaid-select-state", onSelect);
  }, []);

  // Bouncy reveal on scroll-into-view
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setInView(true);
      },
      { threshold: 0.25 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (!profile) {
    return (
      <div className="not-prose my-8 rounded-lg border border-slate-200 bg-slate-50 px-6 py-8 text-center text-sm text-slate-500">
        Loading subject profile…
      </div>
    );
  }

  const entry = profile[stateFips] ?? profile._national;
  if (!entry) return null;

  const nums = computeRollupNumbers(entry);
  const {
    total,
    compliantCount,
    workingHoursCount,
    incomeGateCount,
    studentCount,
    exemptByReasonCount,
    disabledCount,
    caretakerCount,
    postpartumCount,
    residualCount,
    partTimeBelowGateCount,
    noActivityCount,
  } = nums;

  const compliantBody = `${formatBigN(workingHoursCount)} work 80+ hours every month, verifiable through pay stubs. About ${formatBigN(incomeGateCount)} more work fewer hours but meet the $580/month income gate available in higher-minimum-wage states. And ${formatBigN(studentCount)} are full-time students. People in this group lose coverage only when the state portal can't read multi-employer hours, variable-shift volatility, 1099 income, or NSC enrollment data.`;
  const exemptBody = `${formatBigN(disabledCount)} are medically frail; ${formatBigN(caretakerCount)} are primary caretakers of a child under 14; ${formatBigN(postpartumCount)} are postpartum. For parent caretakers, the child's Medicaid case already carries the household linkage, so the exemption should auto-apply without anyone filling out a form. For medically frail enrollees and adults in SUD treatment, states should pull Medicaid claims data and the health information exchange first, and ask for a physician letter only as a last resort. Smaller categorical groups (former foster youth, AI/AN, recently incarcerated, AYA cancer survivor, SNAP/TANF work-req compliant, non-parent kinship caregivers, caregivers of disabled adults) appear in the loss-breakdown below.`;
  const anticipatedDropCount = Math.round(noActivityCount * ANTICIPATED_DROP_SHARE_OF_NOACTIVITY);
  const likelyQualifyNoDataCount = residualCount - anticipatedDropCount;
  const residualBody = `This group splits two ways, and the split decides the outcome. About ${formatBigN(anticipatedDropCount)} show no qualifying activity the survey can see: the population the policy nominally targets. CBO assumes most of them move into compliance through work, school, or volunteering; the Arkansas (2018) and Georgia Pathways (2023) experience suggests many won't, and will simply drop. The other ${formatBigN(likelyQualifyNoDataCount)} are almost certainly compliant or exempt but have no data trail to prove it: part-time workers under the income gate, caregivers of a disabled adult, people in SUD recovery, kinship caregivers, recently incarcerated adults, and AI/AN enrollees (exemptions this subject-level survey can't see, but which the loss-breakdown below counts). Whether that second group keeps coverage is downstream of state operations (comms quality, the submission platform, and timely, correct reviews), not of whether they qualify. The split between the two is an editorial estimate.`;

  // States dropdown — sorted alphabetically
  const states = Object.values(profile)
    .filter((e) => e.state_fips !== "_national")
    .sort((a, b) => a.state_name.localeCompare(b.state_name));

  const stateLabel =
    entry.state_fips === "_national" ? "the United States" : entry.state_name;

  return (
    <div
      ref={containerRef}
      className="not-prose my-10"
      style={{
        width: "min(100vw - 1.5rem, 80rem)",
        marginLeft: "calc(50% - min(50vw - 0.75rem, 40rem))",
        marginRight: "calc(50% - min(50vw - 0.75rem, 40rem))",
      }}
    >
      {/* Header: state selector + total + methods pill */}
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="font-sans text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            View
          </span>
          <select
            value={stateFips}
            onChange={(e) => setStateFips(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-sans text-sm shadow-sm focus:border-cobalt focus:outline-none focus:ring-1 focus:ring-cobalt"
          >
            <option value="_national">National (United States)</option>
            {states.map((s) => (
              <option key={s.state_fips} value={s.state_fips}>
                {s.state_name}
              </option>
            ))}
          </select>
          <span className="font-serif text-[15px] tabular-nums text-charcoal">
            <span className="font-semibold text-cobalt">{formatBigN(total)}</span>{" "}
            subject to verification in {stateLabel}
          </span>
        </div>
        <MethodologyInfo
          id="demographic_profile"
          variant="pill"
          align="right"
          label="How these numbers were derived"
        />
      </div>

      {/* Lead-in: ground the per-card ratios in the subject-pool denominator.
          Skipped in BLUF — the short-form prose already frames the split. */}
      {entry.state_fips === "_national" && !bluf && (
        <p className="mb-4 text-[13px] leading-relaxed text-slate-600">
          That 18.5M is roughly 1 in 14 American adults. It splits into three groups: people already meeting the requirement, people categorically exempt, and a third group the survey can't place in either bucket.
        </p>
      )}

      {/* 3-up rollups */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        <RollupCard
          eyebrow="Auto-confirm most with income or school enrollment"
          bigN={compliantCount}
          ratio={ratioOf(compliantCount, total)}
          headline="Meeting requirements through work or school"
          bodyMain={compliantBody}
          active={inView}
          staggerMs={0}
          compact={bluf}
          tipAlign="left"
        />
        <RollupCard
          eyebrow="Auto-confirm most with state data sources"
          bigN={exemptByReasonCount}
          ratio={ratioOf(exemptByReasonCount, total)}
          headline="Known categorically exempt"
          bodyMain={exemptBody}
          active={inView}
          staggerMs={120}
          compact={bluf}
          tipAlign="center"
        />
        <RollupCard
          eyebrow="More information needed"
          bigN={residualCount}
          ratio={ratioOf(residualCount, total)}
          headline="Not obviously meeting requirements"
          bodyMain={residualBody}
          active={inView}
          staggerMs={240}
          compact={bluf}
          tipAlign="right"
        />
      </div>

      {/* Parent / Section 1931 caveat — parents covered outside expansion aren't
          subject to the requirement at all. Full piece: amber callout. BLUF:
          tucked behind an ⓘ pill so the short view stays lean. */}
      {typeof entry.share_parents_covered_outside_expansion === "number" &&
        entry.share_parents_covered_outside_expansion > 0 &&
        (() => {
          const parentsInner = (
            <>
              <strong className="text-slate-700">A note on parents.</strong>{" "}
              About {Math.round((entry.share_parents_covered_outside_expansion ?? 0) * 100)}% of low-income
              parents in {stateLabel} are covered through the mandatory Section 1931
              parent/caretaker pathway, not expansion, so the work requirement doesn't
              reach them, and they're already removed from these counts. That share
              swings hard by state (about 75% in California, under 20% in Arkansas)
              because each state sets its own Section 1931 income limit. It's the single
              biggest reason a state's real subject pool can differ from a back-of-envelope
              "everyone 0–138% FPL" estimate. See the{" "}
              <a href="/gizmo/medicaid-work-requirements/methodology#section-3-1-the-exemption-stack"
                 className="font-semibold text-cobalt hover:underline">methodology</a>{" "}
              for how we model it.
            </>
          );
          return bluf ? (
            <div className="mt-4">
              <InfoTip variant="pill" align="left" label="A note on parents">
                {parentsInner}
              </InfoTip>
            </div>
          ) : (
            <p className="mt-5 rounded-md border-l-4 border-amber-300 bg-amber-50/60 px-4 py-3 text-[12.5px] leading-relaxed text-slate-600">
              {parentsInner}
            </p>
          );
        })()}
    </div>
  );
}
