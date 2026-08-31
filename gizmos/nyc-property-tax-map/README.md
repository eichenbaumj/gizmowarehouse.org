# NYC Property Tax Map — source

The data prep, modeling, and map-prototyping work behind the parcel-level NYC property-tax map at `/gizmo/nyc-property-tax-map`.

## Status (as of last update)

- **Citywide build complete.** All five boroughs, ~856k tax lots, FY24/25 DOF data via PVAD dataset `8y4t-faws` joined to MapPLUTO 25v4 geometry from DCP's ArcGIS feature server.
- **Citywide median ETR: 0.81%** (842k parcels with valid ETR). p10 = 0.47%, p90 = 4.35%.
- **Tile pipeline (v2) shipped.** `parcels.pmtiles` is **103 MB** (down from 516 MB v1) via property trimming, z=12-15 zoom range, and `--maximum-tile-bytes=500000`. Plus a 4.6 MB `nta-aggregates.geojson` for low-zoom (z<12) neighborhood-median rendering. Both deployed to Cloudflare R2 (bucket `gizmo-warehouse-data`).
- **Five render modes** in the frontend: $/sqft (default), DOF market value, ETR vs citywide median, ETR vs same-class median, abatement intensity. Two-layer (NTA aggregates at low zoom, parcel polygons at high zoom).
- **Address search** wired through NYC PAD (geosearch.planninglabs.nyc) so user-entered addresses (e.g. "111 Hicks Street") resolve to the right BBL even when the tax-lot's primary address differs (e.g. St. George Tower files as "44 Pineapple Street").
- **Tax rates verified** against NYC Open Data dataset `7zb8-7bpk` ("Property Tax Rates by Tax Class"). Rates applied: FY24/25 — Class 1 20.085%, Class 2 12.500%, Class 3 11.181%, Class 4 10.762%.

## What's rendered vs hidden

Not every parcel is shown. The frontend filters out parcels that are legally tax-exempt or otherwise produce visual artifacts (e.g. a giant dark blob over Greenwood Cemetery in $/sqft mode because a tiny maintenance building divides into a multi-million-dollar bill). The filter lives in `src/components/NYCPropertyTaxMap.tsx` as `SHOWABLE_PARCEL`.

**Hidden via building-class prefix:**
- `V*` — vacant land
- `Z*` — parks, cemeteries, public open space
- `T*` — transit (MTA yards, etc.)
- `Q*` — outdoor recreation (golf courses, beaches, marinas)
- `M*` — religious (churches, mosques, synagogues)
- `W*` — educational structures (schools, colleges)
- `I*` — hospitals & health institutional
- `P*` — public-sector facilities (libraries, post offices, civic)
- `Y*` — selected government installations

**Hidden via tax class:**
- Tax class 3 (utility special franchises like Verizon, Con Ed) — billed at the entity level, not the parcel level. ~19 parcels citywide.

**Explicitly *kept* visible:**
- Abated 421-a / 485-x towers (building class D*/R*, exempt fraction near 100%) — these are real taxpayers paying reduced amounts and central to the post's narrative.
- Co-ops (building class C6, D4 etc.) — real taxpayers, but DOF MV understated; co-op ETRs read mechanically high in the data. Methodology note in the post calls this out.

If we ever want a debug "show all" toggle (to verify what's been filtered, or to inspect specific parcels), the cleanest place to add it is a UI checkbox that conditionally swaps `SHOWABLE_PARCEL` for `true`.

## Known limits

- **DOF Market Value caveats:** Class 1 capped assessments and DOF's income-cap method for Class 2C/D4 co-ops both systematically depress reported market value relative to actual sales-implied value. The Phase A.5 sense-check (vs StreetEasy comps, ~30 stratified parcels including St. George) hasn't been run yet — it's the gating step before publishing the post publicly.
- **Hosting on Cloudflare R2.** Bucket `gizmo-warehouse-data`, served via the custom domain `https://data.gizmowarehouse.org` (we don't use the bucket's `pub-*.r2.dev` URL — DNS filters block those; full story in `tools/HOSTING_DATA.md`). Files under prefix `nyc-property-tax/`. Setup steps in `R2_SETUP.md`. Credentials in repo-root `.env.local` (gitignored).
- **Bill calculation is simplified.** `tax_bill = (billable AV − exemptions) × statutory rate` ignores dollar-amount abatements (J-51, ICAP, SCHE/DHE) that are applied AFTER the rate. Spot checks against DOF's published bills should be within ~5–10% on parcels with active dollar abatements.

## Pipeline

Reproducible from a single command. See `pipeline/build.sh`.

```
pipeline/
  config.py                — paths, source URLs, tax rates, fiscal-year stamp
  01_fetch_pluto.py        — DCP MapPLUTO ArcGIS export (with geometry)
  02_fetch_pvad.py         — DOF Property Valuation and Assessment Data (current)
  03_compute_tax_bill.py   — join PLUTO + PVAD on BBL; compute bill, ETR, $/sqft
  04_aggregate.py          — citywide medians + per-class stats + NTA aggregates
  05_build_tiles.sh        — tippecanoe → PMTiles (z=12-15, slim properties)
  06_upload_r2.py          — push to Cloudflare R2 via boto3
  build.sh                 — orchestrator (--sample-zip 11201 / --sample-boro BK / full)
  cors.json                — R2 CORS rule (already applied)
  raw/                     — downloaded source CSVs + GeoJSON (gitignored)
  output/                  — derived artifacts (parcels_with_tax*.geojson, *.pmtiles)
```

Citywide run end-to-end (April 2026):

| Stage | Time |
|---|---|
| 01 PLUTO fetch (paginated ArcGIS) | ~12 min |
| 02 PVAD fetch (5 boros sequentially) | ~35 min |
| 03 Join + compute | ~5 min |
| 04 Aggregate + NTA spatial join | ~3 min |
| 05 Tippecanoe → PMTiles | ~2 min |
| 06 R2 upload (103 MB + 4.6 MB) | ~30 sec on home bandwidth |

Disk: raw is ~3.7 GB, output is ~1.4 GB. Both gitignored.

## Frontend

- `src/config/nycPropertyTaxMap.ts` — colors, zoom curves, render mode bins, R2 source URLs
- `src/components/NYCPropertyTaxMap.tsx` — MapLibre map, five render modes, NTA + parcel two-layer architecture, parcel filter (`SHOWABLE_PARCEL`), legend, hover tooltip, click-pin parcel detail panel, address search via NYC PAD
- `src/content/embeds.ts` — registry mapping `<nyc-tax-map>` markdown tag to the React component (generalizable to future gizmos)
- `src/pages/GizmoPage.tsx` — extended ReactMarkdown with the embed registry
- `src/content/nyc-property-tax-map.ts` — post markdown including the `<nyc-tax-map></nyc-tax-map>` embed in section 3

## Outstanding

1. **Phase A.5 FMV sense-check** — sample ~30 parcels (St. George + stratified by class/borough/building form), pull StreetEasy comps via Chrome MCP, compute `streeteasy_implied_mv / dof_mv` ratio. Decide whether to ship with DOF MV alone or layer in a sales-adjusted denominator. Decision rule: ship DOF MV alone unless the sampled ratio shows systematic drift by class.
2. **Content polish** — sections 1 and 2 may want one more pass; sections 3, 4, 5 are in good shape as of 2026-04-29.
3. **Optional debug "show all" toggle** — to inspect filtered-out parcels for QA / corner cases.

## References

- NYC Open Data `8y4t-faws` (Property Valuation and Assessment Data Tax Classes 1,2,3,4) — currently active, updated through FY26 tentative
- NYC Open Data `7zb8-7bpk` (Property Tax Rates by Tax Class)
- DCP MapPLUTO ArcGIS FeatureServer (`https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/ArcGIS/rest/services/MAPPLUTO/FeatureServer/0`)
- NYC Open Data `9nt8-h7nd` (NTA 2020 boundaries)
- NYC PAD geocoder (`https://geosearch.planninglabs.nyc/v2/autocomplete`)
- `nyc-property-tax-map-data-sources.md` — original scoping doc
- `R2_SETUP.md` — Cloudflare R2 setup replay
