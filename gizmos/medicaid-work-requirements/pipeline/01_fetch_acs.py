"""Stage 01 — fetch ACS 5-Year 2024 tract and county data for all required tables.

We pull every table listed in config.ACS_TABLES at both tract and county
resolution, with both estimates and margins of error. Output is two long-form
parquet files (one per geography) that downstream stages join on GEOID.

Per-(state × table) calls are resumable: if a call has already been written
to raw/by_state/<geo>/<table>__<state>.parquet, we skip it.

Requires CENSUS_API_KEY in environment (or .env.local). Without a key the
Census API rate-limits to 500 calls/day — we make ~714 (51 states × 14
tables), so a key is effectively required for a full national run.

Run: python 01_fetch_acs.py
     MWR_SAMPLE_STATE=PA python 01_fetch_acs.py   # one-state mode
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm import tqdm

import config

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env.local")
load_dotenv(Path(__file__).parent / ".env")

API_KEY = os.environ.get("CENSUS_API_KEY")
if not API_KEY:
    print(
        "ERROR: CENSUS_API_KEY not set. Get a free key from "
        "https://api.census.gov/data/key_signup.html and add it to "
        ".env.local at the repo root or to pipeline/.env.\n"
        "We make ~700 API calls; without a key you hit the 500/day limit.",
        file=sys.stderr,
    )
    sys.exit(1)

BY_STATE_TRACT = config.RAW_DIR / "by_state_tract"
BY_STATE_COUNTY = config.RAW_DIR / "by_state_county"
BY_STATE_TRACT.mkdir(parents=True, exist_ok=True)
BY_STATE_COUNTY.mkdir(parents=True, exist_ok=True)

ACS_TRACT_OUT = config.RAW_DIR / "acs_tract.parquet"
ACS_COUNTY_OUT = config.RAW_DIR / "acs_county.parquet"


def _which_states() -> list[str]:
    sample = os.environ.get("MWR_SAMPLE_STATE", "").strip().upper()
    if not sample:
        return config.ALL_STATE_FIPS
    # Accept either FIPS or 2-letter abbr
    if len(sample) == 2 and sample.isalpha():
        match = [f for f, info in config.STATE_INFO.items() if info["abbr"] == sample]
        if not match:
            print(f"ERROR: unknown state abbreviation {sample!r}", file=sys.stderr)
            sys.exit(1)
        return match
    if sample in config.STATE_INFO:
        return [sample]
    print(f"ERROR: unknown state FIPS {sample!r}", file=sys.stderr)
    sys.exit(1)


def fetch_table_for_state(
    table_id: str,
    state_fips: str,
    *,
    geography: str,
) -> pd.DataFrame:
    """Fetch one ACS table for one state at the given geography level.

    geography is "tract" or "county".
    """
    if geography == "tract":
        params = {
            "get": f"group({table_id})",
            "for": "tract:*",
            "in": f"state:{state_fips}",
            "key": API_KEY,
        }
    elif geography == "county":
        params = {
            "get": f"group({table_id})",
            "for": "county:*",
            "in": f"state:{state_fips}",
            "key": API_KEY,
        }
    else:
        raise ValueError(f"Unknown geography: {geography}")

    resp = requests.get(config.ACS_BASE_URL, params=params, timeout=120)
    if resp.status_code == 204:
        return pd.DataFrame()
    resp.raise_for_status()
    rows = resp.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])

    # Convert numeric columns (everything starting with the table prefix)
    for col in df.columns:
        if col.startswith(table_id + "_") and (col.endswith("E") or col.endswith("M")):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Build GEOID
    if geography == "tract":
        df["GEOID"] = df["state"] + df["county"] + df["tract"]
    else:
        df["GEOID"] = df["state"] + df["county"]

    return df


def cached_fetch(table_id: str, state_fips: str, geography: str) -> pd.DataFrame:
    cache_dir = BY_STATE_TRACT if geography == "tract" else BY_STATE_COUNTY
    cache_path = cache_dir / f"{table_id}__{state_fips}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    df = fetch_table_for_state(table_id, state_fips, geography=geography)
    df.to_parquet(cache_path, index=False)
    return df


def fetch_all(geography: str) -> pd.DataFrame:
    """Fetch every (state × table) for the given geography. Returns merged frame."""
    state_fips_list = _which_states()
    per_table_frames: dict[str, list[pd.DataFrame]] = {tid: [] for tid in config.ACS_TABLES}

    total_calls = len(state_fips_list) * len(config.ACS_TABLES)
    progress = tqdm(total=total_calls, desc=f"ACS {geography}", unit="call")
    for table_id in config.ACS_TABLES:
        for state_fips in state_fips_list:
            try:
                df = cached_fetch(table_id, state_fips, geography)
                if not df.empty:
                    df = df.copy()
                    df["_state_fips"] = state_fips
                    per_table_frames[table_id].append(df)
            except requests.HTTPError as e:
                print(
                    f"\n  WARN: {table_id} {state_fips} {geography} failed: {e}",
                    file=sys.stderr,
                )
            progress.update(1)
    progress.close()

    # Each table becomes a wide DataFrame keyed by GEOID. Then we merge across
    # tables to produce the final long-per-geography frame.
    table_wides: dict[str, pd.DataFrame] = {}
    for table_id, frames in per_table_frames.items():
        if not frames:
            print(f"  WARN: no rows fetched for {table_id} at {geography}", file=sys.stderr)
            continue
        combined = pd.concat(frames, ignore_index=True)
        # Keep only the table's columns + GEOID + state, drop the geography
        # path columns that vary by geo level
        keep = ["GEOID", "_state_fips"] + [c for c in combined.columns if c.startswith(table_id + "_")]
        table_wides[table_id] = combined[keep].drop_duplicates(subset=["GEOID"]).reset_index(drop=True)

    # Outer-merge all tables on GEOID
    merged: pd.DataFrame | None = None
    for table_id, w in table_wides.items():
        if merged is None:
            merged = w
        else:
            merged = merged.merge(w.drop(columns=["_state_fips"]), on="GEOID", how="outer")
    return merged if merged is not None else pd.DataFrame()


def main() -> None:
    print(f"ACS vintage: 5-Year {config.ACS_VINTAGE}")
    print(f"Tables: {len(config.ACS_TABLES)} ({', '.join(config.ACS_TABLES.keys())})")
    states = _which_states()
    print(f"States: {len(states)}")
    print(f"Cache: {BY_STATE_TRACT} and {BY_STATE_COUNTY}")
    print()

    print("Fetching tract-level...")
    tract_df = fetch_all("tract")
    tract_df.to_parquet(ACS_TRACT_OUT, index=False)
    print(f"  -> {ACS_TRACT_OUT.relative_to(config.PIPELINE_DIR)}: "
          f"{len(tract_df):,} tracts × {len(tract_df.columns):,} cols")

    print()
    print("Fetching county-level...")
    county_df = fetch_all("county")
    county_df.to_parquet(ACS_COUNTY_OUT, index=False)
    print(f"  -> {ACS_COUNTY_OUT.relative_to(config.PIPELINE_DIR)}: "
          f"{len(county_df):,} counties × {len(county_df.columns):,} cols")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 01 done in {time.time() - t0:.1f}s")
