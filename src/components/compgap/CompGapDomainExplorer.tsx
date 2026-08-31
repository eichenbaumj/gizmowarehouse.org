// CompGapDomainExplorer — the core interactive. Pick a domain and a level of
// government; see public vs private median wages over time, the raw gap, and the
// composition-adjusted gap (with its specification-sensitivity range). The
// education-gradient view lives in its own embed (CompGapCompression).

import { useEffect, useMemo, useState } from "react";
import TimeSeriesChart, { ChartLegend, type Series } from "./TimeSeriesChart";
import MethodologyInfo from "@/components/MethodologyInfo";
import DomainChip from "./DomainChip";
import DomainCompositionNote from "./DomainCompositionNote";
import { DOMAIN_LABELS, useDomainComposition } from "@/lib/compgapDomains";

const COBALT = "#1F1FD6";
const CAROLINA = "#21A8E0";

interface SeriesRec {
  year: number; domain: string; govlevel: string;
  p50: number; p75: number; p90: number; n_unweighted: number;
  gap_vs_private_fp_pct?: number; gap_vs_private_fp_pct_p90?: number; adj_gap_pct?: number;
  adj_gap_lo?: number; adj_gap_hi?: number; flags?: string[];
}
interface NationalData {
  domains: { key: string; label: string; is_elite: number }[];
  govlevel_labels: Record<string, string>;
  series: SeriesRec[];
}

const GOV_OPTIONS = [
  { key: "federal", label: "Federal" },
  { key: "state", label: "State" },
  { key: "local", label: "Local" },
];

function fmtPct(v: number | undefined): string {
  if (v === undefined || v === null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

export default function CompGapDomainExplorer() {
  const [data, setData] = useState<NationalData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [domain, setDomain] = useState("software_it");
  const [gov, setGov] = useState("federal");
  const [metric, setMetric] = useState<"median" | "top">("top");
  const composition = useDomainComposition();

  useEffect(() => {
    fetch("/data/compgap/national_series.json")
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  const view = useMemo(() => {
    if (!data) return null;
    const inDomain = data.series.filter((r) => r.domain === domain);
    const priv = inDomain.filter((r) => r.govlevel === "private_fp").sort((a, b) => a.year - b.year);
    const pub = inDomain.filter((r) => r.govlevel === gov).sort((a, b) => a.year - b.year);
    const latestPub = pub[pub.length - 1];
    return { priv, pub, latestPub };
  }, [data, domain, gov]);

  if (err) return <div className="my-6 text-sm text-steel">Explorer data unavailable ({err}).</div>;
  if (!data || !view) return <div className="my-6 h-8 animate-pulse rounded bg-vellum" />;

  const govLabel = data.govlevel_labels[gov] ?? gov;
  const isTop = metric === "top";
  const yOf = (r: SeriesRec) => (isTop ? r.p90 : r.p50);
  const series: Series[] = [
    { key: "priv", label: "Private (for-profit)", color: CAROLINA, points: view.priv.map((r) => ({ x: r.year, y: yOf(r) })) },
    { key: "pub", label: govLabel, color: COBALT, points: view.pub.map((r) => ({ x: r.year, y: yOf(r) })) },
  ];
  const lp = view.latestPub;
  const rawGap = lp?.gap_vs_private_fp_pct;
  const adjGap = lp?.adj_gap_pct;
  const topGap = lp?.gap_vs_private_fp_pct_p90;
  const small = lp?.flags?.includes("small_cell");

  return (
    <div className="my-8">
      {/* Controls */}
      <div className="rounded-t-xl border border-b-0 border-slate-200 bg-vellum/60 p-4">
        <div className="mb-2 flex items-center gap-2">
          <span className="font-sans text-[11px] font-semibold uppercase tracking-[0.08em] text-steel">Domain</span>
          <MethodologyInfo id="compgap.domain_gap" variant="icon" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {data.domains.filter((d) => d.key !== "all").map((d) => (
            <DomainChip
              key={d.key}
              label={DOMAIN_LABELS[d.key] ?? d.label}
              selected={domain === d.key}
              elite={!!d.is_elite}
              includes={composition?.domains?.[d.key]?.includes}
              onClick={() => setDomain(d.key)}
            />
          ))}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <span className="font-sans text-[11px] font-semibold uppercase tracking-[0.08em] text-steel">Compare</span>
          <div className="flex gap-1.5">
            {GOV_OPTIONS.map((o) => (
              <button
                key={o.key}
                onClick={() => setGov(o.key)}
                className={
                  "rounded-md border px-3 py-1 text-[12.5px] transition-colors " +
                  (gov === o.key
                    ? "border-cobalt bg-white text-cobalt font-semibold"
                    : "border-slate-300 bg-white text-charcoal/70 hover:border-cobalt/50")
                }
              >
                {o.label}
              </button>
            ))}
            <span className="self-center text-[12.5px] text-charcoal/60">vs. private</span>
          </div>
        </div>
      </div>

      {/* Chart + gap readout */}
      <div className="rounded-b-xl border border-slate-200 bg-white p-5">
        <div className="grid gap-5 md:grid-cols-[1fr_220px]">
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="text-[12px] text-charcoal/70">
                {isTop
                  ? "90th percentile — the top of each field"
                  : "Median worker in each field"}
              </div>
              <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-[12px]">
                {([["median", "Median"], ["top", "Top of the field"]] as const).map(([k, label]) => (
                  <button
                    key={k}
                    onClick={() => setMetric(k)}
                    className={
                      "rounded px-2.5 py-1 transition-colors " +
                      (metric === k ? "bg-cobalt text-white font-semibold" : "text-charcoal/70 hover:text-cobalt")
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <TimeSeriesChart
              series={series}
              yFormat={(v) => `$${v.toFixed(0)}`}
              xFormat={(v) => `${v}`}
              yLabel={`${isTop ? "90th-pct" : "Median"} real hourly wage (2026 $)`}
              height={320}
            />
            <ChartLegend
              items={[
                { label: isTop ? "Private — top of field" : "Private (for-profit)", color: CAROLINA },
                { label: isTop ? `${govLabel} — top of field` : govLabel, color: COBALT },
              ]}
            />
          </div>
          <div className="flex flex-col justify-center gap-4 rounded-lg bg-vellum/50 p-4">
            <div className={!isTop ? "-mx-2 rounded-md bg-cobalt/5 px-2 py-1.5" : ""}>
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-steel">
                Raw wage gap
              </div>
              <div className={"font-serif text-[30px] font-semibold leading-none " + ((rawGap ?? 0) < 0 ? "text-[#D4823A]" : "text-cobalt")}>
                {fmtPct(rawGap)}
              </div>
              <div className="mt-0.5 text-[11px] text-charcoal/60">{govLabel} median vs private</div>
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-steel">
                Adjusted gap <MethodologyInfo id="compgap.adjusted_gap" variant="icon" />
              </div>
              <div className={"font-serif text-[30px] font-semibold leading-none " + ((adjGap ?? 0) < 0 ? "text-[#D4823A]" : "text-cobalt")}>
                {fmtPct(adjGap)}
              </div>
              <div className="mt-0.5 text-[11px] text-charcoal/60">
                {lp?.adj_gap_lo !== undefined ? `range ${fmtPct(lp.adj_gap_lo)} to ${fmtPct(lp.adj_gap_hi)}` : "education, age, hours, geography held equal"}
              </div>
            </div>
            <div className={"border-t border-slate-200 pt-3 " + (isTop ? "-mx-2 rounded-md border-t-0 bg-cobalt/5 px-2 py-1.5" : "")}>
              <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-steel">
                Top of the field
              </div>
              <div className={"font-serif text-[30px] font-semibold leading-none " + ((topGap ?? 0) < 0 ? "text-[#D4823A]" : "text-cobalt")}>
                {fmtPct(topGap)}
              </div>
              <div className="mt-0.5 text-[11px] text-charcoal/60">
                90th-percentile {govLabel.toLowerCase()} vs the best-paid private firms
              </div>
            </div>
            {small && (
              <div className="rounded bg-amber-50 px-2 py-1 text-[10.5px] leading-snug text-amber-800">
                Small sample for this cell — read as indicative.
              </div>
            )}
          </div>
        </div>
        <DomainCompositionNote domain={domain} data={composition} />
        <p className="mt-3 text-[12px] leading-relaxed text-charcoal/60">
          Wages only, full-time workers aged 25–64. The chart opens on the top of the field — the
          90th percentile of each side, where the best-paid private employers sit: big tech in
          software, the white-shoe firms in law, finance, and consulting. Flip to the median to see
          the typical worker, where government usually looks competitive. The gap lives at the top.
          ★ marks the knowledge-economy fields.
        </p>
      </div>
    </div>
  );
}
