"""Stage 08a — pull city-government payroll (individual employees with job titles).

For each city in config.CITY_SOURCES: latest year, full-time salaried rows only,
via the Socrata SODA API (paginated). Standardised to a single "annual pay" + a
free-text title. Resumable (skips cached parquet).

Output: raw/cities/{key}.parquet  (title, pay_annual, year, city, state)
Run: python 08a_fetch_cities.py
"""

from __future__ import annotations

import re
import sys
import time

import pandas as pd
import requests

import config
from fetchers import UA

CITY_RAW = config.RAW_DIR / "cities"
CITY_RAW.mkdir(parents=True, exist_ok=True)
PAGE = 50000


def _num(x) -> float:
    if x is None:
        return float("nan")
    if isinstance(x, (int, float)):
        return float(x)
    s = re.sub(r"[^0-9.\-]", "", str(x))
    # keep only a leading sign + first decimal point (drops malformed sci-notation)
    s = re.sub(r"(?<=.)-", "", s)
    if s.count(".") > 1:
        head, _, tail = s.partition(".")
        s = head + "." + tail.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def soda(domain: str, dataset: str, params: dict) -> list[dict]:
    url = f"https://{domain}/resource/{dataset}.json"
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — transient throttle / non-JSON
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return []


def fetch_city(src: dict) -> pd.DataFrame:
    domain, ds = src["domain"], src["dataset"]
    where = src["where"]
    year = None
    if src.get("year_col"):
        yc = src["year_col"]
        # distinct years -> pick the latest COMPLETE year (never the partial current
        # year, which holds year-to-date accumulated pay for some cities).
        res = soda(domain, ds, {"$select": yc, "$group": yc, "$order": f"{yc} desc", "$limit": 40})
        yrs = sorted({int(float(r[yc])) for r in res if r.get(yc) not in (None, "")}, reverse=True)
        year = next((y for y in yrs if y <= config.CITY_MAX_COMPLETE_YEAR), yrs[0] if yrs else None)
        if year is not None:
            q = f"'{year}'" if src.get("year_text") else f"{year}"
            where = f"{where} AND {yc}={q}"
    rows: list[dict] = []
    offset = 0
    while True:
        params = {
            "$select": f"{src['title_col']} as title, {src['pay_col']} as pay",
            "$where": where, "$limit": PAGE, "$offset": offset,
        }
        chunk = soda(domain, ds, params)
        if not chunk:
            break
        rows.extend(chunk)
        offset += PAGE
        if len(chunk) < PAGE:
            break
        time.sleep(0.4)
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"{src['key']}: no rows returned (check where-clause)")
    df["pay"] = df["pay"].map(_num)
    if src["pay_kind"] == "hourly":
        df["pay_annual"] = df["pay"] * 2080
    else:
        df["pay_annual"] = df["pay"]
    df = df[(df["pay_annual"] > 10000) & (df["pay_annual"] < 1_000_000)]
    df["title"] = df["title"].astype(str)
    df["city"] = src["key"]
    df["state"] = src["state"]
    df["data_year"] = int(year) if (year and str(year).isdigit()) else config.CITY_DATA_YEAR_DEFAULT
    return df[["city", "state", "title", "pay_annual", "data_year"]]


def main() -> None:
    print(f"Stage 08a — city payroll ({len(config.CITY_SOURCES)} cities)")
    for src in config.CITY_SOURCES:
        out = CITY_RAW / f"{src['key']}.parquet"
        if out.exists():
            print(f"  {src['key']}: cached")
            continue
        try:
            df = fetch_city(src)
            df.to_parquet(out, index=False)
            print(f"  {src['key']}: {len(df):,} FT rows, year {df['data_year'].iloc[0]}, "
                  f"median ${df['pay_annual'].median():,.0f}")
        except Exception as e:  # noqa: BLE001
            print(f"  {src['key']}: FAILED — {e}", file=sys.stderr)
    print("Stage 08a done.")


if __name__ == "__main__":
    main()
