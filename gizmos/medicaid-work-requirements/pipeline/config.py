"""Centralized config for the Medicaid Work Requirements pipeline.

Every policy parameter, ACS variable list, color stop, and cross-validation
benchmark lives here. If you find a magic number elsewhere in the pipeline,
it's a bug — move it here with a citation.

See METHODOLOGY.md for the why behind every value.
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent
RAW_DIR = PIPELINE_DIR / "raw"
OUTPUT_DIR = PIPELINE_DIR / "output"
GIZMO_DIR = PIPELINE_DIR.parent
REPO_ROOT = GIZMO_DIR.parent.parent
PUBLIC_DATA_DIR = REPO_ROOT / "public" / "data"
PUBLIC_ASSETS_DIR = REPO_ROOT / "public" / "assets"

for d in (RAW_DIR, OUTPUT_DIR, PUBLIC_DATA_DIR, PUBLIC_ASSETS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# ACS configuration
# ---------------------------------------------------------------------------
# 5-Year ACS 2020-2024 is the latest tract-level release as of 2026-05.
# When 2021-2025 publishes (~Dec 2026), bump this and re-run the pipeline.
ACS_VINTAGE = "2024"
ACS_BASE_URL = f"https://api.census.gov/data/{ACS_VINTAGE}/acs/acs5"

# ACS tables we pull. Each value is a list of column suffixes (the `_NNNXE`
# tail after the table prefix). We always fetch both `_NNNE` (estimate) and
# `_NNNM` (margin of error). Stage 01 expands these to full variable names.
#
# B27003: Medicaid coverage by sex × age. The spine of our estimate.
# B18135: Age × disability × insurance — disability exemption pivot.
# B17024: Age × income/poverty ratio — 138% FPL filter.
# B23008: Age of own children by parents' employment — parent-of-<14 logic.
# B11003: Family households by presence of children under 18.
# B09001: Population under 18 by single year of age — to interpolate <14 share.
# B14004: School enrollment by detailed level — full-time student exemption.
# B16002 / B16004: Language spoken at home — burden-index input.
# B28002: Internet access — burden-index input.
# B15003: Educational attainment — burden-index "low literacy" proxy.
# B01001: Sex by age — denominator.
# B03002: Hispanic origin by race — burden-index input.
# C24010: Sex by occupation for civilian employed 16+ — labor volatility input.
ACS_TABLES = {
    "B27003": "medicaid_coverage_by_sex_age",
    "B18135": "age_disability_insurance",
    "B17024": "age_poverty_ratio",
    "B23008": "age_children_parent_employment",
    "B11003": "family_households_children",
    "B09001": "under_18_population",
    "B14004": "school_enrollment_detailed",
    "B16002": "household_language",
    "B16004": "language_by_ability_to_speak_english",
    "B28002": "internet_access",
    "B15003": "educational_attainment",
    "B01001": "sex_by_age",
    "B03002": "hispanic_origin_by_race",
    "C24010": "sex_by_occupation",
}

# ---------------------------------------------------------------------------
# State info
# ---------------------------------------------------------------------------
# `fips` is the 2-digit state FIPS. `expansion` is True for full ACA expansion,
# False for non-expansion (per KFF as of 2026-05-22). `partial_expansion`
# flags Georgia's Pathways to Coverage (active through 2026-12-31).
# `hardship_exception_status` from KFF May 2026 implementation survey:
#   - "adopting" (27 states + DC)
#   - "undecided" (12 states)
#   - "not_adopting" (4 confirmed: IN, IA, MO, OK)
#   - "no_qualifying_counties" (16 states + DC where N/A)
#   - "non_expansion" (the 10 non-expansion states — exception is moot)
STATE_INFO: dict[str, dict] = {
    "01": {"abbr": "AL", "name": "Alabama", "expansion": False, "hardship_exception_status": "non_expansion"},
    "02": {"abbr": "AK", "name": "Alaska", "expansion": True, "hardship_exception_status": "undecided"},
    "04": {"abbr": "AZ", "name": "Arizona", "expansion": True, "hardship_exception_status": "undecided"},
    "05": {"abbr": "AR", "name": "Arkansas", "expansion": True, "hardship_exception_status": "adopting", "early_implementer": "2026-07-01 soft, 2027-01 full"},
    "06": {"abbr": "CA", "name": "California", "expansion": True, "hardship_exception_status": "adopting"},
    "08": {"abbr": "CO", "name": "Colorado", "expansion": True, "hardship_exception_status": "adopting"},
    "09": {"abbr": "CT", "name": "Connecticut", "expansion": True, "hardship_exception_status": "adopting"},
    "10": {"abbr": "DE", "name": "Delaware", "expansion": True, "hardship_exception_status": "no_qualifying_counties"},
    "11": {"abbr": "DC", "name": "District of Columbia", "expansion": True, "hardship_exception_status": "no_qualifying_counties"},
    "12": {"abbr": "FL", "name": "Florida", "expansion": False, "hardship_exception_status": "non_expansion"},
    "13": {"abbr": "GA", "name": "Georgia", "expansion": False, "partial_expansion": "Pathways to Coverage through 2026-12-31", "hardship_exception_status": "non_expansion"},
    "15": {"abbr": "HI", "name": "Hawaii", "expansion": True, "hardship_exception_status": "undecided"},
    "16": {"abbr": "ID", "name": "Idaho", "expansion": True, "hardship_exception_status": "adopting"},
    "17": {"abbr": "IL", "name": "Illinois", "expansion": True, "hardship_exception_status": "adopting"},
    "18": {"abbr": "IN", "name": "Indiana", "expansion": True, "hardship_exception_status": "not_adopting"},
    "19": {"abbr": "IA", "name": "Iowa", "expansion": True, "hardship_exception_status": "not_adopting", "early_implementer": "2026-12-01"},
    "20": {"abbr": "KS", "name": "Kansas", "expansion": False, "hardship_exception_status": "non_expansion"},
    "21": {"abbr": "KY", "name": "Kentucky", "expansion": True, "hardship_exception_status": "adopting"},
    "22": {"abbr": "LA", "name": "Louisiana", "expansion": True, "hardship_exception_status": "adopting"},
    "23": {"abbr": "ME", "name": "Maine", "expansion": True, "hardship_exception_status": "adopting"},
    "24": {"abbr": "MD", "name": "Maryland", "expansion": True, "hardship_exception_status": "no_qualifying_counties"},
    "25": {"abbr": "MA", "name": "Massachusetts", "expansion": True, "hardship_exception_status": "no_qualifying_counties"},
    "26": {"abbr": "MI", "name": "Michigan", "expansion": True, "hardship_exception_status": "adopting"},
    "27": {"abbr": "MN", "name": "Minnesota", "expansion": True, "hardship_exception_status": "adopting"},
    "28": {"abbr": "MS", "name": "Mississippi", "expansion": False, "hardship_exception_status": "non_expansion"},
    "29": {"abbr": "MO", "name": "Missouri", "expansion": True, "hardship_exception_status": "not_adopting"},
    "30": {"abbr": "MT", "name": "Montana", "expansion": True, "hardship_exception_status": "adopting", "early_implementer": "2026-07-01"},
    "31": {"abbr": "NE", "name": "Nebraska", "expansion": True, "hardship_exception_status": "adopting", "early_implementer": "2026-05-01 (live)"},
    "32": {"abbr": "NV", "name": "Nevada", "expansion": True, "hardship_exception_status": "adopting"},
    "33": {"abbr": "NH", "name": "New Hampshire", "expansion": True, "hardship_exception_status": "adopting"},
    "34": {"abbr": "NJ", "name": "New Jersey", "expansion": True, "hardship_exception_status": "adopting"},
    "35": {"abbr": "NM", "name": "New Mexico", "expansion": True, "hardship_exception_status": "adopting"},
    "36": {"abbr": "NY", "name": "New York", "expansion": True, "hardship_exception_status": "adopting"},
    "37": {"abbr": "NC", "name": "North Carolina", "expansion": True, "hardship_exception_status": "adopting"},
    "38": {"abbr": "ND", "name": "North Dakota", "expansion": True, "hardship_exception_status": "no_qualifying_counties"},
    "39": {"abbr": "OH", "name": "Ohio", "expansion": True, "hardship_exception_status": "adopting"},
    "40": {"abbr": "OK", "name": "Oklahoma", "expansion": True, "hardship_exception_status": "not_adopting"},
    "41": {"abbr": "OR", "name": "Oregon", "expansion": True, "hardship_exception_status": "adopting"},
    "42": {"abbr": "PA", "name": "Pennsylvania", "expansion": True, "hardship_exception_status": "adopting"},
    "44": {"abbr": "RI", "name": "Rhode Island", "expansion": True, "hardship_exception_status": "no_qualifying_counties"},
    "45": {"abbr": "SC", "name": "South Carolina", "expansion": False, "hardship_exception_status": "non_expansion"},
    "46": {"abbr": "SD", "name": "South Dakota", "expansion": True, "hardship_exception_status": "no_qualifying_counties"},
    "47": {"abbr": "TN", "name": "Tennessee", "expansion": False, "hardship_exception_status": "non_expansion"},
    "48": {"abbr": "TX", "name": "Texas", "expansion": False, "hardship_exception_status": "non_expansion"},
    "49": {"abbr": "UT", "name": "Utah", "expansion": True, "hardship_exception_status": "undecided"},
    "50": {"abbr": "VT", "name": "Vermont", "expansion": True, "hardship_exception_status": "no_qualifying_counties"},
    "51": {"abbr": "VA", "name": "Virginia", "expansion": True, "hardship_exception_status": "adopting"},
    "53": {"abbr": "WA", "name": "Washington", "expansion": True, "hardship_exception_status": "adopting"},
    "54": {"abbr": "WV", "name": "West Virginia", "expansion": True, "hardship_exception_status": "adopting"},
    "55": {"abbr": "WI", "name": "Wisconsin", "expansion": False, "hardship_exception_status": "non_expansion"},
    "56": {"abbr": "WY", "name": "Wyoming", "expansion": False, "hardship_exception_status": "non_expansion"},
}

# ---------------------------------------------------------------------------
# Subject-via-1115-waiver states (CMS June 2026 OBBBA subject-state list)
# ---------------------------------------------------------------------------
# OBBBA §1902(xx) reaches the ACA expansion-adult group AND "certain enrollees
# in 1115 waiver programs." Per KFF's tracker and CMS's June 2026 list, the
# requirement covers 44 states + DC: all 41 expansion states PLUS three
# NON-expansion states whose 1115 demonstrations cover an expansion-like adult
# slice — Wisconsin, Georgia, Tennessee. (Five expansion states — HI, MA, NY,
# OR, UT — also have waiver populations, but they are already counted via
# expansion=True; see METHODOLOGY for the small residual undercount.)
#
# These three states did NOT expand, so `expansion` stays False (it drives the
# uninsured overlay and the non-expansion explainer copy). Only an
# administratively-defined SLICE of their 1115 population is subject — sized from
# admin enrollment, NOT the full ACS Medicaid-adult pool. Flipping expansion=True
# would rake the whole state Medicaid-adult pool (millions) and massively
# overcount. Stage 04 rakes the ACS B27003 tract shape to `control_total`.
#
# The three cases differ sharply (handled honestly, per project decision):
#   - WI: ~198K non-disabled childless adults ≤100% FPL (BadgerCare Plus), NOT
#         currently work-conditional → a genuine new loss; fully modeled.
#   - GA: ~8K Pathways enrollees, ALREADY work-conditional (80 hrs/mo since 2023)
#         → OBBBA adds no NET-NEW loss; carried as subject, loss zeroed.
#   - TN: named on the CMS list, but the specific subject population is NOT
#         publicly quantified → flagged as subject, control_total 0, no number.
WAIVER_SUBJECT: dict[str, dict] = {
    "55": {  # Wisconsin
        "control_total": 198_000,
        "already_work_conditional": False,
        "loss_quantified": True,
        # The BadgerCare waiver slice is childless adults by definition, so the
        # parent/caretaker-of-a-child exemption does not apply. Stages 05 and 04c
        # zero that one exemption for childless_only states to avoid removing (and
        # then modeling phantom documentation failures for) parents who aren't here.
        "childless_only": True,
        "label": "BadgerCare Plus childless adults (Section 1115 waiver, ≤100% FPL)",
        "source": (
            "CMS June 2026 OBBBA subject-state list; Wisconsin DHS BadgerCare Plus "
            "1115 waiver enrollment (~198K non-disabled childless adults, Jan 2025)"
        ),
    },
    "13": {  # Georgia
        "control_total": 8_000,
        "already_work_conditional": True,
        "loss_quantified": True,
        "label": "Pathways to Coverage enrollees (Section 1115 waiver; already work-conditional)",
        "source": (
            "CMS June 2026 OBBBA subject-state list; Georgia Pathways to Coverage "
            "enrollment (~8K enrolled, early 2026)"
        ),
    },
    "47": {  # Tennessee
        "control_total": 0,
        "already_work_conditional": False,
        "loss_quantified": False,
        "label": "TennCare III 1115 'MEC Additions' adults (~17.7K parents/caretakers ≤100% FPL) — near-all exempt as parents of a child <14",
        "source": (
            "KFF's read of the CMS June 2026 subject-state list. The only TennCare group OBBBA "
            "reaches is the Section 1115(a)(2) 'MEC Additions' adults — parents/caretaker relatives "
            "covered to 100% FPL (eligibility group EG16 = 17,758, TennCare III quarterly report "
            "Jan-Mar 2025; state projected ~8,100 when added in 2024). But OBBBA exempts parents of "
            "a dependent child under 14 (§1902(xx)(9)), so the genuinely-subject slice is negligible; "
            "we flag Tennessee as in-scope but model no loss. Tennessee has no ACA expansion group."
        ),
    },
}
# Every state CMS names with a subject 1115 waiver population (WI, GA, TN),
# whether or not we can size it.
WAIVER_LISTED_FIPS = list(WAIVER_SUBJECT.keys())

# Convenience derived lists
ALL_STATE_FIPS = list(STATE_INFO.keys())
EXPANSION_STATE_FIPS = [f for f, info in STATE_INFO.items() if info["expansion"]]
NON_EXPANSION_STATE_FIPS = [f for f, info in STATE_INFO.items() if not info["expansion"]]
ADOPTING_HARDSHIP_FIPS = [f for f, info in STATE_INFO.items() if info["hardship_exception_status"] == "adopting"]

# States with ANY OBBBA-subject population we can size (expansion OR a waiver
# slice with a positive control total). This is the predicate downstream stages
# should use when they mean "is this place in scope and modelable," as distinct
# from EXPANSION_STATE_FIPS which means "literally adopted ACA expansion." TN
# (control_total 0) is intentionally excluded — it is flagged, not modeled.
SUBJECT_STATE_FIPS = [
    f for f in STATE_INFO
    if STATE_INFO[f]["expansion"]
    or WAIVER_SUBJECT.get(f, {}).get("control_total", 0) > 0
]


def subject_to_requirement(fips: str) -> bool:
    """True if the state has an OBBBA-subject population we model (expansion or a
    sized 1115-waiver slice). TN (listed but control_total 0) returns False."""
    info = STATE_INFO.get(fips, {})
    if info.get("expansion"):
        return True
    return WAIVER_SUBJECT.get(fips, {}).get("control_total", 0) > 0


def waiver_meta(fips: str) -> dict:
    """The WAIVER_SUBJECT record for a state (empty dict if not a waiver state).
    Carries control_total / already_work_conditional / loss_quantified / label."""
    return WAIVER_SUBJECT.get(fips, {})

# ---------------------------------------------------------------------------
# Geography source URLs
# ---------------------------------------------------------------------------
# TIGER/Line cartographic boundary files (cb_2024 vintage). 500k is the most
# simplified version, suitable for web. We use these instead of full TIGER/Line
# because the simplified geometry reduces our tile bundle by ~85%.
TIGER_BASE = "https://www2.census.gov/geo/tiger/GENZ2024/shp"
TIGER_STATE_URL = f"{TIGER_BASE}/cb_2024_us_state_500k.zip"
TIGER_COUNTY_URL = f"{TIGER_BASE}/cb_2024_us_county_500k.zip"
TIGER_TRACT_URL_FMT = f"{TIGER_BASE}/cb_2024_{{state_fips}}_tract_500k.zip"

# Coordinate reference systems
SOURCE_CRS = "EPSG:4326"
WEB_CRS = "EPSG:4326"  # MapLibre wants WGS84

# ---------------------------------------------------------------------------
# Administrative calibration sources
# ---------------------------------------------------------------------------
# KFF Medicaid expansion enrollment by state — published periodically.
# We will manually update the URL when refreshing the pipeline.
KFF_EXPANSION_ENROLLMENT_URL = "https://www.kff.org/medicaid/state-indicator/medicaid-expansion-enrollment/"

# CMS T-MSIS state monthly enrollment snapshots — published at
# https://www.medicaid.gov/medicaid/data-and-systems/macbis/medicaid-and-chip-enrollment-data/
TMSIS_URL = "https://www.medicaid.gov/medicaid/data-and-systems/macbis/medicaid-and-chip-enrollment-data/"

# BLS LAUS county unemployment — monthly CSV. We pull the 12-month series
# Feb 2025 - Jan 2026 to match KFF's high-unemployment-exception analysis.
BLS_LAUS_URL = "https://www.bls.gov/lau/laucnty24.txt"
BLS_LAUS_VINTAGE = "Feb 2025 - Jan 2026"

# SAMHSA NSDUH state-level SUD prevalence (latest = 2023 release).
SAMHSA_NSDUH_URL = "https://www.samhsa.gov/data/release/2023-national-survey-drug-use-and-health-nsduh-releases"

# SAHIE county-level Medicaid coverage estimates (Small Area Health Insurance Estimates).
SAHIE_URL = "https://www.census.gov/programs-surveys/sahie.html"

# ---------------------------------------------------------------------------
# OBBBA exemption parameters
# ---------------------------------------------------------------------------
# Federally mandatory exemptions (Section 71119 → § 1902(xx)). For each
# exemption we record the share of expansion-adult enrollees we estimate
# falls in that category at the national level. State-level rates come
# from PUMS apportionment in stage 04.
#
# These nationals are *prior* values, not point estimates. They get
# adjusted state-by-state in the pipeline. Source citations per row.
NATIONAL_EXEMPTION_RATES = {
    # v7 (Esty review follow-up): bumped from 0.25 to 0.28 to align with state
    # MMIS reports of 25-30% of expansion adults meeting medical-frailty
    # criteria once chronic conditions are surfaced through diagnostic codes.
    # 0.28 is the midpoint of the reported range. Floor/cap envelope in 04e
    # ([0.5×, 2.0×]) shifts accordingly to [0.140, 0.560].
    "medically_frail": 0.28,
    # v4 (Esty review): per-state rate from 04e via PUMS FER (gave birth in past
    # 12 months). FER captures a 12-month window rather than point-in-time, and
    # over the 6-month renewal cycle every woman who has a birth in that year
    # passes through the postpartum exemption window. National prior set to 0.03
    # (3.0%) to align with the FER measurement; floor/cap envelope at
    # [0.5×, 2.0×] = [1.5%, 6.0%]. v3 used 1.5% point-in-time uniform.
    "pregnant_postpartum": 0.03,
    # ACS B23008 + B09001: roughly 1 in 5 expansion adults has a child
    # under 14 they care for. Apportioned tract-by-tract in stage 04.
    "parent_caretaker_child_under_14": 0.20,
    # ACS B14004 + PUMS full-time-share: ~3-5% of expansion adults are
    # full-time students. We start at 0.04.
    "full_time_student": 0.04,
    # BJS NPS: ~0.5-1% of expansion adults are recently incarcerated.
    "recent_incarceration": 0.008,
    # SAMHSA NSDUH 2023-2024 SAE: ~17% of adults 18+ have past-year SUD;
    # of those, ~35% are in treatment qualifying for medically-frail under
    # OBBBA. National prior is 0.17 × 0.35 ≈ 0.06 (Medicaid-adjusted ~0.042
    # for the 12% Medicaid-enrollee subset). Stage 04e refines per-state.
    "sud_treatment": 0.042,
    # KFF research on dual SNAP+Medicaid: ~15-20% overlap; of those, ~50%
    # would be SNAP-work-compliant. So roughly 8% of expansion adults.
    "snap_tanf_work_compliant": 0.08,
    # v5 NEW: caregivers of disabled adults (often older relatives or adult
    # children). AARP/NAC 2020 "Caregiving in the US" reports ~16% of adults
    # provide unpaid care to an adult; among low-income working-age adults
    # the share is somewhat lower (~10%), and the subset where the care
    # recipient has a documented disability that would qualify the caregiver
    # for an OBBBA exemption is roughly 3-4%. Sarah Esty review: this is a
    # sizable population not surfaced in v4.
    "caregivers_disabled_adult": 0.03,
    # v5 NEW: non-parent kinship caregivers of children ≤13 (grandparents,
    # aunts/uncles, older siblings). AECF KIDS COUNT 2023: ~3% of US children
    # live in non-parent kinship arrangements; for low-income families closer
    # to 7%. Translates to ~1.5% of the expansion subject pool. Pulled out as
    # a distinct subgroup in v5 because the documentation pathway differs
    # materially from parental caretaking — no birth-certificate match.
    "kinship_caregivers": 0.015,
    # v7 NEW (Esty review follow-up): "compliant via other qualifying activity"
    # subgroup — volunteer hours and DOL/WIOA job-training program enrollment.
    # CPS Volunteering Supplement 2023 + DOL WIOA participant data: ~1.5% of
    # low-income working-age adults participate at counts that would meet the
    # OBBBA hours threshold. No good ex-parte admin pathway (volunteer hours
    # aren't centrally tracked); failure rate is high. Lives in the compliant
    # bucket (work/school/volunteer), not the exempt bucket.
    "volunteering_job_training": 0.015,
    # v8 NEW (Esty review 2): AI/AN tribal members, pulled out of the v7
    # other-categorical bundle as their own line. American Indians and Alaska
    # Natives are exempt under OBBBA, and — unlike foster youth or AYA cancer
    # survivors — they ARE observable in the ACS PUMS (RACAIAN recode flags any
    # respondent reporting AI/AN alone or in combination). Stage 04e derives a
    # per-state rate from PUMS; this national prior (~1.0% of the expansion
    # subject pool, IHS/Census order of magnitude) is the floor/cap anchor and
    # the small-sample fallback. The exemption pathway is tribal/IHS enrollment
    # data, which few state eligibility systems consume, so the failure rate
    # is high. Sarah Esty: "We should be able to pull AI/AN."
    "ai_an_exempt": 0.010,
    # v8 (Esty review 2): residual "other categorical exempt" AFTER pulling
    # AI/AN out. Former foster youth aged out under 26 (~0.4% per AFCARS/Casey),
    # AYA cancer survivors (~0.1% per NCI SEER), and the SNAP/TANF work-req
    # compliant subset where Medicaid eligibility doesn't auto-flow (~0.9%).
    # None of these are observable in PUMS, so this stays a uniform prior.
    # Lives in the exemption-doc bucket; high failure rate (50% base) because
    # the admin pathway is fragmented across foster/cancer-registry/SNAP-TANF
    # data sources, only some of which states have integrated.
    "other_categorical_exempt": 0.014,
}

# ---------------------------------------------------------------------------
# Eligibility refinements (v8 — Sarah Esty review 2, 2026-05-30)
# ---------------------------------------------------------------------------
# These close gaps the CBPP critique (relayed via Esty) identified in ACS/PUMS
# Medicaid work-requirement analyses. Our subject pool is raked to administrative
# control totals (T-MSIS expansion enrollment + CBO 18.5M), so our *level* is
# anchored; these refinements correct the within-pool *composition* that drives
# the subject profile, the qualifying-activity overlap, and the exemption rates.

# --- Section 1931 parent carve-out -----------------------------------------
# Parents/caretaker relatives covered through the mandatory Section 1931
# parent/caretaker pathway are NOT in the ACA-expansion category (VIII), so the
# OBBBA work requirement does not apply to them at all. In an expansion state, a
# low-income parent is enrolled under 1931 if their income is below the state's
# 1931 limit, and under expansion between that limit and 138% FPL. We therefore
# treat a PUMS parent (own child < 19 in household) whose POVPIP is below the
# state's 1931 limit as non-expansion / not-subject and remove them from the
# subject pool. Georgetown CCF (2026-04) clarifies that under OBBBA all parents
# of a child under 14 are exempt regardless of pathway, so the binding case is
# parents of teens (14-17) in high-1931-limit states.
#
# Values are the "Section 1931 Limit" (% FPL) from Georgetown CCF's April 2026
# Datawrapper table (chart aYs82), itself built from KFF's 2026 parent-eligibility
# tracker. Keyed by state FIPS. Non-expansion states are included for completeness
# but are not used (the work requirement only touches expansion states).
SECTION_1931_PARENT_THRESHOLD_PCT_FPL = {
    "01": 18,  "02": 121, "04": 106, "05": 12,  "06": 109, "08": 68,  "09": 138,
    "10": 87,  "11": 138, "12": 26,  "13": 29,  "15": 105, "16": 16,  "17": 33,
    "18": 13,  "19": 39,  "20": 38,  "21": 15,  "22": 19,  "23": 100, "24": 123,
    "25": 138, "26": 54,  "27": 138, "28": 22,  "29": 13,  "30": 24,  "31": 58,
    "32": 22,  "33": 43,  "34": 22,  "35": 34,  "36": 67,  "37": 30,  "38": 39,
    "39": 90,  "40": 30,  "41": 27,  "42": 33,  "44": 116, "45": 67,  "46": 37,
    "47": 105, "48": 15,  "49": 30,  "50": 33,  "51": 33,  "53": 36,  "54": 14,
    "55": 100, "56": 44,
}
SECTION_1931_SOURCE = (
    "Georgetown CCF, 'Which Parents Will Be Impacted by the Medicaid Work "
    "Reporting Mandate' (2026-04-02), Section 1931 parent eligibility table "
    "(Datawrapper aYs82), built from KFF 2026 parent-eligibility tracker."
)

# --- Immigration-status refinement -----------------------------------------
# The federal work requirement applies to ACA-expansion adults, who must be
# citizens or qualified non-citizens past the 5-year bar. PUMS can't see
# immigration status precisely, but it does carry CIT (citizenship) and YOEP
# (year of entry). We conservatively exclude only non-citizens (CIT == 5) who
# entered within the last RECENT_IMMIGRANT_YEARS_BAR years — the slice most
# likely to be either undocumented or inside the 5-year bar, and most likely
# (when enrolled in "Medicaid" in ACS) to be in emergency-Medicaid or
# state-funded coverage that the federal expansion work requirement doesn't
# reach. Long-resident LPRs, refugees, and naturalized citizens are kept.
# This is a floor, not a precise eligibility screen; see METHODOLOGY §3.7.
PUMS_CITIZEN_NONCITIZEN_CODE = 5     # CIT == 5 → "not a U.S. citizen"
RECENT_IMMIGRANT_YEARS_BAR = 5       # entered within this many years → excluded
PUMS_SURVEY_END_YEAR = 2024          # ACS 5-Year 2020-2024 reference end

# --- Ex parte capability scoring weights (v8) ------------------------------
# v8 reworks the composite per Esty: the state's OBSERVED ex parte renewal rate
# (CMS unwinding data, 2023-2026) becomes the dominant factor, since it directly
# measures realized auto-renewal capability rather than the v5 vendor-tier proxy.
# Data-sources (the work-req-specific feeds) is secondary; documented prior
# Section 1115 work-requirement churn (AR, NH, KY, GA) is the minor adjustment.
# The legacy vendor-tier "core capability" score is retained as a displayed
# context sub-metric but no longer feeds the composite.
EX_PARTE_WEIGHTS = {
    "observed_ex_parte": 0.50,
    "data_sources": 0.35,
    "historical_churn": 0.15,
}
# National observed ex parte renewal rate — fallback for any state missing from
# state_current_ex_parte.json. Source: CMS PI data 2023-03 to 2026-02.
OBSERVED_EX_PARTE_NATIONAL_FALLBACK = 0.666

# ---------------------------------------------------------------------------
# Cross-cycle compounding factor (v7)
# ---------------------------------------------------------------------------
# OBBBA has 6-month renewal cycles. By the CBO horizon of 2034 there are 14
# cycles. Our per-(state, subgroup) bottom-up math is a single-cycle snapshot;
# CBO's 5.2M cumulative incorporates some accumulation: people who lose
# coverage re-enroll and may fail again on a later cycle. The compounding
# factor scales the single-cycle documentation-failure totals to a cumulative
# 2034 figure.
#
# Derivation: 14 cycles × ~30% per-cycle procedural denial × ~70% re-enrollment
# fraction × geometric decay (each re-enrolled cohort is smaller than the
# previous) ≈ 1.15× of single-cycle gross losses. This is applied to
# documentation-failure buckets only (workdoc + exemption-doc); the
# genuinely-noncompliant residual is already a steady-state count, not a
# per-cycle flow.
CYCLE_COMPOUNDING_FACTOR = 1.15

# State-discretion lever assumptions (used to build strict vs permissive bands)
STRICT_BAND = {
    # No state requests hardship exceptions; no short-term hardships granted.
    "high_unemployment_exception_active": False,
    "short_term_hardship_rate": 0.0,
}
PERMISSIVE_BAND = {
    # All adopting states get hardship exceptions for all qualifying counties;
    # short-term hardships catch 2% of enrollees.
    "high_unemployment_exception_active": True,
    "short_term_hardship_rate": 0.02,
}

# ---------------------------------------------------------------------------
# High-unemployment hardship exception (KFF May 2026 analysis)
# ---------------------------------------------------------------------------
HARDSHIP_UNEMPLOYMENT_THRESHOLDS = {
    "absolute_pct": 0.08,         # 8% county unemployment
    "ratio_to_national": 1.5,     # OR 1.5× national average
    "lookback_months": 12,
}

# ---------------------------------------------------------------------------
# Burden index
# ---------------------------------------------------------------------------
# Composite verification-difficulty score, 0-100 scale, centered on national
# median. See METHODOLOGY.md §5 for component rationale.
BURDEN_INDEX_WEIGHTS = {
    "verification_difficulty": 0.4,
    "labor_volatility": 0.3,
    "access_gap": 0.3,
}

# ---------------------------------------------------------------------------
# Loss-exposure mode
# ---------------------------------------------------------------------------
# CBO assumes ~30% of subject enrollees lose coverage through admin churn.
# This is the default for the loss_exposure render mode. The methodology
# accordion documents this with a slider in v2 to let users model alternatives.
LOSS_EXPOSURE_CHURN_RATE = 0.30

# ---------------------------------------------------------------------------
# Loss-breakdown (stages 04b/04c/04d/07b)
# ---------------------------------------------------------------------------
# v5: bottom-up — no rake. Each state's loss is computed per-(subgroup) from
# subject pool × failure-rate model, then summed. A single global calibration
# multiplier is applied ONLY if the bottom-up total falls outside the
# defensible range bracketing CBO 5.2M (June 2025 OBBBA scoring) and the
# Urban HIPSM / CBPP upper estimates (7.5M-10M depending on state
# implementation lag). If applied, the multiplier is uniform across states
# and subgroups so the geographic and category-level shape is preserved.
LOSS_BREAKDOWN_REFERENCE = {
    "cbo_baseline_2034": 5_200_000,    # CBO June 2025 OBBBA score
    "urban_midpoint_2034": 7_500_000,  # Urban Institute HIPSM
    "cbpp_upper_2034": 10_000_000,     # CBPP if state implementation lags
    # If bottom-up total lands in this range, no calibration is applied:
    "acceptable_range_low": 4_500_000,
    "acceptable_range_high": 11_000_000,
    # If calibration is applied, this is the target (CBO + Urban midpoint):
    "calibration_target": 6_400_000,
}

# v4 back-compat: legacy 45/45/10 rake targets retained as documentation but
# NO LONGER USED by stage 07b (the rake was dropped per Esty v5 review). Kept
# here because METHODOLOGY.md still references them as historical context.
LOSS_BREAKDOWN_TARGETS = {
    "total_loss_2034": 5_200_000,
    "noncompliant_share": 0.10,
    "workdoc_share": 0.45,
    "exemption_share": 0.45,
}

# NAICS code lists used by stage 04b in full-PUMS mode. Documented here so the
# pipeline parameter set is centrally referenced; the actual classification
# logic lives in 04b_fetch_pums_workdoc_breakdown.py.
PUMS_NAICS_CODES = {
    "gig_courier_indp": [7280, 6190],
    "construction_indp_range": (770, 799),
    "agriculture_indp_range": (170, 290),
    "food_service_indp_range": (8660, 8690),
}
PUMS_OCCP_DRIVER_DELIVERY = [9130, 9140, 9560]
PUMS_COW_SELF_EMPLOYED = [6, 7]

# ---------------------------------------------------------------------------
# Display thresholds
# ---------------------------------------------------------------------------
# Disclosure-avoidance + statistical-confidence rules
MIN_DISPLAY_N = 50              # Suppress cells with subject_count < 50 in count modes
CV_HATCH_THRESHOLD = 0.40       # Cells with CV > this render hatched
CV_HIDE_THRESHOLD = 1.00        # Cells with CV > this hidden behind toggle

# ---------------------------------------------------------------------------
# Cross-validation benchmarks
# ---------------------------------------------------------------------------
# Target ranges from V0 verification research (2026-05-22).
# Our pipeline must rake to within these tolerances or stage 11 fails.
CROSS_VALIDATION_TARGETS = {
    "cbo_national_subject_2027": 18_500_000,         # CBO scoring of OBBBA
    "cbo_national_loss_2034": 5_200_000,             # CBO work-req-only loss
    "cbo_national_uninsured_2034": 4_800_000,        # CBO
    "urban_national_loss_2028_high_mitigation": 4_900_000,   # Urban HIPSM March 2026
    "urban_national_loss_2028_low_mitigation": 10_100_000,
    "urban_state_ca_loss_low": 1_000_000,
    "urban_state_ca_loss_high": 1_200_000,
    "urban_state_ny_loss_low": 743_000,
    "urban_state_ny_loss_high": 846_000,
}
TOLERANCE_NATIONAL = 0.10
TOLERANCE_STATE = 0.15
TOLERANCE_COUNTY = 0.20

# ---------------------------------------------------------------------------
# R2 hosting
# ---------------------------------------------------------------------------
# We share the gizmo-warehouse-data bucket with the NYC Tax Map gizmo. New
# prefix here. CDN custom domain documented in tools/HOSTING_DATA.md.
R2_BUCKET = "gizmo-warehouse-data"
R2_PREFIX = "medicaid-work-requirements"
R2_PUBLIC_BASE = f"https://data.gizmowarehouse.org/{R2_PREFIX}"

# ---------------------------------------------------------------------------
# Render mode color stops
# ---------------------------------------------------------------------------
# Centralized so the frontend can read these via a JSON export if we want
# the modes to evolve without a code change. For now they're duplicated
# in src/config/medicaidWorkRequirementsMap.ts — keep in sync.
RENDER_MODE_STOPS = {
    "subject_count_county": [
        [0,       "#F2F2F2"],
        [1_000,   "#D6E4F2"],
        [10_000,  "#7B9BE0"],
        [50_000,  "#1F1FD6"],
        [200_000, "#0A0A8A"],
    ],
    "subject_count_grid": [
        [0,      "#F2F2F2"],
        [100,    "#D6E4F2"],
        [1_000,  "#7B9BE0"],
        [5_000,  "#1F1FD6"],
        [20_000, "#0A0A8A"],
    ],
    "subject_rate": [
        [0.00, "#F2F2F2"],
        [0.02, "#D6E4F2"],
        [0.05, "#7B9BE0"],
        [0.10, "#1F1FD6"],
        [0.20, "#0A0A8A"],
    ],
    "burden_index": [  # diverging, centered at national median
        [-30, "#1F1FD6"],
        [-10, "#7B9BE0"],
        [-5,  "#D6E4F2"],
        [0,   "#F2F2F2"],
        [5,   "#F2D9A8"],
        [15,  "#E69138"],
        [30,  "#B45309"],
    ],
    "loss_exposure": [
        [0,      "#F2F2F2"],
        [300,    "#A7D9CE"],
        [3_000,  "#5BB1A1"],
        [15_000, "#21A8E0"],
        [60_000, "#0A4A40"],
    ],
}

# ---------------------------------------------------------------------------
# Version stamp
# ---------------------------------------------------------------------------
DATA_VERSION_JSON = PUBLIC_DATA_DIR / "medicaid-work-requirements-version.json"


def stamp_version(payload: dict) -> None:
    DATA_VERSION_JSON.write_text(json.dumps(payload, indent=2))


def load_version() -> dict | None:
    if DATA_VERSION_JSON.exists():
        return json.loads(DATA_VERSION_JSON.read_text())
    return None
