// SicVolatility — <sic-volatility></sic-volatility>
//
// What coverage buys: a steadier bill. Every New York government with a documented arrangement is one dot,
// placed by its costliest year in 2015 to 2024 as a multiple of its own ten-year average (1x = every year cost
// the same). Self-insured governments stack above each band's line, covered ones below. An "All governments"
// band leads with two bars to the typical worst year. Thin groups print "only n" instead of a typical value and
// get a plain-words flag; a government with a negative year is counted, named in the note, and not drawn.
// Designed from first principles on 2026-10-10 (4 designers, 3 judges); the model lives in sicVolatilityModel.ts.

import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { ModelsData, NyEntitiesData } from "@/config/selfInsuranceCost";
import { useSicData, useIsNarrow, SicCard, Eyebrow, Sub, Loading, Err, fmtMoney, fmtPop, STEEL } from "./useSicData";
import {
  CLASS_NAME, MIN_TICK, SIDES, X_HI, X_LO, classOrder, countPhrase, fx, shortName, summarize, swarmOneSided, swingCopy,
  swingRows, thinFlag, type ClassKey, type Side, type SwingModelNumbers, type SwingRow,
} from "./sicVolatilityModel";

const COBALT = "#1F1FD6", CAROLINA = "#21A8E0", CHARCOAL = "#3B3B3B";
const MIDLINE = "#C9CCD3", TWICE = "#A3A7AE", GRID = "#E5E7EB", SEP = "#EEF0F3";
const COLOR: Record<Side, string> = { self: COBALT, covered: CAROLINA };
const SIDE_LABEL: Record<Side, string> = { self: "carries its own liability", covered: "buys coverage from a pool or insurer" };

interface Dot { row: SwingRow; x: number; y: number; band: number }
interface Txt { x: number; y: number; s: string; size: number; fill: string; weight?: number; anchor?: "start" | "middle" | "end"; italic?: boolean; halo?: boolean; num?: boolean }
interface Ln { x1: number; x2: number; y1: number; y2: number; stroke: string; w: number }

function layout(rows: SwingRow[], narrow: boolean, leftOutByClass: Record<string, string[]>) {
  const S = summarize(rows);
  const W = narrow ? 300 : 680;
  const r = narrow ? 4 : 4.5;
  const d = 2 * r + 1.5;
  const gap = 3;
  const colW = narrow ? 50 : 96;
  const overW = narrow ? 30 : 44;
  const x0 = narrow ? 8 : 10;
  const x1 = W - colW - overW;
  const xOver = x1 + 14;
  const fs = narrow ? 12 : 12.5;
  const fss = narrow ? 11 : 11.5;
  const tickLen = gap + 2 * r + 3;
  const X = (v: number) => x0 + ((Math.min(Math.max(v, X_LO), X_HI) - X_LO) / (X_HI - X_LO)) * (x1 - x0);

  const lines: Ln[] = [], seps: Ln[] = [], txt: Txt[] = [], dots: Dot[] = [], bars: { d: string; fill: string }[] = [];
  const swatches: { x: number; y: number; r: number; fill: string }[] = [];
  const title = narrow ? ["Costliest year, as a multiple of the", "government's own ten-year average"] : ["Costliest year, as a multiple of the government's own ten-year average"];
  let y = 12;
  for (const t of title) { txt.push({ x: 0, y, s: t, size: fss, fill: STEEL }); y += 14; }
  const tickY = y + 4;
  for (let v = 1; v <= 5; v++) txt.push({ x: X(v), y: tickY, s: `${v}×`, size: fs, fill: STEEL, anchor: "middle", num: true });
  const [hx, ha] = narrow ? [W, "end" as const] : [W - colW + 18.5, "start" as const];
  txt.push({ x: hx, y: tickY - 14, s: "Typical", size: fss, fill: STEEL, anchor: ha });
  txt.push({ x: hx, y: tickY, s: "worst year", size: fss, fill: STEEL, anchor: ha });
  y = tickY + 8;

  const bands: ("all" | ClassKey)[] = ["all", ...classOrder(S)];
  bands.forEach((key, bi) => {
    const name = key === "all" ? "All governments" : CLASS_NAME[key][0];
    if (bi > 0) seps.push({ x1: 0, x2: W, y1: y, y2: y, stroke: SEP, w: 1 });
    const hy = y + 17;
    txt.push({ x: 0, y: hy, s: name, size: narrow ? 13 : 13.5, fill: CHARCOAL, weight: 700 });
    const lo = key === "all" ? [] : leftOutByClass[key] ?? [];
    if (lo.length) txt.push({ x: W, y: hy, s: `${lo.length === 1 ? lo[0] : lo.length} left out, see note`, size: fss, fill: STEEL, anchor: "end", italic: true });
    const cy = narrow ? hy + 16 : hy;
    let cx = narrow ? 0 : 128;
    for (const s of SIDES) {
      const label = countPhrase(S[key][s].n, s);
      swatches.push({ x: cx + 4, y: cy - 4, r: 3.5, fill: COLOR[s] });
      txt.push({ x: cx + 12, y: cy, s: label, size: fss, fill: CHARCOAL });
      cx += 12 + label.length * fss * 0.49 + 16;
    }
    y = cy + 10;

    const halves: Record<Side, { g: SwingRow[]; xs: number[]; offs: number[]; h: number }> = {
      self: { g: [], xs: [], offs: [], h: tickLen + 2 }, covered: { g: [], xs: [], offs: [], h: tickLen + 2 },
    };
    let flag: string[] = [];
    if (key !== "all") {
      for (const s of SIDES) {
        const g = rows.filter((q) => q.cls === key && q.side === s).sort((a, b) => a.ratio - b.ratio);
        const xs = g.map((q) => (q.ratio <= X_HI ? X(q.ratio) : xOver));
        const offs = swarmOneSided(xs, d);
        halves[s] = { g, xs, offs, h: Math.max((offs.length ? Math.max(...offs) : 0) + gap + 2 * r + 2, tickLen + 2) };
      }
      const f = thinFlag(key, S);
      if (f) {
        // wrap to the plot width
        const width = xOver + 8 - (x0 - r);
        let cur = "";
        for (const w of f.split(" ")) {
          const trial = (cur + " " + w).trim();
          if (cur && trial.length * fss * 0.47 > width) { flag.push(cur); cur = w; } else cur = trial;
        }
        if (cur) flag.push(cur);
      }
    }
    const mid = y + halves.self.h;
    const top = y, bottom = mid + halves.covered.h;
    for (let v = 1; v <= 5; v++) lines.push({ x1: X(v), x2: X(v), y1: top, y2: bottom, stroke: v === 1 ? MIDLINE : v === 2 ? TWICE : GRID, w: 1 });
    lines.push({ x1: X(1), x2: key === "all" ? x1 : xOver + 8, y1: mid, y2: mid, stroke: MIDLINE, w: 1 });

    for (const s of SIDES) {
      const sign = s === "self" ? -1 : 1;
      const h = S[key][s];
      if (key === "all") {
        if (h.ratio != null) {
          const xe = X(h.ratio), bh = tickLen - 4, yb = s === "self" ? mid - 2 - bh : mid + 2, rr = 4;
          bars.push({ d: `M${X(1)},${yb} H${xe - rr} a${rr},${rr} 0 0 1 ${rr},${rr} V${yb + bh - rr} a${rr},${rr} 0 0 1 -${rr},${rr} H${X(1)} Z`, fill: COLOR[s] });
        }
      } else {
        const hv = halves[s];
        hv.g.forEach((q, i) => {
          const yy = mid + sign * (gap + r + hv.offs[i]);
          dots.push({ row: q, x: hv.xs[i], y: yy, band: bi });
          if (q.ratio > X_HI) txt.push({ x: hv.xs[i], y: yy + sign * (r + 6) + (sign > 0 ? 4 : 0), s: fx(q.ratio), size: fss - 0.5, fill: STEEL, anchor: "middle", halo: true, num: true });
        });
      }
      if (h.n >= MIN_TICK && h.ratio != null) {
        const xt = X(h.ratio);
        lines.push({ x1: xt, x2: xt, y1: mid, y2: mid + sign * tickLen, stroke: CHARCOAL, w: 2 });
      }
      const ty = mid + sign * Math.max(gap + r, 8.5) + 4.5;
      const kx = W - colW + (narrow ? 8 : 22);
      swatches.push({ x: kx, y: ty - 4.5, r: 3, fill: COLOR[s] });
      if (h.n >= MIN_TICK && h.ratio != null) txt.push({ x: kx + 8, y: ty, s: fx(h.ratio), size: key === "all" ? 13 : fs, fill: CHARCOAL, weight: key === "all" ? 700 : 600, num: true });
      else txt.push({ x: kx + 8, y: ty, s: `only ${h.n}`, size: fss, fill: STEEL });
    }
    flag.forEach((ln, i) => txt.push({ x: x0 - r, y: bottom + 14 + 13.5 * i, s: ln, size: fss, fill: STEEL, italic: true }));
    y = bottom + (flag.length ? 10 + 13.5 * flag.length : 8);
  });
  y += 10;
  for (let v = 1; v <= 5; v++) txt.push({ x: X(v), y, s: `${v}×`, size: fs, fill: STEEL, anchor: "middle", num: true });
  y += 17;
  txt.push({ x: 0, y, s: "1× would mean every year cost the same.", size: fss, fill: STEEL });
  return { W, H: y + 6, r, lines, seps, txt, dots, bars, swatches, S };
}

export default function SicVolatility() {
  const { data, err } = useSicData<NyEntitiesData>("ny_entities");
  const { data: models, err: err2 } = useSicData<ModelsData>("models");
  const narrow = useIsNarrow();
  const [active, setActive] = useState<number | null>(null);
  const [pinned, setPinned] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);

  const model = useMemo(() => {
    if (!data) return null;
    const { drawn, leftOut } = swingRows(data.rows);
    const byClass: Record<string, string[]> = {};
    for (const q of leftOut) (byClass[q.cls] ??= []).push(shortName(q.name));
    return { drawn, leftOut, byClass };
  }, [data]);
  const L = useMemo(() => (model ? layout(model.drawn, narrow, model.byClass) : null), [model, narrow]);
  const copy = useMemo(() => {
    const v: SwingModelNumbers | undefined = models?.ny?.volatility;
    return model && v ? swingCopy(model.drawn, model.leftOut, v) : null;
  }, [model, models]);

  if (err || err2) return <Err msg={(err || err2) as string} />;
  if (!L || !copy || !model) return <Loading h={narrow ? 1100 : 760} />;

  const pick = (e: PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return null;
    const box = svg.getBoundingClientRect();
    const k = L.W / box.width;
    const px = (e.clientX - box.left) * k, py = (e.clientY - box.top) * k;
    let best = -1, bd = Infinity;
    L.dots.forEach((dt, i) => { const dd = (dt.x - px) ** 2 + (dt.y - py) ** 2; if (dd < bd) { bd = dd; best = i; } });
    return best >= 0 && Math.sqrt(bd) <= 20 * k ? best : null;
  };
  const onMove = (e: PointerEvent<SVGSVGElement>) => { if (e.pointerType === "mouse" && !pinned) setActive(pick(e)); };
  const onDown = (e: PointerEvent<SVGSVGElement>) => {
    const i = pick(e);
    if (i == null || (pinned && i === active)) { setActive(null); setPinned(false); } else { setActive(i); setPinned(true); }
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === "Escape") { setActive(null); setPinned(false); return; }
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft" && e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const n = L.dots.length;
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1;
    setActive((a) => (a == null ? 0 : (a + step + n) % n));
    setPinned(true);
  };
  const hot = active != null ? L.dots[active] : null;
  const a = L.S.all;

  return (
    <SicCard>
      <Eyebrow>New York, 2015 to 2024</Eyebrow>
      <h3 className="font-serif text-lg font-bold text-cobalt">Bad years hit harder when a government carries its own liability</h3>
      <Sub>{copy.sub}</Sub>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-charcoal">
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full" style={{ background: COBALT }} />Carries its own liability, above each line</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full" style={{ background: CAROLINA }} />Buys coverage from a pool or insurer, below</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-0.5" style={{ background: CHARCOAL }} />Typical government (the middle one of its group)</span>
      </div>
      <div className="relative mt-3">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${L.W} ${L.H.toFixed(0)}`}
          className="w-full touch-manipulation focus:outline-none focus-visible:ring-2 focus-visible:ring-cobalt"
          style={{ overflow: "visible" }}
          role="img"
          tabIndex={0}
          aria-label={`Dot chart of ${model.drawn.length} New York governments by costliest year as a multiple of their own ten-year average. Typical worst year: ${fx(a.self.ratio ?? 0)} for those that carry their own liability, ${fx(a.covered.ratio ?? 0)} for those that buy coverage.`}
          fontFamily="'Source Sans 3', system-ui, sans-serif"
          onPointerMove={onMove}
          onPointerLeave={() => !pinned && setActive(null)}
          onPointerDown={onDown}
          onKeyDown={onKey}
        >
          {L.seps.map((l, i) => <line key={`s${i}`} x1={l.x1} x2={l.x2} y1={l.y1} y2={l.y2} stroke={l.stroke} strokeWidth={l.w} />)}
          {L.lines.filter((l) => l.stroke !== CHARCOAL).map((l, i) => <line key={`g${i}`} x1={l.x1} x2={l.x2} y1={l.y1} y2={l.y2} stroke={l.stroke} strokeWidth={l.w} />)}
          {L.bars.map((b, i) => <path key={`b${i}`} d={b.d} fill={b.fill} />)}
          {L.swatches.map((c, i) => <circle key={`w${i}`} cx={c.x} cy={c.y} r={c.r} fill={c.fill} />)}
          {L.dots.map((dt, i) => (
            <circle key={dt.row.muni} cx={dt.x} cy={dt.y} r={L.r} fill={COLOR[dt.row.side]} stroke={i === active ? CHARCOAL : "#fff"} strokeWidth={i === active ? 2 : 1.5} />
          ))}
          {L.lines.filter((l) => l.stroke === CHARCOAL).map((l, i) => <line key={`t${i}`} x1={l.x1} x2={l.x2} y1={l.y1} y2={l.y2} stroke={l.stroke} strokeWidth={l.w} />)}
          {L.txt.map((t, i) => (
            <text key={`x${i}`} x={t.x} y={t.y} fontSize={t.size} fill={t.fill} fontWeight={t.weight} textAnchor={t.anchor} fontStyle={t.italic ? "italic" : undefined}
              stroke={t.halo ? "#fff" : undefined} strokeWidth={t.halo ? 3 : undefined} paintOrder={t.halo ? "stroke" : undefined} style={t.num ? { fontVariantNumeric: "tabular-nums" } : undefined}>
              {t.s}
            </text>
          ))}
        </svg>
        {hot && (
          <div
            aria-live="polite"
            className="pointer-events-none absolute max-w-[250px] rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-md"
            style={{ top: `${(hot.y / L.H) * 100}%`, ...(hot.x / L.W > 0.55 ? { right: `${(1 - hot.x / L.W) * 100 + 3}%` } : { left: `${(hot.x / L.W) * 100 + 3}%` }) }}
          >
            <div className="font-semibold text-charcoal">{hot.row.name}</div>
            <div className="text-steel">{CLASS_NAME[hot.row.cls][1]} · {fmtPop(hot.row.pop)} residents · {SIDE_LABEL[hot.row.side]}</div>
            <div className="mt-1">Costliest year{hot.row.worstFy ? `, ${hot.row.worstFy}` : ""}: <b>{fmtMoney(hot.row.max)}</b> per resident</div>
            <div>Ten-year average: {fmtMoney(hot.row.mean)} per resident</div>
            <div>So its worst year ran {fx(hot.row.ratio)} its average.</div>
            <div>In a typical year its bill landed about {Math.round(hot.row.swing * 100)}% above or below that average.</div>
            {hot.row.budget != null && <div className="text-steel">The worst year's cost above average came to {(hot.row.budget * 100).toFixed(1)}% of a year's spending.</div>}
          </div>
        )}
      </div>
      <p className="mt-2 text-xs text-steel">{copy.foot}</p>
    </SicCard>
  );
}
