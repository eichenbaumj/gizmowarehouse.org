"""Stage 04h — multi-category overlap distribution for the upset plot.

Computes the 16-cell joint distribution of the subject pool across four
qualifying-activity categories:

    W = working ≥80 hrs/month (WKHP ≥ 19 in the PUMS classifier)
    P = parent caregiver of child ≤13
    M = medically frail
    S = full-time student

Per-record PUMS source: stage 04b's classifier writes 16 weighted-count
columns per state cache parquet (overlap_cell_WPMS_count_weighted, etc.).
This stage reads those columns directly and aggregates to national. Earlier
versions of this stage used a marginal-independence simulation with
pairwise correlation adjustments; that approximation was replaced once
per-record joint counts became available in the PUMS cache.

Output: public/data/medicaid-category-overlaps.json — consumed by the
MedicaidCategoryOverlap React component.

Run: python 04h_compute_category_overlaps.py
"""

from __future__ import annotations

import json
import time

import pandas as pd

import config

STATE_SUMMARY_IN = config.PUBLIC_DATA_DIR / "medicaid-state-summary.json"
PUMS_CACHE_DIR = config.OUTPUT_DIR / "pums_state_cache"
OUTPUT_PATH = config.PUBLIC_DATA_DIR / "medicaid-category-overlaps.json"

CATEGORIES = ["W", "P", "M", "S"]
CATEGORY_LABELS = {
    "W": "Working ≥ qualifying hours / income",
    "P": "Parent caregiver of child ≤13",
    "M": "Medically frail",
    "S": "Full-time student",
}

# Generate all 16 cell keys in deterministic order.
CELL_KEYS = []
for w in (False, True):
    for p in (False, True):
        for m in (False, True):
            for s in (False, True):
                key = "".join(c if v else "-" for c, v in zip(CATEGORIES, (w, p, m, s)))
                CELL_KEYS.append(key)


def _cell_categories(key: str) -> list[str]:
    """Convert a cell key like 'WP--' to the list of present category codes."""
    return [c for c, present in zip(CATEGORIES, key) if present != "-"]


def _load_state_cells(state_abbr: str) -> dict | None:
    """Load the 16 cell counts + subject_pool_weighted from a state's cache parquet.
    Returns None if the cache is missing or doesn't have cell columns yet.
    """
    path = PUMS_CACHE_DIR / f"{state_abbr.lower()}_classified.parquet"
    if not path.exists():
        return None
    row = pd.read_parquet(path).iloc[0].to_dict()
    schema_v = int(row.get("cache_schema_version", 0))
    if schema_v < 5:
        return None
    cells = {key: float(row.get(f"overlap_cell_{key}_count_weighted", 0.0)) for key in CELL_KEYS}
    return {
        "subject_pool_weighted": float(row.get("subject_pool_weighted", 0.0)),
        "cells": cells,
        # v8: combination-of-activities floor (work part-time AND enrolled in
        # school → clears 80 hrs only by summing across activities).
        "combination_work_school": float(row.get("combination_work_school_count_weighted", 0.0)),
    }


def _distribution_from_cells(subject_count: int, cells: dict[str, float]) -> dict:
    """Build the public distribution object from raw cell counts."""
    total = sum(cells.values())
    cells_list = []
    for key in CELL_KEYS:
        count = int(round(cells.get(key, 0.0)))
        share = (cells.get(key, 0.0) / total) if total > 0 else 0.0
        cells_list.append({
            "key": key,
            "categories": _cell_categories(key),
            "count": count,
            "share": round(share, 4),
        })
    cells_list.sort(key=lambda c: -c["share"])

    # Roll up: how many subjects sit in 0/1/2/3/4 categories?
    by_count = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    for entry in cells_list:
        n = len(entry["categories"])
        by_count[n] += entry["count"]

    # Marginal totals per category — sum any cell that includes that category.
    marginal_totals = {
        cat: sum(c["count"] for c in cells_list if cat in c["categories"])
        for cat in CATEGORIES
    }

    return {
        "subject_count": int(subject_count),
        "cells": cells_list,
        "by_category_count": by_count,
        "marginal_totals": marginal_totals,
    }


def main() -> None:
    summary = json.loads(STATE_SUMMARY_IN.read_text())

    states_out = {}
    national_cells: dict[str, float] = {key: 0.0 for key in CELL_KEYS}
    national_subject = 0.0
    national_combination = 0.0
    missing_states: list[str] = []

    for s in summary["states"]:
        if not s.get("expansion"):
            continue
        cache = _load_state_cells(s["state_abbr"])
        if cache is None:
            missing_states.append(s["state_abbr"])
            continue
        pums_subject = cache["subject_pool_weighted"]
        if pums_subject <= 0:
            continue
        # Use the CBO-anchored subject count (subject_count_strict) for the
        # state's denominator — same source the subject-profile and Sankey use,
        # so all on-page numbers reconcile. Scale the cell counts by the
        # CBO/PUMS ratio so the per-state cell sum equals subject_count_strict
        # while preserving the per-cell PUMS-derived proportions.
        cbo_subject = float(s.get("subject_count_strict", 0))
        if cbo_subject <= 0:
            cbo_subject = pums_subject
        scale = cbo_subject / pums_subject
        scaled_cells = {key: count * scale for key, count in cache["cells"].items()}
        combination_scaled = cache["combination_work_school"] * scale

        states_out[s["state_fips"]] = {
            "abbr": s["state_abbr"],
            "name": s["state_name"],
            **_distribution_from_cells(int(cbo_subject), scaled_cells),
            "combination_work_school": int(round(combination_scaled)),
        }
        national_subject += cbo_subject
        national_combination += combination_scaled
        for key, count in scaled_cells.items():
            national_cells[key] += count

    national_out = _distribution_from_cells(int(national_subject), national_cells)
    national_out["combination_work_school"] = int(round(national_combination))

    payload = {
        "version": "v9.0-2026-05-30",
        "_meta": {
            "method": "per_record_pums_joint_counts",
            "categories": CATEGORIES,
            "category_labels": CATEGORY_LABELS,
            "combination_work_school_note": (
                "combination_work_school counts subjects who work part-time (WKHP 10-18, "
                "≈43-78 monthly hours — under the 80-hr work-alone bar) AND are enrolled in "
                "school. They clear OBBBA's 80-hour threshold only if the state sums hours "
                "across activities, which the statute permits. A FLOOR: volunteer and "
                "job-training hours that would also combine are not observable in PUMS."
            ),
            "source": (
                "ACS PUMS 5-Year 2020-2024 records classified per state in stage "
                "04b. Each subject in the post-filter sample (Medicaid + age 19-64 "
                "+ POVPIP ≤138) is assigned to exactly one of 16 cells based on "
                "four boolean flags: W (WKHP ≥ 19, i.e. ~80 hrs/month), P (parent "
                "caregiver of child ≤13 via household RELSHIPP linkage), M "
                "(medically frail: DIS=1 AND ≥2 specific functional flags), S "
                "(full-time student: SCH ∈ {2,3} AND SCHG ≥ 15). Cell counts are "
                "PWGTP-weighted. National = sum of state cells."
            ),
            "limitation": (
                "Very small expansion states (typically WY, VT, AK, ND, SD) have "
                "thinner PUMS samples; cell counts there are noisier than in larger "
                "states. Exemptions surfaced in the loss-breakdown Sankey (SUD "
                "treatment, recent incarceration, kinship caregivers, caregivers of "
                "disabled adults, AI/AN tribal membership, former foster youth, AYA "
                "cancer survivor) are not among the four categories shown here; "
                "subjects whose only qualifying status is one of those appear in the "
                "zero-bucket band of this view but in the appropriate exempt subgroup "
                "of the loss-breakdown. The subject pool here excludes Section 1931 "
                "parents and recent non-citizens."
            ),
        },
        "_national": national_out,
        "states": states_out,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))

    n = national_out
    print(f"Stage 04h — per-record overlap distribution for {len(states_out)} expansion states + DC")
    if missing_states:
        print(f"  WARN: {len(missing_states)} state(s) had no cell data (schema < 5): {', '.join(missing_states)}")
        print(f"  Re-run 04b --pums-mode full to populate cells.")
    print()
    print(f"National subject pool: {n['subject_count']:>12,.0f}")
    print()
    print(f"Distribution by # of qualifying-activity buckets:")
    for n_buckets, count in n["by_category_count"].items():
        pct = count / n["subject_count"] * 100 if n["subject_count"] > 0 else 0
        print(f"  {n_buckets} buckets: {count:>11,.0f}  ({pct:.1f}%)")
    print()
    print(f"Marginal totals:")
    for cat, count in n["marginal_totals"].items():
        pct = count / n["subject_count"] * 100 if n["subject_count"] > 0 else 0
        print(f"  {cat} ({CATEGORY_LABELS[cat]}): {count:>11,.0f}  ({pct:.1f}%)")
    print()
    print(f"Top 5 cells by share:")
    for cell in n["cells"][:5]:
        labels = " + ".join(cell["categories"]) if cell["categories"] else "(no qualifying activity)"
        print(f"  {cell['key']:<6}  {cell['count']:>11,.0f}  {cell['share']*100:>5.1f}%  {labels}")
    print()
    print(f"-> {OUTPUT_PATH}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 04h done in {time.time() - t0:.1f}s")
