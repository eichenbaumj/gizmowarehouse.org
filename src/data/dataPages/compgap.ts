// Public vs private pay: one page per state (from the state cross-section)
// and one per city (from the locality payroll files) behind "High Floor,
// Low Ceiling".
import type { Cell, DataPage, DataSection, DatasetSpec } from "./types";
import { STATE_NAMES, listJoin, pctPts, slugify, stateSlug, usd } from "./util";

export const COMPGAP_PARENT = "public-private-compensation-comparison";
const BASE = `/gizmo/${COMPGAP_PARENT}`;
export const COMPGAP_FILES = {
  states: "/data/compgap/state_cross_section.json",
  cities: "/data/compgap/localities/cities.json",
};

interface StateRec { state: string; domain: string; sector: "public" | "private" | string; p50: number; p90: number; n_unweighted: number; flags: string[] }
interface StateXs { year: number; source: string; note: string; records: StateRec[] }
interface CityRec { city: string; domain: string; gov_p50: number; gov_p90: number; n: number; private_p50_metro?: number; gap_vs_private_pct?: number; private_p90_metro?: number; gap_top_pct?: number }
interface Cities { dollar_year: number; comparator_note: string; cities: { key: string; name: string; state: string; data_year: number; n: number; title_coverage_pct: number }[]; records: CityRec[] }

export const DOMAIN_LABELS: Record<string, string> = {
  all: "All occupations",
  admin_clerical: "Admin and clerical",
  education: "Education",
  engineering: "Engineering",
  finance: "Finance",
  healthcare: "Healthcare",
  legal: "Legal",
  management: "Management",
  other: "Other",
  protective_service: "Protective service",
  skilled_trades: "Skilled trades",
  software_it: "Software and IT",
};
const gap = (pub: number, priv: number) => ((pub - priv) / priv) * 100;
const hr = (v: number) => `$${v.toFixed(2)}`;

export function buildCompgapPages(files: Record<string, unknown>): DataPage[] {
  const xs = files[COMPGAP_FILES.states] as StateXs;
  const cities = files[COMPGAP_FILES.cities] as Cities;
  if (!xs || !cities) return [];

  const parentTitle = "High Floor, Low Ceiling";
  const snapshot = `${xs.year}-12-31`;
  const crumbsBase = [
    { name: "Gizmo Warehouse", path: "/" },
    { name: parentTitle, path: BASE },
    { name: "By state and city", path: `${BASE}/states` },
  ];
  const sources = [
    { name: "ACS PUMS (Census Bureau)", href: "https://www.census.gov/programs-surveys/acs/microdata.html" },
    { name: "Methodology appendix", href: `${BASE}/methodology` },
  ];
  const pages: DataPage[] = [];
  const hubRows: Cell[][] = [];

  const byState = new Map<string, StateRec[]>();
  for (const r of xs.records) byState.set(r.state, [...(byState.get(r.state) ?? []), r]);

  for (const [abbr, recs] of [...byState.entries()].sort((a, b) => (STATE_NAMES[a[0]] ?? a[0]).localeCompare(STATE_NAMES[b[0]] ?? b[0]))) {
    const name = STATE_NAMES[abbr] ?? abbr;
    const path = `${BASE}/state/${stateSlug(abbr)}`;
    const pair = (d: string) => ({ pub: recs.find((r) => r.domain === d && r.sector === "public"), priv: recs.find((r) => r.domain === d && r.sector === "private") });
    const all = pair("all");
    if (!all.pub || !all.priv) continue;
    const domains = Object.keys(DOMAIN_LABELS).filter((d) => d !== "all" && d !== "other" && pair(d).pub && pair(d).priv);
    const rows: Cell[][] = [];
    const gaps: { d: string; g50: number; g90: number; small: boolean }[] = [];
    for (const d of ["all", ...domains]) {
      const { pub, priv } = pair(d);
      if (!pub || !priv) continue;
      const g50 = gap(pub.p50, priv.p50);
      const g90 = gap(pub.p90, priv.p90);
      const small = [...(pub.flags ?? []), ...(priv.flags ?? [])].includes("small_cell");
      if (d !== "all") gaps.push({ d, g50, g90, small });
      rows.push([DOMAIN_LABELS[d] + (small ? " *" : ""), hr(pub.p50), hr(priv.p50), pctPts(g50), hr(pub.p90), hr(priv.p90), pctPts(g90)]);
    }
    const solid = gaps.filter((g) => !g.small);
    const worst = [...solid].sort((a, b) => a.g50 - b.g50).slice(0, 3);
    const best = [...solid].sort((a, b) => b.g50 - a.g50).slice(0, 2);

    const intro = [
      `In ${xs.year}, the median state and local government worker in ${name} earned ${hr(all.pub.p50)} an hour against ${hr(all.priv.p50)} in the private sector, a gap of ${pctPts(gap(all.pub.p50, all.priv.p50))}. At the 90th percentile the government wage was ${hr(all.pub.p90)} against ${hr(all.priv.p90)} privately (${pctPts(gap(all.pub.p90, all.priv.p90))}). Both figures are real hourly wages from the same-state ACS sample, unadjusted for education and experience.`,
      solid.length
        ? `The gap is widest in ${listJoin(worst.map((g) => `${DOMAIN_LABELS[g.d]} (${pctPts(g.g50)})`))}${best.length ? `, and government pay holds up best in ${listJoin(best.map((g) => `${DOMAIN_LABELS[g.d]} (${pctPts(g.g50)})`))}` : ""}. That is the national pattern too: a high floor, a low ceiling.`
        : `Sample sizes by occupation in ${name} are small; read the domain rows as indicative.`,
    ];
    const sections: DataSection[] = [
      {
        heading: `Public vs private pay in ${name} by occupation, ${xs.year}`,
        table: {
          head: ["Occupation domain", "Government median $/hr", "Private median $/hr", "Gap at median", "Government 90th pct", "Private 90th pct", "Gap at 90th"],
          rows,
          caption: `${xs.note} * marks a small unweighted cell in at least one sector; treat those rows as rough. Source: ${xs.source}.`,
        },
      },
      {
        heading: "How to read this",
        paragraphs: [
          `Raw medians compare different people: government employs more teachers, nurses, and degree-holders than the private sector does. The parent piece adjusts for education and experience nationally (federal pay 7% above comparable private workers, state pay 17% below, local pay 17% below) and shows the gap opening at the top of the ladder, where private pay in software, law, finance, and engineering has pulled away. This state table is the unadjusted view; the methodology appendix explains both.`,
        ],
      },
    ];
    pages.push({
      path,
      parentSlug: COMPGAP_PARENT,
      title: `Public vs private sector pay in ${name} by occupation (${xs.year})`,
      seoTitle: `${name} Public vs Private Sector Pay by Occupation (${xs.year}): Government Wage Gap at the Median and the Top`,
      description: `Median government wage in ${name}: ${hr(all.pub.p50)}/hr vs ${hr(all.priv.p50)} private (${pctPts(gap(all.pub.p50, all.priv.p50))}). Gap by occupation domain and at the 90th percentile, from ACS PUMS ${xs.year}.`,
      kicker: `Public vs private pay · ${name}`,
      intro,
      sections,
      crumbs: [...crumbsBase, { name, path }],
      snapshot,
      sources,
      related: [
        { text: "All states and cities", href: `${BASE}/states` },
        { text: parentTitle, href: BASE },
      ],
    });
    hubRows.push([{ text: name, href: path }, hr(all.pub.p50), hr(all.priv.p50), pctPts(gap(all.pub.p50, all.priv.p50)), pctPts(gap(all.pub.p90, all.priv.p90))]);
  }

  const cityRows: Cell[][] = [];
  for (const c of cities.cities) {
    const recs = cities.records.filter((r) => r.city === c.key);
    const all = recs.find((r) => r.domain === "all");
    if (!all || all.private_p50_metro == null || all.gap_vs_private_pct == null || all.gap_top_pct == null || all.private_p90_metro == null) continue;
    const hasPriv = (r: CityRec): r is Required<CityRec> => r.private_p50_metro != null && r.gap_vs_private_pct != null;
    const path = `${BASE}/city/${slugify(c.name)}`;
    const domains = recs.filter((r) => r.domain !== "all" && r.domain !== "other" && hasPriv(r)).sort((a, b) => a.gap_vs_private_pct - b.gap_vs_private_pct);
    const intro = [
      `The median full-time ${c.name} city-government employee earned ${usd(all.gov_p50)} in base pay (${c.data_year} payroll, in ${cities.dollar_year} dollars) against a private-sector median of ${usd(all.private_p50_metro)} in the metro, a gap of ${pctPts(all.gap_vs_private_pct)}. At the 90th percentile, city pay was ${usd(all.gov_p90)} against ${usd(all.private_p90_metro)} privately (${pctPts(all.gap_top_pct)}).`,
      domains.length
        ? `By domain, city pay trails the private sector most in ${listJoin(domains.slice(0, 3).map((r) => `${DOMAIN_LABELS[r.domain]} (${pctPts(r.gap_vs_private_pct)})`))} and leads in ${listJoin(domains.slice(-2).reverse().map((r) => `${DOMAIN_LABELS[r.domain]} (${pctPts(r.gap_vs_private_pct)})`))}. The payroll file covers ${c.n.toLocaleString("en-US")} employees; ${c.title_coverage_pct}% of titles map to a domain.`
        : "",
    ].filter(Boolean);
    pages.push({
      path,
      parentSlug: COMPGAP_PARENT,
      title: `${c.name} city government pay vs the private sector by occupation (${c.data_year})`,
      seoTitle: `${c.name} City Employee Pay vs Private Sector by Occupation (${c.data_year}): Median and Top-End Gaps`,
      description: `Median ${c.name} city-government pay ${usd(all.gov_p50)} vs ${usd(all.private_p50_metro)} private (${pctPts(all.gap_vs_private_pct)}); at the 90th percentile ${pctPts(all.gap_top_pct)}. Gap by occupation domain from the ${c.data_year} payroll file.`,
      kicker: `Public vs private pay · ${c.name}`,
      intro,
      sections: [
        {
          heading: `${c.name} city pay by occupation domain`,
          table: {
            head: ["Occupation domain", "City median", "Private median (metro)", "Gap at median", "City 90th pct", "Private 90th pct", "Gap at 90th", "Employees"],
            rows: recs
              .filter((r) => r.domain !== "other")
              .sort((a, b) => (a.domain === "all" ? -1 : b.domain === "all" ? 1 : a.domain.localeCompare(b.domain)))
              .map((r) => [
                DOMAIN_LABELS[r.domain] ?? r.domain,
                usd(r.gov_p50),
                r.private_p50_metro != null ? usd(r.private_p50_metro) : "no private comparator",
                r.gap_vs_private_pct != null ? pctPts(r.gap_vs_private_pct) : "",
                usd(r.gov_p90),
                r.private_p90_metro != null ? usd(r.private_p90_metro) : "",
                r.gap_top_pct != null ? pctPts(r.gap_top_pct) : "",
                r.n.toLocaleString("en-US"),
              ]),
            caption: `${cities.comparator_note} Domains without a metro private comparator (too few private-sector records) show city pay only.`,
          },
        },
      ],
      crumbs: [...crumbsBase, { name: c.name, path }],
      snapshot: `${c.data_year}-12-31`,
      sources: [{ name: `${c.name} payroll data (open data portal)`, href: BASE }, ...sources],
      related: [
        { text: "All states and cities", href: `${BASE}/states` },
        { text: parentTitle, href: BASE },
      ],
    });
    cityRows.push([{ text: c.name, href: path }, c.data_year, usd(all.gov_p50), usd(all.private_p50_metro), pctPts(all.gap_vs_private_pct), pctPts(all.gap_top_pct)]);
  }

  pages.unshift({
    path: `${BASE}/states`,
    parentSlug: COMPGAP_PARENT,
    title: `Public vs private sector pay by state and city (${xs.year})`,
    seoTitle: `Public vs Private Sector Pay by State: Government Wage Gap in Every State and Five Big Cities (${xs.year})`,
    description: `Median and 90th-percentile government vs private hourly wages for ${byState.size} states and city-payroll comparisons for ${cities.cities.length} cities, from ACS PUMS and payroll files. One page per state and city, by occupation.`,
    kicker: "Public vs private pay",
    intro: [
      `Government pay holds its own at the bottom of the labor market and falls behind at the top. These pages give the unadjusted state view: median and 90th-percentile real hourly wages for state and local government workers against private workers in the same state, by occupation domain, from ACS PUMS ${xs.year}. City pages use the city's own payroll file against the metro private sector.`,
    ],
    sections: [
      { heading: "States", table: { head: ["State", "Government median $/hr", "Private median $/hr", "Gap at median", "Gap at 90th"], rows: hubRows } },
      { heading: "Cities", table: { head: ["City", "Payroll year", "City median pay", "Private median (metro)", "Gap at median", "Gap at 90th"], rows: cityRows } },
    ],
    crumbs: crumbsBase,
    snapshot,
    sources,
    related: [{ text: parentTitle, href: BASE }],
    isHub: true,
  });

  return pages;
}

export const compgapSpec: DatasetSpec = {
  id: "compgap",
  parentSlug: COMPGAP_PARENT,
  files: Object.values(COMPGAP_FILES),
  build: buildCompgapPages,
  minCells: 8,
};
