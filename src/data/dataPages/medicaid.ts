// Medicaid work requirements: one page per state (51), from the state
// summary, loss breakdown, subject profile, category overlaps, and the
// county table behind "These 5 Million People Are About to Lose Their Medicaid".
import type { Cell, DataPage, DataSection, DatasetSpec } from "./types";
import { listJoin, longDate, n0, pct, plural, stateSlug } from "./util";

export const MEDICAID_PARENT = "medicaid-work-requirements";
const BASE = `/gizmo/${MEDICAID_PARENT}`;
export const MEDICAID_FILES = {
  summary: "/data/medicaid-state-summary.json",
  loss: "/data/medicaid-loss-breakdown.json",
  profile: "/data/medicaid-subject-profile.json",
  overlaps: "/data/medicaid-category-overlaps.json",
  counties: "/data/medicaid-counties-table.json",
};
const BRIEF_BASE = "https://data.gizmowarehouse.org/medicaid-work-requirements/briefs";
const START = "2027-01-01";

interface StateRow {
  state_fips: string;
  state_abbr: string;
  state_name: string;
  expansion: boolean;
  partial_expansion: boolean;
  subject_via_waiver: boolean;
  waiver_listed: boolean;
  loss_quantified: boolean;
  already_work_conditional: boolean;
  waiver_note: string | null;
  hardship_exception_status: string | null;
  early_implementer: string | null;
  expansion_pool: number;
  subject_count_strict: number;
  subject_count_permissive: number;
  loss_exposure_strict: number;
  burden_index_centered: number;
  subject_rate: number;
  top_counties: { county_fips: string; GEOID: string; subject_count_strict: number }[];
}
interface Summary {
  version: string;
  vintage: Record<string, string>;
  national: { subject_count_strict: number; loss_exposure_strict: number; cbo_subject_target: number; cbo_loss_target_2034: number; urban_loss_2028_high_mitigation: number; urban_loss_2028_low_mitigation: number };
  states: StateRow[];
  concentration: { share_in_top_n_counties: Record<string, number> };
}
interface LossState {
  abbr: string;
  name: string;
  ex_parte_score: number;
  ex_parte_band: string;
  scores: Record<string, number>;
  system_vendor: string | null;
  subject_count: number;
  total_loss_2034: number;
  eligible_but_lose: number;
  genuinely_noncompliant: number;
  work_hours_doc_failures?: { total: number; subgroups: Record<string, { label: string; count: number; narrative?: string }> };
  exemption_doc_failures?: { total: number; subgroups: Record<string, { label: string; count: number }> };
  [k: string]: unknown;
}
interface Loss {
  version: string;
  states: Record<string, LossState>;
  ex_parte_table?: { fips: string; abbr: string; name: string; score: number; band: string; observed_ex_parte_rate?: number }[];
}
interface Profile {
  state_name: string;
  subject_total: number;
  age_band: Record<string, number>;
  has_kids_under_14: { yes: number; no: number };
  work_hours_per_wk: Record<string, number>;
  not_working_breakdown: Record<string, number>;
  share_parents_covered_outside_expansion?: number;
}
interface Overlaps {
  _meta: { category_labels: Record<string, string> };
  states: Record<string, { subject_count: number; cells: { key: string; categories: string[]; count: number; share: number }[] }>;
}
export interface CountyRow {
  GEOID: string;
  state_fips: string;
  state_abbr: string;
  county_name: string;
  pov_pct: number;
  subject_count_strict: number;
  loss_exposure_strict: number;
  subject_rate: number;
  total_pop: number;
  working_age_pop: number;
  uninsured_below_138pct: number;
  expansion: boolean;
}

const HOURS_LABEL: Record<string, string> = { "0": "Not working", "1-19": "1 to 19 hours a month", "20-79": "20 to 79 hours a month", "80_plus": "80 or more hours a month (meets the bar)" };
const NOTWORK_LABEL: Record<string, string> = { disabled: "Disabled", caretaker: "Caregiver", postpartum: "Postpartum", student: "Student", other: "Other" };
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
// Model notes were written with em dashes; the site's prose rule is no em dashes.
const note = (t: string | null) => (t ? ` ${t.replace(/\s*—\s*/g, "; ").replace(/\.?$/, ".")}` : "");

export function buildMedicaidPages(files: Record<string, unknown>): DataPage[] {
  const summary = files[MEDICAID_FILES.summary] as Summary;
  const loss = files[MEDICAID_FILES.loss] as Loss;
  const profiles = files[MEDICAID_FILES.profile] as Record<string, Profile>;
  const overlaps = files[MEDICAID_FILES.overlaps] as Overlaps;
  const counties = files[MEDICAID_FILES.counties] as CountyRow[];
  if (!summary || !loss || !profiles || !overlaps || !counties) return [];

  const snapshot = summary.version.replace(/^v\d+-/, "");
  const parentTitle = "These 5 Million People Are About to Lose Their Medicaid";
  const crumbsBase = [
    { name: "Gizmo Warehouse", path: "/" },
    { name: parentTitle, path: BASE },
    { name: "By state", path: `${BASE}/states` },
  ];
  const sources = [
    { name: "ACS PUMS 5-year 2020 to 2024 (Census Bureau)", href: "https://www.census.gov/programs-surveys/acs/microdata.html" },
    { name: "KFF Medicaid work requirement implementation tracker", href: "https://www.kff.org/medicaid/" },
    { name: "CBO scoring of the 2025 reconciliation law", href: "https://www.cbo.gov/" },
    { name: "Methodology and caveats", href: `${BASE}/methodology` },
  ];
  const nat = summary.national;
  const pages: DataPage[] = [];
  const hubRows: Cell[][] = [];

  const states = [...summary.states].sort((a, b) => a.state_name.localeCompare(b.state_name));
  for (const s of states) {
    const path = `${BASE}/state/${stateSlug(s.state_abbr)}`;
    const l = loss.states[s.state_fips];
    const p = profiles[s.state_fips];
    const o = overlaps.states?.[s.state_fips];
    const cs = counties.filter((c) => c.state_fips === s.state_fips && c.subject_count_strict > 0).sort((a, b) => b.subject_count_strict - a.subject_count_strict);
    const applies = s.expansion || s.subject_via_waiver;

    const intro: string[] = [];
    if (s.expansion) {
      intro.push(
        `${s.state_name} ${s.partial_expansion ? "partially " : ""}expanded Medicaid, so the federal work requirement that takes effect ${longDate(START)} applies to its expansion adults. About ${n0(s.subject_count_strict)} of them (${pct(s.subject_rate)} of an expansion pool of ${n0(s.expansion_pool)}) will have to prove 80 hours a month of work, school, or service, or an exemption, to keep coverage.${s.already_work_conditional ? " The state already conditions coverage on work under an existing waiver." : ""}`
      );
    } else if (s.subject_via_waiver) {
      intro.push(
        `${s.state_name} has not adopted the ACA expansion but covers a similar population under a waiver, so the federal work requirement that takes effect ${longDate(START)} reaches about ${n0(s.subject_count_strict)} adults there.${note(s.waiver_note)}`
      );
    } else {
      const gapCounties = counties.filter((c) => c.state_fips === s.state_fips && c.uninsured_below_138pct > 0);
      const gapTotal = gapCounties.reduce((a, c) => a + c.uninsured_below_138pct, 0);
      intro.push(
        `${s.state_name} has not expanded Medicaid, so the federal work requirement that takes effect ${longDate(START)} does not apply to a state expansion population. This model counts no ${s.state_name} adults as subject.${note(s.waiver_note)}`,
        `The requirement matters for ${s.state_name} in a different way: if the state expanded Medicaid later, its expansion adults would report from day one. The American Community Survey counts about ${n0(gapTotal)} uninsured ${s.state_name} adults with household income at or below 138% of the poverty line, the population an expansion would cover and the requirement would then reach.`
      );
    }
    if (applies && s.loss_quantified) {
      intro.push(
        `This model's bottom-up estimate is that ${n0(s.loss_exposure_strict)} people in ${s.state_name} lose coverage by 2034${l ? `: ${n0(l.eligible_but_lose)} of them still eligible but lost to paperwork and reporting failures, and ${n0(l.genuinely_noncompliant)} not meeting the requirement` : ""}. Nationally the same model gives ${n0(nat.loss_exposure_strict)}, against CBO's ${n0(nat.cbo_loss_target_2034)}.`
      );
    } else if (applies) {
      intro.push(`Coverage loss for ${s.state_name} is not quantified in this model version (${summary.version}).`);
    }
    if (applies && l) {
      intro.push(
        `Whether those eligible people keep coverage depends on the state's ability to renew them automatically (ex parte) from data it already holds. ${s.state_name} scores ${l.ex_parte_score} of 100 on this model's ex parte capability index, a ${l.ex_parte_band} band${l.system_vendor ? `; its eligibility system is ${l.system_vendor}` : ""}.`
      );
    }

    const sections: DataSection[] = [];
    sections.push({
      heading: "Key figures",
      table: {
        head: ["Measure", s.state_name],
        rows: [
          ["Expansion state", s.expansion ? (s.partial_expansion ? "Partial" : "Yes") : "No"],
          ["Subject to the requirement via waiver", s.subject_via_waiver ? "Yes" : "No"],
          ["Expansion pool (adults 19 to 64)", n0(s.expansion_pool)],
          ["Adults subject, strict definition", n0(s.subject_count_strict)],
          ["Adults subject, permissive definition", n0(s.subject_count_permissive)],
          ["Share of expansion pool subject", pct(s.subject_rate)],
          ["Projected coverage loss by 2034", s.loss_quantified ? n0(s.loss_exposure_strict) : "not quantified"],
          ["Hardship exception status", s.hardship_exception_status ? cap(s.hardship_exception_status.replace(/_/g, " ")) : "unknown"],
          ["Early implementer", s.early_implementer ? String(s.early_implementer) : "No"],
          ["Ex parte capability score (0 to 100)", l ? `${l.ex_parte_score} (${l.ex_parte_band})` : "n/a"],
        ],
        caption: `Model ${summary.version}. "Strict" counts adults whose ACS record shows them subject with no observable exemption; "permissive" allows the broader exemption reading.`,
      },
    });

    if (applies && p) {
      sections.push({
        heading: `Who is subject in ${s.state_name}`,
        paragraphs: [
          `Of the ${n0(p.subject_total)} subject adults, ${pct(p.work_hours_per_wk["80_plus"] ?? 0, 0)} already work 80 or more hours a month and ${pct(p.work_hours_per_wk["0"] ?? 0, 0)} are not working. ${pct(p.has_kids_under_14.yes, 0)} have a child under 14 at home. Among those not working, ${pct(p.not_working_breakdown.disabled, 0)} report a disability and ${pct(p.not_working_breakdown.caretaker, 0)} are caregivers.`,
        ],
        table: {
          head: ["Characteristic", "Share of subject adults"],
          rows: [
            ...Object.entries(p.age_band).map(([k, v]) => [`Age ${k}`, pct(v, 0)] as Cell[]),
            ...Object.entries(p.work_hours_per_wk).map(([k, v]) => [HOURS_LABEL[k] ?? k, pct(v, 0)] as Cell[]),
            ...Object.entries(p.not_working_breakdown).map(([k, v]) => [`Not working: ${NOTWORK_LABEL[k] ?? k}`, pct(v, 0)] as Cell[]),
          ],
          caption: "ACS PUMS 5-year 2020 to 2024, subject adults only.",
        },
      });
    }

    if (applies && l?.work_hours_doc_failures) {
      const wf = l.work_hours_doc_failures;
      const ef = l.exemption_doc_failures;
      sections.push({
        heading: "Why eligible people lose coverage",
        paragraphs: [
          `Of the ${n0(l.total_loss_2034)} projected to lose coverage in ${s.state_name}, ${n0(l.eligible_but_lose)} meet the requirement or qualify for an exemption but fail to document it. ${n0(wf.total)} of those are working people who cannot prove their hours through data the state can see${ef ? `, and ${n0(ef.total)} qualify for an exemption the state does not detect automatically` : ""}.`,
        ],
        table: {
          head: ["Group", "Projected to lose coverage"],
          rows: [
            ...Object.values(wf.subgroups).sort((a, b) => b.count - a.count).map((g) => [g.label, n0(g.count)] as Cell[]),
            ...(ef ? Object.values(ef.subgroups).sort((a, b) => b.count - a.count).map((g) => [g.label, n0(g.count)] as Cell[]) : []),
          ],
          caption: `Bottom-up model ${loss.version}; documentation-failure buckets compound over the 14 six-month renewal cycles through 2034.`,
        },
      });
    }

    if (applies && l?.scores) {
      const ep = loss.ex_parte_table?.find((e) => e.fips === s.state_fips);
      sections.push({
        heading: "Can the state renew people automatically?",
        paragraphs: [
          `The ex parte capability index blends the state's observed automatic-renewal rate (${ep?.observed_ex_parte_rate != null ? pct(ep.observed_ex_parte_rate, 0) : "n/a"} in CMS eligibility-processing data), the wage, disability, and other data sources it can query, and its history of churn. ${s.state_name}'s composite score is ${l.ex_parte_score} (${l.ex_parte_band} band). A low score means more eligible people will be dropped for paperwork unless the state changes its process before ${longDate(START)}.`,
        ],
        table: {
          head: ["Component", "Score"],
          rows: Object.entries(l.scores).map(([k, v]) => [cap(k.replace(/_/g, " ")), v] as Cell[]),
        },
      });
    }

    if (applies && o) {
      const labels = overlaps._meta.category_labels;
      const top = o.cells.slice().sort((a, b) => b.count - a.count).slice(0, 8);
      sections.push({
        heading: "How subjects overlap across exemption categories",
        table: {
          head: ["Combination", "Adults", "Share"],
          rows: top.map((c) => [c.categories.length ? c.categories.map((k) => labels[k] ?? k).join(" + ") : "None of the four", n0(c.count), pct(c.share, 1)]),
          caption: `Each subject adult sits in exactly one cell. Categories: ${Object.values(labels).join("; ")}.`,
        },
      });
    }

    if (!applies) {
      const gap = counties.filter((c) => c.state_fips === s.state_fips && c.uninsured_below_138pct > 0).sort((a, b) => b.uninsured_below_138pct - a.uninsured_below_138pct);
      if (gap.length) {
        const top3 = gap.slice(0, 3);
        sections.push({
          heading: `Counties in ${s.state_name}: uninsured adults below 138% of poverty`,
          paragraphs: [
            `${listJoin(top3.map((c) => `${c.county_name} (${n0(c.uninsured_below_138pct)})`))} hold the most uninsured low-income adults in ${s.state_name}.`,
          ],
          table: {
            head: ["County", "Uninsured adults at or below 138% FPL", "Poverty rate", "Working-age population"],
            rows: gap.map((c) => [c.county_name, n0(c.uninsured_below_138pct), `${c.pov_pct.toFixed(1)}%`, n0(c.working_age_pop)]),
            caption: `ACS 5-year estimates by county. These adults are not subject to the 2027 requirement because ${s.state_name} has not expanded Medicaid.`,
          },
        });
      }
    }
    if (cs.length) {
      const top3 = cs.slice(0, 3);
      sections.push({
        heading: `Counties in ${s.state_name}`,
        paragraphs: [
          `Subject adults concentrate: ${listJoin(top3.map((c) => `${c.county_name} (${n0(c.subject_count_strict)})`))} account for ${pct(top3.reduce((a, c) => a + c.subject_count_strict, 0) / s.subject_count_strict, 0)} of the state's subject population.`,
        ],
        table: {
          head: ["County", "Adults subject", "Subject rate", "Projected loss", "Poverty rate", "Working-age population"],
          rows: cs.map((c) => [c.county_name, n0(c.subject_count_strict), pct(c.subject_rate), n0(c.loss_exposure_strict), `${c.pov_pct.toFixed(1)}%`, n0(c.working_age_pop)]),
          caption: `All ${plural(cs.length, "county", "counties")} in ${s.state_name} with subject adults, sorted by count. County figures are model allocations of the state estimate by ACS tract characteristics.`,
        },
      });
    }

    sections.push({
      heading: "State brief and methodology",
      list: [
        ...(applies ? [{ text: `${s.state_name} one-page brief (PDF)`, href: `${BRIEF_BASE}/medicaid_brief_${s.state_abbr.toUpperCase()}.pdf` }] : []),
        { text: "Interactive map and state finder", href: BASE },
        { text: "Methodology, sources, and caveats", href: `${BASE}/methodology` },
      ],
      note: "Estimates, not counts. The model rakes to CBO's national subject total and allocates by ACS microdata; state agencies hold the administrative data that would replace these figures.",
    });

    pages.push({
      path,
      parentSlug: MEDICAID_PARENT,
      title: `Medicaid work requirements in ${s.state_name}: who is subject and who loses coverage (2027)`,
      seoTitle: applies
        ? `${s.state_name} Medicaid Work Requirements 2027: Who Is Affected, Projected Coverage Loss, County Numbers`
        : `${s.state_name} and the 2027 Medicaid Work Requirement: Why It Does Not Apply, and Who It Would Reach`,
      description: applies
        ? `About ${n0(s.subject_count_strict)} ${s.state_name} adults must report work or an exemption from January 2027; this model projects ${s.loss_quantified ? n0(s.loss_exposure_strict) : "an unquantified number"} losing coverage. County table, who is subject, and what the state can verify.`
        : `${s.state_name} has not expanded Medicaid, so the 2027 federal work requirement does not apply to an expansion population there. County counts of the uninsured low-income adults an expansion would reach, and the numbers for states where the rule applies.`,
      kicker: `Medicaid work requirements · ${s.state_name}`,
      intro,
      sections,
      crumbs: [...crumbsBase, { name: s.state_name, path }],
      snapshot,
      sources,
      related: [
        { text: "All states", href: `${BASE}/states` },
        { text: parentTitle, href: BASE },
      ],
    });
    hubRows.push([{ text: s.state_name, href: path }, s.expansion ? (s.partial_expansion ? "Partial" : "Yes") : s.subject_via_waiver ? "Waiver" : "No", n0(s.subject_count_strict), s.loss_quantified ? n0(s.loss_exposure_strict) : "n/a", l ? l.ex_parte_score : "n/a"]);
  }

  pages.unshift({
    path: `${BASE}/states`,
    parentSlug: MEDICAID_PARENT,
    title: "Medicaid work requirements by state: who is subject and who loses coverage (2027)",
    seoTitle: "Medicaid Work Requirements by State (2027): Adults Affected and Projected Coverage Loss, All 50 States and DC",
    description: `State-by-state numbers for the federal Medicaid work requirement starting ${longDate(START)}: ${n0(nat.subject_count_strict)} adults subject nationally, ${n0(nat.loss_exposure_strict)} projected to lose coverage. One page per state with county detail.`,
    kicker: "Medicaid work requirements",
    intro: [
      `From ${longDate(START)}, adults covered through Medicaid expansion must show 80 hours a month of work, school, or community service, or qualify for an exemption, at every renewal. This model counts ${n0(nat.subject_count_strict)} adults subject nationally (CBO: ${n0(nat.cbo_subject_target)}) and projects ${n0(nat.loss_exposure_strict)} losing coverage by 2034 (CBO: ${n0(nat.cbo_loss_target_2034)}; Urban Institute for 2028: ${n0(nat.urban_loss_2028_high_mitigation)} to ${n0(nat.urban_loss_2028_low_mitigation)}).`,
      `Most of that loss is people who qualify but cannot get through the paperwork. Each state page shows who is subject, why eligible people fall off, how well the state can renew people automatically, and the county numbers.`,
    ],
    sections: [
      {
        heading: "States",
        table: { head: ["State", "Expansion", "Adults subject", "Projected loss by 2034", "Ex parte score"], rows: hubRows },
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

export const medicaidSpec: DatasetSpec = {
  id: "medicaid",
  parentSlug: MEDICAID_PARENT,
  files: Object.values(MEDICAID_FILES),
  build: buildMedicaidPages,
  minCells: 8,
};
