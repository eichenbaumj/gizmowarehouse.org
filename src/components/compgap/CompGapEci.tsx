// CompGapEci — the benefits nuance: BLS ECI for state & local, total compensation
// vs wages alone, each indexed to its own 2005 level. Caption rewritten so the
// shared starting point reads as "this shows growth, not dollar levels" (note 3).

import { useEffect, useState } from "react";
import TimeSeriesChart, { ChartLegend, type Series } from "./TimeSeriesChart";
import MethodologyInfo from "@/components/MethodologyInfo";

const COBALT = "#1F1FD6";

interface EciPt { year: number; real_index: number }
interface MacroData { eci: Record<string, EciPt[]> }

export default function CompGapEci() {
  const [data, setData] = useState<MacroData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/compgap/macro_topdist.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="my-6 text-sm text-steel">Chart data unavailable ({err}).</div>;
  if (!data) return <div className="my-6 h-8 animate-pulse rounded bg-vellum" />;

  const eci = data.eci;
  const eciSeries: Series[] = [
    { key: "tc", label: "Total compensation", color: COBALT, points: (eci.stlocal_totalcomp ?? []).filter((p) => p.year >= 2005).map((p) => ({ x: p.year, y: p.real_index })) },
    { key: "wg", label: "Wages only", color: COBALT, dash: true, points: (eci.stlocal_wages ?? []).filter((p) => p.year >= 2005).map((p) => ({ x: p.year, y: p.real_index })) },
  ];

  return (
    <div className="my-6 rounded-xl border border-slate-200 bg-vellum/40 p-5">
      <div className="mb-1 flex items-center gap-2">
        <h4 className="font-serif text-[15px] font-semibold text-cobalt">
          Why total pay held up even as wages slipped
        </h4>
        <MethodologyInfo id="compgap.macro_divergence" variant="icon" />
      </div>
      <p className="mb-2 text-[12px] leading-relaxed text-charcoal/70">
        State and local government, BLS Employment Cost Index. Both lines start at 100 in 2005
        because each is set to its own 2005 level — so this tracks how each has <em>grown</em> after
        inflation, not the dollar gap between them (total compensation is higher than wages in every
        year). Adjusted for inflation, total comp roughly held its ground while wages alone slipped,
        and the 2021–22 price spike hit both. The cushion is benefits and pensions.
      </p>
      <TimeSeriesChart series={eciSeries} yFormat={(v) => v.toFixed(0)} xFormat={(v) => `${v}`}
        yLabel="Real index (2005 = 100)" height={240} dots={false} />
      <ChartLegend items={[{ label: "Total compensation", color: COBALT }, { label: "Wages only", color: COBALT, dash: true }]} />
    </div>
  );
}
