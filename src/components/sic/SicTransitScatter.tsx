// SicTransitScatter — <sic-transit-scatter></sic-transit-scatter>
//
// The national picture for transit: every directly operated full reporter in the National Transit
// Database, placed by revenue miles (x, log) and casualty-and-liability share of operating cost (y),
// colored by the structure read from its audited statements for the largest agencies and gray for the
// rest. Descriptive: the biggest agencies nearly all carry their own liability, so size and structure
// cannot be separated across states. Hand-rolled SVG per the repo idiom.

import { useMemo, useState } from "react";
import { STRUCTURE_STYLE, type NtdAgenciesData, type NtdAgencyRow } from "@/config/selfInsuranceCost";
import { useSicData, useIsNarrow, SicCard, Eyebrow, Sub, Loading, Err, fmtMoney, STEEL, GRID } from "./useSicData";

const M = { top: 18, right: 18, bottom: 40, left: 50 };
const SELF = new Set(["self_insured", "self_insured_with_excess"]);
const COVERED = new Set(["pool", "commercial"]);

export default function SicTransitScatter() {
  const { data, err } = useSicData<NtdAgenciesData>("ntd_agencies");
  const narrow = useIsNarrow();
  const [hover, setHover] = useState<NtdAgencyRow | null>(null);
  const VB_W = narrow ? 420 : 720, H = narrow ? 340 : 380;

  const rows = useMemo(() => (data ? data.rows.filter((r) => r.vrm > 0 && r.cl_share != null && r.cl_share >= 0) : []), [data]);
  const plot = useMemo(() => {
    if (!rows.length) return null;
    const xs = rows.map((r) => Math.log10(r.vrm));
    const xMin = Math.floor(Math.min(...xs)), xMax = Math.ceil(Math.max(...xs));
    const ys = [...rows.map((r) => r.cl_share)].sort((a, b) => a - b);
    const yMax = Math.min(0.15, Math.ceil(ys[Math.floor(ys.length * 0.97)] * 1.1 * 100) / 100);
    const innerW = VB_W - M.left - M.right, innerH = H - M.top - M.bottom;
    return { xMin, xMax, yMax, innerW, innerH,
      sx: (x: number) => M.left + ((x - xMin) / (xMax - xMin)) * innerW,
      sy: (y: number) => M.top + (1 - Math.min(y, yMax) / yMax) * innerH };
  }, [rows, VB_W, H]);

  if (err) return <Err msg={err} />;
  if (!data || !plot) return <Loading h={H} />;
  const kind = (r: NtdAgencyRow) => (r.label_source !== "document" ? "unknown" : SELF.has(r.structure) ? "self" : COVERED.has(r.structure) ? "covered" : "other");
  const yTicks = Array.from({ length: 4 }, (_, i) => (plot.yMax * i) / 3);
  const xTicks = [6, 7, 8, 9].filter((t) => t >= plot.xMin && t <= plot.xMax);
  const nLab = rows.filter((r) => r.label_source === "document").length;

  return (
    <SicCard>
      <Eyebrow>United States, {data.years[0]} to {data.years[data.years.length - 1]}</Eyebrow>
      <h3 className="font-serif text-lg font-bold text-cobalt">Transit agencies' casualty and liability cost as a share of operating cost</h3>
      <Sub>National Transit Database, directly operated service; structure read from audited statements for the largest agencies.</Sub>
      <div className="relative">
        <svg viewBox={`0 0 ${VB_W} ${H}`} className="w-full" style={{ overflow: "visible" }} role="img"
          aria-label="Scatter of transit agencies by revenue miles and casualty-and-liability share of operating cost">
          {yTicks.map((t, i) => (
            <g key={i}>
              <line x1={M.left} x2={VB_W - M.right} y1={plot.sy(t)} y2={plot.sy(t)} stroke={GRID} />
              <text x={M.left - 8} y={plot.sy(t) + 3} textAnchor="end" fontSize={narrow ? 12 : 11} fill={STEEL} fontFamily="'Source Sans 3', sans-serif">{(t * 100).toFixed(0)}%</text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={t} x={plot.sx(t)} y={H - M.bottom + 16} textAnchor="middle" fontSize={narrow ? 12 : 11} fill={STEEL} fontFamily="'Source Sans 3', sans-serif">
              {t === 6 ? "1M" : t === 7 ? "10M" : t === 8 ? "100M" : "1B"}
            </text>
          ))}
          <text x={M.left + plot.innerW / 2} y={H - 4} textAnchor="middle" fontSize={11} fill={STEEL} fontFamily="'Source Sans 3', sans-serif">vehicle revenue miles per year (log scale)</text>
          {[...rows].sort((a, b) => (kind(a) === "unknown" ? -1 : 1) - (kind(b) === "unknown" ? -1 : 1)).map((r) => {
            const k = kind(r);
            const color = k === "self" ? STRUCTURE_STYLE.self.color : k === "covered" ? STRUCTURE_STYLE.covered.color : STRUCTURE_STYLE.other.color;
            const isH = hover?.ntd_id === r.ntd_id;
            return (
              <circle key={r.ntd_id} cx={plot.sx(Math.log10(r.vrm))} cy={plot.sy(r.cl_share)} r={k === "unknown" ? 3.5 : isH ? 7 : 5.5}
                fill={k === "unknown" ? "#fff" : color} stroke={k === "unknown" ? STRUCTURE_STYLE.other.color : "#fff"} strokeWidth={isH ? 2.5 : 1.2}
                opacity={k === "unknown" ? 0.9 : 0.85} style={{ cursor: "pointer" }}
                onMouseEnter={() => setHover(r)} onMouseLeave={() => setHover(null)} onClick={() => setHover(isH ? null : r)} />
            );
          })}
        </svg>
        {hover && (
          <div className="pointer-events-none absolute left-2 top-2 max-w-[280px] rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-md">
            <div className="font-semibold text-charcoal">{hover.agency}</div>
            <div className="text-steel">{hover.city}, {hover.state} · {hover.label_source === "document" ? hover.structure.replace(/_/g, " ") : "structure not read"}</div>
            <div className="mt-1">Casualty and liability: <b>{(hover.cl_share * 100).toFixed(1)}%</b> of operating cost · {fmtMoney(hover.cl_per_vrm, 2)} per revenue mile</div>
            <div>{fmtMoney(hover.cl_expense)} a year on {fmtMoney(hover.total_opex)} of operating cost</div>
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-charcoal">
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full" style={{ background: STRUCTURE_STYLE.self.color }} />{STRUCTURE_STYLE.self.label}</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full" style={{ background: STRUCTURE_STYLE.covered.color }} />{STRUCTURE_STYLE.covered.label}</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full border" style={{ borderColor: STRUCTURE_STYLE.other.color }} />statement not read ({rows.length - nLab} agencies)</span>
      </div>
    </SicCard>
  );
}
