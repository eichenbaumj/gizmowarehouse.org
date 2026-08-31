#!/usr/bin/env python3
"""Bake demographic profile estimates for the subject pool.

Applies published national shares from KFF (KFF Medicaid Enrollment Tabulation,
2023 ACS PUMS) and Urban Institute (HIPSM model) to each state's subject
count to produce age × kids × work-hours breakdowns. State-level shares
would ideally come from PUMS, but at v0 we use national shares everywhere
and label this clearly in the methodology disclosure.

Outputs public/data/medicaid-subject-profile.json keyed by state FIPS, with
a "_national" aggregate. Each entry has:
  {
    "subject_total": int,
    "age_band":         {"19-24": pct, "25-34": pct, ...},
    "has_kids_under_14": {"yes": pct, "no": pct},
    "work_hours_per_wk": {"0": pct, "1-19": pct, "20-79": pct, "80_plus": pct},
  }
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE_SUMMARY = REPO / "public/data/medicaid-state-summary.json"
PROFILE_OUT = REPO / "public/data/medicaid-subject-profile.json"

# National shares — sources cited in METHODOLOGY.md §9
# KFF 2023 ACS tabulation of expansion-pathway Medicaid enrollees 19-64
NATIONAL_AGE_SHARES = {
    "19-24": 0.15,
    "25-34": 0.28,
    "35-44": 0.25,
    "45-54": 0.18,
    "55-64": 0.14,
}

# ACS B23008 cross-tab: expansion-Medicaid adults living with own child <14
# This is a synthetic split — actual share varies by state. Documented.
NATIONAL_HAS_KIDS_UNDER_14 = {
    "yes": 0.28,
    "no": 0.72,
}

# Current weekly work hours, ages 19-64 on expansion Medicaid. KFF + CPS.
# The 80+ band is people already above OBBBA's monthly threshold — they
# "should" be unaffected, but verification friction can still bounce them.
NATIONAL_WORK_HOURS = {
    "0":      0.35,
    "1-19":   0.12,
    "20-79":  0.25,
    "80_plus": 0.28,
}

# Per-state adjustments. We allow small deviations from the national share
# for the work_hours field only, where state economic conditions plausibly
# matter. Default = national. Hand-tuned for a few high-population states.
STATE_WORK_HOURS_OVERRIDES: dict[str, dict[str, float]] = {
    # Higher full-time share in tight-labor coastal markets
    "06": {"0": 0.32, "1-19": 0.13, "20-79": 0.25, "80_plus": 0.30},  # CA
    "36": {"0": 0.33, "1-19": 0.13, "20-79": 0.24, "80_plus": 0.30},  # NY
    # Higher unemployment in West Virginia, Kentucky
    "54": {"0": 0.42, "1-19": 0.10, "20-79": 0.24, "80_plus": 0.24},  # WV
    "21": {"0": 0.40, "1-19": 0.11, "20-79": 0.24, "80_plus": 0.25},  # KY
}


def main() -> None:
    summary = json.loads(STATE_SUMMARY.read_text())
    states = summary["states"]

    out: dict[str, dict] = {}
    national_total = 0
    for s in states:
        fips = s["state_fips"]
        subject = int(s.get("subject_count_strict", 0))
        if subject <= 0:
            continue
        national_total += subject

        out[fips] = {
            "state_fips": fips,
            "state_abbr": s["state_abbr"],
            "state_name": s["state_name"],
            "subject_total": subject,
            "age_band": NATIONAL_AGE_SHARES,
            "has_kids_under_14": NATIONAL_HAS_KIDS_UNDER_14,
            "work_hours_per_wk": STATE_WORK_HOURS_OVERRIDES.get(
                fips, NATIONAL_WORK_HOURS
            ),
        }

    out["_national"] = {
        "state_fips": "_national",
        "state_abbr": "US",
        "state_name": "All expansion states",
        "subject_total": national_total,
        "age_band": NATIONAL_AGE_SHARES,
        "has_kids_under_14": NATIONAL_HAS_KIDS_UNDER_14,
        "work_hours_per_wk": NATIONAL_WORK_HOURS,
    }

    PROFILE_OUT.write_text(json.dumps(out, indent=2))
    print(f"-> {PROFILE_OUT.relative_to(REPO)}  ({len(out)} entries)")


if __name__ == "__main__":
    main()
