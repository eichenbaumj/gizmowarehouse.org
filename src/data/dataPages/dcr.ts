// Data-center restrictions: one page per state and one per jurisdiction, from
// the actions dataset behind "Pricing the Fear of Data Centers".
import type { DataPage, DataSection, DatasetSpec, Cell } from "./types";
import { STATE_NAMES, article, listJoin, longDate, n0, plural, slugify, stateSlug, uniqueSlugs } from "./util";

export const DCR_PARENT = "data-center-restriction-cost";
const BASE = `/gizmo/${DCR_PARENT}`;
export const DCR_FILES = {
  rows: `/data/${DCR_PARENT}/actions-rows.json`,
  actions: `/data/${DCR_PARENT}/actions.json`,
  outcomes: `/data/${DCR_PARENT}/outcomes.json`,
  benchmarks: `/data/${DCR_PARENT}/benchmarks.json`,
};

export interface ActionRow {
  id: string;
  dataset: string;
  level: "local" | "state" | "puc";
  state: string;
  state_fips: string;
  jurisdiction: string;
  jurisdiction_type: string;
  action_type: string;
  class: string;
  status: string;
  date: string;
  mw_threshold: string;
  county_fips: string;
  county_name: string;
  county_wide: string;
  summary: string;
  source_name: string;
  source_url: string;
  note: string;
}

interface ActionsMeta {
  snapshot_date: string;
  sources: { id: string; name: string; url: string; license: string }[];
  counts: Record<string, number | string>;
  state_status: Record<string, { abbr: string; name: string; status: string; tariff: string | null; action_ids: string[] }>;
  footprint: { source: string; source_url: string; year: number; projection: string; states: Record<string, { abbr: string; twh_2024: number; twh_2030_medium: number }> };
}
interface Outcomes {
  snapshot_date: string;
  tally: Record<string, number>;
  projects: { id: string; name: string; developer: string; jurisdiction: string; state: string; claimed_capex_usd_b: number | null; mw: number | null; decision_date: string; outcome: string; destination: string | null; months_lost: number | null; note: string }[];
}
interface Benchmarks {
  snapshot_date: string;
  horizon_years: number;
  jobs_per_facility_permanent: number;
  regimes: { id: string; case: string; annual_local_usd_m_low: number; annual_local_usd_m_high: number; note: string }[];
  reference_campus: { name: string; capex_usd_b: number; mw: number; local_10yr_usd_m: number; note: string };
}

export const ACTION_LABEL: Record<string, string> = {
  moratorium: "moratorium",
  zoning_exclusion: "zoning exclusion",
  ordinance_conditions: "conditions ordinance",
  ratepayer_law: "ratepayer-protection law",
  large_load_tariff: "large-load tariff",
  incentive_rollback: "incentive rollback",
  tax_action: "tax action",
  ban: "ban",
  executive_order: "executive order",
  preemption: "state preemption",
  project_rejection: "project rejection",
};
const STATUS_LABEL: Record<string, string> = {
  in_force: "in force",
  enacted: "enacted",
  pending: "pending",
  replaced: "replaced",
  expired: "expired",
  vetoed: "vetoed",
};
const label = (m: Record<string, string>, k: string) => m[k] ?? k.replace(/_/g, " ");
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/**
 * Source jurisdiction strings are messy: "Woodland Park (city)", "Surprise
 * (Maricopa County)", "Maricopa County Board of Supervisors (Project Baccara
 * ... permit), AZ". Keep the body the jurisdiction is named for; the detail
 * survives verbatim in the record's own summary.
 */
export function cleanName(j: string): string {
  let s = j.trim();
  s = s.replace(/,\s*[A-Z]{2}\s*$/, ""); // trailing ", AZ"
  while (/\s*\([^()]*\)\s*$/.test(s)) s = s.replace(/\s*\([^()]*\)\s*$/, ""); // trailing parentheticals
  s = s.replace(/\s*-\s*(?:city|town|village|township|borough)\s*$/i, "");
  return s.trim() || j.trim();
}

function jurisdictionSlug(j: string): string {
  return slugify(cleanName(j)) || slugify(j);
}

function rowSentence(r: ActionRow, stateName: string): string {
  const what = r.class === "condition" ? "a data-center conditions measure" : `a data-center ${label(ACTION_LABEL, r.action_type)}`;
  const when = r.date ? ` on ${longDate(r.date)}` : "";
  const county = r.county_name && r.jurisdiction_type !== "county" ? `, in ${r.county_name}` : "";
  const status = label(STATUS_LABEL, r.status);
  return `${cleanName(r.jurisdiction)}${county}, ${stateName}, adopted ${what}${when}. Its status in this snapshot is ${status}.`;
}

export function buildDcrPages(files: Record<string, unknown>): DataPage[] {
  const rows = files[DCR_FILES.rows] as ActionRow[];
  const meta = files[DCR_FILES.actions] as ActionsMeta;
  const outcomes = files[DCR_FILES.outcomes] as Outcomes;
  const bench = files[DCR_FILES.benchmarks] as Benchmarks;
  if (!rows || !meta || !outcomes || !bench) return [];

  const snapshot = meta.snapshot_date;
  const sources = meta.sources.map((s) => ({ name: s.name, href: s.url }));
  const parentTitle = "Pricing the Fear of Data Centers";
  const crumbsBase = [
    { name: "Gizmo Warehouse", path: "/" },
    { name: parentTitle, path: BASE },
    { name: "Restrictions tracker", path: `${BASE}/tracker` },
  ];
  const payRange = `$${Math.min(...bench.regimes.map((r) => r.annual_local_usd_m_low))}M to $${Math.max(...bench.regimes.map((r) => r.annual_local_usd_m_high))}M a year`;

  // Group rows by state, then by jurisdiction.
  const byState = new Map<string, ActionRow[]>();
  for (const r of rows) byState.set(r.state, [...(byState.get(r.state) ?? []), r]);

  const pages: DataPage[] = [];
  const stateRows: Cell[][] = [];

  for (const [abbr, srows] of [...byState.entries()].sort((a, b) => (STATE_NAMES[a[0]] ?? a[0]).localeCompare(STATE_NAMES[b[0]] ?? b[0]))) {
    const stateName = STATE_NAMES[abbr] ?? abbr;
    const sSlug = stateSlug(abbr);
    const statePath = `${BASE}/state/${sSlug}`;
    const local = srows.filter((r) => r.level === "local");
    const statewide = srows.filter((r) => r.level !== "local");
    const status = Object.values(meta.state_status).find((s) => s.abbr === abbr);
    const fp = Object.values(meta.footprint.states).find((s) => s.abbr === abbr);
    const projects = outcomes.projects.filter((p) => p.state === abbr);

    // Jurisdiction pages (group multi-action jurisdictions).
    const jurKey = (r: ActionRow) => `${cleanName(r.jurisdiction)}|${r.jurisdiction_type}|${r.county_fips}`;
    const byJur = new Map<string, ActionRow[]>();
    for (const r of local) byJur.set(jurKey(r), [...(byJur.get(jurKey(r)) ?? []), r]);
    const jurs = [...byJur.keys()].sort((a, b) => a.localeCompare(b));
    const jSlugs = uniqueSlugs(jurs, (k) => jurisdictionSlug(k.split("|")[0]));
    const jurPath = (j: string) => `${BASE}/${sSlug}/${jSlugs.get(j)}`;
    const rowPath = (r: ActionRow) => jurPath(jurKey(r));

    const typeCounts = new Map<string, number>();
    const statusCounts = new Map<string, number>();
    for (const r of local) {
      typeCounts.set(r.action_type, (typeCounts.get(r.action_type) ?? 0) + 1);
      statusCounts.set(r.status, (statusCounts.get(r.status) ?? 0) + 1);
    }
    const typeText = listJoin([...typeCounts.entries()].sort((a, b) => b[1] - a[1]).map(([k, v]) => `${n0(v)} ${label(ACTION_LABEL, k)}${v === 1 ? "" : k === "moratorium" ? " (moratoria)" : "s"}`.replace(" moratorium (moratoria)", " moratoria")));
    const statusText = listJoin([...statusCounts.entries()].sort((a, b) => b[1] - a[1]).map(([k, v]) => `${n0(v)} ${label(STATUS_LABEL, k)}`));
    const countyCount = new Set(local.map((r) => r.county_fips || r.county_name)).size;

    const statewideText =
      statewide.length > 0
        ? `At the state level, ${listJoin(statewide.map((r) => `${cleanName(r.jurisdiction) === stateName || /statewide/i.test(r.jurisdiction) ? "the state" : cleanName(r.jurisdiction)} has ${article(label(ACTION_LABEL, r.action_type))} (${label(STATUS_LABEL, r.status)}${r.date ? `, ${longDate(r.date)}` : ""})`))}.`
        : `There is no statewide restriction, incentive rollback, or large-load tariff on record for ${stateName} in this snapshot${status?.status && status.status !== "none" ? ` beyond a state status of "${status.status.replace(/_/g, " ")}"` : ""}.`;

    const intro: string[] = [
      `As of ${longDate(snapshot)}, this tracker documents ${plural(local.length, "local government action")} on data centers in ${stateName}, across ${plural(byJur.size, "jurisdiction")}${countyCount > 1 ? ` in ${plural(countyCount, "county", "counties")}` : ""}${local.length ? `: ${typeText}. By status: ${statusText}.` : "."}`,
      statewideText,
    ];
    if (fp) {
      intro.push(
        `Data centers in ${stateName} used about ${fp.twh_2024.toFixed(1)} TWh of electricity in ${meta.footprint.year}; ${meta.footprint.source} projects ${fp.twh_2030_medium.toFixed(1)} TWh in its ${meta.footprint.projection}.`
      );
    }

    const sections: DataSection[] = [];
    if (statewide.length) {
      sections.push({
        heading: `Statewide actions in ${stateName}`,
        list: statewide.map((r) => ({
          text: `${cleanName(r.jurisdiction)}: ${label(ACTION_LABEL, r.action_type)}, ${label(STATUS_LABEL, r.status)}${r.date ? `, ${longDate(r.date)}` : ""}`,
          detail: `${r.summary.trim().replace(/\.?$/, ".")}${r.note ? ` ${r.note.trim().replace(/\.?$/, ".")}` : ""} Source: ${r.source_name}.`,
          href: r.source_url,
        })),
      });
    }
    if (local.length) {
      sections.push({
        heading: `Local actions in ${stateName}`,
        table: {
          head: ["Jurisdiction", "County", "Action", "Status", "Date"],
          rows: local
            .slice()
            .sort((a, b) => (b.date || "").localeCompare(a.date || "") || cleanName(a.jurisdiction).localeCompare(cleanName(b.jurisdiction)))
            .map((r) => [
              { text: cleanName(r.jurisdiction) + (r.jurisdiction_type === "county" && !/county|parish/i.test(r.jurisdiction) ? " County" : ""), href: rowPath(r) },
              r.county_name || "",
              cap(label(ACTION_LABEL, r.action_type)),
              label(STATUS_LABEL, r.status),
              r.date ? longDate(r.date) : "undated",
            ]),
          caption: `Every documented local action in ${stateName} in the ${longDate(snapshot)} snapshot. Documented actions, not a census.`,
        },
      });
    }
    if (projects.length) {
      sections.push({
        heading: `Blocked or delayed projects in ${stateName}`,
        table: {
          head: ["Project", "Jurisdiction", "Developer", "Outcome", "Decision", "Claimed capex"],
          rows: projects.map((p) => [p.name, p.jurisdiction, p.developer, p.outcome.replace(/_/g, " "), p.decision_date ? longDate(p.decision_date) : "", p.claimed_capex_usd_b != null ? `$${p.claimed_capex_usd_b}B` : ""]),
          caption: "From the outcome trace of large projects that hit a restriction: what happened next.",
        },
        list: projects.filter((p) => p.note).map((p) => ({ text: `${p.name}: ${p.note}` })),
      });
    }
    sections.push({
      heading: "What one campus pays a local government",
      paragraphs: [
        `The parent piece's calculator puts a single large campus at ${payRange} in local revenue, depending on the tax regime and abatements. The reference campus (${bench.reference_campus.name}: $${bench.reference_campus.capex_usd_b}B of capital, ${bench.reference_campus.mw} MW) pays about $${bench.reference_campus.local_10yr_usd_m}M to local governments over ${bench.horizon_years} years. Permanent jobs run around ${bench.jobs_per_facility_permanent} per facility.`,
      ],
      table: {
        head: ["Tax regime", "Reference case", "Annual local revenue, low", "Annual local revenue, high"],
        rows: bench.regimes.map((r) => [cap(r.id.replace(/_/g, " ")), r.case, `$${r.annual_local_usd_m_low}M`, `$${r.annual_local_usd_m_high}M`]),
      },
      note: `Run your own numbers in the calculator on the parent piece. Jurisdictions in ${stateName} that say no give up this revenue, not the jobs.`,
    });

    pages.push({
      path: statePath,
      parentSlug: DCR_PARENT,
      title: `Data center moratoriums and restrictions in ${stateName} (${snapshot.slice(0, 4)})`,
      seoTitle: `${stateName} Data Center Moratoriums, Bans, and Restrictions by County and City (${snapshot.slice(0, 4)})`,
      description: `${plural(local.length, "documented local action")} on data centers in ${stateName} as of ${longDate(snapshot)}: ${typeText || "no local restrictions on record"}. Every jurisdiction listed, with status, date, and source.`,
      kicker: `Data center restrictions tracker · ${stateName}`,
      intro,
      sections,
      crumbs: [...crumbsBase, { name: stateName, path: statePath }],
      snapshot,
      sources,
      related: [
        { text: "All states", href: `${BASE}/tracker` },
        { text: parentTitle, href: BASE },
        ...jurs.slice(0, 12).map((j) => ({ text: j.split("|")[0], href: jurPath(j) })),
      ],
    });
    stateRows.push([{ text: stateName, href: statePath }, local.length, byJur.size, statewide.length ? listJoin(statewide.map((r) => label(ACTION_LABEL, r.action_type))) : "none", fp ? fp.twh_2024.toFixed(1) : ""]);

    for (const j of jurs) {
      const jrows = byJur.get(j)!.slice().sort((a, b) => (b.date || "").localeCompare(a.date || ""));
      const lead = jrows[0];
      const name = j.split("|")[0];
      const displayName = lead.jurisdiction_type === "county" && !/county|parish/i.test(name) ? `${name} County` : name;
      const county = lead.county_name;
      const sameCounty = local.filter((r) => r.county_fips && r.county_fips === lead.county_fips && jurKey(r) !== j);
      const others = jurs.filter((x) => x !== j).slice(0, 10);
      const kind = lead.class === "condition" ? "conditions" : label(ACTION_LABEL, lead.action_type);
      const year = (lead.date || snapshot).slice(0, 4);

      const detailRows: Cell[][] = jrows.map((r) => [
        cap(label(ACTION_LABEL, r.action_type)),
        r.class,
        label(STATUS_LABEL, r.status),
        r.date ? longDate(r.date) : "undated",
        r.mw_threshold ? `${r.mw_threshold} MW` : "",
        r.county_wide === "True" ? "county-wide" : r.county_wide === "False" ? "not county-wide" : "",
        { text: r.source_name, href: r.source_url },
      ]);

      const intro = [
        ...jrows.map((r) => rowSentence(r, stateName)),
        `${jrows.length === 1 ? "The record reads" : "The records read"}: ${jrows.map((r) => `"${r.summary.trim().replace(/\.?$/, "")}."`).join(" ")}${jrows.some((r) => r.note) ? ` ${jrows.filter((r) => r.note).map((r) => r.note.trim().replace(/\.?$/, ".")).join(" ")}` : ""}`,
      ];
      const sections: DataSection[] = [
        {
          heading: "Details",
          table: { head: ["Action", "Class", "Status", "Date", "MW threshold", "Scope", "Source"], rows: detailRows },
          note: `Jurisdiction type: ${lead.jurisdiction_type}${county ? `. County: ${county}` : ""}. Dataset: ${lead.dataset.replace(/_/g, " ")}. Snapshot ${longDate(snapshot)}; documented actions, not a census.`,
        },
      ];
      if (sameCounty.length) {
        sections.push({
          heading: `Elsewhere in ${county}`,
          list: sameCounty.map((r) => ({ text: `${cleanName(r.jurisdiction)}: ${label(ACTION_LABEL, r.action_type)}, ${label(STATUS_LABEL, r.status)}${r.date ? `, ${longDate(r.date)}` : ""}`, href: rowPath(r) })),
        });
      }
      sections.push({
        heading: `${stateName} context`,
        paragraphs: [
          `${stateName} has ${plural(local.length, "documented local action")} across ${plural(byJur.size, "jurisdiction")} in this snapshot. ${statewideText}`,
          `A town that says no to a data center gives up local tax revenue, not jobs: one large campus pays ${payRange} depending on the tax regime, against roughly ${bench.jobs_per_facility_permanent} permanent jobs. The parent piece prices it and lists the conditions that beat a ban.`,
        ],
        list: others.map((o) => ({ text: o.split("|")[0], href: jurPath(o) })),
      });

      pages.push({
        path: jurPath(j),
        parentSlug: DCR_PARENT,
        title: `${displayName}, ${stateName}: data center ${kind} (${year})`,
        seoTitle: `${displayName}, ${abbr} Data Center ${cap(kind)} (${year}): Status, Date, Source`,
        description: `${displayName}, ${stateName} ${jrows.length === 1 ? `adopted ${article(`data-center ${kind}`)}` : `has ${plural(jrows.length, "data-center action")}`}${lead.date ? ` on ${longDate(lead.date)}` : ""}; status ${label(STATUS_LABEL, lead.status)} as of ${longDate(snapshot)}. Details, county context, and source.`,
        kicker: `Data center restrictions tracker · ${stateName}`,
        intro,
        sections,
        crumbs: [...crumbsBase, { name: stateName, path: statePath }, { name: displayName, path: jurPath(j) }],
        snapshot,
        sources: [...new Map(jrows.map((r) => [r.source_url, { name: r.source_name, href: r.source_url }])).values()],
        related: [
          { text: `All of ${stateName}`, href: statePath },
          { text: "All states", href: `${BASE}/tracker` },
          { text: parentTitle, href: BASE },
        ],
      });
    }
  }

  // Hub.
  const totalLocal = rows.filter((r) => r.level === "local").length;
  pages.unshift({
    path: `${BASE}/tracker`,
    parentSlug: DCR_PARENT,
    title: `Data center moratoriums and restrictions by state (${snapshot.slice(0, 4)})`,
    seoTitle: `Data Center Moratoriums and Restrictions by State: Every Documented Local and State Action (${snapshot.slice(0, 4)})`,
    description: `${n0(totalLocal)} documented local actions and ${n0(rows.length - totalLocal)} state actions on data centers across ${byState.size} states as of ${longDate(snapshot)}, with a page per state and per jurisdiction.`,
    kicker: "Data center restrictions tracker",
    intro: [
      `This index lists every state with a documented data-center restriction, condition, or related state action as of ${longDate(snapshot)}: ${n0(totalLocal)} local actions across ${byState.size} states, plus ${n0(rows.length - totalLocal)} state-level actions. Each state page lists every jurisdiction with its status, date, and source; each jurisdiction has its own page.`,
      `The dataset combines ${listJoin(meta.sources.map((s) => s.name))} with curated state actions. It is a record of documented actions, not a census, and it will be stale within months of the snapshot.`,
    ],
    sections: [
      {
        heading: "States",
        table: { head: ["State", "Local actions", "Jurisdictions", "Statewide action", `Data-center TWh ${meta.footprint.year}`], rows: stateRows },
      },
      {
        heading: "How to read this",
        paragraphs: [
          `"Moratorium" is a temporary pause on approvals; "zoning exclusion" removes data centers as a permitted use; "conditions" measures allow them with terms attached. "In force" and "enacted" are adopted measures; "pending" ones were under consideration at the snapshot; "replaced" and "expired" have lapsed.`,
        ],
      },
    ],
    crumbs: crumbsBase,
    snapshot,
    sources,
    related: [{ text: parentTitle, href: BASE }],
    isHub: true,
  });

  return pages;
}

export const dcrSpec: DatasetSpec = {
  id: "dcr",
  parentSlug: DCR_PARENT,
  files: Object.values(DCR_FILES),
  build: buildDcrPages,
  minCells: 8,
};
