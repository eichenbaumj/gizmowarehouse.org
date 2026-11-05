// Static stand-ins for the hs-* tags: plain HTML a crawler can read, every number from the same public
// JSON the live components use. Merged into src/content/embeds.static.tsx at publish; until then used by
// the gizmo-local tests only. No browser APIs, no MapLibre. Children pass through so the prose stays.
import type { ComponentType, ReactNode } from "react";
import stops from "../../../public/data/hoyt-schermerhorn-crime-analysis/stops.json";
import ladder from "../../../public/data/hoyt-schermerhorn-crime-analysis/ladder.json";
import ribbon from "../../../public/data/hoyt-schermerhorn-crime-analysis/ribbon.json";
import clock from "../../../public/data/hoyt-schermerhorn-crime-analysis/clock.json";
import density from "../../../public/data/hoyt-schermerhorn-crime-analysis/density.json";
import improvers from "../../../public/data/hoyt-schermerhorn-crime-analysis/improvers.json";
import precincts from "../../../public/data/hoyt-schermerhorn-crime-analysis/precincts_1990.json";
import timelapse from "../../../public/data/hoyt-schermerhorn-crime-analysis/timelapse.json";
import sankey from "../../../public/data/hoyt-schermerhorn-crime-analysis/sankey.json";
import { CLASS_ORDER, CLASS_STYLE, DOWNLOADS } from "@/config/hoytSchermerhorn";

function Figure({ id, caption, children }: { id: string; caption: string; children?: ReactNode }) {
  return <figure data-static-embed={id} className="my-6">{children}<figcaption className="text-sm text-steel mt-2">{caption}</figcaption></figure>;
}
function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return <table><thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table>;
}
const pct = (v: number) => `${Math.round(v * 100)}%`;
const L = ladder as any; const D = density as any; const I = improvers as any; const P = precincts as any; const T = timelapse as any; const S = sankey as any;

const ScrollyStatic: ComponentType<{ stage?: string; children?: ReactNode }> = ({ children }) => (
  <Figure id="hs-scrolly-city" caption={`Interactive map in the browser: every 0.33-mile cell in New York City, violent complaints 2024 to 2025. Half of the city's violent complaints sit in ${I.concentration.cells_for_half} of its ${I.concentration.n_cells} cells. Downtown Brooklyn's cell ranks #${L.primary.all.rank} by count, #${D.ranks.residents.rank} per resident, #${D.ranks.jobs.rank} per job, #${D.ranks.residents_plus_jobs.rank} per resident plus job.`}>
    <Table head={["Cell", "Violent complaints 2024 to 2025", "Rank"]} rows={L.top20.slice(0, 10).map((t: any) => [t.name, t.count, t.rank])} />
    {children}
  </Figure>
);
const ExploreStatic: ComponentType = () => <p data-static-embed="hs-city-explore">Interactive map in the browser: pan and zoom the 2,854 map cells; hover for a cell's name, count and rank.</p>;
const StepStatic: ComponentType<{ step?: string; children?: ReactNode }> = ({ step, children }) => <section data-step={step}>{children}</section>;
const DraftStatic: ComponentType<{ id?: string; children?: ReactNode }> = ({ children }) => <p>{children}</p>;
const PhotoStatic: ComponentType<{ photo?: string }> = ({ photo }) => <p data-static-embed="hs-photo">Photograph: {photo}.</p>;
const TimelapseStatic: ComponentType<{ children?: ReactNode }> = ({ children }) => (
  <Figure id="hs-timelapse" caption={`Interactive time-lapse in the browser: every complaint within 400 m of Hoyt-Schermerhorn in ${T.month}/${T.year}: ${T.counts.violent} violent, ${T.counts.petit_larceny} petit larcenies, ${T.counts.grand_larceny} grand larcenies, ${T.counts.misd_assault} misdemeanor assaults.`}>{children}</Figure>
);
const HourBarsStatic: ComponentType = () => {
  const n = (clock as any).night;
  return <Figure id="hs-hour-bars" caption={`Share of violent complaints by hour, this block vs the city, placeholder times excluded. Night (10pm to 6am): block ${pct(n.core400.share)}, city ${pct(n.city.share)}.`}>
    <Table head={["Hour", "This block", "City"]} rows={(clock as any).hour_share.core400_clean.map((v: number, h: number) => [h, pct(v), pct((clock as any).hour_share.city_clean[h])])} />
  </Figure>;
};
const WeekStatic: ComponentType = () => <p data-static-embed="hs-week">Weekday-by-hour grid of this block's violent complaints since 2006 (darkest cell {(clock as any).week_max.core400}); weekday share printed against the city's.</p>;
const PrecinctStatic: ComponentType = () => (
  <Figure id="hs-precinct-strip" caption={`Change in murder, robbery and felony assault by precinct, 1990 to 2025, from NYPD CompStat historical tables (${P.n_precincts} precincts). City murders ${P.city.murder_1990} in 1990, ${P.city.murder_2025} in 2025.`}>
    <Table head={["Precinct", "1990", "2025", "Change"]} rows={P.summary.slice(0, 10).map((r: any) => [r.precinct, r.violent_1990, r.violent_2025, `${r.change_pct}%`])} />
  </Figure>
);
const RateMapStatic: ComponentType = () => <p data-static-embed="hs-rate-map">Interactive map in the browser: every cell with 500 or more residents, shaded by violent complaints per 1,000 residents per year, 2024 to 2025. This cell: {D.ranks.residents.rate_per_1000_per_year} per 1,000 a year, #{D.ranks.residents.rank} of {D.ranks.residents.n_cells}.</p>;
const SiteMapStatic: ComponentType = () => <p data-static-embed="hs-site-map">Map of the cell with its four sites numbered: the store, the plaza, the subway entrance and the courthouse, inside the 400 m circle around the station.</p>;
const SankeyStatic: ComponentType = () => (
  <Figure id="hs-sankey" caption={`Where the ${S.total} violent complaints of 2024 to 2025 within 400 m were recorded, by place and type.`}>
    <Table head={["Place", "Type", "Complaints"]} rows={S.flows.map((f: any) => [f.place, (CLASS_STYLE as any)[f.cls]?.short ?? f.cls, f.n])} />
  </Figure>
);
const LinesStatic: ComponentType = () => {
  const g = (ribbon as any).geos.core400;
  return <Figure id="hs-lines" caption="Violent complaints per year within 400 m of the station. 2026 is January through June.">
    <Table head={["Year", ...CLASS_ORDER.filter((c) => CLASS_STYLE[c].drawn).map((c) => CLASS_STYLE[c].short), "All"]} rows={g.years.map((y: string, i: number) => [y, ...CLASS_ORDER.filter((c) => CLASS_STYLE[c].drawn).map((c) => g.by_class[c][i]), g.all[i]])} />
  </Figure>;
};
const RibbonStatic: ComponentType<{ window?: string }> = () => {
  const p = (ribbon as any).h1.panels;
  return <Figure id="hs-ribbon-h1" caption="January to June, complaints reported by June 30 of each year.">
    <Table head={["Series", "2024", "2025", "2026"]} rows={Object.keys(p).map((k) => [k, p[k]["2024"], p[k]["2025"], p[k]["2026"]])} />
  </Figure>;
};
const LedgerStatic: ComponentType<{ stop?: string }> = ({ stop }) => {
  const s = (stops as any).stops.find((x: any) => x.id === stop || x.label.toLowerCase().includes(String(stop).toLowerCase()));
  return <p data-static-embed="hs-ledger">{s ? `${s.label}: ${s.totals["2024_25"]} violent complaints in 2024 to 2025, ${s.totals.all} since 2006.` : `Ledger: ${stop}.`}</p>;
};
const LadderStatic: ComponentType = () => <p data-static-embed="hs-rank-ladder">Citywide rank of this cell, 2024 to 2025: #{L.primary.all.rank} on all violent complaints, #{L.primary.no_courthouse.rank} without the courthouse point at 120 Schermerhorn, of {L.n_cells.toLocaleString()} cells.</p>;
const MethodsStatic: ComponentType = () => <p data-static-embed="hs-methods-note">Locations are NYPD-rounded points, not addresses. 2026 covers January through June. Placeholder times are excluded from hour-of-day views.</p>;
const DownloadsStatic: ComponentType = () => <ul data-static-embed="hs-downloads">{DOWNLOADS.map((d) => <li key={d.url}><a href={d.url}>{d.label}</a></li>)}</ul>;

export const hoytEmbedsStatic: Record<string, ComponentType<any>> = {
  "hs-scrolly": ScrollyStatic, "hs-city-explore": ExploreStatic, "hs-step": StepStatic, "hs-draft": DraftStatic, "hs-photo": PhotoStatic, "hs-timelapse": TimelapseStatic,
  "hs-hour-bars": HourBarsStatic, "hs-week": WeekStatic, "hs-precinct-strip": PrecinctStatic, "hs-precinct-map": PrecinctStatic, "hs-rate-map": RateMapStatic, "hs-site-map": SiteMapStatic, "hs-sankey": SankeyStatic, "hs-lines": LinesStatic,
  "hs-ribbon": RibbonStatic, "hs-ledger": LedgerStatic, "hs-rank-ladder": LadderStatic, "hs-methods-note": MethodsStatic, "hs-downloads": DownloadsStatic,
};
