// SicVolatility — <sic-volatility></sic-volatility>
//
// What coverage buys: a steadier bill. Every New York government with a documented arrangement is one dot,
// placed by its costliest year in 2015 to 2024 as a multiple of its own ten-year average (1x = every year cost
// the same). Self-insured governments stack above each band's line, covered ones below.
//
// Built to be read in steps (Joe, 2026-10-10: the full stack was too busy). The "All governments" band and the
// Cities band show by default; Counties, Towns, and Villages sit underneath as collapsed rows that show their
// counts and typical values and open on a tap, one at a time or all together. Each band is its own small SVG on
// a shared x scale, so opening one never reflows the others. Thin groups print "only n" instead of a typical
// value and get a plain-words flag; a government with a negative year is counted, named in the note, and not
// drawn. Designed in a four-designer, three-judge workflow; the model lives in sicVolatilityModel.ts.

import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { ModelsData, NyEntitiesData } from "@/config/selfInsuranceCost";
import { useSicData, useIsNarrow, SicCard, Eyebrow, Sub, Loading, Err, fmtMoney, fmtPop, STEEL } from "./useSicData";
import {
  CLASS_NAME, MIN_TICK, SIDES, X_HI, X_LO, classOrder, countPhrase, fx, shortName, summarize, swarmOneSided, swingCopy,
  swingRows, thinFlag, type ClassKey, type Half, type Side, type SwingModelNumbers, type SwingRow,
} from "./sicVolatilityModel";

const COBALT = "#1F1FD6", CAROLINA = "#21A8E0", CHARCOAL = "#3B3B3B";
const MIDLINE = "#C9CCD3", TWICE = "#A3A7AE", GRID = "#E5E7EB";
const COLOR: Record<Side, string> = { self: COBALT, covered: CAROLINA };
const SIDE_LABEL: Record<Side, string> = { self: "carries its own liability", covered: "buys coverage from a pool or insurer" };
const DEFAULT_OPEN: ClassKey[] = ["city"];

type BandKey = "all" | ClassKey;

function geometry(narrow: boolean) {
  const W = narrow ? 300 : 680;
  const r = narrow ? 4 : 4.5;
  const colW = narrow ? 50 : 96;
  const overW = narrow ? 30 : 44;
  const x0 = narrow ? 8 : 10;
  const x1 = W - colW - overW;
  const gap = 3;
  return {
    W, r, colW, x0, x1, gap, d: 2 * r + 1.5, xOver: x1 + 14, tickLen: gap + 2 * r + 3,
    fs: narrow ? 12 : 12.5, fss: narrow ? 11 : 11.5,
    X: (v: number) => x0 + ((Math.min(Math.max(v, X_LO), X_HI) - X_LO) / (X_HI - X_LO)) * (x1 - x0),
  };
}
type Geo = ReturnType<typeof geometry>;

interface DotPos { row: SwingRow; x: number; y: number }

/** One band's body: dots (or summary bars), grid, ticks, and the margin values. y starts at 0. */
function bandLayout(key: BandKey, rows: SwingRow[], h: Record<Side, Half>, g: Geo) {
  const halves: Record<Side, { g: SwingRow[]; xs: number[]; offs: number[]; h: number }> = {
    self: { g: [], xs: [], offs: [], h: g.tickLen + 2 }, covered: { g: [], xs: [], offs: [], h: g.tickLen + 2 },
  };
  if (key !== "all") {
    for (const s of SIDES) {
      const grp = rows.filter((q) => q.cls === key && q.side === s).sort((a, b) => a.ratio - b.ratio);
      const xs = grp.map((q) => (q.ratio <= X_HI ? g.X(q.ratio) : g.xOver));
      const offs = swarmOneSided(xs, g.d);
      halves[s] = { g: grp, xs, offs, h: Math.max((offs.length ? Math.max(...offs) : 0) + g.gap + 2 * g.r + 2, g.tickLen + 2) };
    }
  }
  const top = 6;
  const mid = top + halves.self.h;
  const H = mid + halves.covered.h + 6;
  const dots: DotPos[] = [];
  const pins: { x: number; y: number; s: string }[] = [];
  const bars: { d: string; fill: string }[] = [];
  const ticks: { x: number; y2: number }[] = [];
  const margin: { y: number; s: string; strong: boolean; thin: boolean; side: Side }[] = [];
  for (const s of SIDES) {
    const sign = s === "self" ? -1 : 1;
    if (key === "all") {
      if (h[s].ratio != null) {
        const xe = g.X(h[s].ratio as number), bh = g.tickLen - 4, yb = s === "self" ? mid - 2 - bh : mid + 2, rr = 4;
        bars.push({ d: `M${g.X(1)},${yb} H${xe - rr} a${rr},${rr} 0 0 1 ${rr},${rr} V${yb + bh - rr} a${rr},${rr} 0 0 1 -${rr},${rr} H${g.X(1)} Z`, fill: COLOR[s] });
      }
    } else {
      const hv = halves[s];
      hv.g.forEach((q, i) => {
        const y = mid + sign * (g.gap + g.r + hv.offs[i]);
        dots.push({ row: q, x: hv.xs[i], y });
        if (q.ratio > X_HI) pins.push({ x: hv.xs[i], y: y + sign * (g.r + 6) + (sign > 0 ? 4 : 0), s: fx(q.ratio) });
      });
    }
    if (h[s].n >= MIN_TICK && h[s].ratio != null) ticks.push({ x: g.X(h[s].ratio as number), y2: mid + sign * g.tickLen });
    const thin = h[s].n < MIN_TICK || h[s].ratio == null;
    margin.push({ y: mid + sign * Math.max(g.gap + g.r, 8.5) + 4.5, s: thin ? `only ${h[s].n}` : fx(h[s].ratio as number), strong: key === "all", thin, side: s });
  }
  return { H, mid, top, dots, pins, bars, ticks, margin, lineEnd: key === "all" ? g.x1 : g.xOver + 8 };
}

function Band({ k, rows, h, g, narrow }: { k: BandKey; rows: SwingRow[]; h: Record<Side, Half>; g: Geo; narrow: boolean }) {
  const L = useMemo(() => bandLayout(k, rows, h, g), [k, rows, h, g]);
  const ref = useRef<SVGSVGElement>(null);
  const [active, setActive] = useState<number | null>(null);
  const [pinned, setPinned] = useState(false);
  const pick = (e: PointerEvent<SVGSVGElement>) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box || !L.dots.length) return null;
    const kx = g.W / box.width;
    const px = (e.clientX - box.left) * kx, py = (e.clientY - box.top) * kx;
    let best = -1, bd = Infinity;
    L.dots.forEach((dt, i) => { const dd = (dt.x - px) ** 2 + (dt.y - py) ** 2; if (dd < bd) { bd = dd; best = i; } });
    return best >= 0 && Math.sqrt(bd) <= 20 * kx ? best : null;
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === "Escape") { setActive(null); setPinned(false); return; }
    if (!["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(e.key) || !L.dots.length) return;
    e.preventDefault();
    const n = L.dots.length, step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1;
    setActive((a) => (a == null ? 0 : (a + step + n) % n));
    setPinned(true);
  };
  const hot = active != null ? L.dots[active] : null;
  const kx0 = g.W - g.colW + (narrow ? 8 : 22);
  return (
    <div className="relative">
      <svg
        ref={ref}
        viewBox={`0 0 ${g.W} ${L.H.toFixed(0)}`}
        className="w-full touch-manipulation focus:outline-none focus-visible:ring-2 focus-visible:ring-cobalt"
        style={{ overflow: "visible" }}
        fontFamily="'Source Sans 3', system-ui, sans-serif"
        role={k === "all" ? "img" : "group"}
        tabIndex={L.dots.length ? 0 : -1}
        aria-label={k === "all" ? "Typical worst year for all governments" : `${CLASS_NAME[k][0]}: one dot per government`}
        onPointerMove={(e) => e.pointerType === "mouse" && !pinned && setActive(pick(e))}
        onPointerLeave={() => !pinned && setActive(null)}
        onPointerDown={(e) => { const i = pick(e); if (i == null || (pinned && i === active)) { setActive(null); setPinned(false); } else { setActive(i); setPinned(true); } }}
        onKeyDown={onKey}
      >
        {[1, 2, 3, 4, 5].map((v) => (
          <line key={v} x1={g.X(v)} x2={g.X(v)} y1={L.top} y2={L.H - 6} stroke={v === 1 ? MIDLINE : v === 2 ? TWICE : GRID} strokeWidth={1} />
        ))}
        <line x1={g.X(1)} x2={L.lineEnd} y1={L.mid} y2={L.mid} stroke={MIDLINE} strokeWidth={1} />
        {L.bars.map((b, i) => <path key={i} d={b.d} fill={b.fill} />)}
        {L.dots.map((dt, i) => (
          <circle key={dt.row.muni} cx={dt.x} cy={dt.y} r={g.r} fill={COLOR[dt.row.side]} stroke={i === active ? CHARCOAL : "#fff"} strokeWidth={i === active ? 2 : 1.5} />
        ))}
        {L.ticks.map((t, i) => <line key={i} x1={t.x} x2={t.x} y1={L.mid} y2={t.y2} stroke={CHARCOAL} strokeWidth={2} />)}
        {L.pins.map((p, i) => (
          <text key={i} x={p.x} y={p.y} textAnchor="middle" fontSize={g.fss - 0.5} fill={STEEL} stroke="#fff" strokeWidth={3} paintOrder="stroke" style={{ fontVariantNumeric: "tabular-nums" }}>{p.s}</text>
        ))}
        {L.margin.map((m) => (
          <g key={m.side}>
            <circle cx={kx0} cy={m.y - 4.5} r={3} fill={COLOR[m.side]} />
            <text x={kx0 + 8} y={m.y} fontSize={m.thin ? g.fss : m.strong ? 13 : g.fs} fontWeight={m.thin ? 400 : m.strong ? 700 : 600} fill={m.thin ? STEEL : CHARCOAL} style={{ fontVariantNumeric: "tabular-nums" }}>{m.s}</text>
          </g>
        ))}
      </svg>
      {hot && (
        <div
          aria-live="polite"
          className="pointer-events-none absolute z-10 max-w-[250px] rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-md"
          style={{ top: `${(hot.y / L.H) * 100}%`, ...(hot.x / g.W > 0.55 ? { right: `${(1 - hot.x / g.W) * 100 + 3}%` } : { left: `${(hot.x / g.W) * 100 + 3}%` }) }}
        >
          <div className="font-semibold text-charcoal">{hot.row.name}</div>
          <div className="text-steel">{fmtPop(hot.row.pop)} residents · {SIDE_LABEL[hot.row.side]}</div>
          <div className="mt-1">Costliest year{hot.row.worstFy ? `, ${hot.row.worstFy}` : ""}: <b>{fmtMoney(hot.row.max)}</b> per resident</div>
          <div>Ten-year average: {fmtMoney(hot.row.mean)} per resident</div>
          <div>So its worst year ran {fx(hot.row.ratio)} its average.</div>
          {hot.row.budget != null && <div className="text-steel">That year's cost above average came to {(hot.row.budget * 100).toFixed(1)}% of a year's spending.</div>}
        </div>
      )}
    </div>
  );
}

function Counts({ k, h }: { k: BandKey; h: Record<Side, Half> }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs font-normal text-charcoal">
      {SIDES.map((s) => (
        <span key={s} className="inline-flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: COLOR[s] }} />
          {countPhrase(h[s].n, s)}
        </span>
      ))}
      {k !== "all" && <span className="sr-only">for {CLASS_NAME[k][2]}</span>}
    </span>
  );
}

export default function SicVolatility() {
  const { data, err } = useSicData<NyEntitiesData>("ny_entities");
  const { data: models, err: err2 } = useSicData<ModelsData>("models");
  const narrow = useIsNarrow();
  const [open, setOpen] = useState<Set<ClassKey>>(() => new Set(DEFAULT_OPEN));
  const g = useMemo(() => geometry(narrow), [narrow]);

  const model = useMemo(() => {
    if (!data) return null;
    const { drawn, leftOut } = swingRows(data.rows);
    const S = summarize(drawn);
    const order: ClassKey[] = [...DEFAULT_OPEN, ...classOrder(S).filter((c) => !DEFAULT_OPEN.includes(c))];
    return { drawn, leftOut, S, order };
  }, [data]);
  const copy = useMemo(() => {
    const v: SwingModelNumbers | undefined = models?.ny?.volatility;
    return model && v ? swingCopy(model.drawn, model.leftOut, v) : null;
  }, [model, models]);

  if (err || err2) return <Err msg={(err || err2) as string} />;
  if (!model || !copy) return <Loading h={narrow ? 640 : 520} />;
  const { drawn, leftOut, S, order } = model;
  const toggle = (c: ClassKey) => setOpen((o) => { const n = new Set(o); if (n.has(c)) n.delete(c); else n.add(c); return n; });
  const allOpen = order.every((c) => open.has(c));
  const openCount = order.filter((c) => open.has(c)).length;

  const Axis = (
    <svg viewBox={`0 0 ${g.W} 22`} className="w-full" style={{ overflow: "visible" }} aria-hidden fontFamily="'Source Sans 3', system-ui, sans-serif">
      {[1, 2, 3, 4, 5].map((v) => (
        <text key={v} x={g.X(v)} y={15} textAnchor="middle" fontSize={g.fs} fill={STEEL} style={{ fontVariantNumeric: "tabular-nums" }}>{v}×</text>
      ))}
      <text x={narrow ? g.W : g.W - g.colW + 18.5} y={15} textAnchor={narrow ? "end" : "start"} fontSize={g.fss} fill={STEEL}>{narrow ? "typical" : "typical worst"}</text>
    </svg>
  );

  return (
    <SicCard>
      <Eyebrow>New York, 2015 to 2024</Eyebrow>
      <h3 className="font-serif text-lg font-bold text-cobalt">Bad years hit harder when a government carries its own liability</h3>
      <Sub>{copy.sub}</Sub>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-charcoal">
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full" style={{ background: COBALT }} />Carries its own liability, above each line</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full" style={{ background: CAROLINA }} />Buys coverage, below</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-0.5" style={{ background: CHARCOAL }} />Typical government</span>
      </div>

      <div className="mt-4 text-xs text-steel">Costliest year, as a multiple of the government's own ten-year average</div>
      {Axis}

      <div className="mt-1">
        <div className="text-sm font-bold text-charcoal">All governments</div>
        <Counts k="all" h={S.all} />
        <Band k="all" rows={drawn} h={S.all} g={g} narrow={narrow} />
      </div>

      {order.map((c) => {
        const isOpen = open.has(c);
        const lo = leftOut.filter((q) => q.cls === c);
        const flag = thinFlag(c, S);
        const typ = (s: Side) => (S[c][s].n >= MIN_TICK && S[c][s].ratio != null ? fx(S[c][s].ratio as number) : `only ${S[c][s].n}`);
        return (
          <div key={c} className="mt-2 border-t border-slate-100 pt-1.5">
            <button
              type="button"
              onClick={() => toggle(c)}
              aria-expanded={isOpen}
              className="flex w-full items-start gap-2 rounded-md px-1 py-1 text-left hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-cobalt"
            >
              <span className={`mt-0.5 inline-block text-xs text-cobalt transition-transform ${isOpen ? "rotate-90" : ""}`} aria-hidden>▶</span>
              <span className="flex flex-1 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <span className="text-sm font-bold text-charcoal">{CLASS_NAME[c][0]}</span>
                  <Counts k={c} h={S[c]} />
                </span>
                {!isOpen && (
                  <span className="text-xs text-steel">
                    typical worst year <span style={{ color: COBALT }}>●</span> {typ("self")} · <span style={{ color: CAROLINA }}>●</span> {typ("covered")}
                    <span className="ml-2 font-semibold text-cobalt">Show</span>
                  </span>
                )}
                {isOpen && lo.length > 0 && <span className="text-xs italic text-steel">{lo.map((q) => shortName(q.name)).join(", ")} left out, see note</span>}
              </span>
            </button>
            {isOpen && (
              <>
                <Band k={c} rows={drawn} h={S[c]} g={g} narrow={narrow} />
                {flag && <div className="mt-0.5 text-xs italic text-steel">{flag}</div>}
              </>
            )}
          </div>
        );
      })}

      {openCount > 1 && <div className="mt-1">{Axis}</div>}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-steel">
        <span>1× would mean every year cost the same.</span>
        <button type="button" onClick={() => setOpen(allOpen ? new Set() : new Set(order))} className="font-semibold text-cobalt hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-cobalt">
          {allOpen ? "Close all types" : "Open all types to compare"}
        </button>
      </div>
      <p className="mt-3 text-xs text-steel">{copy.foot}</p>
    </SicCard>
  );
}
