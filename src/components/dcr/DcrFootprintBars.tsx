// DcrFootprintBars — the concentration exhibit (<dcr-footprint-bars />).
//
// Ranked bars of data center electricity use by state, 2024, from the same
// EPRI footprint block the map's rings use (actions.json — one source of
// truth, no second data file). Virginia is the highlighted entity; the point
// of the chart is the cliff after the top two and how much of the country
// barely registers.

import { useEffect, useState } from "react";
import { BASEMAP, type ActionsData } from "@/config/dataCenterRestrictionCost";

let cache: Promise<ActionsData> | null = null;
function loadActions(): Promise<ActionsData> {
  if (!cache) {
    cache = fetch(BASEMAP.actionsUrl).then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  return cache;
}

interface Row {
  key: string;
  label: string;
  twh: number;
  twh30: number | null;
  highlight: boolean;
  aggregate: boolean;
}

export default function DcrFootprintBars() {
  const [data, setData] = useState<ActionsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadActions().then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <div className="my-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Couldn't load the footprint data ({error}).
      </div>
    );
  }
  if (!data?.footprint) return null;

  const fp = data.footprint;
  const nameByFips: Record<string, string> = {};
  for (const [fips, s] of Object.entries(data.state_status)) nameByFips[fips] = s.name;

  const states = Object.entries(fp.states)
    .filter(([, s]) => s.twh_2024 != null)
    .map(([fips, s]) => ({ fips, abbr: s.abbr, twh: s.twh_2024 as number, twh30: s.twh_2030_medium }))
    .sort((a, b) => b.twh - a.twh);
  const total = states.reduce((acc, s) => acc + s.twh, 0);
  const TOP = 10;
  const top = states.slice(0, TOP);
  const restTwh = total - top.reduce((acc, s) => acc + s.twh, 0);

  const rows: Row[] = [
    ...top.map((s) => ({
      key: s.abbr,
      label: nameByFips[s.fips] ?? s.abbr,
      twh: s.twh,
      twh30: s.twh30,
      highlight: s.abbr === "VA",
      aggregate: false,
    })),
    {
      key: "rest",
      label: `All other ${states.length - TOP} states`,
      twh: restTwh,
      twh30: null,
      highlight: false,
      aggregate: true,
    },
  ];
  const max = Math.max(...rows.map((r) => r.twh));
  const vaShare = Math.round((rows[0].twh / total) * 100);

  return (
    <div className="not-prose my-8 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      <h4 className="font-sans text-[11px] font-semibold uppercase tracking-[0.09em] text-steel">
        Where the electricity goes
      </h4>
      <p className="mb-4 mt-0.5 text-[12px] leading-snug text-steel">
        Data center electricity use by state, 2024. Hover a bar for EPRI's 2030 medium-scenario projection.
      </p>
      <div className="space-y-1.5">
        {rows.map((r) => (
          <div key={r.key} title={r.twh30 ? `${r.twh30} TWh by 2030 in EPRI's medium scenario` : undefined}>
            <div className="flex items-baseline justify-between gap-2">
              <span
                className={
                  "truncate text-[12px] " +
                  (r.highlight ? "font-bold text-charcoal" : r.aggregate ? "text-steel" : "font-semibold text-charcoal")
                }
              >
                {r.label}
              </span>
              <span className="shrink-0 font-sans text-[12px] font-semibold tabular-nums text-charcoal">
                {r.twh >= 10 ? Math.round(r.twh) : r.twh.toFixed(1)} TWh
              </span>
            </div>
            <div className="mt-0.5 h-2.5 w-full overflow-hidden rounded-sm bg-slate-100">
              <div
                className="h-2.5 rounded-sm"
                style={{
                  width: `${Math.max((r.twh / max) * 100, 1)}%`,
                  backgroundColor: r.highlight ? "#1F1FD6" : r.aggregate ? "#D8DCE6" : "#AEB9D6",
                }}
              />
            </div>
            {r.highlight && (
              <div className="mt-0.5 text-[10.5px] leading-snug text-steel">
                {vaShare}% of the national total, more than the bottom thirty-five states combined. Most of it is
                Northern Virginia.
              </div>
            )}
          </div>
        ))}
      </div>
      <p className="mt-3 text-[10.5px] text-steel">
        Source: EPRI, Powering Intelligence 2026, state-level dashboard (2024 historical estimates). National total:{" "}
        {Math.round(total)} TWh, about 4 to 5 percent of all US electricity.
      </p>
    </div>
  );
}
