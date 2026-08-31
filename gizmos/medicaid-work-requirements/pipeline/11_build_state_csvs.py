"""Stage 11 — emit per-state analyst CSVs.

For each state, produce two CSVs:
  - {state_abbr}_tracts.csv: tract-level metrics + MOE columns
  - {state_abbr}_counties.csv: county-level metrics

Plus a national CSV:
  - medicaid_work_requirements_national.csv: all counties + key state-level stats

These are linked from the gizmo's downloads accordion. Analysts on state
Medicaid director teams will use the tract-level CSVs to cross-check our
estimates against their own internal data.

Output goes to public/assets/medicaid-data/ so React can fetch via /assets/.

Run: python 11_build_state_csvs.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

import config

TRACT_IN = config.OUTPUT_DIR / "tract_full.parquet"
COUNTY_IN = config.OUTPUT_DIR / "county_summary.parquet"

OUT_DIR = config.PUBLIC_ASSETS_DIR / "medicaid-data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NATIONAL_OUT = OUT_DIR / "medicaid_work_requirements_national.csv"


def _check_inputs() -> bool:
    if not TRACT_IN.exists():
        print(f"ERROR: {TRACT_IN} missing. Run stage 07 first.", file=sys.stderr)
        return False
    if not COUNTY_IN.exists():
        print(f"ERROR: {COUNTY_IN} missing. Run stage 07 first.", file=sys.stderr)
        return False
    return True


def main() -> None:
    if not _check_inputs():
        sys.exit(1)

    tract = pd.read_parquet(TRACT_IN)
    county = pd.read_parquet(COUNTY_IN)

    # Add state_abbr / state_name for human readability
    fips_to_info = {fips: info for fips, info in config.STATE_INFO.items()}
    tract["state_abbr"] = tract["state_fips"].map(lambda f: fips_to_info.get(f, {}).get("abbr", ""))
    tract["state_name"] = tract["state_fips"].map(lambda f: fips_to_info.get(f, {}).get("name", ""))
    tract["expansion"] = tract["state_fips"].map(lambda f: fips_to_info.get(f, {}).get("expansion", False))

    county["state_abbr"] = county["state_fips"].map(lambda f: fips_to_info.get(f, {}).get("abbr", ""))
    county["state_name"] = county["state_fips"].map(lambda f: fips_to_info.get(f, {}).get("name", ""))
    county["expansion"] = county["state_fips"].map(lambda f: fips_to_info.get(f, {}).get("expansion", False))

    # Round numerics for display
    numeric_cols_tract = [c for c in tract.columns if tract[c].dtype.kind in "fi"]
    tract[numeric_cols_tract] = tract[numeric_cols_tract].round(2)
    numeric_cols_county = [c for c in county.columns if county[c].dtype.kind in "fi"]
    county[numeric_cols_county] = county[numeric_cols_county].round(2)

    # Per-state CSVs
    print("Writing per-state CSVs...")
    n_states = 0
    for state_fips, info in fips_to_info.items():
        abbr = info["abbr"]
        t = tract[tract["state_fips"] == state_fips]
        c = county[county["state_fips"] == state_fips]
        if not t.empty:
            t.to_csv(OUT_DIR / f"{abbr}_tracts.csv", index=False)
        if not c.empty:
            c.to_csv(OUT_DIR / f"{abbr}_counties.csv", index=False)
        n_states += 1
    print(f"  wrote files for {n_states} states")

    # National CSV
    county.to_csv(NATIONAL_OUT, index=False)
    print(f"-> {NATIONAL_OUT.relative_to(config.REPO_ROOT)}: {len(county):,} counties")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 11 done in {time.time() - t0:.1f}s")
