"""Emit benchmarks.json — the fiscal benchmark constants for the
"what a town gives up" module.

Every number is sourced from research/fiscal-benchmarks.md (Georgia DOAA
audit, El Paso Matters, Morrow County OR reporting, Pima County FAQ, JLARC).
Before writing, each load-bearing value is cross-checked against that file's
text; a missing value is a hard failure so a silent drift in the research
corpus cannot ship a stale number.
"""
from __future__ import annotations

import json
import sys

import config

FISCAL_MD = config.GIZMO_DIR / "research" / "fiscal-benchmarks.md"

# (value-as-it-appears-in-corpus, why it matters)
CROSSCHECKS = [
    ("$40M in fees over 15 years", "Morrow County OR enterprise-zone floor (~$2.7M/yr)"),
    ("$33.6M/yr gross", "Georgia audit representative campus gross"),
    ("$5.9M abated", "Georgia audit representative campus abated"),
    ("$27.8M", "Georgia audit representative campus collected"),
    ("~$56M/yr blended", "El Paso Meta all-entities blended annual"),
    (">90% but-for", "JLARC but-for attribution (Virginia)"),
    ("70% of Georgia data centers would exist WITHOUT the exemption",
     "Georgia Dec 2025 audit 30% attribution"),
    ("~50 permanent workers", "JLARC permanent jobs per typical facility"),
]

# Values verified against the Pima County Project Blue FAQ via the
# blocked-projects research track ($97M city + $60M county + $93M state = $250M
# over 10 years; local share = $157M).
PROJECT_BLUE = {"capex_usd_b": 3.6, "mw": 286, "local_10yr_usd_m": 157}


def build_payload() -> dict:
    return {
        "snapshot_date": config.SNAPSHOT_DATE,
        "horizon_years": 10,
        "jobs_per_facility_permanent": 50,
        "regimes": [
            {
                "id": "aggressive_abatement",
                "case": "Morrow County OR (enterprise zone)",
                "annual_local_usd_m_low": 2,
                "annual_local_usd_m_high": 3,
                "note": "2023 enterprise-zone deal traded >$1B in property taxes on five "
                        "AWS data centers for ~$40M in fees over 15 years (~$2.7M/yr).",
            },
            {
                "id": "partial_abatement",
                "case": "Georgia audit representative campus / El Paso Meta",
                "annual_local_usd_m_low": 27.8,
                "annual_local_usd_m_high": 56,
                "gross_annual_usd_m": 33.6,
                "abated_annual_usd_m": 5.9,
                "note": "Low end: Georgia DOAA audit's representative 3-building metro-Atlanta "
                        "campus ($33.6M gross, $5.9M abated, $27.8M collected). High end: "
                        "El Paso Meta, ~$56M/yr blended across all local entities.",
            },
            {
                "id": "unabated_equipment_tax",
                "case": "Virginia-style rates (Loudoun is the ceiling)",
                "annual_local_usd_m_low": 50,
                "annual_local_usd_m_high": 90,
                "note": "Unabated equipment-tax regimes; per-campus range is a modeling "
                        "band anchored at the corpus's '$50M+/yr unabated at Virginia-style "
                        "rates' floor. Loudoun's aggregate is the ceiling, not a per-campus figure.",
            },
        ],
        "reference_campus": {
            "name": "Project Blue scale",
            "capex_usd_b": PROJECT_BLUE["capex_usd_b"],
            "mw": PROJECT_BLUE["mw"],
            "local_10yr_usd_m": PROJECT_BLUE["local_10yr_usd_m"],
            "note": "$97M city + $60M county over 10 years per Pima County's FAQ",
        },
        "counterfactual": {
            "discount_applied": None,
            "note": "The calculator assumes a live proposal and applies no counterfactual "
                    "discount (2026-08-17 design decision) — the same undiscounted basis as "
                    "Pima County's own Project Blue estimate. The audit evidence on the "
                    "would-it-have-come question (JLARC ~90% but-for vs Georgia's 30%) is "
                    "cited in the prose, not modeled.",
        },
    }


def main() -> int:
    config.ensure_dirs()
    text = FISCAL_MD.read_text(encoding="utf-8")
    missing = [(needle, why) for needle, why in CROSSCHECKS if needle not in text]
    if missing:
        for needle, why in missing:
            print(f"  [benchmarks] FATAL cross-check miss: {needle!r} ({why}) "
                  f"not found in {FISCAL_MD.name}")
        return 1

    payload = build_payload()

    # internal consistency: Project Blue local share = 97 + 60
    assert payload["reference_campus"]["local_10yr_usd_m"] == 97 + 60
    # partial-abatement gross - abated ~= collected low end. The audit's own
    # published figures carry rounding (33.6 - 5.9 = 27.7 vs 27.8 stated), so
    # allow a 0.15 tolerance; we report the audit's numbers verbatim.
    partial = payload["regimes"][1]
    assert abs((partial["gross_annual_usd_m"] - partial["abated_annual_usd_m"])
               - partial["annual_local_usd_m_low"]) <= 0.15

    config.BENCHMARKS_JSON.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(f"  [benchmarks] {len(CROSSCHECKS)} corpus cross-checks passed; "
          f"wrote {config.BENCHMARKS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
