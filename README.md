# gizmowarehouse.org

Code, write-ups, and data behind **[gizmowarehouse.org](https://gizmowarehouse.org)** —
Joe Eichenbaum's public archive of things he's built that seemed worth keeping.

This repository is a generated mirror: it contains the site plus the source
material for the gizmos **currently live** on the site, and nothing else.
Work in progress lives in a private working repo; a sync gate publishes a
gizmo's code here only once the gizmo itself is live. History is a series of
snapshot commits, so file history here is intentionally shallow.

## The gizmos

- **[Music Theory with LLMs](https://gizmowarehouse.org/gizmo/gospel-of-claude-code)** (2026-08) — Using Claude Code to write gospel reharmonizations for the fake book, and why next-chord prediction is a natural LLM task.
- **[Pricing the Fear of Data Centers](https://gizmowarehouse.org/gizmo/data-center-restriction-cost)** (2026-08) — A town that says no to a data center gives up tax revenue, not jobs, and how much depends on the local tax regime. Opposition is not partisan, legislatures are choosing conditions over bans, and blocked projects go quiet more than they resurface. A national map of restrictions and conditions, a calculator for what one campus pays a town, and the terms to demand if the answer is yes.
- **[The New Math on NYC's Public Grocery Stores](https://gizmowarehouse.org/gizmo/nyc-public-grocery-new-math)** (2026-08) — Mayor Mamdani's stores will sell a core basket 30% below market, and nobody has priced that promise. This update does: about $167M over ten years, reaching roughly 12,000 households when the same money could reach six to fifteen times as many.
- **[High Floor, Low Ceiling: How Public-Sector Wage Compression Erodes Public Service](https://gizmowarehouse.org/gizmo/public-private-compensation-comparison)** (2026-06) — Public pay is compressed: a high floor and a low ceiling. Government holds its own at the bottom of the labor market but falls far behind at the top, exactly where elite private pay has soared — software, law, finance, engineering. A data piece tracing the public-sector pay gap by skill, by domain, by level of government, and over time, built from ACS PUMS microdata, BLS/BEA/Census series, and city and state payroll files.
- **[These 5 Million People Are About to Lose Their Medicaid — But They Don't Have To](https://gizmowarehouse.org/gizmo/medicaid-work-requirements)** (2026-05) — Starting in 2027, the new federal Medicaid work requirement will end coverage for 5–10 million people. Most of that loss is a state operations problem, not a policy outcome. A nationwide bottom-up model of who's at risk, where they live, and what each state's verification capability looks like. Built for state Medicaid directors with seven months to get the operational pre-work done.
- **[How to Save the Government from Microsoft Copilot](https://gizmowarehouse.org/gizmo/microsoft-copilot)** (2026-05) — Why state and local government keeps defaulting to Microsoft 365 Copilot when the private sector won't, what the head-to-head numbers actually say, and a one-page procurement checklist for getting your agency onto AI tools that work.
- **[NYC Property Tax: Who Pays, Who Doesn't](https://gizmowarehouse.org/gizmo/nyc-property-tax-map)** (2026-04) — An interactive parcel-level map of New York City's effective property-tax rates — plus the long answer to why two identical brownstones across the street from each other can pay wildly different bills.
- **[The Math on NYC's Public Grocery Plan](https://gizmowarehouse.org/gizmo/nyc-public-grocery-math)** (2026-04) — A per-store 10-year P&L for Mayor Mamdani's five city-owned grocery stores, a check on what nutrition a $40k income buys you in the Bronx, and a ranked comparison to what the same $70M would buy if the goal were to feed more people.
- **[Reducing Violent Crime Without New Budget, New Staff, or More Arrests](https://gizmowarehouse.org/gizmo/reducing-violence-whitepaper)** (2026-03) — A pragmatic guide for city leaders on using environmental interventions and cross-department coordination to reduce violence, with Dallas's 2024–2025 implementation as a case study.
- **[Jazz Fakebook Maker](https://gizmowarehouse.org/gizmo/fakebook-maker)** (2026-02) — A Python tool that converts plain-text chord charts into a searchable, bookmarked PDF fake book — built for reading on a laptop on a piano stand.

Each gizmo has its write-up under `src/content/`, its interactive pieces under
`src/components/`, and its source material — pipelines, methodology notes,
build scripts — under `gizmos/<slug>/`.

## Running the site

```
npm ci
npm run dev    # http://localhost:8080
npm run build  # production build → dist/
```

## License

Code is MIT (see `LICENSE`); written content and data outputs are CC BY 4.0
(see `LICENSE-CONTENT`).
