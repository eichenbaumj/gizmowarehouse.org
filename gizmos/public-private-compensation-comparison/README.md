# The Public-Sector Pay Gap — source

Source materials for [the gizmo](../../src/content/public-private-compensation-comparison.ts).

How far have public-sector salaries lagged the private sector, where is the gap
widest, and how has it moved over time. The thesis: a growing economy raises the
opportunity cost of government service, and the lag concentrates at the high-skill /
high-education tail.

## What's in this folder

- `pipeline/` — the staged ETL. `config.py` holds every parameter + citation;
  `build.sh` orchestrates; numbered stages `01_…`–`12_…` pull raw data, model the
  gaps, and emit the shipped JSON. `raw/` and `output/` are gitignored.
- `crosswalks/` — versioned, hand-auditable crosswalk CSVs:
  - `soc_to_domain.csv` — detailed SOC → analyst domain (software/legal/finance/…).
  - `title_to_soc_*.csv` — free-text payroll-title → SOC overrides for the locality
    files (the fuzziest join; curated by headcount).
- `research/` — source notes, the data-survey synthesis, methodology-debate reading.
- `APPENDIX.md` — the full technical appendix, imported `?raw` by
  `src/pages/CompGapMethodology.tsx` and served at
  `/gizmo/public-private-compensation-comparison/methodology`.

## Deployed artifacts (live elsewhere)

- Prose: `src/content/public-private-compensation-comparison.ts`
- Metadata: `src/data/gizmos.ts`
- Precomputed JSON: `public/data/compgap/`
- Large aggregates (if any >25 MB): Cloudflare R2 (`data.gizmowarehouse.org`)

## Data sources (canonical, by section)

| Section | Source |
|---|---|
| Shape of public employment | Census ASPEP / Census of Governments (`govsemp`), BEA NIPA §6, BLS CES |
| Elite private pay soared | EPI State of Working America Data Library, WID / Piketty-Saez, SSA AWI |
| Public comp growth over time | BLS ECI + ECEC, BEA NIPA 6.6 (federal), OPM Pay Agent |
| Domain-level gap (engine) | ACS PUMS microdata (Census API), OEWS-by-ownership, OPM FedScope, CBO |
| Interactive (domain × gov/locality) | ACS PUMS + CA GCC + NYC `k397-673e` payroll |

See `pipeline/config.py` and `APPENDIX.md` for the full provenance + every caveat.
