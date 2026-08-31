// CompGapEarnings — Chart A: what public vs private workers earn over time, with
// the exclude-teachers toggle. Split out of CompGapMacro.

import { useEffect, useState } from "react";
import TimeSeriesChart, { ChartLegend, type Series } from "./TimeSeriesChart";
import MethodologyInfo from "@/components/MethodologyInfo";

const COBALT = "#1F1FD6";
const CAROLINA = "#21A8E0";

interface DistPt { year: number; private_p50: number; gov_p50: number; gov_p50_no_teachers: number }
interface MacroData { dollar_year: number; wage_distribution: DistPt[] }

const dollarsK = (v: number) => `$${Math.round(v / 1000)}k`;

export default function CompGapEarnings() {
  const [data, setData] = useState<MacroData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [exclTeachers, setExclTeachers] = useState(true);

  useEffect(() => {
    fetch("/data/compgap/macro_topdist.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="my-6 text-sm text-steel">Chart data unavailable ({err}).</div>;
  if (!data) return <div className="my-6 h-8 animate-pulse rounded bg-vellum" />;

  const d = data.wage_distribution;
  const govKey = exclTeachers ? "gov_p50_no_teachers" : "gov_p50";
  const yr = data.dollar_year;
  const chartA: Series[] = [
    { key: "priv", label: "Private median", color: CAROLINA, points: d.map((p) => ({ x: p.year, y: p.private_p50 })) },
    { key: "gov", label: exclTeachers ? "Government median (excl. teachers)" : "Government median", color: COBALT, points: d.map((p) => ({ x: p.year, y: p[govKey] })) },
  ];

  return (
    <div className="my-6 rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h4 className="font-serif text-[17px] font-semibold text-cobalt">What public and private workers earn</h4>
        <MethodologyInfo id="compgap.macro_topdist" variant="icon" />
        <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-[12px] text-charcoal/75">
          <input type="checkbox" checked={exclTeachers} onChange={(e) => setExclTeachers(e.target.checked)} className="accent-cobalt" />
          Exclude teachers
        </label>
      </div>
      <p className="mb-2 text-[12.5px] leading-relaxed text-charcoal/70">
        Median real annual wage, constant {yr} dollars, full-time workers. The government median
        tracks or sits a little above the private median.
      </p>
      <TimeSeriesChart series={chartA} yFormat={dollarsK} xFormat={(v) => `${v}`}
        yLabel={`Median wage (${yr} $)`} height={320} />
      <ChartLegend items={chartA.map((s2) => ({ label: s2.label, color: s2.color }))} />
    </div>
  );
}
