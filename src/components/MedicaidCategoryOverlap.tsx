"use client";

import { useEffect, useMemo, useState } from "react";

interface OverlapCell {
  key: string;
  categories: string[];
  count: number;
  share: number;
}

interface OverlapDistribution {
  subject_count: number;
  cells: OverlapCell[];
  by_category_count: Record<string, number>;
  marginal_totals: Record<string, number>;
  // v8: subjects who clear 80 hrs only by COMBINING work + school (a floor —
  // volunteer/training hours that would also combine aren't observable in PUMS).
  combination_work_school?: number;
}

interface OverlapPayload {
  version: string;
  _meta: {
    method: string;
    categories: string[];
    category_labels: Record<string, string>;
    source: string;
    limitation: string;
  };
  _national: OverlapDistribution;
  states: Record<string, OverlapDistribution & { abbr: string; name: string }>;
}

const COBALT = "#1F1FD6";
const CAROLINA = "#21A8E0";
const CHARCOAL = "#3B3B3B";
const SLATE = "#64748B";
// Bars encode magnitude only; pathway identity lives in the dot colors. A neutral
// slate keeps bar color from being read as a fifth pathway (esp. the cobalt Work dot).
const BAR_NEUTRAL = "#475569";

const CATEGORY_FILL: Record<string, string> = {
  W: COBALT,
  P: "#0EA5A4",
  M: CAROLINA,
  S: "#8B5CF6",
};

const CATEGORY_SHORT: Record<string, string> = {
  W: "Work",
  P: "Parent",
  M: "Medically frail",
  S: "Student",
};

function fmtCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

function fmtPct(n: number, total: number): string {
  if (total <= 0) return "0%";
  return `${((n / total) * 100).toFixed(1)}%`;
}

export default function MedicaidCategoryOverlap() {
  const [data, setData] = useState<OverlapPayload | null>(null);
  const [stateAbbr, setStateAbbr] = useState<string>("US");

  useEffect(() => {
    fetch("/data/medicaid-category-overlaps.json")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null));
  }, []);

  const view = useMemo(() => {
    if (!data) return null;
    if (stateAbbr === "US") return data._national;
    const found = Object.values(data.states).find((s) => s.abbr === stateAbbr);
    return found ?? data._national;
  }, [data, stateAbbr]);

  const stateOptions = useMemo(() => {
    if (!data) return [] as Array<{ abbr: string; name: string }>;
    return Object.values(data.states)
      .map((s) => ({ abbr: s.abbr, name: s.name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [data]);

  if (!data || !view) {
    return (
      <div className="my-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-sm text-slate-500">
        Loading category-overlap data…
      </div>
    );
  }

  const { _meta } = data;
  // Top 8 cells by count, then bucket the rest into "Other combinations".
  const topCells = view.cells.slice(0, 8);
  const restCount = view.cells.slice(8).reduce((s, c) => s + c.count, 0);
  const maxCount = Math.max(...topCells.map((c) => c.count), restCount);
  const total = view.subject_count;

  const ROW_HEIGHT = 28;
  const BAR_HEIGHT = 18;
  const DOTS_W = 100;       // dots column ends here (4 dots × 22px spacing + padding)
  const LABEL_AREA_W = 220; // text label area between dots and bars
  const LABEL_W = DOTS_W + LABEL_AREA_W; // where bars start (was 110, now 320)
  const BAR_W = 340;

  return (
    <section className="my-10">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="font-serif text-xl font-semibold text-cobalt">
          How many of these paths can a state verify automatically?
        </h3>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <label htmlFor="overlap-state" className="font-sans text-[10px] font-semibold uppercase tracking-[0.14em]">
            State
          </label>
          <select
            id="overlap-state"
            value={stateAbbr}
            onChange={(e) => setStateAbbr(e.target.value)}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-xs"
          >
            <option value="US">United States</option>
            {stateOptions.map((s) => (
              <option key={s.abbr} value={s.abbr}>{s.name}</option>
            ))}
          </select>
        </div>
      </div>

      <p className="mb-4 text-sm leading-relaxed text-slate-700">
        Each of these four paths has an administrative source a state could check
        on its own: work hours against UI wage records, parent status
        against the child's own Medicaid case, medical frailty against claims and
        the health information exchange, school enrollment against the National
        Student Clearinghouse. So the question that decides coverage isn't how
        many paths a person <em>has</em>; it's how many the state can confirm{" "}
        <strong>ex parte</strong>, without making them prove it. About 18% of
        subjects sit in two or more paths and carry a built-in backstop: if one
        ex parte check misses, another can catch them. The exposure is the 44% in
        exactly one path: their coverage rides entirely on that single check
        clearing automatically. The zero-path band is the genuinely non-compliant
        population plus adults whose only exemption is one this view doesn't track
        (SUD treatment, recent incarceration, pregnancy, kinship care, AI/AN).
      </p>
      {view.combination_work_school != null && view.combination_work_school > 0 && (
        <div className="mb-5 rounded-lg border-l-4 border-cobalt/40 bg-cobalt/[0.04] px-4 py-3 text-sm leading-relaxed text-slate-700">
          <strong className="text-cobalt">And the paths add up.</strong> About{" "}
          <strong>{fmtCount(view.combination_work_school)}</strong> adults don't
          clear 80 hours through work alone or school alone, but do when you{" "}
          <em>combine</em> the two, which OBBBA explicitly allows. They keep
          coverage only if the state sums hours across activities; a portal that
          checks each path in isolation drops them. This is a floor: volunteer and
          job-training hours that would also combine aren't visible in the Census,
          so the true combination population is larger.
        </div>
      )}

      {/* Roll-up: how many paths */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[0, 1, 2, 3, 4].map((nBuckets) => {
          const count = view.by_category_count[nBuckets] ?? 0;
          const pct = total > 0 ? (count / total) * 100 : 0;
          const isHighlight = nBuckets === 0 || nBuckets === 1;
          return (
            <div
              key={nBuckets}
              className={`rounded-lg border p-3 ${
                isHighlight
                  ? "border-amber-200 bg-amber-50/60"
                  : "border-slate-200 bg-slate-50"
              }`}
            >
              <div className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
                {nBuckets === 0 ? "0 paths" : nBuckets === 1 ? "1 path" : `${nBuckets} paths`}
              </div>
              <div className="mt-1 font-serif text-2xl font-black tabular-nums text-cobalt">
                {fmtCount(count)}
              </div>
              <div className="font-mono text-[11px] tabular-nums text-slate-600">
                {pct.toFixed(1)}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Upset plot */}
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-3">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h4 className="font-serif text-base font-semibold text-cobalt">
              Top combinations of qualifying paths
            </h4>
            <span className="font-mono text-[11px] text-slate-500">
              subject pool {fmtCount(total)}
            </span>
          </div>
          {/* Legend: ties each dot color to its pathway. */}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
            {_meta.categories.map((cat) => (
              <span
                key={cat}
                className="inline-flex items-center gap-1.5 text-[12px] text-slate-700"
              >
                <span
                  aria-hidden
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: CATEGORY_FILL[cat] }}
                />
                {CATEGORY_SHORT[cat]}
              </span>
            ))}
          </div>
          <p className="mt-1.5 text-[11px] leading-snug text-slate-500">
            Each row is one combination of qualifying paths. Filled dots mark the paths
            that apply (gray = doesn't apply); the bar shows how many subjects fall in
            that exact combination.
          </p>
        </div>
        <svg
          viewBox={`0 0 ${LABEL_W + BAR_W + 80} ${(topCells.length + (restCount > 0 ? 1 : 0) + 1) * ROW_HEIGHT + 10}`}
          width="100%"
          preserveAspectRatio="xMidYMid meet"
          style={{ fontFamily: "Source Sans 3, system-ui, sans-serif", maxHeight: 360 }}
          role="img"
          aria-label="Bar chart of subject-pool qualifying-activity combinations; colored dots mark which of the four paths (Work, Parent, Medically frail, Student) apply to each combination, keyed by the legend above"
        >
          {/* Header: count axis label. The category key lives in the HTML legend above. */}
          <g>
            <text x={LABEL_W + 4} y={14} fontSize={10} fill={SLATE} fontWeight={600}>
              Count
            </text>
          </g>

          {/* Rows */}
          {[...topCells, ...(restCount > 0 ? [{ key: "OTHER", categories: [], count: restCount, share: restCount / total }] : [])].map((cell, idx) => {
            const y = (idx + 1) * ROW_HEIGHT + 6;
            const barWidth = maxCount > 0 ? (cell.count / maxCount) * BAR_W : 0;
            const isOther = cell.key === "OTHER";
            return (
              <g key={cell.key}>
                {/* Category dots */}
                {_meta.categories.map((cat, i) => {
                  const present = cell.categories.includes(cat);
                  return (
                    <circle
                      key={cat}
                      cx={10 + i * 22}
                      cy={y - 4}
                      r={5.5}
                      fill={present ? CATEGORY_FILL[cat] : "#E2E8F0"}
                      stroke={present ? CATEGORY_FILL[cat] : "#CBD5E1"}
                    />
                  );
                })}
                {/* Label (combination name) */}
                <text
                  x={10 + _meta.categories.length * 22 + 4}
                  y={y - 1}
                  fontSize={11}
                  fill={CHARCOAL}
                  fontStyle={isOther ? "italic" : "normal"}
                >
                  {isOther
                    ? "Other combinations"
                    : cell.categories.length === 0
                    ? "No qualifying activity"
                    : cell.categories.map((c) => CATEGORY_SHORT[c]).join(" + ")}
                </text>
                {/* Bar */}
                <rect
                  x={LABEL_W}
                  y={y - BAR_HEIGHT / 2 - 2}
                  width={barWidth}
                  height={BAR_HEIGHT}
                  fill={BAR_NEUTRAL}
                  fillOpacity={isOther ? 0.4 : 0.85}
                  rx={2}
                />
                {/* Count + share */}
                <text
                  x={LABEL_W + barWidth + 6}
                  y={y - 1}
                  fontSize={11}
                  fill={CHARCOAL}
                  fontWeight={600}
                >
                  {fmtCount(cell.count)}
                </text>
                <text
                  x={LABEL_W + barWidth + 50}
                  y={y - 1}
                  fontSize={10}
                  fill={SLATE}
                >
                  {fmtPct(cell.count, total)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-5 rounded-lg border-l-4 border-cobalt/40 bg-cobalt/[0.04] px-4 py-3 text-sm leading-relaxed text-slate-700">
        <strong className="text-cobalt">Where to focus isn't the same in every state.</strong>{" "}
        The mix above shifts a lot by state, so pick a couple from the dropdown and
        compare. In Maryland the work path is the single biggest: 23% of subjects rely
        on it alone, with medical frailty next at 17% and students a real slice at 5%.
        In West Virginia the order flips, with medical frailty the largest single path,
        the work path smaller, and students barely 2%. A state with limited resources
        should plan around its own profile, not the national one, and wire up the data
        feeds and streamlined manual processes for the paths that carry the most of its
        people first.
      </div>

      <p className="mt-3 text-[11px] leading-snug text-slate-500">
        Method: per-record ACS PUMS joint counts. Each subject is classified
        into exactly one of 16 cells based on four boolean flags (W, P, M, S)
        from the same PUMS cache that feeds the loss-breakdown Sankey. Cell
        counts are PWGTP-weighted at the state level, then scaled so each
        state's total matches its CBO-anchored subject count. {_meta.limitation}
      </p>
    </section>
  );
}
