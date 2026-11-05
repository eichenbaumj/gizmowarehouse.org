// Every precinct's change in violent crime (murder + robbery + felony assault) from 1990 to 2025, as a
// strip of dots. Labels for the most and least improved and the 84th; click any dot to pin it; a search
// box finds a precinct by number, borough or neighborhood.
import { useMemo, useState } from "react";
import { CAROLINA, COBALT, STEEL, type PrecinctsFile } from "@/config/hoytSchermerhorn";
import { useHoytData, fmtInt } from "./hoytData";
import { Card, Eyebrow } from "./HoytChrome";

type Row = PrecinctsFile["summary"][number] & { borough?: string; neighborhoods?: string };
const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][Math.min(n % 10, 4)] ?? "th"}`;

export function HoytPrecinctStrip() {
  const { data } = useHoytData<PrecinctsFile>("precincts_1990");
  const [picked, setPicked] = useState<number | null>(null);
  const rows = useMemo(() => ((data?.summary ?? []) as Row[]).filter((r) => r.change_pct != null), [data]);
  if (!data) return <Card className="not-prose my-8"><div className="h-40 animate-pulse rounded bg-vellum" /></Card>;
  const W = 760; const H = 230; const padL = 20; const padR = 20;
  const min = -100; const max = 20;
  const x = (v: number) => padL + ((v - min) / (max - min)) * (W - padL - padR);
  const sorted = [...rows].sort((a, b) => (a.change_pct as number) - (b.change_pct as number));
  // Beeswarm: dots that would overlap horizontally stack upward from the axis line.
  const R = 5; const baseY = 150; const binW = R * 2 + 1;
  const stacks = new Map<number, number>();
  const placed = sorted.map((r) => {
    const px = x(r.change_pct as number); const bin = Math.round(px / binW);
    const k = stacks.get(bin) ?? 0; stacks.set(bin, k + 1);
    return { r, px, py: baseY - k * (R * 2 + 1) };
  });
  const labeled = new Set<number>([...sorted.slice(0, 3), ...sorted.slice(-3)].map((r) => r.precinct).concat([84]));
  const sel = picked != null ? rows.find((r) => r.precinct === picked) ?? null : null;
  // Labels: sorted by x, pushed right so they never overlap; a leader line points back to the dot.
  const place = (r: Row) => (r.neighborhoods ?? "").split(";")[0].trim() || ordinal(r.precinct);
  const widthOf = (t: string) => Math.max(56, t.length * 6.4 + 10);
  const labels: { r: Row; px: number; py: number; lx: number; ly: number }[] = [];
  let cursorRight = -Infinity;
  for (const pt of placed.filter((q) => labeled.has(q.r.precinct) || q.r.precinct === picked)) {
    const w = widthOf(place(pt.r));
    const lx = Math.min(Math.max(pt.px, cursorRight + w / 2), W - padR - w / 2); cursorRight = lx + w / 2;
    labels.push({ ...pt, lx, ly: 34 });
  }
  return (
    <Card className="not-prose my-8">
      <Eyebrow>Every precinct, change in murder plus robbery plus felony assault, 1990 to 2025</Eyebrow>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full">
        {[-100, -75, -50, -25, 0].map((v) => <g key={v}><line x1={x(v)} x2={x(v)} y1={60} y2={baseY + 10} stroke={v === 0 ? "#3B3B3B" : "#E5E7EB"} /><text x={x(v)} y={baseY + 28} fontSize={11} textAnchor="middle" fontFamily="Source Sans 3" fill={STEEL}>{v > 0 ? "+" : ""}{v}%</text></g>)}
        <line x1={padL} x2={W - padR} y1={baseY + R + 1} y2={baseY + R + 1} stroke="#E5E7EB" />
        {labels.map((l) => <g key={`l${l.r.precinct}`} style={{ cursor: "pointer" }} onClick={() => setPicked(picked === l.r.precinct ? null : l.r.precinct)}><line x1={l.px} y1={l.py - R - 1} x2={l.lx} y2={l.ly + 6} stroke={l.r.precinct === 84 ? COBALT : "#9AA0A6"} strokeWidth={1} /><text x={l.lx} y={l.ly} fontSize={11} textAnchor="middle" fontFamily="Source Sans 3" fontWeight={l.r.precinct === 84 || l.r.precinct === picked ? 700 : 500} fill={l.r.precinct === 84 ? COBALT : "#3B3B3B"}>{place(l.r)}</text></g>)}
        {placed.map(({ r, px, py }) => {
          const isMe = r.precinct === 84; const isSel = r.precinct === picked;
          return <circle key={r.precinct} cx={px} cy={py} r={isSel ? R + 2 : R} fill={isMe ? COBALT : isSel ? "#002D38" : CAROLINA} opacity={isMe || isSel ? 1 : 0.7} stroke="#fff" strokeWidth={1} style={{ cursor: "pointer" }} onClick={() => setPicked(isSel ? null : r.precinct)}><title>{place(r)} ({ordinal(r.precinct)} Precinct), {Math.round(r.change_pct as number)}%</title></circle>;
        })}
        <text x={x(-86)} y={H - 6} fontSize={11} fontFamily="Source Sans 3" fill={STEEL}>most improved</text>
        <text x={x(-10)} y={H - 6} fontSize={11} textAnchor="end" fontFamily="Source Sans 3" fill={STEEL}>least improved</text>
      </svg>
      <div className="mt-1 min-h-[2.5rem] font-sans text-sm text-charcoal">
        {sel ? (
          <div className="flex flex-wrap items-baseline gap-x-2 rounded-md bg-vellum px-3 py-1.5">
            <span className="font-serif text-base font-bold text-cobalt">{place(sel)}</span>
            <span className="text-xs text-steel">{sel.borough}, {ordinal(sel.precinct)} Precinct</span>
            <span>{fmtInt(sel.violent_1990)} in 1990, {fmtInt(sel.violent_2025)} in 2025 ({Math.round(sel.change_pct as number)}%). Robbery {Math.round(sel.robbery_change_pct ?? 0)}%, felony assault {sel.fel_assault_change_pct != null && sel.fel_assault_change_pct > 0 ? "+" : ""}{Math.round(sel.fel_assault_change_pct ?? 0)}%, murders {sel.murder_1990} to {sel.murder_2025}.</span>
            <button className="text-xs font-semibold text-cobalt" onClick={() => setPicked(null)}>clear</button>
          </div>
        ) : <div className="px-1 text-xs text-steel">Click any dot for its precinct. Downtown Brooklyn is the blue one.</div>}
      </div>
      <div className="mt-2 font-sans text-xs text-steel">Murder, robbery and felony assault, NYPD CompStat historical tables. {rows.length} of {data.summary.length} precincts; the 33rd and 121st were created after 1990. Neighborhood names are approximate.</div>
    </Card>
  );
}
