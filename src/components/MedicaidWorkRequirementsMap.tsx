// MedicaidWorkRequirementsMap — interactive map embed for the gizmo.
//
// v2: real state choropleth from placeholder data, no OSM raster base,
// diagonal-hatch pattern for non-expansion states, click-to-select,
// Source Serif 4 statistic typography to match the warehouse brand.

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  MEDICAID_MAP_CONFIG,
  MODE_EXPLAINERS,
  STATE_BOUNDS,
  type MedicaidMapMode,
  type MedicaidMapPrimitive,
} from "@/config/medicaidWorkRequirementsMap";
import { useCountUp } from "@/hooks/useCountUp";
import { isTouchPrimary } from "@/lib/isTouchPrimary";
import { concentrationCalloutText, type ConcentrationData } from "@/lib/medicaidConcentration";
import MedicaidLegend from "@/components/MedicaidLegend";
import MethodologyInfo from "@/components/MethodologyInfo";
import MedicaidTargetList, { type TargetCell } from "@/components/MedicaidTargetList";
import { METHODOLOGY_DOC_URL, getDisclosure } from "@/lib/methodologyDisclosures";

const TARGET_LIST_LOCAL_STORAGE_KEY = "medicaid_target_list";

function loadTargetList(): TargetCell[] {
  try {
    const raw = window.localStorage.getItem(TARGET_LIST_LOCAL_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveTargetList(list: TargetCell[]): void {
  try {
    window.localStorage.setItem(TARGET_LIST_LOCAL_STORAGE_KEY, JSON.stringify(list));
  } catch {
    /* quota exceeded — ignore */
  }
}

/** Build a TargetCell from a click feature. */
function targetCellFrom(
  kind: TargetCell["kind"],
  lngLat: [number, number],
  props: Record<string, any>,
): TargetCell {
  let id: string;
  let label: string;
  let sublabel: string | undefined;
  if (kind === "county") {
    id = `c:${props.GEOID || props.county_geoid || `${lngLat[0].toFixed(4)},${lngLat[1].toFixed(4)}`}`;
    label = `${props.county_name || props.GEOID}, ${props.state_abbr || ""}`.replace(/, $/, "");
  } else if (kind === "grid") {
    id = `g:${props.cell_id || `${lngLat[0].toFixed(5)},${lngLat[1].toFixed(5)}`}`;
    label = buildGridLabel(props);
    sublabel = props.parent_county_name
      ? `${props.parent_county_name} County, ${props.parent_state_abbr || ""}`.replace(/, $/, "")
      : undefined;
  } else {
    // hex
    id = `h:${props.coarse_id || `${lngLat[0].toFixed(5)},${lngLat[1].toFixed(5)}`}`;
    const place = (props.nearest_place_name as string) || "";
    const placeState = (props.nearest_place_state as string) || (props.parent_state_abbr as string) || "";
    label = place ? `Near ${place}, ${placeState}`.replace(/, $/, "") : `5-mi hex · ${props.parent_county_name || "—"} County`;
    sublabel = props.parent_county_name
      ? `${props.parent_county_name} County, ${props.parent_state_abbr || ""}`.replace(/, $/, "")
      : undefined;
  }
  return { id, kind, lngLat, label, sublabel, props, addedAt: Date.now() };
}

/**
 * Build the label for a 1-mi grid cell. Reads the Tier A/B/C/D place fields
 * baked by tools/bake-medicaid-place-labels.py with graceful fallback to
 * the legacy nearest_place_name field (for tiles built before the rebake).
 *
 * Examples:
 *   "Rogers Park · Chicago, IL · by Sullivan High School"  (Tier A/B + POI)
 *   "Rogers Park · Chicago, IL"                            (Tier A/B, no POI in cell)
 *   "Phoenix, AZ · by Maryvale High School"                (Tier C + POI)
 *   "Rural Cook County, IL"                                (Tier D — nothing nearby)
 */
function buildGridLabel(props: Record<string, unknown>): string {
  const placeName = ((props.place_name as string) || "").trim();
  const placeParent = ((props.place_parent as string) || "").trim();
  const placeState = ((props.place_state as string) || (props.parent_state_abbr as string) || "").trim();
  const landmark = ((props.landmark_name as string) || "").trim();
  const landmarkRank = Number(props.landmark_category ?? 99);
  // Ranks 1-7 = institutional anchors a caseworker would recognize → "by".
  // Ranks 8+ = geographic anchors (parks, gov't buildings) → "near".
  const connector = landmarkRank >= 1 && landmarkRank <= 7 ? "by" : "near";

  let head: string;
  if (placeName && placeParent) {
    head = `${placeName} · ${placeParent}, ${placeState}`.replace(/, $/, "");
  } else if (placeName) {
    head = `${placeName}, ${placeState}`.replace(/, $/, "");
  } else {
    // Tile predates Phase 2 bake — fall back to legacy field
    const legacy = ((props.nearest_place_name as string) || "").trim();
    const legacyState = ((props.nearest_place_state as string) || (props.parent_state_abbr as string) || "").trim();
    if (legacy) {
      head = `Near ${legacy}, ${legacyState}`.replace(/, $/, "");
    } else {
      head = `1-mi cell · ${((props.parent_county_name as string) || "—")} County, ${legacyState}`.replace(/, $/, "");
    }
  }

  return landmark ? `${head} · ${connector} ${landmark}` : head;
}

function registerPMTilesProtocol() {
  const p = new Protocol();
  try { maplibregl.removeProtocol("pmtiles"); } catch { /* not yet registered */ }
  try { maplibregl.addProtocol("pmtiles", p.tile); } catch { /* already registered */ }
}

/** Map mode → MethodologyInfo disclosure ID. */
const MODE_DISCLOSURE_ID: Record<MedicaidMapMode, string> = {
  subject_count: "map.subject_count",
  subject_rate: "map.subject_rate",
  burden_index: "map.burden_index",
  loss_exposure: "map.loss_exposure",
};

interface StateRow {
  state_fips: string;
  state_abbr: string;
  state_name: string;
  expansion: boolean;
  partial_expansion?: boolean;
  // Subject via a sized 1115-waiver slice (WI, GA).
  subject_via_waiver?: boolean;
  // Named on CMS's June-2026 subject list at all (WI, GA, TN).
  waiver_listed?: boolean;
  // False for TN (listed but not publicly quantified).
  loss_quantified?: boolean;
  // GA Pathways enrollees already face a work requirement → no net-new loss.
  already_work_conditional?: boolean;
  waiver_note?: string | null;
  hardship_exception_status: string;
  subject_count_strict: number;
  subject_count_permissive: number;
  loss_exposure_strict: number;
  burden_index_centered: number;
  subject_rate: number;
  note?: string;
}

// Suffix for the state dropdowns: distinguishes the OBBBA scope pathways.
// Expansion → none; WI/GA → "(1115 waiver)"; TN → "(1115 waiver — not
// quantified)"; the 7 truly-unaffected states → "(non-expansion)".
function stateScopeTag(s: {
  expansion: boolean;
  subject_via_waiver?: boolean;
  waiver_listed?: boolean;
}): string {
  if (s.expansion) return "";
  if (s.subject_via_waiver) return "  (1115 waiver)";
  if (s.waiver_listed) return "  (1115 waiver — not quantified)";
  return "  (non-expansion)";
}

interface PercentileCutoffs {
  // mode → primitive → percentile string → cutoff value
  [mode: string]: {
    [primitive: string]: { [pct: string]: number };
  };
}

interface StateSummary {
  version: string;
  note?: string;
  vintage: { acs: string; bls_laus: string; obbba_section: string; effective_date: string };
  national: {
    subject_count_strict: number;
    subject_count_permissive: number;
    loss_exposure_strict: number;
    cbo_subject_target: number;
    cbo_loss_target_2034: number;
    urban_loss_2028_high_mitigation: number;
    urban_loss_2028_low_mitigation: number;
  };
  concentration?: ConcentrationData;
  percentile_cutoffs?: PercentileCutoffs;
  states: StateRow[];
}

const COBALT = "#1F1FD6";
const BG = "#F4F6FA";

// 5-step auto-tour that lands the user on the concentration moment. Mirrors
// NPE's tour but Medicaid-framed. localStorage-gated so returning users skip.
interface TourStep {
  title: string;
  body: string;
  center: [number, number];
  zoom: number;
  mode?: MedicaidMapMode;
  /** Percentile (50–99). e.g., 80 = "top 20%". null leaves the slider where it is. */
  thresholdPct?: number | null;
}
const TOUR_STEPS: TourStep[] = [
  {
    title: "5.4 million people are about to lose Medicaid",
    body:
      "On December 31, 2026, the federal work requirement under OBBBA Section 71119 takes effect. This bottom-up model projects roughly 5.4 million will lose coverage by 2034 — just above CBO's 5.2 million baseline — most of them through paperwork failure, not failure to work.",
    center: [-97.5, 39.0],
    zoom: 4,
    mode: "subject_count",
    thresholdPct: 50,
  },
  {
    title: "Concentration",
    body:
      "85% of the impact lives in just 16% of US counties. The slider on the right narrows the highlight down to the densest counties.",
    center: [-97.5, 39.0],
    zoom: 4,
    mode: "subject_count",
    thresholdPct: 80,
  },
  {
    title: "A single county",
    body:
      "Wayne County, Michigan — Detroit and surrounding — has roughly 107,000 expansion enrollees subject to the new rule. One county. The state's Medicaid agency has seven months to find and contact every one of them.",
    center: [-83.2, 42.35],
    zoom: 8,
    mode: "subject_count",
    thresholdPct: 50,
  },
  {
    title: "Where verification fails hardest",
    body:
      "Burden mode highlights where the paperwork — not the work — is most likely to defeat eligible enrollees. Limited-English households, no broadband, seasonal labor. These are the places the rule's procedural failure mode will land hardest.",
    // Centered on Louisiana / the Delta parishes (the burden hot-spots) rather
    // than Mississippi, so the frame isn't dominated by the non-expansion South.
    center: [-92.3, 31.4],
    zoom: 6.3,
    mode: "burden_index",
    thresholdPct: 50,
  },
  {
    title: "Your state",
    body:
      "Pick a state from the sidebar, or just pan. The headline updates with each geography. Every county is downloadable as a CSV — link in the methodology accordion.",
    center: [-97.5, 39.0],
    zoom: 4,
    mode: "subject_count",
    thresholdPct: 50,
  },
];

function fmtCompact(n: number): string {
  if (!Number.isFinite(n)) return "—";
  if (n === 0) return "0";
  if (n < 1000) return new Intl.NumberFormat("en-US").format(Math.round(n));
  if (n < 1_000_000) return (n / 1000).toFixed(0) + "K";
  return (n / 1_000_000).toFixed(1) + "M";
}

function fmtFull(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US").format(Math.round(n));
}

function fmtPct(p: number): string {
  if (!Number.isFinite(p)) return "—";
  return (p * 100).toFixed(1) + "%";
}

function daysUntil(isoDate: string): number {
  const target = new Date(isoDate + "T00:00:00Z").getTime();
  const now = Date.now();
  return Math.max(0, Math.ceil((target - now) / 86_400_000));
}

function buildFillColor(mode: MedicaidMapMode, primitive: "counties" | "hex5mi" | "grid" | "states"): any {
  const cfg = MEDICAID_MAP_CONFIG.modes[mode];
  // Pick the right stops for this primitive:
  //   counties / states → stopsCounty (large polygons, large values)
  //   hex5mi            → stopsHex5mi if defined (subject_count/loss_exposure),
  //                       else stopsGrid (subject_rate/burden_index use one ramp)
  //   grid              → stopsGrid
  const stops =
    primitive === "hex5mi" ? ((cfg as any).stopsHex5mi ?? cfg.stopsGrid) :
    primitive === "grid" ? cfg.stopsGrid :
    cfg.stopsCounty;
  const valueExpr: any = ["coalesce", ["get", cfg.property], 0];
  // Stepped ramp — banded contrast that makes concentration visible at a glance.
  // First color is the "fallback" (below first threshold).
  const step: any[] = ["step", valueExpr, stops[0][1]];
  for (let i = 1; i < stops.length; i++) {
    step.push(stops[i][0], stops[i][1]);
  }
  return [
    "case",
    // Subject via a sized 1115-waiver slice (WI/GA): metric color even though
    // expansion=false. Checked first so it wins over the expansion-false branch.
    ["==", ["get", "subject_via_waiver"], true],
    step,
    // Subject per CMS but not quantified (TN counties): distinct flagged fill.
    ["==", ["get", "waiver_listed"], true],
    MEDICAID_MAP_CONFIG.waiverListedFill,
    // Truly unaffected non-expansion states: gray. (expansion is absent on hexes,
    // so this never fires there — they fall through to the metric ramp.)
    ["==", ["get", "expansion"], false],
    MEDICAID_MAP_CONFIG.nonExpansionFill,
    step,
  ];
}

function buildFillOpacity(layerOpacityStops: number[], threshold: number | null, mode: MedicaidMapMode): any {
  // MapLibre's data-driven paint: `zoom` can only appear as the INPUT to a
  // top-level step/interpolate. Wrapping zoom-interpolates inside a `case`
  // (the previous shape) is silently rejected — `setPaintProperty` returns
  // without error but the expression isn't applied, so threshold UI looks
  // dead. Fix: put `interpolate ["zoom"]` at the top level, with each
  // stop's VALUE being a `case` that dims by feature property.
  if (threshold === null || threshold === undefined) {
    const arr: any[] = ["interpolate", ["linear"], ["zoom"]];
    for (let i = 0; i < layerOpacityStops.length; i += 2) {
      arr.push(layerOpacityStops[i], layerOpacityStops[i + 1]);
    }
    return arr;
  }
  const prop = MEDICAID_MAP_CONFIG.modes[mode].property;
  const above: any = [">=", ["coalesce", ["get", prop], 0], threshold];
  const dim = MEDICAID_MAP_CONFIG.opacityBelowThreshold / MEDICAID_MAP_CONFIG.opacityAboveThreshold;
  const arr: any[] = ["interpolate", ["linear"], ["zoom"]];
  for (let i = 0; i < layerOpacityStops.length; i += 2) {
    const z = layerOpacityStops[i];
    const op = layerOpacityStops[i + 1];
    arr.push(z, ["case", above, op, op * dim]);
  }
  return arr;
}

function registerHatchImage(map: any, name: string, stroke: string) {
  if (map.hasImage(name)) return;
  const size = 16;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, size, size);
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = -size; i < size * 2; i += 5) {
    ctx.moveTo(i, 0);
    ctx.lineTo(i + size, size);
  }
  ctx.stroke();
  const img = ctx.getImageData(0, 0, size, size);
  map.addImage(name, {
    width: size,
    height: size,
    data: new Uint8Array(img.data.buffer.slice(0)),
  });
}

export default function MedicaidWorkRequirementsMap() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const [summary, setSummary] = useState<StateSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedStateFips, setSelectedStateFips] = useState<string>("");
  const [hoverStateFips, setHoverStateFips] = useState<string>("");
  const [mode, setMode] = useState<MedicaidMapMode>(MEDICAID_MAP_CONFIG.defaultMode);
  const [primitive, setPrimitive] = useState<MedicaidMapPrimitive>(MEDICAID_MAP_CONFIG.defaultPrimitive);
  // Clicked feature for the popup. null when no feature is selected.
  type SelectedFeature = {
    kind: "county" | "hex" | "grid";
    lngLat: [number, number];
    props: Record<string, any>;
  };
  const [selectedFeature, setSelectedFeature] = useState<SelectedFeature | null>(null);

  // Target list — operational set the user is building (shift+click to add/remove).
  // Persisted to localStorage so work-in-progress doesn't get blown away on reload.
  const [targetList, setTargetList] = useState<TargetCell[]>(() => loadTargetList());
  useEffect(() => {
    saveTargetList(targetList);
  }, [targetList]);

  // Threshold is a *percentile* (50–99). Default top 50% = percentile 50,
  // i.e., the slider starts at "show everything." Sliding right reveals
  // only higher concentrations. Always active — no on/off toggle. The
  // actual cutoff value per (mode × primitive) is read from the loaded
  // state-summary.json's `percentile_cutoffs` block at render time.
  const [thresholdPct, setThresholdPct] = useState<number>(50);
  // Auto-tour state. null when dismissed; 0-(TOUR_STEPS.length-1) when active.
  // The guided tour starts by default on every load (Skip dismisses it, the
  // "Take the guided tour" sidebar button re-launches it). No once-per-visitor
  // gate — we want every reader to get the walkthrough.
  const [tourStep, setTourStep] = useState<number | null>(0);

  // Touch-primary (phone/tablet) flag, read once. The map's style is built a
  // single time in a []-effect, so this never needs to be reactive. On this
  // path the 57 MB hex GeoJSON is kept out of the initial style and added
  // lazily (see the hex-defer effect below); desktop is unaffected.
  const lite = useMemo(() => isTouchPrimary(), []);
  // Flips when the deferred hex layer has been added on the lite path, so the
  // repaint effect re-runs and paints it. Always-true cost on desktop is nil
  // (hex is in the initial style there and this just stays false).
  const [hexReady, setHexReady] = useState(false);
  const hexAddedRef = useRef(false);

  // Load placeholder state summary
  useEffect(() => {
    fetch(MEDICAID_MAP_CONFIG.stateSummaryUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((j: StateSummary) => setSummary(j))
      .catch((e) => setError(String(e)));
  }, []);

  // Listen for external state-selection events from the find-your-state CTA.
  useEffect(() => {
    const onSelect = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail && typeof detail.fips === "string") {
        setSelectedStateFips(detail.fips);
      }
    };
    window.addEventListener("medicaid-select-state", onSelect);
    return () => window.removeEventListener("medicaid-select-state", onSelect);
  }, []);

  // Initialize MapLibre — our state polygons ARE the map (no raster basemap)
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    registerPMTilesProtocol();

    // `lite` (touch-primary) also drives cooperativeGestures: one-finger
    // vertical scroll passes through to the page instead of panning the map.
    // Two-finger drag still pans; pinch still zooms. Desktop (mouse) is
    // unchanged — plain wheel scroll still zooms the map directly.
    let map: any;
    try {
      const defaultMode = MEDICAID_MAP_CONFIG.defaultMode;
      map = new maplibregl.Map({
        container: mapContainer.current,
        cooperativeGestures: lite,
        style: {
          version: 8,
          glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
          sources: {
            "carto-base": {
              type: "raster",
              tiles: MEDICAID_MAP_CONFIG.basemapTiles,
              tileSize: 256,
              attribution: MEDICAID_MAP_CONFIG.basemapAttribution,
            } as any,
            "carto-labels": {
              type: "raster",
              tiles: MEDICAID_MAP_CONFIG.labelsTiles,
              tileSize: 256,
            } as any,
            states: {
              type: "geojson",
              data: MEDICAID_MAP_CONFIG.statesGeoJsonUrl,
              promoteId: "STATEFP",
            } as any,
            counties: {
              type: "geojson",
              data: MEDICAID_MAP_CONFIG.countiesGeoJsonUrl,
              promoteId: "GEOID",
            } as any,
            // hex5mi is a 57 MB GeoJSON that MapLibre downloads + parses in
            // full the instant the source is added. On touch devices that
            // (×2 with the hero) blows the iOS per-tab memory budget, so we
            // omit it here and add it lazily the first time the reader enters
            // the grid pyramid — the only view where hex is ever visible (in
            // counties mode the repaint effect forces its opacity to 0). See
            // the hex-defer effect below. Desktop keeps it inline, unchanged.
            ...(lite
              ? {}
              : {
                  hex5mi: {
                    type: "geojson",
                    data: MEDICAID_MAP_CONFIG.hex5miGeoJsonUrl,
                    promoteId: "coarse_id",
                  } as any,
                }),
            // 1-mile grid lives on R2 (~100 MB PMTiles). MapLibre handles
            // HTTP Range requests via the pmtiles:// protocol shim above.
            grid: {
              type: "vector",
              url: `pmtiles://${MEDICAID_MAP_CONFIG.gridPmtilesUrl}`,
              promoteId: "cell_id",
            } as any,
          },
          layers: [
            { id: "carto-base", type: "raster", source: "carto-base" } as any,
            {
              id: "states-fill",
              type: "fill",
              source: "states",
              paint: {
                "fill-color": buildFillColor(defaultMode, "states"),
                "fill-opacity": buildFillOpacity(
                  MEDICAID_MAP_CONFIG.statesOpacityStops, null, defaultMode,
                ),
              },
            } as any,
            {
              id: "counties-fill",
              type: "fill",
              source: "counties",
              paint: {
                "fill-color": buildFillColor(defaultMode, "counties"),
                "fill-opacity": buildFillOpacity(
                  MEDICAID_MAP_CONFIG.countiesOpacityStops, null, defaultMode,
                ),
              },
            } as any,
            // hex5mi-fill — omitted on the lite path; added by the hex-defer
            // effect (inserted before medicaid-grid-1mi to preserve z-order).
            ...(lite
              ? []
              : [
                  {
                    id: "hex5mi-fill",
                    type: "fill",
                    source: "hex5mi",
                    paint: {
                      "fill-color": buildFillColor(defaultMode, "hex5mi"),
                      "fill-opacity": buildFillOpacity(
                        MEDICAID_MAP_CONFIG.hex5miOpacityStops, null, defaultMode,
                      ),
                    },
                  } as any,
                ]),
            {
              id: "medicaid-grid-1mi",
              type: "fill",
              source: "grid",
              "source-layer": MEDICAID_MAP_CONFIG.gridSourceLayer,
              minzoom: 8,
              paint: {
                "fill-color": buildFillColor(defaultMode, "grid"),
                "fill-opacity": buildFillOpacity(
                  MEDICAID_MAP_CONFIG.gridOpacityStops, null, defaultMode,
                ),
              },
            } as any,
            {
              id: "counties-outline",
              type: "line",
              source: "counties",
              paint: {
                "line-color": "#94A3B8",
                "line-width": 0.3,
                "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0, 6, 0.3, 9, 0.5],
              },
            } as any,
            {
              id: "states-outline",
              type: "line",
              source: "states",
              paint: {
                "line-color": "#FFFFFF",
                "line-width": 1,
                "line-opacity": ["interpolate", ["linear"], ["zoom"], 4, 1, 7, 0.6, 9, 0.3],
              },
            } as any,
            {
              id: "states-hover-outline",
              type: "line",
              source: "states",
              paint: {
                "line-color": COBALT,
                "line-width": [
                  "case",
                  ["boolean", ["feature-state", "hover"], false], 2.5,
                  ["boolean", ["feature-state", "selected"], false], 2.5,
                  0,
                ],
              },
            } as any,
            // Target-list outlines — render a thick cobalt border on cells
            // the user has added to the target list via shift+click. Width
            // gated on feature-state.targeted.
            {
              id: "counties-target-outline",
              type: "line",
              source: "counties",
              paint: {
                "line-color": "#0A0A8A",
                "line-width": [
                  "case",
                  ["boolean", ["feature-state", "targeted"], false], 3,
                  0,
                ],
              },
            } as any,
            // hex5mi-target-outline — omitted on the lite path; added by the
            // hex-defer effect (before medicaid-grid-1mi-target-outline).
            ...(lite
              ? []
              : [
                  {
                    id: "hex5mi-target-outline",
                    type: "line",
                    source: "hex5mi",
                    paint: {
                      "line-color": "#0A0A8A",
                      "line-width": [
                        "case",
                        ["boolean", ["feature-state", "targeted"], false], 2.5,
                        0,
                      ],
                    },
                  } as any,
                ]),
            {
              id: "medicaid-grid-1mi-target-outline",
              type: "line",
              source: "grid",
              "source-layer": MEDICAID_MAP_CONFIG.gridSourceLayer,
              minzoom: 8,
              paint: {
                "line-color": "#0A0A8A",
                "line-width": [
                  "case",
                  ["boolean", ["feature-state", "targeted"], false], 2.5,
                  0,
                ],
              },
            } as any,
            { id: "carto-labels", type: "raster", source: "carto-labels" } as any,
          ],
        },
        bounds: MEDICAID_MAP_CONFIG.bounds,
        fitBoundsOptions: { padding: 24 },
        minZoom: MEDICAID_MAP_CONFIG.minZoom,
        maxZoom: MEDICAID_MAP_CONFIG.maxZoom,
        attributionControl: false,
        // Enable canvas-level screenshot capture for dev tools + later
        // image export. Small perf cost (one extra GPU copy per frame).
        preserveDrawingBuffer: true,
      } as any);
    } catch (e: any) {
      setError("Map ctor failed: " + (e?.message || String(e)));
      return;
    }

    // Disable double-click-to-zoom. Without this, two quick clicks on
    // adjacent cells are misinterpreted as a dblclick → zoom-in, which
    // breaks the cell-swap flow. Wheel and zoom-control still zoom.
    try { map.doubleClickZoom.disable(); } catch {}
    // Disable box-zoom (shift+drag). We use Shift+click for the target-list
    // toggle, and box-zoom otherwise swallows the shift modifier before our
    // click handler can read it. Wheel and zoom-control still zoom.
    try { map.boxZoom.disable(); } catch {}

    map.on("error", (e: any) => {
      console.error("MapLibre error:", e?.error?.message || e);
    });

    map.on("load", () => {
      try {
        registerHatchImage(map, "hatch-gray", "rgba(80, 80, 80, 0.55)");
        registerHatchImage(map, "hatch-amber", "rgba(180, 120, 20, 0.60)");
        // Gray hatch: the 7 states with NO subject population (did not expand AND
        // not waiver-listed). WI/GA (subject_via_waiver) get NO hatch — they
        // carry real metric data. TN (waiver_listed, not quantified) gets the
        // amber hatch so it reads as "in scope, not modeled," not "unaffected."
        if (!map.getLayer("states-hatch")) {
          map.addLayer(
            {
              id: "states-hatch",
              type: "fill",
              source: "states",
              filter: [
                "all",
                ["==", ["get", "expansion"], false],
                ["!=", ["get", "subject_via_waiver"], true],
                ["!=", ["get", "waiver_listed"], true],
              ],
              paint: { "fill-pattern": "hatch-gray", "fill-opacity": 0.7 },
            },
            "states-outline",
          );
        }
        if (!map.getLayer("states-hatch-waiver")) {
          map.addLayer(
            {
              id: "states-hatch-waiver",
              type: "fill",
              source: "states",
              filter: [
                "all",
                ["==", ["get", "waiver_listed"], true],
                ["!=", ["get", "subject_via_waiver"], true],
              ],
              paint: { "fill-pattern": "hatch-amber", "fill-opacity": 0.55 },
            },
            "states-outline",
          );
        }
      } catch (err) {
        console.warn("Hatch layer setup failed:", err);
      }
    });

    let lastHover: string | null = null;
    map.on("mousemove", "states-fill", (e: any) => {
      const f = e.features?.[0];
      if (!f) return;
      map.getCanvas().style.cursor = "pointer";
      const fips = String(f.id);
      if (lastHover && lastHover !== fips) {
        map.setFeatureState({ source: "states", id: lastHover }, { hover: false });
      }
      map.setFeatureState({ source: "states", id: fips }, { hover: true });
      lastHover = fips;
      setHoverStateFips(fips);
    });
    map.on("mouseleave", "states-fill", () => {
      map.getCanvas().style.cursor = "";
      if (lastHover) {
        map.setFeatureState({ source: "states", id: lastHover }, { hover: false });
        lastHover = null;
      }
      setHoverStateFips("");
    });
    // Clicking the map opens a popup for the topmost feature at the click
    // point — never auto-zoom. Zoom-aware priority (three tiers):
    //   z >= 9  → prefer 1-mile grid cell (sub-county precision)
    //   z >= 5.5 → prefer 5-mile hex
    //   else    → prefer county aggregate
    // State selection is via the sidebar dropdown only.
    map.on("click", (e: any) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: ["medicaid-grid-1mi", "hex5mi-fill", "counties-fill", "states-fill"].filter((l) =>
          map.getLayer(l),
        ),
      });
      if (!features || features.length === 0) {
        setSelectedFeature(null);
        return;
      }
      const grid = features.find((f: any) => f.layer.id === "medicaid-grid-1mi");
      const county = features.find((f: any) => f.layer.id === "counties-fill");
      const hex = features.find((f: any) => f.layer.id === "hex5mi-fill");
      const z = map.getZoom();
      const chosen =
        z >= 9 ? (grid || hex || county) :
        z >= 5.5 ? (hex || county) :
        (county || hex);
      if (!chosen) {
        setSelectedFeature(null);
        return;
      }
      const kind =
        chosen.layer.id === "counties-fill" ? "county" :
        chosen.layer.id === "medicaid-grid-1mi" ? "grid" :
        "hex";
      const lngLat: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      const props = chosen.properties || {};
      // Shift / Cmd+click → toggle this cell in the target list. Don't open
      // a popup (the panel is the surface for selected cells). Regular
      // click → open the popup, no list change.
      const additive =
        e.originalEvent?.shiftKey ||
        e.originalEvent?.metaKey ||
        e.originalEvent?.ctrlKey;
      if (additive) {
        const candidate = targetCellFrom(kind, lngLat, props);
        setTargetList((prev) => {
          const idx = prev.findIndex((c) => c.id === candidate.id);
          if (idx >= 0) {
            return prev.filter((c) => c.id !== candidate.id);
          }
          // Cap at 50 to keep the panel + localStorage sane
          return [...prev, candidate].slice(-50);
        });
        return;
      }
      setSelectedFeature({ kind, lngLat, props });
    });
    map.on("mouseenter", "counties-fill", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "counties-fill", () => {
      map.getCanvas().style.cursor = "";
    });

    mapRef.current = map;
    if (import.meta.env.DEV) (window as any).__medicaidMap = map;

    // Keep the canvas in sync with the container — the map column flexes to
    // match the sidebar height, which can shift after data fetches resolve.
    // MapLibre's internal ResizeObserver sometimes misses these grid-stretch
    // resizes, so observe explicitly and call resize().
    const ro = mapContainer.current
      ? new ResizeObserver(() => {
          try { map.resize(); } catch {}
        })
      : null;
    if (ro && mapContainer.current) ro.observe(mapContainer.current);

    return () => {
      try { ro?.disconnect(); } catch {}
      try { map.remove(); } catch {}
      mapRef.current = null;
    };
  }, []);

  // Threshold semantics changed to percentile in v3 — no per-mode reset needed.
  // The slider's percentile (e.g., 90 = "top 10%") translates to a per-mode,
  // per-primitive cutoff at render time via summary.percentile_cutoffs.

  // Apply the active tour step's params (flyTo + mode + threshold).
  useEffect(() => {
    const map = mapRef.current;
    if (tourStep === null || !map) return;
    const step = TOUR_STEPS[tourStep];
    if (!step) return;
    map.flyTo({ center: step.center, zoom: step.zoom, duration: 2200, essential: true });
    if (step.mode && step.mode !== mode) setMode(step.mode);
    if (step.thresholdPct !== undefined && step.thresholdPct !== null) {
      setThresholdPct(step.thresholdPct);
    }
    // Steps 0-2 tell the story on the county choropleth; step 3 ("Where
    // verification fails hardest") and step 4 ("Your state") drop into the
    // 1-mile grid so the burden hot-spots read at street scale.
    setPrimitive(tourStep >= 3 ? "grid" : "counties");
  }, [tourStep]);

  const dismissTour = () => {
    setPrimitive("counties"); // leave the reader on the at-a-glance county view
    setTourStep(null);
  };

  // Lite (touch) path only: lazily add the deferred 57 MB hex5mi source + its
  // fill and target-outline layers the first time the reader enters the grid
  // pyramid. Hex is *only* visible in grid view — counties mode forces its
  // opacity to 0 in the repaint effect — so this is the exact moment it's
  // needed, and a reader who never leaves the county view never pays the cost.
  // The View-as toggle (primitive="grid") and the guided tour's step 3 both
  // trigger it. Guarded addSource/addLayer mirrors NYCPropertyTaxMap; layers
  // insert before their grid counterparts to reproduce the desktop z-order.
  useEffect(() => {
    if (!lite || hexAddedRef.current || primitive !== "grid") return;
    const map = mapRef.current;
    if (!map) return;
    const add = () => {
      if (hexAddedRef.current) return;
      try {
        if (!map.getSource("hex5mi")) {
          map.addSource("hex5mi", {
            type: "geojson",
            data: MEDICAID_MAP_CONFIG.hex5miGeoJsonUrl,
            promoteId: "coarse_id",
          } as any);
        }
        if (!map.getLayer("hex5mi-fill")) {
          map.addLayer(
            {
              id: "hex5mi-fill",
              type: "fill",
              source: "hex5mi",
              paint: {
                "fill-color": buildFillColor(mode, "hex5mi"),
                "fill-opacity": buildFillOpacity(
                  MEDICAID_MAP_CONFIG.hex5miOpacityStops, null, mode,
                ),
              },
            } as any,
            map.getLayer("medicaid-grid-1mi") ? "medicaid-grid-1mi" : undefined,
          );
        }
        if (!map.getLayer("hex5mi-target-outline")) {
          map.addLayer(
            {
              id: "hex5mi-target-outline",
              type: "line",
              source: "hex5mi",
              paint: {
                "line-color": "#0A0A8A",
                "line-width": [
                  "case",
                  ["boolean", ["feature-state", "targeted"], false], 2.5,
                  0,
                ],
              },
            } as any,
            map.getLayer("medicaid-grid-1mi-target-outline")
              ? "medicaid-grid-1mi-target-outline"
              : undefined,
          );
        }
        hexAddedRef.current = true;
        // Re-run the repaint effect so hex picks up the live mode/threshold and
        // the counties-only/grid-pyramid opacity branching.
        setHexReady(true);
      } catch (e) {
        console.warn("Deferred hex5mi add failed:", e);
      }
    };
    if (map.isStyleLoaded()) add();
    else map.once("idle", add);
  }, [lite, primitive, mode]);

  // Repaint when mode/primitive/threshold changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    // Compute the active cutoff value per primitive from percentile_cutoffs.
    // Returns null only when the data hasn't loaded yet OR the slider is at
    // its minimum (top 50% — i.e., everything passes).
    const cutoffFor = (m: MedicaidMapMode, prim: "counties" | "hex5mi" | "grid"): number | null => {
      if (thresholdPct <= 50) return null;
      const pcts = summary?.percentile_cutoffs?.[m]?.[prim];
      if (!pcts) return null;
      const available = Object.keys(pcts).map(Number).sort((a, b) => a - b);
      if (available.length === 0) return null;
      const nearest = available.reduce((prev, curr) =>
        Math.abs(curr - thresholdPct) < Math.abs(prev - thresholdPct) ? curr : prev,
      );
      return pcts[String(nearest)];
    };
    const apply = () => {
      const countiesCutoff = cutoffFor(mode, "counties");
      const hexCutoff = cutoffFor(mode, "hex5mi");
      const gridCutoff = cutoffFor(mode, "grid");

      // View As toggle controls layer visibility:
      //   primitive === "counties" → counties only, at all zooms (low-res mode)
      //   primitive === "grid"     → zoom-pyramid (counties low → hex mid → grid high)
      // The default is "counties" so the page lands on the simpler aggregate.
      const countiesOnly = primitive === "counties";
      // When counties-only, override the fade-out and keep counties visible
      // all the way through high zoom at a constant opacity.
      const countiesStops = countiesOnly
        ? ([2, 0, 3, 0.35, 14, 0.35] as number[])
        : MEDICAID_MAP_CONFIG.countiesOpacityStops;

      if (map.getLayer("states-fill")) {
        map.setPaintProperty("states-fill", "fill-color", buildFillColor(mode, "states"));
        map.setPaintProperty(
          "states-fill",
          "fill-opacity",
          buildFillOpacity(MEDICAID_MAP_CONFIG.statesOpacityStops, countiesCutoff, mode),
        );
      }
      if (map.getLayer("counties-fill")) {
        map.setPaintProperty("counties-fill", "fill-color", buildFillColor(mode, "counties"));
        map.setPaintProperty(
          "counties-fill",
          "fill-opacity",
          buildFillOpacity(countiesStops, countiesCutoff, mode),
        );
      }
      if (map.getLayer("hex5mi-fill")) {
        map.setPaintProperty("hex5mi-fill", "fill-color", buildFillColor(mode, "hex5mi"));
        // Force hidden in counties-only mode; normal zoom-pyramid otherwise.
        map.setPaintProperty(
          "hex5mi-fill",
          "fill-opacity",
          countiesOnly ? 0 : buildFillOpacity(MEDICAID_MAP_CONFIG.hex5miOpacityStops, hexCutoff, mode),
        );
      }
      if (map.getLayer("medicaid-grid-1mi")) {
        map.setPaintProperty("medicaid-grid-1mi", "fill-color", buildFillColor(mode, "grid"));
        map.setPaintProperty(
          "medicaid-grid-1mi",
          "fill-opacity",
          countiesOnly ? 0 : buildFillOpacity(MEDICAID_MAP_CONFIG.gridOpacityStops, gridCutoff, mode),
        );
      }
    };
    if (map.isStyleLoaded()) apply();
    // "idle" (not "load"): load fires once at init and never again, so a deferred
    // apply during a transient unloaded window (e.g. mid-flyTo) would be dropped
    // and the layer would desync from state. "idle" fires on every settle.
    else map.once("idle", apply);
    // hexReady: when the lite path adds hex5mi late, re-run so the new layer
    // gets the live mode/primitive/threshold paint instead of its placeholder.
  }, [mode, primitive, thresholdPct, summary?.percentile_cutoffs, hexReady]);

  // Sync "selected" feature-state when picker changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !summary) return;
    const apply = () => {
      summary.states.forEach((s) => {
        map.setFeatureState(
          { source: "states", id: s.state_fips },
          { selected: s.state_fips === selectedStateFips },
        );
      });
    };
    if (map.isStyleLoaded()) apply();
    // "idle" (not "load"): load fires once at init and never again, so a deferred
    // apply during a transient unloaded window (e.g. mid-flyTo) would be dropped
    // and the layer would desync from state. "idle" fires on every settle.
    else map.once("idle", apply);
  }, [selectedStateFips, summary]);

  // Sync "targeted" feature-state with the targetList. Drives the cobalt
  // outline on the three -target-outline line layers. Each entry's id is
  // prefixed by kind ("c:GEOID", "h:coarse_id", "g:cell_id"); strip the
  // prefix and route to the right source + source-layer so MapLibre can
  // match feature-state by promoteId. We track the previous set in a ref so
  // a removal can clear feature-state on the cell that just dropped out.
  const prevTargetedRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const parseId = (
        listId: string,
      ): { feat: { source: string; sourceLayer?: string; id: string | number } } | null => {
        const idx = listId.indexOf(":");
        if (idx < 0) return null;
        const kind = listId.slice(0, idx);
        const rawId = listId.slice(idx + 1);
        // Coerce numeric strings so the match works whether promoteId
        // returned a number (vector tile decoder default) or a string.
        const id: string | number = /^-?\d+$/.test(rawId) ? Number(rawId) : rawId;
        if (kind === "c") return { feat: { source: "counties", id } };
        if (kind === "h") return { feat: { source: "hex5mi", id } };
        if (kind === "g")
          return {
            feat: {
              source: "grid",
              sourceLayer: MEDICAID_MAP_CONFIG.gridSourceLayer,
              id,
            },
          };
        return null;
      };
      const newIds = new Set(targetList.map((c) => c.id));
      // Clear cells that were targeted but no longer are.
      prevTargetedRef.current.forEach((listId) => {
        if (newIds.has(listId)) return;
        const parsed = parseId(listId);
        if (!parsed) return;
        try {
          map.removeFeatureState(parsed.feat as any, "targeted");
        } catch {
          /* tile not loaded or feature evicted — silently ignore */
        }
      });
      // Set targeted=true on every current entry (idempotent).
      newIds.forEach((listId) => {
        const parsed = parseId(listId);
        if (!parsed) return;
        try {
          map.setFeatureState(parsed.feat as any, { targeted: true });
        } catch {
          /* tile not yet loaded — feature-state will be applied when it streams in */
        }
      });
      prevTargetedRef.current = newIds;
    };
    if (map.isStyleLoaded()) apply();
    // "idle" (not "load"): load fires once at init and never again, so a deferred
    // apply during a transient unloaded window (e.g. mid-flyTo) would be dropped
    // and the layer would desync from state. "idle" fires on every settle.
    else map.once("idle", apply);
  }, [targetList]);

  // Render the click popup. Tear down + rebuild on selectedFeature change.
  const popupRef = useRef<any>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (popupRef.current) {
      try { popupRef.current.remove(); } catch {}
      popupRef.current = null;
    }
    if (!selectedFeature) return;
    const { kind, lngLat, props } = selectedFeature;
    const pop = Number(props.total_pop ?? 0);
    const subj = Number(props.subject_count_strict ?? 0);
    const rate = Number(props.subject_rate ?? 0);
    const burden = Number(props.burden_index_centered ?? 0);
    const loss = Number(props.loss_exposure_strict ?? 0);
    const exp = props.expansion === true || props.expansion === "true";
    // Subject via a sized 1115-waiver slice (WI/GA) vs. listed-but-not-quantified
    // (TN). subjectViaWaiver counties carry real metric data; show the normal body
    // with a waiver note. waiverListed-only (TN) shows a flagged "not quantified".
    const subjectViaWaiver =
      props.subject_via_waiver === true || props.subject_via_waiver === "true";
    const waiverListed =
      props.waiver_listed === true || props.waiver_listed === "true";
    const inScope = exp || subjectViaWaiver;

    const title =
      kind === "county"
        ? `${props.county_name || props.GEOID}, ${props.state_abbr || ""}`.replace(/, $/, "")
        : kind === "grid"
          ? buildGridLabel(props as Record<string, unknown>)
          : (() => {
              // Hex cells haven't been migrated to the Tier A/B/C/D place fields;
              // they still use the legacy nearest_place_name.
              const place = props.nearest_place_name as string | undefined;
              const placeState = props.nearest_place_state as string | undefined;
              const county = props.parent_county_name as string | undefined;
              const countyState = props.parent_state_abbr as string | undefined;
              if (place && place.length > 0) {
                return `Near ${place}, ${placeState || countyState || ""}`.replace(/, $/, "");
              }
              return `5-mi cell, ${county || "—"} County, ${countyState || ""}`.replace(/, $/, "");
            })();

    const countyContext =
      (kind === "hex" || kind === "grid") && props.parent_county_name
        ? `<div style="margin-top:2px;color:#64748b;font-size:11px;">${kind === "grid" ? "1-mi cell · " : "5-mi cell · "}${props.parent_county_name} County, ${props.parent_state_abbr || ""}</div>`
        : "";

    // Total population row — shown above the headline metric so the reader
     // can size the subject pool against the cell/county footprint. Falls
     // back to a dash if the bake didn't attach a total_pop (rare).
    const popRow = pop > 0
      ? `
          <span style="color:#64748b;">Total population:</span>
          <span style="font-variant-numeric:tabular-nums;">${fmtFull(pop)}</span>
        `
      : "";

    // Waiver footnote shown under the metric grid for WI/GA counties. GA's
    // loss reads 0 (already work-conditional); WI carries a modeled estimate.
    const waiverNote = subjectViaWaiver
      ? `<div style="margin-top:6px;color:#a16207;font-size:11px;line-height:1.45;">Subject via a Section 1115 waiver, not ACA expansion${loss <= 0 ? " — already work-conditional, so no net-new loss is modeled" : ""}.</div>`
      : "";

    const body = !inScope
      ? `
        ${pop > 0 ? `
          <div style="margin-top:6px;display:grid;grid-template-columns:auto 1fr;gap:4px 10px;font-size:11.5px;">
            <span style="color:#64748b;">Total population:</span>
            <span style="font-variant-numeric:tabular-nums;">${fmtFull(pop)}</span>
          </div>
        ` : ""}
        <div style="margin-top:6px;color:#a16207;font-size:11.5px;line-height:1.45;">${
          waiverListed
            ? "Reached only through TennCare's 1115 parent/caretaker group (~17.7K to 100% FPL) — and OBBBA exempts parents of a child under 14, so virtually none are actually subject. Flagged, not modeled."
            : "Non-expansion state with no subject population — the OBBBA work requirement doesn't reach this state."
        }</div>
      `
      : `
        <div style="margin-top:6px;display:grid;grid-template-columns:auto 1fr;gap:4px 10px;font-size:11.5px;">
          ${popRow}
          <span style="color:#64748b;">Subject to verification:</span>
          <span style="font-family:'Source Serif 4',serif;font-weight:600;color:#1F1FD6;font-variant-numeric:tabular-nums;">${fmtFull(subj)}</span>
          <span style="color:#64748b;">% of working-age adults:</span>
          <span style="font-variant-numeric:tabular-nums;">${(rate * 100).toFixed(1)}%</span>
          <span style="color:#64748b;">Projected loss by 2034:</span>
          <span style="font-variant-numeric:tabular-nums;">${fmtFull(loss)}</span>
          <span style="color:#64748b;">Burden index:</span>
          <span style="font-variant-numeric:tabular-nums;">${burden > 0 ? "+" : ""}${burden.toFixed(1)} ${burden > 0 ? "above" : burden < 0 ? "below" : "at"} national median</span>
        </div>
        ${waiverNote}
      `;

    // Methodology link inline at the bottom of the popup. Anchors to the
    // section of METHODOLOGY.md that explains how this primitive is derived.
    const methDisclosureId =
      kind === "county" ? "map.county_apportionment" :
      kind === "grid" ? "map.grid_within_county" :
      "map.hex_within_county";
    // Scroll-to-anchor in the gizmo page rather than the external GitHub URL
    // (which 404s for un-pushed METHODOLOGY.md). The H2 "Methodology" section
    // gets an id="methodology" via GizmoPage's h2 slug override.
    const methLink = inScope
      ? `<a href="#methodology" style="display:inline-flex;align-items:center;gap:4px;margin-top:8px;font-size:10.5px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;color:#1F1FD6;text-decoration:none;"><span>ⓘ</span><span>How this estimate was derived</span><span>→</span></a>`
      : "";

    const html = `
      <div style="font-family:'Source Sans 3','Inter',system-ui,sans-serif;min-width:240px;max-width:280px;">
        <div style="font-family:'Source Serif 4',serif;font-size:14px;font-weight:600;color:#0F172A;line-height:1.2;">
          ${title}
        </div>
        ${countyContext}
        ${body}
        ${methLink}
      </div>
    `;

    popupRef.current = new maplibregl.Popup({
      // false — popup persists when the user clicks another cell, so the
      // swap is instantaneous via our own click handler instead of a
      // flash-close-then-reopen. Empty-map clicks and the X button still
      // dismiss explicitly (via setSelectedFeature(null) in the handler /
      // popup.on("close") below).
      closeOnClick: false,
      closeButton: true,
      maxWidth: "320px",
      offset: 8,
    })
      .setLngLat(lngLat)
      .setHTML(html)
      .addTo(map);

    // When user closes via the X, clear React state too
    popupRef.current.on("close", () => {
      setSelectedFeature(null);
    });

    return () => {
      try { popupRef.current?.remove(); } catch {}
      popupRef.current = null;
    };
  }, [selectedFeature]);

  // Fly to selected state — or back to all-CONUS when cleared
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!selectedStateFips) {
      map.fitBounds(MEDICAID_MAP_CONFIG.bounds, { padding: 24, duration: 900 });
      return;
    }
    const bounds = STATE_BOUNDS[selectedStateFips];
    if (bounds) map.fitBounds(bounds, { padding: 80, duration: 900 });
  }, [selectedStateFips]);

  const selectedState = useMemo<StateRow | null>(() => {
    if (!summary || !selectedStateFips) return null;
    return summary.states.find((s) => s.state_fips === selectedStateFips) ?? null;
  }, [summary, selectedStateFips]);

  const hoverState = useMemo<StateRow | null>(() => {
    if (!summary || !hoverStateFips) return null;
    return summary.states.find((s) => s.state_fips === hoverStateFips) ?? null;
  }, [summary, hoverStateFips]);

  const topStates = useMemo(() => {
    if (!summary) return [];
    const cfg = MEDICAID_MAP_CONFIG.modes[mode];
    const prop = cfg.property as keyof StateRow;
    return [...summary.states]
      .filter((s) => Number(s[prop]) > 0)
      .sort((a, b) => Number(b[prop]) - Number(a[prop]))
      .slice(0, 10);
  }, [summary, mode]);

  const daysToEffective = daysUntil(MEDICAID_MAP_CONFIG.effectiveDate);

  const headlineCount = selectedState
    ? selectedState.subject_count_strict
    : summary?.national.subject_count_strict ?? 0;
  const headlineLoss = selectedState
    ? selectedState.loss_exposure_strict
    : summary?.national.loss_exposure_strict ?? 0;

  // Animated count-up — NPE pattern, 600ms cubic ease-out
  const animatedCount = useCountUp(headlineCount);
  const animatedLoss = useCountUp(headlineLoss);

  // Editorial frame — "These [N] people in [State] are about to lose Medicaid"
  // National: "These 5 Million People Are About to Lose Medicaid" (the headline).
  // State: dynamic with the state's projected loss number.
  const primaryHeadline = selectedState
    ? `These ${fmtCompact(headlineLoss)} people in ${selectedState.state_name} are about to lose Medicaid`
    : "These 5 Million People Are About to Lose Medicaid";
  const primarySubtitle = selectedState
    ? `Of an estimated ${fmtCompact(headlineCount)} subject to verification at each six-month renewal under the OBBBA work requirement (effective December 31, 2026).`
    : "Under the OBBBA Medicaid work requirement, effective December 31, 2026. Here's where they live.";

  // Concentration callout
  const concentrationCopy = useMemo(
    () => concentrationCalloutText(summary?.concentration),
    [summary?.concentration],
  );

  // Threshold (percentile slider). Snaps to baked percentile bins so the
  // visible cutoff matches what the data actually contains. The slider goes
  // 50–99 (showing top 50% down to top 1%).
  const THRESHOLD_PCT_OPTIONS = [50, 67, 75, 80, 85, 90, 95, 97, 99];
  const topPct = 100 - thresholdPct; // "top X%" label

  return (
    <div
      className="medicaid-map-embed-anchor my-10 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
      style={{
        // Break out of the prose container's max-width so the map gets the
        // full viewport. Tasteful margins on big screens via max-w-7xl.
        width: "min(100vw - 1.5rem, 80rem)",
        marginLeft: "calc(50% - min(50vw - 0.75rem, 40rem))",
        marginRight: "calc(50% - min(50vw - 0.75rem, 40rem))",
      }}
    >
      {/* Hero — editorial headline + supporting stats. Use a div not h2 so
          the parent <article class="prose"> doesn't recolor it cobalt. */}
      <div className="bg-cobalt px-6 py-7 text-white sm:px-10 sm:py-9">
        <div className="font-serif text-[clamp(1.75rem,3.6vw,2.8rem)] font-semibold leading-[1.08] text-white">
          {primaryHeadline}
        </div>
        <p className="mt-3 max-w-3xl text-[0.95rem] leading-snug text-white/75">
          {primarySubtitle}
        </p>
        <div className="mt-6 grid grid-cols-1 gap-3 border-t border-white/15 pt-5 sm:grid-cols-3 sm:gap-10">
          <div>
            <div className="text-[10px] font-sans font-semibold uppercase tracking-[0.12em] text-white/60">
              Days until rule takes effect
            </div>
            <div className="mt-1 font-serif text-[1.7rem] font-semibold leading-none tabular-nums">
              {daysToEffective}
            </div>
            <div className="mt-1 text-[11px] text-white/60">to December 31, 2026</div>
          </div>
          <div>
            <div className="flex items-baseline gap-1.5 text-[10px] font-sans font-semibold uppercase tracking-[0.12em] text-white/60">
              <span>{selectedState ? `${selectedState.state_abbr} subject to verification` : "Subject to verification (CBO)"}</span>
              <span className="text-white/70 hover:text-white">
                <MethodologyInfo id="hero_stat.subject" variant="icon" align="left" />
              </span>
            </div>
            <div className="mt-1 font-serif text-[1.7rem] font-semibold leading-none tabular-nums">
              {summary ? fmtCompact(animatedCount) : "—"}
            </div>
            <div className="mt-1 text-[11px] text-white/60">
              {summary && Number.isFinite(headlineCount) ? fmtFull(headlineCount) + " people" : ""}
            </div>
          </div>
          <div>
            <div className="flex items-baseline gap-1.5 text-[10px] font-sans font-semibold uppercase tracking-[0.12em] text-white/60">
              <span>{selectedState ? "Projected coverage loss" : "Projected loss by 2034 (bottom-up; converges with CBO)"}</span>
              <span className="text-white/70 hover:text-white">
                <MethodologyInfo id="hero_stat.loss" variant="icon" align="left" />
              </span>
            </div>
            <div className="mt-1 font-serif text-[1.7rem] font-semibold leading-none tabular-nums">
              {summary ? fmtCompact(animatedLoss) : "—"}
            </div>
            <div className="mt-1 text-[11px] text-white/60">
              {summary && Number.isFinite(headlineLoss) ? fmtFull(headlineLoss) + " people" : ""}
            </div>
          </div>
        </div>
      </div>

      {/* Mobile-only compact controls — state selector + render mode pills.
          Sits above the map so the two most-used controls are reachable
          without scrolling past the 540px map area. Hidden at sm: and up,
          where the right-side sidebar takes over. */}
      <div className="border-t border-slate-200 bg-slate-50 px-4 py-3 md:hidden">
        <div>
          <label className="block font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            State
          </label>
          <select
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-sans text-sm shadow-sm focus:border-cobalt focus:outline-none focus:ring-1 focus:ring-cobalt"
            value={selectedStateFips}
            onChange={(e) => setSelectedStateFips(e.target.value)}
          >
            <option value="">National view</option>
            {summary?.states
              .slice()
              .sort((a, b) => a.state_name.localeCompare(b.state_name))
              .map((s) => (
                <option key={s.state_fips} value={s.state_fips}>
                  {s.state_name}
                  {stateScopeTag(s)}
                </option>
              ))}
          </select>
        </div>
        <div className="mt-3">
          <label className="block font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            Render mode
          </label>
          <div className="mt-1 grid grid-cols-2 gap-1.5">
            {(Object.keys(MEDICAID_MAP_CONFIG.modes) as MedicaidMapMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={
                  "rounded-md px-2 py-1.5 text-left font-sans text-[11px] leading-tight transition " +
                  (mode === m
                    ? "bg-cobalt text-white shadow-sm"
                    : "border border-slate-300 bg-white text-slate-700")
                }
              >
                {MEDICAID_MAP_CONFIG.modes[m].label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Map + sidebar */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr_360px]">
        <div className="relative flex h-[540px] flex-col md:h-[760px]">
          <div ref={mapContainer} className="flex-1" />
          <MedicaidLegend mode={mode} primitive={primitive} disclosureId={MODE_DISCLOSURE_ID[mode]} />
          {/* ⓘ Methods pill, bottom-right of the map. Updates with active mode. */}
          <div className="absolute bottom-3 right-3 z-10">
            <MethodologyInfo id={MODE_DISCLOSURE_ID[mode]} variant="pill" align="right" />
          </div>
          {/* Target list panel — top-right. Shift+click cells to add. */}
          <MedicaidTargetList
            targetList={targetList}
            onRemove={(id) => setTargetList((prev) => prev.filter((c) => c.id !== id))}
            onClear={() => setTargetList([])}
            stateAbbrForExport={selectedState?.state_abbr}
          />

          {/* Auto-tour modal — plays once per browser, localStorage-gated */}
          {tourStep !== null && summary && (
            <div className="pointer-events-none absolute inset-0 flex items-end justify-center px-4 pb-6 sm:items-center sm:justify-start sm:pl-8">
              <div className="pointer-events-auto w-full max-w-md rounded-xl bg-white px-5 py-4 shadow-xl ring-1 ring-slate-200">
                <div className="mb-1 flex items-baseline justify-between">
                  <div className="font-sans text-[10px] font-semibold uppercase tracking-[0.16em] text-cobalt">
                    {tourStep + 1} of {TOUR_STEPS.length}
                  </div>
                  <button
                    onClick={dismissTour}
                    className="font-sans text-[11px] font-semibold uppercase tracking-wider text-slate-400 transition hover:text-slate-700"
                  >
                    Skip tour
                  </button>
                </div>
                <h3 className="font-serif text-xl font-semibold leading-tight text-charcoal">
                  {TOUR_STEPS[tourStep].title}
                </h3>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-600">
                  {TOUR_STEPS[tourStep].body}
                </p>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <button
                    disabled={tourStep === 0}
                    onClick={() => setTourStep((s) => (s !== null && s > 0 ? s - 1 : s))}
                    className="rounded-md px-3 py-1.5 font-sans text-xs font-semibold uppercase tracking-wider text-slate-500 transition hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent"
                  >
                    Back
                  </button>
                  <div className="flex gap-1">
                    {TOUR_STEPS.map((_, i) => (
                      <div
                        key={i}
                        className={
                          "h-1.5 w-1.5 rounded-full transition " +
                          (i === tourStep ? "bg-cobalt" : "bg-slate-300")
                        }
                      />
                    ))}
                  </div>
                  <button
                    onClick={() => {
                      if (tourStep === TOUR_STEPS.length - 1) {
                        dismissTour();
                      } else {
                        setTourStep((s) => (s !== null ? s + 1 : 0));
                      }
                    }}
                    className="rounded-md bg-cobalt px-4 py-1.5 font-sans text-xs font-semibold uppercase tracking-wider text-white shadow-sm transition hover:bg-cobalt/90"
                  >
                    {tourStep === TOUR_STEPS.length - 1 ? "Done" : "Next"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {hoverState && (
            <div className="pointer-events-none absolute left-4 top-4 max-w-[260px] rounded-lg bg-white/95 px-4 py-3 text-sm shadow-md ring-1 ring-slate-200">
              <div className="font-serif text-base font-semibold text-charcoal">
                {hoverState.state_name}
              </div>
              {hoverState.expansion || hoverState.subject_via_waiver ? (
                <>
                  <div className="mt-1 text-xs text-slate-500">Subject to work req</div>
                  <div className="font-serif text-xl font-semibold tabular-nums text-cobalt">
                    {fmtCompact(hoverState.subject_count_strict)}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {fmtPct(hoverState.subject_rate)} of working-age adults
                  </div>
                  {hoverState.subject_via_waiver && (
                    <div className="mt-1 text-xs text-amber-700">
                      Subject via Section 1115 waiver, not ACA expansion
                      {hoverState.already_work_conditional ? " (already work-conditional)" : ""}.
                    </div>
                  )}
                </>
              ) : hoverState.waiver_listed ? (
                <div className="mt-1 text-xs text-amber-700">
                  Reached only through TennCare's 1115 parent/caretaker group, which OBBBA largely
                  exempts (parents of a child under 14) — so virtually no one is actually subject.
                </div>
              ) : (
                <div className="mt-1 text-xs text-slate-600">
                  Has not adopted Medicaid expansion and has no subject 1115-waiver population — the
                  OBBBA work requirement doesn't reach this state.
                </div>
              )}
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 px-5 py-5 md:border-l md:border-t-0 md:max-h-[760px] md:overflow-y-auto">
          {error && (
            <div className="mb-3 rounded bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {error}
            </div>
          )}

          <label className="block font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            State
          </label>
          <select
            className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-sans text-sm shadow-sm focus:border-cobalt focus:outline-none focus:ring-1 focus:ring-cobalt"
            value={selectedStateFips}
            onChange={(e) => setSelectedStateFips(e.target.value)}
          >
            <option value="">National view</option>
            {summary?.states
              .slice()
              .sort((a, b) => a.state_name.localeCompare(b.state_name))
              .map((s) => (
                <option key={s.state_fips} value={s.state_fips}>
                  {s.state_name}
                  {stateScopeTag(s)}
                </option>
              ))}
          </select>

          <label className="mt-5 block font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            Render mode
          </label>
          <div className="mt-1.5 grid grid-cols-2 gap-1.5">
            {(Object.keys(MEDICAID_MAP_CONFIG.modes) as MedicaidMapMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={
                  "rounded-md px-2 py-2 text-left font-sans text-[12px] leading-tight transition " +
                  (mode === m
                    ? "bg-cobalt text-white shadow-sm"
                    : "border border-slate-300 bg-white text-slate-700 hover:border-cobalt/40 hover:bg-slate-50")
                }
              >
                {MEDICAID_MAP_CONFIG.modes[m].label}
              </button>
            ))}
          </div>

          {/* Mode explainer — updates instantly when mode changes */}
          <div className="mt-2.5 rounded-md bg-slate-50 px-3 py-2.5 text-[11.5px] leading-snug text-slate-700">
            <div>{MODE_EXPLAINERS[mode].what}</div>
            <div className="mt-1.5 text-slate-600">
              <strong className="font-semibold text-slate-800">Where it shows up:</strong>{" "}
              {MODE_EXPLAINERS[mode].extreme}
            </div>
            <div className="mt-1.5 italic text-slate-500">{MODE_EXPLAINERS[mode].calc}</div>
          </div>

          <label className="mt-5 block font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            View as
          </label>
          <div className="mt-1.5 grid grid-cols-2 gap-1.5">
            {(["counties", "grid"] as MedicaidMapPrimitive[]).map((p) => (
              <button
                key={p}
                onClick={() => setPrimitive(p)}
                disabled={tourStep !== null}
                className={
                  "rounded-md px-2 py-2 font-sans text-[12px] transition disabled:cursor-not-allowed disabled:opacity-50 " +
                  (primitive === p
                    ? "bg-cobalt text-white shadow-sm"
                    : "border border-slate-300 bg-white text-slate-700 hover:border-cobalt/40 hover:bg-slate-50")
                }
              >
                {p === "counties" ? "Counties" : "1-mile grid"}
              </button>
            ))}
          </div>

          <p className="mt-2 font-sans text-[10.5px] leading-snug text-slate-500">
            <span className="font-semibold text-slate-700">Tip:</span> Counties is the right default for &quot;where will the wave land.&quot;
            Switch to the 1-mile grid to see within-county hot spots once you&apos;ve picked a state.
          </p>

          {/* Replay the guided tour. Hidden while a tour is already running so it
              doesn't collide with the floating tour card. Does NOT clear the
              localStorage "seen" flag — this is an explicit re-launch. */}
          {tourStep === null && (
            <button
              onClick={() => setTourStep(0)}
              className="mt-3 w-full rounded-md border border-cobalt/30 bg-cobalt/5 px-3 py-2 font-sans text-[12px] font-medium text-cobalt transition hover:border-cobalt/50 hover:bg-cobalt/10"
            >
              ↻ Take the guided tour
            </button>
          )}

          {/* Threshold percentile slider — drag right to highlight only the
              top concentration. Cells above the chosen percentile pop at full
              opacity; the rest dim. Always active. Scale-invariant. */}
          <div className="mt-5">
            <div className="flex items-baseline justify-between">
              <label className="block font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                Highlight concentration
              </label>
              <span className="font-sans text-[10px] font-semibold uppercase tracking-wider text-cobalt">
                {thresholdPct <= 50 ? "all cells" : `top ${topPct}%`}
              </span>
            </div>
            <div className="mt-1.5">
              <input
                type="range"
                min={50}
                max={99}
                step={1}
                value={thresholdPct}
                onChange={(e) => setThresholdPct(Number(e.target.value))}
                className="medicaid-threshold-slider w-full"
                style={{
                  WebkitAppearance: "none",
                  appearance: "none",
                  height: "6px",
                  borderRadius: "9999px",
                  background:
                    "linear-gradient(to right, #DBEAFE 0%, #7B9BE0 30%, #1F1FD6 60%, #E69138 100%)",
                }}
              />
              <div className="mt-1 flex items-baseline justify-between text-[11px]">
                <span className="font-sans text-slate-500">all cells</span>
                <span className="font-serif font-semibold tabular-nums text-cobalt">
                  {thresholdPct <= 50 ? "all cells" : `top ${topPct}%`}
                </span>
                <span className="font-sans text-slate-500">top 1%</span>
              </div>
            </div>
          </div>

          {/* Concentration callout — NPE's signature stripe-on-left card */}
          {concentrationCopy && (
            <div
              className="mt-5 rounded-md bg-cobalt/[0.06] px-4 py-3 text-xs leading-relaxed text-slate-700"
              style={{ boxShadow: "inset 4px 0 0 0 #1F1FD6" }}
            >
              {concentrationCopy}
            </div>
          )}

          {selectedState && !selectedState.expansion && (
            <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-xs leading-relaxed text-amber-900">
              {selectedState.subject_via_waiver ? (
                selectedState.already_work_conditional ? (
                  <>
                    <strong>{selectedState.state_name}</strong> did not adopt ACA Medicaid
                    expansion, but is subject to the OBBBA work requirement through its Section 1115
                    waiver ({selectedState.waiver_note || "Pathways to Coverage"}). That program
                    already conditions coverage on 80 hours/month of qualifying activity, so the
                    federal rule adds no net-new procedural loss for current enrollees — the binding
                    requirement is already in force.
                  </>
                ) : (
                  <>
                    <strong>{selectedState.state_name}</strong> did not adopt ACA Medicaid
                    expansion, but its Section 1115 waiver population
                    {selectedState.waiver_note ? ` (${selectedState.waiver_note})` : ""} is subject
                    to the OBBBA work requirement per CMS's June-2026 list. The figures here model
                    that waiver slice, sized from administrative enrollment. Treat them as a
                    projection: there is no state-specific verification-feed data for this population yet.
                  </>
                )
              ) : selectedState.waiver_listed ? (
                <>
                  <strong>{selectedState.state_name}</strong> is on CMS's June-2026 list only through
                  TennCare's 1115 "MEC additions" group — parents/caretaker relatives covered to 100%
                  FPL (~17,700). But OBBBA exempts parents of a child under 14, so almost none of them
                  are actually subject to the requirement. We flag {selectedState.state_name} as
                  in-scope but model no coverage loss.
                </>
              ) : (
                <>
                  <strong>{selectedState.state_name}</strong> has not adopted ACA Medicaid expansion
                  and has no subject 1115-waiver population. The OBBBA work requirement applies
                  specifically to the expansion-adult eligibility group (Category VIII, ages 19-64,
                  ≤138% FPL), which doesn't exist here.
                </>
              )}
              {selectedState.note && (
                <div className="mt-2 italic text-amber-800">{selectedState.note}</div>
              )}
            </div>
          )}

          {selectedState && (
            <a
              href={`https://data.gizmowarehouse.org/medicaid-work-requirements/briefs/medicaid_brief_${selectedState.state_abbr}.pdf`}
              target="_blank"
              rel="noreferrer"
              className="mt-5 flex items-center justify-between rounded-md border border-cobalt/40 bg-cobalt/[0.04] px-3 py-2 text-xs font-semibold text-cobalt transition hover:bg-cobalt/[0.08]"
            >
              <span>Download {selectedState.state_abbr} brief (PDF)</span>
              <span aria-hidden>↓</span>
            </a>
          )}

          <div className="mt-6">
            <div className="flex items-baseline justify-between">
              <div className="font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                Top 10 states
              </div>
              <div className="font-sans text-[10px] text-slate-400">
                {MEDICAID_MAP_CONFIG.modes[mode].legendUnit}
              </div>
            </div>
            <div className="mt-2 space-y-0.5">
              {topStates.map((s, i) => {
                const cfg = MEDICAID_MAP_CONFIG.modes[mode];
                const val = Number(s[cfg.property as keyof StateRow] ?? 0);
                const maxVal = Math.max(
                  ...topStates.map((x) => Number(x[cfg.property as keyof StateRow] ?? 0)),
                );
                const w = maxVal > 0 ? (val / maxVal) * 100 : 0;
                const isSel = s.state_fips === selectedStateFips;
                return (
                  <button
                    key={s.state_fips}
                    onClick={() =>
                      setSelectedStateFips((cur) =>
                        cur === s.state_fips ? "" : s.state_fips,
                      )
                    }
                    className={
                      "group relative block w-full overflow-hidden rounded px-2 py-1 text-left text-xs transition " +
                      (isSel ? "bg-cobalt/10" : "hover:bg-slate-50")
                    }
                  >
                    <div
                      className="absolute inset-y-0 left-0 bg-cobalt/15 transition-all"
                      style={{ width: w + "%" }}
                    />
                    <div className="relative flex items-baseline justify-between gap-2">
                      <span className="font-sans text-slate-600">
                        <span className="inline-block w-5 text-slate-400">{i + 1}.</span>
                        <span className={isSel ? "font-semibold text-cobalt" : ""}>
                          {s.state_name}
                        </span>
                      </span>
                      <span className="font-serif tabular-nums text-slate-800">
                        {mode === "subject_rate" ? fmtPct(val) : fmtCompact(val)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-6 border-t border-slate-200 pt-4 text-[11px] leading-relaxed text-slate-500">
            <strong className="text-slate-700">A note on resolution.</strong>{" "}
            Each cell shows its parent census tract's estimate. Margin of error is inherited,
            not reduced — hex resolution is a display choice, not a measurement choice.{" "}
            <a
              href={METHODOLOGY_DOC_URL}
              target="_blank"
              rel="noreferrer"
              className="text-cobalt underline decoration-cobalt/30 underline-offset-2 hover:decoration-cobalt"
            >
              Read the full methodology
            </a>
            .
          </div>

          {summary?.note && (
            <div className="mt-3 rounded bg-slate-100 px-3 py-2 text-[10px] italic leading-snug text-slate-600">
              {summary.note}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
