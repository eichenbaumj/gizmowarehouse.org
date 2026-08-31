// CompGapLadder — Chart B: where the government median sits in the private wage
// ladder (50th/90th/95th), and how the top has pulled away. A toggle restricts
// the ladder to the knowledge-economy domains (software, legal, finance,
// engineering, management), where the divergence is sharpest (note 6).

import { useEffect, useMemo, useState } from "react";
import TimeSeriesChart, { ChartLegend, type Series } from "./TimeSeriesChart";
import MethodologyInfo from "@/components/MethodologyInfo";

const COBALT = "#1F1FD6";
const CAROLINA = "#21A8E0";
const STEEL = "#6E6E6D";
const GOLD = "#C99A2E";

interface DistPt {
  year: number; private_p50: number; private_p90: number; private_p95: number;
  gov_p50: number; gov_p50_no_teachers: number;
}
interface MacroData {
  dollar_year: number;
  wage_distribution: DistPt[];
  wage_distribution_highskill: DistPt[];
}

const dollarsK = (v: number) => `$${Math.round(v / 1000)}k`;

export default function CompGapLadder() {
  const [data, setData] = useState<MacroData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scope, setScope] = useState<"all" | "highskill">("all");

  useEffect(() => {
    fetch("/data/compgap/macro_topdist.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  const d = useMemo(() => {
    if (!data) return [];
    return scope === "highskill" && data.wage_distribution_highskill?.length
      ? data.wage_distribution_highskill
      : data.wage_distribution;
  }, [data, scope]);

  if (err) return <div className="my-6 text-sm text-steel">Chart data unavailable ({err}).</div>;
  if (!data) return <div className="my-6 h-8 animate-pulse rounded bg-vellum" />;

  const yr = data.dollar_year;
  const chartB: Series[] = [
    { key: "p95", label: "Private 95th percentile", color: COBALT, points: d.map((p) => ({ x: p.year, y: p.private_p95 })) },
    { key: "p90", label: "Private 90th percentile", color: CAROLINA, points: d.map((p) => ({ x: p.year, y: p.private_p90 })) },
    { key: "p50", label: "Private median", color: STEEL, points: d.map((p) => ({ x: p.year, y: p.private_p50 })) },
    { key: "gov", label: "Government median", color: GOLD, points: d.map((p) => ({ x: p.year, y: p.gov_p50_no_teachers })) },
  ];

  return (
    <div className="my-6 rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h4 className="font-serif text-[17px] font-semibold text-cobalt">
          Where government pay sits in the private market
        </h4>
        <MethodologyInfo id="compgap.macro_topdist" variant="icon" />
        <div className="ml-auto inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-[12px]">
          {([["all", "All private"], ["highskill", "Knowledge economy"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setScope(k)}
              className={"rounded px-2.5 py-1 transition-colors " +
                (scope === k ? "bg-cobalt text-white font-semibold" : "text-charcoal/70 hover:text-cobalt")}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <p className="mb-2 text-[12.5px] leading-relaxed text-charcoal/70">
        {scope === "highskill"
          ? `The same ladder for the knowledge-economy fields only: software, law, finance, engineering, and management. The government median has lost ground in real terms while the private top climbed, so the distance to a top private salary in these fields is the widest on the page.`
          : `The private-sector wage ladder, constant ${yr} dollars, with the government median for comparison. The government median sits around the middle of the private market and stays there while the top of that market keeps climbing. Switch to knowledge economy to see the fields where that gap is widest.`}
      </p>
      <TimeSeriesChart series={chartB} yFormat={dollarsK} xFormat={(v) => `${v}`}
        yLabel={`Annual wage (${yr} $)`} height={340} />
      <ChartLegend items={chartB.map((s2) => ({ label: s2.label, color: s2.color }))} />
      <p className="mt-2 text-[11.5px] leading-relaxed text-charcoal/55">
        Census top-codes the highest earners, so the 90th and 95th percentiles understate how far
        the true top has pulled away.
      </p>
    </div>
  );
}
