# Hoyt-Schermerhorn / Downtown Brooklyn scratch extraction (2026-10-19)

Brainstorm-stage pull for a possible gizmo on the Downtown Brooklyn violent-crime hotspot
(explorer cell 40_42, #2 citywide 2024-25 behind Times Square/Port Authority).

- `extract.py` → `bbox_clean.parquet`: every NYPD complaint 2006-2026 (2026 file downloaded Sept 18 but its complaints END 2026-06-30: treat 2026 as H1 only)
  inside lat 40.678-40.699, lon -73.998 to -73.972, deduped on cmplnt_num, with dist_m from
  Hoyt-Schermerhorn station (40.6885, -73.9850), hour, dow, violent flag (ky_cd 101/105/106).
- `citywide.py` → `citywide_violent.csv`: citywide violent counts by year x ky_cd x hour x transit x boro.
- `cellrank.py` → `cellrank.csv`: 2024-25 violent counts per explorer grid cell, split by
  officer-assault and retail-robbery flags, for "where would it rank if…" ladders.

Key finding: 689 of 2,810 core (<=400 m) violent incidents 2006-2026 sit at one generalized point
(40.6901, -73.9890), ~30 m from 120 Schermerhorn St (Brooklyn Criminal Court / Central Booking);
60% of those are "assault police/peace officer". Strip officer assaults and the cell drops to #5;
strip retail (shoplift-to-robbery) too and it is #15.

## 311 (added later on 2026-10-19)

- `pull_311.py` (erm2-nwe9, 2020-present), `pull_311_2010s.py` (76ig-c548, 2010-2017 via within_circle), `pull_311_months.py`
  (76ig-c548, 2018-2019 month-by-month via numeric bbox; within_circle on those years timed out repeatedly).
- `nyc311_core450m_2010_2026.parquet` = all three merged, deduped on unique_key, clipped to 450 m of the station: 102,352 rows.
- Caveat: 311 complaint-type vocabulary changes over time (e.g. "Encampment" is a recent type; "Vendor Enforcement" starts 2023),
  and total 311 volume here grew ~4x 2010→2023, so disorder series need a denominator or an explicit "calls, not conditions" label.
- `VISUAL_CONCEPTS_2026-10-19.md`: synthesis of the 9-agent visual-storytelling workflow (storyboard, moonshot verdict, build plan),
  with the street-imagery feasibility scout, judge scores, and all five concepts appended.
