"""Centralized config for the Public-Sector Pay Gap pipeline.

Every parameter, series ID, occupation code, deflator choice, and published
benchmark lives here with a citation. If you find a magic number elsewhere in
the pipeline, it's a bug — move it here with a source.

See APPENDIX.md for the "why" behind every value. All API contracts below were
verified live against the source APIs on 2026-06-17 before being written down.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent
RAW_DIR = PIPELINE_DIR / "raw"
OUTPUT_DIR = PIPELINE_DIR / "output"
GIZMO_DIR = PIPELINE_DIR.parent
CROSSWALK_DIR = GIZMO_DIR / "crosswalks"
REPO_ROOT = GIZMO_DIR.parent.parent
PUBLIC_DATA_DIR = REPO_ROOT / "public" / "data" / "compgap"
PUBLIC_LOCALITIES_DIR = PUBLIC_DATA_DIR / "localities"

for d in (RAW_DIR, OUTPUT_DIR, CROSSWALK_DIR, PUBLIC_DATA_DIR, PUBLIC_LOCALITIES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Credentials (read from repo-root .env.local, same as the Medicaid pipeline)
# ---------------------------------------------------------------------------
def _load_env() -> None:
    env = REPO_ROOT / ".env.local"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env()
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")

# ---------------------------------------------------------------------------
# ACS PUMS configuration (the workhorse microdata — Census API, no IPUMS needed
# for the modern series). 1-year PUMS person files.
#   Endpoint: https://api.census.gov/data/{YEAR}/acs/acs1/pums
# The Census microdata API serves real person records: we compute weighted
# wage distributions and the public-vs-private gap locally.
# 2020 ACS 1-year was NOT released as standard (COVID data-collection failure) —
# skip it. Earliest 1-year PUMS via the API is 2005.
# ---------------------------------------------------------------------------
PUMS_BASE = "https://api.census.gov/data/{year}/acs/acs1/pums"
# First-iteration trend years (5 evenly-spaced points). The full annual set
# (every year 2005-2023 except 2020) is a later refinement; 5 points establish the
# trend cleanly while bounding ~255 state-year API calls. 2020 has no standard
# 1-year ACS (COVID). SOCP is present every year (verified 2026-06-17), so the
# domain trend uses SOCP throughout, mapped at the SOC major/minor level (robust
# to the 2000->2010->2018 SOC-vintage shifts; detailed codes are not spliced).
PUMS_YEARS = [2005, 2010, 2015, 2019, 2023]
PUMS_LATEST_YEAR = 2023  # the cross-section year
PUMS_SKIP_YEARS = {2020}  # no standard 1-year ACS for 2020

# 50 states + DC (FIPS 11). PR (72) excluded — different labor market + PUMS frame.
STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}
ALL_STATE_FIPS = list(STATE_FIPS.keys())


def pums_vars_for_year(year: int) -> list[str]:
    """Per-year variable list — some vars don't exist in every vintage."""
    base = ["PWGTP", "WAGP", "COW", "SOCP", "SCHL", "AGEP", "WKHP", "ESR", "SEX", "RAC1P"]
    base.append("WKWN" if year >= 2019 else "WKW")
    if year >= 2010:
        base.append("ADJINC")
    return base

# Person-level variables we pull. (PWGTP = person weight; replicate weights
# PWGTP1..80 give design-correct standard errors.)
PUMS_VARS = [
    "PWGTP",   # person weight
    "WAGP",    # wages/salary income, past 12 months
    "PERNP",   # total earnings (wages + self-emp) — for robustness only
    "COW",     # class of worker (see PUMS_COW below)
    "SOCP",    # occupation, 2018 SOC (6-char; "N" when not in labor force)
    "SCHL",    # educational attainment
    "AGEP",    # age
    "WKHP",    # usual hours worked per week
    "WKWN",    # weeks worked past 12 months (2019+; WKW bins pre-2019)
    "WKW",     # weeks-worked recode (bins) — pre-2019 fallback
    "ESR",     # employment status recode
    "ADJINC",  # income inflation adjustment to constant ACS dollars (6 implied decimals)
    "SEX",
    "RAC1P",
]

# PUMS class-of-worker (COW) codes. This is the verification-confirmed lever for
# "public vs private" — it splits the three government tiers cleanly, which NAICS
# industry does not. Self-employed (6,7) and unpaid (8) excluded from the
# public/private comparison.
PUMS_COW = {
    "1": "private_fp",   # private for-profit (employee)
    "2": "private_np",   # private not-for-profit
    "3": "local",        # local government
    "4": "state",        # state government
    "5": "federal",      # federal government
    "6": "self_emp",     # self-employed, not incorporated
    "7": "self_emp",     # self-employed, incorporated
    "8": "unpaid",       # working without pay in family business
    "9": "unemployed",   # unemployed, last worked 5+ yrs ago / never
}
# Which COW codes count as "public" / "private" for the headline binary.
COW_PUBLIC = {"3", "4", "5"}
COW_PRIVATE = {"1", "2"}

# Sample restrictions — the consensus human-capital cell (CBO / Biggs-Richwine / EPI).
AGE_MIN, AGE_MAX = 25, 64
MIN_HOURS_FT = 35          # full-time
MIN_WEEKS_FY = 50          # full-year (WKWN >= 50, or WKW bin 1)
MIN_ANNUAL_WAGE = 1        # positive wages
PERCENTILES = [50, 75, 90]  # p95 computed economy-wide only (macro overlay)
MACRO_PERCENTILES = [50, 90, 95]  # economy-wide overlay; top-coding caps above ~p97

# ---------------------------------------------------------------------------
# Deflator — real wages.
# Recommended: CPI-U-RS for the long historical splice. For the modern PUMS
# window (2005+), CPI-U-RS and CPI-U are methodologically converged, so we use
# CPI-U annual average (FRED CPIAUCSL -> annual mean), which is cleanly
# fetchable, and pin CPI-U-RS as the documented choice for any pre-2005 splice.
# Base year for constant dollars:
# ---------------------------------------------------------------------------
DEFLATOR_FRED_ID = "CPIAUCSL"   # CPI-U, all items, monthly SA
# Wages are expressed in constant dollars of the LATEST available CPI month (a
# 2026 month) so the figures read in present-day money. Each survey year's wage is
# deflated by cpi_target / cpi_annual[year]. DOLLAR_YEAR is just the display label.
DOLLAR_YEAR = 2026
BASE_YEAR = DOLLAR_YEAR  # kept for back-compat references
DEFLATOR_NOTE = (
    "Real wages in constant 2026 dollars: each year's wage deflated by CPI-U to the "
    "latest available month (FRED CPIAUCSL). CPI-U-RS is the documented choice for any "
    "pre-2005 splice; over 2005-2023 CPI-U and CPI-U-RS are methodologically converged."
)

# ---------------------------------------------------------------------------
# BLS Employment Cost Index (ECI) — index levels, base Dec 2005 = 100.
# Verified live 2026-06-17 against FRED ECIALLCIV (civilian total comp = 84.7 @2001Q1).
# ID structure: CIU + owner(1=civilian,2=private,3=state&local) + estimate
#   (01=total comp, 02=wages&salaries, 03=benefits) + 0000000000 + I (index).
# Caveat: this constant-NAICS series starts 2001Q1; ECI state&local exists back to
# 1981 under the older SIC program (a chained break) — flag, don't silently splice.
# ---------------------------------------------------------------------------
BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_API_KEY = os.environ.get("BLS_API_KEY", "")  # optional; raises daily limit
ECI_SERIES = {
    "civilian_totalcomp": "CIU1010000000000I",
    "private_totalcomp": "CIU2010000000000I",
    "stlocal_totalcomp": "CIU3010000000000I",
    "private_wages": "CIU2020000000000I",
    "stlocal_wages": "CIU3020000000000I",
    "private_benefits": "CIU2030000000000I",
    "stlocal_benefits": "CIU3030000000000I",
}
ECI_START_YEAR = 2001

# ---------------------------------------------------------------------------
# FRED series (CSV, no key). Verified live 2026-06-17.
# ---------------------------------------------------------------------------
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
FRED_SERIES = {
    # Median usual weekly real earnings, full-time wage/salary, 1979+ (1982-84$).
    "median_real_weekly_earnings": "LES1252881600Q",
    # BEA NIPA: compensation per FTE, federal general government (civilian), 1998+.
    "federal_comp_per_fte": "B4479C0A052NBEA",
    # ECI civilian total comp index (sanity cross-check vs BLS).
    "eci_civilian_index": "ECIALLCIV",
    # CES government employment (thousands), monthly, 1939+ — the long shape trend.
    "emp_federal": "CES9091000001",
    "emp_state": "CES9092000001",
    "emp_local": "CES9093000001",
    "emp_government_total": "USGOVT",
    "emp_total_nonfarm": "PAYEMS",
    # Deflator.
    "cpi_u": DEFLATOR_FRED_ID,
}

# ---------------------------------------------------------------------------
# Census ASPEP "govsemp" timeseries — state & local FTE + payroll by function.
# Verified live: GOVTYPE 001=all state&local, 002=state, 003=local;
# AGG_DESC EP0005=total (all functions); TOT_PAY is the March monthly payroll ($).
# Federal is NOT in this series after 2014 (Census directs to OPM) -> federal
# headcount comes from CES (emp_federal) and federal pay from BEA.
# ---------------------------------------------------------------------------
GOVSEMP_API = "https://api.census.gov/data/timeseries/govsemp"
GOVSEMP_YEAR = 2022
GOVTYPE = {"001": "state_and_local", "002": "state", "003": "local"}
GOVSEMP_TOTAL_AGG = "EP0005"

# ---------------------------------------------------------------------------
# OEWS by-ownership (cross-sectional p90 tail PUMS top-coding suppresses).
# National files: 000001 = private cross-industry; 999001 = govt (fed+state+local).
# CAVEAT (verified): govt-owned schools/hospitals are scored into PRIVATE NAICS,
# so OEWS-by-ownership UNDERCOUNTS public teachers/nurses — use OEWS only for
# software/legal/finance/engineering; PUMS handles education/health. OEWS is
# wages (not total comp) and BLS discourages it as a time series -> point-in-time
# only. Pulled from the OEWS research files in stage 07.
# ---------------------------------------------------------------------------
OEWS_OWNERSHIP = {"private": "000001", "government": "999001"}
OEWS_SCHOOL_HOSPITAL_EXCLUDED_DOMAINS = {"healthcare", "education"}

# ---------------------------------------------------------------------------
# Published benchmarks — citation-backed constants for cross-validation and the
# narrative anchors. These are PUBLISHED figures with sources, not estimates.
# ---------------------------------------------------------------------------
# CBO, "Comparing the Compensation of Federal and Private-Sector Employees,
# 2022" (April 2024). Federal TOTAL COMPENSATION premium vs private, by education.
# The load-bearing anchor for the "elite lag" thesis: the federal advantage
# reverses and goes negative at the advanced-degree tail.
# https://www.cbo.gov/publication/59970
CBO_2024_FEDERAL_TOTALCOMP_PREMIUM = {
    "high_school_or_less": 0.40,
    "some_college": 0.38,
    "bachelors": 0.05,
    "masters": -0.04,
    "professional_or_doctorate": -0.22,
    "overall": 0.05,
}
CBO_CITATION = (
    "CBO, Comparing the Compensation of Federal and Private-Sector Employees, "
    "2022 (April 2024). https://www.cbo.gov/publication/59970"
)

# Biggs & Richwine composition-adjusted wage premia by level of government — the
# "premium pole" of the methodology debate; shows fed/state/local have OPPOSITE
# signs, which is why we never collapse them into one "public" bucket.
# (Andrew Biggs & Jason Richwine, AEI.) Used as a modeling cross-check, not ours.
BIGGS_RICHWINE_PREMIA = {"federal": 0.141, "state": -0.137, "local": -0.064}

# BLS Employer Costs for Employee Compensation (ECEC). Published $/hr levels +
# benefit shares, private vs state-and-local government. (December 2025 release.)
# https://www.bls.gov/news.release/ecec.htm  -- hardcoded constant (no pipeline
# stage fetches ECEC; pin the exact release vintage here when updating).
ECEC_TOTALCOMP_PER_HR = {"state_and_local": 65.68, "private": 46.15}
ECEC_BENEFIT_SHARE = {"state_and_local": 0.383, "private": 0.299}

# Teachers dominate the public workforce and lack a clean private comparator, so the
# headline public-vs-private charts exclude them by default. "Teacher" here = the
# education-instruction occupation group (SOC 25). Published framing constants:
#   NCES Common Core of Data 2023-24: ~3.25M FTE public K-12 teachers.
#   BLS CES / Census ASPEP 2024: local-government education ~7.6M of ~14.6M local
#   workers (~52%) — "roughly half of local government is public education."
TEACHER_DOMAIN = "education"        # is_teacher when SOCP maps to this domain (SOC 25)
NCES_PUBLIC_K12_TEACHERS_M = 3.25   # millions, NCES CCD 2023-24
LOCAL_GOV_EDUCATION_SHARE = 0.52    # BLS CES / Census ASPEP 2024

# ---------------------------------------------------------------------------
# City payroll sources (note 13). Each city's individual-employee file, pulled
# via the Socrata SODA API. We standardise on "annual base/regular cash pay for
# full-time employees." Column names + filters verified live 2026-06-17.
#   pay_kind: "annual" = pay_col is already annual; "hourly" = multiply by 2080.
#   where: SoQL filter applied server-side to isolate full-time salaried rows.
#   year_col: pick the latest year present (None = file is "current").
# The private comparator is the city's own METRO (central county/counties) PUMS
# private median by domain, built in stage 08b (metro_private.json) from the
# crosswalks/city_to_puma.csv PUMAs and consumed by 08c. This compares e.g. SF
# government to Bay Area private, not all of California. (Earlier versions used a
# same-STATE comparator, which understated the gap in high-cost metros.)
# ---------------------------------------------------------------------------
CITY_SOURCES = [
    {"key": "nyc", "name": "New York City", "state": "NY",
     "domain": "data.cityofnewyork.us", "dataset": "k397-673e",
     "title_col": "title_description", "pay_col": "base_salary", "pay_kind": "annual",
     "year_col": "fiscal_year", "year_text": True,
     "where": "pay_basis='per Annum' AND leave_status_as_of_june_30='ACTIVE'"},
    {"key": "chicago", "name": "Chicago", "state": "IL",
     "domain": "data.cityofchicago.org", "dataset": "xzkq-xp2w",
     "title_col": "job_titles", "pay_col": "annual_salary", "pay_kind": "annual",
     "year_col": None,
     "where": "salary_or_hourly='SALARY' AND full_or_part_time='F'"},
    {"key": "sf", "name": "San Francisco", "state": "CA",
     "domain": "data.sfgov.org", "dataset": "88g8-5mnd",
     "title_col": "job", "pay_col": "salaries", "pay_kind": "annual",
     "year_col": "year", "year_text": True, "where": "year_type='Fiscal'"},
    {"key": "seattle", "name": "Seattle", "state": "WA",
     "domain": "data.seattle.gov", "dataset": "2khk-5ukd",
     "title_col": "job_title", "pay_col": "hourly_rate", "pay_kind": "hourly",
     "year_col": None, "where": "hourly_rate > 20"},
    {"key": "la", "name": "Los Angeles", "state": "CA",
     "domain": "controllerdata.lacity.org", "dataset": "g9h8-fvhu",
     "title_col": "job_title", "pay_col": "regular_pay", "pay_kind": "annual",
     "year_col": "pay_year", "where": "employment_type='FULL_TIME'"},
]
CITY_DATA_YEAR_DEFAULT = 2024     # for deflating "current" city files lacking a year
CITY_MAX_COMPLETE_YEAR = 2025     # never use the in-progress current year (partial YTD pay)

SCHEMA_VERSION = "2.0"
