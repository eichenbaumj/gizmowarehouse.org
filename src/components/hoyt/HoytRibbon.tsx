// Scene 7 (window="all"): stacked ribbon by class, 2006 to 2026, 2026 hatched as first half.
// Scene 12 (window="h1"): four small multiples, matched first-half bars, each with its own y scale.
import { useMemo, useState } from "react";
import { CLASS_ORDER, CLASS_STYLE, STEEL, type ClassKey, type RibbonFile } from "@/config/hoytSchermerhorn";
import { useHoytData, fmtInt } from "./hoytData";
import { Card, Eyebrow } from "./HoytChrome";

const STACK: ClassKey[] = ["street_robbery", "retail_robbery", "other_assault", "officer_assault"];

export function HoytRibbon({ window = "all", geo = "core400" }: { window?: "all" | "h1"; geo?: string }) {
  const { data } = useHoytData<RibbonFile>("ribbon");
  if (!data) return <Card className="not-prose my-8"><div className="h-64 animate-pulse rounded bg-vellum" /></Card>;
  return window === "h1" ? <H1Panels data={data} /> : <Stacked data={data} geo={geo} />;
}

function Stacked({ data, geo }: { data: RibbonFile; geo: string }) {
  const g = data.geos[geo];
  const years = g.years; const n = years.length;
  const W = 760; const H = 320; const padL = 44; const padR = 150; const padT = 12; const padB = 28;
  const [hover, setHover] = useState<number | null>(null);
  const stacks = useMemo(() => years.map((_, i) => { let acc = 0; return STACK.map((c) => { const v = g.by_class[c][i]; const out = [acc, acc + v] as [number, number]; acc += v; return out; }); }), [g]);
  const max = Math.max(...stacks.map((s) => s[s.length - 1][1]));
  const x = (i: number) => padL + (i / (n - 1)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - v / max) * (H - padT - padB);
  const pi = years.indexOf("2026");
  return (
    <Card className="not-prose my-8">
      <Eyebrow>Violent complaints within 400 m of the station, by year and type</Eyebrow>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" onMouseLeave={() => setHover(null)}>
        <defs><pattern id="hs-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="#fff" /><line x1="0" y1="0" x2="0" y2="6" stroke="#9aa0a6" strokeWidth="2" /></pattern></defs>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => <g key={f}><line x1={padL} x2={W - padR} y1={y(max * f)} y2={y(max * f)} stroke="#E5E7EB" /><text x={padL - 6} y={y(max * f) + 4} fontSize={11} textAnchor="end" fontFamily="Source Sans 3" fill={STEEL}>{Math.round(max * f)}</text></g>)}
        {STACK.map((c, k) => {
          const top = years.map((_, i) => `${x(i)},${y(stacks[i][k][1])}`).join(" L");
          const bottom = years.map((_, i) => `${x(i)},${y(stacks[i][k][0])}`).reverse().join(" L");
          return <path key={c} d={`M${top} L${bottom} Z`} fill={CLASS_STYLE[c].color} opacity={0.85} />;
        })}
        {pi >= 0 && <rect x={x(pi - 1)} y={padT} width={x(pi) - x(pi - 1)} height={H - padT - padB} fill="url(#hs-hatch)" opacity={0.55} />}
        {STACK.map((c, k) => { const i = n - 2; const mid = (stacks[i][k][0] + stacks[i][k][1]) / 2; return <text key={c} x={W - padR + 6} y={y(mid) + 4} fontSize={12} fontFamily="Source Sans 3" fill={CLASS_STYLE[c].color} fontWeight={600}>{CLASS_STYLE[c].short} {g.by_class[c][i]}</text>; })}
        {years.map((yr, i) => (i % 4 === 0 || i === n - 1) && <text key={yr} x={x(i)} y={H - 8} fontSize={11} textAnchor="middle" fontFamily="Source Sans 3" fill={STEEL}>{yr}{yr === "2026" ? " (Jan to Jun)" : ""}</text>)}
        {years.map((_, i) => <rect key={i} x={x(i) - (W - padL - padR) / (2 * n)} y={padT} width={(W - padL - padR) / n} height={H - padT - padB} fill="transparent" onMouseEnter={() => setHover(i)} />)}
        {hover != null && <g><line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} stroke="#3B3B3B" strokeDasharray="3 3" /><rect x={Math.min(x(hover) + 8, W - padR - 150)} y={padT} width={150} height={16 * (STACK.length + 1) + 8} fill="#fff" stroke="#E5E7EB" rx={6} /><text x={Math.min(x(hover) + 14, W - padR - 144)} y={padT + 14} fontSize={11} fontFamily="Source Sans 3" fill="#3B3B3B" fontWeight={700}>{years[hover]}{hover === pi ? " (first half)" : ""}: {g.all[hover]}</text>{STACK.map((c, k) => <text key={c} x={Math.min(x(hover) + 14, W - padR - 144)} y={padT + 14 + 16 * (k + 1)} fontSize={11} fontFamily="Source Sans 3" fill={CLASS_STYLE[c].color}>{CLASS_STYLE[c].short} {g.by_class[c][hover]}</text>)}</g>}
      </svg>
      <div className="mt-1 font-sans text-xs text-steel">Street robbery along the bottom. 2026 hatched: January through June only. Homicides (2 since 2006, both in 2020) are not drawn.</div>
    </Card>
  );
}

function H1Panels({ data }: { data: RibbonFile }) {
  const panels: { key: string; title: string }[] = [
    { key: "city", title: "Whole city" }, { key: "street_stores", title: "Sidewalk and stores, 400 m" }, { key: "street_robbery", title: "Street robbery, 400 m" }, { key: "courthouse", title: "The courthouse point" },
  ];
  const yrs = ["2024", "2025", "2026"];
  return (
    <Card className="not-prose my-8">
      <Eyebrow>January to June, complaints reported by June 30 of each year</Eyebrow>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {panels.map((p) => {
          const vals = yrs.map((y) => data.h1.panels[p.key]?.[y] ?? 0);
          const max = Math.max(1, ...vals);
          const up = vals[2] > Math.max(vals[0], vals[1]);
          return (
            <div key={p.key}>
              <div className="font-sans text-[12px] font-semibold text-charcoal">{p.title}</div>
              <svg viewBox="0 0 160 120" className="block w-full">
                {vals.map((v, i) => <g key={i}><rect x={14 + i * 48} y={100 - (v / max) * 84} width={36} height={(v / max) * 84} fill={i === 2 ? (up ? "#d55181" : "#2A2AE0") : "#C9CBD1"} rx={2} /><text x={32 + i * 48} y={100 - (v / max) * 84 - 4} fontSize={11} textAnchor="middle" fontFamily="Source Sans 3" fill="#3B3B3B">{fmtInt(v)}</text><text x={32 + i * 48} y={114} fontSize={10} textAnchor="middle" fontFamily="Source Sans 3" fill={STEEL}>{yrs[i]}</text></g>)}
              </svg>
            </div>
          );
        })}
      </div>
      <div className="mt-1 font-sans text-xs text-steel">Each panel has its own scale. Red marks the one series above both prior years.</div>
    </Card>
  );
}
