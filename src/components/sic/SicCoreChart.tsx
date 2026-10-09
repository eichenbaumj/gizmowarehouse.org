// SicCoreChart — <sic-core-chart></sic-core-chart>
//
// The test, as a picture: every New York county and city whose audited statements say how it finances
// liability, placed by population (x, log) and by what it spent on insurance plus judgments and claims
// per resident over the window (y). Cobalt = carries its own liability; Carolina = buys coverage.
// Hollow gray = the statement was unclear or mixed. Entities held out of the comparison (benefit claims
// on the judgments line, or claims booked elsewhere) are listed under the chart, not plotted.
// Hand-rolled SVG per the repo idiom (compgap/TimeSeriesChart.tsx).

import { useMemo, useState } from "react";
import { STRUCTURE_STYLE, POP_BIN_LABELS, type NyEntitiesData, type NyEntityRow, type Treat } from "@/config/selfInsuranceCost";
import { useSicData, useIsNarrow, SicCard, Eyebrow, Sub, Loading, Err, fmtMoney, fmtPop, STEEL, GRID } from "./useSicData";

const M = { top: 18, right: 18, bottom: 40, left: 54 };

type Metric = "cor_pc_mean" | "cor_share_mean";

export default function SicCoreChart() {
  const { data, err } = useSicData<NyEntitiesData>("ny_entities");
  const narrow = useIsNarrow();
  const [metric, setMetric] = useState<Metric>("cor_pc_mean");
  const [hover, setHover] = useState<NyEntityRow | null>(null);

  const rows = useMemo(() => {
    if (!data) return [];
    return data.rows.filter(
      (r) => r.label_source === "document" && r.pop_mean && r.pop_mean > 0
        && !r.jc_contaminated && !r.coded_elsewhere_holdout && r[metric] != null && (r.n_years ?? 0) >= 8,
    );
  }, [data, metric]);

  const VB_W = narrow ? 420 : 720;
  const H = narrow ? 360 : 400;
  const plot = useMemo(() => {
    if (!rows.length) return null;
    const xs = rows.map((r) => Math.log10(r.pop_mean as number));
    const ys = rows.map((r) => r[metric] as number);
    const xMin = Math.floor(Math.min(...xs) * 2) / 2, xMax = Math.ceil(Math.max(...xs) * 2) / 2;
    const sorted = [...ys].sort((a, b) => a - b);
    const cap = sorted[Math.floor(sorted.length * 0.95)] * 1.15;
    // nice axis: pick a step from {5,10,20,25,50} dollars (or 0.5% / 1% shares) and round the cap up to it
    const steps = metric === "cor_pc_mean" ? [5, 10, 20, 25, 50] : [0.0025, 0.005, 0.01, 0.02];
    const step = steps.find((s) => cap / s <= 5) ?? steps[steps.length - 1];
    const yMax = Math.ceil(cap / step) * step;
    const innerW = VB_W - M.left - M.right, innerH = H - M.top - M.bottom;
    const sx = (x: number) => M.left + ((x - xMin) / (xMax - xMin)) * innerW;
    const sy = (y: number) => M.top + (1 - Math.min(y, yMax) / yMax) * innerH;
    return { xMin, xMax, yMax, sx, sy, innerW, innerH };
  }, [rows, metric, VB_W, H]);

  if (err) return <Err msg={err} />;
  if (!data || !plot) return <Loading h={H} />;

  const nTick = Math.round(plot.yMax / (metric === "cor_pc_mean" ? ([5, 10, 20, 25, 50].find((s) => plot.yMax / s <= 5) ?? 50) : ([0.0025, 0.005, 0.01, 0.02].find((s) => plot.yMax / s <= 5) ?? 0.02)));
  const yTicks = Array.from({ length: nTick + 1 }, (_, i) => (plot.yMax * i) / nTick);
  const xTicks = [4, 4.5, 5, 5.5, 6, 6.5].filter((t) => t >= plot.xMin && t <= plot.xMax);
  const fmtY = (v: number) => (metric === "cor_pc_mean" ? fmtMoney(v) : `${(v * 100).toFixed(1)}%`);
  const treatOf = (r: NyEntityRow): Treat => (r.treat === "self" || r.treat === "covered" ? r.treat : "other");
  const summary = data.summary;

  return (
    <SicCard>
      <Eyebrow>New York, {data.window[0]} to {data.window[1]}</Eyebrow>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-serif text-lg font-bold text-cobalt">How a government pays its claims doesn't predict what it spends</h3>
        <div className="flex gap-1 text-xs">
          {(["cor_pc_mean", "cor_share_mean"] as Metric[]).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={`rounded-full border px-3 py-1 ${metric === m ? "border-cobalt bg-cobalt text-white" : "border-slate-300 text-charcoal"}`}
            >
              {m === "cor_pc_mean" ? "per resident" : "per dollar of spending"}
            </button>
          ))}
        </div>
      </div>
      <Sub>Average yearly cost of premiums plus judgments and claims per resident, in 2024 dollars, for every county, city, town, and village whose arrangement was read from its audited statements.</Sub>
      <div className="relative">
        <svg viewBox={`0 0 ${VB_W} ${H}`} className="w-full" style={{ overflow: "visible" }} role="img"
          aria-label={`Scatter of ${rows.length} New York counties, cities, towns, and villages by population and liability cost, colored by how each pays its claims`}>
          {yTicks.map((t, i) => (
            <g key={i}>
              <line x1={M.left} x2={VB_W - M.right} y1={plot.sy(t)} y2={plot.sy(t)} stroke={GRID} strokeWidth={1} />
              <text x={M.left - 8} y={plot.sy(t) + 3} textAnchor="end" fontSize={narrow ? 12 : 11} fill={STEEL} fontFamily="'Source Sans 3', sans-serif">{fmtY(t)}</text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={t} x={plot.sx(t)} y={H - M.bottom + 16} textAnchor="middle" fontSize={narrow ? 12 : 11} fill={STEEL} fontFamily="'Source Sans 3', sans-serif">
              {fmtPop(Math.pow(10, t))}
            </text>
          ))}
          <text x={M.left + plot.innerW / 2} y={H - 4} textAnchor="middle" fontSize={11} fill={STEEL} fontFamily="'Source Sans 3', sans-serif">population (log scale)</text>
          {rows.map((r) => {
            const t = treatOf(r);
            const x = plot.sx(Math.log10(r.pop_mean as number));
            const v = r[metric] as number;
            const y = plot.sy(v);
            const off = v > plot.yMax;
            const isHover = hover?.muni_code === r.muni_code;
            const common = {
              onMouseEnter: () => setHover(r), onMouseLeave: () => setHover(null), onClick: () => setHover(isHover ? null : r),
              style: { cursor: "pointer" as const },
            };
            const offMark = off ? (
              <text key={r.muni_code + "-off"} x={x} y={M.top - 6} textAnchor="middle" fontSize={9} fill={STEEL} fontFamily="'Source Sans 3', sans-serif">{fmtY(v)}</text>
            ) : null;
            const fill = t === "other" ? "#fff" : STRUCTURE_STYLE[t].color;
            const stroke = t === "other" ? STRUCTURE_STYLE.other.color : "#fff";
            const yy = off ? M.top : y;
            if (r.cls === "city") {
              return (
                <g key={r.muni_code}>{offMark}<rect x={x - 5} y={yy - 5} width={10} height={10} rx={2}
                  fill={fill} stroke={stroke} strokeWidth={isHover ? 2.5 : 1.5} opacity={t === "other" ? 1 : 0.85} {...common} /></g>
              );
            }
            if (r.cls === "town") {
              return (
                <g key={r.muni_code}>{offMark}<rect x={x - 5} y={yy - 5} width={10} height={10} rx={1} transform={`rotate(45 ${x} ${yy})`}
                  fill={fill} stroke={stroke} strokeWidth={isHover ? 2.5 : 1.5} opacity={t === "other" ? 1 : 0.85} {...common} /></g>
              );
            }
            if (r.cls === "village") {
              return (
                <g key={r.muni_code}>{offMark}<polygon points={`${x},${yy - 6} ${x + 6},${yy + 5} ${x - 6},${yy + 5}`}
                  fill={fill} stroke={stroke} strokeWidth={isHover ? 2.5 : 1.5} opacity={t === "other" ? 1 : 0.85} {...common} /></g>
              );
            }
            return (
              <g key={r.muni_code}>{offMark}<circle cx={x} cy={off ? M.top : y} r={isHover ? 7 : 5.5}
                fill={t === "other" ? "#fff" : STRUCTURE_STYLE[t].color} stroke={t === "other" ? STRUCTURE_STYLE.other.color : "#fff"}
                strokeWidth={isHover ? 2.5 : 1.5} opacity={t === "other" ? 1 : 0.85} {...common} /></g>
            );
          })}
        </svg>
        {hover && (
          <div className="pointer-events-none absolute left-2 top-2 max-w-[260px] rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-md">
            <div className="font-semibold text-charcoal">{hover.entity_name}</div>
            <div className="text-steel">{hover.cls} · {fmtPop(hover.pop_mean ?? 0)} residents · {STRUCTURE_STYLE[treatOf(hover)].label.toLowerCase()}</div>
            <div className="mt-1">Cost of risk: <b>{fmtMoney(hover.cor_pc_mean ?? 0)}</b> per resident per year</div>
            <div>Premiums {fmtMoney(hover.ins_pc_mean ?? 0)} · judgments and claims {fmtMoney(hover.jc_pc_mean ?? 0)}</div>
            <div>Worst year in the window: {fmtMoney(hover.cor_pc_p90 ?? 0)}</div>
            {hover.sir_per_occurrence && <div className="text-steel">Retains the first {fmtMoney(Number(hover.sir_per_occurrence))} of each claim</div>}
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-charcoal">
        {(["self", "covered"] as const).map((t) => (
          <span key={t} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: STRUCTURE_STYLE[t].color }} />
            {STRUCTURE_STYLE[t].label}{summary[t] ? ` (${summary[t]!.n})` : ""}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full border" style={{ borderColor: STRUCTURE_STYLE.other.color }} />{STRUCTURE_STYLE.other.label}</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full bg-charcoal" /> county</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-sm bg-charcoal" /> city</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rotate-45 bg-charcoal" /> town</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-0 w-0 border-x-[6px] border-b-[10px] border-x-transparent border-b-charcoal" /> village</span>
      </div>
      {data.holdouts.length > 0 && (
        <p className="mt-2 text-xs text-steel">
          Not plotted: {data.holdouts.map((h) => h.entity_name.replace(/^(County|City) of /, "")).join(", ")}. Their judgments line carries benefit claims or their claims are booked under other accounts; the methodology lists each.
        </p>
      )}
    </SicCard>
  );
}
