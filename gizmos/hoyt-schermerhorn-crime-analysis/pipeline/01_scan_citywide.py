"""Stage 01: the only full scan of the raw NYPD files. One duckdb pass per file, several in parallel,
writing per-file caches under output/cache/<year>_<vintage>/:

  violent_rows.parquet   every row with ky_cd in (101,102,103,105,106), slim columns
  bbox_rows.parquet      every row (any offense) inside the study bbox
  coding_agg.parquet     counts by ky_cd, ofns_desc, pd_cd, pd_desc, law_cat_cd, boro_nm (all offenses)
  time_agg.parquet       counts by boro, violent flag, hour, on-the-hour, default-time, lag bin (all offenses)
  coord_agg.parquet      counts per distinct (lat, lon) for violent rows
  stats.json             rows, min/max dates, null-coordinate counts

A file is rescanned only when its signature changed or --force is given."""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from lib import io  # noqa: E402

VIOLENT_SCAN = "('101','102','103','105','106')"
SLIM = ", ".join(config.SLIM_COLUMNS)


def scan_one(entry: dict) -> dict:
    t0 = time.time()
    key = io.file_key(entry)
    out = config.CACHE_DIR / key
    out.mkdir(parents=True, exist_ok=True)
    con = io.connect(threads=3, mem_gb=3)
    src = io.read_csv_sql(entry["path"])
    con.execute(f"CREATE TABLE raw AS SELECT {SLIM} FROM {src}")
    con.execute(f"ALTER TABLE raw ADD COLUMN src_file VARCHAR DEFAULT '{entry['path'].name}'")
    con.execute(f"ALTER TABLE raw ADD COLUMN vintage VARCHAR DEFAULT '{entry['vintage']}'")
    con.execute(f"ALTER TABLE raw ADD COLUMN file_year INTEGER DEFAULT {entry['year']}")
    con.execute("ALTER TABLE raw ADD COLUMN lat DOUBLE")
    con.execute("ALTER TABLE raw ADD COLUMN lon DOUBLE")
    con.execute("UPDATE raw SET lat = TRY_CAST(latitude AS DOUBLE), lon = TRY_CAST(longitude AS DOUBLE)")
    con.execute(f"COPY (SELECT * FROM raw WHERE ky_cd IN {VIOLENT_SCAN}) TO '{out / 'violent_rows.parquet'}' (FORMAT PARQUET)")
    b = config.BBOX
    con.execute(
        f"COPY (SELECT * FROM raw WHERE lat BETWEEN {b['lat0']} AND {b['lat1']} AND lon BETWEEN {b['lon0']} AND {b['lon1']}) "
        f"TO '{out / 'bbox_rows.parquet'}' (FORMAT PARQUET)")
    con.execute(
        f"COPY (SELECT file_year, vintage, ky_cd, ofns_desc, pd_cd, pd_desc, law_cat_cd, boro_nm, count(*) AS n "
        f"FROM raw GROUP BY ALL) TO '{out / 'coding_agg.parquet'}' (FORMAT PARQUET)")
    con.execute(
        f"""COPY (SELECT file_year, vintage, boro_nm,
                (ky_cd IN ('101','105','106')) AS violent,
                TRY_CAST(substr(cmplnt_fr_tm,1,2) AS INTEGER) AS hour,
                (substr(cmplnt_fr_tm,4,5) = '00:00') AS on_the_hour,
                (cmplnt_fr_tm IN ('00:00:00','12:00:00')) AS default_time,
                CASE WHEN TRY_CAST(substr(rpt_dt,1,10) AS DATE) IS NULL OR TRY_CAST(substr(cmplnt_fr_dt,1,10) AS DATE) IS NULL THEN 'null'
                     WHEN date_diff('day', TRY_CAST(substr(cmplnt_fr_dt,1,10) AS DATE), TRY_CAST(substr(rpt_dt,1,10) AS DATE)) < 0 THEN 'neg'
                     WHEN date_diff('day', TRY_CAST(substr(cmplnt_fr_dt,1,10) AS DATE), TRY_CAST(substr(rpt_dt,1,10) AS DATE)) = 0 THEN '0'
                     WHEN date_diff('day', TRY_CAST(substr(cmplnt_fr_dt,1,10) AS DATE), TRY_CAST(substr(rpt_dt,1,10) AS DATE)) <= 7 THEN '1-7'
                     WHEN date_diff('day', TRY_CAST(substr(cmplnt_fr_dt,1,10) AS DATE), TRY_CAST(substr(rpt_dt,1,10) AS DATE)) <= 30 THEN '8-30'
                     WHEN date_diff('day', TRY_CAST(substr(cmplnt_fr_dt,1,10) AS DATE), TRY_CAST(substr(rpt_dt,1,10) AS DATE)) <= 365 THEN '31-365'
                     ELSE '>365' END AS lag_bin,
                count(*) AS n
            FROM raw GROUP BY ALL) TO '{out / 'time_agg.parquet'}' (FORMAT PARQUET)""")
    con.execute(
        f"COPY (SELECT file_year, vintage, lat, lon, count(*) AS n FROM raw WHERE ky_cd IN ('101','105','106') GROUP BY ALL) "
        f"TO '{out / 'coord_agg.parquet'}' (FORMAT PARQUET)")
    st = con.execute(
        """SELECT count(*) AS rows,
                  min(substr(cmplnt_fr_dt,1,10)) AS fr_min, max(substr(cmplnt_fr_dt,1,10)) AS fr_max,
                  min(substr(rpt_dt,1,10)) AS rpt_min, max(substr(rpt_dt,1,10)) AS rpt_max,
                  sum(CASE WHEN ky_cd IN ('101','105','106') THEN 1 ELSE 0 END) AS violent_rows,
                  sum(CASE WHEN ky_cd IN ('101','105','106') AND (lat IS NULL OR lon IS NULL OR (lat = 0 AND lon = 0)) THEN 1 ELSE 0 END) AS violent_no_coord,
                  sum(CASE WHEN substr(cmplnt_fr_dt,1,4) = CAST(file_year AS VARCHAR) THEN 1 ELSE 0 END) AS rows_in_file_year
           FROM raw""").fetchone()
    cols = ["rows", "fr_min", "fr_max", "rpt_min", "rpt_max", "violent_rows", "violent_no_coord", "rows_in_file_year"]
    stats = {c: (int(v) if isinstance(v, (int,)) or (hasattr(v, "__int__") and not isinstance(v, str)) else v) for c, v in zip(cols, st)}
    stats["seconds"] = round(time.time() - t0, 1)
    (out / "stats.json").write_text(json.dumps(stats, indent=1, default=str))
    con.close()
    return {"key": key, "sig": io.signature(entry), "stats": stats}


def main(force: bool = False, workers: int = 6) -> None:
    manifest = io.load_manifest()
    todo = [e for e in io.raw_files() if e["path"].exists() and io.needs_scan(e, manifest, force)]
    missing = [e for e in io.raw_files() if not e["path"].exists()]
    if missing:
        raise SystemExit(f"missing raw files: {[str(e['path']) for e in missing]}")
    print(f"stage 01: {len(todo)} file(s) to scan, {len(io.raw_files()) - len(todo)} cached")
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(scan_one, e): e for e in todo}
        for f in as_completed(futs):
            r = f.result()
            manifest[r["key"]] = {"sig": r["sig"], "stats": r["stats"]}
            io.save_manifest(manifest)
            s = r["stats"]
            print(f"  {r['key']}: {s['rows']:,} rows, violent {s['violent_rows']:,}, fr {s['fr_min']}..{s['fr_max']}, "
                  f"rpt max {s['rpt_max']}, {s['seconds']}s", flush=True)
    print("stage 01 done")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    main(force=a.force, workers=a.workers)
