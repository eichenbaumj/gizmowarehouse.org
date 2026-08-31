// CompGapCompression — the compression curve. The composition-adjusted public
// wage gap vs private, plotted within each education level, for all three
// levels of government. Every line starts at or above zero (a high floor) and
// slopes below it (a low ceiling): the single picture of a compressed pay
// structure, and the apples-to-apples answer to "does government really pay
// more at the bottom?" — within education, federal does; state and local cross
// to a penalty almost immediately. Reads the already-shipped educ_gradient.json.

import { useEffect, useMemo, useState } from "react";
import TimeSeriesChart, { ChartLegend, type Series } from "./TimeSeriesChart";
import MethodologyInfo from "@/components/MethodologyInfo";

const FEDERAL = "#1F1FD6"; // cobalt
const STATE = "#C99A2E"; // gold
const LOCAL = "#21A8E0"; // carolina

// Education buckets in order, with compact x-axis labels. The keys match
// educ_gradient.json's adjusted_by_education map.
const EDUC: [string, string][] = [
  ["lt_hs", "≤ HS"],
  ["hs", "HS"],
  ["some_college", "Some col."],
  ["assoc", "Assoc."],
  ["bachelors", "Bachelor's"],
  ["masters", "Master's"],
  ["prof_doctorate", "Doctorate"],
];

const LEVELS: { key: string; label: string; color: string }[] = [
  { key: "federal", label: "Federal", color: FEDERAL },
  { key: "state", label: "State", color: STATE },
  { key: "local", label: "Local", color: LOCAL },
];

interface GradientData {
  adjusted_by_education: Record<string, Record<string, number>>;
  cbo_2024_total_comp_premium?: Record<string, number>;
}

export default function CompGapCompression() {
  const [grad, setGrad] = useState<GradientData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/compgap/educ_gradient.json")
      .then((r) => r.json())
      .then(setGrad)
      .catch((e) => setErr(String(e)));
  }, []);

  const series: Series[] = useMemo(() => {
    if (!grad) return [];
    return LEVELS.map((lv) => ({
      key: lv.key,
      label: lv.label,
      color: lv.color,
      points: EDUC.map(([eduKey], i) => {
        const v = grad.adjusted_by_education[eduKey]?.[lv.key];
        return v === undefined ? null : { x: i, y: v };
      }).filter(Boolean) as { x: number; y: number }[],
    }));
  }, [grad]);

  if (err) return <div className="my-6 text-sm text-steel">Compression chart unavailable ({err}).</div>;
  if (!grad) return <div className="my-6 h-8 animate-pulse rounded bg-vellum" />;

  return (
    <div className="my-8 rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-1 flex items-center gap-2">
        <h4 className="font-serif text-[18px] font-semibold text-cobalt">
          A high floor and a low ceiling
        </h4>
        <MethodologyInfo id="compgap.compression" variant="icon" />
      </div>
      <p className="mb-3 text-[12.5px] leading-relaxed text-charcoal/70">
        The composition-adjusted government wage gap vs the private sector, within each education
        level. Above the line, government pays more than the market for the same kind of worker;
        below it, less. Every level of government starts high and slopes down — pay that is
        compressed, generous at the bottom and thin at the top.
      </p>
      <TimeSeriesChart
        series={series}
        yDomain={[-40, 28]}
        yFormat={(v) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`}
        xFormat={(v) => EDUC[Math.round(v)]?.[1] ?? ""}
        yLabel="Adjusted gap vs private"
        refY={0}
        height={320}
      />
      <ChartLegend
        items={[
          { label: "Federal", color: FEDERAL },
          { label: "State", color: STATE },
          { label: "Local", color: LOCAL },
        ]}
      />
      <p className="mt-3 text-[12px] leading-relaxed text-charcoal/60">
        Wages, composition-adjusted (ACS PUMS). The zero line is the comparable private-sector wage.
        Federal pay stays above the market furthest up the ladder; state and local cross into a
        penalty almost immediately, so "government pays more at the bottom" is mostly a federal story.
        The same reversal shows up in the{" "}
        <a
          href="https://www.cbo.gov/publication/60235"
          target="_blank"
          rel="noreferrer"
          className="underline decoration-cobalt/30 underline-offset-2 hover:text-cobalt"
        >
          Congressional Budget Office's total-compensation estimates
        </a>{" "}
        — federal pay +40% at a high-school education or less, fading to roughly even at a bachelor's
        and −22% at the doctoral level.
      </p>
    </div>
  );
}
