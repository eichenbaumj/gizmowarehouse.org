// Static stand-ins for the interactive embeds, used ONLY by the build-time
// render (src/entry-static.tsx; see the alias in vite.config.ts) and by tests.
// Each one renders the same numbers the interactive component shows, as plain
// HTML a crawler can read: a table, a list, or a sentence. The browser never
// loads this file; createRoot().render() replaces the static markup with the
// real components from ./embeds.tsx on load.
//
// Rules: same tag names as ./embeds.tsx (test/embeds.test.ts checks the two
// registries agree), no browser APIs, no MapLibre, and every number comes from
// the same public/data file the live component reads. Only import data for
// gizmos that are PUBLISHED: a draft's data files are excluded from the public
// mirror and the mirror's build would break.
import type { ComponentType, ReactNode } from "react";
import stateSummary from "../../public/data/medicaid-state-summary.json";
import lossBreakdown from "../../public/data/medicaid-loss-breakdown.json";
import subjectProfile from "../../public/data/medicaid-subject-profile.json";
import compgapHeadline from "../../public/data/compgap/headline.json";
import compgapStates from "../../public/data/compgap/state_cross_section.json";
import compgapCities from "../../public/data/compgap/localities/cities.json";
import dcrActions from "../../public/data/data-center-restriction-cost/actions.json";
import dcrBenchmarks from "../../public/data/data-center-restriction-cost/benchmarks.json";
import dcrOutcomes from "../../public/data/data-center-restriction-cost/outcomes.json";
import nycTaxStats from "../../public/data/nyc-property-tax-stats.json";
import { GROCERY_MODEL, computeDial } from "@/config/groceryMath30";

const n0 = (v: number) => Math.round(v).toLocaleString("en-US");
const pct = (v: number, d = 1) => `${(v * 100).toFixed(d)}%`;
const money = (v: number) => `$${n0(v)}`;

function Figure({ id, caption, children }: { id: string; caption: string; children?: ReactNode }) {
  return (
    <figure data-static-embed={id} className="my-6">
      {children}
      <figcaption className="text-sm text-steel mt-2">{caption}</figcaption>
    </figure>
  );
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table>
      <thead>
        <tr>{head.map((h) => <th key={h}>{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

const Nothing: ComponentType = () => null;

// ---------------------------------------------------------------- Medicaid
type StateRow = (typeof stateSummary)["states"][number];
const states: StateRow[] = [...stateSummary.states].sort((a, b) => a.state_name.localeCompare(b.state_name));
const nat = stateSummary.national;

const MedicaidHero: ComponentType = () => (
  <Figure
    id="medicaid-hero-flyover"
    caption="Interactive map in the browser. Source: ACS PUMS 5-year, KFF, CBO; model version in the methodology."
  >
    <p>
      About {n0(nat.subject_count_strict)} adults in Medicaid expansion states are subject to the 2027 federal work
      requirement (CBO's target: {n0(nat.cbo_subject_target)}). This model's bottom-up estimate of coverage loss is{" "}
      {n0(nat.loss_exposure_strict)} people, against CBO's {n0(nat.cbo_loss_target_2034)} by 2034 and the Urban
      Institute's {n0(nat.urban_loss_2028_high_mitigation)} to {n0(nat.urban_loss_2028_low_mitigation)} range for 2028.
    </p>
  </Figure>
);

const MedicaidStateTable: ComponentType = () => (
  <Figure
    id="medicaid-map"
    caption={`Interactive state and county map in the browser. Model ${stateSummary.version}; expansion states only. "Subject" = adults 19 to 64 on Medicaid at or below 138% FPL who must report; "projected loss" is this model's bottom-up estimate of coverage ended for procedural reasons.`}
  >
    <Table
      head={["State", "Expansion", "Adults subject to the requirement", "Projected coverage loss", "Share of expansion pool subject"]}
      rows={states.map((s) => [
        s.state_name,
        s.expansion ? (s.partial_expansion ? "Partial" : "Yes") : "No",
        n0(s.subject_count_strict),
        s.loss_quantified ? n0(s.loss_exposure_strict) : "not quantified",
        pct(s.subject_rate),
      ])}
    />
  </Figure>
);

const MedicaidFindYourState: ComponentType = () => (
  <Figure id="medicaid-find-your-state" caption="Pick a state in the browser to see its figures; the same numbers are in the table above.">
    <p>
      States with the largest subject populations:{" "}
      {[...stateSummary.states]
        .sort((a, b) => b.subject_count_strict - a.subject_count_strict)
        .slice(0, 10)
        .map((s) => `${s.state_name} (${n0(s.subject_count_strict)})`)
        .join(", ")}
      .
    </p>
  </Figure>
);

const MedicaidSubjectProfile: ComponentType = () => {
  const p = (subjectProfile as Record<string, any>)["_national"];
  if (!p) return null;
  return (
    <Figure id="medicaid-subject-profile" caption="Who is subject, all expansion states. ACS PUMS 5-year 2020 to 2024.">
      <Table
        head={["Characteristic", "Share of subjects"]}
        rows={[
          ...Object.entries(p.age_band as Record<string, number>).map(([k, v]) => [`Age ${k}`, pct(v, 0)]),
          ["Has a child under 14", pct(p.has_kids_under_14.yes, 0)],
          ...Object.entries(p.work_hours_per_wk as Record<string, number>).map(([k, v]) => [`Works ${k === "0" ? "0 hours" : k === "80_plus" ? "80+ hours a month" : `${k} hours a month`}`, pct(v, 0)]),
          ...Object.entries(p.not_working_breakdown as Record<string, number>).map(([k, v]) => [`Not working: ${k}`, pct(v, 0)]),
        ]}
      />
    </Figure>
  );
};

const MedicaidLossSankey: ComponentType = () => {
  const lb = lossBreakdown as Record<string, any>;
  const rows: (string | number)[][] = [];
  const buckets = lb.national?.buckets ?? lb.buckets ?? lb.national;
  if (buckets && typeof buckets === "object") {
    for (const [k, v] of Object.entries(buckets as Record<string, any>)) {
      const num = typeof v === "number" ? v : typeof v?.count === "number" ? v.count : null;
      if (num != null) rows.push([k.replace(/_/g, " "), n0(num)]);
    }
  }
  return (
    <Figure id="medicaid-loss-sankey" caption={`How the subject population resolves into compliant, exempt, and lost coverage. Model ${lb.version}.`}>
      {rows.length > 0 ? <Table head={["Bucket", "People"]} rows={rows} /> : <p>Flow diagram available in the browser.</p>}
    </Figure>
  );
};

const MedicaidExParte: ComponentType = () => (
  <Figure id="medicaid-ex-parte-capability" caption="State-by-state ex parte (automatic) renewal capability, scored from CMS eligibility-processing data, data-source access, and history.">
    <Table
      head={["State", "Hardship exception", "Loss quantified"]}
      rows={states.filter((s) => s.expansion).map((s) => [s.state_name, s.hardship_exception_status ?? "unknown", s.loss_quantified ? "yes" : "no"])}
    />
  </Figure>
);

const MedicaidMethodologyLink: ComponentType = () => (
  <p>
    Full methodology, sources, and caveats: <a href="/gizmo/medicaid-work-requirements/methodology">the methodology page</a>.
  </p>
);

// ---------------------------------------------------------------- Comp gap
const CompGapHero: ComponentType = () => {
  const h = compgapHeadline;
  return (
    <Figure id="compgap-hero" caption={`Real median hourly wage growth, ${h.macro.first_year} to ${h.macro.latest_year}. ACS PUMS, BLS, BEA.`}>
      <p>
        Since {h.macro.first_year}, the private sector's 95th-percentile real wage grew {h.macro.p95_real_growth_pct}% while
        the median grew {h.macro.p50_real_growth_pct}%. In {h.dollars.year} dollars the private median is about $
        {h.dollars.private_median_k}K, the private 95th percentile about ${h.dollars.private_p95_k}K, and the government
        median about ${h.dollars.gov_median_k}K. Adjusted for education and experience, federal pay runs{" "}
        {h.adjusted.federal_gap_pct}% versus the private sector, state pay {h.adjusted.state_gap_pct}%, and local pay{" "}
        {h.adjusted.local_gap_pct}%. In software the state gap is {h.adjusted.software_state_gap_pct}%, legal{" "}
        {h.adjusted.legal_state_gap_pct}%, engineering {h.adjusted.engineering_state_gap_pct}%.
      </p>
    </Figure>
  );
};

const CompGapMacro: ComponentType = () => {
  const h = compgapHeadline;
  return (
    <Figure id="compgap-macro" caption={`Government employment by level, ${h.shape.year} (millions). BLS CES.`}>
      <Table
        head={["Level", "Employees (millions)"]}
        rows={[
          ["Federal", h.shape.federal_m],
          ["State", h.shape.state_m],
          ["Local", h.shape.local_m],
          ["All government", `${h.shape.government_total_m} (${h.shape.gov_share_pct}% of jobs)`],
        ]}
      />
    </Figure>
  );
};

const DOMAIN_LABELS: Record<string, string> = {
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

const CompGapDomainExplorer: ComponentType = () => {
  // National-ish view: median public vs private hourly wage by domain, averaged over states weighted equally.
  const byDomain = new Map<string, { pub: number[]; priv: number[] }>();
  for (const r of compgapStates.records) {
    const d = byDomain.get(r.domain) ?? { pub: [], priv: [] };
    (r.sector === "private" ? d.priv : d.pub).push(r.p50);
    byDomain.set(r.domain, d);
  }
  const med = (a: number[]) => {
    const s = [...a].sort((x, y) => x - y);
    return s.length ? s[Math.floor(s.length / 2)] : NaN;
  };
  const rows = [...byDomain.entries()]
    .filter(([d]) => d !== "other")
    .map(([d, v]) => {
      const p = med(v.pub), q = med(v.priv);
      return [DOMAIN_LABELS[d] ?? d, `$${p.toFixed(2)}`, `$${q.toFixed(2)}`, `${(((p - q) / q) * 100).toFixed(0)}%`];
    });
  return (
    <Figure id="compgap-domain-explorer" caption={`Median of state medians, public vs private real hourly wage by domain, ${compgapStates.year}. ${compgapStates.note} Explore any state in the browser.`}>
      <Table head={["Domain", "Government median $/hr", "Private median $/hr", "Gap"]} rows={rows} />
    </Figure>
  );
};

const CompGapLocalityCard: ComponentType = () => {
  const rows = compgapCities.records
    .filter((r) => r.domain === "all")
    .map((r) => {
      const c = compgapCities.cities.find((x) => x.key === r.city);
      return [c?.name ?? r.city, money(r.gov_p50), money(r.private_p50_metro), `${r.gap_vs_private_pct}%`, `${r.gap_top_pct}%`];
    });
  return (
    <Figure id="compgap-locality-card" caption={compgapCities.comparator_note}>
      <Table head={["City", "City-government median pay", "Private median (metro)", "Median gap", "Gap at the 90th percentile"]} rows={rows} />
    </Figure>
  );
};

const CompGapCaption = (id: string, caption: string): ComponentType => () => <Figure id={id} caption={caption} />;

// ---------------------------------------------------------------- Grocery
const GroceryDial: ComponentType = () => {
  const m = GROCERY_MODEL;
  const r = computeDial(m.defaultRevPerSqft, m.defaultBlend, m.defaultPersonsPerHH);
  return (
    <Figure id="grocery-dial" caption="Adjust sales per square foot, the discount blend, and household size in the browser. Central case shown.">
      <Table
        head={["Central case", "Value"]}
        rows={[
          ["Stores", m.stores],
          ["Sales per square foot", `$${n0(m.defaultRevPerSqft)}`],
          ["Basket discount", `${m.basketDiscount * 100}% on ${m.basketShare * 100}% of sales`],
          ["Annual subsidy, five stores", money(r.subsidyPerYear)],
          ["Ten-year public bill (capex plus subsidy)", money(r.envelope)],
          ["Households receiving the full promised savings", n0(r.households)],
          ["People reached", n0(r.people)],
          ["Food benefit per public dollar (present value)", r.leverage.toFixed(2)],
        ]}
      />
    </Figure>
  );
};

// ---------------------------------------------------------------- Data centers
const DcrMap: ComponentType = () => {
  const statuses = Object.values(dcrActions.state_status as Record<string, { abbr: string; name: string; status: string; tariff: string | null; action_ids: string[] }>)
    .filter((s) => s.status !== "none" || s.tariff)
    .sort((a, b) => a.name.localeCompare(b.name));
  return (
    <Figure
      id="dcr-map"
      caption={`Interactive map of ${dcrActions.counts.local_documented} documented local actions and ${dcrActions.counts.state_actions} state actions, snapshot ${dcrActions.snapshot_date}. Sources: ${dcrActions.sources.map((s) => s.name).join("; ")}.`}
    >
      <Table
        head={["State", "State-level status", "Large-load tariff"]}
        rows={statuses.map((s) => [s.name, s.status.replace(/_/g, " "), s.tariff ? String(s.tariff).replace(/_/g, " ") : "none"])}
      />
    </Figure>
  );
};

const DcrTownCalc: ComponentType = () => (
  <Figure id="dcr-town-calc" caption={`What one campus pays a town per year under three tax regimes; horizon ${dcrBenchmarks.horizon_years} years, about ${dcrBenchmarks.jobs_per_facility_permanent} permanent jobs per facility. Adjust in the browser.`}>
    <Table
      head={["Regime", "Reference case", "Annual local revenue (low)", "Annual local revenue (high)"]}
      rows={dcrBenchmarks.regimes.map((r) => [r.id.replace(/_/g, " "), r.case, `$${r.annual_local_usd_m_low}M`, `$${r.annual_local_usd_m_high}M`])}
    />
    <p>
      Reference campus: {dcrBenchmarks.reference_campus.name}, ${dcrBenchmarks.reference_campus.capex_usd_b}B capex,{" "}
      {dcrBenchmarks.reference_campus.mw} MW, ${dcrBenchmarks.reference_campus.local_10yr_usd_m}M to local governments over
      ten years ({dcrBenchmarks.reference_campus.note}).
    </p>
  </Figure>
);

const DcrFootprintBars: ComponentType = () => {
  const f = dcrActions.footprint;
  const rows = Object.values(f.states as Record<string, { abbr: string; twh_2024: number; twh_2030_medium: number }>)
    .sort((a, b) => b.twh_2024 - a.twh_2024)
    .slice(0, 15)
    .map((s) => [s.abbr, s.twh_2024.toFixed(1), s.twh_2030_medium.toFixed(1)]);
  return (
    <Figure id="dcr-footprint-bars" caption={`Data-center electricity use by state, TWh, ${f.year} and ${f.projection}. Source: ${f.source}. US total ${f.us_twh_2024.toFixed(0)} TWh in ${f.year}, ${f.us_twh_2030_medium.toFixed(0)} TWh projected.`}>
      <Table head={["State", `TWh ${f.year}`, "TWh 2030 (medium)"]} rows={rows} />
      <p>
        Outcome trace of blocked or delayed projects: {dcrOutcomes.tally.died} died, {dcrOutcomes.tally.rerouted} rerouted,{" "}
        {dcrOutcomes.tally.delayed_then_built} delayed then built, {dcrOutcomes.tally.pending_litigating} pending or in litigation.
      </p>
    </Figure>
  );
};

// ---------------------------------------------------------------- NYC tax
const NycTaxMap: ComponentType = () => {
  const t = nycTaxStats;
  const classes = Object.entries(t.etr_by_class as Record<string, { n: number; median: number; p10: number; p90: number }>).sort(([a], [b]) => a.localeCompare(b));
  return (
    <Figure id="nyc-tax-map" caption={`Effective tax rate (tax bill ÷ market value) for ${n0(t.n_with_etr)} of ${n0(t.n_parcels_total)} NYC parcels, ${t.tax_year}. Parcel-level map in the browser.`}>
      <p>
        Citywide median effective rate {pct(t.etr_overall.median, 2)}; 10th percentile {pct(t.etr_overall.p10, 2)}, 90th
        percentile {pct(t.etr_overall.p90, 2)}.
      </p>
      <Table
        head={["Tax class", "Parcels", "Median effective rate", "10th percentile", "90th percentile"]}
        rows={classes.map(([k, v]) => [`Class ${k}`, n0(v.n), pct(v.median, 2), pct(v.p10, 2), pct(v.p90, 2)])}
      />
    </Figure>
  );
};

export const gizmoEmbeds: Record<string, ComponentType> = {
  "dcr-map": DcrMap,
  "dcr-town-calc": DcrTownCalc,
  "dcr-footprint-bars": DcrFootprintBars,
  "nyc-tax-map": NycTaxMap,
  "medicaid-contents": Nothing,
  "medicaid-map": MedicaidStateTable,
  "medicaid-hero-flyover": MedicaidHero,
  "medicaid-subject-profile": MedicaidSubjectProfile,
  "medicaid-category-overlap": CompGapCaption("medicaid-category-overlap", "How subjects overlap across working, caregiving, medical frailty, and student status (ACS PUMS joint counts). Chart in the browser."),
  "medicaid-ex-parte-capability": MedicaidExParte,
  "medicaid-loss-sankey": MedicaidLossSankey,
  "medicaid-divider": Nothing,
  "medicaid-find-your-state": MedicaidFindYourState,
  "medicaid-caveats-panel": MedicaidMethodologyLink,
  "medicaid-methodology-panel": MedicaidMethodologyLink,
  "compgap-macro": CompGapMacro,
  "compgap-hero": CompGapHero,
  "compgap-earnings": CompGapCaption("compgap-earnings", "Public vs private earnings distribution by education and experience. Chart in the browser; figures in the methodology appendix."),
  "compgap-ladder": CompGapCaption("compgap-ladder", "The pay ladder: government tracks the private sector at the bottom and falls away at the top. Chart in the browser."),
  "compgap-eci": CompGapCaption("compgap-eci", "Employment Cost Index, public vs private, indexed. Chart in the browser."),
  "compgap-domain-explorer": CompGapDomainExplorer,
  "compgap-compression": CompGapCaption("compgap-compression", "Wage compression: the ratio of 90th-percentile to median pay, public vs private. Chart in the browser."),
  "compgap-locality-card": CompGapLocalityCard,
  "grocery-dial": GroceryDial,
};
