// DcrTownCalc — "what does saying no cost this town" (<dcr-town-calc />).
//
// Two inputs: tax regime (case-anchored ranges) and campus size (denominated
// in announced build cost). No counterfactual discount — the calculator
// assumes a live proposal; the would-it-have-come question lives in the
// prose. Constants and the arithmetic live in
// src/config/dataCenterRestrictionCost.ts — the same numbers
// verify_claims.py locks against the pipeline's benchmarks.json, so this
// widget and the downloadable dataset cannot disagree. Skeleton follows
// GroceryDial.

import { useState } from "react";
import { DCR_MODEL as M, REGIMES, computeForegone } from "@/config/dataCenterRestrictionCost";

const fmtM = (v: number) =>
  v >= 1000 ? `$${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}B` : `$${v >= 100 ? Math.round(v) : v.toFixed(1)}M`;
const fmtRange = (lo: number, hi: number) => `${fmtM(lo)}–${fmtM(hi)}`;

function Row({ label, note, value, strong }: { label: string; note?: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
      <div className="min-w-0">
        <span className={"text-[13px] " + (strong ? "font-semibold text-charcoal" : "text-charcoal/80")}>{label}</span>
        {note && <span className="ml-1.5 text-[11px] text-steel">{note}</span>}
      </div>
      <span
        className={
          "whitespace-nowrap font-sans tabular-nums " +
          (strong ? "text-[15px] font-bold text-cobalt" : "text-[13px] font-semibold text-charcoal")
        }
      >
        {value}
      </span>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  fmt,
  ticks,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  fmt: (v: number) => string;
  ticks?: { at: number; label: string; row?: number }[];
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label className="text-[12px] font-semibold text-charcoal">{label}</label>
        <span className="font-sans text-[13px] font-bold tabular-nums text-cobalt">{fmt(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-cobalt"
        aria-label={label}
      />
      {ticks && (
        <div className={"relative text-[10px] text-steel " + (ticks.some((t) => t.row) ? "h-8" : "h-4")}>
          {ticks.map((t) => {
            const pct = ((t.at - min) / (max - min)) * 100;
            // Edge ticks pin to the rail's ends instead of centering, so long
            // labels don't bleed outside the card.
            const align = pct <= 3 ? "" : pct >= 97 ? "-translate-x-full" : "-translate-x-1/2";
            return (
              <button
                key={t.at}
                onClick={() => onChange(t.at)}
                className={"absolute whitespace-nowrap hover:text-cobalt " + align}
                style={{ left: `${pct}%`, top: t.row ? "1rem" : 0 }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function DcrTownCalc() {
  const [regimeId, setRegimeId] = useState<string>("partial_abatement");
  const [scale, setScale] = useState<number>(1);

  const regime = REGIMES.find((r) => r.id === regimeId) ?? REGIMES[1];
  const r = computeForegone(regimeId, scale);
  const isDefault = regimeId === "partial_abatement" && scale === 1;

  return (
    <div className="my-8 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h4 className="font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-steel">
          What saying no costs this town
        </h4>
        {!isDefault && (
          <button
            onClick={() => {
              setRegimeId("partial_abatement");
              setScale(1);
            }}
            className="rounded-md border border-slate-300 px-2 py-0.5 text-[11px] text-charcoal/70 hover:border-cobalt/50"
          >
            reset to central case
          </button>
        )}
      </div>
      <p className="mb-4 text-[12px] leading-snug text-steel">
        Every range here is anchored to a named case, not a model: what operating campuses actually pay their counties
        and school districts each year. It prices the situation Tucson was in, a live proposal on the table. Abatement
        structure, not facility size, drives the spread.
      </p>

      {/* Tax regime — segmented control */}
      <div className="mb-4">
        <div className="mb-1 text-[12px] font-semibold text-charcoal">Local tax regime</div>
        <div className="flex flex-wrap gap-1.5">
          {REGIMES.map((g) => {
            const on = g.id === regimeId;
            return (
              <button
                key={g.id}
                onClick={() => setRegimeId(g.id)}
                className={`rounded-md border px-2.5 py-1.5 text-left text-[12px] transition-colors ${
                  on ? "border-transparent bg-cobalt text-white" : "border-gray-300 text-charcoal hover:bg-gray-50"
                }`}
              >
                <span className="font-bold">{g.label}</span>
                <span className={"block text-[10px] " + (on ? "text-white/80" : "text-steel")}>{g.anchor}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mb-5">
        <Slider
          label="Campus size (announced build cost)"
          value={scale}
          min={M.scaleMin}
          max={M.scaleMax}
          step={0.05}
          onChange={setScale}
          fmt={(v) => `≈$${(v * M.referenceCapexUsdB).toFixed(1)}B`}
          ticks={[
            { at: M.scaleMin, label: "single building" },
            { at: 1, label: `Project Blue (~$${M.referenceCapexUsdB}B)`, row: 1 },
            { at: M.scaleElPasoMeta, label: "El Paso Meta (~$10B)" },
          ]}
        />
      </div>

      <Row
        label="What a campus like this pays locally"
        note={regime.anchor}
        value={`${fmtRange(regime.lowM * scale, regime.highM * scale)}/yr`}
      />
      <Row
        label={`Foregone local revenue over ${M.horizonYears} years`}
        value={fmtRange(r.low10, r.high10)}
        strong
      />
      <Row
        label="Permanent jobs at stake"
        note="the benefit is tax base, not jobs"
        value={`~${M.jobsPerFacilityPermanent} per facility`}
      />

      <p className="mt-3 text-[12.5px] leading-snug text-charcoal/85">
        Under these assumptions, this town gives up {fmtRange(r.low10, r.high10)} over {M.horizonYears} years. For
        comparison, Pima County penciled about ${M.referenceLocal10yrUsdM}M of city and county revenue for Project
        Blue, a lower number because Arizona's tax structure captures less per campus. The regime buttons matter more
        than the slider. And if there is no live proposal on your desk, these numbers are a ceiling.
      </p>

      <details className="mt-4 border-t border-slate-100 pt-3">
        <summary className="cursor-pointer font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-steel hover:text-cobalt">
          What this holds fixed, and why it stops at ten years
        </summary>
        <div className="mt-2 space-y-2 text-[12px] leading-snug text-charcoal/80">
          <p>
            The ranges are per-campus annual local revenue from documented cases: Morrow County, Oregon's
            enterprise-zone deal (roughly $2–3M a year in fees in exchange for over $1B in abated property taxes),
            Georgia's December 2025 state audit (a representative three-building metro-Atlanta campus: $33.6M a year
            gross, $5.9M abated, $27.8M collected), El Paso's Meta deal (80% abated for 35 years, still roughly $56M a
            year across local entities), and Virginia-style unabated equipment taxation, where Loudoun County collects
            more from data centers than from all residential property tax combined. This is deliberately not a
            per-megawatt model; that takes county assessment rolls and is the next phase of this work.
          </p>
          <p>
            It applies no discount for whether the project would actually have been built here: it assumes a live
            proposal, which is the situation where a town faces this choice, and the same undiscounted basis Pima
            County used for its own Project Blue estimate. Without a proposal on the table, the numbers are a ceiling.
          </p>
          <p>
            Revenue volatility is real and cuts against the high end: servers depreciate in three to five years, and
            Loudoun's June 2026 equipment assessments came in $1.1B under forecast, a roughly $60M budget hole in the
            country's best-case jurisdiction. The county keeps a $114M stabilization fund for exactly this reason.
          </p>
          <p>
            It stops at ten years because the forecasts underneath any longer horizon disagree with each other by a
            factor of two, and the market's own analysts revised their 2035 numbers by 2.5× within fifteen months.
            Extrapolating past 2036 would be speculation, so this calculator refuses to.
          </p>
        </div>
      </details>
    </div>
  );
}
