// CompGapLocalityCard — pick a state (default "All states") or a major city, plus
// a domain, and see government vs private median pay for that place. States come
// from ACS PUMS (annualised from hourly); cities come from their own payroll files
// (NYC, Chicago, SF, Seattle, LA) compared to the metro (central-county) private
// median. All figures are annual, constant 2026 dollars.

import { useEffect, useMemo, useState } from "react";
import MethodologyInfo from "@/components/MethodologyInfo";
import DomainChip from "./DomainChip";
import DomainCompositionNote from "./DomainCompositionNote";
import { DOMAIN_LABELS, DOMAIN_ORDER, useDomainComposition } from "@/lib/compgapDomains";

const COBALT = "#1F1FD6";
const CAROLINA = "#21A8E0";
const FT_FY_HOURS = 2080;

interface StateRec { state: string; domain: string; sector: "public" | "private"; p50: number; p90: number; n_unweighted: number; }
interface StateData { year: number; records: StateRec[]; }
interface CityRec {
  city: string; domain: string; n: number;
  gov_p50: number; gov_p90?: number;
  private_p50_metro?: number; private_p90_metro?: number;
  gap_vs_private_pct?: number; gap_top_pct?: number;
}
interface CityMeta { key: string; name: string; state: string; data_year: number; title_coverage_pct: number; }
interface CityData { dollar_year: number; cities: CityMeta[]; records: CityRec[]; }

const fmtK = (v: number) => `$${Math.round(v / 1000)}k`;

export default function CompGapLocalityCard() {
  const [sdata, setSdata] = useState<StateData | null>(null);
  const [cdata, setCdata] = useState<CityData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState("state:US");      // "state:US" | "state:NY" | "city:nyc"
  const [domain, setDomain] = useState("software_it");
  const [metric, setMetric] = useState<"median" | "top">("top");
  const composition = useDomainComposition();

  useEffect(() => {
    Promise.all([
      fetch("/data/compgap/state_cross_section.json").then((r) => r.json()),
      fetch("/data/compgap/localities/cities.json").then((r) => r.ok ? r.json() : null).catch(() => null),
    ])
      .then(([s, c]) => { setSdata(s); setCdata(c); })
      .catch((e) => setErr(String(e)));
  }, []);

  const states = useMemo(
    () => (sdata ? Array.from(new Set(sdata.records.map((r) => r.state))).filter((s) => s !== "US").sort() : []),
    [sdata],
  );

  const view = useMemo(() => {
    if (!sdata) return null;
    const isTop = metric === "top";
    const [kind, key] = sel.split(":");
    if (kind === "city" && cdata) {
      // all-occupations isn't a valid city comparison (salaried-only payroll)
      if (domain === "all") return { gov: undefined, priv: undefined, gap: null, small: false, isCity: true };
      const rec = cdata.records.find((r) => r.city === key && r.domain === domain);
      const meta = cdata.cities.find((c) => c.key === key);
      const gov = isTop ? rec?.gov_p90 : rec?.gov_p50;
      const priv = isTop ? rec?.private_p90_metro : rec?.private_p50_metro;
      const gap = isTop ? rec?.gap_top_pct : rec?.gap_vs_private_pct;
      if (!rec || priv == null) return { gov, priv: undefined, gap: null, small: true, meta, isCity: true };
      return { gov, priv, gap: gap ?? null, small: rec.n < 30, meta, isCity: true };
    }
    const pub = sdata.records.find((r) => r.state === key && r.domain === domain && r.sector === "public");
    const priv = sdata.records.find((r) => r.state === key && r.domain === domain && r.sector === "private");
    const pubV = pub ? (isTop ? pub.p90 : pub.p50) * FT_FY_HOURS : undefined;
    const privV = priv ? (isTop ? priv.p90 : priv.p50) * FT_FY_HOURS : undefined;
    if (pubV == null || privV == null) return { gov: pubV, priv: privV, gap: null, small: true, isCity: false };
    return { gov: pubV, priv: privV, gap: (pubV / privV - 1) * 100,
             small: (pub!.n_unweighted < 100 || priv!.n_unweighted < 100), isCity: false };
  }, [sdata, cdata, sel, domain, metric]);

  if (err) return <div className="my-6 text-sm text-steel">Locality data unavailable ({err}).</div>;
  if (!sdata || !view) return <div className="my-6 h-8 animate-pulse rounded bg-vellum" />;

  const placeLabel = sel === "state:US" ? "United States"
    : sel.startsWith("city:") ? (cdata?.cities.find((c) => c.key === sel.slice(5))?.name ?? sel)
    : sel.slice(6);
  const maxWage = Math.max(view.gov ?? 0, view.priv ?? 0, 1);
  const bar = (val: number, color: string) => ({ width: `${(val / maxWage) * 100}%`, background: color });

  return (
    <div className="my-8 rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h4 className="font-serif text-[17px] font-semibold text-cobalt">Find your government</h4>
        <MethodologyInfo id="compgap.locality" variant="icon" />
        <select
          value={sel}
          onChange={(e) => {
            const v = e.target.value;
            setSel(v);
            // "All occupations" isn't comparable for cities (salaried-only payroll
            // vs all private), so it's hidden there — switch off it.
            if (v.startsWith("city:") && domain === "all") setDomain("software_it");
          }}
          className="ml-auto rounded-md border border-slate-300 bg-white px-2 py-1 text-[13px] text-charcoal"
          aria-label="Place"
        >
          <option value="state:US">All states (U.S.)</option>
          {cdata && cdata.cities.length > 0 && (
            <optgroup label="Cities">
              {cdata.cities.map((c) => <option key={c.key} value={`city:${c.key}`}>{c.name}</option>)}
            </optgroup>
          )}
          <optgroup label="States">
            {states.map((s) => <option key={s} value={`state:${s}`}>{s}</option>)}
          </optgroup>
        </select>
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5">
        {DOMAIN_ORDER.filter((d) => DOMAIN_LABELS[d] && !(sel.startsWith("city:") && d === "all")).map((d) => (
          <DomainChip
            key={d}
            label={DOMAIN_LABELS[d]}
            selected={domain === d}
            includes={composition?.domains?.[d]?.includes}
            onClick={() => setDomain(d)}
            size="sm"
          />
        ))}
      </div>

      <div className="mb-3 flex items-center gap-2">
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
        <span className="text-[11.5px] text-charcoal/55">
          {metric === "top" ? "90th percentile — the top of the field" : "the median worker"}
        </span>
      </div>

      {view.gov && view.priv ? (
        <div className="space-y-3">
          <div>
            <div className="mb-1 flex justify-between text-[12.5px]">
              <span className="text-charcoal/80">Government — {placeLabel}</span>
              <span className="font-mono font-semibold text-charcoal">{fmtK(view.gov)}/yr</span>
            </div>
            <div className="h-5 w-full rounded bg-slate-100"><div className="h-5 rounded" style={bar(view.gov, COBALT)} /></div>
          </div>
          <div>
            <div className="mb-1 flex justify-between text-[12.5px]">
              <span className="text-charcoal/80">Private — {view.isCity ? `${placeLabel} metro` : placeLabel}</span>
              <span className="font-mono font-semibold text-charcoal">{fmtK(view.priv)}/yr</span>
            </div>
            <div className="h-5 w-full rounded bg-slate-100"><div className="h-5 rounded" style={bar(view.priv, CAROLINA)} /></div>
          </div>
          <div className="flex items-baseline gap-2 pt-1">
            <span className="font-serif text-[24px] font-semibold leading-none"
              style={{ color: (view.gap ?? 0) < 0 ? "#D4823A" : COBALT }}>
              {view.gap !== null ? `${view.gap > 0 ? "+" : ""}${view.gap.toFixed(0)}%` : "—"}
            </span>
            <span className="text-[12.5px] text-charcoal/70">
              {DOMAIN_LABELS[domain]} — government {metric === "top" ? "top of the field" : "median"} vs private, {placeLabel}
            </span>
          </div>
          {view.small && (
            <div className="rounded bg-amber-50 px-2.5 py-1.5 text-[11px] leading-snug text-amber-800">
              Small sample for this cell — read as indicative.
            </div>
          )}
        </div>
      ) : (
        <div className="rounded bg-vellum/60 px-3 py-4 text-[13px] text-steel">
          Not enough sample for {DOMAIN_LABELS[domain]} in {placeLabel}. Try a larger domain or place.
        </div>
      )}

      <DomainCompositionNote domain={domain} data={composition} />

      <p className="mt-4 text-[11.5px] leading-relaxed text-charcoal/55">
        {view.isCity
          ? `City-government pay is from ${placeLabel}'s own payroll file (full-time base pay, ${cdata?.dollar_year}). Job titles are mapped to occupations by keyword. The private comparator is the private sector in ${placeLabel}'s metro area (its central county/counties) from Census microdata — not the whole state.`
          : "Government and private medians are ACS PUMS, full-time, age 25–64, annualised to constant 2026 dollars, by state of residence."}
      </p>
    </div>
  );
}
