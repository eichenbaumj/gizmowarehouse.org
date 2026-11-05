// Inline-SVG primitives shared across the piece: a 24-bin hour strip, a 7x24 week heat strip (rotates to
// 24 rows on narrow screens), and the petit-larceny tide.
import { useMemo } from "react";
import { CAROLINA, COBALT, GHOST, STRIP_RAMP, STEEL, type ClockFile } from "@/config/hoytSchermerhorn";
import { useHoytData } from "./hoytData";
import { useIsNarrow } from "@/hooks/useIsNarrow";
import { DOW, HOURS, hourLabel } from "./hoytData";

export function HoytHourStrip({ hist, tick, height = 48, color = COBALT, ghost }: { hist: number[]; tick?: number; height?: number; color?: string; ghost?: number[] }) {
  const W = 480; const pad = 2;
  const max = Math.max(1, ...hist, ...(ghost ?? []));
  const bw = (W - pad * 2) / 24;
  return (
    <svg viewBox={`0 0 ${W} ${height + 16}`} className="block w-full" role="img" aria-label="Complaints by hour of day">
      {hist.map((v, h) => <rect key={h} x={pad + h * bw + 1} y={height - (v / max) * height} width={bw - 2} height={(v / max) * height} fill={color} />)}
      {/* the comparison series sits on top as an outlined bar, so it reads whether it is above or below the filled one */}
      {ghost && ghost.map((v, h) => <rect key={`g${h}`} x={pad + h * bw + 1.5} y={height - (v / max) * height} width={bw - 3} height={(v / max) * height} fill={GHOST} fillOpacity={0.35} stroke="#3B3B3B" strokeWidth={1.2} />)}
      {tick != null && <line x1={pad + (tick + 0.5) * bw} x2={pad + (tick + 0.5) * bw} y1={0} y2={height} stroke={CAROLINA} strokeWidth={2} strokeDasharray="3 2" />}
      {[0, 6, 12, 18].map((h) => <text key={h} x={pad + (h + 0.5) * bw} y={height + 12} fontSize={10} fontFamily="Source Sans 3" fill={STEEL} textAnchor="middle">{hourLabel(h)}</text>)}
    </svg>
  );
}

function ramp(v: number, max: number): string {
  if (!v || !max) return STRIP_RAMP[0];
  const i = Math.min(STRIP_RAMP.length - 1, 1 + Math.floor((v / max) * (STRIP_RAMP.length - 1)));
  return STRIP_RAMP[i];
}

/** 7 x 24 heat strip. `max` is printed so strips with different totals never read alike. */
export function HoytWeekStrip({ week, title, max }: { week: number[][]; title?: string; max?: number }) {
  const narrow = useIsNarrow(640);
  const m = max ?? Math.max(1, ...week.flat());
  const cell = 14; const gap = 1;
  const cols = narrow ? 7 : 24; const rows = narrow ? 24 : 7;
  const W = 40 + cols * (cell + gap); const H = 18 + rows * (cell + gap) + 16;
  return (
    <figure className="not-prose my-2">
      {title && <div className="mb-1 font-sans text-[12px] font-semibold text-charcoal">{title} <span className="font-normal text-steel">· darkest cell = {m}</span></div>}
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={title ?? "Complaints by weekday and hour"}>
        {week.map((row, d) => row.map((v, h) => {
          const x = narrow ? 40 + d * (cell + gap) : 40 + h * (cell + gap);
          const y = narrow ? 18 + h * (cell + gap) : 18 + d * (cell + gap);
          return <rect key={`${d}-${h}`} x={x} y={y} width={cell} height={cell} fill={ramp(v, m)} rx={2} />;
        }))}
        {narrow
          ? DOW.map((d, i) => <text key={d} x={40 + i * (cell + gap) + cell / 2} y={12} fontSize={9} textAnchor="middle" fontFamily="Source Sans 3" fill={STEEL}>{d}</text>)
          : DOW.map((d, i) => <text key={d} x={36} y={18 + i * (cell + gap) + cell - 3} fontSize={10} textAnchor="end" fontFamily="Source Sans 3" fill={STEEL}>{d}</text>)}
        {narrow
          ? [0, 6, 12, 18].map((h) => <text key={h} x={36} y={18 + h * (cell + gap) + cell - 3} fontSize={9} textAnchor="end" fontFamily="Source Sans 3" fill={STEEL}>{hourLabel(h)}</text>)
          : [0, 6, 12, 18].map((h) => <text key={h} x={40 + h * (cell + gap) + cell / 2} y={12} fontSize={10} textAnchor="middle" fontFamily="Source Sans 3" fill={STEEL}>{hourLabel(h)}</text>)}
      </svg>
    </figure>
  );
}

export function HoytTide({ years, values, partialYear = "2026" }: { years: string[]; values: number[]; partialYear?: string }) {
  const W = 480; const H = 120; const padL = 36; const padB = 18;
  const max = Math.max(1, ...values);
  const n = values.length;
  const x = (i: number) => padL + (i / (n - 1)) * (W - padL - 8);
  const y = (v: number) => H - padB - (v / max) * (H - padB - 8);
  const path = useMemo(() => values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" "), [values]);
  const area = `${path} L${x(n - 1).toFixed(1)},${(H - padB).toFixed(1)} L${x(0).toFixed(1)},${(H - padB).toFixed(1)} Z`;
  const pi = years.indexOf(partialYear);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label="Petit larceny complaints per year">
      <path d={area} fill={CAROLINA} opacity={0.18} />
      <path d={path} fill="none" stroke={CAROLINA} strokeWidth={2} />
      {pi >= 0 && <circle cx={x(pi)} cy={y(values[pi])} r={3} fill="#fff" stroke={CAROLINA} strokeWidth={2} />}
      {[0, Math.round(max / 2), max].map((v) => <text key={v} x={padL - 4} y={y(v) + 3} fontSize={10} textAnchor="end" fontFamily="Source Sans 3" fill={STEEL}>{v.toLocaleString()}</text>)}
      {years.map((yr, i) => (i % 5 === 0 || i === n - 1) && <text key={yr} x={x(i)} y={H - 4} fontSize={10} textAnchor="middle" fontFamily="Source Sans 3" fill={STEEL}>{yr}{yr === partialYear ? "*" : ""}</text>)}
    </svg>
  );
}

export function HoytWeekCompare() {
  const { data } = useHoytData<ClockFile>("clock");
  if (!data) return <div className="not-prose my-8 h-64 animate-pulse rounded-2xl bg-vellum" />;
  // One grid, the block's. The city comparison is the weekday share printed under it; the hour-by-hour
  // comparison already lives in the bars above.
  const share = (w: number[][]) => { const tot = w.flat().reduce((a, b) => a + b, 0); const wk = w.slice(0, 5).flat().reduce((a, b) => a + b, 0); return Math.round((wk / tot) * 100); };
  const blockWk = share(data.week.core400); const cityWk = share(data.week.city);
  return (
    <div className="not-prose my-8 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      <HoytWeekStrip week={data.week.core400} title="This block, every violent complaint since 2006, by weekday and hour" max={data.week_max.core400} />
      <div className="mt-1 grid grid-cols-1 gap-2 font-sans sm:grid-cols-2 sm:gap-4">
        <div><span className="font-serif text-2xl font-bold text-cobalt">{blockWk}%</span> <span className="text-xs text-steel">of this block's complaints fall Monday to Friday</span></div>
        <div><span className="font-serif text-2xl font-bold" style={{ color: STEEL }}>{cityWk}%</span> <span className="text-xs text-steel">of the city's do (five of seven days would be 71%)</span></div>
      </div>
      <div className="mt-1 font-sans text-xs" style={{ color: STEEL }}>Placeholder times (midnight, noon) excluded. Darkest cell printed above.</div>
    </div>
  );
}

export { HOURS };
