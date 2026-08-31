"""Stage 04b — per-state work-hours-documentation-failure breakdown.

These are the people who ARE WORKING (or otherwise engaged in qualifying
activity) but who will lose Medicaid coverage anyway because their hours
can't be documented every month through the state portal: gig drivers,
cash-paid construction trades, people aggregating multiple part-time jobs,
seasonal workers, the self-employed, and people working variable shifts.

This is half of the "social safety net with holes" story. The other half
is exemption documentation failures (stage 04c).

Subgroups (6):
  gig_courier              — DoorDash, Uber, Lyft, Instacart, food delivery
  cash_construction        — Construction trades, day-labor, landscape
  multi_part_time          — Holding 2+ part-time jobs to add up to 80 hrs
  seasonal_ag_hosp         — Agriculture, hospitality, food service seasonality
  self_employed_other      — Self-employment that doesn't fit other buckets
  variable_shifts          — On-call, gig caregiving, variable retail/healthcare

PUMS sourcing modes
  --pums-mode full (default): download per-state ACS PUMS 5-year microdata via
      Census bulk-download (with API fallback), filter on
      (HINS4=1) × (AGEP 19-64) × (POVPIP ≤ 138) × (PWGTP > 0), classify each
      record by INDP/OCCP/COW/WKHP/WKWN into the six work-doc subgroups.
      Also computes weighted counts for the three ACS-derivable exemption
      subgroups (medically frail, caregivers of children ≤13, full-time
      students) — consumed by stage 04e. Takes 30-60 min on first run and
      ~5GB disk; both raw zips and per-state classified output are cached
      so subsequent runs are near-instant.
  --pums-mode synthetic: apply national subgroup shares to per-state subject
      pools. Parameters anchored to published Pew, BLS, KFF research. Used as
      fallback when PUMS zips/API access are unavailable.

METHODOLOGY.md §3.4 / §3.5 documents every parameter and its source.

Cached output schema:
  output/pums_state_cache/<abbr>_classified.parquet — per-state intermediate.
      Schema versioned (CACHE_SCHEMA_VERSION); v2 adds
      medically_frail_count_weighted, caregiver_under14_count_weighted,
      fulltime_student_count_weighted, subject_pool_weighted for stage 04e.

Stage output:
  output/state_workdoc_failures.parquet — columns:
      state_fips, state_abbr, state_name, subject_count,
      ex_parte_score, ex_parte_band,
      per-subgroup columns:
        {subgroup}_eligible          — N in this subgroup
        {subgroup}_doc_fail_rate     — rate
        {subgroup}_doc_failures      — N losing coverage despite working
      total_workdoc_failures_pre_rake — sum across subgroups
      pums_mode                       — 'synthetic' or 'full'

Run: python 04b_fetch_pums_workdoc_breakdown.py
     python 04b_fetch_pums_workdoc_breakdown.py --pums-mode synthetic
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

import config
from lib import pums_refine  # v8: shared Section 1931 + non-citizen refinement

STATE_SUMMARY_IN = config.PUBLIC_DATA_DIR / "medicaid-state-summary.json"
EX_PARTE_IN = config.OUTPUT_DIR / "state_ex_parte_scored.parquet"
WORKDOC_OUT = config.OUTPUT_DIR / "state_workdoc_failures.parquet"

# National subgroup shares as share of the *subject* pool (i.e., expansion
# adults who are NOT already exempt under §1902(xx)). Anchored to the
# published research below. These are starting points; --pums-mode full
# refines them with real microdata.
#
# Of the ~18.5M subject pool, the breakdown of *primary work type* is:
SYNTHETIC_SUBGROUPS = {
    "gig_courier": {
        "label": "Gig / courier (DoorDash, Uber, Lyft, Instacart)",
        "share_of_subject": 0.05,
        # Pew Research Center, "The State of Gig Work in 2021" (Dec 2021):
        # ~9% of US adults earned money from gig work in past year. For
        # Medicaid-eligible income bands, primary-income share is ~5%.
        # (SHED 2022 does not break out gig work, so it isn't used here.)
        "source": "Pew 2021 (gig prevalence in low-income bands)",
        "drivers": ["ui_wage_match", "self_attestation_accepted"],
        "base_failure_rate": 0.75,  # Arkansas-grade: very hard to document
                                    # monthly hours on 1099 income via portal
        "attenuation_per_driver": 0.65,
        "min_floor": 0.20,
        "narrative": (
            "Workers whose primary income comes from food-delivery, ride-share, "
            "or similar gig platforms. Consent-based verification — where the "
            "worker authorizes the state to pull their hours and earnings "
            "directly from the platform via API — is the cleanest path, and "
            "several gig platforms have started integrating it. States without "
            "the integration push the burden to bank screenshots and platform "
            "PDFs uploaded through the portal, which is where the failures "
            "concentrate."
        ),
    },
    "cash_construction": {
        "label": "Cash-paid construction & trades",
        "share_of_subject": 0.06,
        # BLS QCEW + ACS C24010: a large share of low-income (<138% FPL) male
        # working-age adults work in construction/extraction/maintenance. Of
        # those, the IRS 1099-NEC + cash share is roughly 40%. So ~6% of subject
        # pool (a modeled prior, not a directly-published QCEW cut).
        "source": "BLS QCEW 2024 × ACS C24010 × IRS SOI 1099-NEC 2023",
        "drivers": ["self_attestation_accepted"],
        "base_failure_rate": 0.80,
        "attenuation_per_driver": 0.55,
        "min_floor": 0.25,
        "narrative": (
            "Day-labor, residential construction subcontractors, landscape and "
            "trades workers paid in cash or by 1099. No regular pay stub the "
            "portal can accept; UI wage records often don't cover the work. "
            "Bank-account aggregation (consent-based — the worker authorizes "
            "the state to read deposit patterns from their checking account) "
            "is the emerging verification path, and a handful of states are "
            "piloting it. Without that, the fallback is tax records, which "
            "arrive too late for monthly renewal cycles."
        ),
    },
    "multi_part_time": {
        "label": "Multiple part-time jobs (aggregation failure)",
        "share_of_subject": 0.12,
        # BLS Multiple Jobholders 2024: ~5% of all employed hold multiple jobs;
        # CPS puts low-income multiple-jobholding somewhat higher (~6-8%). We use
        # a higher 12% modeled prior for the broader aggregation-failure segment
        # (hours split across employers), not just strict multiple jobholders.
        "source": "BLS Multiple Jobholders 2024 + CPS ASEC 2024",
        "drivers": ["ui_wage_match"],
        "base_failure_rate": 0.50,
        "attenuation_per_driver": 0.45,
        "min_floor": 0.12,
        "narrative": (
            "Workers holding two or three part-time jobs that, summed, exceed "
            "80 hours per month, though no single employer's pay stub does. "
            "State UI wage records aggregate all reported employment by SSN, "
            "so states with a working UI-wage match should be able to verify "
            "this group automatically. Failures concentrate where the state "
            "lacks that match. A cash or gig job that never enters the wage "
            "feed compounds the gap, but the primary cause is the missing "
            "integration, not the kind of work. This population is larger and "
            "more verifiable than the gig-economy framing suggests."
        ),
    },
    "seasonal_ag_hosp": {
        "label": "Seasonal: agriculture, hospitality, food service",
        "share_of_subject": 0.08,
        # ACS C24010 + BLS CES: ~16% of low-income working-age adults are in
        # NAICS 11 + NAICS 72. Of those, ~50% have seasonal (<40 weeks worked)
        # employment patterns. So ~8% of subject pool.
        "source": "ACS C24010 2024 + BLS CES seasonal adjustment",
        "drivers": ["ui_wage_match", "self_attestation_accepted"],
        "base_failure_rate": 0.55,
        "attenuation_per_driver": 0.45,
        "min_floor": 0.15,
        "narrative": (
            "Workers in agriculture, accommodation, and food-service whose hours "
            "are concentrated in peak months. The 80-hours-per-month bar fails "
            "in off-months even when the annual hour total is well above 80×12. "
            "OBBBA provides for an alternative hours calculation (annualizing "
            "earnings or hours over a multi-month window) that addresses this "
            "in principle, but the calculation requires manual review in states "
            "without integrated wage tooling. So the failures concentrate not "
            "in the underlying eligibility but in the operational complexity of "
            "the alternative path."
        ),
    },
    "self_employed_other": {
        "label": "Self-employed (other)",
        "share_of_subject": 0.05,
        # ACS class-of-worker self-employed (incorporated + unincorporated) for
        # low-income adults: ~10%. After removing gig/courier and cash-construction
        # subsets (above), residual self-employed is ~5%.
        "source": "ACS COW codes 2024 + residual after subgroup overlap removal",
        "drivers": ["self_attestation_accepted"],
        "base_failure_rate": 0.70,
        "attenuation_per_driver": 0.55,
        "min_floor": 0.18,
        "narrative": (
            "Workers self-employed as small contractors, tradespeople, family-"
            "business operators, freelancers in professional services, etc. — "
            "those not captured in the gig/courier or cash-construction buckets. "
            "Like cash workers, the cleanest verification path is consent-based "
            "bank-account aggregation; the conventional fallback is Schedule C "
            "or 1099 records from the prior tax year, which lag the renewal "
            "cycle by months."
        ),
    },
    "variable_shifts": {
        "label": "Variable shifts / on-call work",
        "share_of_subject": 0.06,
        # Federal Reserve SHED 2022 + Schneider/Harknett "Shift Project": ~25%
        # of low-wage retail/food/healthcare workers have schedules that vary
        # week-to-week with notice less than 1 week. Conservatively, half of
        # them dip below 80 hrs in at least one month per year.
        "source": "Federal Reserve SHED 2022 + Schneider & Harknett 2024",
        "drivers": ["ui_wage_match", "self_attestation_accepted"],
        "base_failure_rate": 0.45,
        "attenuation_per_driver": 0.50,
        "min_floor": 0.10,
        "narrative": (
            "Retail, healthcare, hospitality, and caregiving workers whose "
            "schedules vary unpredictably. The hours-per-month threshold creates "
            "a coverage cliff in slow months even when annual hours are stable."
        ),
    },
}


def _check_inputs() -> bool:
    ok = True
    if not STATE_SUMMARY_IN.exists():
        print(f"ERROR: {STATE_SUMMARY_IN} missing.", file=sys.stderr)
        ok = False
    if not EX_PARTE_IN.exists():
        print(f"ERROR: {EX_PARTE_IN} missing. Run stage 04d first.", file=sys.stderr)
        ok = False
    return ok


def state_failure_rate(subgroup_meta: dict, state_row: pd.Series | None) -> float:
    rate = subgroup_meta["base_failure_rate"]
    if state_row is not None:
        for driver in subgroup_meta["drivers"]:
            col = f"flag_{driver}"
            if state_row.get(col, False):
                rate *= subgroup_meta["attenuation_per_driver"]
        if state_row.get("integration_bonus", 0) >= 15:
            rate *= 0.80
    return max(rate, subgroup_meta["min_floor"])


def blend_waiver_to_national_avg(
    df: pd.DataFrame, subgroup_keys, total_col: str
) -> pd.DataFrame:
    """Re-rate subject-via-waiver states (WI/GA) at the subject-weighted national
    AVERAGE per-subgroup documentation-failure rate, instead of the unattenuated
    base rate they'd otherwise get for lacking an ex parte row.

    Rationale: a waiver state with no state-specific verification-feed data would
    otherwise inherit the worst-case (zero-attenuation) failure rate, implying it
    has no ex parte capability at all — indefensible for states that run
    integrated eligibility systems. Absent state-specific data, the honest prior
    is the national average, not the national worst case. Eligible counts (which
    carry the childless-only parent zeroing) are preserved; only the per-subgroup
    failure RATE is replaced, then failures are recomputed.
    """
    waiver = {f for f, w in config.WAIVER_SUBJECT.items() if w.get("control_total", 0) > 0}
    is_w = df["state_fips"].isin(waiver)
    if not is_w.any():
        return df
    exp = df[~is_w]
    for key in subgroup_keys:
        rate_col, elig_col, fail_col = f"{key}_doc_fail_rate", f"{key}_eligible", f"{key}_doc_failures"
        if rate_col not in df.columns or elig_col not in df.columns:
            continue
        w = exp["subject_count"].to_numpy(dtype=float)
        r = exp[rate_col].to_numpy(dtype=float)
        natl = float((r * w).sum() / w.sum()) if w.sum() > 0 else float(r.mean())
        df.loc[is_w, rate_col] = natl
        df.loc[is_w, fail_col] = df.loc[is_w, elig_col] * natl
    fail_cols = [f"{k}_doc_failures" for k in subgroup_keys if f"{k}_doc_failures" in df.columns]
    df.loc[is_w, total_col] = df.loc[is_w, fail_cols].sum(axis=1)
    return df


def run_synthetic() -> pd.DataFrame:
    summary = json.loads(STATE_SUMMARY_IN.read_text())
    ex_parte = pd.read_parquet(EX_PARTE_IN).set_index("state_fips")

    rows = []
    for s in summary["states"]:
        fips = s["state_fips"]
        # Process any state with a real subject pool — expansion states plus
        # subject-via-1115-waiver states (WI/GA, populated by stage 04's admin
        # rake). TN (subject 0) and true non-expansion states fall out here.
        subject = float(s["subject_count_strict"])
        if subject <= 0:
            continue
        ex_row = ex_parte.loc[fips] if fips in ex_parte.index else None

        row = {
            "state_fips": fips,
            "state_abbr": s["state_abbr"],
            "state_name": s["state_name"],
            "subject_count": subject,
            "ex_parte_score": int(ex_row["score"]) if ex_row is not None and pd.notna(ex_row.get("score")) else None,
            "ex_parte_band": ex_row["churn_band"] if ex_row is not None else None,
            "pums_mode": "synthetic",
        }

        total_failures = 0.0
        for key, meta in SYNTHETIC_SUBGROUPS.items():
            eligible = subject * meta["share_of_subject"]
            failure_rate = state_failure_rate(meta, ex_row)
            failures = eligible * failure_rate
            row[f"{key}_eligible"] = eligible
            row[f"{key}_doc_fail_rate"] = failure_rate
            row[f"{key}_doc_failures"] = failures
            total_failures += failures
        row["total_workdoc_failures_pre_rake"] = total_failures
        rows.append(row)

    df = pd.DataFrame(rows)
    df = blend_waiver_to_national_avg(
        df, list(SYNTHETIC_SUBGROUPS.keys()), "total_workdoc_failures_pre_rake"
    )
    return df.sort_values("total_workdoc_failures_pre_rake", ascending=False)


PUMS_BASE_URL = "https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year"
PUMS_API_URL = "https://api.census.gov/data/2024/acs/acs5/pums"
PUMS_RAW_DIR = config.RAW_DIR / "pums"
PUMS_CACHE_DIR = config.OUTPUT_DIR / "pums_state_cache"

# Bump when the cached parquet schema changes (e.g., adding new aggregate counts).
# Cached files without this version field, or with a lower version, get recomputed.
# v1: work-doc subgroup counts only
# v2: + medically_frail / caregiver_under14 / fulltime_student / subject_pool (for 04e)
CACHE_SCHEMA_VERSION = 6   # v6 (Esty review 2): Section 1931 + non-citizen subject-pool refinement,
                            # AI/AN exemption count (RACAIAN), combination-of-activities (work+school) count.
                            # v5 added the 16-cell joint distribution (W×P×M×S) for the overlap upset plot.

# Columns we keep when reading the PUMS person CSV. Filtering to ~20 columns
# from PUMS's 280+ columns keeps memory manageable.
# v2 additions:
#   SERIALNO, RELSHIPP — household linkage for caregiver-of-child-under-14 detection
#   DIS, DDRS, DPHY, DOUT, DREM, DEYE, DEAR — medically-frail eligibility
#   SCH, SCHG — full-time student status (SCHG ≥ 15 = college undergraduate or higher)
# v4 additions (Esty review):
#   FER — woman gave birth in last 12 months → pregnancy/postpartum per-state rate
#         (replaces the v1-v3 uniform 1.5% national prior)
PUMS_KEEP_COLS = [
    "PWGTP", "AGEP", "SEX", "HINS4", "POVPIP",
    "COW", "INDP", "OCCP", "WKHP", "WKWN",
    "SERIALNO", "RELSHIPP",
    "DIS", "DDRS", "DPHY", "DOUT", "DREM", "DEYE", "DEAR",
    "SCH", "SCHG",
    "FER",   # v4: gave birth in past 12 months (women 15-50)
    # v8 (Esty review 2):
    "RACAIAN",  # American Indian / Alaska Native recode (1 = AI/AN alone or in combo) → AI/AN exemption
    "CIT",      # citizenship status (5 = not a U.S. citizen) → immigration refinement
    "YOEP",     # year of entry → 5-year-bar screen for recent non-citizens
]

# RELSHIPP codes for "primary caretaker" — reference person + spouse/partner.
RELSHIPP_CARETAKER = {20, 21, 22, 23, 24}

# RELSHIPP codes for "child of reference person in this household."
# 25=biological, 26=adopted, 27=stepson/stepdaughter, 35=foster child.
RELSHIPP_OWN_CHILD = {25, 26, 27, 35}

# v4: RELSHIPP codes for "non-parent kinship arrangement" — a child living with
# the householder but NOT as the householder's bio/adopted/step/foster child.
# 30 = grandchild; 36 = other relative; 37 = housemate/roommate/other nonrelative.
# A household qualifies as kinship-led if it has a child ≤13 with one of these
# RELSHIPP codes AND no person in the household has RELSHIPP_OWN_CHILD with
# AGEP ≤ 13 (i.e., the householder is not also a parent of a young child).
RELSHIPP_KINSHIP_CHILD = {30, 36, 37}


def _classify_pums_record(df: pd.DataFrame) -> pd.Series:
    """Assign each PUMS record (post-filter) to one of the 6 work-doc subgroups.

    Records that don't fall in any subgroup get 'other' — these are conventional
    W-2 workers who fit the verification system cleanly and aren't a work-doc-
    failure risk. The 'other' bucket drops out of our shares computation.

    Subgroup mutual exclusion: applied in priority order via the boolean mask
    construction. Gig/courier is checked first (most distinct signal), then
    cash_construction, then seasonal, then multi-part-time, then self-employed
    residual, then variable shifts as the weakest classifier.
    """
    INDP_GIG_COURIER = {7280, 6190}
    INDP_CONSTRUCTION = set(range(770, 800))
    INDP_AG = set(range(170, 290))
    INDP_FOOD_SERVICE = set(range(8660, 8691))
    OCCP_DRIVER_DELIVERY = {9130, 9140, 9560}
    COW_SELF_EMPLOYED = {6, 7}

    result = pd.Series("other", index=df.index)

    # Gig / courier
    is_gig = df["INDP"].isin(INDP_GIG_COURIER) | (
        df["COW"].isin(COW_SELF_EMPLOYED) & df["OCCP"].isin(OCCP_DRIVER_DELIVERY)
    )
    result[is_gig] = "gig_courier"

    # Cash-paid construction
    is_construction = (
        (result == "other")
        & df["INDP"].isin(INDP_CONSTRUCTION)
        & df["COW"].isin(COW_SELF_EMPLOYED)
    )
    result[is_construction] = "cash_construction"

    # Seasonal ag/hospitality
    wkwn = df["WKWN"] if "WKWN" in df.columns else pd.Series(40, index=df.index)
    is_seasonal = (
        (result == "other")
        & (df["INDP"].isin(INDP_AG) | df["INDP"].isin(INDP_FOOD_SERVICE))
        & (wkwn < 40)
    )
    result[is_seasonal] = "seasonal_ag_hosp"

    # Multiple part-time (proxy: hours < 35, weeks worked >= 40 so it's
    # year-round but at low hours — implies multi-job aggregation)
    is_multi_pt = (
        (result == "other")
        & df["WKHP"].notna()
        & (df["WKHP"] < 35)
        & (wkwn >= 40)
    )
    result[is_multi_pt] = "multi_part_time"

    # Self-employed residual
    is_self_emp = (result == "other") & df["COW"].isin(COW_SELF_EMPLOYED)
    result[is_self_emp] = "self_employed_other"

    # Variable shifts (occupation in retail / healthcare support / food prep)
    # OCCP 4000-4999 sales, 3100-3199 healthcare support, 3500-3699 food prep+serv
    is_variable = (
        (result == "other")
        & (
            ((df["OCCP"] >= 4000) & (df["OCCP"] < 5000))
            | ((df["OCCP"] >= 3100) & (df["OCCP"] < 3200))
            | ((df["OCCP"] >= 3500) & (df["OCCP"] < 3700))
        )
    )
    result[is_variable] = "variable_shifts"

    return result


def _is_valid_zip(path: Path) -> bool:
    """Quick magic-byte check — real ZIPs start with PK."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"PK"
    except OSError:
        return False


def _download_pums_state(abbr_lower: str, *, max_retries: int = 4) -> Path:
    """Download per-state PUMS 5-Year zip if not cached.

    Census's WAF rejects bursts of requests with HTTP 200 + an HTML "Request
    Rejected" body. We validate that the downloaded file looks like a real zip
    (magic bytes "PK") before accepting it, and back off + retry on WAF blocks.
    """
    import random
    import time as _time
    import zipfile as _zipfile

    import requests

    zip_url = f"{PUMS_BASE_URL}/csv_p{abbr_lower}.zip"
    zip_path = PUMS_RAW_DIR / f"csv_p{abbr_lower}.zip"
    if zip_path.exists():
        # Validate cached file is a real zip (could be a leftover WAF block).
        try:
            with _zipfile.ZipFile(zip_path) as _z:
                _z.testzip()
            return zip_path
        except _zipfile.BadZipFile:
            print(f"    cached {zip_path.name} is not a valid zip (WAF block?); re-downloading")
            zip_path.unlink()

    PUMS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    headers = {
        # A real browser-ish UA reduces WAF flag rate. We are a research /
        # analytical client; identifying ourselves keeps Census able to throttle
        # us specifically if needed rather than rejecting all callers.
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
                      "(17A / gizmo-warehouse / medicaid-work-requirements pipeline)",
        "Accept": "application/zip, application/octet-stream",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for attempt in range(1, max_retries + 1):
        print(f"    downloading {abbr_lower} (attempt {attempt}/{max_retries}) from {zip_url}")
        tmp_path = zip_path.with_suffix(".zip.partial")
        try:
            with requests.get(zip_url, stream=True, timeout=600, headers=headers) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total and downloaded % (16 << 20) < (1 << 20):
                            print(f"      {downloaded / 1e6:.0f}/{total / 1e6:.0f} MB ({downloaded / total * 100:.0f}%)")

            # Validate magic bytes — real zips start with "PK\x03\x04".
            with open(tmp_path, "rb") as f:
                magic = f.read(4)
            if magic[:2] != b"PK":
                # WAF block. Read the body for context, then back off and retry.
                body_preview = tmp_path.read_bytes()[:300].decode("utf-8", errors="replace")
                tmp_path.unlink()
                raise RuntimeError(
                    f"non-zip response (likely Census WAF block): {body_preview!r}"
                )

            tmp_path.rename(zip_path)
            return zip_path

        except (requests.RequestException, RuntimeError) as e:
            if tmp_path.exists():
                tmp_path.unlink()
            wait = min(60, (2 ** attempt) + random.uniform(0, 5))
            err_msg = str(e)[:160]
            print(f"    {abbr_lower} download failed ({err_msg}); retrying in {wait:.0f}s")
            _time.sleep(wait)

    raise RuntimeError(f"PUMS download for {abbr_lower} failed after {max_retries} attempts")


def _fetch_pums_via_api(state_fips: str, abbr: str) -> pd.DataFrame:
    """Pull a state's PUMS 5-Year microdata via Census API.

    Fallback for when bulk-download zips are unavailable (Census WAF block).
    Returns a DataFrame with the same columns as the bulk CSV would have.

    Requires CENSUS_API_KEY in environment (loaded from .env.local by main()).
    """
    import os
    import requests

    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "CENSUS_API_KEY not set in environment. Add it to .env.local at repo root."
        )

    params = {
        "get": ",".join(PUMS_KEEP_COLS),
        "for": "public use microdata area:*",
        "in": f"state:{state_fips}",
        "key": api_key,
    }
    print(f"    fetching {abbr} via Census API (state {state_fips})")
    r = requests.get(PUMS_API_URL, params=params, timeout=600)
    r.raise_for_status()
    rows = r.json()
    if not rows or len(rows) < 2:
        raise RuntimeError(f"Census API returned no records for state {state_fips}")
    header = rows[0]
    df = pd.DataFrame(rows[1:], columns=header)
    # API returns all values as strings; coerce numerics for our analysis cols.
    for c in PUMS_KEEP_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _process_pums_state(state_fips: str, abbr: str, name: str) -> dict:
    """Process one state's PUMS — download, filter, classify, aggregate.

    Tries bulk-download zip first (fast, but currently WAF-blocked). Falls
    back to the Census PUMS API if no zip is cached.

    Returns a per-state result dict with subgroup-share columns. Caches the
    final per-state output so re-runs skip the heavy work.
    """
    import zipfile

    PUMS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = PUMS_CACHE_DIR / f"{abbr.lower()}_classified.parquet"
    if cache_path.exists():
        cached = pd.read_parquet(cache_path).iloc[0].to_dict()
        if int(cached.get("cache_schema_version", 1)) >= CACHE_SCHEMA_VERSION:
            return cached
        print(f"      [{abbr}] cache schema {cached.get('cache_schema_version', 1)} < {CACHE_SCHEMA_VERSION}; recomputing")

    abbr_lower = abbr.lower()
    zip_path = PUMS_RAW_DIR / f"csv_p{abbr_lower}.zip"

    # If the zip is already cached, use it. Otherwise go via API (which has
    # separate rate-limiting from the WAF that blocks bulk downloads).
    if zip_path.exists() and _is_valid_zip(zip_path):
        with zipfile.ZipFile(zip_path) as z:
            csv_name = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
            if not csv_name:
                raise RuntimeError(f"no .csv inside {zip_path.name}")
            with z.open(csv_name) as f:
                sample = pd.read_csv(f, nrows=1)
            available_cols = [c for c in PUMS_KEEP_COLS if c in sample.columns]
            missing = set(PUMS_KEEP_COLS) - set(available_cols)
            if missing:
                print(f"      [{abbr}] missing PUMS columns (proceeding without): {sorted(missing)}")
            with z.open(csv_name) as f:
                df = pd.read_csv(f, usecols=available_cols, low_memory=False)
    else:
        df = _fetch_pums_via_api(state_fips, abbr)

    n_raw = len(df)

    # Coerce numerics that may also be referenced before the subject-pool filter
    # (we need AGEP/SERIALNO/RELSHIPP/HINS4 for household-level classification of
    # caregiver-of-child-≤13, which considers children outside the Medicaid filter).
    for c in ("AGEP", "HINS4"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Households with at least one child ≤13 who is the reference person's
    # biological/adopted/stepchild/foster child. Computed before subject-pool
    # filtering because the *child* is rarely the Medicaid-enrolled subject —
    # we need to identify them via the household, then find the adult caregiver.
    if "SERIALNO" in df.columns and "RELSHIPP" in df.columns:
        relshipp_num = pd.to_numeric(df["RELSHIPP"], errors="coerce")
        # Parent-led households: at least one child ≤13 with RELSHIPP in OWN_CHILD set.
        parent_child_mask = (
            df["AGEP"].between(0, 13)
            & relshipp_num.isin(RELSHIPP_OWN_CHILD)
        )
        households_with_child_under14 = set(df.loc[parent_child_mask, "SERIALNO"].astype(str).unique())
        # v4: Kinship-led households — at least one child ≤13 with RELSHIPP in KINSHIP
        # set AND the household has no own-child of the householder. The second
        # condition prevents double-counting households with both bio kids and a
        # grandchild/other-relative; those count as parent-led, not kinship-led.
        kinship_child_mask = (
            df["AGEP"].between(0, 13)
            & relshipp_num.isin(RELSHIPP_KINSHIP_CHILD)
        )
        candidate_kinship_households = set(df.loc[kinship_child_mask, "SERIALNO"].astype(str).unique())
        households_with_kinship_child = candidate_kinship_households - households_with_child_under14
    else:
        households_with_child_under14 = set()
        households_with_kinship_child = set()
        if "SERIALNO" not in df.columns or "RELSHIPP" not in df.columns:
            print(f"      [{abbr}] missing SERIALNO/RELSHIPP — caregiver detection disabled")

    # v4: Identify households containing a working-age (19-64) disabled adult who
    # qualifies as "medically frail" (DIS=1 AND ≥2 specific functional flags).
    # This person is the care RECIPIENT; we'll find their caregiver in the
    # filtered subject pool below.
    if all(c in df.columns for c in ("SERIALNO", "DIS")):
        dis_num = pd.to_numeric(df["DIS"], errors="coerce")
        specific_diff_count_all = sum(
            (pd.to_numeric(df[c], errors="coerce") == 1).astype(int)
            for c in ("DDRS", "DPHY", "DOUT", "DREM") if c in df.columns
        )
        disabled_adult_mask = (
            df["AGEP"].between(19, 64)
            & (dis_num == 1)
            & (specific_diff_count_all >= 2)
        )
        households_with_disabled_adult = set(df.loc[disabled_adult_mask, "SERIALNO"].astype(str).unique())
        # Set of SERIALNOs where the disabled-adult-themselves PWGTP-weighted SERIALNO
        # serves as the lookup key for the disabled person's PUMS row, so we can
        # exclude the disabled adult from being their own caregiver.
        disabled_adult_serial_personmap: dict[str, set] = {}
        if disabled_adult_mask.any():
            # Map SERIALNO → set of (row indices) that are the disabled adult,
            # so we can exclude them from caregiver selection.
            disabled_rows = df.loc[disabled_adult_mask, ["SERIALNO"]].copy()
            disabled_rows["SERIALNO"] = disabled_rows["SERIALNO"].astype(str)
            for serial, group in disabled_rows.groupby("SERIALNO"):
                disabled_adult_serial_personmap[serial] = set(group.index.tolist())
    else:
        households_with_disabled_adult = set()
        disabled_adult_serial_personmap = {}

    # v8 (Esty review 2): households containing the reference person's own child
    # ≤18, for the Section 1931 parent carve-out. Computed on the full frame
    # (the child is rarely the enrolled adult) before the subject-pool filter.
    child_under_19_households = pums_refine.households_with_own_child_under_19(df)

    # Filter — Medicaid + age 19-64 + at/below 138% FPL + positive person weight.
    df = df[
        df["AGEP"].between(19, 64)
        & (df["HINS4"] == 1)
        & df["POVPIP"].notna()
        & df["POVPIP"].between(0, 138)
        & (df["PWGTP"] > 0)
    ].copy()

    # v8 (Esty review 2): remove people who are not in the ACA-expansion subject
    # pool — parents covered through the Section 1931 pathway (POVPIP below the
    # state 1931 limit) and recent non-citizens inside the federal 5-year bar.
    # This corrects the within-pool composition (parent share, overlap, exemption
    # rates); the national level stays anchored by stage 05's CBO rake. See
    # lib/pums_refine.py and METHODOLOGY §3.1 / §3.7.
    df, refine_prov = pums_refine.refine_subject_pool(
        df, None, state_fips,
        child_under_19_households=child_under_19_households,
    )
    n_filtered = len(df)

    # Coerce numerics for classification
    for c in ("INDP", "OCCP", "COW", "WKHP"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    if "WKWN" in df.columns:
        df["WKWN"] = pd.to_numeric(df["WKWN"], errors="coerce")
    for c in ("RELSHIPP", "DIS", "DDRS", "DPHY", "DOUT", "DREM", "DEYE", "DEAR", "SCH", "SCHG", "FER", "SEX", "RACAIAN"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # Classify into work-doc subgroups
    df["subgroup"] = _classify_pums_record(df)

    # Aggregate weighted by PWGTP, by work-doc subgroup
    agg = df.groupby("subgroup")["PWGTP"].sum().to_dict()
    total_weighted = sum(agg.values())

    # --- v2/v3 additions: exemption-eligibility weighted counts -------------
    # Medically frail (v3 tightening): has the broad disability flag DIS *and*
    # at least TWO of {DDRS, DPHY, DOUT, DREM} (self-care, ambulatory, indep-
    # living, cognitive). v2 required any one of the six functional flags
    # including DEYE/DEAR — that over-classified milder impairments (uncorrected
    # vision/hearing) as OBBBA "medically frail." §1902(xx)(2)(B) covers blind/
    # disabled/SUD/disabling-mental/serious-or-complex; requiring ≥2 of the four
    # severe functional flags brings PUMS measurement closer to that statutory
    # threshold. The June 1, 2026 interim final rule (CMS-2454-IFC) ties frailty
    # to a condition that impairs the ability to meet the requirement; this proxy
    # is unchanged for now and will be refined as states operationalize the rule.
    if "DIS" in df.columns:
        specific_diff_count = sum(
            (df[c] == 1).astype(int) for c in ("DDRS", "DPHY", "DOUT", "DREM") if c in df.columns
        )
        medically_frail_mask = (df["DIS"] == 1) & (specific_diff_count >= 2)
        medically_frail_count = float(df.loc[medically_frail_mask, "PWGTP"].sum())
    else:
        medically_frail_count = 0.0

    # Caregiver of child ≤13: subject person is the household reference person
    # or their spouse/partner, AND the household contains a child ≤13 coded as
    # the reference person's own/step/adopted/foster child. Documents a slight
    # undercount of grandparent-caretakers (see RELSHIPP comment above).
    if "SERIALNO" in df.columns and "RELSHIPP" in df.columns and households_with_child_under14:
        caregiver_mask = (
            df["RELSHIPP"].isin(RELSHIPP_CARETAKER)
            & df["SERIALNO"].astype(str).isin(households_with_child_under14)
        )
        caregiver_count = float(df.loc[caregiver_mask, "PWGTP"].sum())
    else:
        caregiver_count = 0.0

    # Full-time student: currently enrolled in school (SCH 2/3 = public/private),
    # at undergraduate or graduate grade level (SCHG ≥ 15). PUMS doesn't have
    # an explicit FT/PT flag for college; for the exemption-eligibility count
    # we accept any current college enrollment and let the failure-rate logic
    # in 04c apply attenuation.
    if "SCH" in df.columns and "SCHG" in df.columns:
        student_mask = df["SCH"].isin([2, 3]) & (df["SCHG"] >= 15)
        student_count = float(df.loc[student_mask, "PWGTP"].sum())
    else:
        student_count = 0.0

    # v4: Kinship caregiver (Esty review). Subject person is Medicaid-eligible and
    # lives in a kinship-led household (containing a child ≤13 with RELSHIPP in
    # KINSHIP set, and the household has no own-child of the householder).
    # We take the householder + spouse (RELSHIPP_CARETAKER codes) as the primary
    # kinship caregiver, weighted by PWGTP. This may understate informal kinship
    # arrangements where the caregiver isn't the householder; we document the gap
    # in METHODOLOGY §3.5 and cross-validate against AECF KIDS COUNT in 04f.
    if (
        "SERIALNO" in df.columns
        and "RELSHIPP" in df.columns
        and households_with_kinship_child
    ):
        kinship_caregiver_mask = (
            df["RELSHIPP"].isin(RELSHIPP_CARETAKER)
            & df["SERIALNO"].astype(str).isin(households_with_kinship_child)
        )
        kinship_caregiver_count = float(df.loc[kinship_caregiver_mask, "PWGTP"].sum())
    else:
        kinship_caregiver_count = 0.0

    # v4: Caregiver of a working-age disabled adult (Esty review). Subject person
    # is Medicaid-eligible and shares a household with a disabled adult (per
    # households_with_disabled_adult above), but the subject is NOT the disabled
    # adult themselves. We apply a primary-caregiver heuristic by aggregating to
    # the household level: at most one caregiver per disabled-adult household,
    # picking the spouse/partner first (RELSHIPP 21) then the householder
    # (RELSHIPP 20) then the eldest other adult by AGEP. This avoids over-
    # counting households with multiple adults but still surfaces a defensible
    # state-level rate.
    if (
        "SERIALNO" in df.columns
        and "RELSHIPP" in df.columns
        and households_with_disabled_adult
    ):
        serial_str = df["SERIALNO"].astype(str)
        candidate_mask = serial_str.isin(households_with_disabled_adult)
        candidates = df.loc[candidate_mask].copy()
        candidates["SERIALNO_STR"] = serial_str.loc[candidates.index]
        # Exclude the disabled adult themselves from being their own caregiver.
        def _is_disabled_adult_row(row):
            return row.name in disabled_adult_serial_personmap.get(row["SERIALNO_STR"], set())
        if not candidates.empty:
            candidates = candidates[~candidates.apply(_is_disabled_adult_row, axis=1)]
        if not candidates.empty:
            # Priority: spouse (21) > householder (20) > eldest other adult.
            def _priority(rel):
                if rel == 21:
                    return 0
                if rel == 20:
                    return 1
                return 2
            candidates["__pri"] = candidates["RELSHIPP"].apply(_priority)
            # For each household, pick min priority; if tie, the eldest by AGEP.
            candidates = candidates.sort_values(["__pri", "AGEP"], ascending=[True, False])
            primary = candidates.groupby("SERIALNO_STR").first()
            caregivers_disabled_adult_count = float(primary["PWGTP"].sum())
        else:
            caregivers_disabled_adult_count = 0.0
    else:
        caregivers_disabled_adult_count = 0.0

    # v4: Pregnant / postpartum (Esty review — replaces uniform 1.5% prior).
    # PUMS FER = 1 means the woman gave birth in the past 12 months. Combined
    # with the subject-pool filter (women aged 19-64, Medicaid, low income),
    # this captures the postpartum eligibility window. PUMS doesn't survey
    # current pregnancy directly; the past-12-month birth flag is the closest
    # proxy and aligns with OBBBA's postpartum exemption window.
    if "FER" in df.columns and "SEX" in df.columns:
        # SEX=2 is female in ACS PUMS coding.
        pregnant_postpartum_mask = (df["FER"] == 1) & (df["SEX"] == 2)
        pregnant_postpartum_count = float(df.loc[pregnant_postpartum_mask, "PWGTP"].sum())
    else:
        pregnant_postpartum_count = 0.0

    # v8 (Esty review 2): AI/AN exemption count. RACAIAN = 1 flags any respondent
    # reporting American Indian / Alaska Native alone or in combination. AI/AN
    # are exempt under OBBBA; we surface them as their own subgroup (04c/07b)
    # rather than bundling into "other categorical." Computed on the refined
    # subject pool. Sarah Esty: "We should be able to pull AI/AN."
    if "RACAIAN" in df.columns:
        ai_an_count = float(df.loc[df["RACAIAN"] == 1, "PWGTP"].sum())
    else:
        ai_an_count = 0.0

    # v8 (Esty review 2): "combination of activities" floor. OBBBA lets an
    # enrollee reach 80 hrs/month by COMBINING work + school + volunteering +
    # job training. PUMS observes work hours (WKHP) and school enrollment (SCH)
    # but not school/volunteer hours, so we floor the combination population at
    # people who work part-time (WKHP 10-18 ≈ 43-78 monthly hours, i.e. under
    # the 80-hr work-alone bar that defines the W flag) AND are enrolled in
    # school (SCH ∈ {2,3}). They clear 80 only if the state sums across
    # activities; if it can't, they fail despite being compliant. Sarah Esty's
    # exact example. A floor: volunteer/training combinations aren't observable.
    if all(c in df.columns for c in ("WKHP", "SCH")):
        combination_work_school_count = float(
            df.loc[(df["WKHP"] >= 10) & (df["WKHP"] < 19) & df["SCH"].isin([2, 3]), "PWGTP"].sum()
        )
    else:
        combination_work_school_count = 0.0

    # Per-record 16-cell joint distribution (W×P×M×S) for the category-overlap
    # upset plot. Replaces the marginal-independence + pairwise-correlation
    # approximation stage 04h used previously. Each subject in the filtered
    # sample is classified into exactly one of 16 cells, weighted by PWGTP.
    #   W = working ≥80 hrs/month (WKHP ≥ 19 ≈ 19hrs/wk × 4.33wk/mo)
    #   P = parent caregiver of child ≤13 (existing caregiver_mask)
    #   M = medically frail (DIS=1 AND ≥2 specific functional flags)
    #   S = full-time student (SCH ∈ {2,3} AND SCHG ≥ 15)
    # Missing-column case: if a mask wasn't computed (e.g., column absent),
    # treat as all-False.
    _local = locals()
    flag_W = (df["WKHP"] >= 19) if "WKHP" in df.columns else pd.Series(False, index=df.index)
    flag_P = _local.get("caregiver_mask", pd.Series(False, index=df.index))
    flag_M = _local.get("medically_frail_mask", pd.Series(False, index=df.index))
    flag_S = _local.get("student_mask", pd.Series(False, index=df.index))

    overlap_cell_counts: dict[str, float] = {}
    for w in (False, True):
        for p in (False, True):
            for m in (False, True):
                for s in (False, True):
                    cell_mask = (flag_W == w) & (flag_P == p) & (flag_M == m) & (flag_S == s)
                    key = "".join(c if v else "-" for c, v in zip("WPMS", (w, p, m, s)))
                    overlap_cell_counts[f"overlap_cell_{key}_count_weighted"] = float(df.loc[cell_mask, "PWGTP"].sum())

    result = {
        "state_fips": state_fips,
        "state_abbr": abbr,
        "state_name": name,
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "pums_records_raw": int(n_raw),
        "pums_records_filtered": int(n_filtered),
        "pums_total_weighted": float(total_weighted),
        # Subject_pool_weighted is the denominator shared by all per-state
        # exemption-eligibility rate computations in stage 04e. It's the same
        # numeric value as pums_total_weighted; we expose it under the clearer
        # name so 04e doesn't have to know the legacy name.
        "subject_pool_weighted": float(total_weighted),
        "medically_frail_count_weighted": medically_frail_count,
        "caregiver_under14_count_weighted": caregiver_count,
        "fulltime_student_count_weighted": student_count,
        # v4 additions (Esty review): per-state PUMS-derived rates for
        # subgroups that v3 carried as uniform national priors.
        "kinship_caregiver_count_weighted": kinship_caregiver_count,
        "caregivers_disabled_adult_count_weighted": caregivers_disabled_adult_count,
        "pregnant_postpartum_count_weighted": pregnant_postpartum_count,
        # v8 additions (Esty review 2):
        "ai_an_count_weighted": ai_an_count,
        "combination_work_school_count_weighted": combination_work_school_count,
        # Refinement provenance — for logging + the "share of parents covered
        # outside expansion" summary stat surfaced on the page.
        "section_1931_parent_excluded_weighted": refine_prov["section_1931_parent_excluded_weighted"],
        "recent_noncitizen_excluded_weighted": refine_prov["recent_noncitizen_excluded_weighted"],
        "parents_of_own_child_total_weighted": refine_prov["parents_of_own_child_total_weighted"],
        "share_parents_covered_outside_expansion": refine_prov["share_parents_covered_outside_expansion"],
        "pool_before_refinement_weighted": refine_prov["pool_before_refinement_weighted"],
        # v5 addition: 16-cell joint distribution for stage 04h.
        **overlap_cell_counts,
    }
    for key, _meta in SYNTHETIC_SUBGROUPS.items():
        count = float(agg.get(key, 0))
        share = count / total_weighted if total_weighted > 0 else 0
        result[f"{key}_count_weighted"] = count
        result[f"{key}_pums_share"] = share

    pd.DataFrame([result]).to_parquet(cache_path)
    return result


def run_pums_full() -> pd.DataFrame:
    """Full-mode PUMS pull. Downloads per-state 5-year PUMS, filters, classifies.

    Replaces the synthetic national shares with state-specific PUMS-derived
    shares. The output schema matches run_synthetic() (same columns) so stage
    07b can ingest either output transparently. Mode is recorded in the
    `pums_mode` column.

    Resources: ~5GB total download; ~30 min processing for 41 expansion states
    on a residential network. Both downloads and classification are cached, so
    re-runs are nearly instant after the first full pass.
    """
    import json as _json

    summary = _json.loads(STATE_SUMMARY_IN.read_text())
    ex_parte = pd.read_parquet(EX_PARTE_IN).set_index("state_fips")

    print(f"PUMS full mode: processing {sum(1 for s in summary['states'] if s['expansion'])} expansion states from {PUMS_BASE_URL}")
    print(f"  raw cache: {PUMS_RAW_DIR}")
    print(f"  per-state classified cache: {PUMS_CACHE_DIR}")
    print()

    import time as _time
    import random as _random

    rows = []
    last_network_call = 0.0
    for i, s in enumerate(summary["states"], 1):
        fips = s["state_fips"]
        # Expansion states + subject-via-1115-waiver states (WI/GA). PUMS gives
        # the per-state subgroup SHAPE; the admin-anchored subject_count gives the
        # LEVEL. For waiver states the PUMS shape reflects the broader low-income
        # Medicaid-adult mix (a documented proxy — see METHODOLOGY).
        subject = float(s["subject_count_strict"])
        if subject <= 0:
            continue

        # Throttle: at least 2s between download attempts (jittered) to keep us
        # below the Census WAF rate threshold. Skipped if the state is cached.
        cache_path = PUMS_CACHE_DIR / f"{s['state_abbr'].lower()}_classified.parquet"
        if not cache_path.exists():
            elapsed = _time.time() - last_network_call
            if elapsed < 2.0:
                _time.sleep(2.0 - elapsed + _random.uniform(0, 1))
            last_network_call = _time.time()

        print(f"[{i}/{len(summary['states'])}] {s['state_abbr']} {s['state_name']}")
        pums_result = _process_pums_state(fips, s["state_abbr"], s["state_name"])

        ex_row = ex_parte.loc[fips] if fips in ex_parte.index else None
        row = {
            "state_fips": fips,
            "state_abbr": s["state_abbr"],
            "state_name": s["state_name"],
            "subject_count": subject,
            "ex_parte_score": int(ex_row["score"]) if ex_row is not None and pd.notna(ex_row.get("score")) else None,
            "ex_parte_band": ex_row["churn_band"] if ex_row is not None else None,
            "pums_mode": "full",
            "pums_records_filtered": pums_result["pums_records_filtered"],
            "pums_total_weighted": pums_result["pums_total_weighted"],
        }

        # PUMS-derived per-state shares replace the synthetic share_of_subject.
        # The failure-rate logic stays the same — it's parameterized by the
        # ex parte flags, not by the subgroup composition.
        total_failures = 0.0
        for key, meta in SYNTHETIC_SUBGROUPS.items():
            pums_share = pums_result.get(f"{key}_pums_share", meta["share_of_subject"])
            eligible = subject * pums_share
            failure_rate = state_failure_rate(meta, ex_row)
            failures = eligible * failure_rate
            row[f"{key}_eligible"] = eligible
            row[f"{key}_pums_share"] = pums_share
            row[f"{key}_doc_fail_rate"] = failure_rate
            row[f"{key}_doc_failures"] = failures
            total_failures += failures
        row["total_workdoc_failures_pre_rake"] = total_failures
        rows.append(row)

    df = pd.DataFrame(rows)
    df = blend_waiver_to_national_avg(
        df, list(SYNTHETIC_SUBGROUPS.keys()), "total_workdoc_failures_pre_rake"
    )
    return df.sort_values("total_workdoc_failures_pre_rake", ascending=False)


def main(pums_mode: str = "synthetic") -> None:
    # Load .env.local so CENSUS_API_KEY is available for the API fallback path.
    from dotenv import load_dotenv
    load_dotenv(config.REPO_ROOT / ".env.local")

    if not _check_inputs():
        sys.exit(1)

    if pums_mode == "synthetic":
        df = run_synthetic()
    elif pums_mode == "full":
        df = run_pums_full()
    else:
        print(f"ERROR: unknown --pums-mode {pums_mode!r}", file=sys.stderr)
        sys.exit(1)

    df.to_parquet(WORKDOC_OUT, index=False)

    nat_total = df["total_workdoc_failures_pre_rake"].sum()
    target_low = 0.45 * config.CROSS_VALIDATION_TARGETS["cbo_national_loss_2034"]
    target_high = 0.55 * config.CROSS_VALIDATION_TARGETS["cbo_national_loss_2034"]

    print(f"Built work-doc-failure breakdown for {len(df)} expansion states + DC ({pums_mode} mode).")
    print(f"Pre-rake national total: {nat_total:>11,.0f}")
    print(f"  target band (45-55% of CBO 5.2M loss): {target_low:,.0f} – {target_high:,.0f}")
    print(f"  pre-rake / target_midpoint ratio: {nat_total / ((target_low + target_high) / 2):.2f}")
    print()
    print("Subgroup national totals (pre-rake):")
    for key, meta in SYNTHETIC_SUBGROUPS.items():
        col = f"{key}_doc_failures"
        total = df[col].sum()
        print(f"  {meta['label']:<55}  {total:>11,.0f}")

    print()
    print("Top 5 states by work-doc-failure exposure:")
    for _, r in df.head(5).iterrows():
        print(f"  {r['state_abbr']}  {int(r['total_workdoc_failures_pre_rake']):>10,d}  "
              f"(ex parte score {int(r['ex_parte_score']) if pd.notna(r['ex_parte_score']) else '—':<3})")

    print(f"\n-> {WORKDOC_OUT.relative_to(config.PIPELINE_DIR)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pums-mode", default="full", choices=["synthetic", "full"],
                    help="full = per-state ACS PUMS 2020-2024 microdata (default); "
                         "synthetic = published-parameter national shares (fallback for "
                         "contributors without local PUMS zips)")
    args = ap.parse_args()
    t0 = time.time()
    main(args.pums_mode)
    print(f"\nStage 04b done in {time.time() - t0:.1f}s")
