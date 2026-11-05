// Config for the hoyt-schermerhorn-crime-analysis gizmo: data URLs, palette, geometry constants,
// scene definitions, and the typed data contract (pipeline/DATA_CONTRACT.md in the gizmo folder).
//
// Palette (dataviz validator, 2026-10-19): marks use a one-step-lighter cobalt (#2A2AE0) because brand
// Cobalt #1F1FD6 sits just under the light-band lightness floor; text and chrome keep #1F1FD6. The set
// #2A2AE0 / #21A8E0 / #c98500 / #d55181 passes the adjacent and all-pairs gates (worst CVD dE 13.2,
// worst normal-vision dE 19.3). Carolina (2.64:1) and the dark yellow (2.99:1) need relief against white,
// which the direct band labels and ledger cards provide. Keep values as plain literals on single lines.

export const HOYT_SLUG = "hoyt-schermerhorn-crime-analysis";
export const DATA_VERSION = 1;
export const ASSET_PREFIX = `/assets/${HOYT_SLUG}-`;

export type HoytDataName =
  | "context" | "stops" | "zones" | "ladder" | "ribbon" | "clock" | "dq" | "imagery" | "footprints" | "labels" | "grid"
  | "density" | "precincts_1990" | "improvers" | "timelapse" | "sankey" | "precinct84" | "points_2024_25" | "precincts";

export function dataUrl(name: HoytDataName): string {
  const ext = name === "footprints" || name === "labels" || name === "grid" || name === "precinct84" || name === "precincts" ? "geojson" : "json";
  return `/data/${HOYT_SLUG}/${name}.${ext}?v=${DATA_VERSION}`;
}

export type ClassKey = "street_robbery" | "retail_robbery" | "other_assault" | "officer_assault" | "homicide";
export type ZoneKey = "street_stores" | "courthouse" | "transit";
export const CLASS_ORDER: ClassKey[] = ["street_robbery", "retail_robbery", "other_assault", "officer_assault", "homicide"];
export const CLASS_STYLE: Record<ClassKey, { color: string; label: string; short: string; drawn: boolean }> = {
  street_robbery: { color: "#2A2AE0", label: "Street robbery", short: "Street robbery", drawn: true },
  retail_robbery: { color: "#21A8E0", label: "Robbery that began as shoplifting or in a store", short: "Store robbery", drawn: true },
  other_assault: { color: "#c98500", label: "Other felony assault", short: "Felony assault", drawn: true },
  officer_assault: { color: "#d55181", label: "Assault on an officer", short: "Officer assault", drawn: true },
  homicide: { color: "#3B3B3B", label: "Homicide", short: "Homicide", drawn: false },
};
export const ZONE_LABEL: Record<ZoneKey, string> = { street_stores: "Sidewalk and stores", courthouse: "120 Schermerhorn", transit: "Stations" };
export const MONO_DISC = "#3B3B3B";
export const GHOST = "#C9CBD1";
export const GRID_RAMP = ["#EEF0FA", "#9AA3EA", "#6F7BE3", "#4A54DC", "#2A2AE0", "#15158F"];
export const STRIP_RAMP = ["#F4F5FC", "#C3C8F2", "#8F99E8", "#5A66DF", "#2A2AE0", "#15158F"];
export const COBALT = "#1F1FD6";
export const CAROLINA = "#21A8E0";
export const CHARCOAL = "#3B3B3B";
export const STEEL = "#6E6E6D";
export const VELLUM = "#F1F1F2";

export const CORE: [number, number] = [-73.985, 40.6885];
export const COURTHOUSE: [number, number] = [-73.989019, 40.690115];
export const BEARING = -25;
export const PITCH = 50;
export const PITCH_TOUCH = 35;
export const DISC_MIN_RADIUS_M = 25;
export const DISC_M2_PER_INCIDENT = 42;
export const MIN_DRAWN = 3;
export const FOOTPRINT_CAP_M = 60;
export const NIGHT_HOURS = [22, 23, 0, 1, 2, 3, 4, 5];
export const WINDOW: [number, number] = [2006, 2026];
export const H1_YEARS = ["2024", "2025", "2026"];
export const MOBILE_STAGE_VH = 60;
export const FLY_MS = 1800;
export const MORPH_MS = 900;
export const N_CELLS = 2854;
export const CELL_ID = "40_42";
export const TIMES_SQUARE_CELL = "54_42";

export type RadiusDef = "all" | "no_officer" | "no_officer_no_retail" | "no_courthouse";

/** Steps of the "city" scrolly (HoytCityGrid). */
export const CITY_STEPS = ["all", "top20", "improvers", "precinct", "dive"] as const;
/** Cell 40_42's edges from the lattice (pipeline/lattice; stable). */
export const CELL_BOUNDS = { west: -73.990617, east: -73.984308, south: 40.687447, north: 40.692229 } as const;
/** The sites the piece names: stop ids in stops.json, numbered for the site map. The subway-entrance stop (s04)
 * was cut with the four-site walk on 2026-10-21; its point stays in stops.json. */
export const SITES: { id: string; n: number; name: string; short: string }[] = [
  { id: "s08", n: 1, name: "The store", short: "Store" },
  { id: "s06", n: 2, name: "The plaza", short: "Plaza" },
  { id: "s01", n: 3, name: "The courthouse", short: "Courthouse" },
];
export type CityStep = (typeof CITY_STEPS)[number];


/** The one-click bundle: four CSVs plus a README with every column defined. Shown in the page header. */
export const DATA_BUNDLE = { label: "Download the data (.zip: four CSVs and a README)", url: `${ASSET_PREFIX}data.zip` };
export const DOWNLOADS: { label: string; url: string }[] = [
  { label: "Every complaint within 500 m, 2006 to mid-2026 (.csv, 11 MB)", url: `${ASSET_PREFIX}core-incidents.csv` },
  { label: "Yearly series by place, class and definition (.csv)", url: `${ASSET_PREFIX}yearly-series.csv` },
  { label: "All 2,854 map cells, 2010s base and 2024 to 2025 (.csv)", url: `${ASSET_PREFIX}cell-ranking.csv` },
  { label: "Data-quality audit, 57 tests (.csv)", url: `${ASSET_PREFIX}dq-audit.csv` },
];

export function streetViewLink(lat: number, lon: number, heading = 0): string {
  return `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lon.toFixed(6)}&heading=${heading}`;
}

// ---- data contract (subset the components read) ----------------------------
export interface Stop {
  id: string; lat: number; lon: number; zone: ZoneKey; label: string; label_status: "verified" | "unverified"; nearest_label_m: number;
  totals: { all: number; "2024_25": number; "2006_2026": number };
  by_class_year: Record<string, Record<ClassKey, number>>;
  by_class_2024_25: Record<ClassKey, number>;
  hour_hist: number[]; hour_hist_clean: number[]; week: number[][];
  premise_mix_2023_26: Record<string, number>;
  petit_larceny_by_year: Record<string, number> | null; misd_assault_by_year: Record<string, number> | null;
  peak_hour: number | null; shoplift_origin_share_2024_25: number | null; street_view_url: string;
  footprint: GeoJSON.Polygon | null;
}
export interface ZoneBlock {
  by_class_year: Record<string, Record<ClassKey, number>>; hour_hist: number[]; hour_hist_clean: number[]; week: number[][];
  night_share: number | null; premise_mix_2023_26: Record<string, number>; premise_mix_2010_19: Record<string, number>;
  demographics: Record<string, unknown> | null;
}
export interface StopsFile { snapshot: string; stops: Stop[]; suppressed: { n_points: number; n_incidents: number; rule: string }; zones: Record<ZoneKey, ZoneBlock> }
export interface LadderFile {
  n_cells: number; cell_id: string;
  primary: Record<RadiusDef, { rank: number; count: number }>;
  spillover: { name: string; cell_id: string; cell_name: string; count_2024_25: number; on_site: number; ex_site: number; rank_all: number; rank_ex_site: number; pop_jobs: number; ex_site_per_1000_present: number | null; rank_ex_site_per_person: number | null; n_cells_per_person: number }[];
  top20: { cell_id: string; name: string; lat: number; lon: number; count: number; rank: number; officer_share: number; retail_share: number }[];
  hubs: { name: string; cell_id: string; count_2024_25: number; by_class_2024_25: Record<ClassKey, number>; ratio_2024_25_vs_2010s: Record<string, number | null>; night_share: number | null }[];
  courthouses: { name: string; cell_id: string; cell_count_2024_25: number; largest_point: { count: number; share_of_cell: number; officer_share: number; by_year: Record<string, number> } }[];
  neighbors: { cell_id: string; name: string; ratio: number | null }[];
  ladder_ok: boolean;
}
export interface RibbonFile {
  geos: Record<string, { years: string[]; by_class: Record<ClassKey, number[]>; all: number[]; partial: Record<string, boolean> }>;
  index_2010s: Record<string, Record<string, (number | null)[]>>;
  petit_larceny: { core400: number[]; years: string[] };
  h1: { rule: string; panels: Record<string, Record<string, number>> };
}
export interface ClockFile {
  hour_share: Record<string, number[]>; week: Record<string, number[][]>; week_max: Record<string, number>;
  night: Record<string, { share: number; ci: [number, number]; n: number } | { value: number; ci: [number, number] }>;
  night_gap_pp: { value: number; ci: [number, number] }; default_time_share: Record<string, Record<string, number>>;
  chi_square_vs_city: Record<string, { stat: number; p: number; n: number }>; clock_ok: boolean; hub_night_shares: Record<string, number | null>;
}
export interface DqTest { id: string; group: string; title: string; status: "pass" | "warn" | "fail" | "kill" | "report" | "skipped"; value: unknown; threshold: unknown; reading: string; affects: string[]; footnote: string | null }
export interface DqClaim { label: string; primary: { value: number | null; words: Record<string, string>; footprint: string; window: string }; range: [number, number] | null; direction_holds: boolean | null; publishable: boolean; kill_reasons: string[]; footnotes: string[] }
export interface DqFile { snapshot: string; tests: DqTest[]; claims: Record<string, DqClaim>; summary: { gates_failed: number; warns: number; killed: string[]; skipped: string[] } }
export interface Photo { key: string; status: "mapillary" | "placeholder" | "shot"; file: string | null; caption: string; captured_at: string | null; facing_deg: number | null; attribution: string | null; source_url: string | null; brief: string; lat: number; lon: number; street_view_url: string }
export interface ImageryFile { snapshot: string; token_present: boolean; photos: Photo[] }
export interface DensityFile {
  min_denominator: number; count_rank: number;
  this_cell: { count_2024_25: number; residents: number; jobs: number };
  ranks: Record<"residents" | "jobs" | "residents_plus_jobs", { rank: number | null; n_cells: number; rate_per_1000_per_year: number | null; denominator: number }>;
  top20: Record<string, { cell_id: string; name: string; rate: number; count_2024_25: number; denominator: number }[]>;
}
export interface ImproversFile {
  year_early: number; year_late: number; min_early: number; basis: string; excluded_codes: string[]; strangulation_law_effective: string;
  excluded_count: Record<string, number>; strangulation_2025: number;
  guard: { window_early: [number, number]; window_late: [number, number]; decline_pct: number; dropped_from_declines: { cell_id: string; name: string; change_pct: number; change_pct_windowed: number }[] };
  biggest_declines: ImproverRow[];
  biggest_increases: ImproverRow[];
  this_cell: ImproverRow & { rank_among_eligible_by_change: number | null; n_eligible: number };
  precinct_84: { cells: { cell_id: string; name: string; share_in_precinct: number; early: number; late: number; change_pct: number | null; lat: number; lon: number }[];
                 early: number; late: number; change_pct: number | null; early_raw: number; late_raw: number; change_pct_raw: number | null; n_down: number; n_up: number; bounds: [number, number, number, number] };
  city: { early: number; late: number; change_pct: number; early_raw: number; late_raw: number; change_pct_raw: number };
  city_change_pct: number;
  city_change_by_family_pct: Record<"robbery" | "felony_assault" | "homicide", { early: number; late: number; change_pct: number }>;
  city_change_by_family_pct_raw: Record<"robbery" | "felony_assault" | "homicide", { early: number; late: number; change_pct: number }>;
  concentration: { n_cells: number; n_cells_with_any: number; top20pct_cells: number; top20pct_share: number; cells_for_half: number; cells_for_half_share_of_all: number; cells_for_20pct: number; cells_for_20pct_share_of_all: number; threshold_count_top20pct: number; threshold_count_half: number };
}
export interface ImproverRow { cell_id: string; name: string; area: string | null; early: number; late: number; change_pct: number; change_pct_windowed: number; early_raw: number; late_raw: number; change_pct_raw: number | null }
export interface PrecinctsFile {
  n_precincts: number; city: { murder_1990: number; murder_2025: number; source: string };
  precincts: Record<string, Record<string, Record<string, number>>>;
  summary: { precinct: number; violent_1990: number; violent_2025: number; change_pct: number | null; robbery_change_pct: number | null; fel_assault_change_pct: number | null; murder_1990: number; murder_2025: number }[];
}
export interface TimelapseFile {
  year: number; month: number; days: number; first_dow: number; radius_m: number; note: string;
  counts: Record<string, number>;
  rows: { d: number; dow: number; h: number | null; default_time: boolean; kind: string; zone: ZoneKey; lat: number; lon: number; premise: string; jitter: [number, number] }[];
}
export interface SankeyFile { window: string; footprint: string; total: number; places: { name: string; n: number }[]; classes: { name: string; n: number }[]; flows: { place: string; cls: string; n: number }[] }
export interface ZonesFile { by_zone_year_class: Record<ZoneKey, Record<string, Record<ClassKey, number>>>; h1: { full: Record<string, Record<ZoneKey, number>>; reported_by_june_30: Record<string, Record<ZoneKey, number>> }; totals_2024_25: Record<ZoneKey, number> }
