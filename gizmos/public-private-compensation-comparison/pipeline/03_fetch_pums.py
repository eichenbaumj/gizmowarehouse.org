"""Stage 03 — ACS PUMS microdata pull (the workhorse engine).

Pulls person records from the Census microdata API, server-side filtered to the
analysis frame (age 25-64, class-of-worker 1-5 = wage/salary employees, all
government tiers + private). Per state-year, resumable (skips cached parquet).

  Endpoint: https://api.census.gov/data/{year}/acs/acs1/pums
  ~80k rows / state-year (NY) at ~5 MB / 3 s — verified 2026-06-17.

Output: raw/pums/{year}_{fips}.parquet  (one per state-year; gitignored)
Run: python 03_fetch_pums.py
     PPC_YEARS=2023 python 03_fetch_pums.py        # one-year mode
     PPC_STATES=36,06 python 03_fetch_pums.py       # subset of states
"""

from __future__ import annotations

import os
import sys
import time

import pandas as pd
import requests

import config
from fetchers import UA

PUMS_RAW = config.RAW_DIR / "pums"
PUMS_RAW.mkdir(parents=True, exist_ok=True)


def which_years() -> list[int]:
    env = os.environ.get("PPC_YEARS", "").strip()
    if env:
        return [int(y) for y in env.split(",")]
    return config.PUMS_YEARS


def which_states() -> list[str]:
    env = os.environ.get("PPC_STATES", "").strip()
    if env:
        return [s.zfill(2) for s in env.split(",")]
    return config.ALL_STATE_FIPS


def fetch_state_year(year: int, fips: str) -> pd.DataFrame:
    variables = config.pums_vars_for_year(year)
    params = {
        "get": ",".join(variables),
        "AGEP": "25:64",
        "COW": "1,2,3,4,5",
        "for": f"state:{fips}",
    }
    if config.CENSUS_API_KEY:
        params["key"] = config.CENSUS_API_KEY
    url = config.PUMS_BASE.format(year=year)
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=120)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:  # noqa: BLE001 — network flake; retry
            if attempt == 3:
                raise
            print(f"    retry {attempt+1} ({fips}/{year}): {e}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    hdr, rows = data[0], data[1:]
    df = pd.DataFrame(rows, columns=hdr)
    # Drop the duplicate predicate columns the API echoes (e.g. AGEP, COW, state).
    df = df.loc[:, ~df.columns.duplicated()]
    num = ["PWGTP", "WAGP", "AGEP", "WKHP", "SCHL", "WKWN", "WKW", "ADJINC", "ESR", "SEX", "RAC1P"]
    for c in num:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["year"] = year
    df["state_fips"] = fips
    df["state_abbr"] = config.STATE_FIPS[fips]
    return df


def main() -> None:
    years, states = which_years(), which_states()
    print(f"Stage 03 — PUMS pull: {len(years)} years x {len(states)} states "
          f"= {len(years)*len(states)} state-years")
    if not config.CENSUS_API_KEY:
        print("WARNING: no CENSUS_API_KEY — the microdata API will rate-limit.", file=sys.stderr)
    done = skipped = 0
    for year in years:
        for fips in states:
            out = PUMS_RAW / f"{year}_{fips}.parquet"
            if out.exists():
                skipped += 1
                continue
            df = fetch_state_year(year, fips)
            df.to_parquet(out, index=False)
            done += 1
            if done % 10 == 0:
                print(f"  {done} fetched ({year} {config.STATE_FIPS[fips]}: {len(df):,} rows)")
            time.sleep(0.2)
    print(f"Stage 03 done. fetched={done} skipped(cached)={skipped}")


if __name__ == "__main__":
    main()
