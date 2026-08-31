"""Configuration for the data-center-restriction-cost pipeline.

Python 3 stdlib only. All paths are derived from this file's location so the
pipeline can run from any working directory.
"""
from __future__ import annotations

import pathlib
import socket
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------
SNAPSHOT_DATE = "2026-08-15"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PIPELINE_DIR = pathlib.Path(__file__).resolve().parent
RAW_DIR = PIPELINE_DIR / "raw"
GIZMO_DIR = PIPELINE_DIR.parent                       # gizmos/data-center-restriction-cost
REPO_ROOT = GIZMO_DIR.parent.parent                   # repo root
OUT_DIR = REPO_ROOT / "public" / "data" / "data-center-restriction-cost"
ASSETS_CSV = REPO_ROOT / "public" / "assets" / "data-center-restriction-cost-actions.csv"
OUTCOMES_ASSETS_CSV = REPO_ROOT / "public" / "assets" / "data-center-restriction-cost-outcomes.csv"

COUNTIES_GEOJSON = REPO_ROOT / "public" / "data" / "medicaid-counties.geojson"
US_STATES_GEOJSON = REPO_ROOT / "public" / "data" / "us-states.geojson"

STATE_ACTIONS_CSV = PIPELINE_DIR / "state_actions.csv"
TARIFF_LAYER_CSV = PIPELINE_DIR / "tariff_layer.csv"
MANUAL_COORDS_CSV = PIPELINE_DIR / "manual_coords.csv"
OUTCOMES_CSV = PIPELINE_DIR / "outcomes.csv"

ACTIONS_JSON = OUT_DIR / "actions.json"
OUTCOMES_JSON = OUT_DIR / "outcomes.json"
BENCHMARKS_JSON = OUT_DIR / "benchmarks.json"

# Raw / intermediate files
MN_RAW_CSV = RAW_DIR / "moratorium_inventory.csv"
MN_DC_ROWS_CSV = RAW_DIR / "mn_dc_rows.csv"
DCT_RAW_JSON = RAW_DIR / "dct_fights.json"
DCT_STATUS_JSON = RAW_DIR / "dct_status.json"
DCT_SPOTCHECK_CSV = RAW_DIR / "dct-spotcheck-sample.csv"
GAZ_PLACE_ZIP = RAW_DIR / "2024_Gaz_place_national.zip"
BUILD_LOG_JSON = RAW_DIR / "build_actions_log.json"
WORKFLOW_TRACE_JSON = RAW_DIR / "workflow_traced_projects.json"

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
# Moratorium Nation (ALEA Institute), CC-BY-4.0. The raw.githubusercontent URL
# is the canonical direct download (verified 2026-08-08); the index page and
# GitHub tree API are discovery fallbacks.
MN_CSV_CANONICAL = (
    "https://raw.githubusercontent.com/mjbommar/moratorium-data-2026/"
    "main/data/moratorium_inventory.csv"
)
MN_INDEX_URL = "https://mjbommar.github.io/moratorium-data-2026/index.html"
MN_SITE_BASE = "https://mjbommar.github.io/moratorium-data-2026/"
MN_GH_TREE_URL = (
    "https://api.github.com/repos/mjbommar/moratorium-data-2026/git/trees/main?recursive=1"
)
MN_GH_RAW_BASE = "https://raw.githubusercontent.com/mjbommar/moratorium-data-2026/main/"
MN_SOURCE_NAME = "Moratorium Nation (ALEA Institute)"
MN_LICENSE = "CC-BY-4.0"
# Published data-center-specific adoption count since 2023 (7+6+59+294),
# per the tracker's own July 31, 2026 release notes. The sector-filtered CSV
# row count is higher (~505) because it includes multi-sector instruments and
# pending/unverified rows; see DECISIONS.md.
MN_PUBLISHED_DC_TOTAL = 366
# QA gates on the sector-filtered row count
MN_DC_MIN_ROWS = 330      # hard fail below this
MN_DC_WARN_ROWS = 460     # warn above this

# datacentertracker.org (Cam Acosta, George Ingebretsen), CC BY 4.0.
# The site's CSV/JSON download buttons are client-side blobs of this file;
# there is no static CSV endpoint (verified 2026-08-08).
DCT_HOME_URL = "https://datacentertracker.org/"
DCT_FIGHTS_URL = "https://datacentertracker.org/data/fights.json"
DCT_SOURCE_NAME = "datacentertracker.org"
DCT_LICENSE = "CC-BY-4.0"

# Census 2024 national places gazetteer. NOTE: the directory is singular
# ("2024_Gazetteer"); the plural form 404s. www2.census.gov can hang over
# IPv6 from some hosts — http_get() below prefers IPv4 for this reason.
GAZ_PLACE_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_place_national.zip"
)

# ---------------------------------------------------------------------------
# EEI large-load tariff tracker — ATTRIBUTED counts, not per-state rows.
# "As of July 2026, 24 states have approved at least one large load tariff,
# and another 6 states have pending large load tariffs." (verified verbatim,
# tracker updated July 17, 2026). The per-state split is not published by EEI;
# we therefore carry only the counts, attributed, and never fabricate rows.
# ---------------------------------------------------------------------------
EEI_TARIFF_APPROVED = 24
EEI_TARIFF_PENDING = 6
EEI_VINTAGE = "EEI, July 2026"

# ---------------------------------------------------------------------------
# Frozen output enums (from the hand-written sample files; see DECISIONS.md
# for the sanctioned additions).
# ---------------------------------------------------------------------------
VALID_LEVELS = {"local", "state", "puc"}
VALID_CLASSES = {"restriction", "condition", "preemption"}
# "expired" = no longer operative with nothing in its place (expired or
# rescinded); "replaced" = superseded by a successor instrument (the
# jurisdiction usually still restricts). Split per Joe's ruling, 2026-08-09.
VALID_STATUSES = {"enacted", "in_force", "vetoed", "pending", "expired", "replaced"}

# County friction layer (map redesign, 2026-08-09).
COUNTIES_OUT_JSON = OUT_DIR / "counties.geojson"
EPRI_RAW_JSON = RAW_DIR / "epri_state_dashboard.json"
VALID_COUNTY_CATEGORIES = {"county_restriction", "town_restriction", "conditions_only",
                           "pending_only", "lapsed_only"}
COUNTY_ASSIGN_MISS_MAX = 5   # hard gate; Anchorage (no AK polygons) is the accepted miss
COUNTIES_MAX_BYTES = 700_000
COUNTIES_WARN_BYTES = 600_000
VALID_ACTION_TYPES = {
    "moratorium", "ban", "ordinance_conditions", "zoning_exclusion",
    "project_rejection", "referendum", "executive_order", "ratepayer_law",
    "tax_action", "incentive_rollback", "large_load_tariff", "preemption",
}
VALID_JURISDICTION_TYPES = {"state", "county", "municipality", "utility", "tribal"}
VALID_GEOCODE = {"manual", "source_dataset", "place_gazetteer", "county_centroid", "none"}
VALID_OUTCOMES = {"died", "rerouted", "delayed_then_built", "pending_litigating"}
VALID_STATE_STATUS = {
    "enacted_restriction", "enacted_conditions", "incentive_rollback",
    "preemption", "none",
}

# ---------------------------------------------------------------------------
# HTTP helper (stdlib only, IPv4-preferring, one retry)
# ---------------------------------------------------------------------------
_USER_AGENT = "gizmo-warehouse-pipeline/1.0 (joe@group17a.com; stdlib urllib)"


def _ipv4_first(host, port, family=0, type=0, proto=0, flags=0):
    """getaddrinfo wrapper that sorts IPv4 results first (census IPv6 hangs)."""
    res = socket._orig_getaddrinfo(host, port, family, type, proto, flags)
    return sorted(res, key=lambda ai: 0 if ai[0] == socket.AF_INET else 1)


if not hasattr(socket, "_orig_getaddrinfo"):
    socket._orig_getaddrinfo = socket.getaddrinfo
    socket.getaddrinfo = _ipv4_first


def http_get(url: str, timeout: int = 120, retries: int = 1) -> bytes:
    """GET a URL, returning body bytes. One retry by default, then raises."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as err:  # noqa: PERF203
            last_err = err
            if attempt < retries:
                time.sleep(3)
    raise RuntimeError(f"fetch failed after {retries + 1} attempts: {url}: {last_err}")


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_CSV.parent.mkdir(parents=True, exist_ok=True)
