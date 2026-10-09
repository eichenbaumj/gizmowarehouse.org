// SicMixBars — <sic-mix-bars></sic-mix-bars>
//
// Where the money goes, by structure: median dollars per resident spent on premiums vs on judgments
// and claims, for the document-labeled counties and cities in the comparison. HTML/CSS bars in the
// DcrFootprintBars idiom. The point is that the totals land close while the mix flips.

import { STRUCTURE_STYLE, type NyEntitiesData } from "@/config/selfInsuranceCost";
import { useSicData, SicCard, Eyebrow, Loading, Err, fmtMoney } from "./useSicData";

export default function SicMixBars() {
  const { data, err } = useSicData<NyEntitiesData>("ny_entities");
  if (err) return <Err msg={err} />;
  if (!data) return <Loading h={200} />;
  // counties only: the tested class (every large city self-insures, so a city median would mix size into the picture)
  const sum = data.summary_by_class?.county ?? {};
  const groups = (["self", "covered"] as const).filter((t) => sum[t]);
  const max = Math.max(...groups.map((t) => sum[t]!.median_cor_pc), 1);
  return (
    <SicCard>
      <Eyebrow>Median dollars per resident per year, {data.window[0]} to {data.window[1]}, New York counties with a documented arrangement</Eyebrow>
      <h3 className="font-serif text-lg font-bold text-cobalt">Same money, different line</h3>
      <div className="mt-4 space-y-4">
        {groups.map((t) => {
          const s = sum[t]!;
          const prem = s.median_ins_pc, jc = s.median_jc_pc, tot = s.median_cor_pc;
          const wP = (prem / max) * 100, wJ = (jc / max) * 100;
          return (
            <div key={t}>
              <div className="mb-1 flex items-baseline justify-between text-sm">
                <span className="font-semibold text-charcoal">{STRUCTURE_STYLE[t].label} <span className="font-normal text-steel">({s.n})</span></span>
                <span className="text-charcoal">{fmtMoney(tot)} per resident</span>
              </div>
              <div className="flex h-7 w-full overflow-hidden rounded-md bg-vellum">
                <div title={`premiums ${fmtMoney(prem)}`} style={{ width: `${wP}%`, background: STRUCTURE_STYLE[t].color, opacity: 0.45 }} />
                <div style={{ width: 2, background: "#fff" }} />
                <div title={`judgments and claims ${fmtMoney(jc)}`} style={{ width: `${wJ}%`, background: STRUCTURE_STYLE[t].color }} />
              </div>
              <div className="mt-1 flex gap-4 text-xs text-steel">
                <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: STRUCTURE_STYLE[t].color, opacity: 0.45 }} />insurance premiums {fmtMoney(prem)}</span>
                <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: STRUCTURE_STYLE[t].color }} />judgments and claims {fmtMoney(jc)}</span>
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-steel">Medians of each group's county averages. The two bars for a group do not add to its total because each median is taken separately. Premiums include property and other lines. Judgments are cash paid in the year. Cities are left out here because every large one carries its own liability.</p>
    </SicCard>
  );
}
