"""Centralized config for the self-insurance-cost pipeline.

Every path, source URL, account code, enum, and pinned value lives here with a
citation. If a magic number appears elsewhere in the pipeline, it is a bug.

Sources verified live on 2026-10-08 (see DECISIONS.md and SCOPING.md).
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
SLUG = "self-insurance-cost"
PUBLIC_DATA_DIR = REPO_ROOT / "public" / "data" / SLUG
ASSETS_DIR = REPO_ROOT / "public" / "assets"

RAW_OSC = RAW_DIR / "osc"
RAW_NTD = RAW_DIR / "ntd"
RAW_ACFR = RAW_DIR / "acfr"
RAW_MANIFEST = RAW_DIR / "manifest.json"


def ensure_dirs() -> None:
    for d in (RAW_OSC, RAW_NTD, RAW_ACFR, OUTPUT_DIR, CROSSWALK_DIR, PUBLIC_DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Credentials (repo-root .env.local; none are required)
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
SOCRATA_APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "")
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")

# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------
SNAPSHOT_DATE = "2026-10-08"  # bump on every refetch; the as-of header and the CSV headers carry it

# ---------------------------------------------------------------------------
# New York State Comptroller — account-level local government finance data
# https://wwe1.osc.state.ny.us/localgov/findata/financial-data-for-local-governments.cfm
# Bulk zip per class, one CSV per fiscal year, 1995/96–2026. Class names below
# are the real file names (the web form's own radio values differ; see DECISIONS.md).
# ---------------------------------------------------------------------------
OSC_ZIP_URL = "https://wwe1.osc.state.ny.us/localgov/findata/level3zip/{cls}_all_years.zip"
OSC_CLASSES = ["county", "city", "town", "village", "schooldistrict", "firedistrict"]
OSC_CORE_CLASSES = ["county", "city", "town", "village"]  # the headline universe
OSC_CLASS_LABEL = {  # CLASS_DESCRIPTION values as they appear in the files
    "county": "County", "city": "City", "town": "Town", "village": "Village",
    "schooldistrict": "School District", "firedistrict": "Fire District",
}

# Account codes (4-digit body after the fund prefix; object digit follows)
ACCT_INSURANCE = "1910"          # Unallocated Insurance (premiums, pool contributions)
ACCT_JUDGMENTS = "1930"          # Judgments and Claims
ACCT_PROPERTY_LOSS = "1931"      # Property Loss (uninsured property losses)
ACCT_SELF_INS_ADMIN = "1710"     # Self Insurance, Administration (MS / S funds)
ACCT_DUES = "1920"               # Municipal Association Dues (placebo outcome)
ACCT_OTHER_GG = "1989"           # General Government Support, Other (suspected hiding place)
ACCT_LAW = "1420"                # Law department (defense cost sensitivity)
ACCT_POLICE = "3120"
ACCT_JAIL = "3150"
ACCT_HIGHWAY = "5110"
ACCT_WORKERS_COMP = "9040"       # carried separately, out of the headline
ACCT_INTERFUND_TRANSFER = "9901"
GL_CLAIMS_PAYABLE = "686"        # W686 Judgments and Claims Payable (claims liability)
GL_INSURANCE_RESERVE = "863"     # A863 Insurance Reserve
REV_INSURANCE_RECOVERIES = "2680"

# Funds whose 1710 line is self-insurance administration (in practice: county workers'-comp plans)
SELF_INS_ADMIN_FUNDS = {"MS", "S", "CS"}
# The self-insurance / workers'-comp fund family: benefit claims (health, comp) are booked here by some
# entities under 1720 and even 1930, so the operating-fund outcome variant excludes these funds entirely.
SELF_INS_FUND_FAMILY = {"M", "MS", "S", "CS"}

# Entities held out of every estimate until their claim coding is reconciled
# against audited statements (DECISIONS.md, 2026-10-08).
CODED_ELSEWHERE_HOLDOUT = {"County of Suffolk", "County of Erie"}

# Window for the headline decade means and for switcher detection
HEADLINE_YEARS = (2015, 2024)
PANEL_YEARS = (1996, 2024)

# Deflator: CPI-U all items (FRED CPIAUCSL), rebased to 2024 average
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
CPI_SERIES = "CPIAUCSL"
DEFLATE_TO_YEAR = 2024

# ---------------------------------------------------------------------------
# National Transit Database (DOT open data portal, Socrata)
# ---------------------------------------------------------------------------
SOCRATA_DOMAIN = "https://data.transportation.gov"
NTD_OPEX_BY_TYPE = "j5uj-anzx"   # 2022–2024 Operating Expenses (by Type): casualty_and_liability column
NTD_SERVICE_BY_MODE = "wwdp-t4re"  # 2022–2024 Service (by Mode and Time Period): revenue miles, UPT
NTD_YEARS = ["2022", "2023", "2024"]  # report_year is TEXT in Socrata
NTD_FULL_REPORTER = "Full Reporter"  # 2022-23 files say "Full Reporter: Operating"; match by prefix
NTD_DIRECTLY_OPERATED = "DO"
NTD_LABEL_TOP_N = 100

# ---------------------------------------------------------------------------
# Treatment labels (crosswalks/)
# ---------------------------------------------------------------------------
VALID_STRUCTURES = {
    "self_insured",            # pays primary claims itself (SIR >= $250K or no excess)
    "self_insured_with_excess",
    "pool",                    # public-entity risk pool / reciprocal (NYMIR, NYSIR, CalTIP, WSTIP, OTRP ...)
    "commercial",              # commercial insurer, first-dollar or small deductible
    "mixed",
    "unknown",
}
VALID_LABEL_SOURCES = {"document", "inferred", "unknown"}
NY_LABELS_CSV = CROSSWALK_DIR / "ny_treatment_labels.csv"
POOL_ROSTER_CSV = CROSSWALK_DIR / "ny_pool_rosters.csv"   # NYMIR subscriber list, 2026-07-31
# "Self-insured with excess" with a retention at or below this is a deductible, not self-insurance
# (Schwartz 2016 treats $250K as the floor for self-insurance; we use $100K so $250K retentions count as self-insured).
SELF_INSURED_MIN_SIR = 100_000
NY_WORKLIST_CSV = CROSSWALK_DIR / "ny_acfr_worklist.csv"
NTD_LABELS_CSV = CROSSWALK_DIR / "ntd_treatment_labels.csv"
STATE_CAPS_CSV = CROSSWALK_DIR / "state_tort_caps.csv"
ENTITY_OVERRIDES_CSV = CROSSWALK_DIR / "ny_entity_overrides.csv"

# Signature rule (premium-only; never uses the judgments line)
SIGNATURE_PREMIUM_RATIO = 1 / 3     # real 1910 per capita below this share of the class × size-bin median
SIGNATURE_MIN_YEARS = 4             # in at least this many of the last 5 years
POP_BINS = [0, 2_500, 10_000, 50_000, 150_000, 10**9]

# Gates (set after the first green run; None = record, don't enforce)
LABEL_MIN_ACCURACY = 0.85
MIN_DOC_LABELS = 70              # 57 counties + ~20 cities at M1
ENTITY_BANDS: dict[str, tuple[int, int]] = {   # distinct entities per class in the 2024 file, ±3%
    "county": (55, 59), "city": (55, 60), "town": (845, 905), "village": (480, 520),
}
PIN_YEAR = 2024
# Statewide totals in the 2024 files, from the 2026-10-08 diagnostics (USD, all funds):
PIN_TOTALS = {
    "county": {"insurance": 74.8e6, "judgments": 222.8e6},
    "city": {"insurance": 35.1e6, "judgments": 86.0e6},
    "town": {"insurance": 98.7e6, "judgments": 28.7e6},
    "village": {"insurance": 59.8e6, "judgments": 12.1e6},
}
PIN_TOLERANCE = 0.005
ZERO_COR_WARN_SHARE = 0.15

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
OSC_LONG_PARQUET = OUTPUT_DIR / "osc_long.parquet"
NY_PANEL_PARQUET = OUTPUT_DIR / "ny_panel.parquet"
RISK_NOTE_CANDIDATES_CSV = OUTPUT_DIR / "risk_note_candidates.csv"
LABELS_INFERRED_PARQUET = OUTPUT_DIR / "labels_inferred.parquet"
LABEL_VALIDATION_JSON = OUTPUT_DIR / "label_validation.json"
NTD_PANEL_PARQUET = OUTPUT_DIR / "ntd_panel.parquet"
MODELS_NY_JSON = OUTPUT_DIR / "models_ny.json"
MODELS_NTD_JSON = OUTPUT_DIR / "models_ntd.json"
ATTRIBUTION_JSON = OUTPUT_DIR / "attribution.json"

PUBLIC_JSON = {
    "ny_entities": PUBLIC_DATA_DIR / "ny_entities.json",
    "ny_switchers": PUBLIC_DATA_DIR / "ny_switchers.json",
    "ntd_agencies": PUBLIC_DATA_DIR / "ntd_agencies.json",
    "models": PUBLIC_DATA_DIR / "models.json",
    "attribution": PUBLIC_DATA_DIR / "attribution.json",
}
PUBLIC_JSON_MAX_BYTES = 600_000
ASSET_NY_PANEL_CSV = ASSETS_DIR / f"{SLUG}-ny-panel.csv"
ASSET_NTD_PANEL_CSV = ASSETS_DIR / f"{SLUG}-ntd-panel.csv"
ASSET_LABELS_CSV = ASSETS_DIR / f"{SLUG}-treatment-labels.csv"
ASSET_METHODOLOGY_MD = ASSETS_DIR / f"{SLUG}-methodology.md"
CSV_HEADER_COMMENT = (
    f"# {SLUG} — gizmowarehouse.org — snapshot {SNAPSHOT_DATE} — license CC-BY-4.0 — "
    "sources: NY State Comptroller local government financial data; FTA National Transit Database; "
    "audited financial statements (GASB 10 notes) — questions: joe@group17a.com"
)

PRIMARY_SPEC = "ny_core_classbin_cor_pc"  # document core, class x pop-bin matching, 2015-2024 means
