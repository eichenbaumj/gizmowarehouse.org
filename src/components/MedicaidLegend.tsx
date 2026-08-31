// MedicaidLegend — small color-scale card in the map's bottom-left corner.
// Reads the active mode + primitive's stops from config and renders 8 color
// swatches with threshold labels. Includes an ⓘ methodology disclosure.

import { MEDICAID_MAP_CONFIG, type MedicaidMapMode } from "@/config/medicaidWorkRequirementsMap";
import MethodologyInfo from "@/components/MethodologyInfo";

interface Props {
  mode: MedicaidMapMode;
  primitive: "counties" | "hex5mi" | "grid";
  /** Methodology disclosure ID to render next to the legend title. */
  disclosureId?: string;
}

function fmtStop(value: number, mode: MedicaidMapMode): string {
  if (mode === "subject_rate") {
    return (value * 100).toFixed(0) + "%";
  }
  if (mode === "burden_index") {
    return (value > 0 ? "+" : "") + value;
  }
  if (value === 0) return "0";
  if (value < 1000) return Math.round(value).toString();
  if (value < 1_000_000) return (value / 1000).toFixed(value < 10_000 ? 1 : 0) + "K";
  return (value / 1_000_000).toFixed(1) + "M";
}

export default function MedicaidLegend({ mode, primitive, disclosureId }: Props) {
  const cfg = MEDICAID_MAP_CONFIG.modes[mode];
  const stops =
    primitive === "hex5mi" ? ((cfg as any).stopsHex5mi ?? cfg.stopsGrid) :
    primitive === "grid" ? cfg.stopsGrid :
    cfg.stopsCounty;

  return (
    <div className="absolute bottom-3 left-3 z-10 max-w-[260px] rounded-md bg-white/95 px-3 py-2 shadow-md ring-1 ring-slate-200 backdrop-blur-sm">
      <div className="flex items-baseline justify-between gap-2">
        <div className="font-sans text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          {cfg.label}
        </div>
        {disclosureId && <MethodologyInfo id={disclosureId} variant="icon" align="right" />}
      </div>
      <div className="mt-1 text-[9.5px] text-slate-500">{cfg.legendUnit}</div>
      <div className="pointer-events-none mt-1.5 w-[192px]">
        <div className="flex h-3 overflow-hidden rounded-sm ring-1 ring-slate-200">
          {stops.map(([value, color], i) => (
            <div
              key={i}
              className="flex-1"
              style={{ background: color }}
              title={fmtStop(value, mode)}
            />
          ))}
        </div>
        <div className="mt-1 flex font-sans text-[8.5px] tabular-nums text-slate-600">
          {stops.map(([value], i) => {
            const isLast = i === stops.length - 1;
            const showLabel = i % 2 === 0 || isLast;
            return (
              <div
                key={i}
                className={"flex-1 " + (isLast ? "text-right" : "text-left")}
              >
                {showLabel ? fmtStop(value, mode) : ""}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
