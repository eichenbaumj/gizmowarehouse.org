"""Stage 03 — fetch administrative-source calibration data.

We need several non-ACS sources to calibrate ACS's known Medicaid undercount
to real administrative levels. Some of these have clean URLs; others require
periodic manual downloads. This stage handles the automatable ones and checks
that the manual ones have been placed in raw/manual/ with documented contents.

Automated:
  - BLS LAUS county unemployment (12-month series ending Jan 2026)

Manual (documented in raw/manual/README.md — must be present before running):
  - kff_expansion_enrollment.csv          # KFF state expansion enrollment
  - cms_tmsis_state_enrollment.csv        # CMS T-MSIS state monthly enrollment
  - sahie_county_medicaid.csv             # Census SAHIE county Medicaid coverage
  - samhsa_nsduh_sud_state.csv            # SAMHSA NSDUH state SUD prevalence
  - kff_hardship_county_eligibility.csv   # KFF May 2026 hardship-exception qualifying counties

Run: python 03_fetch_admin_calibration.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

import config

MANUAL_DIR = config.RAW_DIR / "manual"
MANUAL_DIR.mkdir(parents=True, exist_ok=True)

EXPECTED_MANUAL_FILES = {
    "kff_expansion_enrollment.csv": (
        "KFF state-level Medicaid expansion enrollment. Download from\n"
        "https://www.kff.org/medicaid/state-indicator/medicaid-expansion-enrollment/\n"
        "Required columns: state_abbr, expansion_enrollment\n"
    ),
    "cms_tmsis_state_enrollment.csv": (
        "CMS T-MSIS monthly state enrollment, latest quarter. Download from\n"
        "https://www.medicaid.gov/medicaid/data-and-systems/macbis/medicaid-and-chip-enrollment-data/\n"
        "Required columns: state_abbr, month, expansion_adults_19_64\n"
    ),
    "sahie_county_medicaid.csv": (
        "Census SAHIE county Medicaid coverage estimates, latest vintage.\n"
        "https://www.census.gov/programs-surveys/sahie.html\n"
        "Required columns: state_fips, county_fips, medicaid_count, medicaid_moe\n"
    ),
    "samhsa_nsduh_sud_state.csv": (
        "SAMHSA NSDUH state SUD prevalence, latest release. Download from\n"
        "https://www.samhsa.gov/data/release/2023-national-survey-drug-use-and-health-nsduh-releases\n"
        "Required columns: state_abbr, sud_past_year_pct_18_64\n"
    ),
    "kff_hardship_county_eligibility.csv": (
        "KFF list of counties qualifying for high-unemployment hardship exception\n"
        "(May 2026 analysis based on Feb 2025 - Jan 2026 BLS data).\n"
        "Required columns: state_fips, county_fips, county_name, "
        "unemployment_12mo_avg_pct, qualifies\n"
    ),
}


def fetch_bls_laus() -> Path:
    """Download BLS LAUS county unemployment text file and parse to CSV."""
    out = config.RAW_DIR / "bls_laus_county_2025.csv"
    if out.exists():
        print(f"  cache hit: {out.name}")
        return out

    print(f"  downloading BLS LAUS: {config.BLS_LAUS_URL}")
    # BLS rejects requests without a User-Agent header (403 Forbidden).
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (17A / gizmo-warehouse / medicaid-work-requirements pipeline)",
    }
    import time as _time
    last_exc = None
    for attempt in range(1, 5):
        if attempt > 1:
            print(f"    retry {attempt}/4 after {2 ** (attempt - 1)}s backoff")
            _time.sleep(2 ** (attempt - 1))
        try:
            resp = requests.get(config.BLS_LAUS_URL, timeout=120, headers=headers)
            resp.raise_for_status()
            break
        except (requests.RequestException, requests.exceptions.ChunkedEncodingError) as e:
            last_exc = e
            print(f"    network error: {type(e).__name__}: {e}")
    else:
        raise RuntimeError("BLS LAUS download failed after 4 attempts") from last_exc

    # BLS LAUS county file format is fixed-width with a header block followed
    # by data rows. Parse with pandas using whitespace delimiter on the data.
    lines = resp.text.splitlines()
    # Find first row that looks like county data (starts with "CN")
    data_start = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("CN") and "," in line),
        None,
    )
    if data_start is None:
        raise RuntimeError("Could not locate BLS LAUS data rows")

    # BLS LAUS rows are comma-delimited with fixed columns:
    # laus_code, state_fips, county_fips, county_name_state, year,
    # labor_force, employed, unemployed, unemployment_rate
    records = []
    for line in lines[data_start:]:
        if not line.strip() or not line.startswith("CN"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9:
            continue
        try:
            records.append({
                "laus_code": parts[0],
                "state_fips": parts[1],
                "county_fips": parts[2],
                "county_name": parts[3],
                "year": parts[4],
                "labor_force": parts[5].replace(",", ""),
                "employed": parts[6].replace(",", ""),
                "unemployed": parts[7].replace(",", ""),
                "unemployment_rate_pct": parts[8],
            })
        except IndexError:
            continue

    df = pd.DataFrame(records)
    for col in ["labor_force", "employed", "unemployed", "unemployment_rate_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["geoid"] = df["state_fips"] + df["county_fips"]
    df.to_csv(out, index=False)
    print(f"  -> {out.name}: {len(df):,} county-rows")
    return out


def check_manual_files() -> bool:
    """Verify all required manual downloads are present. Returns True if ok."""
    missing = []
    for name, instructions in EXPECTED_MANUAL_FILES.items():
        if not (MANUAL_DIR / name).exists():
            missing.append((name, instructions))

    readme = MANUAL_DIR / "README.md"
    readme_lines = [
        "# Manual data downloads",
        "",
        "These files cannot be reliably fetched programmatically. Download them",
        "from the URLs below and drop them in this directory. The pipeline will",
        "halt at stage 04 if any are missing.",
        "",
    ]
    for name, instructions in EXPECTED_MANUAL_FILES.items():
        readme_lines.append(f"## {name}")
        readme_lines.append("")
        readme_lines.append(instructions)
        readme_lines.append("")
    readme.write_text("\n".join(readme_lines))

    if missing:
        print()
        print("=" * 60)
        print(f"MANUAL DOWNLOADS REQUIRED: {len(missing)} file(s) missing")
        print("=" * 60)
        for name, _ in missing:
            print(f"  - {MANUAL_DIR / name}")
        print()
        print(f"See {readme.relative_to(config.PIPELINE_DIR)} for download instructions.")
        print(
            "Stage 03 will not block the pipeline yet (downstream stages will "
            "warn about missing calibration). Once collected, re-run from any stage."
        )
        return False
    return True


def main() -> None:
    print("Fetching BLS LAUS...")
    fetch_bls_laus()

    print("\nChecking manual-download artifacts...")
    ok = check_manual_files()
    if ok:
        print("  all manual files present.")
    print()


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 03 done in {time.time() - t0:.1f}s")
