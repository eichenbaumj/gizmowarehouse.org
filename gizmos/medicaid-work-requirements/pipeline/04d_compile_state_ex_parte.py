"""Stage 04d — compile per-state ex parte verification capability scores (v5).

Three-factor composite scoring. The composite predicts how well a state's
eligibility system can verify employment, exemption status, and qualifying
activity against existing administrative data without forcing the enrollee to
re-prove what the state already knows.

Sources:
  - KFF May 2026 implementation survey (43 states + DC)
  - State eligibility-system vendor public filings
  - CMS T-MSIS Technical Assessment summary 2025-Q4
  - State public-health vital-records modernization filings (CSTE registry,
    CDC WONDER documentation) — for vital_records_match
  - Publicly-filed WIOA state plans + NASWA workforce-data interoperability
    reports — for workforce_dev_records_match
  - Prior Section 1115 work-requirement experience (AR 2018 Sommers/NEJM,
    NH 2019, GA Pathways 2023-present, KY 2018 vacated) — for the new
    historical_churn factor; see state_historical_experience.json

v5 scoring formula (replaces v4 two-factor):

  Score A — Core Capability (0-100):
    system_integration (0-25)  — vendor tier lookup
    account_matching   (0-20)  — vendor tier lookup
    deduplication      (0-15)  — vendor tier lookup
    operational_sla    (0-15)  — round(integration_bonus × 0.75)
    self_attestation_policy (0-15)  — 15 if flag TRUE else 0
    identity_proofing  (0-10)  — vendor tier lookup
    SUM (cap 100)

  Score B — Data Sources (0-100), quality-weighted:
    Wage data        (30 pts): ui_wage_match (30). Income-verification tools (credit-agency, consent-based) are NOT scored — see §3.5.
    Medical frailty  (30 pts): medicaid_claims_match (20) + behavioral_health_mco_match (10)
    Other sources    (20 pts): snap_tanf_compliance_match (5) + vital_records_match (4)
                              + workforce_dev_records_match (4) + corrections_records_match (4)
                              + child_welfare_records_match (3)

  Score C — Historical Churn (0-100): round((1 - prior_denial_rate) × 100).
    States with prior Section 1115 work-requirement experience get a sourced
    score. States without prior experience use a neutral prior of 50. Loaded
    from state_historical_experience.json.

  Composite = round(0.4 × Score A + 0.4 × Score B + 0.2 × Score C)

  Bands (driven by composite):
    composite >= 70 → "low"   (admin churn likely substantially mitigated)
    composite 45-69 → "mid"
    composite < 45  → "high"  (admin churn likely Arkansas-grade)

The historical factor resolves the AR/CA inversion that v4 reviewers flagged:
under v4, AR's poor forward-looking capability (legacy ARIES, missing data
flags) produced composite 34, while its 2018 actual experience (~39% denial,
score component 61) was mid-tier. The 20% historical weight pulls AR up to
composite ~40 — still in the high-churn band, but with reasoning that matches
the empirical record. CA's neutral historical prior of 50 pulls its composite
from 100 down to ~93, which is more honest about the uncertainty.

Output:
  output/state_ex_parte_scored.parquet — state_fips, abbr, expansion,
      score (composite, for back-compat), composite, core_capability, data_sources,
      historical_churn, core_components_*, source_components_*, flag_*,
      integration_bonus, system_vendor, churn_band (back-compat alias for
      band_composite), band_composite, band_core_capability, band_data_sources,
      notes.

  state_ex_parte_capability.json — updated in place with computed scores,
      core_components{}, source_components{}, bands{}, historical_experience{}
      (when present), and a legacy `score` alias = composite for back-compat.

Run: python 04d_compile_state_ex_parte.py
"""

from __future__ import annotations

import json
import sys
import time

import pandas as pd

import config

EX_PARTE_JSON = config.PIPELINE_DIR / "state_ex_parte_capability.json"
HISTORICAL_JSON = config.PIPELINE_DIR / "state_historical_experience.json"
CURRENT_EX_PARTE_JSON = config.PIPELINE_DIR / "state_current_ex_parte.json"  # v8: observed rates
EX_PARTE_OUT = config.OUTPUT_DIR / "state_ex_parte_scored.parquet"

NEUTRAL_HISTORICAL_PRIOR = 50

# v8 (Esty review 2): composite weights now lead with the OBSERVED ex parte
# renewal rate (CMS unwinding data), which directly measures realized
# auto-renewal capability rather than the v5 vendor-tier proxy. Sourced from
# config so the weighting is documented in one place.
WEIGHT_OBSERVED = config.EX_PARTE_WEIGHTS["observed_ex_parte"]      # 0.50
WEIGHT_SOURCES = config.EX_PARTE_WEIGHTS["data_sources"]            # 0.35
WEIGHT_HISTORICAL = config.EX_PARTE_WEIGHTS["historical_churn"]     # 0.15
# The legacy vendor-tier "core capability" score is still computed and shown as
# a context sub-metric, but no longer feeds the composite.

# ----- Data-source flag taxonomy (v4) -----

DATA_SOURCE_FLAG_KEYS = [
    "medicaid_claims_match",
    "behavioral_health_mco_match",
    "ui_wage_match",
    "snap_tanf_compliance_match",
    "corrections_records_match",
    "child_welfare_records_match",
    "vital_records_match",
    "workforce_dev_records_match",
    "self_attestation_accepted",
]

SOURCE_WEIGHTS = {
    "ui_wage_match":               30,
    "medicaid_claims_match":       20,
    "behavioral_health_mco_match": 10,
    "snap_tanf_compliance_match":   5,
    "vital_records_match":          4,
    "workforce_dev_records_match":  4,
    "corrections_records_match":    4,
    "child_welfare_records_match":  3,
}

SOURCE_BUCKETS = {
    "wage_data":    ["ui_wage_match"],
    "frailty_data": ["medicaid_claims_match", "behavioral_health_mco_match"],
    "other_data":   ["snap_tanf_compliance_match", "vital_records_match",
                     "workforce_dev_records_match", "corrections_records_match",
                     "child_welfare_records_match"],
}

# ----- Vendor → core-capability tier lookup -----

VENDOR_TIER = {
    # Tier 1 — Most mature integrated stacks
    "CalSAWS": 1,
    "HIX-IES": 1,
    "HBE / ProviderOne": 1,
    "NYSoH / WMS": 1,
    "METS": 1,
    "CBMS": 1,
    "IES": 1,
    "ONE": 1,
    "COMPASS": 1,
    "VHC / ACCESS": 1,
    "MA EE": 1,
    "OBIE / Ohio Benefits": 1,
    # Tier 2 — Modern integrated, partial coverage
    "kynect": 2,
    "Bridges / MiBridges": 2,
    "NCFAST": 2,
    "NJ FamilyCare": 2,
    "KOLEA": 2,
    "DCAS": 2,
    "VaCMS": 2,
    # Tier 3 — Mid-tier integrated
    "HEAplus / Cúram": 3,
    "ASSIST": 3,
    "ImpaCT": 3,
    "ASPEN": 3,
    "ABE": 3,
    "ACCESS Nevada": 3,
    "NH EASY": 3,
    "ACES": 3,
    "RIBridges": 3,
    "eREP": 3,
    "iBES": 3,
    "LaMEDS": 3,
    "RAPIDS": 3,
    "MMIS-SD": 3,
    # Tier 4 — Limited integration
    "CHIMES": 4,
    "Vision": 4,
    "N-FOCUS": 4,
    # Tier 5 — Legacy / minimal
    "ICES (Cúram)": 5,
    "FAMIS": 5,
    "Soonercare IMS": 5,
    "ARIES (Northrop Grumman, legacy)": 5,
    "ARIES (planned migration)": 5,
}

VENDOR_TIER_SCORES = {
    1: {"system_integration": 25, "account_matching": 20, "deduplication": 15, "identity_proofing": 10},
    2: {"system_integration": 20, "account_matching": 16, "deduplication": 12, "identity_proofing":  8},
    3: {"system_integration": 15, "account_matching": 12, "deduplication": 10, "identity_proofing":  6},
    4: {"system_integration": 10, "account_matching":  8, "deduplication":  6, "identity_proofing":  4},
    5: {"system_integration":  5, "account_matching":  4, "deduplication":  3, "identity_proofing":  2},
}

# ----- Band thresholds -----

def score_to_band(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 70:
        return "low"
    if score >= 45:
        return "mid"
    return "high"


# ----- Score computations -----

def compute_score_b(flags: dict, components_out: dict) -> int:
    total = 0
    bucket_totals = {b: 0 for b in SOURCE_BUCKETS}
    for k, w in SOURCE_WEIGHTS.items():
        if flags.get(k, False):
            total += w
            for bucket, members in SOURCE_BUCKETS.items():
                if k in members:
                    bucket_totals[bucket] += w
                    break
    components_out.update(bucket_totals)
    return min(100, total)


def compute_score_a(entry: dict, components_out: dict) -> int:
    vendor = entry.get("system_vendor", "")
    tier = VENDOR_TIER.get(vendor, 5)
    base = VENDOR_TIER_SCORES[tier].copy()
    bonus = int(entry.get("integration_bonus", 0) or 0)
    sla = round(bonus * 0.75)
    if sla > 15:
        sla = 15
    self_attest = 15 if (entry.get("flags") or {}).get("self_attestation_accepted", False) else 0
    components_out.update(base)
    components_out["operational_sla"] = sla
    components_out["self_attestation_policy"] = self_attest
    return min(100, sum(base.values()) + sla + self_attest)


def load_historical_experience() -> dict:
    """Returns {fips: full_record} from state_historical_experience.json."""
    if not HISTORICAL_JSON.exists():
        print(f"WARNING: {HISTORICAL_JSON.name} missing, using neutral prior everywhere",
              file=sys.stderr)
        return {}
    payload = json.loads(HISTORICAL_JSON.read_text())
    return payload.get("states", {})


def load_observed_ex_parte() -> dict:
    """Returns {fips: observed_ex_parte_rate (0-1)} from state_current_ex_parte.json.

    Source: CMS State Medicaid & CHIP Eligibility Processing Data, the share of
    completed renewals conducted ex parte, volume-weighted 2023-03 to 2026-02.
    """
    if not CURRENT_EX_PARTE_JSON.exists():
        print(f"WARNING: {CURRENT_EX_PARTE_JSON.name} missing; using national "
              f"fallback ({config.OBSERVED_EX_PARTE_NATIONAL_FALLBACK:.0%}) everywhere",
              file=sys.stderr)
        return {}
    payload = json.loads(CURRENT_EX_PARTE_JSON.read_text())
    return {
        fips: rec.get("observed_ex_parte_rate")
        for fips, rec in payload.get("states", {}).items()
    }


def compute_scores(entry: dict, historical_record: dict | None,
                   observed_rate: float | None) -> dict:
    """Returns dict with composite / observed_ex_parte / core_capability /
    data_sources / historical_churn / sub-components / bands.

    v8: composite = round(0.50 × observed_ex_parte + 0.35 × data_sources
    + 0.15 × historical_churn). The vendor-tier core_capability score is still
    computed and returned as a context sub-metric but does NOT feed the composite.

    For non-expansion states (empty flags dict), returns all-null structure.
    """
    flags = entry.get("flags") or {}
    if not flags:
        return {
            "composite": None,
            "observed_ex_parte": None,
            "core_capability": None,
            "data_sources": None,
            "historical_churn": None,
            "core_components": None,
            "source_components": None,
            "bands": {"composite": None, "observed_ex_parte": None,
                      "core_capability": None, "data_sources": None,
                      "historical_churn": None},
        }
    core_components: dict = {}
    source_components: dict = {}
    score_a = compute_score_a(entry, core_components)        # core capability (context only)
    score_b = compute_score_b(flags, source_components)      # data sources
    if historical_record and historical_record.get("historical_churn_score") is not None:
        score_c = int(historical_record["historical_churn_score"])
    else:
        score_c = NEUTRAL_HISTORICAL_PRIOR
    # Observed ex parte renewal rate → 0-100. National fallback for any gap.
    rate = observed_rate if observed_rate is not None else config.OBSERVED_EX_PARTE_NATIONAL_FALLBACK
    score_observed = round(float(rate) * 100)
    composite = round(
        WEIGHT_OBSERVED * score_observed
        + WEIGHT_SOURCES * score_b
        + WEIGHT_HISTORICAL * score_c
    )
    return {
        "composite": composite,
        "observed_ex_parte": score_observed,
        "core_capability": score_a,
        "data_sources": score_b,
        "historical_churn": score_c,
        "core_components": core_components,
        "source_components": source_components,
        "bands": {
            "composite": score_to_band(composite),
            "observed_ex_parte": score_to_band(score_observed),
            "core_capability": score_to_band(score_a),
            "data_sources": score_to_band(score_b),
            "historical_churn": score_to_band(score_c),
        },
    }


# ----- Main -----

def main() -> None:
    if not EX_PARTE_JSON.exists():
        print(f"ERROR: {EX_PARTE_JSON} missing", file=sys.stderr)
        sys.exit(1)

    payload = json.loads(EX_PARTE_JSON.read_text())
    states = payload["states"]
    historical = load_historical_experience()
    observed_map = load_observed_ex_parte()   # v8: CMS observed ex parte renewal rates

    # Update _meta with v8 formula description (single source of truth).
    payload["_meta"]["version"] = "v9.0-2026-06-02"
    payload["_meta"]["scoring_formula"] = (
        "Observed-rate-led composite. Score A (OBSERVED ex parte, 0-100): the "
        "state's actual share of Medicaid renewals completed ex parte, from CMS eligibility-processing "
        "data (2023-03 to 2026-02), × 100. This is the dominant factor — a realized measure of "
        "auto-renewal capability, not a proxy. Score B (data sources, 0-100): wage 30pts (ui_wage 30; income-verification "
        "tools — credit-agency, consent-based — are not scored, see §3.5) + frailty 30pts (medicaid_claims 20 + behavioral_health_mco 10) + other 20pts "
        "(snap_tanf 5 + vital_records 4 + workforce_dev 4 + corrections 4 + child_welfare 3) — the "
        "work-requirement-specific feeds that income-renewal ex parte didn't test. Score C (historical "
        "churn, 0-100): round((1 - prior_section_1115_denial_rate) × 100); neutral 50 prior for states "
        "without documented prior work-requirement experience. Composite = round(0.50 × Score A + 0.35 × "
        "Score B + 0.15 × Score C). A legacy vendor-tier capability score is retained as "
        "context only and does not feed the composite. Bands: composite ≥ 70 'low churn', 45-69 "
        "'mid', < 45 'high churn'. See METHODOLOGY.md §3.5."
    )
    payload["_meta"]["uncertainty"] = (
        "The observed ex parte rate measures realized income/eligibility auto-renewal during the unwinding "
        "— necessary but not sufficient for work-requirement verification, which also needs the hours and "
        "exemption feeds captured in Score B. Treat the composite as a relative state-by-state ranking, not "
        "a prediction of work-requirement admin-churn rates. Score C is documented for the four states with "
        "prior Section 1115 work-requirement experience (AR, NH, GA, KY) and is a neutral 50 prior elsewhere."
    )
    payload["_meta"]["observed_ex_parte_source"] = (
        "CMS State Medicaid & CHIP Eligibility Processing Data (data.medicaid.gov 5abea2e0), share of "
        "completed renewals conducted ex parte, volume-weighted 2023-03 to 2026-02. National ~66.6%."
    )

    rows = []
    unknown_vendors = set()
    for fips, entry in states.items():
        historical_record = historical.get(fips)
        observed_rate = observed_map.get(fips)
        scores = compute_scores(entry, historical_record, observed_rate)
        entry["scores"] = {
            "composite": scores["composite"],
            "observed_ex_parte": scores["observed_ex_parte"],
            "core_capability": scores["core_capability"],
            "data_sources": scores["data_sources"],
            "historical_churn": scores["historical_churn"],
        }
        if observed_rate is not None and (entry.get("flags") or {}):
            entry["observed_ex_parte_rate"] = round(float(observed_rate), 4)
        entry["core_components"] = scores["core_components"]
        entry["source_components"] = scores["source_components"]
        entry["bands"] = scores["bands"]
        entry["score"] = scores["composite"]
        entry["churn_band"] = scores["bands"]["composite"]
        if historical_record:
            entry["historical_experience"] = {
                "denial_rate": historical_record.get("denial_rate"),
                "implementation_window": historical_record.get("implementation_window"),
                "people_affected": historical_record.get("people_affected"),
                "primary_source": historical_record.get("primary_source"),
                "context_note": historical_record.get("context_note"),
            }
        elif "historical_experience" in entry:
            del entry["historical_experience"]

        vendor = entry.get("system_vendor", "")
        if (entry.get("flags") or {}) and vendor and vendor not in VENDOR_TIER:
            unknown_vendors.add(vendor)

        info = config.STATE_INFO.get(fips, {})
        row = {
            "state_fips": fips,
            "state_abbr": entry["abbr"],
            "state_name": info.get("name", entry["abbr"]),
            "expansion": info.get("expansion", False),
            "system_vendor": vendor,
            "integration_bonus": int(entry.get("integration_bonus", 0) or 0),
            "score": scores["composite"],
            "composite": scores["composite"],
            "observed_ex_parte": scores["observed_ex_parte"],
            "observed_ex_parte_rate": round(float(observed_rate), 4) if observed_rate is not None else None,
            "core_capability": scores["core_capability"],
            "data_sources": scores["data_sources"],
            "historical_churn": scores["historical_churn"],
            "churn_band": scores["bands"]["composite"],
            "band_composite": scores["bands"]["composite"],
            "band_observed_ex_parte": scores["bands"]["observed_ex_parte"],
            "band_core_capability": scores["bands"]["core_capability"],
            "band_data_sources": scores["bands"]["data_sources"],
            "has_historical_experience": historical_record is not None,
            "notes": entry.get("notes", ""),
        }
        if scores["core_components"]:
            for k, v in scores["core_components"].items():
                row[f"core_{k}"] = v
            for k, v in scores["source_components"].items():
                row[f"source_{k}"] = v
        else:
            for k in ["system_integration", "account_matching", "deduplication",
                      "operational_sla", "self_attestation_policy", "identity_proofing"]:
                row[f"core_{k}"] = None
            for k in SOURCE_BUCKETS:
                row[f"source_{k}"] = None
        for k in DATA_SOURCE_FLAG_KEYS:
            row[f"flag_{k}"] = bool((entry.get("flags") or {}).get(k, False))
        rows.append(row)

    df = pd.DataFrame(rows).sort_values(["expansion", "composite"], ascending=[False, False])
    df.to_parquet(EX_PARTE_OUT, index=False)
    EX_PARTE_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    scored = df[df["composite"].notna()]
    n_scored = len(scored)
    n_unscored = df["composite"].isna().sum()
    high = (df["band_composite"] == "high").sum()
    mid = (df["band_composite"] == "mid").sum()
    low = (df["band_composite"] == "low").sum()
    n_historical = df["has_historical_experience"].sum()

    print(f"Stage 04d v8 — observed-rate-led scoring (50/35/15 observed/sources/historical; core = context only)")
    print(f"Scored {n_scored} expansion states + DC; {n_unscored} non-expansion (null).")
    print(f"States with prior Section 1115 experience: {n_historical}")
    print()
    print(f"Composite bands:")
    print(f"  high (composite <45):  {high:>2} states  — {', '.join(df[df.band_composite == 'high']['state_abbr'].tolist())}")
    print(f"  mid  (composite 45-69): {mid:>2} states")
    print(f"  low  (composite ≥70):  {low:>2} states  — {', '.join(df[df.band_composite == 'low']['state_abbr'].tolist())}")
    print()
    print(f"Top 10 by composite:")
    for _, r in scored.head(10).iterrows():
        marker = " *" if r["has_historical_experience"] else "  "
        print(f"  {r['state_abbr']:<3}{marker} composite {r['composite']:>3}  obs {r['observed_ex_parte']:>3}  sources {r['data_sources']:>3}  hist {r['historical_churn']:>3}  (core {r['core_capability']:>3}, {r['system_vendor']})")
    print()
    print(f"Bottom 10 expansion states by composite:")
    for _, r in scored.tail(10).iterrows():
        marker = " *" if r["has_historical_experience"] else "  "
        print(f"  {r['state_abbr']:<3}{marker} composite {r['composite']:>3}  obs {r['observed_ex_parte']:>3}  sources {r['data_sources']:>3}  hist {r['historical_churn']:>3}  (core {r['core_capability']:>3}, {r['system_vendor']})")
    print()
    print("(* indicates state has documented prior Section 1115 work-requirement experience)")

    if unknown_vendors:
        print()
        print("WARNING: unknown vendor(s), scored at tier 5 (conservative):")
        for v in sorted(unknown_vendors):
            print(f"  '{v}'")
        print("Add to VENDOR_TIER in 04d_compile_state_ex_parte.py to fix.")

    print(f"\n-> {EX_PARTE_OUT.relative_to(config.PIPELINE_DIR)}")
    print(f"-> {EX_PARTE_JSON.name} (updated in place with v8 observed-rate-led scores)")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"\nStage 04d done in {time.time() - t0:.1f}s")
