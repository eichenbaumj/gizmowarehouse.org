// TimeSeriesChart — a hand-rolled SVG multi-series line chart, matching the
// repo's no-charting-library idiom (cf. MedicaidLossSankey). Responsive via a
// fixed viewBox; hover shows a vertical guide + a tooltip with every series'
// value at the nearest x. 17A palette by default (cobalt = public, carolina =
// private). No external deps.

import { useMemo, useRef, useState } from "react";

export interface Series {
  key: string;
  label: string;
  color: string;
  /** dashed line (e.g. for a projected or secondary series) */
  dash?: boolean;
  points: { x: number; y: number }[];
}

interface Props {
  series: Series[];
  /** y-axis value formatter (e.g. d => `$${d}`) */
  yFormat?: (v: number) => string;
  xFormat?: (v: number) => string;
  /** force a y domain; otherwise auto from data with padding */
  yDomain?: [number, number];
  yLabel?: string;
  height?: number;
  /** draw a dot at each data point */
  dots?: boolean;
  /** a y value at which to draw a reference line (e.g. 0 for a gap chart) */
  refY?: number;
  className?: string;
}

const VB_W = 720;
const M = { top: 16, right: 16, bottom: 34, left: 52 };

export default function TimeSeriesChart({
  series,
  yFormat = (v) => `${v}`,
  xFormat = (v) => `${v}`,
  yDomain,
  yLabel,
  height = 360,
  dots = true,
  refY,
  className,
}: Props) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [hoverX, setHoverX] = useState<number | null>(null);

  const plot = useMemo(() => {
    const allX = series.flatMap((s) => s.points.map((p) => p.x));
    const allY = series.flatMap((s) => s.points.map((p) => p.y));
    if (allX.length === 0) return null;
    const xMin = Math.min(...allX);
    const xMax = Math.max(...allX);
    let [yMin, yMax] = yDomain ?? [Math.min(...allY), Math.max(...allY)];
    if (refY !== undefined) {
      yMin = Math.min(yMin, refY);
      yMax = Math.max(yMax, refY);
    }
    if (!yDomain) {
      const pad = (yMax - yMin) * 0.08 || 1;
      yMin -= pad;
      yMax += pad;
    }
    const innerW = VB_W - M.left - M.right;
    const innerH = height - M.top - M.bottom;
    const sx = (x: number) =>
      M.left + (xMax === xMin ? innerW / 2 : ((x - xMin) / (xMax - xMin)) * innerW);
    const sy = (y: number) =>
      M.top + (yMax === yMin ? innerH / 2 : (1 - (y - yMin) / (yMax - yMin)) * innerH);
    return { xMin, xMax, yMin, yMax, sx, sy, innerW, innerH };
  }, [series, yDomain, refY, height]);

  const xValues = useMemo(
    () => Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.x)))).sort((a, b) => a - b),
    [series],
  );

  if (!plot) return null;

  // y ticks: 5 evenly spaced
  const yTicks = Array.from({ length: 5 }, (_, i) => plot.yMin + ((plot.yMax - plot.yMin) * i) / 4);

  const nearestX =
    hoverX === null
      ? null
      : xValues.reduce((best, x) =>
          Math.abs(plot.sx(x) - hoverX) < Math.abs(plot.sx(best) - hoverX) ? x : best,
        xValues[0]);

  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const xInVb = ((e.clientX - rect.left) / rect.width) * VB_W;
    setHoverX(xInVb);
  }

  const tooltipRows =
    nearestX === null
      ? []
      : series
          .map((s) => {
            const pt = s.points.find((p) => p.x === nearestX);
            return pt ? { label: s.label, color: s.color, y: pt.y } : null;
          })
          .filter(Boolean) as { label: string; color: string; y: number }[];

  // tooltip left position (% of container), flip if near right edge
  const tipLeftPct = nearestX !== null ? (plot.sx(nearestX) / VB_W) * 100 : 0;
  const flip = tipLeftPct > 62;

  return (
    <div ref={wrapRef} className={`relative w-full ${className ?? ""}`}>
      <svg
        viewBox={`0 0 ${VB_W} ${height}`}
        className="w-full"
        style={{ overflow: "visible" }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverX(null)}
        role="img"
      >
        {/* y gridlines + labels */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={M.left}
              x2={VB_W - M.right}
              y1={plot.sy(t)}
              y2={plot.sy(t)}
              stroke="#E5E7EB"
              strokeWidth={1}
            />
            <text
              x={M.left - 8}
              y={plot.sy(t) + 3}
              textAnchor="end"
              fontSize={11}
              fill="#6E6E6D"
              fontFamily="'Source Sans 3', sans-serif"
            >
              {yFormat(t)}
            </text>
          </g>
        ))}
        {yLabel && (
          <text
            x={14}
            y={M.top + plot.innerH / 2}
            textAnchor="middle"
            fontSize={11}
            fill="#6E6E6D"
            fontFamily="'Source Sans 3', sans-serif"
            transform={`rotate(-90 14 ${M.top + plot.innerH / 2})`}
          >
            {yLabel}
          </text>
        )}

        {/* x labels — thinned to ~10 max, always showing first & last */}
        {(() => {
          const step = Math.max(1, Math.ceil(xValues.length / 10));
          return xValues.filter(
            (_, i) => i % step === 0 || i === xValues.length - 1,
          );
        })().map((x) => (
          <text
            key={x}
            x={plot.sx(x)}
            y={height - 12}
            textAnchor="middle"
            fontSize={11}
            fill="#6E6E6D"
            fontFamily="'Source Sans 3', sans-serif"
          >
            {xFormat(x)}
          </text>
        ))}

        {/* reference line (e.g. y=0) */}
        {refY !== undefined && (
          <line
            x1={M.left}
            x2={VB_W - M.right}
            y1={plot.sy(refY)}
            y2={plot.sy(refY)}
            stroke="#9CA3AF"
            strokeWidth={1.25}
            strokeDasharray="4 3"
          />
        )}

        {/* hover guide */}
        {nearestX !== null && (
          <line
            x1={plot.sx(nearestX)}
            x2={plot.sx(nearestX)}
            y1={M.top}
            y2={height - M.bottom}
            stroke="#9CA3AF"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}

        {/* lines */}
        {series.map((s) => {
          const pts = [...s.points].sort((a, b) => a.x - b.x);
          const d = pts
            .map((p, i) => `${i === 0 ? "M" : "L"}${plot.sx(p.x).toFixed(1)},${plot.sy(p.y).toFixed(1)}`)
            .join(" ");
          return (
            <path
              key={s.key}
              d={d}
              fill="none"
              stroke={s.color}
              strokeWidth={2.5}
              strokeDasharray={s.dash ? "6 4" : undefined}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          );
        })}

        {/* dots */}
        {dots &&
          series.map((s) =>
            s.points.map((p) => (
              <circle
                key={`${s.key}-${p.x}`}
                cx={plot.sx(p.x)}
                cy={plot.sy(p.y)}
                r={nearestX === p.x ? 4 : 2.5}
                fill={s.color}
              />
            )),
          )}
      </svg>

      {/* tooltip */}
      {nearestX !== null && tooltipRows.length > 0 && (
        <div
          className="pointer-events-none absolute z-20 rounded-md border border-slate-200 bg-white/95 px-3 py-2 text-[12px] shadow-lg"
          style={{
            top: 6,
            left: `${flip ? tipLeftPct - 2 : tipLeftPct + 2}%`,
            transform: flip ? "translateX(-100%)" : "none",
            minWidth: 130,
          }}
        >
          <div className="mb-1 font-sans text-[11px] font-semibold text-charcoal">
            {xFormat(nearestX)}
          </div>
          {tooltipRows.map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-charcoal/80">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: r.color }}
                />
                {r.label}
              </span>
              <span className="font-mono font-semibold text-charcoal">{yFormat(r.y)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Shared legend row used by the embeds. */
export function ChartLegend({ items }: { items: { label: string; color: string; dash?: boolean }[] }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5 text-[12px] text-charcoal/80">
          <svg width="20" height="8" aria-hidden>
            <line
              x1="0"
              y1="4"
              x2="20"
              y2="4"
              stroke={it.color}
              strokeWidth="2.5"
              strokeDasharray={it.dash ? "5 3" : undefined}
            />
          </svg>
          {it.label}
        </span>
      ))}
    </div>
  );
}
