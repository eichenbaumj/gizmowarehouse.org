// Rank chip and ladder, ledger card, methods note.
import { useEffect, useState } from "react";
import { CLASS_ORDER, CLASS_STYLE, N_CELLS, SITES, STEEL, type ClockFile, type DqFile, type LadderFile, type RadiusDef, type Stop, type StopsFile } from "@/config/hoytSchermerhorn";
import { useCountUp } from "@/hooks/useCountUp";
import { claimOk, fmtInt, hourLabel, useHoytData } from "./hoytData";
import { Card, Eyebrow } from "./HoytChrome";
import { HoytSiteMap } from "./HoytSiteMap";
import { HoytHourStrip } from "./HoytStrips";

const DEF_LABEL: Record<RadiusDef, string> = { all: "All violent complaints", no_officer: "Without assaults on officers", no_officer_no_retail: "Without officer assaults and store robberies", no_courthouse: "Without the courthouse point" };

export function HoytRankChip({ def }: { def: RadiusDef }) {
  const { data: ladder } = useHoytData<LadderFile>("ladder");
  const { data: dq } = useHoytData<DqFile>("dq");
  const rank = ladder?.primary[def].rank ?? 0;
  const shown = useCountUp(rank, 500);
  if (!ladder) return null;
  if (!claimOk(dq, "claim_7")) return <div className="rounded-full bg-white/95 px-3 py-1.5 font-sans text-xs font-semibold text-steel shadow ring-1 ring-slate-200">Rank UNVERIFIED</div>;
  return (
    <div className="rounded-xl bg-white/95 px-4 py-2 shadow ring-1 ring-slate-200">
      <div className="font-sans text-[11px] font-semibold uppercase tracking-[0.09em]" style={{ color: STEEL }}>{DEF_LABEL[def]}</div>
      <div className="font-serif text-3xl font-bold text-cobalt">#{shown}<span className="ml-2 font-sans text-sm font-normal text-steel">of {fmtInt(ladder.n_cells)} cells</span></div>
    </div>
  );
}

export function HoytRankLadder({ compact = false }: { compact?: boolean }) {
  const { data: ladder } = useHoytData<LadderFile>("ladder");
  const { data: dq } = useHoytData<DqFile>("dq");
  if (!ladder) return null;
  if (!claimOk(dq, "claim_7") || !ladder.ladder_ok) return <div className="font-sans text-sm text-steel">Rank ladder withheld (claim not verified).</div>;
  // The piece's argument is one address: the full count, then the same cell with 120 Schermerhorn set aside.
  const defs: RadiusDef[] = ["all", "no_courthouse"];
  return (
    <div className={`not-prose my-6 grid gap-3 ${compact ? "grid-cols-2" : "grid-cols-1 sm:grid-cols-2"}`}>
      {defs.map((d) => (
        <div key={d} className="rounded-xl bg-white/95 px-4 py-3 shadow ring-1 ring-slate-200">
          <div className="font-sans text-[11px] font-semibold uppercase tracking-[0.09em]" style={{ color: STEEL }}>{DEF_LABEL[d]}</div>
          <div className="font-serif text-3xl font-bold text-cobalt">#{ladder.primary[d].rank}</div>
          <div className="font-sans text-xs text-steel">{fmtInt(ladder.primary[d].count)} complaints, 2024 to 2025 · of {fmtInt(N_CELLS)} cells</div>
        </div>
      ))}
    </div>
  );
}

export function HoytLedgerCard({ stop: stopId = "", capturedHour }: { stop?: string; capturedHour?: number }) {
  const { data } = useHoytData<StopsFile>("stops");
  const stop = data?.stops.find((s) => s.id === stopId || s.label.toLowerCase().includes(stopId.toLowerCase()));
  if (!stop) return <Card><Eyebrow>Ledger</Eyebrow><div className="font-sans text-sm text-steel">No point matched "{stopId}".</div></Card>;
  const rec = stop.totals["2024_25"];
  const site = SITES.find((x) => x.id === stop.id);
  const two = (b: Record<string, number> | null | undefined) => (b ? (b["2024"] ?? 0) + (b["2025"] ?? 0) : null);
  const pl = two(stop.petit_larceny_by_year); const ma = two(stop.misd_assault_by_year);
  return (
    <Card className="not-prose my-4">
      <Eyebrow>{site ? `${site.name} · ` : ""}{stop.label}{stop.label_status === "unverified" ? " · nearest label, unverified" : ""}</Eyebrow>
      <div className={site ? "grid grid-cols-1 gap-4 sm:grid-cols-[1fr_200px]" : ""}>
      <div className="grid grid-cols-2 gap-3 font-sans">
        <Stat label="Violent complaints, 2024 to 2025" value={fmtInt(rec)} />
        <Stat label="Since 2006" value={fmtInt(stop.totals.all)} />
        {stop.shoplift_origin_share_2024_25 != null && <Stat label="Robberies that began as shoplifting" value={`${Math.round(stop.shoplift_origin_share_2024_25 * 100)}%`} note="Share of this point's 2024 to 2025 robberies that NYPD coded as a shoplifting that turned into a robbery, usually at the door" />}
        {ma != null && <Stat label="Misdemeanor assaults, 2024 to 2025" value={fmtInt(ma)} />}
        {pl != null && <Stat label="Petit larcenies, 2024 to 2025" value={fmtInt(pl)} />}
        {stop.peak_hour != null && <Stat label="Busiest hour" value={hourLabel(stop.peak_hour)} />}
      </div>
      {site && <div className="self-start"><HoytSiteMap focus={stop.id} size="mini" /><div className="mt-1 font-sans text-[11px] text-steel">This point on the map.</div></div>}
      </div>
      <div className="mt-3">
        <HoytHourStrip hist={stop.hour_hist_clean} tick={capturedHour} height={36} />
      </div>
      <div className="mt-2 font-sans text-xs text-steel">
        <span className="font-semibold text-charcoal">The {fmtInt(rec)} violent complaints of 2024 to 2025, by type:</span>{" "}
        {CLASS_ORDER.filter((c) => CLASS_STYLE[c].drawn && stop.by_class_2024_25[c] > 0).map((c, i, arr) => (
          <span key={c}><span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: CLASS_STYLE[c].color }} />{stop.by_class_2024_25[c]} {CLASS_STYLE[c].label.toLowerCase()}{i < arr.length - 1 ? ", " : "."}</span>
        ))}
      </div>
      <div className="mt-2 font-sans text-xs text-steel">One rounded point on this block, not an address. <a className="underline" href={stop.street_view_url} target="_blank" rel="noreferrer">Open this corner in Street View</a></div>
    </Card>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <div className="font-serif text-2xl font-bold text-charcoal">{value}</div>
      <div className="text-xs text-steel">{label}</div>
      {note && <div className="mt-0.5 text-[11px] leading-snug text-steel/80">{note}</div>}
    </div>
  );
}

export function HoytMethodsNote() {
  const { data: dq } = useHoytData<DqFile>("dq");
  const { data: clock } = useHoytData<ClockFile>("clock");
  const { data: ctx } = useHoytData<any>("context");
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { /* keep hook order stable */ }, []);
  const warns = dq?.tests.filter((t) => t.status === "warn" && t.footnote) ?? [];
  const claimNotes = dq ? Object.entries(dq.claims).flatMap(([id, c]) => c.footnotes.map((f) => ({ id, f }))) : [];
  const dts = clock?.default_time_share?.core400 ? Object.values(clock.default_time_share.core400) : [];
  const dtShare = dts.length ? (dts.slice(-3).reduce((a, b) => a + b, 0) / Math.min(3, dts.length)) : null;
  return (
    <Card className="not-prose my-8">
      <button type="button" className="flex w-full items-center justify-between text-left" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
        <span className="font-serif text-xl font-bold text-cobalt">Methodology</span>
        <span className="font-sans text-sm font-semibold text-cobalt">{expanded ? "Hide" : "Show"}</span>
      </button>
      {!expanded && <div className="mt-1 font-sans text-sm text-steel">Definitions, caveats and the {dq?.tests.length ?? 0}-test data-quality audit behind every number on this page.</div>}
      {expanded && <>
      <ul className="mt-3 list-disc space-y-1.5 pl-5 font-sans text-[15px] leading-relaxed text-charcoal">
        <li>"Complaint" is NYPD's term for a reported or recorded crime, one incident per record (the NYPD Complaint Data on NYC Open Data). It is not a 311 service request.</li>
        <li>Each complaint sits at a point NYPD rounds to a midblock or intersection, never an address. The maps draw one dot per rounded point, sized by how many complaints sit on it; the ledgers show only points with three or more.</li>
        <li>2026 covers January through June only. First-half comparisons count complaints reported by June 30 of each year, because the newest files hold no late reports.</li>
        {dtShare != null && <li>About {Math.round(dtShare * 100)} percent of complaints here carry a placeholder time of midnight or noon; hour-of-day views leave those out.</li>}
        <li>Hours at the courthouse point are when complaints were recorded, not when anything happened.</li>
        {ctx?.improvers && <li>Every "since {ctx.improvers.year_early}" figure compares {ctx.improvers.year_early} with {ctx.improvers.year_late} and counts only offense codes that existed in {ctx.improvers.year_early}. New York made strangulation a felony in November 2010 ({ctx.improvers.strangulation_2025.toLocaleString()} complaints in {ctx.improvers.year_late}) and added three assault codes for public employees in 2017. With those codes included, felony assault citywide is up {ctx.improvers.city_fel_assault_change_pct_raw} percent rather than {ctx.improvers.city_fel_assault_change_pct}, the city total {ctx.improvers.city_change_pct_raw_round > 0 ? "up " + ctx.improvers.city_change_pct_raw_round : "down " + Math.abs(ctx.improvers.city_change_pct_raw_round)} percent rather than {ctx.improvers.city_change_pct_round > 0 ? "up " + ctx.improvers.city_change_pct_round : "down " + Math.abs(ctx.improvers.city_change_pct_round)}, and the 84th Precinct up {ctx.improvers.p84_change_pct_raw} rather than {ctx.improvers.p84_change_pct}. A cell is named among the biggest declines only if its three-year averages ({ctx.improvers.year_early} to {ctx.improvers.year_early + 2} against {ctx.improvers.year_late - 2} to {ctx.improvers.year_late}) also fell by at least 60 percent. The 1990 to {ctx.improvers.year_late} precinct figures are NYPD's own and include every code.</li>}
        {ctx?.opening && <li>The large-city robbery comparison uses each police department's year-end 2025 count from the Major Cities Chiefs Association survey (New York's from the NYPD year-end release) over Census Bureau 2025 population estimates, for cities over 550,000 people with a published count; Jacksonville, Charlotte and Washington could not be matched. New York: {ctx.opening.robbery_rate_2025_per_100k} robberies per 100,000, {ctx.opening.robbery_rank_2025}th of {ctx.opening.robbery_rank_of}.</li>}
        {ctx?.opening && <li>The 1990 counts ({ctx.opening.murders_1990.toLocaleString()} murders, {ctx.opening.robberies_1990.toLocaleString()} robberies) are the sum of NYPD's CompStat precinct tables, which matches NYPD's citywide totals for that year. "One for every {ctx.opening.residents_per_robbery_1990} residents" divides robberies by the 1990 census population of 7,322,564; some people were robbed more than once, so it is not the share of New Yorkers who were robbed. The 1990 ranking uses the FBI's Uniform Crime Reports (Jacob Kaplan's compilation, openICPSR 100707) for the {ctx.opening.robbery_rank_1990_of} city police departments serving more than 550,000 people, the same cutoff as the 2025 comparison: New York at {ctx.opening.robbery_rate_1990_per_100k.toLocaleString()} robberies per 100,000, then {ctx.opening.robbery_runner_up_1990} at {ctx.opening.robbery_runner_up_1990_per_100k.toLocaleString()}. Some smaller cities, Miami, Newark and Atlanta among them, had higher rates.</li>}
        {ctx?.opening && <li>"About as safe as it has ever been": 2025 set the record low for shooting incidents ({ctx.opening.shootings_2025.toLocaleString()}); its {ctx.opening.murders_2025} murders are the third-lowest year on record, after {ctx.opening.lowest_murder_count} in {ctx.opening.lowest_murder_year} and 295 in 2018.</li>}
        {warns.map((t) => <li key={t.id}>{t.footnote}</li>)}
        {claimNotes.map((n, i) => <li key={i}>{n.f}</li>)}
      </ul>
      <button className="mt-3 font-sans text-sm font-semibold text-cobalt" onClick={() => setOpen((o) => !o)}>{open ? "Hide" : "Show"} the full audit ({dq?.tests.length ?? 0} tests)</button>
      {open && dq && (
        <table className="mt-3 w-full font-sans text-xs">
          <tbody>
            {dq.tests.map((t) => (
              <tr key={t.id} className="border-t border-slate-100 align-top">
                <td className="py-1 pr-2 font-semibold">{t.id}</td>
                <td className="py-1 pr-2 uppercase text-steel">{t.status}</td>
                <td className="py-1">{t.title}: {t.reading}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      </>}
    </Card>
  );
}
