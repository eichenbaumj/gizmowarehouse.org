#!/usr/bin/env python3
"""Bake demographic profile estimates from real ACS PUMS microdata.

Supersedes tools/bake-placeholder-medicaid-subject-profile.py (which applied
national shares uniformly). This script computes per-state age × kids ×
work-hours shares from PUMS 5-Year 2020-2024 records, filtered to
expansion-adult Medicaid (HINS4=1, AGEP 19-64, POVPIP ≤ 138, PWGTP > 0).

PUMS download path: cached zips in pipeline/raw/pums/ where available,
Census API otherwise. Reuses the same download/validation logic as
gizmos/medicaid-work-requirements/pipeline/04b_fetch_pums_workdoc_breakdown.py.

Outputs public/data/medicaid-subject-profile.json keyed by state FIPS plus
"_national", schema unchanged so MedicaidSubjectProfile.tsx picks up the
new shares without code changes.

Run: python3 tools/bake-medicaid-subject-profile.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
STATE_SUMMARY = REPO / "public/data/medicaid-state-summary.json"
PROFILE_OUT = REPO / "public/data/medicaid-subject-profile.json"

# v8 (Esty review 2): reuse the pipeline's shared Section 1931 + non-citizen
# subject-pool refinement so the SubjectProfile reconciles with the map, the
# overlap chart, and the loss breakdown.
PIPELINE_DIR = REPO / "gizmos/medicaid-work-requirements/pipeline"
sys.path.insert(0, str(PIPELINE_DIR))
import config  # type: ignore  # noqa: E402
from lib import pums_refine  # type: ignore  # noqa: E402

PUMS_BASE_URL = "https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year"
PUMS_API_URL = "https://api.census.gov/data/2024/acs/acs5/pums"
PUMS_RAW_DIR = REPO / "gizmos/medicaid-work-requirements/pipeline/raw/pums"

# Columns we need:
#   PWGTP    — person weight
#   AGEP     — age (filter + household-join to detect "child under 14")
#   HINS4    — Medicaid coverage (filter)
#   POVPIP   — income-to-poverty ratio (filter to ≤138% FPL)
#   WKHP     — usual hours worked per week (bucket into monthly-hours equivalent)
#   SERIALNO — household identifier (join to detect "child under 14 in household")
#   DIS      — disability (1=with, 2=without) — medically-frail exemption proxy
#   SCH      — school enrollment (1=no, 2=public, 3=private/home) — student exemption
#   SEX      — sex (1=male, 2=female) — used with FER for postpartum exemption
#   FER      — gave birth in last 12 months (1=yes, 2=no, 0=N/A) — postpartum exemption
#
# Note: HUPARC is in the PUMS HOUSEHOLD file, not the person file. SERIALNO+AGEP
# household join is more accurate (matches OBBBA's exact 0-13 cutoff) and avoids
# the household-file dependency.
PUMS_KEEP_COLS = [
    "PWGTP", "AGEP", "HINS4", "POVPIP", "WKHP", "SERIALNO",
    "DIS", "SCH", "SEX", "FER",
    # v8 (Esty review 2): for the Section 1931 parent carve-out (RELSHIPP) and
    # the recent-non-citizen screen (CIT, YOEP). See lib/pums_refine.py.
    "RELSHIPP", "CIT", "YOEP",
]

AGE_BUCKETS = [
    ("19-24", 19, 24),
    ("25-34", 25, 34),
    ("35-44", 35, 44),
    ("45-54", 45, 54),
    ("55-64", 55, 64),
]

# WKHP = usual hours worked per week. We use these to project monthly hours:
# 0 hrs/week → "Not working", 1-19 → "1-19 hrs/week", 20-79 = ≥20 → bucketed
# Note: WKHP is a per-week field. ≥20 hrs/week ≈ ≥80 hrs/month, the OBBBA bar.
WORK_HOURS_BUCKETS = ["0", "1-19", "20-79", "80_plus"]

# Decomposition of the "not working" group into OBBBA exemption status.
# Priority order: a person is assigned to their first-matching category, so
# disabled-AND-caretaker → "disabled" (because either exempts them, but the
# disability is the more clearly load-bearing status). The "other" residual
# is the OBBBA-subject not-working population — the share the law is
# actually targeting.
NOT_WORKING_REASONS = ["disabled", "caretaker", "postpartum", "student", "other"]


def _is_valid_zip(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"PK"
    except OSError:
        return False


def _download_pums_state(abbr_lower: str, *, max_retries: int = 4) -> Path | None:
    """Download per-state PUMS 5-Year zip if not cached; return path or None on failure."""
    zip_url = f"{PUMS_BASE_URL}/csv_p{abbr_lower}.zip"
    zip_path = PUMS_RAW_DIR / f"csv_p{abbr_lower}.zip"
    if zip_path.exists() and _is_valid_zip(zip_path):
        try:
            with zipfile.ZipFile(zip_path) as _z:
                _z.testzip()
            return zip_path
        except zipfile.BadZipFile:
            zip_path.unlink()

    PUMS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
                      "(17A / gizmo-warehouse / medicaid-work-requirements pipeline)",
        "Accept": "application/zip, application/octet-stream",
    }
    for attempt in range(1, max_retries + 1):
        tmp_path = zip_path.with_suffix(".zip.partial")
        try:
            print(f"    downloading {abbr_lower} (attempt {attempt}/{max_retries})")
            with requests.get(zip_url, stream=True, timeout=600, headers=headers) as r:
                r.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            with open(tmp_path, "rb") as f:
                if f.read(2) != b"PK":
                    tmp_path.unlink()
                    raise RuntimeError("non-zip response (Census WAF block)")
            tmp_path.rename(zip_path)
            return zip_path
        except (requests.RequestException, RuntimeError) as e:
            if tmp_path.exists():
                tmp_path.unlink()
            wait = min(60, (2 ** attempt) + random.uniform(0, 5))
            print(f"    {abbr_lower} download failed ({str(e)[:120]}); retrying in {wait:.0f}s")
            time.sleep(wait)
    return None


def _fetch_pums_via_api(state_fips: str, abbr: str) -> pd.DataFrame:
    """Pull PUMS 5-Year via Census API. Requires CENSUS_API_KEY."""
    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        raise RuntimeError("CENSUS_API_KEY not set in environment (load .env.local)")
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
    df = pd.DataFrame(rows[1:], columns=rows[0])
    for c in PUMS_KEEP_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _load_pums_records(state_fips: str, abbr: str) -> pd.DataFrame:
    """Return the per-state PUMS person records, from cached zip if available, else API."""
    zip_path = _download_pums_state(abbr.lower())
    if zip_path is not None:
        with zipfile.ZipFile(zip_path) as z:
            csv_name = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
            with z.open(csv_name) as f:
                sample = pd.read_csv(f, nrows=1)
            available = [c for c in PUMS_KEEP_COLS if c in sample.columns]
            with z.open(csv_name) as f:
                df = pd.read_csv(f, usecols=available, low_memory=False)
        return df
    # Fall back to Census API
    return _fetch_pums_via_api(state_fips, abbr)


def _bucket_age(age: int) -> str | None:
    for label, lo, hi in AGE_BUCKETS:
        if lo <= age <= hi:
            return label
    return None


def _bucket_work_hours(wkhp: float | None) -> str:
    """Bucket WKHP (hrs/week) into monthly-hours equivalent.

    OBBBA's bar is 80 hrs/month ≈ 20 hrs/week. We bucket by monthly equivalent
    so the labels match the statute:
      "0"       → not working
      "1-19"    → 1-19 hrs/month  (very casual; WKHP 1-4)
      "20-79"   → 20-79 hrs/month (some work, under threshold; WKHP 5-19)
      "80_plus" → ≥80 hrs/month   (compliant; WKHP ≥ 20)
    """
    if wkhp is None or pd.isna(wkhp) or wkhp <= 0:
        return "0"
    monthly = float(wkhp) * 4
    if monthly < 20:
        return "1-19"
    if monthly < 80:
        return "20-79"
    return "80_plus"


def _classify_not_working_reason(row: pd.Series, kid_serialnos: set) -> str:
    """Priority-assigned exemption category for an adult not working.

    Order matters: disabled wins over caretaker wins over postpartum wins over
    student. The point is to surface the clearest exemption status, not to
    double-count overlapping categories. "other" = the residual the OBBBA
    work requirement is actually targeting.
    """
    if row.get("DIS") == 1:
        return "disabled"
    serialno = row.get("SERIALNO")
    if serialno is not None and not pd.isna(serialno) and str(serialno) in kid_serialnos:
        return "caretaker"
    if row.get("SEX") == 2 and row.get("FER") == 1:
        return "postpartum"
    sch = row.get("SCH")
    if sch in (2, 3):
        return "student"
    return "other"


def _compute_state_shares(df: pd.DataFrame, state_fips: str) -> dict:
    """Filter to expansion-adult Medicaid, return weighted shares for the 3 panels.

    The "has child under 14" flag is computed via a household join on SERIALNO:
    any adult who shares a SERIALNO with a person whose AGEP ≤ 13 is flagged.
    This captures the exact OBBBA statutory cutoff (child age 13 or younger)
    and covers grandparent/foster caretakers, not just biological parents.
    """
    # Step 1: identify households with at least one child under 14.
    # Done across ALL persons in the state's PUMS, before any filter.
    if "SERIALNO" in df.columns and "AGEP" in df.columns:
        kid_serialnos = set(df.loc[df["AGEP"] <= 13, "SERIALNO"].dropna().astype(str).tolist())
    else:
        kid_serialnos = set()
    # v8: households with the reference person's own child ≤18, for the
    # Section 1931 parent carve-out.
    child19_households = pums_refine.households_with_own_child_under_19(df)

    # Step 2: filter to expansion-adult Medicaid records.
    adults = df[
        (df["AGEP"] >= 19) & (df["AGEP"] <= 64)
        & (df["HINS4"] == 1)
        & df["POVPIP"].notna() & (df["POVPIP"] >= 0) & (df["POVPIP"] <= 138)
        & (df["PWGTP"] > 0)
    ].copy()

    # v8 (Esty review 2): remove Section 1931 parents (covered outside expansion)
    # and recent non-citizens (not federally expansion-eligible), so the profile
    # composition matches the refined subject pool used everywhere else.
    adults, refine_prov = pums_refine.refine_subject_pool(
        adults, None, state_fips, child_under_19_households=child19_households
    )

    if adults.empty:
        return {"age_band": {}, "has_kids_under_14": {}, "work_hours_per_wk": {},
                "not_working_breakdown": {k: 0 for k in NOT_WORKING_REASONS},
                "share_parents_covered_outside_expansion": 0.0, "n_records": 0}

    adults["_age_bucket"] = adults["AGEP"].apply(_bucket_age)
    adults["_hours_bucket"] = (
        adults["WKHP"].apply(_bucket_work_hours) if "WKHP" in adults.columns else "0"
    )
    if "SERIALNO" in adults.columns and kid_serialnos:
        adults["_kids_bucket"] = adults["SERIALNO"].astype(str).apply(
            lambda s: "yes" if s in kid_serialnos else "no"
        )
    else:
        adults["_kids_bucket"] = "no"

    total_weight = float(adults["PWGTP"].sum())

    def shares(col, keys):
        out = {}
        grouped = adults.groupby(col)["PWGTP"].sum()
        for k in keys:
            out[k] = round(float(grouped.get(k, 0)) / total_weight, 4) if total_weight > 0 else 0
        return out

    # Step 3: for the not-working subset only, decompose by exemption status.
    not_working = adults[adults["_hours_bucket"] == "0"].copy()
    if not not_working.empty:
        not_working["_nw_reason"] = not_working.apply(
            lambda r: _classify_not_working_reason(r, kid_serialnos), axis=1
        )
        nw_total = float(not_working["PWGTP"].sum())
        nw_grouped = not_working.groupby("_nw_reason")["PWGTP"].sum()
        not_working_breakdown = {
            k: round(float(nw_grouped.get(k, 0)) / nw_total, 4) if nw_total > 0 else 0
            for k in NOT_WORKING_REASONS
        }
    else:
        not_working_breakdown = {k: 0 for k in NOT_WORKING_REASONS}

    return {
        "age_band": shares("_age_bucket", [k for k, _, _ in AGE_BUCKETS]),
        "has_kids_under_14": shares("_kids_bucket", ["yes", "no"]),
        "work_hours_per_wk": shares("_hours_bucket", WORK_HOURS_BUCKETS),
        "not_working_breakdown": not_working_breakdown,
        # v8: share of in-pool parents who turn out to be covered outside
        # expansion (below the state's Section 1931 limit) → not subject at all.
        "share_parents_covered_outside_expansion": round(
            refine_prov["share_parents_covered_outside_expansion"], 4
        ),
        "n_records": int(len(adults)),
        "total_weighted": int(total_weight),
    }


def main() -> None:
    load_dotenv(REPO / ".env.local")

    if not STATE_SUMMARY.exists():
        print(f"ERROR: {STATE_SUMMARY} missing — run state-summary bake first", file=sys.stderr)
        sys.exit(1)

    summary = json.loads(STATE_SUMMARY.read_text())
    states = summary["states"]

    out: dict[str, dict] = {}
    national_total = 0
    # National aggregation: weighted average of per-state shares, weighted by subject_total
    nat_shares = {
        "age_band": {k: 0.0 for k, _, _ in AGE_BUCKETS},
        "has_kids_under_14": {"yes": 0.0, "no": 0.0},
        "work_hours_per_wk": {k: 0.0 for k in WORK_HOURS_BUCKETS},
        "not_working_breakdown": {k: 0.0 for k in NOT_WORKING_REASONS},
    }
    nat_weight_total = 0.0
    nat_parent_outside_weighted = 0.0  # v8: subject-weighted national share

    for i, s in enumerate(states, 1):
        fips = s["state_fips"]
        if not s.get("expansion", False):
            continue
        subject = int(s.get("subject_count_strict", 0))
        if subject <= 0:
            continue
        abbr = s["state_abbr"]
        print(f"[{i}/{len(states)}] {abbr} {s['state_name']}")

        df = _load_pums_records(fips, abbr)
        shares = _compute_state_shares(df, fips)
        if shares["n_records"] == 0:
            print(f"    skipped {abbr}: 0 records after filter")
            continue

        out[fips] = {
            "state_fips": fips,
            "state_abbr": abbr,
            "state_name": s["state_name"],
            "subject_total": subject,
            "age_band": shares["age_band"],
            "has_kids_under_14": shares["has_kids_under_14"],
            "work_hours_per_wk": shares["work_hours_per_wk"],
            "not_working_breakdown": shares["not_working_breakdown"],
            "share_parents_covered_outside_expansion": shares["share_parents_covered_outside_expansion"],
        }
        national_total += subject
        nat_parent_outside_weighted += shares["share_parents_covered_outside_expansion"] * subject

        # Accumulate national shares weighted by subject count
        for panel_key in ("age_band", "has_kids_under_14", "work_hours_per_wk", "not_working_breakdown"):
            for bucket_key, v in shares[panel_key].items():
                nat_shares[panel_key][bucket_key] = nat_shares[panel_key].get(bucket_key, 0) + v * subject
        nat_weight_total += subject

    # Finalize national shares
    for panel_key in nat_shares:
        for bucket_key in nat_shares[panel_key]:
            nat_shares[panel_key][bucket_key] = round(
                nat_shares[panel_key][bucket_key] / nat_weight_total, 4
            ) if nat_weight_total > 0 else 0

    out["_national"] = {
        "state_fips": "_national",
        "state_abbr": "US",
        "state_name": "All expansion states",
        "subject_total": national_total,
        **nat_shares,
        "share_parents_covered_outside_expansion": round(
            nat_parent_outside_weighted / national_total, 4
        ) if national_total > 0 else 0.0,
    }

    PROFILE_OUT.write_text(json.dumps(out, indent=2))
    print()
    print(f"-> {PROFILE_OUT.relative_to(REPO)}  ({len(out) - 1} states + national)")
    print()
    # Sanity: confirm per-state shares actually differ
    sample_states = ["06", "18", "05", "25"]  # CA, IN, AR, MA
    print("Sample shares (work_hours_per_wk → 80_plus):")
    for fips in sample_states:
        if fips in out:
            v = out[fips]["work_hours_per_wk"].get("80_plus", 0)
            print(f"  {out[fips]['state_abbr']}: {v:.3f}")


if __name__ == "__main__":
    main()
