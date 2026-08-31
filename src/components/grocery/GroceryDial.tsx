// GroceryDial — the xlsx model's core chain, embedded as a web dial. Three
// inputs (traffic, blended discount, household size); every line of arithmetic
// displayed; leverage read against the 1.0× direct-transfer floor. Constants
// and formulas live in src/config/groceryMath30.ts — the same numbers
// verify_claims.py locks against the downloadable workbook, so this widget and
// the spreadsheet cannot disagree.

import { useState } from "react";
import { GROCERY_MODEL as M, computeDial } from "@/config/groceryMath30";

// one decimal until the rounded value reaches $100M ($99.96M → "$100M", never "$100.0M")
const fmtM = (v: number) =>
  `$${(v / 1e6).toFixed(Math.round(Math.abs(v) / 1e5) >= 1000 ? 0 : 1)}M`;
// hand off at the rounding boundary ($999.5k → "$1.0M", never "$1,000k")
const fmtK = (v: number) =>
  Math.round(Math.abs(v) / 1e3) >= 1000 ? fmtM(v) : `$${Math.round(v / 1e3).toLocaleString()}k`;
// contribution as cents on the dollar: round away from zero, typographic minus, and
// float dust at a 7% blend must read "0¢", never a signed zero
const fmtCents = (v: number) => {
  const cents = Math.round(Math.abs(v) * 100);
  return cents === 0 ? "0¢" : `${v < 0 ? "−" : ""}${cents}¢`;
};
// signed operating result; a value that rounds to $0k carries no sign
const fmtSignedK = (v: number) => {
  const mag = fmtK(Math.abs(v));
  return `${mag === "$0k" ? "" : v < 0 ? "−" : "+"}${mag}`;
};
// round people/households to the nearest hundred — the model isn't sharper than that
const fmtN100 = (v: number) => (Math.round(v / 100) * 100).toLocaleString();

function Row({ label, note, value, strong }: { label: string; note?: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
      <div className="min-w-0">
        <span className={"text-[13px] " + (strong ? "font-semibold text-charcoal" : "text-charcoal/80")}>{label}</span>
        {note && <span className="ml-1.5 text-[11px] text-steel">{note}</span>}
      </div>
      <span className={"whitespace-nowrap font-sans tabular-nums " + (strong ? "text-[15px] font-bold text-cobalt" : "text-[13px] font-semibold text-charcoal")}>
        {value}
      </span>
    </div>
  );
}

function Slider({
  label, value, min, max, step, onChange, fmt, ticks,
}: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; fmt: (v: number) => string;
  // row 1 drops a tick label a line down so close neighbors don't collide
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
          {ticks.map((t) => (
            <button
              key={t.at}
              onClick={() => onChange(t.at)}
              className="absolute -translate-x-1/2 whitespace-nowrap hover:text-cobalt"
              style={{ left: `${((t.at - min) / (max - min)) * 100}%`, top: t.row ? "1rem" : 0 }}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function GroceryDial() {
  const [rev, setRev] = useState<number>(M.defaultRevPerSqft);
  const [blend, setBlend] = useState<number>(M.defaultBlend);
  const [pph, setPph] = useState<number>(M.defaultPersonsPerHH);

  const r = computeDial(rev, blend, pph);
  const overFloor = r.leverage >= 1;
  // blend ≤ 7% means contribution ≥ 0: the store's own economics turn profitable
  // before the discount, so the cash-floor comparison stops binding — the asymptote
  // copy (blend − 7¢ in the denominator) must never render in this regime; the
  // epsilon absorbs float noise at exactly 7%
  const blendUnderMargin = r.contribution >= -1e-9;
  const isDefault = rev === M.defaultRevPerSqft && blend === M.defaultBlend && pph === M.defaultPersonsPerHH;

  return (
    <div className="my-8 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h4 className="font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-steel">
          Dial the assumptions
        </h4>
        {!isDefault && (
          <button
            onClick={() => { setRev(M.defaultRevPerSqft); setBlend(M.defaultBlend); setPph(M.defaultPersonsPerHH); }}
            className="rounded-md border border-slate-300 px-2 py-0.5 text-[11px] text-charcoal/70 hover:border-cobalt/50"
          >
            reset to central case
          </button>
        )}
      </div>
      <p className="mb-4 text-[12px] leading-snug text-steel">
        The downloadable model's core chain, live. Costs are held at industry figures
        (COGS 72%, labor 12%, other 9% of gross, $400k operator fee, $70M build) — the
        spreadsheet's yellow cells cover those too.
      </p>

      <div className="mb-5 grid gap-4 sm:grid-cols-3">
        <Slider
          label="Sales per sqft"
          value={rev} min={300} max={3000} step={1}
          onChange={setRev} fmt={(v) => `$${v.toLocaleString()}`}
          ticks={[
            { at: M.aprilRevPerSqft, label: "quieter" },
            { at: M.defaultRevPerSqft, label: "industry avg (FMI 2025)", row: 1 },
            { at: 2000, label: "Trader Joe's" },
            { at: 2200, label: "past any real store", row: 1 },
          ]}
        />
        <Slider
          label="Blended in-store discount"
          value={blend} min={0.05} max={0.3} step={0.005}
          onChange={setBlend}
          fmt={(v) => `${(v * 100).toFixed(1).replace(/\.0$/, "")}%`}
          ticks={[
            { at: M.aprilDiscount, label: "April model" },
            { at: M.defaultBlend, label: "30% × 60% basket" },
            { at: 0.3, label: "all basket" },
          ]}
        />
        <Slider
          label="People per household"
          value={pph} min={2} max={3.5} step={0.01}
          onChange={setPph} fmt={(v) => v.toFixed(2)}
          ticks={[{ at: M.defaultPersonsPerHH, label: "NYC avg (Census)" }]}
        />
      </div>

      <Row label="Gross revenue per store" note={`${M.avgSqft.toLocaleString()} sqft × $${rev.toLocaleString()}`} value={`${fmtM(r.grossPerStore)}/yr`} />
      <Row label="Kept from each $1 of sales" note={`(1 − ${(blend * 100).toFixed(1).replace(/\.0$/, "")}%) − 93¢ of costs`} value={fmtCents(r.contribution)} />
      <Row label="Operating result per store" value={`${fmtSignedK(r.resultPerStore)}/yr`} />
      <Row label={r.subsidyPerYear >= 0 ? "Public subsidy, five stores" : "Public profit, five stores"} value={`${fmtM(Math.abs(r.subsidyPerYear))}/yr`} />
      <Row label="Ten-year public envelope" note="$70M build + ten years of subsidy" value={fmtM(r.envelope)} strong />
      <Row label="Discount dollars reaching shoppers" value={`${fmtM(r.transferPerYear)}/yr`} />
      <Row label="Households getting the full deal" note={`at the promised $${r.savingsPerYear.toLocaleString()}/yr`} value={fmtN100(r.households)} strong />
      <Row label="New Yorkers" note={`× ${pph.toFixed(2)} per household`} value={fmtN100(r.people)} strong />

      {/* Leverage vs the 1.0× floor */}
      <div className="mt-4">
        <div className="flex items-baseline justify-between">
          <div className="min-w-0">
            <span className="text-[13px] font-semibold text-charcoal">Food benefit per public dollar</span>
            <span className="ml-1.5 text-[11px] text-steel">in today's dollars</span>
          </div>
          <span className={"font-sans text-[15px] font-bold tabular-nums " + (overFloor ? "text-carolina" : "text-cobalt")}>
            {(r.leverage < 1 ? Math.floor(r.leverage * 100) / 100 : r.leverage).toFixed(2)}×
          </span>
        </div>
        <div className="relative mt-1 h-3 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={"h-full rounded-full " + (overFloor ? "bg-carolina" : "bg-cobalt")}
            style={{ width: `${Math.min(r.leverage / 1.25, 1) * 100}%` }}
          />
          <div className="absolute inset-y-0" style={{ left: `${(1 / 1.25) * 100}%` }}>
            <div className="h-full w-0.5 bg-charcoal/60" />
          </div>
        </div>
        <div className="relative mt-0.5 h-4 text-[10px] text-steel">
          <span className="absolute -translate-x-1/2" style={{ left: `${(1 / 1.25) * 100}%` }}>
            1.0× = plain cash transfer
          </span>
        </div>
        <p className="mt-2 text-[12.5px] leading-snug text-charcoal/85">
          {overFloor ? (
            blendUnderMargin ? (
              <>At blends of 7% and below the store's own economics turn profitable before
              the discount — the cash-floor comparison no longer binds; drag the discount
              deeper to model the announced plan.</>
            ) : (
              <>At these settings the stores beat a plain cash transfer — it takes sales above
              about $2,200/sqft, busier than almost any grocery store in America, and the subsidy
              runs {fmtM(r.subsidyPerYear)} a year. Even infinite traffic tops out at{" "}
              {(blend / (blend - 0.07)).toFixed(2)}× at this blend (the details below explain why).</>
            )
          ) : (
            <>At these settings: a {fmtM(r.envelope)} ten-year envelope reaches {fmtN100(r.households)} households
            ({fmtN100(r.people)} New Yorkers) with the full deal, at {(Math.floor(r.leverage * 100) / 100).toFixed(2)}× — under the 1.0×
            floor a plain cash transfer hits by definition.</>
          )}
        </p>
      </div>

      <details className="mt-4 border-t border-slate-100 pt-3">
        <summary className="cursor-pointer font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-steel hover:text-cobalt">
          How this behaves at the extremes
        </summary>
        <div className="mt-2 space-y-2 text-[12px] leading-snug text-charcoal/80">
          <p>
            Traffic is an input, not a consequence. Nothing here makes shoppers show up — the
            slider hands the stores whatever volume you choose. The discount is the obvious
            mechanism that would draw a crowd, but the model doesn't feed that back.
          </p>
          <p>
            The leverage line reads in today's dollars: ten years of discounts and ten years
            of subsidy are each discounted to present value at a 4% municipal borrowing rate
            before dividing, while the envelope line stays nominal — the sum of the checks
            the city writes.
          </p>
          <p>
            The stores can beat the 1.0× floor in this model, above about $2,200 per square
            foot at any blend. The algebra: each $1 of sales carries 93¢ of industry costs, so
            before the operator fee a store keeps 7¢. That 7¢ slowly pays off the fixed $70M of
            construction and $2M a year of operator fees; past ~$2,200/sqft the fixed costs are
            covered and every sale funds a sliver of its own discount.
          </p>
          <p>
            It cannot run away. Even at infinite traffic, leverage tops out at discount ÷
            (discount − 7¢): 1.64× at the central 18% blend, 1.30× at 30%. Time doesn't rescue
            it either: run the stores forever and charge for replacing the fit-out as it wears
            out, and they sit under the cash floor (0.70–0.82×); the ten-year record is 0.69×.
            The alternatives in the table above run 1× to 20×.
          </p>
          <p>
            $2,000/sqft is Trader Joe's-class, the busiest sustained grocery throughput in
            America. The slider runs to $3,000 so the crossing is visible; treat everything past
            ~$2,200 as uncharted for any US grocer, let alone five municipal startups. Costs are
            held at industry ratios at every volume — real stores do a bit better on purchasing
            and labor at extreme volume, so the far right end, if anything, understates the
            stores. The realism constraint is the traffic itself.
          </p>
          <p>
            And the ratio is not the bill: at the crossover the subsidy still runs $19&ndash;37M a
            year depending on the blend. Every input here is also a yellow cell in the{" "}
            <a href="/assets/nyc-public-grocery-model.xlsx" className="text-carolina hover:underline">
              downloadable model
            </a>{" "}
            (July 2026 Update tab), which also covers what this dial holds fixed: 13,800 avg
            sqft across the five announced stores, the cost ratios, and the $70M build.
          </p>
        </div>
      </details>
    </div>
  );
}
