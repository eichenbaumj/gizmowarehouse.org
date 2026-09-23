# Pricing the Fear of Data Centers — data & methodology

**Snapshot date: 2026-08-15** (actions dataset; the outcome trace carries its own date, 2026-08-19). This document describes every dataset behind the piece at gizmowarehouse.org/gizmo/data-center-restriction-cost, with enough detail to recreate the data from public sources. Two companion downloads: `data-center-restriction-cost-actions.csv`, the full jurisdiction-action dataset, one row per documented government action with a source URL on every row, and `data-center-restriction-cost-outcomes.csv`, the full project outcome trace, one row per traced project with one or more sources per row. License: CC-BY-4.0 (with attribution to the upstream sources below, which carry their own CC-BY licenses).

## 1. What counts as a row

One row per **formal government action** concerning data center development: an adopted local moratorium, ban, zoning exclusion, project rejection, or referendum; an adopted conditions ordinance (noise, setbacks, cooling, decommissioning); an enacted state law or executive order; or a commission-approved large-load utility tariff. Bills that merely advanced are excluded, with two status-flagged exceptions carried for context: Maine LD 307 (passed the legislature, **vetoed** April 24, 2026, override failed) and Georgia SB 410 (passed the Senate only; status `pending`).

Every row is coded:

- `class` — the piece's spine. `restriction` = says no (moratorium, ban, zoning exclusion, rejection, referendum). `condition` = says yes-if (conditions ordinances, ratepayer laws, tariffs, tax conditions). `preemption` = state removal of local authority (its own class; it restricts governments, not data centers).
- `level` — `state`, `local`, or `puc` (public utility commission).
- `action_type`, `status` (enacted / in_force / expired / pending / vetoed / in_litigation), `date`, `mw_threshold` where the instrument has one, `lat`/`lon` with a `geocode` provenance field, `summary`, `source_url`, `source_name`, and `dataset` (which upstream source contributed the row).

Judgment calls (for example, how incentive pauses are classed) are logged in `pipeline/DECISIONS.md` in the project repository.

**County shading (the map's local layer).** Every local action is assigned to a county by point-in-polygon against Census county/equivalent boundaries; the map then shades each county by its most binding action **in force today**: solid red = the county government itself restricts, striped red = a restriction belonging to a town inside the county, blue = conditions only. A county is shaded even when the action is a single town's — the stripe marks exactly that case. Pending and lapsed measures are excluded from the default view (toggles add them). County-wide coding: county-typed rows, county-named authorities, Virginia-style independent cities (county-equivalents), and a short list of consolidated city-counties (Indianapolis, Nashville, Denver, and similar). Tribal and utility-district actions shade the county containing their location. Anchorage has no county polygon (the boundary file covers 49 states) and renders as a point. Two upstream coordinate errors were corrected by hand and logged (`pipeline/manual_coords.csv`). The shipped `counties.geojson` carries the per-county summary; the displayed categories are re-derived in the browser from the row data so the source and status toggles stay consistent everywhere.

## 2. Sources, exactly

**Local layer.**
- Moratorium Nation, by Michael J. Bommarito (ALEA Institute), CC-BY-4.0. Project page: `https://mjbommar.github.io/moratorium-data-2026/`; repository: `https://github.com/mjbommar/moratorium-data-2026` (carries a CITATION.cff; the companion working paper is "Moratorium Nation: A Survey of Data Center, Renewable Energy, and Battery Storage Moratoria in the United States," 2026). This is the map's largest single source (504 of the 933 local rows at this snapshot). Canonical CSV: `https://raw.githubusercontent.com/mjbommar/moratorium-data-2026/main/data/moratorium_inventory.csv` (533 instruments across 42 states as of the July 31, 2026 release; built from ~4,600 primary documents). The `sectors` column is a JSON-array string; data center rows are those whose array contains `"data_center"` (505 rows at this snapshot, of which 404 are data-center-only). Coordinates come from the file's own latitude/longitude columns.
- datacentertracker.org, built by Cam Acosta and George Ingebretsen, CC-BY 4.0 (429 of the 933 local rows at this snapshot). Endpoint: `https://datacentertracker.org/data/fights.json` (1,486 records at this snapshot). Community-assembled from public sources and marked as such; rows contributed by it carry `dataset: datacentertracker` so you can weigh them separately. A 25-row random sample was audited against primary documents and local press (2026-08-09): every sampled action was real; among the sampled rows that reach the map, two carried wrong dates and one described a project approval miscoded as a restriction. Those were corrected or removed via `pipeline/dct_overrides.json`, which logs each change with its reason.

**State layer.** Hand-curated from primary documents (session laws, executive orders, governors' veto messages) and law-firm/legislative-service analyses, with bill numbers in the `summary` field. Checked into the repository as `pipeline/state_actions.csv`.

**Utility layer.** Hand-curated from commission dockets (for example PUCO 24-0508-EL-ATA, IURC cause 46097, Georgia PSC docket 44280, Virginia SCC PUR-2025-00058, Oregon PUC UM 2377). The count of tariff states (24 approved / 6 pending) is **attributed to EEI's "Large Load Projects and Tariffs" tracker, July 2026 edition** rather than reconstructed per state, because the EEI document does not tag each state and the reconstruction is uncertain for two states.

**Footprint layer.** The map's charcoal rings size each state by data center electricity use in 2024, from EPRI's Powering Intelligence 2026 state-level dashboard (`https://powering-intelligence.epri.com/dashboard/`), which publishes per-state nominal capacity, peak load, and annual energy for 2021–2024 plus low/medium/high scenarios to 2030 and offers the data for download. The rings show 2024 historical actuals; popups add the 2030 medium scenario, labeled as such. EPRI's dashboard covers the 50 states (no District of Columbia); states under 0.5 TWh are not drawn.

**Deliberately not used as data:** Data Center Watch's blocked/delayed dollar tallies. They are developer-announced project values compiled by an industry-adjacent tracker (10a Labs); the piece quotes them only with attribution.

## 3. The outcome trace

The 28 best-documented blocked or disrupted projects (2023 through mid-2026) traced to status, from local press and government records (full trace 2026-08-08; the 13 still-open cases re-checked 2026-08-15; a displacement audit on 2026-08-19 re-verified every settled case against six pre-registered disqualification tests, with each claimed relocation adversarially reviewed). Coding rules: `rerouted` requires a documented destination; `died` means abandoned with no documented relocation; `delayed_then_built` means it proceeded at or adjacent to the original site; everything unresolved is `pending_litigating`. The audit recoded one project: Tucson's Project Blue, first coded `rerouted`, was built on the same county-owned parcel it was always planned for (the city vote rescinded a planned annexation, not the site), so it is now `delayed_then_built`. The schema also carries an optional `followup_*` marker for the softest tier of relocation evidence, a same-developer nearby build or site search not confirmed as the same project; as of 2026-08-19, no candidate for that tier survived adversarial review, so the columns are present and empty. Each project carries at least one source and a confidence flag (`medium` where sourcing leans on advocacy compilations). Claimed capital-expenditure figures are developer-announced and labeled as such. Refresh protocol: the trace's unresolved and dead rows are re-checked on the piece's quarterly refresh cadence, and status changes are recorded rather than overwritten.

## 4. Fiscal benchmarks and the calculator

The calculator's per-campus annual local revenue ranges are anchored to named cases, not modeled:

- Aggressive abatement: Morrow County, OR enterprise-zone agreements (~$2–3M/yr in fees against >$1B abated).
- Partial abatement: the Georgia state audit's representative three-building metro-Atlanta campus ($33.6M/yr gross, $5.9M abated, $27.8M collected; Georgia DOAA / Carl Vinson Institute, Dec 2025) and El Paso's Meta agreement (~$56M/yr blended across entities at 80% abatement).
- Unabated equipment tax: Virginia-style rates, where Loudoun County collected $894.5M in FY25 and budgeted $1,135.7M for FY26 (~42% of local tax funding). This range is a labeled estimate, the weakest constant in the set.

Reference campus: Tucson's Project Blue ($3.6B announced, 286 MW, ~$157M city+county revenue over 10 years per Pima County's published FAQ). The size slider is denominated in announced build cost because that is what the anchor cases are quoted in. The calculator assumes a live proposal and applies no counterfactual discount: Georgia's 30% attribution finding and JLARC's ~90% disagree too widely to average, so the assumption is stated in the piece rather than modeled. Horizon is 10 years; the piece explains why nothing extends past 2036.

This is deliberately not a per-MW model. The per-MW version requires county assessment rolls and is planned as the next phase.

## 5. Recreating the data

The pipeline is plain Python (standard library only) in the project repository under `gizmos/data-center-restriction-cost/pipeline/`:

1. `fetch_moratorium_nation.py` and `fetch_datacentertracker.py` pull the two upstream files (URLs above) into `raw/`.
2. `state_actions.csv` and `tariff_layer.csv` are the hand-curated layers (checked in, every row sourced).
3. `build_actions.py` merges the layers, dedups (same jurisdiction + action family within 60 days → the primary-document source wins), derives each state's posture, and writes `actions.json` plus the flat CSV export.
4. `build_outcomes.py` and `build_benchmarks.py` emit the trace and calculator files.
5. `run_all.py` runs everything and enforces QA gates: row counts against the upstream trackers' published totals, a source URL on every row, enum validity, geocode coverage (misses reported, never dropped), and recomputed tallies.

Counts (documented local actions, states with enacted laws, tariff states) are computed from the data at build time and recorded in the `counts` block of `actions.json` — the piece reads them from there, so prose and data cannot drift apart.

## 6. Known limits

- **Documented actions, not a census.** Discovery is news- and document-driven; small-jurisdiction actions are undercounted. Treat every count as a floor.
- The landscape moved at roughly 40–80 documented local actions per month in mid-2026. This snapshot will age quickly.
- Community-assembled rows (datacentertracker.org) are sample-audited, not row-by-row verified. The sampled error profile (dates more often than substance) likely extends to unsampled rows.
- Coordinates are jurisdiction centers, suitable for a national map and nothing finer.

Questions or corrections: joe@group17a.com.
