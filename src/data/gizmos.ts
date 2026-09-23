export type Category = "Public Safety" | "Music" | "Using AI" | "City Government" | "State Government" | "Healthcare Policy" | "NYC";

export interface Gizmo {
  slug: string;
  title: string;
  categories: Category[];
  date: string;
  summary: string;
  /** Search snippet (<=155 chars, answers the query in the first clause). Falls back to summary. */
  metaDescription?: string;
  /**
   * Search-facing <title> and JSON-LD headline, in the words people type
   * ("Medicaid work requirements by state"). `title` stays the H1, the card,
   * and the social (og:) title. Falls back to `title`. See src/lib/seo.ts.
   */
  seoTitle?: string;
  /** One-line subhead rendered under the title on the detail page. */
  dek?: string;
  /**
   * When true, the gizmo is unlisted: omitted from the home-page grid
   * (src/pages/Home.tsx), the sitemap (tools/generate-sitemap.ts), and the
   * social-preview prerender (tools/prerender.ts). The detail page still
   * resolves at /gizmo/<slug> via the SPA fallback — the entry stays in this
   * array — so direct links keep working.
   */
  hidden?: boolean;
  links?: { label: string; url: string }[];
  /**
   * Optional URL to a JSON file whose contents are interpolated into the
   * gizmo's markdown content via {tokenName} placeholders. See
   * src/lib/interpolateTokens.ts for the syntax.
   */
  dataContextUrl?: string;
}

export const ALL_CATEGORIES: Category[] = ["Public Safety", "Music", "Using AI", "City Government", "State Government", "Healthcare Policy", "NYC"];

/** "City Government" -> "city-government" (the /category/<slug> URL). */
export function categorySlug(c: Category): string {
  return c.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

export function categoryFromSlug(slug: string): Category | undefined {
  return ALL_CATEGORIES.find((c) => categorySlug(c) === slug);
}

export const gizmos: Gizmo[] = [
  {
    slug: "daf-yomi",
    title: "Introducing Daf Yomi Dot Dev",
    categories: ["Using AI"],
    date: "2026-09",
    summary: "I built a Daf Yomi Machine with Claude. I hope it causes me to read a little more Talmud. I explain how I made it. I hope you use it if you're interested!",
    seoTitle: "Daf Yomi Dot Dev: A Daily Page of Talmud with an AI Study Note",
    metaDescription:
      "daf-yomi.dev shows today's page of Talmud with a short AI-written note and one question, plus a daily email. How I built it with Claude, and why.",
    links: [
      {
        label: "Open daf-yomi.dev",
        url: "https://daf-yomi.dev",
      },
      {
        label: "Source on GitHub",
        url: "https://github.com/eichenbaumj/daf-yomi",
      },
    ],
  },
  {
    slug: "only-way-to-start-is-by-starting",
    title: "The Only Way to Start Is by Starting",
    categories: ["Using AI", "State Government", "City Government"],
    date: "2026-09",
    summary: "A short paper on how a state or local agency can get real value from AI in ninety days with one accountable owner, a handful of paid licenses, and one well-chosen piece of real work.",
    seoTitle: "How a State or Local Agency Gets Real Value from AI in 90 Days",
    metaDescription:
      "A short whitepaper for agency leaders: one accountable owner, a handful of paid licenses, one real piece of work. The 90-day recipe for AI in government.",
    links: [
      {
        label: "Read the whitepaper (PDF)",
        url: "/assets/only-way-to-start-is-by-starting.pdf",
      },
    ],
  },
  {
    slug: "gospel-of-claude-code",
    title: "Music Theory with LLMs",
    categories: ["Music", "Using AI"],
    date: "2026-08",
    summary: "Using Claude Code to write gospel reharmonizations for the fake book, and why next-chord prediction is a natural LLM task.",
    seoTitle: "Gospel Reharmonization with an LLM: Music Theory in Claude Code",
    metaDescription:
      "I had Claude Code write gospel reharmonizations for my fake book. Why predicting the next chord is a natural job for a language model, with examples.",
    links: [
      {
        label: "Download the fakebook (public-domain edition)",
        url: "/assets/fakebook.pdf",
      },
      {
        label: "Get the code on GitHub",
        url: "https://github.com/eichenbaumj/fakebook-maker",
      },
    ],
  },
  {
    slug: "data-center-restriction-cost",
    title: "Pricing the Fear of Data Centers",
    categories: ["State Government", "City Government"],
    date: "2026-08",
    dek: "What saying no actually costs, and what to demand instead",
    summary:
      "A town that says no to a data center gives up tax revenue, not jobs, and how much depends on the local tax regime. Opposition is not partisan, legislatures are choosing conditions over bans, and blocked projects go quiet more than they resurface. A national map of restrictions and conditions, a calculator for what one campus pays a town, and the terms to demand if the answer is yes.",
    seoTitle: "Data Center Moratoriums and Restrictions by State and County (2026 Tracker)",
    metaDescription:
      "Every documented US data-center restriction on one map, what a town gives up when it says no, and the conditions that beat a ban.",
    links: [
      {
        label: "Download the actions dataset (.csv)",
        url: "/assets/data-center-restriction-cost-actions.csv",
      },
      {
        label: "Download the outcome trace (.csv)",
        url: "/assets/data-center-restriction-cost-outcomes.csv",
      },
      {
        label: "Methodology & sources (.md)",
        url: "/assets/data-center-restriction-cost-methodology.md",
      },
    ],
  },
  {
    slug: "nyc-public-grocery-new-math",
    title: "The New Math on NYC's Public Grocery Stores",
    categories: ["City Government", "NYC"],
    date: "2026-08",
    summary:
      "Mayor Mamdani's stores will sell a core basket 30% below market, and nobody has priced that promise. This update does: about $167M over ten years, reaching roughly 12,000 households when the same money could reach six to fifteen times as many.",
    seoTitle: "NYC Public Grocery Stores: What the 30% Discount Costs Over Ten Years",
    metaDescription:
      "NYC's city-owned grocery stores will cut a core basket 30%. A new model prices the hidden subsidy: ~$167M over ten years, reaching ~29,000 New Yorkers a year.",
    links: [
      {
        label: "Download the financial model (.xlsx)",
        url: "/assets/nyc-public-grocery-model.xlsx",
      },
      {
        label: "The April piece this updates",
        url: "/gizmo/nyc-public-grocery-math",
      },
    ],
  },
  {
    slug: "public-private-compensation-comparison",
    title: "High Floor, Low Ceiling: How Public-Sector Wage Compression Erodes Public Service",
    categories: ["City Government", "State Government", "Using AI"],
    date: "2026-06",
    summary:
      "Public pay is compressed: a high floor and a low ceiling. Government holds its own at the bottom of the labor market but falls far behind at the top, exactly where elite private pay has soared — software, law, finance, engineering. A data piece tracing the public-sector pay gap by skill, by domain, by level of government, and over time, built from ACS PUMS microdata, BLS/BEA/Census series, and city and state payroll files.",
    seoTitle: "Public vs Private Sector Pay: The Government Wage Gap by Job, State, and Over Time",
    metaDescription:
      "The public-sector pay gap by skill, state, and over time. Government pay holds up at the bottom of the labor market and falls far behind at the top.",
    dataContextUrl: "/data/compgap/headline.json",
  },
  {
    slug: "medicaid-work-requirements",
    title: "These 5 Million People Are About to Lose Their Medicaid — But They Don't Have To",
    categories: ["Healthcare Policy", "State Government"],
    date: "2026-05",
    summary:
      "Starting in 2027, the new federal Medicaid work requirement will end coverage for 5–10 million people. Most of that loss is a state operations problem, not a policy outcome. A nationwide bottom-up model of who's at risk, where they live, and what each state's verification capability looks like. Built for state Medicaid directors with seven months to get the operational pre-work done.",
    seoTitle: "Medicaid Work Requirements by State: Who Loses Coverage in 2027",
    metaDescription:
      "Starting Jan 2027, a federal Medicaid work requirement puts 5–10M people at risk. State-by-state model of who's affected and what each state can verify.",
    dataContextUrl: "/data/medicaid-state-summary.json",
  },
  {
    slug: "microsoft-copilot",
    title: "How to Save the Government from Microsoft Copilot",
    categories: ["Using AI", "City Government"],
    date: "2026-05",
    summary:
      "Why state and local government keeps defaulting to Microsoft 365 Copilot when the private sector won't, what the head-to-head numbers actually say, and a one-page procurement checklist for getting your agency onto AI tools that work.",
    seoTitle: "Microsoft 365 Copilot for Government: What the Numbers Say, and What to Buy Instead",
    metaDescription:
      "Why state and local government defaults to Microsoft 365 Copilot, the head-to-head benchmarks against the alternatives, and a one-page AI procurement checklist.",
    links: [
      {
        label: "Procurement checklist (PDF)",
        url: "/assets/government-ai-procurement-guide.pdf",
      },
      {
        label: "Procurement checklist (markdown)",
        url: "/assets/government-ai-procurement-guide.md",
      },
    ],
  },
  {
    slug: "nyc-property-tax-map",
    title: "NYC Property Tax: Who Pays, Who Doesn't",
    categories: ["City Government", "State Government", "Using AI", "NYC"],
    date: "2026-04",
    summary:
      "An interactive parcel-level map of New York City's effective property-tax rates — plus the long answer to why two identical brownstones across the street from each other can pay wildly different bills.",
    seoTitle: "NYC Property Tax Rates by Neighborhood and Building Class: Who Pays, Who Doesn't",
    metaDescription:
      "Interactive parcel-level map of NYC effective property-tax rates, with the long answer to why neighbors pay wildly different bills.",
  },
  {
    slug: "nyc-public-grocery-math",
    title: "The Math on NYC's Public Grocery Plan",
    categories: ["City Government", "NYC"],
    date: "2026-04",
    summary:
      "A per-store 10-year P&L for Mayor Mamdani's five city-owned grocery stores, a check on what nutrition a $40k income buys you in the Bronx, and a ranked comparison to what the same $70M would buy if the goal were to feed more people.",
    seoTitle: "The Cost of NYC's City-Owned Grocery Stores: A 10-Year P&L per Store",
    metaDescription:
      "A 10-year P&L for Mayor Mamdani's five city-owned grocery stores, plus a ranked comparison of what $70M would buy if the goal were feeding more people.",
    links: [
      {
        label: "Download the financial model (.xlsx)",
        url: "/assets/nyc-public-grocery-model.xlsx",
      },
      {
        label: "The update: the announced 30% discount",
        url: "/gizmo/nyc-public-grocery-new-math",
      },
    ],
  },
  {
    slug: "reducing-violence-whitepaper",
    title: "Reducing Violent Crime Without New Budget, New Staff, or More Arrests",
    categories: ["Public Safety", "City Government"],
    date: "2026-03",
    summary:
      "A pragmatic guide for city leaders on using environmental interventions and cross-department coordination to reduce violence, with Dallas's 2024\u20132025 implementation as a case study.",
    seoTitle: "Reducing Violent Crime Without New Budget, New Staff, or More Arrests: A City Playbook",
    metaDescription:
      "Violent crime concentrates on 3 to 5% of a city's blocks. A whitepaper on place-based fixes and cross-department coordination, with Dallas's 2024 to 2025 results.",
    links: [
      {
        label: "Read the whitepaper",
        url: "/assets/reducing-violence-whitepaper/",
      },
      {
        label: "Download the PDF",
        url: "/assets/reducing-violence-whitepaper/Reducing_Violent_Crime_17A.pdf",
      },
    ],
  },
  {
    slug: "fakebook-maker",
    title: "Jazz Fakebook Maker",
    categories: ["Music", "Using AI"],
    date: "2026-02",
    summary:
      "A Python tool that converts plain-text chord charts into a searchable, bookmarked PDF fake book \u2014 built for reading on a laptop on a piano stand.",
    seoTitle: "Jazz Fakebook Maker: Turn Chord Charts into a Bookmarked PDF Fake Book",
    metaDescription:
      "A Python tool that converts plain-text chord charts into a searchable, bookmarked PDF fake book for a laptop on a piano stand. Free code and a public-domain edition.",
    links: [
      { label: "Get the code on GitHub", url: "https://github.com/eichenbaumj/fakebook-maker" },
      { label: "Download the fakebook (public-domain edition)", url: "/assets/fakebook.pdf" },
    ],
  },
  {
    slug: "claude-code-usage",
    title: "Using Claude Code to Understand How I Use Claude Code \u2014 and My Time",
    categories: ["Using AI"],
    hidden: true,
    date: "2026-04",
    summary:
      "A usage analysis of ~95 hours of Claude Code across 81 sessions \u2014 tracking where my time actually goes, day-to-day, as a consultant using AI tools.",
  },
];
