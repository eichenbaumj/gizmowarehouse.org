# What Is Going On at Hoyt-Schermerhorn — source

DRAFT (not wired, not live, not mirrored). Preview locally only: `npm run dev`, then
http://localhost:8080/gizmo/hoyt-schermerhorn-crime-analysis (the route exists only under the dev
server, through `src/dev/drafts.tsx` and the `virtual:dev-drafts` plugin in `vite.config.ts`).

## Layout

- `pipeline/` — numbered stages 01 to 10, `config.py`, `run_all.py` (QA gates), `DATA_CONTRACT.md`,
  `DECISIONS.md`, `crosswalks/`, `tests/` (pytest). `raw/` and `output/` are gitignored and regenerable
  from the crime-data-pipeline caches in `~/Downloads/crime_data/nyc`. Cold run about 2 minutes.
- `research/` — never ships: `FINDINGS.md` (numbers ledger + corrections from the tested pipeline),
  `STORYBOARD.md` (the 13-scene plan), `VISUAL_CONCEPTS_2026-10-19.md` (the visual workflow).
- `test/` — vitest, gizmo-local (`vite.config.ts` includes `gizmos/*/test`).
- Page code: `src/config/hoytSchermerhorn.ts` (palette, scenes, data types), `src/components/hoyt/`
  (`HoytScrolly` sticky stages, `blockMapController` + `HoytBlockStage` map, `HoytClockStage`,
  `HoytRibbon`, `HoytSplits`, `HoytCards`, `HoytStrips`, `HoytChrome`, `hoytEmbeds.ts`,
  `hoyt.static.tsx`), `src/content/hoyt-schermerhorn-crime-analysis.ts` (13 scenes; every prose slot
  is an `<hs-draft>` Joe fills).
- Public data: `public/data/hoyt-schermerhorn-crime-analysis/` (JSON + GeoJSON, under 2 MB each) and
  four downloadable CSVs at `public/assets/hoyt-schermerhorn-crime-analysis-*.csv`. `tools/check-draft-leak.ts`
  strips a draft's public files from `dist/` on every build.

## Status (2026-10-19)

Pipeline GREEN (57 DQ tests, 8 claims publishable, 4 footnoted warnings). Page renders every scene on
desktop and mobile against real data. Open: Joe's prose in the DRAFT slots, imagery (Mapillary token or
phone shots), the human source on what the courthouse-point complaints physically are, reduced-motion
check on a real device, `verify_claims.py`, OG card, publish wiring (see `PUBLISH_CHECKLIST.md`).
