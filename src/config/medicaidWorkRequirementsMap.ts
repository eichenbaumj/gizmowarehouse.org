// Configuration for the Medicaid Work Requirements interactive map.
//
// Layer pyramid (NPE pattern, opacity stops verbatim):
//   - States (51 features, static GeoJSON)            z 2-4
//   - Counties (3,109 CONUS features, static GeoJSON) z 4-7
//   - 5-mile hex (pointy-top tiling, static GeoJSON)  z 4-9
//   - 1-mile hex grid (PMTiles)                       z 8-14
//   - Carto Voyager raster basemap (always behind)    all zooms
//
// Four render modes: subject_count, subject_rate, burden_index, loss_exposure.
// Ramps are *stepped* (MapLibre `step` expression), not interpolated — banded
// contrast makes concentration visible at a glance.
//
// Non-expansion states (10) render gray-hatched with a click-card explaining
// why; an "Uninsured Adults" overlay surfaces their would-be-affected population.

import { CARTO_ATTRIBUTION, cartoRasterTiles } from "./basemap";

export const MEDICAID_MAP_CONFIG = {
  center: [-97.5, 39.0] as [number, number],
  zoom: 4,
  minZoom: 3,
  maxZoom: 14,
  bounds: [
    [-125, 24],
    [-66, 50],
  ] as [[number, number], [number, number]],

  // Carto Voyager light raster — same basemap as NPE. Key + builders: ./basemap.ts
  basemapTiles: cartoRasterTiles("voyager_nolabels"),
  basemapAttribution: CARTO_ATTRIBUTION,
  // Labels overlay (renders above the choropleth so place names stay legible)
  labelsTiles: cartoRasterTiles("voyager_only_labels"),

  // Data sources — states + counties + state summary ship from /public/data
  // (small files). 5-mi hex GeoJSON (57 MB) and 1-mi grid PMTiles (100 MB)
  // are too large for Lovable's per-file asset slot, so they live on R2 at
  // data.gizmowarehouse.org. CORS GET/HEAD with Range is configured on the
  // bucket — see tools/HOSTING_DATA.md.
  statesGeoJsonUrl: "/data/medicaid-states.geojson",
  countiesGeoJsonUrl: "/data/medicaid-counties.geojson",
  // v3: 5-mile hex rebuilt as a complete, non-overlapping pointy-top tiling
  // (~3.8 mi across) by aggregating the 1-mile cells — carries bottom-up loss +
  // ratio-of-sums working-age subject_rate + most-common place/county labels, and
  // reconciles exactly to the grid. Versioned because R2 serves these `immutable` —
  // a stable name would pin returning visitors to the old bytes. Bumped in
  // lockstep with grid.v6.pmtiles below.
  hex5miGeoJsonUrl: "https://data.gizmowarehouse.org/medicaid-work-requirements/hex-5mi.v4.geojson",
  // v6: grid rebuilt as 1-mile HEXES on the NPE mesh (was square cells), apportioned
  // tract-dasymetric by population, carrying bottom-up loss + working-age subject_rate
  // + the Tier A/B/C/D place labels and Medicaid landmark re-rank (FQHC > hospital >
  // school > library). Non-overlapping hexes share vertices and tile to ~105 MB (the
  // square build had bloated to 681 MB). See pipeline/08_resample_to_grid.py +
  // tools/bake-medicaid-place-labels.py + bake-medicaid-landmarks.py.
  gridPmtilesUrl: "https://data.gizmowarehouse.org/medicaid-work-requirements/grid.v7.pmtiles",
  gridSourceLayer: "grid",
  stateSummaryUrl: "/data/medicaid-state-summary.json",

  // Layer crossfade opacity stops. The 5-mile hex grid is the *primary*
  // visual layer at every zoom from 4 up. NPE uses 0.55 default opacity —
  // street names show through, and the cool→warm hue ramp does the visual
  // work so saturation isn't dulled by transparency.
  statesOpacityStops: [2, 0.7, 3, 0.3, 4, 0] as number[],
  countiesOpacityStops: [2.5, 0, 3, 0.4, 4, 0.3, 6, 0.25, 8, 0.12, 9, 0] as number[],
  hex5miOpacityStops: [3, 0, 4, 0.55, 5, 0.6, 9, 0.5, 10, 0.25, 11, 0.1, 12, 0] as number[],
  // 1-mile grid fades in from z=9 (PMTiles minzoom is 8) so within-county hot
  // spots arrive ~2 zooms earlier than before; full opacity z=11 → z=14.
  // Crossover with hex5mi around z=9-10 — both contribute, hex5mi fading out
  // as the grid fades in.
  gridOpacityStops: [8, 0, 9, 0.15, 10, 0.45, 11, 0.7, 14, 0.7] as number[],

  // Color ramps — stepped, 8 stops for strong visual contrast.
  // Each mode keeps stopsCounty (used at low/mid zoom) and stopsGrid (denser
  // breakpoints for sub-county cells).
  modes: {
    subject_count: {
      label: "People subject to work req",
      property: "subject_count_strict",
      legendUnit: "people",
      // Stepped cool→warm ramp. Breakpoints recalibrated to the actual
      // per-primitive distribution shipped in medicaid-state-summary.json
      // (percentile_cutoffs, stage 09b) so each of the 8 colors carries a real
      // slice of cells — pale→medium blue across the low range where most cells
      // sit, warm tier for the top ~15%. Tuned for contrast nationally + zoomed.
      // County p50≈780, p75≈3.1k, p90≈10.8k, p95≈23.6k, p99≈82k.
      stopsCounty: [
        [0, "#EFF6FF"],
        [500, "#BFDBFE"],
        [1_300, "#60A5FA"],
        [3_000, "#FEF9C3"],
        [6_400, "#FDE047"],
        [17_000, "#FB923C"],
        [38_000, "#DC2626"],
        [82_000, "#7F1D1D"],
      ] as [number, string][],
      // Grid p50≈1.9, p75≈5.2, p90≈17, p95≈45, p99≈224.
      stopsGrid: [
        [0, "#EFF6FF"],
        [1.3, "#BFDBFE"],
        [2.7, "#60A5FA"],
        [5, "#FEF9C3"],
        [10, "#FDE047"],
        [30, "#FB923C"],
        [85, "#DC2626"],
        [225, "#7F1D1D"],
      ] as [number, string][],
      // 5-mi hex p50≈23, p75≈69, p90≈236, p95≈618, p99≈2.3k.
      stopsHex5mi: [
        [0, "#EFF6FF"],
        [12, "#BFDBFE"],
        [35, "#60A5FA"],
        [68, "#FEF9C3"],
        [135, "#FDE047"],
        [420, "#FB923C"],
        [1_090, "#DC2626"],
        [2_330, "#7F1D1D"],
      ] as [number, string][],
    },
    subject_rate: {
      label: "% of working-age adults subject",
      property: "subject_rate",
      legendUnit: "%",
      // Recalibrated to the actual rate distribution (grid/hex p50≈0.12,
      // p90≈0.23, p99≈0.38; counties run lower, p50≈0.10). The old ramp spread
      // 8 colors over 0–0.65, so most cells fell in 2 near-white blues (national
      // "sea of blue") and dense tracts lumped into one yellow band. These stops
      // add a medium blue and put the median at the blue→yellow boundary, then
      // graduate the populated 0.05–0.31 range so adjacent tracts differentiate.
      // NOTE: subject_rate is uniform within a census tract, so zoomed-in
      // contrast is *between* tracts; counties get their own (lower) stops.
      stopsCounty: [
        [0, "#EFF6FF"],
        [0.04, "#BFDBFE"],
        [0.07, "#60A5FA"],
        [0.096, "#FEF9C3"],
        [0.125, "#FDE047"],
        [0.155, "#FB923C"],
        [0.2, "#DC2626"],
        [0.26, "#7F1D1D"],
      ] as [number, string][],
      // Grid + hex share this ramp (their rate distributions are ~identical).
      stopsGrid: [
        [0, "#EFF6FF"],
        [0.05, "#BFDBFE"],
        [0.085, "#60A5FA"],
        [0.12, "#FEF9C3"],
        [0.155, "#FDE047"],
        [0.195, "#FB923C"],
        [0.245, "#DC2626"],
        [0.31, "#7F1D1D"],
      ] as [number, string][],
    },
    burden_index: {
      label: "Compliance burden index",
      property: "burden_index_centered",
      legendUnit: "index (centered on national median)",
      // Diverging cobalt ↔ amber, neutral (#F2F2F2) at 0. Positive breakpoints
      // recalibrated to the distribution (grid p50≈3.6, p90≈11, p99≈23; counties
      // lower, p50≈0.9, p90≈7.6, p99≈12) so the amber tier graduates instead of
      // saturating; the negative side handles the below-median minority.
      stopsCounty: [
        [-15, "#1F1FD6"],
        [-7, "#7B9BE0"],
        [-2, "#D6E4F2"],
        [0, "#F2F2F2"],
        [2.5, "#FCE7B5"],
        [5, "#E69138"],
        [8, "#B45309"],
        [11, "#7C2D12"],
      ] as [number, string][],
      stopsGrid: [
        [-20, "#1F1FD6"],
        [-10, "#7B9BE0"],
        [-3, "#D6E4F2"],
        [0, "#F2F2F2"],
        [4, "#FCE7B5"],
        [8, "#E69138"],
        [13, "#B45309"],
        [20, "#7C2D12"],
      ] as [number, string][],
      diverging: true as const,
    },
    loss_exposure: {
      label: "Projected coverage loss",
      property: "loss_exposure_strict",
      legendUnit: "people",
      // Cool→warm, breakpoints recalibrated to the loss distribution per
      // primitive (county p50≈294, p90≈3.5k, p99≈25k; grid p50≈0.8, p90≈6.4,
      // p99≈84; 5-mi hex p50≈9, p90≈90, p99≈865).
      stopsCounty: [
        [0, "#EFF6FF"],
        [200, "#BFDBFE"],
        [500, "#60A5FA"],
        [1_100, "#FEF9C3"],
        [2_200, "#FDE047"],
        [5_000, "#FB923C"],
        [11_000, "#DC2626"],
        [25_000, "#7F1D1D"],
      ] as [number, string][],
      stopsGrid: [
        [0, "#EFF6FF"],
        [0.5, "#BFDBFE"],
        [1.1, "#60A5FA"],
        [2, "#FEF9C3"],
        [4, "#FDE047"],
        [11, "#FB923C"],
        [32, "#DC2626"],
        [84, "#7F1D1D"],
      ] as [number, string][],
      stopsHex5mi: [
        [0, "#EFF6FF"],
        [6, "#BFDBFE"],
        [14, "#60A5FA"],
        [27, "#FEF9C3"],
        [52, "#FDE047"],
        [130, "#FB923C"],
        [410, "#DC2626"],
        [865, "#7F1D1D"],
      ] as [number, string][],
    },
  } as const,

  defaultMode: "subject_count" as const,
  // Default to the county aggregate — the right level for an at-a-glance
  // visualization of *where* the impact will concentrate. Within-county
  // hot spots are available via the "View as" toggle (1-mile grid).
  defaultPrimitive: "counties" as const,

  // Threshold slider — NPE's binary-reveal pattern. Cells above threshold pop;
  // cells below dim. Default per mode.
  thresholdDefaults: {
    subject_count: 5_000,
    subject_rate: 0.08,
    burden_index: 5,
    loss_exposure: 1_500,
  },
  thresholdRanges: {
    subject_count: [0, 50_000] as [number, number],
    subject_rate: [0, 0.25] as [number, number],
    burden_index: [-20, 30] as [number, number],
    loss_exposure: [0, 20_000] as [number, number],
  },
  opacityAboveThreshold: 0.65,
  opacityBelowThreshold: 0.12,

  // The 7 states with NO OBBBA-subject population: did not expand AND have no
  // subject 1115-waiver group. (WI/GA/TN moved out — they're subject via waiver;
  // see waiverListedFips / waiverSubjectFips below.) Drives nothing functional —
  // the map styles off the GeoJSON `expansion` / `subject_via_waiver` /
  // `waiver_listed` properties — but kept as the canonical reference list.
  nonExpansionStateFips: [
    "01", "12", "20", "28", "45", "48", "56",
  ] as string[],
  // CMS June-2026: 3 non-expansion states subject via 1115 waiver. WI/GA are
  // sized + modeled (subject_via_waiver); TN is listed but not quantified.
  waiverSubjectFips: ["13", "55"] as string[],   // GA, WI
  waiverListedFips: ["13", "47", "55"] as string[],  // GA, TN, WI
  nonExpansionFill: "#E5E5E5",
  // Subject per CMS but affected population not quantified (TN): pale amber so it
  // reads as "flagged / in scope", distinct from both shaded and gray-hatched.
  waiverListedFill: "#FBEACB",

  // OBBBA key dates
  effectiveDate: "2026-12-31",
  hhsRuleDeadline: "2026-06-01",
  stateNotificationDeadline: "2026-09-30",
  hardshipExtensionEnd: "2028-12-31",
};

export type MedicaidMapMode = keyof typeof MEDICAID_MAP_CONFIG.modes;
export type MedicaidMapPrimitive = "counties" | "hex5mi" | "grid";

// Short editorial copy explaining each render mode. Renders in the sidebar
// below the mode-toggle buttons. Format: what it shows, why it differs from
// the others, an extreme example, how it's calculated. Place names should
// match the actual data once the real pipeline runs.
export const MODE_EXPLAINERS: Record<MedicaidMapMode, {
  what: string;
  extreme: string;
  calc: string;
}> = {
  subject_count: {
    what: "Raw count of expansion-Medicaid enrollees who'll need to prove 80 hours of qualifying activity each month.",
    extreme: "Los Angeles County leads at ~1.1 million subject enrollees — by itself larger than the entire expansion-Medicaid pool of 39 of the 41 expansion states + DC.",
    calc: "Tract-level ACS Medicaid estimates, raked to each state's CBO-anchored total and aggregated up to the county. Useful for 'how many people my office has to contact.'",
  },
  subject_rate: {
    what: "The same enrollees, expressed as a share of working-age adults (19-64) in each place.",
    extreme: "The District of Columbia (~24%) and California's Central Valley — Fresno, Kern, Riverside — exceed 20%, close to 1 in 4 working-age adults on expansion Medicaid; smaller rural Western counties run higher still.",
    calc: "subject_count ÷ working-age population. Normalizes away population size — shows where the policy bites structurally, not where it's just big.",
  },
  burden_index: {
    what: "A composite predicting verification failure (not work failure): limited-English households, employment volatility, broadband + DSS access.",
    extreme: "Louisiana's Claiborne Parish tops the burden index above +20 — high subject rates and high paperwork friction layered together, with neighboring north-Louisiana parishes like Bienville close behind.",
    calc: "0.4 × verification difficulty + 0.3 × labor volatility + 0.3 × access gap, centered on the national median. Editorial — weights in METHODOLOGY.md §5.",
  },
  loss_exposure: {
    what: "Estimated coverage loss when the rule takes effect — not because people are ineligible, but because they can't keep up with the six-month renewal paperwork.",
    extreme: "Los Angeles County leads at ~247,000 projected losses — by itself larger than the entire projected loss of 38 of the 41 expansion states + DC.",
    calc: "Each state's bottom-up projected loss — the per-(state, subgroup) model summed to ~5.42M nationally, just above CBO's 5.2M baseline — apportioned to its counties by subject share. The per-state rate varies with ex parte capability: low-capability states (Indiana, Idaho) lose a larger share than high-capability ones (California). Most losses are paperwork failures — missed letters, portal outages, wrong addresses, forms that require paystubs gig workers can't produce.",
  },
};

// State bounds for "fly to state" feature.
export const STATE_BOUNDS: Record<string, [[number, number], [number, number]]> = {
  "01": [[-88.5, 30.2], [-84.9, 35.0]],
  "02": [[-180, 50], [-130, 72]],
  "04": [[-114.8, 31.3], [-109.0, 37.0]],
  "05": [[-94.6, 33.0], [-89.6, 36.5]],
  "06": [[-124.5, 32.5], [-114.1, 42.0]],
  "08": [[-109.1, 36.9], [-102.0, 41.0]],
  "09": [[-73.7, 40.9], [-71.8, 42.1]],
  "10": [[-75.8, 38.4], [-75.0, 39.9]],
  "11": [[-77.2, 38.8], [-76.9, 39.0]],
  "12": [[-87.7, 24.4], [-79.9, 31.0]],
  "13": [[-85.7, 30.3], [-80.7, 35.0]],
  "15": [[-160, 18.5], [-154.5, 23.5]],
  "16": [[-117.3, 41.9], [-111.0, 49.0]],
  "17": [[-91.6, 37.0], [-87.4, 42.6]],
  "18": [[-88.1, 37.7], [-84.7, 41.8]],
  "19": [[-96.7, 40.3], [-90.1, 43.6]],
  "20": [[-102.1, 36.9], [-94.5, 40.1]],
  "21": [[-89.6, 36.5], [-81.9, 39.2]],
  "22": [[-94.1, 28.9], [-88.7, 33.1]],
  "23": [[-71.1, 43.0], [-66.8, 47.5]],
  "24": [[-79.5, 37.9], [-75.0, 39.7]],
  "25": [[-73.5, 41.2], [-69.9, 42.9]],
  "26": [[-90.5, 41.7], [-82.4, 48.3]],
  "27": [[-97.3, 43.4], [-89.4, 49.4]],
  "28": [[-91.7, 30.1], [-88.0, 35.0]],
  "29": [[-95.8, 36.0], [-89.0, 40.6]],
  "30": [[-116.1, 44.3], [-104.0, 49.0]],
  "31": [[-104.1, 39.9], [-95.3, 43.0]],
  "32": [[-120.0, 35.0], [-114.0, 42.0]],
  "33": [[-72.6, 42.6], [-70.6, 45.3]],
  "34": [[-75.6, 38.9], [-73.9, 41.4]],
  "35": [[-109.1, 31.3], [-103.0, 37.0]],
  "36": [[-79.8, 40.5], [-71.8, 45.0]],
  "37": [[-84.4, 33.8], [-75.4, 36.6]],
  "38": [[-104.1, 45.9], [-96.5, 49.0]],
  "39": [[-84.8, 38.4], [-80.5, 41.9]],
  "40": [[-103.0, 33.6], [-94.4, 37.0]],
  "41": [[-124.6, 41.9], [-116.5, 46.3]],
  "42": [[-80.5, 39.7], [-74.7, 42.3]],
  "44": [[-71.9, 41.1], [-71.1, 42.0]],
  "45": [[-83.4, 32.0], [-78.5, 35.2]],
  "46": [[-104.1, 42.5], [-96.4, 45.9]],
  "47": [[-90.3, 35.0], [-81.7, 36.7]],
  "48": [[-106.7, 25.8], [-93.5, 36.5]],
  "49": [[-114.1, 36.9], [-109.0, 42.0]],
  "50": [[-73.4, 42.7], [-71.4, 45.0]],
  "51": [[-83.7, 36.5], [-75.2, 39.5]],
  "53": [[-124.8, 45.5], [-116.9, 49.0]],
  "54": [[-82.7, 37.2], [-77.7, 40.6]],
  "55": [[-92.9, 42.5], [-86.2, 47.1]],
  "56": [[-111.1, 40.9], [-104.0, 45.0]],
};
