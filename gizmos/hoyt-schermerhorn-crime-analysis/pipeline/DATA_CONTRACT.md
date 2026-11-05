# Data contract: `public/data/hoyt-schermerhorn-crime-analysis/`

Produced by `pipeline/09_export.py`; consumed by `src/components/hoyt/*` and the gizmo-local tests.
Every file carries `{"snapshot": "YYYY-MM-DD", "definitions": {...}, "partial_year": 2026, ...}` at the
top level. Class keys everywhere: `street_robbery | retail_robbery | other_assault | officer_assault |
homicide`. Zone keys: `street_stores | courthouse | transit`. Years are strings in object keys.
Front end must treat any missing optional field as "not shipped" and render nothing, never a zero.

## `context.json` (tokens for prose, flat)
```
{ "snapshot", "years": {"first": 2006, "last": 2026, "partial": 2026, "partial_through": "2026-06-30"},
  "cell": {"id": "40_42", "n_cells": 2854, "count_2024_25", "rank_all", "rank_no_officer",
           "rank_no_officer_no_retail", "times_square_count_2024_25"},
  "core": {"radius_m": 400, "violent_2006_2026", "courthouse_point_total", "courthouse_point_share_2024_25"},
  "night": {"core_share", "city_share", "gap_pp", "gap_ci": [lo, hi]},
  "index": {"core_2024_25_vs_2010s", "core_ex_courthouse_2024_25_vs_2010s", "brooklyn_2024_25_vs_2010s",
            "city_2024_25_vs_2010s"},
  "retail": {"shoplift_robbery_2010s_per_year", "shoplift_robbery_2024", "shoplift_robbery_2025",
             "petit_larceny_2010s_per_year", "petit_larceny_peak_year", "petit_larceny_peak"},
  "street_robbery": {"min_year_count", "max_year_count", "flat": true|false},
  "h1": {"rule": "reported_by_june_30", "core": {"2024","2025","2026"}, "city": {...}, "brooklyn": {...},
         "courthouse": {...}, "street_stores": {...}} }
```

## `stops.json`
```
{ "stops": [ { "id": "s01", "lat", "lon", "zone", "label", "label_status": "verified|unverified",
   "nearest_address_hint", "totals": {"all": n, "2024_25": n, "2006_2026": n},
   "by_class_year": { "2006": {"street_robbery": n, ...}, ... },
   "by_class_2024_25": {...}, "hour_hist": [24 ints, all years], "hour_hist_clean": [24 ints, no default times],
   "week": [[24 ints] x 7, Mon..Sun], "premise_mix_2023_26": {"group": n},
   "petit_larceny_by_year": {"2006": n, ...} | null,
   "footprint": GeoJSON Polygon | null  (transit stops: station footprint),
   "peak_hour", "shoplift_origin_share_2024_25" | null, "street_view_url" } ],
  "suppressed": {"n_points": k, "n_incidents": m, "rule": "fewer than 3 incidents"},
  "zones": { "street_stores": { "by_class_year": {...}, "hour_hist": [...], "hour_hist_clean": [...],
             "week": [...], "night_share", "demographics": {... only if n>=50 ...} | null }, "courthouse": {...}, "transit": {...} } }
```
Radius is NOT shipped; the front end computes `max(25, sqrt(count * m2_per_incident / pi))` metres.

## `zones.json`
```
{ "by_zone_year_class": { "street_stores": { "2006": {class: n}, ... }, ... },
  "footprints": { "core400": {...same shape...}, "core300": {...}, "core500": {...}, "cell_40_42": {...} },
  "h1": { "full": { "2024": {zone: n}, "2025": {...}, "2026": {...} },
          "reported_by_june_30": { ... } },
  "totals_2024_25": {"street_stores": n, "courthouse": n, "transit": n} }
```

## `ladder.json`
```
{ "window": "2024_25", "n_cells": 2854, "cell_id": "40_42",
  "primary": { "all": {"rank", "count"}, "no_officer": {"rank", "count"}, "no_officer_no_retail": {"rank", "count"} },
  "sensitivity": [ {"violent_rule": "primary|wide", "transit": "in|out", "vintage": "main|main_held",
                    "all": rank, "no_officer": rank, "no_officer_no_retail": rank} ... ],
  "top20": [ {"cell_id", "name", "lat", "lon", "count", "rank", "officer_share", "retail_share"} ... ],
  "hubs": [ {"name", "cell_id", "count_2024_25", "by_class_2024_25": {...}, "ratio_2024_25_vs_2010s": {class: x}, "night_share"} ],
  "courthouses": [ {"name", "cell_id", "largest_point": {"lat","lon","count","share_of_cell","officer_share","null_premise_share"}, "jump_year"} ],
  "neighbors": [ {"cell_id", "count_2024_25", "ratio_2024_25_vs_2010s"} ],
  "ladder_ok": true|false }
```

## `ribbon.json`
```
{ "geos": { "core400": { "years": ["2006",...,"2026"], "by_class": {class: [n per year]}, "partial": {"2026": true} },
            "cell_40_42": {...}, "pct_84": {...}, "brooklyn": {...}, "city": {...} },
  "index_2010s": { geo: {class|"all": [index per year]} },
  "petit_larceny": { "core400": [n per year] },
  "h1": { "rule": "reported_by_june_30", "panels": { "city": {"2024","2025","2026"}, "street_stores": {...},
          "street_robbery": {...}, "courthouse": {...} } } }
```

## `clock.json`
```
{ "hour_share": { "core400": [24 floats], "core400_clean": [24], "city": [24], "city_clean": [24], "brooklyn": [24],
                  "street_stores": [24], "courthouse": [24], "transit": [24] },
  "week": { "core400": [[24] x 7], "city": [...], "street_stores": [...], "courthouse": [...], "transit": [...] },
  "week_max": { geo: n },
  "night": { geo: {"share", "ci": [lo, hi], "n"} }, "night_gap_pp": {"value", "ci": [lo, hi]},
  "default_time_share": { geo: {"2006": x, ...} },
  "chi_square_vs_city": { geo: {"stat", "p"} }, "clock_ok": true|false }
```

## `dq.json`
```
{ "tests": [ {"id": "I1", "group": "integrity", "title", "status": "pass|warn|fail|report|skipped",
              "value": any, "threshold": any, "reading": "one plain sentence", "affects": ["claim_1"],
              "footnote": "text or null"} ... ],
  "claims": { "claim_1": {"label", "primary": {"value", "words", "footprint", "window"},
              "range": [min, max], "direction_holds": true, "publishable": true, "kill_reasons": [], "footnotes": []}, ... },
  "summary": {"gates_failed": 0, "warns": k, "killed": [...]} }
```
Claim ids: `claim_1` core 2.6x vs Brooklyn/city; `claim_2` street robbery flat; `claim_3` shoplift-origin
robbery rise; `claim_4` other felony assault rise; `claim_5` night share gap; `claim_6` courthouse point
share; `claim_7` rank ladder; `claim_8` 2026 H1.

## `footprints.geojson`
FeatureCollection of Polygons; properties `{bin, height_m (capped 60), role: "building|courthouse|station|store"}`.

## `labels.geojson`
Points; properties `{name, kind: "street|place|station|institution", status: "verified|unverified", anchor_stop_id|null}`.

## `grid.geojson`
2,854 Polygons; properties `{cell_id, name, count_2024_25, rank, is_focus (40_42 or Times Square)}`.

## `imagery.json`
```
{ "photos": [ {"key": "arrive-fulton-east", "stop_id"|null, "status": "mapillary|placeholder|shot",
   "file": "/assets/hoyt-schermerhorn-crime-analysis-photo-<key>.jpg" | null,
   "caption", "captured_at" | null, "facing_deg" | null, "attribution": "Mapillary user X, CC BY-SA 4.0" | null,
   "source_url" | null, "brief": "planned shot text for the placeholder" } ] }
```

## Downloads (`public/assets/`)
`hoyt-schermerhorn-crime-analysis-core-incidents.csv` (within 500 m, 2006-2026, violent + petit/grand
larceny + theft of services + drugs + weapons; no victim/suspect demographic columns; columns: cmplnt_num,
date, time, year, hour, dow, ky_cd, ofns_desc, pd_cd, pd_desc, law_cat_cd, prem_typ_desc, loc_of_occur_desc,
juris_desc, lat, lon, dist_m, cell_id, zone, class, point_id, default_time, lag_days, vintage),
`-yearly-series.csv` (geo, year, class, variant, count), `-cell-ranking.csv`, `-dq-audit.csv`.
First line of every CSV is a `#` comment with slug, snapshot date, and source (NYC Open Data, NYPD
Complaint Data Historic and Year-To-Date). `-data.zip` bundles the four CSVs with a generated README.md
(source, definitions, every column defined, terms); the page header links the zip, `<hs-downloads>` lists both.


## Added 2026-10-20 by stage 11 (`11_context_city.py`)

- `density.json`: `{min_denominator, count_rank, this_cell: {count_2024_25, residents, jobs}, ranks: {residents|jobs|residents_plus_jobs: {rank, n_cells, rate_per_1000_per_year, denominator}}, top20: {...}}`.
  Residents = 2020 Census PL block population; jobs = LEHD LODES 8 WAC 2022 C000 (workplace block); blocks assigned to cells by representative point; cells under 500 excluded from a rate.
- `precincts_1990.json`: `{n_precincts, city: {murder_1990, murder_2025}, precincts: {"84": {"Robbery": {"1990": n, "1993", "1998", "2001", "2025"}, ...}}, summary: [{precinct, violent_1990, violent_2025, change_pct, robbery_change_pct, fel_assault_change_pct, murder_1990, murder_2025}] sorted by change}`. Source: NYPD CompStat precinct PDFs, Historical Perspective table.
- `improvers.json`: biggest cell declines/increases 2006-08 to 2023-25 (cells with 30+/yr early), this cell, city change, and `concentration` (top-20% share, cells for half, threshold count).
- `timelapse.json`: one month, every complaint within 400 m (violent + petit/grand larceny + misdemeanor assault) with day, hour, kind, zone, rounded point, jitter seed.
- `sankey.json`: place -> class flows for 2024-25 within 400 m.
- `context.json` gains `precincts`, `improvers`, `density`, `timelapse` token blocks.
