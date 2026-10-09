// SicVolatility — <sic-volatility></sic-volatility>
//
// What financing structure actually buys: not a lower bill, a smoother one. For each class of New York
// government with a documented arrangement, the median year-to-year swing in liability cost per resident
// (standard deviation over mean, 2015 to 2024) for the self-insured and the covered, as paired HTML bars
// in the DcrFootprintBars idiom; then the same for police-heavy governments by police share.

import { STRUCTURE_STYLE, type ModelsData } from "@/config/selfInsuranceCost";
import { useSicData, SicCard, Eyebrow, Sub, Loading, Err } from "./useSicData";

const CLASS_LABEL: Record<string, string> = { city: "Cities", county: "Counties", town: "Towns", village: "Villages" };
const pct = (v: number | null | undefined) => (v == null ? "" : `${Math.round(v * 100)}%`);

function Pair({ label, self, covered, max, nSelf, nCovered }: { label: string; self: number | null; covered: number | null; max: number; nSelf?: number; nCovered?: number }) {
  return (
    <div className="mb-3">
      <div className="mb-1 text-sm font-semibold text-charcoal">{label}</div>
      {(["self", "covered"] as const).map((k) => {
        const v = k === "self" ? self : covered;
        const n = k === "self" ? nSelf : nCovered;
        return (
          <div key={k} className="mb-1 flex items-center gap-2 text-xs">
            <span className="w-[150px] shrink-0 text-steel">{k === "self" ? "carries its own" : "buys coverage"}{n != null ? ` (${n})` : ""}</span>
            <div className="h-4 flex-1 rounded-sm bg-vellum">
              <div className="h-4 rounded-sm" style={{ width: `${v == null ? 0 : (v / max) * 100}%`, background: STRUCTURE_STYLE[k].color }} />
            </div>
            <span className="w-10 text-right text-charcoal">{pct(v)}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function SicVolatility() {
  const { data, err } = useSicData<ModelsData>("models");
  if (err) return <Err msg={err} />;
  if (!data?.ny?.volatility) return <Loading h={360} />;
  const v = data.ny.volatility;
  const classes = ["village", "city", "town", "county"].filter((c) => v.by_class[c]);
  const terc = v.police_terciles ?? {};
  const all = [
    ...classes.flatMap((c) => [v.by_class[c].yoy_cv_self ?? 0, v.by_class[c].yoy_cv_covered ?? 0]),
    ...Object.values(terc).flatMap((t) => [t.self?.yoy_cv ?? 0, t.covered?.yoy_cv ?? 0]),
  ];
  const max = Math.max(...all, 0.1) * 1.05;
  return (
    <SicCard>
      <Eyebrow>New York, 2015 to 2024</Eyebrow>
      <h3 className="font-serif text-lg font-bold text-cobalt">How much liability cost jumps around from year to year</h3>
      <Sub>Median swing in cost per resident, by how the government finances liability. Governments whose arrangement was read from their audited statements.</Sub>
      <div className="mt-4 grid gap-x-8 gap-y-2 sm:grid-cols-2">
        <div>
          <div className="mb-2 text-xs font-semibold text-charcoal">By type of government</div>
          {classes.map((c) => (
            <Pair key={c} label={CLASS_LABEL[c] ?? c} self={v.by_class[c].yoy_cv_self} covered={v.by_class[c].yoy_cv_covered} max={max}
              nSelf={v.by_class[c].n_self} nCovered={v.by_class[c].n_covered} />
          ))}
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold text-charcoal">Governments with police, by share of budget spent on police</div>
          {(["low", "mid", "high"] as const).filter((k) => terc[k]).map((k) => (
            <Pair key={k} label={`${k === "low" ? "Lower" : k === "mid" ? "Middle" : "Higher"} third (about ${pct(terc[k].self?.police_share ?? terc[k].covered?.police_share)} of spending on police)`}
              self={terc[k].self?.yoy_cv ?? null} covered={terc[k].covered?.yoy_cv ?? null} max={max} nSelf={terc[k].self?.n} nCovered={terc[k].covered?.n} />
          ))}
        </div>
      </div>
      <p className="mt-2 text-xs text-steel">Swing = standard deviation of a government's yearly cost per resident divided by its average, over the window; bars show the median government in each group. Villages and cities have few covered comparators (see the methodology).</p>
    </SicCard>
  );
}
