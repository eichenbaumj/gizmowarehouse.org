// CompGapHero — the public-workforce stat strip with the workforce Sankey beneath
// it. Both use the same ACS universe (employed residents 25-64) so the headline
// counts and the Sankey line up. The familiar BLS payroll framing is preserved in
// the footnote.

import { useEffect, useState } from "react";
import MethodologyInfo from "@/components/MethodologyInfo";
import { useCountUp } from "@/hooks/useCountUp";
import CompGapWorkforceSankey from "./CompGapWorkforceSankey";

interface Flow { govlevel: string; workgroup: string; employed_m: number }
interface WfcData {
  year: number;
  level_totals_m: { federal: number; state: number; local: number };
  matrix: Flow[];
}

function Stat({ value, suffix, label }: { value: number; suffix: string; label: string }) {
  const v = useCountUp(value);
  return (
    <div className="flex flex-col">
      <span className="font-serif text-[26px] font-semibold leading-none text-cobalt">
        {v.toLocaleString(undefined, { maximumFractionDigits: 1 })}
        <span className="text-[18px]">{suffix}</span>
      </span>
      <span className="mt-1 text-[12px] leading-tight text-charcoal/70">{label}</span>
    </div>
  );
}

export default function CompGapHero() {
  const [data, setData] = useState<WfcData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/compgap/workforce_composition.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="my-6 text-sm text-steel">Chart data unavailable ({err}).</div>;
  if (!data) return <div className="my-6 h-8 animate-pulse rounded bg-vellum" />;

  const t = data.level_totals_m;
  const total = t.federal + t.state + t.local;
  const localEdu = data.matrix.find((m) => m.govlevel === "local" && m.workgroup === "education")?.employed_m;
  const localEduShare = localEdu ? Math.round((localEdu / t.local) * 100) : null;
  const totalEdu = data.matrix
    .filter((m) => m.workgroup === "education")
    .reduce((s, m) => s + m.employed_m, 0);

  return (
    <div className="my-8 rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-3 flex items-center gap-2">
        <h4 className="font-sans text-[11px] font-semibold uppercase tracking-[0.08em] text-steel">
          The public workforce, {data.year}
        </h4>
        <MethodologyInfo id="compgap.shape" variant="icon" />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat value={t.federal} suffix="M" label="Federal" />
        <Stat value={t.state} suffix="M" label="State" />
        <Stat value={t.local} suffix="M" label="Local" />
        <Stat value={total} suffix="M" label="Total, ages 25–64" />
      </div>
      <p className="mt-3 text-[12.5px] leading-relaxed text-charcoal/70">
        Local government is the largest, and education is the biggest piece of it:
        about <strong>{localEdu?.toFixed(1)} million</strong> of those {t.local.toFixed(1)} million
        local workers teach or work in schools{localEduShare ? `, roughly ${localEduShare}% of the local payroll` : ""}.
        Counting state and federal education too, the teaching total reaches
        about <strong>{totalEdu.toFixed(1)} million</strong>, the figure shown in the chart below.
      </p>
      <p className="mt-2 text-[11px] leading-relaxed text-charcoal/55">
        Counts are ACS (employed residents 25–64), the same basis as the Sankey and the wage
        charts below. By the standard BLS payroll measure, government is about 23 million jobs,
        ~15% of U.S. employment; ACS runs higher for federal (it counts active-duty military and
        self-reported federal workers) and lower for local (it omits the part-time and under-25
        jobs BLS counts).
      </p>

      <div className="mt-5 border-t border-slate-100 pt-4">
        <CompGapWorkforceSankey />
      </div>
    </div>
  );
}
