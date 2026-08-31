// MedicaidLossSankey — a 3-column inline-SVG flow diagram showing how the
// projected 5.2M Medicaid coverage losses break down by failure mode, plus a
// state-level ex parte verification capability table.
//
// Renders the chart with hand-positioned Bezier curves so the visual matches
// the rest of the gizmo's hand-tuned aesthetic. No D3, no Sankey library.
// State switching recomputes column-3 widths from the loss-breakdown JSON.
//
// Data source: /data/medicaid-loss-breakdown.json (produced by pipeline 07b).

import { useEffect, useMemo, useRef, useState } from "react";
import MethodologyInfo from "@/components/MethodologyInfo";
import { type CartogramView, CARTOGRAM_VIEW_LABELS } from "@/lib/medicaidExParteViews";

interface Subgroup {
  label: string;
  count: number;
  narrative?: string;
}

interface ExParteScores {
  composite: number | null;
  observed_ex_parte: number | null;   // v8: realized ex parte renewal rate × 100
  core_capability: number | null;      // v8: context sub-metric only (not in composite)
  data_sources: number | null;
  historical_churn: number | null;
}

// Back-compat alias for code that referenced the v4 three-factor type.
type ThreeScores = ExParteScores;

interface CoreComponents {
  system_integration: number;
  account_matching: number;
  deduplication: number;
  operational_sla: number;
  self_attestation_policy: number;
  identity_proofing: number;
}

interface SourceComponents {
  wage_data: number;
  frailty_data: number;
  other_data: number;
}

interface ExParteBands {
  composite: string | null;
  observed_ex_parte: string | null;   // v8
  core_capability: string | null;
  data_sources: string | null;
  historical_churn: string | null;
}

type ThreeBands = ExParteBands;

interface HistoricalExperience {
  denial_rate: number | null;
  implementation_window: string;
  people_affected: string;
  primary_source: string;
  context_note: string;
}

interface BreakdownEntry {
  abbr: string;
  name: string;
  ex_parte_score: number | null;
  ex_parte_band: string | null;
  scores?: ExParteScores;
  core_components?: CoreComponents | null;
  source_components?: SourceComponents | null;
  bands?: ExParteBands;
  historical_experience?: HistoricalExperience;
  system_vendor: string;
  subject_count: number;
  total_loss_2034: number;
  eligible_but_lose: number;
  genuinely_noncompliant: number;
  work_hours_doc_failures: {
    total: number;
    subgroups: Record<string, Subgroup>;
  };
  exemption_doc_failures: {
    total: number;
    subgroups: Record<string, Subgroup>;
  };
}

export interface ExParteRow {
  fips: string;
  abbr: string;
  name: string;
  score: number | null;            // back-compat alias = composite
  band: string | null;             // back-compat alias = bands.composite
  scores?: ExParteScores;
  observed_ex_parte_rate?: number | null;  // v8: raw 0-1 rate, for display
  core_components?: CoreComponents | null;
  source_components?: SourceComponents | null;
  bands?: ExParteBands;
  historical_experience?: HistoricalExperience;
  system_vendor: string;
  notes: string;
  expansion: boolean;
  // Subject-via-1115-waiver flags (WI/GA sized, TN listed-not-quantified). These
  // states are in scope but unscored (no work-requirement-specific verification
  // data), so the cartogram renders them distinctly rather than as "unaffected".
  subject_via_waiver?: boolean;
  waiver_listed?: boolean;
  loss_quantified?: boolean;
  already_work_conditional?: boolean;
  flags: Record<string, boolean>;
}

// v8: lead with the observed ex parte rate (realized capability). Core
// capability (vendor tier) is now a hover-only context metric, not a top view.

interface LossBreakdown {
  version: string;
  vintage: Record<string, string>;
  national_targets: Record<string, number>;
  _national: BreakdownEntry;
  states: Record<string, BreakdownEntry>;
  ex_parte_table: ExParteRow[];
}

// Order in which subgroups render (top to bottom in their bucket).
// v7: Sarah Esty legal-category restructure. "Compliant" (work/school/volunteer)
// and "exempt" (medical/caregiving/pregnancy) are distinct under OBBBA. Students
// moved to the workdoc/compliant bucket; new volunteering_job_training added
// there. New other_categorical_exempt added to the exemption side.
const WORKDOC_KEYS = [
  "gig_courier",
  "cash_construction",
  "multi_part_time",
  "seasonal_ag_hosp",
  "self_employed_other",
  "variable_shifts",
  "students_no_match",            // v7 moved from EXEMPTION_KEYS
  "volunteering_job_training",    // v7 NEW
] as const;

const EXEMPTION_KEYS = [
  "medically_frail_no_match",
  "caregivers_no_match",
  "kinship_caregivers_other",      // v5 NEW (split from caregivers_no_match)
  "caregivers_disabled_adult",     // v5 NEW
  "sud_not_flagged",
  "recent_incarc_data_gap",
  "pregnancy_lag",
  "ai_an_exempt",                  // v8 NEW (split out of the bundle; PUMS-derived)
  "other_categorical_exempt",      // v7 (foster youth, AYA cancer, SNAP/TANF)
] as const;

// Color stops. Cobalt family for work-hours bucket (cool factual), Carolina
// blue family for exemption bucket (warmer-cool), gray for non-compliant.
const COBALT = "#1F1FD6";
const COBALT_LIGHT = "#7B9BE0";
const COBALT_FAINT = "#D6E4F2";
const CAROLINA = "#21A8E0";
const CAROLINA_LIGHT = "#7AC5E8";
const CAROLINA_FAINT = "#C8E7F5";
const GRAY = "#94A3B8";
const GRAY_FAINT = "#E2E8F0";
const CHARCOAL = "#3B3B3B";

// Per-subgroup color (lighter shades within each parent family).
const SUBGROUP_COLORS: Record<string, string> = {
  gig_courier: "#1F1FD6",
  cash_construction: "#3A3DE5",
  multi_part_time: "#5C6BEF",
  seasonal_ag_hosp: "#7B9BE0",
  self_employed_other: "#9DC2EE",
  variable_shifts: "#BCD9F5",
  // Compliant bucket (cobalt family): students + volunteering live here in v7+.
  students_no_match: "#94D6EF",
  volunteering_job_training: "#A9C4F0",
  // Exemption bucket (carolina family).
  medically_frail_no_match: "#1A8FC4",
  caregivers_no_match: "#21A8E0",
  kinship_caregivers_other: "#3FB4E5",
  caregivers_disabled_adult: "#58BEE9",
  sud_not_flagged: "#6EC8EB",
  recent_incarc_data_gap: "#86D2EE",
  pregnancy_lag: "#A6DEF2",
  ai_an_exempt: "#0E7FB0",            // v8: distinct deeper teal for the AI/AN line
  other_categorical_exempt: "#BBE5F4",
};

function fmtCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 100_000) return `${Math.round(n / 1000).toLocaleString()}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return n.toLocaleString();
}

function fmtPct(num: number, denom: number): string {
  if (denom === 0) return "—";
  return `${((num / denom) * 100).toFixed(0)}%`;
}

// SVG layout constants. The viewBox is fixed; the parent <svg> scales via
// width=100% with preserveAspectRatio so the layout stays proportional on
// tablets and reduces gracefully to the mobile fallback below 640px.
const VB_W = 1200;
const VB_H = 720;
const LEFT_X = 60;
const SRC_W = 30;
const BUCKET_X = 380;
const BUCKET_W = 22;
const SUB_X = 800;
const SUB_W = 18;
const LABEL_X = 832;
const COL_TOP = 40;
const COL_BOT = 680;
const COL_H = COL_BOT - COL_TOP;
const GAP_BETWEEN_BUCKETS = 18;
const GAP_BETWEEN_SUBGROUPS = 6;

interface BandLayout {
  srcTop: number;
  srcBot: number;
  tgtTop: number;
  tgtBot: number;
}

function bandPath(srcX: number, tgtX: number, layout: BandLayout): string {
  const ctrl1 = srcX + (tgtX - srcX) * 0.5;
  const ctrl2 = srcX + (tgtX - srcX) * 0.5;
  return [
    `M ${srcX} ${layout.srcTop}`,
    `C ${ctrl1} ${layout.srcTop} ${ctrl2} ${layout.tgtTop} ${tgtX} ${layout.tgtTop}`,
    `L ${tgtX} ${layout.tgtBot}`,
    `C ${ctrl2} ${layout.tgtBot} ${ctrl1} ${layout.srcBot} ${srcX} ${layout.srcBot}`,
    `Z`,
  ].join(" ");
}

export default function MedicaidLossSankey() {
  const [data, setData] = useState<LossBreakdown | null>(null);
  const [stateKey, setStateKey] = useState<string>("US");
  const [hoverBand, setHoverBand] = useState<string | null>(null);
  // v4: click-to-open narrative tooltip on Sankey subgroup bars.
  // Tracks { key, bucket: "wd" | "ex", x, y } where x/y are SVG-relative
  // coordinates of the bar's right edge mid-height.
  const [activeSubgroup, setActiveSubgroup] = useState<{
    key: string;
    bucket: "wd" | "ex";
    label: string;
    count: number;
    narrative: string;
    color: string;
    pixelX: number;
    pixelY: number;
  } | null>(null);
  // Reference to the Sankey wrapper for click-outside dismissal.
  const sankeyWrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fetch("/data/medicaid-loss-breakdown.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((j: LossBreakdown) => setData(j))
      .catch(() => setData(null));
  }, []);

  // ESC dismisses the active narrative card.
  useEffect(() => {
    if (!activeSubgroup) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setActiveSubgroup(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeSubgroup]);

  // Open the narrative tooltip card for a clicked subgroup bar.
  const showSubgroupCard = (
    sub: { key: string; label: string; count: number; narrative?: string },
    bucket: "wd" | "ex",
    el: SVGGElement,
    color: string,
  ) => {
    if (!sankeyWrapperRef.current) return;
    const wrapperRect = sankeyWrapperRef.current.getBoundingClientRect();
    const barRect = el.getBoundingClientRect();
    setActiveSubgroup({
      key: sub.key,
      bucket,
      label: sub.label,
      count: sub.count,
      narrative: sub.narrative || "",
      color,
      pixelX: barRect.right - wrapperRect.left,
      pixelY: (barRect.top + barRect.bottom) / 2 - wrapperRect.top,
    });
  };

  const entry: BreakdownEntry | undefined = useMemo(() => {
    if (!data) return undefined;
    if (stateKey === "US") return data._national;
    return data.states[stateKey] ?? data._national;
  }, [data, stateKey]);

  // Compute SVG layout for the current entry.
  const layout = useMemo(() => {
    if (!entry) return null;
    const total = entry.total_loss_2034;
    if (total === 0) return null;
    const px = (n: number) => (n / total) * (COL_H - 2 * GAP_BETWEEN_BUCKETS);

    // Source column = the full total. Single block.
    const srcTop = COL_TOP;
    const srcBot = COL_BOT;
    const srcMid = (srcTop + srcBot) / 2;

    // Bucket column: 3 blocks stacked top → bottom (work, exemption, non-compliant)
    // with gaps. We compute their y-extents.
    const wdH = px(entry.work_hours_doc_failures.total);
    const exH = px(entry.exemption_doc_failures.total);
    const ncH = px(entry.genuinely_noncompliant);
    let y = COL_TOP;
    const workBucket = { top: y, bot: y + wdH };
    y = workBucket.bot + GAP_BETWEEN_BUCKETS;
    const exBucket = { top: y, bot: y + exH };
    y = exBucket.bot + GAP_BETWEEN_BUCKETS;
    const ncBucket = { top: y, bot: y + ncH };

    // For col-1 → col-2 connection: each bucket draws a band from a slice of
    // the source column to its block. The source y-extents are proportional
    // to that bucket's share of total.
    let srcCursor = srcTop;
    const wdSrcSlice = { top: srcCursor, bot: srcCursor + wdH };
    srcCursor = wdSrcSlice.bot;
    const exSrcSlice = { top: srcCursor, bot: srcCursor + exH };
    srcCursor = exSrcSlice.bot;
    const ncSrcSlice = { top: srcCursor, bot: srcCursor + ncH };

    // Subgroup column: 6 in the workdoc family (top), 6 in the exemption family (middle).
    // Lay out each subgroup's bar height proportionally inside its bucket, but
    // place the LABEL on a separate slotted track with a minimum vertical gap.
    // Then draw a small leader line from the bar mid-y to the label mid-y so
    // tiny subgroups don't collide with their neighbors' labels.
    const LABEL_MIN_GAP = 30; // ~ one body-line + a hair
    const layoutSubgroups = (
      subs: Record<string, Subgroup>,
      keys: readonly string[],
      bucketTop: number,
      bucketBot: number,
    ) => {
      const total = keys.reduce((sum, k) => sum + (subs[k]?.count ?? 0), 0);
      const avail = bucketBot - bucketTop - (keys.length - 1) * GAP_BETWEEN_SUBGROUPS;
      // First pass: bar geometry (proportional).
      let yc = bucketTop;
      const bars: Array<{ key: string; top: number; bot: number; count: number; label: string }> = [];
      for (const k of keys) {
        const s = subs[k];
        const c = s?.count ?? 0;
        const h = total > 0 ? (c / total) * avail : 0;
        bars.push({ key: k, top: yc, bot: yc + h, count: c, label: s?.label ?? k });
        yc += h + GAP_BETWEEN_SUBGROUPS;
      }
      // Second pass: label slot positions (enforce min spacing while staying
      // within the bucket's vertical band; if forced collisions push past the
      // bottom, back-propagate upward to avoid overflow).
      const labelYs: number[] = bars.map((b) => (b.top + b.bot) / 2);
      // Forward pass: enforce min spacing going down.
      for (let i = 1; i < labelYs.length; i++) {
        const minAllowed = labelYs[i - 1] + LABEL_MIN_GAP;
        if (labelYs[i] < minAllowed) labelYs[i] = minAllowed;
      }
      // If the last label exceeds the bucket bottom, back-propagate.
      const labelTopPad = 12;
      const labelBotPad = 12;
      const labelTopLimit = bucketTop + labelTopPad;
      const labelBotLimit = bucketBot - labelBotPad;
      if (labelYs[labelYs.length - 1] > labelBotLimit) {
        labelYs[labelYs.length - 1] = labelBotLimit;
        for (let i = labelYs.length - 2; i >= 0; i--) {
          const maxAllowed = labelYs[i + 1] - LABEL_MIN_GAP;
          if (labelYs[i] > maxAllowed) labelYs[i] = maxAllowed;
        }
      }
      // And clamp the first up if it ended below the top.
      if (labelYs[0] < labelTopLimit) labelYs[0] = labelTopLimit;
      return bars.map((b, i) => ({ ...b, labelY: labelYs[i] }));
    };

    const wdSubs = layoutSubgroups(
      entry.work_hours_doc_failures.subgroups,
      WORKDOC_KEYS,
      workBucket.top,
      workBucket.bot,
    );
    const exSubs = layoutSubgroups(
      entry.exemption_doc_failures.subgroups,
      EXEMPTION_KEYS,
      exBucket.top,
      exBucket.bot,
    );

    return {
      total,
      srcTop, srcBot, srcMid,
      workBucket, exBucket, ncBucket,
      wdSrcSlice, exSrcSlice, ncSrcSlice,
      wdSubs, exSubs,
    };
  }, [entry]);

  if (!data || !entry || !layout) {
    return (
      <div className="not-prose my-8 rounded-lg border border-slate-200 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
        Loading the documentation-failure breakdown…
      </div>
    );
  }

  // Sorted states for dropdown.
  const stateOptions = Object.entries(data.states)
    .map(([fips, s]) => ({ fips, name: s.name, abbr: s.abbr }))
    .sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div
      ref={sankeyWrapperRef}
      className="not-prose relative my-10 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
      style={{
        width: "min(100vw - 1.5rem, 80rem)",
        marginLeft: "calc(50% - min(50vw - 0.75rem, 40rem))",
        marginRight: "calc(50% - min(50vw - 0.75rem, 40rem))",
      }}
      onClick={(e) => {
        // Dismiss the narrative card if user clicks anywhere outside an
        // already-open card (the card stops propagation itself).
        if (activeSubgroup) setActiveSubgroup(null);
        void e;
      }}
    >
      {/* Header */}
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <div className="font-serif text-lg font-semibold text-cobalt">
          Where the projected losses come from
        </div>
        <MethodologyInfo
          id="loss_breakdown"
          variant="pill"
          align="right"
          label="How these subgroups were sized"
        />
      </div>
      <p className="text-sm leading-relaxed text-slate-600">
        Projected Medicaid coverage loss by 2034 broken into named subgroups.
        Most of these people <em>are</em> working or <em>are</em>{" "}
        exemption-eligible but can't prove it on every renewal cycle through
        their state's verification portal. The total is a bottom-up sum that
        converges with CBO's 5.2M baseline; state-level numbers reflect each
        state's expansion-pool size, its ACS PUMS-derived employment and
        exemption mix (per-state disability prevalence, household
        composition, student enrollment, plus SAMHSA NSDUH SUD and BJS NPS
        incarceration data), and its ex parte verification capability score.{" "}
        <span className="font-semibold text-cobalt">
          Click any subgroup label for the story behind why those enrollees are at risk.
        </span>
      </p>

      {/* State selector */}
      <div className="mt-5 flex flex-wrap items-baseline gap-3">
        <label className="block font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          State
        </label>
        <select
          value={stateKey}
          onChange={(e) => setStateKey(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-sans text-sm shadow-sm focus:border-cobalt focus:outline-none focus:ring-1 focus:ring-cobalt"
        >
          <option value="US">United States (national)</option>
          {stateOptions.map((s) => (
            <option key={s.fips} value={s.fips}>
              {s.name}
            </option>
          ))}
        </select>
        <div className="text-xs text-slate-500">
          {stateKey === "US" ? (
            <>National. Bottom-up projection: <span className="font-semibold text-cobalt">{fmtCount(entry.total_loss_2034)}</span> coverage losses by 2034 (CBO 5.2M; Urban 3–7M; CBPP 9.7–14.4M at risk).</>
          ) : (
            <>
              In <span className="font-semibold">{entry.name}</span>:{" "}
              <span className="font-semibold text-cobalt">{fmtCount(entry.total_loss_2034)}</span>{" "}
              projected losses
              {entry.subject_count > 0 && (
                <>
                  {" — "}
                  <span className="font-semibold text-cobalt">
                    {((entry.total_loss_2034 / entry.subject_count) * 100).toFixed(1)}%
                  </span>{" "}
                  of the {fmtCount(entry.subject_count)} subject pool
                </>
              )}
              {entry.ex_parte_score !== null && (
                <>
                  {" · "}ex parte capability{" "}
                  <span className="font-semibold">{entry.ex_parte_score}/100</span>{" "}
                  (
                  <span
                    className={
                      entry.ex_parte_band === "low"
                        ? "text-emerald-700"
                        : entry.ex_parte_band === "high"
                          ? "text-amber-700"
                          : "text-slate-700"
                    }
                  >
                    {entry.ex_parte_band === "low"
                      ? "admin churn likely substantially mitigated"
                      : entry.ex_parte_band === "high"
                        ? "admin churn likely Arkansas-grade"
                        : "mid range"}
                  </span>
                  )
                </>
              )}
              {entry.system_vendor && (
                <> · Eligibility system: <span className="font-semibold">{entry.system_vendor}</span></>
              )}
            </>
          )}
        </div>
      </div>

      {/* Sankey */}
      <div className="mt-6 hidden sm:block">
        <svg
          viewBox={`-180 0 ${VB_W + 180} ${VB_H}`}
          width="100%"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Sankey diagram of Medicaid coverage loss by failure mode"
          style={{ fontFamily: "Source Sans 3, system-ui, sans-serif" }}
        >
          {/* --- Left stat callout: big total + range source --- */}
          <text
            x={LEFT_X - 24}
            y={layout.srcMid}
            textAnchor="end"
            fill={COBALT}
            fontFamily="Source Serif 4, Source Serif Pro, Georgia, serif"
          >
            <tspan x={LEFT_X - 24} dy="-0.85em" fontSize={56} fontWeight={700} style={{ fontVariantNumeric: "tabular-nums" }}>
              {fmtCount(layout.total)}
            </tspan>
            <tspan
              x={LEFT_X - 24}
              dy="1.45em"
              fontSize={15}
              fontWeight={500}
              fill={CHARCOAL}
              fontFamily="Source Sans 3, system-ui, sans-serif"
            >
              will lose coverage by 2034
            </tspan>
            <tspan
              x={LEFT_X - 24}
              dy="1.25em"
              fontSize={12}
              fontWeight={500}
              fill={GRAY}
              fontFamily="Source Sans 3, system-ui, sans-serif"
            >
              bottom-up; converges with CBO 5.2M
            </tspan>
            <tspan
              x={LEFT_X - 24}
              dy="1.25em"
              fontSize={12}
              fontWeight={500}
              fill={GRAY}
              fontFamily="Source Sans 3, system-ui, sans-serif"
            >
              Urban 3–7M, CBPP 9.7–14.4M at risk
            </tspan>
          </text>

          {/* --- Source column block --- */}
          <rect
            x={LEFT_X}
            y={layout.srcTop}
            width={SRC_W}
            height={layout.srcBot - layout.srcTop}
            fill={COBALT}
            opacity={0.9}
          />

          {/* --- Bands col 1 → col 2 --- */}
          <path
            d={bandPath(LEFT_X + SRC_W, BUCKET_X, {
              srcTop: layout.wdSrcSlice.top,
              srcBot: layout.wdSrcSlice.bot,
              tgtTop: layout.workBucket.top,
              tgtBot: layout.workBucket.bot,
            })}
            fill={COBALT_FAINT}
            opacity={hoverBand && hoverBand !== "work" ? 0.3 : 0.85}
            onMouseEnter={() => setHoverBand("work")}
            onMouseLeave={() => setHoverBand(null)}
          />
          <path
            d={bandPath(LEFT_X + SRC_W, BUCKET_X, {
              srcTop: layout.exSrcSlice.top,
              srcBot: layout.exSrcSlice.bot,
              tgtTop: layout.exBucket.top,
              tgtBot: layout.exBucket.bot,
            })}
            fill={CAROLINA_FAINT}
            opacity={hoverBand && hoverBand !== "exemption" ? 0.3 : 0.85}
            onMouseEnter={() => setHoverBand("exemption")}
            onMouseLeave={() => setHoverBand(null)}
          />
          <path
            d={bandPath(LEFT_X + SRC_W, BUCKET_X, {
              srcTop: layout.ncSrcSlice.top,
              srcBot: layout.ncSrcSlice.bot,
              tgtTop: layout.ncBucket.top,
              tgtBot: layout.ncBucket.bot,
            })}
            fill={GRAY_FAINT}
            opacity={hoverBand && hoverBand !== "nc" ? 0.3 : 0.85}
            onMouseEnter={() => setHoverBand("nc")}
            onMouseLeave={() => setHoverBand(null)}
          />

          {/* --- Bucket column blocks + labels --- */}
          <rect x={BUCKET_X} y={layout.workBucket.top} width={BUCKET_W} height={layout.workBucket.bot - layout.workBucket.top} fill={COBALT} opacity={0.85} />
          <rect x={BUCKET_X} y={layout.exBucket.top} width={BUCKET_W} height={layout.exBucket.bot - layout.exBucket.top} fill={CAROLINA} opacity={0.85} />
          <rect x={BUCKET_X} y={layout.ncBucket.top} width={BUCKET_W} height={layout.ncBucket.bot - layout.ncBucket.top} fill={GRAY} opacity={0.85} />

          {/* Bucket label boxes — placed to the LEFT of the middle bars so
              they read against the lighter source-to-bucket band area and are
              unambiguously associated with the middle category bars (not with
              the subgroup column to the right). */}
          {[
            { name: "Compliant but can't prove it", top: layout.workBucket.top, bot: layout.workBucket.bot, count: entry.work_hours_doc_failures.total, color: COBALT, faint: COBALT_FAINT },
            { name: "Exempt but can't prove it", top: layout.exBucket.top, bot: layout.exBucket.bot, count: entry.exemption_doc_failures.total, color: CAROLINA, faint: CAROLINA_FAINT },
            { name: "Genuinely non-compliant", top: layout.ncBucket.top, bot: layout.ncBucket.bot, count: entry.genuinely_noncompliant, color: GRAY, faint: GRAY_FAINT },
          ].map((b) => {
            const mid = (b.top + b.bot) / 2;
            return (
              <g key={b.name}>
                <text x={BUCKET_X - 12} y={mid - 4} textAnchor="end" fontSize={13} fontWeight={700} fill={b.color}>
                  {b.name}
                </text>
                <text x={BUCKET_X - 12} y={mid + 12} textAnchor="end" fontSize={11} fill={CHARCOAL}>
                  {fmtCount(b.count)} ({fmtPct(b.count, layout.total)})
                </text>
              </g>
            );
          })}

          {/* --- Bands col 2 → col 3 (subgroups) --- */}
          {/* Workdoc bands */}
          {(() => {
            // For col 2→3, we need to slice the bucket block top→bottom by each subgroup's share.
            const bucketH = layout.workBucket.bot - layout.workBucket.top;
            const total = entry.work_hours_doc_failures.total;
            let cursor = layout.workBucket.top;
            return layout.wdSubs.map((sub) => {
              const sliceH = total > 0 ? ((sub.count) / total) * bucketH : 0;
              const srcSlice = { top: cursor, bot: cursor + sliceH };
              cursor += sliceH;
              const path = bandPath(BUCKET_X + BUCKET_W, SUB_X, {
                srcTop: srcSlice.top,
                srcBot: srcSlice.bot,
                tgtTop: sub.top,
                tgtBot: sub.bot,
              });
              const dim = hoverBand && hoverBand !== `wd:${sub.key}` && hoverBand !== "work";
              return (
                <path
                  key={"wd-band-" + sub.key}
                  d={path}
                  fill={SUBGROUP_COLORS[sub.key] ?? COBALT_LIGHT}
                  opacity={dim ? 0.25 : 0.7}
                  onMouseEnter={() => setHoverBand(`wd:${sub.key}`)}
                  onMouseLeave={() => setHoverBand(null)}
                />
              );
            });
          })()}

          {/* Exemption bands */}
          {(() => {
            const bucketH = layout.exBucket.bot - layout.exBucket.top;
            const total = entry.exemption_doc_failures.total;
            let cursor = layout.exBucket.top;
            return layout.exSubs.map((sub) => {
              const sliceH = total > 0 ? ((sub.count) / total) * bucketH : 0;
              const srcSlice = { top: cursor, bot: cursor + sliceH };
              cursor += sliceH;
              const path = bandPath(BUCKET_X + BUCKET_W, SUB_X, {
                srcTop: srcSlice.top,
                srcBot: srcSlice.bot,
                tgtTop: sub.top,
                tgtBot: sub.bot,
              });
              const dim = hoverBand && hoverBand !== `ex:${sub.key}` && hoverBand !== "exemption";
              return (
                <path
                  key={"ex-band-" + sub.key}
                  d={path}
                  fill={SUBGROUP_COLORS[sub.key] ?? CAROLINA_LIGHT}
                  opacity={dim ? 0.25 : 0.7}
                  onMouseEnter={() => setHoverBand(`ex:${sub.key}`)}
                  onMouseLeave={() => setHoverBand(null)}
                />
              );
            });
          })()}

          {/* --- Subgroup column blocks + labels with leader lines (clickable) --- */}
          {layout.wdSubs.map((sub) => {
            const barMid = (sub.top + sub.bot) / 2;
            const labelY = sub.labelY;
            const leaderColor = SUBGROUP_COLORS[sub.key] ?? COBALT_LIGHT;
            const narrative = entry.work_hours_doc_failures.subgroups[sub.key]?.narrative ?? "";
            const isActive = activeSubgroup?.key === sub.key && activeSubgroup?.bucket === "wd";
            return (
              <g
                key={"wd-sub-" + sub.key}
                style={{ cursor: "pointer" }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (isActive) {
                    setActiveSubgroup(null);
                  } else {
                    showSubgroupCard(
                      { key: sub.key, label: sub.label, count: sub.count, narrative },
                      "wd",
                      e.currentTarget as SVGGElement,
                      leaderColor,
                    );
                  }
                }}
              >
                <rect
                  x={SUB_X}
                  y={sub.top}
                  width={SUB_W}
                  height={sub.bot - sub.top}
                  fill={leaderColor}
                  opacity={isActive ? 1 : 0.9}
                  stroke={isActive ? CHARCOAL : "none"}
                  strokeWidth={isActive ? 1.5 : 0}
                />
                {Math.abs(labelY - barMid) > 1 && (
                  <path
                    d={`M ${SUB_X + SUB_W} ${barMid} L ${SUB_X + SUB_W + 12} ${barMid} L ${LABEL_X - 4} ${labelY} L ${LABEL_X - 1} ${labelY}`}
                    fill="none"
                    stroke={leaderColor}
                    strokeWidth={1}
                    opacity={0.7}
                  />
                )}
                <text x={LABEL_X} y={labelY - 6} fontSize={11.5} fontWeight={600} fill={CHARCOAL} dominantBaseline="middle">
                  {sub.label}
                  <tspan
                    fontSize={9}
                    fontWeight={400}
                    fill="#94A3B8"
                    dx="6"
                    dy="-1"
                  >
                    ⓘ
                  </tspan>
                </text>
                <text x={LABEL_X} y={labelY + 9} fontSize={10.5} fill="#475569" dominantBaseline="middle">
                  {fmtCount(sub.count)}
                </text>
              </g>
            );
          })}
          {layout.exSubs.map((sub) => {
            const barMid = (sub.top + sub.bot) / 2;
            const labelY = sub.labelY;
            const leaderColor = SUBGROUP_COLORS[sub.key] ?? CAROLINA_LIGHT;
            const narrative = entry.exemption_doc_failures.subgroups[sub.key]?.narrative ?? "";
            const isActive = activeSubgroup?.key === sub.key && activeSubgroup?.bucket === "ex";
            return (
              <g
                key={"ex-sub-" + sub.key}
                style={{ cursor: "pointer" }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (isActive) {
                    setActiveSubgroup(null);
                  } else {
                    showSubgroupCard(
                      { key: sub.key, label: sub.label, count: sub.count, narrative },
                      "ex",
                      e.currentTarget as SVGGElement,
                      leaderColor,
                    );
                  }
                }}
              >
                <rect
                  x={SUB_X}
                  y={sub.top}
                  width={SUB_W}
                  height={sub.bot - sub.top}
                  fill={leaderColor}
                  opacity={isActive ? 1 : 0.9}
                  stroke={isActive ? CHARCOAL : "none"}
                  strokeWidth={isActive ? 1.5 : 0}
                />
                {Math.abs(labelY - barMid) > 1 && (
                  <path
                    d={`M ${SUB_X + SUB_W} ${barMid} L ${SUB_X + SUB_W + 12} ${barMid} L ${LABEL_X - 4} ${labelY} L ${LABEL_X - 1} ${labelY}`}
                    fill="none"
                    stroke={leaderColor}
                    strokeWidth={1}
                    opacity={0.7}
                  />
                )}
                <text x={LABEL_X} y={labelY - 6} fontSize={11.5} fontWeight={600} fill={CHARCOAL} dominantBaseline="middle">
                  {sub.label}
                  <tspan
                    fontSize={9}
                    fontWeight={400}
                    fill="#94A3B8"
                    dx="6"
                    dy="-1"
                  >
                    ⓘ
                  </tspan>
                </text>
                <text x={LABEL_X} y={labelY + 9} fontSize={10.5} fill="#475569" dominantBaseline="middle">
                  {fmtCount(sub.count)}
                </text>
              </g>
            );
          })}

          {/* Non-compliant block (no subgroups) — render its label directly at col 3 position */}
          <rect x={SUB_X} y={layout.ncBucket.top} width={SUB_W} height={layout.ncBucket.bot - layout.ncBucket.top} fill={GRAY} opacity={0.85} />
          <text x={LABEL_X} y={(layout.ncBucket.top + layout.ncBucket.bot) / 2 + 1} fontSize={11.5} fontWeight={600} fill={CHARCOAL} dominantBaseline="middle">
            Genuinely non-compliant
          </text>
          <text x={LABEL_X} y={(layout.ncBucket.top + layout.ncBucket.bot) / 2 + 15} fontSize={10.5} fill="#475569" dominantBaseline="middle">
            {fmtCount(entry.genuinely_noncompliant)}
          </text>
          {/* Connecting band: source nc slice → nc subgroup block */}
          <path
            d={bandPath(BUCKET_X + BUCKET_W, SUB_X, {
              srcTop: layout.ncBucket.top,
              srcBot: layout.ncBucket.bot,
              tgtTop: layout.ncBucket.top,
              tgtBot: layout.ncBucket.bot,
            })}
            fill={GRAY_FAINT}
            opacity={hoverBand && hoverBand !== "nc" ? 0.25 : 0.7}
            onMouseEnter={() => setHoverBand("nc")}
            onMouseLeave={() => setHoverBand(null)}
          />
        </svg>
      </div>

      {/* Click-tooltip narrative card (desktop only — SVG-anchored). */}
      {activeSubgroup && (
        <div
          className="pointer-events-auto absolute z-20 hidden rounded-lg border border-slate-200 bg-white p-4 shadow-xl sm:block"
          onClick={(e) => e.stopPropagation()}
          style={{
            // Position the card to the right of the bar, vertically centered.
            // Clamp inside the wrapper so it never overflows on small viewports.
            left: Math.min(
              activeSubgroup.pixelX + 16,
              (sankeyWrapperRef.current?.clientWidth ?? 1200) - 360,
            ),
            top: Math.max(8, activeSubgroup.pixelY - 90),
            width: 340,
            maxWidth: "calc(100% - 32px)",
          }}
        >
          <div className="flex items-baseline justify-between gap-3">
            <div
              className="font-serif text-[15px] font-semibold leading-snug"
              style={{ color: activeSubgroup.color }}
            >
              {activeSubgroup.label}
            </div>
            <button
              type="button"
              aria-label="Close"
              onClick={(e) => {
                e.stopPropagation();
                setActiveSubgroup(null);
              }}
              className="text-[14px] leading-none text-slate-400 hover:text-slate-600"
            >
              ×
            </button>
          </div>
          <div className="mt-1 font-sans text-[11px] uppercase tracking-wider text-slate-500">
            {fmtCount(activeSubgroup.count)} projected · {fmtPct(activeSubgroup.count, entry.total_loss_2034)} of total loss
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-slate-700">
            {activeSubgroup.narrative || "No narrative available for this subgroup."}
          </p>
          <div className="mt-2 text-[10.5px] italic text-slate-400">
            ESC or click outside to dismiss · methodology §3.5
          </div>
        </div>
      )}

      {/* Mobile fallback: stacked rows, no SVG */}
      <div className="mt-6 sm:hidden">
        <MobileBreakdown entry={entry} />
      </div>

      {/* Footnote under sankey */}
      <p className="mt-4 text-xs leading-snug text-slate-500">
        Each state's loss is computed bottom-up per-(subgroup) as
        subject_pool × eligibility_rate × failure_rate, then summed and
        scaled by a cross-cycle compounding factor (×1.15) to translate
        single-renewal-cycle snapshots into a cumulative 2034 figure.
        The within-bucket proportions and the compliant/exempt/non-compliant
        split emerge from the math rather than from an editorial target.
        Work and student subgroup composition comes from ACS PUMS 5-Year
        2020–2024 classified per state. Exemption-doc subgroup eligibility
        comes from per-state PUMS where ACS speaks (medically frail, parent
        caregivers, students, kinship and disabled-adult caregivers via
        household structure inference, pregnancy via FER), SAMHSA NSDUH
        2023–2024 state SUD estimates, BJS NPS state releases, AI/AN from
        PUMS RACAIAN (its own line, sized per state), and bundled priors for
        the remaining small categorical exemptions (foster youth, AYA cancer
        survivor, SNAP/TANF). Per-(state, subgroup) failure
        rates attenuate with each ex parte capability flag the state has
        set. The bottom-up national total is compared against the
        published range (CBO 5.2M, Urban 3–7M, CBPP 9.7–14.4M at risk); a single
        uniform calibration multiplier is applied only if the total lands
        outside the [4.5M, 11M] band. See methodology accordion below for
        the full parameter table.
      </p>

    </div>
  );
}

// ---------- Tile cartogram ----------

const STATE_GRID: Record<string, [number, number]> = {
  // [col, row] — 12-col × 8-row tile-cartogram layout (NPR/Pitch style).
  AK: [0, 7],
  ME: [10, 0],
  VT: [9, 1], NH: [10, 1],
  WA: [1, 2], ID: [2, 2], MT: [3, 2], ND: [4, 2], MN: [5, 2], WI: [6, 2], MI: [7, 2], NY: [9, 2], MA: [10, 2],
  OR: [1, 3], NV: [2, 3], WY: [3, 3], SD: [4, 3], IA: [5, 3], IL: [6, 3], IN: [7, 3], OH: [8, 3], PA: [9, 3], NJ: [10, 3], CT: [11, 3],
  CA: [1, 4], UT: [2, 4], CO: [3, 4], NE: [4, 4], MO: [5, 4], KY: [6, 4], WV: [7, 4], VA: [8, 4], MD: [9, 4], DE: [10, 4], RI: [11, 4],
  AZ: [2, 5], NM: [3, 5], KS: [4, 5], AR: [5, 5], TN: [6, 5], NC: [7, 5], SC: [8, 5], DC: [9, 5],
  HI: [0, 6], OK: [4, 6], LA: [5, 6], MS: [6, 6], AL: [7, 6], GA: [8, 6],
  TX: [4, 7], FL: [8, 7],
};

// Diverging warm-to-cool ramp for the ex parte cartogram. Cuts are tuned to the
// real composite spread (41-81) and honor the methodology edges (45 = high-churn
// floor, 70 = entry to "low churn"), so the warm swatches actually populate and
// the map stops reading as one shade of blue. Below-readiness states render warm,
// above-readiness cool. Ordered high-to-low for first-match lookup; the legend
// reads the same array reversed so the two can never drift.
export const EX_PARTE_BANDS: { min: number; fill: string; text: string; label: string }[] = [
  { min: 90, fill: "#0A0A8A", text: "#FFFFFF", label: "≥90" },
  { min: 80, fill: "#1F1FD6", text: "#FFFFFF", label: "80–89" },
  { min: 70, fill: "#21A8E0", text: "#FFFFFF", label: "70–79" },
  { min: 64, fill: "#A9D6EE", text: "#0F2A3F", label: "64–69" },
  { min: 55, fill: "#F4D7A1", text: "#7C2D12", label: "55–63" },
  { min: 45, fill: "#E8914A", text: "#FFFFFF", label: "45–54" },
  { min: 0, fill: "#C2410C", text: "#FFFFFF", label: "<45" },
];

function colorForScore(
  score: number | null,
  expansion: boolean,
  waiverInScope = false,
): { fill: string; text: string; hatched: boolean } {
  // Subject via a 1115 waiver (WI/GA) or CMS-listed-not-quantified (TN): in scope
  // but unscored. Amber-tinted + hatched so it reads as "subject, not scored,"
  // distinct from both scored states and gray "unaffected" non-expansion states.
  if (!expansion && waiverInScope) return { fill: "#FBEACB", text: "#92660C", hatched: true };
  if (!expansion) return { fill: "#E2E8F0", text: "#64748B", hatched: true };
  if (score === null) return { fill: "#F1F5F9", text: "#94A3B8", hatched: false };
  const band =
    EX_PARTE_BANDS.find((b) => score >= b.min) ?? EX_PARTE_BANDS[EX_PARTE_BANDS.length - 1];
  return { fill: band.fill, text: band.text, hatched: false };
}

const FLAG_LABEL_MAP: Record<string, string> = {
  medicaid_claims_match: "Medicaid claims",
  behavioral_health_mco_match: "BH MCO",
  ui_wage_match: "UI wage",
  snap_tanf_compliance_match: "SNAP/TANF",
  corrections_records_match: "Corrections",
  child_welfare_records_match: "Child welfare",
  vital_records_match: "Vital records",
  workforce_dev_records_match: "Workforce dev",
  self_attestation_accepted: "Self-attest",
};

// Helpers to read scores/bands for a given cartogram view, with back-compat fallback.
function scoreForView(row: ExParteRow, view: CartogramView): number | null {
  if (row.scores) {
    return row.scores[view];
  }
  // Back-compat: only composite is available via top-level `score`.
  return view === "composite" ? row.score : null;
}

function bandForView(row: ExParteRow, view: CartogramView): string | null {
  if (row.bands) return row.bands[view];
  return view === "composite" ? row.band : null;
}

export function ExParteCartogram({ rows, view }: { rows: ExParteRow[]; view: CartogramView }) {
  const [hover, setHover] = useState<ExParteRow | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);

  const CELL = 44;
  const GAP = 4;
  const COLS = 12;
  const ROWS = 8;
  const W = COLS * (CELL + GAP);
  const H = ROWS * (CELL + GAP);

  // Build a map keyed by abbreviation for lookup.
  const byAbbr: Record<string, ExParteRow> = {};
  for (const r of rows) byAbbr[r.abbr] = r;

  // Shared handler: set tooltip target + position for a given tile element.
  // Used by both mouse hover and tap so touch devices get the tooltip too.
  const showFor = (r: ExParteRow, el: SVGGElement) => {
    const rect = el.getBoundingClientRect();
    const svgRect = (el.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    setHover(r);
    setHoverPos({
      x: rect.left - svgRect.left + rect.width / 2,
      y: rect.top - svgRect.top,
    });
  };

  return (
    <div
      className="relative"
      // Tap outside any tile clears the tooltip (mobile dismiss).
      onClick={() => { setHover(null); setHoverPos(null); }}
    >
      <svg
        viewBox={`0 0 ${W} ${H + 80}`}
        width="100%"
        preserveAspectRatio="xMidYMid meet"
        style={{ fontFamily: "Source Sans 3, system-ui, sans-serif", maxHeight: "520px" }}
        role="img"
        aria-label="Tile cartogram of state ex parte verification capability"
      >
        <defs>
          <pattern id="hatched" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#E2E8F0" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#CBD5E1" strokeWidth="2" />
          </pattern>
          {/* Amber hatch: subject-via-1115-waiver states (WI/GA) + CMS-listed-not-
              quantified (TN) — in scope but unscored, distinct from gray unaffected. */}
          <pattern id="hatched-amber" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#FBEACB" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#E0B057" strokeWidth="2" />
          </pattern>
        </defs>

        {Object.entries(STATE_GRID).map(([abbr, [col, row]]) => {
          const r = byAbbr[abbr];
          if (!r) return null;
          const x = col * (CELL + GAP);
          const y = row * (CELL + GAP);
          const activeScore = scoreForView(r, view);
          const waiverInScope = Boolean(r.subject_via_waiver || r.waiver_listed);
          const c = colorForScore(activeScore, r.expansion, waiverInScope);
          const isHovered = hover?.abbr === abbr;
          return (
            <g
              key={abbr}
              onMouseEnter={(e) => showFor(r, e.currentTarget as SVGGElement)}
              onMouseLeave={() => { setHover(null); setHoverPos(null); }}
              onClick={(e) => {
                // Tap toggles: if this tile is already shown, dismiss; otherwise show.
                e.stopPropagation();
                if (hover?.abbr === abbr) {
                  setHover(null);
                  setHoverPos(null);
                } else {
                  showFor(r, e.currentTarget as SVGGElement);
                }
              }}
              style={{ cursor: "pointer" }}
            >
              <rect
                x={x}
                y={y}
                width={CELL}
                height={CELL}
                rx={5}
                fill={c.hatched ? (waiverInScope ? "url(#hatched-amber)" : "url(#hatched)") : c.fill}
                stroke={isHovered ? "#0A0A8A" : "transparent"}
                strokeWidth={isHovered ? 2 : 0}
              />
              <text
                x={x + CELL / 2}
                y={y + CELL / 2 - 4}
                textAnchor="middle"
                fontSize={12}
                fontWeight={700}
                fill={c.text}
                dominantBaseline="middle"
              >
                {abbr}
              </text>
              {activeScore !== null && (
                <text
                  x={x + CELL / 2}
                  y={y + CELL / 2 + 10}
                  textAnchor="middle"
                  fontSize={9}
                  fill={c.text}
                  opacity={0.85}
                  dominantBaseline="middle"
                >
                  {activeScore}
                </text>
              )}
              {r.historical_experience && (
                <g aria-label="State has prior Section 1115 work-requirement experience">
                  <circle
                    cx={x + CELL - 6}
                    cy={y + 6}
                    r={4}
                    fill="#FFFFFF"
                    stroke={c.text === "#FFFFFF" ? "#FFFFFF" : "#1F2937"}
                    strokeWidth={1}
                  />
                  <text
                    x={x + CELL - 6}
                    y={y + 6}
                    textAnchor="middle"
                    fontSize={6.5}
                    fontWeight={700}
                    fill={c.text === "#FFFFFF" ? "#0A0A8A" : "#1F2937"}
                    dominantBaseline="central"
                  >
                    H
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* Legend strip. Label sits on its own row above the swatches so it
            doesn't overlap when the dynamic view name is long ("Core
            capability" / "Data sources"). */}
        <g transform={`translate(0, ${H + 16})`}>
          <text x="0" y="0" fontSize={10} fontWeight={600} fill="#475569" style={{ textTransform: "uppercase" }} letterSpacing="0.6">
            {CARTOGRAM_VIEW_LABELS[view]} score
          </text>
          {[...EX_PARTE_BANDS].reverse().map((b, i) => {
            const lx = i * 56;
            return (
              <g key={b.label} transform={`translate(${lx}, 12)`}>
                <rect width="20" height="14" rx="3" fill={b.fill} />
                <text x="25" y="11" fontSize={10.5} fill="#1F2937">{b.label}</text>
              </g>
            );
          })}
          <g transform={`translate(${7 * 56}, 12)`}>
            <rect width="22" height="14" rx="3" fill="url(#hatched)" />
            <text x="28" y="11" fontSize={11} fill="#64748B">Non-exp.</text>
          </g>
          {/* Second legend row: subject-via-1115-waiver states (WI/GA/TN). */}
          <g transform={`translate(0, 34)`}>
            <rect width="22" height="14" rx="3" fill="url(#hatched-amber)" />
            <text x="28" y="11" fontSize={11} fill="#92660C">Subject via 1115 waiver (unscored: WI, GA, TN)</text>
          </g>
        </g>
      </svg>

      {/* Hover tooltip */}
      {hover && hoverPos && (
        <div
          className="pointer-events-none absolute z-10 rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-lg"
          style={{
            left: Math.max(8, Math.min(hoverPos.x - 160, 100000)),
            top: Math.max(8, hoverPos.y - 8),
            transform: "translateY(-100%)",
            maxWidth: 360,
            minWidth: 280,
          }}
        >
          <div className="font-serif text-sm font-semibold text-cobalt">
            {hover.name} ({hover.abbr})
          </div>
          {hover.expansion ? (
            <>
              {(() => {
                const composite = scoreForView(hover, "composite");
                const observed = scoreForView(hover, "observed_ex_parte");
                // core_capability is a context sub-metric on `scores`, not a cartogram
                // view, so read it directly (same pattern as historical_churn below).
                const core = hover.scores?.core_capability ?? null;
                const sources = scoreForView(hover, "data_sources");
                const historical = hover.scores?.historical_churn ?? null;
                const activeBand = bandForView(hover, view);
                const obsRate = hover.observed_ex_parte_rate;
                const ROW = (label: string, val: number | null, isActive: boolean, suffix?: string) => (
                  <div
                    key={label}
                    className={`flex items-baseline gap-2 text-[11.5px] ${isActive ? "font-semibold text-slate-900" : "text-slate-600"}`}
                  >
                    <span className="w-[120px]">{label}:</span>
                    <span className="font-mono tabular-nums">{val ?? "—"}{val !== null ? " / 100" : ""}{suffix ? ` ${suffix}` : ""}</span>
                  </div>
                );
                return (
                  <>
                    <div className="mt-1.5 space-y-0.5">
                      {ROW("Composite",        composite, view === "composite")}
                      {ROW("Observed ex parte", observed, view === "observed_ex_parte",
                          obsRate != null ? `(${Math.round(obsRate * 100)}% of renewals)` : undefined)}
                      {ROW("Data sources",     sources,   view === "data_sources")}
                      {ROW("Historical churn", historical, false)}
                      {ROW("Core capability",  core,      false)}
                    </div>
                    <div className="mt-1.5">
                      <span
                        className={`inline-block rounded px-1.5 py-0.5 text-[10.5px] font-semibold ${
                          activeBand === "low" ? "bg-emerald-100 text-emerald-800"
                            : activeBand === "high" ? "bg-amber-100 text-amber-800"
                              : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {CARTOGRAM_VIEW_LABELS[view]}: {activeBand === "low" ? "low churn" : activeBand === "high" ? "high churn" : activeBand === "mid" ? "mid" : "—"}
                      </span>
                    </div>
                  </>
                );
              })()}
              {view === "composite" && hover.core_components && (
                <div className="mt-2 border-t border-slate-100 pt-1.5 text-[10.5px] leading-snug">
                  <div className="text-slate-500 uppercase tracking-wider text-[9.5px] mb-0.5">Core capability sub-components (context — not in composite)</div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-slate-700">
                    <div>System integration <span className="font-mono">{hover.core_components.system_integration}/25</span></div>
                    <div>Account matching <span className="font-mono">{hover.core_components.account_matching}/20</span></div>
                    <div>Deduplication <span className="font-mono">{hover.core_components.deduplication}/15</span></div>
                    <div>Operational SLA <span className="font-mono">{hover.core_components.operational_sla}/15</span></div>
                    <div>Self-attest policy <span className="font-mono">{hover.core_components.self_attestation_policy}/15</span></div>
                    <div>Identity proofing <span className="font-mono">{hover.core_components.identity_proofing}/10</span></div>
                  </div>
                </div>
              )}
              {view === "data_sources" && hover.source_components && (
                <div className="mt-2 border-t border-slate-100 pt-1.5 text-[10.5px] leading-snug">
                  <div className="text-slate-500 uppercase tracking-wider text-[9.5px] mb-0.5">Source buckets (quality-weighted)</div>
                  <div className="space-y-0.5 text-slate-700">
                    <div>Wage data <span className="font-mono">{hover.source_components.wage_data}/30</span></div>
                    <div>Frailty data <span className="font-mono">{hover.source_components.frailty_data}/30</span></div>
                    <div>Other sources <span className="font-mono">{hover.source_components.other_data}/20</span></div>
                  </div>
                </div>
              )}
              <div className="mt-2 border-t border-slate-100 pt-1.5 text-[11px] leading-snug">
                <div className="text-slate-500 text-[10px] uppercase tracking-wider">Data sources planned</div>
                <div className="text-slate-700">
                  {Object.entries(hover.flags).filter(([, v]) => v).map(([k]) => FLAG_LABEL_MAP[k] ?? k).join(", ") || "—"}
                </div>
              </div>
              <div className="mt-1.5 text-[11px] leading-snug">
                <div className="text-slate-500 text-[10px] uppercase tracking-wider">Eligibility system</div>
                <div className="text-slate-700">{hover.system_vendor || "—"}</div>
              </div>
              {hover.historical_experience && (
                <div className="mt-2 border-t border-slate-100 pt-1.5 text-[11px] leading-snug">
                  <div className="text-slate-500 text-[10px] uppercase tracking-wider">Prior Section 1115 experience</div>
                  <div className="text-slate-700">
                    {hover.historical_experience.implementation_window}.{" "}
                    {hover.historical_experience.people_affected}.
                    {hover.historical_experience.denial_rate !== null && (
                      <>
                        {" "}Denial rate ≈ <span className="font-mono tabular-nums">{Math.round((hover.historical_experience.denial_rate ?? 0) * 100)}%</span>.
                      </>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : hover.subject_via_waiver ? (
            <div className="mt-1 text-[11px] leading-snug text-amber-700">
              Subject to the OBBBA work requirement through a Section 1115 waiver, not ACA expansion
              {hover.already_work_conditional
                ? " — and already work-conditional, so no net-new loss is modeled"
                : ""}
              . Not scored here: there is no work-requirement-specific verification data for this
              waiver population yet.
            </div>
          ) : hover.waiver_listed ? (
            <div className="mt-1 text-[11px] leading-snug text-amber-700">
              On CMS's June-2026 list only via TennCare's 1115 parent/caretaker group (~17.7K to 100%
              FPL), which OBBBA largely exempts (parents of a child under 14) — so virtually no one is
              actually subject. Flagged, not scored.
            </div>
          ) : (
            <div className="mt-1 text-[11px] leading-snug text-slate-500">
              Non-expansion state with no subject population. The OBBBA work requirement does not reach it.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------- Mobile fallback ----------

function MobileBreakdown({ entry }: { entry: BreakdownEntry }) {
  const total = entry.total_loss_2034;
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const sections: Array<{
    label: string;
    color: string;
    n: number;
    subs: Array<{ key: string; label: string; count: number; narrative?: string }>;
  }> = [
    {
      label: "Compliant but can't prove it",
      color: COBALT,
      n: entry.work_hours_doc_failures.total,
      subs: WORKDOC_KEYS.map((k) => ({
        key: "wd:" + k,
        label: entry.work_hours_doc_failures.subgroups[k]?.label ?? k,
        count: entry.work_hours_doc_failures.subgroups[k]?.count ?? 0,
        narrative: entry.work_hours_doc_failures.subgroups[k]?.narrative,
      })),
    },
    {
      label: "Exempt but can't prove it",
      color: CAROLINA,
      n: entry.exemption_doc_failures.total,
      subs: EXEMPTION_KEYS.map((k) => ({
        key: "ex:" + k,
        label: entry.exemption_doc_failures.subgroups[k]?.label ?? k,
        count: entry.exemption_doc_failures.subgroups[k]?.count ?? 0,
        narrative: entry.exemption_doc_failures.subgroups[k]?.narrative,
      })),
    },
    {
      label: "Genuinely non-compliant",
      color: GRAY,
      n: entry.genuinely_noncompliant,
      subs: [],
    },
  ];
  return (
    <div className="space-y-5">
      {/* Mobile anchor — mirrors the desktop SVG's big left callout so phone
          readers get the headline 5.2M number before the breakdown sections. */}
      <div className="rounded-lg border border-cobalt/20 bg-cobalt/[0.04] px-4 py-3">
        <div className="font-serif text-[2.4rem] font-black leading-none tabular-nums text-cobalt">
          {fmtCount(total)}
        </div>
        <div className="mt-1 font-sans text-[13px] font-medium text-charcoal">
          will lose coverage by 2034
        </div>
        <div className="mt-0.5 font-sans text-[11px] text-slate-500">
          bottom-up; lands just above CBO 5.2M (Urban 3–7M, CBPP 9.7–14.4M at risk)
        </div>
      </div>
      <p className="text-[11px] italic text-slate-500">
        Tap any subgroup name for the story behind why those enrollees are at risk.
      </p>
      {sections.map((sec) => (
        <div key={sec.label} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="flex items-baseline justify-between gap-2">
            <div className="font-serif text-sm font-semibold" style={{ color: sec.color }}>
              {sec.label}
            </div>
            <div className="font-mono text-sm font-semibold text-slate-900">
              {fmtCount(sec.n)} ({fmtPct(sec.n, total)})
            </div>
          </div>
          {sec.subs.length > 0 && (
            <div className="mt-2 space-y-1.5">
              {sec.subs.map((s) => {
                const isExpanded = expandedKey === s.key;
                return (
                  <div key={s.key}>
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedKey(isExpanded ? null : s.key)
                      }
                      className="grid w-full grid-cols-[1fr_auto] items-baseline gap-3 text-left text-[12px]"
                    >
                      <div className="text-slate-700 hover:text-cobalt">
                        {s.label}
                        <span className="ml-1 text-[10px] text-slate-400">
                          {isExpanded ? "▾" : "▸"}
                        </span>
                      </div>
                      <div className="font-mono tabular-nums text-slate-600">{fmtCount(s.count)}</div>
                    </button>
                    {isExpanded && (
                      <p className="mt-1 rounded border-l-2 border-slate-300 bg-white px-2 py-1.5 text-[11.5px] leading-relaxed text-slate-700">
                        {s.narrative || "No narrative available for this subgroup."}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
