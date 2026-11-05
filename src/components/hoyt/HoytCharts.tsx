// Non-sticky charts: hour bars (block vs city), the precinct 1990-to-2025 dot strip, the place-to-type
// Sankey, and the plain twenty-year lines.
import { useMemo, useState } from "react";
import { CLASS_STYLE, GHOST, STEEL, type ClassKey, type ClockFile, type RibbonFile, type SankeyFile } from "@/config/hoytSchermerhorn";
import { useHoytData, fmtInt } from "./hoytData";
import { Card, Eyebrow } from "./HoytChrome";
import { HoytHourStrip } from "./HoytStrips";

export function HoytHourBars() {
  const { data } = useHoytData<ClockFile>("clock");
  if (!data) return <Card className="not-prose my-8"><div className="h-40 animate-pulse rounded bg-vellum" /></Card>;
  const night = data.night as Record<string, { share: number; ci: [number, number] }>;
  const share = (w: number[][]) => { const tot = w.flat().reduce((a, b) => a + b, 0); const wk = w.slice(0, 5).flat().reduce((a, b) => a + b, 0); return Math.round((wk / tot) * 100); };
  const weekday = { block: share(data.week.core400), city: share(data.week.city) };
  return (
    <Card className="not-prose my-8">
      <Eyebrow>Share of violent complaints by hour: this block (blue bars) against the whole city (outlined)</Eyebrow>
      <HoytHourStrip hist={data.hour_share.core400_clean.map((x) => x * 1000)} ghost={data.hour_share.city_clean.map((x) => x * 1000)} height={110} />
      <div className="mt-2 grid grid-cols-1 gap-2 font-sans sm:grid-cols-2 sm:gap-4">
        <div><span className="font-serif text-2xl font-bold text-cobalt">{Math.round(night.core400.share * 100)}%</span> <span className="text-xs text-steel">of this block's complaints fall between 10pm and 6am (range {Math.round(night.core400.ci[0] * 100)} to {Math.round(night.core400.ci[1] * 100)})</span></div>
        <div><span className="font-serif text-2xl font-bold" style={{ color: STEEL }}>{Math.round(night.city.share * 100)}%</span> <span className="text-xs text-steel">of the city's do</span></div>
        <div><span className="font-serif text-2xl font-bold text-cobalt">{weekday.block}%</span> <span className="text-xs text-steel">of this block's fall Monday to Friday</span></div>
        <div><span className="font-serif text-2xl font-bold" style={{ color: STEEL }}>{weekday.city}%</span> <span className="text-xs text-steel">of the city's do (five of seven days would be 71%)</span></div>
      </div>
      <div className="mt-1 font-sans text-xs text-steel">2006 to mid-2026. Placeholder times (midnight, noon) excluded.</div>
    </Card>
  );
}

const COURT_RE = /court and booking/i;

export function HoytSankey() {
  const { data: raw } = useHoytData<SankeyFile>("sankey");
  // The courthouse row is off by default: it is a count the block carries, not something the block feels.
  const [withCourt, setWithCourt] = useState(false);
  const data = useMemo(() => {
    if (!raw) return null;
    if (withCourt) return raw;
    const flows = raw.flows.filter((f) => !COURT_RE.test(f.place));
    const places = raw.places.filter((p) => !COURT_RE.test(p.name));
    const byCls = new Map<string, number>(); for (const f of flows) byCls.set(f.cls, (byCls.get(f.cls) ?? 0) + f.n);
    const classes = raw.classes.map((c) => ({ ...c, n: byCls.get(c.name) ?? 0 })).filter((c) => c.n > 0);
    return { ...raw, flows, places, classes, total: flows.reduce((a, f) => a + f.n, 0) };
  }, [raw, withCourt]);
  const courtN = raw?.places.find((p) => COURT_RE.test(p.name))?.n ?? 0;
  const { data: ctx } = useHoytData<any>("context");
  const layout = useMemo(() => {
    if (!data) return null;
    const W = 760; const H = 360; const padT = 10; const gap = 8; const colW = 14; const left = 230; const right = W - 170;
    const total = data.total;
    const scale = (H - padT * 2 - gap * (data.places.length - 1)) / total;
    const L: Record<string, { y0: number; y1: number }> = {}; let y = padT;
    for (const p of data.places) { L[p.name] = { y0: y, y1: y + p.n * scale }; y += p.n * scale + gap; }
    const scaleR = (H - padT * 2 - gap * (data.classes.length - 1)) / total;
    const R: Record<string, { y0: number; y1: number }> = {}; y = padT;
    for (const c of data.classes) { R[c.name] = { y0: y, y1: y + c.n * scaleR }; y += c.n * scaleR + gap; }
    const lOff: Record<string, number> = {}; const rOff: Record<string, number> = {};
    const bands = [];
    const flows = [...data.flows].sort((a, b) => data.places.findIndex((p) => p.name === a.place) - data.places.findIndex((p) => p.name === b.place) || data.classes.findIndex((c) => c.name === a.cls) - data.classes.findIndex((c) => c.name === b.cls));
    for (const f of flows) {
      if (!L[f.place] || !R[f.cls]) continue;
      const ly0 = L[f.place].y0 + (lOff[f.place] ?? 0); const lh = f.n * scale; lOff[f.place] = (lOff[f.place] ?? 0) + lh;
      const ry0 = R[f.cls].y0 + (rOff[f.cls] ?? 0); const rh = f.n * scaleR; rOff[f.cls] = (rOff[f.cls] ?? 0) + rh;
      const x0 = left + colW, x1 = right; const cx = (x0 + x1) / 2;
      const d = `M${x0},${ly0} C${cx},${ly0} ${cx},${ry0} ${x1},${ry0} L${x1},${ry0 + rh} C${cx},${ry0 + rh} ${cx},${ly0 + lh} ${x0},${ly0 + lh} Z`;
      bands.push({ d, color: CLASS_STYLE[f.cls as ClassKey]?.color ?? GHOST, n: f.n, key: `${f.place}-${f.cls}` });
    }
    return { W, H, L, R, bands, left, right, colW };
  }, [data]);
  if (!data || !layout) return <Card className="not-prose my-8"><div className="h-64 animate-pulse rounded bg-vellum" /></Card>;
  return (
    <Card className="not-prose my-8">
      <Eyebrow>Where the {fmtInt(data.total)} violent complaints of 2024 to 2025 were recorded, and what they were{withCourt ? "" : " (courthouse left out)"}</Eyebrow>
      <svg viewBox={`0 0 ${layout.W} ${layout.H}`} className="block w-full">
        {layout.bands.map((b) => <path key={b.key} d={b.d} fill={b.color} opacity={0.55} />)}
        {data.places.map((p) => {
          const s = layout.L[p.name]; const mid = (s.y0 + s.y1) / 2; const isCourt = COURT_RE.test(p.name);
          const two = p.name.length > 22 ? [p.name.slice(0, p.name.lastIndexOf(" (") > 0 ? p.name.lastIndexOf(" (") : p.name.lastIndexOf(" ")), p.name.slice(p.name.lastIndexOf(" (") > 0 ? p.name.lastIndexOf(" (") + 1 : p.name.lastIndexOf(" ") + 1)] : [p.name];
          return <g key={p.name} style={isCourt ? { cursor: "pointer" } : undefined} onClick={isCourt ? () => setWithCourt(false) : undefined}><rect x={layout.left} y={s.y0} width={layout.colW} height={Math.max(1, s.y1 - s.y0)} fill="#3B3B3B" />
            {two.map((line, i) => <text key={i} x={layout.left - 6} y={mid + (two.length === 2 ? (i === 0 ? -3 : 11) : 4)} fontSize={12} textAnchor="end" fontFamily="Source Sans 3" fill="#3B3B3B">{line}{i === two.length - 1 && <> <tspan fill={STEEL}>{p.n}</tspan></>}</text>)}
            {isCourt && <title>Click to leave the courthouse out again</title>}
          </g>; })}
        {data.classes.map((c) => { const s = layout.R[c.name]; const st = CLASS_STYLE[c.name as ClassKey]; return <g key={c.name}><rect x={layout.right} y={s.y0} width={layout.colW} height={Math.max(1, s.y1 - s.y0)} fill={st?.color ?? GHOST} /><text x={layout.right + layout.colW + 6} y={(s.y0 + s.y1) / 2 + 4} fontSize={12} fontFamily="Source Sans 3" fill={st?.color ?? STEEL} fontWeight={600}>{st?.short ?? c.name} <tspan fill={STEEL} fontWeight={400}>{c.n}</tspan></text></g>; })}
      </svg>
      {ctx?.cell?.rank_no_courthouse && (
        <div className="mt-2 font-sans text-sm text-charcoal">
          {withCourt ? <>With the courthouse, the cell ranks <b>#{ctx.cell.rank_all}</b> of {fmtInt(ctx.cell.n_cells)} citywide.</> : <>Even without the courthouse's {fmtInt(courtN)}, the cell would still rank <b>#{ctx.cell.rank_no_courthouse}</b> of {fmtInt(ctx.cell.n_cells)} citywide, in the top one percent.</>}
        </div>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-sans text-xs text-steel">
        <button type="button" className="rounded-full border border-slate-300 px-3 py-1 font-semibold text-cobalt hover:bg-vellum" onClick={() => setWithCourt((v) => !v)}>
          {withCourt ? `Leave out 120 Schermerhorn (${fmtInt(courtN)})` : `Add 120 Schermerhorn, court and booking (+${fmtInt(courtN)})`}
        </button>
        <span>Within 400 m of the station. "Place" is NYPD's premise field plus the courthouse point and the station footprints. Homicides (2) are not drawn.</span>
      </div>
    </Card>
  );
}

export function HoytLines() {
  const { data } = useHoytData<RibbonFile>("ribbon");
  if (!data) return <Card className="not-prose my-8"><div className="h-56 animate-pulse rounded bg-vellum" /></Card>;
  const g = data.geos.core400; const ex = data.geos.core400_ex_courthouse;
  // Full years only. A half-year point on a yearly line reads as a collapse, so the partial year is reported as a
  // like-for-like first-half comparison under the chart instead.
  const partial = new Set(Object.entries(g.partial ?? {}).filter(([, v]) => v).map(([k]) => k));
  const keep = g.years.map((yr, i) => (partial.has(yr) ? -1 : i)).filter((i) => i >= 0);
  const years = keep.map((i) => g.years[i]); const n = years.length;
  const pick = (v: number[]) => keep.map((i) => v[i]);
  const W = 760; const H = 260; const padL = 44; const padR = 130; const padT = 12; const padB = 28;
  const series: { key: string; label: string; color: string; vals: number[] }[] = [
    // The courthouse point is set aside (the rank ladder above covers it); what is left, and its three parts.
    { key: "all", label: "All violent", color: "#3B3B3B", vals: pick(ex.all) },
    { key: "fa", label: CLASS_STYLE.other_assault.short, color: CLASS_STYLE.other_assault.color, vals: pick(ex.by_class.other_assault) },
    { key: "rr", label: CLASS_STYLE.retail_robbery.short, color: CLASS_STYLE.retail_robbery.color, vals: pick(ex.by_class.retail_robbery) },
    { key: "sr", label: CLASS_STYLE.street_robbery.short, color: CLASS_STYLE.street_robbery.color, vals: pick(ex.by_class.street_robbery) },
  ];
  const max = Math.max(...series.flatMap((s) => s.vals));
  const x = (i: number) => padL + (i / (n - 1)) * (W - padL - padR); const y = (v: number) => padT + (1 - v / max) * (H - padT - padB);
  // end labels sit at the last year; nudge apart so close lines keep readable labels
  const labelY: Record<string, number> = {};
  [...series].sort((a, b) => y(a.vals[n - 1]) - y(b.vals[n - 1])).forEach((s, i, arr) => {
    const want = y(s.vals[n - 1]); const prev = i ? labelY[arr[i - 1].key] : -Infinity;
    labelY[s.key] = Math.max(want, prev + 15);
  });
  // first half of each year, same reporting cutoff (by June 30), courthouse point excluded
  const h1 = data.h1?.panels; const h1Years = h1 ? Object.keys(h1.core400).sort() : [];
  const h1Ex = (yr: string) => h1!.core400[yr] - h1!.courthouse[yr];
  return (
    <Card className="not-prose my-8">
      <Eyebrow>Violent complaints per year within 400 m of the station, courthouse point excluded</Eyebrow>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full">
        {[0, 0.5, 1].map((f) => <g key={f}><line x1={padL} x2={W - padR} y1={y(max * f)} y2={y(max * f)} stroke="#E5E7EB" /><text x={padL - 6} y={y(max * f) + 4} fontSize={11} textAnchor="end" fontFamily="Source Sans 3" fill={STEEL}>{Math.round(max * f)}</text></g>)}
        {series.map((s) => <g key={s.key}><path d={s.vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ")} fill="none" stroke={s.color} strokeWidth={s.key === "all" ? 2.5 : 2} /><text x={W - padR + 6} y={labelY[s.key] + 4} fontSize={12} fontFamily="Source Sans 3" fill={s.color} fontWeight={600}>{s.label}</text></g>)}
        {years.map((yr, i) => (i % 4 === 0 || i === n - 1) && <text key={yr} x={x(i)} y={H - 8} fontSize={11} textAnchor="middle" fontFamily="Source Sans 3" fill={STEEL}>{yr}</text>)}
      </svg>
      {h1Years.length >= 2 && (
        <div className="font-sans text-xs text-steel">
          Full years through {years[n - 1]}. For 2026 only January through June is available. Counting the same months each year, the total without the courthouse point was{" "}
          {h1Years.map((yr, i) => <span key={yr}>{fmtInt(h1Ex(yr))} in {yr}{i < h1Years.length - 2 ? ", " : i === h1Years.length - 2 ? " and " : "."}</span>)}
        </div>
      )}
    </Card>
  );
}
