// MedicaidTargetList — floating panel at top-right of the Medicaid map.
//
// Shift+click a cell in the map → adds it to the target list. The list is
// what a state Medicaid director would actually build operationally: "these
// are the geographies my outreach team is owning, here's the running
// aggregate, give me the CSV." Persists across reloads via localStorage so
// work-in-progress targeting doesn't get blown away.
//
// Aggregates use the right formula: population-weighted average rate
// (Σ subject / Σ working-age), NOT the arithmetic mean of rates.

import { useEffect, useMemo, useState } from "react";

export interface TargetCell {
  /** Stable identifier — cell_id for grid, GEOID for county, coarse_id for hex */
  id: string;
  /** Map primitive for the cobalt outline + heterogeneity warning */
  kind: "county" | "hex" | "grid";
  /** Lng/lat for "fly to" link */
  lngLat: [number, number];
  /** Human-readable location label rendered in the row */
  label: string;
  /** Subpoints — state, county, etc. */
  sublabel?: string;
  /** Snapshot of feature properties at the moment of pin (so removing the
   * cell from view doesn't lose the data). Refresh on re-pin. */
  props: Record<string, any>;
  /** Unix ms — used for FIFO ordering when needed */
  addedAt: number;
}

interface Props {
  targetList: TargetCell[];
  onRemove: (id: string) => void;
  onClear: () => void;
  /** State abbreviation used for the CSV filename */
  stateAbbrForExport?: string;
}

const COBALT = "#1F1FD6";

function fmtN(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return Math.round(n).toLocaleString("en-US");
}

function fmtCompact(n: number): string {
  if (!Number.isFinite(n)) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return Math.round(n / 1_000).toLocaleString() + "K";
  return Math.round(n).toLocaleString();
}

function fmtPct(p: number): string {
  if (!Number.isFinite(p)) return "—";
  return (p * 100).toFixed(1) + "%";
}

function downloadCsv(rows: TargetCell[], stateAbbr?: string): void {
  const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const filename = stateAbbr
    ? `medicaid-targeting-${stateAbbr}-${ts}.csv`
    : `medicaid-targeting-${ts}.csv`;
  const header = [
    "id",
    "kind",
    "label",
    "sublabel",
    "lng",
    "lat",
    "subject_count_strict",
    "loss_exposure_strict",
    "subject_rate",
    "burden_index_centered",
    "total_pop",
  ];
  const lines = [header.join(",")];
  for (const c of rows) {
    const p = c.props || {};
    const fields = [
      c.id,
      c.kind,
      `"${(c.label || "").replace(/"/g, '""')}"`,
      `"${(c.sublabel || "").replace(/"/g, '""')}"`,
      c.lngLat[0].toFixed(5),
      c.lngLat[1].toFixed(5),
      p.subject_count_strict ?? "",
      p.loss_exposure_strict ?? "",
      p.subject_rate ?? "",
      p.burden_index_centered ?? "",
      p.total_pop ?? "",
    ];
    lines.push(fields.join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function MedicaidTargetList({
  targetList,
  onRemove,
  onClear,
  stateAbbrForExport,
}: Props) {
  // Default collapsed when the list first appears — keeps the corner light
  // and avoids overlapping freshly-opened popups. User clicks to expand.
  const [expanded, setExpanded] = useState(false);

  // When the list goes from empty → non-empty, stay collapsed (don't surprise the user
  // with a panel covering the cell they just clicked). When it goes from non-empty →
  // empty, the parent unmounts us anyway.
  useEffect(() => {
    if (targetList.length === 0) setExpanded(false);
  }, [targetList.length]);

  // Aggregates — population-weighted average rate (Σ subject / Σ working-age).
  // Per-row rate × pop is correct because cells' working-age pop is
  // (total_pop × WORKING_AGE_SHARE) where WORKING_AGE_SHARE is constant in
  // the bake, so the weight is proportional to total_pop. We use subject /
  // working_age_proxy where working_age_proxy = subject / rate (avoids
  // needing the working-age field on every primitive).
  const { totalSubject, totalLoss, weightedRate, hasMixedPrimitives } =
    useMemo(() => {
      let sumSubject = 0;
      let sumLoss = 0;
      let sumWA = 0;
      const kindSet = new Set<string>();
      for (const c of targetList) {
        const p = c.props || {};
        const subj = Number(p.subject_count_strict ?? 0);
        const loss = Number(p.loss_exposure_strict ?? 0);
        const rate = Number(p.subject_rate ?? 0);
        sumSubject += subj;
        sumLoss += loss;
        // Derive cell's working-age pop from subject + rate (since rate = subj/WA)
        if (rate > 0) sumWA += subj / rate;
        kindSet.add(c.kind);
      }
      return {
        totalSubject: sumSubject,
        totalLoss: sumLoss,
        weightedRate: sumWA > 0 ? sumSubject / sumWA : 0,
        hasMixedPrimitives: kindSet.size > 1,
      };
    }, [targetList]);

  if (targetList.length === 0) return null;

  // Collapsed pill — default state. Light, out of the way, but noticeable.
  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="pointer-events-auto absolute right-3 top-3 z-20 flex items-center gap-1.5 rounded-full bg-white/95 px-3 py-1.5 font-sans text-[11px] font-semibold uppercase tracking-[0.08em] text-cobalt shadow-md ring-1 ring-slate-200 backdrop-blur-sm transition hover:bg-white hover:shadow-lg"
        aria-label="Expand target list"
        aria-expanded="false"
      >
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: COBALT }}
          aria-hidden
        />
        <span>Targeting · {targetList.length}</span>
        <span aria-hidden className="text-slate-400">▾</span>
      </button>
    );
  }

  return (
    <div
      className="pointer-events-auto absolute right-3 top-3 z-20 w-[300px] rounded-lg bg-white/95 shadow-xl ring-1 ring-slate-200 backdrop-blur-sm"
      style={{ maxHeight: "calc(100% - 24px)", display: "flex", flexDirection: "column" }}
    >
      {/* Header — aggregates */}
      <div className="border-b border-slate-200 px-4 py-3" style={{ background: "rgba(31, 31, 214, 0.04)" }}>
        <div className="flex items-baseline justify-between">
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="font-sans text-[10px] font-semibold uppercase tracking-[0.12em] text-cobalt transition hover:text-cobalt/70"
            aria-label="Collapse target list"
            aria-expanded="true"
          >
            Targeting · {targetList.length} {targetList.length === 1 ? "cell" : "cells"} <span className="text-slate-400">▴</span>
          </button>
          <button
            type="button"
            onClick={onClear}
            className="font-sans text-[10px] font-semibold uppercase tracking-wider text-slate-400 transition hover:text-rose-600"
            aria-label="Clear all targeted cells"
          >
            Clear
          </button>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-2">
          <div>
            <div className="font-serif text-[1.2rem] font-semibold leading-none tabular-nums text-cobalt">
              {fmtCompact(totalSubject)}
            </div>
            <div className="mt-0.5 text-[9.5px] font-sans text-slate-500">Subject</div>
          </div>
          <div>
            <div className="font-serif text-[1.2rem] font-semibold leading-none tabular-nums text-cobalt">
              {fmtCompact(totalLoss)}
            </div>
            <div className="mt-0.5 text-[9.5px] font-sans text-slate-500">Projected loss</div>
          </div>
          <div>
            <div className="font-serif text-[1.2rem] font-semibold leading-none tabular-nums text-cobalt">
              {fmtPct(weightedRate)}
            </div>
            <div className="mt-0.5 text-[9.5px] font-sans text-slate-500">Avg rate</div>
          </div>
        </div>
        {hasMixedPrimitives && (
          <div className="mt-2 rounded bg-amber-50 px-2 py-1 text-[10px] text-amber-800">
            Mixed primitives (county + cells) — aggregates may double-count overlapping geographies.
          </div>
        )}
      </div>

      {/* Rows */}
      <div className="overflow-y-auto" style={{ flex: 1 }}>
        {targetList.map((c) => (
          <div
            key={c.id}
            className="group flex items-start justify-between gap-2 border-b border-slate-100 px-4 py-2 last:border-b-0 hover:bg-slate-50"
          >
            <div className="min-w-0 flex-1">
              <div className="truncate font-sans text-[11.5px] font-semibold text-slate-700">
                {c.label}
              </div>
              {c.sublabel && (
                <div className="truncate font-sans text-[10px] text-slate-500">{c.sublabel}</div>
              )}
              <div className="mt-1 flex items-baseline gap-2 text-[10.5px] font-sans text-slate-600">
                <span className="font-serif font-semibold tabular-nums text-cobalt">
                  {fmtN(Number(c.props?.subject_count_strict ?? 0))}
                </span>
                <span className="text-slate-400">subject</span>
                <span className="font-serif tabular-nums">
                  {fmtPct(Number(c.props?.subject_rate ?? 0))}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onRemove(c.id)}
              className="mt-0.5 flex-shrink-0 rounded p-0.5 text-slate-300 transition hover:bg-rose-100 hover:text-rose-700"
              aria-label={`Remove ${c.label} from target list`}
            >
              <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden>
                <path
                  d="M3 3l8 8M11 3l-8 8"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        ))}
      </div>

      {/* Footer — CSV download */}
      <div className="border-t border-slate-200 px-4 py-2.5">
        <button
          type="button"
          onClick={() => downloadCsv(targetList, stateAbbrForExport)}
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-cobalt px-3 py-1.5 font-sans text-[11px] font-semibold uppercase tracking-wider text-white shadow-sm transition hover:bg-cobalt/90"
          style={{ background: COBALT }}
        >
          Download CSV ({targetList.length})
          <span aria-hidden>↓</span>
        </button>
      </div>
    </div>
  );
}
