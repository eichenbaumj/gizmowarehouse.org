"""Single source of paths, codes, thresholds, pins and comparators for the
hoyt-schermerhorn-crime-analysis pipeline. Keep numeric literals on single lines
(verify_claims.py regex-reads them)."""
from __future__ import annotations

from pathlib import Path

SLUG = "hoyt-schermerhorn-crime-analysis"
HERE = Path(__file__).resolve().parent
GIZMO_DIR = HERE.parent
REPO_ROOT = GIZMO_DIR.parent.parent
RAW_DIR = HERE / "raw"
OUT_DIR = HERE / "output"
CACHE_DIR = OUT_DIR / "cache"
CROSSWALKS = HERE / "crosswalks"
PUBLIC_DATA_DIR = REPO_ROOT / "public" / "data" / SLUG
ASSETS_DIR = REPO_ROOT / "public" / "assets"
ASSET_PREFIX = f"{SLUG}-"

# ---- upstream caches (crime-data-pipeline owns these; read-only here) ----------
RAW_NYC = Path.home() / "Downloads" / "crime_data" / "nyc"
RAW_VINTAGE = RAW_NYC / "vintage"
HELD_2025 = RAW_VINTAGE / "2026-09-18-held" / "nyc_raw_2025.csv"
VINTAGE_2026_0731 = RAW_VINTAGE / "2026-07-31" / "nyc_raw_2026.csv"
CRIME_PIPELINE = Path.home() / "Projects" / "crime-data-pipeline"
LATTICE_JSON = CRIME_PIPELINE / "lattices" / "nyc.json"
ASSIGN_PY = CRIME_PIPELINE / "pipeline" / "lattice" / "assign.py"
GRID_CELLS_CSV = CRIME_PIPELINE / "output" / "nyc" / "nyc_grid_cells.csv"
GRID_CELLS_JSON = CRIME_PIPELINE / "output" / "nyc" / "nyc_grid_cells.json"
# NYC Open Data "Police Precincts" (y76i-bdw7, 78 polygons, property `precinct`). The crime-pipeline copy is
# missing the 123rd (Tottenville), so it is only a fallback. Fetch:
#   curl -L -o pipeline/raw/precincts_nyc_open_data/nypp.geojson "https://data.cityofnewyork.us/resource/y76i-bdw7.geojson?$limit=200"
PRECINCTS_GEOJSON = RAW_DIR / "precincts_nyc_open_data" / "nypp.geojson"
PRECINCTS_GEOJSON_FALLBACK = CRIME_PIPELINE / "nyc" / "data" / "nyc_police_precincts.geojson"

SNAPSHOT_DATE = "2026-10-19"
YEARS = list(range(2006, 2027))
PARTIAL_YEAR = 2026
PARTIAL_END = "2026-06-30"
MAIN_2025_RPT_MAX = "2025-12-31"
H1_END_MMDD = "06-30"
BASE_YEARS = (2010, 2019)
RECENT_YEARS = (2024, 2025)
H1_YEARS = (2024, 2025, 2026)

# ---- geometry ----------------------------------------------------------------
STATION_LAT = 40.6885
STATION_LON = -73.9850
CORE_RADII_M = {"core400": 400, "core300": 300, "core500": 500}
PRIMARY_FOOTPRINT = "core400"
BBOX = {"lat0": 40.678, "lat1": 40.699, "lon0": -73.998, "lon1": -73.972}
CELL_ID = "40_42"
CELL_EDGES = {"south": 40.68744654, "north": 40.69222915, "west": -73.99061717, "east": -73.98430822}
N_CELLS = 2854
COURTHOUSE_LAT = 40.690115
COURTHOUSE_LON = -73.989019
COURTHOUSE_MATCH_M = 15
COURTHOUSE_ADDRESS = "120 Schermerhorn St (Brooklyn Criminal Court and Central Booking)"
PRECINCT_CORE = 84
TIMES_SQUARE_CELL = "54_42"

# ---- offense definitions -----------------------------------------------------
VIOLENT_PRIMARY = {"101", "105", "106"}
HOMICIDE_CODES = {"101"}
EXPLORER_EXTRA_HOMICIDE = {"102", "103"}  # negligent homicide pulled in by the explorer's ofns_desc fallback
CONTEXT_KY = {"341", "109", "344", "351", "117", "118", "578"}  # petit larceny, grand larceny, assault 3, crim mischief, drugs, weapons, harassment
THEFT_OF_SERVICES_PREFIX = "THEFT OF SERVICES"
DEFAULT_TIMES = {"00:00:00", "12:00:00"}
NIGHT_HOURS = {22, 23, 0, 1, 2, 3, 4, 5}
SPAN_MAX_HOURS = 6
CLASSES = ["street_robbery", "retail_robbery", "other_assault", "officer_assault", "homicide"]
ZONES = ["street_stores", "courthouse", "transit"]

# ---- comparators (anchor coordinates; cell ids resolved and asserted in stage 04) ----
HUB_ANCHORS = {
    "Times Square / Port Authority": (40.7568, -73.9875),
    "Herald Square": (40.7498, -73.9878),
    "Jamaica Center": (40.7021, -73.8010),
    "Fordham Road": (40.8620, -73.8928),
    "Flushing Main St": (40.7596, -73.8303),
    "125th St Harlem": (40.8076, -73.9454),
    "Atlantic Terminal": (40.6844, -73.9775),
}
COURTHOUSE_ANCHORS = {
    "Bronx Criminal Court (215 E 161st)": (40.8266, -73.9212),
    "Manhattan Criminal Court (100 Centre)": (40.7160, -74.0017),
    "Queens Criminal Court (125-01 Queens Blvd)": (40.7122, -73.8302),
    "Staten Island Criminal Court (26 Central Ave)": (40.6410, -74.0764),
}
COMPARATOR_BASE_MIN = 20
COMPARATOR_TOP_DECILE = 0.10

# ---- gates and thresholds ----------------------------------------------------
PIN_TOLERANCE = 0.005
PIN_CITY_VIOLENT_EXPLORER = {2024: 46073, 2025: 44795}
PIN_CELL_2024 = 202
PIN_CELL_2025 = 236
GATE_PRECINCT_AGREE = 0.90  # generalized coordinates near the 84/88/78 seams; see DECISIONS.md
GATE_COORD_NULL = 0.03
GATE_YEAR_FILE_AGREE = 0.99
GATE_LAWCAT_STABLE = 0.99
GATE_EXPLORER_EXTRA = 0.002
WARN_DEFAULT_TIME_PP = 5.0
KILL_NIGHT_GAP_PP = 8.0
WARN_LAG30_PP = 2.0
WARN_POINT_STEP = 0.15
WARN_HELD_SHARE_FACTOR = 1.5
KILL_C1_PERCENTILE = 90
KILL_P3_PERCENTILE = 95
KILL_NB_Z = 3.0
WARN_LOYO_RANGE = 0.20
WARN_HUB_NIGHT_PP = 3.0
CLAIM1_TOL = (2.2, 3.0)
CLAIM7_TOL = (1, 3)
LADDER_MIN_STEP = 2
FLAT_MAXMIN = 1.5
CLOCK_P = 0.01
BOOTSTRAP_B = 2000
MIN_POINT_N = 3
DEMOGRAPHIC_MIN_N = 50
PUBLIC_JSON_MAX_BYTES = 2_000_000
FOOTPRINTS_MAX_BYTES = 1_500_000
ASSET_MAX_BYTES = 25_000_000
FOOTPRINT_CAP_M = 60

DROP_FROM_DOWNLOADS = ["susp_age_group", "susp_race", "susp_sex", "vic_age_group", "vic_race", "vic_sex"]
CSV_HEADER_COMMENT = (
    f"# {SLUG} | snapshot {SNAPSHOT_DATE} | source: NYC Open Data, NYPD Complaint Data Historic (qgea-i56i) "
    "and Year-To-Date (5uac-w243) | coordinates are NYPD-generalized (midblock/intersection) | joe@group17a.com"
)

SLIM_COLUMNS = [
    "cmplnt_num", "cmplnt_fr_dt", "cmplnt_fr_tm", "cmplnt_to_dt", "cmplnt_to_tm", "rpt_dt", "addr_pct_cd",
    "ky_cd", "ofns_desc", "pd_cd", "pd_desc", "law_cat_cd", "crm_atpt_cptd_cd", "boro_nm", "loc_of_occur_desc",
    "prem_typ_desc", "juris_desc", "jurisdiction_code", "latitude", "longitude", "patrol_boro", "station_name",
    "transit_district", "susp_age_group", "susp_race", "susp_sex", "vic_age_group", "vic_race", "vic_sex",
]

# context.json blocks written by stage 11 (stage 09 preserves them; run_all gates on their presence)
CONTEXT_STAGE11_BLOCKS = ("opening", "precincts", "improvers", "density", "timelapse", "growth", "plaza", "clock")

# "Stable-code" basis for 2006-to-2025 comparisons: drop offense codes that did not exist, or were not
# felonies, in 2006. Strangulation (NY Penal Law 121.12 / 121.13) took effect 2010-11-11; before that most
# of these were misdemeanor assault 3 or uncharged. The three public-employee assault codes first appear
# in NYPD data in 2017. Raw figures ship alongside and are footnoted.
STABLE_CODE_EXCLUDE_PD_DESC = {"STRANGULATION 1ST", "ASSAULT OTHER PUBLIC SERVICE EMPLOYEE", "ASSAULT TRAFFIC AGENT", "ASSAULT SCHOOL SAFETY AGENT"}
STRANGULATION_LAW_EFFECTIVE = "2010-11-11"
CHANGE_YEAR_EARLY = 2006   # single-year endpoints for every "since 2006" figure in the prose
CHANGE_YEAR_LATE = 2025
CHANGE_WINDOW_EARLY = (2006, 2008)   # three-year windows: an eligibility guard for named cells, never a printed number
CHANGE_WINDOW_LATE = (2023, 2025)
CHANGE_GUARD_DECLINE_PCT = -60.0     # a cell is named a "biggest decline" only if its windowed change is at least this

# K3 spillover test: per-person ranks only among cells with at least this many residents + jobs
SPILLOVER_MIN_POP_JOBS = 2000

# grid.geojson properties written by stage 11 (stage 08 preserves them on a rerun)
GRID_STAGE11_PROPS = ("residents", "jobs", "rate_res", "rank_res")
